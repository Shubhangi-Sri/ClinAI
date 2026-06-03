from __future__ import annotations
"""
LLM Report Generation — ClinAI v2.0
Priority order:
  1. Groq  (free, Llama 3.3 70B, 300-800 tok/s)       ← PRIMARY
  2. Ollama (local, offline, phi3.5 on RTX 2050)        ← OFFLINE FALLBACK
  3. Claude claude-sonnet-4-20250514 (if ANTHROPIC_API_KEY set)          ← LAST RESORT

Get your free Groq key: https://console.groq.com
Add to backend/.env:   GROQ_API_KEY=gsk_xxxxxxxxxxxx
"""

import os, json, logging
from typing import AsyncGenerator, Optional
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("clinicai.report")
router = APIRouter()

# ── Config ────────────────────────────────────────────────────────────────────
GROQ_API_KEY  = os.environ.get("GROQ_API_KEY", "")
GROQ_URL      = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL    = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

OLLAMA_URL    = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL  = os.environ.get("OLLAMA_MODEL", "phi3.5")

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL  = "claude-sonnet-4-20250514"

SYSTEM_PROMPT = """You are ClinAI, an expert clinical documentation AI assistant working in a HIPAA-compliant environment.
Generate precise, comprehensive clinical documents from doctor-patient consultation transcripts.

Strict rules:
- Use ALL-CAPS section headings (SUBJECTIVE, OBJECTIVE, ASSESSMENT, PLAN, etc.)
- Assign ICD-10-CM codes for every diagnosis mentioned
- Rank differential diagnoses by probability with brief clinical reasoning for each
- Provide complete medication dosing: drug name, dose, route, frequency, duration
- Flag any urgent or emergency findings with WARNING:
- Note clinically significant drug interactions or contraindications
- Be thorough but concise — avoid filler text"""


# ── Models ────────────────────────────────────────────────────────────────────
class TranscriptSegment(BaseModel):
    speaker: str
    text: str

class ReportRequest(BaseModel):
    session_id:      str
    transcript:      list[TranscriptSegment]
    report_type:     str = "soap"
    patient_context: Optional[dict] = None
    use_rag:         bool = False


# ── Prompt builder ────────────────────────────────────────────────────────────
def build_user_prompt(transcript_str: str, report_type: str, patient_ctx: str) -> str:
    ctx  = f"\nPATIENT CONTEXT:\n{patient_ctx}\n" if patient_ctx else ""
    base = f"{ctx}\nTRANSCRIPT:\n{transcript_str}\n"

    templates = {
        "soap": (
            "Convert the consultation transcript below into a complete, structured SOAP note.\n\n"
            "Required sections (use ALL-CAPS headings exactly):\n"
            "PATIENT SUMMARY\nCHIEF COMPLAINT\nSUBJECTIVE\nOBJECTIVE\n"
            "ASSESSMENT\nPLAN\nICD-10 CODES\nFOLLOW-UP INSTRUCTIONS\n"
            + base
        ),
        "discharge": (
            "Write a complete hospital discharge summary from the transcript below.\n\n"
            "Required sections (ALL-CAPS headings):\n"
            "ADMISSION DIAGNOSIS\nHOSPITAL COURSE\nDISCHARGE DIAGNOSES\n"
            "DISCHARGE MEDICATIONS\nFOLLOW-UP APPOINTMENTS\nRETURN PRECAUTIONS\n"
            "ACTIVITY RESTRICTIONS\nDIET INSTRUCTIONS\nICD-10 CODES\n"
            + base
        ),
        "referral": (
            "Write a specialist referral letter from the transcript below.\n\n"
            "Required sections (ALL-CAPS headings):\n"
            "REFERRING PHYSICIAN\nPATIENT INFORMATION\nREASON FOR REFERRAL\n"
            "CLINICAL HISTORY\nEXAMINATION FINDINGS\nINVESTIGATIONS PERFORMED\n"
            "CURRENT MEDICATIONS\nURGENCY LEVEL\nSPECIFIC QUESTIONS FOR SPECIALIST\n"
            + base
        ),
    }
    return templates.get(report_type, templates["soap"])


