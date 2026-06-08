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
  const [showSidebar, setShowSidebar] = useState(true)

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
        <button className="toggle" onClick={() => setShowSidebar(v => !v)} aria-label="Toggle holdings panel">☰</button>
        <h1>🔁 LOOPER</h1>
        <span className="tag">portfolio of active loops</span>
        <button className="refresh" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </header>

      <div className="layout">
        {showSidebar && (
          <aside className="sidebar">
            <AddHolding onChange={load} />
          </aside>
        )}

        <main className="content">
          {err && (
            <div className="error">
              Couldn’t reach the backend ({err}).
              <div className="muted small">
                Make sure it’s running (the <code>./run.sh</code> launcher starts it on port 8000),
                then click retry. Open the app at <b>http://localhost:5173</b>, not :8000.
              </div>
              <button onClick={load} style={{ marginTop: 8 }}>Retry</button>
            </div>
          )}
          {detail ? (
            <StockDetail ticker={detail} onBack={() => setDetail(null)} />
          ) : data ? (
            <Portfolio data={data} onOpen={setDetail} />
          ) : (
            !err && <p className="muted">Loading portfolio…</p>
          )}
        </main>
      </div>

      <footer className="foot">Decision support, not financial advice.</footer>
    </div>
  )
}
