import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { mockFhirPlugin } from './mock-fhir/plugin'

// Build target: ../agent/static_dashboard so FastAPI's StaticFiles can mount the
// production bundle at /dashboard alongside the existing Co-Pilot UI at /.
// Dev mode runs on :5174 (Co-Pilot UI uses :5173) and ships an in-memory
// FHIR server at /dashboard-fhir for card development against curated data.
export default defineConfig({
  plugins: [react(), mockFhirPlugin()],
  base: '/dashboard/',
  build: {
    outDir: '../agent/static_dashboard',
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    proxy: {
      // OpenEMR REST proxy (used when targeting a real OpenEMR instance).
      '/openemr-api': {
        target: process.env.VITE_OPENEMR_BASE_URL ?? 'http://localhost:8080',
        changeOrigin: true,
        secure: false,
        rewrite: (p) => p.replace(/^\/openemr-api/, ''),
      },
    },
  },
})
