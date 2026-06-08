import React, { useState, useEffect } from 'react'
import { addStock, removeStock, getConfig } from '../api'

const EMPTY = { ticker: '', entry_price: '', shares: '1', state: 'holding', analyst_target: '' }

export default function AddHolding({ onChange }) {
  const [f, setF] = useState(EMPTY)
  const [msg, setMsg] = useState(null)
  const [stocks, setStocks] = useState([])

  const refreshList = () => getConfig().then(d => setStocks(d.stocks || [])).catch(() => {})
  useEffect(() => { refreshList() }, [])

  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setMsg(null)
    if (!f.ticker || !(parseFloat(f.entry_price) > 0)) {
      setMsg('Enter a symbol and a buy price above 0.')
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
      setMsg(`Saved ${f.ticker.toUpperCase()}.`)
      setF(EMPTY)
      refreshList()
      onChange && onChange()
    } catch (err) {
      setMsg(err.message)
    }
  }

  const remove = async (ticker) => {
    await removeStock(ticker)
    refreshList()
    onChange && onChange()
  }

  return (
    <div className="addbox">
      <h2>Add / update a holding</h2>
      <form onSubmit={submit} className="addform">
        <input placeholder="Symbol (e.g. NVDA)" value={f.ticker} onChange={set('ticker')} />
        <input placeholder="Buy price ($)" type="number" step="0.01" value={f.entry_price} onChange={set('entry_price')} />
        <input placeholder="Shares" type="number" step="1" value={f.shares} onChange={set('shares')} />
        <select value={f.state} onChange={set('state')}>
          <option value="holding">holding (watch to sell)</option>
          <option value="cash">cash (watch to re-enter)</option>
        </select>
        <input placeholder="Analyst target ($, optional)" type="number" step="0.01" value={f.analyst_target} onChange={set('analyst_target')} />
        <button type="submit">Save holding</button>
        {msg && <p className="msg">{msg}</p>}
      </form>

      {stocks.length > 0 && (
        <div className="holdings">
          <h3>Current</h3>
          {stocks.map(s => (
            <div className="hold" key={s.ticker}>
              <span>{s.ticker} <small>({s.position?.state})</small></span>
              <button className="link danger" onClick={() => remove(s.ticker)}>remove</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
