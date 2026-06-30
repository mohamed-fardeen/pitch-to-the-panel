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

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

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
        # Tier-2b: API keys
        self._api_keys: dict[str, ApiKey] = {}  # by key id
        self._api_key_by_hash: dict[str, str] = {}  # hash -> key id
        # Tier-2c: Prompt experiments
        self._experiments: dict[str, PromptExperiment] = {}  # by name
        # Outcomes: keyed by (experiment_name, metric_name), value is
        # list of (variant, assignment_id, session_id, value).
        self._outcomes: dict[str, list[tuple[str, str, str, float]]] = {}

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

    async def get_session(self, session_id: str) -> PitchSession | None:
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
    ) -> PitchSession | None:
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
        agent_id: str | None = None,
        agent_name: str | None = None,
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
        strongest: str | None = None,
        weakness: str | None = None,
        fix: str | None = None,
        investment_score: float | None = None,
        recommendation: str | None = None,
        confidence_score: int = 0,
        signal: VerdictSignal | str = VerdictSignal.MEDIUM,
        charts: dict[str, Any] | None = None,
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

    async def get_verdict(self, session_id: str) -> PitchVerdict | None:
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
        ocean: dict[str, float] | None = None,
        config: dict[str, Any] | None = None,
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

    async def get_persona(self, persona_id: str) -> AgentPersona | None:
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
        email: str | None = None,
        name: str | None = None,
        image_url: str | None = None,
        provider: str = "email",
        provider_account_id: str | None = None,
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

    async def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    async def get_user_by_provider(
        self, provider: str, provider_account_id: str
    ) -> User | None:
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
        import uuid as _uuid_lib
        from datetime import datetime

        from .models import ApiKey
        now = datetime.now(UTC)
        key = ApiKey(
            id=str(_uuid_lib.uuid4()),
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=user_id,
            scopes=list(scopes or []),
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
            created_at=now,
            updated_at=now,
        )
        self._api_keys[key.id] = key
        self._api_key_by_hash[key_hash] = key.id
        return key

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        from datetime import datetime
        key_id = self._api_key_by_hash.get(key_hash)
        if key_id is None:
            return None
        key = self._api_keys.get(key_id)
        if key is None:
            return None
        # Skip revoked or expired keys
        if not key.is_active or key.revoked_at is not None:
            return None
        if key.expires_at is not None and datetime.now(UTC) > key.expires_at:
            return None
        return key

    async def list_api_keys(self, user_id: str | None = None) -> list[ApiKey]:
        rows = list(self._api_keys.values())
        if user_id is not None:
            rows = [k for k in rows if k.user_id == user_id]
        # Newest first
        rows.sort(key=lambda k: k.created_at, reverse=True)
        return rows

    async def revoke_api_key(self, key_id: str) -> bool:
        from datetime import datetime
        key = self._api_keys.get(key_id)
        if key is None:
            return False
        key.is_active = False
        key.revoked_at = datetime.now(UTC)
        return True

    async def record_api_key_usage(self, key_id: str) -> None:
        from datetime import datetime
        key = self._api_keys.get(key_id)
        if key is None:
            return
        key.total_requests += 1
        key.last_used_at = datetime.now(UTC)

    # ─── Prompt Experiments (Tier-2c) ───────────────────────────

    async def create_prompt_experiment(
        self, experiment: PromptExperiment
    ) -> PromptExperiment:
        from datetime import datetime
        if not experiment.id:
            experiment.id = str(uuid.uuid4())
        experiment.created_at = experiment.created_at or datetime.now(UTC)
        experiment.updated_at = experiment.created_at
        self._experiments[experiment.name] = experiment
        return experiment

    async def get_prompt_experiment_by_name(
        self, name: str
    ) -> PromptExperiment | None:
        return self._experiments.get(name)

    async def update_prompt_experiment(
        self, experiment: PromptExperiment
    ) -> PromptExperiment:
        from datetime import datetime
        if experiment.name not in self._experiments:
            # Insert if missing
            return await self.create_prompt_experiment(experiment)
        existing = self._experiments[experiment.name]
        existing.description = experiment.description
        existing.is_active = experiment.is_active
        existing.variant_weights = dict(experiment.variant_weights)
        existing.meta = dict(experiment.meta)
        existing.updated_at = datetime.now(UTC)
        return existing

    async def record_prompt_outcome(
        self,
        *,
        experiment_name: str,
        session_id: str,
        metric_name: str,
        metric_value: float,
    ) -> None:
        from uuid import uuid4

        from prompts_versions.router import pick_variant

        exp = self._experiments.get(experiment_name)
        if exp is None:
            return  # No experiment — silently ignore
        # Determine the variant (deterministic by session_id, like the router)
        variant = pick_variant(
            experiment_name, session_id, dict(exp.variant_weights)
        )
        key = f"{experiment_name}:{metric_name}"
        outcomes = self._outcomes.setdefault(key, [])
        # If there's already an outcome for this session, update it
        for i, (v, _aid, sid, _val) in enumerate(outcomes):
            if v == variant and sid == session_id:
                outcomes[i] = (variant, str(uuid4()), session_id, metric_value)
                return
        outcomes.append((variant, str(uuid4()), session_id, metric_value))

    async def list_prompt_outcomes(
        self, experiment_name: str, metric_name: str
    ) -> list[tuple[str, str, float]]:
        """Returns (variant, assignment_id, value) tuples."""
        key = f"{experiment_name}:{metric_name}"
        return [
            (variant, aid, value)
            for variant, aid, _sid, value in self._outcomes.get(key, [])
        ]


__all__ = ["InMemorySessionRepository"]
