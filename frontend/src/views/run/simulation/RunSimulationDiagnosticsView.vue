<script setup lang="ts">
/**
 * Diagnose der Simulation (Etappe 4, #1801, Bauplan 4.5/4.9): dieselbe
 * Protokoll-Komponente wie die Konsole, auf diesen Lauf beschränkt und
 * vorgefiltert auf Tool-Calls, Fehler und Fortschritt (Balken verdichtet),
 * dazu das Konsolenprotokoll des Simulationsprozesses als zweite Quelle.
 * Das Protokoll ist Betreiber-Zustand: ohne Zugang steht hier ein Hinweis.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import LogStream from '@/components/activity/LogStream.vue'
import DiagnosticsProcessLog from '@/components/run/simulation/DiagnosticsProcessLog.vue'
import { useLogStreamPageClaim } from '@/composables/useLogDrawer'
import { useOperatorAccess } from '@/composables/useOperatorAccess'
import type { LogKindFilter } from '@/composables/activity/logKinds'

const props = defineProps<{ simulationId: string }>()
const { t } = useI18n()

const available = useOperatorAccess()
// Die Seite hält den Protokollstrom allein, die Konsole bleibt ausgeblendet.
useLogStreamPageClaim()

const kindFilter = computed<LogKindFilter>(() => ({
  kinds: ['error', 'toolCall', 'progress'],
  toggleLabel: t('views.run.simDiagnostics.showAll'),
  collapsedLabel: (count: number) => t('views.run.simDiagnostics.collapsed', { count }),
}))
</script>

<template>
  <section class="rsd" data-testid="run-sim-diagnostics">
    <h2 class="rsd__title">{{ t('views.run.simDiagnostics.title') }}</h2>
    <p v-if="!available" class="rsd__notice" role="status" data-testid="diagnostics-no-access">
      {{ t('views.run.simDiagnostics.noAccess') }}
    </p>
    <template v-else>
      <p class="rsd__note">{{ t('views.run.simDiagnostics.serverNote') }}</p>
      <div class="rsd__card">
        <LogStream
          :title="t('views.run.simDiagnostics.serverTitle')"
          :scope-id="props.simulationId"
          :kind-filter="kindFilter"
        />
      </div>
    </template>
    <DiagnosticsProcessLog :simulation-id="props.simulationId" />
  </section>
</template>

<style scoped>
.rsd { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.rsd__title { margin: 0; font-size: 16px; font-weight: 650; color: var(--fg); }
.rsd__note { margin: 0; font-size: 12px; color: var(--fg3); }
.rsd__notice { margin: 0; padding: 10px 12px; border-radius: var(--ag-r-8); background: var(--s2); color: var(--fg2); font-size: 13px; }
.rsd__card {
  display: flex; flex-direction: column; height: 420px;
  background: var(--s2); border-radius: var(--ag-r-12); overflow: hidden;
}
</style>
