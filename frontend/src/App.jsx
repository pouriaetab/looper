import React, { useState, useEffect, useCallback } from 'react'
import { getPortfolio, getSettings, setTimespan } from './api'
import Portfolio from './components/Portfolio'
import StockDetail from './components/StockDetail'
import AddHolding from './components/AddHolding'
import Tally from './components/Tally'

export default function App() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState(null)
  const [showSidebar, setShowSidebar] = useState(true)
  const [horizon, setHorizon] = useState('day')
  const [sidebarWidth, setSidebarWidth] = useState(
    () => Number(localStorage.getItem('looperSidebarW')) || 400
  )

  // Drag the divider to resize the sidebar (240–640px), remembered across sessions.
  const startResize = (e) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = sidebarWidth
    let latest = startW
    const onMove = (ev) => {
      latest = Math.min(640, Math.max(240, startW + ev.clientX - startX))
      setSidebarWidth(latest)
    }
    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
      localStorage.setItem('looperSidebarW', String(latest))
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

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
  useEffect(() => { getSettings().then(s => setHorizon(s.timespan || 'day')).catch(() => {}) }, [])

  const changeHorizon = async (tspan) => {
    setHorizon(tspan)
    try {
      await setTimespan(tspan)
      await load()
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <button className="toggle" onClick={() => setShowSidebar(v => !v)} aria-label="Toggle holdings panel">☰</button>
        <h1>🔁 LOOPER</h1>
        <span className="tag">portfolio of active loops</span>
        <label className="horizon" title="Swing = daily bars (faster signals). Long-term = weekly bars (slower, weeks–months view).">
          Horizon:&nbsp;
          <select value={horizon} onChange={(e) => changeHorizon(e.target.value)}>
            <option value="day">Swing (daily)</option>
            <option value="week">Long-term (weekly)</option>
          </select>
        </label>
        <button className="refresh" onClick={load} disabled={loading}>
          {loading ? 'Refreshing…' : '↻ Refresh'}
        </button>
      </header>

      <div className="layout">
        {showSidebar && (
          <>
            <aside className="sidebar" style={{ '--sw': sidebarWidth + 'px' }}>
              <AddHolding onChange={load} />
            </aside>
            <div className="resizer" onMouseDown={startResize} title="Drag to resize the panel" />
          </>
        )}

        <main className="content">
          {!detail && <Tally refreshKey={data} />}
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
