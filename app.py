"""
LOOPER — Phase 3 dashboard (multi-stock portfolio view)
=======================================================
Home page: every active loop on one scannable screen, split into a SELL section
(stocks you hold, ranked by how urgently to sell) and a BUY section (stocks you're
in cash on, ranked by re-entry readiness). Each stock is one line; the ▾ expander
reveals a second line of detail, and "Open full page" drills into a per-stock
detail view (signals, re-entry plan, and — coming next — earnings/news/financials).

Run locally:
    streamlit run app.py
Use the Network URL on your phone (same Wi-Fi). The daily number-crunching is done
by looper_engine.py on a schedule; this app is just the viewer + a Refresh button.
"""

import json
import datetime as dt
from pathlib import Path

import streamlit as st

import looper_engine as engine
import fundamentals

ROOT = Path(__file__).resolve().parent

st.set_page_config(page_title="LOOPER", page_icon="🔁", layout="wide")

# headline -> (background, foreground)
COLORS = {
    "SELL SIGNAL": ("#b00020", "#ffffff"),
    "WATCH": ("#c77700", "#ffffff"),
    "RE-ENTRY ZONE": ("#0b6e3b", "#ffffff"),
    "RE-ENTRY WATCH": ("#c77700", "#ffffff"),
    "HOLD": ("#1f4e8c", "#ffffff"),
    "WAIT": ("#5a5a5a", "#ffffff"),
}


def esc(s):
    # Streamlit markdown treats $...$ as LaTeX math; escape dollar signs.
    return str(s).replace("$", "\\$")


def badge(headline, big=False):
    bg, fg = COLORS.get(headline, ("#1f4e8c", "#ffffff"))
    pad = "8px 16px" if big else "3px 9px"
    size = "20px" if big else "12px"
    weight = "800" if big else "700"
    st.markdown(
        f"<span style='background:{bg};color:{fg};padding:{pad};border-radius:10px;"
        f"font-size:{size};font-weight:{weight};letter-spacing:.5px;'>{headline}</span>",
        unsafe_allow_html=True,
    )


def pl_pct(result):
    pos = result.get("position", {})
    entry = pos.get("entry_price")
    if entry:
        return (result["price"] / entry - 1) * 100
    return None


# --------------------------------------------------------------------------- #
# Data loading / refresh (cached in session so clicks don't re-hit the API)
# --------------------------------------------------------------------------- #
def load_portfolio_file():
    f = ROOT / "data" / "portfolio.json"
    if f.exists():
        data = json.loads(f.read_text())
        return data.get("results", []), data.get("errors", [])
    return None, None


def _is_stale(results):
    """True if there's no data or it's from before today (so we should re-pull)."""
    if not results:
        return True
    return (results[0].get("as_of", "")[:10] != dt.date.today().isoformat())


if "results" not in st.session_state:
    res, errs = load_portfolio_file()
    st.session_state.results = res or []
    st.session_state.errors = errs or []
    # Auto-run the engine on first open if data is missing or stale — so you can
    # just `streamlit run app.py` without running the engine by hand first.
    if _is_stale(st.session_state.results):
        with st.spinner("Refreshing data from Massive…"):
            try:
                r, e = engine.run_all()
                st.session_state.results, st.session_state.errors = r, e
            except Exception as ex:        # noqa: BLE001
                st.session_state.errors = [{"ticker": "—", "error": str(ex)}]
if "detail" not in st.session_state:
    st.session_state.detail = None


def get_result(ticker):
    return next((r for r in st.session_state.results if r["ticker"] == ticker), None)


def get_detail(ticker):
    """Fetch news + financials once per ticker per session (cached)."""
    cache = st.session_state.setdefault("detail_cache", {})
    if ticker not in cache:
        with st.spinner(f"Loading {ticker} financials & news…"):
            try:
                cache[ticker] = engine.fetch_detail(ticker)
            except Exception as e:        # noqa: BLE001
                cache[ticker] = {"ratios": None, "news": [], "errors": {"all": str(e)}}
    return cache[ticker]


