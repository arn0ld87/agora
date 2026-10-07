<script setup lang="ts">
/**
 * Mittlere Spalte der Interviews (#1805, Etappe 6, Bauplan 4.7).
 *
 * Einzelgespräch: Verlauf "Du: …" / "<Name> (SIM · Interview): …". Jede Antwort
 * ist eine eigene Fläche mit den Marken "SIM" und "Interview" und sieht
 * bewusst nicht aus wie ein Feed-Beitrag (kein `TwitterCard`/`RedditRow`).
 * Gruppenfrage: die Antworten stehen nebeneinander (Spaltenraster, bricht bei
 * schmaler Breite um), je Persona Antwort oder Fehler, mit Verweis ins
 * Einzelgespräch. Eingabe: echtes Label, Senden per Knopf und Strg/Cmd+Enter,
 * während des Sendens gesperrt mit Status, daneben Modell und Kostenhinweis.
 * Der Budgetabbruch steht dauerhaft in `InterviewBudgetNotice` (View).
 *
 * Schnittstelle: Props `selection` (geparste conversationId oder null),
 * `personaById`, `canAsk` (false: Hinweis statt Eingabefeld), `personasLoading`
 * (Profile noch nicht geladen: unbekannte Persona wird dann nicht gemeldet).
 */
import { computed, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import type { RunPersona } from '@/composables/run/simulation/useRunPersonas'
import { useRunInterviewsContext } from '@/composables/run/interviews/useRunInterviews'
import {
  conversationIdForPersona,
  type ParsedConversationId,
} from '@/composables/run/interviews/conversations'

const props = withDefaults(
  defineProps<{
    selection: ParsedConversationId | null
    personaById: (personaId: string) => RunPersona | null
    canAsk: boolean
    simulationId?: string
    personasLoading?: boolean
  }>(),
  { simulationId: '', personasLoading: false },
)
const { t, locale } = useI18n()
const ctx = useRunInterviewsContext()

const inputId = `interviews-ask-${useId()}`
const text = ref('')
const inputEl = ref<HTMLTextAreaElement | null>(null)
// Höfliche Ansage nach dem Senden (Live-Region `ask-status`).
const announce = ref('')

function nameOf(agentId: number): string {
  return props.personaById(String(agentId))?.name ?? t('views.run.interviews.agentFallback', { n: agentId })
}

function formatTime(stamp: string | null | undefined): string {
  if (!stamp) return ''
  const d = new Date(stamp)
  return Number.isNaN(d.getTime()) ? stamp : d.toLocaleString(locale.value)
}

function platformLabel(platform: string | null | undefined): string {
  if (!platform) return ''
  return platform === 'twitter' || platform === 'reddit'
    ? t(`views.run.simFeed.network.${platform}`)
    : platform
}

const persona = computed(() => {
  const sel = props.selection
  if (!sel || sel.kind !== 'persona') return null
  const turns = ctx.conversations.value.find((c) => c.agentId === sel.agentId)?.turns ?? []
  return {
    agentId: sel.agentId,
    name: nameOf(sel.agentId),
    turns,
    unknown: !props.personasLoading && turns.length === 0 && props.personaById(String(sel.agentId)) === null,
  }
})
const group = computed(() => {
  const sel = props.selection
  if (!sel || sel.kind !== 'group') return null
  return ctx.groupResults.value.find((g) => g.groupId === sel.groupId) ?? null
})
const answeredCount = computed(() => group.value?.answers.filter((a) => !a.error && a.answer).length ?? 0)
const hasAny = computed(() => ctx.conversations.value.length > 0 || ctx.groupResults.value.length > 0)

function personaTo(agentId: number) {
  return {
    name: 'RunInterviews',
    params: { simulationId: props.simulationId, conversationId: conversationIdForPersona(agentId) },
  }
}

// --- Kopieren ----------------------------------------------------------------

const copyStatus = ref('')
async function copy(value: string | null): Promise<void> {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    copyStatus.value = t('views.run.interviews.pane.copied')
  } catch {
    copyStatus.value = t('views.run.interviews.pane.copyFailed')
  }
}

// --- Senden ------------------------------------------------------------------

const canSubmit = computed(() => text.value.trim() !== '' && !ctx.sending.value)
async function send() {
  const sel = props.selection
  if (!sel || sel.kind !== 'persona' || !canSubmit.value) return
  const out = await ctx.ask(sel.agentId, text.value)
  if (out.status === 'answered') {
    text.value = ''
    announce.value = t('views.run.interviews.pane.answeredStatus', { name: nameOf(sel.agentId) })
  } else {
    announce.value = ''
  }
  // Der Fokus bleibt im Eingabefeld, auch nach Klick auf "Senden".
  inputEl.value?.focus()
}
</script>

