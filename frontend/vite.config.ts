import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * In development the browser talks only to Vite (localhost:5173). Vite
 * forwards /api and /health to FastAPI, so requests are same-origin and the
 * session cookie works without CORS.
 */
const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: false,
  },
  '/health': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: false,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: apiProxy,
  },
  preview: {
    port: 4173,
    proxy: apiProxy,
  },
})
