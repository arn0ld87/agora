import { describe, expect, it } from 'vitest';

import { findTabOrderViolations, type TabStopRect } from './e2e/helpers/tabOrder';

/**
 * Issue #1088 — konservativer Tab-Reihenfolge-Check.
 *
 * Fixtures sind reine Geometrie-Daten (keine Playwright-Abhängigkeit), damit
 * die Verletzungsdefinition ohne laufenden Stack nachweisbar ist. Siehe
 * tests/e2e/helpers/tabOrder.ts für die vollständige Definition.
 */

function stop(partial: Partial<TabStopRect> & Pick<TabStopRect, 'top' | 'bottom' | 'left' | 'right'>): TabStopRect {
  const width = partial.width ?? partial.right - partial.left;
  const height = partial.height ?? partial.bottom - partial.top;
  return {
    landmark: partial.landmark ?? 'main#0',
    label: partial.label ?? 'stop',
    width,
    height,
    ...partial,
  };
}

describe('findTabOrderViolations', () => {
  it('erkennt ein absichtlich kaputtes Reorder-Layout in einer Spalte (column-reverse-Effekt)', () => {
    // Eine Spalte (left 0-100), drei Stops, DOM-/Tab-Reihenfolge steigt,
    // aber die visuelle Position fällt — klassischer flex `column-reverse`-
    // oder CSS-`order`-Fehler.
    const stops: TabStopRect[] = [
      stop({ left: 0, right: 100, top: 200, bottom: 230, label: 'Stop A (unten)' }),
      stop({ left: 0, right: 100, top: 100, bottom: 130, label: 'Stop B (mitte)' }),
      stop({ left: 0, right: 100, top: 0, bottom: 30, label: 'Stop C (oben)' }),
    ];

    const violations = findTabOrderViolations(stops);

    expect(violations).toHaveLength(2);
    expect(violations[0]).toMatchObject({ prevIndex: 0, nextIndex: 1 });
    expect(violations[1]).toMatchObject({ prevIndex: 1, nextIndex: 2 });
  });

  it('lässt ein zweispaltiges Layout grün, wenn Tab von Ende Spalte 1 zu Anfang Spalte 2 springt', () => {
    // Spalte 1: links 0-100, Spalte 2: links 150-250 — keine horizontale
    // Überlappung, also unterschiedliche Spalten trotz gleichen Landmarks.
    const stops: TabStopRect[] = [
      stop({ left: 0, right: 100, top: 0, bottom: 30, label: 'Spalte 1, Stop 1' }),
      stop({ left: 0, right: 100, top: 50, bottom: 80, label: 'Spalte 1, Stop 2' }),
      stop({ left: 150, right: 250, top: 0, bottom: 30, label: 'Spalte 2, Stop 1' }),
      stop({ left: 150, right: 250, top: 50, bottom: 80, label: 'Spalte 2, Stop 2' }),
    ];

    expect(findTabOrderViolations(stops)).toEqual([]);
  });

  it('lässt unterschiedlich hohe Controls in derselben Zeile grün', () => {
    // Beide Controls beginnen etwa auf gleicher Höhe, überlappen sich zu
    // >=50% horizontal (gleiche Spalte per Definition), aber der zweite
    // Stop liegt nicht oberhalb des ersten — nur höher/niedriger.
    const stops: TabStopRect[] = [
      stop({ left: 0, right: 200, top: 0, bottom: 40, label: 'Kurzes Control' }),
      stop({ left: 150, right: 250, top: 10, bottom: 100, label: 'Hohes Control' }),
    ];

    expect(findTabOrderViolations(stops)).toEqual([]);
  });

  it('vergleicht Stops in unterschiedlichen Landmarks nicht, selbst bei geometrischem Aufwärtssprung', () => {
    const stops: TabStopRect[] = [
      stop({ left: 0, right: 100, top: 200, bottom: 230, landmark: 'nav#0', label: 'Nav-Link' }),
      stop({ left: 0, right: 100, top: 0, bottom: 30, landmark: 'main#0', label: 'Main-Button' }),
    ];

    expect(findTabOrderViolations(stops)).toEqual([]);
  });

  it('behandelt die Toleranzgrenze von 8px korrekt', () => {
    // next.bottom === prev.top - 8 → genau an der Grenze, zählt als Verstoß.
    const atTolerance: TabStopRect[] = [
      stop({ left: 0, right: 100, top: 100, bottom: 130, label: 'Stop A' }),
      stop({ left: 0, right: 100, top: 0, bottom: 92, label: 'Stop B (bottom=100-8)' }),
    ];
    expect(findTabOrderViolations(atTolerance)).toHaveLength(1);

    // next.bottom === prev.top - 7 → knapp innerhalb der Toleranz, kein Verstoß.
    const withinTolerance: TabStopRect[] = [
      stop({ left: 0, right: 100, top: 100, bottom: 130, label: 'Stop A' }),
      stop({ left: 0, right: 100, top: 0, bottom: 93, label: 'Stop B (bottom=100-7)' }),
    ];
    expect(findTabOrderViolations(withinTolerance)).toEqual([]);
  });

  it('behandelt die Spalten-Überlappungsgrenze von 50% korrekt', () => {
    // Schmaleres Element hat Breite 100 (left 150-250). Überlappung mit
    // erstem Element (left 0-200) ist 0-200 ∩ 150-250 = 150-200 = 50px =
    // genau 50% von 100 → gilt als selbe Spalte → Verstoß, da next oberhalb.
    const atOverlapBoundary: TabStopRect[] = [
      stop({ left: 0, right: 200, top: 100, bottom: 130, label: 'Breiter Stop' }),
      stop({ left: 150, right: 250, top: 0, bottom: 30, label: 'Schmaler Stop, 50% Overlap' }),
    ];
    expect(findTabOrderViolations(atOverlapBoundary)).toHaveLength(1);

    // Überlappung knapp unter 50% (49px von 100) → unterschiedliche Spalte → grün.
    const belowOverlapBoundary: TabStopRect[] = [
      stop({ left: 0, right: 199, top: 100, bottom: 130, label: 'Breiter Stop' }),
      stop({ left: 150, right: 250, top: 0, bottom: 30, label: 'Schmaler Stop, 49% Overlap' }),
    ];
    expect(findTabOrderViolations(belowOverlapBoundary)).toEqual([]);
  });
});
