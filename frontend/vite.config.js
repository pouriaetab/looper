import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev, the React app runs on :5173 and proxies /api calls to the FastAPI
// backend on :8000, so there are no CORS issues and you use one URL in the browser.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
