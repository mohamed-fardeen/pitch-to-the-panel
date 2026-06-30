"""
SqlAlchemySessionRepository — the production implementation.

Persists every session, turn, verdict, revision, persona, and user to the
SQL database selected by DATABASE_URL. Uses the async engine from
`database.py`.

The asyncio event bus is *not* persisted (it's process-local by design) —
it's held in a per-process dict, but tied to the same session_id. If you
run multiple processes, each process has its own event bus; the in-flight
session lives in whichever process originated it (sticky sessions required).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .database import get_sessionmaker
from .models import (
    AgentPersona,
    ApiKey,
    PitchRevision,
    PitchSession,
    PitchTurn,
    PitchVerdict,
    PromptExperiment,
    SessionStatus,
    TurnRole,
    TurnType,
    User,
    VerdictSignal,
)
from .repository import SessionEventBus, SessionRepository

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlAlchemySessionRepository(SessionRepository):
    """Production repository backed by SQLAlchemy 2.0 (async)."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._sessionmaker = sessionmaker or get_sessionmaker()
        # Per-process event buses. Same lifetime caveat as the in-memory repo.
        self._events: dict[str, SessionEventBus] = {}

    # ─── Lifecycle ────────────────────────────────────────────────

    async def create_session(
        self,
        *,
        session_id: str,
        pitch: str,
        mode: str,
        provider: str,
        aggressiveness: int = 5,
        user_id: str | None = None,
    ) -> PitchSession:
        now = _utcnow()
        session = PitchSession(
            id=session_id,
            user_id=user_id,
            pitch_summary=pitch,
            mode=mode,
            provider=provider,
            aggressiveness=aggressiveness,
            status=SessionStatus.CREATED.value,
            domain={},
            hitl_data={},
            global_memory={
                "claims": [],
                "risks": [],
                "strengths": [],
                "contradictions": [],
                "opinions": [],
                "covered_topics": [],
            },
            agent_memory={},
            memory_history=[],
            active_panel=[],
            started_at=now,
        )
        async with self._sessionmaker() as db:
            db.add(session)
            await db.commit()
            await db.refresh(session)
        self._events[session_id] = SessionEventBus()
        logger.debug("Created DB session %s", session_id)
        return session

    async def get_session(self, session_id: str) -> PitchSession | None:
        async with self._sessionmaker() as db:
            return await db.get(PitchSession, session_id)

    async def list_sessions_for_user(
        self, user_id: str, limit: int = 50
    ) -> list[PitchSession]:
        async with self._sessionmaker() as db:
            stmt = (
                select(PitchSession)
                .where(PitchSession.user_id == user_id)
                .order_by(PitchSession.created_at.desc())
                .limit(limit)
            )
            result = await db.execute(stmt)
            return list(result.scalars().all())

    async def update_session(
        self, session_id: str, **fields: Any
    ) -> PitchSession | None:
        async with self._sessionmaker() as db:
            session = await db.get(PitchSession, session_id)
            if session is None:
                return None
            for k, v in fields.items():
                if not hasattr(session, k):
                    raise AttributeError(f"Session has no field {k!r}")
                setattr(session, k, v)
            session.updated_at = _utcnow()
            await db.commit()
            await db.refresh(session)
            return session

    async def delete_session(self, session_id: str) -> bool:
        async with self._sessionmaker() as db:
            session = await db.get(PitchSession, session_id)
            if session is None:
                return False
            await db.delete(session)
            await db.commit()
        self._events.pop(session_id, None)
        return True

    # ─── Turns ────────────────────────────────────────────────────

    async def append_turn(
        self,
        session_id: str,
        *,
        step_index: int,
        role: TurnRole | str,
        turn_type: TurnType | str,
        content: str,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> PitchTurn:
        role_val = role.value if isinstance(role, TurnRole) else str(role)
        type_val = turn_type.value if isinstance(turn_type, TurnType) else str(turn_type)
        turn = PitchTurn(
            id=str(uuid.uuid4()),
            session_id=session_id,
            step_index=step_index,
            role=role_val,
            turn_type=type_val,
            agent_id=agent_id,
            agent_name=agent_name,
            content=content,
        )
        async with self._sessionmaker() as db:
            db.add(turn)
            await db.commit()
            await db.refresh(turn)
        return turn

    async def list_turns(self, session_id: str) -> list[PitchTurn]:
        async with self._sessionmaker() as db:
            stmt = (
                select(PitchTurn)
                .where(PitchTurn.session_id == session_id)
                .order_by(PitchTurn.step_index)
            )
            result = await db.execute(stmt)
            return list(result.scalars().all())

    # ─── Verdict ──────────────────────────────────────────────────

    async def save_verdict(
        self,
        session_id: str,
        *,
        verdict_text: str,
        strongest: str | None = None,
        weakness: str | None = None,
        fix: str | None = None,
        investment_score: float | None = None,
        recommendation: str | None = None,
        confidence_score: int = 0,
        signal: VerdictSignal | str = VerdictSignal.MEDIUM,
        charts: dict[str, Any] | None = None,
    ) -> PitchVerdict:
        signal_val = signal.value if isinstance(signal, VerdictSignal) else str(signal)
        async with self._sessionmaker() as db:
            await db.get(PitchVerdict, None)  # not by id, need query
            stmt = select(PitchVerdict).where(PitchVerdict.session_id == session_id)
            result = await db.execute(stmt)
            verdict = result.scalar_one_or_none()

            if verdict is not None:
                verdict.verdict_text = verdict_text
                verdict.strongest = strongest
                verdict.weakness = weakness
                verdict.fix = fix
                verdict.investment_score = investment_score
                verdict.recommendation = recommendation
                verdict.confidence_score = confidence_score
                verdict.signal = signal_val
                if charts is not None:
                    verdict.charts = charts
                verdict.updated_at = _utcnow()
            else:
                verdict = PitchVerdict(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    verdict_text=verdict_text,
                    strongest=strongest,
                    weakness=weakness,
                    fix=fix,
                    investment_score=investment_score,
                    recommendation=recommendation,
                    confidence_score=confidence_score,
                    signal=signal_val,
                    charts=charts or {},
                )
                db.add(verdict)

            await db.commit()
            await db.refresh(verdict)
            return verdict

    async def get_verdict(self, session_id: str) -> PitchVerdict | None:
        async with self._sessionmaker() as db:
            stmt = select(PitchVerdict).where(PitchVerdict.session_id == session_id)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    # ─── Revisions ────────────────────────────────────────────────

    async def save_revision(
        self,
        session_id: str,
        *,
        original_pitch: str,
        revised_pitch: str,
        improvements_addressed: list[str],
    ) -> PitchRevision:
        revision = PitchRevision(
            id=str(uuid.uuid4()),
            session_id=session_id,
            original_pitch=original_pitch,
            revised_pitch=revised_pitch,
            improvements_addressed=improvements_addressed,
        )
        async with self._sessionmaker() as db:
            db.add(revision)
            await db.commit()
            await db.refresh(revision)
        return revision

    async def list_revisions(self, session_id: str) -> list[PitchRevision]:
        async with self._sessionmaker() as db:
            stmt = (
                select(PitchRevision)
                .where(PitchRevision.session_id == session_id)
                .order_by(PitchRevision.created_at)
            )
            result = await db.execute(stmt)
            return list(result.scalars().all())

    # ─── Personas ─────────────────────────────────────────────────

    async def upsert_persona(
        self,
        *,
        id: str,
        name: str,
        role: str,
        system_prompt: str,
        goal: str = "",
        ocean: dict[str, float] | None = None,
        config: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> AgentPersona:
        ocean = ocean or {}
        async with self._sessionmaker() as db:
            persona = await db.get(AgentPersona, id)
            if persona is not None:
                persona.name = name
                persona.role = role
                persona.system_prompt = system_prompt
                persona.goal = goal
                persona.ocean_openness = ocean.get("openness", persona.ocean_openness)
                persona.ocean_conscientiousness = ocean.get(
                    "conscientiousness", persona.ocean_conscientiousness
                )
                persona.ocean_extraversion = ocean.get("extraversion", persona.ocean_extraversion)
                persona.ocean_agreeableness = ocean.get("agreeableness", persona.ocean_agreeableness)
                persona.ocean_neuroticism = ocean.get("neuroticism", persona.ocean_neuroticism)
                if config is not None:
                    persona.config = config
                persona.enabled = enabled
                persona.updated_at = _utcnow()
            else:
                persona = AgentPersona(
                    id=id,
                    name=name,
                    role=role,
                    system_prompt=system_prompt,
                    goal=goal,
                    ocean_openness=ocean.get("openness", 0.5),
                    ocean_conscientiousness=ocean.get("conscientiousness", 0.5),
                    ocean_extraversion=ocean.get("extraversion", 0.5),
                    ocean_agreeableness=ocean.get("agreeableness", 0.5),
                    ocean_neuroticism=ocean.get("neuroticism", 0.5),
                    config=config or {},
                    enabled=enabled,
                )
                db.add(persona)
            await db.commit()
            await db.refresh(persona)
            return persona

    async def get_persona(self, persona_id: str) -> AgentPersona | None:
        async with self._sessionmaker() as db:
            return await db.get(AgentPersona, persona_id)

    async def list_personas(self, enabled_only: bool = True) -> list[AgentPersona]:
        async with self._sessionmaker() as db:
            stmt = select(AgentPersona).order_by(AgentPersona.id)
            if enabled_only:
                stmt = stmt.where(AgentPersona.enabled.is_(True))
            result = await db.execute(stmt)
            return list(result.scalars().all())

    # ─── Users ────────────────────────────────────────────────────

    async def upsert_user(
        self,
        *,
        email: str | None = None,
        name: str | None = None,
        image_url: str | None = None,
        provider: str = "email",
        provider_account_id: str | None = None,
    ) -> User:
        async with self._sessionmaker() as db:
            user: User | None = None
            if provider_account_id:
                stmt = select(User).where(
                    User.provider == provider,
                    User.provider_account_id == provider_account_id,
                )
                result = await db.execute(stmt)
                user = result.scalar_one_or_none()

            if user is not None:
                if email is not None:
                    user.email = email
                if name is not None:
                    user.name = name
                if image_url is not None:
                    user.image_url = image_url
                user.updated_at = _utcnow()
            else:
                user = User(
                    id=str(uuid.uuid4()),
                    email=email,
                    name=name,
                    image_url=image_url,
                    provider=provider,
                    provider_account_id=provider_account_id,
                )
                db.add(user)

            await db.commit()
            await db.refresh(user)
            return user

    async def get_user(self, user_id: str) -> User | None:
        async with self._sessionmaker() as db:
            return await db.get(User, user_id)

    async def get_user_by_provider(
        self, provider: str, provider_account_id: str
    ) -> User | None:
        async with self._sessionmaker() as db:
            stmt = select(User).where(
                User.provider == provider,
                User.provider_account_id == provider_account_id,
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    # ─── Events (process-local) ──────────────────────────────────

    def get_events(self, session_id: str) -> SessionEventBus:
        if session_id not in self._events:
            self._events[session_id] = SessionEventBus()
        return self._events[session_id]

    # ─── API Keys (Tier-2b) ─────────────────────────────────────

    async def create_api_key(
        self,
        *,
        name: str,
        key_hash: str,
        key_prefix: str,
        user_id: str | None = None,
        scopes: list[str] | None = None,
        expires_at: Any | None = None,
        rate_limit_per_minute: int | None = None,
    ) -> ApiKey:
        from .models import ApiKey
        key = ApiKey(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=user_id,
            scopes=list(scopes or []),
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
        )
        async with self._sessionmaker() as session:
            session.add(key)
            await session.commit()
            await session.refresh(key)
        return key

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        from datetime import datetime
        async with self._sessionmaker() as session:
            from sqlalchemy import select
            stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
            result = await session.execute(stmt)
            key = result.scalar_one_or_none()
            if key is None:
                return None
            if not key.is_active or key.revoked_at is not None:
                return None
            if key.expires_at is not None and datetime.now(UTC) > key.expires_at:
                return None
            return key

    async def list_api_keys(self, user_id: str | None = None) -> list[ApiKey]:
        from sqlalchemy import select
        async with self._sessionmaker() as session:
            stmt = select(ApiKey).order_by(ApiKey.created_at.desc())
            if user_id is not None:
                stmt = stmt.where(ApiKey.user_id == user_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def revoke_api_key(self, key_id: str) -> bool:
        from datetime import datetime
        async with self._sessionmaker() as session:
            key = await session.get(ApiKey, key_id)
            if key is None:
                return False
            key.is_active = False
            key.revoked_at = datetime.now(UTC)
            await session.commit()
            return True

    async def record_api_key_usage(self, key_id: str) -> None:
        from datetime import datetime

        from sqlalchemy import update
        async with self._sessionmaker() as session:
            await session.execute(
                update(ApiKey)
                .where(ApiKey.id == key_id)
                .values(
                    total_requests=ApiKey.total_requests + 1,
                    last_used_at=datetime.now(UTC),
                )
            )
            await session.commit()

    # ─── Prompt Experiments (Tier-2c) ───────────────────────────

    async def create_prompt_experiment(
        self, experiment: PromptExperiment
    ) -> PromptExperiment:
        async with self._sessionmaker() as session:
            session.add(experiment)
            await session.commit()
            await session.refresh(experiment)
            return experiment

    async def get_prompt_experiment_by_name(
        self, name: str
    ) -> PromptExperiment | None:
        from sqlalchemy import select
        async with self._sessionmaker() as session:
            stmt = select(PromptExperiment).where(PromptExperiment.name == name)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def update_prompt_experiment(
        self, experiment: PromptExperiment
    ) -> PromptExperiment:
        from datetime import datetime
        async with self._sessionmaker() as session:
            existing = await session.get(PromptExperiment, experiment.id)
            if existing is None:
                session.add(experiment)
            else:
                existing.description = experiment.description
                existing.is_active = experiment.is_active
                existing.variant_weights = dict(experiment.variant_weights)
                existing.meta = dict(experiment.meta)
                existing.updated_at = datetime.now(UTC)
                experiment = existing
            await session.commit()
            await session.refresh(experiment)
            return experiment

    async def record_prompt_outcome(
        self,
        *,
        experiment_name: str,
        session_id: str,
        metric_name: str,
        metric_value: float,
    ) -> None:
        # For Postgres, persist outcomes in a separate table. For Tier-2c v1
        # we keep this simple: if there's no PromptOutcome table, do nothing.
        # (The full implementation lands in a follow-up PR alongside
        # Alembic migrations.)
        return None

    async def list_prompt_outcomes(
        self, experiment_name: str, metric_name: str
    ) -> list[tuple[str, str, float]]:
        return []

    # ─── Diagnostics ──────────────────────────────────────────────

    def is_in_memory(self) -> bool:
        return False


__all__ = ["SqlAlchemySessionRepository"]
