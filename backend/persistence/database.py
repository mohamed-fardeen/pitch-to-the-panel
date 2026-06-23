"""
Async SQLAlchemy engine + session factory.

Usage
─────

    from backend.persistence.database import get_engine, get_sessionmaker

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = get_sessionmaker()
    async with SessionLocal() as session:
        # ... your queries
        await session.commit()

The engine is created once and reused (per process). The sessionmaker is
also process-wide.

Supported drivers
─────────────────
- SQLite:   `sqlite+aiosqlite:///./panelmind.db`    (default in dev)
- Postgres: `postgresql+asyncpg://user:pass@host/db`  (production)

The DATABASE_URL env var selects between them. Empty / missing falls back
to in-memory repository (no DB at all).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .base import Base

logger = logging.getLogger(__name__)

_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _resolve_database_url() -> str:
    """Pull DATABASE_URL from the env, with a sensible default."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    # Default: SQLite in the apps/api/data/ directory
    default_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "apps",
        "api",
        "data",
        "panelmind.db",
    )
    os.makedirs(os.path.dirname(default_path), exist_ok=True)
    return f"sqlite+aiosqlite:///{default_path}"


def get_engine(url: Optional[str] = None) -> AsyncEngine:
    """Return the process-wide async engine, creating it lazily."""
    global _engine
    if _engine is None:
        db_url = url or _resolve_database_url()
        logger.info("Creating async SQLAlchemy engine for %s", _redact_url(db_url))

        # SQLite needs a special connect_args to allow cross-thread access
        # (FastAPI's threadpool). Postgres doesn't.
        connect_args: dict = {}
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_async_engine(
            db_url,
            connect_args=connect_args,
            echo=False,
            pool_pre_ping=True,  # helps detect stale connections
        )
    return _engine


def get_sessionmaker(url: Optional[str] = None) -> async_sessionmaker[AsyncSession]:
    """Return the process-wide sessionmaker."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(url),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def create_all_tables() -> None:
    """Create all tables (dev convenience; use Alembic in production)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Created all tables (or they already existed).")


async def drop_all_tables() -> None:
    """Drop all tables. Destructive — for tests only."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def dispose_engine() -> None:
    """Close the engine and free its connection pool. Call on shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None


def _redact_url(url: str) -> str:
    """Hide the password in a database URL for logging."""
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        creds = f"{user}:***"
    return f"{scheme}://{creds}@{host}"
