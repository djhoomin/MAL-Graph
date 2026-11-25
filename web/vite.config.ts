import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

/** The graph page's files are only known by name after the build. On the home page this asks for them straight away,
 *  alongside the first script, rather than once that script has run. Other pages don't fetch them. */
const preloadGraph: Plugin = {
  name: 'preload-graph',
  transformIndexHtml: {
    order: 'post',
    handler(_html, { bundle }) {
      if (!bundle) return
      const chunks = Object.values(bundle).filter((c) => c.type === 'chunk')
      const page = chunks.find((c) => c.facadeModuleId?.endsWith('/GraphPage.tsx'))
      if (!page) throw new Error('preload-graph: no GraphPage chunk')
      const entry = chunks.find((c) => c.isEntry)
      const files = new Set<string>()
      const add = (file: string) => {
        if (files.has(file) || file === entry?.fileName) return
        files.add(file)
        chunks.find((c) => c.fileName === file)?.imports.forEach(add)
      }
      add(page.fileName)
      const list = JSON.stringify([...files].map((f) => '/' + f))
      const code = `if(/^#?\\/?$/.test(location.hash))for(const h of ${list}){const l=document.createElement('link');l.rel='modulepreload';l.crossOrigin='';l.href=h;document.head.append(l)}`
      return [{ tag: 'script', children: code, injectTo: 'head' }]
    },
  },
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), preloadGraph],
  // Same origin as production (Caddy proxies /api), so the sign-in cookie works in dev too.
  // API_PROXY points dev at another API, for example a second uvicorn with sign-in turned off.
  server: { proxy: { '/api': process.env.API_PROXY ?? 'http://localhost:8000' } },
})
