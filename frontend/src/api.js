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
