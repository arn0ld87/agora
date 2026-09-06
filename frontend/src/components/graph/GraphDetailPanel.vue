<template>
  <div class="detail-panel">
    <div class="detail-panel-header">
      <span class="detail-title">{{ item.type === 'node' ? 'Node Details' : 'Relationship' }}</span>
      <span
        v-if="item.type === 'node'"
        class="detail-type-badge"
        :style="{ background: item.color, color: 'var(--mono-50)' }"
      >
        {{ item.entityType }}
      </span>
      <button class="detail-close" @click="$emit('close')">×</button>
    </div>

    <div v-if="item.type === 'node'" class="detail-content">
      <div class="detail-row">
        <span class="detail-label">Name:</span>
        <span class="detail-value">{{ item.data.name }}</span>
      </div>
      <div class="detail-row">
        <span class="detail-label">UUID:</span>
        <span class="detail-value uuid-text">{{ item.data.uuid }}</span>
      </div>
      <div v-if="item.data.created_at" class="detail-row">
        <span class="detail-label">Created:</span>
        <span class="detail-value">{{ formatDateTime(item.data.created_at) }}</span>
      </div>

      <div v-if="hasAttributes" class="detail-section">
        <div class="section-title">Properties:</div>
        <div class="properties-list">
          <div v-for="(value, key) in item.data.attributes" :key="key" class="property-item">
            <span class="property-key">{{ key }}:</span>
            <span class="property-value">{{ value || 'None' }}</span>
          </div>
        </div>
      </div>

      <div v-if="item.data.summary" class="detail-section">
        <div class="section-title">Summary:</div>
        <div class="summary-text">{{ item.data.summary }}</div>
      </div>

      <div v-if="hasLabels" class="detail-section">
        <div class="section-title">Labels:</div>
        <div class="labels-list">
          <span v-for="label in item.data.labels" :key="label" class="label-tag">
            {{ label }}
          </span>
        </div>
      </div>
    </div>

    <div v-else class="detail-content">
      <template v-if="item.data.isSelfLoopGroup">
        <div class="edge-relation-header self-loop-header">
          {{ item.data.source_name }} - Self Relations
          <span class="self-loop-count">{{ item.data.selfLoopCount }} items</span>
        </div>

        <div class="self-loop-list">
          <div
            v-for="(loop, idx) in item.data.selfLoopEdges"
            :key="loop.uuid || idx"
            class="self-loop-item"
            :class="{ expanded: expandedSelfLoops.has(loop.uuid || idx) }"
          >
            <div class="self-loop-item-header" @click="$emit('toggle-self-loop', loop.uuid || idx)">
              <span class="self-loop-index">#{{ idx + 1 }}</span>
              <span class="self-loop-name">{{ loop.name || loop.fact_type || 'RELATED' }}</span>
              <span class="self-loop-toggle">{{ expandedSelfLoops.has(loop.uuid || idx) ? '−' : '+' }}</span>
            </div>

            <div v-show="expandedSelfLoops.has(loop.uuid || idx)" class="self-loop-item-content">
              <div v-if="loop.uuid" class="detail-row">
                <span class="detail-label">UUID:</span>
                <span class="detail-value uuid-text">{{ loop.uuid }}</span>
              </div>
              <div v-if="loop.fact" class="detail-row">
                <span class="detail-label">Fact:</span>
                <span class="detail-value fact-text">{{ loop.fact }}</span>
              </div>
              <div v-if="loop.fact_type" class="detail-row">
                <span class="detail-label">Type:</span>
                <span class="detail-value">{{ loop.fact_type }}</span>
              </div>
              <div v-if="loop.created_at" class="detail-row">
                <span class="detail-label">Created:</span>
                <span class="detail-value">{{ formatDateTime(loop.created_at) }}</span>
              </div>
              <div v-if="loop.episodes?.length" class="self-loop-episodes">
                <span class="detail-label">Episodes:</span>
                <div class="episodes-list compact">
                  <span v-for="ep in loop.episodes" :key="ep" class="episode-tag small">{{ ep }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <div class="edge-relation-header">
          {{ item.data.source_name }} → {{ item.data.name || 'RELATED_TO' }} → {{ item.data.target_name }}
        </div>

        <div class="detail-row">
          <span class="detail-label">UUID:</span>
          <span class="detail-value uuid-text">{{ item.data.uuid }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Label:</span>
          <span class="detail-value">{{ item.data.name || 'RELATED_TO' }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">Type:</span>
          <span class="detail-value">{{ item.data.fact_type || 'Unknown' }}</span>
        </div>
        <div v-if="item.data.fact" class="detail-row">
          <span class="detail-label">Fact:</span>
          <span class="detail-value fact-text">{{ item.data.fact }}</span>
        </div>

        <div v-if="item.data.episodes?.length" class="detail-section">
          <div class="section-title">Episodes:</div>
          <div class="episodes-list">
            <span v-for="ep in item.data.episodes" :key="ep" class="episode-tag">
              {{ ep }}
            </span>
          </div>
        </div>

        <div v-if="item.data.created_at" class="detail-row">
          <span class="detail-label">Created:</span>
          <span class="detail-value">{{ formatDateTime(item.data.created_at) }}</span>
        </div>
        <div v-if="item.data.valid_at" class="detail-row">
          <span class="detail-label">Valid From:</span>
          <span class="detail-value">{{ formatDateTime(item.data.valid_at) }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import { formatDateTime } from './graphPanelUtils'

const props = defineProps({
  item: {
    type: Object,
    required: true,
  },
  expandedSelfLoops: {
    type: Object,
    default: () => new Set(),
  },
})

defineEmits(['close', 'toggle-self-loop'])

const hasAttributes = computed(() => Object.keys(props.item.data.attributes || {}).length > 0)
const hasLabels = computed(() => Array.isArray(props.item.data.labels) && props.item.data.labels.length > 0)
</script>

<style scoped>
.detail-panel {
  position: absolute;
  top: 60px;
  right: 20px;
  width: 320px;
  max-height: calc(100% - 100px);
  background: var(--bg-elevated);
  border: 1px solid var(--rule);
  border-radius: var(--r-1);
  box-shadow: var(--shadow-popover);
  overflow: hidden;
  font-family: var(--ff-sans);
  font-size: 13px;
  z-index: 20;
  display: flex;
  flex-direction: column;
}

.detail-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: var(--bg-sunken);
  border-bottom: 1px solid var(--rule);
  flex-shrink: 0;
}

.detail-title {
  font-weight: 600;
  color: var(--fg);
  font-size: 14px;
}

.detail-type-badge {
  padding: 4px 10px;
  border-radius: var(--r-2);
  font-size: 11px;
  font-weight: 500;
  margin-left: auto;
  margin-right: 12px;
}

.detail-close {
  background: none;
  border: none;
  font-size: 20px;
  cursor: pointer;
  color: var(--fg-meta);
  line-height: 1;
  padding: 0;
  transition: color 0.2s;
}

.detail-close:hover {
  color: var(--fg);
}

.detail-content {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.detail-row {
  margin-bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.detail-label {
  color: var(--fg-muted);
  font-size: 12px;
  font-weight: 500;
  min-width: 80px;
}

.detail-value {
  color: var(--fg);
  flex: 1;
  word-break: break-word;
}

.detail-value.uuid-text {
  font-family: var(--ff-mono);
  font-size: 11px;
  color: var(--fg-body);
}

.detail-value.fact-text {
  line-height: 1.5;
  color: var(--fg-body);
}

.detail-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--rule);
}

.section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-body);
  margin-bottom: 10px;
}

.properties-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.property-item {
  display: flex;
  gap: 8px;
}

.property-key {
  color: var(--fg-muted);
  font-weight: 500;
  min-width: 90px;
}

.property-value {
  color: var(--fg);
  flex: 1;
}

.summary-text {
  line-height: 1.6;
  color: var(--fg-body);
  font-size: 12px;
}

.labels-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.label-tag {
  display: inline-block;
  padding: 4px 12px;
  background: var(--bg-panel-2);
  border: 1px solid var(--rule);
  border-radius: var(--r-2);
  font-size: 11px;
  color: var(--fg-body);
}

.episodes-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.episode-tag {
  display: inline-block;
  padding: 6px 10px;
  background: var(--bg-panel);
  border: 1px solid var(--rule);
  border-radius: var(--r-2);
  font-family: var(--ff-mono);
  font-size: 10px;
  color: var(--fg-body);
  word-break: break-all;
}

.edge-relation-header {
  background: var(--bg-panel);
  padding: 12px;
  border-radius: var(--r-5);
  margin-bottom: 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--fg);
  line-height: 1.5;
  word-break: break-word;
}

