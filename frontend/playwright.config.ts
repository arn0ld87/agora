import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  // Ein versehentlich committetes test.only wuerde in CI sonst still den
  // gesamten Rest der Datei ueberspringen und trotzdem gruen melden.
  forbidOnly: !!process.env.CI,
  // Ein Retry NUR in CI — ausschliesslich fuer die Diagnose: der Report weist
  // den Test als "flaky" statt "failed" aus, und `trace: retain-on-failure`
  // (unten) behaelt den Trace des FEHLGESCHLAGENEN Versuchs. Der Trace des
  // bestandenen Retrys wird von diesem Modus bewusst verworfen — fuer die
  // Fehlersuche ist der fehlgeschlagene Versuch der aussagekraeftige, und
  // `retain-on-failure-and-retries` wuerde die Artefakte ohne echten
  // Mehrwert vergroessern. Lokal bleibt es bei 0, damit Flakiness beim
  // Entwickeln sofort auffaellt.
  retries: process.env.CI ? 1 : 0,
  // ZWINGEND zusammen mit `retries`: ohne diese Zeile beendet Playwright einen
  // Lauf mit flaky-Tests mit Exit-Code 0. Da alle sechs Smokes Required Checks
  // sind, wuerde eine intermittierende Regression damit zum gruenen Merge-Gate
  // — das Gate waere schwaecher als vorher, nicht nur besser instrumentiert.
  // `retries` allein macht Instabilitaet sichtbar; erst `failOnFlakyTests`
  // haelt sie auch rot. (Codex-Finding P1 zu PR #977.)
  failOnFlakyTests: !!process.env.CI,
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
