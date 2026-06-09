# Agora — Refactoring-Plan (Output-Qualität)

**Stand:** 2026-05-10
**Quelle:** `agora_bewertung_komplett.md` §13 (priorisierte Fixes), Code-Review gegen `main` 2026-05-10.
**Zweck:** Heuristischer Stufenplan, der nach **Wirkung auf Output-Qualität** priorisiert. Keine Architekturwechsel — nur Refactoring auf der bestehenden Codebasis. Sicherheits- und Infra-Themen sind in `PLAN.md` und `docu/refactoring-backlog-priorisiert.md` separat geführt.

---

## Bewertungslogik

- **Priorität (1–10):** Wirkung auf den Score aus `agora_bewertung_komplett.md`. 10 = direkter Score-Hebel, 1 = kosmetisch.
- **Aufwand:** S (≤ 1 PR / ≤ 200 LOC), M (1–2 PRs / 200–600 LOC), L (≥ 2 PRs / ≥ 600 LOC).
- **Risiko:** niedrig / mittel / hoch — Ausstrahlung auf Bestandsfunktionalität.
- **Abhängig von:** Slice-IDs aus `PLAN.md` oder anderen Refactor-Steps.

---

## Stufenplan

### R1 — Pflichtabschnitt-Validator hart machen

| Feld | Wert |
|---|---|
| Priorität | **10** |
| Aufwand | **M** |
| Risiko | mittel |
| Slice-Mapping | `PLAN.md` § 2.1 (P1.1) |
| Files | `backend/app/contracts/report_contract.py`, `backend/app/services/report_agent/manager.py`, **NEU:** `backend/app/services/report_agent/contract_validator.py` |
| Abhängig von | — |

**Befund.** `ReportOutlineModel.sections` erlaubt `min_length=1, max_length=15` ohne Set-Vergleich gegen `DEFAULT_REPORT_SECTIONS`. Die Konstante existiert nur als Snapshot-Test-Pin. Pipeline produziert 3 Sections statt 11.

**Refactor.**

1. `ReportOutlineModel`: `@model_validator(mode="after")` ergänzen, der `[s.title for s in sections]` gegen die Default-Section-Liste case-insensitive prüft. Fehlende Titel landen im `ValidationError`.
2. `manager.py::finalize_outline()` — Validator-Aufruf direkt nach LLM-Outline-Parsing. Bei Fehler: kein `report.md`-Schreiben, `progress.json` bekommt `status="incomplete"` + `missing_sections[]`.
3. Neue `contract_validator.py` als reine Hilfsfunktion (DI-tauglich, ohne Container-Zugriff, testbar in 5 LOC).

**Risiko-Hinweis.** Bestehende Reports mit nur 3 Sections würden beim Re-Loading invalide. Migration: Read-Pfad bleibt tolerant (`ReportContractModel` v2 unverändert), nur Write-Pfad wird strikt. Bestandsreports werden nicht rückwirkend kaputt.

---

### R2 — ReportV3 als Persistenz-Format aktivieren

| Feld | Wert |
|---|---|
| Priorität | **10** |
| Aufwand | **L** |
| Risiko | mittel |
| Slice-Mapping | `PLAN.md` § 4.1 (P3.1) |
| Files | `backend/app/services/evidence_migrations.py`, `backend/app/services/report_agent/storage.py`, `backend/app/services/report_agent/manager.py`, `backend/app/contracts/report_v3.py` |
| Abhängig von | R1 |

**Befund.** `ReportV3` ist als Pydantic-DTO + Zod-Spiegel + JSON-Schema vollständig vorhanden. Pipeline schreibt aber `schema_version=2` (`evidence_migrations.py:14`). DTOs werden nirgends als Container-Persistenz-Modell genutzt.

**Refactor.**

