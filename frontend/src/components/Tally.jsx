import React, { useEffect, useState, useCallback } from 'react'
import { getTally, getLedger, updateLedgerRow, deleteLedgerRow } from '../api'

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

// Columns the user can edit inline (the ledger is the master history)
const EDIT_COLS = [
  'date', 'action', 'ticker', 'shares', 'price', 'entry_price',
  'proceeds', 'cost_basis', 'realized_profit', 'net_profit_taken',
  'reentry_reserve', 'reserve_used',
]

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
    <div className="tscroll">
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
    </div>
  )
}

function LedgerTable({ rows, field, onEdited }) {
  const isReserve = field === 'reentry_reserve'
  const hl = (f) => (field === f ? 'hl' : '')

  // filters
  const [fAction, setFAction] = useState('all')
  const [fTicker, setFTicker] = useState('all')
  const [fDate, setFDate] = useState('all')

  // inline editing
  const [editIdx, setEditIdx] = useState(null)
  const [draft, setDraft] = useState({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  // keep each row's original position so edits target the right CSV line
  const withIdx = rows.map((r, i) => ({ ...r, _idx: i }))
  const tickers = [...new Set(rows.map(r => r.ticker).filter(Boolean))].sort()
  const dates = [...new Set(rows.map(r => r.date).filter(Boolean))].sort()
  const actions = [...new Set(rows.map(r => r.action).filter(Boolean))].sort()

  const shown = withIdx.filter(r =>
    (fAction === 'all' || r.action === fAction) &&
    (fTicker === 'all' || r.ticker === fTicker) &&
    (fDate === 'all' || r.date === fDate))

  // Reserve summary always reflects the WHOLE ledger (not the filter) so it stays true
  const reserveAdded = rows.reduce((s, r) => s + (r.action === 'sell' ? (num(r.reentry_reserve) || 0) : 0), 0)
  const reserveUsed = rows.reduce((s, r) => s + (num(r.reserve_used) || 0), 0)
  const reserveRemaining = reserveAdded - reserveUsed
  // Realized / net totals reflect what's shown
  const shownSells = shown.filter(r => r.action === 'sell')
  const colTotal = shownSells.reduce((s, r) => s + (num(r[field]) || 0), 0)

  const startEdit = (r) => { setEditIdx(r._idx); setDraft({ ...r }); setErr(null) }
  const cancel = () => { setEditIdx(null); setDraft({}); setErr(null) }
  const dset = (k) => (e) => setDraft({ ...draft, [k]: e.target.value })

  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const patch = {}
      EDIT_COLS.forEach(k => { patch[k] = draft[k] ?? '' })
      await updateLedgerRow(editIdx, patch)
      cancel()
      onEdited && onEdited()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const del = async (idx) => {
    if (!window.confirm('Delete this ledger row? This edits the master history everywhere.')) return
    setBusy(true); setErr(null)
    try { await deleteLedgerRow(idx); if (editIdx === idx) cancel(); onEdited && onEdited() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const editing = (r) => editIdx === r._idx
  const txt = (r, k, render) => editing(r)
    ? <input className="ledit" value={draft[k] ?? ''} onChange={dset(k)} />
    : render()

  return (
    <>
      <div className="ledgerbar">
        <span className="muted">Filter:</span>
        <select value={fAction} onChange={e => setFAction(e.target.value)}>
          <option value="all">Action: all</option>
          {actions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={fTicker} onChange={e => setFTicker(e.target.value)}>
          <option value="all">Ticker: all</option>
          {tickers.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={fDate} onChange={e => setFDate(e.target.value)}>
          <option value="all">Date: all</option>
          {dates.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        {(fAction !== 'all' || fTicker !== 'all' || fDate !== 'all') && (
          <button className="link" onClick={() => { setFAction('all'); setFTicker('all'); setFDate('all') }}>clear</button>
        )}
        <span className="muted" style={{ marginLeft: 'auto' }}>{shown.length} of {rows.length} rows · click ✎ to edit</span>
      </div>
      {err && <p className="error" style={{ margin: '6px 0' }}>{err}</p>}

      <div className="tscroll">
        <table className="ttable ledgertable">
          <thead>
            <tr>
              <th>Date</th><th>Action</th><th>Ticker</th><th>Shares</th><th>Price</th><th>Entry</th>
              <th>Proceeds</th><th>Cost</th>
              <th className={hl('realized_profit')}>Realized</th>
              <th className={hl('net_profit_taken')}>Net taken</th>
              <th className={hl('reentry_reserve')}>Reserve +</th>
              <th className={isReserve ? 'hl' : ''}>Reserve used −</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r._idx} className={editing(r) ? 'editing' : ''}>
                <td>{txt(r, 'date', () => r.date)}</td>
                <td>{txt(r, 'action', () => r.action)}</td>
                <td>{txt(r, 'ticker', () => r.ticker)}</td>
                <td>{txt(r, 'shares', () => r.shares)}</td>
                <td>{txt(r, 'price', () => money(num(r.price)))}</td>
                <td>{txt(r, 'entry_price', () => money(num(r.entry_price)))}</td>
                <td>{txt(r, 'proceeds', () => (r.proceeds ? money(num(r.proceeds)) : '—'))}</td>
                <td>{txt(r, 'cost_basis', () => (r.cost_basis ? money(num(r.cost_basis)) : '—'))}</td>
                <td className={hl('realized_profit')}>{txt(r, 'realized_profit', () => (r.realized_profit ? money(num(r.realized_profit)) : '—'))}</td>
                <td className={hl('net_profit_taken')}>{txt(r, 'net_profit_taken', () => (r.net_profit_taken ? money(num(r.net_profit_taken)) : '—'))}</td>
                <td className={hl('reentry_reserve')}>{txt(r, 'reentry_reserve', () => (r.reentry_reserve ? money(num(r.reentry_reserve)) : '—'))}</td>
                <td className={isReserve ? 'hl' : ''}>{txt(r, 'reserve_used', () => (r.reserve_used ? '-' + money(num(r.reserve_used)) : '—'))}</td>
                <td className="ledgeract">
                  {editing(r) ? (
                    <>
                      <button className="link" disabled={busy} onClick={save}>save</button>
                      <button className="link" disabled={busy} onClick={cancel}>cancel</button>
                    </>
                  ) : (
                    <>
                      <button className="link" title="Edit this row" onClick={() => startEdit(r)}>✎</button>
                      <button className="link danger" title="Delete this row" disabled={busy} onClick={() => del(r._idx)}>✕</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {shown.length === 0 && <tr><td colSpan={13} className="muted">No transactions match this filter.</td></tr>}
          </tbody>
          {shownSells.length > 0 && !isReserve && (
            <tfoot>
              <tr>
                <td colSpan={8} style={{ textAlign: 'right', fontWeight: 600 }}>Total (shown)</td>
                <td className={hl('realized_profit')}>{field === 'realized_profit' ? money(colTotal) : ''}</td>
                <td className={hl('net_profit_taken')}>{field === 'net_profit_taken' ? money(colTotal) : ''}</td>
                <td colSpan={3}></td>
              </tr>
            </tfoot>
          )}
          {isReserve && (
            <tfoot>
              <tr>
                <td colSpan={10} style={{ textAlign: 'right', fontWeight: 600 }}>
                  Added {money(reserveAdded)} − used {money(reserveUsed)} =
                </td>
                <td colSpan={3} className="hl" style={{ fontWeight: 700 }}>{money(reserveRemaining)} left</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </>
  )
}

export default function Tally({ refreshKey }) {
  const [t, setT] = useState(null)
  const [ledger, setLedger] = useState([])
  const [active, setActive] = useState(null)

  const load = useCallback(() => {
    getTally().then(setT).catch(() => {})
    getLedger().then(d => setLedger(d.rows || [])).catch(() => {})
  }, [])

  useEffect(() => { load() }, [refreshKey, load])

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
              sub={t.reserve_used ? `${money(t.reserve_added)} added · ${money(t.reserve_used)} used` : 'available to redeploy'} />
      </div>

      {active && (
        <div className="tdetail">
          <div className="tdetail-head">
            <strong>{active} — details</strong>
            <button className="link" onClick={() => setActive(null)}>close ✕</button>
          </div>
          {(active === 'Holdings' || active === 'Unrealized P/L')
            ? <HoldingsTable holdings={t.holdings || []} />
            : <LedgerTable rows={ledger} field={FIELD[active]} onEdited={load} />}
        </div>
      )}
    </div>
  )
}
