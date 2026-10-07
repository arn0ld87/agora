<script setup lang="ts">
/**
 * Linke Spalte der Feed-Oberfläche (#1801): Netzwerk-Umschalter, Filter
 * (Persona, Runde, Textsuche) und die Streitfrage des Laufs als Text. Es gibt
 * keinen Filter „Streitfrage": Beiträge tragen dafür kein Feld.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FeedNetwork } from '@/composables/run/simulation/threads'

const props = defineProps<{
  network: FeedNetwork
  persona: string
  /** Genau eine Runde oder `null`. */
  round: number | null
  query: string
  personaOptions: { id: string; name: string }[]
  roundOptions: number[]
  contestedQuestion: string | null
}>()
const emit = defineEmits<{
  'update:network': [network: FeedNetwork]
  'update:persona': [id: string]
  'update:round': [round: number | null]
  'update:query': [q: string]
  reset: []
}>()
const { t } = useI18n()

const NETWORKS: FeedNetwork[] = ['twitter', 'reddit']
const dirty = computed(() => props.persona !== '' || props.round !== null || props.query !== '')

function onRound(event: Event): void {
  const raw = (event.target as HTMLSelectElement).value
  emit('update:round', raw === '' ? null : Number(raw))
}
</script>

<template>
  <div class="side" data-testid="feed-sidebar">
    <div class="side__group" role="group" :aria-label="t('views.run.simFeed.network.label')">
      <button
        v-for="n in NETWORKS"
        :key="n"
        type="button"
        class="side__net"
        :aria-pressed="network === n"
        :data-testid="`feed-network-${n}`"
        @click="emit('update:network', n)"
      >
        {{ t(`views.run.simFeed.network.${n}`) }}
      </button>
    </div>

    <section class="side__filters" :aria-label="t('views.run.simFeed.filters.title')">
      <label class="side__field">
        <span>{{ t('views.run.simFeed.filters.persona') }}</span>
        <select
          :value="persona"
          data-testid="feed-filter-persona"
          @change="emit('update:persona', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">{{ t('views.run.simFeed.filters.personaAll') }}</option>
          <option v-for="p in personaOptions" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
      </label>
      <label class="side__field">
        <span>{{ t('views.run.simFeed.filters.round') }}</span>
        <select :value="round ?? ''" data-testid="feed-filter-round" @change="onRound">
          <option value="">{{ t('views.run.simFeed.filters.roundAll') }}</option>
          <option v-for="r in roundOptions" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
      <label class="side__field">
        <span>{{ t('views.run.simFeed.filters.search') }}</span>
        <input
          type="search"
          :value="query"
          :placeholder="t('views.run.simFeed.filters.searchPlaceholder')"
          data-testid="feed-filter-query"
          @input="emit('update:query', ($event.target as HTMLInputElement).value)"
        />
      </label>
      <button v-if="dirty" type="button" class="side__reset" data-testid="feed-filter-reset" @click="emit('reset')">
        {{ t('views.run.simFeed.filters.reset') }}
      </button>
    </section>

    <section class="side__question" :aria-label="t('views.run.simFeed.filters.contested')" data-testid="feed-contested">
      <h3 class="side__heading">{{ t('views.run.simFeed.filters.contested') }}</h3>
      <p v-if="contestedQuestion" class="side__text">{{ contestedQuestion }}</p>
      <p v-else class="side__text side__text--muted">{{ t('views.run.simFeed.filters.contestedNone') }}</p>
    </section>
  </div>
</template>

<style scoped>
.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--fg);
}
.side__group {
  display: flex;
  gap: 4px;
}
.side__net {
  flex: 1;
  height: 30px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg2);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.side__net[aria-pressed='true'] {
  border-color: var(--acc);
  background: var(--acc);
  color: var(--on-acc);
}
.side__filters {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.side__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.side__field select,
.side__field input {
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s2);
  color: var(--fg);
  font: inherit;
  font-size: 13px;
}
.side__net:focus-visible,
.side__field select:focus-visible,
.side__field input:focus-visible,
.side__reset:focus-visible {
  outline: 2px solid var(--acc-line);
  outline-offset: 2px;
}
.side__reset {
  align-self: flex-start;
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  background: var(--s3);
  color: var(--fg2);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.side__heading {
  margin: 0 0 4px;
  color: var(--fg3);
  font-size: 12px;
  font-weight: 600;
}
.side__text {
  margin: 0;
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.side__text--muted {
  color: var(--fg2);
}
</style>
