import { defineConfig } from 'vite'

// The page is served from its own vendor folder under a strict policy (deploy/nginx/frappe.conf.template, D-325's
// pattern): relative paths only, and no inline script (Vite's module-preload polyfill is one).
export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2022',
    modulePreload: { polyfill: false },
    chunkSizeWarningLimit: 8000,
  },
})
