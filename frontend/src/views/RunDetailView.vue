<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getRun } from '../api/runs'
import { ApiError } from '../api/envelope'
import { RunDetailSchema } from '../contracts/runsContract'
import type { RunDetail } from '../contracts/runsContract'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const runId = String(route.params.id)

const run = ref<RunDetail | null>(null)
const loading = ref(false)
const error = ref('')

async function loadRun(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const envelope = await getRun(runId)
    const payload = (envelope as { data?: unknown }).data
    const parsed = RunDetailSchema.safeParse(payload)
    if (!parsed.success) {
      error.value = `Schema-Drift: ${parsed.error.issues[0]?.message ?? 'unbekannt'}`
      return
    }
    run.value = parsed.data
  } catch (e) {
    if (e instanceof ApiError) {
      error.value = e.message
    } else {
      error.value = e instanceof Error ? e.message : 'Netzwerkfehler'
    }
  } finally {
    loading.value = false
  }
}

function goBack(): void {
  void router.push({ name: 'Runs' })
}

onMounted(() => void loadRun())
</script>

<template>
  <div class="run-detail">
    <header class="detail-header">
      <button type="button" class="back-btn" @click="goBack">
        {{ t('runs.dashboard.back_to_dashboard') }}
      </button>
      <h1 class="detail-title">Run: {{ runId }}</h1>
    </header>

    <!-- Loading -->
    <div v-if="loading && !run" class="state-msg" aria-live="polite">
      {{ t('runs.dashboard.loading') }}
    </div>

    <!-- Error -->
    <div v-else-if="error" class="error-banner" role="alert">
      {{ t('runs.dashboard.error', { message: error }) }}
    </div>

    <!-- Detail content -->
    <template v-else-if="run">
      <section class="detail-section">
        <dl class="detail-grid">
          <dt>{{ t('runs.dashboard.columns.status') }}</dt>
          <dd>
            <span class="status-badge" :class="`status-badge--${run.status}`">
              {{ run.status }}
            </span>
          </dd>

          <dt>{{ t('runs.dashboard.columns.type') }}</dt>
          <dd>{{ run.run_type }}</dd>

          <dt>{{ t('runs.dashboard.columns.entity') }}</dt>
          <dd>{{ run.summary?.document_name ?? run.entity_id }}</dd>

          <dt>{{ t('runs.dashboard.columns.progress') }}</dt>
          <dd>{{ run.progress }}%</dd>

          <dt>{{ t('runs.dashboard.columns.started') }}</dt>
          <dd>{{ run.started_at }}</dd>

          <template v-if="run.completed_at">
            <dt>Abgeschlossen</dt>
            <dd>{{ run.completed_at }}</dd>
          </template>

          <template v-if="run.message">
            <dt>Meldung</dt>
            <dd>{{ run.message }}</dd>
          </template>

          <template v-if="run.error">
            <dt>Fehler</dt>
            <dd class="detail-error">{{ run.error }}</dd>
          </template>

          <template v-if="run.branch_label">
            <dt>Branch</dt>
            <dd>{{ run.branch_label }}</dd>
          </template>
        </dl>
      </section>

      <!-- Linked IDs -->
      <section
        v-if="Object.keys(run.linked_ids).length > 0"
        class="detail-section"
      >
        <h2 class="section-title">Verknüpfte IDs</h2>
        <dl class="detail-grid">
          <template v-for="(val, key) in run.linked_ids" :key="String(key)">
            <dt>{{ String(key) }}</dt>
            <dd>{{ String(val) }}</dd>
          </template>
        </dl>
      </section>

      <!-- Artifacts -->
      <section
        v-if="Object.keys(run.artifacts).length > 0"
        class="detail-section"
      >
        <h2 class="section-title">Artefakte</h2>
        <pre class="detail-pre">{{ JSON.stringify(run.artifacts, null, 2) }}</pre>
      </section>
    </template>

    <!-- Refresh button -->
    <div class="detail-actions">
      <button
        type="button"
        class="action-btn"
        :disabled="loading"
        @click="() => void loadRun()"
      >
        {{ t('common.refresh') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.run-detail {
  display: flex;
  flex-direction: column;
  gap: var(--s-5, 1.25rem);
  padding: var(--s-6, 1.5rem) var(--s-7, 2rem);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: var(--s-4, 1rem);
  flex-wrap: wrap;
}

.back-btn {
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
  letter-spacing: var(--ls-mono, 0.06em);
  text-transform: uppercase;
  background: transparent;
  border: 1px solid var(--rule-strong, #ccc);
  color: var(--fg, #111);
  padding: 5px 12px;
  cursor: pointer;
}
.back-btn:hover { background: var(--bg-elevated, #f5f5f5); }

.detail-title {
  font-family: var(--ff-mono, monospace);
  font-size: 14px;
  margin: 0;
  font-weight: 600;
}

.state-msg {
  color: var(--fg-muted, #888);
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
  padding: var(--s-5, 1.25rem);
}

.error-banner {
  padding: var(--s-4, 1rem);
  background: #fee2e2;
  border: 1px solid #f87171;
  color: #7f1d1d;
  font-size: 13px;
}

.detail-section {
  border: 1px solid var(--rule, #ddd);
  padding: var(--s-4, 1rem);
}

.section-title {
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  letter-spacing: var(--ls-mono, 0.06em);
  text-transform: uppercase;
  color: var(--fg-muted, #888);
  margin: 0 0 var(--s-3, 0.75rem);
}

.detail-grid {
  display: grid;
  grid-template-columns: 10rem 1fr;
  gap: 2px var(--s-4, 1rem);
  font-size: 13px;
  margin: 0;
}

.detail-grid dt {
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  color: var(--fg-muted, #888);
  text-transform: uppercase;
  padding: 4px 0;
}

.detail-grid dd {
  margin: 0;
  padding: 4px 0;
  word-break: break-all;
}

.detail-error { color: #991b1b; }

.status-badge {
  display: inline-block;
  font-family: var(--ff-mono, monospace);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 2px;
  text-transform: uppercase;
}
.status-badge--pending,
.status-badge--processing,
.status-badge--paused   { background: #dbeafe; color: #1d4ed8; }
.status-badge--completed { background: #dcfce7; color: #166534; }
.status-badge--failed,
.status-badge--stopped  { background: #fee2e2; color: #991b1b; }

.detail-pre {
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
  background: var(--bg-elevated, #f5f5f5);
  padding: var(--s-3, 0.75rem);
  overflow: auto;
  margin: 0;
}

.detail-actions {
  display: flex;
  gap: var(--s-3, 0.75rem);
}

.action-btn {
  font-family: var(--ff-mono, monospace);
  font-size: 12px;
  letter-spacing: var(--ls-mono, 0.06em);
  text-transform: uppercase;
  background: transparent;
  border: 1px solid var(--rule-strong, #ccc);
  color: var(--fg, #111);
  padding: 6px 14px;
  cursor: pointer;
}
.action-btn:hover { background: var(--bg-elevated, #f5f5f5); }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
