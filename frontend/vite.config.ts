import { defineConfig } from 'vite';

// The dev server proxies /api to the backend. Override the target with VITE_API_TARGET when the
// backend runs on another port, e.g. VITE_API_TARGET=http://127.0.0.1:8001 npm run dev.
const target = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000';

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, '') } },
  },
});
