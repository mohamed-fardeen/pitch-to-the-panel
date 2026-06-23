# PanelMind API

The Python backend for [PanelMind](../../README.md). FastAPI + LangGraph +
SQLAlchemy 2.0 (async).

## Status

**Tier 0a only.** This directory contains the project skeleton — `pyproject.toml`,
configuration, and tooling config. The actual FastAPI app (`app/main.py`) and
LangGraph state machine (`app/agents/`) arrive in **Tier 0b**.

The legacy code still lives at `../../backend/` and is served via the existing
`run.bat` / `run.ps1` scripts. See [Tier 0b](../../CHANGELOG.md) for the
migration plan.

## Running

Once Tier 0b ships:

```bash
# Local dev
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Tests
pytest
```

## Layout (target)

```
app/
├── main.py            FastAPI app factory
├── config.py          Pydantic settings
├── deps.py            Dependency injection
├── logging.py         structlog config
├── api/v1/            HTTP routes
├── agents/
│   ├── graph.py       LangGraph state machine
│   ├── nodes/         Per-node async functions
│   ├── personas/      YAML persona configs
│   └── prompts/       Versioned prompt library
├── services/          llm, embeddings, search, pdf
├── db/                SQLAlchemy models + repositories
└── tests/             pytest suite
```
