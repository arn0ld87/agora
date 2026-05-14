# Mai-Welle — Plan & Status

**Stand:** 2026-05-14
**Bezug:** Post-v1.0.0-Restwelle. Nicht im v1.0-Output-Vertrag-Plan (`PLAN.md`) abgedeckt, aber aus der Repo-Analyse vom 14. Mai 2026 als ergänzender Cleanup-/Härtungs-Block hervorgegangen.
**Zweck:** Single Source of Truth für die 17 Mai-Slices. Reihenfolge, Status, Files, Issue-Bezug. Subagent-Mapping in [`plan.heuristic-mai.md`](plan.heuristic-mai.md). Orchestrator: [`/agora-mai-next-task`](../.claude/commands/agora-mai-next-task.md).

---

## Status-Legende

| Symbol | Bedeutung |
|---|---|
| 🔴 | offen — noch nichts begonnen |
| 🟡 | begonnen — Worktree existiert, Tests rot oder unvollständig |
| 🟢 | durch — auf `main`, Akzeptanz erfüllt |
| ⏸️ | pausiert — blockiert auf Upstream/User-Entscheidung |

---

## Slices in Reihenfolge

### Block A — Output-Vertrag final dichtmachen

| Slice | Status | Titel | Aufwand | Files | Refs / Closes |
|---|---|---|---|---|---|
| MAI-01 | ✅ | P4.4 Mode-Smokes in CI verdrahten | S | `.github/workflows/e2e-smokes.yml` | Refs PLAN.md §5.4 |
| MAI-04 | 🔴 | Schema-Drift-Gate `--check` | S | `backend/app/contracts/dump_schemas.py`, `.github/workflows/contract-gates.yml` | Refs R12 |
| MAI-13 | 🔴 | Dependabot #323 + #326 mergen | S | `backend/uv.lock` | Closes #323, Closes #326 |

### Block B — Bewertungs-Score-Hebel

| Slice | Status | Titel | Aufwand | Files | Refs / Closes |
|---|---|---|---|---|---|
| MAI-02 | 🔴 | R4 Evidence-Routing in Hypotheses/DataGaps | M | `backend/app/services/report_agent/agent.py`, `backend/app/services/report_agent/workflow.py`, `backend/app/contracts/report_contract.py` | Refs R4 |
| MAI-03 | 🔴 | R11 Hypothesen-Slot voll integrieren | M | `backend/app/services/report_agent/sections.py`, `backend/app/services/report_agent/manager.py`, `backend/app/contracts/report_v3.py`, `frontend/src/contracts/reportV3Contract.ts` | Refs R11 |
| MAI-14 | 🔴 | Confidence-Contradiction-Penalty | S | `backend/app/services/confidence_calculator.py`, `backend/tests/test_confidence_calculator.py` | Refs Bewertung §10 |

### Block C — Hygiene parallel zu B

| Slice | Status | Titel | Aufwand | Files | Refs / Closes |
|---|---|---|---|---|---|
| MAI-08 | 🔴 | `report_prompts.py` Paket-Split | M | `backend/app/services/report_prompts.py` → Paket | Refs R13 |
| MAI-09 | 🔴 | `markdown.js` → `markdown.ts` | S | `frontend/src/utils/markdown.js` | Refs R14 |
| MAI-10 | 🔴 | Issue #203 schließen | S | — (reine Doku) | Closes #203 |

### Block D — Production-Cleanup

| Slice | Status | Titel | Aufwand | Files | Refs / Closes |
|---|---|---|---|---|---|
| MAI-06 | 🔴 | v2-`full_report.md` retiren | L | `backend/app/services/report_agent/manager.py`, `backend/scripts/migrate_v2_full_report_to_v3.py` | Refs ADR-0001 |
| MAI-12 | 🔴 | Fork-Safety `register_at_fork` + `--preload` | M | `backend/app/__init__.py`, `backend/run.py`, `backend/Dockerfile` | Refs CLAUDE.md Hot-Spots |
| MAI-11 | ✅ | PR-Smoke nur auf RC/Release | S | `.github/workflows/docker-image.yml` | Refs STATUS.md 2026-05-06 |

### Block E — Bewertungs-Polish

| Slice | Status | Titel | Aufwand | Files | Refs / Closes |
|---|---|---|---|---|---|
| MAI-05 | 🔴 | Voice-Lint CI-Pflicht | S | `backend/scripts/check_voice.py`, `.github/workflows/contract-gates.yml` | Refs Task 11 PLAN.md |
| MAI-07 | 🔴 | Quote-Marker CSS im Standalone-HTML | S | `frontend/src/composables/useReportExports.ts`, `frontend/src/utils/markdown.ts` | Refs P3.3 |
| MAI-15 | 🔴 | E2E mit `persona_detail_level=compact` | S | `.github/workflows/e2e-smokes.yml`, `backend/app/utils/llm_e2e_stub.py` | Refs Issue #217 |

### Block F — Optional / Nice-to-have

