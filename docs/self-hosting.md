# Self-hosting

> This document will be filled in alongside the Docker + docker-compose work
> in Tier 0c. For now, see the [README](../README.md#quick-start).

## Quick reference

### One-command Docker

```bash
git clone https://github.com/your-org/panelmind.git
cd panelmind
cp .env.example .env
# Edit .env
docker compose up
```

Open <http://localhost:3000> for the web UI.

### Without Docker

See [README → Quick start](../README.md#quick-start).

## Production checklist

When you self-host PanelMind in production:

- [ ] Use Postgres (not SQLite) for the database
- [ ] Set a strong `NEXTAUTH_SECRET` (`openssl rand -base64 32`)
- [ ] Configure `ALLOWED_ORIGINS` for CORS
- [ ] Enable rate limiting (`RATE_LIMIT_ENABLED=true`)
- [ ] Put the API behind HTTPS (Caddy / nginx / Cloudflare)
- [ ] Set up database backups
- [ ] Configure Sentry for error tracking (Tier 1)
- [ ] Configure Langfuse for LLM tracing (Tier 1)