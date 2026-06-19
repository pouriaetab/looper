"""
LOOPER — FastAPI layer
======================
A thin JSON API over the same engine the dashboard uses, so any front-end (React,
another project, etc.) can consume LOOPER's signals without touching the Python
logic. The engine returns plain dicts, so these endpoints are mostly pass-throughs.

Run it:
    uvicorn api:app --reload --port 8000
Then open http://localhost:8000/docs for interactive, auto-generated API docs.

Endpoints:
    GET    /api/portfolio          -> all stocks evaluated (sell/buy, urgency, etc.)
    GET    /api/config             -> the current watchlist/holdings
    GET    /api/stock/{ticker}     -> one stock: signals + scorecard + fused stance + detail
    POST   /api/stocks             -> add/replace a holding (symbol, buy price, shares)
    PATCH  /api/stocks/{ticker}    -> update a holding (e.g. mark sold -> cash)
    DELETE /api/stocks/{ticker}    -> remove a holding
"""

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import looper_engine as engine
import fundamentals

app = FastAPI(title="LOOPER API", version="1.0")

# Allow a separate front-end (e.g. React on another port) to call this in dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class StockIn(BaseModel):
    ticker: str
    entry_price: float
    shares: float = 1
    state: str = "holding"               # "holding" or "cash"
    analyst_target: Optional[float] = None
    last_sell_price: Optional[float] = None
    acquired_date: Optional[str] = None  # YYYY-MM-DD format
    when: Optional[str] = None  # optional ISO date/datetime for the ledger; defaults to now
    from_reserve: bool = False  # fund this buy from the re-entry reserve (draws it down)


class StockPatch(BaseModel):
    state: Optional[str] = None
    entry_price: Optional[float] = None
    shares: Optional[float] = None
    last_sell_price: Optional[float] = None
    analyst_target: Optional[float] = None
    next_earnings: Optional[str] = None
    acquired_date: Optional[str] = None


class SellIn(BaseModel):
    shares: float
    price: float
    when: Optional[str] = None  # optional ISO datetime; defaults to now


@app.get("/api/portfolio")
def portfolio():
    results, errors = engine.run_all()
    return {"results": results, "errors": errors}


@app.get("/api/config")
def get_config():
    return {"stocks": engine.load_config().get("stocks", [])}


class SettingsIn(BaseModel):
    horizon: str   # one of engine.HORIZONS (swing / position / weekly / monthly)


def _current_horizon(th):
    return th.get("horizon") or ("weekly" if th.get("timespan") == "week" else "swing")


@app.get("/api/settings")
def get_settings():
    th = engine.load_config().get("thresholds", {})
    return {
        "horizon": _current_horizon(th),
        "horizons": [{"value": k, "label": v["label"], "approx": v["approx"]}
                     for k, v in engine.HORIZONS.items()],
    }


@app.post("/api/settings")
def set_settings(body: SettingsIn):
    if body.horizon not in engine.HORIZONS:
        raise HTTPException(status_code=400,
                            detail=f"horizon must be one of {list(engine.HORIZONS)}")
    cfg = engine.load_config()
    th = cfg.setdefault("thresholds", {})
    th["horizon"] = body.horizon
    th["timespan"] = engine.HORIZONS[body.horizon]["timespan"]   # keep legacy key in sync
    engine.save_config(cfg)
    return {"horizon": body.horizon}


@app.get("/api/stock/{ticker}")
def stock(ticker: str):
    cfg = engine.load_config()
    s = next((x for x in cfg.get("stocks", []) if x["ticker"].upper() == ticker.upper()), None)
    if s is None:
        # Not an owned position (e.g. a watchlist symbol) — analyze it as a no-position view.
        result = engine.evaluate_watch(ticker.upper())
    else:
        result = engine.evaluate(ticker.upper(), engine._stock_cfg(cfg, s))
    detail = engine.fetch_detail(ticker.upper())
    sc = fundamentals.build_scorecard(detail.get("ratios"), detail.get("income"))
    stance, reason = fundamentals.fuse_stance(sc["quality_verdict"], sc["value_verdict"],
                                              result["headline"])
    digest = fundamentals.news_digest(detail.get("news"), result["price"],
                                      result["ema_short"], result["ema_long"], result["rsi"])
    return {
        "result": result,
        "scorecard": sc,
        "stance": {"label": stance, "reason": reason},
        "news_digest": digest,
        "catalysts": fundamentals.catalysts(detail.get("news")),
        "detail": detail,
    }


