import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build target: ../agent/static so FastAPI's StaticFiles mount serves the
// production bundle the same way it served the previous vanilla index.html.
// Dev mode: proxy /chat and /health to the running uvicorn on :8000.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../agent/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/chat': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
})
