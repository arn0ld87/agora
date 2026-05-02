# Sub-Slice A · Wording-Glossar v1 verankern

**Datum:** 2026-05-02
**Branch:** `feat/wording-glossary` (Worktree `/mnt/brain/Projekte/Agora-wording`)
**Refs:** GitHub-Issue #175 · CLAUDE.md Layer 2 (Prompt-Semantik)
**Auto-Close:** **nein** — #175 schließt erst nach Sub-Slice C (Restcode + Doku-Zitate)

## Ausgangslage

Repo enthält an mehreren Stellen US-Marketing- und „Crystal-Ball"-Vokabular, das nicht zur sachlichen DACH-Außendarstellung passt und das LLM in einen Vorhersage-Frame zieht. CLAUDE.md führt das bereits unter „Verboten" („revolutionary", „seamless", „prediction of the future"), aber ohne verbindliches Glossar mit EN-Code-Equivalenten.

Verifikation via `rg`:

- `README.md:7` — Tagline `Local-first, cloud-compatible Agentic-Prediction-Engine.`
- `backend/app/services/report_prompts.py` — 13 Treffer (Hot-Spot Layer 2)
- `backend/app/services/graph_tools.py:171–175` — Markdown-Header im Report
- `backend/app/services/report_agent.py` — mehrere
- `backend/app/services/ontology_generator.py` — wenige
- `docu/prompts/repo-review-master-remediation.md:27` — Zitatblock

Frontend: keine Treffer. Historische Logs unter `docu/logs/`: bewusst ausgespart (Zeitdokumente).

Parallel läuft Task 13 (Time-Series-Sampling + Section-Dedup) im Worktree `/tmp/agora-task-13` an `report_agent.py` → Sub-Slice C wartet auf Merge, Slice A+B sind kollisionsfrei.

## Scope dieses Sub-Slice (A)

Genau **ein Commit**, kleinster ehrlicher Schritt zu Issue #175:

1. Glossar als Single-Source-of-Truth anlegen (`docu/glossary-wording.md`) mit EN- und DE-Spalte plus Verifikations-Snippet.
2. README-Tagline (Zeile 7) ersetzen: `Local-first, cloud-kompatibler Persona-basierter Resonanz-Simulator.` Sprache bleibt Mischsprache wie der Rest der README — Tagline ist die Außendarstellung, also DE.
3. Lokale CLAUDE.md (gitignored) um Glossar-Verweis ergänzen — separat im Hauptrepo, nicht in diesem Commit.

**Out of Scope (folgt in B/C):**

- B: `report_prompts.py` und `graph_tools.py:171–175` (Layer 2, Snapshot-Tests müssen mitziehen).
- C: `report_agent.py`, `ontology_generator.py`, `docu/prompts/repo-review-master-remediation.md`. **C blockiert durch Task 13.**

## Verifikation

```bash
cd /mnt/brain/Projekte/Agora-wording
rg -ni "agentic-prediction-engine|prediction|rehears|high.fidelity|god.s eye|public opinion" \
   README.md docu/ \
   --glob '!docu/logs/**' --glob '!docu/glossary-wording.md'
```

**Erwartet nach Slice A:** nur noch der eine Treffer in `docu/prompts/repo-review-master-remediation.md:27` (gehört zu Slice C).

**Tatsächlich gemessen:** identisch — alle übrigen Treffer in README/docu sind weg.

## Folgeschritte

- Sub-Slice B sofort starten (kollisionsfrei).
- Sub-Slice C nach Merge von Task 13.
- Issue-Milestone-Counter beim Slice-Abschluss-PR pflegen.

## Geänderte Dateien

- `docu/glossary-wording.md` (neu)
- `README.md` (Zeile 7)
- `docu/2026-05-02-wording-glossar-slice-a-arbeitsprotokoll.md` (dieses Protokoll)
