"""
LOOPER — Phase 2: Re-entry sizing & next-swing recommendation (Branch 2)
=======================================================================
After a sell, LOOPER answers three questions:

  1. How much cash should I reserve to buy back in?
     -> never less than the original position cost; ideally original cost plus a
        configurable slice of the realized profit (config: reinvest_profit_pct).
  2. Where is the next likely re-entry zone on this same stock?
     -> the support levels below the current price: EMA20, EMA50, the recent
        swing low, and the nearest round number.
  3. How many shares does my reserve buy at those levels?
     -> whole shares preferred, fractional shown too. A lower re-entry price
        means the same reserve buys MORE shares — that's the loop compounding.

This module is pure math on already-fetched data (no API calls). While you are
still HOLDING it runs as a *projection* ("if you sell now…"); once you are in
CASH with a recorded last_sell_price it uses the realized numbers.
"""

import math


def _nearest_round_below(price, step=5):
    r = math.floor(price / step) * step
    return r if r < price else r - step


def plan_reentry(price, bars, ema_s, ema_l, rsi_now, cfg, state):
    th = cfg["thresholds"]
    pos = cfg.get("position", {})
    entry = pos.get("entry_price")
    shares = pos.get("shares", 1) or 1
    reinvest = cfg.get("reinvest_profit_pct", 0.5)

    # Which sell price to base the budget on
    if state == "cash" and pos.get("last_sell_price"):
        sell_price = pos["last_sell_price"]
        basis = "realized"
    else:
        sell_price = price
        basis = "projected (if you sell now)"

    # Budget math
    original_cost = (entry or sell_price) * shares
    proceeds = sell_price * shares
    profit = proceeds - original_cost
    reserve = original_cost + reinvest * max(profit, 0.0)   # floor = original cost

    # Next-swing entry zone: support levels strictly below the current price
    look = th.get("swing_low_lookback", 45)
    window = bars[-look:] if len(bars) >= look else bars
    swing_low = min(b["l"] for b in window)
    round_sup = _nearest_round_below(price)

    candidates = {
        f"EMA{th['ema_short']}": ema_s,
        f"EMA{th['ema_long']}": ema_l,
        "recent swing low": swing_low,
        f"round ${round_sup:.0f}": float(round_sup),
    }
    levels = sorted(
        [(n, v) for n, v in candidates.items() if v < price],
        key=lambda x: -x[1],            # nearest (highest) support first
    )

    def size_at(p):
        total = reserve / p
        return {
            "price": round(p, 2),
            "whole_shares": int(total),
            "total_shares": round(total, 3),
            "vs_original": round(total - shares, 3),   # extra shares vs the position you sold
        }

    sizing = [{"level": n, **size_at(v)} for n, v in levels[:3]]
    primary = levels[0] if levels else None

    return {
        "basis": basis,
        "sell_price": round(sell_price, 2),
        "shares_sold": shares,
        "original_cost": round(original_cost, 2),
        "proceeds": round(proceeds, 2),
        "profit": round(profit, 2),
        "reinvest_profit_pct": reinvest,
        "reserve_budget": round(reserve, 2),
        "rsi_now": round(rsi_now, 1),
        "entry_levels": [{"level": n, "price": round(v, 2)} for n, v in levels],
        "primary_entry": ({"level": primary[0], "price": round(primary[1], 2)}
                          if primary else None),
        "sizing": sizing,
        "note": (f"These are price targets, not a trigger — a real re-entry still "
                 f"needs the hard signal (RSI ≤ {th['rsi_oversold']} or a confirmed "
                 f"support bounce)."),
    }
