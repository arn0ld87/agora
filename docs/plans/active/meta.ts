/**
 * Kinder chronologisch nach Dateiname ( ADR-Nummern / Datums-Präfixe ).
 * Statische Seitenreihenfolge ( numerische Präfixe wie 2026-… kollidieren sonst
 * als Sidebar-Order → BLUME_DUPLICATE_SIDEBAR_ORDER ). Neue Dateien erscheinen
 * automatisch nach den hier gelisteten.
 */
export default {
  pages: [
  "05-15-observability-slice-1",
  "05-15-observability-slice-2-metrics",
  "05-15-observability-slice-3-logs-correlation",
  "05-15-observability-slice-4-slos-alerts"
],
};
