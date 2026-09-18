/**
 * Kinder chronologisch nach Dateiname ( ADR-Nummern / Datums-Präfixe ).
 * Statische Seitenreihenfolge ( numerische Präfixe wie 2026-… kollidieren sonst
 * als Sidebar-Order → BLUME_DUPLICATE_SIDEBAR_ORDER ). Neue Dateien erscheinen
 * automatisch nach den hier gelisteten.
 */
export default {
  pages: [
  "auth-model",
  "evidence-gating",
  "supersedes",
  "pydantic-settings-migration",
  "cve-upstream-escalation",
  "ai-provider-connections",
  "embedding-configuration-and-index-migration",
  "single-user-profile-and-onboarding",
  "unified-model-picker",
  "vue-v4-route-consolidation",
  "evidence-entailment-and-provenance",
  "run-budgets",
  "seed-corpus-document-anchor",
  "README"
],
};
