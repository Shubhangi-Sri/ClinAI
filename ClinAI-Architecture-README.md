# ClinAI — Voice Clinical Documentation System
## Full-Stack Architecture Guide

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLINICAI ARCHITECTURE                        │
│                                                                     │
│  ┌──────────┐    ┌──────────────────────────────────────────────┐  │
│  │ Browser  │    │           FastAPI Backend (Python)            │  │
│  │          │    │                                              │  │
│  │  React   │◄──►│  ┌─────────┐  ┌─────────┐  ┌────────────┐  │  │
│  │  Frontend│    │  │   ASR   │  │   RAG   │  │    LLM     │  │  │
│  │          │    │  │ Router  │  │ Router  │  │   Router   │  │  │
│  └──────────┘    │  └────┬────┘  └────┬────┘  └─────┬──────┘  │  │
│                  │       │            │               │         │  │
│                  │  ┌────▼────┐  ┌───▼─────┐  ┌────▼──────┐  │  │
│                  │  │ Whisper │  │Pinecone │  │  Claude   │  │  │
│                  │  │  +      │  │  VectorDB│  │  claude-sonnet-4-20250514 │  │  │
│                  │  │Deepgram │  │         │  │           │  │  │
│                  │  └─────────┘  └─────────┘  └───────────┘  │  │
│                  │                                              │  │
│                  │  ┌──────────────────────────────────────┐   │  │
│                  │  │          FHIR R4 Router               │   │  │
│                  │  │  Patient | Encounter | Observation    │   │  │
│                  │  │  Condition | MedicationRequest        │   │  │
│                  │  │  DiagnosticReport | Bundle            │   │  │
│                  │  └──────────────┬───────────────────────┘   │  │
│                  │                 │                            │  │
│                  │  ┌──────────────▼───────────────────────┐   │  │
│                  │  │       HIPAA Middleware Stack           │   │  │
│                  │  │  AES-256-GCM │ TLS 1.3 │ Audit Log   │   │  │
│                  │  └─────────────────────────────────────-─┘   │  │
│                  └──────────────────────────────────────────────┘  │
│                                          │                          │
│                               ┌──────────▼─────────┐               │
│                               │   Epic / Cerner     │               │
│                               │   FHIR R4 Server   │               │
│                               └────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. ASR — Automatic Speech Recognition

### Primary: OpenAI Whisper
- **Model**: `whisper-1` (fine-tuned for general + medical English)
- **Endpoint**: `POST https://api.openai.com/v1/audio/transcriptions`
- **Format**: Verbose JSON with segment-level timestamps
- **Medical Vocabulary Prompt**: Pre-injected clinical term list improves accuracy for drug names, diagnoses, lab values
- **Diarization**: Heuristic turn-taking (replace with pyannote-audio for production)

### Fallback: Deepgram Nova-2-Medical
- **Model**: `nova-2-medical` — purpose-built for clinical conversations
- **Features**: Native speaker diarization (`diarize=true`), smart formatting, utterance segmentation
- **Real-time Streaming**: WebSocket endpoint `/api/asr/stream` (PCM 16kHz input, <300ms latency)
- **Use case**: Live streaming during consultation vs. Whisper for post-recording batch

### Production Upgrade Path
```
pyannote/speaker-diarization-3.1  →  true speaker-level diarization
AssemblyAI Universal-2             →  best-in-class medical ASR
Azure Cognitive Services Speech    →  HIPAA BAA available
```

---

## 2. RAG — Retrieval-Augmented Generation

### Vector Database: Pinecone
- **Index**: Serverless, AWS us-east-1, cosine similarity
- **Dimensions**: 3072 (OpenAI `text-embedding-3-large`)
- **Namespace**: `medical-knowledge`

### Knowledge Base Sources
| Source | Category | Chunks |
|--------|----------|--------|
| Harrison's Principles of Internal Medicine | Diagnosis | ~12,000 |
| ESC/ACC/AHA Clinical Guidelines | Treatment | ~8,000 |
| ICD-10-CM 2024 | Codes | ~70,000 |
| RxNorm Drug Database | Pharmacology | ~15,000 |
| SNOMED-CT Clinical Terminology | Terminology | ~350,000 |
| UpToDate Clinical Decision Support | Evidence | ~25,000 |

### Chunking Strategy
- **Chunk size**: 512 tokens (word-based approximation)
- **Overlap**: 64 tokens (prevents context loss at boundaries)
- **Minimum similarity threshold**: 0.30 (filters irrelevant matches)

### Query Pipeline
```
1. Transcript text → first 1000 chars as search query
2. embed_text() → 3072-dim vector (OpenAI text-embedding-3-large)
3. Pinecone similarity search → top-8 chunks
4. Optional category filter (diagnosis | treatment | drug | icd10 | lab)
5. Chunks injected into LLM prompt as RAG context
```

---

## 3. LLM — Report Generation (Claude)

### Model: `claude-sonnet-4-20250514`
- Streaming via SSE (Server-Sent Events)
- 2048 max output tokens
- System prompt: Expert clinical documentation AI

### Report Types
| Type | Prompt Template | Use Case |
|------|----------------|----------|
| `soap` | SOAP Note | Standard consultation documentation |
| `discharge` | Discharge Summary | Hospital discharge |
| `referral` | Referral Letter | Specialist referral |

