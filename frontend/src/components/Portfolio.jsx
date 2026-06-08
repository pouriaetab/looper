import React, { useState } from 'react'

const COLORS = {
  'SELL SIGNAL': '#b00020', 'WATCH': '#c77700', 'RE-ENTRY ZONE': '#0b6e3b',
  'RE-ENTRY WATCH': '#c77700', 'HOLD': '#1f4e8c', 'WAIT': '#5a5a5a',
}

function Row({ r, onOpen }) {
  const [open, setOpen] = useState(false)
  const gain = r.position?.entry_price ? (r.price / r.position.entry_price - 1) * 100 : null
  return (
    <div className="row">
      <div className="rowmain">
        <span className="badge" style={{ background: COLORS[r.headline] || '#1f4e8c' }}>{r.headline}</span>
        <span className="tkr">{r.ticker}</span>
        <span className="px">
          ${r.price.toFixed(2)}{gain != null && ` (${gain >= 0 ? '+' : ''}${gain.toFixed(0)}%)`}
        </span>
        <span className="reason">{r.top_reason}</span>
        <button className="open" onClick={() => onOpen(r.ticker)}>Open ▸</button>
        <button className="chev" onClick={() => setOpen(!open)} aria-label="details">{open ? '▾' : '▸'}</button>
      </div>
      {open && (
        <div className="rowdetail">
          RSI {r.rsi.toFixed(0)} · EMA20 ${r.ema_short.toFixed(2)} · EMA50 ${r.ema_long.toFixed(2)}
          {' · '}sell {r.counts.sell}/3 · re-entry {r.counts.reentry}/3 · hold {r.counts.hold}/3
          <div className="muted"><em>{r.action}</em></div>
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
      {errors.map((e, i) => <div className="error" key={i}>{e.ticker}: {e.error}</div>)}
      <div className="cols">
        <section>
          <h2>🔴 Sell watch ({sells.length})</h2>
          <p className="sub">Positions you hold — most urgent to sell on top</p>
          {sells.length ? sells.map(r => <Row key={r.ticker} r={r} onOpen={onOpen} />)
            : <p className="muted">No held positions.</p>}
        </section>
        <section>
          <h2>🟢 Buy / re-entry ({buys.length})</h2>
          <p className="sub">Cash waiting to re-enter — closest to a buy on top</p>
          {buys.length ? buys.map(r => <Row key={r.ticker} r={r} onOpen={onOpen} />)
            : <p className="muted">Nothing in cash yet. Sell one (set its status to “cash”) and it appears here.</p>}
        </section>
      </div>
    </div>
  )
}
