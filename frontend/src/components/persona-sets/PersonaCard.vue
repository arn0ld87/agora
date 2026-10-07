<script setup lang="ts">
/**
 * Karte einer Persona im Satz (#1807, E7-F2). Eigene Checkbox für die Auswahl,
 * eigener Knopf zum Öffnen: beides per Tastatur erreichbar, Reihenfolge
 * Auswahl -> Öffnen. `fallback` und `ai_draft` tragen Symbol und Text, nie nur Farbe.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Badge from '@/components/ui/Badge.vue'
import type { PersonaSetEntry, PersonaSetQualityIssue } from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from './detailTestIds'

const props = defineProps<{
  entry: PersonaSetEntry
  selected: boolean
  selectDisabled: boolean
  issues: readonly PersonaSetQualityIssue[]
}>()
const emit = defineEmits<{ (e: 'toggle', entryId: string): void; (e: 'open', entryId: string): void }>()
const { t } = useI18n()

const initials = computed(() =>
  props.entry.profile.name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join(''),
)
const symbol = computed(() => ({ graph: '◇', manual: '✎', ai_draft: '✦', fallback: '⚠' })[props.entry.origin])
const variant = computed(() => (props.entry.origin === 'fallback' ? 'warn' : props.entry.origin === 'ai_draft' ? 'info' : 'outline'))
const degraded = computed(() => props.entry.origin === 'fallback' || props.entry.origin === 'ai_draft')
const titleId = computed(() => `persona-card-title-${props.entry.entry_id}`)
</script>

<template>
  <li class="pcard" :class="{ 'pcard--degraded': degraded, 'pcard--selected': selected }" :data-testid="Id.card" :data-origin="entry.origin">
    <input
      type="checkbox"
      class="pcard__select"
      :checked="selected"
      :disabled="selectDisabled"
      :aria-label="t('views.personaSets.detail.card.select', { name: entry.profile.name })"
      :data-testid="Id.cardSelect"
      @change="emit('toggle', entry.entry_id)"
    />
    <span class="pcard__avatar" aria-hidden="true">{{ initials }}</span>
    <div class="pcard__body">
      <button type="button" class="pcard__open" :aria-describedby="titleId" :data-testid="Id.cardOpen" @click="emit('open', entry.entry_id)">
        <span :id="titleId" class="pcard__name">{{ entry.profile.name }}</span>
        <span class="pcard__username">@{{ entry.profile.username }}</span>
      </button>
      <p class="pcard__meta">
        <span>{{ entry.profile.profession ?? t('views.personaSets.detail.card.noRole') }}</span>
        <span aria-hidden="true"> · </span>
        <span>{{ t(`views.personaSets.detail.kind.${entry.profile.persona_kind}`) }}</span>
      </p>
      <p class="pcard__tags">
        <Badge :variant="variant" :data-testid="Id.originBadge">
          <span aria-hidden="true">{{ symbol }}</span>
          {{ t(`views.personaSets.detail.origin.${entry.origin}`) }}
        </Badge>
      </p>
      <p v-if="entry.origin === 'fallback'" class="pcard__note">{{ t('views.personaSets.detail.card.fallbackNote') }}</p>
      <p v-else-if="entry.origin === 'ai_draft'" class="pcard__note">{{ t('views.personaSets.detail.card.draftNote') }}</p>
      <ul v-if="issues.length > 0" class="pcard__issues" :data-testid="Id.qualityHint" :aria-label="t('views.personaSets.detail.quality.issuesFor', { name: entry.profile.name })">
        <li v-for="(issue, i) in issues" :key="`${issue.code}-${i}`">
          <span class="pcard__sev">{{ t(`views.personaSets.detail.quality.severity.${issue.severity}`) }}</span>
          {{ issue.code }}
        </li>
      </ul>
    </div>
  </li>
</template>

<style scoped>
.pcard {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: var(--sp-3, 12px);
  align-items: start;
  padding: var(--sp-4, 16px);
  background: var(--surface-elevated, var(--bg-elevated));
  border: 1px solid var(--hairline, var(--rule));
  border-radius: var(--r-7, var(--r-3));
  list-style: none;
}
.pcard--degraded { border-style: dashed; border-color: var(--hairline-strong, var(--hairline)); }
.pcard--selected { outline: 2px solid var(--text-primary, currentColor); outline-offset: -2px; }
.pcard__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1px solid var(--hairline, var(--rule));
  font-weight: 600;
  color: var(--text-secondary, var(--fg-muted));
}
.pcard__open {
  all: unset;
  display: flex;
  flex-direction: column;
  cursor: pointer;
  border-radius: var(--r-3, 4px);
}
.pcard__open:focus-visible, .pcard__select:focus-visible { outline: 2px solid var(--text-primary, currentColor); outline-offset: 2px; }
.pcard__name { font-weight: 600; }
.pcard__username, .pcard__meta, .pcard__note, .pcard__issues { color: var(--text-secondary, var(--fg-muted)); font-size: var(--fs-caption-1, 12px); margin: 0; }
.pcard__tags { margin: var(--sp-2, 8px) 0 0; }
.pcard__issues { padding-left: 1em; margin-top: var(--sp-2, 8px); }
.pcard__sev { font-weight: 600; }
</style>
