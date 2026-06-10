import React, { useEffect, useState } from 'react'
import { getTally, getLedger } from '../api'

function money(n) {
  if (n == null || isNaN(n)) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

const num = (v) => (v === '' || v == null ? null : parseFloat(v))

// Which ledger column each money card breaks down into
const FIELD = {
  'Realized P/L': 'realized_profit',
  'Net profit taken': 'net_profit_taken',
  'Re-entry reserve': 'reentry_reserve',
}

function Card({ label, value, sub, tone, active, onClick }) {
  return (
    <div className={`tcard ${tone || ''} ${active ? 'active' : ''}`} onClick={onClick}
         role="button" tabIndex={0} title="Click to see the activity behind this number">
      <div className="tlabel">{label}</div>
      <div className="tvalue">{value}</div>
      {sub ? <div className="tsub">{sub}</div> : null}
    </div>
  )
}

function HoldingsTable({ holdings }) {
  return (
    <table className="ttable">
      <thead>
        <tr><th>Ticker</th><th>Shares</th><th>Entry</th><th>Last</th><th>Cost basis</th><th>Unrealized</th></tr>
      </thead>
      <tbody>
        {holdings.map(h => (
          <tr key={h.ticker}>
            <td>{h.ticker}</td><td>{h.shares}</td><td>{money(h.entry_price)}</td>
            <td>{h.last_price != null ? money(h.last_price) : '—'}</td>
            <td>{money(h.cost_basis)}</td>
            <td className={h.unrealized > 0 ? 'pos' : h.unrealized < 0 ? 'neg' : ''}>
              {h.unrealized != null ? money(h.unrealized) : '—'}
            </td>
          </tr>
        ))}
        {holdings.length === 0 && <tr><td colSpan={6} className="muted">No current holdings.</td></tr>}
      </tbody>
    </table>
  )
}

function LedgerTable({ rows, field }) {
  const sells = rows.filter(r => r.action === 'sell')
  const total = sells.reduce((s, r) => s + (num(r[field]) || 0), 0)
  return (
    <table className="ttable">
      <thead>
        <tr>
          <th>Date</th><th>Action</th><th>Ticker</th><th>Shares</th><th>Price</th><th>Entry</th>
          <th>Proceeds</th><th>Cost</th>
          <th className={field === 'realized_profit' ? 'hl' : ''}>Realized</th>
          <th className={field === 'net_profit_taken' ? 'hl' : ''}>Net taken</th>
          <th className={field === 'reentry_reserve' ? 'hl' : ''}>Reserve</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <td>{r.date}</td><td>{r.action}</td><td>{r.ticker}</td>
            <td>{r.shares}</td><td>{money(num(r.price))}</td><td>{money(num(r.entry_price))}</td>
            <td>{r.proceeds ? money(num(r.proceeds)) : '—'}</td>
            <td>{r.cost_basis ? money(num(r.cost_basis)) : '—'}</td>
            <td className={field === 'realized_profit' ? 'hl' : ''}>{r.realized_profit ? money(num(r.realized_profit)) : '—'}</td>
            <td className={field === 'net_profit_taken' ? 'hl' : ''}>{r.net_profit_taken ? money(num(r.net_profit_taken)) : '—'}</td>
            <td className={field === 'reentry_reserve' ? 'hl' : ''}>{r.reentry_reserve ? money(num(r.reentry_reserve)) : '—'}</td>
          </tr>
        ))}
        {rows.length === 0 && <tr><td colSpan={11} className="muted">No transactions yet.</td></tr>}
      </tbody>
      {sells.length > 0 && (
        <tfoot>
          <tr>
            <td colSpan={8} style={{ textAlign: 'right', fontWeight: 600 }}>Total</td>
            <td className={field === 'realized_profit' ? 'hl' : ''}>{field === 'realized_profit' ? money(total) : ''}</td>
            <td className={field === 'net_profit_taken' ? 'hl' : ''}>{field === 'net_profit_taken' ? money(total) : ''}</td>
            <td className={field === 'reentry_reserve' ? 'hl' : ''}>{field === 'reentry_reserve' ? money(total) : ''}</td>
          </tr>
        </tfoot>
      )}
    </table>
  )
}

export default function Tally({ refreshKey }) {
  const [t, setT] = useState(null)
  const [ledger, setLedger] = useState([])
  const [active, setActive] = useState(null)

  useEffect(() => {
    let alive = true
    getTally().then(d => { if (alive) setT(d) }).catch(() => {})
    getLedger().then(d => { if (alive) setLedger(d.rows || []) }).catch(() => {})
    return () => { alive = false }
  }, [refreshKey])

  if (!t) return null
  const tone = (n) => (n > 0 ? 'pos' : n < 0 ? 'neg' : '')
  const toggle = (label) => setActive(a => (a === label ? null : label))

  return (
    <div>
      <div className="tally">
        <Card label="Holdings" value={t.positions} active={active === 'Holdings'}
              onClick={() => toggle('Holdings')}
              sub={`${t.total_shares} shares · cost ${money(t.total_cost_basis)}`} />
        <Card label="Unrealized P/L" value={money(t.unrealized_profit)} tone={tone(t.unrealized_profit)}
              active={active === 'Unrealized P/L'} onClick={() => toggle('Unrealized P/L')}
              sub={t.unrealized_priced < t.unrealized_total
                ? `${t.unrealized_priced}/${t.unrealized_total} priced` : 'all priced'} />
        <Card label="Realized P/L" value={money(t.realized_profit)} tone={tone(t.realized_profit)}
              active={active === 'Realized P/L'} onClick={() => toggle('Realized P/L')}
              sub="from sold shares" />
        <Card label="Net profit taken" value={money(t.net_profit_taken)} tone={tone(t.net_profit_taken)}
              active={active === 'Net profit taken'} onClick={() => toggle('Net profit taken')}
              sub={`after ${Math.round(t.reinvest_profit_pct * 100)}% reinvest`} />
        <Card label="Re-entry reserve" value={money(t.reentry_reserve)}
              active={active === 'Re-entry reserve'} onClick={() => toggle('Re-entry reserve')}
              sub="cost + reinvested profit" />
      </div>

      {active && (
        <div className="tdetail">
          <div className="tdetail-head">
            <strong>{active} — details</strong>
            <button className="link" onClick={() => setActive(null)}>close ✕</button>
          </div>
          {(active === 'Holdings' || active === 'Unrealized P/L')
            ? <HoldingsTable holdings={t.holdings || []} />
            : <LedgerTable rows={ledger} field={FIELD[active]} />}
        </div>
      )}
    </div>
  )
}
