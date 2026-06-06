"""
LOOPER — Phase 1 connection test
=================================
Purpose: prove we can pull PRICE, RSI, and MOVING AVERAGES from the Massive API
for a single ticker (default BRKR). This is a *connection test only* — there is
NO trading/strategy logic here yet. We confirm the data flows before building anything.

The API key is read from the environment variable MASSIVE_API_KEY.
It is never written in this file. See README.md for how to export it.

Run it from your VS Code terminal:
    python test_massive_connection.py
or test a different ticker:
    python test_massive_connection.py AAPL
"""

import os
import sys
import requests

BASE = "https://api.massive.com"          # Massive REST base URL
API_KEY = os.environ.get("MASSIVE_API_KEY")  # pulled from your shell environment


def _get(path, params=None):
    """Small helper: GET a Massive endpoint and return parsed JSON."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    params = params or {}
    resp = requests.get(BASE + path, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_latest_price(ticker):
    """Most recent daily close (previous trading day's bar)."""
    data = _get(f"/v2/aggs/ticker/{ticker}/prev", {"adjusted": "true"})
    bar = data["results"][0]
    return {
        "close": bar["c"],
        "open": bar["o"],
        "high": bar["h"],
        "low": bar["l"],
        "volume": bar["v"],
    }


def get_rsi(ticker, window=14):
    """Latest RSI value (default 14-day, on daily closes)."""
    data = _get(
        f"/v1/indicators/rsi/{ticker}",
        {"timespan": "day", "window": window, "series_type": "close",
         "order": "desc", "limit": 1},
    )
    return data["results"]["values"][0]["value"]


def get_ema(ticker, window):
    """Latest EMA value for the given window (on daily closes)."""
    data = _get(
        f"/v1/indicators/ema/{ticker}",
        {"timespan": "day", "window": window, "series_type": "close",
         "order": "desc", "limit": 1},
    )
    return data["results"]["values"][0]["value"]


def main():
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "BRKR").upper()

    if not API_KEY:
        print("✗ MASSIVE_API_KEY is not set in your environment.")
        print("  Export it first (see README.md), then re-run this script.")
        sys.exit(1)

    print(f"Testing Massive API connection for {ticker}...\n")

    try:
        price = get_latest_price(ticker)
        rsi = get_rsi(ticker, 14)
        ema20 = get_ema(ticker, 20)
        ema50 = get_ema(ticker, 50)
    except requests.HTTPError as e:
        print(f"✗ API request failed: {e}")
        print("  Check that your key is valid and your plan covers this endpoint.")
        sys.exit(1)
    except (KeyError, IndexError):
        print("✗ Got a response but couldn't find the expected data fields.")
        print("  The API response format may differ — paste the output to Claude.")
        sys.exit(1)

    print(f"  Price (last close): ${price['close']:.2f}")
    print(f"     open {price['open']:.2f} | high {price['high']:.2f} | "
          f"low {price['low']:.2f} | volume {price['volume']:,.0f}")
    print(f"  RSI (14):           {rsi:.2f}")
    print(f"  EMA (20):           ${ema20:.2f}")
    print(f"  EMA (50):           ${ema50:.2f}")
    print("\n✓ SUCCESS — price, RSI, and moving averages all pulled correctly.")


if __name__ == "__main__":
    main()
