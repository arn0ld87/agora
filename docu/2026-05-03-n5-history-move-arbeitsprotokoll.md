# Arbeitsprotokoll N5 — Veraltete Repo-Root-Audits nach `docu/history/`

**Datum:** 2026-05-03  
**Slice:** M9-1.5 / N5  
**Subagent:** agora-doc-worker (Haiku)  
**Branch:** chore/n5-history-move  
**Refs:** PLAN.md F13 (Doku-Fragmentierung)

## Problem

Vier historische Audit-Dateien lagen im Repo-Root (`agora_*.md`) und veralteten mit jedem Slice. Die Dateien enthielten Behauptungen, die gegen aktuellen Code falsch waren (z. B. „kein DOMPurify", „kein Vitest in CI" — beides längst behoben). Neue Reviewer generierten falsche Erwartungen.

## Änderungen

### 1. Datei-Verschiebung

| Alt (Repo-Root) | Neu (`docu/history/`) |
|---|---|
| `agora_evidence_pipeline_testfall.md` | `docu/history/2026-04-2x-evidence-pipeline-testfall.md` |
| `agora_json_evdence_review.md` | `docu/history/2026-04-2x-json-evidence-review.md` |
| `agora_repo_review_neuer_stand.md` | `docu/history/2026-04-2x-repo-review-neuer-stand.md` |
| `agora_repository_review.md` | `docu/history/2026-04-2x-repository-review.md` |

### 2. Header-Caveat

Jede verschobene Datei bekam einen Header:

> **HISTORISCHER SNAPSHOT (Stand 2026-04-2x).**  
> Aktueller Stand siehe: `CLAUDE.md` / `PLAN.md` / `docu/STATUS.md`  
> Diese Datei wurde aus dem Repo-Root nach `docu/history/` verschoben.

### 3. Link-Check

`README.md` und `CLAUDE.md` enthalten keine Hardlinks auf die alten Dateinamen — keine Nacharbeit nötig.

## Akzeptanz

```bash
find . -maxdepth 1 -name "agora_*.md"  # → leer
ls docu/history/ | wc -l                # → ≥ 4
```

## Offen

- Merge auf `main` per FF nach 90 s Wartezeit + CI-Prüfung.
