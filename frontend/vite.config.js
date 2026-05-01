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
    // node-Environment reicht für die aktuelle Smoke-Coverage (api/envelope.ts);
    // Vue-Component- und DOM-Tests in EPIC-10-ST-07 werden auf jsdom umstellen.
    environment: 'node',
    include: ['src/**/*.{test,spec}.{js,ts}'],
    globals: false
  }
})
