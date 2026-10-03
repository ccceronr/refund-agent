/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The app serves the built frontend itself (design §1 "Serving"). In development,
// the Vite dev server forwards /api to the app so the browser still sees one origin.
const API_TARGET = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': API_TARGET,
    },
  },
  test: {
    environment: 'node',
  },
})