1. `evidence_migrations.py`: `CURRENT_SCHEMA_VERSION = 3`, neue Funktion `migrate_v2_to_v3(raw)` — übernimmt Section-Claims 1:1, baut zusätzlich `personas[]`, `segments[]`, `friction_points[]`, `trust_signals[]`, `change_recommendations[]`, `data_gaps[]` aus den existierenden Section-Strukturen.
2. `storage.py`: `write_report_v3()` neu (atomare JSON-Datei `report-v3.json` neben `evidence-map.json`).
3. `manager.py::finalize_report()`: nach Section-Generierung Aggregations-Pass, dann v3-Persistenz. v2 läuft parallel weiter (bestehende Tests bleiben grün).
4. CI-Gate: `tests/contracts/test_report_v3_contract.py::test_persisted_v3_validates`.

**Risiko-Hinweis.** Doppel-Persistenz für eine Übergangszeit. Speicherbedarf ca. 1,5× pro Report. Akzeptabel für Single-User-Deploys (siehe ADR-0001).

---

### R3 — Persona-Mindestanzahl Pipeline-bindend

| Feld | Wert |
|---|---|
| Priorität | **9** |
| Aufwand | **S** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 2.2 (P1.2) |
| Files | `backend/app/services/prepare_service.py`, `backend/app/services/persona_quota_defaults.py`, `frontend/src/components/Step3Simulation.vue` |
| Abhängig von | — |

**Befund.** `MIN_PERSONA_TABLE_ROWS = 50` ist als Konstante deklariert (`contract_constants.py`) und im Snapshot-Test gepinnt — aber `prepare_service.py:138` ruft `default_dach_industry_quota(max(total_entities, 1))` ohne Floor-Check. Wenn der User 10 Personas wählt, bekommt er 10.

**Refactor.**

1. `prepare_service.py::_resolve_total_personas()`: harter Floor `max(user_value, MIN_PERSONA_TABLE_ROWS)` mit Log-Eintrag.
2. Frontend `Step3Simulation.vue`: Persona-Slider `:min="50"`, Tooltip „Mindestmenge für DACH-Persona-Tabelle". Slider-Step bleibt 1.
3. `manager.py::finalize_report()`: Soft-Check — wenn `len(personas) < 50`, Warnung in `data_gaps[]` + `report_status="degraded"`.

**Risiko-Hinweis.** Kostentreiber für LLM-Calls (50 statt 10 Persona-Generierungen). Bei explizitem Quick-Test-Modus (`?fast=1`) kann der Floor übergangen werden — separat evaluieren.

---

### R4 — Claims ohne Evidence automatisch in Hypotheses/DataGaps routen

| Feld | Wert |
|---|---|
| Priorität | **9** |
| Aufwand | **M** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 3.1 (P2.1) |
| Files | `backend/app/services/report_agent/agent.py`, `backend/app/services/report_agent/workflow.py`, `backend/app/contracts/report_contract.py` |
| Abhängig von | R1 |

**Befund.** `report3.json` zeigt 67 Claims, davon 49 mit `evidence: []`. `ReportClaimModel.evidence` ist `default_factory=list` — keine Mindest-Bindung. Der Confidence-Calculator gibt low-Confidence ohne Evidence ein, aber die Section-Markdown enthält die Aussagen unverändert als Prosa.

**Refactor.**

1. `ReportClaimModel`: `evidence: list[EvidenceItemModel] = Field(default_factory=list, max_length=10)` → ergänzen um `@model_validator`, der bei `confidence_label != "low"` und `evidence == []` einen ValidationError wirft.
2. `agent.py::_finalize_section_claims()`: Pre-Persistence-Filter — Claim ohne Evidence + Score < 0.4 → Umwandlung in `ReportSectionHypothesisModel` (existiert bereits, wird heute aber nicht aktiv befüllt).
3. `workflow.py::generate_section()`: leere-Evidence-Drops automatisch in `data_gaps[]` als `gap_reason="no_evidence_bound"`.

