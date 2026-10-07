<script setup lang="ts">
/**
 * Reiter "Interviews" am Lauf (Etappe 6, #1805, Bauplan 4.7): Dreispalter.
 * Adresse: `/simulations/:simulationId/interviews/:conversationId?`
 * (`persona-<n>` oder `group-<kennung>`).
 *
 * GERÜST dieses Tickets. Die View legt `useRunInterviews` einmal an und
 * verteilt es per `provide` (`RUN_INTERVIEWS_KEY`); die Spalten holen es mit
 * `useRunInterviewsContext()`. Ein Folgeticket baut Mitte und rechts aus,
 * ohne dass diese View sich ändert. Schnittstellen:
 * - `ConversationList` (links):   `simulationId`, `activeId`, `personas`, `personaById`
 * - `ConversationPane` (Mitte):   `selection`, `personaById`, `canAsk`
 * - `InterviewPersonaPane` (rechts): `selection`, `personaById`
 * `selection` ist die geparste conversationId (`parseConversationId`).
 *
 * Nutzbar ab abgeschlossener Simulation: Läuft sie noch nicht oder wurde sie
 * nie gestartet (Zustand der Stufe im Arbeitsbereich), steht ein Hinweis statt
 * des Eingabefelds; der Reiter bleibt erreichbar. Kein `h1`: die Überschrift
 * gehört dem Arbeitsbereich.
 */
import { computed, inject, provide, toRef } from 'vue'
import { useI18n } from 'vue-i18n'
import ConversationList from '@/components/run/interviews/ConversationList.vue'
import ConversationPane from '@/components/run/interviews/ConversationPane.vue'
import InterviewBudgetNotice from '@/components/run/interviews/InterviewBudgetNotice.vue'
import InterviewPersonaPane from '@/components/run/interviews/InterviewPersonaPane.vue'
import { parseConversationId } from '@/composables/run/interviews/conversations'
import { RUN_INTERVIEWS_KEY, useRunInterviews } from '@/composables/run/interviews/useRunInterviews'
import { useRunPersonas } from '@/composables/run/simulation/useRunPersonas'
import { RUN_WORKSPACE_KEY } from '@/composables/run/useRunWorkspace'

const props = defineProps<{ simulationId: string; conversationId?: string }>()
const { t } = useI18n()

const simulationId = toRef(props, 'simulationId')
const interviews = useRunInterviews(simulationId)
provide(RUN_INTERVIEWS_KEY, interviews)
const personas = useRunPersonas(simulationId)

const workspace = inject(RUN_WORKSPACE_KEY, null)

// Stufen, in denen es (noch) keine abgeschlossene Simulation gibt.
const NOT_FINISHED = new Set(['notStarted', 'queued', 'running', 'paused'])
const canAsk = computed(() => {
  const row = workspace?.stages.value.find((r) => r.key === 'simulation')
  return !row || !NOT_FINISHED.has(row.state)
})

const selection = computed(() => parseConversationId(props.conversationId))
const activeId = computed(() => (selection.value ? (props.conversationId ?? null) : null))
const showInitialLoad = computed(() => interviews.loading.value && interviews.conversations.value.length === 0)
</script>

<template>
  <div class="interviews" data-testid="run-interviews">
    <p v-if="showInitialLoad" class="interviews__status" role="status" data-testid="interviews-loading">
      {{ t('views.run.interviews.loading') }}
    </p>

    <div v-if="interviews.error.value" class="interviews__alert" role="alert" data-testid="interviews-error">
      <span>{{ interviews.error.value }}</span>
      <button type="button" class="interviews__btn" data-testid="interviews-retry" @click="interviews.reload()">
        {{ t('views.run.interviews.retry') }}
      </button>
    </div>

    <p v-if="personas.error.value" class="interviews__alert" role="alert" data-testid="interviews-personas-error">
      {{ personas.error.value }}
    </p>

    <p v-if="!interviews.available.value" class="interviews__alert" role="alert" data-testid="interviews-unavailable">
      {{ t('views.run.interviews.unavailable') }}
      <span v-if="interviews.unavailableReason.value"> {{ interviews.unavailableReason.value }}</span>
    </p>

    <InterviewBudgetNotice />

    <p v-if="!canAsk" class="interviews__notice" role="status" data-testid="interviews-not-run">
      {{ t('views.run.interviews.notRun') }}
    </p>

    <div class="interviews__grid">
      <ConversationList
        :simulation-id="simulationId"
        :active-id="activeId"
        :personas="personas.personas.value"
        :persona-by-id="personas.personaById"
      />
      <ConversationPane
        :selection="selection"
        :persona-by-id="personas.personaById"
        :can-ask="canAsk && interviews.available.value"
        :simulation-id="simulationId"
        :personas-loading="personas.loading.value"
      />
      <InterviewPersonaPane :selection="selection" :persona-by-id="personas.personaById" />
    </div>
  </div>
</template>

<style scoped>
.interviews {
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--fg);
}
.interviews__grid {
  display: grid;
  grid-template-columns: minmax(200px, 260px) minmax(0, 1fr) minmax(200px, 280px);
  gap: 16px;
  align-items: start;
}
.interviews__status,
.interviews__notice {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}
.interviews__notice {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
}
.interviews__alert {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--ag-r-8);
  background: var(--err-soft);
  color: var(--err);
  font-size: 13px;
}
.interviews__btn {
  padding: 4px 10px;
  border: 1px solid var(--err);
  border-radius: var(--ag-r-8);
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.interviews__btn:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
@media (max-width: 900px) {
  .interviews__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
