import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Proxy all API routes to the FastAPI backend on port 8000
      // NOTE: /auth is NOT proxied — auth is handled entirely in the frontend
      // against a local users.json file (see src/lib/auth.js).
      '^/api': { target: 'http://localhost:8000', changeOrigin: true },
      '^/chat': { target: 'http://localhost:8000', changeOrigin: true },
      '^/history': { target: 'http://localhost:8000', changeOrigin: true },
      '^/feedback': { target: 'http://localhost:8000', changeOrigin: true },
      '^/preferences': { target: 'http://localhost:8000', changeOrigin: true },
      '^/places': { target: 'http://localhost:8000', changeOrigin: true },
      '^/city': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
