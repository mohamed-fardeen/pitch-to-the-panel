"""
Pitch history embeddings (Tier-1d).

Replaces the legacy `services/db.py` (which used the unmaintained
`vecs` library) with native pgvector via SQLAlchemy for production
and an in-memory cosine-similarity fallback for SQLite / no-DB dev.

Public API (unchanged from the legacy module):
- save_pitch_history(session_id, pitch_summary, verdict_parts, confidence_score)
- retrieve_past_pitches(pitch_summary, top_k=2) -> list[dict]
- format_past_pitches_for_context(past_pitches) -> str

Backend selection:
- DATABASE_URL=postgresql+asyncpg://...  -> pgvector (production)
- DATABASE_URL=sqlite+aiosqlite:///...   -> in-memory fallback
- No DATABASE_URL                       -> in-memory fallback (default)

The in-memory fallback stores embeddings in process memory. They
don't persist across server restarts. That's fine for dev; pgvector
is the real production store.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


# ─── Configuration ────────────────────────────────────────────────

JINA_API_KEY = os.getenv("JINA_API_KEY", "").strip()
EMBEDDING_DIM = int(os.getenv("PANELMIND_EMBEDDING_DIM", "1024"))


def _current_database_url() -> str:
    """Read DATABASE_URL fresh on each call. Used for env-based dispatch."""
    return os.getenv("DATABASE_URL", "").strip()


def _is_postgres() -> bool:
    """True if DATABASE_URL points at Postgres."""
    return _current_database_url().startswith(("postgresql", "postgres"))


# ─── Embedding API ────────────────────────────────────────────────


def _embed_jina(text: str) -> Optional[list[float]]:
    """Call Jina Embeddings API synchronously. Returns None on failure."""
    if not JINA_API_KEY:
        return None
    try:
        url = "https://api.jina.ai/v1/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {JINA_API_KEY}",
        }
        payload = {
            "model": "jina-embeddings-v3",
            "task": "retrieval.passage",
            "dimensions": EMBEDDING_DIM,
            "input": [text[:8000]],
        }
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    except Exception as e:
        logger.warning("[JINA] Embedding failed: %s", e)
        return None


async def _embed_async(text: str) -> Optional[list[float]]:
    """Async wrapper around the Jina embedding call."""
    return await asyncio.to_thread(_embed_jina, text)


# ─── In-memory fallback ────────────────────────────────────────────


@dataclass
class _InMemoryStore:
    """Process-local store for embeddings. Lost on restart."""
    records: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Note: vectors themselves are stored separately for cosine similarity

    def __post_init__(self) -> None:
        if not hasattr(self, "_vectors"):
            self._vectors: dict[str, list[float]] = {}


_store = _InMemoryStore()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0..1."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ─── pgvector backend ──────────────────────────────────────────────


_pgvector_collection = None
_pgvector_initialized = False


async def _ensure_pgvector_table() -> bool:
    """Create the pgvector table if it doesn't exist. Returns False on failure."""
    global _pgvector_collection, _pgvector_initialized
    if _pgvector_initialized:
        return _pgvector_collection is not None

    if not _is_postgres():
        _pgvector_initialized = True
        return False

    try:
        from backend.persistence.database import get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            from sqlalchemy import text
            # Enable the pgvector extension if not already
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Create the pitch_embeddings table
            await conn.execute(text(
                f"""
                CREATE TABLE IF NOT EXISTS pitch_embeddings (
                    id TEXT PRIMARY KEY,
                    embedding vector({EMBEDDING_DIM}) NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ))
            # Create an IVFFlat index for cosine similarity (lists=100 is a
            # common default for datasets under 1M rows)
            try:
                await conn.execute(text(
                    """
                    CREATE INDEX IF NOT EXISTS pitch_embeddings_embedding_idx
                    ON pitch_embeddings
                    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
                    """
                ))
            except Exception:
                # Index creation can fail on small tables; that's OK
                pass
        _pgvector_initialized = True
        _pgvector_collection = "pgvector"  # marker
        logger.info("pgvector extension + pitch_embeddings table ready.")
        return True
    except Exception as e:
        logger.warning("pgvector init failed: %s", e)
        _pgvector_initialized = True
        return False


# ─── Public API ───────────────────────────────────────────────────


async def save_pitch_history(
    session_id: str,
    pitch_summary: str,
    verdict_parts: dict,
    confidence_score: int,
) -> None:
    """Embed a pitch summary and persist it for future similarity search.

    Best-effort: silently does nothing if no embedding API key is
    configured AND no pgvector store is available.
    """
    embedding = await _embed_async(pitch_summary)
    if embedding is None:
        logger.debug("save_pitch_history: no embedding produced, skipping.")
        return

    metadata = {
        "session_id": session_id,
        "pitch_summary": pitch_summary[:1000],
        "strongest": verdict_parts.get("strongest", ""),
        "weakness": verdict_parts.get("weakness", ""),
        "fix": verdict_parts.get("fix", ""),
        "confidence_score": confidence_score,
        "timestamp": int(time.time()),
    }
    doc_id = f"{session_id}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    use_pg = await _ensure_pgvector_table()
    if use_pg:
        await _save_to_pgvector(doc_id, embedding, metadata)
    else:
        await _save_to_memory(doc_id, embedding, metadata)


async def _save_to_pgvector(
    doc_id: str, embedding: list[float], metadata: dict[str, Any]
) -> None:
    """Persist a single embedding to pgvector."""
    try:
        from backend.persistence.database import get_sessionmaker
        from sqlalchemy import text

        Session = get_sessionmaker()
        async with Session() as session:
            # pgvector accepts a vector literal as a string
            vec_str = "[" + ",".join(str(float(x)) for x in embedding) + "]"
            meta_json = json.dumps(metadata)
            await session.execute(
                text(
                    """
                    INSERT INTO pitch_embeddings (id, embedding, metadata, created_at)
                    VALUES (:id, :embedding::vector, CAST(:metadata AS JSONB), NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata,
                        created_at = NOW()
                    """
                ),
                {"id": doc_id, "embedding": vec_str, "metadata": meta_json},
            )
            await session.commit()
        logger.info("pgvector: saved embedding for %s", metadata.get("session_id"))
    except Exception as e:
        logger.warning("pgvector save failed: %s", e)


async def _save_to_memory(
    doc_id: str, embedding: list[float], metadata: dict[str, Any]
) -> None:
    """Persist a single embedding to the in-memory store."""
    _store.records[doc_id] = metadata
    _store._vectors[doc_id] = embedding


async def retrieve_past_pitches(
    pitch_summary: str, top_k: int = 2
) -> list[dict[str, Any]]:
    """Find past pitches semantically similar to `pitch_summary`.

    Returns a list of metadata dicts (with a `similarity` field) sorted
    by descending similarity. Returns [] if no embedding API key or no
    embeddings stored.
    """
    embedding = await _embed_async(pitch_summary)
    if embedding is None:
        return []

    use_pg = await _ensure_pgvector_table()
    if use_pg:
        return await _retrieve_from_pgvector(embedding, top_k)
    return _retrieve_from_memory(embedding, top_k)


async def _retrieve_from_pgvector(
    embedding: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Cosine-similarity search against pgvector."""
    try:
        from backend.persistence.database import get_sessionmaker
        from sqlalchemy import text

        vec_str = "[" + ",".join(str(float(x)) for x in embedding) + "]"
        Session = get_sessionmaker()
        async with Session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, metadata, 1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                    FROM pitch_embeddings
                    ORDER BY embedding <=> CAST(:embedding AS vector)
                    LIMIT :top_k
                    """
                ),
                {"embedding": vec_str, "top_k": top_k},
            )
            rows = result.fetchall()
        out: list[dict[str, Any]] = []
        for _id, metadata, similarity in rows:
            if similarity > 0.70:
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                out.append({"similarity": round(float(similarity), 2), **metadata})
        return out
    except Exception as e:
        logger.warning("pgvector query failed: %s", e)
        return []


def _retrieve_from_memory(
    embedding: list[float], top_k: int
) -> list[dict[str, Any]]:
    """Cosine-similarity search against the in-memory store."""
    if not _store._vectors:
        return []
    scored = [
        (sim, _store.records[doc_id])
        for doc_id, vec in _store._vectors.items()
        for sim in [_cosine_similarity(embedding, vec)]
        if sim > 0.70
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"similarity": round(sim, 2), **meta}
        for sim, meta in scored[:top_k]
    ]


def format_past_pitches_for_context(past_pitches: list[dict[str, Any]]) -> str:
    """Format retrieved pitches as a context block for the controller prompt."""
    if not past_pitches:
        return ""

    lines = ["=== PITCHER'S HISTORY (from previous sessions) ==="]
    for i, p in enumerate(past_pitches, 1):
        sim = p.get("similarity", 0)
        lines.append(f"\nPrevious Pitch #{i} (similarity: {sim:.0%}):")
        lines.append(f"  Summary: {p.get('pitch_summary', 'N/A')[:300]}")
        lines.append(f"  Strongest Point: {p.get('strongest', 'N/A')}")
        lines.append(f"  Biggest Weakness: {p.get('weakness', 'N/A')}")
        lines.append(f"  Advised Fix: {p.get('fix', 'N/A')}")
        lines.append(f"  Confidence Score: {p.get('confidence_score', 'N/A')}/100")
    lines.append("\nAgents: Reference this history. Ask if they addressed previous weaknesses.")
    return "\n".join(lines)


# ─── List all (for the history dashboard) ──────────────────────────


async def list_all_pitches(limit: int = 20) -> list[dict[str, Any]]:
    """Return all stored pitch embeddings, newest first.

    Used by the /api/pitch-history endpoint to show the user's
    past pitches. For pgvector, queries with a zero vector and
    orders by created_at desc. For in-memory, sorts in Python.
    """
    use_pg = await _ensure_pgvector_table()
    if use_pg:
        return await _list_all_from_pgvector(limit)
    return _list_all_from_memory(limit)


async def _list_all_from_pgvector(limit: int) -> list[dict[str, Any]]:
    try:
        from backend.persistence.database import get_sessionmaker
        from sqlalchemy import text

        Session = get_sessionmaker()
        async with Session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, metadata
                    FROM pitch_embeddings
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
            rows = result.fetchall()
        out: list[dict[str, Any]] = []
        for _id, metadata in rows:
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            out.append(metadata)
        return out
    except Exception as e:
        logger.warning("pgvector list_all failed: %s", e)
        return []


def _list_all_from_memory(limit: int) -> list[dict[str, Any]]:
    """In-memory list: sort by timestamp desc, return most recent N."""
    sorted_records = sorted(
        _store.records.values(),
        key=lambda r: r.get("timestamp", 0),
        reverse=True,
    )
    return sorted_records[:limit]


# ─── Test helpers ──────────────────────────────────────────────────


def reset_for_tests() -> None:
    """Clear the in-memory store and pgvector init flag. Used by tests."""
    global _pgvector_initialized, _pgvector_collection
    _store.records.clear()
    _store._vectors.clear()
    _pgvector_initialized = False
    _pgvector_collection = None


__all__ = [
    "EMBEDDING_DIM",
    "format_past_pitches_for_context",
    "list_all_pitches",
    "retrieve_past_pitches",
    "save_pitch_history",
    "reset_for_tests",
]