<template>
  <section class="cpane" :aria-label="t('views.run.interviews.pane.aria')" data-testid="conversation-pane">
    <p v-if="!selection" class="cpane__hint" data-testid="pane-empty">
      {{ hasAny ? t('views.run.interviews.pane.choose') : t('views.run.interviews.pane.none') }}
    </p>

    <template v-else-if="persona">
      <h2 class="cpane__title" data-testid="pane-title">{{ t('views.run.interviews.pane.with', { name: persona.name }) }}</h2>
      <p v-if="persona.unknown" class="cpane__hint cpane__hint--warn" role="status" data-testid="pane-unknown-persona">
        {{ t('views.run.interviews.pane.unknownPersona', { n: persona.agentId }) }}
      </p>
      <template v-else>
        <p class="cpane__origin" data-testid="pane-origin">{{ t('views.run.interviews.pane.origin') }}</p>
        <p v-if="persona.turns.length === 0" class="cpane__hint" data-testid="pane-no-turns">
          {{ t('views.run.interviews.pane.noTurns') }}
        </p>
        <ol v-else class="cpane__turns" data-testid="turns">
          <li v-for="(turn, i) in persona.turns" :key="`${turn.timestamp}-${i}`" class="cpane__turn">
            <p class="cpane__q"><span class="cpane__who">{{ t('views.run.interviews.pane.you') }}</span> {{ turn.question }}</p>
            <div v-if="turn.error" class="cpane__sim cpane__sim--error" role="alert" data-testid="turn-error">
              <p class="cpane__head">
                <span class="cpane__who">{{ persona.name }}</span>
                <span class="cpane__time">{{ formatTime(turn.timestamp) }}</span>
              </p>
              <p class="cpane__body">{{ t('views.run.interviews.pane.failedReason', { reason: turn.error }) }}</p>
            </div>
            <article v-else class="cpane__sim" data-testid="turn-answer">
              <p class="cpane__head">
                <span class="cpane__who">{{ persona.name }}</span>
                <span class="cpane__badge">{{ t('views.run.interviews.pane.badgeSim') }}</span>
                <span class="cpane__badge">{{ t('views.run.interviews.pane.badgeInterview') }}</span>
                <span v-if="turn.platform" class="cpane__time">{{ platformLabel(turn.platform) }}</span>
                <span class="cpane__time">{{ formatTime(turn.timestamp) }}</span>
              </p>
              <p class="cpane__body">{{ turn.answer ?? t('views.run.interviews.noAnswer') }}</p>
              <button
                v-if="turn.answer"
                type="button"
                class="cpane__copy"
                data-testid="turn-copy"
                :aria-label="t('views.run.interviews.pane.copyAnswer', { name: persona.name })"
                @click="copy(turn.answer)"
              >
                {{ t('views.run.interviews.pane.copy') }}
              </button>
            </article>
          </li>
        </ol>
      </template>
    </template>

    <template v-else-if="group">
      <h2 class="cpane__title" data-testid="pane-title">{{ t('views.run.interviews.pane.groupTitle') }}</h2>
      <p class="cpane__origin" data-testid="pane-origin">{{ t('views.run.interviews.pane.origin') }}</p>
      <p class="cpane__q"><span class="cpane__who">{{ t('views.run.interviews.pane.you') }}</span> {{ group.question }}</p>
      <p class="cpane__count" data-testid="group-count">
        {{ t('views.run.interviews.pane.groupCount', { answered: answeredCount, total: group.answers.length }) }}
      </p>
      <ul class="cpane__grid" data-testid="group-answers">
        <li v-for="a in group.answers" :key="a.agentId" class="cpane__cell">
          <div v-if="a.error" class="cpane__sim cpane__sim--error" role="alert" data-testid="group-answer-error">
            <p class="cpane__head">
              <router-link :to="personaTo(a.agentId)" class="cpane__link" data-testid="group-answer-link">{{ nameOf(a.agentId) }}</router-link>
            </p>
            <p class="cpane__body">{{ t('views.run.interviews.pane.failedReason', { reason: a.error }) }}</p>
          </div>
          <article v-else class="cpane__sim" data-testid="group-answer">
            <p class="cpane__head">
              <router-link :to="personaTo(a.agentId)" class="cpane__link" data-testid="group-answer-link">{{ nameOf(a.agentId) }}</router-link>
              <span class="cpane__badge">{{ t('views.run.interviews.pane.badgeSim') }}</span>
              <span class="cpane__badge">{{ t('views.run.interviews.pane.badgeInterview') }}</span>
              <span v-if="a.platform" class="cpane__time">{{ platformLabel(a.platform) }}</span>
              <span class="cpane__time">{{ formatTime(a.timestamp) }}</span>
            </p>
            <p class="cpane__body">{{ a.answer }}</p>
            <button
              v-if="a.answer"
              type="button"
              class="cpane__copy"
              :aria-label="t('views.run.interviews.pane.copyAnswer', { name: nameOf(a.agentId) })"
              @click="copy(a.answer)"
            >
              {{ t('views.run.interviews.pane.copy') }}
            </button>
          </article>
        </li>
      </ul>
    </template>

    <p v-else class="cpane__hint" data-testid="pane-group-missing">{{ t('views.run.interviews.pane.groupGone') }}</p>

    <p class="cpane__sr" role="status" aria-live="polite" data-testid="copy-status">{{ copyStatus }}</p>

    <template v-if="persona && !persona.unknown">
      <form v-if="canAsk" class="cpane__form" data-testid="ask-form" @submit.prevent="send">
        <label :for="inputId" class="cpane__label">{{ t('views.run.interviews.pane.inputLabel') }}</label>
        <textarea
          :id="inputId"
          ref="inputEl"
          v-model="text"
          rows="3"
          class="cpane__input"
          data-testid="ask-input"
          :readonly="ctx.sending.value"
          :aria-busy="ctx.sending.value"
          :aria-describedby="`${inputId}-hint`"
          @keydown.ctrl.enter.prevent="send"
          @keydown.meta.enter.prevent="send"
        />
        <div :id="`${inputId}-hint`" class="cpane__meta">
          <p class="cpane__model" data-testid="ask-model">
            {{ ctx.modelLabel.value ? t('views.run.interviews.pane.model', { model: ctx.modelLabel.value }) : t('views.run.interviews.pane.modelUnknown') }}
          </p>
          <p class="cpane__model" data-testid="ask-cost">{{ t('views.run.interviews.pane.cost') }}</p>
          <p class="cpane__model">{{ t('views.run.interviews.pane.shortcut') }}</p>
        </div>
        <button type="submit" class="cpane__btn" :disabled="!canSubmit" data-testid="ask-send">
          {{ ctx.sending.value ? t('views.run.interviews.sending') : t('views.run.interviews.pane.send') }}
        </button>
        <p class="cpane__sr" role="status" aria-live="polite" data-testid="ask-status">
          {{ ctx.sending.value ? t('views.run.interviews.sending') : announce }}
        </p>
        <p
          v-if="ctx.sendError.value && !ctx.budgetExceeded.value"
          class="cpane__error"
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
.cpane__hint,
.cpane__origin,
.cpane__count {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}
.cpane__origin {
  color: var(--fg3);
  font-size: 12px;
}
.cpane__hint--warn {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
}
.cpane__turns,
.cpane__grid {
  margin: 0;
  padding: 0;
  list-style: none;
}
.cpane__turns {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cpane__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 12px;
}
.cpane__turn,
.cpane__cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.cpane__q {
  margin: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}
/* Eigene Fläche: gestrichelter Rahmen und Akzentkante, nie wie ein Feed-Beitrag. */
.cpane__sim {
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  padding: 8px 10px;
  border: 1px dashed var(--acc-line);
  border-left: 3px solid var(--acc);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  font-size: 13px;
}
.cpane__sim--error {
  border-style: solid;
  border-color: var(--err);
  background: var(--err-soft);
  color: var(--err);
}
.cpane__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin: 0;
}
.cpane__body {
  margin: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.cpane__who,
.cpane__link {
  font-weight: 650;
}
.cpane__link {
  color: var(--fg);
}
.cpane__link:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
.cpane__time {
  color: var(--fg3);
  font-size: 11px;
}
.cpane__badge {
  padding: 1px 6px;
  border: 1px solid var(--acc-line);
  border-radius: var(--ag-r-pill);
  color: var(--fg2);
  font-size: 11px;
}
.cpane__copy {
  align-self: flex-start;
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg2);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
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
.cpane__btn:focus-visible,
.cpane__copy:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
.cpane__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
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
.cpane__sr {
  margin: 0;
  color: var(--fg2);
  font-size: 12px;
}
.cpane__sr:empty {
  display: none;
}
</style>
