import { describe, it, expect, vi, afterEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useIsMobile } from '../useIsMobile'
import { MOBILE_MEDIA_QUERY } from '../../constants/breakpoints'

/** Minimal-Komponente, die den Wert nur sichtbar macht. */
const Probe = defineComponent({
  setup() {
    const { isMobile } = useIsMobile()
    return () => h('div', isMobile.value ? 'schmal' : 'breit')
  },
})

function stubMatchMedia(matches: boolean) {
  const listeners: Array<(e: MediaQueryListEvent) => void> = []
  const mql = {
    matches,
    media: MOBILE_MEDIA_QUERY,
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.push(cb),
    removeEventListener: vi.fn(),
  }
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: vi.fn().mockReturnValue(mql),
  })
  return { mql, listeners }
}

afterEach(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, configurable: true, value: undefined })
})

describe('useIsMobile', () => {
  it('meldet "schmal", wenn die Media-Query greift', () => {
    stubMatchMedia(true)
    expect(mount(Probe).text()).toBe('schmal')
  })

  it('meldet "breit", wenn sie nicht greift', () => {
    stubMatchMedia(false)
    expect(mount(Probe).text()).toBe('breit')
  })

  it('faellt ohne matchMedia auf die Desktop-Ansicht zurueck, statt zu werfen', () => {
    // jsdom kennt matchMedia nicht. Ohne den Guard wuerde jeder
    // Komponententest der Huelle beim Mounten scheitern.
    expect(() => mount(Probe)).not.toThrow()
    expect(mount(Probe).text()).toBe('breit')
  })

  it('reagiert auf einen Wechsel der Fensterbreite', async () => {
    const { listeners } = stubMatchMedia(false)
    const w = mount(Probe)
    expect(w.text()).toBe('breit')

    listeners.forEach((cb) => cb({ matches: true } as MediaQueryListEvent))
    await w.vm.$nextTick()
    expect(w.text()).toBe('schmal')
  })

  it('haengt den Listener beim Zerstoeren wieder ab', () => {
    const { mql } = stubMatchMedia(true)
    mount(Probe).unmount()
    expect(mql.removeEventListener).toHaveBeenCalled()
  })

  it('nutzt die SSoT-Media-Query, keinen eigenen Breakpoint', () => {
    stubMatchMedia(false)
    mount(Probe)
    expect(window.matchMedia).toHaveBeenCalledWith(MOBILE_MEDIA_QUERY)
  })
})
