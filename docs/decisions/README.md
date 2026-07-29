# Architecture Decision Records (ADRs)

Sammlung der Architektur-Entscheidungen für Agora. Format: [MADR-Light](https://adr.github.io/madr/).

## Aktive ADRs

| Nr | Titel | Status | Slice |
|---|---|---|---|
| [0001](0001-auth-model.md) | Auth-Zielbild für v1.0 | Accepted (2026-05-04) | M10.4 |
| [0002](0002-evidence-gating.md) | Evidence-Gating für Report-Generation | Accepted (2026-05-10) | M11.7 |
| [0003](0003-pydantic-settings-migration.md) | Pydantic-Settings-Migration | Accepted (2026-05-15) | Pydantic-Settings-Epic |
| [0004](0004-cve-upstream-escalation.md) | CVE-Upstream-Eskalation: Risikoakzeptanz nltk | Accepted (2026-07-06) | ALE-20 |
| [0006](0006-ai-provider-connections.md) | Kanonische KI-Provider-Verbindungen | Proposed | Onboarding/Provider-Unification Slice 0 |
| [0007](0007-embedding-configuration-and-index-migration.md) | Embedding-Konfiguration und Indexmigration | Proposed | Onboarding/Provider-Unification Slice 0 |
| [0008](0008-single-user-profile-and-onboarding.md) | Single-User-Profil und Erst-Onboarding | Proposed | Onboarding/Provider-Unification Slice 0 |
| [0010](0010-vue-v4-route-consolidation.md) | Vue-v4-Referenzrouten und Deep-Link-Lebenszyklus | Proposed | #830 |
| [0012](0012-run-budgets.md) | Run-Budgets — Micros-Preise, Termination-Reason, ehrliche Unbekannt-Status | Accepted (2026-07-29) | #764 |

## Geplante ADRs

| Nr | Titel | Bezug |
|---|---|---|
| 0005 | Prod-Observability (JSON-Logs, Request-IDs, Metrics, Trace-Korrelation) | M13-Vorbereitung |

## Konvention

- Jede ADR bekommt eine eindeutige Nummer (4-stellig, beginnend bei `0001`).
- Status: `Proposed` → `Accepted` (nach User-Sign-off) → ggf. `Superseded by ADR-XXXX` oder `Deferred`.
- Eine ADR wird **nicht inhaltlich geändert** nach Accept — bei neuer Erkenntnis: neue ADR, die die alte supersedet.
- Querverweise auf [`PLAN.md`](../../PLAN.md), `docs/archive/plans/plan.heuristic.md` und konkreten Code-Pfaden bevorzugt.
