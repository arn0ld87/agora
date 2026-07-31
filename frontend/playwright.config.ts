import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  // Ein versehentlich committetes test.only wuerde in CI sonst still den
  // gesamten Rest der Datei ueberspringen und trotzdem gruen melden.
  forbidOnly: !!process.env.CI,
  // Ein Retry NUR in CI. Das ist kein Gruen-Faerben: Playwright meldet einen
  // Test, der erst im Retry besteht, als "flaky" — nicht als "passed". Damit
  // wird Instabilitaet sichtbar protokolliert statt wie bisher als harter
  // Fehlschlag, den jemand manuell nachlaufen laesst (ohne Spur). Alle sechs
  // Smokes sind Required Checks; ein Cold-Start-Hickser im Docker-Stack
  // blockierte bisher den PR und kostete einen kompletten 25-min-Rerun.
  // Lokal bleibt es bei 0, damit Flakiness beim Entwickeln sofort auffaellt.
  retries: process.env.CI ? 1 : 0,
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
