# Contributing to PanelMind

First off — thank you for taking the time to contribute. PanelMind is a community project and we want it to be a great place to contribute, regardless of your experience level.

## Table of contents

- [Code of conduct](#code-of-conduct)
- [Quick start](#quick-start)
- [Development setup](#development-setup)
- [Project structure](#project-structure)
- [How to contribute](#how-to-contribute)
  - [Add a new persona](#add-a-new-persona)
  - [Add a new agent node](#add-a-new-agent-node)
  - [Improve a prompt](#improve-a-prompt)
  - [Report a bug](#report-a-bug)
  - [Request a feature](#request-a-feature)
- [Style guide](#style-guide)
- [Pull request process](#pull-request-process)
- [Release process](#release-process)

## Code of conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the maintainers.

## Quick start

```bash
# 1. Fork and clone
git clone https://github.com/your-fork/panelmind.git
cd panelmind

# 2. Install dependencies
pnpm install
cd apps/api && pip install -e ".[dev]" && cd ../..

# 3. Copy env
cp .env.example .env

# 4. Run
docker compose up
# OR
pnpm dev
```

Visit <http://localhost:3000> to see the app.

## Development setup

### Prerequisites

- **Node.js 20+** and **pnpm 9+** ([install pnpm](https://pnpm.io/installation))
- **Python 3.11+** and **uv** (recommended) or pip
- **Docker** and **Docker Compose** (for the one-command dev environment)

### Without Docker

Two terminals:

```bash
# Terminal 1: API
cd apps/api
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Terminal 2: Web
cd apps/web
pnpm install
pnpm dev
```

### Running tests

```bash
# Python tests
cd apps/api
pytest

# TypeScript tests
cd apps/web
pnpm test

# End-to-end smoke tests
pnpm test:e2e
```

## Project structure

```
panelmind/
├── apps/
│   ├── api/         FastAPI backend + LangGraph
│   └── web/         Next.js 14 frontend
├── packages/
│   └── shared/      Shared TypeScript types (TBD)
├── docs/            Architecture, personas, etc.
└── docker-compose.yml
```

## How to contribute

### Add a new persona

The fastest way to make PanelMind your own. Personas are YAML data, not code — no Python knowledge required.

1. Create a new YAML file in `apps/api/agents/personas/` (use `vc.yaml` as a template).
2. Add a one-line description, an OCEAN profile, a goal, and a few example phrases.
3. Add a thumbnail or avatar under `apps/web/public/personas/`.
4. Open a PR. The persona automatically appears in the next panel composition.

Full guide: [`docs/personas.md`](docs/personas.md).

### Add a new agent node

A "node" is a single step in the LangGraph state machine. Each one is one async function.

1. Create `apps/api/agents/nodes/my_node.py`.
2. Add a graph edge in `apps/api/agents/graph.py`.
3. Add a unit test in `apps/api/tests/nodes/test_my_node.py`.
4. Open a PR.

### Improve a prompt

All prompts live in `apps/api/agents/prompts/`. They're versioned with the codebase — every change is a git diff.

1. Edit the prompt.
2. Run the eval suite (`pytest apps/api/tests/evals/`) to make sure you didn't break anything.
3. Open a PR with before/after example outputs.

### Report a bug

Use the [bug report issue template](.github/ISSUE_TEMPLATE/bug.md). Include:

- What you did (steps to reproduce)
- What you expected
- What actually happened
- Your OS, browser, Python version, Node version
- Any error logs or screenshots

### Request a feature

Use the [feature request template](.github/ISSUE_TEMPLATE/feature.md). Describe the problem you're trying to solve, not the solution you'd prefer. We may have a better idea.

## Style guide

### Python

- **Formatter**: `ruff format`
- **Linter**: `ruff check`
- **Type checker**: `mypy --strict`
- **Docstrings**: Google style
- **Imports**: absolute, sorted by `ruff`

### TypeScript

- **Formatter**: `prettier`
- **Linter**: `eslint`
- **Types**: strict, no `any` without a comment explaining why
- **Naming**: camelCase for variables, PascalCase for components, kebab-case for files

### Commits

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(personal): add climate VC persona
fix(api): prevent session leak on SSE disconnect
docs: update README install steps
chore: bump langgraph to 0.3
```

## Pull request process

1. **Branch off `main`**. Branch names: `feat/your-feature`, `fix/your-bug`, `docs/your-doc`.
2. **Keep PRs small**. Aim for <500 lines of diff. If your change is bigger, break it up.
3. **Write tests** for any non-trivial change. We won't merge without them.
4. **Run the linter and tests locally** before pushing. CI will run them again, but a local run is faster.
5. **Update the CHANGELOG.md** under "Unreleased" with a one-line description of your change.
6. **Request a review** from `@maintainers`.
7. **Address review feedback** in new commits (don't force-push during review).
8. **Squash and merge** once approved.

## Release process

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** — breaking changes to the public API or persona schema
- **MINOR** — new features, backward-compatible
- **PATCH** — bug fixes, backward-compatible

Releases are cut from `main` on the first of each month. The release process is fully automated via GitHub Actions.

## Getting help

- **GitHub Discussions** for general questions
- **Discord** (coming soon) for real-time chat
- **Email** maintainers@panelmind.dev for private matters

Thanks again for contributing. 🙏
