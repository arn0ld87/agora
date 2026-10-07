import { defineComponent, h } from 'vue'
import { useSimulationRunStateContext } from '@/composables/run/simulation/useSimulationRunStateContext'
import type { SimulationRunState } from '@/composables/run/simulation/useSimulationRunState'

/** Testverbraucher: nimmt den Laufstand aus der Hülle bzw. legt einen eigenen an und merkt sich ihn. */
export function makeConsumer(seen: SimulationRunState[]) {
  return defineComponent({
    props: { simulationId: { type: String, default: 'sim_1' } },
    setup(props) {
      seen.push(useSimulationRunStateContext(() => props.simulationId))
      return () => h('div', { 'data-testid': 'consumer' })
    },
  })
}
