<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { entryTarget, type RunEntry } from '@/composables/library/runState'
import RunStateMark from './RunStateMark.vue'

/** Band „Im Blick“: laufende Laeufe und Laeufe, die Aufmerksamkeit brauchen. Nur sichtbar, wenn es welche gibt. */
defineProps<{ running: RunEntry[]; attention: RunEntry[] }>()
const { t } = useI18n()
</script>

<template>
  <section class="band" :aria-label="t('views.library.runs.band.title')" data-testid="runs-band">
    <h2 class="band__title">{{ t('views.library.runs.band.title') }}</h2>

    <ul v-if="running.length" class="band__group" :aria-label="t('views.library.runs.band.running')">
      <li v-for="e in running" :key="e.lauf.id" class="band__item">
        <component :is="entryTarget(e) ? RouterLink : 'span'" :to="entryTarget(e) ?? undefined" class="band__chip">
          <RunStateMark :state="e.state" />
          <span class="band__name">{{ e.title }}</span>
          <span v-if="typeof e.lauf.progress === 'number'" class="band__progress">
            {{ t('views.library.runs.tile.progress', { n: e.lauf.progress }) }}
          </span>
        </component>
      </li>
    </ul>

    <div v-if="attention.length" class="band__attention">
      <span class="band__label">{{ t('views.library.runs.band.attention') }}</span>
      <ul class="band__group" :aria-label="t('views.library.runs.band.attention')">
        <li v-for="e in attention" :key="e.lauf.id" class="band__item">
          <component :is="entryTarget(e) ? RouterLink : 'span'" :to="entryTarget(e) ?? undefined" class="band__chip">
            <RunStateMark :state="e.state" />
            <span class="band__name">{{ e.title }}</span>
          </component>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.band {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 20px;
  padding: 8px 10px 8px 16px;
  border-radius: 12px;
  background: var(--s1);
}
.band__title {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg2);
}
.band__group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.band__attention {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.band__label {
  font-size: 13px;
  color: var(--fg2);
}
.band__chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 34px;
  padding: 0 10px 0 6px;
  border-radius: 999px;
  background: var(--s2);
  color: var(--fg);
  font-size: 12.5px;
  text-decoration: none;
}
a.band__chip:hover {
  background: var(--s3);
}
a.band__chip:focus-visible {
  outline: 2px solid var(--acc-text);
  outline-offset: 2px;
}
.band__name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.band__progress {
  color: var(--fg2);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
