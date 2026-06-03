from __future__ import annotations
"""
ASR Router — Speech-to-Text
Primary:  OpenAI Whisper (whisper-1) for accuracy + medical vocabulary
Fallback: Deepgram Nova-2-Medical (real-time streaming)

Supports:
- File upload transcription (POST /api/asr/transcribe)
- Real-time WebSocket streaming (WS /api/asr/stream)
- Speaker diarization (Doctor / Patient labeling)
- Medical term post-processing
"""

import os
import io
import json
import asyncio
import logging
import tempfile
from typing import AsyncGenerator

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("clinicai.asr")
router = APIRouter()

WHISPER_API_URL = "https://api.openai.com/v1/audio/transcriptions"
DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_STREAM_URL = "wss://api.deepgram.com/v1/listen"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")

# Medical vocabulary prompt for Whisper — dramatically improves clinical term accuracy
MEDICAL_PROMPT = (
    "Medical consultation transcript. Terms: troponin, creatinine, lisinopril, "
    "metformin, pleuritis, pericarditis, dyspnea, tachycardia, bradycardia, "
    "myocardial infarction, pulmonary embolism, D-dimer, CT-PA, CBC, BMP, "
    "mmHg, bpm, SpO2, ECG, SOAP note, differential diagnosis, ICD-10."
)


class TranscriptSegment(BaseModel):
    speaker: str        # "Doctor" | "Patient" | "Unknown"
    text: str
    start_time: float
    end_time: float
    confidence: float


class TranscriptionResult(BaseModel):
    session_id: str
    segments: list[TranscriptSegment]
    full_text: str
    language: str
    duration_seconds: float
    provider: str       # "whisper" | "deepgram"
    medical_terms_detected: list[str]


# ── File Upload Transcription ─────────────────────────────────────────────────

@router.post("/transcribe", response_model=TranscriptionResult)
async def transcribe_audio(
    file: UploadFile = File(...),
    session_id: str = "session-001",
    provider: str = "whisper",    # "whisper" | "deepgram" | "auto"
):
    """
    Transcribe an audio file (WAV, MP3, M4A, WebM, OGG).
    Uses Whisper for batch files, Deepgram for streaming/real-time.
    """
    audio_bytes = await file.read()
    logger.info(f"Received audio: {file.filename}, {len(audio_bytes)} bytes, provider={provider}")

    if len(audio_bytes) > 25 * 1024 * 1024:  # 25MB Whisper limit
        raise HTTPException(400, "Audio file exceeds 25MB limit. Split into chunks.")

    if provider in ("whisper", "auto"):
        try:
            return await _transcribe_whisper(audio_bytes, file.filename, session_id)
        except Exception as e:
            logger.warning(f"Whisper failed ({e}), falling back to Deepgram")
            if provider == "auto":
                return await _transcribe_deepgram(audio_bytes, session_id)
            raise

    return await _transcribe_deepgram(audio_bytes, session_id)


