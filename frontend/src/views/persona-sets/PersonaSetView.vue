<script setup lang="ts">
/**
 * Personasatz-Detail (#1807, Etappe 7, Skelett): Überschrift, Lade-, Fehler- und
 * Sperrzustand. Die Eintragsliste baut ein Folgeticket auf `usePersonaSet`.
 */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import { usePersonaSet } from '@/composables/personaSets/usePersonaSet'
import { PersonaSetTestId } from '@/contracts/testIds'

const props = defineProps<{ setId: string }>()
const { t } = useI18n()
const { record, loading, error, isLocked, entries, load } = usePersonaSet(() => props.setId)

onMounted(() => void load())
</script>

<template>
  <div :data-testid="PersonaSetTestId.detailRoot">
    <PageHeader :title="record?.name ?? t('views.personaSets.detail.title')" />

    <p v-if="loading" role="status" aria-busy="true" :data-testid="PersonaSetTestId.loading">
      {{ t('views.personaSets.loading') }}
    </p>

    <div v-else-if="error" role="alert" :data-testid="PersonaSetTestId.error">
      <p>{{ error }}</p>
      <button type="button" @click="load">{{ t('views.personaSets.retry') }}</button>
    </div>

    <template v-else-if="record">
      <p v-if="isLocked" role="status" :data-testid="PersonaSetTestId.locked">
        {{ t('views.personaSets.detail.locked') }}
      </p>
      <p v-if="entries.length === 0" :data-testid="PersonaSetTestId.empty">
        {{ t('views.personaSets.detail.empty') }}
      </p>
    </template>
  </div>
</template>
