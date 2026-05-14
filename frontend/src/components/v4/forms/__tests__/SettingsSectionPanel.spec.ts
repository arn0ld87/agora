/**
 * SettingsSectionPanel — Smokes (Slice G1).
 *
 * Prueft Tab-Filterung nach `allowedSections` und Render der Felder.
 * Der settingsStore wird mit Mock-Daten initialisiert; Netzwerk-Aufrufe
 * sind ueber das `@/api/settings`-Modul gemockt.
 */
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'

import de from '@/i18n/locales/de.json'
import en from '@/i18n/locales/en.json'

vi.mock('@/api/settings', () => ({
  fetchSettings: vi.fn(),
  fetchSettingsSchema: vi.fn(),
  openSettingsStream: vi.fn().mockResolvedValue({ close: vi.fn() }),
  putSettings: vi.fn(),
  putSecrets: vi.fn(),
}))

import { fetchSettings, fetchSettingsSchema } from '@/api/settings'
import SettingsSectionPanel from '../SettingsSectionPanel.vue'

function makeI18n() {
  return createI18n({
    legacy: false,
    locale: 'de',
    fallbackLocale: 'en',
    messages: { de, en },
  })
}

function buildResponses() {
  ;(fetchSettingsSchema as ReturnType<typeof vi.fn>).mockResolvedValue({
    success: true,
    data: {
      sections: ['llm', 'logging', 'neo4j'],
      fields: [
        { key: 'LLM_MODEL_NAME', section: 'llm', type: 'string', secret: false, reload_required: false, default: 'qwen2.5:32b' },
        { key: 'LOG_LEVEL', section: 'logging', type: 'enum', secret: false, reload_required: false, default: 'INFO', enum_values: ['DEBUG', 'INFO', 'WARN'] },
        { key: 'NEO4J_PASSWORD', section: 'neo4j', type: 'string', secret: true, reload_required: true, default: null },
      ],
    },
  })
  ;(fetchSettings as ReturnType<typeof vi.fn>).mockResolvedValue({
    success: true,
    data: {
      sections: ['llm', 'logging', 'neo4j'],
      fields: {
        llm: [{
          key: 'LLM_MODEL_NAME', section: 'llm', type: 'string',
          secret: false, reload_required: false,
          value: 'qwen2.5:32b', default: 'qwen2.5:32b',
          source: 'env', is_set: true,
        }],
        logging: [{
          key: 'LOG_LEVEL', section: 'logging', type: 'enum',
          secret: false, reload_required: false,
          value: 'INFO', default: 'INFO', enum_values: ['DEBUG', 'INFO', 'WARN'],
          source: 'default', is_set: true,
        }],
        neo4j: [{
          key: 'NEO4J_PASSWORD', section: 'neo4j', type: 'string',
          secret: true, reload_required: true,
          value: null, default: null,
          source: 'env', is_set: true,
        }],
      },
    },
  })
}

async function mountPanel(allowedSections: string[]) {
  buildResponses()
  const pinia = createPinia()
  setActivePinia(pinia)
  const i18n = makeI18n()
  const wrapper = mount(SettingsSectionPanel, {
    props: { allowedSections },
    global: { plugins: [pinia, i18n] },
  })
  // settingsStore.ensureLoaded() ist async — flushen
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('SettingsSectionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('rendert nur Tabs der erlaubten Sektionen', async () => {
    const w = await mountPanel(['llm', 'logging'])
    const tabs = w.findAll('.v4-tab__label').map((t) => t.text())
    expect(tabs).toEqual(['LLM', 'Logging'])
  })

  it('versteckt Sektionen, die nicht in allowedSections sind', async () => {
    const w = await mountPanel(['llm'])
    const tabs = w.findAll('.v4-tab__label').map((t) => t.text())
    expect(tabs).not.toContain('Neo4j')
  })

  it('rendert die Field-Tabelle der aktiven Sektion', async () => {
    const w = await mountPanel(['llm', 'logging'])
    expect(w.text()).toContain('LLM_MODEL_NAME')
  })

  it('zeigt Empty-Banner, wenn keine Sektion erlaubt ist', async () => {
    const w = await mountPanel([])
    expect(w.find('.v4-banner--muted').exists()).toBe(true)
  })

  // Regression: Gemini HIGH-Finding auf #422 — hasDirtySecrets darf nur
  // Secrets aus den erlaubten Sektionen beruecksichtigen.
  it('zeigt kein Secret-Modal, wenn dirty Secret in nicht sichtbarer Sektion liegt', async () => {
    const w = await mountPanel(['llm'])
    const { useSettingsStore } = await import('@/store/settings')
    const store = useSettingsStore()
    // dirty Secret in 'neo4j' setzen — neo4j ist NICHT in allowedSections.
    ;(store.draft as Record<string, unknown>).NEO4J_PASSWORD = 'neu'
    await flushPromises()

    // Save-Button finden (zweiter Btn im Footer) und klicken.
    const buttons = w.findAll('button')
    const saveBtn = buttons.find((b) => b.text().includes('Speichern'))
    expect(saveBtn).toBeDefined()
    await saveBtn!.trigger('click')
    await flushPromises()

    // Modal darf nicht erscheinen, weil das dirty Secret nicht zu den
    // sichtbaren Sektionen gehoert.
    expect(w.find('.v4-modal').exists()).toBe(false)
  })
})
