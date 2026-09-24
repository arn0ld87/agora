import type { Page } from '@playwright/test';
import { expect } from '@playwright/test';

/**
 * Issue #1088 — belastbarer Tab-Reihenfolge-Check.
 *
 * Der frühere Ansatz „visuelle Lesereihenfolge je Landmark“
 * (`findReadingOrderViolations`) wurde real in CI getestet und wegen False
 * Positives zurückgezogen (Spaltenwechsel und unterschiedlich hohe Controls
 * wurden faelschlich als Verstoss gemeldet). Diese Fassung ist bewusst
 * konservativ: sie meldet nur echte "Sprünge nach oben" innerhalb derselben
 * visuellen Spalte desselben Landmarks.
 *
 * Verletzungsdefinition:
 * - Verglichen werden nur AUFEINANDERFOLGENDE Tab-Stops im SELBEN Landmark
 *   (`main`, `nav`, `header`, `footer`, `aside`, `[role=...]`).
 * - Beide Stops muessen in derselben visuellen SPALTE liegen: horizontale
 *   Ueberlappung >= 50% der Breite des schmaleren Elements.
 * - Verletzung nur, wenn der spaetere Stop deutlich OBERHALB des frueheren
 *   liegt: `next.bottom <= prev.top - VERTICAL_TOLERANCE_PX` (Toleranz 8px).
 * - Spaltenwechsel, gleiche Zeile, unterschiedlich hohe Controls und reine
 *   Ueberlappungen ohne Aufwaerts-Sprung sind NIE eine Verletzung.
 * - Grid/Flex-`order` wird nicht gesondert behandelt: er faellt genau dann
 *   auf, wenn er innerhalb einer Spalte nach oben springt.
 */

export interface TabStopRect {
  top: number;
  bottom: number;
  left: number;
  right: number;
  width: number;
  height: number;
  /** Eindeutige Kennung des umschliessenden Landmarks (Tag/Role + Instanz-ID). */
  landmark: string;
  /** Fuer Fehlermeldungen: Selektor/Text des Elements. */
  label: string;
}

export interface TabOrderViolation {
  prevIndex: number;
  nextIndex: number;
  prev: TabStopRect;
  next: TabStopRect;
}

const VERTICAL_TOLERANCE_PX = 8;
const MIN_COLUMN_OVERLAP_RATIO = 0.5;

function horizontalOverlapRatio(a: TabStopRect, b: TabStopRect): number {
  const overlapLeft = Math.max(a.left, b.left);
  const overlapRight = Math.min(a.right, b.right);
  const overlapWidth = Math.max(0, overlapRight - overlapLeft);
  const narrowerWidth = Math.min(a.width, b.width);
  if (narrowerWidth <= 0) return 0;
  return overlapWidth / narrowerWidth;
}

/**
 * Reine Geometrie-Funktion (kein Playwright im Inneren) — siehe Modul-Doku
 * fuer die vollstaendige Verletzungsdefinition.
 */
export function findTabOrderViolations(stops: TabStopRect[]): TabOrderViolation[] {
  const violations: TabOrderViolation[] = [];

  for (let i = 0; i < stops.length - 1; i += 1) {
    const prev = stops[i];
    const next = stops[i + 1];

    if (prev.landmark !== next.landmark) continue;
    if (horizontalOverlapRatio(prev, next) < MIN_COLUMN_OVERLAP_RATIO) continue;
    if (next.bottom > prev.top - VERTICAL_TOLERANCE_PX) continue;

    violations.push({ prevIndex: i, nextIndex: i + 1, prev, next });
  }

  return violations;
}

function formatViolation(v: TabOrderViolation): string {
  return (
    `Tab-Reihenfolge springt in Landmark "${v.prev.landmark}" von Stop #${v.prevIndex} ` +
    `(${v.prev.label}) zu Stop #${v.nextIndex} (${v.next.label}) nach oben ` +
    `(prev.top=${v.prev.top}, next.bottom=${v.next.bottom}).`
  );
}

function formatViolations(violations: TabOrderViolation[]): string {
  return violations.map(formatViolation).join('\n');
}

export interface TabStopCollectOptions {
  /** Obergrenze der gesammelten Tab-Presses (Default 40). */
  maxStops?: number;
}

type TabStopProbe =
  | { kind: 'stop'; rect: Omit<TabStopRect, 'label' | 'landmark'>; landmark: string; label: string; signature: string }
  | { kind: 'excluded' }
  | { kind: 'left-page' };

