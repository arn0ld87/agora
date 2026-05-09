import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: process.env.CI ? [['list'], ['github']] : 'list',
  globalSetup: './tests/e2e/global-setup.ts',
  globalTeardown: './tests/e2e/global-teardown.ts',
  use: {
    baseURL: process.env.AGORA_E2E_BASE_URL ?? 'http://127.0.0.1:80',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  // KEIN webServer-Hook (siehe Cut-Analyse §4.2): docker-compose-Lifecycle
  // wird über global-setup.ts/global-teardown.ts via scripts/e2e-up.sh/down.sh
  // verwaltet, weil Playwrights webServer den Container-Detach nicht
  // erkennen kann.
});