# --------------------------------------------------------------------------- #
# Detail page (per stock)
# --------------------------------------------------------------------------- #
CHIP = {  # verdict label -> (bg, fg)
    "High quality": ("#0b6e3b", "#fff"), "Solid": ("#0b6e3b", "#fff"),
    "Average": ("#c77700", "#fff"), "Weak": ("#b00020", "#fff"),
    "Deteriorating": ("#b00020", "#fff"),
    "Cheap": ("#0b6e3b", "#fff"), "Fair": ("#1f4e8c", "#fff"),
    "Rich": ("#c77700", "#fff"), "Expensive": ("#b00020", "#fff"), "n/a": ("#5a5a5a", "#fff"),
}
STANCE = {  # fused stance -> (bg, fg)
    "Accumulate": ("#0b6e3b", "#fff"), "Accumulate / core hold": ("#0b6e3b", "#fff"),
    "Hold": ("#1f4e8c", "#fff"), "Hold / wait": ("#1f4e8c", "#fff"),
    "Trim / take profit": ("#c77700", "#fff"), "Reduce": ("#c77700", "#fff"),
    "Exit / avoid": ("#b00020", "#fff"),
}


def chip(label, mapping=CHIP, size="13px"):
    bg, fg = mapping.get(label, ("#5a5a5a", "#fff"))
    return (f"<span style='background:{bg};color:{fg};padding:3px 10px;border-radius:9px;"
            f"font-size:{size};font-weight:600'>{label}</span>")


def score_chip(status, score):
    if score is None:
        bg = "#5a5a5a"
    elif score >= 0.7:
        bg = "#0b6e3b"
    elif score >= 0.4:
        bg = "#c77700"
    else:
        bg = "#b00020"
    return (f"<span style='background:{bg};color:#fff;padding:2px 8px;border-radius:8px;"
            f"font-size:12px'>{status}</span>")


def render_scorecard(sc):
    for cat in ["Valuation", "Quality", "Health", "Growth"]:
        data = sc["categories"][cat]
        s = data["score"]
        pct = f"{s*100:.0f}/100" if s is not None else "n/a"
        st.markdown(f"**{cat}** &nbsp; <span style='color:gray;font-size:13px'>{pct}</span>",
                    unsafe_allow_html=True)
        rows = ""
        for f in data["factors"]:
            pull = ("<span style='color:#0b6e3b'>▲</span>" if f["pull"] == "supporting"
                    else "<span style='color:#b00020'>▼</span>" if f["pull"] == "dragging"
                    else "<span style='color:#999'>•</span>")
            contrib = f"{f['contribution']:.0f}%" if f["scored"] else "—"
            rows += (
                "<div style='display:flex;align-items:center;gap:8px;padding:5px 0;"
                "border-bottom:0.5px solid rgba(128,128,128,.2)'>"
                f"<span title=\"{f['tip']}\" style='cursor:help;flex:2.4'>{f['spec_label']} "
                "<span style='color:#999;font-size:11px'>ⓘ</span></span>"
                f"<span style='flex:1;text-align:right'>{f['value']}</span>"
                f"<span style='flex:1.3;text-align:right'>{score_chip(f['status'], f['score'])}</span>"
                f"<span style='flex:.9;text-align:right;font-size:12px;color:#666'>{pull} {contrib}</span>"
                "</div>"
            )
        st.markdown(esc(rows), unsafe_allow_html=True)
        st.write("")


