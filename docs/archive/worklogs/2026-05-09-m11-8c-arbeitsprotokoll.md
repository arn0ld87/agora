# Arbeitsprotokoll — M11.8c: ReportV3-Contract (Pydantic-DTOs für 11 Pflichtabschnitte)

**Datum:** 2026-05-09
**Slice:** M11.8c — ReportV3-Contract
**Branch:** feat/m11-8c-reportv3-contract

## Ziel

Pydantic-v2-DTOs für die 11 Pflichtabschnitte aus dem externen Bewertungs-Doc
(`docs/2026-05-09-output-vertrag-bewertung-evidence-quality.md`, Score 5,8/10,
Abschnitt 6.1/8) einführen. Vorbereitung für M11.8d (Strict-Schema-Forced-Output)
und M11.8e (Quote/Evidence-Anchors).

## Geänderte / erstellte Dateien

| Datei | Art | Zeilen-Delta |
|---|---|---|
| `backend/app/contracts/report_v3.py` | NEU | +192 |
| `backend/app/contracts/__init__.py` | geändert | +14 (Re-Export-Gruppe + __all__) |
| `backend/app/services/report_agent/schemas.py` | geändert | +12 (Re-Export-Stub) |
| `backend/tests/contracts/test_report_v3_contract.py` | NEU | +287 (17 Tests) |
| `frontend/src/contracts/reportV3Contract.ts` | NEU | +192 |
| `frontend/src/contracts/__tests__/reportV3Contract.spec.ts` | NEU | +120 (9 Tests) |
| `schemas/report-v3.schema.json` | auto-generiert | via dump_schemas |
| `docs/2026-05-09-m11-8c-arbeitsprotokoll.md` | NEU | dieses Dokument |
| `CHANGELOG.md` | geändert | +1 Eintrag [Unreleased] |

## Implementierungs-Entscheidungen

- `ConfigDict(extra="forbid", str_strip_whitespace=True)` auf jedem DTO — verhindert
  unerwartete Felder, konsistent mit bestehenden Contracts.
- `_STRICT`-Alias für wiederverwendeten ConfigDict-Wert — reduziert Boilerplate.
- `Claim.evidence_refs: list[str] = Field(min_length=1)` — Pflichtfeld, kein leeres
  Array erlaubt; spiegelt das Evidence-Dedup-Ziel (Sub-Slice 07).
- `Persona.voice_register` als `Literal["formal-de", "neutral-de", "technical-de",
  "skeptisch-de"]` — spiegelt `VoiceRegister`-Enum aus `persona_contract.py`.
- `ReportV3.schema_version: Literal[3] = 3` — Versions-Lock analog zu
  `ReportContractModel(schema_version=2)`.
- Kein Wording-Glossar-v1-Verstoß: keine Felder/Kommentare mit "prediction",
  "rehearsal", "god's eye view", "future prediction".
- Zod-Spiegel in `reportV3Contract.ts` folgt 1:1 dem Pydantic-Modell:
  `z.literal(3)`, `.strict()`, identische enum-Werte.

## Akzeptanz-Output (Auszug)

```
# Backend-Tests
tests/contracts/test_report_v3_contract.py  17 passed
Gesamte Suite: 1622 passed, 9 skipped, 0 failures

# Re-Export-Check
OK: Re-Exports funktionieren

# Schema-Dump
✓ schemas/report-v3.schema.json
git diff --exit-code schemas/  →  exit 0 (kein Drift)

# ruff
All checks passed!

# mypy app/contracts/
Success: no issues found in 9 source files

# Frontend
Tests: 461 passed (461)
Build: ✓ built in 1.65s
```

## Out-of-Scope

- DTO-Verdrahtung in `agent.py`, `manager.py`, `workflow.py` — kommt in M11.8d.
- Renderer-Migration in `Step4Report.vue` — kommt nach M11.8d.
- Schema-Migrationen.
