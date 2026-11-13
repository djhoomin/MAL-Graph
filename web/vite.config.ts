import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Same origin as production (Caddy proxies /api), so the sign-in cookie works in dev too.
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
