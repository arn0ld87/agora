/**
 * Slice 7.2 — Golden-Gate Accessibility Gates.
 *
 * Wiederverwendbare Playwright-Gates für Shell, Settings, Onboarding und Picker.
 * Prüft pro Route:
 * - axe-core ohne serious/critical violations
 * - 320×800 Viewport ohne horizontales Dokument-Scrollen
 * - Tastaturbedienung (Tab-Navigation)
 * - Focus sichtbar (:focus-visible)
 * - Reduced Motion (prefers-reduced-motion: reduce)
 *
 * Stack: Playwright + axe-core (siehe global-setup.ts + scripts/e2e-up.sh).
 * Auth: Single-User-Token-Mode via localStorage (siehe helpers/auth.ts).
 */
import { test } from '@playwright/test';
import { injectAuthToken } from './helpers/auth';
import {
  checkAccessibilityGate,
  runAxe,
  assertNoCriticalViolations,
  check320pxNoHorizontalScroll,
  checkKeyboardNavigation,
  checkFocusVisible,
  checkReducedMotion,
} from './helpers/accessibility';

test.describe('Slice 7.2 · Golden-Gate Accessibility Gates', () => {
  test.beforeEach(async ({ context }) => {
    await injectAuthToken(context);
  });

  test.describe('Shell', () => {
    test('Dashboard passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/dashboard');
    });

    test('Runs passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/runs');
    });
  });

  test.describe('Settings', () => {
    test('Settings General passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/general');
    });

    test('Settings Integrations passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/integrations');
    });

    test('Settings Profile passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/profile');
    });

    test('Settings API Keys passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/api-keys');
    });

    test('Settings LLM Providers passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/llm-providers');
    });

    test('Settings Embedding passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/settings/embedding');
    });
  });

  test.describe('Onboarding', () => {
    test('Onboarding passes accessibility gates', async ({ page }) => {
      await checkAccessibilityGate(page, '/onboarding');
    });
  });

  test.describe('Picker', () => {
    test('AiModelPicker in LLM Routing passes accessibility gates', async ({ page }) => {
      // Picker benötigt Run-ID für RunLlmRoutingPanel
      await page.goto('/settings/llm-routing', { waitUntil: 'domcontentloaded' });
      await page.getByTestId('run-id-input').fill('run_e2e_accessibility');

      // Warte bis Picker gerendert ist
      await page.waitForSelector('[data-testid="ai-model-picker"]', { timeout: 5000 });

      // axe-core
      const axeResults = await runAxe(page);
      assertNoCriticalViolations(axeResults);

      // 320px
      await check320pxNoHorizontalScroll(page);

      // Reset viewport
      await page.setViewportSize({ width: 1280, height: 720 });

      // Keyboard
      await checkKeyboardNavigation(page);

      // Focus visible
      await checkFocusVisible(page);

      // Reduced motion
      await checkReducedMotion(page);
    });
  });
});
