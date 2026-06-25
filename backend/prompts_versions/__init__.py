"""
backend.prompts_versions — Tier-2c prompt versioning and A/B framework.

Provides a simple, lightweight system for running A/B tests on
prompts without a full experimentation platform.

Core concepts:

- `PromptExperiment` — a named A/B test (e.g. "controller-v2").
- `PromptAssignment` — which variant a specific session is in.
- `PromptOutcome` — recorded metric for a session (e.g. user rating).

Usage:

    from backend.prompts_versions import router

    # At startup: register experiments
    router.register(
        name="controller-v2",
        description="Test the new controller prompt",
        variants={"control": 80, "v2": 20},
    )

    # Per request: pick a variant (deterministic by session_id)
    variant = router.pick_variant("controller-v2", session_id="abc")

    # Per request: record an outcome
    router.record_outcome(
        experiment_name="controller-v2",
        session_id="abc",
        metric_name="user_rating",
        metric_value=4.5,
    )

    # Compare variants
    comparison = router.compare("controller-v2", "user_rating")
"""
