"""
Prompt experiment router (Tier-2c).

Lightweight A/B testing for prompts. Stores experiments in the
repository. Picks variants deterministically by session_id (so the
same session always gets the same variant). Records outcomes for
later comparison.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class VariantComparison:
    """Aggregated stats for a single variant of an experiment."""

    variant: str
    n: int
    mean: float
    stddev: float
    min: float
    max: float


@dataclass
class ExperimentComparison:
    """Per-variant comparison for one metric of an experiment."""

    experiment: str
    metric: str
    variants: list[VariantComparison]
    winner: Optional[str] = None
    """If one variant's mean is significantly different, this is its name."""


def _hash_to_int(s: str) -> int:
    """Stable hash of a string to an integer in [0, 2^32)."""
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def pick_variant(
    experiment_name: str,
    session_id: str,
    variants: dict[str, int],
) -> str:
    """Pick a variant for the given session deterministically.

    `variants` is a map of variant_name -> weight. The total weight
    is normalized, and a stable hash of (experiment_name, session_id)
    picks a value in [0, total).
    """
    if not variants:
        raise ValueError("variants must be non-empty")
    total = sum(variants.values())
    if total <= 0:
        raise ValueError("variant weights must be positive")
    h = _hash_to_int(f"{experiment_name}:{session_id}") % total
    cumulative = 0
    for name, weight in variants.items():
        cumulative += weight
        if h < cumulative:
            return name
    return list(variants.keys())[-1]  # fallback for floating-point


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def compare_variants(
    experiment_name: str,
    metric_name: str,
    assignments: list[tuple[str, str, float]],
) -> ExperimentComparison:
    """Compare variants of an experiment on a single metric.

    `assignments` is a list of (variant, assignment_id, metric_value).
    Returns per-variant stats and a winner (variant with the highest
    mean, if there's a meaningful difference).
    """
    by_variant: dict[str, list[float]] = {}
    for variant, _aid, value in assignments:
        by_variant.setdefault(variant, []).append(value)

    variants = []
    for variant, values in by_variant.items():
        variants.append(
            VariantComparison(
                variant=variant,
                n=len(values),
                mean=mean(values),
                stddev=stddev(values),
                min=min(values) if values else 0.0,
                max=max(values) if values else 0.0,
            )
        )
    # Sort by mean descending
    variants.sort(key=lambda v: v.mean, reverse=True)

    # Pick a "winner" — variant with the highest mean, only if
    # the difference is at least 5% of the metric range.
    winner = None
    if len(variants) >= 2:
        top, second = variants[0], variants[1]
        if top.n >= 3 and second.n >= 3:
            spread = top.mean - second.mean
            metric_range = max(top.mean, second.mean, 1.0) - min(top.mean, second.mean, 0.0)
            if abs(spread) >= 0.05 * max(metric_range, 1.0):
                winner = top.variant

    return ExperimentComparison(
        experiment=experiment_name,
        metric=metric_name,
        variants=variants,
        winner=winner,
    )


# ─── Repository-integrated router ─────────────────────────────────
# Singleton that wraps the stateless functions above with the
# SessionRepository for persistence. Use this in production code.


class _Router:
    """A/B router with persistence.

    Registers experiments (in-memory + DB), assigns variants to
    sessions (with deterministic hashing), and records outcomes for
    later comparison.
    """

    def __init__(self) -> None:
        # Cached experiments: name -> {variants, is_active, ...}
        self._cache: dict[str, dict[str, Any]] = {}

    async def register(
        self,
        *,
        name: str,
        description: str,
        variants: dict[str, int],
        is_active: bool = True,
    ) -> None:
        """Register an experiment. Persists to the repository.

        If an experiment with this name already exists, it's updated.
        """
        from persistence import get_repository
        repo = get_repository()
        # Try to find an existing experiment by name
        existing = None
        if hasattr(repo, "get_prompt_experiment_by_name"):
            existing = await repo.get_prompt_experiment_by_name(name)

        if existing is None:
            from persistence.models import PromptExperiment
            exp = PromptExperiment(
                name=name,
                description=description,
                is_active=is_active,
                variant_weights=dict(variants),
            )
            if hasattr(repo, "create_prompt_experiment"):
                await repo.create_prompt_experiment(exp)
        else:
            existing.description = description
            existing.is_active = is_active
            existing.variant_weights = dict(variants)
            if hasattr(repo, "update_prompt_experiment"):
                await repo.update_prompt_experiment(existing)
        # Update cache
        self._cache[name] = {
            "variants": dict(variants),
            "is_active": is_active,
            "description": description,
        }

    async def pick_variant(
        self, experiment_name: str, session_id: str
    ) -> str:
        """Pick a variant for a session. Returns the "control" variant
        if the experiment doesn't exist or is inactive.
        """
        # Get the experiment (cache + DB)
        if experiment_name not in self._cache:
            from persistence import get_repository
            repo = get_repository()
            if hasattr(repo, "get_prompt_experiment_by_name"):
                exp = await repo.get_prompt_experiment_by_name(experiment_name)
                if exp is not None:
                    self._cache[experiment_name] = {
                        "variants": dict(exp.variant_weights),
                        "is_active": exp.is_active,
                        "description": exp.description,
                    }
        cached = self._cache.get(experiment_name)
        if cached is None or not cached.get("is_active"):
            # No experiment or inactive — return the first variant
            # (which we treat as "control"). This is a safe default
            # that means the prompt experiment code is non-blocking
            # when no experiment is configured.
            return "control"
        return pick_variant(
            experiment_name, session_id, cached["variants"]
        )

    async def record_outcome(
        self,
        *,
        experiment_name: str,
        session_id: str,
        metric_name: str,
        metric_value: float,
    ) -> None:
        """Record an outcome for the session's assignment.

        Idempotent: re-recording the same (experiment, session, metric)
        updates the value (last write wins).
        """
        from persistence import get_repository
        repo = get_repository()
        if hasattr(repo, "record_prompt_outcome"):
            await repo.record_prompt_outcome(
                experiment_name=experiment_name,
                session_id=session_id,
                metric_name=metric_name,
                metric_value=metric_value,
            )

    async def compare(
        self, experiment_name: str, metric_name: str
    ) -> Optional[ExperimentComparison]:
        """Compare variants on a given metric. Returns None if no data."""
        from persistence import get_repository
        repo = get_repository()
        if not hasattr(repo, "list_prompt_outcomes"):
            return None
        assignments = await repo.list_prompt_outcomes(
            experiment_name, metric_name
        )
        if not assignments:
            return None
        return compare_variants(experiment_name, metric_name, assignments)


router = _Router()


__all__ = [
    "ExperimentComparison",
    "VariantComparison",
    "compare_variants",
    "mean",
    "pick_variant",
    "router",
    "stddev",
]