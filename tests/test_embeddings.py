"""
Tests for the embeddings service (Tier-1d).

These tests exercise the in-memory fallback path (no real pgvector,
no real Jina API). For pgvector-specific tests, see
`test_embeddings_pgvector.py` (skipped automatically when no
DATABASE_URL points at Postgres).
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

from backend.services import embeddings as emb


@pytest.fixture(autouse=True)
def _reset_store():
    """Reset the in-memory store before each test."""
    emb.reset_for_tests()
    yield
    emb.reset_for_tests()


def _fake_embed(text: str) -> list[float]:
    """Deterministic fake embedding: hash of text → fixed-length vector."""
    import hashlib
    h = hashlib.md5(text.encode("utf-8")).digest()
    return [(b - 128) / 128.0 for b in h[:32]]


@pytest.fixture
def fake_jina():
    """Patch _embed_jina with a deterministic fake. Opt-in for tests
    that need embeddings but don't want to mock the network."""
    with patch.object(emb, "_embed_jina", side_effect=_fake_embed):
        yield


# ─── In-memory fallback ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_retrieve_round_trip(fake_jina):
    """Save an embedding, then retrieve it via similarity search."""
    await emb.save_pitch_history(
        session_id="sess-1",
        pitch_summary="We are building an AI-powered CRM for dentists.",
        verdict_parts={
            "strongest": "Clear market",
            "weakness": "No moat",
            "fix": "Build network effects",
        },
        confidence_score=72,
    )
    # Retrieve using the same text — should match itself with similarity ~1
    results = await emb.retrieve_past_pitches(
        pitch_summary="We are building an AI-powered CRM for dentists.",
        top_k=2,
    )
    assert len(results) >= 1
    top = results[0]
    assert top["similarity"] > 0.95
    assert top["session_id"] == "sess-1"
    assert top["strongest"] == "Clear market"


@pytest.mark.asyncio
async def test_similarity_threshold_filters_irrelevant(fake_jina):
    """If the new pitch is too different, no results are returned."""
    await emb.save_pitch_history(
        session_id="sess-1",
        pitch_summary="alpha alpha alpha alpha alpha",
        verdict_parts={"strongest": "x"},
        confidence_score=50,
    )
    # A completely different text — different hash → different vector
    results = await emb.retrieve_past_pitches(
        pitch_summary="a completely different pitch about something else entirely",
        top_k=2,
    )
    # Could be empty if nothing crosses the 0.7 threshold
    assert all(r["similarity"] > 0.70 for r in results)


@pytest.mark.asyncio
async def test_top_k_limits_results(fake_jina):
    """`top_k` caps the number of returned results."""
    for i in range(5):
        await emb.save_pitch_history(
            session_id=f"sess-{i}",
            pitch_summary="Identical pitch used for testing.",
            verdict_parts={"strongest": f"strength {i}"},
            confidence_score=50,
        )
    results = await emb.retrieve_past_pitches(
        pitch_summary="Identical pitch used for testing.",
        top_k=2,
    )
    assert len(results) <= 2


@pytest.mark.asyncio
async def test_save_with_no_jina_key_silently_skips(fake_jina):
    """If no JINA_API_KEY, save_pitch_history is a silent no-op."""
    with patch.dict(os.environ, {"JINA_API_KEY": ""}, clear=False):
        # Force re-read of the constant (it's loaded at import time,
        # so we patch _embed_jina directly)
        with patch.object(emb, "_embed_jina", return_value=None):
            await emb.save_pitch_history(
                session_id="sess-x",
                pitch_summary="X",
                verdict_parts={"strongest": "X"},
                confidence_score=50,
            )
            # No exception, no stored embeddings
            results = await emb.retrieve_past_pitches("X", top_k=5)
            assert results == []


@pytest.mark.asyncio
async def test_retrieve_with_no_jina_key_returns_empty(fake_jina):
    """If no embedding can be produced, retrieve returns []."""
    with patch.object(emb, "_embed_jina", return_value=None):
        results = await emb.retrieve_past_pitches("anything", top_k=2)
        assert results == []


# ─── format_past_pitches_for_context ───────────────────────────────


def test_format_empty_returns_empty_string():
    assert emb.format_past_pitches_for_context([]) == ""


def test_format_single_pitch_renders_correctly():
    pitches = [
        {
            "similarity": 0.85,
            "pitch_summary": "AI CRM for dentists.",
            "strongest": "Clear market",
            "weakness": "No moat",
            "fix": "Network effects",
            "confidence_score": 75,
        }
    ]
    out = emb.format_past_pitches_for_context(pitches)
    assert "PITCHER'S HISTORY" in out
    assert "85%" in out
    assert "AI CRM for dentists." in out
    assert "Clear market" in out
    assert "No moat" in out
    assert "Network effects" in out
    assert "75/100" in out


