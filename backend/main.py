"""
ClinAI Backend — v2.0
Run: python main.py
Docs: http://localhost:8000/api/docs
"""
from __future__ import annotations
import os, logging, importlib, uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="ClinAI API", version="2.0.0", docs_url="/api/docs", redoc_url="/api/redoc")

# ── CORS — allow all local dev origins ───────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.56.1:3000",  # VirtualBox / VM
        "http://0.0.0.0:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Optional HIPAA middleware ─────────────────────────────────────────────────
try:
    from middleware.security import HIPAASecurityMiddleware, AuditLogMiddleware
    from middleware.encryption import EncryptionMiddleware
    app.add_middleware(HIPAASecurityMiddleware)
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(EncryptionMiddleware)
    logger.info("✅ HIPAA middleware loaded")
except ImportError as e:
    logger.warning(f"⚠️  Middleware skipped (ok in dev): {e}")

# ── Routers ───────────────────────────────────────────────────────────────────
from routers.health import router as health_router
app.include_router(health_router, prefix="/api")
logger.info("✅ health router loaded")

for name, prefix in [
    ("patient", "/api/patient"),   # MUST be before other routers
    ("asr",     "/api/asr"),
    ("rag",     "/api/rag"),
    ("report",  "/api/report"),
    ("fhir",    "/api/fhir"),
]:
    try:
        mod = importlib.import_module(f"routers.{name}")
        app.include_router(mod.router, prefix=prefix)
        logger.info(f"✅ {name} router loaded")
    except ImportError as e:
        logger.warning(f"⚠️  {name} router skipped: {e}")
    except Exception as e:
        logger.error(f"❌ {name} router error: {e}")

@app.get("/")
def root():
    return {"status": "ok", "version": "2.0.0", "docs": "http://localhost:8000/api/docs"}

if __name__ == "__main__":
    port = int(os.environ.get("APP_PORT", 8000))
    logger.info(f"🚀 ClinAI → http://localhost:{port}")
    logger.info(f"📖 Docs  → http://localhost:{port}/api/docs")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, workers=1)