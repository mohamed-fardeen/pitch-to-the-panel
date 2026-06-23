# PanelMind

> **Adversarial feedback from synthetic VCs, designers, and operators — before you talk to a real one.**

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

PanelMind runs your startup pitch through a panel of AI personas (a sharp VC, a UX designer, an operator, a domain expert, and a curious beginner), each of whom critiques it from their perspective. The result is a structured verdict, a downloadable PDF report, and a re-pitch loop that helps you iterate until the panel is happy.

It's the same idea as Y Combinator office hours — but available at 2 AM, in 12 languages, and for free.

---

## ✨ Features

- **Multi-agent debate** — five distinct AI personas argue from their worldview
- **Three evaluation modes** — Spark (creative ideation), Venture (market/ROI), Reality (operational risks)
- **HITL summary approval** — your pitch is refined by the LLM, then you confirm before the panel starts
- **Adversarial revision loop** — get a verdict, then ask the panel to re-evaluate an improved version
- **PDF report export** — a shareable, professionally designed pitch evaluation
- **Multi-provider LLM** — Anthropic, OpenAI, Gemini, Groq, or local Ollama
- **Voice-first input** — speak your pitch instead of typing it
- **Real-time panel reactions** — TTS playback of each agent's critique
- **Open source, MIT licensed** — self-host, extend, ship

---

## 🚀 Quick start

### One-command Docker (recommended)

```bash
git clone https://github.com/your-org/panelmind.git
cd panelmind
cp .env.example .env
# Edit .env — at minimum, set one LLM provider key (ANTHROPIC_API_KEY, GROQ_API_KEY, etc.)
docker compose up
```

Open <http://localhost:3000> for the web UI and <http://localhost:8000/docs> for the API.

### Local dev (without Docker)

```bash
# Backend
cd apps/api
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Frontend (in another terminal)
cd apps/web
pnpm install
pnpm dev
```

Open <http://localhost:3000>.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  apps/web        Next.js 14 (App Router)                     │
│  ├─ (marketing)  Landing, pricing, docs                      │
│  ├─ (auth)       Sign in via Google / GitHub                 │
│  └─ (app)        Authenticated pitch UI                      │
└──────────────────────────────────────────────────────────────┘
                            │  REST + SSE
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  apps/api        FastAPI + LangGraph                         │
│  ├─ routes/      HTTP endpoints (pitches, verdicts, agents)  │
│  ├─ agents/      LangGraph state machine                     │
│  │  ├─ nodes/    pitch_refiner → controller → persona → ...  │
│  │  └─ personas/ YAML configs (vc, designer, operator, ...) │
│  ├─ services/    llm, embeddings, search, pdf                 │
│  └─ db/          SQLAlchemy + Postgres (SQLite in dev)       │
└──────────────────────────────────────────────────────────────┘
```

The full state machine:

```
                ┌──────────────┐
                │ pitch_refiner│ (LLM rewrites your pitch)
                └──────┬───────┘
                       │
                ┌──────▼───────┐
                │  controller  │ (Lead Strategist LLM decides next step)
                └──────┬───────┘
                       │
       ┌───────────┬───┴────┬──────────┬──────────┐
       │           │        │          │          │
   ┌───▼───┐  ┌────▼───┐ ┌──▼──┐ ┌─────▼────┐ ┌───▼───┐
   │persona│  │pitcher │ │tool │ │reflection│ │ final │
   │(agent)│  │(answer)│ │(web)│ │(meta)    │ │(end)  │
   └───┬───┘  └────┬───┘ └──┬──┘ └─────┬────┘ └───▲───┘
       │           │        │          │          │
       └────────┬──┴────────┴──────────┴──────────┘
                │
         ┌──────▼───────┐
         │memory_update │ (extract risks/strengths/claims)
         └──────┬───────┘
                │
         (loop back to controller)
```

See [`docs/architecture.md`](docs/architecture.md) for the deep dive.

---

## 🤝 Contributing

We welcome PRs of all sizes. The best places to start:

- **Add a new persona** — see [`docs/personas.md`](docs/personas.md). Drop a YAML file in `apps/api/agents/personas/` and the panel automatically picks it up.
- **Add a new node to the graph** — see `apps/api/agents/nodes/`. Each node is a single async function.
- **Improve a prompt** — all prompts are versioned under `apps/api/agents/prompts/`.
- **Build a new visualization** — the graph state stream is exposed as SSE; you can render it any way you want.
- **Translate the UI** — translations go in `apps/web/messages/`.

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a PR.

---

## 🌍 Community

- **GitHub Issues** — bug reports, feature requests
- **GitHub Discussions** — questions, ideas, show & tell
- **Discord** — *(coming soon — Tier 1)*

---

## 📄 License

[MIT](LICENSE) — use it, fork it, ship it, sell it. We just ask for attribution.

---

## 🙏 Acknowledgments

- **LangGraph** for the multi-agent orchestration primitives
- **shadcn/ui** for the design system inspiration
- The open-source LLM community for making this possible
- **Every founder** who has ever pitched into the void and wished they had a second opinion

---

<p align="center">
  Made with ❤️ by founders, for founders.
</p>
