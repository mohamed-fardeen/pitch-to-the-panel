"""
SessionRepository — the contract between the orchestrator and any storage layer.

The orchestrator never touches the database directly. Instead, it talks to
a SessionRepository. Two implementations exist:

- InMemorySessionRepository  (default, dev, tests)
- SqlAlchemySessionRepository  (production)

Both expose the same async interface, so swapping them is a one-line change
in main.py.

Threading / concurrency note
────────────────────────────
The orchestrator uses `asyncio.Event` objects to signal between the SSE
generator task and the API endpoints that accept user input. These events
are *in-process* — they don't persist across server restarts and they don't
make sense in a multi-process deployment. So they live on the in-memory
repository (and are not part of the SQLAlchemy schema).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .models import ApiKey

from .models import (
    AgentPersona,
    ApiKey,
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


class SessionEventBus:
    """
    Per-session event bus for asyncio coordination.

    These events are short-lived and process-local. They live alongside the
    repository so that both implementations can offer the same surface area.
    The orchestrator awaits these to coordinate between the SSE task and
    user-input endpoints.
    """

    def __init__(self) -> None:
        self.answer_event = asyncio.Event()
        self.interrupt_event = asyncio.Event()
        self.summary_approved = asyncio.Event()
        self.speech_complete_event = asyncio.Event()

    def reset(self) -> None:
        """Clear all events. Used when a session moves to a new phase."""
        for evt in (
            self.answer_event,
            self.interrupt_event,
            self.summary_approved,
            self.speech_complete_event,
        ):
            evt.clear()


class SessionRepository(ABC):
    """
    Abstract repository. Both the in-memory and SQLAlchemy implementations
    must satisfy this contract.

    A "session" here is the full pitch evaluation: a PitchSession row plus
    its turns, verdict, revisions, and the asyncio event bus.
    """

    # ─── Lifecycle ────────────────────────────────────────────────

    @abstractmethod
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
        """Create a new pitch session and return the row."""

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[PitchSession]:
        """Fetch a session by id, or None if not found."""

    @abstractmethod
    async def list_sessions_for_user(
        self, user_id: str, limit: int = 50
    ) -> list[PitchSession]:
        """List the most recent sessions for a user."""

    @abstractmethod
    async def update_session(
        self, session_id: str, **fields: Any
    ) -> Optional[PitchSession]:
        """Update arbitrary fields on a session. Returns the updated row."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all related rows. Returns True if deleted."""

    # ─── Turns ────────────────────────────────────────────────────

    @abstractmethod
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
        """Append a turn to a session's conversation log."""

    @abstractmethod
    async def list_turns(self, session_id: str) -> list[PitchTurn]:
        """Return all turns for a session in step order."""

    # ─── Verdict ──────────────────────────────────────────────────

    @abstractmethod
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
        """Upsert the verdict for a session. Each session has at most one."""

    @abstractmethod
    async def get_verdict(self, session_id: str) -> Optional[PitchVerdict]:
        """Fetch the verdict for a session, or None if not yet rendered."""

    # ─── Revisions ────────────────────────────────────────────────

    @abstractmethod
    async def save_revision(
        self,
        session_id: str,
        *,
        original_pitch: str,
        revised_pitch: str,
        improvements_addressed: list[str],
    ) -> PitchRevision:
        """Record a pitch revision (in the re-pitch loop)."""

    @abstractmethod
    async def list_revisions(self, session_id: str) -> list[PitchRevision]:
        """Return all revisions for a session in chronological order."""

    # ─── Personas (global catalog) ───────────────────────────────

    @abstractmethod
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
        """Insert or update a persona in the global catalog."""

    @abstractmethod
    async def get_persona(self, persona_id: str) -> Optional[AgentPersona]:
        """Fetch a persona by id."""

    @abstractmethod
    async def list_personas(self, enabled_only: bool = True) -> list[AgentPersona]:
        """List all personas in the catalog."""

    # ─── Users ───────────────────────────────────────────────────

    @abstractmethod
    async def upsert_user(
        self,
        *,
        email: Optional[str] = None,
        name: Optional[str] = None,
        image_url: Optional[str] = None,
        provider: str = "email",
        provider_account_id: Optional[str] = None,
    ) -> User:
        """Insert or update a user. Returns the user row."""

    @abstractmethod
    async def get_user(self, user_id: str) -> Optional[User]:
        """Fetch a user by id."""

    @abstractmethod
    async def get_user_by_provider(
        self, provider: str, provider_account_id: str
    ) -> Optional[User]:
        """Look up a user by their OAuth provider account id."""

    # ─── Events (process-local) ──────────────────────────────────

    @abstractmethod
    def get_events(self, session_id: str) -> SessionEventBus:
        """Return the asyncio event bus for a session. Created lazily."""

    # ─── API Keys (Tier-2b) ─────────────────────────────────────

    @abstractmethod
    async def create_api_key(
        self,
        *,
        name: str,
        key_hash: str,
        key_prefix: str,
        user_id: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        expires_at: Optional[Any] = None,
        rate_limit_per_minute: Optional[int] = None,
    ) -> "ApiKey":
        """Create a new API key. Returns the row."""

    @abstractmethod
    async def get_api_key_by_hash(self, key_hash: str) -> Optional["ApiKey"]:
        """Look up an API key by its hash. Returns None if not found or revoked."""

    @abstractmethod
    async def list_api_keys(self, user_id: Optional[str] = None) -> list["ApiKey"]:
        """List API keys. If user_id is set, filter to that user."""

    @abstractmethod
    async def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key. Returns True if the key was found and revoked."""

    @abstractmethod
    async def record_api_key_usage(self, key_id: str) -> None:
        """Increment usage counters for an API key."""

    # ─── Convenience ─────────────────────────────────────────────

    def is_in_memory(self) -> bool:
        """True if this is the in-memory implementation. Used for diagnostics."""
        return False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "SessionEventBus",
    "SessionRepository",
    "SessionStatus",
    "TurnRole",
    "TurnType",
    "VerdictSignal",
    "User",
    "AgentPersona",
    "PitchSession",
    "PitchTurn",
    "PitchVerdict",
    "PitchRevision",
]
