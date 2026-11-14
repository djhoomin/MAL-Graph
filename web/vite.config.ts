import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Same origin as production (Caddy proxies /api), so the sign-in cookie works in dev too.
  // API_PROXY points dev at another API, for example a second uvicorn with sign-in turned off.
  server: { proxy: { '/api': process.env.API_PROXY ?? 'http://localhost:8000' } },
})
