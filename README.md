# LOOPER

**A rules-based swing-trading assistant that turns a discretionary "buy quality,
sell high, re-enter lower" strategy into repeatable, explainable signals.**

For each stock on a watchlist, LOOPER answers the three questions a portfolio
manager asks — *is this a good business, is it cheap right now, and is it a good
moment to trade?* — by combining a technical timing engine (RSI, moving averages,
volume, analyst targets) with a fundamental scorecard (valuation, quality, health,
growth). It distills everything into one plain-English stance — **Accumulate,
Hold, Trim, or Exit** — and always shows the reasoning behind the call.

Built as a personal tool but engineered like a small product: a headless Python
engine that runs unattended on a schedule, a phone-friendly web dashboard, secrets
kept in environment variables, and a clean split between data, logic, and UI.

> Decision support, not financial advice.

## Features

- **Loop timing signals** — SELL / WATCH / HOLD / RE-ENTRY from a 2-of-3 rule set
  over RSI, EMA-20/50, price vs analyst target, and volume.
- **Fundamental scorecard** — each stock scored on valuation, quality, health, and
  growth; every factor carries a status, a weight, and a plain-language tooltip.
- **Two verdicts + fused stance** — separates "good business at a good price" from
  "good time to trade," then fuses them into a portfolio-manager call.
- **Re-entry planner** — after a sell, sizes how much cash to reserve and where the
  next entry zone is, in whole and fractional shares.
- **Multi-stock dashboard** — sell and buy watchlists ranked by urgency, with
  drill-down detail pages (financials, news + sentiment, earnings).
- **Runs locally on a schedule** — the engine has no external-AI dependency and
  costs nothing to run daily; the dashboard is just a viewer.

## How it works

```text
        Massive API  (prices · RSI/EMA · fundamentals · news)
                              │
                   looper_engine.py  ──►  data/portfolio.json
            (timing signals + scoring, runs on a schedule)
              ┌───────────────┼────────────────┐
   fundamentals.py     reentry_planner.py    (per-stock results)
 (valuation/quality/   (reserve + next
   health/growth)        entry zone)
                              ▼
                api.py  (FastAPI JSON API)
                              ▼
              frontend/  (React, laptop & phone)
```

1. **`looper_engine.py`** pulls daily price, RSI, EMAs, and volume for each stock in
   `config.json`, evaluates the timing rules, and writes `data/portfolio.json`.
   It runs standalone (cron / macOS launchd) with no AI/token cost.
2. **`fundamentals.py`** scores each business and fuses that with the timing read
   into a single stance.
3. **`reentry_planner.py`** computes the reserve budget and next entry zone after a
   sell.
4. **`api.py`** exposes all of it as a JSON API; the **React app in `frontend/`**
   renders the portfolio, detail pages, and the add-holding form.

**Tech:** Python · FastAPI · React (Vite) · Massive (Polygon-compatible) REST API.
Secrets via environment variables; personal config and holdings kept out of
version control.

---

## One-time setup

### 1. Export your Massive API key (never goes in code)

Your key lives in your shell environment, not in any file in this repo.

```bash
# confirm you're on zsh (default on modern macOS)
echo $SHELL

# open your shell config in VS Code
code ~/.zshrc

# add this line at the bottom, paste your real key between the quotes, save:
export MASSIVE_API_KEY="your_real_key_here"

# reload so the current terminal picks it up
source ~/.zshrc

# verify it's set (prints "key is set" without revealing the key)
[ -n "$MASSIVE_API_KEY" ] && echo "key is set"
```

Because the key is exported in `~/.zshrc`, every project and every terminal on
your machine can read it via `MASSIVE_API_KEY` — set it once, reuse everywhere.

### 2. Create a virtual environment and install dependencies

One isolated environment per project keeps your trading projects from interfering
with each other.

```bash
cd path/to/looper
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json   # then edit config.json with your stocks/positions
```

Your real positions live in `config.json`, which is gitignored and never pushed.
The committed `config.example.json` is a sanitized template.

### 3. Run the connection test

```bash
python test_massive_connection.py          # tests BRKR
python test_massive_connection.py AAPL      # or any ticker
```

You should see the last close price, RSI(14), EMA(20), and EMA(50).

### 4. Run the backend (FastAPI) and frontend (React)

Open two terminals.

**Terminal 1 — backend (from the repo root, venv active):**

```bash
uvicorn api:app --reload --port 8000      # JSON API; docs at http://localhost:8000/docs
```

**Terminal 2 — frontend (needs Node.js installed):**

```bash
cd frontend
npm install          # first time only
npm run dev          # opens the React app at http://localhost:5173
```

Open **http://localhost:5173**. The React app calls the API (Vite proxies `/api`
to port 8000, so no CORS hassle). To view on your phone, run the frontend with
`npm run dev -- --host` and open the Network URL it prints (phone + computer on the
same Wi-Fi).

