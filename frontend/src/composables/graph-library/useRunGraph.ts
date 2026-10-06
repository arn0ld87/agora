/**
 * Loest den Graphen eines Laufs auf (#1797, Etappe 2): `GET /api/simulation/<id>`
 * liefert die `project_id`, danach laedt `useProjectGraph` Projekt und Graph.
 */
import { ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { getSimulation } from '@/api/simulation'
import { SimulationRefSchema } from './graphReaderModel'
import { errorText, useProjectGraph } from './useProjectGraph'

export type RunResolution =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'resolved' }

export function useRunGraph(simulationId: Ref<string>) {
  const { t } = useI18n()
  const resolution = ref<RunResolution>({ kind: 'loading' })
  const projectId = ref<string | null>(null)
  const graph = useProjectGraph(projectId)

  let seq = 0
  async function resolve(): Promise<void> {
    const mySeq = ++seq
    resolution.value = { kind: 'loading' }
    projectId.value = null
    try {
      const res = await getSimulation(simulationId.value)
      if (mySeq !== seq) return
      if (!res.success) throw new Error(res.error || t('views.graphLibrary.errors.run'))
      const parsed = SimulationRefSchema.safeParse(res.data)
      if (!parsed.success) throw new Error(t('views.graphLibrary.errors.schema'))
      projectId.value = parsed.data.project_id
      resolution.value = { kind: 'resolved' }
    } catch (caught) {
      if (mySeq !== seq) return
      resolution.value = { kind: 'error', message: errorText(caught, t('views.graphLibrary.errors.unknown')) }
    }
  }

  watch(simulationId, () => void resolve(), { immediate: true })

  return {
    resolution,
    projectId,
    ...graph,
    reload: () => resolve(),
  }
}
