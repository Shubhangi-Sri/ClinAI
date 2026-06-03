# ClinAI — Local Setup Guide

## Folder Structure (create this on your computer)

```
clinicai/                          ← your project root
│
├── clinicai.code-workspace        ← open this in VS Code
├── setup.sh                       ← Mac/Linux: run once to install everything
├── setup.bat                      ← Windows: double-click to install everything
│
├── backend/                       ← Python FastAPI
│   ├── main.py                    ← ✅ provided
│   ├── requirements.txt           ← ✅ provided
│   ├── .env                       ← ✅ provided (add your API keys)
│   ├── .venv/                     ← auto-created by setup script
│   │
│   ├── routers/
│   │   ├── __init__.py            ← create empty file
│   │   ├── health.py              ← ✅ from download: router_health.py → rename
│   │   ├── asr.py                 ← ✅ from download: router_asr.py → rename
│   │   ├── rag.py                 ← ✅ from download: router_rag.py → rename
│   │   ├── report.py              ← ✅ from download: router_report.py → rename
│   │   └── fhir.py                ← ✅ from download: router_fhir.py → rename
│   │
│   ├── middleware/
│   │   ├── __init__.py            ← create empty file
│   │   ├── security.py            ← ✅ from download: middleware_security.py → rename
│   │   └── encryption.py         ← ✅ from download: middleware_encryption.py → rename
│   │
│   └── audit/                     ← auto-created, stores PHI audit logs
│
└── frontend/                      ← React app
    ├── package.json               ← ✅ provided
    ├── public/
    │   └── index.html             ← ✅ provided
    └── src/
        ├── index.js               ← ✅ provided
        ├── App.js                 ← ✅ provided
        └── ClinAI.jsx             ← ✅ from download: ClinAI-frontend.jsx → rename
```

---

## Step-by-Step Setup

### Step 1 — Create folder structure

**Mac/Linux** (open Terminal):
```bash
mkdir -p clinicai/backend/routers clinicai/backend/middleware clinicai/backend/audit
mkdir -p clinicai/frontend/src clinicai/frontend/public
```

**Windows** (open Command Prompt):
```cmd
mkdir clinicai\backend\routers clinicai\backend\middleware clinicai\backend\audit
mkdir clinicai\frontend\src clinicai\frontend\public
```

---

### Step 2 — Copy downloaded files into the right places

| Downloaded file | → Copy to |
|----------------|-----------|
| `ClinAI-frontend.jsx` | `frontend/src/ClinAI.jsx` |
| `backend_main.py` | `backend/main.py` |
| `router_asr.py` | `backend/routers/asr.py` |
| `router_rag.py` | `backend/routers/rag.py` |
| `router_report.py` | `backend/routers/report.py` |
| `router_fhir.py` | `backend/routers/fhir.py` |
| `middleware_security.py` | `backend/middleware/security.py` |
| `middleware_encryption.py` | `backend/middleware/encryption.py` |
| `requirements.txt` | `backend/requirements.txt` |
| `.env` (from this package) | `backend/.env` |
| `package.json` | `frontend/package.json` |
| `index.html` | `frontend/public/index.html` |
| `index.js` | `frontend/src/index.js` |
| `App.js` | `frontend/src/App.js` |
| `clinicai.code-workspace` | `clinicai/clinicai.code-workspace` |

---

### Step 3 — Create empty `__init__.py` files

```bash
# Mac/Linux
touch backend/routers/__init__.py backend/middleware/__init__.py

# Windows (in Command Prompt)
type nul > backend\routers\__init__.py
type nul > backend\middleware\__init__.py
```

---

### Step 4 — Add your API key

Open `backend/.env` in VS Code and replace the placeholder:
```
ANTHROPIC_API_KEY=sk-ant-api03-REPLACE_WITH_YOUR_KEY
```
Get your key from: https://console.anthropic.com → API Keys

The system works in **demo mode** without the other keys (OpenAI, Deepgram, Pinecone).

---

### Step 5 — Run setup script (installs all dependencies)

**Mac/Linux:**
```bash
cd clinicai
chmod +x setup.sh
./setup.sh
```

**Windows:**
Double-click `setup.bat` inside the `clinicai` folder.

---

### Step 6 — Open in VS Code

```bash
code clinicai.code-workspace
```

Or: File → Open Workspace from File → select `clinicai.code-workspace`

---

### Step 7 — Start the app (TWO terminals needed)

In VS Code, open two terminals with **Ctrl+`** (backtick):

**Terminal 1 — Backend:**
```bash
# Mac/Linux
cd backend
source .venv/bin/activate
python main.py

# Windows
cd backend
.venv\Scripts\activate
python main.py
```

You should see:
```
INFO: ClinAI starting on http://localhost:8000
INFO: API docs: http://localhost:8000/api/docs
INFO: Uvicorn running on http://0.0.0.0:8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm start
```

You should see:
```
Compiled successfully!
Local: http://localhost:3000
```

---

### Step 8 — Open in browser

Go to: **http://localhost:3000**

Test the API directly: **http://localhost:8000/api/docs**

---

## Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `python: command not found` | Use `python3` instead of `python` on Mac/Linux |
| `ModuleNotFoundError: No module named 'fastapi'` | Run `source .venv/bin/activate` first, then `python main.py` |
| `Port 3000 already in use` | Kill existing process or press `Y` when npm asks to use another port |
| `Port 8000 already in use` | Change `APP_PORT=8001` in `.env` and update `"proxy"` in `frontend/package.json` |
| `CORS error` in browser | Make sure backend is running on port 8000 before starting frontend |
| `Microphone permission denied` | Click the 🔒 lock in your browser address bar → allow microphone |
| `ANTHROPIC_API_KEY not configured` | Add key to `backend/.env`, restart backend |

---

## Quick Test (without microphone)

Once both servers are running, you can test by clicking **START** — the system will use the mock transcript automatically if ASR keys are not configured, then call Claude to generate a real SOAP note.
