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

### Changed
- *(none yet)*

### Deprecated
- *(none yet)*

### Removed
- Mock library and transcripts views with hardcoded "OCT 24, 2023" dates
- Material Symbols + emoji mix (replaced with consistent icon set in later tiers)

### Fixed
- *(none yet)*

### Security
- *(none yet)*

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
