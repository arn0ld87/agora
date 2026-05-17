<script lang="ts">
/**
 * Re-Export von deriveLabel damit Imports aus ConfidenceBadge.vue funktionieren:
 *   import ConfidenceBadge, { deriveLabel } from './ui/ConfidenceBadge.vue'
 */
export { deriveLabel } from '../../utils/confidenceUtils'
</script>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { deriveLabel } from '../../utils/confidenceUtils'
import type { AuditEntry } from '../../utils/confidenceUtils'

interface Props {
  score: number
  label?: 'speculative' | 'low' | 'medium' | 'high' | 'verified'
  auditTrail?: AuditEntry[]
  showCount?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: undefined,
  auditTrail: () => [],
  showCount: true,
})

const hover = ref(false)
let closeTimer: ReturnType<typeof setTimeout> | null = null

function onMouseEnter() {
  if (closeTimer !== null) {
    clearTimeout(closeTimer)
    closeTimer = null
  }
  hover.value = true
}

function onMouseLeave() {
  closeTimer = setTimeout(() => {
    hover.value = false
    closeTimer = null
  }, 200)
}

const bucket = computed(() => props.label ?? deriveLabel(props.score))
const pct = computed(() => Math.round(props.score * 100))
const hasAudit = computed(() => Array.isArray(props.auditTrail) && props.auditTrail.length > 0)

const BUCKET_LABELS: Record<'speculative' | 'low' | 'medium' | 'high' | 'verified', string> = {
  speculative: 'spekulativ',
  low: 'niedrig',
  medium: 'mittel',
  high: 'hoch',
  verified: 'verifiziert',
}

const bucketLabel = computed(() => BUCKET_LABELS[bucket.value] ?? bucket.value)
const ariaLabel = computed(() => `Konfidenz: ${BUCKET_LABELS[bucket.value] ?? bucket.value}`)
</script>

<template>
  <span
    class="confidence-badge"
    :class="`is-${bucket}`"
    :aria-label="ariaLabel"
    @mouseenter="onMouseEnter"
    @mouseleave="onMouseLeave"
  >
    <span class="badge-label">
      <template v-if="showCount">{{ pct }}% · </template>{{ bucketLabel }}
    </span>

    <div v-if="hover" class="audit-popover">
      <div class="audit-popover-head">
        Audit-Trail · {{ hasAudit ? (auditTrail || []).length : 0 }} Einträge
      </div>
      <template v-if="hasAudit">
        <ul class="audit-list">
          <li
            v-for="(entry, idx) in auditTrail"
            :key="idx"
            class="audit-item"
          >
            <span v-if="entry.source" class="audit-source">{{ entry.source }}</span>
            <span v-if="entry.snippet" class="audit-snippet">{{ entry.snippet }}</span>
          </li>
        </ul>
      </template>
      <template v-else>
        <p class="audit-empty">Keine Audit-Einträge</p>
      </template>
    </div>
  </span>
</template>

<style scoped>
.confidence-badge {
  position: relative;
  display: inline-flex;
  align-items: center;
  border-radius: var(--r-pill);
  padding: 2px 10px;
  font-family: var(--ff-mono);
  font-size: 11px;
  letter-spacing: var(--ls-mono);
  white-space: nowrap;
  cursor: default;
  user-select: none;
  border: 1px solid transparent;
}

.is-verified {
  background: color-mix(in oklch, #1d6fa4 12%, transparent);
  color: #1d6fa4;
  border-color: color-mix(in oklch, #1d6fa4 40%, transparent);
}

.is-high {
  background: var(--ok-soft);
  color: var(--ok);
  border-color: color-mix(in oklch, var(--ok) 40%, transparent);
}

.is-medium {
  background: var(--warn-soft);
  color: var(--warn);
  border-color: color-mix(in oklch, var(--warn) 40%, transparent);
}

.is-low {
  background: var(--err-soft);
  color: var(--err);
  border-color: color-mix(in oklch, var(--err) 40%, transparent);
}

.is-speculative {
  background: color-mix(in oklch, #7c6f9e 10%, transparent);
  color: #7c6f9e;
  border-color: color-mix(in oklch, #7c6f9e 35%, transparent);
}

.audit-popover {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 100;
  min-width: 240px;
  max-width: 340px;
  background: var(--bg-elevated, #fff);
  border: 1px solid var(--rule);
  border-radius: var(--r-1, 4px);
  padding: var(--s-3, 8px);
  box-shadow: 0 4px 16px color-mix(in srgb, var(--fg, #000) 12%, transparent);
}

.audit-popover-head {
  font-family: var(--ff-mono);
  font-size: 10px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
  margin-bottom: var(--s-2, 6px);
  padding-bottom: var(--s-2, 6px);
  border-bottom: 1px solid var(--rule);
}

.audit-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 240px;
  overflow-y: auto;
}

.audit-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.audit-source {
  font-family: var(--ff-mono);
  font-size: 10px;
  letter-spacing: var(--ls-mono);
  text-transform: uppercase;
  color: var(--fg-muted);
}

.audit-snippet {
  font-family: var(--ff-sans, sans-serif);
  font-size: 12px;
  line-height: 1.5;
  color: var(--fg);
  word-break: break-word;
}

.audit-empty {
  font-family: var(--ff-mono);
  font-size: 11px;
  color: var(--fg-muted);
  margin: 0;
}
</style>
