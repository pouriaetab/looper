"""
LOOPER — Phase 1 signal engine (Branch 1: Core Loop Engine)
===========================================================
Single-stock tracker. Pulls price / RSI / EMA / volume from the Massive API and
evaluates the SELL, RE-ENTRY, and STOP-LOOP rule sets from the project brief
(each fires when 2 of 3 conditions are true).

Design: this file is self-contained and has NO Claude/AI dependency. Run it on a
schedule (cron / launchd) and it writes data/<TICKER>_status.json. The FastAPI
layer (api.py) and React frontend just read that, so the daily run is free and local.

Usage:
    python looper_engine.py            # uses config.json
    python looper_engine.py AAPL       # override ticker for a one-off check

The API key is read from the MASSIVE_API_KEY environment variable (see README).
"""

import os
import sys
import csv
import json
import threading
import datetime as dt
from collections import defaultdict, deque
from pathlib import Path

import requests

from reentry_planner import plan_reentry

BASE = "https://api.massive.com"
API_KEY = os.environ.get("MASSIVE_API_KEY")
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

# Append-only transaction ledger (the permanent dataset for later analysis).
LEDGER = DATA_DIR / "ledger.csv"
LEDGER_FIELDS = [
    "timestamp", "date", "action", "ticker", "shares", "price",
    "entry_price", "proceeds", "cost_basis", "realized_profit",
    "net_profit_taken", "reentry_reserve", "reserve_used", "shares_remaining", "note",
]

# Horizon presets — each bundles the bar timespan + EMA windows. Bigger = slower,
# longer-term signals (they only move when the multi-period trend actually shifts).
HORIZONS = {
    "swing":    {"timespan": "day",   "ema_short": 20, "ema_long": 50,
                 "label": "Swing (daily)",            "approx": "days–2 weeks"},
    "position": {"timespan": "day",   "ema_short": 50, "ema_long": 100,
                 "label": "Position (daily, longer)", "approx": "~2–4 weeks"},
    "weekly":   {"timespan": "week",  "ema_short": 20, "ema_long": 50,
                 "label": "Long-term (weekly)",       "approx": "months"},
    "monthly":  {"timespan": "month", "ema_short": 12, "ema_long": 24,
                 "label": "Very long-term (monthly)", "approx": "1–2+ years"},
}


def _append_ledger(row: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    is_new = not LEDGER.exists()
    with open(LEDGER, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in LEDGER_FIELDS})


def read_ledger() -> list:
    if not LEDGER.exists():
        return []
    with open(LEDGER, newline="") as f:
        return list(csv.DictReader(f))


def _write_ledger(rows: list) -> None:
    """Rewrite the whole ledger CSV from `rows` (list of dicts). Used by the
    editable 'master file' editor so a fix in the table updates the source of truth."""
    DATA_DIR.mkdir(exist_ok=True)
    with open(LEDGER, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in LEDGER_FIELDS})


def update_ledger_row(index: int, fields: dict) -> dict:
    """Edit one ledger row in place (the ledger is the master history: editing a
    value here corrects it everywhere the tally reads from). Only real ledger
    columns are writable; the timestamp is preserved. Blank/None clears a cell."""
    rows = read_ledger()
    if index < 0 or index >= len(rows):
        raise ValueError(f"Ledger row {index} does not exist.")
    editable = set(LEDGER_FIELDS) - {"timestamp"}
    row = rows[index]
    for key, val in fields.items():
        if key not in editable:
            continue
        row[key] = "" if val is None else val
    rows[index] = row
    _write_ledger(rows)
    return row


def delete_ledger_row(index: int) -> dict:
    """Remove one ledger row (e.g. a stray/duplicate entry)."""
    rows = read_ledger()
    if index < 0 or index >= len(rows):
        raise ValueError(f"Ledger row {index} does not exist.")
    removed = rows.pop(index)
    _write_ledger(rows)
    return removed


def _lnum(row, key):
    """Parse a ledger cell as float, or None if blank/missing."""
    v = row.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def paired_ledger():
    """Round-trip VIEW over the raw ledger: FIFO-match each ticker's sells against
    its buys so a buy and the sell that closed it appear as ONE row (buy date/price
    + sell date/price + realized + reserve). Rules:
      • Open (unsold) buys show with the sell side blank.
      • A legacy sell with no buy row (bought before the ledger existed) uses the
        sell's own entry_price as the buy side.
      • Each leg keeps its underlying ledger row index (buy_idx / sell_idx) so inline
        edits go straight back to the correct RAW row — the raw ledger stays the
        single source of truth (every buy and every sell is its own dated row).
    Trips are returned most-recent-first (by the closing sell date, else the buy date).
    """
    indexed = [dict(r, _idx=i) for i, r in enumerate(read_ledger())]
    by_ticker = defaultdict(list)
    for r in indexed:
        by_ticker[r.get("ticker", "")].append(r)

    def _trip(tkr, shares, buy, sell):
        buy_price = buy["price"] if buy else (_lnum(sell, "entry_price") if sell else None)
        cost = (_lnum(buy["row"], "cost_basis") if (buy and buy["whole"]) else
                (round(shares * buy_price, 4) if buy_price is not None else None))
        sell_price = _lnum(sell, "price") if sell else None
        proceeds = (_lnum(sell, "proceeds") if (sell and _lnum(sell, "proceeds") is not None)
                    else (round(shares * sell_price, 4) if sell_price is not None else None))
        realized = _lnum(sell, "realized_profit") if sell else None
        if realized is None and cost is not None and proceeds is not None:
            realized = round(proceeds - cost, 4)
        buy_whole = (buy is None) or buy["whole"]
        sell_whole = (sell is None) or (abs(shares - (_lnum(sell, "shares") or shares)) < 1e-9)
        return {
            "ticker": tkr,
            "shares": round(shares, 6),
            "buy_idx": buy["row"]["_idx"] if buy else None,
            "buy_date": buy["row"]["date"] if buy else None,
            "buy_price": round(buy_price, 4) if buy_price is not None else None,
            "sell_idx": sell["_idx"] if sell else None,
            "sell_date": sell["date"] if sell else None,
            "sell_price": round(sell_price, 4) if sell_price is not None else None,
            "cost_basis": cost,
            "proceeds": proceeds,
            "realized_profit": realized,
            "net_profit_taken": _lnum(sell, "net_profit_taken") if sell else None,
            "reentry_reserve": _lnum(sell, "reentry_reserve") if sell else None,
            "reserve_used": (buy["row"].get("reserve_used") or None) if buy else None,
            "open": sell is None,
            # only 1:1 whole-lot trips map cleanly back to single rows for inline edit
            "editable": buy_whole and sell_whole,
            "sort_key": (sell["timestamp"] if sell else buy["row"]["timestamp"] if buy else ""),
        }

    trips = []
    for tkr, rows in by_ticker.items():
        rows.sort(key=lambda r: (r.get("timestamp") or r.get("date") or ""))
        open_lots = deque()   # FIFO queue of open buy lots
        for r in rows:
            act = r.get("action")
            shares = _lnum(r, "shares") or 0.0
            if act in ("buy", "reentry"):
                open_lots.append({"row": r, "left": shares, "orig": shares})
            elif act == "sell":
                remaining = shares
                while remaining > 1e-9 and open_lots:
                    lot = open_lots[0]
                    take = min(lot["left"], remaining)
                    buy = {"row": lot["row"], "price": _lnum(lot["row"], "price"),
                           "whole": abs(take - lot["orig"]) < 1e-9}
                    trips.append(_trip(tkr, take, buy, r))
                    lot["left"] -= take
                    remaining -= take
                    if lot["left"] <= 1e-9:
                        open_lots.popleft()
                if remaining > 1e-9:                      # legacy sell, no buy row
                    trips.append(_trip(tkr, remaining, None, r))
        for lot in open_lots:                             # still-open positions
            buy = {"row": lot["row"], "price": _lnum(lot["row"], "price"),
                   "whole": abs(lot["left"] - lot["orig"]) < 1e-9}
            trips.append(_trip(tkr, lot["left"], buy, None))

    trips.sort(key=lambda t: t["sort_key"], reverse=True)
    for t in trips:
        t.pop("sort_key", None)
    return trips


