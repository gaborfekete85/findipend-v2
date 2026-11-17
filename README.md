# Findipend

A full-stack cryptocurrency portfolio tracker. Users record buys and sells across multiple portfolios, choose exactly which lots each sell draws from, and see cost basis, realized and unrealized P&L per asset, per portfolio, and across all portfolios.

Domain vocabulary is defined in [GLOSSARY.md](./GLOSSARY.md); key decisions are in [docs/adr/](./docs/adr/). This README uses those terms exactly.

## Scope

### In scope (v1)
- Sign-up / sign-in via Clerk; each user sees only their own data
- Portfolio create, rename, delete
- Buys (each opens one lot) and sells (allocated to specific lots); both editable and deletable
- Open and closed positions, per-portfolio summary, all-portfolios overview
- Live USD prices from CoinGecko

### Out of scope (v1)
- CSV / exchange imports
- Transfers between portfolios
- Currencies other than USD
- Price-history charts, portfolio value over time
- Tax reports
- Sharing portfolios between users
- Any deployment beyond local Docker Compose

## Domain Rules

### Buys and lots
- A buy records: asset, quantity (> 0), total USD amount (≥ 0, fee included), fee, trade date, optional comment.
- **Fee** is contained in the total, not added on top. It defaults to 0.1% of the total and can be overridden (including to 0). It is stored for display only.
- **Trade date** is a calendar date (no time); defaults to today. Back-dating is allowed.
- A zero-total buy (airdrop, staking reward, gift) is valid: its lot has zero cost basis.
- Each buy opens exactly one **lot**. Lot cost per unit = buy total ÷ buy quantity.

### Sells and allocations
- A sell records: asset, quantity (> 0), total USD received (≥ 0, fee included, i.e. net proceeds), fee, trade date, optional comment, and one or more **allocations**.
- Each allocation names a lot and a quantity. Allocation quantities must sum exactly to the sell quantity.
- An allocation may only draw from a lot that is: the same asset, in the same portfolio, with trade date ≤ the sell's trade date, and with enough unsold quantity.
- Selling more than available is rejected.
- The backend never chooses lots. The UI pre-fills a FIFO suggestion (oldest lot first) that the user can edit before submitting.

### Editing and deleting
- Editing or deleting a sell releases its allocations back to their lots.
- Editing a lot's buy is allowed only if its quantity stays ≥ the quantity already allocated from it and its trade date stays ≤ every sell drawing from it.
- Deleting a buy whose lot has allocations is blocked until those sells are deleted or re-allocated by the user.
- No change ever silently re-allocates a sell.
- Deleting a portfolio deletes all its buys, sells and allocations, after the user types the portfolio name to confirm.

### Portfolios
- Portfolio names are unique per user (case-insensitive), 1–50 characters.

### Calculations
All analytics are derived on read from buys, sells and allocations; nothing below is stored ([ADR-0002](./docs/adr/0002-derived-positions.md)).

| Metric | Definition |
|---|---|
| Lot unsold quantity | buy quantity − Σ allocated quantity from that lot |
| Allocation proceeds | sell total × (allocation qty ÷ sell qty) |
| Allocation cost | lot cost per unit × allocation qty |
| **Realized P&L** | Σ (allocation proceeds − allocation cost) |
| **Total Invested** | Σ buy totals, all time (informational; never used in P&L) |
| **Cost Basis** | Σ over open lots: lot cost per unit × unsold quantity |
| **Average Buy Price** | cost basis ÷ unsold quantity (per position; informational) |
| Market Value | Σ unsold quantity × current price |
| **Unrealized P&L** | market value − cost basis |
| **Total P&L** | realized P&L + unrealized P&L |

Positive P&L means profit. Every metric is available per asset, per portfolio, and across all portfolios.

Example: buy 1 BTC for $30k (lot A) and 1 BTC for $50k (lot B); sell lot A for $60k; BTC now $60k → realized +$30k, total invested $80k, cost basis $50k, unrealized +$10k, total P&L +$40k.

### Numbers
- Quantities: up to 18 decimal places.
- USD: stored with 8 decimal places, displayed with 2.
- Exact decimal arithmetic end to end (Python `Decimal`, Postgres `NUMERIC`, strings over JSON); round only at display.

### Prices
- The backend fetches prices from CoinGecko and caches them ~60 s; the asset list (7000+ assets) is cached daily.
- If CoinGecko is unavailable, the app keeps working: it shows the last known price with its timestamp, or "price unavailable" (and omits unrealized P&L for that asset).

