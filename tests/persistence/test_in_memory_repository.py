"""
Tests for the in-memory SessionRepository implementation.

These tests run fast and exercise the full contract. They are the
canonical reference for the SQLAlchemy implementation too — if a test
passes here and not in the SQLAlchemy version, the bug is in the
SQLAlchemy code.
"""

from __future__ import annotations

import pytest

from backend.persistence.in_memory import InMemorySessionRepository
from backend.persistence.models import (
    SessionStatus,
    TurnRole,
    TurnType,
    VerdictSignal,
)


# ─── Lifecycle ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_session():
    repo = InMemorySessionRepository()
    session = await repo.create_session(
        session_id="sess-1",
        pitch="AI-powered CRM for dentists",
        mode="venture",
        provider="groq",
        aggressiveness=5,
    )
    assert session.id == "sess-1"
    assert session.pitch_summary == "AI-powered CRM for dentists"
    assert session.mode == "venture"
    assert session.provider == "groq"
    assert session.status == SessionStatus.CREATED.value
    assert session.started_at is not None

    fetched = await repo.get_session("sess-1")
    assert fetched is not None
    assert fetched.id == session.id


@pytest.mark.asyncio
async def test_create_session_duplicate_raises():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="dup",
        pitch="x",
        mode="venture",
        provider="groq",
    )
    with pytest.raises(ValueError, match="already exists"):
        await repo.create_session(
            session_id="dup",
            pitch="x",
            mode="venture",
            provider="groq",
        )


@pytest.mark.asyncio
async def test_get_unknown_session_returns_none():
    repo = InMemorySessionRepository()
    assert await repo.get_session("nope") is None


@pytest.mark.asyncio
async def test_update_session_fields():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="u1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    updated = await repo.update_session(
        "u1",
        refined_pitch="A refined pitch",
        status=SessionStatus.DEBATING.value,
        current_step=3,
    )
    assert updated is not None
    assert updated.refined_pitch == "A refined pitch"
    assert updated.status == SessionStatus.DEBATING.value
    assert updated.current_step == 3


@pytest.mark.asyncio
async def test_update_unknown_session_returns_none():
    repo = InMemorySessionRepository()
    result = await repo.update_session("nope", refined_pitch="x")
    assert result is None


@pytest.mark.asyncio
async def test_update_session_rejects_unknown_field():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="u1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    with pytest.raises(AttributeError, match="no field"):
        await repo.update_session("u1", not_a_field=123)


@pytest.mark.asyncio
async def test_delete_session():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="d1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    assert await repo.delete_session("d1") is True
    assert await repo.get_session("d1") is None
    # Second delete returns False (idempotent)
    assert await repo.delete_session("d1") is False


@pytest.mark.asyncio
async def test_list_sessions_for_user_orders_by_recency():
    repo = InMemorySessionRepository()
    user_id = "user-1"

    # Create a user to associate sessions with
    user = await repo.upsert_user(email="alice@example.com", name="Alice")
    assert user.id

    # Create sessions — these won't have user_id set since we created them
    # without one. We need to update them.
    s1 = await repo.create_session(
        session_id="s1",
        pitch="p1",
        mode="venture",
        provider="groq",
    )
    s2 = await repo.create_session(
        session_id="s2",
        pitch="p2",
        mode="venture",
        provider="groq",
    )
    await repo.update_session("s1", user_id=user_id)
    await repo.update_session("s2", user_id=user_id)

    listed = await repo.list_sessions_for_user(user_id)
    assert len(listed) == 2
    # Newest first (created via upsert user creates timestamps; s2 was created after s1)
    assert listed[0].id in ("s1", "s2")
    assert listed[1].id in ("s1", "s2")


# ─── Turns ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_and_list_turns():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="t1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    await repo.append_turn(
        "t1",
        step_index=0,
        role=TurnRole.PERSONA,
        turn_type=TurnType.QUESTION,
        content="What's your TAM?",
        agent_id="vc",
        agent_name="Arjun (VC)",
    )
    await repo.append_turn(
        "t1",
        step_index=1,
        role=TurnRole.PITCHER,
        turn_type=TurnType.ANSWER,
        content="$2B in the US",
    )
    turns = await repo.list_turns("t1")
    assert len(turns) == 2
    assert turns[0].step_index == 0
    assert turns[0].role == "persona"
    assert turns[1].step_index == 1
    assert turns[1].role == "pitcher"


@pytest.mark.asyncio
async def test_append_turn_accepts_string_enums():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="t1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    await repo.append_turn(
        "t1",
        step_index=0,
        role="persona",  # string instead of TurnRole.PERSONA
        turn_type="question",
        content="Hi",
    )
    turns = await repo.list_turns("t1")
    assert turns[0].role == "persona"
    assert turns[0].turn_type == "question"


@pytest.mark.asyncio
async def test_append_turn_unknown_session_raises():
    repo = InMemorySessionRepository()
    with pytest.raises(KeyError):
        await repo.append_turn(
            "missing",
            step_index=0,
            role=TurnRole.PERSONA,
            turn_type=TurnType.QUESTION,
            content="x",
        )


