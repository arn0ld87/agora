/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    open: true,
    host: true,
    allowedHosts: ['.ts.net', 'localhost', '127.0.0.1'],
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
    globals: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      reportsDirectory: 'coverage',
      include: ['src/**/*.{js,ts,vue}'],
      exclude: [
        'src/**/*.{test,spec}.{js,ts}',
        'src/**/__mocks__/**',
        'src/main.{js,ts}',
        'src/router/**',
        'src/types/**',
      ],
      // Startschwelle M11.3: Ist-Wert branches=26.70% ist Bottleneck-Metrik
      // (vollständiger include: src/**/*.{js,ts,vue} erfasst auch untestete Views).
      // PLAN-Default 60 % nicht erreichbar (viele Vue-SFCs ohne Browsertest-Pfad).
      // Fallback-Formel: floor(26.70 - 2) = 24. Roadmap: +2 Punkte/Monat bis 80 %.
      thresholds: {
        lines: 24,
        functions: 24,
        branches: 24,
        statements: 24,
      },
    },
  }
})
