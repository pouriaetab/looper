import React, { useState, useEffect } from 'react'
import { addStock, removeStock, getConfig } from '../api'

const EMPTY = { ticker: '', entry_price: '', shares: '1', state: 'holding', analyst_target: '' }

export default function AddHolding({ onChange }) {
  const [f, setF] = useState(EMPTY)
  const [msg, setMsg] = useState(null)
  const [msgType, setMsgType] = useState(null) // 'success' or 'error'
  const [stocks, setStocks] = useState([])

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

  const remove = async (ticker) => {
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
      <h2>Add / Update Position</h2>
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

      {stocks.length > 0 && (
        <div className="holdings">
          <h3>📊 Portfolio ({stocks.length})</h3>
          {stocks.map(s => (
            <div className="hold" key={s.ticker}>
              <div>
                <strong>{s.ticker}</strong>
                <span style={{ marginLeft: '6px', fontSize: '12px', color: 'var(--text-secondary)' }}>
                  {s.position?.entry_price && `@$${s.position.entry_price.toFixed(2)} × ${s.position.shares || 1}`}
                </span>
                <span style={{ marginLeft: '4px', fontSize: '11px', fontWeight: '600', textTransform: 'uppercase', letterSpacing: '0.3px' }}>
                  {s.position?.state === 'holding' ? '🔴 holding' : '🟢 cash'}
                </span>
              </div>
              <button className="link danger" onClick={() => remove(s.ticker)}>remove</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
