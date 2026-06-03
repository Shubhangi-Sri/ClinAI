"""
Run this ONCE from your backend folder to wipe the old database
that has demo patients seeded in it.

Usage:
  cd c:\projects\clinicai\backend
  python reset_db.py
"""
import os, sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "clinicai.db")

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print(f"✅ Deleted old database: {DB_PATH}")
else:
    print(f"ℹ️  No database found at {DB_PATH} — nothing to delete.")

# Re-create clean empty tables
conn = sqlite3.connect(DB_PATH)
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
conn.commit()
conn.close()
print("✅ Fresh empty database created. No demo patients.")
print("   Restart your backend: python main.py")