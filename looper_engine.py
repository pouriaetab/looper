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
import datetime as dt
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
def _get(path, params=None):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    resp = requests.get(BASE + path, headers=headers, params=params or {}, timeout=20)
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
    reserve_used = _sum("reserve_used", actions=("buy", "reentry"))
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


def scan_candidates(tickers=None, limit=10):
    """Phase 4: Scan for quality stocks that are oversold (RSI < 35) or overbought (RSI > 72).
    Returns candidates with price, RSI, analyst target, and quality score.
    If tickers not provided, scans a default watchlist of popular liquid stocks.
    """
    if not API_KEY:
        raise RuntimeError("MASSIVE_API_KEY is not set.")

    # Default universe: popular, liquid, quality-focused stocks
    if not tickers:
        tickers = [
            "NVDA", "AVGO", "ADBE", "ASML", "CDNS", "COST", "CRM", "DDOG",
            "ENPH", "GOOG", "GOOGL", "HUBS", "IRM", "KLAC", "LRCX", "META",
            "MSFT", "NFLX", "NOW", "PSTG", "PYPL", "SNOW", "SPLK", "TTD",
            "TSLA", "WDAY", "ZM", "BRKR", "ACGL", "AEP", "BDX", "JNJ"
        ]

    # Scan on the same horizon (daily/weekly/monthly) the rest of LOOPER is using,
    # so the scanner's oversold/overbought reads match the portfolio + watchlist.
    cfg = load_config()
    _, tspan, hth = _resolve_horizon(cfg.get("thresholds", {}))
    es, el = hth["ema_short"], hth["ema_long"]

    candidates = []
    for ticker in tickers:
        try:
            # Fetch current RSI and price on the active horizon
            rsi_data = fetch_rsi_series(ticker, 14, limit=1, timespan=tspan)
            rsi = rsi_data[0] if rsi_data else None

            if rsi is None:
                continue

            bars = fetch_daily_bars(ticker, timespan=tspan)
            if not bars:
                continue

            price = bars[-1]["c"]  # last close
            ema_20 = fetch_ema(ticker, es, timespan=tspan)
            ema_50 = fetch_ema(ticker, el, timespan=tspan)

            # Determine if oversold or overbought
            if rsi < 35:
                category = "oversold"
                urgency = (35 - rsi) / 35  # closer to 0, more oversold
            elif rsi > 72:
                category = "overbought"
                urgency = (rsi - 72) / 28  # closer to 100, more overbought
            else:
                continue  # skip neutral RSI

            # Analyst target if this ticker is one of your tracked stocks
            stock_cfg = next((s for s in cfg.get("stocks", []) if s["ticker"].upper() == ticker.upper()), None)
            analyst_target = stock_cfg.get("analyst_target") if stock_cfg else None

            candidates.append({
                "ticker": ticker,
                "price": round(price, 2),
                "rsi": round(rsi, 1),
                "ema_20": round(ema_20, 2),
                "ema_50": round(ema_50, 2),
                "category": category,
                "urgency": round(urgency, 2),
                "analyst_target": analyst_target,
                "last_updated": dt.datetime.now().isoformat(timespec="seconds"),
            })
        except Exception:  # noqa: BLE001 - keep scanning even if one fails
            pass

    # Sort by urgency (highest first)
    candidates.sort(key=lambda x: -x["urgency"])
    return candidates[:limit]


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