def render_detail(result):
    if st.button("← Back to portfolio"):
        st.session_state.detail = None
        st.rerun()

    head = st.columns([1, 3])
    with head[0]:
        st.title(result["ticker"])
    with head[1]:
        st.write("")
        badge(result["headline"], big=True)
    st.caption(f"As of {result['as_of']} · last bar {result['last_bar_date']}")

    # Pull live fundamentals and build the scorecard + fused stance up top
    detail = get_detail(result["ticker"])
    sc = fundamentals.build_scorecard(detail.get("ratios"), detail.get("income"))
    stance, reason = fundamentals.fuse_stance(sc["quality_verdict"], sc["value_verdict"], result["headline"])

    bg, fg = STANCE.get(stance, ("#1f4e8c", "#fff"))
    st.markdown(
        f"<div style='background:{bg};color:{fg};padding:16px;border-radius:12px;margin:6px 0'>"
        f"<span style='font-size:22px;font-weight:800'>{stance}</span><br>"
        f"<span style='font-size:14px;opacity:.95'>{reason}</span></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "Quality " + chip(sc["quality_verdict"]) + " &nbsp;&nbsp; Valuation " + chip(sc["value_verdict"])
        + " &nbsp;&nbsp; Timing " + chip(result["headline"], {result["headline"]: COLORS.get(result["headline"], ("#5a5a5a", "#fff"))}),
        unsafe_allow_html=True,
    )
    st.caption("Quality & Valuation = is this a good business at a good price (quality + value lens). "
               "Timing = the swing signal. Stance fuses them. Decision support, not advice.")

    watch = result.get("watch", {})
    if watch.get("on"):
        st.warning("**Timing flag:** " + " · ".join(watch["reasons"]))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Price", f"${result['price']:.2f}")
    c2.metric("RSI (14)", f"{result['rsi']:.0f}")
    c3.metric("EMA 20", f"${result['ema_short']:.2f}")
    c4.metric("EMA 50", f"${result['ema_long']:.2f}")

    pos = result.get("position", {})
    gain = pl_pct(result)
    line = f"**Position:** {pos.get('state', '—')}"
    if pos.get("entry_price"):
        line += f" · entry ${pos['entry_price']:.2f} · {pos.get('shares', 0)} share(s)"
        if gain is not None:
            line += f" · unrealized {gain:+.1f}%"
    st.markdown(esc(line))

    if result.get("analyst_target"):
        avg = result["analyst_target"]
        lo, hi = result.get("target_low"), result.get("target_high")
        cnt, rating = result.get("analyst_count"), result.get("analyst_rating")
        url = result.get("analyst_source_url")
        a = f"<b>Analyst consensus:</b> ${avg:.2f} average"
        if cnt:
            tip = f"Average of {cnt} analysts' 12-month price targets."
            if lo and hi:
                tip += f" Individual targets range ${lo:.0f} (lowest) to ${hi:.0f} (highest)."
            if rating:
                tip += f" Overall rating: {rating}."
            tip += " Click to see every analyst and their target." if url else \
                   " (Per-analyst names/targets need the Benzinga analyst add-on.)"
            count_html = (f"<a href='{url}' target='_blank'>{cnt} analysts ↗</a>" if url
                          else f"<span title=\"{tip}\" style='cursor:help;border-bottom:1px dotted #888'>"
                               f"{cnt} analysts ⓘ</span>")
            a += f" across {count_html}"
        if lo and hi:
            a += f" · range ${lo:.0f}–${hi:.0f} (low→high)"
        if rating:
            a += f" · rating {rating}"
        st.markdown(esc(a), unsafe_allow_html=True)
        if result["price"] > (hi or float("inf")):
            st.caption("⚠ Trading above the highest analyst target — richly valued vs the Street.")
        elif result["price"] >= avg:
            st.caption("⚠ Trading above the average target — limited consensus upside left.")
    else:
        st.markdown("**Analyst consensus:** not set")

    st.divider()
    st.subheader("Fundamental scorecard")
    st.caption("Each factor scored vs conventional thresholds. ▲ supporting · ▼ dragging the verdict; "
               "% = how much it weighs. Hover a factor name for what it means and its typical range.")
    if detail.get("errors", {}).get("ratios") and not detail.get("ratios"):
        st.caption(f"Financials unavailable: {detail['errors']['ratios']}")
    else:
        render_scorecard(sc)

    st.divider()
    st.subheader("Timing signals")
    GROUPS = [("sell", "SELL signals", "Exit when 2 of 3 are true"),
              ("reentry", "RE-ENTRY signals", "Buy back when 2 of 3 are true"),
              ("hold", "STOP-LOOP / HOLD", "Just hold when 2 of 3 are true")]
    for key, label, sub in GROUPS:
        n = result["counts"][key]
        with st.expander(f"{label} — {n}/3 met", expanded=(n >= 2)):
            st.caption(sub)
            for s in result["signals"][key]:
                st.markdown(("✅ " if s["met"] else "▫️ ") + s["reason"])

    plan = result.get("reentry_plan")
    if plan:
        st.divider()
        st.subheader("Re-entry plan")
        st.caption(f"Basis: {plan['basis']}")
        p1, p2, p3 = st.columns(3)
        p1.metric("Reserve to buy back", f"${plan['reserve_budget']:,.2f}")
        p2.metric("Realized/projected profit", f"${plan['profit']:+,.2f}")
        p3.metric("Sold", f"${plan['sell_price']:.2f} × {plan['shares_sold']}")
        st.caption(esc(f"Reserve = original cost ${plan['original_cost']:,.2f} + "
                       f"{plan['reinvest_profit_pct']*100:.0f}% of profit, never less than original."))
        for s in plan["sizing"]:
            st.markdown(esc(f"- **{s['level']}** ~${s['price']:.2f} → **{s['whole_shares']} whole** / "
                            f"{s['total_shares']:.2f} total shares ({s['vs_original']:+.2f} vs sold)"))
        st.info(plan["note"])

    # --- Phase 3b: earnings, financials, news ---
    st.divider()
    st.subheader("Earnings")
    nxt = result.get("next_earnings")
    st.markdown(f"**Next earnings:** {nxt}" if nxt
                else "**Next earnings:** not set — add `next_earnings` (YYYY-MM-DD) in config.json.")
    moves = result.get("big_moves") or []
    if moves:
        st.markdown("**Biggest recent daily moves** (usually earnings reactions):")
        for m in moves:
            arrow = "🔺" if m["pct"] >= 0 else "🔻"
            st.markdown(f"- {arrow} **{m['pct']:+.1f}%** ({m['points']:+.2f} pts) on {m['date']}")

    r = detail.get("ratios")
    if r:
        def fmt(v, money=False, pct=False):
            if v is None:
                return "—"
            if money:
                return f"${v/1e9:,.1f}B" if abs(v) >= 1e9 else f"${v:,.0f}"
            if pct:
                return f"{v*100:.1f}%"
            return f"{v:,.2f}"
        st.divider()
        st.subheader("Snapshot")
        s1, s2, s3 = st.columns(3)
        s1.metric("Market cap", fmt(r.get("market_cap"), money=True),
                  help="Total value of all shares (price × shares outstanding). "
                       ">$200B mega-cap, $10–200B large-cap, $2–10B mid, <$2B small/micro.")
        s2.metric("EPS (TTM)", fmt(r.get("earnings_per_share")),
                  help="Earnings per share over the trailing 12 months — company profit "
                       "divided by shares. No fixed 'range'; higher and rising is better, "
                       "and price ÷ EPS = the P/E. Negative EPS means it's lossmaking.")
        s3.metric("Dividend yield", fmt(r.get("dividend_yield"), pct=True),
                  help="Annual dividend ÷ price. 0% = pays none (common for growth/tech), "
                       "1–3% typical, >5% high (check it's sustainable).")
        st.caption(f"TTM ratios as of {r.get('date', '—')}.")

    st.divider()
    st.subheader("News & sentiment")
    news = detail.get("news") or []
    if news:
        dig = fundamentals.news_digest(news, result["price"], result["ema_short"],
                                       result["ema_long"], result["rsi"])
        if dig:
            net_color = {"Positive": "#0b6e3b", "Leaning positive": "#0b6e3b",
                         "Negative": "#b00020", "Leaning negative": "#b00020",
                         "Mixed / neutral": "#c77700", "Unrated": "#5a5a5a"}.get(dig["net"], "#5a5a5a")
            c = dig["counts"]
            st.markdown(
                f"<span style='background:{net_color};color:#fff;padding:3px 10px;border-radius:9px;"
                f"font-size:13px;font-weight:600'>{dig['net']}</span> "
                f"<span style='color:gray;font-size:13px'>&nbsp;{c['positive']}▲ / {c['neutral']}• / "
                f"{c['negative']}▼ across {c['total']} recent articles</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Momentum:** {dig['momentum']}")
            if dig["themes"]:
                st.markdown("**Themes:** " + " · ".join(dig["themes"]))
            st.write("")
        for a in news[:6]:
            tag = f" · _{a['sentiment']}_" if a.get("sentiment") else ""
            meta = " · ".join(x for x in (a.get("publisher"), a.get("published")) if x)
            link = a.get("url")
            title = f"[{a['title']}]({link})" if link else a["title"]
            st.markdown(esc(f"- {title}  \n  <span style='color:gray;font-size:12px'>{meta}{tag}</span>"),
                        unsafe_allow_html=True)
    elif detail.get("errors", {}).get("news"):
        st.caption(f"News unavailable: {detail['errors']['news']}")
    else:
        st.caption("No recent news returned.")