# ── 1. GROQ streaming ─────────────────────────────────────────────────────────
async def _stream_groq(prompt: str, session_id: str) -> AsyncGenerator[str, None]:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens":  2048,
        "temperature": 0.3,
        "stream":      True,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", GROQ_URL, json=payload, headers=headers) as resp:
                if resp.status_code == 401:
                    yield f"data: {json.dumps({'error': 'Invalid Groq API key — check GROQ_API_KEY in .env'})}\n\n"; return
                if resp.status_code == 429:
                    yield f"data: {json.dumps({'error': 'Groq rate limit hit — wait a moment and retry'})}\n\n"; return
                if resp.status_code != 200:
                    err = await resp.aread()
                    yield f"data: {json.dumps({'error': f'Groq {resp.status_code}: {err.decode()[:200]}'})}\n\n"; return

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "): continue
                    raw = line[6:].strip()
                    if raw == "[DONE]": yield "data: [DONE]\n\n"; return
                    try:
                        chunk = json.loads(raw)
                        token = chunk["choices"][0].get("delta", {}).get("content", "")
                        if token:
                            yield f"data: {json.dumps({'text': token, 'session_id': session_id, 'provider': 'groq'})}\n\n"
                        if chunk["choices"][0].get("finish_reason") == "stop":
                            yield "data: [DONE]\n\n"; return
                    except (json.JSONDecodeError, KeyError, IndexError):
                        pass

    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': 'Cannot reach Groq API — check internet connection'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Groq error: {str(e)}'})}\n\n"


# ── 2. OLLAMA streaming ───────────────────────────────────────────────────────
async def _stream_ollama(prompt: str, session_id: str) -> AsyncGenerator[str, None]:
    payload = {
        "model":  OLLAMA_MODEL,
        "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
        "stream": True,
        "options": {"temperature": 0.3, "num_predict": 2048, "num_gpu": 99, "num_thread": 8},
    }
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/generate", json=payload) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    msg  = body.decode()
                    hint = (f"Model '{OLLAMA_MODEL}' not found. Run: ollama pull {OLLAMA_MODEL}"
                            if "model" in msg.lower() else f"Ollama error: {msg[:150]}")
                    yield f"data: {json.dumps({'error': hint})}\n\n"; return

                async for line in resp.aiter_lines():
                    if not line.strip(): continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("response", "")
                        if token:
                            yield f"data: {json.dumps({'text': token, 'session_id': session_id, 'provider': 'ollama'})}\n\n"
                        if chunk.get("done"):
                            yield "data: [DONE]\n\n"; return
                    except json.JSONDecodeError:
                        pass

    except httpx.ConnectError:
        yield f"data: {json.dumps({'error': 'Ollama not running. Run: ollama serve'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': f'Ollama error: {str(e)}'})}\n\n"


