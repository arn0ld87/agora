import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SystemHealthCard from '../SystemHealthCard.vue'
import type { SystemStatusResponse } from '../../../../contracts/systemStatusContract'
import { makeI18n } from './dashTestHelpers'

function buildStatus(over: Partial<SystemStatusResponse> = {}): SystemStatusResponse {
  return {
    backend: { ok: true, version: '1.0.0', auth_mode: 'single_user_token' },
    neo4j: { reachable: true, uri: 'bolt://neo4j:7687', error: null },
    ollama: {
      reachable: true,
      base_url: 'http://localhost:11434',
      models_available: ['qwen2.5:32b', 'llama3.1:8b'],
      default_model: 'qwen2.5:32b',
      error: null,
    },
    disk: { uploads: { path: '/uploads', used_pct: 42, free_bytes: 12_000_000_000, total_bytes: 24_000_000_000 } },
    gpu: { nvidia_smi_available: true, ollama_uses_gpu: true, hints: [] },
    timestamp: '2026-05-14T12:00:00Z',
    ...over,
  } as SystemStatusResponse
}

describe('SystemHealthCard', () => {
  it('rendert drei Health-Rows im Ready-State', () => {
    const w = mount(SystemHealthCard, {
      props: { status: buildStatus(), loading: false, error: '' },
      global: { plugins: [makeI18n()] },
    })
    const rows = w.findAll('.sh-row')
    expect(rows).toHaveLength(3)
    expect(w.text()).toContain('Ollama')
    expect(w.text()).toContain('Neo4j')
    expect(w.text()).toContain('OASIS')
  })

  it('rendert Disk-Footer mit used_pct', () => {
    const w = mount(SystemHealthCard, {
      props: { status: buildStatus(), loading: false, error: '' },
      global: { plugins: [makeI18n()] },
    })
    expect(w.find('.sh-disk').exists()).toBe(true)
    expect(w.find('.sh-disk__value').text()).toContain('42%')
  })

  it('rendert Error-State mit Retry-Button', () => {
    const w = mount(SystemHealthCard, {
      props: { status: null, loading: false, error: 'Backend offline' },
      global: { plugins: [makeI18n()] },
    })
    expect(w.find('.sh-error').exists()).toBe(true)
    expect(w.find('.sh-retry').exists()).toBe(true)
    expect(w.text()).toContain('Backend offline')
  })

  it('emit refresh bei Retry-Klick', async () => {
    const w = mount(SystemHealthCard, {
      props: { status: null, loading: false, error: 'down' },
      global: { plugins: [makeI18n()] },
    })
    await w.find('.sh-retry').trigger('click')
    expect(w.emitted('refresh')).toBeTruthy()
  })
})
