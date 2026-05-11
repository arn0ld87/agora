# Sub-Slice B · Wording-Glossar v1 in Prompt-Layer + Graph-Tools

**Datum:** 2026-05-02
**Branch:** `feat/wording-glossary` (Folge auf Slice A)
**Refs:** GitHub-Issue #175 · CLAUDE.md Layer 2 (Prompt-Semantik) · Slice A (Commit `3983c82`/`c4fffc1`)
**Auto-Close:** **nein** — #175 schliesst erst nach Sub-Slice C

## Ausgangslage

Slice A hat das Glossar in `docs/glossary-wording.md` und die README-Tagline verankert. Die eigentliche Wirkung des Glossars liegt aber im LLM-Prompt-Layer (Layer 2 in CLAUDE.md): solange `report_prompts.py` „future prediction reports", „rehearsal of the future" und „god's eye view" sagt, schreibt der Report-Agent weiter im Vorhersage-Frame.

Verifikation der Treffer (vor Slice B):

- `backend/app/services/report_prompts.py` — 13 Treffer in 4 Konstanten (PLAN_SYSTEM, PLAN_USER, SECTION_SYSTEM, CHAT_SYSTEM)
- `backend/app/services/graph_tools.py:171–177` — Markdown-Header und Statistik-Labels in `InsightForgeResult.to_text()`, die 1:1 in den exportierten Report wandern

Test-Voraussetzung geprüft: `tests/test_report_prompts.py` validiert nur Existenz, Platzhalter und Format-Aufrufbarkeit — kein Wortlaut-Snapshot. → kein Test-Bruch durch Wording-Tausch erwartet.

Pre-existing Failure ausserhalb des Scope: `tests/test_report_manager.py::test_report_claim_model_keeps_legacy_fields_and_numeric_score` (`0.6 != 0.65`, Floating-Point-Vergleich). Mit `git stash` verifiziert: bricht auch ohne Slice-B-Änderungen.

## Scope dieses Sub-Slice (B)

Genau **ein Commit**:

1. `backend/app/services/report_prompts.py` — alle 13 Treffer nach Glossar-Mapping ersetzen, Format-Platzhalter unverändert lassen.
2. `backend/app/services/graph_tools.py:171–177` — Header `## Future Prediction Deep Analysis` → `## Scenario Evaluation Deep Analysis`, Labels analog.
3. `backend/tests/test_wording_glossary.py` (neu) — Glossar-Wächter: parametrisierte Tests gegen 15 verbotene Patterns × 12 Prompt-Konstanten + `InsightForgeResult.to_text()`. Macht jede zukünftige Re-Einführung der Vorhersage-Phrasen rot.

**Out of Scope (Slice C):**

- `report_agent.py` (blockiert durch Task 13 — `feat/layer-3-task-13-timeseries-sampling-section-dedup`)
- `ontology_generator.py`
- `docs/prompts/repo-review-master-remediation.md`

## Mapping (vollständig, EN→EN)

| Vorher | Nachher |
|---|---|
| `future prediction reports?` | `scenario evaluation reports?` |
| `god's eye view` | `analytical observer perspective` |
| `rehearsal of the future` | `structured test of our assumptions` |
| `simulated world` | `simulated environment` |
| `predictions of future human behavior` | `simulated persona reactions` |
| `Prediction Scenario Settings` | `Scenario Evaluation Settings` |
| `Prediction Scenario` (Header) | `Evaluation Scenario` |
| `prediction results` / `core prediction findings` | `evaluation results` / `core evaluation findings` |
| `Sample of Some Future Facts Predicted by Simulation` | `Sample of Persona Observations Produced by the Simulation` |
| `examine this future rehearsal from a god's eye view` | `examine this scenario evaluation from an analytical observer perspective` |
| `simulation prediction assistant` | `scenario evaluation assistant` |
| `Prediction Condition` | `Evaluation Condition` |
| `Future Prediction Deep Analysis` | `Scenario Evaluation Deep Analysis` |
| `Prediction Data Statistics` | `Evaluation Data Statistics` |
| `Related Prediction Facts` | `Related Simulation Facts` |
| `core evidence of simulation predictions` | `core evidence of the simulation observations` |
| `What happened in the future` / `how the future will unfold` | `How the scenario unfolds under those conditions` |
| `future trends` (substantivisch) | `emerging trends` |

## Verifikation

```bash
# aus dem Repo-Root des feat/wording-glossary-Branchs:
cd backend && uv run pytest tests/test_wording_glossary.py tests/test_report_prompts.py -q
# erwartet: 242 passed
```

Tatsächlich gemessen: **242 passed** (15 Patterns × 12 Prompt-Konstanten = 180 Wächter-Tests + 15 für `InsightForgeResult.to_text()` + 47 bestehende Prompt-Tests).

```bash
# Manuelle Cross-Check: keine Glossar-Verstoesse mehr in den beiden Files
rg -ni "future prediction|prediction scenario|prediction results?|rehears|god.s eye|prediction data|prediction facts?" \
   backend/app/services/report_prompts.py backend/app/services/graph_tools.py
```

Erwartet: keine Treffer.

## Folgeschritte

- Slice C nach Merge von Task 13.
- Wenn jemand das Glossar erweitern will: Patterns in `tests/test_wording_glossary.py:FORBIDDEN_PATTERNS` ergänzen — der Test parametrisiert sich selbst.

## Geänderte Dateien

- `backend/app/services/report_prompts.py` — 4 Edits in 4 Prompt-Konstanten
- `backend/app/services/graph_tools.py` — 1 Edit in `InsightForgeResult.to_text()`
- `backend/tests/test_wording_glossary.py` — neu, Glossar-Wächter
- `docs/2026-05-02-wording-glossar-slice-b-arbeitsprotokoll.md` — dieses Protokoll
