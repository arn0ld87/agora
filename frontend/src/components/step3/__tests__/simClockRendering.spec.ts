/**
 * #1018 — die Sim-Uhr der Live-Feed-Kopfzeile muss sich über einen Lauf bewegen.
 *
 * Die bestehenden Tests prüfen useSimClock und SimulationProgressPanel jeweils
 * für sich, mit einem einzelnen Zeitwert. Damit blieb offen, was das Issue
 * tatsächlich verlangt: dass eine Folge eingehender post_created-Frames die
 * *gerenderte* Kopfzeile verändert.
 *
 * Der Host unten bindet die Uhr an das Panel wie Step3Simulation es tut —
 * Composable → computed → Prop → gerendertes <time>. Geprüft wird der sichtbare
 * String, nicht der Zwischenzustand.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { defineComponent } from 'vue'

import SimulationProgressPanel from '../SimulationProgressPanel.vue'
import { useSimClock, clearSimClock } from '@/composables/useSimClock'
import type { PostCreatedEvent } from '@/contracts/postEventContract'

const SIM_ID = 'sim-1018-rendering'

const localStorageMock = (() => {
  const store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
})()
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true })

const i18n = createI18n({
  legacy: false,
  locale: 'de',
  missingWarn: false,
  fallbackWarn: false,
  messages: { de: {}, en: {} },
})

const globalStubs = {
  Kicker: { template: '<span><slot /></span>' },
}

function makeEvent(simTime: string | null): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: SIM_ID,
    post_id: 'p-' + Math.random().toString(36).slice(2),
    parent_post_id: null,
    platform: 'twitter',
persona_id: 'persona-1',
    persona_name: 'Test Persona',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: 'tick',
    timestamp: '2026-08-01T22:00:00.000Z',
    score: 0,
    sim_time: simTime,
  }
}

const Host = defineComponent({
  components: { SimulationProgressPanel },
  setup() {
    const clock = useSimClock(SIM_ID)
    return {
      currentSimTime: clock.currentSimTime,
      elapsed: clock.elapsed,
      ingest: clock.ingest,
    }
  },
  template: `
    <SimulationProgressPanel
      :total-actions="1"
      :twitter-actions="1"
      :reddit-actions="0"
      :current-sim-time="currentSimTime"
      :sim-elapsed-sec="elapsed"
    />
  `,
})

function mountHost() {
  return mount(Host, { global: { plugins: [i18n], stubs: globalStubs } })
}

function clockText(wrapper: ReturnType<typeof mountHost>): string {
  return wrapper.find('.sim-clock time').text()
}

beforeEach(() => clearSimClock(SIM_ID))
afterEach(() => clearSimClock(SIM_ID))

describe('Sim-Uhr im gerenderten Live-Feed-Kopf (#1018)', () => {
  it('bewegt sich über eine Folge von Frames mit wachsender sim_time', async () => {
    const wrapper = mountHost()

    // Vor dem ersten Frame gibt es nichts anzuzeigen.
    expect(wrapper.find('.sim-clock').exists()).toBe(false)

    const seen: string[] = []
    for (const simTime of [
      '2026-08-01T22:00:00.000Z',
      '2026-08-01T22:12:00.000Z',
      '2026-08-01T22:24:00.000Z',
      '2026-08-01T22:36:00.000Z',
    ]) {
      wrapper.vm.ingest(makeEvent(simTime))
      await wrapper.vm.$nextTick()
      seen.push(clockText(wrapper))
    }

    expect(wrapper.find('.sim-clock').exists()).toBe(true)
    expect(new Set(seen).size).toBe(seen.length)
    expect(seen).toEqual([...seen].sort())
  })

  it('steht still, solange alle Frames dieselbe sim_time tragen', async () => {
    // Das war das Verhalten vor dem Backend-Fix: sim_time wurde einmal pro
    // Runde berechnet, alle Posts einer Runde trugen denselben Wert.
    const wrapper = mountHost()

    const seen: string[] = []
    for (let i = 0; i < 4; i++) {
      wrapper.vm.ingest(makeEvent('2026-08-01T22:00:00.000Z'))
      await wrapper.vm.$nextTick()
      seen.push(clockText(wrapper))
    }

    expect(new Set(seen).size).toBe(1)
  })

  it('ignoriert Frames ohne sim_time, ohne die Anzeige zurückzusetzen', async () => {
    const wrapper = mountHost()

    wrapper.vm.ingest(makeEvent('2026-08-01T22:00:00.000Z'))
    await wrapper.vm.$nextTick()
    const afterFirst = clockText(wrapper)

    wrapper.vm.ingest(makeEvent(null))
    await wrapper.vm.$nextTick()

    expect(clockText(wrapper)).toBe(afterFirst)
  })

  it('verwirft rückwärts laufende Frames — die Anzeige springt nicht zurück', async () => {
    // Trägt die Rundengrenze aus compute_post_sim_time: überschritte sie ein
    // Intra-Runden-Versatz, käme genau dieser Fall zustande und die Uhr bliebe
    // ohne sichtbare Ursache stehen.
    const wrapper = mountHost()

    wrapper.vm.ingest(makeEvent('2026-08-01T22:30:00.000Z'))
    await wrapper.vm.$nextTick()
    const afterLater = clockText(wrapper)

    wrapper.vm.ingest(makeEvent('2026-08-01T22:05:00.000Z'))
    await wrapper.vm.$nextTick()

    expect(clockText(wrapper)).toBe(afterLater)
  })
})
