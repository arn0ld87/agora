/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'agora-design-v3-showcase-index',
      configureServer(server) {
        server.middlewares.use('/design/v3/', (req, res, next) => {
          if (req.url && req.url !== '/') {
            next()
            return
          }
          const file = resolve(server.config.publicDir, 'design/v3/index.html')
          res.setHeader('Content-Type', 'text/html;charset=utf-8')
          res.end(readFileSync(file, 'utf-8'))
        })
      },
    },
  ],
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
      // M11.3 Step1 (2026-05-10): Schwellen auf 26 % angehoben (vorgezogen, war
      // 2026-06-04 geplant). Ist-Werte 2026-05-10: statements=50.46 %,
      // branches=39.56 %, functions=38.59 %, lines=52.50 % — alle vier
      // deutlich ueber 26 %. Naechste Anhebung: 2026-06-10 → 28 %.
      thresholds: {
        lines: 26,
        functions: 26,
        branches: 26,
        statements: 26,
      },
    },
  }
})