@app.post("/api/stocks")
def add(stock: StockIn):
    try:
        return engine.add_stock(stock.ticker, stock.entry_price, stock.shares,
                                state=stock.state, analyst_target=stock.analyst_target,
                                last_sell_price=stock.last_sell_price, when=stock.when,
                                from_reserve=stock.from_reserve,
                                acquired_date=stock.acquired_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/stocks/{ticker}")
def patch(ticker: str, body: StockPatch):
    try:
        return engine.update_stock(ticker, **body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/stocks/{ticker}/sell")
def sell(ticker: str, body: SellIn):
    """Record a sale (date/time auto-stamped). Full sell removes the stock;
    partial sell keeps it with reduced shares. Always logged to the ledger."""
    try:
        return engine.sell_stock(ticker, body.shares, body.price, when=body.when)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tally")
def tally():
    """Portfolio totals: holdings, realized vs unrealized profit, net taken, reserve."""
    return engine.portfolio_tally()


@app.get("/api/ledger")
def ledger():
    """The full transaction history (the analysis dataset)."""
    return {"rows": engine.read_ledger()}


@app.delete("/api/stocks/{ticker}")
def delete(ticker: str):
    return {"stocks": engine.remove_stock(ticker)}


# ============================================================================
# Phase 4: Candidate Scanner + Watchlist
# ============================================================================
@app.get("/api/candidates")
def get_candidates(limit: int = 10):
    """Scan for quality stocks that are oversold (RSI < 35) or overbought (RSI > 72)."""
    try:
        return {"candidates": engine.scan_candidates(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/watchlist")
def get_watchlist():
    """Get the manual watchlist, each item enriched with a LIVE signal (price, RSI,
    headline, reason) — tracked the same way as owned positions and scanner hits."""
    cfg = engine.load_config()
    out = []
    for w in cfg.get("watchlist", []):
        item = dict(w)
        try:
            r = engine.evaluate_watch(w["ticker"])
            item["signal"] = {
                "headline": r["headline"], "price": r["price"], "rsi": r["rsi"],
                "ema_short": r["ema_short"], "ema_long": r["ema_long"],
                "top_reason": r["top_reason"], "action": r["action"],
                "counts": r["counts"],
            }
        except Exception as e:        # noqa: BLE001
            item["signal_error"] = str(e)
        out.append(item)
    return {"watchlist": out}


@app.post("/api/watchlist")
def add_to_watchlist(ticker: str, notes: Optional[str] = None):
    """Add a stock to the manual watchlist."""
    cfg = engine.load_config()
    ticker = ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker is required.")

    watchlist = cfg.setdefault("watchlist", [])
    # Check if already in watchlist
    if any(w["ticker"] == ticker for w in watchlist):
        raise HTTPException(status_code=400, detail=f"{ticker} already in watchlist.")

    # Try to fetch current data for the stock
    try:
        bars = engine.fetch_daily_bars(ticker, days=5)
        rsi_data = engine.fetch_rsi_series(ticker, 14, limit=1)
        if bars and rsi_data:
            price = bars[-1]["c"]
            rsi = rsi_data[0]
            entry = {
                "ticker": ticker,
                "added_date": engine.dt.datetime.now().isoformat(timespec="seconds"),
                "price_when_added": round(price, 2),
                "rsi_when_added": round(rsi, 1),
                "notes": notes,
            }
            watchlist.append(entry)
            engine.save_config(cfg)
            return {"added": entry, "watchlist": watchlist}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch {ticker}: {str(e)}")


@app.delete("/api/watchlist/{ticker}")
def remove_from_watchlist(ticker: str):
    """Remove a stock from the manual watchlist."""
    cfg = engine.load_config()
    ticker = ticker.strip().upper()
    watchlist = cfg.get("watchlist", [])
    cfg["watchlist"] = [w for w in watchlist if w["ticker"] != ticker]
    engine.save_config(cfg)
    return {"removed": ticker, "watchlist": cfg["watchlist"]}
