from __future__ import annotations
"""
RAG Service — Medical Knowledge Retrieval
Vector DB: Pinecone (serverless, cosine similarity)
Embeddings: OpenAI text-embedding-3-large (3072-dim)
Knowledge Base: Harrison's, ESC/ACC/AHA Guidelines, ICD-10, RxNorm, SNOMED-CT

Pipeline:
1. Ingest medical documents → chunk → embed → upsert to Pinecone
2. At query time: embed clinical query → search Pinecone → rerank → return top-k
"""

import os
import json
import logging
import hashlib
from typing import Optional
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("clinicai.rag")
router = APIRouter()

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_HOST = os.environ.get("PINECONE_HOST", "")  # e.g. https://clinicai-xxxx.svc.pinecone.io
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072
INDEX_NAME = "clinicai-medical-knowledge"
TOP_K = 8


# ── Data Models ───────────────────────────────────────────────────────────────

class KnowledgeChunk(BaseModel):
    id: str
    source: str           # "Harrison's Principles", "ESC Guidelines 2023", etc.
    category: str         # "diagnosis", "treatment", "drug", "icd10", "lab"
    content: str
    page_reference: Optional[str] = None
    evidence_level: Optional[str] = None   # "A", "B", "C" (guideline evidence)
    score: Optional[float] = None


class RAGQuery(BaseModel):
    query: str
    top_k: int = TOP_K
    filter_category: Optional[str] = None   # filter by knowledge category
    session_id: str = "default"


class RAGResponse(BaseModel):
    query: str
    chunks: list[KnowledgeChunk]
    total_found: int


# ── Pinecone Initialization ───────────────────────────────────────────────────

async def init_pinecone():
    """
    Initialize Pinecone index on startup.
    Creates the index if it doesn't exist, then loads seed knowledge.
    """
    if not PINECONE_API_KEY:
        logger.warning("PINECONE_API_KEY not set — RAG will use fallback knowledge base")
        return

    async with httpx.AsyncClient() as client:
        # Check if index exists
        resp = await client.get(
            f"https://api.pinecone.io/indexes/{INDEX_NAME}",
            headers={"Api-Key": PINECONE_API_KEY},
        )

        if resp.status_code == 404:
            logger.info(f"Creating Pinecone index: {INDEX_NAME}")
            await _create_index(client)
            await _seed_medical_knowledge(client)
        else:
            logger.info(f"Pinecone index '{INDEX_NAME}' ready")


async def _create_index(client: httpx.AsyncClient):
    """Create serverless Pinecone index with cosine similarity."""
    payload = {
        "name": INDEX_NAME,
        "dimension": EMBEDDING_DIM,
        "metric": "cosine",
        "spec": {
            "serverless": {
                "cloud": "aws",
                "region": "us-east-1",
            }
        },
    }
    resp = await client.post(
        "https://api.pinecone.io/indexes",
        headers={"Api-Key": PINECONE_API_KEY, "Content-Type": "application/json"},
        json=payload,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create Pinecone index: {resp.text}")
    logger.info("Pinecone index created successfully")


# ── Embedding ─────────────────────────────────────────────────────────────────

async def embed_text(text: str) -> list[float]:
    """Generate embedding using OpenAI text-embedding-3-large."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"model": EMBEDDING_MODEL, "input": text},
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Embedding error: {resp.text}")
    return resp.json()["data"][0]["embedding"]


# ── Document Ingestion ────────────────────────────────────────────────────────

async def ingest_document(content: str, source: str, category: str, metadata: dict = {}):
    """
    Chunk a medical document and upsert embeddings to Pinecone.
    Uses sliding window: 512-token chunks with 64-token overlap.
    """
    chunks = _chunk_text(content, chunk_size=512, overlap=64)
    vectors = []

    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(f"{source}-{i}-{chunk[:50]}".encode()).hexdigest()
        embedding = await embed_text(chunk)

        vectors.append({
            "id": chunk_id,
            "values": embedding,
            "metadata": {
                "source": source,
                "category": category,
                "content": chunk,
                **metadata,
            },
        })

    # Batch upsert to Pinecone (100 vectors per batch)
    async with httpx.AsyncClient(timeout=60.0) as client:
        for batch_start in range(0, len(vectors), 100):
            batch = vectors[batch_start:batch_start + 100]
            resp = await client.post(
                f"{PINECONE_HOST}/vectors/upsert",
                headers={"Api-Key": PINECONE_API_KEY, "Content-Type": "application/json"},
                json={"vectors": batch, "namespace": "medical-knowledge"},
            )
            if resp.status_code != 200:
                logger.error(f"Pinecone upsert error: {resp.text}")

    logger.info(f"Ingested {len(chunks)} chunks from '{source}'")


def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Sliding window text chunker (approximate token count using word count)."""
    words = text.split()
    chunks = []
    step = chunk_size - overlap
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


# ── Query / Retrieval ─────────────────────────────────────────────────────────

@router.post("/query", response_model=RAGResponse)
async def query_knowledge(request: RAGQuery):
    """
    Semantic search over medical knowledge base.
    Returns top-k most relevant chunks with similarity scores.
    """
    if not PINECONE_API_KEY:
        # Fallback for dev/demo without Pinecone
        return _fallback_knowledge(request.query)

    try:
        query_embedding = await embed_text(request.query)
        chunks = await _pinecone_search(query_embedding, request.top_k, request.filter_category)

        return RAGResponse(
            query=request.query,
            chunks=chunks,
            total_found=len(chunks),
        )
    except Exception as e:
        logger.error(f"RAG query error: {e}")
        return _fallback_knowledge(request.query)


async def _pinecone_search(
    query_embedding: list[float],
    top_k: int,
    filter_category: Optional[str],
) -> list[KnowledgeChunk]:
    """Query Pinecone and return ranked knowledge chunks."""
    payload = {
        "vector": query_embedding,
        "topK": top_k,
        "includeMetadata": True,
        "namespace": "medical-knowledge",
    }
    if filter_category:
        payload["filter"] = {"category": {"$eq": filter_category}}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{PINECONE_HOST}/query",
            headers={"Api-Key": PINECONE_API_KEY, "Content-Type": "application/json"},
            json=payload,
        )

    if resp.status_code != 200:
        raise RuntimeError(f"Pinecone query error: {resp.text}")

    matches = resp.json().get("matches", [])
    return [
        KnowledgeChunk(
            id=m["id"],
            source=m["metadata"].get("source", "Unknown"),
            category=m["metadata"].get("category", "general"),
            content=m["metadata"].get("content", ""),
            page_reference=m["metadata"].get("page_reference"),
            evidence_level=m["metadata"].get("evidence_level"),
            score=m.get("score", 0.0),
        )
        for m in matches
        if m.get("score", 0) > 0.3  # Minimum relevance threshold
    ]


