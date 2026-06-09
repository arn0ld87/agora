<script setup lang="ts">
import { type PropType, type ComponentPublicInstance } from 'vue'
import { useI18n } from 'vue-i18n'
import Badge from '../ui/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import StickyScrollBanner from '../ui/StickyScrollBanner.vue'

const { t } = useI18n()

const props = defineProps({
  consoleLogs: { type: Array, required: true },
  toolPanelFilter: { type: String, default: 'all' },
  filteredConsoleLogs: { type: Array, required: true },
  consoleScrollRef: { type: Function as PropType<(el: Element | ComponentPublicInstance | null) => void>, default: null },
  consoleUnreadCount: { type: Number, default: 0 },
})

const emit = defineEmits([
  'update:toolPanelFilter',
  'copy-line',
  'scroll-to-bottom',
])

const ERROR_PATTERN = /(error|exception|traceback|fatal|warn|warning)/i

function isErrorLine(line: unknown): boolean {
  if (typeof line !== 'string') return false
  return ERROR_PATTERN.test(line)
}

async function copyLine(line: unknown) {
  emit('copy-line', line)
}
</script>

<template>
  <article
    class="card tool-panel-card"
    role="region"
    :aria-label="t('step3.toolPanel.toggle')"
    data-testid="simulation-tool-panel"
  >
    <header class="card-head">
      <Kicker num="04">{{ t('step3.toolPanel.toggle') }}</Kicker>
      <div class="log-meta">
        <div class="filter-toggle" role="group" :aria-label="t('step3.toolPanel.filter')">
          <button
            type="button"
            class="filter-btn"
            :class="{ active: toolPanelFilter === 'all' }"
            :aria-pressed="toolPanelFilter === 'all'"
            @click="emit('update:toolPanelFilter', 'all')"
          >{{ t('step3.toolPanel.filterAll') }}</button>
          <button
            type="button"
            class="filter-btn"
            :class="{ active: toolPanelFilter === 'errors' }"
            :aria-pressed="toolPanelFilter === 'errors'"
            @click="emit('update:toolPanelFilter', 'errors')"
          >{{ t('step3.toolPanel.filterErrors') }}</button>
        </div>
        <Badge variant="ghost">{{ filteredConsoleLogs.length }} / {{ consoleLogs.length }}</Badge>
      </div>
    </header>
    <div class="log-pane">
      <div class="log-pane-scroll-wrap">
        <div :ref="consoleScrollRef" class="log-block log-pane-body">
          <div v-if="!filteredConsoleLogs.length" class="meta">
            {{ toolPanelFilter === 'errors' ? t('step3.toolPanel.noErrors') : t('step3.toolPanel.empty') }}
          </div>
          <div
            v-for="(line, i) in filteredConsoleLogs"
            :key="'c' + i"
            class="console-line"
            :class="{ 'is-error': isErrorLine(line) }"
          >
            <button
              type="button"
              class="copy-btn"
              :title="t('step3.toolPanel.copyAsJson')"
              @click="copyLine(line)"
            >📋</button>
            <span>{{ line }}</span>
          </div>
        </div>
        <StickyScrollBanner
          :count="consoleUnreadCount"
          @jump="emit('scroll-to-bottom')"
        />
      </div>
    </div>
  </article>
</template>

<style scoped>
.card {
  background: var(--bg);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  padding: var(--s-5);
  display: flex;
  flex-direction: column;
  gap: var(--s-4);
}
.card-head {
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-3);
}
.log-meta { display: flex; gap: var(--s-2); }
.log-pane {
  display: flex;
  flex-direction: column;
  gap: var(--s-2);
  min-width: 0;
}
.log-pane-scroll-wrap { position: relative; }
.log-pane-body {
  min-height: 480px;
  max-height: clamp(480px, 60vh, 720px);
  overflow-y: auto;
}
.filter-toggle {
  display: inline-flex;
  border: 1px solid var(--hairline, var(--rule));
  border-radius: var(--r-5, var(--r-1));
  overflow: hidden;
  background: var(--surface-elevated, transparent);
}
.filter-btn {
  background: transparent;
  border: 0;
  padding: 4px 10px;
  font-family: var(--font-sans, var(--ff-sans));
  font-size: 11px;
  color: var(--text-secondary, var(--fg-muted));
  cursor: pointer;
}
.filter-btn + .filter-btn { border-left: 1px solid var(--separator, var(--rule)); }
.filter-btn:hover { background: var(--surface-hover, transparent); color: var(--text-primary, var(--fg)); }
.filter-btn.active { background: var(--accent); color: var(--text-on-accent, var(--bg)); }
.console-line {
  display: flex;
  gap: var(--s-2);
  align-items: flex-start;
  font-family: var(--font-sans, var(--ff-sans));
  font-size: 11px;
  color: var(--text-secondary, var(--mono-100));
  word-wrap: break-word;
  white-space: pre-wrap;
  margin-bottom: 2px;
  line-height: 1.5;
}
.console-line.is-error { color: var(--status-red, var(--status-error, #f56565)); }
.copy-btn {
  background: transparent;
  border: 0;
  cursor: pointer;
  font-size: 11px;
  opacity: 0.4;
  transition: opacity 120ms ease;
  padding: 0 4px;
  flex-shrink: 0;
}
.copy-btn:hover { opacity: 1; }
.meta { color: var(--fg-muted); font-family: var(--ff-mono); font-size: 11px; }
</style>
