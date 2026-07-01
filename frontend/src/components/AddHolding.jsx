import React, { useState, useEffect } from 'react'
import { addStock, removeStock, sellStock, getConfig, recordReserveUse } from '../api'

const EMPTY = { ticker: '', entry_price: '', shares: '1', state: 'holding', analyst_target: '', acquired_date: '', acquired_time: '', from_reserve: false }

// Build an ISO timestamp from optional date + time inputs.
// Both blank -> null (backend uses the current date/time). Otherwise use what's given.
function buildWhen(date, time) {
  if (!date && !time) return null
  const d = date || new Date().toISOString().slice(0, 10)
  const t = time || new Date().toTimeString().slice(0, 5)
  return `${d}T${t}:00`
}

export default function AddHolding({ onChange }) {
  const [f, setF] = useState(EMPTY)
  const [msg, setMsg] = useState(null)
  const [msgType, setMsgType] = useState(null) // 'success' or 'error'
  const [stocks, setStocks] = useState([])
  const [sellFor, setSellFor] = useState(null)   // ticker currently being sold
  const [sellForm, setSellForm] = useState({ shares: '', price: '' })
  const [showForm, setShowForm] = useState(true) // collapse the add form to bring Portfolio up

  const refreshList = () => getConfig().then(d => setStocks(d.stocks || [])).catch(() => {})
  useEffect(() => { refreshList() }, [])

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setMsg(null)
    setMsgType(null)
    if (!f.ticker || !(parseFloat(f.entry_price) > 0)) {
      setMsg('Enter a symbol and a buy price above 0.')
      setMsgType('error')
      return
    }
    if (!(parseFloat(f.shares) > 0)) {
      setMsg('Shares must be greater than 0.')
      setMsgType('error')
      return
    }
    try {
      await addStock({
        ticker: f.ticker.toUpperCase(),
        entry_price: parseFloat(f.entry_price),
        shares: parseFloat(f.shares || '1'),
        state: f.state,
        analyst_target: f.analyst_target ? parseFloat(f.analyst_target) : null,
        acquired_date: f.acquired_date || null,
        when: buildWhen(f.acquired_date, f.acquired_time),
        from_reserve: f.from_reserve,
      })
      setMsg(`✓ Added ${f.ticker.toUpperCase()} to portfolio.`)
      setMsgType('success')
      setF(EMPTY)
      refreshList()
      onChange && onChange()
    } catch (err) {
      setMsg(`Error: ${err.message}`)
      setMsgType('error')
    }
  }

  const openSell = (s) => {
    setSellFor(s.ticker)
    setSellForm({ shares: String(s.position?.shares ?? ''), price: '', date: '', time: '' })
    setMsg(null)
    setMsgType(null)
  }

  const confirmSell = async (ticker) => {
    const shares = parseFloat(sellForm.shares)
    const price = parseFloat(sellForm.price)
    if (!(shares > 0) || !(price > 0)) {
      setMsg('Enter shares sold and sale price (both above 0).')
      setMsgType('error')
      return
    }
    try {
      const r = await sellStock(ticker, { shares, price, when: buildWhen(sellForm.date, sellForm.time) })
      setMsg(
        `✓ Sold ${shares} ${ticker} @ $${price}. Realized ${r.realized_profit >= 0 ? '+' : ''}$${r.realized_profit}` +
        (r.closed ? ' — now in the Buy section, watching for re-entry.' : ` — ${r.shares_remaining} shares left.`)
      )
      setMsgType('success')
      setSellFor(null)
      refreshList()
      onChange && onChange()
    } catch (err) {
      setMsg(`Error selling ${ticker}: ${err.message}`)
      setMsgType('error')
    }
  }

  const reserveUse = async (s) => {
    const v = window.prompt(`How much of ${s.ticker} was funded from the re-entry reserve? ($)`)
    if (v == null) return
    const amt = parseFloat(v)
    if (!(amt > 0)) { setMsg('Enter an amount above 0.'); setMsgType('error'); return }
    try {
      await recordReserveUse(s.ticker, amt)
      setMsg(`✓ Recorded $${amt} of ${s.ticker} from the re-entry reserve.`)
      setMsgType('success')
      onChange && onChange()
    } catch (err) {
      setMsg(`Error: ${err.message}`); setMsgType('error')
    }
  }

  const remove = async (s) => {
    const ticker = s.ticker
    const isCash = s.position?.state === 'cash'
    const prompt = isCash
      ? `Stop tracking ${ticker} for re-entry? It will be removed from LOOPER entirely.`
      : `Delete ${ticker} without recording a sale?`
    if (!window.confirm(prompt)) return
    try {
      await removeStock(ticker)
      refreshList()
      onChange && onChange()
    } catch (err) {
      setMsg(`Error removing ${ticker}: ${err.message}`)
      setMsgType('error')
    }
  }

  return (
    <div className="addbox">
      <button className="addhead" onClick={() => setShowForm(v => !v)}
              title={showForm ? 'Hide the form' : 'Show the form'}>
        <span>Add / Update Position</span>
        <span className="chev">{showForm ? '▲' : '▼'}</span>
      </button>
      {showForm && (<>
      <p style={{ margin: '0 0 12px 0', fontSize: '13px', color: 'var(--text-secondary)' }}>
        Enter a stock symbol, the price you paid, and number of shares. The app tracks sell signals when holding, and re-entry zones after you sell.
      </p>

      <form onSubmit={submit} className="addform">
        <div>
          <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>Stock Symbol</label>
          <input placeholder="e.g., NVDA, BRKR" value={f.ticker} onChange={set('ticker')} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <div>
            <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>Entry Price ($)</label>
            <input placeholder="0.00" type="number" step="0.01" value={f.entry_price} onChange={set('entry_price')} />
          </div>
          <div>
            <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>Shares</label>
            <input placeholder="1" type="number" step="0.1" value={f.shares} onChange={set('shares')} />
          </div>
        </div>

        <div>
          <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>Position Status</label>
          <select value={f.state} onChange={set('state')}>
            <option value="holding">🔴 Holding — watch for sell signal</option>
            <option value="cash">🟢 Sold — watch for re-entry zone</option>
          </select>
        </div>

        <div>
          <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>Analyst Target (optional)</label>
          <input placeholder="Price target, e.g., 125.00" type="number" step="0.01" value={f.analyst_target} onChange={set('analyst_target')} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <div>
            <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>Date (optional)</label>
            <input type="date" value={f.acquired_date} onChange={set('acquired_date')} />
          </div>
          <div>
            <label style={{ fontSize: '12px', fontWeight: '600', display: 'block', marginBottom: '4px' }}>Time (optional)</label>
            <input type="time" value={f.acquired_time} onChange={set('acquired_time')} />
          </div>
        </div>
        <p style={{ margin: '-4px 0 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
          Leave date &amp; time blank to use the current date/time.
        </p>

        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', margin: '2px 0' }}>
          <input type="checkbox" checked={f.from_reserve}
                 onChange={(e) => setF({ ...f, from_reserve: e.target.checked })}
                 style={{ width: 'auto' }} />
          Fund this buy from the re-entry reserve (draws it down)
        </label>

        <button type="submit" style={{ marginTop: '4px', fontWeight: '600' }}>Add to Portfolio</button>

        {msg && (
          <p style={{
            margin: '8px 0 0',
            padding: '8px 10px',
            fontSize: '13px',
            fontWeight: '500',
            borderRadius: '6px',
            background: msgType === 'success' ? '#f0f8f5' : '#fdf2f2',
            color: msgType === 'success' ? 'var(--success)' : 'var(--danger)',
            border: `1px solid ${msgType === 'success' ? 'var(--success)' : 'var(--danger)'}`,
          }}>
            {msg}
          </p>
        )}
      </form>
      </>)}

      {stocks.length > 0 && (
        <div className="holdings">
          <h3>📊 Portfolio ({stocks.length})</h3>
          {stocks.map(s => (
            <div className="hold" key={s.ticker} style={{ flexWrap: 'wrap' }}>
              <div>
                <strong>{s.ticker}</strong>
                <span style={{ marginLeft: '6px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {s.position?.entry_price && `@$${s.position.entry_price.toFixed(2)} × ${s.position.shares || 1}`}
                </span>
                {s.acquired_date && (
                  <span className="hold-date" style={{ marginLeft: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                    • {s.acquired_date}
                  </span>
                )}
                <span style={{ marginLeft: '4px', fontSize: '11px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.3px' }}>
                  {s.position?.state === 'holding' ? '🔴 holding' : '🟢 cash'}
                </span>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                {s.position?.state === 'holding' && (
                  <button className="link" onClick={() => (sellFor === s.ticker ? setSellFor(null) : openSell(s))}>
                    {sellFor === s.ticker ? 'cancel' : 'sell'}
                  </button>
                )}
                <button className="link" onClick={() => reserveUse(s)} title="Record how much of this buy came from the re-entry reserve">reserve</button>
                <button className="link danger" onClick={() => remove(s)}>
                  {s.position?.state === 'cash' ? 'stop' : 'delete'}
                </button>
              </div>

              {sellFor === s.ticker && (
                <>
                <div className="sellrow" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center', width: '100%', marginTop: '8px' }}>
                  <input
                    type="number" step="0.1" placeholder="shares sold"
                    value={sellForm.shares}
                    onChange={(e) => setSellForm({ ...sellForm, shares: e.target.value })}
                    style={{ width: '110px' }}
                  />
                  <input
                    type="number" step="0.01" placeholder="sale price $"
                    value={sellForm.price}
                    onChange={(e) => setSellForm({ ...sellForm, price: e.target.value })}
                    style={{ width: '120px' }}
                  />
                  <input
                    type="date" title="Sale date (optional)"
                    value={sellForm.date}
                    onChange={(e) => setSellForm({ ...sellForm, date: e.target.value })}
                    style={{ width: '140px' }}
                  />
                  <input
                    type="time" title="Sale time (optional)"
                    value={sellForm.time}
                    onChange={(e) => setSellForm({ ...sellForm, time: e.target.value })}
                    style={{ width: '110px' }}
                  />
                  <button onClick={() => confirmSell(s.ticker)} style={{ fontWeight: 600 }}>Record sale</button>
                </div>
                <p style={{ margin: '4px 0 0', fontSize: '11px', color: 'var(--text-secondary)', width: '100%' }}>
                  Date &amp; time optional — blank uses the current date/time.
                </p>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
