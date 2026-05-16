# Sub-Slice M11.7b — `EvidenceSourceKind` + Cross-Stakeholder/Inferred-Validators

**Datum:** 2026-05-10
**Sprint:** M11.7 (Evidence-Gating, Welle 1 abgeschlossen)
**Branch:** `feat/m11-7b-evidence-source-kind`
**Spec:** `docu/decisions/0002-evidence-gating.md` (ADR-0002, Anker 3 + 4 + 5)
**Vorgaenger:** Sub-Slice M11.7a (`75e6d30`) — Anker 1 (Prompt-Block) + 2 (Hedge-Snapshot)

## Was, warum

ADR-0002 verankert fuenf strukturelle Anker gegen Halluzinations-Drift im
Report-Pipeline. M11.7a hat die Prompt-Seite gesetzt; M11.7b setzt die
**Layer-0-Pflicht-Anker** im Pydantic-Vertrag und im Zod-Spiegel:

- **Anker 3:** `EvidenceSourceKind` als geschlossene 4-Werte-Enum
  (`seed_corpus`, `agent_quote`, `graph_relation`, `inferred`).
- **Anker 4:** `cross_stakeholder_for_high` — `high`/`verified`-Claims
  verlangen `agent_quote`-Evidence aus mindestens **2 unterschiedlichen
  Stakeholder-Gruppen**.
- **Anker 5:** `reject_inferred_in_high_confidence` — `high`/`verified`
  duldet keine `source_kind=inferred`-Evidence (Anti-Halluzination).

Default `source_kind=seed_corpus` sichert Backward-Compat fuer Fixtures
ohne explizites Feld; die scharfen Cross-Stakeholder/Inferred-Regeln
greifen erst ab `high`/`verified` und sind damit additiv-strikt.

Drift-Guard zu Anker 1 (Prompt-Block in `report_prompts.py`): der neue
Test `test_enum_values_pinned` pinnt die Werte-Liste 1:1.

## Geaenderte Dateien

| Datei | Δ |
|---|---|
| `backend/app/contracts/report_contract.py` | +Enum, +2 Felder, +3 Validators |
| `backend/app/contracts/__init__.py` | Re-Export `EvidenceSourceKind` |
| `backend/tests/contracts/test_evidence_source_kind.py` (NEU) | +6 Tests |
| `backend/tests/contracts/test_report_contract.py` | Round-Trip + verified-Test auf Cross-Stakeholder migriert |
| `backend/tests/test_report_export.py` | Demo-Fixture `high` -> `medium` (Cross-Stakeholder out of scope) |
| `backend/tests/eval/fixtures/good/clean_small.json` | 6× `high` -> `medium` (siehe "Bewusst nicht migriert") |
| `backend/tests/eval/fixtures/good/medium_with_dedup.json` | 3× `high` -> `medium` |
| `backend/tests/eval/fixtures/bad/orphan_heavy.json` | 1× `high` -> `medium` |
| `frontend/src/contracts/reportContract.ts` | +EvidenceSourceKindSchema, +2 Felder, +2 superRefine-Branches |
| `frontend/src/contracts/__tests__/reportContract.spec.ts` | Round-Trip auf 2 agent_quotes migriert |
| `frontend/src/components/__tests__/Step4Report.spec.ts` | 3× `high` -> `medium` (UI-Render-Fixtures) |
| `schemas/evidence-map.schema.json` | +Enum + 2 Felder (Auto-Sync) |
| `schemas/report-contract.schema.json` | +Enum + 2 Felder (Auto-Sync) |
| `CHANGELOG.md` | `[Unreleased] ### Added` Bullet |

## Bewusst nicht migriert

