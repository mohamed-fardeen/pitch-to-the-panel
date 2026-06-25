"""
Tests for the prompt versioning + A/B framework (Tier-2c).

Verifies:
- Variant picking is deterministic by session_id
- A 100/0 weight split always picks "control"
- A 0/100 weight split always picks "v2"
- A 50/50 weight split is balanced
- The router persists and reads back experiments
- compare_variants() returns per-variant stats
- A "winner" is picked when there's a meaningful difference
- A non-existent experiment returns "control" (safe default)
"""

from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from backend.prompts_versions.router import (
    _Router,
    compare_variants,
    mean,
    pick_variant,
    router,
    stddev,
)


# ─── pick_variant ────────────────────────────────────────────────


def test_pick_variant_is_deterministic():
    """Same session_id always gets the same variant."""
    a = pick_variant("test", "session-1", {"control": 50, "v2": 50})
    b = pick_variant("test", "session-1", {"control": 50, "v2": 50})
    assert a == b


def test_pick_variant_distributes_load():
    """A 50/50 split should be roughly balanced across many sessions."""
    counts: Counter = Counter()
    for i in range(1000):
        v = pick_variant("test-dist", f"session-{i}", {"control": 50, "v2": 50})
        counts[v] += 1
    # Each variant should be in the 40-60% range (loose tolerance)
    for variant, count in counts.items():
        assert 400 <= count <= 600, f"{variant} got {count} (expected ~500)"


def test_pick_variant_zero_weight_for_one():
    """If one variant has weight 0, it's never picked."""
    for i in range(100):
        v = pick_variant("test-zero", f"session-{i}", {"a": 100, "b": 0})
        assert v == "a"


def test_pick_variant_full_weight_to_one():
    """If one variant has 100% weight, it's always picked."""
    for i in range(50):
        v = pick_variant("test-full", f"session-{i}", {"winner": 100, "loser": 0})
        assert v == "winner"


def test_pick_variant_different_experiments_independent():
    """Two experiments with the same session_id can pick different variants."""
    session = "shared-session"
    # Use 100/0 in one, 0/100 in the other
    a = pick_variant("exp-a", session, {"control": 100, "v2": 0})
    b = pick_variant("exp-b", session, {"control": 0, "v2": 100})
    assert a == "control"
    assert b == "v2"


def test_pick_variant_raises_on_empty():
    with pytest.raises(ValueError, match="variants must be non-empty"):
        pick_variant("test", "session", {})


def test_pick_variant_raises_on_zero_total():
    with pytest.raises(ValueError, match="must be positive"):
        pick_variant("test", "session", {"a": 0, "b": 0})


# ─── compare_variants ────────────────────────────────────────────


def test_compare_variants_orders_by_mean():
    """The variant with the highest mean is first."""
    assignments = [
        ("control", "aid-1", 3.0),
        ("control", "aid-2", 4.0),
        ("v2", "aid-3", 5.0),
        ("v2", "aid-4", 6.0),
    ]
    result = compare_variants("test", "user_rating", assignments)
    assert result.variants[0].variant == "v2"  # higher mean
    assert result.variants[0].mean == 5.5
    assert result.variants[1].mean == 3.5


def test_compare_variants_picks_winner_on_meaningful_diff():
    """A winner is picked when the mean diff is at least 5% of the range."""
    # control avg 4.0, v2 avg 5.0 -> 25% diff, winner = v2
    assignments = [
        ("control", "aid-1", 4.0),
        ("control", "aid-2", 4.0),
        ("control", "aid-3", 4.0),
        ("v2", "aid-4", 5.0),
        ("v2", "aid-5", 5.0),
        ("v2", "aid-6", 5.0),
    ]
    result = compare_variants("test", "user_rating", assignments)
    assert result.winner == "v2"


def test_compare_variants_no_winner_when_too_close():
    """Tiny differences don't pick a winner."""
    assignments = [
        ("control", "aid-1", 4.0),
        ("control", "aid-2", 4.0),
        ("control", "aid-3", 4.0),
        ("v2", "aid-4", 4.1),
        ("v2", "aid-5", 4.1),
        ("v2", "aid-6", 4.1),
    ]
    result = compare_variants("test", "user_rating", assignments)
    # 0.1/4 = 2.5% diff, below 5% threshold
    assert result.winner is None


