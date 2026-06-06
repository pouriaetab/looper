"""
LOOPER — Fundamental scorecard (Phase 3c)
=========================================
Turns raw financials into a plain-English, quality + value read of a business.

It answers TWO questions, kept deliberately separate from the timing engine:
  - VALUE  : is the stock cheap or expensive right now?
  - QUALITY: is this a good business (profitable, well-run, low-debt, growing)?

Each factor is scored against conventional thresholds, gets a status chip
("Cheap", "Strong", "Elevated"…), a plain-language tooltip with the typical range,
and a weight showing how much it moves the verdict. The two verdicts are then
fused with the technical timing label into a portfolio-manager stance
(Accumulate / Hold / Trim / Reduce / Exit).

Lens: quality + value. High ROE, durable margins, low debt, real cash
flow, and a sensible price are rewarded; hot stories with weak economics are not.

This is decision SUPPORT, not financial advice. Thresholds are general heuristics
and vary by sector.
"""

INF = float("inf")


# --------------------------------------------------------------------------- #
# Factor definitions
# bands: ordered list of (threshold, label, score). For lower_is_better the first
# band whose threshold the value is <= wins; for higher_is_better, value >=.
# weight: relative influence inside the scorecard.
# fmt: how to display the raw value.
# tip: one-line meaning + typical range (shown on hover).
# --------------------------------------------------------------------------- #
FACTORS = [
    # ---- VALUATION (cheaper = better) ----
    dict(key="price_to_earnings", label="P/E", cat="Valuation", weight=2.0, lower=True, fmt="x",
         bands=[(15, "Cheap", 1.0), (25, "Fair", 0.7), (40, "Elevated", 0.4), (INF, "Expensive", 0.15)],
         tip="Price per $1 of annual earnings. <15 cheap, 15–25 fair, >40 pricey (varies by sector)."),
    dict(key="price_to_sales", label="P/S", cat="Valuation", weight=1.5, lower=True, fmt="x",
         bands=[(2, "Cheap", 1.0), (5, "Fair", 0.7), (10, "Elevated", 0.4), (INF, "Expensive", 0.15)],
         tip="Price vs sales. <1 deep value, <2 cheap, >10 expensive. Useful when earnings are noisy."),
    dict(key="price_to_book", label="P/B", cat="Valuation", weight=1.0, lower=True, fmt="x",
         bands=[(1.5, "Cheap", 1.0), (3, "Fair", 0.7), (6, "Elevated", 0.4), (INF, "High", 0.2)],
         tip="Price vs book value (net worth). <1.5 value territory; naturally high for asset-light tech."),
    dict(key="price_to_free_cash_flow", label="P/FCF", cat="Valuation", weight=1.5, lower=True, fmt="x",
         bands=[(15, "Cheap", 1.0), (25, "Fair", 0.7), (40, "Elevated", 0.4), (INF, "Expensive", 0.15)],
         tip="Price vs free cash flow. <15 attractive cash yield; values the actual cash a business throws off."),
    dict(key="ev_to_ebitda", label="EV/EBITDA", cat="Valuation", weight=1.5, lower=True, fmt="x",
         bands=[(10, "Cheap", 1.0), (15, "Fair", 0.7), (22, "Elevated", 0.4), (INF, "High", 0.2)],
         tip="Whole-company value vs operating earnings (ignores debt structure). <10 cheap, >22 rich."),

    # ---- QUALITY (higher = better) ----
    dict(key="return_on_equity", label="ROE", cat="Quality", weight=2.5, lower=False, fmt="pct",
         bands=[(0.20, "Excellent", 1.0), (0.15, "Strong", 0.8), (0.08, "Adequate", 0.5), (-INF, "Weak", 0.2)],
         tip="Profit on shareholders' capital. Consistent >15% is the mark of a strong compounder; >20% excellent, <8% weak."),
    dict(key="return_on_assets", label="ROA", cat="Quality", weight=1.5, lower=False, fmt="pct",
         bands=[(0.08, "Strong", 1.0), (0.04, "Adequate", 0.6), (-INF, "Weak", 0.25)],
         tip="Profit on total assets. >8% capital-efficient, <4% weak. Comparable across capital structures."),
    dict(key="gross_margin", label="Gross margin", cat="Quality", weight=1.5, lower=False, fmt="pct",
         bands=[(0.50, "Wide moat", 1.0), (0.35, "Solid", 0.75), (0.20, "Thin", 0.45), (-INF, "Low", 0.2)],
         tip="Sales kept after production cost. High & durable margin = pricing power / moat. >50% wide."),
    dict(key="operating_margin", label="Operating margin", cat="Quality", weight=1.5, lower=False, fmt="pct",
         bands=[(0.25, "Strong", 1.0), (0.15, "Solid", 0.7), (0.05, "Thin", 0.4), (-INF, "Weak", 0.15)],
         tip="Profit from core operations per $1 of sales. >25% strong, <5% thin."),
    dict(key="free_cash_flow", label="Free cash flow", cat="Quality", weight=1.5, lower=False, fmt="money",
         bands=[(0.0000001, "Positive", 1.0), (-INF, "Negative", 0.1)],
         tip="Cash left after running and reinvesting in the business. Positive & growing = healthy."),

    # ---- FINANCIAL HEALTH ----
    dict(key="debt_to_equity", label="Debt / equity", cat="Health", weight=2.0, lower=True, fmt="ratio",
         bands=[(0.5, "Conservative", 1.0), (1.0, "Moderate", 0.7), (2.0, "Elevated", 0.4), (INF, "High", 0.15)],
         tip="Leverage. <0.5 conservative, 1–2 elevated, >2 risky."),
    dict(key="current", label="Current ratio", cat="Health", weight=1.0, lower=False, fmt="ratio",
         bands=[(1.5, "Healthy", 1.0), (1.0, "Adequate", 0.6), (-INF, "Tight", 0.25)],
         tip="Short-term assets vs short-term bills. >1.5 comfortable, <1 a liquidity worry."),
    dict(key="quick", label="Quick ratio", cat="Health", weight=1.0, lower=False, fmt="ratio",
         bands=[(1.0, "Healthy", 1.0), (0.7, "Adequate", 0.6), (-INF, "Tight", 0.3)],
         tip="Liquidity excluding inventory. >1 can cover near-term bills without selling stock."),

    # ---- GROWTH ----
    dict(key="revenue_growth", label="Revenue growth (YoY)", cat="Growth", weight=2.0, lower=False, fmt="pct",
         bands=[(0.15, "Strong", 1.0), (0.05, "Steady", 0.65), (0.0, "Flat", 0.4), (-INF, "Declining", 0.1)],
         tip="Year-over-year sales growth. >15% strong; a real decline is a red flag (the brief's exit rule)."),
    dict(key="eps_growth", label="EPS growth (YoY)", cat="Growth", weight=1.5, lower=False, fmt="pct",
         bands=[(0.15, "Strong", 1.0), (0.05, "Steady", 0.65), (0.0, "Flat", 0.4), (-INF, "Declining", 0.1)],
         tip="Year-over-year earnings-per-share growth. Rising EPS is the engine of long-run returns."),

    # ---- ADDED FACTORS ----
    dict(key="peg", label="PEG", cat="Valuation", weight=1.5, lower=True, fmt="ratio",
         bands=[(1.0, "Cheap vs growth", 1.0), (2.0, "Fair", 0.7), (3.0, "Elevated", 0.4), (INF, "Expensive", 0.15)],
         tip="P/E relative to earnings growth. <1 means growth is cheap; >2 means you're paying up for it."),
    dict(key="fcf_margin", label="FCF margin", cat="Quality", weight=1.5, lower=False, fmt="pct",
         bands=[(0.20, "Strong", 1.0), (0.10, "Solid", 0.7), (0.03, "Thin", 0.4), (-INF, "Weak", 0.15)],
         tip="Free cash flow as a % of sales. >20% is excellent cash conversion; negative is a warning."),
    dict(key="margin_cv", label="Margin consistency", cat="Quality", weight=1.5, lower=True, fmt="pct",
         bands=[(0.10, "Very steady", 1.0), (0.20, "Steady", 0.7), (0.35, "Variable", 0.4), (INF, "Erratic", 0.15)],
         tip="How much operating margin has wobbled over recent years (lower = steadier). Durable margins = a moat."),
    dict(key="share_change", label="Share count trend", cat="Quality", weight=1.5, lower=True, fmt="pct",
         bands=[(-0.02, "Buybacks", 1.0), (0.01, "Flat", 0.7), (0.05, "Mild dilution", 0.4), (INF, "Diluting", 0.15)],
         tip="Change in diluted share count over the period. Negative = buybacks (good); positive = dilution."),
    dict(key="interest_coverage", label="Interest coverage", cat="Health", weight=1.5, lower=False, fmt="x",
         bands=[(8, "Strong", 1.0), (3, "Adequate", 0.6), (1, "Tight", 0.3), (-INF, "Risky", 0.1)],
         tip="Operating income ÷ interest expense — how easily it pays debt interest. >8x comfortable, <1.5x stressed."),
]

