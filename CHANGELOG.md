# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Rebrand from "Pitch to the Panel" to **PanelMind**
- Monorepo structure: `apps/web`, `apps/api`, `packages/shared`
- New top-level README, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY
- Real landing page replacing mock UI (Tier 0a)
- Persistence layer: SQLAlchemy 2.0 async models, `SessionRepository`
  abstraction, `InMemorySessionRepository` (default), and
  `SqlAlchemySessionRepository` (production) (Tier 0b)
- `pytest.ini` and 75 pytest tests covering both repository implementations,
  the legacy `sanitize_pitch_input`, the legacy `extract_json`, the legacy
  `VerdictSchema`, the new `SessionPersistenceBridge`, and FastAPI
  integration via `TestClient` (Tier 0b/0c)
- `SessionPersistenceBridge` (Tier 0c) — async-mirrors session-dict writes
  to the durable repository, filters out in-process state (asyncio.Event
  objects, etc.), survives DB outages
- FastAPI lifespan hook that creates the SQL schema on startup
  (`init_repository_schema`) and disposes the engine on shutdown
- `apps/api/data/panelmind.db` (SQLite) created automatically on first run

### Changed
- **Security**: rewrote the `sanitize_pitch_input` injection-pattern regexes
  to actually match multi-word variants like "ignore all previous
  instructions" (the old regex required `instructions` to immediately
  follow `ignore`). Adds matches for `disregard`, `act as`, `pretend to be`,
  ChatML markers, and Anthropic-style im_start/im_end tokens.

### Deprecated
- *(none yet)*

### Removed
- Mock library and transcripts views with hardcoded "OCT 24, 2023" dates
- Material Symbols + emoji mix (replaced with consistent icon set in later tiers)

### Fixed
- **Security**: `sanitize_pitch_input` regex bug — the original pattern
  `r'ignore (all |previous |above )?instructions?'` only matched when
  `instructions` immediately followed `ignore`, missing real-world
  injection attempts like "ignore all previous instructions and…".

### Security
- See "Changed" + "Fixed" above for the sanitizer hardening.
- The new persistence layer uses parameterized SQL throughout (no
  string interpolation in queries).

---

## [0.0.0] — Hackathon origin

The original hackathon project lived at the path before the rebrand. Its
history is preserved in the git log. Key features shipped:

- Multi-agent LangGraph orchestration (controller + 6 personas)
- Three evaluation modes (spark / venture / reality)
- HITL summary approval flow
- SSE streaming for real-time agent reactions
- TTS voice playback of each agent
- Black-swan analyst
- PDF report generation
- Pitch revision loop (rewrite → re-pitch)
- pgvector-based pitch history (Supabase)
- Multi-provider LLM support (Anthropic / OpenAI / Gemini / Groq / Ollama)

[Unreleased]: https://github.com/your-org/panelmind/compare/main...HEAD
[0.0.0]: https://github.com/your-org/panelmind/releases/tag/0.0.0
