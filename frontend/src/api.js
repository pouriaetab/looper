// Thin wrapper around the LOOPER FastAPI endpoints.
async function j(resp) {
  if (!resp.ok) {
    let detail = resp.statusText
    try { detail = (await resp.json()).detail || detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json()
}

export const getPortfolio = () => fetch('/api/portfolio').then(j)
export const getStock = (ticker) => fetch(`/api/stock/${ticker}`).then(j)
export const getConfig = () => fetch('/api/config').then(j)

export const addStock = (body) =>
  fetch('/api/stocks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(j)

export const removeStock = (ticker) =>
  fetch(`/api/stocks/${ticker}`, { method: 'DELETE' }).then(j)

export const sellStock = (ticker, body) =>
  fetch(`/api/stocks/${ticker}/sell`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(j)

export const getTally = () => fetch('/api/tally').then(j)
export const getLedger = () => fetch('/api/ledger').then(j)

export const getSettings = () => fetch('/api/settings').then(j)
export const setTimespan = (timespan) =>
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ timespan }),
  }).then(j)

// Phase 4: Candidates & Watchlist
export const getCandidates = (limit = 10) => fetch(`/api/candidates?limit=${limit}`).then(j)

export const getWatchlist = () => fetch('/api/watchlist').then(j)

export const addToWatchlist = (ticker, notes = null) =>
  fetch(`/api/watchlist?ticker=${ticker}${notes ? `&notes=${encodeURIComponent(notes)}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  }).then(j)

export const removeFromWatchlist = (ticker) =>
  fetch(`/api/watchlist/${ticker}`, { method: 'DELETE' }).then(j)
