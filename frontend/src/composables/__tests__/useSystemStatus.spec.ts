import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'

vi.mock('../../api/status', () => ({
  getSystemStatus: vi.fn(),
}))

import { getSystemStatus } from '../../api/status'
import { useSystemStatus, statusErrorKey, type UseSystemStatusReturn } from '../useSystemStatus'

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  messages: { de: { errors: { network: 'Netzwerkfehler' } }, en: {} },
})

const statusPayload = {
  backend: { ok: true, version: '0.9.1-dev', auth_mode: 'single_user_token' },
  neo4j: { reachable: true, error: null, uri: 'bolt://neo4j:7687' },
  ollama: {
    reachable: true,
    base_url: 'http://localhost:11434',
    models_available: ['qwen2.5:32b'],
    default_model: 'qwen2.5:32b',
    error: null,
  },
  disk: { uploads: { used_pct: 23.5, free_bytes: 1000, total_bytes: 4000 } },
  gpu: { nvidia_smi_available: false, ollama_uses_gpu: null, hints: [] },
  timestamp: '2026-05-14T10:00:00Z',
}

function mountComposable(): UseSystemStatusReturn {
  let exposed: UseSystemStatusReturn | undefined
  const Comp = defineComponent({
    setup() {
      exposed = useSystemStatus(15000)
      return () => h('div')
    },
  })
  mount(Comp, { global: { plugins: [i18n] } })
  return exposed as UseSystemStatusReturn
}

describe('useSystemStatus', () => {
  beforeEach(() => {
    vi.mocked(getSystemStatus).mockReset()
  })

  it('validiert erfolgreiche Status-Antworten via Zod', async () => {
    vi.mocked(getSystemStatus).mockResolvedValue({ success: true, data: statusPayload } as never)
    const s = mountComposable()

    await s.refresh()

    expect(s.error.value).toBe('')
    expect(s.status.value?.backend.version).toBe('0.9.1-dev')
    expect(s.status.value?.disk.uploads.used_pct).toBe(23.5)
    expect(s.status.value?.ollama.models_available).toEqual(['qwen2.5:32b'])
  })

  it('akzeptiert auch flaches Envelope ohne data-Wrapper', async () => {
    vi.mocked(getSystemStatus).mockResolvedValue({
      success: true,
      ...statusPayload,
    } as never)
    const s = mountComposable()

    await s.refresh()

    expect(s.error.value).toBe('')
    expect(s.status.value?.timestamp).toBe('2026-05-14T10:00:00Z')
  })

  it('behaelt last-known-good bei Schema-Mismatch', async () => {
    vi.mocked(getSystemStatus)
      .mockResolvedValueOnce({ success: true, data: statusPayload } as never)
      .mockResolvedValueOnce({ success: true, data: { backend: {} } } as never)
    const s = mountComposable()

    await s.refresh()
    await s.refresh()

    expect(s.error.value).toContain('Schema-Drift')
    expect(s.status.value?.timestamp).toBe('2026-05-14T10:00:00Z')
  })
})

describe('statusErrorKey', () => {
  it('bildet bekannte Fehlercodes auf ihren i18n-Schluessel ab', () => {
    expect(statusErrorKey({ code: 'unreachable' })).toBe('dashboard.system.error.unreachable')
    expect(statusErrorKey({ code: 'timeout' })).toBe('dashboard.system.error.timeout')
    expect(statusErrorKey({ code: 'auth' })).toBe('dashboard.system.error.auth')
  })

  it('faellt bei unbekanntem Code auf unexpected zurueck, statt leer zu bleiben', () => {
    expect(statusErrorKey({ code: 'quantum_flux' })).toBe('dashboard.system.error.unexpected')
  })

  it('liefert einen leeren Schluessel, wenn kein Fehler anliegt', () => {
    expect(statusErrorKey(null)).toBe('')
    expect(statusErrorKey(undefined)).toBe('')
  })
})
