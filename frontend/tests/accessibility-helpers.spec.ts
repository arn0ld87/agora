import type { Page } from '@playwright/test';
import { afterEach, describe, expect, it, vi } from 'vitest';

// @axe-core/playwright ist ein E2E-only-Dep (nur in `runAxe` + Type-Positionen
// des Helpers genutzt, nicht in den hier getesteten Pure-Functions). Unter
// paralleler Full-Suite-Last rast Vites Lazy-Resolver beim Auflösen dieses
// CJS-Pakets gelegentlich und der File flakt mit "Failed to resolve import
// @axe-core/playwright". Stub auf einen Noop-Default — die getesteten
// Funktionen (diffFocusStyle/parseMaxDuration/checkFocusVisible/
// checkReducedMotion) rufen `runAxe` nicht auf, `@playwright/test`'s `expect`
// bleibt echt (in checkFocusVisible genutzt).
vi.mock('@axe-core/playwright', () => ({
  default: class AxeBuilder {
    constructor() {}
    options() {
      return this;
    }
    analyze() {
      return Promise.resolve({});
    }
  },
}));

import {
  assertRouteNotHijacked,
  checkFocusVisible,
  checkReducedMotion,
  diffFocusStyle,
  isOnboardingHijack,
  parseMaxDuration,
  pathOf,
  type FocusStyleSnapshot,
} from './e2e/helpers/accessibility';

const DEFAULT_CONTROL_STYLE: FocusStyleSnapshot = {
  outlineStyle: 'none',
  outlineWidth: '0px',
  outlineColor: 'rgb(0, 0, 0)',
  outlineOffset: '0px',
  boxShadow: 'none',
  borderTopStyle: 'solid',
  borderTopWidth: '1px',
  borderTopColor: 'rgb(118, 118, 118)',
  borderRightStyle: 'solid',
  borderRightWidth: '1px',
  borderRightColor: 'rgb(118, 118, 118)',
  borderBottomStyle: 'solid',
  borderBottomWidth: '1px',
  borderBottomColor: 'rgb(118, 118, 118)',
  borderLeftStyle: 'solid',
  borderLeftWidth: '1px',
  borderLeftColor: 'rgb(118, 118, 118)',
};

describe('diffFocusStyle', () => {
  it('rejects an unchanged native control border as focus indicator', () => {
    expect(diffFocusStyle(DEFAULT_CONTROL_STYLE, DEFAULT_CONTROL_STYLE)).toBe(false);
  });

  it('detects a visible outline or box shadow added on focus', () => {
    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        outlineStyle: 'solid',
        outlineWidth: '2px',
      }),
    ).toBe(true);

    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        boxShadow: 'rgb(0, 95, 204) 0px 0px 0px 3px',
      }),
    ).toBe(true);
  });

  it('ignores a computed box shadow whose pixel lengths are all zero', () => {
    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        boxShadow: 'rgba(0, 0, 0, 0) 0px 0px 0px 0px',
      }),
    ).toBe(false);
  });

  it('requires opacity and non-zero geometry in the same shadow layer', () => {
    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        boxShadow: 'rgba(0, 0, 0, 0) 0px 0px 0px 3px',
      }),
    ).toBe(false);

    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        boxShadow: 'rgba(0, 0, 0, 0) 0px 0px 0px 3px, rgb(0, 0, 0) 0px 0px 0px 0px',
      }),
    ).toBe(false);

    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        boxShadow: 'rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgb(0, 0, 0) 0px 0px 0px 3px',
      }),
    ).toBe(true);
  });

  it('detects a visible border color or width change', () => {
    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        borderTopColor: 'rgb(0, 95, 204)',
      }),
    ).toBe(true);

    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        borderTopWidth: '2px',
      }),
    ).toBe(true);
  });

  it('ignores border changes while the focused border remains invisible', () => {
    const invisibleBorder = {
      ...DEFAULT_CONTROL_STYLE,
      borderTopStyle: 'none',
      borderRightStyle: 'none',
      borderBottomStyle: 'none',
      borderLeftStyle: 'none',
    };

    expect(
      diffFocusStyle(invisibleBorder, {
        ...invisibleBorder,
        borderTopWidth: '2px',
        borderTopColor: 'rgb(0, 95, 204)',
      }),
    ).toBe(false);
  });

  it('requires the changed border side itself to remain visible', () => {
    expect(
      diffFocusStyle(DEFAULT_CONTROL_STYLE, {
        ...DEFAULT_CONTROL_STYLE,
        borderTopStyle: 'none',
        borderTopWidth: '2px',
        borderTopColor: 'rgb(0, 95, 204)',
      }),
    ).toBe(false);
  });
});