async def _transcribe_whisper(
    audio_bytes: bytes, filename: str, session_id: str
) -> TranscriptionResult:
    """OpenAI Whisper with verbose JSON for word-level timestamps + diarization."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            WHISPER_API_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            files={"file": (filename or "audio.wav", audio_bytes, "audio/wav")},
            data={
                "model": "whisper-1",
                "response_format": "verbose_json",
                "timestamp_granularities[]": "segment",
                "language": "en",
                "prompt": MEDICAL_PROMPT,
            },
        )

    if response.status_code != 200:
        raise HTTPException(502, f"Whisper API error: {response.text}")

    data = response.json()
    segments = _parse_whisper_segments(data.get("segments", []))
    full_text = data.get("text", "")

    return TranscriptionResult(
        session_id=session_id,
        segments=segments,
        full_text=full_text,
        language=data.get("language", "en"),
        duration_seconds=data.get("duration", 0.0),
        provider="whisper",
        medical_terms_detected=_extract_medical_terms(full_text),
    )


def _parse_whisper_segments(raw_segments: list) -> list[TranscriptSegment]:
    """
    Heuristic speaker diarization from Whisper segments.
    In production: use pyannote-audio or AssemblyAI diarization.
    Pattern: Doctor speaks first, short Q-A turns alternate speakers.
    """
    segments = []
    speaker_map = {}
    current_speaker_idx = 0
    speakers = ["Doctor", "Patient"]

    for i, seg in enumerate(raw_segments):
        text = seg.get("text", "").strip()
        if not text:
            continue

        # Simple heuristic: detect question marks → Doctor, statements → Patient
        # Replace with pyannote speaker embeddings in production
        if text.endswith("?") or i % 2 == 0:
            speaker = "Doctor"
        else:
            speaker = "Patient"

        segments.append(TranscriptSegment(
            speaker=speaker,
            text=text,
            start_time=seg.get("start", 0.0),
            end_time=seg.get("end", 0.0),
            confidence=seg.get("avg_logprob", -0.5) + 1,  # normalize
        ))

    return segments


async def _transcribe_deepgram(audio_bytes: bytes, session_id: str) -> TranscriptionResult:
    """
    Deepgram Nova-2-Medical — purpose-built medical ASR model.
    Supports diarization natively via diarize=true.
    """
    params = {
        "model": "nova-2-medical",
        "diarize": "true",
        "punctuate": "true",
        "utterances": "true",
        "language": "en-US",
        "smart_format": "true",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            DEEPGRAM_API_URL,
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "audio/wav",
            },
            params=params,
            content=audio_bytes,
        )

    if response.status_code != 200:
        raise HTTPException(502, f"Deepgram API error: {response.text}")

    data = response.json()
    return _parse_deepgram_response(data, session_id)


def _parse_deepgram_response(data: dict, session_id: str) -> TranscriptionResult:
    """Parse Deepgram utterances with speaker labels into TranscriptSegments."""
    utterances = data.get("results", {}).get("utterances", [])
    segments = []
    # Deepgram speaker IDs: 0 = Doctor (first speaker), 1 = Patient, etc.
    speaker_labels = {0: "Doctor", 1: "Patient"}

    for utt in utterances:
        speaker_id = utt.get("speaker", 0)
        segments.append(TranscriptSegment(
            speaker=speaker_labels.get(speaker_id, f"Speaker {speaker_id}"),
            text=utt.get("transcript", ""),
            start_time=utt.get("start", 0.0),
            end_time=utt.get("end", 0.0),
            confidence=utt.get("confidence", 0.9),
        ))

    channels = data.get("results", {}).get("channels", [{}])
    full_text = channels[0].get("alternatives", [{}])[0].get("transcript", "")
    duration = data.get("metadata", {}).get("duration", 0.0)

    return TranscriptionResult(
        session_id=session_id,
        segments=segments,
        full_text=full_text,
        language="en",
        duration_seconds=duration,
        provider="deepgram",
        medical_terms_detected=_extract_medical_terms(full_text),
    )


# ── Real-time WebSocket Streaming (Deepgram) ──────────────────────────────────

@router.websocket("/stream")
async def stream_transcription(websocket: WebSocket):
    """
    Real-time bidirectional WebSocket:
    Client → sends raw audio chunks (PCM 16kHz mono)
    Server → streams back TranscriptSegments as JSON
    Uses Deepgram streaming API for <300ms latency.
    """
    await websocket.accept()
    logger.info("WebSocket ASR stream opened")

    import websockets  # websockets library for Deepgram WS

    dg_url = (
        f"{DEEPGRAM_STREAM_URL}"
        f"?model=nova-2-medical"
        f"&diarize=true"
        f"&punctuate=true"
        f"&encoding=linear16"
        f"&sample_rate=16000"
        f"&channels=1"
        f"&interim_results=true"
    )

    try:
        async with websockets.connect(
            dg_url,
            extra_headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
        ) as dg_ws:
            async def forward_audio():
                """Client audio → Deepgram."""
                try:
                    while True:
                        audio_chunk = await websocket.receive_bytes()
                        await dg_ws.send(audio_chunk)
                except WebSocketDisconnect:
                    await dg_ws.send(json.dumps({"type": "CloseStream"}))

            async def forward_transcript():
                """Deepgram transcripts → Client."""
                async for message in dg_ws:
                    result = json.loads(message)
                    if result.get("type") == "Results":
                        channel = result["channel"]
                        alt = channel["alternatives"][0]
                        is_final = result.get("is_final", False)
                        speaker = "Doctor" if result.get("channel_index", [0])[0] == 0 else "Patient"

                        segment = {
                            "speaker": speaker,
                            "text": alt.get("transcript", ""),
                            "confidence": alt.get("confidence", 0.0),
                            "is_final": is_final,
                        }
                        await websocket.send_text(json.dumps(segment))

            await asyncio.gather(forward_audio(), forward_transcript())

    except Exception as e:
        logger.error(f"WebSocket ASR error: {e}")
        await websocket.close(code=1011, reason=str(e))


# ── Medical Term Extraction ───────────────────────────────────────────────────

MEDICAL_TERMS = {
    "troponin", "d-dimer", "creatinine", "bmp", "cbc", "ecg", "ekg",
    "ct-pa", "ct scan", "mri", "x-ray", "ultrasound",
    "lisinopril", "metformin", "aspirin", "warfarin", "heparin",
    "pericarditis", "pleuritis", "myocardial infarction", "pulmonary embolism",
    "pneumonia", "sepsis", "hypertension", "diabetes", "tachycardia",
    "dyspnea", "bradycardia", "arrhythmia", "atrial fibrillation",
    "mmhg", "spo2", "bpm", "mg/dl", "ng/ml",
}

def _extract_medical_terms(text: str) -> list[str]:
    text_lower = text.lower()
    return [term for term in MEDICAL_TERMS if term in text_lower]
