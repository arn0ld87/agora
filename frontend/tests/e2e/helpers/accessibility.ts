import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';
import type { AxeResults, Result } from 'axe-core';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Slice 7.2 — Accessibility-Gate Helper.
 *
 * Stellt wiederverwendbare Playwright-Gates für WCAG-AA-Konformität bereit:
 * - axe-core ohne serious/critical violations
 * - 320×800 Viewport ohne horizontales Dokument-Scrollen
 * - Tastaturbedienung (Tab-Navigation)
 * - Focus sichtbar (:focus-visible)
 * - Reduced Motion (prefers-reduced-motion: reduce)
 */

export interface AxeCheckOptions {
  rules?: Record<string, { enabled: boolean }>;
}

/**
 * Führt axe-core im Browser-Kontext aus und gibt die Results zurück.
 */
export async function runAxe(
  page: Page,
  options: AxeCheckOptions = {},
): Promise<AxeResults> {
  // Inject axe-core script in browser context
  const axePath = resolve(__dirname, '../../../node_modules/axe-core/axe.min.js');
  await page.addScriptTag({ path: axePath });

  return page.evaluate(async (opts) => {
    // @ts-expect-error — axe is injected via addScriptTag
    return window.axe.run(document, opts);
  }, options);
}

/**
 * Prüft, dass keine serious oder critical violations vorliegen.
 */
export function assertNoCriticalViolations(results: AxeResults): void {
  const violations = results.violations.filter(
    (v: Result) => v.impact === 'serious' || v.impact === 'critical',
  );

  if (violations.length > 0) {
    const summary = violations
      .map(
        (v: Result) =>
          `[${v.impact}] ${v.id}: ${v.description} (${v.nodes.length} nodes)`,
      )
      .join('\n');
    throw new Error(`Accessibility violations found:\n${summary}`);
  }
}

/**
 * Setzt Viewport auf 320×800 und prüft, dass kein horizontales Dokument-Scrollen nötig ist.
 */
export async function check320pxNoHorizontalScroll(page: Page): Promise<void> {
  await page.setViewportSize({ width: 320, height: 800 });

  const hasHorizontalScroll = await page.evaluate(() => {
    return document.documentElement.scrollWidth > document.documentElement.clientWidth;
  });

  expect(hasHorizontalScroll).toBe(false);
}

/**
 * Prüft Tastatur-Navigation durch alle fokussierbaren Elemente.
 */
export async function checkKeyboardNavigation(
  page: Page,
  tabCount: number = 10,
): Promise<void> {
  const focusableSelectors = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ');

  const focusableCount = await page.locator(focusableSelectors).count();
  expect(focusableCount).toBeGreaterThan(0);

  // Tab durch die ersten N Elemente
  for (let i = 0; i < Math.min(tabCount, focusableCount); i++) {
    await page.keyboard.press('Tab');
  }

  // Prüfe, dass ein Element fokussiert ist
  const hasFocus = await page.evaluate(() => {
    return document.activeElement !== null && document.activeElement !== document.body;
  });

  expect(hasFocus).toBe(true);
}

/**
 * Prüft, dass :focus-visible Styles vorhanden sind.
 */
export async function checkFocusVisible(page: Page): Promise<void> {
  // Fokussiere das erste fokussierbare Element
  await page.keyboard.press('Tab');

  const hasFocusVisible = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el === document.body) return false;

    // Prüfe computed style für outline oder box-shadow
    const style = window.getComputedStyle(el);
    const hasOutline = style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0;
    const hasBoxShadow = style.boxShadow !== 'none';
    const hasBorder = style.borderStyle !== 'none' && parseFloat(style.borderWidth) > 0;

    return hasOutline || hasBoxShadow || hasBorder;
  });

  expect(hasFocusVisible).toBe(true);
}

/**
 * Prüft, dass prefers-reduced-motion: reduce nicht-essentielle Animationen unterdrückt.
 */
export async function checkReducedMotion(page: Page): Promise<void> {
  // Emuliere prefers-reduced-motion: reduce
  await page.emulateMedia({ reducedMotion: 'reduce' });

  // Prüfe, dass transition-duration für animierte Elemente 0 oder sehr kurz ist
  const hasReducedMotion = await page.evaluate(() => {
    const animatedElements = document.querySelectorAll(
      '[class*="animate"], [class*="transition"], [style*="transition"]',
    );

    const isReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    for (const el of animatedElements) {
      const style = window.getComputedStyle(el);
      const transitionDuration = parseFloat(style.transitionDuration || '0');
      const animationDuration = parseFloat(style.animationDuration || '0');
      if (isReduced && (transitionDuration > 0.1 || animationDuration > 0.1)) {
        return false;
      }
    }
    return true;
  });

  expect(hasReducedMotion).toBe(true);

  // Reset
  await page.emulateMedia({ reducedMotion: 'no-preference' });
}

/**
 * Kombinierte Accessibility-Prüfung für eine Route.
 */
export async function checkAccessibilityGate(
  page: Page,
  route: string,
  options: AxeCheckOptions = {},
): Promise<void> {
  await page.goto(route, { waitUntil: 'domcontentloaded' });

  // axe-core
  const axeResults = await runAxe(page, options);
  assertNoCriticalViolations(axeResults);

  // 320px
  await check320pxNoHorizontalScroll(page);

  // Reset viewport für weitere Checks
  await page.setViewportSize({ width: 1280, height: 720 });

  // Keyboard
  await checkKeyboardNavigation(page);

  // Focus visible
  await checkFocusVisible(page);

  // Reduced motion
  await checkReducedMotion(page);
}