# Which categories roll into which verdict.
VALUE_CATS = {"Valuation"}
QUALITY_CATS = {"Quality", "Health", "Growth"}


def _band_score(value, bands, lower):
    for thr, label, score in bands:
        if (lower and value <= thr) or (not lower and value >= thr):
            return label, score
    return bands[-1][1], bands[-1][2]


def _derive(ratios, income):
    """Compute margins + growth from income statements (sorted newest first)."""
    vals = dict(ratios or {})
    inc = income or []
    latest = inc[0] if len(inc) >= 1 else None
    prior = inc[1] if len(inc) >= 2 else None
    if latest:
        rev = latest.get("revenue")
        if rev:
            if latest.get("gross_profit") is not None:
                vals["gross_margin"] = latest["gross_profit"] / rev
            if latest.get("operating_income") is not None:
                vals["operating_margin"] = latest["operating_income"] / rev
    if latest and prior:
        r0, r1 = latest.get("revenue"), prior.get("revenue")
        if r0 and r1 and r1 > 0:
            vals["revenue_growth"] = r0 / r1 - 1
        e0, e1 = latest.get("diluted_earnings_per_share"), prior.get("diluted_earnings_per_share")
        if e0 is not None and e1 and e1 > 0:
            vals["eps_growth"] = e0 / e1 - 1

    # FCF margin (free cash flow from ratios ÷ latest annual revenue)
    if latest and latest.get("revenue") and vals.get("free_cash_flow") is not None:
        vals["fcf_margin"] = vals["free_cash_flow"] / latest["revenue"]

    # PEG (P/E ÷ EPS growth %); only meaningful with positive growth
    pe = vals.get("price_to_earnings")
    g = vals.get("eps_growth")
    if pe and g and g > 0:
        vals["peg"] = pe / (g * 100)

    # Interest coverage (operating income ÷ interest expense), latest annual
    if latest:
        op, ie = latest.get("operating_income"), latest.get("interest_expense")
        if op is not None and ie and ie > 0:
            vals["interest_coverage"] = op / ie

    # Operating-margin consistency over the available annual periods (coefficient of
    # variation: stdev / mean — lower means steadier margins)
    margins = [s["operating_income"] / s["revenue"]
               for s in inc
               if s.get("revenue") and s.get("operating_income") is not None and s["revenue"] > 0]
    if len(margins) >= 3:
        mean = sum(margins) / len(margins)
        if mean > 0:
            var = sum((m - mean) ** 2 for m in margins) / len(margins)
            vals["margin_cv"] = (var ** 0.5) / mean

    # Share-count trend (diluted shares newest vs oldest available period)
    sh = [s.get("diluted_shares_outstanding") for s in inc if s.get("diluted_shares_outstanding")]
    if len(sh) >= 2 and sh[-1] > 0:
        vals["share_change"] = sh[0] / sh[-1] - 1   # inc is newest-first

    return vals


