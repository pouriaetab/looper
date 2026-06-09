import React, { useEffect, useState } from 'react'
import { getTally } from '../api'

function money(n) {
  if (n == null || isNaN(n)) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function Card({ label, value, sub, tone }) {
  return (
    <div className={`tcard ${tone || ''}`}>
      <div className="tlabel">{label}</div>
      <div className="tvalue">{value}</div>
      {sub ? <div className="tsub">{sub}</div> : null}
    </div>
  )
}

export default function Tally({ refreshKey }) {
  const [t, setT] = useState(null)

  useEffect(() => {
    let alive = true
    getTally().then(d => { if (alive) setT(d) }).catch(() => {})
    return () => { alive = false }
  }, [refreshKey])

  if (!t) return null
  const tone = (n) => (n > 0 ? 'pos' : n < 0 ? 'neg' : '')

  return (
    <div className="tally">
      <Card label="Holdings" value={t.positions}
            sub={`${t.total_shares} shares · cost ${money(t.total_cost_basis)}`} />
      <Card label="Unrealized P/L" value={money(t.unrealized_profit)} tone={tone(t.unrealized_profit)}
            sub={t.unrealized_priced < t.unrealized_total
              ? `${t.unrealized_priced}/${t.unrealized_total} priced`
              : 'all priced'} />
      <Card label="Realized P/L" value={money(t.realized_profit)} tone={tone(t.realized_profit)}
            sub="from sold shares" />
      <Card label="Net profit taken" value={money(t.net_profit_taken)} tone={tone(t.net_profit_taken)}
            sub={`after ${Math.round(t.reinvest_profit_pct * 100)}% reinvest`} />
      <Card label="Re-entry reserve" value={money(t.reentry_reserve)}
            sub="cost + reinvested profit" />
    </div>
  )
}
