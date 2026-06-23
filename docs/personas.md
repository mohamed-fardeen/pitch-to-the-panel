# Personas

> Under construction. The YAML schema and per-persona guide will be added in
> Tier 0b alongside the move of agent configs from `apps/api/agents/personal/
> ...` to per-persona YAML files.

## What is a persona?

A persona is a synthetic expert with a specific worldview. Each one critiques
your pitch from their perspective. The panel works best when personas
*disagree* with each other — that's where the most useful feedback comes from.

## Built-in personas

The initial five personas cover the most common perspectives a founder needs:

| Persona        | Role                  | Cares most about          |
| -------------- | --------------------- | ------------------------- |
| Arjun (VC)     | Venture Capitalist    | ROI, market size, moat    |
| Priya (Designer)| Design Strategist    | UX, engagement, delight   |
| Ravi (Operator)| Operations Manager    | Execution, risk, scale    |
| Expert         | Technical Consultant  | Feasibility, fact-checks  |
| Kiran (Beginner)| Curious Consumer     | Clarity, purpose, "why?"  |

## How to add a new persona

1. Copy `apps/api/agents/personas/_template.yaml` (added in Tier 0b).
2. Fill in the required fields.
3. Drop it in `apps/api/agents/personas/your_persona.yaml`.
4. Open a PR. The persona will appear in the next release.

Full schema reference coming in Tier 0b.