**Adding holdings:** use the **Add / update a holding** form in the app sidebar
(symbol, buy price, shares, status) — no need to hand-edit `config.json`.

The API routes: `GET /api/portfolio`, `GET /api/stock/{ticker}` (signals +
scorecard + fused stance + news + catalysts), `GET /api/config`,
`POST /api/stocks`, `PATCH /api/stocks/{ticker}` (e.g. mark sold),
`DELETE /api/stocks/{ticker}`.

You can also run the engine directly (for the scheduled job or a quick check):

```bash
python looper_engine.py          # checks EVERY stock -> data/portfolio.json
python looper_engine.py AVGO     # or just one stock
```

### 5. (Later) Schedule the daily run locally

Once stable, schedule `python looper_engine.py` to run each evening with cron or
macOS `launchd`. It writes the status file with no Claude/token cost, and the
dashboard simply displays the latest result.

---

## How Phase 1 signals work

The engine pulls daily price, RSI(14), EMA-20, EMA-50, and volume from Massive,
then scores three rule sets from the brief — each fires when **2 of 3** are true:

- **SELL** — RSI overbought and rolling over · price ≥ analyst target · price broke
  below EMA-20 after a sustained run-up.
- **RE-ENTRY** — RSI ≤ 35 · price sitting on support (EMA or round number) · volume
  dried up on the dip then spiked on a recovery day.
- **STOP-LOOP / HOLD** — clean steady uptrend · fundamental catalyst flagged ·
  price far above analyst target (possible new regime).

The headline respects your `position.state`: while `holding` it watches for SELL;
while in `cash` it watches for RE-ENTRY. A strong STOP-LOOP reading overrides SELL
so you don't sell a stock breaking into a new regime.

---

## How Phase 2 works (re-entry planner)

When you sell, flip `position.state` to `"cash"` and set `last_sell_price` to your
fill. The planner then tells you:

- **Reserve budget** — how much cash to set aside to buy back: your original
  position cost plus `reinvest_profit_pct` of the realized profit, and never less
  than the original cost (so each loop re-enters with at least as much capital).
- **Next entry zone** — the support levels below the current price (EMA-20, EMA-50,
  recent swing low, nearest round number), nearest first.
- **Sizing** — how many whole and fractional shares your reserve buys at each
  level. A lower re-entry price buys *more* shares than you sold — the loop
  compounding in action.

While you're still `holding`, it shows the same plan as a projection ("if you sell
now…") so you can see the payoff before acting. These are price targets, not a
trigger — a real re-entry still needs the hard RE-ENTRY signal.

---

## Git / version control

```bash
cd path/to/looper
git init
git add .
git commit -m "Phase 1: connection test + project scaffold"
```

Then create a **private** repo on GitHub named `looper` and link it:

```bash
git remote add origin https://github.com/<your-username>/looper.git
git branch -M main
git push -u origin main
```

The `.gitignore` excludes `.env`, virtual environments, and data files so no
secret or local data is ever pushed.

---

## Changelog

- **2026-06-04** — **Moved to FastAPI + React.** Retired the Streamlit app; the UI
  is now a React (Vite) app in `frontend/` that consumes the FastAPI JSON API —
  portfolio with sell/buy sections, per-stock detail (stance, scorecard, signals,
  re-entry plan, catalysts, news), and the add/remove-holding form. Backend and
  frontend run separately (`uvicorn api:app` + `npm run dev`).
- **2026-06-04** — **FastAPI layer + add-holding form.** New `api.py` exposes the
  engine as a JSON API (portfolio, per-stock signals/scorecard/stance, and
  add/patch/remove holdings) with CORS, so a React or other front-end can be added
  without changing the logic. The dashboard sidebar gained an "Add / update a
  holding" form (and a remove control) that writes to `config.json` — no more
  hand-editing. Engine gained `add_stock`/`update_stock`/`remove_stock`/`save_config`.
- **2026-06-04** — **Catalysts, splits, auto-refresh.** Detail page gained a
  "Catalysts & events" section: upcoming/recent stock splits (`/stocks/v1/splits`)
  and catalysts keyword-scanned from headlines (M&A, layoffs, splits, buybacks,
  guidance, launches). Added an optional sidebar auto-refresh (Off / 5 / 15 / 30 /
  60 min). First open still auto-pulls if data is missing or stale.
- **2026-06-04** — **More factors + one-command launch.** Scorecard gained PEG, FCF
  margin, multi-year margin consistency, share-count trend (buybacks vs dilution),
  and interest coverage. The dashboard now auto-runs the engine on first open if
  data is missing or stale, so `streamlit run app.py` is all that's needed. Analyst
  count links to the full analyst list; removed name references from the docs/code.
