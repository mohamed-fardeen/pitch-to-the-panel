# Architecture

> Under construction. This document will be expanded in Tier 1 alongside the
> Langfuse observability integration. For now, see the [README](../README.md)
> for the high-level diagram.

## High-level

PanelMind is a single FastAPI process that exposes both REST and SSE
endpoints, plus a Next.js 14 frontend. The interesting part is the agent
orchestration, which lives entirely server-side.

## Why LangGraph

LangGraph gives us a few things for free that would be painful to build by hand:

1. **State management** — every node receives the full session state and
   returns a partial update. We never have to pass around mutable globals
   (we still do, but we're fixing that in Tier 0b).
2. **Conditional edges** — the controller decides what runs next based on
   the current state.
3. **Async streaming** — `graph.astream()` lets us emit events to the SSE
   queue in real time as nodes complete.
4. **Built-in interrupt support** — useful for the user-answer flow where
   the graph needs to pause until the user types something.

## The state machine

See the diagram in the [README](../README.md#architecture).

## Key design decisions

### Why a Lead Strategist controller node?

We could have let each persona decide when to speak. Instead, we have a single
LLM-driven controller that picks the next action. This is simpler to debug
(the action log is one place) and prevents "talk-over" where two agents
generate simultaneously.

### Why HITL summary approval?

Before the panel starts debating, we run the user's raw pitch through an LLM
to rewrite it into a clear, concise paragraph. The user then sees this
rewritten version and either approves it or edits it. This dramatically
improves downstream agent quality — a 5-word pitch gives the panel nothing
to work with.

### Why a memory layer?

Without memory, every agent would only see the most recent turns. With
memory, each agent has access to a structured list of risks, strengths,
claims, and contradictions extracted from prior turns. The controller can
also use the memory's `missing` field to decide when to ask the user for
more information.

### Why a revision loop?

A single verdict is useful. Two verdicts (one before revision, one after)
are dramatically more useful — they show the founder the *delta*. This is
the same reason sports teams watch game film: the value is in what changed.

## What's coming

- **Tier 0b**: replace the in-memory `sessions` dict with SQLAlchemy + SQLite
- **Tier 1**: Langfuse integration for full trace observability
- **Tier 2**: Dramatiq workers for long-running evaluations
- **Tier 2**: eval suite for prompt regression testing