## Tech Stack

### Backend (Python)
- **FastAPI**, **Pydantic**, **SQLAlchemy**, **PostgreSQL**
- Clerk session JWT verified on every request (via Clerk JWKS); the Clerk user ID scopes all data. No local user table.

### Frontend (TypeScript only)
- **Vite + React 19 + TypeScript**
- **Tailwind CSS**, **React Router**
- **Clerk React SDK** for sign-up / sign-in

### DevOps
- **Docker** + **Docker Compose** (Postgres, backend, frontend)

## Project Structure

```
findipend/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routers
│   │   ├── core/             # Config, DB session, Clerk auth
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── services/         # Domain logic: allocations, P&L, prices
│   │   └── main.py
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/              # Typed API client
│   │   ├── pages/            # Overview, portfolio detail, buy/sell forms
│   │   └── components/
│   ├── Dockerfile
│   └── package.json
└── docker-compose.yml
```

## Data Model

### portfolios
- id, user_id (Clerk user ID), name, created_at, updated_at
- unique (user_id, lower(name))

### buys (one row = one lot)
- id, portfolio_id → portfolios (cascade delete)
- asset_id (CoinGecko id), asset_name, asset_symbol
- quantity NUMERIC(38,18), total_usd NUMERIC(28,8), fee_usd NUMERIC(28,8)
- trade_date DATE, comment, created_at, updated_at

### sells
- id, portfolio_id → portfolios (cascade delete)
- asset_id, asset_name, asset_symbol
- quantity NUMERIC(38,18), total_usd NUMERIC(28,8), fee_usd NUMERIC(28,8)
- trade_date DATE, comment, created_at, updated_at

### allocations
- id, sell_id → sells (cascade delete), buy_id → buys (restrict delete)
- quantity NUMERIC(38,18)

There is no positions table.

## API (all endpoints require a Clerk session; all data scoped to the caller)

### Portfolios
- `POST /api/v1/portfolios` — create
- `GET /api/v1/portfolios` — list
- `GET /api/v1/portfolios/{id}` — get
- `PATCH /api/v1/portfolios/{id}` — rename
- `DELETE /api/v1/portfolios/{id}` — delete with all contents (body: `{ "confirm_name": "..." }`)

### Buys
- `POST /api/v1/portfolios/{id}/buys`
- `GET /api/v1/portfolios/{id}/buys`
- `PUT /api/v1/portfolios/{id}/buys/{buy_id}` — subject to lot edit rules
- `DELETE /api/v1/portfolios/{id}/buys/{buy_id}` — 409 if the lot has allocations

### Lots
- `GET /api/v1/portfolios/{id}/lots?asset_id=&open=true&as_of=YYYY-MM-DD` — lots with unsold quantity, for the sell form

### Sells
- `POST /api/v1/portfolios/{id}/sells` — body includes `allocations: [{ buy_id, quantity }]`
- `GET /api/v1/portfolios/{id}/sells` — with allocations and per-allocation realized P&L
- `PUT /api/v1/portfolios/{id}/sells/{sell_id}` — replaces allocations
- `DELETE /api/v1/portfolios/{id}/sells/{sell_id}`

### Analytics
- `GET /api/v1/portfolios/{id}/positions` — open and closed positions
- `GET /api/v1/portfolios/{id}/summary` — portfolio totals with current prices
- `GET /api/v1/summary` — all-portfolios totals and per-asset breakdown

### Assets
- `GET /api/v1/assets?query=` — search the cached CoinGecko asset list

Validation failures return 422; rule conflicts (over-selling, uncovered allocations, duplicate name) return 409 with a message naming the offending lot/sell.

## Screens
- **Overview** — all-portfolios widgets (total invested, cost basis, realized, unrealized, total P&L) and per-asset table
- **Portfolio detail** — the same widgets for one portfolio, open positions table, closed positions table, transaction history (buys and sells, sells expandable to show allocations)
- **Buy form** — asset search, quantity, total, fee (pre-filled 0.1%), trade date (pre-filled today), comment
- **Sell form** — asset (from open positions), quantity, total, fee, trade date, comment, lot allocation table pre-filled FIFO and editable; submit disabled until allocations sum to the sell quantity

## Getting Started

```bash
cp .env.example .env   # set CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY, CLERK_JWKS_URL
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (docs at `/docs`)
- PostgreSQL: localhost:5432
