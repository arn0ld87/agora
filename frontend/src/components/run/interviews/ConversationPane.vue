<script setup lang="ts">
/**
 * Mittlere Spalte der Interviews (#1805, Etappe 6). In diesem Ticket nur:
 * Verlauf des gewählten Gesprächs als schlichte Liste und ein Eingabefeld,
 * das `ask` aufruft. Das Folgeticket baut diese Spalte aus (Antwortkarten,
 * Gruppenvergleich nebeneinander, Modell- und Kostenhinweis).
 *
 * Schnittstelle: Props `selection` (geparste conversationId oder null),
 * `personaById`, `canAsk` (false: Hinweis statt Eingabefeld, z. B. Simulation
 * noch nicht gelaufen). Daten und `ask` aus `useRunInterviewsContext()`.
 * Jede Antwort trägt "SIM" und "Interview" (Bauplan 4.7).
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { RunPersona } from '@/composables/run/simulation/useRunPersonas'
import { useRunInterviewsContext } from '@/composables/run/interviews/useRunInterviews'
import type { ParsedConversationId } from '@/composables/run/interviews/conversations'

const props = defineProps<{
  selection: ParsedConversationId | null
  personaById: (personaId: string) => RunPersona | null
  canAsk: boolean
}>()
const { t } = useI18n()
const ctx = useRunInterviewsContext()

const inputId = `interviews-ask-${Math.random().toString(36).slice(2, 8)}`
const text = ref('')

function nameOf(agentId: number): string {
  return props.personaById(String(agentId))?.name ?? t('views.run.interviews.agentFallback', { n: agentId })
}

const persona = computed(() => {
  const sel = props.selection
  if (!sel || sel.kind !== 'persona') return null
  return {
    agentId: sel.agentId,
    name: nameOf(sel.agentId),
    turns: ctx.conversations.value.find((c) => c.agentId === sel.agentId)?.turns ?? [],
  }
})
const group = computed(() => {
  const sel = props.selection
  if (!sel || sel.kind !== 'group') return null
  return ctx.groupResults.value.find((g) => g.groupId === sel.groupId) ?? null
})
const hasAny = computed(() => ctx.conversations.value.length > 0 || ctx.groupResults.value.length > 0)

async function send() {
  const sel = props.selection
  if (!sel || sel.kind !== 'persona' || text.value.trim() === '' || ctx.sending.value) return
  const out = await ctx.ask(sel.agentId, text.value)
  if (out.status === 'answered') text.value = ''
}
</script>

<template>
  <section class="cpane" :aria-label="t('views.run.interviews.pane.aria')" data-testid="conversation-pane">
    <p v-if="!selection" class="cpane__hint" data-testid="pane-empty">
      {{ hasAny ? t('views.run.interviews.pane.choose') : t('views.run.interviews.pane.none') }}
    </p>

    <template v-else-if="persona">
      <h2 class="cpane__title" data-testid="pane-title">{{ t('views.run.interviews.pane.with', { name: persona.name }) }}</h2>
      <p v-if="persona.turns.length === 0" class="cpane__hint" data-testid="pane-no-turns">
        {{ t('views.run.interviews.pane.noTurns') }}
      </p>
      <ol v-else class="cpane__turns" data-testid="turns">
        <li v-for="(turn, i) in persona.turns" :key="`${turn.timestamp}-${i}`" class="cpane__turn">
          <p class="cpane__q"><span class="cpane__who">{{ t('views.run.interviews.pane.you') }}</span> {{ turn.question }}</p>
          <p v-if="turn.error" class="cpane__a cpane__a--error" role="alert" data-testid="turn-error">
            <span class="cpane__who">{{ persona.name }}</span> {{ turn.error }}
          </p>
          <p v-else class="cpane__a" data-testid="turn-answer">
            <span class="cpane__who">{{ persona.name }}</span>
            <span class="cpane__badge">{{ t('views.run.interviews.pane.badge') }}</span>
            {{ turn.answer ?? t('views.run.interviews.noAnswer') }}
          </p>
        </li>
      </ol>
    </template>

    <template v-else-if="group">
      <h2 class="cpane__title" data-testid="pane-title">{{ t('views.run.interviews.pane.groupTitle') }}</h2>
      <p class="cpane__q"><span class="cpane__who">{{ t('views.run.interviews.pane.you') }}</span> {{ group.question }}</p>
      <ul class="cpane__turns" data-testid="group-answers">
        <li v-for="a in group.answers" :key="a.agentId" class="cpane__turn">
          <p v-if="a.error" class="cpane__a cpane__a--error" role="alert">
            <span class="cpane__who">{{ nameOf(a.agentId) }}</span> {{ a.error }}
          </p>
          <p v-else class="cpane__a">
            <span class="cpane__who">{{ nameOf(a.agentId) }}</span>
            <span class="cpane__badge">{{ t('views.run.interviews.pane.badge') }}</span>
            {{ a.answer }}
          </p>
        </li>
      </ul>
    </template>

    <p v-else class="cpane__hint" data-testid="pane-group-missing">{{ t('views.run.interviews.pane.groupGone') }}</p>

    <template v-if="persona">
      <form v-if="canAsk" class="cpane__form" data-testid="ask-form" @submit.prevent="send">
        <label :for="inputId" class="cpane__label">{{ t('views.run.interviews.pane.inputLabel') }}</label>
        <textarea :id="inputId" v-model="text" rows="3" class="cpane__input" data-testid="ask-input" />
        <p class="cpane__model" data-testid="ask-model">
          {{ ctx.modelLabel.value ? t('views.run.interviews.pane.model', { model: ctx.modelLabel.value }) : t('views.run.interviews.pane.modelUnknown') }}
        </p>
        <button type="submit" class="cpane__btn" :disabled="ctx.sending.value || text.trim() === ''" data-testid="ask-send">
          {{ ctx.sending.value ? t('views.run.interviews.sending') : t('views.run.interviews.pane.send') }}
        </button>
        <p
          v-if="ctx.sendError.value"
          class="cpane__error"
          :class="{ 'cpane__error--budget': ctx.budgetExceeded.value }"
          role="alert"
          data-testid="ask-error"
        >
          {{ ctx.sendError.value }}
        </p>
      </form>
      <p v-else class="cpane__hint" data-testid="ask-blocked">{{ t('views.run.interviews.pane.notRun') }}</p>
    </template>
  </section>
</template>

<style scoped>
.cpane {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  color: var(--fg);
}
.cpane__title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
}
.cpane__hint {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}
.cpane__turns {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.cpane__turn {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cpane__q,
.cpane__a {
  margin: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.cpane__a {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
}
.cpane__a--error {
  border-color: var(--err);
  background: var(--err-soft);
  color: var(--err);
}
.cpane__who {
  font-weight: 650;
}
.cpane__badge {
  margin: 0 4px;
  padding: 1px 6px;
  border: 1px solid var(--acc-line);
  border-radius: var(--ag-r-pill);
  color: var(--fg2);
  font-size: 11px;
}
.cpane__form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cpane__label {
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.cpane__input {
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
}
.cpane__input:focus-visible,
.cpane__btn:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
.cpane__model {
  margin: 0;
  color: var(--fg3);
  font-size: 12px;
}
.cpane__btn {
  align-self: flex-start;
  padding: 6px 14px;
  border: 1px solid var(--acc-line);
  border-radius: var(--ag-r-8);
  background: var(--acc);
  color: var(--on-acc);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.cpane__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.cpane__error {
  margin: 0;
  padding: 6px 8px;
  border-radius: var(--ag-r-8);
  background: var(--err-soft);
  color: var(--err);
  font-size: 12px;
}
.cpane__error--budget {
  border: 1px solid var(--err);
  font-weight: 650;
}
</style>
