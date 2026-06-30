"""
Persona catalog loader.

Reads YAML files from ``apps/api/agents/personas/*.yaml`` and returns
a :class:`PersonaCatalog`. The loader is:

- Idempotent: calling it twice returns the same catalog (cached).
- Resilient: malformed YAMLs are logged and skipped, not raised.
- Fronted by :func:`get_catalog` which is the public entry point.

We support two lookup strategies:

1. From the project root — default. The path is
   ``<repo>/apps/api/agents/personas/``.
2. From a custom directory — for tests and self-hosted deployments
   that want to override the persona set without modifying the repo.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import yaml

from .catalog import OceanProfile, Persona, PersonaCatalog

logger = logging.getLogger(__name__)

# Path resolution: <repo>/apps/api/agents/personas/
# We compute this from the loader's location, not cwd, so the loader
# works regardless of where the process is started from.
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent  # backend/agents/loader.py -> repo root
DEFAULT_PERSONAS_DIR = _REPO_ROOT / "apps" / "api" / "agents" / "personas"

# Allow override via env var (used in tests and self-hosted deployments).
_PERSONAS_DIR_ENV = "PANELMIND_PERSONAS_DIR"

# Sentinel for "not yet loaded"
_UNLOADED: object = object()

_lock = threading.Lock()
_cached_catalog: PersonaCatalog | object = _UNLOADED


def get_catalog(*, force_reload: bool = False) -> PersonaCatalog:
    """
    Return the process-wide persona catalog, loading it lazily.

    The catalog is loaded once and cached. Pass ``force_reload=True`` to
    bypass the cache (used by tests that modify YAML files between calls).
    """
    global _cached_catalog
    with _lock:
        if force_reload or _cached_catalog is _UNLOADED:
            _cached_catalog = _load_catalog(_resolve_personas_dir())
        # The cast is safe because we just set it
        assert isinstance(_cached_catalog, PersonaCatalog)
        return _cached_catalog


def reset_catalog() -> None:
    """Reset the catalog cache. Used by tests."""
    global _cached_catalog
    with _lock:
        _cached_catalog = _UNLOADED


def _resolve_personas_dir() -> Path:
    """Resolve the personas directory, allowing env-var override."""
    override = os.getenv(_PERSONAS_DIR_ENV)
    if override:
        return Path(override)
    return DEFAULT_PERSONAS_DIR


def _load_catalog(personas_dir: Path) -> PersonaCatalog:
    """Load all YAMLs from a directory into a PersonaCatalog."""
    if not personas_dir.exists():
        logger.warning("Personas directory not found: %s", personas_dir)
        return PersonaCatalog(personas=[])

    personas: list[Persona] = []
    # Sort for deterministic ordering
    yaml_files = sorted(personas_dir.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No persona YAMLs found in %s", personas_dir)
        return PersonaCatalog(personas=[])

    for yaml_path in yaml_files:
        if yaml_path.name.startswith("_"):
            # Skip template files
            continue
        try:
            persona = _load_one_persona(yaml_path)
        except Exception as e:
            logger.error("Failed to load persona from %s: %s", yaml_path.name, e)
            continue
        personas.append(persona)
        logger.debug("Loaded persona %s from %s", persona.id, yaml_path.name)

    # Sort by sort_order from config, then by id for stability
    personas.sort(key=lambda p: (p.sort_order, p.id))
    logger.info("Loaded %d personas from %s", len(personas), personas_dir)
    return PersonaCatalog(personas=personas)


def _load_one_persona(yaml_path: Path) -> Persona:
    """Load and validate a single persona YAML file."""
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Top-level YAML must be a mapping, got {type(data).__name__}")

    # Required fields
    for field_name in ("id", "name", "role", "system_prompt"):
        if field_name not in data:
            raise ValueError(f"Missing required field: {field_name!r}")
        if not isinstance(data[field_name], str):
            raise ValueError(
                f"Field {field_name!r} must be a string, got {type(data[field_name]).__name__}"
            )
        if not data[field_name].strip():
            raise ValueError(f"Field {field_name!r} must not be empty")

    return Persona(
        id=data["id"].strip(),
        name=data["name"].strip(),
        role=data["role"].strip(),
        system_prompt=data["system_prompt"].strip(),
        goal=str(data.get("goal", "")).strip(),
        ocean=OceanProfile.from_dict(data.get("ocean")),
        enabled=bool(data.get("enabled", True)),
        config=dict(data.get("config", {}) or {}),
    )


# ─── Backwards-compat shims for the legacy orchestrator ──────────
#
# The legacy orchestrator.py imports three dicts from this module:
#   AGENTS_CONFIG   — { persona_id: {name, role, system_prompt} }
#   AGENT_GOALS     — { persona_id: "goal text" }
#   OCEAN_PROFILES  — { persona_id: {openness, conscientiousness, ...} }
#
# We expose them so orchestrator.py can keep working without changes.
# When the orchestrator is refactored to use PersonaCatalog directly,
# these shims will be deleted.


def _legacy_dicts() -> tuple[dict, dict, dict]:
    """Build the three legacy dicts from the current catalog."""
    catalog = get_catalog()
    agents_config: dict = {}
    agent_goals: dict = {}
    ocean_profiles: dict = {}
    for p in catalog:
        agents_config[p.id] = {
            "name": p.name,
            "role": p.role,
            "system_prompt": p.system_prompt,
        }
        if p.goal:
            agent_goals[p.id] = p.goal
        ocean_profiles[p.id] = p.ocean.to_dict()
    return agents_config, agent_goals, ocean_profiles


# Module-level lazy properties. We compute them on first access so
# tests that swap the catalog see the new values.
def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name in ("AGENTS_CONFIG", "AGENT_GOALS", "OCEAN_PROFILES"):
        a, g, o = _legacy_dicts()
        if name == "AGENTS_CONFIG":
            return a
        if name == "AGENT_GOALS":
            return g
        if name == "OCEAN_PROFILES":
            return o
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DEFAULT_PERSONAS_DIR",
    "get_catalog",
    "reset_catalog",
]
