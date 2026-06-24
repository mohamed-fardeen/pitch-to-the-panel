"""
Tests for the public verdict endpoints (Tier-1c).

Verifies:
- GET /v/{session_id}/public returns sanitized verdict for public sessions
- Returns 404 for private sessions
- Returns 404 for non-existent sessions
- Returns 404 for non-completed sessions
- GET /v/{session_id}/og returns HTML with OG meta tags
- The pitch excerpt is truncated to 200 chars
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.persistence import (
    get_repository,
    reset_repository,
    set_repository,
)
from backend.persistence.in_memory import InMemorySessionRepository
from backend.persistence.models import (
    SessionStatus,
    VerdictSignal,
)


@pytest.fixture
def fresh_repo(monkeypatch):
    """Reset the global repository to a fresh in-memory one for each test.

    Must run BEFORE the FastAPI app is constructed, because the app
    caches the repo during the lifespan. So we set it before
    importing/constructing the test client.
    """
    # Reset cached factory state
    reset_repository()
    repo = InMemorySessionRepository()
    set_repository(repo)
    yield repo
    # Cleanup after the test
    reset_repository()


@pytest.fixture
def client(fresh_repo):
    """A TestClient that doesn't actually start the server.

    Depends on fresh_repo so the in-memory repo is set before the
    lifespan runs.
    """
    # Lazy import so the fixture setup runs first
    from backend.main import app
    with TestClient(app) as c:
        yield c


# ─── Public verdict JSON endpoint ─────────────────────────────────


def test_public_verdict_returns_sanitized_data(client, fresh_repo):
    """A public, completed session returns a sanitized verdict JSON."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="public-1",
            pitch="A" * 500,  # > 200 chars, to test truncation
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "public-1",
            status=SessionStatus.COMPLETED.value,
            is_public=True,
        )
        await fresh_repo.save_verdict(
            "public-1",
            verdict_text="This is a strong idea overall.",
            strongest="Clear market segment",
            weakness="No clear moat",
            fix="Build network effects",
            investment_score=7.5,
            recommendation="Conditional",
            confidence_score=72,
            signal=VerdictSignal.MEDIUM,
        )

    asyncio.run(setup())

    r = client.get("/v/public-1/public")
    assert r.status_code == 200
    data = r.json()
    assert data["session_id"] == "public-1"
    assert data["is_public"] is True
    assert data["mode"] == "venture"
    assert data["investment_signal"] == "MEDIUM"
    assert data["confidence_score"] == 72
    assert data["verdict"]["strongest"] == "Clear market segment"
    assert data["verdict"]["weakness"] == "No clear moat"
    # Pitch is truncated to 200 chars + "..."
    assert len(data["pitch_excerpt"]) <= 203
    assert data["pitch_excerpt"].endswith("...")


def test_public_verdict_404_for_missing_session(client, fresh_repo):
    r = client.get("/v/does-not-exist/public")
    assert r.status_code == 404


def test_public_verdict_404_for_private_session(client, fresh_repo):
    """Sessions marked is_public=false are not visible to non-owners."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="private-1",
            pitch="Secret pitch",
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "private-1",
            status=SessionStatus.COMPLETED.value,
            is_public=False,  # private
        )
        await fresh_repo.save_verdict(
            "private-1",
            verdict_text="Confidential",
            confidence_score=80,
            signal=VerdictSignal.STRONG,
        )

    asyncio.run(setup())

    r = client.get("/v/private-1/public")
    assert r.status_code == 404


def test_public_verdict_404_for_incomplete_session(client, fresh_repo):
    """Sessions that haven't reached COMPLETED state return 404."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="incomplete-1",
            pitch="WIP pitch",
            mode="venture",
            provider="groq",
        )
        # status stays at "created" (default)
        # No verdict saved

    asyncio.run(setup())

    r = client.get("/v/incomplete-1/public")
    assert r.status_code == 404


def test_public_verdict_404_for_session_with_no_verdict(client, fresh_repo):
    """A completed session without a verdict row returns 404."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="no-verdict-1",
            pitch="A pitch",
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "no-verdict-1",
            status=SessionStatus.COMPLETED.value,
            is_public=True,
        )
        # No save_verdict call

    asyncio.run(setup())

    r = client.get("/v/no-verdict-1/public")
    assert r.status_code == 404


def test_public_verdict_pitch_excerpt_under_200_chars(client, fresh_repo):
    """Short pitches are returned without the '...' suffix."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="short-1",
            pitch="A short pitch.",
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "short-1",
            status=SessionStatus.COMPLETED.value,
            is_public=True,
        )
        await fresh_repo.save_verdict(
            "short-1",
            verdict_text="OK",
            confidence_score=50,
            signal=VerdictSignal.MEDIUM,
        )

    asyncio.run(setup())

    r = client.get("/v/short-1/public")
    data = r.json()
    assert data["pitch_excerpt"] == "A short pitch."
    assert not data["pitch_excerpt"].endswith("...")


