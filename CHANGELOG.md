# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Langfuse LLM observability** (Tier-1a): every LLM call is traced
  with input/output/latency/fallback metadata. Opt-in via
  `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` + `LANGFUSE_HOST`. In
  dev, the trace context manager is a zero-cost no-op.
- **Sentry error tracking** (Tier-1b): FastAPI + Next.js integration.
  Server-side via `sentry-sdk[fastapi]`, client/server split for the
  web app via `@sentry/nextjs`. Opt-in via `SENTRY_DSN` (server) and
  `NEXT_PUBLIC_SENTRY_DSN` (client).
- **Public verdict pages /v/[verdictId]** (Tier-1c): server-rendered
  shareable page for any public verdict. Includes OG meta tags for
  Twitter/LinkedIn previews. Pitch content is truncated to 200 chars
  to prevent leaking the founder's full pitch. Per-session
  `is_public` flag on `PitchSession` (default `true`). Backend
  endpoints: `GET /v/{id}/public` (sanitized JSON) and
  `GET /v/{id}/og` (HTML with OG tags). Frontend route at
  `apps/web/app/v/[verdictId]/page.tsx` with full SEO + meta
  generation via `generateMetadata()`.
- **Embeddings migrated to native pgvector** (Tier-1d): the legacy
  `services/db.py` (using the unmaintained `vecs` library) is
  replaced by `services/embeddings.py` which uses SQLAlchemy + raw
  pgvector SQL for Postgres production and an in-memory cosine
  fallback for SQLite dev. The legacy /api/pitch-history endpoint
  is rewired to use the new list_all_pitches() helper. Same public
  API (save_pitch_history, retrieve_past_pitches,
  format_past_pitches_for_context) so no orchestrator changes
  needed.
- **Multi-language pitch translation** (Tier-1e): `POST /api/translate`
  endpoint translates any text into one of 8 supported languages
  (en, es, hi, zh, fr, de, pt, ja) using the configured LLM provider.
  English-to-English is a passthrough (no LLM call). Errors fall
  back to the original text with model='fallback'. `GET /api/languages`
  returns the supported language catalog.
- **Eval suite + golden transcripts** (Tier-2a): prompt regression
  testing. `tests/evals/golden_transcripts/*.json` are 4 sample
  pitches across the 3 modes with expected verdict shape, score
  ranges, and keyword presence. The eval suite (14 tests) verifies
  every transcript produces a well-formed verdict. Runs against a
  deterministic mock by default; set `PANELMIND_EVAL_REAL_LLM=1` to
  run against the real LLM provider. Catches prompt regressions in CI.

### Fixed
- **Module duplication**: `backend/main.py` was importing
  `persistence` (bare) while tests used `backend.persistence`
  (absolute). These are two distinct module objects with separate
  module-level state, causing test fixtures' `set_repository()` to
  silently fail. Switched `main.py` to absolute imports throughout.

### Added (Tier 0)
- Rebrand from "Pitch to the Panel" to **PanelMind**
- Monorepo structure: `apps/web`, `apps/api`, `packages/shared`
- New top-level README, LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY
- Real landing page replacing mock UI (Tier 0a)
- Persistence layer: SQLAlchemy 2.0 async models, `SessionRepository`
  abstraction, `InMemorySessionRepository` (default), and
  `SqlAlchemySessionRepository` (production) (Tier 0b)
- `pytest.ini` and 95 pytest tests covering both repository implementations,
  the legacy `sanitize_pitch_input`, the legacy `extract_json`, the legacy
  `VerdictSchema`, the new `SessionPersistenceBridge`, FastAPI
  integration via `TestClient`, and the persona YAML loader (Tier 0b/0c/0d)
- `SessionPersistenceBridge` (Tier 0c) — async-mirrors session-dict writes
  to the durable repository, filters out in-process state (asyncio.Event
  objects, etc.), survives DB outages
- FastAPI lifespan hook that creates the SQL schema on startup
  (`init_repository_schema`) and disposes the engine on shutdown
- `apps/api/data/panelmind.db` (SQLite) created automatically on first run
- **Persona catalog** (Tier 0d): 6 YAMLs in `apps/api/agents/personas/`
  (vc, designer, operator, expert, beginner, interviewer) plus a
  `_template.yaml` for new contributors
- **Persona loader** (`backend/agents/loader.py`): reads YAMLs at
  import time, validates, caches, exposes `PersonaCatalog` plus
  backwards-compat shims for the legacy orchestrator
- **NextAuth v5** (Tier 0e): Google + GitHub OAuth providers, sign-in
  and sign-out pages, edge middleware that gates `/app/*` and
  `/api/pitches/*`, SessionProvider in root layout
- **Docker** (Tier 0f): `Dockerfile.api` (multi-stage, ~150 MB runtime)
  and `Dockerfile.web` (Next.js standalone, ~120 MB runtime) plus
  `docker-compose.yml` with a named volume for SQLite persistence
- **GitHub Actions CI** (Tier 0f): `.github/workflows/ci.yml` runs
  backend lint + typecheck + test, web lint + typecheck + build,
  and Docker image builds on every push
- **Rate limiting** (Tier 0f): `backend/rate_limit.py` configures
  SlowAPI with 60 req/min per IP by default, in-memory storage,
  env-tunable
- **Structured logging** (Tier 0f): `LOG_LEVEL` env var, basic
  formatter with timestamps; ready to swap to structlog/JSON in
  Tier 1
- **Root `pyproject.toml`**: ruff + mypy workspace config that
  applies to all Python code in the repo

### Removed
- **Meshy 3D endpoint** (`/api/pitch/generate-3d`): hackathon-era
  dead code that contributed nothing to the pitch evaluation flow.
  `generate_3d_from_sketch()` and the `MESHY_API_URL` constant
  are gone from `orchestrator.py` too.

### Security
- **CORS lockdown** (Tier 0f): `allow_origins=["*"]` replaced with
  an env-driven allowlist (`ALLOWED_ORIGINS`). Setting wildcards
  with `allow_credentials=True` is a known anti-pattern.

### Changed
- **Personas as YAML**: replaced the hardcoded `AGENTS_CONFIG` /
  `AGENT_GOALS` / `OCEAN_PROFILES` / `PERSONA_ANCHORS` dicts in
  `backend/orchestrator.py` and `backend/prompts.py` with a YAML-based
  catalog at `apps/api/agents/personas/`. Adding a new persona is now
  one YAML file. See `docs/personas.md` for the schema.
- **Persona loader** (`backend/agents/loader.py`): reads YAMLs at
  import time, validates required fields, skips malformed files,
  exposes a typed `PersonaCatalog`. Backwards-compat shims for
  `AGENTS_CONFIG` / `AGENT_GOALS` / `OCEAN_PROFILES` are computed
  from the catalog so the legacy orchestrator code works unchanged.
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
