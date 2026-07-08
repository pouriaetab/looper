import React, { useEffect, useState, useCallback } from 'react'
import { getTally, getPairedLedger, updateLedgerRow, deleteLedgerRow, adjustReserve } from '../api'

function money(n) {
  if (n == null || isNaN(n)) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

const num = (v) => (v === '' || v == null ? null : parseFloat(v))

// Which ledger column each money card highlights
const FIELD = {
  'Realized P/L': 'realized_profit',
  'Net profit taken': 'net_profit_taken',
  'Re-entry reserve': 'reentry_reserve',
}

const PAGE_SIZES = [10, 25, 50, 1000]

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

// One round-trip = a buy FIFO-paired with the sell that closed it (or an open buy).
function LedgerTable({ trips, field, onEdited }) {
  const isReserve = field === 'reentry_reserve'
  const hl = (f) => (field === f ? 'hl' : '')

  const [fTicker, setFTicker] = useState('all')
  const [fStatus, setFStatus] = useState('all')   // all | open | closed
  const [pageSize, setPageSize] = useState(10)
  const [page, setPage] = useState(0)

  const [editKey, setEditKey] = useState(null)
  const [draft, setDraft] = useState({})
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  // manual reserve adjustments only belong in the reserve view
  const base = isReserve ? trips : trips.filter(t => !t.reserve_adjust)
  const tickers = [...new Set(base.map(t => t.ticker).filter(Boolean))].sort()
  const shown = base.filter(t =>
    (fTicker === 'all' || t.ticker === fTicker) &&
    (fStatus === 'all' || (fStatus === 'open' ? t.open : !t.open)))

  // reset to first page whenever the filter/page-size changes the view
  useEffect(() => { setPage(0) }, [fTicker, fStatus, pageSize])

  const pages = Math.max(1, Math.ceil(shown.length / pageSize))
  const clampedPage = Math.min(page, pages - 1)
  const pageRows = shown.slice(clampedPage * pageSize, clampedPage * pageSize + pageSize)

  // totals over the FILTERED set (whole set, not just the page)
  const sum = (f) => shown.reduce((s, t) => s + (t[f] || 0), 0)
  const realizedTotal = sum('realized_profit')
  const netTotal = sum('net_profit_taken')
  const reserveAdded = sum('reentry_reserve')
  const reserveUsed = sum('reserve_used')
  const reserveRemaining = reserveAdded - reserveUsed

  const keyOf = (t) => `${t.buy_idx}-${t.sell_idx}`
  const editing = (t) => editKey === keyOf(t)
  const startEdit = (t) => {
    setEditKey(keyOf(t)); setErr(null)
    setDraft({
      ticker: t.ticker, shares: t.shares,
      buy_date: t.buy_date ?? '', buy_price: t.buy_price ?? '',
      sell_date: t.sell_date ?? '', sell_price: t.sell_price ?? '',
      cost_basis: t.cost_basis ?? '', proceeds: t.proceeds ?? '',
      realized_profit: t.realized_profit ?? '', net_profit_taken: t.net_profit_taken ?? '',
      reentry_reserve: t.reentry_reserve ?? '', reserve_used: t.reserve_used ?? '',
    })
  }
  const cancel = () => { setEditKey(null); setDraft({}); setErr(null) }
  const dset = (k) => (e) => setDraft({ ...draft, [k]: e.target.value })

  const save = async (t) => {
    setBusy(true); setErr(null)
    try {
      // Buy leg
      if (t.buy_idx != null) {
        await updateLedgerRow(t.buy_idx, {
          ticker: draft.ticker, shares: draft.shares, date: draft.buy_date,
          price: draft.buy_price, entry_price: draft.buy_price,
          cost_basis: draft.cost_basis, reserve_used: draft.reserve_used,
        })
      }
      // Sell leg (must run AFTER the buy write — each PATCH rewrites the whole file)
      if (t.sell_idx != null) {
        const sellPatch = {
          ticker: draft.ticker, shares: draft.shares, date: draft.sell_date,
          price: draft.sell_price, proceeds: draft.proceeds,
          realized_profit: draft.realized_profit, net_profit_taken: draft.net_profit_taken,
          reentry_reserve: draft.reentry_reserve,
        }
        if (t.buy_idx == null) {   // legacy sell-only: buy price lives on this row's entry_price
          sellPatch.entry_price = draft.buy_price
          sellPatch.cost_basis = draft.cost_basis
        }
        await updateLedgerRow(t.sell_idx, sellPatch)
      }
      cancel(); onEdited && onEdited()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const del = async (t) => {
    if (!window.confirm(`Delete this ${t.ticker} round-trip from the ledger? This edits the master history.`)) return
    setBusy(true); setErr(null)
    try {
      // delete the higher index first so the lower index stays valid
      const idxs = [t.buy_idx, t.sell_idx].filter(i => i != null).sort((a, b) => b - a)
      for (const i of idxs) await deleteLedgerRow(i)
      if (editing(t)) cancel()
      onEdited && onEdited()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  // cell: show value, or an input when this row is being edited (and the leg exists)
  const cell = (t, key, legIdx, render) =>
    editing(t) && legIdx !== null
      ? <input className="ledit" value={draft[key] ?? ''} onChange={dset(key)} />
      : render()

  return (
    <>
      <div className="ledgerbar">
        <span className="muted">Filter:</span>
        <select value={fTicker} onChange={e => setFTicker(e.target.value)}>
          <option value="all">Ticker: all</option>
          {tickers.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={fStatus} onChange={e => setFStatus(e.target.value)} title="closed = a completed buy→sell round-trip; open = still holding">
          <option value="all">Status: all</option>
          <option value="closed">Closed</option>
          <option value="open">Open</option>
        </select>
        {(fTicker !== 'all' || fStatus !== 'all') && (
          <button className="link" onClick={() => { setFTicker('all'); setFStatus('all') }}>clear</button>
        )}
        <span className="muted" style={{ marginLeft: 'auto' }}>
          Show
          <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))} style={{ margin: '0 4px' }}>
            {PAGE_SIZES.map(n => <option key={n} value={n}>{n >= 1000 ? 'all' : n}</option>)}
          </select>
        </span>
        <button className="link" disabled={clampedPage <= 0} onClick={() => setPage(p => Math.max(0, p - 1))} title="Newer">‹</button>
        <span className="muted">{shown.length ? `${clampedPage * pageSize + 1}–${Math.min(shown.length, (clampedPage + 1) * pageSize)}` : 0} / {shown.length}</span>
        <button className="link" disabled={clampedPage >= pages - 1} onClick={() => setPage(p => Math.min(pages - 1, p + 1))} title="Older">›</button>
      </div>
      {err && <p className="error" style={{ margin: '6px 0' }}>{err}</p>}

      <div className="tscroll">
        <table className="ttable ledgertable">
          <thead>
            <tr>
              <th>Ticker</th><th>Shares</th>
              <th>Buy date</th><th>Buy $</th>
              <th>Sell date</th><th>Sell $</th>
              <th>Cost</th><th>Proceeds</th>
              <th className={hl('realized_profit')}>Realized</th>
              <th className={hl('net_profit_taken')}>Net taken</th>
              <th className={hl('reentry_reserve')}>Reserve +</th>
              <th className={isReserve ? 'hl' : ''}>Reserve −</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((t) => (
              <tr key={keyOf(t)} className={`${editing(t) ? 'editing' : ''} ${t.reserve_adjust ? 'resrow' : ''}`}>
                <td>{t.reserve_adjust
                  ? <span title={t.note}>{t.reentry_reserve ? 'Reserve +' : 'Reserve −'}</span>
                  : cell(t, 'ticker', t.sell_idx ?? t.buy_idx, () => t.ticker)}</td>
                <td>{cell(t, 'shares', t.sell_idx ?? t.buy_idx, () => t.shares)}</td>
                <td>{cell(t, 'buy_date', t.buy_idx, () => (t.reserve_adjust ? t.sell_date : (t.buy_date || '—')))}</td>
                <td>{cell(t, 'buy_price', t.sell_idx ?? t.buy_idx, () => money(t.buy_price))}</td>
                <td>{cell(t, 'sell_date', t.sell_idx, () => (t.open ? <span className="rtag r-mid">open</span> : t.sell_date))}</td>
                <td>{cell(t, 'sell_price', t.sell_idx, () => (t.sell_price != null ? money(t.sell_price) : '—'))}</td>
                <td>{cell(t, 'cost_basis', t.sell_idx ?? t.buy_idx, () => (t.cost_basis != null ? money(t.cost_basis) : '—'))}</td>
                <td>{cell(t, 'proceeds', t.sell_idx, () => (t.proceeds != null ? money(t.proceeds) : '—'))}</td>
                <td className={hl('realized_profit') + ' ' + (t.realized_profit > 0 ? 'pos' : t.realized_profit < 0 ? 'neg' : '')}>
                  {cell(t, 'realized_profit', t.sell_idx, () => (t.realized_profit != null ? money(t.realized_profit) : '—'))}
                </td>
                <td className={hl('net_profit_taken')}>{cell(t, 'net_profit_taken', t.sell_idx, () => (t.net_profit_taken != null ? money(t.net_profit_taken) : '—'))}</td>
                <td className={hl('reentry_reserve')}>{cell(t, 'reentry_reserve', t.sell_idx, () => (t.reentry_reserve != null ? money(t.reentry_reserve) : '—'))}</td>
                <td className={isReserve ? 'hl' : ''}>{cell(t, 'reserve_used', t.buy_idx, () => (t.reserve_used != null ? '-' + money(t.reserve_used) : '—'))}</td>
                <td className="ledgeract">
                  {editing(t) ? (
                    <>
                      <button className="link" disabled={busy} onClick={() => save(t)}>save</button>
                      <button className="link" disabled={busy} onClick={cancel}>cancel</button>
                    </>
                  ) : (
                    <>
                      <button className="link" title={t.editable ? 'Edit this round-trip' : 'Split lot — edit the raw rows individually'} disabled={!t.editable} onClick={() => startEdit(t)}>✎</button>
                      <button className="link danger" title="Delete this round-trip" disabled={busy} onClick={() => del(t)}>✕</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
            {shown.length === 0 && <tr><td colSpan={13} className="muted">No round-trips match this filter.</td></tr>}
          </tbody>
          <tfoot>
            {isReserve ? (
              <tr>
                <td colSpan={10} style={{ textAlign: 'right', fontWeight: 600 }}>
                  In {money(reserveAdded)} − out {money(reserveUsed)} =
                </td>
                <td colSpan={3} className={`hl ${reserveRemaining < 0 ? 'neg' : 'pos'}`} style={{ fontWeight: 700 }}>
                  {reserveRemaining < 0 ? `overspent ${money(-reserveRemaining)}` : `${money(reserveRemaining)} left`}
                </td>
              </tr>
            ) : (field === 'realized_profit' || field === 'net_profit_taken') ? (
              <tr>
                <td colSpan={8} style={{ textAlign: 'right', fontWeight: 600 }}>Total (filtered)</td>
                <td className={hl('realized_profit')}>{field === 'realized_profit' ? money(realizedTotal) : ''}</td>
                <td className={hl('net_profit_taken')}>{field === 'net_profit_taken' ? money(netTotal) : ''}</td>
                <td colSpan={3}></td>
              </tr>
            ) : null}
          </tfoot>
        </table>
      </div>
    </>
  )
}

// Reserve summary + manual add / reduce controls (shown above the reserve ledger).
function ReserveAdjust({ t, onDone }) {
  const [amt, setAmt] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const net = t.reserve_net ?? 0

  const go = async (direction) => {
    const v = parseFloat(amt)
    if (!(v > 0)) { setErr('Enter an amount above 0.'); return }
    setBusy(true); setErr(null)
    try { await adjustReserve(v, direction); setAmt(''); onDone && onDone() }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="reservebox">
      <div className="reservesum">
        <span>In <b>{money(t.reserve_added)}</b></span>
        <span>Out <b>{money(t.reserve_used)}</b></span>
        <span className={net < 0 ? 'neg' : 'pos'}>
          {net < 0 ? `Overspent ${money(-net)}` : `Available ${money(net)}`}
        </span>
      </div>
      <div className="reserveadj">
        <input type="number" step="0.01" placeholder="amount $" value={amt}
               onChange={e => setAmt(e.target.value)} style={{ width: '110px' }} />
        <button disabled={busy} onClick={() => go('add')}>+ Add to reserve</button>
        <button disabled={busy} onClick={() => go('reduce')}>− Reduce reserve</button>
        <span className="muted small">logged as a ledger row you can delete</span>
      </div>
      {err && <p className="error small" style={{ margin: '6px 0 0' }}>{err}</p>}
    </div>
  )
}

export default function Tally({ refreshKey }) {
  const [t, setT] = useState(null)
  const [trips, setTrips] = useState([])
  const [active, setActive] = useState(null)

  const load = useCallback(() => {
    getTally().then(setT).catch(() => {})
    getPairedLedger().then(d => setTrips(d.trips || [])).catch(() => {})
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
        <Card label="Re-entry reserve" value={money(t.reserve_net ?? t.reentry_reserve)}
              tone={(t.reserve_net ?? 0) < 0 ? 'neg' : ''}
              active={active === 'Re-entry reserve'} onClick={() => toggle('Re-entry reserve')}
              sub={(t.reserve_net ?? 0) < 0
                ? `overspent ${money(t.reserve_overspent)} · in ${money(t.reserve_added)} · out ${money(t.reserve_used)}`
                : `in ${money(t.reserve_added)} · out ${money(t.reserve_used)}`} />
      </div>

      {active && (
        <div className="tdetail">
          <div className="tdetail-head">
            <strong>{active} — {(active === 'Holdings' || active === 'Unrealized P/L') ? 'details' : 'round-trips (buy ↔ sell)'}</strong>
            <button className="link" onClick={() => setActive(null)}>close ✕</button>
          </div>
          {active === 'Re-entry reserve' && <ReserveAdjust t={t} onDone={load} />}
          {(active === 'Holdings' || active === 'Unrealized P/L')
            ? <HoldingsTable holdings={t.holdings || []} />
            : <LedgerTable trips={trips} field={FIELD[active]} onEdited={load} />}
        </div>
      )}
    </div>
  )
}
