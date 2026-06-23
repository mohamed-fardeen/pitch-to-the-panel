"""
InMemorySessionRepository — the default implementation, used in dev and tests.

Behaves identically to the legacy `sessions: dict` in `backend/orchestrator.py`,
so swapping it in is a non-breaking change. State lives in process memory only —
restart the server and everything is gone.

This implementation is also useful as a reference for the SQLAlchemy
implementation: every method here corresponds to one in
`sqlalchemy_repository.py`.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .models import (
    AgentPersona,
    PitchRevision,
    PitchSession,
    PitchTurn,
    PitchVerdict,
    SessionStatus,
    TurnRole,
    TurnType,
    User,
    VerdictSignal,
)
from .repository import SessionEventBus, SessionRepository

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class InMemorySessionRepository(SessionRepository):
    """
    Drop-in replacement for the legacy `sessions: dict[str, dict]`.

    State is held in three dicts:
    - _sessions:  session_id       -> PitchSession
    - _users:     user_id          -> User
    - _personas:  persona_id       -> AgentPersona
    - _events:    session_id       -> SessionEventBus

    Plus a global User lookup index by (provider, account_id) for OAuth.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, PitchSession] = {}
        self._users: dict[str, User] = {}
        self._personas: dict[str, AgentPersona] = {}
        self._events: dict[str, SessionEventBus] = {}
        self._user_by_provider: dict[tuple[str, str], str] = {}
        self._session_turns: dict[str, list[PitchTurn]] = {}
        self._session_revisions: dict[str, list[PitchRevision]] = {}
        self._session_verdicts: dict[str, PitchVerdict] = {}

    # ─── Lifecycle ────────────────────────────────────────────────

    async def create_session(
        self,
        *,
        session_id: str,
        pitch: str,
        mode: str,
        provider: str,
        aggressiveness: int = 5,
        user_id: Optional[str] = None,
    ) -> PitchSession:
        if session_id in self._sessions:
            raise ValueError(f"Session {session_id!r} already exists")

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
            created_at=now,
            updated_at=now,
            started_at=now,
        )
        self._sessions[session_id] = session
        self._session_turns[session_id] = []
        self._session_revisions[session_id] = []
        self._events[session_id] = SessionEventBus()
        logger.debug("Created in-memory session %s", session_id)
        return session

    async def get_session(self, session_id: str) -> Optional[PitchSession]:
        return self._sessions.get(session_id)

    async def list_sessions_for_user(
        self, user_id: str, limit: int = 50
    ) -> list[PitchSession]:
        rows = [s for s in self._sessions.values() if s.user_id == user_id]
        # Defend against None created_at (shouldn't happen but be safe)
        rows.sort(
            key=lambda s: s.created_at or _utcnow(),
            reverse=True,
        )
        return rows[:limit]

    async def update_session(
        self, session_id: str, **fields: Any
    ) -> Optional[PitchSession]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        for k, v in fields.items():
            if not hasattr(session, k):
                raise AttributeError(f"Session has no field {k!r}")
            setattr(session, k, v)
        session.updated_at = _utcnow()
        return session

    async def delete_session(self, session_id: str) -> bool:
        existed = session_id in self._sessions
        self._sessions.pop(session_id, None)
        self._session_turns.pop(session_id, None)
        self._session_revisions.pop(session_id, None)
        self._session_verdicts.pop(session_id, None)
        self._events.pop(session_id, None)
        return existed

    # ─── Turns ────────────────────────────────────────────────────

    async def append_turn(
        self,
        session_id: str,
        *,
        step_index: int,
        role: TurnRole | str,
        turn_type: TurnType | str,
        content: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> PitchTurn:
        if session_id not in self._sessions:
            raise KeyError(f"Unknown session {session_id!r}")
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
        self._session_turns[session_id].append(turn)
        return turn

    async def list_turns(self, session_id: str) -> list[PitchTurn]:
        return list(self._session_turns.get(session_id, []))

    # ─── Verdict ──────────────────────────────────────────────────

    async def save_verdict(
        self,
        session_id: str,
        *,
        verdict_text: str,
        strongest: Optional[str] = None,
        weakness: Optional[str] = None,
        fix: Optional[str] = None,
        investment_score: Optional[float] = None,
        recommendation: Optional[str] = None,
        confidence_score: int = 0,
        signal: VerdictSignal | str = VerdictSignal.MEDIUM,
        charts: Optional[dict[str, Any]] = None,
    ) -> PitchVerdict:
        if session_id not in self._sessions:
            raise KeyError(f"Unknown session {session_id!r}")
        signal_val = signal.value if isinstance(signal, VerdictSignal) else str(signal)
        existing = self._session_verdicts.get(session_id)
        if existing is not None:
            existing.verdict_text = verdict_text
            existing.strongest = strongest
            existing.weakness = weakness
            existing.fix = fix
            existing.investment_score = investment_score
            existing.recommendation = recommendation
            existing.confidence_score = confidence_score
            existing.signal = signal_val
            if charts is not None:
                existing.charts = charts
            existing.updated_at = _utcnow()
            return existing
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
        self._session_verdicts[session_id] = verdict
        return verdict

    async def get_verdict(self, session_id: str) -> Optional[PitchVerdict]:
        return self._session_verdicts.get(session_id)

    # ─── Revisions ────────────────────────────────────────────────

    async def save_revision(
        self,
        session_id: str,
        *,
        original_pitch: str,
        revised_pitch: str,
        improvements_addressed: list[str],
    ) -> PitchRevision:
        if session_id not in self._sessions:
            raise KeyError(f"Unknown session {session_id!r}")
        revision = PitchRevision(
            id=str(uuid.uuid4()),
            session_id=session_id,
            original_pitch=original_pitch,
            revised_pitch=revised_pitch,
            improvements_addressed=improvements_addressed,
        )
        self._session_revisions[session_id].append(revision)
        return revision

    async def list_revisions(self, session_id: str) -> list[PitchRevision]:
        return list(self._session_revisions.get(session_id, []))

    # ─── Personas ─────────────────────────────────────────────────

    async def upsert_persona(
        self,
        *,
        id: str,
        name: str,
        role: str,
        system_prompt: str,
        goal: str = "",
        ocean: Optional[dict[str, float]] = None,
        config: Optional[dict[str, Any]] = None,
        enabled: bool = True,
    ) -> AgentPersona:
        ocean = ocean or {}
        existing = self._personas.get(id)
        if existing is not None:
            existing.name = name
            existing.role = role
            existing.system_prompt = system_prompt
            existing.goal = goal
            existing.ocean_openness = ocean.get("openness", existing.ocean_openness)
            existing.ocean_conscientiousness = ocean.get(
                "conscientiousness", existing.ocean_conscientiousness
            )
            existing.ocean_extraversion = ocean.get("extraversion", existing.ocean_extraversion)
            existing.ocean_agreeableness = ocean.get("agreeableness", existing.ocean_agreeableness)
            existing.ocean_neuroticism = ocean.get("neuroticism", existing.ocean_neuroticism)
            if config is not None:
                existing.config = config
            existing.enabled = enabled
            existing.updated_at = _utcnow()
            return existing

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
        self._personas[id] = persona
        return persona

    async def get_persona(self, persona_id: str) -> Optional[AgentPersona]:
        return self._personas.get(persona_id)

    async def list_personas(self, enabled_only: bool = True) -> list[AgentPersona]:
        rows = list(self._personas.values())
        if enabled_only:
            rows = [p for p in rows if p.enabled]
        return rows

    # ─── Users ────────────────────────────────────────────────────

    async def upsert_user(
        self,
        *,
        email: Optional[str] = None,
        name: Optional[str] = None,
        image_url: Optional[str] = None,
        provider: str = "email",
        provider_account_id: Optional[str] = None,
    ) -> User:
        key = (provider, provider_account_id) if provider_account_id else None
        if key and key in self._user_by_provider:
            user = self._users[self._user_by_provider[key]]
            if email is not None:
                user.email = email
            if name is not None:
                user.name = name
            if image_url is not None:
                user.image_url = image_url
            user.updated_at = _utcnow()
            return user

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            name=name,
            image_url=image_url,
            provider=provider,
            provider_account_id=provider_account_id,
        )
        self._users[user.id] = user
        if key:
            self._user_by_provider[key] = user.id
        return user

    async def get_user(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    async def get_user_by_provider(
        self, provider: str, provider_account_id: str
    ) -> Optional[User]:
        key = (provider, provider_account_id)
        user_id = self._user_by_provider.get(key)
        if user_id is None:
            return None
        return self._users.get(user_id)

    # ─── Events (process-local) ──────────────────────────────────

    def get_events(self, session_id: str) -> SessionEventBus:
        if session_id not in self._events:
            self._events[session_id] = SessionEventBus()
        return self._events[session_id]

    # ─── Diagnostics ──────────────────────────────────────────────

    def is_in_memory(self) -> bool:
        return True

    def __len__(self) -> int:
        """Total live sessions (for tests/diagnostics)."""
        return len(self._sessions)


__all__ = ["InMemorySessionRepository"]
