from __future__ import annotations
"""
Patient Management Router — ClinAI v2.0
NO demo data. NO seeding. Starts completely empty.
"""
import os, uuid, sqlite3, logging, json
from datetime import datetime, timezone
from typing import Optional
from contextlib import contextmanager
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("clinicai.patient")
router = APIRouter()

DB_PATH = os.environ.get(
    "CLINICAI_DB",
    os.path.join(os.path.dirname(__file__), "..", "clinicai.db")
)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()

def init_db():
    """Create tables only. Zero data inserted."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patients (
                patient_id  TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                age         INTEGER,
                sex         TEXT,
                phone       TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id           TEXT PRIMARY KEY,
                patient_id   TEXT NOT NULL,
                report_type  TEXT NOT NULL DEFAULT 'soap',
                soap_note    TEXT,
                transcript   TEXT,
                created_at   TEXT NOT NULL,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
            );
        """)
    logger.info(f"✅ DB ready: {DB_PATH}")

# Only init tables — NO seed call
init_db()

class PatientCreate(BaseModel):
    name:  str
    age:   Optional[int] = None
    sex:   Optional[str] = "M"
    phone: Optional[str] = None

class SaveReportRequest(BaseModel):
    patient_id:  str
    report_type: str = "soap"
    soap_note:   str
    transcript:  list = []

def p2d(r): return {"patient_id":r["patient_id"],"name":r["name"],"age":r["age"],"sex":r["sex"],"phone":r["phone"],"created_at":r["created_at"]}
def s2d(r): return {"id":r["id"],"patient_id":r["patient_id"],"report_type":r["report_type"],"soap_note":r["soap_note"],"created_at":r["created_at"]}

@router.get("/list")
def list_patients():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM patients ORDER BY created_at DESC").fetchall()
    return [p2d(r) for r in rows]   # empty list [] if no patients — no demo fallback

@router.post("/create")
def create_patient(data: PatientCreate):
    pid = f"P{uuid.uuid4().hex[:6].upper()}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO patients (patient_id,name,age,sex,phone,created_at) VALUES (?,?,?,?,?,?)",
            (pid, data.name, data.age, data.sex, data.phone, now)
        )
        row = conn.execute("SELECT * FROM patients WHERE patient_id=?", (pid,)).fetchone()
    logger.info(f"New patient: {pid} {data.name}")
    return p2d(row)

@router.get("/history/{patient_id}")
def get_history(patient_id: str):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE patient_id=? ORDER BY created_at DESC", (patient_id,)
        ).fetchall()
    return [s2d(r) for r in rows]

@router.post("/save-report")
def save_report(data: SaveReportRequest):
    sid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sessions (id,patient_id,report_type,soap_note,transcript,created_at) VALUES (?,?,?,?,?,?)",
            (sid, data.patient_id, data.report_type, data.soap_note, json.dumps(data.transcript), now)
        )
    return {"status":"saved","session_id":sid,"created_at":now}

@router.get("/{patient_id}")
def get_patient(patient_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
    if not row: raise HTTPException(404, f"Patient {patient_id} not found")
    return p2d(row)

@router.delete("/{patient_id}")
def delete_patient(patient_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE patient_id=?", (patient_id,))
        r = conn.execute("DELETE FROM patients WHERE patient_id=?", (patient_id,))
    if r.rowcount==0: raise HTTPException(404)
    return {"status":"deleted","patient_id":patient_id}