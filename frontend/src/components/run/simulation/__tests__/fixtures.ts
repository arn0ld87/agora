import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import type { PostCreatedEvent } from '@/contracts/postEventContract'
import de from '@/i18n/locales/de.json'

export function makePost(over: Partial<PostCreatedEvent> & { post_id: string }): PostCreatedEvent {
  return {
    event_type: 'post_created',
    simulation_id: 'sim_1',
    parent_post_id: null,
    platform: 'twitter',
    persona_id: '0',
    persona_name: 'Anna',
    voice_register: 'neutral-de',
    is_simulated: true,
    body: `Text ${over.post_id}`,
    timestamp: '2026-10-01T10:00:00+00:00',
    score: 0,
    ...over,
  } as PostCreatedEvent
}

const Stub = defineComponent({ render: () => h('div') })

/** Router mit den Adressen der Simulation für Link- und Navigationstests. */
export function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/simulations/:simulationId/simulation/feed/:network(twitter|reddit)?',
        name: 'RunSimulationFeed',
        component: Stub,
        props: true,
      },
      {
        path: '/simulations/:simulationId/simulation/post/:postId',
        name: 'RunSimulationPost',
        component: Stub,
        props: true,
      },
    ],
  })
  void router.push('/simulations/sim_1/simulation/feed')
  return router
}

export const i18n = createI18n({ legacy: false, locale: 'de', fallbackLocale: 'de', messages: { de } })
