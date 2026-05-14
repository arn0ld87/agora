<script setup lang="ts">
/**
 * DashboardView — Operator-Workbench (Slice F+, Design-v4, 2026-05-14).
 *
 * Ersetzt den Slice-F-Stub. Hängt useRunsPolling + useSystemStatus an,
 * leitet Stats lokal ab und propagiert nach unten in die Sub-Components.
 */
import { computed, onMounted, onUnmounted } from 'vue'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import HeroNewRun from '@/components/v4/dashboard/HeroNewRun.vue'
import StatsRow from '@/components/v4/dashboard/StatsRow.vue'
import ActiveRunsCard from '@/components/v4/dashboard/ActiveRunsCard.vue'
import SystemHealthCard from '@/components/v4/dashboard/SystemHealthCard.vue'
import RecentReportsCard from '@/components/v4/dashboard/RecentReportsCard.vue'
import QuickActionsRow from '@/components/v4/dashboard/QuickActionsRow.vue'
import { useRunsPolling } from '@/composables/useRunsPolling'
import { useSystemStatus } from '@/composables/useSystemStatus'
import type { RunDetail } from '@/contracts/runsContract'

const BREADCRUMBS = [{ label: 'Dashboard' }]

const {
  runs,
  loading: runsLoading,
  error: runsError,
  start: runsStart,
  stop: runsStop,
  refresh: runsRefresh,
} = useRunsPolling(5000)

const {
  status: sysStatus,
  loading: sysLoading,
  error: sysError,
  start: sysStart,
  stop: sysStop,
  refresh: sysRefresh,
} = useSystemStatus(15000)

onMounted(() => {
  void runsStart()
  void sysStart()
})

onUnmounted(() => {
  runsStop()
  sysStop()
})

const ACTIVE = ['pending', 'processing', 'paused']

function isCompletedToday(r: RunDetail): boolean {
  if (r.status !== 'completed') return false
  const completedAt = r.completed_at ?? r.updated_at
  if (!completedAt) return false
  const ts = Date.parse(completedAt)
  if (Number.isNaN(ts)) return false
  const today0 = new Date()
  today0.setHours(0, 0, 0, 0)
  return ts >= today0.getTime()
}

const activeRunsCount = computed(() =>
  runs.value.filter(r => ACTIVE.includes(r.status)).length,
)

const completedTodayCount = computed(() =>
  runs.value.filter(isCompletedToday).length,
)

const avgConfidence = computed<number | null>(() => {
  const samples: number[] = []
  for (const r of runs.value) {
    if (r.run_type !== 'report_generate') continue
    if (r.status !== 'completed') continue
    const meta = r.metadata as Record<string, unknown>
    const cand = meta?.['confidence_score'] ?? meta?.['confidence']
    if (typeof cand === 'number' && Number.isFinite(cand)) samples.push(cand)
  }
  if (samples.length === 0) return null
  return samples.reduce((a, b) => a + b, 0) / samples.length
})

const personasInFlight = computed(() => {
  let total = 0
  for (const r of runs.value) {
    if (!ACTIVE.includes(r.status)) continue
    const n = r.summary?.persona_count
    if (typeof n === 'number' && Number.isFinite(n)) total += n
  }
  return total
})
</script>

<template>
  <AppShell :breadcrumbs="BREADCRUMBS">
    <PageHeader
      :title="$t('dashboard.title')"
      :subtitle="$t('dashboard.subtitle')"
    />

    <div class="dash-stack">
      <HeroNewRun />

      <StatsRow
        :active-runs="activeRunsCount"
        :completed-today="completedTodayCount"
        :avg-confidence="avgConfidence"
        :personas="personasInFlight"
      />

      <div class="dash-grid">
        <ActiveRunsCard
          :runs="runs"
          :loading="runsLoading"
          :error="runsError"
          @refresh="() => void runsRefresh()"
        />
        <SystemHealthCard
          :status="sysStatus"
          :loading="sysLoading"
          :error="sysError"
          @refresh="() => void sysRefresh()"
        />
      </div>

      <RecentReportsCard />

      <QuickActionsRow />
    </div>
  </AppShell>
</template>

<style scoped>
.dash-stack {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 1280px;
}

.dash-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

@media (max-width: 1080px) {
  .dash-grid {
    grid-template-columns: 1fr;
  }
}
</style>
