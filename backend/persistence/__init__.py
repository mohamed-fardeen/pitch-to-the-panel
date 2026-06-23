"""
backend/persistence
===================

Session persistence for PanelMind (Tier 0b).

This package provides:
- SQLAlchemy 2.0 async models for User, PitchSession, PitchTurn, PitchVerdict,
  AgentPersona, AgentMemoryEntry, PitchRevision
- A `SessionRepository` abstract interface (the contract the orchestrator
  depends on)
- Two implementations: `InMemorySessionRepository` (default, used in dev) and
  `SqlAlchemySessionRepository` (production)
- A factory `get_repository()` that picks the right one based on settings

The orchestrator (`backend/orchestrator.py`) was refactored in Sub-PR 2a to
accept a `SessionRepository` instead of using the global `sessions: dict`
directly. The default is still in-memory; switching to SQLite/Postgres is a
single env-var change.

The actual database file (when using SQLite) is at:
    apps/api/data/panelmind.db
"""