def test_public_verdict_handles_empty_verdict_fields(client, fresh_repo):
    """A verdict with no parts (e.g. from a parse failure) returns empty strings."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="empty-verdict-1",
            pitch="X",
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "empty-verdict-1",
            status=SessionStatus.COMPLETED.value,
            is_public=True,
        )
        await fresh_repo.save_verdict(
            "empty-verdict-1",
            verdict_text="",  # no parts
            confidence_score=0,
            signal=VerdictSignal.WEAK,
        )

    asyncio.run(setup())

    r = client.get("/v/empty-verdict-1/public")
    assert r.status_code == 200
    data = r.json()
    assert data["verdict"]["strongest"] == ""
    assert data["verdict"]["weakness"] == ""
    assert data["verdict"]["fix"] == ""


# ─── OG meta tag endpoint ────────────────────────────────────────


def test_og_endpoint_returns_html(client, fresh_repo):
    """GET /v/{id}/og returns HTML with proper OG meta tags."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="og-1",
            pitch="Test pitch",
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "og-1",
            status=SessionStatus.COMPLETED.value,
            is_public=True,
        )
        await fresh_repo.save_verdict(
            "og-1",
            verdict_text="OK",
            strongest="Strong team",
            confidence_score=80,
            signal=VerdictSignal.STRONG,
        )

    asyncio.run(setup())

    r = client.get("/v/og-1/og")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "<title>" in body
    assert "PanelMind" in body
    assert "STRONG" in body
    assert 'property="og:title"' in body
    assert 'property="og:description"' in body
    assert 'property="og:url"' in body
    assert 'name="twitter:card"' in body
    # Strongest point should be the description
    assert "Strong team" in body


def test_og_endpoint_404_for_private_session(client, fresh_repo):
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="og-private-1",
            pitch="X",
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "og-private-1",
            status=SessionStatus.COMPLETED.value,
            is_public=False,
        )
        await fresh_repo.save_verdict(
            "og-private-1",
            verdict_text="X",
            confidence_score=50,
            signal=VerdictSignal.MEDIUM,
        )

    asyncio.run(setup())

    r = client.get("/v/og-private-1/og")
    assert r.status_code == 404


def test_og_endpoint_escapes_html_in_description(client, fresh_repo):
    """The OG endpoint must HTML-escape user-controlled content."""
    import asyncio

    async def setup():
        await fresh_repo.create_session(
            session_id="og-xss-1",
            pitch="X",
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "og-xss-1",
            status=SessionStatus.COMPLETED.value,
            is_public=True,
        )
        await fresh_repo.save_verdict(
            "og-xss-1",
            verdict_text="</title><script>alert(1)</script>",
            strongest="<script>steal()</script>",
            confidence_score=50,
            signal=VerdictSignal.MEDIUM,
        )

    asyncio.run(setup())

    r = client.get("/v/og-xss-1/og")
    body = r.text
    # Raw script tags should be escaped
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body
    # Strongest should also be escaped
    assert "<script>steal()</script>" not in body


# ─── CORS / privacy ──────────────────────────────────────────────


def test_og_endpoint_does_not_leak_pitch_content(client, fresh_repo):
    """The OG endpoint's description must come from the verdict, not the pitch."""
    import asyncio

    sensitive_pitch = "MY_SSN_IS_123-45-6789_AND_MY_PASSWORD_IS_HUNTER2"

    async def setup():
        await fresh_repo.create_session(
            session_id="og-leak-1",
            pitch=sensitive_pitch,
            mode="venture",
            provider="groq",
        )
        await fresh_repo.update_session(
            "og-leak-1",
            status=SessionStatus.COMPLETED.value,
            is_public=True,
        )
        await fresh_repo.save_verdict(
            "og-leak-1",
            verdict_text="OK",
            strongest="OK",
            confidence_score=50,
            signal=VerdictSignal.MEDIUM,
        )

    asyncio.run(setup())

    r = client.get("/v/og-leak-1/og")
    body = r.text
    # The pitch must not appear in the OG response
    assert "123-45-6789" not in body
    assert "HUNTER2" not in body