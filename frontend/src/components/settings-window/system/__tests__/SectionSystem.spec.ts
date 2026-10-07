import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { createI18n } from 'vue-i18n'
import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

const getSystemStatus = vi.hoisted(() => vi.fn())
vi.mock('@/api/status', () => ({ getSystemStatus }))
vi.mock('../../../../api/status', () => ({ getSystemStatus }))

const logDrawer = vi.hoisted(() => ({ open: vi.fn(), available: { value: true } }))
vi.mock('@/composables/useLogDrawer', () => ({
  useLogDrawer: () => ({ available: ref(logDrawer.available.value), open: logDrawer.open }),
}))

import SectionSystem from '../../sections/SectionSystem.vue'

const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'en', messages: { de, en } })

function envelope(over: Record<string, unknown> = {}) {
  return {
    success: true,
    backend: { ok: true, version: '0.9.6' },
    neo4j: { reachable: true },
    ollama: { reachable: null, skipped: true, skipped_provider: 'openai' },
    disk: { uploads: { free_bytes: 5e10, used_pct: 42.4 } },
    timestamp: '2026-10-06T10:00:00Z',
    ...over,
  }
}

async function mountIt() {
  const w = mount(SectionSystem, { global: { plugins: [i18n] } })
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
  logDrawer.available.value = true
})

describe('SectionSystem', () => {
  it('zeigt Zustände, Version und Speicher; „nicht geprüft“ ist nicht „in Ordnung“', async () => {
    getSystemStatus.mockResolvedValue(envelope())
    const w = await mountIt()
    expect(w.get('[data-testid="system-state-backend"]').text()).toBe('In Ordnung')
    expect(w.get('[data-testid="system-state-neo4j"]').attributes('data-tone')).toBe('ok')
    const ollama = w.get('[data-testid="system-state-ollama"]')
    expect(ollama.text()).toBe('Nicht geprüft')
    expect(ollama.attributes('data-tone')).toBe('neutral')
    expect(w.get('[data-testid="system-version"]').text()).toBe('0.9.6')
    expect(w.get('[data-testid="system-disk"]').text()).toContain('50.0 GB frei')
    expect(w.text()).toContain('Redis und PostgreSQL')
    expect(w.text()).not.toContain('In Vorbereitung')
    w.unmount()
  })

  it('färbt nicht erreichbare Dienste als Fehler und nennt den Grund', async () => {
    getSystemStatus.mockResolvedValue(envelope({ neo4j: { reachable: false, error: { code: 'timeout' } } }))
    const w = await mountIt()
    const neo = w.get('[data-testid="system-state-neo4j"]')
    expect(neo.text()).toBe('Nicht erreichbar')
    expect(neo.attributes('data-tone')).toBe('down')
    expect(w.text()).toContain('Zeitüberschreitung')
    w.unmount()
  })

  it('zeigt bei Abruffehler Meldung und Wiederholen, Dienste bleiben „Unbekannt“', async () => {
    getSystemStatus.mockRejectedValue(new Error('offline'))
    const w = await mountIt()
    expect(w.get('[role="alert"]').text()).toContain('offline')
    expect(w.get('[data-testid="system-state-neo4j"]').text()).toBe('Unbekannt')
    expect(w.get('[data-testid="system-state-neo4j"]').attributes('data-tone')).toBe('neutral')
    getSystemStatus.mockResolvedValue(envelope())
    await w.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').exists()).toBe(false)
    expect(w.get('[data-testid="system-state-neo4j"]').text()).toBe('In Ordnung')
    w.unmount()
  })

  it('zeigt den Ladezustand', async () => {
    getSystemStatus.mockReturnValue(new Promise(() => {}))
    const w = mount(SectionSystem, { global: { plugins: [i18n] } })
    await flushPromises()
    expect(w.get('[role="status"]').text()).toContain('geprüft')
    w.unmount()
  })

  it('„Konsole öffnen“ ruft den Konsolen-Mechanismus; ohne Betreiberzugang gesperrt', async () => {
    getSystemStatus.mockResolvedValue(envelope())
    const w = await mountIt()
    const btn = w.findAll('button').find((b) => b.text() === 'Konsole öffnen')!
    await btn.trigger('click')
    expect(logDrawer.open).toHaveBeenCalledTimes(1)
    w.unmount()

    logDrawer.available.value = false
    const w2 = await mountIt()
    const btn2 = w2.findAll('button').find((b) => b.text() === 'Konsole öffnen')!
    expect(btn2.attributes('disabled')).toBeDefined()
    w2.unmount()
  })
})
