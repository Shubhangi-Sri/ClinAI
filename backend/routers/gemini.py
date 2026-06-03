import os
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
GEMINI_STREAM_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse"


class CodeGenRequest(BaseModel):
    prompt: str
    language: str = "python"
    context: str = ""


@router.post("/generate")
async def generate_code(req: CodeGenRequest):
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    system_prompt = (
        "You are an expert " + req.language + " developer. "
        "Generate clean, well-commented, production-ready code only. "
        "Return only the code block, no extra explanation."
    )
    full_prompt = (
        system_prompt + "\n\nContext:\n" + req.context + "\n\nTask:\n" + req.prompt
        if req.context
        else system_prompt + "\n\nTask:\n" + req.prompt
    )

    payload = {"contents": [{"role": "user", "parts": [{"text": full_prompt}]}]}
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(GEMINI_URL, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return {"code": text, "model": "gemini-2.5-flash"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))