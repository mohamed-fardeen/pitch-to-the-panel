"""
Factory that returns the right SessionRepository based on environment.

Selection rules (highest priority first):
1. `PANELMIND_REPOSITORY=memory`  -> InMemorySessionRepository
2. `PANELMIND_REPOSITORY=sqlalchemy` (default) -> SqlAlchemySessionRepository
3. Empty/missing -> SqlAlchemySessionRepository (auto-creates SQLite)

This module also exposes a `set_repository()` hook so tests and CLI tools
can inject a custom repository.
"""

from __future__ import annotations

import logging
import os
import threading

from .in_memory import InMemorySessionRepository
from .repository import SessionRepository
from .sqlalchemy_repository import SqlAlchemySessionRepository

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_default_repo: SessionRepository | None = None


def get_repository() -> SessionRepository:
    """
    Return the process-wide repository, creating it lazily.

    Side effect: on first call, ensures the SQL schema exists
    (when using the SQLAlchemy repo). This is a no-op for the
    in-memory repository.
    """
    global _default_repo
    with _lock:
        if _default_repo is None:
            _default_repo = _build_repository()
        return _default_repo


def set_repository(repo: SessionRepository) -> None:
    """Inject a custom repository. Used by tests."""
    global _default_repo
    with _lock:
        _default_repo = repo


def reset_repository() -> None:
    """Reset to None; the next get_repository() call will rebuild."""
    global _default_repo
    with _lock:
        _default_repo = None


def _build_repository() -> SessionRepository:
    choice = os.getenv("PANELMIND_REPOSITORY", "sqlalchemy").lower().strip()
    if choice == "memory":
        logger.info("Using InMemorySessionRepository (PANELMIND_REPOSITORY=memory)")
        return InMemorySessionRepository()

    # Default: SQLAlchemy
    logger.info("Using SqlAlchemySessionRepository (DATABASE_URL=%s)", _redact(os.getenv("DATABASE_URL", "")))
    return SqlAlchemySessionRepository()

    # Run schema creation in a background-friendly way. The async function
    # is awaited by the FastAPI lifespan handler (not here) — we just import
    # it lazily to avoid spinning up a loop on module load.


async def init_repository_schema() -> None:
    """Create tables. Call from FastAPI lifespan on startup."""
    repo = get_repository()
    if isinstance(repo, SqlAlchemySessionRepository):
        from .database import create_all_tables
        await create_all_tables()
        logger.info("SQL schema ready")


def _redact(url: str) -> str:
    if "@" not in url:
        return url or "(default)"
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        creds = f"{user}:***"
    return f"{scheme}://{creds}@{host}"


__all__ = ["get_repository", "set_repository", "reset_repository", "init_repository_schema"]