def _fmt(value, kind):
    if value is None:
        return "—"
    if kind == "x":
        return f"{value:.1f}x"
    if kind == "ratio":
        return f"{value:.2f}"
    if kind == "pct":
        return f"{value*100:.1f}%"
    if kind == "money":
        a = abs(value)
        if a >= 1e9:
            return f"${value/1e9:,.1f}B"
        if a >= 1e6:
            return f"${value/1e6:,.0f}M"
        return f"${value:,.0f}"
    return str(value)


def build_scorecard(ratios, income):
    """Return the structured scorecard: per-factor readings, category scores,
    Value verdict, Quality verdict."""
    vals = _derive(ratios, income)
    factors = []
    for spec in FACTORS:
        v = vals.get(spec["key"])
        if v is None:
            factors.append(dict(spec_label=spec["label"], cat=spec["cat"], value="—",
                                status="n/a", score=None, weight=spec["weight"],
                                tip=spec["tip"], scored=False))
            continue
        label, score = _band_score(v, spec["bands"], spec["lower"])
        factors.append(dict(spec_label=spec["label"], cat=spec["cat"], value=_fmt(v, spec["fmt"]),
                            status=label, score=score, weight=spec["weight"],
                            tip=spec["tip"], scored=True))

    total_w = sum(f["weight"] for f in factors if f["scored"]) or 1
    for f in factors:
        f["contribution"] = round(f["weight"] / total_w * 100, 1) if f["scored"] else 0.0
        f["pull"] = ("supporting" if f["scored"] and f["score"] >= 0.6
                     else "dragging" if f["scored"] and f["score"] <= 0.4
                     else "neutral")

    def cat_score(cats):
        sel = [f for f in factors if f["scored"] and f["cat"] in cats]
        w = sum(f["weight"] for f in sel)
        return (sum(f["score"] * f["weight"] for f in sel) / w) if w else None

    value_score = cat_score(VALUE_CATS)
    quality_score = cat_score(QUALITY_CATS)

    value_verdict = _label(value_score, [(0.75, "Cheap"), (0.55, "Fair"), (0.35, "Rich"), (0, "Expensive")])
    quality_verdict = _label(quality_score, [(0.75, "High quality"), (0.55, "Solid"),
                                             (0.40, "Average"), (0, "Weak")])
    # Deterioration override (brief's "exit completely" trigger)
    if (vals.get("revenue_growth") is not None and vals["revenue_growth"] < 0
            and vals.get("eps_growth") is not None and vals["eps_growth"] < 0):
        quality_verdict = "Deteriorating"

    categories = {}
    for cat in ["Valuation", "Quality", "Health", "Growth"]:
        categories[cat] = {
            "score": cat_score({cat}),
            "factors": [f for f in factors if f["cat"] == cat],
        }

    return {
        "value_verdict": value_verdict,
        "value_score": value_score,
        "quality_verdict": quality_verdict,
        "quality_score": quality_score,
        "categories": categories,
    }


