<script setup lang="ts">
/**
 * ActiveModelBadge — zeigt das aktive LLM-Modell im WorkspaceHeader.
 *
 * @deprecated Slice 5.5 — v3-Komponente, vom Grep-Check als Legacy-Ziel
 * geführt. Bleibt als Read-Adapter (SSE-Modell-Badge) bis zur Ablösung im
 * v4-App-Shell-Port. Keine neuen Importeure.
 *
 * Slice E.2 / Observability Wave 2026-05 (Anti-Flicker, Issue #213).
 *
 * - Während 'connecting'/'reconnecting': zeigt letzten bekannten Modell-String
 *   (currentModel || lastKnownModel) mit dezenten Spinner-Dot, KEIN „Verbinde…"
 *   als Hauptlabel mehr.
 * - 'failed': Reload-Button bleibt (EventSource kann hier komplett scheitern).
 * - 'idle' / isStale ohne bekanntes Modell: activeModel.unknown-Fallback.
 * - aria-live="polite", role="status".
 */
import { computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useActiveModelStore } from '../store/useActiveModelStore'
import OllamaIcon from './icons/OllamaIcon.vue'
import CloudIcon from './icons/CloudIcon.vue'
import OpenAiIcon from './icons/OpenAiIcon.vue'
import UnknownModelIcon from './icons/UnknownModelIcon.vue'

const { t } = useI18n()
const store = useActiveModelStore()

const isTransient = computed(() =>
  store.connectionStatus === 'connecting' || store.connectionStatus === 'reconnecting',
)

/**
 * Anzuzeigender Modell-String: zuerst live, dann lastKnown, dann i18n-Fallback.
 */
const displayModel = computed(() =>
  store.currentModel ?? store.lastKnownModel ?? t('activeModel.unknown'),
)

/**
 * Provider aus dem letzten Event — für Icon-Auswahl auch während Reconnect.
 */
const displayProvider = computed(() => store.lastEvent?.provider ?? null)

const displayContext = computed(() => store.lastEvent?.context ?? null)

onMounted(() => {
  store.connect()
})

onUnmounted(() => {
  store.disconnect()
})
</script>

<template>
  <div
    class="active-model-badge"
    role="status"
    aria-live="polite"
    :aria-label="t('activeModel.label')"
  >
    <!-- Failed state: show reload button -->
    <template v-if="store.connectionStatus === 'failed'">
      <span class="badge-status badge-status--failed">
        {{ t('activeModel.failed') }}
      </span>
      <button
        type="button"
        class="badge-reload-btn"
        @click="store.reconnect()"
      >
        {{ t('activeModel.reload') }}
      </button>
    </template>

    <!-- Connecting / reconnecting: Modell bleibt sichtbar, dezenter Spinner-Dot -->
    <template v-else-if="isTransient">
      <span class="badge-spinner-dot" :title="t('activeModel.reconnecting')" aria-hidden="true" />
      <span
        v-if="displayProvider"
        class="badge-provider-icon"
        :title="t(`activeModel.provider.${displayProvider}`)"
      >
        <OllamaIcon v-if="displayProvider === 'ollama'" />
        <CloudIcon v-else-if="displayProvider === 'cloud'" />
        <OpenAiIcon v-else-if="displayProvider === 'openai'" />
        <UnknownModelIcon v-else />
      </span>
      <span
        class="badge-model-name badge-model-name--faded"
        :title="displayContext ? t(`activeModel.context.${displayContext}`) : undefined"
      >
        {{ displayModel }}
      </span>
    </template>

    <!-- Idle fallback: no event yet or data is stale and no lastKnown -->
    <template v-else-if="store.isStale && store.lastKnownModel === null">
      <span class="badge-status badge-status--idle">
        {{ t('activeModel.idle') }}
      </span>
    </template>

    <!-- Active model info (connected, not stale) or stale with lastKnown -->
    <template v-else>
      <span
        v-if="displayProvider"
        class="badge-provider-icon"
        :title="t(`activeModel.provider.${displayProvider}`)"
      >
        <OllamaIcon v-if="displayProvider === 'ollama'" />
        <CloudIcon v-else-if="displayProvider === 'cloud'" />
        <OpenAiIcon v-else-if="displayProvider === 'openai'" />
        <UnknownModelIcon v-else />
      </span>
      <span
        class="badge-model-name"
        :title="displayContext ? t(`activeModel.context.${displayContext}`) : undefined"
      >
        {{ displayModel }}
      </span>
    </template>
  </div>
</template>

<style scoped>
.active-model-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--s-2, 0.25rem);
  font-size: 0.75rem;
  line-height: 1;
  padding: 0.2rem 0.5rem;
  border-radius: 9999px;
  background: var(--bg-subtle, rgba(0,0,0,0.06));
  color: var(--text-secondary, #666);
  white-space: nowrap;
  max-width: 20rem;
  overflow: hidden;
}

.badge-model-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge-model-name--faded {
  opacity: 0.65;
}

.badge-provider-icon {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  width: 1rem;
  height: 1rem;
}

/* Dezenter Spinner-Dot: pulsierender Kreis, kein ablenkender Ring */
.badge-spinner-dot {
  display: inline-block;
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: var(--color-warning, #f59e0b);
  flex-shrink: 0;
  animation: badge-pulse 1.4s ease-in-out infinite;
}

@keyframes badge-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.35; transform: scale(0.75); }
}

.badge-status {
  font-size: 0.7rem;
}

.badge-status--failed {
  color: var(--color-error, #c00);
}

.badge-status--idle {
  color: var(--text-tertiary, #999);
}

.badge-reload-btn {
  font-size: 0.7rem;
  padding: 0.1rem 0.4rem;
  border: 1px solid currentColor;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  color: var(--color-error, #c00);
  line-height: 1.4;
}

.badge-reload-btn:hover {
  background: var(--color-error-subtle, rgba(200,0,0,0.08));
}

@media (max-width: 720px) {
  .active-model-badge {
    display: none;
  }
}
</style>
