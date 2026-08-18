<!--
  CompareView — v4-Shell-Wrapper fuer BranchComparePanel.
  Slice I: nur Wrapper; Inhalts-Refactor von BranchComparePanel in spaeterem Slice.

  Route: /v4/compare/:simulationId
  Laedt availableBranches via listSimulationBranches, reicht beides als Props weiter.
-->
<template>
  <AppShell :breadcrumbs="crumbs">
    <PageHeader :title="$t('views.compare.title')" />

    <div v-if="loadError" class="compare-view-error" role="alert">
      {{ loadError }}
    </div>
    <div v-else-if="loading" class="compare-view-loading" aria-busy="true">
      Lade Branches…
    </div>
    <BranchComparePanel
      v-else
      :simulation-id="simulationId"
      :available-branches="branches"
    />
  </AppShell>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import AppShell from '@/components/v4/shell/AppShell.vue'
import PageHeader from '@/components/v4/shell/PageHeader.vue'
import BranchComparePanel from '@/components/compare/BranchComparePanel.vue'
import { listSimulationBranches } from '@/api/simulation'
import type { BreadcrumbItem } from '@/components/v4/shell/Breadcrumbs.vue'

const props = defineProps<{ simulationId: string }>()

const crumbs: BreadcrumbItem[] = [{ label: 'Compare' }]

interface BranchEntry {
  id: string
  label: string
  completed_at?: string
}

const branches = ref<BranchEntry[]>([])
const loading = ref(true)
const loadError = ref<string | null>(null)

onMounted(async () => {
  try {
    const raw = await listSimulationBranches(props.simulationId)
    branches.value = raw.map((b) => {
      const completedAt = typeof b['completed_at'] === 'string' ? b['completed_at'] : undefined
      return {
        id: b.branch_id,
        label: b.branch_name || b.branch_id,
        completed_at: completedAt,
      }
    })
  } catch (err) {
    loadError.value = err instanceof Error ? err.message : 'Fehler beim Laden der Branches.'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.compare-view-error {
  padding: 16px;
  color: var(--status-red);
  background: var(--status-red-bg);
  border-radius: 8px;
}

.compare-view-loading {
  padding: 16px;
  color: var(--text-secondary);
  font-size: 14px;
}
</style>
