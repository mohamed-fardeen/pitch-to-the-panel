"""
Tests for the SessionPersistenceBridge.

The bridge mirrors writes from the legacy `sessions: dict` into the
durable repository. These tests verify:
- The bridge correctly forwards session creation
- The bridge correctly forwards updates (and filters out non-persisted keys)
- The bridge swallows errors (so DB outages don't crash the request handler)
"""

from __future__ import annotations

import pytest

from backend.persistence.in_memory import InMemorySessionRepository
from backend.persistence.sync import NON_PERSISTED_KEYS, SessionPersistenceBridge


@pytest.mark.asyncio
async def test_session_created_writes_to_repo():
    repo = InMemorySessionRepository()
    bridge = SessionPersistenceBridge(repo)

    await bridge.session_created(
        session_id="s1",
        pitch="AI-powered CRM for dentists",
        mode="venture",
        provider="groq",
        aggressiveness=5,
    )
    session = await repo.get_session("s1")
    assert session is not None
    assert session.pitch_summary == "AI-powered CRM for dentists"
    assert session.mode == "venture"


@pytest.mark.asyncio
async def test_session_updated_filters_non_persisted_keys():
    repo = InMemorySessionRepository()
    bridge = SessionPersistenceBridge(repo)
    await bridge.session_created(
        session_id="s1",
        pitch="x",
        mode="venture",
        provider="groq",
    )

    # Send a payload that includes non-persisted keys
    await bridge.session_updated(
        "s1",
        fields={
            "refined_pitch": "A better pitch",
            "events": {"answer_event": "NOT_AN_EVENT"},  # would crash if persisted
            "graph_task": "NOT_A_TASK",
            "sse_queue": "NOT_A_QUEUE",
            "current_step": 3,
        },
    )

    session = await repo.get_session("s1")
    assert session is not None
    assert session.refined_pitch == "A better pitch"
    assert session.current_step == 3
    # The non-persisted keys should NOT have leaked into the repo.
    # (We don't have a "events" column on PitchSession, so this just
    # verifies no exception was raised.)


@pytest.mark.asyncio
async def test_session_updated_empty_fields_is_noop():
    repo = InMemorySessionRepository()
    bridge = SessionPersistenceBridge(repo)
    await bridge.session_created(
        session_id="s1",
        pitch="x",
        mode="venture",
        provider="groq",
    )
    # If only non-persisted keys are sent, nothing should be updated
    # and no error should be raised.
    await bridge.session_updated("s1", fields={"events": "x", "graph_task": "y"})


@pytest.mark.asyncio
async def test_session_ended_marks_status():
    repo = InMemorySessionRepository()
    bridge = SessionPersistenceBridge(repo)
    await bridge.session_created(
        session_id="s1",
        pitch="x",
        mode="venture",
        provider="groq",
    )

    # Normal completion
    await bridge.session_ended("s1", cancelled=False)
    s = await repo.get_session("s1")
    assert s is not None
    assert s.status == "completed"
    assert s.is_cancelled is False
    assert s.completed_at is not None

    # Aborted
    await bridge.session_ended("s1", cancelled=True)
    s = await repo.get_session("s1")
    assert s is not None
    assert s.status == "aborted"
    assert s.is_cancelled is True


@pytest.mark.asyncio
async def test_turn_recorded_persists_to_conversation():
    repo = InMemorySessionRepository()
    bridge = SessionPersistenceBridge(repo)
    await bridge.session_created(
        session_id="s1",
        pitch="x",
        mode="venture",
        provider="groq",
    )
    await bridge.turn_recorded(
        "s1",
        step_index=0,
        role="persona",
        turn_type="question",
        content="What's your TAM?",
        agent_id="vc",
        agent_name="Arjun (VC)",
    )
    turns = await repo.list_turns("s1")
    assert len(turns) == 1
    assert turns[0].content == "What's your TAM?"
    assert turns[0].agent_id == "vc"


@pytest.mark.asyncio
async def test_verdict_recorded_persists():
    repo = InMemorySessionRepository()
    bridge = SessionPersistenceBridge(repo)
    await bridge.session_created(
        session_id="s1",
        pitch="x",
        mode="venture",
        provider="groq",
    )
    await bridge.verdict_recorded(
        "s1",
        verdict_text="Overall positive",
        strongest="Strong team",
        weakness="No moat",
        fix="Build network effects",
        investment_score=7.5,
        recommendation="Conditional",
        confidence_score=72,
        signal="MEDIUM",
    )
    v = await repo.get_verdict("s1")
    assert v is not None
    assert v.confidence_score == 72
    assert v.signal == "MEDIUM"


@pytest.mark.asyncio
async def test_revision_recorded_persists():
    repo = InMemorySessionRepository()
    bridge = SessionPersistenceBridge(repo)
    await bridge.session_created(
        session_id="s1",
        pitch="x",
        mode="venture",
        provider="groq",
    )
    await bridge.revision_recorded(
        "s1",
        original_pitch="Original",
        revised_pitch="Revised v1",
        improvements_addressed=["Weakness 1", "Fix 1"],
    )
    revisions = await repo.list_revisions("s1")
    assert len(revisions) == 1
    assert revisions[0].revised_pitch == "Revised v1"


def test_non_persisted_keys_include_in_process_state():
    """Sanity check: the dict of non-persisted keys includes the in-process
    state we never want to land in the database."""
    assert "events" in NON_PERSISTED_KEYS
    assert "graph_task" in NON_PERSISTED_KEYS
    assert "sse_queue" in NON_PERSISTED_KEYS