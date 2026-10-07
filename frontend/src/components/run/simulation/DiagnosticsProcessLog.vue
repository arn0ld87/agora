<script setup lang="ts">
/**
 * Konsolenprotokoll des Simulationsprozesses (OASIS-Subprozess) dieses Laufs
 * als zweite Quelle der Diagnose: `GET /api/simulation/<id>/console-log`,
 * inkrementell gepollt. Gleiche Zeilenarten, Verdichtung und Fehlererkennung
 * wie das Server-Protokoll.
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { z } from 'zod'
import { getSimulationConsoleLog } from '@/api/simulation'
import { useIncrementalLogPolling } from '@/composables/useIncrementalLogPolling'
import { readEnvelope, describeError } from '@/composables/run/simulation/simulationEnvelope'
import { classifyLogLine, collapseProgress, type LogLineKind } from '@/composables/activity/logKinds'
import { isErrorLine } from '@/utils/errorLinePattern'

const props = defineProps<{ simulationId: string }>()
const { t } = useI18n()

const KINDS: readonly LogLineKind[] = ['error', 'toolCall', 'progress']
const ConsolePageSchema = z
  .object({
    lines: z.array(z.string()).default(() => []),
    from_line: z.number().optional(),
    total_lines: z.number().optional(),
    next_line: z.number().optional(),
  })
  .passthrough()

const error = ref<string | null>(null)
const showEverything = ref(false)

const { lines, polling } = useIncrementalLogPolling<string>({
  intervalMs: 2000,
  fetcher: async (since) => {
    try {
      const data = readEnvelope(await getSimulationConsoleLog(props.simulationId, since), ConsolePageSchema, 'GET /api/simulation/<id>/console-log')
      error.value = null
      return { success: true, data }
    } catch (err) {
      error.value = describeError(err)
      return null
    }
  },
})

onMounted(() => void polling.start({ immediate: true }))

const shown = computed<string[]>(() => {
  if (showEverything.value) return lines.value
  return collapseProgress(lines.value)
    .map((c) => (c.count > 1 ? `${c.line}  ${t('views.run.simDiagnostics.collapsed', { count: c.count })}` : c.line))
    .filter((ln) => KINDS.includes(classifyLogLine(ln)))
})

function retry(): void {
  void polling.tick()
}
</script>

<template>
  <section class="dpl" :aria-labelledby="`dpl-title-${simulationId}`" data-testid="diagnostics-process-log">
    <header class="dpl__head">
      <h3 :id="`dpl-title-${simulationId}`" class="dpl__title">{{ t('views.run.simDiagnostics.processTitle') }}</h3>
      <label class="dpl__toggle">
        <input v-model="showEverything" type="checkbox" data-testid="process-show-all" />
        {{ t('views.run.simDiagnostics.showAll') }}
      </label>
    </header>
    <p class="dpl__note">{{ t('views.run.simDiagnostics.processNote') }}</p>
    <div v-if="error" class="dpl__error" role="alert" data-testid="process-error">
      <span>{{ t('views.run.simDiagnostics.processError', { reason: error }) }}</span>
      <button type="button" class="dpl__btn" @click="retry">{{ t('views.run.simDiagnostics.retry') }}</button>
    </div>
    <div class="dpl__body" role="log" tabindex="0" :aria-label="t('views.run.simDiagnostics.processTitle')">
      <p v-if="lines.length === 0" class="dpl__meta" data-testid="process-empty">{{ t('views.run.simDiagnostics.processEmpty') }}</p>
      <p v-else-if="shown.length === 0" class="dpl__meta" data-testid="process-filtered">{{ t('views.run.simDiagnostics.processFiltered') }}</p>
      <div v-for="(line, i) in shown" :key="i" class="dpl__line" :class="{ 'is-error': isErrorLine(line) }">{{ line }}</div>
    </div>
  </section>
</template>

<style scoped>
.dpl { display: flex; flex-direction: column; gap: 6px; background: var(--s2); border-radius: var(--ag-r-12); padding: 10px 0; }
.dpl__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 0 16px; }
.dpl__title { margin: 0; font-size: 14px; font-weight: 600; color: var(--fg); }
.dpl__toggle { display: inline-flex; gap: 6px; align-items: center; font-size: 13px; color: var(--fg3); cursor: pointer; }
.dpl__note { margin: 0; padding: 0 16px; font-size: 12px; color: var(--fg3); }
.dpl__error {
  display: flex; align-items: center; gap: 12px; margin: 0 16px; padding: 8px 10px;
  border-radius: var(--ag-r-8); background: var(--err-soft); color: var(--err); font-size: 13px;
}
.dpl__btn {
  height: 28px; padding: 0 10px; border: 1px solid currentColor; border-radius: var(--ag-r-6);
  background: transparent; color: inherit; font: inherit; font-size: 12px; cursor: pointer;
}
.dpl__btn:focus-visible, .dpl__body:focus-visible { outline: 2px solid var(--acc-text); outline-offset: -2px; }
.dpl__body {
  max-height: 320px; overflow-y: auto; padding: 4px 16px 8px;
  font-family: var(--ag-font-mono); font-size: 12px; line-height: 1.5; color: var(--fg);
  white-space: pre-wrap; overflow-wrap: anywhere;
}
.dpl__line { padding: 3px 0; border-top: 1px solid var(--line); }
.dpl__line:first-child { border-top: none; }
.dpl__line.is-error { color: var(--err); }
.dpl__meta { margin: 0; padding: 8px 0; color: var(--fg3); font-family: var(--ag-font-sans); font-size: 13px; }
</style>
