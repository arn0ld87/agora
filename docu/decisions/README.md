# Architecture Decision Records (ADRs)

Sammlung der Architektur-Entscheidungen für Agora. Format: [MADR-Light](https://adr.github.io/madr/).

## Aktive ADRs

| Nr | Titel | Status | Slice |
|---|---|---|---|
| [0001](0001-auth-model.md) | Auth-Zielbild für v1.0 | Proposed | M10.4 |

## Geplante ADRs

| Nr | Titel | Bezug |
|---|---|---|
| 0002 | CVE-Upstream-Eskalation (Vendoring / Soft-Fork / Replacement) | Hardstop 2026-07-30, [`docu/dependency-risk-register.md`](../dependency-risk-register.md) |
| 0003 | Prod-Observability (JSON-Logs, Request-IDs, Metrics, Trace-Korrelation) | M13-Vorbereitung |

## Konvention

- Jede ADR bekommt eine eindeutige Nummer (4-stellig, beginnend bei `0001`).
- Status: `Proposed` → `Accepted` (nach User-Sign-off) → ggf. `Superseded by ADR-XXXX` oder `Deferred`.
- Eine ADR wird **nicht inhaltlich geändert** nach Accept — bei neuer Erkenntnis: neue ADR, die die alte supersedet.
- Querverweise auf [`PLAN.md`](../../PLAN.md), [`docu/plan.heuristic.md`](../plan.heuristic.md) und konkreten Code-Pfaden bevorzugt.