def test_format_multiple_pitches():
    pitches = [
        {"similarity": 0.9, "pitch_summary": "Pitch A", "strongest": "S1",
         "weakness": "W1", "fix": "F1", "confidence_score": 80},
        {"similarity": 0.75, "pitch_summary": "Pitch B", "strongest": "S2",
         "weakness": "W2", "fix": "F2", "confidence_score": 60},
    ]
    out = emb.format_past_pitches_for_context(pitches)
    assert "Previous Pitch #1" in out
    assert "Previous Pitch #2" in out
    assert "90%" in out
    assert "75%" in out


def test_format_truncates_long_pitch_summary():
    long_summary = "x" * 1000
    pitches = [
        {"similarity": 0.8, "pitch_summary": long_summary, "strongest": "s",
         "weakness": "w", "fix": "f", "confidence_score": 50}
    ]
    out = emb.format_past_pitches_for_context(pitches)
    # Summary is truncated to 300 chars
    assert "x" * 300 in out
    assert "x" * 301 not in out


def test_format_handles_missing_fields():
    """Robust to missing keys."""
    pitches = [{"similarity": 0.8}]  # no other fields
    out = emb.format_past_pitches_for_context(pitches)
    assert "PITCHER'S HISTORY" in out
    assert "N/A" in out


# ─── Module configuration ─────────────────────────────────────────


def test_is_postgres_detects_postgres_url(monkeypatch):
    monkeypatch.setattr(emb, "_current_database_url", lambda: "postgresql+asyncpg://localhost/db")
    assert emb._is_postgres() is True


def test_is_postgres_detects_sqlite(monkeypatch):
    monkeypatch.setattr(emb, "_current_database_url", lambda: "sqlite+aiosqlite:///./x.db")
    assert emb._is_postgres() is False


def test_is_postgres_detects_empty(monkeypatch):
    monkeypatch.setattr(emb, "_current_database_url", lambda: "")
    assert emb._is_postgres() is False


# ─── Embedding call (with mocked network) ─────────────────────────


def test_embed_jina_calls_correct_url(monkeypatch):
    """Verify the Jina API URL and payload structure."""
    captured = {}

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"data": [{"embedding": [0.1] * 1024}]}

        def raise_for_status(self):
            pass

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(emb.requests, "post", fake_post)
    # Set the constant after the autouse fixture reset it
    monkeypatch.setattr(emb, "JINA_API_KEY", "fake-key")
    # Restore the original function (autouse fixture replaced it with a fake)
    import backend.services.embeddings as real_emb_module
    monkeypatch.setattr(emb, "_embed_jina", real_emb_module._embed_jina)

    result = emb._embed_jina("test text")
    assert result is not None
    assert captured["url"] == "https://api.jina.ai/v1/embeddings"
    assert captured["headers"]["Authorization"] == "Bearer fake-key"
    assert captured["payload"]["model"] == "jina-embeddings-v3"
    assert captured["payload"]["dimensions"] == 1024
    assert captured["payload"]["input"] == ["test text"]


def test_embed_jina_handles_network_error(monkeypatch):
    """A network error should return None, not raise."""
    import requests
    import backend.services.embeddings as real_emb_module
    monkeypatch.setattr(emb, "_embed_jina", real_emb_module._embed_jina)

    def fake_post(*_args, **_kwargs):
        raise requests.ConnectionError("Network down")

    monkeypatch.setattr(emb.requests, "post", fake_post)
    monkeypatch.setattr(emb, "JINA_API_KEY", "fake-key")

    assert emb._embed_jina("text") is None


def test_embed_jina_returns_none_when_no_key(monkeypatch):
    """Without JINA_API_KEY, return None without calling the API."""
    import backend.services.embeddings as real_emb_module
    monkeypatch.setattr(emb, "_embed_jina", real_emb_module._embed_jina)
    monkeypatch.setattr(emb, "JINA_API_KEY", "")

    called = {"value": False}

    def fake_post(*_args, **_kwargs):
        called["value"] = True
        return None

    monkeypatch.setattr(emb.requests, "post", fake_post)
    assert emb._embed_jina("text") is None
    assert called["value"] is False


def test_embed_jina_truncates_long_input(monkeypatch):
    """Inputs > 8000 chars should be truncated to 8000."""
    import backend.services.embeddings as real_emb_module
    monkeypatch.setattr(emb, "_embed_jina", real_emb_module._embed_jina)
    captured = {}

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"data": [{"embedding": [0.1] * 1024}]}

        def raise_for_status(self):
            pass

    def fake_post(url, headers, json, timeout):
        captured["input"] = json["input"][0]
        return FakeResponse()

    monkeypatch.setattr(emb.requests, "post", fake_post)
    monkeypatch.setattr(emb, "JINA_API_KEY", "fake-key")

    very_long = "x" * 10_000
    emb._embed_jina(very_long)
    assert len(captured["input"]) == 8000