<script setup lang="ts">
/**
 * Bibliothek → Personasätze (#1807, Etappe 7, Skelett): Überschrift und
 * ehrlicher Leerzustand. Die Kacheln bauen Folgetickets auf `usePersonaSets`.
 */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import { usePersonaSets } from '@/composables/personaSets/usePersonaSets'
import { PersonaSetTestId } from '@/contracts/testIds'

const { t } = useI18n()
const { loading, error, isEmpty, reload } = usePersonaSets()

onMounted(() => void reload())
</script>

<template>
  <div :data-testid="PersonaSetTestId.libraryRoot">
    <PageHeader :title="t('views.personaSets.title')" />

    <p v-if="loading" role="status" aria-busy="true" :data-testid="PersonaSetTestId.loading">
      {{ t('views.personaSets.loading') }}
    </p>

    <div v-else-if="error" role="alert" :data-testid="PersonaSetTestId.error">
      <p>{{ t('views.personaSets.errorTitle') }}</p>
      <p>{{ error }}</p>
      <button type="button" @click="reload">{{ t('views.personaSets.retry') }}</button>
    </div>

    <p v-else-if="isEmpty" :data-testid="PersonaSetTestId.empty">
      {{ t('views.personaSets.library.empty') }}
    </p>
  </div>
</template>
