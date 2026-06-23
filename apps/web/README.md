# PanelMind Web

The Next.js 14 frontend for [PanelMind](../../README.md). Currently contains
the new marketing landing page. The full pitch UI lives in `frontend/` (legacy)
and will migrate here in **Tier 0b**.

## Running the new landing page

```bash
pnpm install
pnpm dev
```

Open <http://localhost:3000>.

## Status

- ✅ `app/(marketing)/page.tsx` — new landing page (this PR)
- ⏳ `app/(auth)/` — sign-in pages (Tier 0b)
- ⏳ `app/(app)/pitch/new` — pitch setup form (Tier 0b)
- ⏳ Migration of `frontend/app/page.tsx` → `app/(app)/page.tsx` (Tier 0b)
