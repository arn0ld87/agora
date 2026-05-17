<script setup lang="ts">
/**
 * ReportRedTeamSection (Slice 5 — Issue #497).
 *
 * Rendert red_team_findings[] aus ReportV3 als Liste mit Warn-Icon.
 * Versteckt sich automatisch wenn findings leer ist (Backward-Compat).
 * Section-Anker: id="section-red-team" für In-Page-Navigation.
 * Steht oberhalb von Datenlücken (data_gaps).
 */
import { computed } from 'vue'

interface Props {
  findings: string[]
}

const props = defineProps<Props>()

const hasFindings = computed(() => props.findings.length > 0)
</script>

<template>
  <section
    v-if="hasFindings"
    id="section-red-team"
    class="red-team-section"
    aria-label="Red-Team-Befunde"
  >
    <header class="red-team-header">
      <h3 class="red-team-title">
        Red-Team-Befunde
      </h3>
      <span
        class="red-team-tooltip"
        title="Automatische Konsens-/Widerspruchs-Prüfung"
        aria-label="Automatische Konsens-/Widerspruchs-Prüfung"
      >?</span>
    </header>
    <ul class="red-team-list" role="list">
      <li
        v-for="(finding, index) in findings"
        :key="index"
        class="red-team-item"
        data-testid="red-team-finding"
      >
        <span class="red-team-icon" aria-hidden="true">&#9888;</span>
        <span class="red-team-text">{{ finding }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.red-team-section {
  margin: var(--s-4, 16px) 0;
  border: 1px solid var(--status-warn-border, #f59e0b);
  border-radius: var(--r-1, 6px);
  padding: var(--s-3, 12px) var(--s-4, 16px);
  background: color-mix(in srgb, var(--status-warn, #f59e0b) 8%, var(--bg-elevated, #fff));
}

.red-team-header {
  display: flex;
  align-items: center;
  gap: var(--s-2, 8px);
  margin-bottom: var(--s-3, 12px);
}

.red-team-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--status-warn-fg, #92400e);
  font-family: var(--ff-mono, monospace);
}

.red-team-tooltip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1px solid var(--status-warn, #f59e0b);
  color: var(--status-warn-fg, #92400e);
  font-size: 10px;
  font-weight: 700;
  cursor: help;
  flex-shrink: 0;
}

.red-team-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--s-2, 8px);
}

.red-team-item {
  display: flex;
  align-items: flex-start;
  gap: var(--s-2, 8px);
  padding: var(--s-2, 8px) var(--s-3, 12px);
  background: color-mix(in srgb, var(--status-warn, #f59e0b) 5%, var(--bg, #f8fafc));
  border: 1px solid color-mix(in srgb, var(--status-warn, #f59e0b) 30%, transparent);
  border-radius: var(--r-1, 4px);
}

.red-team-icon {
  flex-shrink: 0;
  font-size: 14px;
  color: var(--status-warn, #f59e0b);
  line-height: 1.4;
}

.red-team-text {
  color: var(--fg-body, #1e293b);
  line-height: 1.5;
  font-size: 14px;
}
</style>
