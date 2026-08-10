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
export async function runAxe(
  page: Page,
  options: AxeCheckOptions = {},
  guard: { allowOnboarding?: boolean } = {},
): Promise<AxeResults> {
  // Issue #988: zweite Verteidigungslinie für Specs, die runAxe direkt nach
  // eigenem page.goto aufrufen und deshalb nicht durch die Prüfung in
  // checkAccessibilityGate laufen. Ohne sie prüft ein vergessener
  // Onboarding-Bypass den Wizard und meldet grün.
  if (!guard.allowOnboarding && pathOf(page.url()).startsWith('/onboarding')) {
    throw new Error(
      'runAxe laeuft auf /onboarding. Entweder fehlt der Bypass ' +
        '(ensureOnboardingDismissed(page) vor dem page.goto) — dann prueft das ' +
        'Gate den Wizard statt der Zielseite —, oder der Wizard ist wirklich ' +
        'gemeint: dann runAxe(page, options, { allowOnboarding: true }) aufrufen.',
    );
  }

  const appRoot = page.locator('#app > *').first();
  await expect(appRoot).toBeVisible();

  // Zwei Frames geben Vue Gelegenheit, die Enter-Klassen anzulegen. Danach
  // warten wir bedingungsbasiert auf das tatsächliche Transition-Ende.
  await appRoot.evaluate(
    () => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))),
  );
  await expect(page.locator('.fade-enter-active')).toHaveCount(0);
  await expect(appRoot).not.toHaveClass(/fade-enter-active/);
  await expect(appRoot).toHaveCSS('opacity', '1');

  return new AxeBuilder({ page }).options(options).analyze();
}

/**
 * Prüft, dass keine serious oder critical violations vorliegen.
 */
export function assertNoCriticalViolations(results: AxeResults): void {
  const violations = results.violations.filter((v: Result) => v.impact === 'serious' || v.impact === 'critical');

  if (violations.length > 0) {
    const summary = violations
      .map((v: Result) => {
        const targets = v.nodes.map((node) => JSON.stringify(node.target)).join(', ');
        return `[${v.impact}] ${v.id}: ${v.description} (${v.nodes.length} nodes: ${targets})`;
      })
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
  // `:visible` MUSS an jedem Einzelselektor hängen, nicht an der Gesamtliste:
  // `locator(liste).locator(':visible')` würde sichtbare *Nachfahren* der
  // fokussierbaren Elemente suchen statt diese selbst zu filtern.
  const focusableSelectors = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ]
    .map((selector) => `${selector}:visible`)
    .join(', ');

  // Sichtbarkeit ist zwingend: count() zählt sonst auch Treffer, die im DOM
  // liegen, aber nicht sichtbar und damit nicht tabbbar sind (z. B. die Links
  // eines eingeklappten Navigations-Untermenüs). Überzählt man, tabbt die
  // Schleife über den letzten echten Tab-Stop hinaus und der Fokus verlässt
  // das Dokument. Gefunden auf /runs/:id (Issue #838); der Fehler lag latent
  // bereits vorher vor, blieb aber unentdeckt, weil alle zuvor gegateten
  // Routen deutlich mehr als tabCount sichtbare Tab-Stops haben.
  const focusableCount = await page.locator(focusableSelectors).count();
  expect(focusableCount).toBeGreaterThan(0);

  // Gemessen wird, ob Tab den Fokus tatsächlich auf Elemente der Seite legt.
  // Bewusst NICHT gemessen wird, wo der Fokus nach dem letzten Tab-Stop
  // landet: dass er dann in den Browser-Chrome wandert, ist normales
  // Browserverhalten und kein Mangel der Seite. Die frühere Fassung prüfte
  // genau das und war deshalb auf jeder Seite mit wenigen Tab-Stops
  // falsch-negativ.
  let focusStepCount = 0;
  for (let i = 0; i < Math.min(tabCount, focusableCount); i++) {
    await page.keyboard.press('Tab');
    const focusedInDocument = await page.evaluate(
      () => document.activeElement !== null && document.activeElement !== document.body,
    );
    if (focusedInDocument) focusStepCount += 1;
  }

  // Der erste Tab muss den Fokus in die Seite bringen; sonst ist sie per
  // Tastatur nicht erreichbar.
  const hasFocus = focusStepCount > 0;

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

  // Issue #921 — Implizite Tab-Stops (scrollbare Container ohne tabindex)
  // erscheinen erst nach genügend Tab-Presses im Tab-Zyklus. Auf einer Route
  // ohne echte interaktive Elemente (z. B. /v4/simulation/:id/feed mit
  // leeren Feed-Spalten) wandert der Fokus nach dem ersten Tab in den
  // Browser-Chrome und activeElement wird wieder body. Wir probieren daher
  // bis zu MAX_TAB_ATTEMPTS Tabs, bevor wir aufgeben.
  const MAX_TAB_ATTEMPTS = 20;
  let target: ElementHandle<HTMLElement> | null = null;
  for (let attempt = 0; attempt < MAX_TAB_ATTEMPTS; attempt += 1) {
    await page.keyboard.press('Tab');
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
    const handle = await page.evaluateHandle(() => document.activeElement as HTMLElement | null);
    const isElement = await handle.evaluate((node) => node !== null && node !== document.body);
    if (isElement) {
      target = handle as ElementHandle<HTMLElement>;
      break;
    }
    await handle.dispose();
  }

  try {
    expect(
      target,
      'checkFocusVisible: nach bis zu MAX_TAB_ATTEMPTS Tab-Presses landet der Fokus nicht in einem echten Element der Seite (vermutlich Route ohne sichtbare Tab-Stops)',
    ).not.toBeNull();
    if (!target) return;

    const afterStyle = await captureFocusStyle(target);

    await target.evaluate((node) => node.blur());
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));

    const beforeStyle = await captureFocusStyle(target);

    expect(diffFocusStyle(beforeStyle, afterStyle)).toBe(true);
  } finally {
    await target?.dispose();
  }
}

