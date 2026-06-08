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


class StockPatch(BaseModel):
    state: Optional[str] = None
    entry_price: Optional[float] = None
    shares: Optional[float] = None
    last_sell_price: Optional[float] = None
    analyst_target: Optional[float] = None
    next_earnings: Optional[str] = None


@app.get("/api/portfolio")
def portfolio():
    results, errors = engine.run_all()
    return {"results": results, "errors": errors}


@app.get("/api/config")
def get_config():
    return {"stocks": engine.load_config().get("stocks", [])}


@app.get("/api/stock/{ticker}")
def stock(ticker: str):
    cfg = engine.load_config()
    s = next((x for x in cfg.get("stocks", []) if x["ticker"].upper() == ticker.upper()), None)
    if s is None:
        raise HTTPException(status_code=404, detail=f"{ticker.upper()} is not in config.")
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
                                last_sell_price=stock.last_sell_price)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/stocks/{ticker}")
def patch(ticker: str, body: StockPatch):
    try:
        return engine.update_stock(ticker, **body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/stocks/{ticker}")
def delete(ticker: str):
    return {"stocks": engine.remove_stock(ticker)}
