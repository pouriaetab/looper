import React, { useState, useEffect } from 'react'
import { getCandidates, getWatchlist, addToWatchlist, removeFromWatchlist } from '../api'

const COLORS = {
  'SELL SIGNAL': '#b00020', 'WATCH': '#c77700', 'RE-ENTRY ZONE': '#0b6e3b',
  'RE-ENTRY WATCH': '#c77700', 'HOLD': '#1f4e8c', 'WAIT': '#5a5a5a',
}

function Row({ r, onOpen }) {
  const [open, setOpen] = useState(false)
  const gain = r.position?.entry_price ? (r.price / r.position.entry_price - 1) * 100 : null
  const urgencyLabel = r.urgency > 0.8 ? '🔥' : r.urgency > 0.5 ? '⚠️' : '•'

  return (
    <div className="row">
      <div className="rowmain">
        <span style={{ fontSize: '16px' }}>{urgencyLabel}</span>
        <span className="badge" style={{ background: COLORS[r.headline] || '#1f4e8c' }}>
          {r.headline.split(' ')[0]}
        </span>
        <span className="tkr">{r.ticker}</span>
        <span className="px">
          ${r.price.toFixed(2)}{gain != null && ` (${gain >= 0 ? '+' : ''}${gain.toFixed(0)}%)`}
        </span>
        <span className="reason">{r.top_reason}</span>
        <button className="open" onClick={() => onOpen(r.ticker)}>Analyze ▸</button>
        <button className="chev" onClick={() => setOpen(!open)} aria-label="details">
          {open ? '▾' : '▸'}
        </button>
      </div>
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

  return (
    <div className="row">
      <div className="rowmain">
        <span className="badge" style={{
          background: c.category === 'oversold' ? '#0b6e3b' : '#c77700'
        }}>
          {c.category.toUpperCase()}
        </span>
        <span className="tkr">{c.ticker}</span>
        <span className="px">${c.price.toFixed(2)} | RSI {c.rsi.toFixed(0)}</span>
        <span style={{ flex: 1, fontSize: '13px', color: 'var(--text-secondary)' }}>
          {c.category === 'oversold' ? '↓ Good re-entry opportunity' : '↑ Consider taking profit'}
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
          <span className="badge" style={{ background: COLORS[sig.headline] || '#1f4e8c' }}>
            {sig.headline.split(' ')[0]}
          </span>
        ) : (
          <span className="badge" style={{ background: '#5a5a5a' }}>{w.signal_error ? 'N/A' : '…'}</span>
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
  const [candidates, setCandidates] = useState(null)   // null = not loaded yet
  const [watchlist, setWatchlist] = useState([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [dismissedErrors, setDismissedErrors] = useState(new Set())
  const [manualTicker, setManualTicker] = useState('')
  const [wlMsg, setWlMsg] = useState(null)
  const [showScanner, setShowScanner] = useState(false)
  const [showWatch, setShowWatch] = useState(false)

  const results = data.results || []
  const errors = (data.errors || []).filter(e => !dismissedErrors.has(e.ticker))
  const sells = results.filter(r => r.side === 'sell').sort((a, b) => b.urgency - a.urgency)
  const buys = results.filter(r => r.side === 'buy').sort((a, b) => b.urgency - a.urgency)

  // Watchlist is light — load it on mount. Scanner is heavy (scans ~32 tickers),
  // so only run it the first time you open that section.
  useEffect(() => {
    getWatchlist().then(d => setWatchlist(d.watchlist || [])).catch(() => setWatchlist([]))
  }, [])

  useEffect(() => {
    if (showScanner && candidates === null && !loadingCandidates) {
      setLoadingCandidates(true)
      getCandidates(8).then(d => setCandidates(d.candidates || []))
        .catch(() => setCandidates([])).finally(() => setLoadingCandidates(false))
    }
  }, [showScanner, candidates, loadingCandidates])

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
          <h2 style={{ margin: '0 0 4px 0', borderTop: 'none', paddingTop: 0 }}>
            🔴 Sell Watch
          </h2>
          <p className="sub">
            {sells.length} {sells.length === 1 ? 'position' : 'positions'} you hold — most urgent on top
          </p>
          {sells.length > 0 ? (
            sells.map(r => <Row key={r.ticker} r={r} onOpen={onOpen} />)
          ) : (
            <p className="muted" style={{ padding: '16px 0', textAlign: 'center', background: 'var(--surface-alt)', borderRadius: '8px' }}>
              No held positions yet.<br/>
              <span style={{ fontSize: '12px' }}>Add one using the sidebar form.</span>
            </p>
          )}
        </section>

        {/* Buy section */}
        <section>
          <h2 style={{ margin: '0 0 4px 0', borderTop: 'none', paddingTop: 0 }}>
            🟢 Re-Entry Zones
          </h2>
          <p className="sub">
            {buys.length} {buys.length === 1 ? 'position' : 'positions'} in cash — closest to buy on top
          </p>
          {buys.length > 0 ? (
            buys.map(r => <Row key={r.ticker} r={r} onOpen={onOpen} />)
          ) : (
            <p className="muted" style={{ padding: '16px 0', textAlign: 'center', background: 'var(--surface-alt)', borderRadius: '8px' }}>
              Nothing in cash waiting.<br/>
              <span style={{ fontSize: '12px' }}>Sell a position (change status to "cash") and it appears here.</span>
            </p>
          )}
        </section>
      </div>

      {/* Phase 4: Candidate Scanner — collapsible to keep the page short */}
      <section className="collapse">
        <button className="secthead" onClick={() => setShowScanner(v => !v)}>
          <span>🔍 Candidate Scanner</span>
          <span className="chev">{showScanner ? '▾' : '▸'}</span>
        </button>
        {showScanner && (
          <div className="sectbody">
            <p className="sub">Quality stocks oversold (re-entry) or overbought (take-profit), on your current horizon</p>
            {loadingCandidates ? (
              <p className="muted">Scanning the universe… (this takes a moment)</p>
            ) : (candidates && candidates.length > 0) ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '12px' }}>
                {candidates.map(c => (
                  <CandidateRow key={c.ticker} c={c} onAddToWatchlist={handleAddToWatchlist} />
                ))}
              </div>
            ) : (
              <p className="muted">No oversold or overbought names in the scan right now.</p>
            )}
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
