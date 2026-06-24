"""
tests.evals — Eval suite for PanelMind prompts.

The eval suite runs each "golden transcript" (a sample pitch + expected
verdict shape) through the orchestrator's verdict-generation path and
checks that the output:

- Matches the JSON schema (strongest, weakness, fix, score, recommendation)
- Contains expected keywords (e.g. the pitch domain)
- Falls within expected score ranges
- Has the expected number of risks and strengths in memory

This is **shape validation**, not exact-text matching. We don't want
to break the eval every time the LLM rewrites a sentence — we want
to catch regressions where the prompt produces malformed output,
empty fields, wrong types, or wildly wrong scores.

Run with:
    pytest tests/evals/ -v

The eval framework can run against the real LLM provider (slow but
authoritative) or with a deterministic mock (fast, for CI).
"""