# backend/routers/routers.py

import os
import uuid
from datetime import datetime

import google.generativeai as genai
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ─────────────────────────────────────────────
# DB SETUP (LOCAL SQLITE)
# ─────────────────────────────────────────────

from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "sqlite:///./clinicai.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String, primary_key=True, index=True)
    name = Column(String)
    age = Column(Integer)
    sex = Column(String)


class Visit(Base):
    __tablename__ = "visits"

    id = Column(String, primary_key=True, index=True)
    patient_id = Column(String)
    soap_note = Column(Text)
    doctor_pdf = Column(String)
    patient_pdf = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


# ─────────────────────────────────────────────
# ROUTER INIT
# ─────────────────────────────────────────────

router = APIRouter()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))


# ─────────────────────────────────────────────
# PATIENT MODELS
# ─────────────────────────────────────────────

class PatientCreate(BaseModel):
    patient_id: str
    name: str
    age: int
    sex: str


# ─────────────────────────────────────────────
# PATIENT APIs
# ─────────────────────────────────────────────

@router.post("/patient/create")
def create_patient(data: PatientCreate):
    db = SessionLocal()

    existing = db.query(Patient).filter(Patient.patient_id == data.patient_id).first()
    if existing:
        raise HTTPException(400, "Patient already exists")

    patient = Patient(**data.dict())
    db.add(patient)
    db.commit()

    return {"message": "Patient created"}


@router.get("/patient/list")
def list_patients():
    db = SessionLocal()
    return db.query(Patient).all()


@router.get("/patient/history/{patient_id}")
def get_history(patient_id: str):
    db = SessionLocal()
    return db.query(Visit).filter(Visit.patient_id == patient_id).all()


# ─────────────────────────────────────────────
# REPORT STORAGE (SAVE FILES LOCALLY)
# ─────────────────────────────────────────────

SAVE_DIR = "records"
os.makedirs(SAVE_DIR, exist_ok=True)


class SaveReportRequest(BaseModel):
    patient_id: str
    content: str


@router.post("/report/save")
def save_report(req: SaveReportRequest):
    db = SessionLocal()

    visit_id = str(uuid.uuid4())

    doctor_path = f"{SAVE_DIR}/{visit_id}_doctor.txt"
    patient_path = f"{SAVE_DIR}/{visit_id}_patient.txt"

    # Save locally
    with open(doctor_path, "w") as f:
        f.write(req.content)

    with open(patient_path, "w") as f:
        f.write(req.content)

    visit = Visit(
        id=visit_id,
        patient_id=req.patient_id,
        soap_note=req.content,
        doctor_pdf=doctor_path,
        patient_pdf=patient_path
    )

    db.add(visit)
    db.commit()

    return {"message": "Saved", "visit_id": visit_id}


# ─────────────────────────────────────────────
# GEMINI CODE GENERATION (EXISTING)
# ─────────────────────────────────────────────

class CodeGenRequest(BaseModel):
    prompt: str
    language: str = "python"
    context: str = ""


@router.post("/generate")
async def generate_code(req: CodeGenRequest):
    if not os.getenv("GOOGLE_API_KEY"):
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    system_prompt = f"""You are an expert {req.language} developer.
Generate clean, well-commented, production-ready code.
If context is provided, modify or extend it as requested.
Return only the code block, no extra explanation."""

    full_prompt = (
        f"{system_prompt}\n\nContext:\n{req.context}\n\nTask:\n{req.prompt}"
        if req.context else f"{system_prompt}\n\nTask:\n{req.prompt}"
    )

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(full_prompt)
        return {"code": response.text, "model": "gemini-2.5-flash"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate/stream")
async def generate_code_stream(req: CodeGenRequest):

    if not os.getenv("GOOGLE_API_KEY"):
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY not configured")

    system_prompt = f"You are an expert {req.language} developer. Generate clean, production-ready code only."
    full_prompt = f"{system_prompt}\n\nTask:\n{req.prompt}"

    def stream():
        model = genai.GenerativeModel("gemini-2.5-flash")
        for chunk in model.generate_content(full_prompt, stream=True):
            if chunk.text:
                yield chunk.text

    return StreamingResponse(stream(), media_type="text/plain")