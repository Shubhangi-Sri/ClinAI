from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = "sqlite:///./clinicai.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()


# ── TABLES ─────────────────────────────────────

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


def init_db():
    Base.metadata.create_all(bind=engine)