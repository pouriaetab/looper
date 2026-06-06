"""
LOOPER — Phase 1 signal engine (Branch 1: Core Loop Engine)
===========================================================
Single-stock tracker. Pulls price / RSI / EMA / volume from the Massive API and
evaluates the SELL, RE-ENTRY, and STOP-LOOP rule sets from the project brief
(each fires when 2 of 3 conditions are true).

Design: this file is self-contained and has NO Claude/AI dependency. Run it on a
schedule (cron / launchd) and it writes data/<TICKER>_status.json. The Streamlit
dashboard (app.py) just reads that file, so the daily run is free and local.

Usage:
    python looper_engine.py            # uses config.json
    python looper_engine.py AAPL       # override ticker for a one-off check

The API key is read from the MASSIVE_API_KEY environment variable (see README).
"""

import os
import sys
import json
import datetime as dt
from pathlib import Path

import requests

from reentry_planner import plan_reentry

BASE = "https://api.massive.com"
API_KEY = os.environ.get("MASSIVE_API_KEY")
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"


# --------------------------------------------------------------------------- #
# API helpers
# --------------------------------------------------------------------------- #
def _get(path, params=None):
    headers = {"Authorization": f"Bearer {API_KEY}"}
    resp = requests.get(BASE + path, headers=headers, params=params or {}, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_daily_bars(ticker, days=160):
    """Daily OHLCV bars for roughly the last `days` calendar days."""
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    data = _get(
        f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}",
        {"adjusted": "true", "sort": "asc", "limit": 50000},
    )
    bars = data.get("results", []) or []
    # normalise to simple dicts
    return [
        {"o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["v"], "t": b["t"]}
        for b in bars
    ]


def fetch_rsi_series(ticker, window, limit=15):
    data = _get(
        f"/v1/indicators/rsi/{ticker}",
        {"timespan": "day", "window": window, "series_type": "close",
         "order": "desc", "limit": limit},
    )
    return [v["value"] for v in data["results"]["values"]]  # newest first


def fetch_ema(ticker, window):
    data = _get(
        f"/v1/indicators/ema/{ticker}",
        {"timespan": "day", "window": window, "series_type": "close",
         "order": "desc", "limit": 1},
    )
    return data["results"]["values"][0]["value"]


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
def evaluate(ticker, cfg):
    th = cfg["thresholds"]
    target = cfg.get("analyst_target")

    bars = fetch_daily_bars(ticker)
    if len(bars) < 30:
        raise RuntimeError(f"Only {len(bars)} bars returned for {ticker}; need more history.")
    price = bars[-1]["c"]
    rsi = fetch_rsi_series(ticker, 14)
    ema_s = fetch_ema(ticker, th["ema_short"])
    ema_l = fetch_ema(ticker, th["ema_long"])

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
        raise SystemExit("MASSIVE_API_KEY is not set. Export it first (see README).")
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