### Prompt Architecture
```
System: Clinical documentation expert with guideline knowledge
User:
  ├── Transcript (speaker-labeled)
  ├── RAG Context (8 knowledge chunks with sources)
  ├── Patient Context (optional EHR data)
  └── Instruction: Generate [report_type] with ICD-10, differentials, plan
```

---

## 4. FHIR R4 — EHR Integration

### Resources Generated
```
Bundle (Transaction)
├── Patient          ← demographics + MRN
├── Encounter        ← visit metadata (AMB, date, practitioner)
├── Observation[]    ← vitals (BP, HR, SpO₂, Temp) with LOINC codes
├── Condition[]      ← diagnoses with ICD-10-CM codes
├── MedicationRequest[] ← prescriptions with RxNorm codes
└── DiagnosticReport ← full SOAP note as base64 attachment
```

### LOINC Codes Used
| Vital | LOINC |
|-------|-------|
| Blood pressure | 85354-9 |
| Systolic BP | 8480-6 |
| Diastolic BP | 8462-4 |
| Heart rate | 8867-4 |
| SpO₂ | 59408-5 |
| Temperature | 8310-5 |
| SOAP Note | 11488-4 |

### EHR Compatibility
- **Epic**: FHIR R4 + SMART on FHIR OAuth2
- **Cerner Millennium**: FHIR R4 API
- **athenahealth**: FHIR R4
- **Any SMART on FHIR compliant system**

### Authentication: SMART on FHIR
```
1. Register app in EHR developer portal
2. Get client_id + client_secret
3. POST to token endpoint with client_credentials grant
4. Include Bearer token in all FHIR API calls
```

---

## 5. HIPAA Compliance

### Technical Safeguards (§164.312)

#### Encryption at Rest — AES-256-GCM
```python
# Per-record key derivation (HKDF-SHA256)
key = HKDF(master_key, info=f"clinicai-phi-{record_id}")
ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
payload = nonce(12 bytes) + ciphertext + GCM_tag(16 bytes)
```
- Master key stored in AWS KMS / Azure Key Vault
- Envelope encryption: unique key per record
- PHI fields encrypted before database write

#### Encryption in Transit — TLS 1.3
- HSTS header: `max-age=63072000; includeSubDomains; preload`
- HTTP → HTTPS redirect enforced in middleware
- All API keys transmitted via HTTPS only

#### Audit Controls — §164.312(b)
```json
{
  "timestamp": "2024-11-15T10:23:44.123Z",
  "event_type": "PHI_ACCESS",
  "user_id": "dr_smith_001",
  "provider_id": "hosp_main",
  "endpoint": "/api/report/generate",
  "status_code": 200,
  "integrity_hash": "sha256:abc123..."
}
```
- Every PHI-touching endpoint is logged
- SHA-256 integrity hash per entry (tamper detection)
- Logs shipped to SIEM in production (Splunk / CloudWatch)

#### Access Controls — §164.312(a)
- JWT-based authentication (python-jose)
- Role-based access: Provider / Admin / ReadOnly
- MFA via TOTP (pyotp)
- Session timeout: 8 hours

#### Additional Compliance
- Business Associate Agreement (BAA) required with:
  - OpenAI (Whisper) ← BAA available at enterprise tier
  - Deepgram ← HIPAA-compliant, BAA available
  - Anthropic (Claude) ← Enterprise BAA available
  - Pinecone ← HIPAA-compliant, BAA available
  - AWS (KMS, RDS) ← BAA available

---

## 6. Deployment

### Docker Compose
```yaml
services:
  backend:
    build: ./backend
    environment:
      - ANTHROPIC_API_KEY
      - OPENAI_API_KEY
      - DEEPGRAM_API_KEY
      - PINECONE_API_KEY
      - CLINICAI_MASTER_KEY
    volumes:
      - ./certs:/app/certs:ro
      - audit_logs:/app/audit

  frontend:
    build: ./frontend
    environment:
      - REACT_APP_API_URL=https://api.clinicai.internal

  db:
    image: postgres:16
    environment:
      - POSTGRES_DB=clinicai
    volumes:
      - pg_data:/var/lib/postgresql/data
```

### Environment Variables
See `.env.example` for all required variables.

### API Keys Required
| Service | Variable | Get From |
|---------|----------|----------|
| Claude LLM | `ANTHROPIC_API_KEY` | console.anthropic.com |
| Whisper ASR | `OPENAI_API_KEY` | platform.openai.com |
| Deepgram ASR | `DEEPGRAM_API_KEY` | console.deepgram.com |
| Pinecone RAG | `PINECONE_API_KEY` | app.pinecone.io |
| FHIR Server | `FHIR_CLIENT_ID/SECRET` | EHR developer portal |

---

## 7. Project Structure

```
clinicai/
├── backend/
│   ├── main.py                  # FastAPI app + middleware stack
│   ├── requirements.txt
│   ├── .env.example
│   ├── routers/
│   │   ├── asr.py               # Whisper + Deepgram ASR
│   │   ├── rag.py               # Pinecone vector search
│   │   ├── report.py            # Claude LLM generation
│   │   ├── fhir.py              # FHIR R4 bundle builder
│   │   └── health.py            # Service health check
│   ├── middleware/
│   │   ├── security.py          # HIPAA headers + audit log
│   │   └── encryption.py        # AES-256-GCM field encryption
│   └── audit/                   # PHI audit logs (gitignored)
│
└── frontend/
    └── ClinAI-frontend.jsx      # React SPA (all 4 integrations)
```
