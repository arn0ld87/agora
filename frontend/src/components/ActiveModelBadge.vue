<script setup lang="ts">
/**
 * ActiveModelBadge — zeigt das aktive LLM-Modell im WorkspaceHeader.
 *
 * Slice E.2, Issue #213.
 *
 * - Holt sich den Store, öffnet den SSE-Stream on mount.
 * - Zeigt Modell + Provider-Icon (SVG inline, Emoji-Fallback für unbekannte Provider).
 * - Idle-Fallback: isStale oder kein lastEvent → activeModel.idle.
 * - Failed-State: Reload-Button analog J.6 LogDrawer.
 * - aria-live="polite", role="status".
 * - Alle Strings über t('activeModel.*').
 */
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useActiveModelStore } from '../store/useActiveModelStore'
import OllamaIcon from './icons/OllamaIcon.vue'
import CloudIcon from './icons/CloudIcon.vue'
import OpenAiIcon from './icons/OpenAiIcon.vue'
import UnknownModelIcon from './icons/UnknownModelIcon.vue'

const { t } = useI18n()
const store = useActiveModelStore()

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

    <!-- Connecting / reconnecting state -->
    <template v-else-if="store.connectionStatus === 'connecting' || store.connectionStatus === 'reconnecting'">
      <span class="badge-status badge-status--connecting">
        {{ t('activeModel.connecting') }}
      </span>
    </template>

    <!-- Idle fallback: no event yet or data is stale -->
    <template v-else-if="store.isStale || store.lastEvent === null">
      <span class="badge-status badge-status--idle">
        {{ t('activeModel.idle') }}
      </span>
    </template>

    <!-- Active model info -->
    <template v-else>
      <span class="badge-provider-icon" :title="t(`activeModel.provider.${store.lastEvent.provider}`)">
        <OllamaIcon v-if="store.lastEvent.provider === 'ollama'" />
        <CloudIcon v-else-if="store.lastEvent.provider === 'cloud'" />
        <OpenAiIcon v-else-if="store.lastEvent.provider === 'openai'" />
        <UnknownModelIcon v-else />
      </span>
      <span class="badge-model-name" :title="t(`activeModel.context.${store.lastEvent.context}`)">
        {{ store.lastEvent.model }}
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

.badge-provider-icon {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  width: 1rem;
  height: 1rem;
}

.badge-status {
  font-size: 0.7rem;
}

.badge-status--failed {
  color: var(--color-error, #c00);
}

.badge-status--connecting {
  color: var(--text-tertiary, #999);
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
