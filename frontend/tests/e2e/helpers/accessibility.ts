import type { ElementHandle, Page } from '@playwright/test';
import { expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

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

export type AxeCheckOptions = Parameters<AxeBuilder['options']>[0];
export type AxeResults = Awaited<ReturnType<AxeBuilder['analyze']>>;
export type Result = AxeResults['violations'][number];

export interface FocusStyleSnapshot {
  outlineStyle: string;
  outlineWidth: string;
  outlineColor: string;
  outlineOffset: string;
  boxShadow: string;
  borderTopStyle: string;
  borderTopWidth: string;
  borderTopColor: string;
  borderRightStyle: string;
  borderRightWidth: string;
  borderRightColor: string;
  borderBottomStyle: string;
  borderBottomWidth: string;
  borderBottomColor: string;
  borderLeftStyle: string;
  borderLeftWidth: string;
  borderLeftColor: string;
}

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ');

const FOCUS_STYLE_PROPERTIES: Record<keyof FocusStyleSnapshot, string> = {
  outlineStyle: 'outline-style',
  outlineWidth: 'outline-width',
  outlineColor: 'outline-color',
  outlineOffset: 'outline-offset',
  boxShadow: 'box-shadow',
  borderTopStyle: 'border-top-style',
  borderTopWidth: 'border-top-width',
  borderTopColor: 'border-top-color',
  borderRightStyle: 'border-right-style',
  borderRightWidth: 'border-right-width',
  borderRightColor: 'border-right-color',
  borderBottomStyle: 'border-bottom-style',
  borderBottomWidth: 'border-bottom-width',
  borderBottomColor: 'border-bottom-color',
  borderLeftStyle: 'border-left-style',
  borderLeftWidth: 'border-left-width',
  borderLeftColor: 'border-left-color',
};

const BORDER_SIDES = ['Top', 'Right', 'Bottom', 'Left'] as const;

function splitBoxShadowLayers(value: string): string[] {
  const layers: string[] = [];
  let depth = 0;
  let layerStart = 0;

  for (let index = 0; index < value.length; index += 1) {
    if (value[index] === '(') depth += 1;
    if (value[index] === ')') depth = Math.max(0, depth - 1);
    if (value[index] === ',' && depth === 0) {
      layers.push(value.slice(layerStart, index).trim());
      layerStart = index + 1;
    }
  }

  layers.push(value.slice(layerStart).trim());
  return layers;
}

function isVisibleBoxShadow(value: string): boolean {
  const zeroAlpha = String.raw`(?:0(?:\.0+)?|\.0+)%?`;
  const legacyTransparent = new RegExp(
    String.raw`rgba\(\s*(?:[^,]+,\s*){3}${zeroAlpha}\s*\)`,
    'i',
  );
  const modernTransparent = new RegExp(
    String.raw`(?:rgba?|hsla?|color)\([^)]*\/\s*${zeroAlpha}\s*\)`,
    'i',
  );

  return splitBoxShadowLayers(value).some((layer) => {
    const isTransparent =
      /\btransparent\b/i.test(layer) ||
      legacyTransparent.test(layer) ||
      modernTransparent.test(layer);
    const lengths = layer.match(/-?(?:\d+(?:\.\d*)?|\.\d+)px/g) ?? [];
    return !isTransparent && lengths.some((length) => Number.parseFloat(length) !== 0);
  });
}

export function diffFocusStyle(before: FocusStyleSnapshot, after: FocusStyleSnapshot): boolean {
  const outlineChanged = (['outlineStyle', 'outlineWidth', 'outlineColor', 'outlineOffset'] as const).some(
    (property) => before[property] !== after[property],
  );
  const hasVisibleOutline = after.outlineStyle !== 'none' && Number.parseFloat(after.outlineWidth) > 0;

  const boxShadowChanged = before.boxShadow !== after.boxShadow;
  const hasVisibleBoxShadow = isVisibleBoxShadow(after.boxShadow);

  const hasVisibleBorderChange = BORDER_SIDES.some((side) => {
    const sideChanged = ([`border${side}Style`, `border${side}Width`, `border${side}Color`] as const).some(
      (property) => before[property] !== after[property],
    );
    return (
      sideChanged &&
      after[`border${side}Style`] !== 'none' &&
      Number.parseFloat(after[`border${side}Width`]) > 0
    );
  });

  return (
    (outlineChanged && hasVisibleOutline) ||
    (boxShadowChanged && hasVisibleBoxShadow) ||
    hasVisibleBorderChange
  );
}

export function parseMaxDuration(value: string): number {
  const durations = value.split(',').map((entry) => {
    const match = /^(-?(?:\d+(?:\.\d*)?|\.\d+))(ms|s)?$/i.exec(entry.trim());
    if (!match) return 0;

    const duration = Number.parseFloat(match[1]);
    if (!Number.isFinite(duration) || duration < 0) return 0;
    return match[2]?.toLowerCase() === 'ms' ? duration / 1000 : duration;
  });

  return Math.max(0, ...durations);
}

async function captureFocusStyle(element: ElementHandle<HTMLElement>): Promise<FocusStyleSnapshot> {
  return element.evaluate((node, properties) => {
    const style = window.getComputedStyle(node);
    return Object.fromEntries(
      Object.entries(properties).map(([key, property]) => [key, style.getPropertyValue(property)]),
    ) as unknown as FocusStyleSnapshot;
  }, FOCUS_STYLE_PROPERTIES);
}

/**
 * Führt axe-core im Browser-Kontext aus und gibt die Results zurück.
 */
export async function runAxe(page: Page, options: AxeCheckOptions = {}): Promise<AxeResults> {
  return new AxeBuilder({ page }).options(options).analyze();
}

/**
 * Prüft, dass keine serious oder critical violations vorliegen.
 */
export function assertNoCriticalViolations(results: AxeResults): void {
  const violations = results.violations.filter((v: Result) => v.impact === 'serious' || v.impact === 'critical');

  if (violations.length > 0) {
    const summary = violations
      .map((v: Result) => `[${v.impact}] ${v.id}: ${v.description} (${v.nodes.length} nodes)`)
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
export async function checkKeyboardNavigation(page: Page, tabCount: number = 10): Promise<void> {
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
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  });

  const focusableElements = (await page.locator(FOCUSABLE_SELECTOR).elementHandles()) as ElementHandle<HTMLElement>[];
  try {
    expect(focusableElements.length).toBeGreaterThan(0);
    const beforeStyles = await Promise.all(focusableElements.map(captureFocusStyle));

    await page.keyboard.press('Tab');
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));

    let focusedIndex = -1;
    for (let index = 0; index < focusableElements.length; index += 1) {
      if (await focusableElements[index].evaluate((element) => element === document.activeElement)) {
        focusedIndex = index;
        break;
      }
    }

    const afterStyle = focusedIndex >= 0 ? await captureFocusStyle(focusableElements[focusedIndex]) : undefined;
    expect(afterStyle ? diffFocusStyle(beforeStyles[focusedIndex], afterStyle) : false).toBe(true);
  } finally {
    await Promise.all(focusableElements.map((element) => element.dispose()));
  }
}

/**
 * Prüft, dass prefers-reduced-motion: reduce nicht-essentielle Animationen unterdrückt.
 */
export async function checkReducedMotion(page: Page): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  try {
    const reducedMotion = await page.evaluate(() => {
      const animatedElements = document.querySelectorAll(
        '[class*="animate"], [class*="transition"], [style*="transition"]',
      );

      return {
        isReduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        durations: Array.from(animatedElements, (element) => {
          const style = window.getComputedStyle(element);
          return [style.transitionDuration, style.animationDuration];
        }).flat(),
      };
    });

    expect(reducedMotion.isReduced).toBe(true);
    expect(reducedMotion.durations.every((value) => parseMaxDuration(value) <= 0.1)).toBe(true);
  } finally {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
  }
}

/**
 * Kombinierte Accessibility-Prüfung für eine Route.
 */
export async function checkAccessibilityGate(page: Page, route: string, options: AxeCheckOptions = {}): Promise<void> {
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
