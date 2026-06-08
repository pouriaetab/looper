import React, { useState, useEffect, useCallback } from 'react'
import { getPortfolio } from './api'
import Portfolio from './components/Portfolio'
import StockDetail from './components/StockDetail'
import AddHolding from './components/AddHolding'

export default function App() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setErr(null)
    try {
      setData(await getPortfolio())
    } catch (e) {
      setErr(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  return (
    <div className="app">
      <header className="topbar">
        <h1>🔁 LOOPER</h1>
        <span className="tag">portfolio of active loops</span>
        <button className="refresh" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <AddHolding onChange={load} />
        </aside>

        <main className="content">
          {err && <div className="error">Error: {err}</div>}
          {detail ? (
            <StockDetail ticker={detail} onBack={() => setDetail(null)} />
          ) : data ? (
            <Portfolio data={data} onOpen={setDetail} />
          ) : (
            !err && <p className="muted">Loading portfolio…</p>
          )}
        </main>
      </div>

      <footer className="foot">
        Decision support, not financial advice.
      </footer>
    </div>
  )
}
