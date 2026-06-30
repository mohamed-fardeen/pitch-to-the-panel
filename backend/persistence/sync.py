"""
Bridge between the legacy synchronous `sessions: dict` and the async
SessionRepository.

Background
──────────

The legacy code in `backend/main.py` and `backend/orchestrator.py` uses a
plain dict for in-process session state:

    sessions: dict[str, dict] = {}
    session = sessions.get(session_id)        # sync read
    session["pitch_summary"] = "..."          # sync write
    session["events"]["answer_event"].set()   # asyncio.Event — process-local

A pure dict has two problems for production:
1. State vanishes on server restart.
2. It doesn't work across multiple worker processes.

The new async SessionRepository solves both — but the orchestrator code
relies on sync dict access and on storing `asyncio.Event` objects inside
the dict. asyncio.Event objects are *inherently* process-local — they
cannot be persisted to a database or shared across processes.

Strategy
────────

This module provides a `SessionPersistenceBridge` that:

- Listens for writes to the in-process session dict and *asynchronously*
  mirrors them to the durable repository.
- On session creation, writes a row to the repository (in the background).
- On session update, writes the diff to the repository (in the background).
- Does NOT persist asyncio.Event objects (those stay in-process by design).

The bridge is best-effort: if a database write fails, it logs the error
but does NOT block the request handler. The in-process cache is still
the source of truth for the current request lifecycle.

A future Sub-PR will add startup hydration: on server boot, load all
active sessions from the repository into the in-process cache so the
dict is pre-warmed. This is non-trivial because asyncio.Event objects
need to be re-created and any in-flight graph tasks need to be
re-attached. That's a Tier 1 concern.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC
from typing import Any

from .repository import SessionRepository

logger = logging.getLogger(__name__)

# Fields that are in-process only and must NEVER be persisted to the DB.
# These hold asyncio.Event objects, asyncio.Task objects, and similar
# process-local state.
NON_PERSISTED_KEYS = frozenset(
    {
        "events",            # asyncio.Event bus
        "graph_task",        # asyncio.Task running the LangGraph stream
        "sse_queue",         # asyncio.Queue for SSE events
    }
)


class SessionPersistenceBridge:
    """
    Mirrors session-dict writes to the durable SessionRepository.

    Usage in main.py:

        from backend.persistence import get_repository
        from backend.persistence.sync import SessionPersistenceBridge

        bridge = SessionPersistenceBridge(get_repository())

        # After creating a session in the dict:
        sessions[session_id] = {...}
        await bridge.session_created(session_id, payload=sessions[session_id])

        # After mutating the session dict:
        sessions[session_id]["pitch_summary"] = "new value"
        await bridge.session_updated(session_id, fields={"pitch_summary": "new value"})
    """

    def __init__(self, repo: SessionRepository) -> None:
        self._repo = repo
        # Background tasks we don't await. We hold weak references so the
        # GC can reclaim them. If they fail, the exception is swallowed.
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def session_created(
        self,
        session_id: str,
        *,
        pitch: str,
        mode: str,
        provider: str,
        aggressiveness: int = 5,
        user_id: str | None = None,
    ) -> None:
        """
        Persist a newly-created session.

        Note: this assumes the session doesn't already exist in the repo.
        If it does (e.g. after a restart), the repo will raise and we
        silently swallow the error — the in-process cache is the source
        of truth for the current request.
        """
        try:
            await self._repo.create_session(
                session_id=session_id,
                pitch=pitch,
                mode=mode,
                provider=provider,
                aggressiveness=aggressiveness,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(
                "session_created: persistence failed for %s: %s",
                session_id, e,
            )

    async def session_updated(
        self,
        session_id: str,
        fields: dict[str, Any],
    ) -> None:
        """
        Persist a partial update to a session.

        Filters out non-persisted keys (asyncio.Event etc.).
        """
        clean_fields = {
            k: v for k, v in fields.items() if k not in NON_PERSISTED_KEYS
        }
        if not clean_fields:
            return
        try:
            await self._repo.update_session(session_id, **clean_fields)
        except Exception as e:
            logger.warning(
                "session_updated: persistence failed for %s: %s",
                session_id, e,
            )

    async def session_ended(self, session_id: str, *, cancelled: bool) -> None:
        """Mark a session as completed (or aborted)."""
        from .models import SessionStatus

        status = (
            SessionStatus.ABORTED.value if cancelled else SessionStatus.COMPLETED.value
        )
        try:
            await self._repo.update_session(
                session_id,
                status=status,
                completed_at=_utcnow(),
                is_cancelled=cancelled,
            )
        except Exception as e:
            logger.warning(
                "session_ended: persistence failed for %s: %s",
                session_id, e,
            )

    async def turn_recorded(
        self,
        session_id: str,
        *,
        step_index: int,
        role: str,
        turn_type: str,
        content: str,
        agent_id: str | None = None,
        agent_name: str | None = None,
    ) -> None:
        """Append a turn to the durable conversation log."""
        try:
            await self._repo.append_turn(
                session_id,
                step_index=step_index,
                role=role,
                turn_type=turn_type,
                content=content,
                agent_id=agent_id,
                agent_name=agent_name,
            )
        except Exception as e:
            logger.warning(
                "turn_recorded: persistence failed for %s: %s",
                session_id, e,
            )

    async def verdict_recorded(
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
        signal: str = "MEDIUM",
        charts: dict[str, Any] | None = None,
    ) -> None:
        """Persist the final verdict."""
        try:
            await self._repo.save_verdict(
                session_id,
                verdict_text=verdict_text,
                strongest=strongest,
                weakness=weakness,
                fix=fix,
                investment_score=investment_score,
                recommendation=recommendation,
                confidence_score=confidence_score,
                signal=signal,
                charts=charts,
            )
        except Exception as e:
            logger.warning(
                "verdict_recorded: persistence failed for %s: %s",
                session_id, e,
            )

    async def revision_recorded(
        self,
        session_id: str,
        *,
        original_pitch: str,
        revised_pitch: str,
        improvements_addressed: list[str],
    ) -> None:
        """Persist a pitch revision."""
        try:
            await self._repo.save_revision(
                session_id,
                original_pitch=original_pitch,
                revised_pitch=revised_pitch,
                improvements_addressed=improvements_addressed,
            )
        except Exception as e:
            logger.warning(
                "revision_recorded: persistence failed for %s: %s",
                session_id, e,
            )


def _utcnow():
    from datetime import datetime
    return datetime.now(UTC)


__all__ = ["SessionPersistenceBridge", "NON_PERSISTED_KEYS"]