describe('checkFocusVisible', () => {
  it('keeps the before snapshot bound to the focused element when focus mutates the DOM', async () => {
    document.body.innerHTML = '<button>first</button><button>target</button>';
    const [first, target] = Array.from(document.querySelectorAll('button'));
    first.style.border = '1px solid rgb(118, 118, 118)';
    target.style.border = '1px solid rgb(118, 118, 118)';
    target.addEventListener('focus', () => {
      target.style.outlineStyle = 'solid';
      target.style.outlineWidth = '2px';
      target.style.outlineColor = 'rgb(0, 95, 204)';
      target.insertAdjacentHTML('beforebegin', '<button>inserted on focus</button>');
    });

    window.requestAnimationFrame = (callback: FrameRequestCallback): number => {
      callback(0);
      return 1;
    };

    const handles = [first, target].map((element) => ({
      evaluate: async (fn: (node: Element, arg?: unknown) => unknown, arg?: unknown) => {
        // the actual page.evaluate runs `window.getComputedStyle(node)` if arg is FOCUS_STYLE_PROPERTIES
        // so we need to run it in the context of the document.
        if (fn.toString().includes('node.blur')) {
          (element as HTMLElement).blur();
          element.style.outlineStyle = 'none';
          element.style.outlineWidth = '0px';
          element.style.outlineColor = 'rgb(0, 0, 0)';
          return undefined;
        }
        return fn(element, arg);
      },
      dispose: async () => undefined,
    }));
    const page = {
      evaluate: async (fn: (arg?: unknown) => unknown, arg?: unknown) => {
        if (fn.toString().includes('requestAnimationFrame')) {
          return fn();
        }
        return fn(arg);
      },
      evaluateHandle: async (fn: (arg?: unknown) => unknown, arg?: unknown) => handles[1],
      keyboard: { press: async () => { target.focus(); return undefined; } },
      locator: () => ({ elementHandles: async () => handles }),
    } as unknown as Page;

    await expect(checkFocusVisible(page)).resolves.toBeUndefined();
  });
});

describe('checkReducedMotion', () => {
  afterEach(() => {
    document.body.innerHTML = '';
    vi.restoreAllMocks();
  });

  // Regressionstest Slice 7.3.1: Vor dem Fix filterte checkReducedMotion nur
  // Elemente mit "animate"/"transition" im Klassennamen oder Inline-Style
  // (`[class*="animate"], [class*="transition"], [style*="transition"]`).
  // Echte CSS-Transitionen aus Stylesheet-Regeln wie
  // `.app-shell__sidebar { transition: transform 200ms ease; }` tragen
  // weder das eine noch das andere im Markup — der alte Selector fand sie
  // nie, der Verstoß blieb unentdeckt. Dieser Test simuliert genau diesen
  // Fall über getComputedStyle() (Stellvertreter für die Stylesheet-Regel)
  // und muss fehlschlagen (throw), sonst ist die Reduced-Motion-Prüfung
  // wieder blind für nicht-inline deklarierte Transitionen.
  it('erkennt eine aktive Transition auf einem Element ohne "transition"/"animate" im Klassennamen', async () => {
    document.body.innerHTML = '<nav class="app-shell__sidebar"></nav>';
    const sidebar = document.querySelector<HTMLElement>('.app-shell__sidebar')!;

    const nativeGetComputedStyle = window.getComputedStyle.bind(window);
    vi.spyOn(window, 'getComputedStyle').mockImplementation((element: Element) => {
      if (element === sidebar) {
        return { transitionDuration: '0.2s', animationDuration: '0s' } as CSSStyleDeclaration;
      }
      return nativeGetComputedStyle(element);
    });

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: vi.fn((query: string) => ({
        matches: true,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    });

    const page = {
      emulateMedia: async () => undefined,
      evaluate: async (fn: (arg?: unknown) => unknown, arg?: unknown) => fn(arg),
    } as unknown as Page;

    await expect(checkReducedMotion(page)).rejects.toThrow();
  });
});

describe('parseMaxDuration', () => {
  it('normalizes milliseconds and returns the longest list entry in seconds', () => {
    expect(parseMaxDuration('0.05s, 250ms, 0.1s')).toBe(0.25);
    expect(parseMaxDuration(' 100MS , .15s ')).toBe(0.15);
  });

  it('ignores invalid and negative duration tokens', () => {
    expect(parseMaxDuration('invalid, 100msjunk, -2s')).toBe(0);
    expect(parseMaxDuration('invalid, 75ms')).toBe(0.075);
    expect(parseMaxDuration('')).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Issue #988 — Route-Entführung durch den Onboarding-Guard
// ---------------------------------------------------------------------------

describe('isOnboardingHijack', () => {
  it('erkennt die Umleitung einer beliebigen Zielroute auf den Wizard', () => {
    expect(isOnboardingHijack('/runs/run_42', 'http://localhost:5173/onboarding')).toBe(true);
    expect(isOnboardingHijack('/dashboard', '/onboarding?step=2')).toBe(true);
    expect(isOnboardingHijack('/settings/general', '/onboarding/welcome')).toBe(true);
  });

  it('meldet nichts, wenn die Zielroute erreicht wurde', () => {
    expect(isOnboardingHijack('/runs/run_42', 'http://localhost:5173/runs/run_42')).toBe(false);
    expect(isOnboardingHijack('/dashboard', '/dashboard#main')).toBe(false);
  });

  it('meldet nichts, wenn der Wizard absichtlich gegatet wird', () => {
    // golden-gate-accessibility.spec.ts prüft /onboarding selbst — das darf
    // kein false positive werden, sonst wird der Riegel wieder ausgebaut.
    expect(isOnboardingHijack('/onboarding', 'http://localhost:5173/onboarding')).toBe(false);
  });

  it('assertRouteNotHijacked wirft mit einem Hinweis auf den fehlenden Bypass', () => {
    expect(() => assertRouteNotHijacked('/runs/run_42', '/onboarding')).toThrowError(
      /ensureOnboardingDismissed/,
    );
    expect(() => assertRouteNotHijacked('/runs/run_42', '/runs/run_42')).not.toThrow();
  });
});


describe('pathOf', () => {
  it('entfernt Origin, Query und Hash', () => {
    expect(pathOf('http://localhost:5173/runs/run_42?tab=budget#top')).toBe('/runs/run_42');
    expect(pathOf('/dashboard')).toBe('/dashboard');
    expect(pathOf('http://localhost:5173')).toBe('/');
  });
});