async function readTabStop(page: Page): Promise<TabStopProbe> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el || el === document.body || el === document.documentElement) {
      return { kind: 'left-page' } as const;
    }

    const rect = el.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return { kind: 'excluded' } as const;
    }

    const style = window.getComputedStyle(el);
    if (style.position === 'fixed' || style.position === 'sticky') {
      return { kind: 'excluded' } as const;
    }

    if (el.closest('[role="dialog"], [aria-modal="true"], dialog[open]')) {
      return { kind: 'excluded' } as const;
    }

    const landmarkEl = el.closest('main, nav, header, footer, aside, [role]') as HTMLElement | null;
    let landmark = 'document';
    if (landmarkEl) {
      const registry = window as unknown as {
        __agoraLandmarkIds?: WeakMap<Element, number>;
        __agoraLandmarkCounter?: number;
      };
      registry.__agoraLandmarkIds ??= new WeakMap();
      registry.__agoraLandmarkCounter ??= 0;
      let id = registry.__agoraLandmarkIds.get(landmarkEl);
      if (id === undefined) {
        id = registry.__agoraLandmarkCounter;
        registry.__agoraLandmarkCounter += 1;
        registry.__agoraLandmarkIds.set(landmarkEl, id);
      }
      const kind = landmarkEl.getAttribute('role') ?? landmarkEl.tagName.toLowerCase();
      landmark = `${kind}#${id}`;
    }

    const label =
      el.getAttribute('data-testid') ||
      el.id ||
      el.getAttribute('aria-label') ||
      el.textContent?.trim().slice(0, 60) ||
      el.tagName.toLowerCase();

    const nodeRegistry = window as unknown as {
      __agoraTabStopIds?: WeakMap<Element, number>;
      __agoraTabStopCounter?: number;
    };
    nodeRegistry.__agoraTabStopIds ??= new WeakMap();
    nodeRegistry.__agoraTabStopCounter ??= 0;
    let sigId = nodeRegistry.__agoraTabStopIds.get(el);
    if (sigId === undefined) {
      sigId = nodeRegistry.__agoraTabStopCounter;
      nodeRegistry.__agoraTabStopCounter += 1;
      nodeRegistry.__agoraTabStopIds.set(el, sigId);
    }

    return {
      kind: 'stop',
      rect: {
        top: rect.top,
        bottom: rect.bottom,
        left: rect.left,
        right: rect.right,
        width: rect.width,
        height: rect.height,
      },
      landmark,
      label,
      signature: `node-${sigId}`,
    } as const;
  });
}

/**
 * Sammelt Tab-Stops via echter `Tab`-Presses, nur sichtbare Elemente mit
 * Breite/Höhe > 0. Bricht ab, wenn der Fokus die Seite verlässt oder
 * zyklisch zum ersten Stop zurückkehrt, spätestens nach `maxStops`.
 */
export async function collectTabStops(page: Page, options: TabStopCollectOptions = {}): Promise<TabStopRect[]> {
  const maxStops = options.maxStops ?? 40;
  const stops: TabStopRect[] = [];
  let firstSignature: string | null = null;

  for (let i = 0; i < maxStops; i += 1) {
    await page.keyboard.press('Tab');
    const probe = await readTabStop(page);

    if (probe.kind === 'left-page') break;
    if (probe.kind === 'excluded') continue;

    if (firstSignature === null) {
      firstSignature = probe.signature;
    } else if (probe.signature === firstSignature) {
      break;
    }

    stops.push({
      top: probe.rect.top,
      bottom: probe.rect.bottom,
      left: probe.rect.left,
      right: probe.rect.right,
      width: probe.rect.width,
      height: probe.rect.height,
      landmark: probe.landmark,
      label: probe.label,
    });
  }

  return stops;
}

/**
 * Sammelt die reale Tab-Reihenfolge und prüft sie gegen die konservative
 * Verletzungsdefinition (siehe Modul-Doku). Wirft bei Verstoß mit
 * Selektor/Text beider beteiligter Stops.
 */
export async function checkTabOrder(page: Page, options: TabStopCollectOptions = {}): Promise<void> {
  // Fokus zuruecksetzen: ein vorangegangener Check (z.B. checkKeyboardNavigation)
  // kann den Fokus bereits mehrere Tab-Stops tief bewegt haben. Ohne Reset
  // wuerde die Sammlung erst mittendrin einsetzen und die ersten Stops der
  // Seite nie miteinander vergleichen.
  await page.evaluate(() => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
  });

  const stops = await collectTabStops(page, options);
  const violations = findTabOrderViolations(stops);

  expect(violations, formatViolations(violations)).toEqual([]);
}
