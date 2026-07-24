import React, { useState, useEffect, useCallback } from 'react'
import { getProfit, setAllocation, deployProfit, undoDeployment } from '../api'

function money(n) {
  if (n == null || isNaN(n)) return '—'
  const sign = n < 0 ? '-' : ''
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

// Deploy "net profit taken" into a target ETF/theme allocation, with a running
// available balance and a history of past deployments.
export default function ProfitDeploy() {
  const [s, setS] = useState(null)
  const [amount, setAmount] = useState('')
  const [editing, setEditing] = useState(false)
  const [rows, setRows] = useState([])       // editable allocation draft
  const [showHist, setShowHist] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [msg, setMsg] = useState(null)

  const load = useCallback(() => {
    getProfit().then(d => {
      setS(d)
      setAmount(a => (a === '' ? String(Math.max(0, d.available).toFixed(2)) : a))
    }).catch(e => setErr(e.message))
  }, [])
  useEffect(() => { load() }, [load])

  if (!s) return <p className="muted small">Loading profit plan…</p>

  const amt = parseFloat(amount) || 0
  const prices = s.prices || {}
  const plan = (s.allocation || []).map(sl => {
    const dollars = amt * (Number(sl.pct) || 0) / 100
    const primary = (sl.tickers || [])[0]
    const px = primary ? prices[primary] : null
    return { ...sl, dollars, primary, px, shares: px ? dollars / px : null }
  })
  const pctSum = (s.allocation || []).reduce((x, sl) => x + Number(sl.pct || 0), 0)

  const deploy = async () => {
    if (!(amt > 0)) { setErr('Enter an amount above 0.'); return }
    setBusy(true); setErr(null); setMsg(null)
    try {
      const d = await deployProfit(amt)
      setS(d); setAmount(String(Math.max(0, d.available).toFixed(2)))
      setMsg(`Deployed ${money(amt)}. ${money(d.available)} left available.`)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const undo = async (idx) => {
    if (!window.confirm('Undo this deployment? The amount goes back to available.')) return
    setBusy(true); setErr(null)
    try { await undoDeployment(idx); load() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const startEdit = () => {
    setRows((s.allocation || []).map(sl => ({
      name: sl.name, pct: String(sl.pct), tickers: (sl.tickers || []).join(', '),
    })))
    setEditing(true); setErr(null)
  }
  const setRow = (i, k, v) => setRows(rs => rs.map((r, j) => (j === i ? { ...r, [k]: v } : r)))
  const addRow = () => setRows(rs => [...rs, { name: '', pct: '', tickers: '' }])
  const delRow = (i) => setRows(rs => rs.filter((_, j) => j !== i))
  const saveEdit = async () => {
    setBusy(true); setErr(null)
    try {
      const sleeves = rows.filter(r => r.name.trim()).map(r => ({
        name: r.name.trim(), pct: parseFloat(r.pct) || 0,
        tickers: r.tickers.split(',').map(t => t.trim()).filter(Boolean),
      }))
      await setAllocation(sleeves); setEditing(false); load()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const draftSum = rows.reduce((x, r) => x + (parseFloat(r.pct) || 0), 0)

  return (
    <div className="deploybox">
      <div className="reservesum">
        <span>Net taken <b>{money(s.net_profit_taken)}</b></span>
        <span>Deployed <b>{money(s.total_deployed)}</b></span>
        <span className={s.available > 0 ? 'pos' : ''}>Available <b>{money(s.available)}</b></span>
      </div>

      <div className="reserveadj">
        <span className="muted small">Deploy $</span>
        <input type="number" step="0.01" min="0" value={amount}
               onChange={e => setAmount(e.target.value)} style={{ width: '100px' }} />
        <button className="link" onClick={() => setAmount(String(Math.max(0, s.available).toFixed(2)))}>use available</button>
        <button disabled={busy || !(amt > 0)} onClick={deploy}>Deploy across allocation</button>
        <button className="link" onClick={editing ? () => setEditing(false) : startEdit}>
          {editing ? 'cancel edit' : 'edit allocation'}
        </button>
      </div>
      {err && <p className="error small" style={{ margin: '6px 0 0' }}>{err}</p>}
      {msg && <p className="muted small" style={{ margin: '6px 0 0' }}>{msg}</p>}

      {!editing ? (
        <div className="tscroll">
          <table className="ttable ledgertable" style={{ marginTop: '8px' }}>
            <thead>
              <tr><th>Sleeve</th><th>%</th><th>Buy $</th><th>Tickers</th><th>≈ shares (primary)</th></tr>
            </thead>
            <tbody>
              {plan.map((p, i) => (
                <tr key={i}>
                  <td>{p.name}</td>
                  <td>{p.pct}%</td>
                  <td><b>{money(p.dollars)}</b></td>
                  <td>{(p.tickers || []).join(', ') || '—'}</td>
                  <td>{p.px ? `${p.shares.toFixed(3)} @ ${money(p.px)} (${p.primary})` : (p.primary ? `— (${p.primary})` : '—')}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className={Math.abs(pctSum - 100) > 0.01 ? 'neg' : ''}>{pctSum}%{Math.abs(pctSum - 100) > 0.01 ? ' ⚠ not 100' : ''}</td>
                <td></td><td><b>{money(amt)}</b></td><td colSpan={2}></td>
              </tr>
            </tfoot>
          </table>
        </div>
      ) : (
        <div className="tscroll">
          <table className="ttable ledgertable" style={{ marginTop: '8px' }}>
            <thead>
              <tr><th>Sleeve</th><th>%</th><th>Tickers (comma-sep, first = primary)</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td><input className="ledit" style={{ width: '130px' }} value={r.name} onChange={e => setRow(i, 'name', e.target.value)} /></td>
                  <td><input className="ledit" style={{ width: '46px' }} value={r.pct} onChange={e => setRow(i, 'pct', e.target.value)} /></td>
                  <td><input className="ledit" style={{ width: '200px' }} value={r.tickers} onChange={e => setRow(i, 'tickers', e.target.value)} /></td>
                  <td><button className="link danger" onClick={() => delRow(i)}>✕</button></td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td className={Math.abs(draftSum - 100) > 0.01 ? 'neg' : 'pos'}>{draftSum}%{Math.abs(draftSum - 100) > 0.01 ? ' ⚠' : ' ✓'}</td>
                <td colSpan={3} style={{ textAlign: 'left' }}>
                  <button className="link" onClick={addRow}>+ add sleeve</button>
                  <button onClick={saveEdit} disabled={busy} style={{ marginLeft: '8px' }}>Save allocation</button>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <div style={{ marginTop: '8px' }}>
        <button className="link" onClick={() => setShowHist(h => !h)}>
          {showHist ? 'hide' : 'show'} deployment history ({s.deployments.length})
        </button>
        {showHist && (
          <div className="tscroll">
            <table className="ttable ledgertable" style={{ marginTop: '6px' }}>
              <thead><tr><th>Date</th><th>Amount</th><th>Breakdown</th><th></th></tr></thead>
              <tbody>
                {s.deployments.map(d => (
                  <tr key={d.idx}>
                    <td>{d.date}</td>
                    <td><b>{money(d.amount)}</b></td>
                    <td>{(d.breakdown || []).map(b => `${b.tickers?.[0] || b.name} ${money(b.amount)}`).join(' · ')}</td>
                    <td><button className="link danger" onClick={() => undo(d.idx)}>undo</button></td>
                  </tr>
                ))}
                {s.deployments.length === 0 && <tr><td colSpan={4} className="muted">Nothing deployed yet.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
