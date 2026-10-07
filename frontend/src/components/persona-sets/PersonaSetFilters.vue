<script setup lang="ts">
/** Filterleiste (#1807, E7-F2): Herkunft, Art, Rolle, Textsuche, Zähler „x von y“. */
import { useI18n } from 'vue-i18n'
import type { PersonaOrigin } from '@/contracts/personaSetContract'
import { ALL } from '@/composables/personaSets/usePersonaSetFilters'
import { PersonaSetDetailTestId as Id } from './detailTestIds'

defineProps<{
  originOptions: readonly PersonaOrigin[]
  kindOptions: readonly string[]
  roleOptions: readonly string[]
  shown: number
  total: number
  isFiltered: boolean
}>()
const origin = defineModel<string>('origin', { required: true })
const kind = defineModel<string>('kind', { required: true })
const role = defineModel<string>('role', { required: true })
const query = defineModel<string>('query', { required: true })
const emit = defineEmits<{ (e: 'reset'): void }>()
const { t } = useI18n()
</script>

<template>
  <div class="pfilters" role="search" :aria-label="t('views.personaSets.detail.filter.label')">
    <label>
      {{ t('views.personaSets.detail.filter.search') }}
      <input v-model="query" type="search" :data-testid="Id.filterSearch" />
    </label>
    <label>
      {{ t('views.personaSets.detail.filter.origin') }}
      <select v-model="origin" :data-testid="Id.filterOrigin">
        <option :value="ALL">{{ t('views.personaSets.detail.filter.all') }}</option>
        <option v-for="o in originOptions" :key="o" :value="o">{{ t(`views.personaSets.detail.origin.${o}`) }}</option>
      </select>
    </label>
    <label>
      {{ t('views.personaSets.detail.filter.kind') }}
      <select v-model="kind" :data-testid="Id.filterKind">
        <option :value="ALL">{{ t('views.personaSets.detail.filter.all') }}</option>
        <option v-for="k in kindOptions" :key="k" :value="k">{{ t(`views.personaSets.detail.kind.${k}`) }}</option>
      </select>
    </label>
    <label>
      {{ t('views.personaSets.detail.filter.role') }}
      <select v-model="role" :data-testid="Id.filterRole">
        <option :value="ALL">{{ t('views.personaSets.detail.filter.all') }}</option>
        <option v-for="r in roleOptions" :key="r" :value="r">{{ r }}</option>
      </select>
    </label>
    <button v-if="isFiltered" type="button" :data-testid="Id.filterReset" @click="emit('reset')">
      {{ t('views.personaSets.detail.filter.reset') }}
    </button>
    <span class="pfilters__count" :data-testid="Id.filterCount">
      {{ t('views.personaSets.detail.filter.count', { shown, total }) }}
    </span>
  </div>
</template>

<style scoped>
.pfilters { display: flex; flex-wrap: wrap; gap: var(--sp-3, 12px); align-items: end; margin-bottom: var(--sp-4, 16px); }
.pfilters label { display: flex; flex-direction: column; gap: var(--sp-1, 4px); font-size: var(--fs-caption-1, 12px); }
.pfilters__count { color: var(--text-secondary, var(--fg-muted)); }
</style>
