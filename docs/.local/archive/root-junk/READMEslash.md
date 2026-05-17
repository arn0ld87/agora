# Agora Mai-Welle — Slash-Commands + Plan + Heuristik

**Stand:** 2026-05-14
**Quelle:** Repo-Analyse `arn0ld87/agora` Post-v1.0.0 (Dump vom 14. Mai 2026).
**Inhalt:** 17 fertige Claude-Code-Slash-Commands + Master-Orchestrator + Plan + Subagent-Heuristik.

## Was hier drin ist

```
.claude/commands/
  agora-mai-next-task.md           Master-Orchestrator (Plan-getrieben)
  fix-mai-01-mode-smokes-ci.md     Block A: P4.4 in CI
  fix-mai-02-evidence-routing.md   Block B: R4 aktivieren  [Opus-Pre-Review]
  fix-mai-03-hypotheses-slot.md    Block B: R11 voll       [Opus-Pre-Review]
  fix-mai-04-schema-drift-gate.md  Block A: --check-Flag
  fix-mai-05-voice-lint-ci.md      Block E: Wording-Gate
  fix-mai-06-retire-v2-md.md       Block D: v3 Single Source [Opus-Pre-Review, PR-Pflicht]
  fix-mai-07-quote-marker-css.md   Block E: SIM-Badge in PDF
  fix-mai-08-prompts-split.md      Block C: 508 LOC → Paket
  fix-mai-09-markdown-ts.md        Block C: letzte JS → TS
  fix-mai-10-close-issue-203.md    Block C: Issue closen
  fix-mai-11-pr-smoke-rc-only.md   Block D: PR-Smoke gated
  fix-mai-12-fork-safety.md        Block D: --preload aktiv  [Opus-Pre-Review]
  fix-mai-13-dependabot-cleanup.md Block A: mistune+pygments
  fix-mai-14-contradiction-penalty.md  Block B: Confidence-Penalty
  fix-mai-15-e2e-persona-compact.md    Block E: schnellere E2E
  fix-mai-16-status-sync-ci.md     Block F: STATUS.md gated
  fix-mai-17-radon-gate.md         Block F: Complexity-Gate
docu/
  plan.mai.md                      17 Slices, 6 Blöcke, Status-Tabelle, Reihenfolge-Diagramm
  plan.heuristic-mai.md            Subagent-Routing + Opus-Trigger pro Slice
```

## Installation ins Agora-Repo

```bash
# Im Mai-Paket (entpackt aus ZIP) und im Agora-Repo:
AGORA=/Volumes/T7/Projekte/agora

# 1) Slash-Commands rüberkopieren (existierende werden NICHT überschrieben)
cp -n .claude/commands/agora-mai-next-task.md "$AGORA/.claude/commands/"
cp -n .claude/commands/fix-mai-*.md "$AGORA/.claude/commands/"

# 2) Plan + Heuristik in docu/
cp -n docu/plan.mai.md "$AGORA/docu/"
cp -n docu/plan.heuristic-mai.md "$AGORA/docu/"

# 3) Verifizieren
ls "$AGORA/.claude/commands/" | grep -E "^(agora-mai|fix-mai-)"
ls "$AGORA/docu/" | grep "mai"
```

## Sofort-Start

In Claude Code im Agora-Repo:

```
/agora-mai-next-task
```

Der Orchestrator scannt `docu/plan.mai.md`, prüft 13 Code-Indikatoren, wählt den
ersten offenen Slice, baut den Sub-Slice-Plan, dispatcht den passenden
Subagent. Bei Layer-0- oder Persistenz-Touch macht er vorher Opus-Pre-Review.

## Heuristik in einer Tabelle

| Block | Slices | Wirkung |
|---|---|---|
| A | 01, 04, 13 | v1.0-Output-Vertrag final-locked |
| B | 02, 03, 14 | Bewertungs-Score-Hebel (R4 + R11 + Contradiction) |
| C | 08, 09, 10 | Hygiene (parallel zu B) |
| D | 06, 11, 12 | Production-Cleanup (Persistenz + Fork-Safety) |
| E | 05, 07, 15 | Bewertungs-Polish |
| F | 16, 17 | Optional (Drift-Gates) |

Innerhalb eines Blocks: **Aufwand S vor M vor L**.

## Subagent-Verteilung

| Subagent | Slices |
|---|---|
| `agora-refactor-worker` | 02, 03, 04, 05, 06, 08, 11, 12, 13, 14, 16 |
| `agora-frontend-worker` | 01, 07, 09, 15 |
| `agora-doc-worker` | 10 |
| `agora-test-worker` | 17 |

**Opus-Pre-Review-Pflicht** bei: 02, 03, 06, 12.

## Was bewusst NICHT drin ist

- Coverage-Schwellen-Anhebung (M11.2/M11.3) — eigene Roadmap.
- ADR-0001-Reversals (server-PDF, multi-user, LLM-Abstraktion).
- OASIS/CAMEL-Upgrade (PR #315 blockiert auf `camel-oasis==0.2.5`).

## Quellen im Repo

- `PLAN.md` — v1.0-Output-Vertrag (M9–M13)
- `REFACTORING_PLAN (1).md` — R1–R14 Output-Qualität
- `agora_bewertung_komplett.md` — Bewertung 2026-04
- `STATUS.md` — Test-Counts/Coverage Single Source of Truth
- `CLAUDE.md` — Subagent-Routing-Grundlagen
- `AGENTS.md` — Subagent-Knigge

## Lizenz

Dieselbe wie das Agora-Repo (intern).
