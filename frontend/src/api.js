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
export const getQuotes = (tickers) =>
  fetch(`/api/quotes?tickers=${encodeURIComponent((tickers || []).join(','))}`).then(j)
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
export const getPairedLedger = () => fetch('/api/ledger/paired').then(j)

// Profit deployment: net profit taken -> target ETF/theme allocation
export const getProfit = () => fetch('/api/profit').then(j)
export const setAllocation = (sleeves) =>
  fetch('/api/profit/allocation', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sleeves }),
  }).then(j)
export const deployProfit = (amount, note = null) =>
  fetch('/api/profit/deploy', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount, note }),
  }).then(j)
export const undoDeployment = (idx) =>
  fetch(`/api/profit/deploy/${idx}`, { method: 'DELETE' }).then(j)

// Manually add to (direction 'add') or reduce (direction 'reduce') the re-entry reserve.
export const adjustReserve = (amount, direction) =>
  fetch('/api/reserve/adjust', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount, direction }),
  }).then(j)

// Edit the ledger as a master file: fix a value in one row, or delete a row.
export const updateLedgerRow = (index, fields) =>
  fetch(`/api/ledger/${index}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  }).then(j)

export const deleteLedgerRow = (index) =>
  fetch(`/api/ledger/${index}`, { method: 'DELETE' }).then(j)

export const getSettings = () => fetch('/api/settings').then(j)
export const setHorizon = (horizon) =>
  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ horizon }),
  }).then(j)

// Deep Opportunity Scan (background job)
export const startScan = () => fetch('/api/scan/start', { method: 'POST' }).then(j)
export const scanStatus = () => fetch('/api/scan/status').then(j)

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