def _now_parts(when=None):
    moment = dt.datetime.now() if not when else dt.datetime.fromisoformat(when)
    return moment.isoformat(timespec="seconds"), moment.strftime("%Y-%m-%d")


def _last_price(ticker: str):
    path = DATA_DIR / f"{ticker.upper()}_status.json"
    if not path.exists():
        return None
    try:
        return float(json.load(open(path)).get("price"))
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# API helpers
# --------------------------------------------------------------------------- #
def _get(path, params=None, timeout=20):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    resp = requests.get(BASE + path, headers=headers, params=params or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def fetch_daily_bars(ticker, days=None, timespan="day"):
    """OHLCV bars for the given timespan ('day' or 'week').
    Weekly bars give a slower, longer-term view (RSI/EMA span weeks–months)."""
    if days is None:
        days = {"week": 1100, "month": 4000}.get(timespan, 160)   # enough history per timespan
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    data = _get(
        f"/v2/aggs/ticker/{ticker}/range/1/{timespan}/{start}/{end}",
        {"adjusted": "true", "sort": "asc", "limit": 50000},
    )
    bars = data.get("results", []) or []
    # normalise to simple dicts
    return [
        {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "t": b["t"]}
        for b in bars
    ]


def fetch_rsi_series(ticker, window, limit=15, timespan="day"):
    data = _get(
        f"/v1/indicators/rsi/{ticker}",
        {"timespan": timespan, "window": window, "series_type": "close",
         "order": "desc", "limit": limit},
    )
    values = (data.get("results") or {}).get("values") or []
    return [v["value"] for v in values]  # newest first (empty if not enough history)


def fetch_ema(ticker, window, timespan="day"):
    data = _get(
        f"/v1/indicators/ema/{ticker}",
        {"timespan": timespan, "window": window, "series_type": "close",
         "order": "desc", "limit": 1},
    )
    values = (data.get("results") or {}).get("values") or []
    return values[0]["value"] if values else None   # None if not enough history


# --------------------------------------------------------------------------- #
# Phase 3b: detail-page data (news + financial ratios). Fetched on demand by the
# dashboard, not on every engine run, to keep API calls down.
# --------------------------------------------------------------------------- #
def fetch_news(ticker, limit=5):
    data = _get("/v2/reference/news",
                {"ticker": ticker, "limit": limit, "order": "desc",
                 "sort": "published_utc"})
    out = []
    for a in data.get("results", []) or []:
        sentiment = None
        for ins in a.get("insights", []) or []:
            if ins.get("ticker") == ticker:
                sentiment = ins.get("sentiment")
        out.append({
            "title": a.get("title"),
            "publisher": (a.get("publisher") or {}).get("name"),
            "published": (a.get("published_utc") or "")[:10],
            "url": a.get("article_url"),
            "sentiment": sentiment,
            "keywords": a.get("keywords") or [],
        })
    return out


def fetch_ratios(ticker):
    data = _get("/stocks/financials/v1/ratios", {"ticker": ticker, "limit": 1})
    res = data.get("results") or []
    return res[0] if res else None


def fetch_income_statements(ticker, timeframe="annual", limit=5):
    """Income statements, newest period first (for growth + margins)."""
    data = _get("/stocks/financials/v1/income-statements",
                {"tickers": ticker, "timeframe": timeframe,
                 "sort": "period_end.desc", "limit": limit})
    return data.get("results") or []


def fetch_splits(ticker, limit=5):
    """Stock split events, newest first (catches upcoming + recent splits)."""
    data = _get("/stocks/v1/splits",
                {"ticker": ticker, "sort": "execution_date.desc", "limit": limit})
    return data.get("results") or []


def fetch_detail(ticker):
    """Live financials + income statements + news for the detail page. Each piece is
    wrapped so one missing dataset (e.g. not on your plan) doesn't break the page."""
    detail = {"ratios": None, "income": [], "news": [], "splits": [], "errors": {}}
    try:
        detail["ratios"] = fetch_ratios(ticker)
    except Exception as e:        # noqa: BLE001
        detail["errors"]["ratios"] = str(e)
    try:
        detail["income"] = fetch_income_statements(ticker)
    except Exception as e:        # noqa: BLE001
        detail["errors"]["income"] = str(e)
    try:
        detail["news"] = fetch_news(ticker, limit=15)
    except Exception as e:        # noqa: BLE001
        detail["errors"]["news"] = str(e)
    try:
        detail["splits"] = fetch_splits(ticker)
    except Exception as e:        # noqa: BLE001
        detail["errors"]["splits"] = str(e)
    return detail


def biggest_daily_moves(bars, n=4):
    """Top day-over-day moves (a good proxy for past earnings reactions)."""
    moves = []
    for i in range(1, len(bars)):
        prev, cur = bars[i - 1]["c"], bars[i]["c"]
        if prev:
            moves.append({
                "date": dt.datetime.utcfromtimestamp(bars[i]["t"] / 1000).date().isoformat(),
                "pct": round((cur / prev - 1) * 100, 1),
                "points": round(cur - prev, 2),
            })
    return sorted(moves, key=lambda m: -abs(m["pct"]))[:n]


# --------------------------------------------------------------------------- #
# Signal logic — each returns (met: bool, reason: str)
# --------------------------------------------------------------------------- #
def _rsi_overbought_turning_down(rsi, th):
    # rsi is newest-first. Was it recently overbought, and is it now ticking down?
    recent = rsi[:5]
    peaked = max(recent) >= th["rsi_overbought"]
    turning = len(rsi) >= 2 and rsi[0] < rsi[1]
    met = peaked and turning
    return met, (
        f"RSI hit {max(recent):.0f} (>{th['rsi_overbought']}) and is turning down "
        f"({rsi[1]:.0f}→{rsi[0]:.0f})" if met
        else f"RSI {rsi[0]:.0f} — not overbought-and-rolling-over"
    )


def _price_at_or_above_target(price, target):
    if target is None:
        return False, "No analyst target set"
    met = price >= target
    return met, (
        f"Price ${price:.2f} ≥ analyst target ${target:.2f}" if met
        else f"Price ${price:.2f} below analyst target ${target:.2f}"
    )


def _dropped_below_ema_after_run(price, ema_s, bars, th):
    look = th["run_up_lookback_days"]
    had_run = len(bars) > look and (price / bars[-look]["c"] - 1) >= th["run_up_min_gain_pct"]
    below = price < ema_s
    met = had_run and below
    gain = (price / bars[-look]["c"] - 1) * 100 if len(bars) > look else 0
    return met, (
        f"Price ${price:.2f} dropped below EMA{th['ema_short']} ${ema_s:.2f} after a "
        f"{gain:.0f}% run-up" if met
        else f"Price ${price:.2f} vs EMA{th['ema_short']} ${ema_s:.2f} "
             f"({gain:+.0f}% over {look}d) — no post-run breakdown"
    )


def _rsi_oversold(rsi, th):
    met = rsi[0] <= th["rsi_oversold"]
    return met, (f"RSI {rsi[0]:.0f} ≤ {th['rsi_oversold']} (oversold)" if met
                 else f"RSI {rsi[0]:.0f} — not oversold")


def _found_support(price, ema_s, ema_l, th):
    p = th["support_proximity_pct"]
    near_ema_l = abs(price / ema_l - 1) <= p
    near_ema_s = abs(price / ema_s - 1) <= p
    round_level = round(price / 10) * 10
    near_round = round_level > 0 and abs(price / round_level - 1) <= p
    met = near_ema_l or near_ema_s or near_round
    where = []
    if near_ema_s: where.append(f"EMA{th['ema_short']} ${ema_s:.2f}")
    if near_ema_l: where.append(f"EMA{th['ema_long']} ${ema_l:.2f}")
    if near_round: where.append(f"round ${round_level:.0f}")
    return met, (f"Price ${price:.2f} sitting on support ({', '.join(where)})" if met
                 else f"Price ${price:.2f} not near a known support level")


def _volume_dry_then_spike(bars, th):
    w = th["volume_window_days"]
    if len(bars) < w + 1:
        return False, "Not enough history for volume analysis"
    avg_vol = sum(b["v"] for b in bars[-w-1:-1]) / w
    last = bars[-1]
    prev = bars[-2]
    down_then_up = prev["c"] < bars[-3]["c"] and last["c"] > prev["c"]
    spike = last["v"] >= 1.3 * avg_vol
    met = down_then_up and spike
    return met, (
        f"Volume dried up on the dip, then spiked {last['v']/avg_vol:.1f}x avg on a "
        f"recovery day" if met
        else f"Volume {last['v']/avg_vol:.1f}x avg — no dry-up-then-spike pattern"
    )


def _clean_uptrend(price, ema_s, ema_l, bars, th):
    golden = ema_s > ema_l and price > ema_s
    # "no sharp spikes" => modest average daily range over last 10 sessions
    recent = bars[-10:]
    avg_range = sum((b["h"] - b["l"]) / b["c"] for b in recent) / len(recent) if recent else 1
    smooth = avg_range < 0.04
    met = golden and smooth
    return met, (
        f"Clean uptrend: EMA{th['ema_short']} > EMA{th['ema_long']}, price above both, "
        f"avg daily range {avg_range*100:.1f}%" if met
        else f"Trend not clean/steady (golden={golden}, avg range {avg_range*100:.1f}%)"
    )


def _far_above_targets(price, target, th):
    if target is None:
        return False, "No analyst target set"
    met = price >= target * (1 + th["target_breakout_buffer_pct"])
    return met, (
        f"Price ${price:.2f} is >{th['target_breakout_buffer_pct']*100:.0f}% above "
        f"target ${target:.2f} — possible new regime" if met
        else f"Price ${price:.2f} not far above target ${target:.2f}")


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _resolve_horizon(th):
    """Resolve the horizon preset -> (timespan, thresholds with the right EMA windows).
    Falls back to the legacy 'timespan' key, then to swing."""
    name = th.get("horizon")
    if not name:
        name = "weekly" if th.get("timespan") == "week" else "swing"
    h = HORIZONS.get(name, HORIZONS["swing"])
    merged = {**th, "ema_short": h["ema_short"], "ema_long": h["ema_long"]}
    return name, h["timespan"], merged


def evaluate(ticker, cfg):
    target = cfg.get("analyst_target")
    horizon, tspan, th = _resolve_horizon(cfg["thresholds"])

    bars = fetch_daily_bars(ticker, timespan=tspan)
    if not bars:
        raise RuntimeError(f"No price data returned for {ticker}.")
    price = bars[-1]["c"]

    # Indicators may be unavailable for very new/short-history tickers. Fall back
    # gracefully so the position still shows a price and P/L instead of erroring.
    rsi = fetch_rsi_series(ticker, 14, timespan=tspan)
    ema_s = fetch_ema(ticker, th["ema_short"], timespan=tspan)
    ema_l = fetch_ema(ticker, th["ema_long"], timespan=tspan)
    data_limited = (len(bars) < 30) or (not rsi) or (ema_s is None) or (ema_l is None)
    if not rsi:
        rsi = [50.0]                       # neutral RSI when unavailable
    if ema_s is None:
        ema_s = price                      # treat price as its own short-term mean
    if ema_l is None:
        ema_l = ema_s

    sell = [
        _rsi_overbought_turning_down(rsi, th),
        _price_at_or_above_target(price, target),
        _dropped_below_ema_after_run(price, ema_s, bars, th),
    ]
    reentry = [
        _rsi_oversold(rsi, th),
        _found_support(price, ema_s, ema_l, th),
        _volume_dry_then_spike(bars, th),
    ]
    hold = [
        _clean_uptrend(price, ema_s, ema_l, bars, th),
        (bool(cfg.get("fundamental_catalyst")),
         "Fundamental catalyst flagged in config" if cfg.get("fundamental_catalyst")
         else "No fundamental catalyst flagged"),
        _far_above_targets(price, target, th),
    ]

    sell_n = sum(1 for m, _ in sell if m)
    reentry_n = sum(1 for m, _ in reentry if m)
    hold_n = sum(1 for m, _ in hold if m)

    state = cfg.get("position", {}).get("state", "holding")

    # WATCH tiers — early "get ready" heads-ups that sit between the neutral state
    # and a full SELL / RE-ENTRY. They never force a trade.
    sell_watch = []
    if rsi[0] >= th.get("rsi_watch", 78):
        sell_watch.append(f"RSI {rsi[0]:.0f} is extreme (≥{th.get('rsi_watch', 78)})")
    if target is not None and price >= target * (1 - th.get("target_approach_pct", 0.03)):
        sell_watch.append(f"Price ${price:.2f} is within "
                          f"{th.get('target_approach_pct', 0.03)*100:.0f}% of target ${target:.2f}")
    if sell_n >= 1:
        sell_watch.append("1 of 3 hard sell conditions already met")

    buy_watch = []
    if rsi[0] <= th.get("rsi_watch_buy", 42):
        buy_watch.append(f"RSI {rsi[0]:.0f} approaching oversold (≤{th.get('rsi_watch_buy', 42)})")
    sap = th.get("support_approach_pct", 0.05)
    if ema_l <= price <= ema_l * (1 + sap):
        buy_watch.append(f"Price ${price:.2f} approaching EMA{th['ema_long']} support ${ema_l:.2f}")
    if reentry_n >= 1:
        buy_watch.append("1 of 3 hard re-entry conditions already met")

    watch_reasons = sell_watch if state == "holding" else buy_watch if state == "cash" else []
    watch_on = len(watch_reasons) > 0

    # Decision: respect what the trader is currently doing.
    # Stop-loop/hold takes priority (don't sell a stock breaking into a new regime).
    if hold_n >= 2:
        headline, action = "HOLD", "Stop looping — let it run. Conditions suggest a new regime, not a swing."
    elif state == "holding" and sell_n >= 2:
        headline, action = "SELL SIGNAL", "2+ sell conditions met. Consider selling near this local high."
    elif state == "holding" and watch_on:
        headline, action = "WATCH", ("Getting toppy. Consider setting a sell limit near your "
                                     "target or waiting for RSI to roll over — not a full sell yet.")
    elif state == "cash" and reentry_n >= 2:
        headline, action = "RE-ENTRY ZONE", "2+ re-entry conditions met. Consider buying back in."
    elif state == "cash" and watch_on:
        headline, action = "RE-ENTRY WATCH", ("Approaching a re-entry. Get ready to buy back — watch for "
                                              "RSI to bottom or a support bounce. Not a buy yet.")
    elif state == "holding":
        headline, action = "HOLD", "Holding shares. No sell trigger yet — keep riding."
    else:
        headline, action = "WAIT", "Holding cash. No re-entry trigger yet — keep waiting."

    # Side + urgency score for ranking on the portfolio page, plus a one-line
    # "top reason" for the collapsed row.
    met_sell = [r for m, r in sell if m]
    met_re = [r for m, r in reentry if m]
    met_hold = [r for m, r in hold if m]
    if state == "holding":
        side = "sell"
        urgency = round(sell_n * 100 + max(rsi[0] - th["rsi_overbought"], 0) * 2 + len(sell_watch) * 10, 1)
        top_reason = (met_sell[0] if met_sell else
                      sell_watch[0] if sell_watch else
                      "No sell trigger — keep riding")
    else:
        side = "buy"
        urgency = round(reentry_n * 100 + max(th["rsi_oversold"] - rsi[0], 0) * 2 + len(buy_watch) * 10, 1)
        top_reason = (met_re[0] if met_re else
                      buy_watch[0] if buy_watch else
                      "No re-entry trigger — keep waiting")
    if hold_n >= 2 and met_hold:
        top_reason = met_hold[0]

    return {
        "ticker": ticker,
        "side": side,
        "urgency": urgency,
        "top_reason": top_reason,
        "as_of": dt.datetime.now().isoformat(timespec="seconds"),
        "last_bar_date": dt.datetime.utcfromtimestamp(bars[-1]["t"] / 1000).date().isoformat(),
        "price": round(price, 2),
        "rsi": round(rsi[0], 2),
        "ema_short": round(ema_s, 2),
        "ema_long": round(ema_l, 2),
        "volume": bars[-1]["v"],
        "position": cfg.get("position", {}),
        "analyst_target": target,
        "analyst_count": cfg.get("analyst_count"),
        "target_low": cfg.get("target_low"),
        "target_high": cfg.get("target_high"),
        "analyst_rating": cfg.get("analyst_rating"),
        "analyst_source_url": cfg.get("analyst_source_url"),
        "next_earnings": cfg.get("next_earnings"),
        "timespan": tspan,
        "horizon": horizon,
        "data_limited": data_limited,
        "last_move_pct": round((price / bars[-2]["c"] - 1) * 100, 2) if len(bars) >= 2 and bars[-2]["c"] else None,
        "big_moves": biggest_daily_moves(bars),
        "headline": headline,
        "action": action,
        "watch": {"on": watch_on, "reasons": watch_reasons},
        "reentry_plan": plan_reentry(price, bars, ema_s, ema_l, rsi[0], cfg, state),
        "counts": {"sell": sell_n, "reentry": reentry_n, "hold": hold_n},
        "signals": {
            "sell": [{"met": m, "reason": r} for m, r in sell],
            "reentry": [{"met": m, "reason": r} for m, r in reentry],
            "hold": [{"met": m, "reason": r} for m, r in hold],
        },
    }


def load_config():
    with open(ROOT / "config.json") as f:
        cfg = json.load(f)
    # Backward compatibility: wrap an old single-stock config into the list form.
    if "stocks" not in cfg:
        cfg["stocks"] = [{
            "ticker": cfg.get("ticker"),
            "position": cfg.get("position", {}),
            "analyst_target": cfg.get("analyst_target"),
            "fundamental_catalyst": cfg.get("fundamental_catalyst", False),
        }]
    return cfg


def save_config(cfg):
    with open(ROOT / "config.json", "w") as f:
        json.dump(cfg, f, indent=2)


def add_stock(ticker, entry_price, shares=1, state="holding",
              analyst_target=None, last_sell_price=None, when=None,
              from_reserve=False, **extra):
    """Add or replace a holding in config.json (used by the dashboard form + API).

    `when` is an optional ISO date/datetime for the ledger entry; defaults to now.
    """
    cfg = load_config()
    ticker = ticker.strip().upper()
    if not ticker:
        raise ValueError("Ticker is required.")
    stock = {
        "ticker": ticker,
        "position": {"state": state, "entry_price": float(entry_price),
                     "shares": float(shares), "last_sell_price": last_sell_price},
        "analyst_target": analyst_target,
        "fundamental_catalyst": False,
        "next_earnings": None,
    }
    stock.update({k: v for k, v in extra.items() if v is not None})

    prior = next((s for s in cfg.get("stocks", []) if s["ticker"].upper() == ticker), None)
    prior_state = (prior or {}).get("position", {}).get("state")
    action, note = "buy", ""

    # Marking an existing HOLDING as "cash" via the form means you SOLD it — record a
    # real sale (realized P/L + reserve) at the entered price, not a buy.
    if prior is not None and prior_state == "holding" and state == "cash":
        held = float(prior.get("position", {}).get("shares", 0) or 0)
        if held > 0:
            return sell_stock(ticker, held, float(entry_price), when=when)

    if prior is not None and prior_state == "holding" and state == "holding":
        # Buying MORE of a stock you already hold -> blend into one position at the
        # weighted-average cost; sum the shares. Every individual buy stays in the
        # ledger with its own date/price, so the history is never lost.
        ppos = prior.get("position", {})
        old_sh = float(ppos.get("shares", 0) or 0)
        old_entry = float(ppos.get("entry_price", 0) or 0)
        new_sh = old_sh + float(shares)
        avg_entry = ((old_sh * old_entry + float(shares) * float(entry_price)) / new_sh
                     if new_sh else float(entry_price))
        stock["position"]["shares"] = round(new_sh, 6)
        stock["position"]["entry_price"] = round(avg_entry, 6)
        # Keep the OLDEST acquired date as the position's "held since".
        dates = [d for d in (prior.get("acquired_date"), stock.get("acquired_date")) if d]
        if dates:
            stock["acquired_date"] = min(dates)
        note = f"added {shares} @ {entry_price} to existing {old_sh} (avg cost {avg_entry:.4f})"
    elif prior_state == "cash":
        action = "reentry"
        note = "re-entry after sell"

    cfg["stocks"] = [s for s in cfg.get("stocks", []) if s["ticker"].upper() != ticker] + [stock]
    save_config(cfg)

    cost_basis = round(float(shares) * float(entry_price), 4)
    # A re-entry (buying back what you sold) is funded from the reserve by definition;
    # any other buy draws from the reserve only if you flag it (from_reserve).
    drew_from_reserve = bool(from_reserve) or action == "reentry"
    reserve_used = cost_basis if drew_from_reserve else ""
    if drew_from_reserve and not note:
        note = "funded from re-entry reserve"

    ts, day = _now_parts(when)
    _append_ledger({
        "timestamp": ts, "date": day, "action": action, "ticker": ticker,
        "shares": float(shares), "price": float(entry_price), "entry_price": float(entry_price),
        "cost_basis": cost_basis,
        "reserve_used": reserve_used,
        "shares_remaining": stock["position"]["shares"],
        "note": note,
    })
    return stock


def sell_stock(ticker, shares, price, when=None, reinvest_pct=None):
    """Record a sale: log it to the ledger, reduce shares, and apply the
    reserve/profit split. A full sell removes the stock from the active list;
    a partial sell keeps it (with fewer shares) in the holdings/sell section.
    The ledger always keeps the complete history regardless.
    """
    cfg = load_config()
    ticker = ticker.strip().upper()
    stock = next((s for s in cfg.get("stocks", []) if s["ticker"].upper() == ticker), None)
    if stock is None:
        raise ValueError(f"{ticker} not found in config.")

    pos = stock.get("position", {})
    held = float(pos.get("shares", 0) or 0)
    entry = float(pos.get("entry_price", 0) or 0)
    shares = float(shares)
    price = float(price)
    if shares <= 0:
        raise ValueError("Shares sold must be greater than zero.")
    if shares > held + 1e-9:
        raise ValueError(f"Cannot sell {shares} shares; only {held} held.")

    reinvest = cfg.get("reinvest_profit_pct", 0.5) if reinvest_pct is None else float(reinvest_pct)
    proceeds = shares * price
    cost_basis = shares * entry
    realized = proceeds - cost_basis
    gain = max(realized, 0.0)
    # Reserve = original cost of the sold shares + a slice of the profit (never < cost).
    reserve = cost_basis + reinvest * gain
    net_taken = realized - reinvest * gain  # for a loss this equals the (negative) realized
    remaining = held - shares

    ts, day = _now_parts(when)
    _append_ledger({
        "timestamp": ts, "date": day, "action": "sell", "ticker": ticker,
        "shares": shares, "price": price, "entry_price": entry,
        "proceeds": round(proceeds, 4), "cost_basis": round(cost_basis, 4),
        "realized_profit": round(realized, 4), "net_profit_taken": round(net_taken, 4),
        "reentry_reserve": round(reserve, 4), "shares_remaining": round(max(remaining, 0.0), 6),
    })

    pos["last_sell_price"] = price
    closed = remaining <= 1e-9
    if closed:
        # Don't delete the stock — flip it to 'cash' so LOOPER keeps watching it for
        # a re-entry (it moves to the Buy section). Keep entry_price + shares as the
        # reference for re-entry sizing. To stop tracking it entirely, remove_stock().
        pos["state"] = "cash"
    else:
        pos["shares"] = remaining
    stock["position"] = pos
    save_config(cfg)

    return {
        "ticker": ticker,
        "removed": False,
        "closed": closed,                       # fully sold -> now in re-entry watch
        "shares_remaining": max(remaining, 0.0),
        "realized_profit": round(realized, 4),
        "net_profit_taken": round(net_taken, 4),
        "reentry_reserve": round(reserve, 4),
    }


def portfolio_tally():
    """Live totals for the dashboard: holdings, realized vs unrealized profit,
    net profit taken, and re-entry reserve. Unrealized uses the last computed
    price per ticker (data/<TICKER>_status.json) so it needs no network call.
    """
    cfg = load_config()
    stocks = cfg.get("stocks", [])
    reinvest = cfg.get("reinvest_profit_pct", 0.5)

    holdings = []
    total_shares = total_cost = current_value = priced_cost = 0.0
    priced = 0
    for s in stocks:
        pos = s.get("position", {})
        shares = float(pos.get("shares", 0) or 0)
        if shares <= 0 or pos.get("state") == "cash":
            continue
        entry = float(pos.get("entry_price", 0) or 0)
        last = _last_price(s["ticker"])
        cost = shares * entry
        total_shares += shares
        total_cost += cost
        unreal = None
        if last is not None:
            current_value += shares * last
            priced_cost += cost
            unreal = round((last - entry) * shares, 2)
            priced += 1
        holdings.append({
            "ticker": s["ticker"], "shares": shares, "entry_price": entry,
            "last_price": last, "cost_basis": round(cost, 2), "unrealized": unreal,
        })

    ledger = read_ledger()

    def _sum(field, actions=("sell",)):
        total = 0.0
        for row in ledger:
            if row.get("action") in actions and row.get(field):
                try:
                    total += float(row[field])
                except ValueError:
                    pass
        return round(total, 2)

    # Re-entry reserve is a running pool: sales ADD to it, reserve-funded buys
    # DRAW from it. Remaining = added − used (can't go below 0).
    reserve_added = _sum("reentry_reserve")
    reserve_used = _sum("reserve_used", actions=("buy", "reentry", "reserve_use"))
    reserve_remaining = round(max(reserve_added - reserve_used, 0.0), 2)

    return {
        "positions": len(holdings),
        "total_shares": round(total_shares, 6),
        "total_cost_basis": round(total_cost, 2),
        "current_value": round(current_value, 2),
        "unrealized_profit": round(current_value - priced_cost, 2),
        "unrealized_priced": priced,
        "unrealized_total": len(holdings),
        "realized_profit": _sum("realized_profit"),
        "net_profit_taken": _sum("net_profit_taken"),
        "reentry_reserve": reserve_remaining,
        "reserve_added": reserve_added,
        "reserve_used": reserve_used,
        "reinvest_profit_pct": reinvest,
        "holdings": holdings,
    }


def update_stock(ticker, **fields):
    """Patch an existing holding (e.g. flip state to 'cash' + set last_sell_price)."""
    cfg = load_config()
    ticker = ticker.strip().upper()
    found = None
    for s in cfg.get("stocks", []):
        if s["ticker"].upper() == ticker:
            found = s
            pos = s.setdefault("position", {})
            for k in ("state", "entry_price", "shares", "last_sell_price"):
                if fields.get(k) is not None:
                    pos[k] = fields[k]
            for k in ("analyst_target", "next_earnings", "fundamental_catalyst",
                      "analyst_count", "target_low", "target_high", "analyst_rating",
                      "analyst_source_url", "acquired_date"):
                if k in fields:
                    s[k] = fields[k]
    if found is None:
        raise ValueError(f"{ticker} not found in config.")
    save_config(cfg)
    return found


def remove_stock(ticker):
    cfg = load_config()
    ticker = ticker.strip().upper()
    cfg["stocks"] = [s for s in cfg.get("stocks", []) if s["ticker"].upper() != ticker]
    save_config(cfg)
    return cfg["stocks"]


def record_reserve_use(ticker, amount, when=None):
    """Manually record that `amount` of a buy was funded from the re-entry reserve
    (for old/forgotten entries). Draws the reserve down without changing shares."""
    ticker = ticker.strip().upper()
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")
    ts, day = _now_parts(when)
    _append_ledger({
        "timestamp": ts, "date": day, "action": "reserve_use", "ticker": ticker,
        "reserve_used": round(amount, 4), "note": "manual: funded from re-entry reserve",
    })
    return {"ticker": ticker, "reserve_used": round(amount, 4)}


def _stock_cfg(cfg, stock):
    """Merge one stock's fields with the global thresholds/reinvest settings so the
    existing evaluate()/plan_reentry() code can consume it unchanged."""
    return {
        "ticker": stock["ticker"],
        "position": stock.get("position", {}),
        "analyst_target": stock.get("analyst_target"),
        "analyst_count": stock.get("analyst_count"),
        "target_low": stock.get("target_low"),
        "target_high": stock.get("target_high"),
        "analyst_rating": stock.get("analyst_rating"),
        "analyst_source_url": stock.get("analyst_source_url"),
        "fundamental_catalyst": stock.get("fundamental_catalyst", False),
        "next_earnings": stock.get("next_earnings"),
        "reinvest_profit_pct": cfg.get("reinvest_profit_pct", 0.5),
        "thresholds": cfg["thresholds"],
    }


def _save(result):
    DATA_DIR.mkdir(exist_ok=True)
    with open(DATA_DIR / f"{result['ticker']}_status.json", "w") as f:
        json.dump(result, f, indent=2)


def run(ticker=None, save=True):
    """Evaluate a single stock (first in the list if no ticker given)."""
    if not API_KEY:
        raise SystemExit("MASSIVE_API_KEY is not set. Export it first (see README).")
    cfg = load_config()
    stocks = cfg["stocks"]
    if ticker:
        stock = next((s for s in stocks if s["ticker"].upper() == ticker.upper()), None)
        if stock is None:
            raise SystemExit(f"{ticker} is not in config.json (stocks: "
                             f"{', '.join(s['ticker'] for s in stocks)}).")
    else:
        stock = stocks[0]
    result = evaluate(stock["ticker"].upper(), _stock_cfg(cfg, stock))
    if save:
        _save(result)
    return result


def build_alert(result, news):
    """Concise, actionable alert for a stock box: flags a possible M&A/deal (or other
    catalyst) and/or a big single-bar move, with a one-line summary + suggested action.
    Returns None when nothing notable is happening."""
    import fundamentals
    move = result.get("last_move_pct")
    state = result.get("position", {}).get("state")
    cats = fundamentals.catalysts(news) or []
    deal = next((c for c in cats if str(c.get("type", "")).startswith("M&A")), None)
    big = move is not None and abs(move) >= 6.0

    if not deal and not big and not cats:
        return None

    if deal:
        title, headline, level = "Possible deal / M&A", deal.get("headline", ""), "event"
    elif cats:
        title, headline, level = cats[0].get("type", "News"), cats[0].get("headline", ""), "event"
    else:
        digest = fundamentals.news_digest(news, result["price"], result["ema_short"],
                                          result["ema_long"], result["rsi"]) or {}
        title, headline, level = f"{move:+.1f}% move", digest.get("momentum", ""), "move"

    if deal and state == "holding":
        suggestion = "M&A often pops the stock — consider selling into the deal to lock the gain."
    elif big and move > 0 and state == "holding":
        suggestion = "Big up-move — review taking profit."
    elif big and move < 0 and state == "holding":
        suggestion = "Big drop — hold if the thesis holds; add only if quality is intact."
    elif state == "cash" and big and move < 0:
        suggestion = "Big drop while in cash — possible re-entry; check the scorecard."
    else:
        suggestion = "Open the detail page before acting."

    return {"level": level, "title": title, "headline": headline,
            "move_pct": move, "suggestion": suggestion}


def run_all(save=True):
    """Evaluate every stock in config.json. Writes per-stock files plus a combined
    data/portfolio.json. Errors on one stock don't stop the others."""
    if not API_KEY:
        raise RuntimeError("MASSIVE_API_KEY is not set. Export it first (see README).")
    cfg = load_config()
    results, errors = [], []
    for stock in cfg["stocks"]:
        tkr = stock["ticker"].upper()
        try:
            r = evaluate(tkr, _stock_cfg(cfg, stock))
            try:
                r["alert"] = build_alert(r, fetch_news(tkr, limit=8))
            except Exception:        # noqa: BLE001 - alerts are best-effort
                r["alert"] = None
            results.append(r)
            if save:
                _save(r)
        except Exception as e:        # noqa: BLE001 - keep the portfolio resilient
            errors.append({"ticker": tkr, "error": str(e)})
    if save:
        DATA_DIR.mkdir(exist_ok=True)
        with open(DATA_DIR / "portfolio.json", "w") as f:
            json.dump({"as_of": dt.datetime.now().isoformat(timespec="seconds"),
                       "results": results, "errors": errors}, f, indent=2)
    return results, errors


def _print(result):
    print(f"\n{result['ticker']}  —  {result['headline']}")
    print(f"  {result['action']}")
    print(f"  As of {result['as_of']} (last bar {result['last_bar_date']})")
    print(f"  Price ${result['price']:.2f} | RSI {result['rsi']:.1f} | "
          f"EMA20 ${result['ema_short']:.2f} | EMA50 ${result['ema_long']:.2f}")
    if result.get("watch", {}).get("on"):
        print("\n  WATCH flags:")
        for r in result["watch"]["reasons"]:
            print(f"    ⚠ {r}")
    for group, label in (("sell", "SELL"), ("reentry", "RE-ENTRY"), ("hold", "STOP-LOOP/HOLD")):
        n = result["counts"][group]
        print(f"\n  {label} signals ({n}/3):")
        for s in result["signals"][group]:
            mark = "✓" if s["met"] else "·"
            print(f"    {mark} {s['reason']}")

    p = result.get("reentry_plan")
    if p:
        print(f"\n  RE-ENTRY PLAN  [{p['basis']}]")
        print(f"    Sell ${p['sell_price']:.2f} × {p['shares_sold']} = "
              f"${p['proceeds']:.2f} proceeds | cost ${p['original_cost']:.2f} | "
              f"profit ${p['profit']:+.2f}")
        print(f"    Reserve to buy back: ${p['reserve_budget']:.2f} "
              f"(original cost + {p['reinvest_profit_pct']*100:.0f}% of profit)")
        if p["primary_entry"]:
            print(f"    Next entry zone (nearest support first):")
            for s in p["sizing"]:
                print(f"      {s['level']:<16} ~${s['price']:.2f}  →  "
                      f"{s['whole_shares']} whole / {s['total_shares']:.2f} total "
                      f"shares ({s['vs_original']:+.2f} vs sold)")
        print(f"    {p['note']}")
    print()


def evaluate_watch(ticker):
    """Evaluate a watchlist symbol you don't own. Treats it as 'cash' (no position)
    so it gets the same live HOLD / RE-ENTRY WATCH / RE-ENTRY signals the engine
    gives owned positions and scanner hits."""
    cfg = load_config()
    scfg = {
        "ticker": ticker.upper(),
        "position": {"state": "cash", "entry_price": None, "shares": 0, "last_sell_price": None},
        "analyst_target": None,
        "fundamental_catalyst": False,
        "next_earnings": None,
        "reinvest_profit_pct": cfg.get("reinvest_profit_pct", 0.5),
        "thresholds": cfg["thresholds"],
    }
    return evaluate(ticker.upper(), scfg)


def fetch_movers(direction):
    """Top ~20 daily gainers or losers across the whole US market (min volume 10k).
    direction: 'gainers' or 'losers'."""
    data = _get(f"/v2/snapshot/locale/us/markets/stocks/{direction}", {})
    return data.get("tickers", []) or []


def scan_candidates(tickers=None, limit=20):
    """Daily-movers swing scanner (days–1 week focus). Instead of a fixed list, it
    scans the WHOLE market's biggest movers each day: the biggest DROPS are buy-low /
    oversold candidates, the biggest POPS are overbought / take-profit candidates —
    each confirmed with RSI. Fresh names every day."""
    if not API_KEY:
        raise RuntimeError("MASSIVE_API_KEY is not set.")

    MIN_PRICE = 5.0      # skip penny/micro names
    PER_SIDE = 12        # how many of each side to RSI-confirm
    out = []

    for direction, side in (("losers", "buy"), ("gainers", "sell")):
        try:
            movers = fetch_movers(direction)
        except Exception:        # noqa: BLE001
            movers = []
        rows = []
        for m in movers:
            day = m.get("day") or {}
            prev = m.get("prevDay") or {}
            price = day.get("c") or prev.get("c")
            chg = m.get("todaysChangePerc")
            if not price or price < MIN_PRICE or chg is None:
                continue
            rows.append((abs(chg), m.get("ticker"), price, chg))
        rows.sort(reverse=True)                      # biggest movers first

        for _, tkr, price, chg in rows[:PER_SIDE]:
            if not tkr:
                continue
            try:
                rsi_data = fetch_rsi_series(tkr, 14, limit=1, timespan="day")
                rsi = rsi_data[0] if rsi_data else None
            except Exception:        # noqa: BLE001
                rsi = None
            if side == "buy":
                category = "oversold" if (rsi is not None and rsi <= 40) else "pullback (buy-low)"
            else:
                category = "overbought" if (rsi is not None and rsi >= 65) else "extended (take-profit)"
            out.append({
                "ticker": tkr,
                "price": round(price, 2),
                "rsi": round(rsi, 1) if rsi is not None else None,
                "change_pct": round(chg, 1),
                "category": category,
                "side": side,
                "urgency": round(min(abs(chg) / 12.0, 1.0), 2),
                "last_updated": dt.datetime.now().isoformat(timespec="seconds"),
            })

    out.sort(key=lambda x: -x["urgency"])            # biggest movers on top
    return out[:limit] if limit else out


# =========================================================================== #
# Deep Opportunity Scan — whole-market snapshot + deep analysis + theme momentum.
# Runs in a background thread with live progress (see _SCAN / start_scan).
# =========================================================================== #

# Curated theme baskets — representative liquid names per theme. Momentum is
# measured from the daily snapshot, so we can flag which themes are heating up
# (like quantum/semis did) or cooling (like some robotics names) without extra calls.
THEMES = {
    "AI / datacenter": ["NVDA", "AVGO", "AMD", "SMCI", "DELL", "ANET", "VRT", "MRVL", "MU", "CRWV"],
    "Semiconductors": ["NVDA", "AMD", "AVGO", "MU", "TSM", "ASML", "LRCX", "KLAC", "AMAT", "QCOM", "INTC", "ARM"],
    "Quantum computing": ["IONQ", "RGTI", "QBTS", "QUBT", "ARQQ", "LAES"],
    "Robotics / automation": ["ISRG", "ROK", "TER", "PATH", "SERV", "RR", "ABB", "OMCL"],
    "Nuclear / uranium": ["CCJ", "UEC", "SMR", "OKLO", "LEU", "NNE", "BWXT", "VST", "CEG"],
    "Cybersecurity": ["PANW", "CRWD", "ZS", "FTNT", "S", "OKTA", "NET"],
    "EV / batteries": ["TSLA", "RIVN", "LCID", "QS", "ALB", "LI", "NIO"],
    "Space / defense": ["RKLB", "LMT", "RTX", "LHX", "ASTS", "PL", "LUNR"],
    "Biotech": ["MRNA", "VRTX", "REGN", "CRSP", "NTLA", "BEAM"],
    "Crypto-linked": ["COIN", "MARA", "RIOT", "CLSK", "MSTR", "HOOD"],
}

_SCAN = {
    "running": False, "stage": "idle", "progress": 0, "total": 0,
    "started": None, "finished": None, "error": None,
    "scanned_universe": 0, "results": None, "themes": None,
}
_SCAN_LOCK = threading.Lock()


# Common leveraged / inverse ETF tickers to exclude outright (backstop; the ticker
# 'type' check below catches the rest). We want the real underlying stock, not its
# 2x/3x or single-stock leveraged ETF wrappers.
LEVERAGED_ETFS = {
    "TQQQ", "SQQQ", "SOXL", "SOXS", "TNA", "TZA", "UPRO", "SPXU", "SPXL", "SPXS",
    "UDOW", "SDOW", "TMF", "TMV", "LABU", "LABD", "FAS", "FAZ", "YINN", "YANG",
    "NVDL", "NVDU", "NVDS", "NVDQ", "TSLL", "TSLQ", "TSLS", "TSLT", "CONL", "MSTX",
    "MSTU", "MSTZ", "AMDL", "AMUU", "GGLL", "AAPU", "AAPD", "METU", "AMZU", "PLTU",
    "CRWL", "CWVX", "CRWG", "BITX", "ETHU", "USD", "SSO", "QLD", "DDM", "SVXY", "UVXY",
}
# Keep only real equities (common stock / ADRs); drop ETFs, ETNs, funds.
_COMMON_TYPES = {"CS", "ADRC", "ADR", "ADRP"}

# Popular / widely-recognized names. These rarely have the day's *biggest* % move,
# so the "what's moving" ranking almost never surfaces them — yet these are the
# names you actually want a read on. We ALWAYS deep-analyze any of these that are
# in the snapshot (bypassing the volume/liquidity floor) and put them in their own
# "Popular names" section so you see NVDA, GOOGL, COIN, RKLB, etc. every scan.
POPULAR = {
    "NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "TSLA", "AVGO", "AMD",
    "NFLX", "COIN", "SHOP", "AFRM", "SNDK", "MU", "RKLB", "ASTS", "PYPL", "NOW",
    "PLTR", "HOOD", "SOFI", "CRWV", "NBIS", "SMCI", "ARM", "TSM", "QCOM", "INTC",
    "MRVL", "MSTR", "UBER", "ABNB", "DIS", "BA", "F", "SQ", "XYZ", "DKNG", "RBLX",
    "SNAP", "PINS", "ROKU", "CVNA", "DELL", "CRM", "ORCL", "ADBE", "BABA", "RIVN",
    "V", "MA", "JPM", "WMT", "COST", "GME", "LLY", "NKE", "OKLO", "IONQ", "RGTI",
}


def _classify_bucket(rsi, chg, vsurge):
    if rsi is not None and rsi <= 40 and chg < 0:
        return "buy-low"          # oversold pullback — potential entry
    if rsi is not None and rsi >= 68 and chg > 0:
        return "overbought"       # extended — take profit / don't chase
    if chg > 0 and vsurge >= 1.5:
        return "momentum"         # breaking out on volume — hot name
    return "watch"


def _deep_row(sym, price, chg, vsurge, popular=False):
    """Pull RSI + EMAs for one symbol and classify it into an opportunity bucket."""
    try:
        rsi_series = fetch_rsi_series(sym, 14, limit=1, timespan="day")
        rsi = rsi_series[0] if rsi_series else None
        ema20 = fetch_ema(sym, 20, timespan="day")
        ema50 = fetch_ema(sym, 50, timespan="day")
    except Exception:        # noqa: BLE001
        rsi = ema20 = ema50 = None
    chg = chg if chg is not None else 0.0
    bucket = _classify_bucket(rsi, chg, vsurge)
    uptrend = (ema20 is not None and ema50 is not None and ema20 > ema50)
    interest = abs(chg) * (1 + min(vsurge, 5) / 5)
    return {
        "ticker": sym, "price": round(price, 2), "change_pct": round(chg, 1),
        "rsi": round(rsi, 1) if rsi is not None else None,
        "vol_surge": vsurge, "bucket": bucket, "uptrend": uptrend,
        "score": round(interest, 1), "popular": popular,
    }


def fetch_ticker_type(sym):
    """The security type (CS = common stock, ETF, ADRC, …) from ticker reference."""
    try:
        data = _get(f"/v3/reference/tickers/{sym}", {})
        return (data.get("results") or {}).get("type")
    except Exception:        # noqa: BLE001
        return None


def fetch_quotes(tickers):
    """FAST price + today's %change for a specific set of tickers in ONE call.
    Powers the live refresh of the Sell/Buy boxes without re-running the full
    indicator evaluation (which is the slow part). Returns {SYM: {price, change_pct}}."""
    syms = sorted({t.strip().upper() for t in tickers if t and t.strip()})
    if not syms:
        return {}
    data = _get("/v2/snapshot/locale/us/markets/stocks/tickers",
                {"tickers": ",".join(syms)}, timeout=15)
    out = {}
    for t in data.get("tickers", []) or []:
        sym = t.get("ticker")
        day = t.get("day") or {}
        prev = t.get("prevDay") or {}
        price = day.get("c") or prev.get("c")
        chg = t.get("todaysChangePerc")
        if chg is None and price and prev.get("c"):
            chg = (price / prev["c"] - 1) * 100
        if sym and price:
            out[sym] = {"price": round(price, 2),
                        "change_pct": round(chg, 2) if chg is not None else None}
    return out


def fetch_full_snapshot():
    """One call: every US ticker's latest daily bar (price, %chg, volume).
    Uses a long timeout — the response covers 10,000+ tickers."""
    data = _get("/v2/snapshot/locale/us/markets/stocks/tickers", {}, timeout=60)
    out = {}
    for t in data.get("tickers", []) or []:
        sym = t.get("ticker")
        day = t.get("day") or {}
        prev = t.get("prevDay") or {}
        # Off-hours the day bar can be empty — fall back to the previous day.
        price = day.get("c") or prev.get("c")
        vol = day.get("v") or 0
        prev_vol = prev.get("v") or 0
        chg = t.get("todaysChangePerc")
        if chg is None and price and prev.get("c"):
            chg = (price / prev["c"] - 1) * 100
        if not sym or not price:
            continue
        out[sym] = {"price": price, "chg": chg, "vol": vol, "prev_vol": prev_vol}
    return out


def theme_momentum(snap):
    """Average daily move per theme basket → which sectors are hot / cooling today."""
    themes = []
    for name, syms in THEMES.items():
        rows = [snap[s] for s in syms if s in snap and snap[s].get("chg") is not None]
        if not rows:
            continue
        avg = sum(r["chg"] for r in rows) / len(rows)
        up = sum(1 for r in rows if r["chg"] > 0)
        themes.append({
            "theme": name, "avg_chg": round(avg, 2), "up": up, "count": len(rows),
            "state": "hot" if avg >= 1.5 else "cooling" if avg <= -1.5 else "mixed",
        })
    themes.sort(key=lambda x: -x["avg_chg"])
    return themes


def run_deep_scan(top_n=60, min_price=5.0, min_dollar_vol=5_000_000, min_volume=400_000):
    """Background job: full-market snapshot -> liquidity filter -> deep RSI/EMA on the
    most interesting names -> classified opportunities + theme momentum. Updates _SCAN
    so the UI can show a progress bar. Persists to data/scan.json.

    Excludes leveraged/inverse ETFs and non-common-stock securities (we want the real
    underlying, e.g. CRWV, not its 2x wrapper), and low-volume names."""
    with _SCAN_LOCK:
        _SCAN.update(running=True, stage="snapshot", progress=0, total=0,
                     started=dt.datetime.now().isoformat(timespec="seconds"),
                     finished=None, error=None)
    try:
        snap = fetch_full_snapshot()
        _SCAN["scanned_universe"] = len(snap)
        if not snap:
            raise RuntimeError("Market snapshot came back empty. Snapshot data repopulates "
                               "around 4:00 AM ET — try again during/near market hours.")

        # Rank the whole liquid market for "something is happening": magnitude of the
        # day's move amplified by a volume surge vs. the prior day. Volume falls back
        # to the prior day so we still find names outside of regular trading hours.
        ranked = []
        for sym, d in snap.items():
            price, chg = d["price"], d.get("chg")
            vol = max(d.get("vol") or 0, d.get("prev_vol") or 0)
            if chg is None or price < min_price or vol < min_volume or price * vol < min_dollar_vol:
                continue
            if sym in LEVERAGED_ETFS:            # skip obvious leveraged/inverse ETFs
                continue
            vsurge = (d["vol"] / d["prev_vol"]) if (d.get("vol") and d.get("prev_vol")) else 1.0
            interest = abs(chg) * (1 + min(vsurge, 5) / 5)
            ranked.append((interest, sym, price, chg, round(vsurge, 2)))
        ranked.sort(reverse=True)

        # Popular names always get analyzed regardless of how much they moved.
        popular_pending = [sym for sym in POPULAR if sym in snap and snap[sym]["price"] >= min_price]
        with _SCAN_LOCK:
            _SCAN.update(stage="analyzing", total=top_n + len(popular_pending), progress=0)

        results = []
        seen = set()

        # 1) Popular / recognizable names first (no volume filter, no type lookup —
        #    they're all known common stocks). This guarantees NVDA/GOOGL/COIN/… show.
        for sym in popular_pending:
            d = snap[sym]
            vsurge = (d["vol"] / d["prev_vol"]) if (d.get("vol") and d.get("prev_vol")) else 1.0
            results.append(_deep_row(sym, d["price"], d.get("chg"), round(vsurge, 2), popular=True))
            seen.add(sym)
            with _SCAN_LOCK:
                _SCAN["progress"] = len(results)

        # 2) Walk the ranked movers, keeping only real common stocks (drops ETFs/
        #    leveraged), until we have top_n discovery names or hit a sane cap.
        checked = 0
        for (interest, sym, price, chg, vsurge) in ranked:
            if (len(results) - len(seen)) >= top_n or checked >= top_n * 4:
                break
            if sym in seen:
                continue
            checked += 1
            if fetch_ticker_type(sym) not in _COMMON_TYPES:
                continue                          # ETF / ETN / fund — skip
            results.append(_deep_row(sym, price, chg, vsurge, popular=False))
            seen.add(sym)
            with _SCAN_LOCK:
                _SCAN["progress"] = len(results)

        # nice ordering: buy-low first (your entries), then momentum, then overbought
        order = {"buy-low": 0, "momentum": 1, "overbought": 2, "watch": 3}
        results.sort(key=lambda r: (order.get(r["bucket"], 9), -r["score"]))

        # Sector heat + the constituent names behind each theme (so the UI can expand a
        # sector into its stocks). Reuse already-analyzed rows; fetch RSI for the rest.
        with _SCAN_LOCK:
            _SCAN.update(stage="themes")
        analyzed = {r["ticker"]: r for r in results}

        def _theme_row(sym):
            if sym in analyzed:
                return analyzed[sym]
            d = snap[sym]
            vs = (d["vol"] / d["prev_vol"]) if (d.get("vol") and d.get("prev_vol")) else 1.0
            row = _deep_row(sym, d["price"], d.get("chg"), round(vs, 2))
            analyzed[sym] = row
            return row

        themes = theme_momentum(snap)
        keep = ("ticker", "price", "change_pct", "rsi", "bucket", "uptrend")
        for th in themes:
            stocks = []
            for sym in THEMES.get(th["theme"], []):
                if sym in snap:
                    r = _theme_row(sym)
                    stocks.append({k: r[k] for k in keep})
            th["stocks"] = stocks

        DATA_DIR.mkdir(exist_ok=True)
        payload = {"as_of": dt.datetime.now().isoformat(timespec="seconds"),
                   "results": results, "themes": themes,
                   "scanned_universe": _SCAN["scanned_universe"]}
        with open(DATA_DIR / "scan.json", "w") as f:
            json.dump(payload, f, indent=2)

        with _SCAN_LOCK:
            _SCAN.update(running=False, stage="done", results=results, themes=themes,
                         finished=payload["as_of"])
    except Exception as e:        # noqa: BLE001
        with _SCAN_LOCK:
            _SCAN.update(running=False, stage="error", error=str(e))


def start_scan():
    """Kick off the deep scan in a background thread (no-op if already running)."""
    if not API_KEY:
        raise RuntimeError("MASSIVE_API_KEY is not set.")
    with _SCAN_LOCK:
        if _SCAN["running"]:
            return {"running": True, "stage": _SCAN["stage"]}
    threading.Thread(target=run_deep_scan, daemon=True).start()
    return {"running": True, "stage": "starting"}


def scan_status():
    """Current progress + results. Falls back to the last saved scan when idle."""
    with _SCAN_LOCK:
        st = {k: _SCAN[k] for k in ("running", "stage", "progress", "total",
                                    "started", "finished", "error", "scanned_universe")}
        st["results"] = _SCAN.get("results")
        st["themes"] = _SCAN.get("themes")
    if st["results"] is None:
        f = DATA_DIR / "scan.json"
        if f.exists():
            try:
                saved = json.load(open(f))
                st["results"] = saved.get("results")
                st["themes"] = saved.get("themes")
                st["finished"] = saved.get("as_of")
                st["scanned_universe"] = saved.get("scanned_universe", 0)
            except Exception:        # noqa: BLE001
                pass
    return st


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # python looper_engine.py AVGO  -> just that one stock
        _print(run(sys.argv[1]))
    else:
        # python looper_engine.py  -> the whole portfolio, sell-urgency first
        results, errors = run_all()
        for r in sorted(results, key=lambda x: -x["urgency"]):
            _print(r)
        for e in errors:
            print(f"\n{e['ticker']}  —  ERROR: {e['error']}")
