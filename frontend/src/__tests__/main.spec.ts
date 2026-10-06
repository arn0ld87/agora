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

const useThemeMock = vi.hoisted(() => vi.fn())
vi.mock('../composables/useTheme', () => ({
  useTheme: useThemeMock,
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

// auth store mock — main.ts startet ensureInit() vor dem Router (#1617)
const authMock = vi.hoisted(() => ({ ensureInit: vi.fn(async () => {}) }))
vi.mock('../store/auth', () => ({ useAuthStore: () => authMock }))

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
  // vitest 5 setzt `clearMocks` jetzt standardmässig auf `true` — jeder
  // vi.fn() wird vor dem ersten `it()` geleert, auch wenn der eigentliche
  // Aufruf (hier: der Side-Effect aus `main.ts`) bereits in `beforeAll`
  // passiert ist. Die Aufrufzahl muss deshalb HIER, vor dem Clearing,
  // festgehalten werden statt sie spaeter aus dem (dann geleerten) Mock
  // zu lesen.
  let initFrontendTracingCallCount = -1
  let ensureInitCallCount = -1
  let useThemeCallCount = -1

  beforeAll(async () => {
    // Stelle sicher, dass #app im DOM vorhanden ist
    if (!document.getElementById('app')) {
      const div = document.createElement('div')
      div.id = 'app'
      document.body.appendChild(div)
    }

    // Dynamic import triggert die Side-Effects deterministisch
    await import('../main')

    const { initFrontendTracing } = await import('../observability/tracing')
    initFrontendTracingCallCount = (initFrontendTracing as ReturnType<typeof vi.fn>).mock.calls.length
    ensureInitCallCount = authMock.ensureInit.mock.calls.length
    useThemeCallCount = useThemeMock.mock.calls.length
  })

  it('startet den Auth-Store genau einmal (#1617)', () => {
    expect(ensureInitCallCount).toBe(1)
  })

  // #1795: Hell/Dunkel folgt dem System bzw. der gespeicherten Wahl. Der Wert
  // wird zweimal gesetzt — inline in index.html vor dem ersten Paint (kein
  // Aufblitzen) und hier ueber useTheme(), bevor die App mountet. Die Logik
  // selbst deckt useTheme.spec.ts ab.
  it('initialisiert das Theme genau einmal über useTheme() (#1795)', () => {
    expect(useThemeCallCount).toBe(1)
  })

  it('setzt data-ui-version auf <html> (nicht null)', () => {
    expect(document.documentElement.getAttribute('data-ui-version')).not.toBeNull()
  })

  it('setzt window.__AGORA_UI_VERSION__', () => {
    expect((window as any).__AGORA_UI_VERSION__).toBeDefined()
    expect(typeof (window as any).__AGORA_UI_VERSION__).toBe('string')
  })

  it('initFrontendTracing wurde 1× aufgerufen', () => {
    expect(initFrontendTracingCallCount).toBe(1)
  })
})