**Risiko-Hinweis.** Bestehende Section-Snapshots (in `tests/eval/snapshots/`) müssen aktualisiert werden — deutlich kürzere Section-Texte zu erwarten. Der Test `test_evidence_gating_prompt.py` erfasst diesen Pfad teilweise schon.

---

### R5 — Markdown-Tabellen-Renderer für Pflichtabschnitte

| Feld | Wert |
|---|---|
| Priorität | **8** |
| Aufwand | **L** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 4.2 (P3.2) |
| Files | **NEU:** `backend/app/services/report_agent/markdown_renderer.py`, `backend/app/services/report_agent/manager.py` |
| Abhängig von | R2 |

**Befund.** Heute generiert das LLM Section-Inhalte als Fließtext. Persona-Tabelle, Segment-Tabelle, Top-10-Listen sind nicht als Markdown-Tabellen sichtbar. Die DTOs liegen vollständig vor — es fehlt der deterministische Renderer.

**Refactor.**

1. Neue Datei `markdown_renderer.py` mit reinen Funktionen — keine Container-Abhängigkeit, kein LLM-Call:
   - `render_persona_table(personas: list[Persona]) -> str`
   - `render_segment_table(segments: list[Segment]) -> str`
   - `render_top10_list(items, *, by: Literal["severity","priority","reichweite_score"]) -> str`
   - `render_data_gaps(gaps: list[DataGap]) -> str`
   - `render_hypotheses(hypotheses: list[Hypothesis]) -> str`
   - `render_report_v3(report: ReportV3) -> str` als Orchestrator.
2. `manager.py`: nach R2-Persistenz den Renderer aufrufen, Output als `report-v3.md` schreiben.
3. Hard-Tests pro Renderer-Funktion: Stub-Inputs, Snapshot-Vergleich auf Tabellen-Spaltenbreite und Reihenanzahl.

**Risiko-Hinweis.** Renderer ist deterministisch — wenig Snapshot-Drift zu erwarten. Tabellen-Breite kann beim Browser-Print überlaufen; `useReportExports.ts::buildStandaloneHtml` muss `table { table-layout: fixed; }` dazubekommen.

---

### R6 — Low-Confidence sichtbar im Markdown-Output

| Feld | Wert |
|---|---|
| Priorität | **8** |
| Aufwand | **S** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 3.2 (P2.2) |
| Files | `backend/app/services/report_agent/sections.py`, `frontend/src/utils/markdown.js`, `frontend/src/composables/useReportExports.ts` |
| Abhängig von | R4 |

**Befund.** `ReportEvidencePanel.vue` zeigt Confidence im UI als Badge. Der **exportierte Markdown** enthält keinen Hinweis. Bewertung §10: Low-Confidence wird wie Gewissheit verkauft.

**Refactor.**

1. `sections.py::render_claim_to_markdown()`:
   - `confidence_label="low"` → `> ⚠️ **Low-Confidence-Hinweis** (score=0.15): {claim_text}`
   - `confidence_label="medium"` → `{claim_text} _(medium-confidence, score=0.55)_`
   - `confidence_label="high"` → unverändert.
2. Frontend `markdown.js` parst `> ⚠️ **Low-Confidence-Hinweis**` → CSS-Klasse `.conf-low`.
3. Print-CSS in `useReportExports.ts` ergänzt:
   ```css
   .conf-low { background: #fff3cd; border-left: 3px solid #c0a000; }
   .conf-medium { font-style: italic; color: #555; }
   ```

**Risiko-Hinweis.** Snapshot-Tests in `tests/eval/snapshots/` müssen aktualisiert werden, da viele Beispiel-Reports betroffen sind.

---

### R7 — Report-Modi `strict`/`balanced`/`explorative`