- **Eval-Fixtures auf cross-stakeholder-konform**: Statt jeden `high`-Claim
  in `clean_small.json`/`medium_with_dedup.json` mit zwei `agent_quote`-
  Evidence-Items aufzubauen, sind alle bestehenden `high`-Claims in den
  Fixtures auf `medium` heruntergestuft worden. Begruendung: die Fixtures
  speisen `tests/eval/test_eval_baselines.py`, deren Erwartungswerte in
  `expected_metrics.json` hart gepinnt sind. Eine Migration auf Cross-
  Stakeholder-Setup wuerde Evidence-Items hinzufuegen oder Inhalte aendern
  und mindestens `claim_support_ratio` / `concentration_index` driften.
  Confidence-Label spielt fuer alle Layer-5-Metriken keine Rolle (siehe
  `backend/scripts/check_evidence_quality.py::evaluate`), daher ist
  `medium` neutral. Die ADR-0002-konforme Migration der Eval-Fixtures
  gehoert in M11.7d (Snapshot-Eval-Suite mit Bad-/Good-Cases gegen
  Evidence-Gating).
- **Frontend-Step4Report-Fixtures**: gleiche Begruendung — die Tests
  pruefen UI-Render von ConfidenceBadge / Quote-Anchor, nicht das
  Cross-Stakeholder-Verhalten. `medium` reicht aus.
- **`source_kind`-Default fuer alte v1->v2-Migrations-Tests**: nicht
  angefasst, weil Default `seed_corpus` ohne explizites Feld greift und
  diese Tests keine `high`/`verified`-Claims verwenden.

## Validator-Reihenfolge (bewusst)

`reject_orphan_high_confidence` -> `cross_stakeholder_for_high` ->
`reject_inferred_in_high_confidence`. Pydantic v2 fuehrt
`@model_validator(mode="after")` in Definitionsreihenfolge aus. Damit
bleibt die alte Fehlermeldung "supports_claim=True" fuer den orphan-Fall
unveraendert; die neuen Validators feuern nur, wenn der orphan-Test
schon durch ist.

## Verifikation

```
backend/tests/contracts/test_evidence_source_kind.py — 6/6 grün
backend/tests/contracts/                              — 94/94 grün
backend/tests/                                        — 1699 passed, 9 skipped
ruff check app/ tests/                                — clean
mypy app                                              — Success: no issues found in 132 source files
python -m app.contracts.dump_schemas                  — 12/12 schemas refreshed
git diff schemas/                                     — nur 2 Files: evidence-map + report-contract (Enum + 2 Felder)
frontend/npm run check                                — 45 Test Files / 465 Tests / build OK
```

## Schema-Diff-Zusammenfassung

```
schemas/evidence-map.schema.json:
  + EvidenceSourceKind (enum: seed_corpus, agent_quote, graph_relation, inferred)
  + EvidenceItemModel.source_kind (default seed_corpus)
  + EvidenceItemModel.persona_stakeholder_group (Optional[str], 1..200)

schemas/report-contract.schema.json:
  identische Aenderungen (selbe sub-defs).
```

`schemas/report.schema.json` ist unveraendert — `ReportModel` enthaelt
keine direkten Evidence-Items, daher kein Schema-Drift dort.

## Folgeauftraege (nicht Teil dieses Slice)

- **M11.7c:** `ReportSectionModel.hypotheses[]` + Frontend-Renderer in
  `Step4Report.vue`. Schliesst die Trennung "Behauptung mit Evidence"
  vs. "Hypothese ohne Evidence" auf UI-Ebene.
- **M11.7d:** Snapshot-Eval-Suite mit fixen Bad-/Good-Cases gegen die
  jetzt aktivierten Validators. Migration der bestehenden
  `clean_small.json`/`medium_with_dedup.json` auf cross-stakeholder-
  konformes Setup gehoert hierhin.
- **Report-Generator** (`backend/app/services/report_agent/*`) muss die
  neuen Felder beim Bauen von Evidence setzen — solange das nicht
  passiert, faellt der Generator-Output zwangslaeufig in das
  `medium`-Bucket. Das ist der naechste Sub-Slice der Welle 2.
