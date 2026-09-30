<script setup lang="ts">
/**
 * SimFilterBar — Filter oberhalb Feed/Diskurs/Runden/Protokoll.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.2. Ersetzt
 * konzeptionell den Kopfbereich von SimulationPulseBar.vue (die
 * Aktivitaetsanzeige lebt jetzt in SimRunHeader).
 *
 * Filter leben in route.query (persistiert ueber Reload) — die aufrufende
 * View haelt den Query-State und uebergibt ihn hier nur als Props/Events.
 * A11y: alle Selects mit Label-Elementen, Freitext hat role="searchbox".
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Platform } from '@/contracts/postEventContract'

export interface SimFilterBarPersona {
  id: string
  name: string
}

const props = withDefaults(
  defineProps<{
    platform: 'all' | Platform
    round: number | null
    persona: string | null
    q: string
    personas: SimFilterBarPersona[]
    rounds: number[]
    scope: 'feed' | 'threads' | 'rounds' | 'actions'
    loading?: boolean
  }>(),
  { loading: false },
)

const emit = defineEmits<{
  'update:platform': [value: 'all' | Platform]
  'update:round': [value: number | null]
  'update:persona': [value: string | null]
  'update:q': [value: string]
}>()

const { t } = useI18n()

const showSearch = computed(() => props.scope === 'feed' || props.scope === 'threads')
const personasEmpty = computed(() => props.personas.length === 0)

function onPlatformChange(event: Event): void {
  emit('update:platform', (event.target as HTMLSelectElement).value as 'all' | Platform)
}
function onRoundChange(event: Event): void {
  const raw = (event.target as HTMLSelectElement).value
  emit('update:round', raw === '' ? null : Number(raw))
}
function onPersonaChange(event: Event): void {
  const raw = (event.target as HTMLSelectElement).value
  emit('update:persona', raw === '' ? null : raw)
}
function onSearchInput(event: Event): void {
  emit('update:q', (event.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="sfb-root">
    <div class="sfb-field">
      <label class="sfb-label" :for="`sfb-platform-${scope}`">{{ t('feed.scope.platform') }}</label>
      <select
        :id="`sfb-platform-${scope}`"
        class="sfb-select"
        :class="{ 'sfb-select--loading': loading }"
        :disabled="loading"
        :value="platform"
        @change="onPlatformChange"
      >
        <option value="all">{{ t('feed.scope.platformAll') }}</option>
        <option value="reddit">{{ t('feed.reddit') }}</option>
        <option value="twitter">{{ t('feed.twitter') }}</option>
      </select>
    </div>

    <div class="sfb-field">
      <label class="sfb-label" :for="`sfb-round-${scope}`">{{ t('feed.scope.round') }}</label>
      <select
        :id="`sfb-round-${scope}`"
        class="sfb-select"
        :class="{ 'sfb-select--loading': loading }"
        :disabled="loading"
        :value="round === null ? '' : String(round)"
        @change="onRoundChange"
      >
        <option value="">{{ t('feed.scope.roundAll') }}</option>
        <option v-for="r in rounds" :key="r" :value="r">{{ r }}</option>
      </select>
    </div>

    <div class="sfb-field">
      <label class="sfb-label" :for="`sfb-persona-${scope}`">{{ t('feed.scope.persona') }}</label>
      <select
        :id="`sfb-persona-${scope}`"
        class="sfb-select"
        :class="{ 'sfb-select--loading': loading }"
        :disabled="loading || personasEmpty"
        :value="persona === null ? '' : persona"
        @change="onPersonaChange"
      >
        <option value="">{{ t('feed.scope.personaAll') }}</option>
        <option v-for="p in personas" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
      <p v-if="personasEmpty && !loading" class="sfb-hint">{{ t('feed.scope.noPersonas') }}</p>
    </div>

    <div v-if="showSearch" class="sfb-field sfb-field--search">
      <label class="sfb-label" :for="`sfb-q-${scope}`">{{ t('feed.scope.search') }}</label>
      <input
        :id="`sfb-q-${scope}`"
        type="search"
        role="searchbox"
        class="sfb-input"
        :aria-label="t('feed.scope.search')"
        :placeholder="t('feed.scope.searchPlaceholder')"
        :value="q"
        @input="onSearchInput"
      />
    </div>
  </div>
</template>

<style scoped>
.sfb-root {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  padding: var(--sim-header-py) var(--sim-header-px);
  border-bottom: 1px solid var(--hairline);
}
.sfb-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 120px;
}
.sfb-field--search {
  flex: 1;
  min-width: 180px;
}
.sfb-label {
  font-size: 11.5px;
  font-weight: 590;
  color: var(--text-secondary);
}
.sfb-select,
.sfb-input {
  height: var(--ctl-h-md, 34px);
  padding: 0 10px;
  background: var(--surface-inset);
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  color: var(--text-primary);
  font-size: var(--sim-time-fs);
}
.sfb-select--loading {
  opacity: 0.5;
}
.sfb-input::placeholder {
  color: var(--text-tertiary);
}
.sfb-hint {
  margin: 0;
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
