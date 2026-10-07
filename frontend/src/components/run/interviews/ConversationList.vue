<script setup lang="ts">
/**
 * Linke Spalte der Interviews (#1805, Etappe 6): Gespräche des Laufs, "Neues
 * Gespräch" mit Persona-Auswahl und "Gruppenfrage".
 *
 * Schnittstelle: Props `simulationId`, `activeId` (conversationId der Adresse
 * oder null), `personas` (Auswahlliste) und `personaById` (Namen). Daten und
 * Aktionen kommen aus `useRunInterviewsContext()`. Die Auswahl ändert die
 * Adresse (`RunInterviews`), die Liste hält keinen eigenen Zustand dafür.
 */
import { computed, ref, useId } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { RunPersona } from '@/composables/run/simulation/useRunPersonas'
import { useRunInterviewsContext } from '@/composables/run/interviews/useRunInterviews'
import { conversationIdForGroup, conversationIdForPersona } from '@/composables/run/interviews/conversations'

const props = defineProps<{
  simulationId: string
  activeId: string | null
  personas: RunPersona[]
  personaById: (personaId: string) => RunPersona | null
}>()
const { t } = useI18n()
const router = useRouter()
const ctx = useRunInterviewsContext()

const uid = useId()
const pickId = `interviews-new-${uid}`
const groupTextId = `interviews-group-text-${uid}`

function nameOf(agentId: number): string {
  return props.personaById(String(agentId))?.name ?? t('views.run.interviews.agentFallback', { n: agentId })
}

function open(conversationId: string) {
  void router.push({ name: 'RunInterviews', params: { simulationId: props.simulationId, conversationId } })
}

const picked = ref('')
function openNew() {
  if (picked.value === '') return
  open(conversationIdForPersona(Number(picked.value)))
}

const groupOpen = ref(false)
const groupIds = ref<string[]>([])
const groupText = ref('')
const groupSummary = ref<{ asked: number; answered: number; failed: number } | null>(null)

const warn = computed(() => ctx.largeGroupWarning(groupIds.value.length))
const canSendGroup = computed(
  () => groupIds.value.length > 0 && groupText.value.trim() !== '' && !ctx.sending.value,
)

async function sendGroup() {
  if (!canSendGroup.value) return
  const out = await ctx.askGroup(groupIds.value.map(Number), groupText.value)
  groupSummary.value = out
  const latest = ctx.groupResults.value[0]
  if (latest && out.asked > 0) {
    groupText.value = ''
    open(conversationIdForGroup(latest.groupId))
  }
}

function groupLabel(question: string): string {
  const flat = question.replace(/\s+/g, ' ').trim()
  return flat.length > 48 ? `${flat.slice(0, 47)}…` : flat
}
</script>