def _label(score, bands):
    if score is None:
        return "n/a"
    for thr, label in bands:
        if score >= thr:
            return label
    return bands[-1][1]


# Map technical timing headline -> simple bucket
_TIMING = {
    "SELL SIGNAL": "sell", "WATCH": "sell",
    "RE-ENTRY ZONE": "buy", "RE-ENTRY WATCH": "buy",
    "HOLD": "hold", "WAIT": "hold",
}


def fuse_stance(quality_verdict, value_verdict, timing_headline):
    """Combine the business read with the timing read into a PM stance + reason."""
    q = quality_verdict
    val = value_verdict
    t = _TIMING.get(timing_headline, "hold")
    cheapish = val in ("Cheap", "Fair")
    pricey = val in ("Rich", "Expensive")

    if q in ("Weak", "Deteriorating"):
        return ("Exit / avoid",
                f"Business quality is {q.lower()} — not a stock to keep looping regardless of price.")
    if t == "buy" and cheapish:
        return ("Accumulate",
                f"{q} business near a re-entry and {val.lower()} on valuation — add on the dip.")
    if t == "buy" and pricey:
        return ("Hold / wait",
                f"Technically near a re-entry but valuation is {val.lower()} — wait for a better price.")
    if t == "sell" and pricey:
        return ("Trim / take profit",
                f"Stretched on price AND valuation ({val.lower()}) — bank some gains.")
    if t == "sell" and cheapish:
        return ("Hold",
                f"Overbought short-term but the business is {q.lower()} and only {val.lower()} — let it run.")
    # timing == hold
    if q == "High quality" and val == "Cheap":
        return ("Accumulate / core hold", "High-quality business at a cheap price — a keeper.")
    return ("Hold", f"{q} business, {val.lower()} valuation, no timing trigger — stay put.")


