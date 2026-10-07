<script setup lang="ts">
/**
 * Rechte Spalte der Interviews (#1805, Etappe 6, Bauplan 4.7).
 *
 * Einzelgespräch: wiederverwendete `PersonaCard`, darunter "Beiträge im Feed
 * (n) →" (Sprung in den Feed mit dem Personen-Filter) und "Im Bericht zitiert
 * (n) →" (Sprung in den Bericht). Eine Zahl erscheint nur, wenn sie aus
 * vorhandenen Endpunkten belegt ist (`usePersonaReferences`); sonst steht der
 * Verweis ohne Zahl bzw. die Zeile fehlt. Gruppengespräch: Liste der
 * beteiligten Personas mit Sprung ins Einzelgespräch.
 *
 * Schnittstelle: Props `selection` (geparste conversationId oder null),
 * `personaById`, optional `simulationId`, `references` (Zähler) und
 * `reportTo` (Ziel des Berichtssprungs, `null` ohne Bericht).
 */
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import PersonaCard from '@/components/run/simulation/PersonaCard.vue'
import type { RunPersona } from '@/composables/run/simulation/useRunPersonas'
import { useRunInterviewsContext } from '@/composables/run/interviews/useRunInterviews'
import type { PersonaReferences } from '@/composables/run/interviews/usePersonaReferences'
import {
  conversationIdForPersona,
  type ParsedConversationId,
} from '@/composables/run/interviews/conversations'

const props = withDefaults(
  defineProps<{
    selection: ParsedConversationId | null
    personaById: (personaId: string) => RunPersona | null
    simulationId?: string
    references?: PersonaReferences | null
    reportTo?: RouteLocationRaw | null
  }>(),
  { simulationId: '', references: null, reportTo: null },
)
const { t } = useI18n()
const ctx = useRunInterviewsContext()

const agentId = computed(() => (props.selection?.kind === 'persona' ? props.selection.agentId : null))
const persona = computed(() => (agentId.value !== null ? props.personaById(String(agentId.value)) : null))
const fallbackName = computed(() =>
  agentId.value !== null && !persona.value
    ? t('views.run.interviews.agentFallback', { n: agentId.value })
    : null,
)

const feedTo = computed<RouteLocationRaw | null>(() =>
  agentId.value !== null && props.simulationId
    ? {
        name: 'RunSimulationFeed',
        params: { simulationId: props.simulationId },
        query: { persona: String(agentId.value) },
      }
    : null,
)
const feedCount = computed(() => (agentId.value !== null ? (props.references?.feedCount(agentId.value) ?? null) : null))
const feedLabel = computed(() => {
  const n = feedCount.value
  if (n === null) return t('views.run.interviews.persona.feed')
  const key = props.references?.feedTruncated.value ? 'feedCountAtLeast' : 'feedCount'
  return t(`views.run.interviews.persona.${key}`, { n })
})
const citedCount = computed(() => (agentId.value !== null ? (props.references?.citedCount(agentId.value) ?? null) : null))

const group = computed(() => {
  const sel = props.selection
  if (!sel || sel.kind !== 'group') return null
  return ctx.groupResults.value.find((g) => g.groupId === sel.groupId) ?? null
})

function nameOf(id: number): string {
  return props.personaById(String(id))?.name ?? t('views.run.interviews.agentFallback', { n: id })
}
function personaTo(id: number): RouteLocationRaw {
  return {
    name: 'RunInterviews',
    params: { simulationId: props.simulationId, conversationId: conversationIdForPersona(id) },
  }
}
</script>

<template>
  <aside class="ipane" data-testid="interview-persona-pane">
    <template v-if="group">
      <section class="ipane__group" :aria-label="t('views.run.interviews.persona.participants')">
        <h3 class="ipane__heading">{{ t('views.run.interviews.persona.participants') }}</h3>
        <ul class="ipane__list" data-testid="group-participants">
          <li v-for="a in group.answers" :key="a.agentId">
            <router-link :to="personaTo(a.agentId)" class="ipane__link" data-testid="group-participant-link">
              {{ nameOf(a.agentId) }}
            </router-link>
          </li>
        </ul>
      </section>
    </template>
    <template v-else>
      <PersonaCard :persona="persona" :fallback-name="fallbackName" />
      <ul v-if="agentId !== null" class="ipane__list ipane__refs" data-testid="persona-refs">
        <li v-if="feedTo">
          <router-link :to="feedTo" class="ipane__link" data-testid="persona-feed-link">{{ feedLabel }} →</router-link>
        </li>
        <li v-if="citedCount !== null && reportTo">
          <router-link v-if="citedCount > 0" :to="reportTo" class="ipane__link" data-testid="persona-report-link">
            {{ t('views.run.interviews.persona.cited', { n: citedCount }) }} →
          </router-link>
          <span v-else class="ipane__muted" data-testid="persona-report-none">
            {{ t('views.run.interviews.persona.cited', { n: citedCount }) }}
          </span>
        </li>
      </ul>
    </template>
  </aside>
</template>

<style scoped>
.ipane {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.ipane__group {
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
}
.ipane__heading {
  margin: 0 0 6px;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.ipane__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: 13px;
}
.ipane__link {
  color: var(--fg);
  text-decoration: underline;
  overflow-wrap: anywhere;
}
.ipane__link:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
.ipane__muted {
  color: var(--fg2);
}
</style>
