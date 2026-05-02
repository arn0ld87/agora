# Sub-Slice C · Wording-Glossar v1 — Restcode + Doku-Zitat + Wächter-Erweiterung

**Datum:** 2026-05-02
**Branch:** `feat/wording-glossary-slice-c` (basiert auf `feat/wording-glossary-slice-b`, der wiederum auf `claude/v0.9.0-frontend-version`)
**Refs:** GitHub-Issue #175 · Slice A (PR #176, gemergt) · Slice B (PR #177, offen)
**Auto-Close:** **ja** — `Closes #175`

## Ausgangslage

Task 13 (Time-Series-Sampling + Section-Dedup) ist auf `main` gemergt (Commit `512bd9c`). Damit ist der Slice-C-Blocker weg. Lage nach Re-Verifikation:

| Branch | `report_agent.py` | `ontology_generator.py` | `repo-review-master-remediation.md` |
|---|---|---|---|
| `main` (post-Task-13) | clean | clean | 1 Treffer (Z.27) |
| `claude/v0.9.0-frontend-version` | 4 Treffer (Z.753–757, Default-Outline-Fallback) | clean | 1 Treffer (Z.27) |

`ontology_generator.py` war bereits in einem früheren Slice gereinigt (vermutlich vor Task 13). Ich nehme es trotzdem in den Wächter-Test auf, damit es so bleibt.

`report_agent.py` ist auf main aufgrund Task-13-Refactor strukturell anders — der Default-Outline-Block in Z.753 könnte beim späteren `v0.9.0`→`main`-Merge konfligieren. Slice C fixt es jetzt im v0.9.0-Branch; der Glossar-Wächter zwingt beim Merge die Glossar-konforme Variante zu gewinnen.

## Scope dieses Sub-Slice (C)

Genau **ein Commit**:

1. `backend/app/services/report_agent.py:753–757` — Default-Outline-Fallback (`Future Prediction Report`, `Prediction Scenario and Core Findings`, `Crowd Behavior Prediction Analysis`, `Future trends ... simulation predictions`) auf Glossar-Vokabular umstellen.
2. `docu/prompts/repo-review-master-remediation.md:27` — Repo-Self-Description im Master-Remediation-Prompt: `local-first agentic prediction engine` → `local-first persona-basierter Resonanz-Simulator`.
3. `backend/tests/test_wording_glossary.py` — Wächter erweitern: source-level Pattern-Check über `report_agent.py` und `ontology_generator.py`. Macht jede zukünftige Re-Einführung der Vorhersage-Strings rot, auch ausserhalb der Modul-Konstanten.

## Verifikation

```bash
# aus Repo-Root des Slice-C-Branchs:
cd backend && uv run pytest tests/test_wording_glossary.py -q
# erwartet: 225 passed
```

Tatsächlich gemessen: **225 passed** (15 Patterns × 12 Prompt-Konstanten + 15 InsightForge + 15 × 2 Service-Files = 180 + 15 + 30).

```bash
# Manueller Cross-Check
rg -ni "future prediction|prediction scenario|prediction results|rehears|god.s eye|agentic.prediction.engine" \
   backend/app/services/ \
   docu/prompts/repo-review-master-remediation.md
```

Erwartet: keine Treffer.

**Pre-existing Failures (NICHT durch Slice C verursacht, mit `git stash` verifiziert):**

- `tests/test_report_manager.py::test_report_claim_model_keeps_legacy_fields_and_numeric_score` — `0.6 != 0.65`, Float-Vergleich (Drift seit Sub-Slice 08, dokumentiert vom parallelen Slice-13-Lauf).
- `tests/test_ontology_generator.py::*` (3 Tests) — `LLM_API_KEY not configured` in lokalem Setup; CI hat env var, also CI-grün.

Voller Test-Lauf abzüglich dieser 4 vorbestehenden Failures: **1126 passed, 9 skipped**.

## Folgeschritte

- PR #177 (Slice B) zuerst mergen, dann Slice C — beide Branches stacken.
- Nach Slice-C-Merge: Issue #175 schliesst auto via `Closes #175` im Commit-Body.
- Wenn `claude/v0.9.0-frontend-version` später nach `main` gemergt wird, trifft der Wächter-Test in CI sicher — Glossar-konforme Strings gewinnen.

## Geänderte Dateien

- `backend/app/services/report_agent.py` — 1 Edit (Default-Outline-Fallback)
- `docu/prompts/repo-review-master-remediation.md` — 1 Edit (Repo-Self-Description)
- `backend/tests/test_wording_glossary.py` — Wächter erweitert um Service-File-Source-Check
- `docu/2026-05-02-wording-glossar-slice-c-arbeitsprotokoll.md` — dieses Protokoll