# stopword set so the theme extraction surfaces real topics, not filler
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "as",
         "at", "by", "inc", "corp", "stock", "stocks", "shares", "report", "reports", "news",
         "market", "markets", "company", "update", "says", "new", "this", "that", "after",
         "from", "amid", "its", "what", "why", "how", "you", "are", "be", "will", "vs"}


def news_digest(news, price, ema_s, ema_l, rsi):
    """Aggregate recent-news sentiment + a short momentum line + top themes.
    Pure heuristics — runs locally, no LLM/token cost."""
    if not news:
        return None
    pos = sum(1 for a in news if (a.get("sentiment") or "").lower() == "positive")
    neg = sum(1 for a in news if (a.get("sentiment") or "").lower() == "negative")
    neu = sum(1 for a in news if (a.get("sentiment") or "").lower() == "neutral")
    rated = pos + neg + neu

    if rated == 0:
        net = "Unrated"
    elif pos >= 2 * max(neg, 1) and pos > neu:
        net = "Positive"
    elif neg >= 2 * max(pos, 1) and neg > neu:
        net = "Negative"
    elif pos > neg:
        net = "Leaning positive"
    elif neg > pos:
        net = "Leaning negative"
    else:
        net = "Mixed / neutral"

    # Price momentum from the technicals we already have
    if price > ema_s > ema_l:
        trend = "uptrend"
    elif price < ema_s < ema_l:
        trend = "downtrend"
    elif price > ema_l:
        trend = "holding above trend"
    else:
        trend = "below trend"
    if rsi >= 70:
        trend += ", overbought"
    elif rsi <= 35:
        trend += ", oversold"
    flow = {"Positive": "bullish news flow", "Leaning positive": "mildly positive news",
            "Negative": "bearish news flow", "Leaning negative": "mildly negative news",
            "Mixed / neutral": "mixed news", "Unrated": "light news flow"}.get(net, "mixed news")
    momentum = f"{trend.capitalize()}; {flow}."

    # Themes from article keywords (fallback to title words)
    counts = {}
    for a in news:
        words = [k.lower() for k in (a.get("keywords") or [])]
        if not words:
            words = [w.strip(".,:–-()'\"").lower() for w in (a.get("title") or "").split()]
        for w in words:
            if len(w) > 2 and w not in _STOP and not w.isdigit():
                counts[w] = counts.get(w, 0) + 1
    themes = [w for w, _ in sorted(counts.items(), key=lambda x: -x[1])[:5]]

    return {
        "net": net,
        "counts": {"positive": pos, "neutral": neu, "negative": neg, "rated": rated, "total": len(news)},
        "momentum": momentum,
        "themes": themes,
    }


# Event types that often move a stock — scanned from recent news headlines.
_CATALYST_KEYWORDS = {
    "M&A / deal": ["acqui", "merger", "merge", "buyout", "takeover", "to buy ", "buys ",
                   "acquisition", "stake in", "deal to"],
    "Layoffs / restructuring": ["layoff", "job cut", "jobs cut", "restructur", "workforce reduction"],
    "Stock split": ["stock split", "share split", "-for-", "split announce"],
    "Buyback": ["buyback", "repurchase", "repurchases"],
    "Guidance / outlook": ["guidance", "outlook", "raises forecast", "cuts forecast",
                           "lowers guidance", "raises guidance", "warns"],
    "New product / launch": ["launch", "unveil", "new chip", "new product"],
}


def catalysts(news):
    """Flag potential catalysts (M&A, layoffs, splits, buybacks, guidance, launches)
    by scanning recent news headlines. news is newest-first, so the first hit per
    type is the most recent."""
    found = {}
    for a in news or []:
        text = (a.get("title") or "").lower()
        for label, kws in _CATALYST_KEYWORDS.items():
            if label not in found and any(k in text for k in kws):
                found[label] = a
    return [{"type": label, "headline": a.get("title"), "url": a.get("url"),
             "date": a.get("published")} for label, a in found.items()]