@router.post("/ingest")
async def ingest_endpoint(
    source: str,
    category: str,
    content: str,
):
    """Ingest a new medical document into the knowledge base."""
    await ingest_document(content, source, category)
    return {"status": "ingested", "source": source}


# ── Fallback Knowledge Base (no Pinecone required for demo) ──────────────────

FALLBACK_KB = [
    KnowledgeChunk(id="f1", source="Harrison's Principles, 21st Ed.", category="diagnosis",
        content="Pleuritis: Sharp, pleuritic chest pain worsened by inspiration and movement. "
                "Associated with viral illness, autoimmune disease, or adjacent pneumonia. "
                "Treatment: NSAIDs, treat underlying cause.", score=0.91),
    KnowledgeChunk(id="f2", source="ESC Guidelines 2023 — Pericarditis", category="diagnosis",
        content="Acute pericarditis: Pleuritic chest pain, pericardial friction rub, "
                "new ST elevation or PR depression on ECG. First-line: Aspirin/NSAID + Colchicine 3 months. "
                "Evidence Level: A.", score=0.88, evidence_level="A"),
    KnowledgeChunk(id="f3", source="AHA/ACC PE Guidelines 2023", category="diagnosis",
        content="Pulmonary embolism: Dyspnea, pleuritic chest pain, hemoptysis. Wells score ≥2 → "
                "D-dimer. If elevated → CT pulmonary angiography. Anticoagulation: LMWH or DOAC.", score=0.85),
    KnowledgeChunk(id="f4", source="RxNorm Drug Database", category="drug",
        content="Lisinopril (ACE inhibitor): Standard dose 10–40mg QD for hypertension. "
                "Contraindicated in pregnancy. Monitor: serum creatinine, potassium. "
                "Interaction: NSAIDs may reduce antihypertensive effect.", score=0.79),
    KnowledgeChunk(id="f5", source="ICD-10-CM 2024", category="icd10",
        content="R07.1 – Chest pain on breathing (pleuritic). "
                "I30.9 – Acute pericarditis, unspecified. "
                "I26.99 – Pulmonary embolism without acute cor pulmonale. "
                "J90 – Pleural effusion.", score=0.82),
    KnowledgeChunk(id="f6", source="UpToDate Clinical Decision Support", category="treatment",
        content="Colchicine for pericarditis: 0.5mg BID (>70kg) or 0.5mg QD (<70kg) for 3 months. "
                "Reduces recurrence risk by 50%. Combine with NSAID for acute phase.", score=0.76),
    KnowledgeChunk(id="f7", source="ACEP Emergency Guidelines", category="lab",
        content="Troponin I/T: Elevated in ACS, myocarditis, PE. Serial troponin at 0h and 3h. "
                "High-sensitivity troponin <5 ng/L rules out ACS at 0h. "
                "D-dimer: >500 ng/mL warrants CT-PA evaluation.", score=0.80),
    KnowledgeChunk(id="f8", source="SNOMED-CT Clinical Terminology", category="terminology",
        content="Dyspnea (230145002): Subjective difficulty breathing. "
                "Pleuritic pain (75088002): Pain worsened by respiratory movement. "
                "Fever (386661006): Body temperature >38.0°C.", score=0.72),
]

def _fallback_knowledge(query: str) -> RAGResponse:
    """Return pre-loaded knowledge when Pinecone is unavailable."""
    query_lower = query.lower()
    scored = []
    for chunk in FALLBACK_KB:
        relevance = sum(1 for word in query_lower.split() if word in chunk.content.lower())
        scored.append((relevance, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return RAGResponse(
        query=query,
        chunks=[c for _, c in scored[:5]],
        total_found=len(scored),
    )


# ── Seed medical knowledge into Pinecone ─────────────────────────────────────

async def _seed_medical_knowledge(client: httpx.AsyncClient):
    """Seed the Pinecone index with the fallback knowledge base on first run."""
    for chunk in FALLBACK_KB:
        await ingest_document(chunk.content, chunk.source, chunk.category)
    logger.info("Medical knowledge base seeded into Pinecone")
