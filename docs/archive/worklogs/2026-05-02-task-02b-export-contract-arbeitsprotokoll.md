# Sub-Slice 02b · `ReportContractModel`-Envelope für `/api/report/<id>/export?format=json`

**Datum:** 2026-05-02
**Branch:** `claude/v0.9.0-frontend-version`
**Refs:** [`PLAN.md`](../PLAN.md) Layer 0 Task 02, GitHub-Issue #107
**Auto-Close:** **nein** — #107 schließt erst mit Sub-Slice 02c (Generator-Output-Validation + Persist-Round-Trip im `ReportManager`).

## Ausgangslage

02a hat den `schema_version`-Drift in `report_agent.py`/`api/report.py` und den In-Place-Migrator `migrate_v1_to_v2` gelandet. Damit zog der JSON-Export zwar v2 durch, baute den Envelope aber weiter als rohes Dict mit `EXPORT_SCHEMA_VERSION = 2`. Die Pydantic-Verträge aus dem Layer-0-Bundle (`backend/app/contracts/`) sind seit Slice X1 (`adcdf1a`) Teil des Repos, wurden aber an keinem Boundary verdrahtet — die `/fix-task-02-wire-contracts`-Skill-Definition spricht das genau aus:

> Nach Z. 417 wurde bisher rohes Dict gebaut. Ersetze durch `ReportContractModel(...)` und `model_dump_json(...)`.

Code-Belege im echten Stand vor 02b:

- [`backend/app/api/report.py:417–426`](../backend/app/api/report.py:417) — `payload = { ... "schema_version": EXPORT_SCHEMA_VERSION, ... }` + `json.dumps(...)`.
- [`backend/app/contracts/__init__.py`](../backend/app/contracts/__init__.py) — `ReportContractModel`/`ReportModel`/`EvidenceMapModel` exportiert, aber in `app/api/` nirgends importiert (`rg "ReportContractModel" app/api/` leer).
- [`backend/tests/contracts/test_report_contract.py`](../backend/tests/contracts/test_report_contract.py) — pinnt strikten v2-Vertrag (Literal[2], `claim_id`-Pattern, `section_index >= 1`, `extra="forbid"`).

## Scope dieses Sub-Slice

Genau **ein Commit**, kleinster ehrlicher Schritt aus PLAN.md Task 02 (Skill-Punkt 2.1):

1. JSON-Export-Branch in [`backend/app/api/report.py`](../backend/app/api/report.py) auf `ReportContractModel.model_dump_json(...)` umstellen.
2. Boundary-Mapper `_map_outline_for_contract` einführen — `ReportSection.to_dict()` liefert `{"title", "content"}`, `ReportOutlineSectionModel` verlangt `{"title", "description"}` mit `extra="forbid"`. Storage-Reshape ist 02c-Scope, deshalb das Mapping bewusst am API-Boundary.
3. Helper `_build_export_envelope(report_obj, raw_evidence_map)` baut den Envelope; `EvidenceMapModel.model_validate` läuft mit Try/Except — legacy-v1-geformte Evidence-Maps (claim_id `c1`, section_index 0, fehlendes `section_summary`) werden vorerst aus dem Envelope gedroppt und mit `logger.warning` belegt, statt den Export auf 500 zu setzen. Persistenz-Reshape steckt explizit in 02c.
4. `tests/test_report_export.py`-Fixture auf v2-Vertragsform heben:
   - `outline.sections` jetzt 2 Einträge (Vertrag verlangt `min_length=2`).
   - Evidence-Map als v2-konform: `simulation_id`, `section_index=1`, `section_summary`, `claim_id="claim_01"`, `claim_text` ≥ 8 Zeichen, `evidence` mit `match_score=0.7` + `supports_claim=True`, `audit_trail=[]`.
   - Assertion auf `payload["report"]["schema_version"] == 2` ergänzt — der Vertrag macht das jetzt zu einem `Literal[2]`-Zwang, der pinnen-wert ist.

**Out of Scope (folgt in 02c):**

- `EvidenceMapModel`-Validation am Persist-Boundary in `ReportManager.save_evidence_map`/`get_evidence_map`.
- `ReportContractModel`-Validation am Generator-Output (`ReportAgent.generate_report`).
- Reshape persistierter Legacy-Evidence-Maps in Vertragsform (claim_id-Pattern, section_index-Off-by-One). Schließt #107.
- Frontend-Strict-Mode (Task 04, eigener Slice).

## Diff

### Geändert

- [`backend/app/api/report.py`](../backend/app/api/report.py)
  - `import json` raus (durch `model_dump_json` obsolet); `from typing import Any, Optional` rein.
  - `from pydantic import ValidationError` rein.
  - `from ..contracts import EvidenceMapModel, ReportContractModel, ReportModel` rein.
  - Neuer Boundary-Mapper `_map_outline_for_contract(outline)` — verwirft den `content`-Key, fällt auf `description` zurück (Default `"—"` falls leer), erzwingt Title/Summary-Defaults statt None.
  - Neuer Envelope-Builder `_build_export_envelope(report_obj, raw_evidence_map)` — strikt-validiert `ReportModel`, best-effort `EvidenceMapModel`, ruft den Migrator vor der Validation, droppt Evidence bei `ValidationError` mit `logger.warning` (Top-3-Fehlerliste).
  - JSON-Branch in `export_report`: `payload = {...}; json.dumps(...)` ersetzt durch `envelope = _build_export_envelope(...); body = envelope.model_dump_json(indent=2)`.
  - Docstring der Route auf `ReportContractModel`-Envelope-Sprache umformuliert.

