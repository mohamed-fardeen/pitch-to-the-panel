"""
End-to-end bridge + SQLAlchemy integration test.

This is the "real" test: it actually persists to a SQLite file via the
SQLAlchemy repository, exercising the full bridge → repo → DB path.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from backend.persistence import SqlAlchemySessionRepository
from backend.persistence.database import create_all_tables, drop_all_tables, get_sessionmaker
from backend.persistence.sync import SessionPersistenceBridge


@pytest_asyncio.fixture
async def sql_repo(temp_sqlite_url: str):
    sessionmaker = get_sessionmaker(temp_sqlite_url)
    await drop_all_tables()
    await create_all_tables()
    yield SqlAlchemySessionRepository(sessionmaker=sessionmaker)
    await drop_all_tables()


@pytest.mark.asyncio
async def test_bridge_persists_full_session_lifecycle_to_sqlite(
    sql_repo: SqlAlchemySessionRepository,
):
    """The bridge + SQLAlchemy repo can persist a full session lifecycle:
    create → multiple turns → verdict → revision. Then a fresh query
    through the repo confirms everything was committed.
    """
    bridge = SessionPersistenceBridge(sql_repo)

    # 1. Create the session
    await bridge.session_created(
        session_id="lifecycle-1",
        pitch="AI-powered CRM for dentists",
        mode="venture",
        provider="groq",
        aggressiveness=7,
    )

    # 2. Update the refined pitch
    await bridge.session_updated(
        "lifecycle-1",
        fields={"refined_pitch": "An AI-driven CRM tailored to dental practices."},
    )

    # 3. Record several turns
    for i, (role, content, agent_id, agent_name) in enumerate(
        [
            ("persona", "What's your TAM?", "vc", "Arjun (VC)"),
            ("pitcher", "$2B in the US.", None, "Pitcher"),
            ("persona", "Why dentists specifically?", "hostile", "Ravi (Operator)"),
        ]
    ):
        await bridge.turn_recorded(
            "lifecycle-1",
            step_index=i,
            role=role,
            turn_type="question" if role == "persona" else "answer",
            content=content,
            agent_id=agent_id,
            agent_name=agent_name,
        )

    # 4. Record the final verdict
    await bridge.verdict_recorded(
        "lifecycle-1",
        verdict_text="Conditional go",
        strongest="Clear market segment",
        weakness="No clear moat",
        fix="Build network effects",
        investment_score=7.2,
        recommendation="Conditional",
        confidence_score=72,
        signal="MEDIUM",
    )

    # 5. Record a revision
    await bridge.revision_recorded(
        "lifecycle-1",
        original_pitch="AI-powered CRM for dentists",
        revised_pitch="AI-driven CRM with 10-year data moat for dental practices.",
        improvements_addressed=["No clear moat"],
    )

    # 6. Mark the session as ended
    await bridge.session_ended("lifecycle-1", cancelled=False)

    # ─── Now query fresh and confirm everything was persisted ───
    session = await sql_repo.get_session("lifecycle-1")
    assert session is not None
    assert session.pitch_summary == "AI-powered CRM for dentists"
    assert session.refined_pitch.startswith("An AI-driven CRM")
    assert session.aggressiveness == 7
    assert session.status == "completed"
    assert session.is_cancelled is False
    assert session.completed_at is not None

    turns = await sql_repo.list_turns("lifecycle-1")
    assert len(turns) == 3
    assert turns[0].content == "What's your TAM?"
    assert turns[1].role == "pitcher"
    assert turns[2].agent_id == "hostile"

    verdict = await sql_repo.get_verdict("lifecycle-1")
    assert verdict is not None
    assert verdict.confidence_score == 72
    assert verdict.signal == "MEDIUM"
    assert verdict.investment_score == 7.2

    revisions = await sql_repo.list_revisions("lifecycle-1")
    assert len(revisions) == 1
    assert revisions[0].revised_pitch.startswith("AI-driven CRM")


@pytest.mark.asyncio
async def test_bridge_does_not_persist_in_process_state(sql_repo):
    """Verify that asyncio.Event-shaped values can't sneak into the database."""
    bridge = SessionPersistenceBridge(sql_repo)
    await bridge.session_created(
        session_id="filter-1",
        pitch="x",
        mode="venture",
        provider="groq",
    )
    # Try to push a non-persisted key
    await bridge.session_updated(
        "filter-1",
        fields={
            "refined_pitch": "A fine pitch",  # persisted
            "events": {"answer_event": "THIS WOULD CRASH THE DB"},
            "graph_task": "ALSO BAD",
        },
    )
    session = await sql_repo.get_session("filter-1")
    assert session is not None
    assert session.refined_pitch == "A fine pitch"


@pytest.mark.asyncio
async def test_bridge_survives_repo_errors(monkeypatch):
    """If the repository raises, the bridge should log and continue,
    not propagate the exception to the caller."""
    from backend.persistence.sync import SessionPersistenceBridge

    class BrokenRepo:
        async def create_session(self, **_):
            raise RuntimeError("simulated DB outage")

    bridge = SessionPersistenceBridge(BrokenRepo())  # type: ignore[arg-type]
    # Should not raise
    await bridge.session_created(
        session_id="oops",
        pitch="x",
        mode="venture",
        provider="groq",
    )