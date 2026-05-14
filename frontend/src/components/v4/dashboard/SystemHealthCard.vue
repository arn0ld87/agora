<script setup lang="ts">
/**
 * SystemHealthCard — Health-Row für Ollama / Neo4j / OASIS + Disk-Subtext.
 *
 * Workbench-These: Status nur über Token-Tones, kein Glow. Dot links, Pill rechts,
 * Subtext gedimmt darunter.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Card from '../forms/Card.vue'
import Badge from '../forms/Badge.vue'
import type { SystemStatusResponse } from '../../../contracts/systemStatusContract'

const props = defineProps<{
  status: SystemStatusResponse | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  refresh: []
}>()

const { t } = useI18n()

interface HealthRow {
  key: 'ollama' | 'neo4j' | 'oasis'
  label: string
  tone: 'green' | 'orange' | 'red' | 'gray'
  state: 'reachable' | 'unreachable' | 'idle'
  hint: string
}

function fmtBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '—'
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`
  return `${bytes} B`
}

const rows = computed<HealthRow[]>(() => {
  const s = props.status
  if (!s) {
    return [
      { key: 'ollama', label: t('dashboard.system.ollama'), tone: 'gray', state: 'idle', hint: '' },
      { key: 'neo4j', label: t('dashboard.system.neo4j'), tone: 'gray', state: 'idle', hint: '' },
      { key: 'oasis', label: t('dashboard.system.oasis'), tone: 'gray', state: 'idle', hint: t('dashboard.system.oasisHint') },
    ]
  }
  const ollamaModels = s.ollama.models_available?.length ?? 0
  return [
    {
      key: 'ollama',
      label: t('dashboard.system.ollama'),
      tone: s.ollama.reachable ? 'green' : 'red',
      state: s.ollama.reachable ? 'reachable' : 'unreachable',
      hint: s.ollama.reachable
        ? t('dashboard.system.ollamaHint', { n: ollamaModels })
        : (s.ollama.error ?? s.ollama.base_url ?? ''),
    },
    {
      key: 'neo4j',
      label: t('dashboard.system.neo4j'),
      tone: s.neo4j.reachable ? 'green' : 'red',
      state: s.neo4j.reachable ? 'reachable' : 'unreachable',
      hint: s.neo4j.reachable ? (s.neo4j.uri ?? '') : (s.neo4j.error ?? ''),
    },
    {
      key: 'oasis',
      label: t('dashboard.system.oasis'),
      tone: 'gray',
      state: 'idle',
      hint: t('dashboard.system.oasisHint'),
    },
  ]
})

const diskRow = computed(() => {
  const d = props.status?.disk.uploads
  if (!d) return null
  const used = d.used_pct ?? null
  const free = d.free_bytes ?? null
  return { used, free }
})

const stateLabel = (state: HealthRow['state']) => {
  if (state === 'reachable') return t('dashboard.system.statusReachable')
  if (state === 'unreachable') return t('dashboard.system.statusUnreachable')
  return t('dashboard.system.statusIdle')
}
</script>

<template>
  <Card :title="$t('dashboard.system.title')">
    <template #right>
      <span v-if="loading" class="sh-loading">{{ $t('common.loading') }}</span>
    </template>

    <div v-if="error" class="sh-error">
      <Badge tone="red">{{ $t('dashboard.active.errorLabel') }}</Badge>
      <span class="sh-error__msg">{{ error }}</span>
      <button class="sh-retry" type="button" @click="emit('refresh')">
        {{ $t('common.tryAgain') }}
      </button>
    </div>

    <ul v-else class="sh-list">
      <li v-for="row in rows" :key="row.key" class="sh-row">
        <div class="sh-row__head">
          <span class="sh-row__label">{{ row.label }}</span>
          <Badge :tone="row.tone">{{ stateLabel(row.state) }}</Badge>
        </div>
        <p v-if="row.hint" class="sh-row__hint">{{ row.hint }}</p>
      </li>
    </ul>

    <template v-if="!error && diskRow" #footer>
      <div class="sh-disk">
        <span class="sh-disk__label">{{ $t('dashboard.system.disk') }}</span>
        <span class="sh-disk__bar" aria-hidden="true">
          <span class="sh-disk__bar-fill" :style="{ width: `${diskRow.used ?? 0}%` }" />
        </span>
        <span class="sh-disk__value">
          {{ diskRow.used !== null ? `${diskRow.used}%` : '—' }}
          <span class="sh-disk__free">· {{ fmtBytes(diskRow.free) }} {{ $t('dashboard.system.diskFree') }}</span>
        </span>
      </div>
    </template>
  </Card>
</template>

<style scoped>
.sh-loading {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--text-tertiary);
}

.sh-error {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sh-error__msg {
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--text-secondary);
  flex: 1;
  min-width: 0;
}

.sh-retry {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--accent);
  background: transparent;
  border: 0;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: var(--r-3, 6px);
}

.sh-retry:hover {
  background: var(--accent-tint-bg);
}

.sh-retry:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px var(--focus-ring);
}

.sh-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.sh-row {
  padding: 12px 0;
  border-top: 1px solid var(--separator);
}

.sh-row:first-child {
  border-top: 0;
  padding-top: 0;
}

.sh-row__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sh-row__label {
  font-family: var(--font-sans);
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.sh-row__hint {
  margin: 4px 0 0;
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--text-tertiary);
  line-height: 1.5;
  word-break: break-all;
}

.sh-disk {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  font-family: var(--font-sans);
  font-size: 12px;
}

.sh-disk__label {
  color: var(--text-secondary);
  font-weight: 500;
}

.sh-disk__bar {
  height: 4px;
  border-radius: var(--r-pill, 999px);
  background: var(--gray-5, #e5e5ea);
  overflow: hidden;
  display: block;
}

.sh-disk__bar-fill {
  display: block;
  height: 100%;
  background: var(--text-tertiary);
  transition: width 240ms ease;
}

.sh-disk__value {
  font-family: var(--font-mono);
  color: var(--text-secondary);
  white-space: nowrap;
}

.sh-disk__free {
  color: var(--text-tertiary);
}
</style>