# --------------------------------------------------------------------------- #
# Portfolio row (home page)
# --------------------------------------------------------------------------- #
def render_row(result):
    gain = pl_pct(result)
    with st.container(border=True):
        c = st.columns([1.1, 1.6, 4.3, 1.0])
        with c[0]:
            badge(result["headline"])
        with c[1]:
            st.markdown(esc(f"**{result['ticker']}**  ${result['price']:.2f}"
                            + (f"  ({gain:+.0f}%)" if gain is not None else "")))
        with c[2]:
            st.markdown(result["top_reason"])
        with c[3]:
            if st.button("Open ▸", key=f"open_{result['ticker']}", use_container_width=True):
                st.session_state.detail = result["ticker"]
                st.rerun()
        with st.expander("▾ details"):
            st.markdown(
                f"RSI **{result['rsi']:.0f}** · EMA20 ${result['ema_short']:.2f} · "
                f"EMA50 ${result['ema_long']:.2f}  \n"
                f"Signals — sell {result['counts']['sell']}/3 · "
                f"re-entry {result['counts']['reentry']}/3 · hold {result['counts']['hold']}/3  \n"
                f"_{result['action']}_"
            )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
top = st.columns([3, 1])
with top[0]:
    st.title("🔁 LOOPER")
    st.caption("Phase 3 — portfolio of active loops")