.self-loop-header {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--status-success-soft);
  border: 1px solid var(--status-success);
}

.self-loop-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--fg-body);
  background: var(--bg-panel-2);
  padding: 2px 8px;
  border-radius: var(--r-1);
}

.self-loop-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.self-loop-item {
  background: var(--bg-sunken);
  border: 1px solid var(--rule);
  border-radius: var(--r-5);
}

.self-loop-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-panel-2);
  cursor: pointer;
  transition: background 0.2s;
}

.self-loop-item-header:hover {
  background: var(--bg-panel-2);
}

.self-loop-item.expanded .self-loop-item-header {
  background: var(--rule-strong);
}

.self-loop-index {
  font-size: 10px;
  font-weight: 600;
  color: var(--fg-muted);
  background: var(--rule-strong);
  padding: 2px 6px;
  border-radius: var(--r-2);
}

.self-loop-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--fg);
  flex: 1;
}

.self-loop-toggle {
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--fg-muted);
  background: var(--rule-strong);
  border-radius: var(--r-3);
  transition: all 0.2s;
}

.self-loop-item.expanded .self-loop-toggle {
  background: var(--mono-600);
  color: var(--fg-body);
}

.self-loop-item-content {
  padding: 12px;
  border-top: 1px solid var(--rule);
}

.self-loop-item-content .detail-row {
  margin-bottom: 8px;
}

.self-loop-item-content .detail-label {
  font-size: 11px;
  min-width: 60px;
}

.self-loop-item-content .detail-value {
  font-size: 12px;
}

.self-loop-episodes {
  margin-top: 8px;
}

.episodes-list.compact {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 4px;
}

.episode-tag.small {
  padding: 3px 6px;
  font-size: 9px;
}

/* Design v3 detail panel polish. */
.graph-detail-panel,
.detail-row,
.self-loop-item,
.episode-tag {
  font-family: var(--font-sans, var(--ff-sans));
}
.self-loop-item-content,
.self-loop-item {
  border-color: var(--separator, var(--rule));
}
.self-loop-toggle {
  background: var(--surface-inset, var(--rule-strong));
  color: var(--text-secondary, var(--fg-muted));
}
.self-loop-item.expanded .self-loop-toggle {
  background: var(--accent-tint-bg, var(--mono-600));
  color: var(--accent-tint-text, var(--fg-body));
}
.detail-label {
  color: var(--text-secondary, var(--fg-muted));
}
.detail-value {
  color: var(--text-primary, var(--fg));
}
</style>
