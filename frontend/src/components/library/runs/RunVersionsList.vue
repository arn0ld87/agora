<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { formatShelfDate } from '@/composables/useShelf'
import type { VersionsState } from '@/composables/library/useLibraryRuns'
import RunStateMark from './RunStateMark.vue'

/**
 * Liste aller Fassungen eines Laufs (Datum, Zustand). Jede Zeile fuehrt auf die
 * alte Berichtsansicht (`StepReport`); der Bericht traegt kein Modell, deshalb
 * gibt es keine Modellspalte.
 */
defineProps<{ id: string; state: VersionsState }>()
const { t, locale } = useI18n()
</script>

<template>
  <div :id="id" class="versions" role="region" :aria-label="t('views.library.runs.versions.listLabel')" data-testid="run-versions">
    <p v-if="state.loading" class="versions__note" aria-busy="true">{{ t('views.library.runs.versions.loading') }}</p>
    <p v-else-if="state.error" class="versions__note versions__note--err" role="alert">
      {{ t('views.library.runs.versions.error') }}
    </p>
    <template v-else>
      <p v-if="state.versions.length === 0" class="versions__note">{{ t('views.library.runs.versions.empty') }}</p>
      <ul v-else class="versions__list">
        <li v-for="v in state.versions" :key="v.reportId" class="versions__row">
          <RouterLink :to="{ name: 'StepReport', params: { reportId: v.reportId } }" class="versions__link">
            <span class="versions__name">{{ t('views.library.runs.versions.row', { n: v.number }) }}</span>
            <span class="versions__date">{{ formatShelfDate(v.createdAt, locale, t) }}</span>
            <RunStateMark :state="v.state" />
          </RouterLink>
        </li>
      </ul>
      <p v-if="state.invalid > 0" class="versions__note versions__note--warn" role="status">
        {{ t('views.library.runs.versions.invalid', { n: state.invalid }, state.invalid) }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.versions {
  position: relative;
  z-index: 2;
  margin-top: 4px;
  padding: 8px;
  border-radius: 8px;
  background: var(--s1);
}
.versions__list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.versions__link {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 8px;
  border-radius: 6px;
  color: var(--fg);
  text-decoration: none;
  font-size: 13px;
}
.versions__link:hover {
  background: var(--s3);
}
.versions__link:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 1px;
}
.versions__name {
  font-weight: 600;
}
.versions__date {
  flex: 1;
  color: var(--fg2);
  font-variant-numeric: tabular-nums;
}
.versions__note {
  margin: 0;
  font-size: 12.5px;
  color: var(--fg2);
}
.versions__note--err {
  color: var(--fg);
  font-weight: 600;
}
.versions__note--warn {
  margin-top: 6px;
  color: var(--fg);
}
</style>
