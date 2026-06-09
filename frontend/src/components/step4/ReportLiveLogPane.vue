<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Badge from '../ui/Badge.vue'
import Kicker from '@/components/v4/data/Kicker.vue'
import StickyScrollBanner from '../ui/StickyScrollBanner.vue'
import { entryAnchorId } from '../../utils/sourceAnchor'

const { t } = useI18n()

defineProps({
  agentLogs: { type: Array, required: true },
  consoleLogs: { type: Array, required: true },
  agentLogRef: { type: Object, default: null },
  consoleLogRef: { type: Object, default: null },
  agentUnreadCount: { type: Number, default: 0 },
  consoleUnreadCount: { type: Number, default: 0 },
})

const emit = defineEmits(['agent-scroll-to-bottom', 'console-scroll-to-bottom'])
</script>

<template>
  <article class="card" data-testid="report-live-log-pane">
    <header class="card-head">
      <Kicker num="03">{{ t('step4.view.tools') }}</Kicker>
      <div class="log-meta">
        <Badge variant="ghost">{{ agentLogs.length }} agent</Badge>
        <Badge variant="ghost">{{ consoleLogs.length }} console</Badge>
      </div>
    </header>
    <div class="logs-grid">
      <div class="log-pane">
        <div class="log-pane-head">
          <span class="meta">Agent</span>
          <span class="meta">{{ agentLogs.length }}</span>
        </div>
        <div class="log-pane-scroll-wrap">
          <div class="log-block log-pane-body">
            <div v-if="!agentLogs.length" class="meta">Warte auf Agent-Aktivität…</div>
            <div
              v-for="(e, i) in agentLogs"
              :key="'a' + i"
              :id="`agent-entry-${entryAnchorId(e as any)}`"
              class="agent-entry"
              :class="'action-' + ((e as any).action || 'unknown')"
            >
              <div class="agent-entry-head">
                <span v-if="(e as any).ts" class="agent-ts">{{ (e as any).ts }}</span>
                <span class="agent-title">{{ (e as any).title }}</span>
                <span v-if="(e as any).elapsed" class="agent-meta">{{ (e as any).elapsed.toFixed(1) }}s</span>
              </div>
              <div v-if="(e as any).subtitle" class="agent-subtitle">{{ (e as any).subtitle }}</div>
              <div v-if="(e as any).body" class="agent-body">{{ (e as any).body.length > 600 ? (e as any).body.slice(0, 600) + '…' : (e as any).body }}</div>
            </div>
          </div>
          <StickyScrollBanner
            :count="agentUnreadCount"
            @jump="emit('agent-scroll-to-bottom')"
          />
        </div>
      </div>
      <div class="log-pane">
        <div class="log-pane-head">
          <span class="meta">Console</span>
          <span class="meta">{{ consoleLogs.length }}</span>
        </div>
        <div class="log-pane-scroll-wrap">
          <div class="log-block log-pane-body">
            <div v-for="(line, i) in consoleLogs" :key="'c' + i" class="log-line console">
              {{ line }}
            </div>
          </div>
          <StickyScrollBanner
            :count="consoleUnreadCount"
            @jump="emit('console-scroll-to-bottom')"
          />
        </div>
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
.card-head { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--rule); padding-bottom: var(--s-3); }
.log-meta { display: flex; gap: var(--s-2); }
.logs-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-3); }
.log-pane { display: flex; flex-direction: column; gap: var(--s-2); }
.log-pane-scroll-wrap { position: relative; }
.log-pane-head {
  display: flex;
  justify-content: space-between;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--rule);
  padding-bottom: var(--s-2);
}
.log-pane-body { max-height: 280px; overflow-y: auto; border-radius: var(--r-1); }
.log-block { max-height: 280px; overflow-y: auto; }
.log-line { font-family: var(--ff-mono); font-size: 11px; color: var(--mono-50); word-wrap: break-word; white-space: pre-wrap; margin-bottom: 2px; line-height: 1.5; }
.log-line.console { color: var(--mono-300); }
.agent-entry { padding: 6px 0; border-bottom: 1px dashed var(--rule-soft); font-family: var(--font-sans, var(--ff-mono)); font-size: 11px; line-height: 1.5; color: var(--mono-100); }
.agent-entry-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 2px; }
.agent-ts { color: var(--mono-400); font-size: 10px; }
.agent-title { color: var(--mono-50); font-weight: 500; text-transform: uppercase; letter-spacing: 0.03em; }
.agent-meta { margin-left: auto; color: var(--mono-400); font-size: 10px; }
.agent-subtitle { color: var(--mono-300); margin-bottom: 2px; word-break: break-word; }
.agent-body { color: var(--mono-200); white-space: pre-wrap; word-break: break-word; padding: 4px 0 0 12px; border-left: 2px solid color-mix(in srgb, var(--accent) 35%, transparent); font-family: var(--font-sans, var(--ff-sans)); font-size: 12px; line-height: 1.6; }
.agent-entry.action-tool_call .agent-title { color: var(--accent); }
.agent-entry.action-tool_result .agent-title { color: var(--status-green, var(--status-success)); }
.agent-entry.action-error .agent-title { color: var(--status-red, var(--status-error)); }
.agent-entry.action-section_start .agent-title,
.agent-entry.action-section_complete .agent-title { color: var(--status-orange, var(--status-warn)); }
.agent-entry.action-llm_response .agent-title { color: var(--mono-400); }
.agent-entry.is-highlighted { background: var(--accent-tint-bg, var(--accent-soft)); transition: background 0.4s ease-in-out; }
.meta { font-family: var(--ff-mono); font-size: 11px; color: var(--fg-muted); }
@media (max-width: 880px) { .logs-grid { grid-template-columns: 1fr; } }
</style>
