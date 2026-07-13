import type { Page } from '@playwright/test';
import { describe, expect, it } from 'vitest';

import {
  checkFocusVisible,
  diffFocusStyle,
  parseMaxDuration,
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
      evaluate: async (fn: (node: Element, arg?: unknown) => unknown, arg?: unknown) =>
        fn(element, arg),
      dispose: async () => undefined,
    }));
    const page = {
      evaluate: async (fn: (arg?: unknown) => unknown, arg?: unknown) => fn(arg),
      keyboard: { press: async () => target.focus() },
      locator: () => ({ elementHandles: async () => handles }),
    } as unknown as Page;

    await expect(checkFocusVisible(page)).resolves.toBeUndefined();
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
