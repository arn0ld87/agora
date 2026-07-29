<script setup lang="ts">
/**
 * Chart — standardisierter Card-Container für D3-Visualisierungen
 * Slice UI-B · 2026-05-15
 *
 * Use-Case: Risk-Verlauf, Confidence-Histogramm, Mood-Timeline, …
 *
 * Diese Komponente enthält **keine** Chart-Logik. Sie liefert ausschließlich
 * den standardisierten Header (Titel, Beschreibung, Zeitraum, Einheit) und
 * den Footer (Interpretation). Das eigentliche Rendering passiert im
 * default-Slot — typischerweise eine eigene `<XyzChart>`-Komponente, die D3
 * gegen ein SVG mountet.
 *
 * Pflichtfelder pro UI-Rule:
 * - title: Pflicht
 * - timeRange: Pflicht bei Zeitserien (sonst undefined)
 * - unit: Pflicht bei numerischen Werten (sonst undefined)
 * - interpretation: Pflicht bei nicht-trivialen Daten (sonst undefined)
 *
 * Die Pflichten werden runtime nicht erzwungen — sind aber durch den Header-
 * Layout-Slot strukturell sichtbar, sodass Reviewer fehlende Felder sofort
 * bemerken.
 */

export interface ChartLabels {
  /** Label für die timeRange-Metazeile (Default: "Zeitraum") */
  timeRange: string
  /** Label für die unit-Metazeile (Default: "Einheit") */
  unit: string
  /** Screenreader-Text während loading=true (Default: "Lade Chart…") */
  loading: string
}

withDefaults(
  defineProps<{
    /** Chart-Titel — Pflicht */
    title: string
    /** Kurze Beschreibung, was die Achse/Aggregation zeigt */
    description?: string
    /** Zeitraum-Label (z. B. "Jan – Jun 2026", "letzte 7 Tage") */
    timeRange?: string
    /** Einheit der Y-Achse (z. B. "%", "Risiko-Index 0–100") */
    unit?: string
    /** Interpretation/Fazit unter dem Chart */
    interpretation?: string
    /** Lade-Zustand: zeigt Skeleton-Placeholder statt Slot */
    loading?: boolean
    /** Mindest-Höhe für die Slot-Region */
    minHeight?: string
    /**
     * UI-Labels für i18n. Konsument übergibt `t('chart.timeRange')` etc.;
     * Default sind deutsche Strings ("Zeitraum", "Einheit", "Lade Chart…").
     */
    labels?: Partial<ChartLabels>
  }>(),
  {
    description: undefined,
    timeRange: undefined,
    unit: undefined,
    interpretation: undefined,
    loading: false,
    minHeight: '240px',
    // Inline-Default — withDefaults darf keine Outer-Scope-Refs in Functions referenzieren.
    labels: () => ({
      timeRange: 'Zeitraum',
      unit: 'Einheit',
      loading: 'Lade Chart…',
    }),
  },
)

defineSlots<{
  default: () => unknown
  /** Optional: rechts oben im Header, z. B. Range-Picker */
  toolbar: () => unknown
  /** Optional: Legende unter dem Chart, vor Interpretation */
  legend: () => unknown
}>()
</script>

<template>
  <section class="ch-root">
    <header class="ch-header">
      <div class="ch-titles">
        <h3 class="ch-title">{{ title }}</h3>
        <p v-if="description" class="ch-description">{{ description }}</p>
      </div>

      <div v-if="$slots.toolbar" class="ch-toolbar">
        <slot name="toolbar" />
      </div>
    </header>

    <div v-if="timeRange || unit" class="ch-meta">
      <span v-if="timeRange" class="ch-meta-item">
        <span class="ch-meta-label">{{ labels?.timeRange ?? 'Zeitraum' }}</span>
        <span class="ch-meta-value">{{ timeRange }}</span>
      </span>
      <span v-if="unit" class="ch-meta-item">
        <span class="ch-meta-label">{{ labels?.unit ?? 'Einheit' }}</span>
        <span class="ch-meta-value">{{ unit }}</span>
      </span>
    </div>

    <div class="ch-canvas" :style="{ minHeight }">
      <div v-if="loading" class="ch-loading" role="status" aria-busy="true" aria-live="polite">
        <span class="ch-sr-only">{{ labels?.loading ?? 'Lade Chart…' }}</span>
        <div class="ch-skeleton-bar" />
        <div class="ch-skeleton-bar ch-skeleton-bar--mid" />
        <div class="ch-skeleton-bar ch-skeleton-bar--short" />
      </div>
      <slot v-else />
    </div>

    <div v-if="$slots.legend" class="ch-legend">
      <slot name="legend" />
    </div>

    <p v-if="interpretation" class="ch-interpretation">
      {{ interpretation }}
    </p>
  </section>
</template>

<style scoped>
.ch-root {
  background: var(--surface-elevated);
  border: 1px solid var(--hairline);
  border-radius: var(--r-3, 6px);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-family: var(--font-sans);
  color: var(--text-secondary);
}

.ch-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.ch-titles {
  flex: 1 1 auto;
  min-width: 0;
}

.ch-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.ch-description {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.ch-toolbar {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ch-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 8px 0;
  border-top: 1px solid var(--separator);
  border-bottom: 1px solid var(--separator);
  font-size: 12px;
}

.ch-meta-item {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}

.ch-meta-label {
  color: var(--text-tertiary);
  text-transform: uppercase;
  font-size: 10.5px;
  letter-spacing: 0.04em;
  font-weight: 500;
}

.ch-meta-value {
  color: var(--text-secondary);
  font-weight: 500;
}

.ch-canvas {
  position: relative;
  width: 100%;
}

.ch-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
}

.ch-interpretation {
  margin: 0;
  padding-top: 10px;
  border-top: 1px solid var(--separator);
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

/* ── Loading-Skeleton ────────────────────────────────────── */

.ch-loading {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 8px;
  height: 100%;
  min-height: inherit;
  padding: 12px;
}

.ch-skeleton-bar {
  height: 16px;
  background: linear-gradient(
    90deg,
    var(--surface-inset) 0%,
    var(--surface-hover) 50%,
    var(--surface-inset) 100%
  );
  background-size: 200% 100%;
  animation: ch-shimmer 1.4s ease-in-out infinite;
  border-radius: var(--r-1, 3px);
  width: 100%;
}

.ch-skeleton-bar--mid {
  width: 75%;
}

.ch-skeleton-bar--short {
  width: 40%;
}

.ch-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

@keyframes ch-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ch-skeleton-bar {
    animation: none;
    background: var(--surface-inset);
  }
}
</style>
