# Arbeitsprotokoll — M11.8b: Output-Contract-Snapshot (schlank)

**Datum:** 2026-05-09
**Slice:** M11.8b — Output-Contract-Snapshot (schlank)
**Branch:** feat/m11-8b-output-contract-snapshot

## Ziel

Den im PR #334 verankerten Output-Vertrag (`docu/2026-05-09-output-vertrag-bewertung-evidence-quality.md`) maschinenprüfbar machen, ohne den vollen Eval-Korpus (seed.md / prompt.md / pdf / evidence.json) zu benötigen — die liegen aktuell nicht im Repo.

Stattdessen: gepinnter Snapshot-Test gegen die bereits eingecheckte `DEFAULT_REPORT_SECTIONS` (PR #335 / `backend/app/services/report_prompts.py`) und eine neue Konstante `MIN_PERSONA_TABLE_ROWS`.

## Begründung für schlanken Cut

Eval-Korpus (seed.md, prompt.md, agora_1.pdf, evidence.json) liegt aktuell nicht im Repo. Schlanker Snapshot gegen DEFAULT_REPORT_SECTIONS deckt das Drift-Risiko ab; voller Eval-Pfad wartet auf separate Korpus-Einchecken-Slice.

## Geänderte Dateien

| Datei | Art | Beschreibung |
|---|---|---|
| `backend/app/services/report_agent/contract_constants.py` | NEU | `MIN_PERSONA_TABLE_ROWS=50` — Mengengerüst aus §6.1 des Output-Vertrags |
| `backend/app/services/report_agent/__init__.py` | geändert | Re-Export `MIN_PERSONA_TABLE_ROWS` aus `contract_constants` |
| `backend/tests/eval/snapshots/output-contract-required-sections.txt` | NEU | 11-Zeilen-Snapshot der Pflichtabschnitte |
| `backend/tests/eval/test_output_contract_snapshot.py` | NEU | 4 Snapshot-Tests (Titles, Descriptions, Count, MIN_PERSONA_TABLE_ROWS) |
| `CHANGELOG.md` | geändert | `[Unreleased] ### Added` Eintrag M11.8b |
| `docu/STATUS.md` | zu syncen | `sync-status.sh` läuft nach Commit |

## Out-of-Scope

- ReportV3-DTOs (M11.8c)
- chat_json Strict-Schema (M11.8d)
- Quote-Markup (M11.8e)
- Echter Eval-Korpus mit seed/prompt/pdf/json — User checkt separat ein
- Pydantic-/Layer-0-Änderungen

## Verifikation

Alle Pflicht-Schritte grün:

1. Schema-Drift clean (`git diff --exit-code schemas/`)
2. Snapshot-Datei 11 Zeilen
3. Pydantic-Contracts importierbar, `MIN_PERSONA_TABLE_ROWS=50`
4. Schema-Dump idempotent
5. Contract-Tests grün
6. 4 neue Output-Contract-Snapshot-Tests grün
7. Voice-Lint grün
8. Volltest grün (1615 → 1619 Tests)
9. `sync-status.sh --check` Exit 0