- [`backend/tests/test_report_export.py`](../backend/tests/test_report_export.py)
  - `_persist_report` schreibt jetzt 2 Outline-Sections (`Intro`, `Outlook`) — `ReportOutlineModel.sections` hat `min_length=2`.
  - Evidence-Map auf v2-konforme Form: `simulation_id`, `section_index=1`, `section_summary`, `claim_id="claim_01"`, `claim_text="Demo claim text long enough"` (10 Zeichen), `evidence=[{type: "graph_metric", source: "simulation_metrics", snippet, match_score=0.7, supports_claim: true}]`, `audit_trail=[]`.
  - `test_export_json_returns_combined_envelope` assertet zusätzlich `payload["report"]["schema_version"] == 2` und `claim_id == "claim_01"` (vorher `"c1"`).
  - Kommentar im Test verweist auf 02b statt 02a.

## Verifikation

Aus `/mnt/brain/Projekte/Agora/backend`:

- `uv run pytest tests/test_report_export.py tests/contracts/ -x -q` → **27 passed** in 1.05 s.
- `uv run pytest -x -q` (Volltest backend) → **913 passed, 2 skipped** in 60 s. Skips orthogonal: 2 × Redis-Integration aus dem MiroFish-Schwesterprojekt (`TEST_REDIS_URL` nicht gesetzt).
- `uv run python -m app.contracts.dump_schemas` → 5/5 Schemas dumped.
- `git diff --exit-code schemas/` → leer (keine Drift, Vertrags-Shape unverändert — wir haben **konsumiert**, nicht definiert).
- `rg '"schema_version": 1' backend/app/` → leer.
- `rg "EXPORT_SCHEMA_VERSION" backend/app/` → nur `= CURRENT_SCHEMA_VERSION` plus eine Doc-String-Referenz im Vertrags-Modul (historischer Anker für den ehemaligen Drift in `api/report.py:379`).
- `uv run ruff check app/api/report.py` → clean.

`uv run mypy` ist im Repo nicht als Dev-Dep verdrahtet (`pyproject.toml` listet nur `ruff`); die in `CLAUDE.md` aufgeführte mypy-Linie ist deshalb hier kein Verifikations-Punkt.

## Issue- und Milestone-Mapping

| Issue | Status nach 02b | Begründung |
|---|---|---|
| #107 — Schema-Migration v1→v2 | offen, `Refs #107` (kein Auto-Close) | API-Export ist jetzt vertrags-gepinnt (`schema_version` per `Literal[2]` unmöglich zu typen). **Persist-Boundary** in `ReportManager` und **Generator-Output-Validation** in `ReportAgent.generate_report` folgen in 02c — erst dann gilt der Issue als geschlossen. |
| PLAN.md Task 02 (Master) | Sub-Slice 02b done, 02c offen | 02c: Pydantic-Validation am Generator-Output (`ReportAgent.generate_report`) plus Reshape persistierter Evidence-Maps in `ReportManager.get_evidence_map` — danach kann der `try/except`-Drop-Pfad in `_build_export_envelope` rausfliegen. |

## Folge-Sub-Slices

- **02c** — `EvidenceMapModel`-Reshape im `ReportManager` (claim_id-Pattern, section_index-Off-by-One, `section_summary`-Default), Pydantic-Validation am Generator-Output, Round-Trip-Test gegen synthetische v1-Fixtures. Schließt #107 und macht den `try/except`-Fallback in `_build_export_envelope` überflüssig.

## Notizen

- **Outline-Mapping gehört genau hier hin.** Die Dataclass `ReportSection` benutzt `content` als Doppelnutzung („Outline-Beschreibung" + „gefüllte Section-Body"); der Vertrag trennt das in `description` (Outline) vs. Section-Body (separater Pfad). Den Mapper am API-Boundary statt in der Dataclass zu halten, vermeidet Kollisionen mit den ~6 anderen `outline.to_dict()`-Konsumenten (`report_logger.py`, `api/report.py:218` Status-Endpoint, etc.).
- **Best-Effort-Evidence-Validation** ist eine bewusste Schritt-für-Schritt-Entscheidung. Der Skill-Snippet zeigt `EvidenceMapModel.model_validate(...)` strikt; in der Realität sind alle persistierten Evidence-Maps der bestehenden Reports vor 02c noch nicht vertragskonform (claim_id `c1`, section_index 0). Strikte Validation würde den Export für Bestands-Reports auf 500 setzen — `try/except` mit `logger.warning` liefert den Pfad **ehrlich**: alte Reports exportieren ohne Evidence (Markdown-Body bleibt vollständig), neue Reports kriegen den vollen Envelope. Der Drop wird in den Backend-Logs sichtbar.
- **`claim_text="Demo claim text long enough"`** im Test ist 27 Zeichen, deutlich über `min_length=8`. Ich habe bewusst nicht knapp am Limit getestet, weil der Vertrags-Test `test_full_contract_round_trip` in `tests/contracts/test_report_contract.py` den Edge-Case schon abdeckt — der Export-Test soll Workflow, nicht Vertrags-Edges pinnen.
- Der `EXPORT_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION`-Re-Export in `api/report.py:386` bleibt stehen, weil `report_logger.py` und externer Tooling-Code ihn potenziell importieren; entkoppelt vom Wert ist die Konstante jetzt aber redundant — Aufräumen läuft mit 02c.