| Feld | Wert |
|---|---|
| Priorität | **7** |
| Aufwand | **M** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 5.1 (P4.1) |
| Files | `backend/app/api/report.py`, `backend/app/services/report_agent/manager.py`, `backend/app/contracts/report_v3.py`, `frontend/src/views/ReportView.vue` |
| Abhängig von | R2, R4 |

**Befund.** Bewertung §11 Phase 4 fordert drei Modi. Aktuell gibt es kein Mode-Konzept im Backend.

**Refactor.**

1. `ReportV3.report_mode: Literal["strict","balanced","explorative"] = "balanced"` ergänzen.
2. `manager.py`: Mode-spezifische Pipeline-Branch-Logik:
   - **strict**: Drop-Filter für `evidence == []` (nicht Hypothese, sondern Drop), Drop für `confidence_label="low"`, harte Quote-Anchor-Validierung.
   - **balanced**: R4-Verhalten (Hypothesen-Routing).
   - **explorative**: alles durch, sichtbarer Header-Banner.
3. API: `POST /api/report?mode=strict|balanced|explorative` (default `balanced`).
4. Frontend `ReportView.vue`: `<select>`-Mode-Selector im Report-Header.
5. `markdown_renderer.py` (R5): Mode-spezifischer Header-Block.

**Risiko-Hinweis.** Drei Modi multiplizieren den E2E-Smoke-Aufwand. Phase 4 plant das explizit ein.

---

### R8 — CSV-Export für Personas/Segmente/Claims

| Feld | Wert |
|---|---|
| Priorität | **6** |
| Aufwand | **M** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 5.2 (P4.2) |
| Files | `backend/app/api/report.py`, `frontend/src/composables/useReportExports.ts`, `frontend/src/api/report.ts` |
| Abhängig von | R2 |

**Befund.** `useReportExports.ts` deckt MD/HTML/JSON/Evidence ab, **CSV fehlt komplett**. Bewertung §13 Punkt 10 fordert MD/PDF/CSV/JSON.

**Refactor.**

1. Backend-Endpoint `GET /api/report/<id>/export?format=csv&table=personas|segments|claims`. Server liest `report-v3.json`, baut CSV via `csv.writer` (RFC-4180, UTF-8 BOM für Excel-Kompat).
2. `useReportExports.ts::downloadCsv(table)` — pro Tabelle einzeln. Optional `downloadCsvBundle()` mit ZIP über JSZip-Lib (siehe R9).
3. Drei Snapshot-Tests pro Tabelle (Header-Zeile, Spaltenanzahl, Beispiel-Datensatz).

**Risiko-Hinweis.** CSV-Spalten müssen bei DTO-Erweiterung mitwandern. Ein Property-Roundtrip-Test gegen `Persona`/`Segment`/`Claim` sichert das ab.

---

### R9 — ZIP-Bundle-Export

| Feld | Wert |
|---|---|
| Priorität | **5** |
| Aufwand | **S** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 5.3 (P4.3) |
| Files | `backend/app/api/report.py`, `frontend/src/composables/useReportExports.ts` |
| Abhängig von | R5, R8 |

**Befund.** Anwender muss heute mehrere Buttons klicken (MD, JSON, Evidence). Ein Bundle-Download fehlt.

**Refactor.**

1. Backend: `GET /api/report/<id>/export?format=zip` — bündelt `report-v3.md`, `report-v3.json`, `evidence-map.json`, `personas.csv`, `segments.csv`, `claims.csv`. Streaming-ZIP via `zipfile.ZipFile(io.BytesIO(), "w", ZIP_DEFLATED)`.
2. Frontend: `downloadAllBundle()` — ein Button.

**Risiko-Hinweis.** ZIP-Größe pro Report ca. 100–500 KB. Kein Streaming-Buffer-Issue.

---

### R10 — Quote-Source-Marker explizit im Markdown

| Feld | Wert |
|---|---|
| Priorität | **5** |
| Aufwand | **S** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 4.3 (P3.3) |
| Files | `backend/app/services/report_agent/sections.py`, `frontend/src/utils/markdown.js` |
| Abhängig von | R5 |

