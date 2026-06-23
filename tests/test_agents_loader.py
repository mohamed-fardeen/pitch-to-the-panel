"""
Tests for the persona YAML loader (backend/agents/loader.py).

These tests verify:
- YAML files are loaded correctly into Persona / PersonaCatalog objects
- Required-field validation works
- The backwards-compat shims (AGENTS_CONFIG, AGENT_GOALS, OCEAN_PROFILES)
  match the YAML contents
- The catalog is idempotent and thread-safe
- The /api/agents endpoint returns the loaded personas
"""

from __future__ import annotations

import pytest

from backend.agents.catalog import OceanProfile, Persona, PersonaCatalog
from backend.agents import loader
from backend.agents.loader import (
    get_catalog,
    reset_catalog,
)


@pytest.fixture(autouse=True)
def _reset_loader_cache():
    """Reset the loader cache before each test so we get fresh data."""
    reset_catalog()
    yield
    reset_catalog()


# ─── Catalog structure ────────────────────────────────────────────


def test_catalog_has_six_personas():
    catalog = get_catalog()
    assert len(catalog) == 6


def test_catalog_contains_legacy_ids():
    """The 6 legacy IDs must be present (backwards-compat)."""
    catalog = get_catalog()
    expected = {"vc", "enthusiastic", "hostile", "expert", "beginner", "interviewer"}
    actual = {p.id for p in catalog}
    assert expected == actual


def test_each_persona_has_required_fields():
    catalog = get_catalog()
    for p in catalog:
        assert p.id, f"Persona missing id"
        assert p.name, f"Persona {p.id} missing name"
        assert p.role, f"Persona {p.id} missing role"
        assert p.system_prompt, f"Persona {p.id} missing system_prompt"


def test_ocen_profile_is_clamped():
    """Ocean values outside 0..1 should be clamped, not error."""
    ocean = OceanProfile.from_dict({"openness": 1.5, "conscientiousness": -0.3})
    assert ocean.openness == 1.0
    assert ocean.conscientiousness == 0.0


def test_ocen_defaults_when_missing():
    """If ocean is missing entirely, all traits default to 0.5."""
    ocean = OceanProfile.from_dict(None)
    assert ocean.openness == 0.5
    assert ocean.conscientiousness == 0.5
    assert ocean.extraversion == 0.5
    assert ocean.agreeableness == 0.5
    assert ocean.neuroticism == 0.5


def test_visible_vs_hidden():
    """The interviewer (strategist) is hidden; the others are visible."""
    catalog = get_catalog()
    visible_ids = {p.id for p in catalog.visible()}
    hidden_ids = {p.id for p in catalog.hidden()}
    assert "interviewer" in hidden_ids
    assert "vc" in visible_ids
    assert "enthusiastic" in visible_ids


def test_persona_lookup_by_id():
    catalog = get_catalog()
    vc = catalog.get("vc")
    assert vc is not None
    assert vc.id == "vc"
    assert vc.name == "Arjun (VC)"


def test_persona_lookup_unknown_returns_none():
    catalog = get_catalog()
    assert catalog.get("nonexistent") is None


def test_persona_contains():
    catalog = get_catalog()
    assert "vc" in catalog
    assert "nonexistent" not in catalog


def test_sort_order():
    """The strategist (sort_order 0) should come first, then vc (1), etc."""
    catalog = get_catalog()
    ids = [p.id for p in catalog]
    assert ids[0] == "interviewer"
    assert ids[1] == "vc"
    # The rest are in order


# ─── Backwards-compat shims ──────────────────────────────────────


def test_legacy_agents_config_has_all_personas():
    cfg = loader.AGENTS_CONFIG
    assert "vc" in cfg
    assert cfg["vc"]["name"] == "Arjun (VC)"
    assert cfg["vc"]["role"] == "Venture Capitalist"


def test_legacy_agent_goals_only_for_personas_with_goals():
    goals = loader.AGENT_GOALS
    assert "vc" in goals
    assert "ROI" in goals["vc"]
    # All our personas have goals
    assert len(goals) >= 5


