<script setup lang="ts">
/**
 * System — Zustand der Dienste, Version, Sprung zur Konsole (#1799, Etappe 3).
 *
 * Datenquelle ist wie bei der früheren SystemHealthCard useSystemStatus
 * (GET /api/status, Zod-validiert). Zustände werden ehrlich gezeigt: nur
 * `reachable === true` gilt als in Ordnung; „nicht erreichbar“, „unbekannt“
 * und „nicht geprüft“ erscheinen nie in der Farbe von „in Ordnung“ und
 * tragen immer auch einen Text.
 */
import { computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import SettingsGroup from '../SettingsGroup.vue'
import SettingsRow from '../SettingsRow.vue'
import { statusErrorKey, useSystemStatus } from '@/composables/useSystemStatus'
import { useLogDrawer } from '@/composables/useLogDrawer'

type Tone = 'ok' | 'down' | 'neutral'
type StateKey = 'ok' | 'down' | 'unknown' | 'skipped'

interface ServiceRow {
  key: 'backend' | 'neo4j' | 'ollama'
  state: StateKey
  detail: string
}

const { t } = useI18n()
const { status, loading, error, start, stop, refresh } = useSystemStatus()
const { available: consoleAvailable, open: openConsole } = useLogDrawer()

onMounted(() => {
  void start()
})
onUnmounted(stop)

function errorDetail(err: { code: string } | null | undefined): string {
  return err ? t(statusErrorKey(err)) : ''
}

const rows = computed<ServiceRow[]>(() => {
  const s = status.value
  if (!s) {
    return (['backend', 'neo4j', 'ollama'] as const).map((key) => ({ key, state: 'unknown' as StateKey, detail: '' }))
  }
  const ollama: ServiceRow =
    s.ollama.reachable === null
      ? {
          key: 'ollama',
          state: 'skipped',
          detail: t('views.settingsWindow.system.ollama.skipped', { provider: s.ollama.skipped_provider ?? '—' }),
        }
      : {
          key: 'ollama',
          state: s.ollama.reachable ? 'ok' : 'down',
          detail: s.ollama.reachable ? '' : errorDetail(s.ollama.error),
        }
  return [
    { key: 'backend', state: s.backend.ok ? 'ok' : 'down', detail: '' },
    {
      key: 'neo4j',
      state: s.neo4j.reachable ? 'ok' : 'down',
      detail: s.neo4j.reachable ? '' : errorDetail(s.neo4j.error),
    },
    ollama,
  ]
})

function tone(state: StateKey): Tone {
  if (state === 'ok') return 'ok'
  if (state === 'down') return 'down'
  return 'neutral'
}

const version = computed(() => status.value?.backend.version ?? t('views.settingsWindow.system.version.unknown'))

function fmtBytes(bytes: number): string {
  if (bytes >= 1e12) return `${(bytes / 1e12).toFixed(1)} TB`
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`
  return `${bytes} B`
}

const diskText = computed(() => {
  const d = status.value?.disk.uploads
  if (!d || d.error) return ''
  const parts: string[] = []
  if (typeof d.free_bytes === 'number') {
    parts.push(t('views.settingsWindow.system.disk.free', { free: fmtBytes(d.free_bytes) }))
  }
  if (typeof d.used_pct === 'number') {
    parts.push(t('views.settingsWindow.system.disk.used', { pct: Math.round(d.used_pct) }))
  }
  return parts.join(' · ')
})
</script>

<template>
  <div class="section-system">
    <div v-if="error" class="system-alert" role="alert">
      <span>{{ t('views.settingsWindow.system.loadError') }} {{ error }}</span>
      <button type="button" class="system-btn" :disabled="loading" @click="refresh()">
        {{ t('views.settingsWindow.system.retry') }}
      </button>
    </div>
    <p v-else-if="loading && !status" class="system-loading" role="status">
      {{ t('views.settingsWindow.system.loading') }}
    </p>

    <SettingsGroup :title="t('views.settingsWindow.system.groupServices')">
      <SettingsRow
        v-for="row in rows"
        :key="row.key"
        :label="t(`views.settingsWindow.system.${row.key}.label`)"
        :hint="row.detail || t(`views.settingsWindow.system.${row.key}.hint`)"
      >
        <span class="system-state" :data-tone="tone(row.state)" :data-testid="`system-state-${row.key}`">
          <span class="system-state__dot" aria-hidden="true" />
          {{ t(`views.settingsWindow.system.state.${row.state}`) }}
        </span>
      </SettingsRow>
      <SettingsRow v-if="diskText" :label="t('views.settingsWindow.system.disk.label')">
        <span class="system-value" data-testid="system-disk">{{ diskText }}</span>
      </SettingsRow>
    </SettingsGroup>
    <p class="system-note">{{ t('views.settingsWindow.system.unreported') }}</p>

    <SettingsGroup :title="t('views.settingsWindow.system.groupApp')">
      <SettingsRow :label="t('views.settingsWindow.system.version.label')">
        <span class="system-value" data-testid="system-version">{{ version }}</span>
      </SettingsRow>
      <SettingsRow
        :label="t('views.settingsWindow.system.console.label')"
        :hint="consoleAvailable ? t('views.settingsWindow.system.console.hint') : t('views.settingsWindow.system.console.unavailable')"
      >
        <button type="button" class="system-btn" :disabled="!consoleAvailable" @click="openConsole()">
          {{ t('views.settingsWindow.system.console.open') }}
        </button>
      </SettingsRow>
    </SettingsGroup>
  </div>
</template>

<style scoped>
.section-system {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.system-loading,
.system-note {
  margin: 0;
  padding: 0 4px;
  font-size: 12.5px;
  color: var(--fg3);
}

.system-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid var(--err);
  border-radius: var(--ag-r-10);
  color: var(--fg);
  font-size: 13px;
}

.system-state {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--fg);
  font-size: 13px;
}

.system-state__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--fg3);
}

.system-state[data-tone='ok'] .system-state__dot {
  background: var(--ok);
}

.system-state[data-tone='down'] .system-state__dot {
  background: var(--err);
}

.system-value {
  color: var(--fg2);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.system-btn {
  appearance: none;
  font: inherit;
  font-size: 13px;
  color: var(--fg);
  background: var(--s2);
  border: 1px solid var(--line);
  border-radius: var(--ag-r-8);
  padding: 5px 12px;
  cursor: pointer;
}

.system-btn:hover:not(:disabled) {
  border-color: var(--acc);
}

.system-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.system-btn:focus-visible {
  outline: 2px solid var(--acc);
  outline-offset: 2px;
}
</style>
