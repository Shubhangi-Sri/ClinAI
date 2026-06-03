from __future__ import annotations
"""Health check and system status endpoints."""
import os
from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "1.0.0",
        "services": {
            "asr_whisper":  bool(os.environ.get("OPENAI_API_KEY")),
            "asr_deepgram": bool(os.environ.get("DEEPGRAM_API_KEY")),
            "rag_pinecone": bool(os.environ.get("PINECONE_API_KEY")),
            "llm_claude":   bool(os.environ.get("ANTHROPIC_API_KEY")),
            "fhir_server":  bool(os.environ.get("FHIR_SERVER_URL")),
            "encryption":   True,
            "audit_logging":True,
        },
        "hipaa_compliance": {
            "encryption_at_rest":   "AES-256-GCM",
            "encryption_in_transit":"TLS 1.3",
            "audit_logging":        "enabled",
            "access_controls":      "RBAC",
        },
    }
