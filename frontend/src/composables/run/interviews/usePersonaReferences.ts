/**
 * Verweise einer Persona in Feed und Bericht (#1805, Etappe 6, Bauplan 4.7).
 *
 * Beide Zahlen kommen aus bereits vorhandenen Endpunkten, nichts wird
 * geschätzt:
 * - `feedCount(agentId)`: Beiträge der Persona im Feed-Snapshot (Twitter und
 *   Reddit, `persona_id` = Listenposition = `agent_id`). `feedTruncated` ist
 *   wahr, wenn ein Snapshot sein Limit erreichte: die Zahl ist dann ein
 *   Mindestwert. `null`, solange nichts geladen ist oder der Abruf scheiterte.
 * - `citedCount(agentId)`: Einträge des Beleg-Index der jüngsten Berichtsfassung
 *   mit `voice_key === "agent:<agentId>"`. `null`, wenn es keinen Bericht gibt
 *   oder die Evidence nicht lesbar ist (fehlgeschlagen oder `evidence_omitted`).
 */
import { computed, ref, toValue, watch, type ComputedRef, type Ref } from 'vue'
import { getReportEvidence } from '@/api/report'
import { useRunFeed } from '@/composables/run/simulation/useRunFeed'

export interface PersonaReferences {
  feedCount: (agentId: number) => number | null
  feedTruncated: ComputedRef<boolean>
  citedCount: (agentId: number) => number | null
}

export function usePersonaReferences(
  simulationId: Ref<string> | string,
  latestReportId: Ref<string | null> | (() => string | null),
): PersonaReferences {
  // Nur Snapshot, kein Strom: die Interviews brauchen keine Live-Beiträge.
  const feed = useRunFeed(simulationId, { immediate: false })
  const feedLoaded = ref(false)
  const cited = ref<Map<string, number> | null>(null)
  let evidenceToken = 0

  watch(
    () => toValue(simulationId),
    () => {
      feedLoaded.value = false
      void feed
        .reload()
        .then(() => {
          feedLoaded.value = feed.error.value === null
        })
        .catch(() => {
          feedLoaded.value = false
        })
    },
    { immediate: true },
  )

  watch(
    () => toValue(latestReportId),
    async (reportId) => {
      const mine = ++evidenceToken
      cited.value = null
      if (!reportId) return
      try {
        const env = await getReportEvidence(reportId)
        if (mine !== evidenceToken) return
        if (!('data' in env) || env.success !== true) return
        const counts = new Map<string, number>()
        for (const record of Object.values(env.data.evidence_index)) {
          if (record.voice_key) counts.set(record.voice_key, (counts.get(record.voice_key) ?? 0) + 1)
        }
        cited.value = counts
      } catch {
        if (mine === evidenceToken) cited.value = null
      }
    },
    { immediate: true },
  )

  const perPersona = computed(() => {
    const counts = new Map<string, number>()
    for (const p of feed.posts.value) counts.set(p.persona_id, (counts.get(p.persona_id) ?? 0) + 1)
    return counts
  })

  return {
    feedCount: (agentId) => (feedLoaded.value ? (perPersona.value.get(String(agentId)) ?? 0) : null),
    feedTruncated: computed(() => feed.truncated.value),
    citedCount: (agentId) => (cited.value ? (cited.value.get(`agent:${agentId}`) ?? 0) : null),
  }
}
