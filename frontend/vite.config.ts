/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Local dev proxies the FastAPI surface so the app can run against
// `uvicorn insmart_api.app:app` with no CORS changes on the backend.
const apiProxy = Object.fromEntries(
  ['/assets', '/ingest', '/diagnoses', '/review', '/health'].map((path) => [
    path,
    { target: 'http://localhost:8000' },
  ]),
)

export default defineConfig({
  plugins: [react()],
  server: { proxy: apiProxy },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
