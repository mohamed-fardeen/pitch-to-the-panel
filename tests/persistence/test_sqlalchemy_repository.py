"""
Tests for the SQLAlchemy SessionRepository implementation.

These mirror `test_in_memory_repository.py` and verify the SQL backend
satisfies the same contract. They use a per-test temporary SQLite file
to keep tests isolated and fast.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.persistence.database import create_all_tables, drop_all_tables, get_sessionmaker
from backend.persistence.models import (
    SessionStatus,
    TurnRole,
    TurnType,
    VerdictSignal,
)
from backend.persistence.sqlalchemy_repository import SqlAlchemySessionRepository


@pytest_asyncio.fixture
async def repo(temp_sqlite_url: str) -> SqlAlchemySessionRepository:
    """Build a fresh SQLAlchemy repo against a per-test SQLite file."""
    # Each repo gets its own sessionmaker (otherwise they'd share connection state)
    sessionmaker = get_sessionmaker(temp_sqlite_url)
    # Wipe any prior state and create fresh tables
    await drop_all_tables()
    await create_all_tables()
    yield SqlAlchemySessionRepository(sessionmaker=sessionmaker)
    # Cleanup
    await drop_all_tables()


# ─── Lifecycle ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_get_session(repo: SqlAlchemySessionRepository):
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
    assert session.status == SessionStatus.CREATED.value

    fetched = await repo.get_session("sess-1")
    assert fetched is not None
    assert fetched.pitch_summary == "AI-powered CRM for dentists"


@pytest.mark.asyncio
async def test_create_session_duplicate_raises(repo: SqlAlchemySessionRepository):
    await repo.create_session(
        session_id="dup",
        pitch="x",
        mode="venture",
        provider="groq",
    )
    with pytest.raises(Exception):  # IntegrityError
        await repo.create_session(
            session_id="dup",
            pitch="x",
            mode="venture",
            provider="groq",
        )


@pytest.mark.asyncio
async def test_get_unknown_session_returns_none(repo: SqlAlchemySessionRepository):
    assert await repo.get_session("nope") is None


@pytest.mark.asyncio
async def test_update_session_persists(repo: SqlAlchemySessionRepository):
    await repo.create_session(
        session_id="u1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    await repo.update_session(
        "u1",
        refined_pitch="A refined pitch",
        status=SessionStatus.DEBATING.value,
        current_step=3,
    )
    # Re-fetch to confirm the change was committed
    fetched = await repo.get_session("u1")
    assert fetched is not None
    assert fetched.refined_pitch == "A refined pitch"
    assert fetched.status == SessionStatus.DEBATING.value
    assert fetched.current_step == 3


@pytest.mark.asyncio
async def test_delete_session_removes_row(repo: SqlAlchemySessionRepository):
    await repo.create_session(
        session_id="d1",
        pitch="p",
        mode="venture",
        provider="groq",
    )
    assert await repo.delete_session("d1") is True
    assert await repo.get_session("d1") is None
    # Idempotent
    assert await repo.delete_session("d1") is False


@pytest.mark.asyncio
async def test_list_sessions_for_user(repo: SqlAlchemySessionRepository):
    user = await repo.upsert_user(email="x@example.com", provider="email", provider_account_id="x-1")
    s1 = await repo.create_session(
        session_id="s1", pitch="p1", mode="venture", provider="groq", user_id=user.id
    )
    s2 = await repo.create_session(
        session_id="s2", pitch="p2", mode="venture", provider="groq", user_id=user.id
    )
    s3 = await repo.create_session(
        session_id="s3", pitch="p3", mode="venture", provider="groq"  # no user
    )
    listed = await repo.list_sessions_for_user(user.id)
    assert len(listed) == 2
    listed_ids = {s.id for s in listed}
    assert listed_ids == {"s1", "s2"}


# ─── Turns ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_append_and_list_turns_in_order(repo: SqlAlchemySessionRepository):
    await repo.create_session(
        session_id="t1", pitch="p", mode="venture", provider="groq"
    )
    await repo.append_turn(
        "t1", step_index=2, role=TurnRole.PERSONA, turn_type=TurnType.QUESTION,
        content="third (out of order)", agent_id="vc", agent_name="Arjun",
    )
    await repo.append_turn(
        "t1", step_index=0, role=TurnRole.PERSONA, turn_type=TurnType.QUESTION,
        content="first", agent_id="vc", agent_name="Arjun",
    )
    await repo.append_turn(
        "t1", step_index=1, role=TurnRole.PITCHER, turn_type=TurnType.ANSWER,
        content="second",
    )
    turns = await repo.list_turns("t1")
    assert [t.step_index for t in turns] == [0, 1, 2]
    assert [t.content for t in turns] == ["first", "second", "third (out of order)"]


# ─── Verdict ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_get_verdict_persists(repo: SqlAlchemySessionRepository):
    await repo.create_session(
        session_id="v1", pitch="p", mode="venture", provider="groq"
    )
    await repo.save_verdict(
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
    fetched = await repo.get_verdict("v1")
    assert fetched is not None
    assert fetched.strongest == "Strong team"
    assert fetched.confidence_score == 72


@pytest.mark.asyncio
async def test_save_verdict_upserts(repo: SqlAlchemySessionRepository):
    """Saving twice on the same session updates the same row."""
    await repo.create_session(
        session_id="v1", pitch="p", mode="venture", provider="groq"
    )
    await repo.save_verdict("v1", verdict_text="first", confidence_score=50)
    v2 = await repo.save_verdict("v1", verdict_text="second", confidence_score=80)
    fetched = await repo.get_verdict("v1")
    assert fetched is not None
    assert fetched.id == v2.id
    assert fetched.verdict_text == "second"
    assert fetched.confidence_score == 80


# ─── Revisions ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_and_list_revisions(repo: SqlAlchemySessionRepository):
    await repo.create_session(
        session_id="r1", pitch="p", mode="venture", provider="groq"
    )
    await repo.save_revision(
        "r1", original_pitch="Original", revised_pitch="v1",
        improvements_addressed=["A"],
    )
    await repo.save_revision(
        "r1", original_pitch="Original", revised_pitch="v2",
        improvements_addressed=["A", "B"],
    )
    revisions = await repo.list_revisions("r1")
    assert [r.revised_pitch for r in revisions] == ["v1", "v2"]


# ─── Personas ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_and_list_personas(repo: SqlAlchemySessionRepository):
    await repo.upsert_persona(
        id="vc", name="Arjun", role="VC", system_prompt="ROI", goal="Find 10x",
    )
    await repo.upsert_persona(
        id="designer", name="Priya", role="Designer", system_prompt="UX",
    )
    personas = await repo.list_personas()
    assert {p.id for p in personas} == {"vc", "designer"}


@pytest.mark.asyncio
async def test_upsert_persona_updates(repo: SqlAlchemySessionRepository):
    await repo.upsert_persona(id="vc", name="Arjun v1", role="VC", system_prompt="v1")
    await repo.upsert_persona(id="vc", name="Arjun v2", role="VC", system_prompt="v2")
    p = await repo.get_persona("vc")
    assert p is not None
    assert p.name == "Arjun v2"
    assert p.system_prompt == "v2"


# ─── Users ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_upsert_user_idempotent_by_provider(repo: SqlAlchemySessionRepository):
    u1 = await repo.upsert_user(
        email="bob@example.com", provider="google", provider_account_id="g-1"
    )
    u2 = await repo.upsert_user(
        email="bob.new@example.com", provider="google", provider_account_id="g-1"
    )
    assert u1.id == u2.id
    assert u2.email == "bob.new@example.com"
    fetched = await repo.get_user_by_provider("google", "g-1")
    assert fetched is not None
    assert fetched.id == u1.id


# ─── Events ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_events_are_process_local(repo: SqlAlchemySessionRepository):
    bus1 = repo.get_events("sess-1")
    bus2 = repo.get_events("sess-1")
    assert bus1 is bus2  # same event bus per session
    bus1.answer_event.set()
    assert bus2.answer_event.is_set()
    bus1.reset()
    assert not bus2.answer_event.is_set()


# ─── Diagnostics ───────────────────────────────────────────────


def test_is_in_memory_returns_false():
    from backend.persistence.database import get_sessionmaker
    repo = SqlAlchemySessionRepository(sessionmaker=get_sessionmaker("sqlite+aiosqlite:///:memory:"))
    assert repo.is_in_memory() is False