| Slice | Status | Titel | Aufwand | Files | Refs / Closes |
|---|---|---|---|---|---|
| MAI-16 | ✅ | `sync-status.sh --check` als CI-Pflicht | S | `scripts/sync-status.sh`, `.github/workflows/ci.yml` | Refs Phase 6 |
| MAI-17 | ✅ | `radon` Komplexitäts-Gate | S | `.github/workflows/contract-gates.yml`, `backend/radon-allowlist.txt` | Refs M11.5 |

---

## Reihenfolge-Diagramm

```text
MAI-01 ──┐
MAI-04 ──┼── Block A (parallel-fähig, 1 Tag)
MAI-13 ──┘
            │
            ▼
MAI-02 ──┐
MAI-03 ──┼── Block B (Sequenz: 02 → 03 → 14; MAI-03 hängt an MAI-02 wegen Hypothesen-Persistenz)
MAI-14 ──┘
            │
            ▼  (Block C parallel zu Block B)
MAI-08 ──┐
MAI-09 ──┼── Block C
MAI-10 ──┘
            │
            ▼
MAI-06 ──┐
MAI-12 ──┼── Block D (Persistenz/Pool — Opus-Pre-Review-Pflicht für 06+12)
MAI-11 ──┘
            │
            ▼
MAI-05 ──┐
MAI-07 ──┼── Block E
MAI-15 ──┘
            │
            ▼
MAI-16 ──┐
MAI-17 ──┘  Block F (rein optional, kein v1.0-Blocker)
```

---

## Bewertungslogik

- **Priorität** ergibt sich aus Block (A > B > C > D > E > F) und innerhalb des Blocks aus Aufwand (S vor M vor L).
- **Risiko niedrig** → Direkt-Push auf `main` per FF nach Verify.
- **Risiko mittel/hoch** → PR mit Gemini-Findings-Sichtung vor Merge (`gh api repos/.../pulls/<N>/reviews`).
- **Layer-0-Touch oder Persistenz-Touch** → Opus-Pre-Review-Pflicht (siehe Heuristik).

---

## Akzeptanz auf Block-Ebene

| Block | Pflicht-Verify | Block-Abschluss-Doku |
|---|---|---|
| A | `gh workflow run e2e-smokes.yml` zeigt 4 Jobs grün, `dump_schemas --check` blockiert Drift, `uv.lock` ohne offene Mai-Dependabot-Bumps | `docu/2026-05-XX-mai-blockA-abschluss.md` |
| B | `pytest tests/services/test_evidence_routing.py` grün, Snapshot-Diff committed, `report-v3.schema.json` enthält `hypotheses` | `docu/2026-05-XX-mai-blockB-abschluss.md` |
| C | `find backend/app/services/report_prompts.py` leer (nur Paket), `find frontend/src/utils -name "*.js"` leer, `gh issue view 203` state=CLOSED | `docu/2026-05-XX-mai-blockC-abschluss.md` |
| D | Neuer Smoke-Report unter `uploads/reports/` ohne `full_report.md`, einfaches `Neo4j storage initialized`-Log, PR-Smoke-Workflow nicht mehr auf Feature-PRs | `docu/2026-05-XX-mai-blockD-abschluss.md` |
| E | Voice-Lint fail-trigger bewusst getestet, Print-PDF-Screenshot mit SIM-Badge im Worklog, E2E-Laufzeit-Vergleich | `docu/2026-05-XX-mai-blockE-abschluss.md` |
| F | `sync-status.sh --check` failt bei manueller Drift, `radon cc --min C` ohne neue Funde | `docu/2026-05-XX-mai-blockF-abschluss.md` |

---

## Was bewusst NICHT in dieser Welle ist

- **Coverage-Schwellen-Anhebung** (M11.2/M11.3) — läuft monatlich +2 % auf eigener Roadmap, kein Mai-Slice.
- **Server-seitiges PDF-Rendering** — ADR-0001-Entscheidung, Browser-Print bleibt kanonisch.
- **Multi-User-Auth-Rewrite** — ADR-0001 Single-User-only-v1 Accepted.
- **LLM-Provider-Abstraktion neu** — Strict-JSON-Mode ist bereits drin.
- **OASIS/CAMEL-Upgrade** — `camel-oasis==0.2.5` Pin bleibt, PR #315 blockiert.

---

## Aktualisierungs-Protokoll

- 2026-05-14: Plan initial angelegt nach Repo-Dump-Analyse. 17 Slices identifiziert, in 6 Blöcke gruppiert, Reihenfolge nach Risiko × Wirkung.

---

## Referenzen

- [`PLAN.md`](../PLAN.md) — v1.0-Output-Vertrag-Plan (M9–M13)
- [`docu/STATUS.md`](STATUS.md) — Test-Counts, Coverage, Layer-Status (Single Source of Truth)
- [`REFACTORING_PLAN (1).md`](../REFACTORING_PLAN%20(1).md) — Output-Qualität-Stufenplan R1–R14
- [`agora_bewertung_komplett.md`](../agora_bewertung_komplett.md) — Bewertung 2026-04
- [`plan.heuristic-mai.md`](plan.heuristic-mai.md) — Subagent-Mapping
- [`.claude/commands/agora-mai-next-task.md`](../.claude/commands/agora-mai-next-task.md) — Orchestrator
- [`.claude/commands/fix-mai-*.md`](../.claude/commands/) — Slice-Detail-Briefs
