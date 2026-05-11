<script setup lang="ts">
import { ref } from 'vue'
import Card from '@/components/v4/forms/Card.vue'
import Pill from '@/components/v4/forms/Pill.vue'
import { MOCK_ROUTING_STAGES } from './mockData'
import type { RoutingTone, StageOverrideRow } from './mockData'

// Lokale Kopie für Bearbeitung
const rows = ref<StageOverrideRow[]>(MOCK_ROUTING_STAGES.map((r) => ({ ...r })))
const dirty = ref(false)

function onCellChange() {
  dirty.value = true
}

function save() {
  dirty.value = false
  // Backend-Verdrahtung: Slice G
}

function reset() {
  rows.value = MOCK_ROUTING_STAGES.map((r) => ({ ...r }))
  dirty.value = false
}
</script>

<template>
  <Card title="Stage Overrides">
    <table class="soc-table">
      <thead>
        <tr class="soc-table__head-row">
          <th class="soc-table__th">Stage</th>
          <th class="soc-table__th">Provider</th>
          <th class="soc-table__th">Model</th>
          <th class="soc-table__th">Effort</th>
          <th class="soc-table__th">Status</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.stage"
          class="soc-table__row"
        >
          <td class="soc-table__td soc-table__td--mono">{{ row.stage }}</td>
          <td class="soc-table__td soc-table__td--secondary">{{ row.provider }}</td>
          <td class="soc-table__td soc-table__td--mono">{{ row.model }}</td>
          <td class="soc-table__td soc-table__td--secondary">{{ row.effort }}</td>
          <td class="soc-table__td">
            <Pill :tone="(row.tone as RoutingTone)">{{ row.status }}</Pill>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- CTAs -->
    <div class="soc-actions">
      <button class="soc-btn soc-btn--secondary" type="button" aria-label="Stage Override hinzufuegen">
        <svg width="12" height="12" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <line x1="10" y1="3" x2="10" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          <line x1="3" y1="10" x2="17" y2="10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
        Stage Override
      </button>
      <div class="soc-actions__right">
        <button class="soc-btn soc-btn--secondary" type="button" @click="reset">Zurücksetzen</button>
        <button class="soc-btn soc-btn--primary" type="button" @click="save">Speichern</button>
      </div>
    </div>
  </Card>
</template>

<style scoped>
.soc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.soc-table__head-row {
  color: var(--text-secondary);
  font-size: 11.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.soc-table__th {
  text-align: left;
  padding: 6px 8px;
  font-family: var(--font-sans);
}

.soc-table__row {
  border-top: 1px solid var(--separator);
}

.soc-table__td {
  padding: 10px 8px;
  font-family: var(--font-sans);
}

.soc-table__td--mono {
  font-family: var(--font-mono);
  font-size: 13px;
}

.soc-table__td--secondary {
  color: var(--text-secondary);
}

.soc-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 18px;
}

.soc-actions__right {
  display: flex;
  gap: 8px;
}

/* Inline-Buttons (kein globaler btn-Scope vorhanden) */
.soc-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 14px;
  border-radius: 8px;
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 120ms ease, border-color 120ms ease;
}

.soc-btn--primary {
  background: var(--accent, #0a84ff);
  color: #fff;
  border-color: var(--accent, #0a84ff);
}

.soc-btn--primary:hover {
  background: var(--accent-hover, #006edb);
  border-color: var(--accent-hover, #006edb);
}

.soc-btn--secondary {
  background: var(--surface-elevated, #fff);
  color: var(--text-primary);
  border-color: var(--hairline);
}

.soc-btn--secondary:hover {
  background: var(--surface-inset, #f2f2f7);
}
</style>
