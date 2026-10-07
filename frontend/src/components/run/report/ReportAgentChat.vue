<script setup lang="ts">
/**
 * Nachfragen an den Berichtsagenten (Etappe 5, #1804, Bauplan 4.6), im Slot
 * `questions` der rechten Spalte. Der Chat hängt am Lauf, nicht an der Fassung;
 * ein dezenter Satz sagt das. Antworten sind als Modellausgabe gekennzeichnet
 * („SIM“ plus Text) und laufen als Markdown durch `renderMarkdown`
 * (marked + DOMPurify), dieselbe Funktion wie der Lesetext. Fragen und Fehler
 * stehen als Text, nie als HTML.
 *
 * Barrierefreiheit: Eingabe mit `label[for]`, Senden per Knopf oder Strg/Cmd+Enter,
 * Verlauf als `role="log"` (neue Antworten werden angesagt), Sendezustand in
 * einer `aria-live`-Region, Fehler als `role="alert"`.
 *
 * Ohne Berichtsfassung gibt es eine Erklärung statt eines Eingabefelds.
 */
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRunReportContext } from '@/composables/run/report/useRunReport'
import { useReportAgentChat } from '@/composables/run/report/useReportAgentChat'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ simulationId: string }>()
const { t } = useI18n()
const ctx = useRunReportContext()

const chat = useReportAgentChat({ simulationId: () => props.simulationId, t: (key) => t(key) })
const draft = ref('')

const hasVersion = computed(
  () => ctx.versions.value.status === 'ok' && ctx.versions.value.items.length > 0,
)
const canSend = computed(() => draft.value.trim().length > 0 && !chat.sending.value)

async function submit(): Promise<void> {
  if (!canSend.value) return
  const text = draft.value
  draft.value = ''
  await chat.send(text)
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    void submit()
  }
}
</script>

<template>
  <div class="rac" data-testid="report-chat">
    <p v-if="!hasVersion" class="rac__note" data-testid="report-chat-unavailable">
      {{ t('views.run.report.chat.unavailable') }}
    </p>

    <template v-else>
      <p class="rac__scope" data-testid="report-chat-scope">{{ t('views.run.report.chat.scope') }}</p>

      <div class="rac__log" role="log" :aria-label="t('views.run.report.chat.logLabel')" data-testid="report-chat-log">
        <p v-if="chat.messages.value.length === 0" class="rac__note">{{ t('views.run.report.chat.empty') }}</p>
        <template v-for="m in chat.messages.value" :key="m.id">
          <div v-if="m.role === 'user'" class="rac__msg rac__msg--user" data-testid="report-chat-question">
            <p class="rac__who">{{ t('views.run.report.chat.you') }}</p>
            <p class="rac__text">{{ m.content }}</p>
          </div>
          <div v-else-if="m.role === 'assistant'" class="rac__msg rac__msg--agent" data-testid="report-chat-answer">
            <p class="rac__who">
              <span class="rac__mark" data-testid="report-chat-mark">{{ t('views.run.report.chat.mark') }}</span>
              {{ t('views.run.report.chat.agentLabel') }}
            </p>
            <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown säubert mit DOMPurify -->
            <div class="rac__body" v-html="renderMarkdown(m.content)" />
          </div>
          <p v-else class="rac__problem" role="alert" data-testid="report-chat-error">{{ m.content }}</p>
        </template>
      </div>

      <p class="rac__status" role="status" aria-live="polite" data-testid="report-chat-status">
        {{ chat.sending.value ? t('views.run.report.chat.sending') : '' }}
      </p>

      <form class="rac__form" @submit.prevent="submit">
        <label class="rac__label" for="report-chat-input">{{ t('views.run.report.chat.inputLabel') }}</label>
        <textarea
          id="report-chat-input"
          v-model="draft"
          class="rac__input"
          rows="3"
          aria-describedby="report-chat-hint"
          data-testid="report-chat-input"
          @keydown="onKey"
        />
        <p id="report-chat-hint" class="rac__hint">{{ t('views.run.report.chat.hint') }}</p>
        <div class="rac__actions">
          <button type="button" class="rac__send" :disabled="!canSend" data-testid="report-chat-send" @click="submit">
            {{ t('views.run.report.chat.send') }}
          </button>
          <button
            type="button"
            class="rac__clear"
            :disabled="chat.messages.value.length === 0 || chat.sending.value"
            data-testid="report-chat-clear"
            @click="chat.clear()"
          >
            {{ t('views.run.report.chat.clear') }}
          </button>
        </div>
      </form>
    </template>
  </div>
</template>

<style scoped>
.rac {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.rac__note,
.rac__scope,
.rac__hint,
.rac__status {
  margin: 0;
  font-size: 12px;
  color: var(--fg2);
}
.rac__status:empty {
  display: none;
}
.rac__log {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
}
.rac__msg {
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
}
.rac__msg--user {
  background: var(--s3);
}
.rac__who {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg3);
}
.rac__mark {
  padding: 0 6px;
  border: 1px solid var(--acc-line);
  border-radius: var(--ag-r-pill);
  color: var(--fg);
  font-size: 11px;
  font-weight: 700;
}
.rac__text {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--fg);
}
.rac__body {
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
  color: var(--fg);
}
.rac__body :deep(p) {
  margin: 0 0 6px;
}
.rac__problem {
  margin: 0;
  padding: 8px 10px;
  border: 1px solid var(--err);
  border-radius: var(--ag-r-12);
  font-size: 13px;
  color: var(--err);
  overflow-wrap: anywhere;
}
.rac__form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rac__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg3);
}
.rac__input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  resize: vertical;
}
.rac__input:focus-visible,
.rac__send:focus-visible,
.rac__clear:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.rac__actions {
  display: flex;
  gap: 8px;
}
.rac__send,
.rac__clear {
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.rac__send:disabled,
.rac__clear:disabled {
  color: var(--fg3);
  cursor: not-allowed;
}
</style>
