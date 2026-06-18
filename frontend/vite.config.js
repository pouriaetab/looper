import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The React app proxies /api calls to the FastAPI backend so there are no CORS
// issues. Ports are read from the environment (BACKEND_PORT / FRONTEND_PORT) so
// Control Deck can assign unique ones; they fall back to the defaults otherwise.
const FRONTEND_PORT = Number(process.env.FRONTEND_PORT) || 5173
const BACKEND_PORT = Number(process.env.BACKEND_PORT) || 8000

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',   // bind IPv4 so http://127.0.0.1:PORT is always reachable
    port: FRONTEND_PORT,
    strictPort: true,    // use exactly this port (fail loudly) instead of drifting
    proxy: {
      '/api': `http://127.0.0.1:${BACKEND_PORT}`,
    },
  },
})
