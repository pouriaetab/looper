import React, { useState } from 'react'

const COLORS = {
  'SELL SIGNAL': '#b00020', 'WATCH': '#c77700', 'RE-ENTRY ZONE': '#0b6e3b',
  'RE-ENTRY WATCH': '#c77700', 'HOLD': '#1f4e8c', 'WAIT': '#5a5a5a',
}

function Row({ r, onOpen }) {
  const [open, setOpen] = useState(false)
  const gain = r.position?.entry_price ? (r.price / r.position.entry_price - 1) * 100 : null
  const urgencyLabel = r.urgency > 0.8 ? '🔥' : r.urgency > 0.5 ? '⚠️' : '•'

  return (
    <div className=”row”>
      <div className=”rowmain”>
        <span style={{ fontSize: '16px' }}>{urgencyLabel}</span>
        <span className=”badge” style={{ background: COLORS[r.headline] || '#1f4e8c' }}>
          {r.headline.split(' ')[0]}
        </span>
        <span className=”tkr”>{r.ticker}</span>
        <span className=”px”>
          ${r.price.toFixed(2)}{gain != null && ` (${gain >= 0 ? '+' : ''}${gain.toFixed(0)}%)`}
        </span>
        <span className=”reason”>{r.top_reason}</span>
        <button className=”open” onClick={() => onOpen(r.ticker)}>Analyze ▸</button>
        <button className=”chev” onClick={() => setOpen(!open)} aria-label=”details”>
          {open ? '▾' : '▸'}
        </button>
      </div>
      {open && (
        <div className=”rowdetail”>
          <strong>Signals:</strong> RSI {r.rsi.toFixed(0)} · EMA20 ${r.ema_short.toFixed(2)} · EMA50 ${r.ema_long.toFixed(2)}<br/>
          <strong>Counts:</strong> sell {r.counts.sell}/3 · re-entry {r.counts.reentry}/3 · hold {r.counts.hold}/3<br/>
          <em style={{ color: 'var(--text-secondary)', marginTop: '4px', display: 'block' }}>{r.action}</em>
        </div>
      )}
    </div>
  )
}

export default function Portfolio({ data, onOpen }) {
  const results = data.results || []
  const errors = data.errors || []
  const sells = results.filter(r => r.side === 'sell').sort((a, b) => b.urgency - a.urgency)
  const buys = results.filter(r => r.side === 'buy').sort((a, b) => b.urgency - a.urgency)

  return (
    <div>
      {errors.map((e, i) => (
        <div className=”error” key={i} style={{ margin: '0 0 12px 0' }}>
          <strong>{e.ticker}</strong> — {e.error}
        </div>
      ))}

      <div className=”cols”>
        {/* Sell section */}
        <section>
          <h2 style={{ margin: '0 0 4px 0', borderTop: 'none', paddingTop: 0 }}>
            🔴 Sell Watch
          </h2>
          <p className=”sub”>
            {sells.length} {sells.length === 1 ? 'position' : 'positions'} you hold — most urgent on top
          </p>
          {sells.length > 0 ? (
            sells.map(r => <Row key={r.ticker} r={r} onOpen={onOpen} />)
          ) : (
            <p className=”muted” style={{ padding: '16px 0', textAlign: 'center', background: 'var(--surface-alt)', borderRadius: '8px' }}>
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
          <p className=”sub”>
            {buys.length} {buys.length === 1 ? 'position' : 'positions'} in cash — closest to buy on top
          </p>
          {buys.length > 0 ? (
            buys.map(r => <Row key={r.ticker} r={r} onOpen={onOpen} />)
          ) : (
            <p className=”muted” style={{ padding: '16px 0', textAlign: 'center', background: 'var(--surface-alt)', borderRadius: '8px' }}>
              Nothing in cash waiting.<br/>
              <span style={{ fontSize: '12px' }}>Sell a position (change status to “cash”) and it appears here.</span>
            </p>
          )}
        </section>
      </div>

      {/* Future: Candidate scanner section placeholder */}
      <section style={{ marginTop: '24px', padding: '16px', background: 'var(--surface-alt)', borderRadius: '10px', border: '1px dashed var(--border)' }}>
        <h2 style={{ margin: '0 0 8px 0', borderTop: 'none', paddingTop: 0 }}>
          🔍 Candidate Scanner (Coming soon)
        </h2>
        <p className=”muted” style={{ margin: 0 }}>
          Quality stocks that are oversold or overbought — good entry/watch opportunities. Phase 4 feature.
        </p>
      </section>
    </div>
  )
}
