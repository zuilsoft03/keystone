import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

// The build is served by Frappe's nginx from /assets/construction_shell/shell/ (D-111). There is no index.html: the
// page is rendered by construction_shell/www/ws_workspace.html, which reads the entry's files from the manifest.
export default defineConfig({
  base: '/assets/construction_shell/shell/',
  plugins: [vue()],
  resolve: {
    dedupe: ['vue'],
    alias: { '@shell': fileURLToPath(new URL('../construction_shell', import.meta.url)) },
  },
  // frappe-ui ships .vue sources: plugin-vue compiles them like ours.
  optimizeDeps: { exclude: ['frappe-ui'] },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    manifest: true,
    chunkSizeWarningLimit: 2000,
    // The workspace (P2-02), the client portal (P2-06, D-121) and the join page (P3-17, D-214): shared chunks.
    rollupOptions: {
      input: ['src/main.js', 'src/portal.js', 'src/join.js', 'src/login.js', 'src/mailbox.js', 'src/dispute.js'],  // P3-24: the sign-in page; P3-77: the mailbox confirm page; P3-78: "This was not me"
      // The shared stylesheet keeps its own chunk, whatever code the entries come to share (P3-20, D-232).
      output: { manualChunks: (id) => (/\/src\/style\.css$|frappe-ui\/style\.css$/.test(id) ? 'style' : undefined) },
    },
  },
})
