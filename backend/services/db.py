"""
services/db.py — Pitch Memory using Jina Embeddings + Supabase pgvector (vecs)

Stores pitch history so agents can recall previous attempts and call out improvements.
Falls back gracefully if DB is not configured.
"""

import asyncio
import os
import time

import requests

# Lazy-init so the app boots even if DB is not configured
_vx_client = None
_pitches_collection = None

JINA_API_KEY = os.getenv("JINA_API_KEY", "")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")

EMBEDDING_DIM = 1024  # jina-embeddings-v3 default


def _get_vecs_client():
    """Lazily initialize the vecs client and pitches collection."""
    global _vx_client, _pitches_collection

    if _pitches_collection is not None:
        return _pitches_collection

    if not SUPABASE_DB_URL:
        return None

    try:
        import vecs
        _vx_client = vecs.create_client(SUPABASE_DB_URL)
        _pitches_collection = _vx_client.get_or_create_collection(
            name="pitch_history",
            dimension=EMBEDDING_DIM
        )
        # Ensure we have an index for cosine similarity search
        import contextlib
        with contextlib.suppress(Exception):
            _pitches_collection.create_index(measure=vecs.IndexMeasure.cosine_distance)

        print("[DB] Connected to Supabase pgvector — pitch_history collection ready.")
        return _pitches_collection
    except Exception as e:
        print(f"[DB WARNING] Could not connect to Supabase: {e}")
        return None


def _embed_jina(text: str) -> list | None:
    """Call Jina Embeddings API synchronously."""
    if not JINA_API_KEY:
        return None
    try:
        url = "https://api.jina.ai/v1/embeddings"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {JINA_API_KEY}"
        }
        payload = {
            "model": "jina-embeddings-v3",
            "task": "retrieval.passage",
            "dimensions": EMBEDDING_DIM,
            "input": [text[:8000]]  # Jina v3 supports up to 8192 tokens
        }
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]
    except Exception as e:
        print(f"[JINA ERROR] Embedding failed: {e}")
        return None


async def _embed_async(text: str) -> list | None:
    """Async wrapper for Jina embedding call."""
    return await asyncio.to_thread(_embed_jina, text)


async def save_pitch_history(session_id: str, pitch_summary: str, verdict_parts: dict, confidence_score: int):
    """
    Embed a pitch summary and save it to the pgvector collection.
    Called after final_node generates the verdict.
    """
    collection = await asyncio.to_thread(_get_vecs_client)
    if collection is None:
        return

    embedding = await _embed_async(pitch_summary)
    if embedding is None:
        return

    doc_id = f"{session_id}_{int(time.time())}"
    metadata = {
        "session_id": session_id,
        "pitch_summary": pitch_summary[:1000],
        "strongest": verdict_parts.get("strongest", ""),
        "weakness": verdict_parts.get("weakness", ""),
        "fix": verdict_parts.get("fix", ""),
        "confidence_score": confidence_score,
        "timestamp": int(time.time())
    }

    try:
        await asyncio.to_thread(
            collection.upsert,
            records=[(doc_id, embedding, metadata)]
        )
        print(f"[DB] Pitch history saved — session={session_id}")
    except Exception as e:
        print(f"[DB ERROR] Failed to save pitch: {e}")


async def retrieve_past_pitches(pitch_summary: str, top_k: int = 2) -> list[dict]:
    """
    Given a new pitch summary, find semantically similar past pitches.
    Returns a list of metadata dicts with verdict info for context injection.
    """
    collection = await asyncio.to_thread(_get_vecs_client)
    if collection is None:
        return []

    embedding = await _embed_async(pitch_summary)
    if embedding is None:
        return []

    try:
        results = await asyncio.to_thread(
            collection.query,
            data=embedding,
            limit=top_k,
            include_metadata=True,
            include_value=True
        )
        past = []
        for _doc_id, distance, metadata in results:
            similarity = 1 - distance  # cosine distance → similarity
            if similarity > 0.70:  # Only inject if genuinely similar
                past.append({
                    "similarity": round(similarity, 2),
                    **metadata
                })
        return past
    except Exception as e:
        print(f"[DB ERROR] Failed to retrieve past pitches: {e}")
        return []


def format_past_pitches_for_context(past_pitches: list[dict]) -> str:
    """
    Format retrieved pitches into a string that gets injected into the
    controller's system context so agents know about previous sessions.
    """
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