def test_compare_variants_no_winner_with_too_few_samples():
    """With < 3 samples per variant, no winner is picked (need statistical power)."""
    assignments = [
        ("control", "aid-1", 4.0),
        ("v2", "aid-2", 5.0),
    ]
    result = compare_variants("test", "user_rating", assignments)
    assert result.winner is None


def test_compare_variants_empty_data():
    """No assignments → no comparison."""
    result = compare_variants("test", "user_rating", [])
    assert result.variants == []


# ─── Math helpers ───────────────────────────────────────────────


def test_mean_empty():
    assert mean([]) == 0.0


def test_mean_simple():
    assert mean([1.0, 2.0, 3.0]) == 2.0


def test_stddev_single_value():
    assert stddev([5.0]) == 0.0


def test_stddev_known():
    """Our stddev uses sample variance (divides by N-1), so for [2,4,4,4,5,5,7,9]
    we expect sqrt(((2-5)^2 + (4-5)^2*3 + (5-5)^2*2 + (7-5)^2 + (9-5)^2) / 7)
    = sqrt((9 + 3 + 0 + 4 + 16) / 7) = sqrt(32/7) ≈ 2.138.
    """
    assert stddev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.138, abs=0.001)


# ─── _Router (with persistence) ──────────────────────────────────


@pytest.fixture
def fresh_repo():
    """Set up a fresh in-memory repo for router tests."""
    from backend.persistence import set_repository
    from backend.persistence.in_memory import InMemorySessionRepository

    repo = InMemorySessionRepository()
    set_repository(repo)
    return repo


@pytest.mark.asyncio
async def test_router_pick_returns_control_for_unknown_experiment(fresh_repo):
    """When no experiment is registered, the router returns 'control' safely."""
    r = _Router()
    v = await r.pick_variant("nonexistent", "any-session")
    assert v == "control"


@pytest.mark.asyncio
async def test_router_register_and_pick(fresh_repo):
    r = _Router()
    await r.register(
        name="ctrl-v2",
        description="controller prompt v2",
        variants={"control": 50, "v2": 50},
    )
    # Same session, same variant
    v1 = await r.pick_variant("ctrl-v2", "session-x")
    v2 = await r.pick_variant("ctrl-v2", "session-x")
    assert v1 == v2
    # Different sessions, may or may not differ
    v3 = await r.pick_variant("ctrl-v2", "session-y")
    # No assertion needed, just that no error


@pytest.mark.asyncio
async def test_router_inactive_experiment_returns_control(fresh_repo):
    r = _Router()
    await r.register(
        name="off-exp",
        description="off",
        variants={"control": 0, "v2": 100},
        is_active=False,
    )
    # Inactive -> always control
    for sid in ["a", "b", "c"]:
        v = await r.pick_variant("off-exp", sid)
        assert v == "control"


@pytest.mark.asyncio
async def test_router_record_outcome_and_compare(fresh_repo):
    r = _Router()
    await r.register(
        name="rating-exp",
        description="test",
        variants={"control": 50, "v2": 50},
    )
    # Record some outcomes (will be assigned to variants deterministically)
    for i in range(20):
        v = await r.pick_variant("rating-exp", f"session-{i}")
        await r.record_outcome(
            experiment_name="rating-exp",
            session_id=f"session-{i}",
            metric_name="user_rating",
            metric_value=4.0 if v == "control" else 5.0,
        )

    comparison = await r.compare("rating-exp", "user_rating")
    assert comparison is not None
    assert len(comparison.variants) == 2


@pytest.mark.asyncio
async def test_router_compare_returns_none_for_no_data(fresh_repo):
    r = _Router()
    await r.register(
        name="empty-exp",
        description="test",
        variants={"control": 50, "v2": 50},
    )
    result = await r.compare("empty-exp", "no-metric")
    assert result is None