<template>
  <nav class="clist" :aria-label="t('views.run.interviews.list.aria')" data-testid="conversation-list">
    <h2 class="clist__heading">{{ t('views.run.interviews.list.heading') }}</h2>

    <p v-if="ctx.conversations.value.length === 0 && ctx.groupResults.value.length === 0" class="clist__empty" data-testid="list-empty">
      {{ t('views.run.interviews.list.empty') }}
    </p>
    <ul v-else class="clist__items">
      <li v-for="g in ctx.groupResults.value" :key="g.conversationId">
        <router-link
          :to="{ name: 'RunInterviews', params: { simulationId, conversationId: g.conversationId } }"
          class="clist__item"
          :class="{ 'clist__item--active': activeId === g.conversationId }"
          :aria-current="activeId === g.conversationId ? 'page' : undefined"
          data-testid="conversation-item"
        >
          <span class="clist__name">{{ t('views.run.interviews.list.group', { question: groupLabel(g.question) }) }}</span>
          <span class="clist__count">{{ g.count }}</span>
        </router-link>
      </li>
      <li v-for="c in ctx.conversations.value" :key="c.conversationId">
        <router-link
          :to="{ name: 'RunInterviews', params: { simulationId, conversationId: c.conversationId } }"
          class="clist__item"
          :class="{ 'clist__item--active': activeId === c.conversationId }"
          :aria-current="activeId === c.conversationId ? 'page' : undefined"
          data-testid="conversation-item"
        >
          <span class="clist__name">{{ nameOf(c.agentId) }}</span>
          <span class="clist__count">{{ c.count }}</span>
        </router-link>
      </li>
    </ul>

    <section class="clist__block" :aria-labelledby="`${pickId}-title`">
      <h3 :id="`${pickId}-title`" class="clist__title">{{ t('views.run.interviews.new.title') }}</h3>
      <label :for="pickId" class="clist__label">{{ t('views.run.interviews.new.label') }}</label>
      <select :id="pickId" v-model="picked" class="clist__field" data-testid="new-persona">
        <option value="">{{ t('views.run.interviews.new.placeholder') }}</option>
        <option v-for="p in personas" :key="p.personaId" :value="p.personaId">{{ p.name }}</option>
      </select>
      <button type="button" class="clist__btn" :disabled="picked === ''" data-testid="new-open" @click="openNew">
        {{ t('views.run.interviews.new.open') }}
      </button>
    </section>

    <section class="clist__block">
      <h3 class="clist__title">
        <button
          type="button"
          class="clist__toggle"
          :aria-expanded="groupOpen"
          :aria-controls="`${groupTextId}-panel`"
          data-testid="group-toggle"
          @click="groupOpen = !groupOpen"
        >
          {{ t('views.run.interviews.group.title') }}
        </button>
      </h3>
      <div v-show="groupOpen" :id="`${groupTextId}-panel`" class="clist__panel">
        <fieldset class="clist__fieldset">
          <legend class="clist__label">{{ t('views.run.interviews.group.personas') }}</legend>
          <div v-for="p in personas" :key="p.personaId" class="clist__check">
            <input :id="`${groupTextId}-p${p.personaId}`" v-model="groupIds" type="checkbox" :value="p.personaId" />
            <label :for="`${groupTextId}-p${p.personaId}`">{{ p.name }}</label>
          </div>
        </fieldset>
        <label :for="groupTextId" class="clist__label">{{ t('views.run.interviews.group.question') }}</label>
        <textarea :id="groupTextId" v-model="groupText" rows="3" class="clist__field" data-testid="group-text" />
        <p v-if="warn" class="clist__warn" role="status" data-testid="group-warning">
          {{ t('views.run.interviews.group.large', { n: groupIds.length }) }}
        </p>
        <p class="clist__hint" data-testid="group-cost">
          {{ t('views.run.interviews.group.cost', { n: groupIds.length }, groupIds.length) }}
        </p>
        <button type="button" class="clist__btn" :disabled="!canSendGroup" data-testid="group-send" @click="sendGroup">
          {{ ctx.sending.value ? t('views.run.interviews.sending') : t('views.run.interviews.group.send') }}
        </button>
        <p v-if="groupSummary" class="clist__summary" role="status" data-testid="group-summary">
          {{ t('views.run.interviews.group.summary', groupSummary) }}
        </p>
        <p v-if="ctx.sendError.value" class="clist__error" role="alert" data-testid="group-error">
          {{ ctx.sendError.value }}
        </p>
      </div>
    </section>
  </nav>
</template>

<style scoped>
.clist {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
  color: var(--fg);
}
.clist__heading,
.clist__title {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
  color: var(--fg2);
}
.clist__empty {
  margin: 0;
  color: var(--fg2);
  font-size: 13px;
}
.clist__items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.clist__item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: var(--ag-r-8);
  color: var(--fg);
  text-decoration: none;
  font-size: 13px;
}
.clist__item:hover {
  background: var(--s3);
}
.clist__item:focus-visible,
.clist__btn:focus-visible,
.clist__toggle:focus-visible,
.clist__field:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
.clist__item--active {
  border-color: var(--acc-line);
  background: var(--s3);
}
.clist__name {
  overflow-wrap: anywhere;
}
.clist__count {
  color: var(--fg3);
}
.clist__block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-12);
  background: var(--s2);
}
.clist__panel,
.clist__fieldset {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  border: 0;
}
.clist__hint {
  margin: 0;
  color: var(--fg3);
  font-size: 12px;
}
.clist__label {
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.clist__field {
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
}
.clist__check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.clist__btn {
  align-self: flex-start;
  padding: 6px 12px;
  border: 1px solid var(--acc-line);
  border-radius: var(--ag-r-8);
  background: var(--acc);
  color: var(--on-acc);
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.clist__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.clist__toggle {
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}
.clist__warn {
  margin: 0;
  padding: 6px 8px;
  border-radius: var(--ag-r-8);
  background: var(--warn-soft);
  color: var(--warn);
  font-size: 12px;
}
.clist__summary {
  margin: 0;
  color: var(--fg2);
  font-size: 12px;
}
.clist__error {
  margin: 0;
  padding: 6px 8px;
  border-radius: var(--ag-r-8);
  background: var(--err-soft);
  color: var(--err);
  font-size: 12px;
}
</style>
