# Looper (for /market/looper/)

## Overview
LOOPER is a personal swing-trading assistant. It tracks a portfolio of active "loops"
(sell a name high, buy it back low), surfaces sell / re-entry signals, scores fundamentals,
scans the whole market for opportunities, and keeps a full buy/sell ledger with
re-entry-reserve and profit accounting.

## Tech Stack
- **Backend**: FastAPI + Uvicorn (ASGI), Python 3.10+. Only third-party deps are
  `fastapi`, `uvicorn`, `requests`; the rest is the standard library
  (`csv`, `json`, `threading`, `datetime`, `collections`, `pathlib`).
- **Frontend**: React 18 + Vite 5 (`@vitejs/plugin-react`). Single-page app, no UI/state/CSS
  framework — plain CSS (`styles.css`), a thin `fetch` wrapper (`api.js`), and `localStorage`
  for small UI prefs (hidden boxes, sidebar width, live-refresh interval).
- **Data source**: Massive API (Polygon.io-compatible REST) over HTTPS with a bearer token —
  real-time prices, RSI/EMA indicators, full-market snapshots, news, financials.
- **Storage**: no database. Flat files are the source of truth — `config.json`
  (holdings / watchlist / settings), `data/ledger.csv` (every buy & sell, the master history),
  `data/scan.json` (last scan), and per-ticker `data/<TICKER>_status.json` price caches.

## Modules
- `looper_engine.py` — core: signal evaluation, deep scan, ledger + tally, quotes.
- `api.py` — thin FastAPI JSON layer over the engine.
- `fundamentals.py` — fundamental scorecard, news digest, fused stance.
- `reentry_planner.py` — re-entry sizing plan from reserve + profit.

## Running
```bash
./run.sh
```
Launcher (zsh) creates a Python venv, installs deps, and starts both servers.

- App (open this):  `http://localhost:5173`
- Backend API:      `http://localhost:8000`  (docs at `/docs`)

Ports are env-overridable (`BACKEND_PORT`, `FRONTEND_PORT`); Vite proxies `/api` → backend.

## Environment Variables
```
MASSIVE_API_KEY=<your key>   # required — read from the environment, never committed to code
```

## Features
- Portfolio of loops: Sell Watch (held) and Re-Entry Zones (cash), each box showing live
  P/L and a hold / sell / add / buy-back decision chip.
- Signals: RSI + EMA (2-of-3 rules) with selectable horizons (swing/position/weekly/monthly).
- Fundamental scorecard + news/event alerts (M&A, big moves) inside each stock box.
- Deep Opportunity Scan: whole-market, with popular names, buckets, and clickable
  sector-theme heat; per-subsection sort / filter / hide.
- Ledger as an editable master file: FIFO round-trip view (buy paired with sell), pagination,
  re-entry-reserve and profit-split accounting.
- Live price refresh for the Sell/Buy boxes (fast quotes endpoint, manual + auto intervals).

## Data Source
Massive API (real-time). Auth via `MASSIVE_API_KEY` bearer token.

---
**Status**: Active | **Owner**: Pouria Etab | **Updated**: July 7, 2026