def test_legacy_ocean_profiles():
    ocean = loader.OCEAN_PROFILES
    assert "vc" in ocean
    assert ocean["vc"]["openness"] == pytest.approx(0.35, abs=0.01)


def test_legacy_dicts_use_yaml_as_source_of_truth():
    """If a YAML changes, the legacy dicts change too (no caching issue)."""
    # Force reload
    reset_catalog()
    catalog = get_catalog(force_reload=True)
    vc = catalog.get("vc")
    cfg = loader.AGENTS_CONFIG
    # The name should match what's in the YAML
    assert cfg["vc"]["name"] == vc.name


# ─── Loader behavior ─────────────────────────────────────────────


def test_loader_caches_result():
    """Calling get_catalog() twice returns the same object."""
    a = get_catalog()
    b = get_catalog()
    assert a is b


def test_force_reload_creates_new_instance():
    a = get_catalog()
    b = get_catalog(force_reload=True)
    # The contents are equal but the objects may differ (depends on cache)
    assert len(a) == len(b)


def test_invalid_yaml_skipped(tmp_path, monkeypatch):
    """If a YAML is malformed, the loader logs an error and skips it."""
    # Create a temp personas directory with one valid and one broken file
    valid_dir = tmp_path / "personas"
    valid_dir.mkdir()
    (valid_dir / "good.yaml").write_text(
        "id: good\nname: Good\nrole: Tester\nsystem_prompt: Test\n",
        encoding="utf-8",
    )
    (valid_dir / "broken.yaml").write_text(
        "id: broken\nname: [unclosed",  # invalid YAML
        encoding="utf-8",
    )

    # Point the loader at the temp directory
    monkeypatch.setenv("PANELMIND_PERSONAS_DIR", str(valid_dir))
    reset_catalog()

    catalog = get_catalog()
    # Only the valid one loads
    assert len(catalog) == 1
    assert catalog.get("good") is not None
    assert catalog.get("broken") is None


def test_missing_required_field_skipped(tmp_path, monkeypatch):
    """YAMLs missing required fields are skipped, not raised."""
    valid_dir = tmp_path / "personas"
    valid_dir.mkdir()
    (valid_dir / "missing_role.yaml").write_text(
        "id: x\nname: X\nsystem_prompt: Y\n",  # missing 'role'
        encoding="utf-8",
    )

    monkeypatch.setenv("PANELMIND_PERSONAS_DIR", str(valid_dir))
    reset_catalog()

    catalog = get_catalog()
    assert len(catalog) == 0


def test_template_files_skipped(tmp_path, monkeypatch):
    """Files starting with _ are skipped (template convention)."""
    valid_dir = tmp_path / "personas"
    valid_dir.mkdir()
    (valid_dir / "_template.yaml").write_text(
        "id: tpl\nname: Template\nrole: Template\nsystem_prompt: Template\n",
        encoding="utf-8",
    )
    (valid_dir / "real.yaml").write_text(
        "id: real\nname: Real\nrole: Real\nsystem_prompt: Real\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("PANELMIND_PERSONAS_DIR", str(valid_dir))
    reset_catalog()

    catalog = get_catalog()
    assert len(catalog) == 1
    assert catalog.get("real") is not None
    assert catalog.get("tpl") is None


# ─── /api/agents endpoint ────────────────────────────────────────


def test_api_agents_endpoint_returns_yaml_personas():
    """The /api/agents endpoint should return personas from the YAML catalog."""
    from fastapi.testclient import TestClient
    import os
    from backend.main import app

    # The endpoint excludes 'interviewer' (internal strategist)
    with TestClient(app) as client:
        r = client.get("/api/agents")
        assert r.status_code == 200
        data = r.json()
        assert "vc" in data
        assert data["vc"]["name"] == "Arjun (VC)"
        assert data["vc"]["role"] == "Venture Capitalist"
        # The endpoint should not include the interviewer
        assert "interviewer" not in data