/**
 * Prüft, dass prefers-reduced-motion: reduce nicht-essentielle Animationen unterdrückt.
 */
export async function checkReducedMotion(page: Page): Promise<void> {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  try {
    const reducedMotion = await page.evaluate(() => {
      // Slice 7.3.1: Klassen-/Inline-Style-Substring-Matching ("animate"/
      // "transition") übersieht echte CSS-Transitionen aus Stylesheet-Regeln
      // (z.B. `.app-shell__sidebar { transition: transform 200ms ease; }`).
      // getComputedStyle() ist die einzig verlässliche Quelle — sie
      // reflektiert die tatsächlich angewendete Transition/Animation
      // unabhängig davon, wie/wo sie deklariert wurde.
      const allElements = document.querySelectorAll('*');

      return {
        isReduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        durations: Array.from(allElements, (element) => {
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
 * Wartet, bis Stylesheets und Webfonts angewendet sind.
 *
 * `goto(..., { waitUntil: 'domcontentloaded' })` kehrt zurück, bevor CSS und
 * Fonts wirksam sind. Läuft axe-core in diesem Fenster, misst es die
 * Fallback-Farben des ungestylten Dokuments und meldet massenhaft
 * color-contrast-Verstöße — inklusive `:root`. Das ist ein reines
 * Timing-Artefakt und trat bisher nur deshalb nicht auf, weil die CI-Läufe
 * langsam genug waren; auf einem schnellen Runner kippen dadurch auch
 * Routen, an denen niemand etwas geändert hat (beobachtet auf /dashboard
 * und /runs, Issue #838).
 *
 * Zusätzlich stabilisiert das den Zustand nach einem Viewport-Wechsel: die
 * Tastatur- und Fokusprüfungen laufen sonst gegen ein Layout, das noch neu
 * berechnet wird.
 */
async function waitForStyledPaint(page: Page): Promise<void> {
  await page.waitForLoadState('load');
  await page.evaluate(async () => {
    if (document.fonts?.ready) await document.fonts.ready;
    // Zwei Frames abwarten: der erste committet das Layout, der zweite den
    // darauf basierenden Paint.
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => requestAnimationFrame(() => resolve())),
    );
  });
}

/**
 * Kombinierte Accessibility-Prüfung für eine Route.
 */
export async function checkAccessibilityGate(page: Page, route: string, options: AxeCheckOptions = {}): Promise<void> {
  await page.goto(route, { waitUntil: 'domcontentloaded' });
  await waitForStyledPaint(page);

  // Issue #988: erst prüfen, WO wir gelandet sind. Der Onboarding-Guard
  // (src/router/onboardingGuard.ts) leitet jede nicht-exempte Route auf
  // /onboarding um, solange onboarding_required gilt — der Default eines
  // frischen E2E-Stacks. Ohne diese Prüfung laufen alle folgenden Checks
  // gegen den Wizard statt gegen die Zielseite und melden zuverlässig grün.
  // Genau so blieben in run-budget.spec.ts monatelang sechs echte
  // color-contrast-Verstöße unentdeckt.
  assertRouteNotHijacked(route, page.url());

  // axe-core
  const axeResults = await runAxe(page, options, {
    allowOnboarding: pathOf(route).startsWith('/onboarding'),
  });
  assertNoCriticalViolations(axeResults);

  // 320px
  await check320pxNoHorizontalScroll(page);

  // Reset viewport für weitere Checks. Das Layout muss danach neu berechnet
  // sein, bevor Sichtbarkeit und Tab-Reihenfolge geprüft werden — sonst
  // zählt checkKeyboardNavigation gegen den 320px-Zustand, in dem Teile der
  // Navigation ausgeblendet sind.
  await page.setViewportSize({ width: 1280, height: 720 });
  await waitForStyledPaint(page);

  // Keyboard
  await checkKeyboardNavigation(page);

  // Issue #1088: Reihenfolge, nicht nur Erreichbarkeit.
  await checkTabOrderFollowsReadingOrder(page);

  // Focus visible
  await checkFocusVisible(page);

  // Reduced motion
  await checkReducedMotion(page);
}

// ---------------------------------------------------------------------------
// Issue #988 — Route-Entführung durch den Onboarding-Guard erkennen
// ---------------------------------------------------------------------------

/** Pfad aus einer absoluten oder relativen URL, ohne Query und Hash. */
export function pathOf(url: string): string {
  const withoutOrigin = url.replace(/^[a-z]+:\/\/[^/]+/i, '');
  return withoutOrigin.split(/[?#]/)[0] || '/';
}

/**
 * Wurde die angeforderte Route auf den Onboarding-Wizard umgeleitet?
 *
 * Reine Funktion, damit der Fall ohne laufenden Stack prüfbar ist. Wer den
 * Wizard *absichtlich* gatet — `checkAccessibilityGate(page, '/onboarding')` —
 * bekommt kein false positive.
 */
export function isOnboardingHijack(intendedRoute: string, actualUrl: string): boolean {
  const intended = pathOf(intendedRoute);
  const actual = pathOf(actualUrl);
  if (intended.startsWith('/onboarding')) return false;
  return actual === '/onboarding' || actual.startsWith('/onboarding/');
}

export function assertRouteNotHijacked(intendedRoute: string, actualUrl: string): void {
  if (!isOnboardingHijack(intendedRoute, actualUrl)) return;
  throw new Error(
    `Accessibility-Gate laeuft gegen die falsche Seite: angefordert war ${intendedRoute}, ` +
      `gelandet auf ${pathOf(actualUrl)}. Der Onboarding-Guard hat umgeleitet. ` +
      'Die Spec muss vor dem page.goto ensureOnboardingDismissed(page) aufrufen ' +
      '(oder POST /api/onboarding/dismiss senden) — sonst prueft das Gate den ' +
      'Wizard und meldet gruen, ohne die Zielseite je gesehen zu haben.',
  );
}

// ---------------------------------------------------------------------------
// Issue #1088 — Tab-Reihenfolge gegen die visuelle Lesereihenfolge
// ---------------------------------------------------------------------------

/** Ein per Tab erreichter Fokus-Stopp mit Position und umgebendem Landmark. */
export interface TabStop {
  /** Nullbasierte Position in der Tab-Kette. */
  order: number;
  /** Landmark-Kennung (`main`, `nav[1]`, …) oder `document`. */
  landmark: string;
  /** Menschenlesbare Kennzeichnung für die Fehlermeldung. */
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Zwei Elemente gelten als in derselben Zeile, wenn sich ihre vertikalen
 * Bereiche um mehr als die Hälfte der kleineren Höhe überlappen.
 *
 * Ohne diese Toleranz wäre jede Button-Leiste ein Verstoß: Elemente
 * nebeneinander haben fast nie exakt dasselbe `y`.
 */
export function isSameRow(a: TabStop, b: TabStop): boolean {
  const overlap = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  const reference = Math.min(a.height, b.height);
  if (reference <= 0) return Math.abs(a.y - b.y) <= ROW_TOLERANCE_PX;
  return overlap > reference / 2;
}

/** Zulässiger Rückwärtsversatz in Pixeln, um Rundung und Rahmen abzufangen. */
const ROW_TOLERANCE_PX = 4;

/**
 * Verstöße gegen die visuelle Lesereihenfolge — reine Funktion.
 *
 * Geprüft wird je Landmark getrennt: innerhalb einer Zeile muss die
 * Tab-Reihenfolge nach rechts laufen, über Zeilen hinweg nach unten. Der Sprung
 * zwischen zwei Landmarks wird bewusst nicht bewertet — eine Sprungmarke
 * ("Zum Inhalt springen") führt korrekterweise nach unten und vorne zugleich.
 *
 * Diese Regel ist absichtlich nicht die DOM-Reihenfolge: der Fehler, um den es
 * geht, ist "sieht oben aus, kommt beim Tabben zuletzt" — erzeugt durch CSS
 * (`order`, `grid-area`) oder positives `tabindex`. Die DOM-Reihenfolge bleibt
 * dabei unverändert und würde den Fehler nie sehen.
 */
export function findReadingOrderViolations(stops: readonly TabStop[]): string[] {
  const violations: string[] = [];
  for (let i = 1; i < stops.length; i++) {
    const previous = stops[i - 1];
    const current = stops[i];
    if (previous.landmark !== current.landmark) continue;

    if (isSameRow(previous, current)) {
      if (current.x < previous.x - ROW_TOLERANCE_PX) {
        violations.push(
          `${current.landmark}: Tab-Stopp ${current.order} (${current.label}) liegt links von ` +
            `Stopp ${previous.order} (${previous.label}) in derselben Zeile ` +
            `(x=${Math.round(current.x)} < ${Math.round(previous.x)}).`,
        );
      }
      continue;
    }

    if (current.y < previous.y - ROW_TOLERANCE_PX) {
      violations.push(
        `${current.landmark}: Tab-Stopp ${current.order} (${current.label}) liegt oberhalb von ` +
          `Stopp ${previous.order} (${previous.label}) ` +
          `(y=${Math.round(current.y)} < ${Math.round(previous.y)}).`,
      );
    }
  }
  return violations;
}

/** Obergrenze für die Tab-Kette — schützt vor Fokusfallen mit Endlosschleife. */
const MAX_TAB_STOPS = 60;

/**
 * Sammelt die tatsächliche Tab-Kette und prüft sie gegen die Lesereihenfolge.
 *
 * Bewusst getabbt statt aus dem DOM abgeleitet: nur so wird ein positives
 * `tabindex` sichtbar. Geprüft wird ausschließlich die Reihenfolge der
 * Elemente, die im Moment der Prüfung fokussierbar sind — ob ein bestimmtes
 * Element vorhanden ist, gehört in einen Funktionstest. Vermischt man beides,
 * wird der Check bei jeder bedingten Anzeige rot und endet bei pauschalen
 * Retries.
 */
export async function checkTabOrderFollowsReadingOrder(page: Page): Promise<void> {
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
  });

  const stops: TabStop[] = [];
  const seen = new Set<string>();

  for (let index = 0; index < MAX_TAB_STOPS; index++) {
    await page.keyboard.press('Tab');
    const stop = await page.evaluate(() => {
      const active = document.activeElement;
      if (!(active instanceof HTMLElement) || active === document.body) return null;

      const landmarkSelector = 'main, nav, aside, header, footer, [role="main"], [role="navigation"], [role="complementary"], [role="banner"], [role="contentinfo"]';
      const container = active.closest<HTMLElement>(landmarkSelector);
      let landmark = 'document';
      if (container) {
        const role = container.getAttribute('role');
        const tag = container.tagName.toLowerCase();
        const base = role ?? tag;
        const siblings = Array.from(document.querySelectorAll<HTMLElement>(landmarkSelector)).filter(
          (node) => (node.getAttribute('role') ?? node.tagName.toLowerCase()) === base,
        );
        landmark = siblings.length > 1 ? `${base}[${siblings.indexOf(container)}]` : base;
      }

      const rect = active.getBoundingClientRect();
      const text = (active.getAttribute('aria-label') || active.textContent || '').trim().slice(0, 40);
      const id = active.id ? `#${active.id}` : '';
      return {
        key: `${active.tagName}${id}:${rect.x},${rect.y}`,
        landmark,
        label: `${active.tagName.toLowerCase()}${id}${text ? ` "${text}"` : ''}`,
        x: rect.x + window.scrollX,
        y: rect.y + window.scrollY,
        width: rect.width,
        height: rect.height,
      };
    });

    // Fokus hat das Dokument verlassen (Browser-Chrome) oder die Kette hat sich
    // geschlossen — beides beendet die Sammlung, keins ist ein Mangel.
    if (!stop) break;
    if (seen.has(stop.key)) break;
    seen.add(stop.key);
    stops.push({ order: index, landmark: stop.landmark, label: stop.label, x: stop.x, y: stop.y, width: stop.width, height: stop.height });
  }

  const violations = findReadingOrderViolations(stops);
  if (violations.length > 0) {
    throw new Error(
      `Tab-Reihenfolge folgt nicht der visuellen Lesereihenfolge (${stops.length} Stopps gesammelt):\n` +
        violations.join('\n'),
    );
  }
}