**Befund.** Pipeline produziert `<simulated_quote persona_id seed_anchor>`-Tags (siehe `report3.md`). Im finalen Markdown landet das aber als nackter Blockquote ohne sichtbaren „Simuliert"-Marker — Bewertung §6.3.

**Refactor.**

1. `sections.py::transform_simulated_quote()`:
   ```markdown
   > **Simulierter Persona-O-Ton** (persona_10, seed_anchor: robert_krasniqi_statement)
   > „Meine Generation will keine 5-Tage-Woche mehr. […]"
   ```
2. Frontend `markdown.js` rendert eine `.sim-quote`-CSS-Klasse mit linkem Akzentbalken („SIM").
3. `validate_quote_anchors` (existiert) im strict-Modus erzwingen — alle `seed_anchor`s müssen im `seed_evidence_index` auflösbar sein.

**Risiko-Hinweis.** Snapshot-Tests müssen aktualisiert werden. Kosmetisch, aber bewertungsrelevant.

---

### R11 — Hypothesen-Slot vollständig integrieren

| Feld | Wert |
|---|---|
| Priorität | **5** |
| Aufwand | **S** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 3.3 (P2.3) |
| Files | `backend/app/services/report_agent/sections.py`, `frontend/src/components/step4/ReportEvidencePanel.vue`, `frontend/src/utils/markdown.js` |
| Abhängig von | R4 |

**Befund.** `ReportSectionHypothesisModel` existiert (`report_contract.py:208`). Frontend-Panel hat einen Hypothesen-Tab im Code (`ReportEvidencePanel.vue:75-88`). **Aber:** Render-Pipeline füllt den Slot nicht aktiv (Voraussetzung in R4) und Markdown-Export ignoriert ihn.

**Refactor.**

1. `sections.py`: pro Section einen `### Hypothesen ohne Evidence`-Subblock generieren, der `hypotheses[]` mit Rationale + Suggested-Evidence rendert.
2. `useReportExports.ts::downloadCombinedJson()` führt `hypotheses[]` mit aus (kein Drop).
3. UI-Test in `frontend/tests` für Hypothesen-Tab.

**Risiko-Hinweis.** Geringe Auswirkung auf Bestandstexte.

---

### R12 — Schema-Drift-Gate als CI-Job

| Feld | Wert |
|---|---|
| Priorität | **4** |
| Aufwand | **S** |
| Risiko | niedrig |
| Slice-Mapping | `PLAN.md` § 2.3 (P1.3) |
| Files | `backend/app/contracts/dump_schemas.py`, `.github/workflows/contract-gates.yml`, `schemas/` |
| Abhängig von | R1, R2 |

**Befund.** `dump_schemas.py` existiert (44 LOC). JSON-Schemas in `schemas/` sind teilweise vorhanden. Ob CI-Drift-Gate aktiv prüft, ist unklar.

**Refactor.**

1. `dump_schemas.py` erweitern um `--check`-Flag: regeneriert die JSON-Schemas und verglich byte-genau gegen die Dateien in `schemas/`. Drift → exit 1.
2. CI-Job in `contract-gates.yml`:
   ```yaml
   schema-drift:
     run: uv run python -m app.contracts.dump_schemas --check
   ```
3. Property-Roundtrip-Test im Frontend: `reportV3Contract.ts` Zod-Schema muss alle Properties aus `schemas/report-v3.schema.json` decken.

**Risiko-Hinweis.** Initial einmalig viel Schema-Regeneration nötig — danach automatisch.

---

### R13 — `report_prompts.py` aufteilen (Refactor-Hygiene)

| Feld | Wert |
|---|---|
| Priorität | **3** |
| Aufwand | **M** |
| Risiko | niedrig |
| Slice-Mapping | rein technische Hygiene, kein User-Facing-Effekt |
| Files | `backend/app/services/report_prompts.py` (508 LOC) |
| Abhängig von | — |

**Befund.** `report_prompts.py` hat 508 LOC mit vier semantischen Clustern (Planning, Sections, ReACT, Chat). Komplexität konzentriert.

**Refactor.**

1. Aufteilen in `report_prompts/{__init__.py, planning.py, sections.py, react.py, chat.py}` — Re-Export der Konstanten.
2. Bestehende Imports (`from app.services.report_prompts import …`) bleiben gültig durch Re-Export.

**Risiko-Hinweis.** Kein Output-Effekt. Erst nach R1–R7 angehen.

---

### R14 — `frontend/src/utils/markdown.js` zu TypeScript

| Feld | Wert |
|---|---|
| Priorität | **2** |
| Aufwand | **S** |
| Risiko | niedrig |
| Slice-Mapping | F11 in alter Plan-Liste; Layer-6-Hygiene |
| Files | `frontend/src/utils/markdown.js` |
| Abhängig von | R6, R10 |

**Befund.** Datei ist eines der letzten `.js`-Dateien im Frontend. Confidence-Marker (R6) und Quote-Marker (R10) erweitern das File — guter Anlass für TS-Migration.

**Refactor.**

1. Datei nach `markdown.ts` umbenennen, Typ-Annotationen ergänzen (besonders für DOMPurify-Konfig und Marker-Patterns).
2. Tests in `frontend/src/utils/__tests__/markdown.spec.ts` mitziehen.

**Risiko-Hinweis.** XSS-Sicherheit (S1) darf nicht zurückfallen — `purify`-Konfiguration unverändert übernehmen.

---

## Reihenfolge-Empfehlung

```
R1 ──┬──> R2 ──┬──> R5 ──┬──> R7 ──┬──> R9
     │         │         │         │
R3 ──┘         │         │         │
               │         │         │
R4 ──────┬─────┴──> R6 ──┘         │
         │                         │
         └────────> R10 ───────────┤
         │                         │
         └────────> R11            │
                                   │
R12 ──── parallel ─────────────────┤
                                   │
R8 ────────────────────────────────┘
```

- **R1–R4** sind die vier Kernpfeiler. Erst danach lohnen sich Renderer/Modi.
- **R5–R7** bringen den größten sichtbaren Score-Sprung (Tabellen + Confidence + Modi).
- **R8–R11** sind Vervollständigungen, jede einzeln auslieferbar.
- **R12** läuft parallel und kann ohne R1–R4 gestartet werden, blockiert aber keinen anderen Step.
- **R13–R14** sind Refactor-Hygiene, kein Score-Hebel.

---

## Was bewusst NICHT gemacht wird

- **Server-seitiges PDF-Rendering** (Headless Chrome, WeasyPrint). Bewertung sagt explizit: PDF nur als Export-Layer. Print-CSS bleibt der kanonische PDF-Pfad.
- **Multi-User-Auth-Rewrite.** ADR-0001 hält Single-User mit Shared Token + signed Tickets fest.
- **LLM-Provider-Abstraktion** über das bestehende Niveau hinaus. Strict-JSON-Schema-Mode ist bereits implementiert (M11.8d).
- **Persona-Generator komplett neu schreiben.** `oasis_profile_generator.py` (1502 LOC) ist Hotspot, aber R3 reicht für die Bewertungslücke.
- **Großer UI-Redesign-Pass.** Phase 4 fügt Mode-Selector + CSV-Buttons ein, alles andere bleibt.

---

## Nächste Schritte

1. **R1 starten** — kleinster, wirksamster Hebel. PR `refactor/output-contract-validator`.
2. **R3 parallel** — hängt nicht an R1. PR `refactor/persona-min-floor`.
3. **R2 vorbereiten** — Migrations-Spec + Test-Fixtures schreiben, bevor Persistenz umgestellt wird.
