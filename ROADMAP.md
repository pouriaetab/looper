# LOOPER — Roadmap

Phase 1 (current) is a single-stock tracker. This file captures the agreed
direction for later phases so we build toward it deliberately.

## Phase 2 — Re-entry sizing & next-swing recommendation
- After a sell, recommend how much to reserve for re-entry (never less than the
  original cost; ideally original cost + a slice of the profit taken).
- Identify the next likely entry zone on the same stock (support, RSI, EMAs).
- Position sizing toward whole shares, fractional allowed.

## Phase 3 — Multi-stock dashboard  ✅ built (3a)
Status: portfolio view live — SELL/BUY sections ranked by urgency, one-line rows
with ▾ expander, click-through to a per-stock detail page. Stocks added manually
in config.json for now.

### Phase 3c — fundamental scorecard  ✅ built
- Two verdicts (Quality, Valuation) + fused PM stance, Buffett quality+value lens.
- Per-factor status chips, % weights, and hover tooltips.
- Still to add: PEG / explicit sector-relative thresholds, multi-year consistency
  (e.g. 5-yr ROE/margin stability), and insider/buyback signals.

### Phase 3b — detail page  ✅ mostly built
- ✅ key financials live (ratios endpoint) and ✅ recent news with sentiment.
- ✅ "biggest recent daily moves" derived from price as an earnings-reaction proxy.
- next earnings date: manual `next_earnings` field for now. Still to do: auto
  earnings calendar + true historical earnings-move size (needs the Benzinga
  earnings add-on, not on the current stocks plan) and an explicit sector read.

### Original vision (kept for reference)
The home screen for desktop **and** phone is a scannable list, not one stock:

- **One line per stock** (max two). Line 1 = the essentials: ticker, price,
  signal badge (SELL / WATCH / HOLD / RE-ENTRY), and the single most important
  reason. A click/expander reveals **line 2** = second-priority info.
- **Sell section on top, sorted by urgency** — the stock that most warrants
  selling first appears at the top (e.g. ranked by how many sell conditions are
  met, RSI extremity, and distance to target).
- **Buy / re-entry section below (or side-by-side)** — candidates closest to a
  re-entry, ranked the same way.
- **Click a stock → its own detail page** for deeper decisions, showing:
  - upcoming earnings date + historical earnings-move size (% / points)
  - likely move up/down context, prior reaction history
  - top financials, top news, and overall market / sector read
  - the full signal breakdown and price/indicator chart.

## Phase 4 — New candidate scanner (Branch 3)
Scan for new quality stocks fitting the LOOPER profile (history of 20%+ swings,
real revenue, analyst Buy/Strong Buy, accessible price, target sectors).

## Adding stocks — now vs later
- **Now:** stocks are added manually to `config.json` (ticker, entry, shares,
  target) when the trader says so.
- **Later option A:** scrape Robinhood for held stocks' buy price and current
  price to auto-populate the list (held off for now).
- **Later option B / if it becomes a product:** link directly to the brokerage to
  pull positions automatically.

## Later / maybe (not now)
- Broker integration (e.g. Robinhood) to execute buy/sell from the app — only
  considered if this grows into a real product. Until then LOOPER is signal-only;
  execution stays manual in Robinhood.

## Design principles
- Mobile-first, glanceable: decisions readable in seconds, detail on demand.
- Always show the *reason* for a signal, never just the label.
- The daily engine runs locally on a schedule (no token cost); the web app is
  only the viewer.
