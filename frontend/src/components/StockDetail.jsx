import React, { useState, useEffect } from 'react'
import { getStock } from '../api'

const STANCE = {
  'Accumulate': '#1B7F49', 'Accumulate / core hold': '#1B7F49',
  'Hold': '#C8643F', 'Hold / wait': '#C8643F',
  'Trim / take profit': '#B07515', 'Reduce': '#B07515', 'Exit / avoid': '#C13B2B',
}
const CHIP = {
  'High quality': '#1B7F49', 'Solid': '#1B7F49', 'Average': '#B07515',
  'Weak': '#C13B2B', 'Deteriorating': '#C13B2B',
  'Cheap': '#1B7F49', 'Fair': '#C8643F', 'Rich': '#B07515', 'Expensive': '#C13B2B',
}
const scoreColor = (s) => s == null ? '#8C8A82' : s >= 0.7 ? '#1B7F49' : s >= 0.4 ? '#B07515' : '#C13B2B'

export default function StockDetail({ ticker, onBack }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    setD(null); setErr(null)
    getStock(ticker).then(setD).catch(e => setErr(e.message))
  }, [ticker])

  const back = <button className="back" onClick={onBack}>← Back to portfolio</button>
  if (err) return <div>{back}<div className="error">{err}</div></div>
  if (!d) return <div>{back}<p className="muted">Loading {ticker}…</p></div>

  const r = d.result, sc = d.scorecard, st = d.stance, plan = r.reentry_plan
  return (
    <div className="detail">
      {back}
      <h1>{r.ticker}</h1>

      <div className="stance" style={{ background: STANCE[st.label] || '#C8643F' }}>
        <strong>{st.label}</strong>
        <div className="reason">{st.reason}</div>
      </div>

      <p className="verdicts">
        Quality <span className="chip" style={{ background: CHIP[sc.quality_verdict] || '#8C8A82' }}>{sc.quality_verdict}</span>
        Valuation <span className="chip" style={{ background: CHIP[sc.value_verdict] || '#8C8A82' }}>{sc.value_verdict}</span>
        Timing <span className="chip" style={{ background: '#C8643F' }}>{r.headline}</span>
      </p>

      <div className="metrics">
        <div><small>Price</small><b>${r.price.toFixed(2)}</b></div>
        <div><small>RSI</small><b>{r.rsi.toFixed(0)}</b></div>
        <div><small>EMA 20</small><b>${r.ema_short.toFixed(2)}</b></div>
        <div><small>EMA 50</small><b>${r.ema_long.toFixed(2)}</b></div>
      </div>

      {r.analyst_target && (
        <p className="muted">
          Analyst consensus: ${r.analyst_target.toFixed(2)} average
          {r.analyst_count ? <> across <a href={r.analyst_source_url || '#'} target="_blank" rel="noreferrer">{r.analyst_count} analysts</a></> : null}
          {r.target_low && r.target_high ? ` · range $${r.target_low}–$${r.target_high}` : ''}
          {r.analyst_rating ? ` · ${r.analyst_rating}` : ''}
        </p>
      )}

      <h2>Fundamental scorecard</h2>
      <p className="muted small">Hover a factor for what it means and its typical range. ▲ supporting · ▼ dragging the verdict; % = weight.</p>
      {['Valuation', 'Quality', 'Health', 'Growth'].map(cat => {
        const c = sc.categories[cat]
        if (!c) return null
        return (
          <div key={cat} className="catblock">
            <h3>{cat} {c.score != null && <small>{Math.round(c.score * 100)}/100</small>}</h3>
            {c.factors.map((f, i) => (
              <div className="factor" key={i} title={f.tip}>
                <span className="fl">{f.spec_label} <span className="info">ⓘ</span></span>
                <span className="fv">{f.value}</span>
                <span className="chip sm" style={{ background: scoreColor(f.score) }}>{f.status}</span>
                <span className="fc">
                  {f.pull === 'supporting' ? '▲' : f.pull === 'dragging' ? '▼' : '•'} {f.scored ? f.contribution + '%' : '—'}
                </span>
              </div>
            ))}
          </div>
        )
      })}

      <h2>Timing signals</h2>
      {[['sell', 'SELL'], ['reentry', 'RE-ENTRY'], ['hold', 'STOP-LOOP / HOLD']].map(([k, label]) => (
        <div key={k} className="sigblock">
          <strong>{label} — {r.counts[k]}/3 met</strong>
          {r.signals[k].map((s, i) => (
            <div key={i} className="sig">{s.met ? '✅' : '▫️'} {s.reason}</div>
          ))}
        </div>
      ))}

      {plan && (
        <>
          <h2>Re-entry plan</h2>
          <p className="muted small">Basis: {plan.basis}</p>
          <div className="metrics">
            <div><small>Reserve</small><b>${plan.reserve_budget.toLocaleString()}</b></div>
            <div><small>Profit</small><b>${plan.profit.toLocaleString()}</b></div>
            <div><small>Sold</small><b>${plan.sell_price.toFixed(2)} × {plan.shares_sold}</b></div>
          </div>
          {plan.sizing.map((s, i) => (
            <div key={i} className="size">
              <strong>{s.level}</strong> ~${s.price.toFixed(2)} → {s.whole_shares} whole / {s.total_shares.toFixed(2)} total ({s.vs_original >= 0 ? '+' : ''}{s.vs_original.toFixed(2)} vs sold)
            </div>
          ))}
        </>
      )}

      {(d.detail?.splits?.length > 0 || d.catalysts?.length > 0) && (
        <>
          <h2>Catalysts & events</h2>
          {d.detail.splits?.length > 0 && (() => {
            const s0 = d.detail.splits[0]
            const ratio = (s0.split_to && s0.split_from) ? `${s0.split_to}-for-${s0.split_from}` : 'split'
            const when = (s0.execution_date || '') > new Date().toISOString().slice(0, 10) ? 'Upcoming' : 'Last'
            return <p><strong>{when} split:</strong> {ratio} {(s0.adjustment_type || '').replace('_', ' ')} on {s0.execution_date}</p>
          })()}
          {d.catalysts?.map((c, i) => (
            <div key={i} className="cat"><strong>{c.type}</strong> — <a href={c.url} target="_blank" rel="noreferrer">{c.headline}</a></div>
          ))}
        </>
      )}

      {d.news_digest && (
        <>
          <h2>News & sentiment</h2>
          <p><strong>{d.news_digest.net}</strong> — {d.news_digest.counts.positive}▲ / {d.news_digest.counts.neutral}• / {d.news_digest.counts.negative}▼ across {d.news_digest.counts.total}</p>
          <p>Momentum: {d.news_digest.momentum}</p>
          {d.news_digest.themes?.length > 0 && <p>Themes: {d.news_digest.themes.join(' · ')}</p>}
        </>
      )}
      {(d.detail?.news || []).slice(0, 6).map((a, i) => (
        <div className="news" key={i}>
          <a href={a.url} target="_blank" rel="noreferrer">{a.title}</a>
          <small> {a.publisher}{a.published ? ` · ${a.published}` : ''}{a.sentiment ? ` · ${a.sentiment}` : ''}</small>
        </div>
      ))}
    </div>
  )
}
