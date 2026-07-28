/**
 * Bootstrap-Tests für main.ts.
 *
 * main.ts führt Side-Effects beim Import aus (initFrontendTracing, DOM-Mutations,
 * cleanupStaleRuntimeLlmStorage, app.mount). Alle externen Abhängigkeiten werden
 * gemockt bevor der Dynamic-Import getriggert wird.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'

// CSS-Imports werden von Vite/jsdom als noop behandelt — kein Mock nötig.

vi.mock('../observability/tracing', () => ({
  initFrontendTracing: vi.fn(),
}))

vi.mock('../composables/useDensity', () => ({
  useDensity: vi.fn(() => ({ applyOnMount: vi.fn() })),
}))

vi.mock('../router', () => ({
  default: { install: vi.fn() },
}))

vi.mock('../i18n', () => ({
  default: {
    install: vi.fn(),
    global: {},
  },
}))

vi.mock('../i18n/translate', () => ({
  registerI18n: vi.fn(),
}))

vi.mock('../App.vue', () => ({
  default: { name: 'AppStub', render: () => null },
}))

// pinia mock — createPinia muss ein install()-fähiges Objekt zurückgeben
vi.mock('pinia', () => ({
  createPinia: vi.fn(() => ({ install: vi.fn() })),
}))

// vue mock — nur createApp brauchen wir
vi.mock('vue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue')>()
  return {
    ...actual,
    createApp: vi.fn(() => ({
      use: vi.fn().mockReturnThis(),
      mount: vi.fn(),
    })),
  }
})

describe('main.ts Bootstrap', () => {
  beforeAll(async () => {
    // Stelle sicher, dass #app im DOM vorhanden ist
    if (!document.getElementById('app')) {
      const div = document.createElement('div')
      div.id = 'app'
      document.body.appendChild(div)
    }

    // Dynamic import triggert die Side-Effects deterministisch
    await import('../main')
  })

  it('setzt data-theme="light" auf <html>', () => {
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('setzt data-ui-version auf <html> (nicht null)', () => {
    expect(document.documentElement.getAttribute('data-ui-version')).not.toBeNull()
  })

  it('setzt window.__AGORA_UI_VERSION__', () => {
    expect((window as any).__AGORA_UI_VERSION__).toBeDefined()
    expect(typeof (window as any).__AGORA_UI_VERSION__).toBe('string')
  })

  it('initFrontendTracing wurde 1× aufgerufen', async () => {
    const { initFrontendTracing } = await import('../observability/tracing')
    expect(initFrontendTracing).toHaveBeenCalledTimes(1)
  })
})