- **2026-06-04** — **Analyst consensus detail.** `analyst_target` is now explicitly
  the aggregated average; added `analyst_count`, `target_low`, `target_high`, and
  `analyst_rating` per stock, shown on the detail page ("$X average across N
  analysts · range $lo–$hi · rating") with a warning when price sits above the
  average or Street-high target. BRKR switched from the BofA bull-case $65 to the
  ~$49.54 13-analyst consensus.
- **2026-06-04** — **Public-repo prep + polish.** Real holdings moved out of the
  repo: `config.json` is now gitignored and a sanitized `config.example.json` is
  committed instead (copy it to `config.json` and add your own positions). Removed
  personal paths from docs. Fixed a Streamlit rendering bug where `$` in amounts
  was parsed as LaTeX math (now escaped). Added hover help to the Snapshot metrics.
  News section now shows an overall sentiment read, a one-line momentum summary,
  and top themes (all derived locally — no token cost). Set next-earnings dates.
- **2026-06-04** — **Phase 3c: fundamental scorecard** (`fundamentals.py`). A
  quality + value read of each business: valuation (P/E, P/S, P/B,
  P/FCF, EV/EBITDA), quality (ROE, ROA, gross & operating margins, FCF), health
  (debt/equity, current, quick) and growth (revenue & EPS YoY, from income
  statements). Every factor gets a status chip, a hover tooltip (meaning + typical
  range), and a % weight showing how much it moves the verdict. Produces a Quality
  verdict + a Valuation verdict, then fuses them with the timing signal into a PM
  stance (Accumulate / Hold / Trim / Reduce / Exit). The detail page now leads
  with the stance + two verdicts and the scorecard, with timing/re-entry below.
- **2026-06-04** — **Phase 3b: detail-page data**. The per-stock page now pulls
  live **financials** (`/stocks/financials/v1/ratios` — market cap, P/E, P/S, EPS,
  ROE, debt/equity, dividend yield, FCF) and **recent news with sentiment**
  (`/v2/reference/news`), both on the $199 plan. "Biggest recent daily moves"
  (derived from price) stand in as an earnings-reaction history; `next_earnings`
  is a manual per-stock field for now. AVGO target set to the ~$489 analyst
  consensus. Detail fetches are cached per session and degrade gracefully if a
  dataset isn't on the plan.
- **2026-06-04** — **Phase 3: multi-stock portfolio**. Config is now a `stocks`
  list (added AVGO alongside BRKR). `looper_engine.py` gained `run_all()` (writes
  `data/portfolio.json`) plus a per-stock `side` + `urgency` score and a one-line
  `top_reason`. Rebuilt `app.py` as a portfolio view: a SELL section (held stocks,
  most urgent first) and a BUY section (cash, closest to re-entry first), each row
  one line with a ▾ expander for the second line and an "Open ▸" button to a
  per-stock detail page. Detail page has the full signals + re-entry plan, with an
  earnings/news/financials section stubbed for Phase 3b. Fixed a null-target edge
  case (AVGO has no target set yet).
- **2026-06-04** — **Phase 2: re-entry planner** (`reentry_planner.py`). After a
  sell it computes the reserve budget (original cost + `reinvest_profit_pct` of
  profit, never below original cost), the next-swing entry zone from support /
  EMA / swing-low / round levels, and whole+fractional sizing at each level. Runs
  as a projection while holding; uses `last_sell_price` once in cash. Shown in the
  terminal and a new dashboard "Re-entry plan" section.
- **2026-06-04** — Added a symmetric **RE-ENTRY WATCH** (buy-side, only when
  `state` is `cash`): amber alert when RSI ≤ `rsi_watch_buy` (42), price is within
  `support_approach_pct` (5%) above EMA50, or any 1 hard re-entry condition is met.
  Added `ROADMAP.md` capturing the multi-stock dashboard vision.
- **2026-06-04** — Added a **WATCH tier** between HOLD and SELL. Amber alert that
  fires while holding when RSI ≥ `rsi_watch` (78), price is within
  `target_approach_pct` (3%) of the analyst target, or any 1 hard sell condition
  is met. Full SELL still requires 2 of 3 — WATCH never forces a sale, it's an
  early heads-up to set a sell limit or watch for an RSI rollover. On BRKR today
  this reads WATCH (RSI 83 extreme).
- **2026-06-03** — Phase 1 engine + dashboard: `looper_engine.py` computes SELL /
  RE-ENTRY / STOP-LOOP signals (2-of-3 rules) from Massive data and writes a status
  JSON; `app.py` Streamlit dashboard shows the signal banner, indicators, and
  position; `config.json` holds ticker/position/target/thresholds. Connection
  verified on BRKR (price $62.70, RSI 83).
- **2026-06-03** — Phase 1 scaffold: project structure, secure API-key setup,
  Massive connection test (price, RSI, EMA-20, EMA-50). No strategy logic yet.