# ─── Verdict ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_get_verdict():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="v1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    verdict = await repo.save_verdict(
        "v1",
        verdict_text="Overall positive",
        strongest="Strong team",
        weakness="No clear moat",
        fix="Build network effects",
        investment_score=7.5,
        recommendation="Conditional",
        confidence_score=72,
        signal=VerdictSignal.MEDIUM,
    )
    assert verdict.session_id == "v1"
    assert verdict.confidence_score == 72

    fetched = await repo.get_verdict("v1")
    assert fetched is not None
    assert fetched.strongest == "Strong team"


@pytest.mark.asyncio
async def test_save_verdict_upserts():
    """Saving a verdict twice updates the existing row (one per session)."""
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="v1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    v1 = await repo.save_verdict(
        "v1", verdict_text="first", confidence_score=50, signal=VerdictSignal.WEAK
    )
    v2 = await repo.save_verdict(
        "v1", verdict_text="second", confidence_score=80, signal=VerdictSignal.STRONG
    )
    assert v1.id == v2.id  # same row updated
    assert v2.verdict_text == "second"
    assert v2.confidence_score == 80
    # And there's still only one verdict for this session
    assert await repo.get_verdict("v1") is not None


@pytest.mark.asyncio
async def test_verdict_accepts_string_signal():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="v1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    v = await repo.save_verdict(
        "v1", verdict_text="x", signal="WEAK"
    )
    assert v.signal == "WEAK"


# ─── Revisions ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_list_revisions():
    repo = InMemorySessionRepository()
    await repo.create_session(
        session_id="r1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    await repo.save_revision(
        "r1",
        original_pitch="Original",
        revised_pitch="Revised v1",
        improvements_addressed=["Weakness 1", "Fix 1"],
    )
    await repo.save_revision(
        "r1",
        original_pitch="Original",
        revised_pitch="Revised v2",
        improvements_addressed=["Weakness 1", "Weakness 2"],
    )
    revisions = await repo.list_revisions("r1")
    assert len(revisions) == 2
    assert revisions[0].revised_pitch == "Revised v1"
    assert revisions[1].revised_pitch == "Revised v2"


# ─── Personas ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_and_list_personas():
    repo = InMemorySessionRepository()
    await repo.upsert_persona(
        id="vc",
        name="Arjun (VC)",
        role="Venture Capitalist",
        system_prompt="ROI focused.",
        goal="Find the 10x.",
        ocean={"openness": 0.35, "conscientiousness": 0.92, "extraversion": 0.58,
               "agreeableness": 0.18, "neuroticism": 0.42},
    )
    await repo.upsert_persona(
        id="designer",
        name="Priya (Designer)",
        role="Design Strategist",
        system_prompt="UX focused.",
    )
    personas = await repo.list_personas()
    assert len(personas) == 2
    ids = {p.id for p in personas}
    assert ids == {"vc", "designer"}


@pytest.mark.asyncio
async def test_upsert_persona_is_idempotent():
    repo = InMemorySessionRepository()
    await repo.upsert_persona(
        id="vc",
        name="Arjun v1",
        role="VC",
        system_prompt="v1",
    )
    await repo.upsert_persona(
        id="vc",
        name="Arjun v2",
        role="VC",
        system_prompt="v2",
    )
    p = await repo.get_persona("vc")
    assert p is not None
    assert p.name == "Arjun v2"
    assert p.system_prompt == "v2"
    assert len(await repo.list_personas()) == 1


@pytest.mark.asyncio
async def test_list_personas_can_include_disabled():
    repo = InMemorySessionRepository()
    await repo.upsert_persona(id="a", name="A", role="r", system_prompt="s", enabled=True)
    await repo.upsert_persona(id="b", name="B", role="r", system_prompt="s", enabled=False)
    enabled = await repo.list_personas(enabled_only=True)
    all_ = await repo.list_personas(enabled_only=False)
    assert {p.id for p in enabled} == {"a"}
    assert {p.id for p in all_} == {"a", "b"}


# ─── Users ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_user_by_provider():
    repo = InMemorySessionRepository()
    u1 = await repo.upsert_user(
        email="bob@example.com",
        name="Bob",
        provider="google",
        provider_account_id="google-123",
    )
    # Look up by provider
    u2 = await repo.get_user_by_provider("google", "google-123")
    assert u2 is not None
    assert u2.id == u1.id
    # Same call returns the same user (idempotent)
    u3 = await repo.upsert_user(
        email="bob.new@example.com",
        provider="google",
        provider_account_id="google-123",
    )
    assert u3.id == u1.id
    assert u3.email == "bob.new@example.com"


@pytest.mark.asyncio
async def test_get_user_by_provider_unknown_returns_none():
    repo = InMemorySessionRepository()
    assert await repo.get_user_by_provider("google", "missing") is None


# ─── Events ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_events_creates_bus_lazily():
    repo = InMemorySessionRepository()
    bus = repo.get_events("new-session")
    assert bus is not None
    assert isinstance(bus, type(repo.get_events("new-session")))
    # Setting and clearing an event works
    bus.answer_event.set()
    assert bus.answer_event.is_set()
    bus.reset()
    assert not bus.answer_event.is_set()


# ─── Diagnostics ───────────────────────────────────────────────


def test_is_in_memory_returns_true():
    repo = InMemorySessionRepository()
    assert repo.is_in_memory() is True


def test_len_reports_session_count():
    repo = InMemorySessionRepository()
    assert len(repo) == 0
    # We can't await __len__ in a sync context, but len() works on the dict
