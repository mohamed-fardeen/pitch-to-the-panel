"""
backend.persistence
===================

Session persistence for PanelMind (Tier 0b/0c).

This package provides:
- SQLAlchemy 2.0 async models (User, PitchSession, PitchTurn, PitchVerdict,
  PitchRevision, AgentPersona)
- A `SessionRepository` abstract interface — the contract the orchestrator
  depends on
- Two implementations:
  - `InMemorySessionRepository` — default, used in dev and tests
  - `SqlAlchemySessionRepository` — production
- A factory `get_repository()` that picks the right one based on settings

The orchestrator (`backend/orchestrator.py`) still uses the legacy
`sessions: dict` directly, but each mutation is mirrored to the
repository via `SessionPersistenceBridge`. Switching to SQLite/Postgres
is a single env-var change (PANELMIND_REPOSITORY=sqlalchemy +
DATABASE_URL=...).
"""

from .factory import (
    get_repository,
    init_repository_schema,
    reset_repository,
    set_repository,
)
from .in_memory import InMemorySessionRepository
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
from .sqlalchemy_repository import SqlAlchemySessionRepository
from .sync import NON_PERSISTED_KEYS, SessionPersistenceBridge

__all__ = [
    # Factory
    "get_repository",
    "init_repository_schema",
    "reset_repository",
    "set_repository",
    # Repository implementations
    "InMemorySessionRepository",
    "SqlAlchemySessionRepository",
    "SessionRepository",
    "SessionEventBus",
    # Sync bridge
    "SessionPersistenceBridge",
    "NON_PERSISTED_KEYS",
    # Models
    "User",
    "AgentPersona",
    "PitchSession",
    "PitchTurn",
    "PitchVerdict",
    "PitchRevision",
    # Enums
    "SessionStatus",
    "TurnRole",
    "TurnType",
    "VerdictSignal",
]