<script setup lang="ts">
/**
 * SimActionsTable — Protokoll.
 *
 * Slice UI-2b (#1713), docs/design/simulation-feed.md §2.10. Datenquelle:
 * GET /api/simulation/<id>/actions (SimActionPage, Cursor-Pagination).
 *
 * Deviation von der abgekuerzten Spezifikation: die Spaltennamen
 * "persona_name"/"payload_preview" existieren im Vertrag
 * (SimActionRecord, backend/app/contracts/sim_action_contract.py) nicht
 * woertlich — die Felder heissen `agent_name`/`content`. Diese Komponente
 * bindet die tatsaechlichen Vertragsfelder, nicht die Doku-Kurznamen.
 * Zusaetzlich zu den in §2.10 genannten Spalten macht sie zwei weitere
 * Vertragsfelder sichtbar statt sie stillschweigend zu verwerfen (Prinzip
 * „Degradation sichtbar", §4 der Spezifikation): `role_conflict`
 * (Role-Leakage-Erkennung) als Chip neben der Persona, `success=false`
 * als Chip neben der Aktionsart.
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Platform } from '@/contracts/postEventContract'
import type { SimActionPage, SimActionRecord, SimActionType } from '@/contracts/simActionContract'

export interface SimActionsTableFilters {
  round?: number
  agentId?: string
  platform?: Platform
  actionType?: SimActionType
}

const props = defineProps<{
  page: SimActionPage
  loading: boolean
  filters: SimActionsTableFilters
}>()

const emit = defineEmits<{ loadMore: []; openPost: [postId: string] }>()

const { t } = useI18n()

function formatTime(record: SimActionRecord): string {
  const value = record.sim_time ?? record.timestamp
  return value.slice(0, 16).replace('T', ' ')
}

function actionLabel(type: SimActionType): string {
  return t(`feed.actionType.${type}`)
}

function payloadPreview(record: SimActionRecord): string {
  if (!record.content) return t('feed.actionsTable.noPayload')
  return record.content.length > 80 ? `${record.content.slice(0, 80)}…` : record.content
}

function platformLabel(platform: Platform): string {
  return platform === 'reddit' ? t('feed.reddit') : t('feed.twitter')
}

function openTarget(record: SimActionRecord): void {
  if (record.target_post_id) emit('openPost', record.target_post_id)
}

function onKeydown(event: KeyboardEvent, record: SimActionRecord): void {
  if ((event.key === 'Enter' || event.key === ' ') && record.target_post_id) {
    event.preventDefault()
    openTarget(record)
  }
}

const hasItems = computed(() => props.page.items.length > 0)
const isInitialLoading = computed(() => props.loading && !hasItems.value)
const hasMore = computed(() => props.page.next_cursor !== null)
</script>

<template>
  <div class="sat-root">
    <div v-if="isInitialLoading" class="sat-skeleton" aria-busy="true">
      <div v-for="i in 5" :key="i" class="sat-skeleton-row"></div>
    </div>

    <p v-else-if="!hasItems" class="sat-empty" role="status">
      {{ t('feed.actionsTable.empty') }}
    </p>

    <template v-else>
      <table class="sat-table">
        <caption class="sat-caption">{{ t('feed.actionsTab') }}</caption>
        <thead>
          <tr>
            <th scope="col">{{ t('feed.actionsTable.round') }}</th>
            <th scope="col">{{ t('feed.actionsTable.time') }}</th>
            <th scope="col">{{ t('feed.actionsTable.persona') }}</th>
            <th scope="col">{{ t('feed.actionsTable.platform') }}</th>
            <th scope="col">{{ t('feed.actionsTable.type') }}</th>
            <th scope="col">{{ t('feed.actionsTable.target') }}</th>
            <th scope="col">{{ t('feed.actionsTable.payload') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(record, index) in page.items"
            :key="`${record.agent_id}-${record.timestamp}-${index}`"
            class="sat-row"
            :class="{ 'sat-row--failed': !record.success, 'sat-row--clickable': !!record.target_post_id }"
            :tabindex="record.target_post_id ? 0 : undefined"
            @click="openTarget(record)"
            @keydown="(event) => onKeydown(event, record)"
          >
            <td>{{ record.round_num }}</td>
            <td>{{ formatTime(record) }}</td>
            <td>
              {{ record.agent_name }}
              <span v-if="record.role_conflict" class="sat-badge sat-badge--warn">
                {{ t('feed.actionsTable.roleConflict') }}
              </span>
            </td>
            <td>{{ platformLabel(record.platform) }}</td>
            <td>
              {{ actionLabel(record.action_type) }}
              <span v-if="!record.success" class="sat-badge sat-badge--danger">
                {{ t('feed.actionsTable.failed') }}
              </span>
            </td>
            <td>
              <span v-if="record.target_post_id" class="sat-target">{{ record.target_post_id }}</span>
              <span v-else>{{ t('feed.actionsTable.noTarget') }}</span>
            </td>
            <td class="sat-payload">{{ payloadPreview(record) }}</td>
          </tr>
        </tbody>
      </table>

      <div v-if="loading" class="sat-skeleton sat-skeleton--append" aria-busy="true">
        <div v-for="i in 3" :key="i" class="sat-skeleton-row"></div>
      </div>
      <button
        v-else-if="hasMore"
        type="button"
        class="sat-load-more"
        @click="emit('loadMore')"
      >
        {{ t('feed.actionsTable.loadMore') }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.sat-root {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.sat-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--sim-time-fs);
}
.sat-caption {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
.sat-table th {
  position: sticky;
  top: 0;
  background: var(--surface-inset);
  text-align: left;
  padding: var(--table-cell-py, 8px) var(--table-cell-px, 10px);
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: var(--sim-item-divider);
}
.sat-table td {
  padding: var(--table-cell-py, 8px) var(--table-cell-px, 10px);
  border-bottom: var(--sim-item-divider);
  color: var(--text-primary);
  vertical-align: top;
}
.sat-row--clickable {
  cursor: pointer;
}
.sat-row--clickable:hover {
  background: var(--surface-hover);
}
.sat-row:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.sat-row--failed {
  opacity: 0.7;
}
.sat-target {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--status-teal);
}
.sat-payload {
  max-width: 320px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-secondary);
}
.sat-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: var(--r-2);
  font-size: 10px;
  font-weight: 600;
}
.sat-badge--warn {
  background: var(--status-warning-soft, var(--status-orange-bg));
  color: var(--status-warning, var(--status-orange));
}
.sat-badge--danger {
  background: var(--status-red-bg);
  color: var(--status-red);
}
.sat-empty {
  margin: 0;
  padding: 32px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
}
.sat-load-more {
  display: block;
  margin: 12px auto;
  border: 1px solid var(--hairline);
  border-radius: var(--r-5);
  background: var(--surface-inset);
  color: var(--text-primary);
  padding: 6px 16px;
  font-size: 12px;
  cursor: pointer;
}
.sat-load-more:hover {
  background: var(--surface-hover);
}
.sat-skeleton {
  padding: var(--sim-item-py) var(--sim-item-px);
  display: flex;
  flex-direction: column;
  gap: var(--sim-item-gap);
}
.sat-skeleton-row {
  height: 32px;
  border-radius: var(--r-5);
  background: var(--surface-inset);
  animation: sat-shimmer 1.4s ease-in-out infinite;
}
@keyframes sat-shimmer {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}
@media (prefers-reduced-motion: reduce) {
  .sat-skeleton-row {
    animation: none;
  }
}
</style>
