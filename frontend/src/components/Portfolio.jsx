import React, { useState, useEffect, useRef, useCallback } from 'react'
import { getWatchlist, addToWatchlist, removeFromWatchlist, startScan, scanStatus, getQuotes } from '../api'

// Auto-refresh interval options for the live price refresh (seconds; 0 = off)
const LIVE_INTERVALS = [[0, 'Off'], [3, '3s'], [5, '5s'], [10, '10s'], [30, '30s'], [60, '1m'], [300, '5m']]

// RSI condition read, reused across every scan subsection and sector drill-down.
const RSI_TAG = (rsi) => rsi == null ? { text: 'no data', cls: 'r-mid' }
  : rsi <= 40 ? { text: 'oversold', cls: 'r-low' }
  : rsi >= 68 ? { text: 'overbought', cls: 'r-high' }
  : { text: 'neutral', cls: 'r-mid' }

const SCAN_SORTS = [
  ['default', 'Sort: default'],
  ['mchg', '1-month (high→low)'],
  ['rsi', 'RSI (oversold first)'],
  ['price', 'Price (high→low)'],
  ['chg', 'Today % (high→low)'],
]

// Reusable scan subsection: title with inline show/hide + sort + type filter, then rows.
// This is the shared pattern for popular names, each bucket, and sector drill-downs.
function ScanSection({ title, rows, onAddToWatchlist, onOpen, defaultSort = 'default' }) {
  const [collapsed, setCollapsed] = useState(false)
  const [sort, setSort] = useState(defaultSort)
  const [type, setType] = useState('all')   // all | oversold | neutral | overbought

  let list = type === 'all' ? rows : rows.filter(r => RSI_TAG(r.rsi).text === type)
  if (sort === 'rsi') list = [...list].sort((a, b) => (a.rsi ?? 999) - (b.rsi ?? 999))
  else if (sort === 'price') list = [...list].sort((a, b) => b.price - a.price)
  else if (sort === 'chg') list = [...list].sort((a, b) => b.change_pct - a.change_pct)
  else if (sort === 'mchg') list = [...list].sort((a, b) => (b.mchg ?? -999) - (a.mchg ?? -999))

  return (
    <div className="scanbucket">
      <div className="scanhead">
        <h4>{title} <span className="muted">({rows.length})</span></h4>
        <div className="scanctl">
          <select value={type} onChange={e => setType(e.target.value)} title="Filter by RSI condition">
            <option value="all">Type: all</option>
            <option value="oversold">Oversold</option>
            <option value="neutral">Neutral</option>
            <option value="overbought">Overbought</option>
          </select>
          <select value={sort} onChange={e => setSort(e.target.value)} title="Sort these names">
            {SCAN_SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button className="link" onClick={() => setCollapsed(c => !c)}>{collapsed ? 'show' : 'hide'}</button>
        </div>
      </div>
      {!collapsed && list.map(r => {
        const tag = RSI_TAG(r.rsi)
        return (
          <div className="scanrow" key={r.ticker}>
            <button className="tkr tkrlink" title={`Open deep analysis for ${r.ticker}`}
                    onClick={() => onOpen && onOpen(r.ticker)}>{r.ticker}</button>
            <span className="px">
              ${r.price.toFixed(2)} · {r.change_pct >= 0 ? '+' : ''}{r.change_pct}%
              {r.rsi != null && ` · RSI ${Math.round(r.rsi)}`}
              {r.mchg != null && <> · <b className={r.mchg >= 0 ? 'pos' : 'neg'}>1mo {r.mchg >= 0 ? '+' : ''}{r.mchg}%</b></>}
              {r.uptrend ? ' · uptrend' : ''}
              <span className={`rtag ${tag.cls}`}>{tag.text}</span>
            </span>
            <button className="link" onClick={() => onAddToWatchlist(r.ticker)}>+ watch</button>
          </div>
        )
      })}
      {!collapsed && list.length === 0 && <p className="muted small">None match this filter.</p>}
    </div>
  )
}

// ---- Deep Opportunity Scan panel (whole-market, with progress + themes) ----
function OpportunityScan({ onAddToWatchlist, onOpen }) {
  const [st, setSt] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [openTheme, setOpenTheme] = useState(null)   // sector drilled into
  const pollRef = useRef(null)

  const load = () => scanStatus().then(setSt).catch(() => {})
  useEffect(() => { load() }, [])

  // poll while a scan is running
  useEffect(() => {
    if (st?.running && !pollRef.current) {
      pollRef.current = setInterval(load, 1500)
    } else if (!st?.running && pollRef.current) {
      clearInterval(pollRef.current); pollRef.current = null
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [st?.running])

  // elapsed timer
  useEffect(() => {
    if (!st?.running || !st?.started) return
    const start = new Date(st.started).getTime()
    const id = setInterval(() => setElapsed(Math.round((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(id)
  }, [st?.running, st?.started])

  const run = async () => { try { await startScan(); await load() } catch { /* ignore */ } }

  const results = st?.results || []
  const themes = st?.themes || []
  const pct = st?.total ? Math.round((st.progress / st.total) * 100) : 8
  const buckets = [
    ['buy-low', '↓ Buy-low — oversold pullbacks (your entries)'],
    ['momentum', '↑ Momentum — breaking out on volume (hot names)'],
    ['overbought', '⚠ Overbought — extended (take profit / don’t chase)'],
  ]

  return (
    <div>
      <div className="scanbar">
        <button onClick={run} disabled={st?.running}>{st?.running ? 'Scanning…' : '⟳ Run deep scan'}</button>
        {st?.running && (
          <span className="scanprog">
            <span className="pbar"><span className="pfill" style={{ width: `${pct}%` }} /></span>
            {st.stage === 'snapshot' ? 'pulling market snapshot…'
              : st.stage === 'momentum' ? 'checking 1-month trends…'
              : st.stage === 'themes' ? 'checking sector leaders…'
              : `analyzing ${st.progress}/${st.total}`} · {elapsed}s
          </span>
        )}
        {!st?.running && st?.finished && (
          <span className="muted small">
            scanned {(st.scanned_universe || 0).toLocaleString()} stocks · {new Date(st.finished).toLocaleString()}
          </span>
        )}
      </div>
      {st?.error && <div className="error" style={{ margin: '0 0 12px' }}>Scan error: {st.error}</div>}

      {(results.length > 0 || themes.length > 0) && (
        <p className="muted small scanlegend">
          {st?.finished && <>As of <b>{new Date(st.finished).toLocaleString()}</b> — click ⟳ to refresh · </>}
          Click a ticker for deep analysis. RSI = momentum (≤40 oversold · ≥68 overbought).
          % = today’s change{st?.month_date ? `; 1mo = since ${st.month_date}` : '; 1mo = ~1-month change'}.
        </p>
      )}

      {themes.length > 0 && (() => {
        const openT = themes.find(t => t.theme === openTheme)
        return (
          <>
            <div className="themes">
              <span className="muted small" style={{ marginRight: 4 }}>Sector heat:</span>
              {themes.map(t => (
                <button key={t.theme}
                        className={`theme t-${t.state} ${openTheme === t.theme ? 'sel' : ''}`}
                        title={`${t.up}/${t.count} up today — click to see the names`}
                        onClick={() => setOpenTheme(openTheme === t.theme ? null : t.theme)}>
                  {t.theme} <b>{t.avg_chg >= 0 ? '+' : ''}{t.avg_chg}%</b>
                </button>
              ))}
            </div>
            {openT && (openT.stocks?.length
              ? <ScanSection title={`${openT.theme} — sector names`} rows={openT.stocks}
                             onAddToWatchlist={onAddToWatchlist} onOpen={onOpen} defaultSort="rsi" />
              : <p className="muted small">No names to show for {openT.theme} in this scan.</p>)}
          </>
        )
      })()}

      {results.filter(r => r.popular).length > 0 && (
        <ScanSection title="★ Popular names — at a glance"
                     rows={results.filter(r => r.popular)}
                     onAddToWatchlist={onAddToWatchlist} onOpen={onOpen} defaultSort="rsi" />
      )}

      {results.filter(r => r.mchg != null && r.mchg >= 12).length > 0 && (
        <ScanSection title="↑ Monthly climbers — trending up over ~1 month"
                     rows={results.filter(r => r.mchg != null && r.mchg >= 12)}
                     onAddToWatchlist={onAddToWatchlist} onOpen={onOpen} defaultSort="mchg" />
      )}

      {buckets.map(([b, label]) => {
        const rows = results.filter(r => r.bucket === b && !r.popular)
        if (!rows.length) return null
        return <ScanSection key={b} title={label} rows={rows}
                            onAddToWatchlist={onAddToWatchlist} onOpen={onOpen} />
      })}

      {!st?.running && results.length === 0 && !st?.error && (
        st?.finished
          ? <p className="muted">Scan found 0 candidates (scanned {(st.scanned_universe || 0).toLocaleString()} names). Market data can be thin outside trading hours — try again during market hours.</p>
          : <p className="muted">No scan yet — click “Run deep scan”. It analyzes the whole market (~30–60s).</p>
      )}
    </div>
  )
}

const COLORS = {
  'SELL SIGNAL': '#C13B2B', 'WATCH': '#B07515', 'RE-ENTRY ZONE': '#1B7F49',
  'RE-ENTRY WATCH': '#B07515', 'HOLD': '#C8643F', 'WAIT': '#8C8A82',
}

function VisBar({ list, hidden, onToggle, onShowAll, onHideAll }) {
  return (
    <div className="visbar">
      <button className="link" onClick={onShowAll} title="Show all boxes">show all</button>
      <span className="vsep">·</span>
      <button className="link" onClick={onHideAll} title="Hide all boxes">hide all</button>
      {list.map(r => (
        <button key={r.ticker}
          className={`vchip ${hidden.has(r.ticker) ? 'off' : ''}`}
          title={hidden.has(r.ticker) ? `Show ${r.ticker}` : `Hide ${r.ticker}`}
          onClick={() => onToggle(r.ticker)}>{r.ticker}</button>
      ))}
    </div>
  )
}

// Turn the raw signal + your position into a plain-English hold / sell / add / buy-back
// steer, shown right on the box. Decision support, not advice — uses only your entry,
// the current price, RSI and the analyst target.
function decide(r) {
  const pos = r.position || {}
  const held = r.side === 'sell'
  const h = r.headline || ''
  const rsi = Math.round(r.rsi)
  if (held) {
    const entry = pos.entry_price
    const gp = entry ? (r.price / entry - 1) * 100 : null
    const upside = r.analyst_target ? (r.analyst_target / r.price - 1) * 100 : null
    if (h.startsWith('SELL'))
      return { label: gp != null && gp >= 0 ? 'Sell — take profit' : 'Sell signal', tone: 'danger',
        tip: gp != null
          ? (gp >= 0 ? `Exit signals firing while you're up ${gp.toFixed(0)}% — consider locking in the gain.`
                     : `Sell signals while down ${Math.abs(gp).toFixed(0)}% — reassess the thesis or cut the loss.`)
          : 'Sell signals are firing — consider taking profit.' }
    if (h === 'WATCH')
      return { label: 'Trim / tighten', tone: 'warn',
        tip: `Getting toppy (RSI ${rsi}) — consider trimming some or tightening your stop.` }
    if (gp != null && gp <= -8 && r.rsi <= 40)
      return { label: 'Hold / add', tone: 'hold',
        tip: `Down ${Math.abs(gp).toFixed(0)}% and oversold${upside ? `, ~${upside.toFixed(0)}% to target` : ''} — hold, or add if conviction is high.` }
    return { label: 'Hold', tone: 'hold', tip: r.top_reason || 'Trend intact — hold.' }
  }
  const last = pos.last_sell_price
  const vs = last ? (r.price / last - 1) * 100 : null
  if (h.startsWith('RE-ENTRY ZONE'))
    return { label: 'Buy back', tone: 'good',
      tip: last ? `Now ${vs <= 0 ? `${Math.abs(vs).toFixed(0)}% below` : `${vs.toFixed(0)}% above`} your $${last} exit — re-entry zone reached.` : 'Re-entry zone reached — consider buying back.' }
  if (h.includes('WATCH'))
    return { label: 'Almost — get ready', tone: 'warn', tip: `Approaching your re-entry zone (RSI ${rsi}).` }
  return { label: 'Wait', tone: 'muted',
    tip: last ? `Sold at $${last}; now $${r.price.toFixed(2)} — not cheap enough yet.` : 'Waiting for a better level.' }
}

function Row({ r, onOpen, open, onToggle }) {
  const pos = r.position || {}
  const held = r.side === 'sell'
  const entry = pos.entry_price
  const shares = pos.shares
  const gp = entry ? (r.price / entry - 1) * 100 : null
  const gAbs = (entry && shares) ? (r.price - entry) * shares : null
  const last = pos.last_sell_price
  const vs = last ? (r.price / last - 1) * 100 : null             // now vs your sell price
  const vsAbs = (last && shares) ? (r.price - last) * shares : null // $ swing on your sold size
  const saleGain = (entry && last && shares) ? (last - entry) * shares : null  // made at sale
  const saleGainPct = (entry && last) ? (last / entry - 1) * 100 : null
  const d = decide(r)
  const urg = r.urgency > 0.8 ? '🔥' : r.urgency > 0.5 ? '⚠️' : '•'

  const plText = gAbs != null
    ? `${gAbs >= 0 ? '+' : '-'}$${Math.abs(gAbs).toFixed(2)} (${gp >= 0 ? '+' : '-'}${Math.abs(gp).toFixed(0)}%)`
    : gp != null ? `${gp >= 0 ? '+' : '-'}${Math.abs(gp).toFixed(0)}%` : null

  // Re-entry pill: price ABOVE your exit = red (ran away), BELOW = green (cheaper to rebuy)
  const exitText = vs != null
    ? `${vs > 0 ? '+' : ''}${vs.toFixed(1)}%${vsAbs != null ? ` · ${vsAbs >= 0 ? '+' : '-'}$${Math.abs(vsAbs).toFixed(2)}` : ''} vs exit`
    : null

  return (
    <div className={`row t-${d.tone} ${open ? 'is-open' : ''}`}>
      <div className="rowmain" onClick={onToggle} style={{ cursor: 'pointer' }}>
        <span className="chev">{open ? '▾' : '▸'}</span>
        <span className="urg">{urg}</span>
        <span className="badge" style={{ background: COLORS[r.headline] || '#C8643F' }}>
          {r.headline.split(' ')[0]}
        </span>
        <span className="tkr">{r.ticker}</span>
        <span className="px">${r.price.toFixed(2)}</span>
        <span className="rowright">
          {held && plText && <span className={`pl ${gp >= 0 ? 'pos' : 'neg'}`}>{plText}</span>}
          {!held && exitText && (
            <span className={`exit ${vs > 0 ? 'neg' : 'pos'}`}>{exitText}</span>
          )}
          <span className={`decis t-${d.tone}`}>{d.label}</span>
        </span>
      </div>

      <div className="rowsub">
        <span className="tip">{d.tip}</span>
        <span className="metric">
          RSI {Math.round(r.rsi)}
          {held && entry ? ` · in @ $${entry.toFixed(2)}`
            : (!held && last
              ? ` · out @ $${last}${saleGain != null ? ` · made ${saleGain >= 0 ? '+' : '-'}$${Math.abs(saleGain).toFixed(2)} (${saleGainPct >= 0 ? '+' : ''}${saleGainPct.toFixed(0)}%)` : ''}`
              : '')}
        </span>
      </div>

      {r.alert && (
        <div className={`alert-box lvl-${r.alert.level}`}>
          <strong>⚑ {r.alert.title}</strong>
          {r.alert.move_pct != null && <span className="amove"> · {r.alert.move_pct >= 0 ? '+' : ''}{r.alert.move_pct}%</span>}
          {r.alert.headline && <span className="ah"> — {r.alert.headline}</span>}
          <div className="asug">{r.alert.suggestion}</div>
        </div>
      )}

      {open && (
        <div className="rowdetail">
          <strong>Signals:</strong> RSI {r.rsi.toFixed(0)} · EMA20 ${r.ema_short.toFixed(2)} · EMA50 ${r.ema_long.toFixed(2)}<br/>
          <strong>Counts:</strong> sell {r.counts.sell}/3 · re-entry {r.counts.reentry}/3 · hold {r.counts.hold}/3<br/>
          <em style={{ color: 'var(--text-secondary)', marginTop: '4px', display: 'block' }}>{r.action}</em>
          {r.data_limited && (
            <span style={{ color: 'var(--warning)', fontSize: '11px', display: 'block', marginTop: '4px' }}>
              ⚠ limited price history — indicators are approximate.
            </span>
          )}
          <button className="open" onClick={(e) => { e.stopPropagation(); onOpen(r.ticker) }} style={{ marginTop: '8px' }}>
            Full analysis ▸
          </button>
        </div>
      )}
    </div>
  )
}

function CandidateRow({ c, onAddToWatchlist }) {
  const [adding, setAdding] = useState(false)
  const isBuy = c.side === 'buy'

  return (
    <div className="row">
      <div className="rowmain">
        <span className="badge" style={{ background: isBuy ? '#1B7F49' : '#B07515' }}>
          {c.category.toUpperCase()}
        </span>
        <span className="tkr">{c.ticker}</span>
        <span className="px">
          ${c.price.toFixed(2)} · {c.change_pct >= 0 ? '+' : ''}{c.change_pct}% today
          {c.rsi != null && ` · RSI ${Math.round(c.rsi)}`}
        </span>
        <span style={{ flex: 1, fontSize: '13px', color: 'var(--text-secondary)' }}>
          {isBuy ? '↓ big drop — potential buy-low' : '↑ big pop — potential take-profit'}
        </span>
        <button
          onClick={() => {
            setAdding(true)
            onAddToWatchlist(c.ticker)
            setTimeout(() => setAdding(false), 1000)
          }}
          disabled={adding}
          style={{ marginLeft: '8px' }}
        >
          {adding ? '✓ Added' : '+ Watch'}
        </button>
      </div>
    </div>
  )
}

function WatchlistRow({ w, onRemove, onOpen }) {
  const sig = w.signal
  return (
    <div className="row">
      <div className="rowmain">
        {sig ? (
          <span className="badge" style={{ background: COLORS[sig.headline] || '#C8643F' }}>
            {sig.headline.split(' ')[0]}
          </span>
        ) : (
          <span className="badge" style={{ background: '#8C8A82' }}>{w.signal_error ? 'N/A' : '…'}</span>
        )}
        <span className="tkr">{w.ticker}</span>
        {sig ? (
          <span className="px">${sig.price.toFixed(2)} | RSI {sig.rsi.toFixed(0)}</span>
        ) : (
          <span className="px muted">{w.signal_error ? 'no data' : 'loading…'}</span>
        )}
        <span className="reason">{sig ? sig.top_reason : (w.notes || '')}</span>
        {sig && <button className="open" onClick={() => onOpen(w.ticker)}>Analyze ▸</button>}
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
          added {new Date(w.added_date).toLocaleDateString()}
        </span>
        <button className="link danger" onClick={() => onRemove(w.ticker)} style={{ marginLeft: '8px' }}>
          remove
        </button>
      </div>
    </div>
  )
}

export default function Portfolio({ data, onOpen }) {
  const [watchlist, setWatchlist] = useState([])
  const [dismissedErrors, setDismissedErrors] = useState(new Set())
  const [manualTicker, setManualTicker] = useState('')
  const [wlMsg, setWlMsg] = useState(null)
  const [showScanner, setShowScanner] = useState(false)
  const [showWatch, setShowWatch] = useState(false)
  const [expanded, setExpanded] = useState(() => new Set())   // expanded row tickers
  const [hidden, setHidden] = useState(
    () => new Set(JSON.parse(localStorage.getItem('looperHidden') || '[]'))
  )
  // Live price refresh for the Sell/Buy boxes only (fast, no full re-evaluation)
  const [quotes, setQuotes] = useState({})          // { TICKER: {price, change_pct} }
  const [liveSec, setLiveSec] = useState(
    () => Number(localStorage.getItem('looperLiveSec')) || 0
  )
  const [liveBusy, setLiveBusy] = useState(false)
  const [liveAt, setLiveAt] = useState(null)
  const [liveErr, setLiveErr] = useState(false)
  const liveTick = useRef(null)

  const toggleRow = (t) => setExpanded(prev => {
    const n = new Set(prev); n.has(t) ? n.delete(t) : n.add(t); return n
  })
  const expandAll = (list) => setExpanded(prev => new Set([...prev, ...list.map(r => r.ticker)]))
  const collapseAll = (list) => setExpanded(prev => {
    const n = new Set(prev); list.forEach(r => n.delete(r.ticker)); return n
  })
  const persistHidden = (s) => localStorage.setItem('looperHidden', JSON.stringify([...s]))
  const toggleHide = (t) => setHidden(prev => { const n = new Set(prev); n.has(t) ? n.delete(t) : n.add(t); persistHidden(n); return n })
  const hideAll = (list) => setHidden(prev => { const n = new Set(prev); list.forEach(r => n.add(r.ticker)); persistHidden(n); return n })
  const showAll = (list) => setHidden(prev => { const n = new Set(prev); list.forEach(r => n.delete(r.ticker)); persistHidden(n); return n })

  // Overlay any live quotes onto the latest full evaluation (updates price → P/L +
  // the decision tip; RSI/signals stay from the last full refresh).
  const results = (data.results || []).map(r => {
    const q = quotes[r.ticker]
    return q ? { ...r, price: q.price } : r
  })
  const errors = (data.errors || []).filter(e => !dismissedErrors.has(e.ticker))
  const sells = results.filter(r => r.side === 'sell').sort((a, b) => b.urgency - a.urgency)
  const buys = results.filter(r => r.side === 'buy').sort((a, b) => b.urgency - a.urgency)
  const visibleSells = sells.filter(r => !hidden.has(r.ticker))
  const visibleBuys = buys.filter(r => !hidden.has(r.ticker))

  // Fast refresh of ONLY the Sell/Buy box prices (one quotes call, no re-eval).
  const refreshPrices = useCallback(async () => {
    const tickers = (data.results || []).map(r => r.ticker)
    if (!tickers.length) return
    setLiveBusy(true); setLiveErr(false)
    try {
      const d = await getQuotes(tickers)
      setQuotes(d.quotes || {})
      setLiveAt(Date.now())
    } catch { setLiveErr(true) } finally { setLiveBusy(false) }
  }, [data])

  // Auto-refresh loop at the chosen interval (immediate hit, then every N seconds).
  useEffect(() => {
    if (liveTick.current) { clearInterval(liveTick.current); liveTick.current = null }
    if (liveSec > 0) {
      refreshPrices()
      liveTick.current = setInterval(refreshPrices, liveSec * 1000)
    }
    return () => { if (liveTick.current) { clearInterval(liveTick.current); liveTick.current = null } }
  }, [liveSec, refreshPrices])

  useEffect(() => { localStorage.setItem('looperLiveSec', String(liveSec)) }, [liveSec])
  // A full refresh brings fresh prices — drop the live overlay so nothing goes stale.
  useEffect(() => { setQuotes({}); setLiveAt(null) }, [data])

  useEffect(() => {
    getWatchlist().then(d => setWatchlist(d.watchlist || [])).catch(() => setWatchlist([]))
  }, [])

  const handleAddToWatchlist = async (ticker) => {
    try {
      await addToWatchlist(ticker, null)
      const w = await getWatchlist()
      setWatchlist(w.watchlist || [])
    } catch (err) {
      console.error('Error adding to watchlist:', err)
    }
  }

  const handleRemoveFromWatchlist = async (ticker) => {
    try {
      await removeFromWatchlist(ticker)
      const w = await getWatchlist()
      setWatchlist(w.watchlist || [])
    } catch (err) {
      console.error('Error removing from watchlist:', err)
    }
  }

  const addManual = async (e) => {
    e.preventDefault()
    const t = manualTicker.trim().toUpperCase()
    if (!t) return
    setWlMsg('Adding…')
    try {
      await addToWatchlist(t, null)
      const w = await getWatchlist()
      setWatchlist(w.watchlist || [])
      setManualTicker('')
      setWlMsg(`Added ${t} to your watchlist.`)
    } catch (err) {
      setWlMsg(err.message)
    }
  }

  const dismissError = (ticker) => {
    setDismissedErrors(new Set([...dismissedErrors, ticker]))
  }

  const clearAllErrors = () => {
    setDismissedErrors(new Set(errors.map(e => e.ticker)))
  }

  return (
    <div>
      {/* Errors with dismiss button */}
      {errors.length > 0 && (
        <div style={{ marginBottom: '16px' }}>
          {errors.map((e, i) => (
            <div className="error" key={i} style={{ margin: '0 0 8px 0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span><strong>{e.ticker}</strong> — {e.error}</span>
              <button className="link danger" onClick={() => dismissError(e.ticker)} style={{ marginLeft: '8px' }}>✕</button>
            </div>
          ))}
          {errors.length > 1 && (
            <button onClick={clearAllErrors} style={{ fontSize: '12px', marginTop: '8px' }}>
              Clear all errors
            </button>
          )}
        </div>
      )}

      {/* Live price refresh — Sell/Buy boxes only (fast; doesn't touch the rest) */}
      {results.length > 0 && (
        <div className="liverow">
          <button className="link" onClick={refreshPrices} disabled={liveBusy}
                  title="Refresh just the Sell/Buy prices — fast, and it won't reshuffle the rest">
            {liveBusy ? '↻ refreshing…' : '↻ refresh prices'}
          </button>
          <label className="livauto" title="Auto-refresh these prices on a timer">
            auto
            <select value={liveSec} onChange={e => setLiveSec(Number(e.target.value))}>
              {LIVE_INTERVALS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <span className="muted small">
            {liveErr ? 'couldn’t update prices'
              : liveAt ? `prices updated ${new Date(liveAt).toLocaleTimeString()}`
              : 'live prices · P/L only (full ↻ Refresh updates signals)'}
          </span>
        </div>
      )}

      {/* Portfolio sections */}
      <div className="cols">
        {/* Sell section */}
        <section>
          <h2 style={{ margin: '0 0 4px', borderTop: 'none', paddingTop: 0 }}>🔴 Sell Watch</h2>
          {sells.length > 0 && (
            <VisBar list={sells} hidden={hidden} onToggle={toggleHide}
                    onShowAll={() => showAll(sells)} onHideAll={() => hideAll(sells)} />
          )}
          {sells.length === 0 ? (
            <p className="muted" style={{ padding: '16px 0', textAlign: 'center', background: 'var(--surface-alt)', borderRadius: '8px' }}>
              No held positions yet.<br/>
              <span style={{ fontSize: '12px' }}>Add one using the sidebar form.</span>
            </p>
          ) : visibleSells.length === 0 ? (
            <p className="muted small">All hidden — click a ticker above to show it.</p>
          ) : (
            visibleSells.map(r => (
              <Row key={r.ticker} r={r} onOpen={onOpen}
                   open={expanded.has(r.ticker)} onToggle={() => toggleRow(r.ticker)} />
            ))
          )}
        </section>

        {/* Buy section */}
        <section>
          <h2 style={{ margin: '0 0 4px', borderTop: 'none', paddingTop: 0 }}>🟢 Re-Entry Zones</h2>
          {buys.length > 0 && (
            <VisBar list={buys} hidden={hidden} onToggle={toggleHide}
                    onShowAll={() => showAll(buys)} onHideAll={() => hideAll(buys)} />
          )}
          {buys.length === 0 ? (
            <p className="muted" style={{ padding: '16px 0', textAlign: 'center', background: 'var(--surface-alt)', borderRadius: '8px' }}>
              Nothing in cash waiting.<br/>
              <span style={{ fontSize: '12px' }}>Sell a position (change status to "cash") and it appears here.</span>
            </p>
          ) : visibleBuys.length === 0 ? (
            <p className="muted small">All hidden — click a ticker above to show it.</p>
          ) : (
            visibleBuys.map(r => (
              <Row key={r.ticker} r={r} onOpen={onOpen}
                   open={expanded.has(r.ticker)} onToggle={() => toggleRow(r.ticker)} />
            ))
          )}
        </section>
      </div>

      {/* Deep Opportunity Scan — collapsible */}
      <section className="collapse">
        <button className="secthead" onClick={() => setShowScanner(v => !v)}>
          <span>🔍 Opportunity Scan</span>
          <span className="chev">{showScanner ? '▾' : '▸'}</span>
        </button>
        {showScanner && (
          <div className="sectbody">
            <p className="sub">Deep whole-market scan — oversold buy-low pullbacks, hot momentum names, and sector-theme heat (quantum, semis, robotics…). Takes ~30–60s with a progress bar.</p>
            <OpportunityScan onAddToWatchlist={handleAddToWatchlist} onOpen={onOpen} />
          </div>
        )}
      </section>

      {/* Manual Watchlist — collapsible */}
      <section className="collapse">
        <button className="secthead" onClick={() => setShowWatch(v => !v)}>
          <span>📋 Your Watchlist {watchlist.length > 0 && <span className="count">({watchlist.length})</span>}</span>
          <span className="chev">{showWatch ? '▾' : '▸'}</span>
        </button>
        {showWatch && (
          <div className="sectbody">
            <p className="sub">Symbols you're monitoring for a buy (not positions you own) — live signals on your horizon</p>
            <form onSubmit={addManual} style={{ display: 'flex', gap: '8px', margin: '0 0 12px', maxWidth: '380px' }}>
              <input placeholder="Add a symbol, e.g. NVDA" value={manualTicker}
                     onChange={e => setManualTicker(e.target.value)} style={{ flex: 1 }} />
              <button type="submit">+ Add</button>
            </form>
            {wlMsg && <p className="muted small" style={{ margin: '-4px 0 10px' }}>{wlMsg}</p>}
            {watchlist.length > 0 ? (
              watchlist.map(w => (
                <WatchlistRow key={w.ticker} w={w} onRemove={handleRemoveFromWatchlist} onOpen={onOpen} />
              ))
            ) : (
              <p className="muted">Nothing on your watchlist yet — add a symbol above, or “+ Watch” one from the scanner.</p>
            )}
          </div>
        )}
      </section>
    </div>
  )
}
