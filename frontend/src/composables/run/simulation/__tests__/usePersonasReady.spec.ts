import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { RUN_WORKSPACE_KEY } from '@/composables/run/useRunWorkspace'
import { usePersonasReady } from '../usePersonasReady'

function ready(stages: { key: string; state: string }[] | null): boolean {
  let value = false
  const Probe = defineComponent({
    setup() {
      const r = usePersonasReady()
      return () => h('span', String((value = r.value)))
    },
  })
  mount(Probe, {
    global: { provide: stages ? { [RUN_WORKSPACE_KEY as symbol]: { stages: ref(stages) } } : {} },
  })
  return value
}

describe('usePersonasReady', () => {
  it('ist bereit bei Abschlusszuständen der Personas-Stufe, auch degradiert und Fallback', () => {
    for (const state of ['done', 'degraded', 'fallback', 'incomplete']) {
      expect(ready([{ key: 'personas', state }])).toBe(true)
    }
  })

  it('ist nicht bereit, solange die Stufe läuft, fehlt oder nicht gestartet ist', () => {
    expect(ready([{ key: 'personas', state: 'running' }])).toBe(false)
    expect(ready([{ key: 'personas', state: 'notStarted' }])).toBe(false)
    expect(ready([])).toBe(false)
  })

  it('sperrt nichts ohne Arbeitsbereich', () => {
    expect(ready(null)).toBe(true)
  })
})
