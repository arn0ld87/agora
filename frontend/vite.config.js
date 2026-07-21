/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
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
    // Issue #811: pinia 4 + @pinia/testing 2 (Dependabot) haben unter dem
    // Standard-"forks"-Pool eine Vitest-interne Worker-Teardown-Race
    // sichtbar gemacht (EnvironmentTeardownError bzw. "Failed to start
    // forks worker" / "Timeout waiting for worker to respond" beim
    // Prozess-Cleanup). Ursache ist keine pinia-API-Aenderung, sondern
    // Vitest-Forks-Pool-Verhalten unter paralleler Prozess-Last; pinia 4
    // aendert nur die Cleanup-Reihenfolge in setActivePinia/createPinia
    // und erhoeht damit die Trefferwahrscheinlichkeit. Threads-Pool haelt
    // Worker als Worker-Threads im selben Prozess statt als Child-Prozesse
    // und vermeidet damit die Fork-Spawn/Teardown-Race.
    pool: 'threads',
    // Issue #797 (Restproblem nach #811): auch mit dem threads-Pool trat
    // sporadisch "EnvironmentTeardownError: Closing rpc while
    // onUserConsoleLog was pending" auf — Ursache ist Vitests eigener
    // console-Intercept-Mechanismus, der jede console.*-Ausgabe per RPC an
    // den Hauptprozess weiterreicht. Beim Worker-Teardown kann dieser RPC-
    // Call noch offen sein, wenn der Worker geschlossen wird. Globale
    // Deaktivierung des Intercepts entfernt den racenden Mechanismus fuer
    // die gesamte Suite, statt ihn pro Spec mit console-Spies zu umgehen.
    disableConsoleIntercept: true,
    // jsdom-Environment seit EPIC-10-ST-07 (Issue #84) — Composable-Tests
    // brauchen DOM-APIs (mount/unmount, EventSource-Mock, document.body).
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{js,ts}', 'tests/**/*.{test,spec}.{js,ts}'],
    exclude: ['tests/e2e/**', 'node_modules/**', 'dist/**'],
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
      // M11.3 Step2 (2026-06-10): Schwellen auf 28 % angehoben.
      // Ist-Werte 2026-05-10: statements=50.46 %, branches=39.56 %,
      // functions=38.59 %, lines=52.50 % — alle vier deutlich ueber 28 %.
      thresholds: {
        lines: 28,
        functions: 28,
        branches: 28,
        statements: 28,
      },
    },
  }
})