# ── 3. CLAUDE streaming ───────────────────────────────────────────────────────
async def _stream_claude(prompt: str, session_id: str) -> AsyncGenerator[str, None]:
    headers = {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    payload = {"model": CLAUDE_MODEL, "max_tokens": 2048, "stream": True,
               "system": SYSTEM_PROMPT, "messages": [{"role": "user", "content": prompt}]}
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", ANTHROPIC_URL, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err = await resp.aread()
                    yield f"data: {json.dumps({'error': f'Claude {resp.status_code}: {err.decode()[:200]}'})}\n\n"; return
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "): continue
                    raw = line[6:].strip()
                    if raw == "[DONE]": yield "data: [DONE]\n\n"; return
                    try:
                        c = json.loads(raw)
                        if c.get("type") == "content_block_delta":
                            tok = c.get("delta", {}).get("text", "")
                            if tok:
                                yield f"data: {json.dumps({'text': tok, 'session_id': session_id, 'provider': 'claude'})}\n\n"
                        elif c.get("type") == "message_stop":
                            yield "data: [DONE]\n\n"; return
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


# ── Smart router: Groq → Ollama → Claude ─────────────────────────────────────
async def _is_groq_available() -> bool:
    if not GROQ_API_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get("https://api.groq.com/openai/v1/models",
                            headers={"Authorization": f"Bearer {GROQ_API_KEY}"})
            return r.status_code == 200
    except Exception:
        return False

async def _is_ollama_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False

async def _smart_stream(prompt: str, session_id: str) -> AsyncGenerator[str, None]:
    # 1. Groq
    if await _is_groq_available():
        logger.info(f"▶ Provider: Groq / {GROQ_MODEL}")
        yield f"data: {json.dumps({'info': f'Groq · {GROQ_MODEL} · 70B parameters'})}\n\n"
        async for chunk in _stream_groq(prompt, session_id):
            yield chunk
        return

    # 2. Ollama
    if await _is_ollama_available():
        logger.info(f"▶ Provider: Ollama / {OLLAMA_MODEL}")
        yield f"data: {json.dumps({'info': f'Ollama · {OLLAMA_MODEL} · offline mode'})}\n\n"
        async for chunk in _stream_ollama(prompt, session_id):
            yield chunk
        return

    # 3. Claude
    if ANTHROPIC_KEY:
        logger.info("▶ Provider: Claude API")
        yield f"data: {json.dumps({'info': 'Claude API · fallback'})}\n\n"
        async for chunk in _stream_claude(prompt, session_id):
            yield chunk
        return

    # Nothing available
    msg = (
        "No LLM configured. Fix options: "
        "1) Add GROQ_API_KEY to backend/.env (free at console.groq.com)  "
        "2) Run: ollama serve  "
        "3) Add ANTHROPIC_API_KEY to backend/.env"
    )
    yield f"data: {json.dumps({'error': msg})}\n\n"


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.post("/generate")
async def generate_report(request: ReportRequest):
    t      = "\n".join(f"{s.speaker}: {s.text}" for s in request.transcript)
    ctx    = json.dumps(request.patient_context) if request.patient_context else ""
    prompt = build_user_prompt(t, request.report_type, ctx)
    return StreamingResponse(
        _smart_stream(prompt, request.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/generate/sync")
async def generate_report_sync(request: ReportRequest) -> dict:
    t      = "\n".join(f"{s.speaker}: {s.text}" for s in request.transcript)
    ctx    = json.dumps(request.patient_context) if request.patient_context else ""
    prompt = build_user_prompt(t, request.report_type, ctx)
    full   = ""
    async for chunk in _smart_stream(prompt, request.session_id):
        if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
            try:
                d = json.loads(chunk[6:])
                if "text"  in d: full += d["text"]
                if "error" in d: raise HTTPException(502, d["error"])
            except json.JSONDecodeError:
                pass
    return {"session_id": request.session_id, "report_type": request.report_type, "content": full}


@router.get("/status")
async def report_status():
    if await _is_groq_available():
        return {"active_provider": "groq",   "model": GROQ_MODEL,   "ready": True,
                "speed": "300-800 tok/s",    "message": f"✅ Groq ready · {GROQ_MODEL}"}
    if await _is_ollama_available():
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
            models = [m["name"] for m in r.json().get("models", [])]
        ok = any(OLLAMA_MODEL in m for m in models)
        return {"active_provider": "ollama", "model": OLLAMA_MODEL, "ready": ok,
                "speed": "15-25 tok/s",      "message": f"✅ Ollama · {OLLAMA_MODEL}" if ok
                          else f"⚠ Run: ollama pull {OLLAMA_MODEL}"}
    if ANTHROPIC_KEY:
        return {"active_provider": "claude", "model": CLAUDE_MODEL, "ready": True,
                "message": "✅ Claude API ready"}
    return {"active_provider": "none", "ready": False,
            "message": "❌ Add GROQ_API_KEY to backend/.env"}