with top[1]:
    st.write("")
    if st.button("🔄 Refresh all", use_container_width=True):
        with st.spinner("Pulling latest data from Massive for every stock…"):
            try:
                res, errs = engine.run_all()
                st.session_state.results = res
                st.session_state.errors = errs
                st.session_state.detail = None
            except Exception as e:
                st.error(f"Refresh failed: {e}")
        st.rerun()

# Detail view takes over the page when a stock is selected
if st.session_state.detail:
    r = get_result(st.session_state.detail)
    if r:
        render_detail(r)
        st.stop()
    else:
        st.session_state.detail = None

if not st.session_state.results:
    st.info("No data yet. Click **Refresh all** to run the first check on every stock in config.json.")
    st.stop()

for e in st.session_state.errors or []:
    st.error(f"{e['ticker']}: {e['error']}")

sells = sorted([r for r in st.session_state.results if r["side"] == "sell"],
               key=lambda x: -x["urgency"])
buys = sorted([r for r in st.session_state.results if r["side"] == "buy"],
              key=lambda x: -x["urgency"])

left, right = st.columns(2)
with left:
    st.subheader(f"🔴 Sell watch ({len(sells)})")
    st.caption("Positions you hold — most urgent to sell on top")
    if sells:
        for r in sells:
            render_row(r)
    else:
        st.caption("No held positions.")
with right:
    st.subheader(f"🟢 Buy / re-entry ({len(buys)})")
    st.caption("Cash waiting to re-enter — closest to a buy on top")
    if buys:
        for r in buys:
            render_row(r)
    else:
        st.caption("Nothing in cash yet. Flip a stock's state to \"cash\" in config.json "
                   "after you sell, and it shows up here.")

st.divider()
st.caption("Signals are decision support, not financial advice. "
           "Add or edit stocks in config.json.")
