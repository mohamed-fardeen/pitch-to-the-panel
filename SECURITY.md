# Security policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

We are currently in pre-1.0 development. Only the latest minor version receives security updates.

## Reporting a vulnerability

We take all security reports seriously. **Please do not open a public GitHub issue for security problems.**

Instead, please email **security@panelmind.dev** with:

- A description of the vulnerability
- Steps to reproduce
- The impact you believe it has
- (Optional) Suggested fix

We will acknowledge receipt within 48 hours and aim to ship a fix within 7 days for critical issues, 30 days for others.

If you would like to be credited in the disclosure, please let us know. We follow [coordinated disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure) best practices.

## Scope

### In scope

- The PanelMind web app (`apps/web`)
- The PanelMind API (`apps/api`)
- The published persona YAML schema (`apps/api/agents/personas/`)
- Documentation that leads to insecure defaults

### Out of scope

- Third-party services we integrate with (LangChain, Vercel, Fly.io, etc.) — report upstream
- Self-hosted deployments with non-default configurations
- Denial of service attacks
- Social engineering of maintainers

## Security considerations for self-hosters

When you self-host PanelMind:

- **Set strong API keys** for your LLM providers — they can be expensive if leaked
- **Lock down CORS** — set `ALLOWED_ORIGINS` in your `.env`
- **Enable rate limiting** — `RATE_LIMIT_ENABLED=true` (default in production)
- **Use HTTPS** in front of the API — do not expose port 8000 directly
- **Rotate your `NEXTAUTH_SECRET`** periodically
- **Back up your database** — the SQLite file in `apps/api/data/panelmind.db` is your source of truth
- **Keep dependencies updated** — `pnpm update && pip install --upgrade -e apps/api`

## Hall of fame

We thank the following security researchers for responsibly disclosing issues:

- *(Your name here, after your first report)*
