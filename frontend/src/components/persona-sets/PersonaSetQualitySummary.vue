<script setup lang="ts">
/** Qualitätszusammenfassung (#1807, E7-F2): Lade-, Fehler- und Ergebniszustand. */
import { useI18n } from 'vue-i18n'
import type { PersonaSetQualityReport } from '@/contracts/personaSetContract'
import { PersonaSetDetailTestId as Id } from './detailTestIds'

defineProps<{ report: PersonaSetQualityReport | null; loading: boolean; error: string | null }>()
const emit = defineEmits<{ (e: 'retry'): void }>()
const { t } = useI18n()
</script>

<template>
  <section class="pqual" :aria-label="t('views.personaSets.detail.quality.label')" :data-testid="Id.qualityBox">
    <p v-if="loading" role="status" aria-busy="true" :data-testid="Id.qualityLoading">
      {{ t('views.personaSets.detail.quality.loading') }}
    </p>
    <div v-else-if="error" role="alert" :data-testid="Id.qualityError">
      <p>{{ t('views.personaSets.detail.quality.error') }} {{ error }}</p>
      <button type="button" :data-testid="Id.qualityRetry" @click="emit('retry')">{{ t('views.personaSets.retry') }}</button>
    </div>
    <template v-else-if="report">
      <p>
        {{
          t('views.personaSets.detail.quality.summary', {
            roles: report.summary.distinct_roles.length,
            mbti: report.summary.distinct_mbti.length,
            total: report.summary.total,
          })
        }}
      </p>
      <ul v-if="report.global_issues.length > 0">
        <li v-for="(issue, i) in report.global_issues" :key="`${issue.code}-${i}`">
          <strong>{{ t(`views.personaSets.detail.quality.severity.${issue.severity}`) }}</strong> {{ issue.code }}
        </li>
      </ul>
      <p v-else>{{ t('views.personaSets.detail.quality.noGlobalIssues') }}</p>
    </template>
  </section>
</template>

<style scoped>
.pqual {
  padding: var(--sp-4, 16px);
  margin-bottom: var(--sp-4, 16px);
  border: 1px solid var(--hairline, var(--rule));
  border-radius: var(--r-7, var(--r-3));
}
</style>
