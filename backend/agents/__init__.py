"""
backend.agents — Shim for the agent catalog.

The canonical persona YAMLs live at ``apps/api/agents/personas/*.yaml``
(new monorepo home). This package re-exports the loader and catalog
so the legacy ``backend/orchestrator.py`` can import them as
``from agents import AGENTS_CONFIG, AGENT_GOALS, OCEAN_PROFILES, ...``.

In Tier 0d (the directory move) this shim goes away; orchestrator.py
moves to ``apps/api/agents/`` and imports from a sibling module.
"""
