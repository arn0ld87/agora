<script setup lang="ts">
import Card from '@/components/v4/forms/Card.vue'
import Pill from '@/components/v4/forms/Pill.vue'
import { MOCK_STAGE_STATUS } from './mockData'
import type { RoutingTone } from './mockData'
</script>

<template>
  <Card title="Aktive Snapshots">
    <!-- Version-Pills -->
    <div class="asc-pills">
      <Pill tone="blue" :dot="false">
        Configured routing version:&nbsp;<b>8</b>
      </Pill>
      <Pill tone="purple" :dot="false">
        Active snapshot version:&nbsp;<b>7</b>
      </Pill>
    </div>

    <!-- Info-Banner -->
    <div class="asc-info-banner">
      <svg class="asc-info-icon" width="14" height="14" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M10 2L18 17H2L10 2Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>
        <line x1="10" y1="9" x2="10" y2="13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
        <circle cx="10" cy="15.5" r="0.8" fill="currentColor"/>
      </svg>
      <span>
        Laufende Stages sind für die Ausführung gesperrt. Änderungen gelten für noch nicht gestartete Stages.
      </span>
    </div>

    <!-- Stage-Status-Tabelle -->
    <table class="asc-table">
      <thead>
        <tr class="asc-table__head-row">
          <th class="asc-table__th">Stage</th>
          <th class="asc-table__th">Status</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in MOCK_STAGE_STATUS"
          :key="row.stage"
          class="asc-table__row"
        >
          <td class="asc-table__td asc-table__td--mono">{{ row.stage }}</td>
          <td class="asc-table__td">
            <Pill :tone="(row.tone as RoutingTone)">{{ row.status }}</Pill>
          </td>
        </tr>
      </tbody>
    </table>
  </Card>
</template>

<style scoped>
.asc-pills {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.asc-info-banner {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--accent-tint-bg, rgba(10, 132, 255, 0.08));
  color: var(--text-secondary);
  font-size: 13px;
  margin-bottom: 14px;
  line-height: 1.45;
}

.asc-info-icon {
  flex: none;
  margin-top: 1px;
  color: var(--accent, #0a84ff);
}

.asc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.asc-table__head-row {
  color: var(--text-secondary);
  font-size: 11.5px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.asc-table__th {
  text-align: left;
  padding: 6px 8px;
  font-family: var(--font-sans);
}

.asc-table__row {
  border-top: 1px solid var(--separator);
}

.asc-table__td {
  padding: 10px 8px;
  font-family: var(--font-sans);
}

.asc-table__td--mono {
  font-family: var(--font-mono);
}
</style>
