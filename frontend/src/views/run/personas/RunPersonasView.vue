<script setup lang="ts">
/**
 * Reiter „Personas“ am Lauf (#1807, Etappe 7, Skelett): Überschrift und
 * ehrlicher Leerzustand. Der Reiter in `runTabs.ts` bleibt bis zu den
 * Folgetickets unverändert; diese Route ist nur die künftige Zieladresse.
 */
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePersonaSets } from '@/composables/personaSets/usePersonaSets'
import { PersonaSetTestId } from '@/contracts/testIds'

defineProps<{ simulationId: string }>()
const { t } = useI18n()
const { loading, error, reload } = usePersonaSets()

onMounted(() => void reload())
</script>

<template>
  <section :data-testid="PersonaSetTestId.runRoot" :aria-labelledby="'run-personas-title'">
    <h2 id="run-personas-title">{{ t('views.personaSets.run.title') }}</h2>

    <p v-if="loading" role="status" aria-busy="true" :data-testid="PersonaSetTestId.loading">
      {{ t('views.personaSets.loading') }}
    </p>
    <div v-else-if="error" role="alert" :data-testid="PersonaSetTestId.error">
      <p>{{ error }}</p>
      <button type="button" @click="reload">{{ t('views.personaSets.retry') }}</button>
    </div>
    <p v-else :data-testid="PersonaSetTestId.empty">{{ t('views.personaSets.run.empty') }}</p>
  </section>
</template>
