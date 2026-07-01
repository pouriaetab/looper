import React, { useState, useEffect, useRef } from 'react'
import { getWatchlist, addToWatchlist, removeFromWatchlist, startScan, scanStatus } from '../api'

// ---- Deep Opportunity Scan panel (whole-market, with progress + themes) ----
function OpportunityScan({ onAddToWatchlist }) {
  const [st, setSt] = useState(null)
  const [elapsed, setElapsed] = useState(0)
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
            {st.stage === 'snapshot' ? 'pulling market snapshot…' : `analyzing ${st.progress}/${st.total}`} · {elapsed}s
          </span>
        )}
        {!st?.running && st?.finished && (
          <span className="muted small">
            scanned {(st.scanned_universe || 0).toLocaleString()} stocks · {new Date(st.finished).toLocaleString()}
          </span>
        )}
      </div>
      {st?.error && <div className="error" style={{ margin: '0 0 12px' }}>Scan error: {st.error}</div>}

      {themes.length > 0 && (
        <div className="themes">
          <span className="muted small" style={{ marginRight: 4 }}>Sector heat:</span>
          {themes.map(t => (
            <span key={t.theme} className={`theme t-${t.state}`} title={`${t.up}/${t.count} up today`}>
              {t.theme} <b>{t.avg_chg >= 0 ? '+' : ''}{t.avg_chg}%</b>
            </span>
          ))}
        </div>
      )}

      {buckets.map(([b, label]) => {
        const rows = results.filter(r => r.bucket === b)
        if (!rows.length) return null
        return (
          <div key={b} className="scanbucket">
            <h4>{label} <span className="muted">({rows.length})</span></h4>
            {rows.map(r => (
              <div className="scanrow" key={r.ticker}>
                <span className="tkr">{r.ticker}</span>
                <span className="px">
                  ${r.price.toFixed(2)} · {r.change_pct >= 0 ? '+' : ''}{r.change_pct}%
                  {r.rsi != null && ` · RSI ${Math.round(r.rsi)}`}{r.uptrend ? ' · uptrend' : ''}
                </span>
                <button className="link" onClick={() => onAddToWatchlist(r.ticker)}>+ watch</button>
              </div>
            ))}
          </div>
        )
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

function Row({ r, onOpen, open, onToggle }) {
  const gain = r.position?.entry_price ? (r.price / r.position.entry_price - 1) * 100 : null
  const urgencyLabel = r.urgency > 0.8 ? '🔥' : r.urgency > 0.5 ? '⚠️' : '•'

  return (
    <div className={`row ${open ? '' : 'row-collapsed'}`}>
      <div className="rowmain" onClick={onToggle} style={{ cursor: 'pointer' }}>
        <span className="chev">{open ? '▾' : '▸'}</span>
        <span style={{ fontSize: '15px' }}>{urgencyLabel}</span>
        <span className="badge" style={{ background: COLORS[r.headline] || '#C8643F' }}>
          {r.headline.split(' ')[0]}
        </span>
        <span className="tkr">{r.ticker}</span>
        <span className="px">
          ${r.price.toFixed(2)}{gain != null && ` (${gain >= 0 ? '+' : ''}${gain.toFixed(0)}%)`}
        </span>
        {open && <span className="reason">{r.top_reason}</span>}
        {open && (
          <button className="open" onClick={(e) => { e.stopPropagation(); onOpen(r.ticker) }}>
            Analyze ▸
          </button>
        )}
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

  const results = data.results || []
  const errors = (data.errors || []).filter(e => !dismissedErrors.has(e.ticker))
  const sells = results.filter(r => r.side === 'sell').sort((a, b) => b.urgency - a.urgency)
  const buys = results.filter(r => r.side === 'buy').sort((a, b) => b.urgency - a.urgency)
  const visibleSells = sells.filter(r => !hidden.has(r.ticker))
  const visibleBuys = buys.filter(r => !hidden.has(r.ticker))

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
            <OpportunityScan onAddToWatchlist={handleAddToWatchlist} />
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
