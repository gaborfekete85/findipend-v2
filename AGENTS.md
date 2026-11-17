# AGENTS.md — Findipend

Crypto portfolio tracker: buys open lots, sells are allocated to user-chosen lots, all P&L is derived on read. The README is the spec; GLOSSARY.md is the vocabulary; docs/adr/ holds decisions. Read all three before changing behaviour.

## Layout

- `backend/` — FastAPI + Pydantic + SQLAlchemy + PostgreSQL, managed with **uv** (`pyproject.toml`)
  - `app/api` routers · `app/core` config/DB/Clerk auth · `app/models` · `app/schemas` · `app/services` domain logic (allocations, P&L, prices)
- `frontend/` — Vite + React 19 + TypeScript + Tailwind + React Router + Clerk, managed with **bun**
  - `src/api` typed client · `src/pages` · `src/components`
- `docker-compose.yml` — Postgres, backend, frontend (local only)
- `docs/adr/` — architecture decisions

## Commands

```bash
# backend
cd backend && uv run ruff check . && uv run pytest
# frontend
cd frontend && bun install --frozen-lockfile && bun run lint && bunx tsc --noEmit && bun run test
# full stack
docker compose up --build
```

`g-stack verify` runs the same checks; each one is skipped until its directory exists.

## Rules

- **Use the glossary terms.** Buy, Lot, Sell, Allocation, Position, Cost Basis, Realized/Unrealized P&L. Avoid the synonyms GLOSSARY.md lists.
- **Exact decimals end to end.** Python `Decimal`, Postgres `NUMERIC`, decimal strings over JSON. Never `float`. Round only at display.
- **Nothing derived is stored.** There is no positions table and no stored P&L (ADR-0002).
- **The backend never chooses lots.** Allocations come from the client; FIFO is only a UI pre-fill (ADR-0001).
- **No silent re-allocation.** Edits or deletes that would invalidate an allocation are rejected with a 409 naming the lot or sell.
- **Every query is scoped to the Clerk user ID** from the verified JWT. There is no local user table.
- **CoinGecko outages must not break the app.** Show the last known price or "price unavailable".
- Bun for the frontend, never npm/npx. TypeScript only in `frontend/`.
- Never commit `.env` or Clerk keys. `.env.example` holds placeholders only.
- Changes to money math, auth or the DB schema carry the `money` / `auth` / `schema` label and always need a human merge.
