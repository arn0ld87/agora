/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
        secure: false
      }
    }
  },
  test: {
    // jsdom-Environment seit EPIC-10-ST-07 (Issue #84) — Composable-Tests
    // brauchen DOM-APIs (mount/unmount, EventSource-Mock, document.body).
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{js,ts}'],
    globals: false
  }
})
