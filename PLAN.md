# Agora — Releaseplan v1.0

**Stand:** 2026-05-10 (post-Phase-1, P2.1/P2.2/P3.1/P3.3/P3.4/P4.2 grün)
**Quelle:** `agora_bewertung_komplett.md` (Score 5,8/10), Code-Verifikation gegen `main` (`backend/app/`, `frontend/src/`, `schemas/`, `.github/workflows/`), `report3.json` als realer Pipeline-Output.
**Ziel:** Agora schrittweise in einen releasefähigen Zustand bringen. Output-Vertrag erzwingen, Evidence härten, Tabellen rendern, Vertrauensmodi einführen.

> Bestehende Sicherheits-/Infrastruktur-Slices (M9.x, S1–S5, M10.x, M11 Phase 1–6) sind code-verifiziert grün. Dieser Plan adressiert ausschließlich den **Output-Vertrag** und die daraus abgeleiteten Releasekriterien. Historischer Backlog → siehe `docu/refactoring-backlog-priorisiert.md`.

## Status-Snapshot (2026-05-10)

Code-Verifikation gegen `main` (HEAD `c06563e`):

| Slice | Status | Anker im Code |
|---|---|---|
| P1.1 Pflichtabschnitt-Validator | ✅ done | `contract_validator.py`, `ReportOutlineModel.require_default_sections`, `workflow.py:466-486` |
| P1.2 Persona-Mindestanzahl | ✅ done | `MIN_PERSONA_TABLE_ROWS` in `contract_constants.py`, `prepare_service.py:34/362/385`, `workflow.py:488-499` |
| P1.3 Schema-Drift-Gate | ✅ done | `app.contracts.dump_schemas`, `.github/workflows/contract-gates.yml::schema-drift` |
| P2.1 Evidence-Anker-Pflicht | ✅ done | Commit `16bd51c`. `ReportClaimModel.non_low_claims_need_evidence`, `agent.py::_finalize_section_claims` data-gap-Routing, `migrate_legacy_claims_to_anchored` für Bestandsreports. 10 Routing-Tests. |
| P2.2 Low-Confidence-Marker | ✅ done | `render_claim_to_markdown` rendert ⚠️ Hinweis (`sections.py:149-167`) |
| P2.3 Hypotheses-Slot | ⚠️ in Arbeit | `render_hypotheses_for_section` da; Worktree `feat/m11-7c-report-hypotheses` aktiv für Frontend/JSON-Vollständigkeit |
| P3.1 ReportV3-Persistenz | ✅ done | Commit `84aa04b`. `migrate_v2_to_v3` + `write_report_v3`/`read_report_v3` (atomar via `os.replace`). Manager-Hook (`build_report_v3`/`save_report_v3`) war bereits verdrahtet. 6 neue Contract-Tests. `CURRENT_SCHEMA_VERSION` bleibt 2 (Evidence-Map-Schema). |
| P3.2 Markdown-Renderer | ⚠️ teilweise | `markdown_renderer.render_report_v3()` vollständig; Manager-Hook (`report-v3.md` schreiben) + Frontend-Default-Switch auf v3 noch offen |
| P3.3 Quote-Source-Marker | ✅ done | Commit `66af4d2 feat(report): render simulated_quote tags as marked blockquote` |
| P3.4 PDF-Print-Doku | ✅ done | Commit `58cd667 docs(report): document browser-print as canonical PDF path` |
| P4.1 Report-Modi | ❌ offen | kein `report_mode` auf `ReportV3`, kein API-Param |
| P4.2 CSV-Export | ✅ done | Commit `c06563e`. `GET /api/report/<id>/export?format=csv&table=…` (RFC-4180), `csv_export.py` Helper, `fetchReportCsv`/`downloadCsv`/`downloadCsvBundle` im Frontend (jszip nicht installiert → 3 Einzeldownloads, ZIP als Followup). 18 Backend- + 7 Frontend-Tests. |
| P4.3 ZIP-Bundle | ❌ offen | abhängig von P4.2 (jszip-Install + ZIP-on-the-fly-Endpoint) |
| P4.4 E2E-Smokes Modi | ❌ offen | abhängig von P4.1 |

**Restarbeit bis v1.0:** P3.2-Verdrahtung, P4.1, P4.3, P4.4. P2.3 läuft separat im Worktree.

---

## 0. Lückenbefund (Code vs. Bewertung)

| Bereich | Code-Stand `main` | Output-Effekt in `report3.json` |
|---|---|---|
| Pflichtabschnitt-Liste | `DEFAULT_REPORT_SECTIONS` (11 Einträge) in `report_prompts.py` definiert, in Snapshot-Test gepinnt | Pipeline schreibt **3 Sections** statt 11 — keine harte Validierung |
| Persona-Mindestanzahl | `MIN_PERSONA_TABLE_ROWS = 50` als Konstante, Snapshot-Test pinnt den Wert | Wird **nirgends in der Generator-Pipeline ausgewertet** |
| ReportV3-Container | `contracts/report_v3.py`, Zod-Spiegel + `schemas/report-v3.schema.json` vollständig | Persistenz schreibt weiterhin `schema_version=2`, kein v3 im Storage |
| Evidence-Bindung pro Claim | `evidence_binder.py` (Cosine ≥ 0.65) + `confidence_calculator.py` aktiv | **49 von 67 Claims** im Beispiel-Run haben `evidence: []` |
| Hypotheses-Slot | `ReportSectionHypothesisModel` definiert, im UI-Panel sichtbar | Wird **nicht als Auffangbecken** für Evidence-lose Claims genutzt |
| Confidence-Marker im Export | Confidence-Badge nur in der UI (`ReportEvidencePanel.vue`) | Im exportierten Markdown **nicht sichtbar** |
| Tabellen-Rendering | nicht vorhanden | Report ist Fließtext mit `<simulated_quote>`-Blöcken — keine Persona-/Segment-/Top-10-Tabellen |
| Report-Modi | nicht vorhanden | kein `strict`/`balanced`/`explorative` |
| CSV-Export | nicht vorhanden | nur MD/HTML/JSON in `useReportExports.ts` |

---

## 1. Phasen-Übersicht

| Phase | Inhalt | Effekt auf Score | Aufwand |
|---|---|---|---|
| **Phase 1** | Output-Vertrag absichern (Validator + Schema + Persona-Min) | 5,8 → ~7,0 | M |
| **Phase 2** | Evidence-Härtung (Anker-Pflicht, Low-Conf-Markierung, DataGap-Routing) | 7,0 → ~7,8 | M |
| **Phase 3** | Report-Qualität (Markdown-First, Tabellen, ReportV3 als Persistenz) | 7,8 → ~8,5 | L |
| **Phase 4** | Vertrauensmodi + Export-Vollständigkeit (CSV, ZIP, Modes) | 8,5 → ~9,0 | M |

Jede Phase ist **eigenständig deploybar und testbar**. Kein Big-Bang. Grobe PR-Größe: 200–600 LOC pro Slice.

---

## 2. Phase 1 — Output-Vertrag absichern

**Ziel:** Kein Report verlässt die Pipeline, dem Pflichtabschnitte fehlen oder die Persona-Tabelle unter 50 Zeilen liegt.

### 2.1 Pflichtabschnitt-Validator (Slice P1.1)

**Files:** `backend/app/services/report_agent/contract_validator.py` (neu), `backend/app/services/report_agent/manager.py`, `backend/app/contracts/report_contract.py`.

**Schritte:**

1. Neue Datei `contract_validator.py` mit Funktion `validate_required_sections(outline_titles: list[str], required: list[str]) -> list[str]`. Liefert die Liste fehlender Abschnitte (case-insensitive, Whitespace-tolerant).
2. `ReportOutlineModel.sections` Validator ergänzen (`@model_validator`): wenn `DEFAULT_REPORT_SECTIONS`-Set nicht vollständig vorhanden ist, `ValidationError` mit den Fehlrubriken werfen.
3. `manager.py`: nach `plan_outline()` → `validate_required_sections(outline.sections, [t for t,_ in DEFAULT_REPORT_SECTIONS])` aufrufen. Bei Fehlrubriken: `ReportStatus.incomplete` setzen, fehlende Abschnitte in `progress.json` listen, **kein** finales `report.md` schreiben.
4. API: `GET /api/report/<id>` liefert `status`, `missing_sections[]` strukturiert. Frontend zeigt rote Box.

**Akzeptanz:**

```bash
# Soll-Zustand: Run mit unvollständigem Outline produziert keinen finalen Report
pytest backend/tests/contracts/test_report_contract.py::test_outline_rejects_missing_required_sections -v
# erwartet: PASS, ValidationError listet alle fehlenden Section-Titel
```

### 2.2 Persona-Mindestanzahl in der Pipeline (Slice P1.2)

**Files:** `backend/app/services/prepare_service.py`, `backend/app/services/persona_quota_defaults.py`, `backend/app/services/report_agent/manager.py`.

**Schritte:**

1. `prepare_service.py::_resolve_total_personas()`: harter Floor auf `MIN_PERSONA_TABLE_ROWS` (Import aus `report_agent`). Wenn der User-Wert < 50 ist, auf 50 anheben + Log-Eintrag „persona-floor angewendet".
2. `manager.py::finalize_report()`: prüft `len(personas)` gegen `MIN_PERSONA_TABLE_ROWS`. Bei Unterschreitung: `ReportStatus.incomplete`, Eintrag in `data_gaps`.
3. Frontend: `Step3Simulation.vue` Persona-Slider bekommt `min={50}` mit Tooltip „Mindestmenge für DACH-Persona-Tabelle".

**Akzeptanz:**

```bash
# Default-Run muss 50 Personas erzeugen
curl -s http://localhost:5001/api/runs/<id> | jq '.summary.persona_count'
# erwartet: ≥ 50
```

### 2.3 JSON-Schema-Drift-Gate (Slice P1.3)

**Files:** `backend/app/contracts/dump_schemas.py`, `schemas/`, neue CI-Job-Stage.

**Schritte:**

1. `dump_schemas.py` erweitern, sodass `report-v3.schema.json`, `persona.schema.json`, `evidence-map.schema.json`, `report-contract.schema.json` aus den Pydantic-DTOs neu erzeugt werden.
2. CI-Job `contract-gates.yml::schema-drift` läuft `python -m app.contracts.dump_schemas --check` (existiert bereits konzeptionell — verifizieren). Drift → CI rot.
3. Frontend Zod-Schemas (`reportV3Contract.ts` etc.) bekommen einen Property-Roundtrip-Test gegen die JSON-Schema-Dateien (Snapshot-Vergleich auf Property-Set).

**Akzeptanz:** `npm run test:contracts && pytest backend/tests/contracts/` grün, Drift in einem der Dumps wird blockiert.

### 2.4 Phase-1-Definition-of-Done

- [ ] Pflichtabschnitt-Validator blockt unvollständige Reports mit explizit gelisteten Fehlrubriken.
- [ ] Persona-Mindestanzahl 50 wird Pipeline-seitig erzwungen, im Frontend als Slider-Floor sichtbar.
- [ ] JSON-Schema-Dump-Gate verhindert Drift zwischen Backend-DTOs, JSON-Schemas und Frontend-Zod-Schemas.
- [ ] Smoke-Test `tests/eval/test_output_contract_snapshot.py` und `tests/contracts/test_report_v3_contract.py` grün.

---

## 3. Phase 2 — Evidence-Härtung

**Ziel:** Jeder Claim trägt mindestens einen nachvollziehbaren Anker. Was keinen Anker hat, wandert in `hypotheses[]` oder `data_gaps[]`. Low-Confidence wird im Output sichtbar.

### 3.1 Evidence-Anker als Pflichtfeld erzwingen (Slice P2.1)

**Files:** `backend/app/services/report_agent/agent.py`, `backend/app/services/report_agent/workflow.py`, `backend/app/contracts/report_contract.py`.

**Schritte:**

1. `ReportClaimModel`: `evidence` von `default_factory=list` umstellen auf `min_length=1`, oder neuen Validator: wenn `evidence == []` und `confidence_label != "low"` → ValidationError. Migrationspfad für Bestandsreports über `evidence_migrations.py::migrate_v2_to_v3`.
2. `agent.py::_finalize_section_claims()`: Vor Persistenz Filter — Claim ohne Evidence + `confidence_score < 0.4` → in `hypotheses[]` umschreiben (`hypothesis_id`, `rationale`, `suggested_evidence` aus `audit_trail`-Hinweisen).
3. `workflow.py::generate_section()`: `data_gaps[]` der Section-Metadata bekommt automatisch alle Claim-Texte ohne Evidence-Bindung als `gap_reason="no_evidence_bound"`.

**Akzeptanz:** In `tests/eval/fixtures/bad/` wird ein synthetischer Run gepinnt, dessen Claims allesamt Evidence-leer sind. Test prüft: `claims=0, hypotheses=N, data_gaps=N`.

### 3.2 Low-Confidence-Markierung im Markdown-Export (Slice P2.2)

**Files:** `backend/app/services/report_agent/sections.py`, `frontend/src/utils/markdown.js`.

**Schritte:**

1. `sections.py::render_claim_to_markdown()` ergänzen: bei `confidence_label in ("low",)` Hedging-Präfix ergänzen — z. B. `> ⚠️ Low-Confidence-Hinweis (score=0.15): {claim_text}`.
2. Bei `confidence_label="medium"` ein dezenter Marker `_(medium-confidence)_` am Satzende.
3. Frontend `markdown.js` rendert die Confidence-Marker als CSS-Badges (`.conf-low`, `.conf-medium`, `.conf-high`).
4. Print-CSS in `useReportExports.ts::buildStandaloneHtml` bekommt die Badge-Styles dazu, damit PDF-Print sie sichtbar zeigt.

**Akzeptanz:**

```bash
# Soll-Zustand: jeder Low-Confidence-Claim trägt ein sichtbares ⚠️-Marker im exportierten MD
grep -c "Low-Confidence-Hinweis" agora-report-<id>.md
# erwartet: == Anzahl der confidence_label="low" Claims
```

### 3.3 Hypotheses-Slot vollständig integrieren (Slice P2.3)

**Files:** `backend/app/services/report_agent/sections.py`, `frontend/src/components/step4/ReportEvidencePanel.vue`, `frontend/src/utils/markdown.js`.

**Schritte:**

1. Markdown-Render: pro Section `### Hypothesen ohne Evidence`-Subsection mit `hypotheses[]` rendern (rationale + suggested_evidence-Liste).
2. UI bekommt eigenen Hypothesen-Tab im `ReportEvidencePanel` (existiert teilweise — verifizieren und Layout-Vollständigkeit prüfen).
3. JSON-Export führt `hypotheses[]` mit auf, kein Drop.

**Akzeptanz:** `tests/api/test_report_export.py::test_hypotheses_in_markdown_and_json` — beide Pfade enthalten den Hypothesen-Block.

### 3.4 Phase-2-Definition-of-Done

- [ ] Claims ohne Evidence sind im Output unmöglich — sie sind entweder `hypothesis` oder `data_gap`.
- [ ] Low-Confidence-Claims sind im exportierten Markdown sichtbar markiert (⚠️-Badge).
- [ ] Hypothesen-Block ist in MD, HTML, JSON und im UI gleichwertig sichtbar.
- [ ] Snapshot-Tests in `tests/eval/snapshots/` für Hypothesen-Routing aktualisiert.

---

## 4. Phase 3 — Report-Qualität: Markdown-First + Tabellen

**Ziel:** Strukturierte Rohdaten zuerst, daraus deterministisch gerendertes Markdown, daraus Browser-Print-PDF. Tabellen für Personas, Segmente, Top-10-Listen.

### 4.1 ReportV3 als Persistenz-Format (Slice P3.1)

**Files:** `backend/app/services/evidence_migrations.py`, `backend/app/services/report_agent/storage.py`, `backend/app/services/report_agent/manager.py`, `backend/app/contracts/report_v3.py`.

**Schritte:**

1. `evidence_migrations.py`: `CURRENT_SCHEMA_VERSION = 3`, neue Funktion `migrate_v2_to_v3(raw)` — übernimmt `sections[].claims[]` 1:1, baut zusätzlich aggregierte `personas[]`, `segments[]`, `friction_points[]`, `trust_signals[]` etc. aus den existierenden Section-Inhalten.
2. `storage.py::write_report_v3(report_id, ReportV3)` neu — schreibt ein zusätzliches Artefakt `report-v3.json` neben `evidence-map.json`. v2 bleibt vorerst parallel (Read-Modell für Bestandsreports).
3. `manager.py::finalize_report()` ruft am Ende die v3-Aggregation auf, sobald alle Sections vorhanden sind.
4. CI-Gate: `tests/contracts/test_report_v3_contract.py::test_persisted_v3_validates` neu — lädt das geschriebene Artefakt und parst es gegen `ReportV3`.

**Akzeptanz:** Nach jedem grünen Run liegen `report.json` (v2) **und** `report-v3.json` parallel im Storage. v3 valide gegen Pydantic-Modell.

### 4.2 Markdown-Renderer aus ReportV3 (Slice P3.2)

**Files:** `backend/app/services/report_agent/markdown_renderer.py` (neu), `backend/app/services/report_agent/manager.py`.

**Schritte:**

1. Neue Datei `markdown_renderer.py` mit reinen Funktionen:
   - `render_persona_table(personas: list[Persona]) -> str` — vollständige Markdown-Tabelle, alle 50+ Zeilen.
   - `render_segment_table(segments: list[Segment]) -> str`.
   - `render_top10_list(items: list[FrictionPoint|TrustSignal|ChangeRecommendation]) -> str` — sortiert nach `severity`/`priority`.
   - `render_data_gaps(gaps: list[DataGap]) -> str`.
   - `render_report_v3(report: ReportV3) -> str` — orchestriert alle Pflichtabschnitte in der Default-Reihenfolge.
2. `manager.py`: nach v3-Aggregation den Renderer aufrufen, Ergebnis zusätzlich als `report-v3.md` schreiben. v2-`report.md` bleibt für Bestandskompatibilität.
3. Frontend `useReportExports.ts`: Default-MD-Download wechselt auf `report-v3.md`, Fallback auf `report.md` wenn v3 fehlt.

**Akzeptanz:**

```bash
# Persona-Tabelle muss exakt MIN_PERSONA_TABLE_ROWS Zeilen haben
grep -c "^| P[0-9]" agora-report-<id>-v3.md
# erwartet: ≥ 50
```

### 4.3 Quote-Source-Markierung verfeinern (Slice P3.3)

**Files:** `backend/app/services/report_agent/sections.py`, `frontend/src/utils/markdown.js`.

**Schritte:**

1. `<simulated_quote persona_id seed_anchor>` wird im finalen Markdown zu einem Blockquote mit explizitem Marker:
   ```markdown
   > **Simulierter Persona-O-Ton** (persona_10, seed_anchor: robert_krasniqi_statement)
   > „Meine Generation will keine 5-Tage-Woche mehr. […]"
   ```
2. Frontend `markdown.js` kennt das Pattern und rendert eine farbige Markierung links („SIM").
3. Validator: `validate_quote_anchors` (existiert bereits laut `workflow.py`) muss in `strict`-Modus jedes Quote auf `seed_anchor`-Existenz im `seed_evidence_index` prüfen. Strict-Modus ist Voraussetzung für Phase 4.

**Akzeptanz:** Kein Quote im Markdown ohne explizit sichtbaren `(persona_id, seed_anchor)`-Header.

### 4.4 PDF nur als Browser-Print dokumentieren (Slice P3.4)

**Files:** `docu/deployment-prod-like.md`, `README.md`, `useReportExports.ts`.

**Schritte:**

1. `useReportExports.ts::printReport` prominenter platzieren (Button-Label „Als PDF drucken (Browser)").
2. Doku ergänzen: kein server-seitiges PDF, keine Headless-Chrome-Pipeline. Print-CSS ist die kanonische PDF-Quelle.
3. Print-CSS um Confidence-Badges aus Phase 2.2 ergänzen (siehe oben).

**Akzeptanz:** Browser-Print eines erzeugten Reports liefert vollständige Persona-Tabelle, Top-10-Listen und Confidence-Badges.

### 4.5 Phase-3-Definition-of-Done

- [ ] `report-v3.json` liegt nach jedem Run im Storage und valide gegen `ReportV3`.
- [ ] `report-v3.md` enthält alle 11 Pflichtabschnitte als deterministisch gerenderte Tabellen/Listen.
- [ ] Persona-Tabelle ≥ 50 Zeilen, Segment-Tabelle, Top-10-Listen vollständig.
- [ ] Print-PDF zeigt sichtbare Confidence-Badges und Quote-Marker.

---

## 5. Phase 4 — Vertrauensmodi + Export

**Ziel:** Drei Berichtsmodi mit unterschiedlicher Strenge, vollständiger Export in MD/JSON/CSV/PDF, optional ZIP-Bundle.

### 5.1 Report-Modi `strict`/`balanced`/`explorative` (Slice P4.1)

**Files:** `backend/app/api/report.py`, `backend/app/services/report_agent/manager.py`, `backend/app/contracts/report_v3.py`, `frontend/src/views/ReportView.vue`.

**Schritte:**

1. `ReportV3.report_mode: Literal["strict","balanced","explorative"] = "balanced"` ergänzen.
2. API `POST /api/report` akzeptiert `?mode=strict|balanced|explorative`, default `balanced`.
3. Manager-Verhalten:
   - **strict**: Claims ohne Evidence werden gedroppt (nicht in Hypotheses umgewandelt). Quote-Anchor-Validator hart. `confidence_label="low"` Claims werden gedroppt.
   - **balanced** (default): Phase-2-Verhalten — Hypotheses-Routing, Low-Confidence sichtbar markiert.
   - **explorative**: alle Claims durch, alle Quotes durch, sichtbar als `EXPLORATIVE`-Banner im Header.
4. Frontend `ReportView.vue`: Mode-Selector im Header (`<select>` mit drei Optionen + Tooltip-Erklärung).
5. Markdown-Renderer ergänzt einen Header-Block:
   ```markdown
   > **Report-Modus:** balanced — Belegte Claims plus markierte Hypothesen.
   ```

**Akzeptanz:** Drei Reports vom selben Run mit den drei Modi unterscheiden sich messbar in `claim_count`, `hypothesis_count` und Header-Banner.

### 5.2 CSV-Export für strukturierte Tabellen (Slice P4.2)

**Files:** `backend/app/api/report.py`, `frontend/src/composables/useReportExports.ts`, `frontend/src/api/report.ts`.

**Schritte:**

1. Backend-Endpoint `GET /api/report/<id>/export?format=csv&table=personas|segments|claims`. Liefert RFC-4180-konformes CSV.
2. `useReportExports.ts::downloadCsvBundle()` lädt alle drei Tabellen, packt sie in ein ZIP via `JSZip` (bereits npm-paket-tauglich, sonst lokal als drei Einzeldownloads).
3. Frontend-Button „CSV herunterladen" mit Dropdown (Personas / Segmente / Alle).

**Akzeptanz:**

```bash
curl -s "http://localhost:5001/api/report/<id>/export?format=csv&table=personas" \
  | head -1
# erwartet: id,voice_register,alter_range,beruf,region,…
```

### 5.3 ZIP-Bundle-Export (Slice P4.3)

**Files:** `frontend/src/composables/useReportExports.ts`.

**Schritte:**

1. `downloadAllBundle()` zieht serverseitig vorbereitetes ZIP (`GET /api/report/<id>/export?format=zip`) — enthält `report-v3.md`, `report-v3.json`, `evidence-map.json`, `personas.csv`, `segments.csv`, `claims.csv`.
2. Backend-Seite: kein neues Storage, ZIP wird on-the-fly aus existierenden Artefakten gebaut.

**Akzeptanz:** ZIP entpackt enthält 6 Dateien, alle gegen ihre Schemas valide.

### 5.4 E2E-Smokes für die Modi (Slice P4.4)

**Files:** `frontend/tests/e2e/report-modes.spec.ts` (neu).

**Schritte:**

1. Drei Playwright-Smokes (Health/Login → Run-Trigger → Mode-Auswahl → Export).
2. Snapshot-Vergleich auf den Mode-Banner im exportierten Markdown.

**Akzeptanz:** `npm run test:e2e -- --grep report-modes` grün auf allen drei Modi.

### 5.5 Phase-4-Definition-of-Done

- [ ] Drei Modi sind UI-seitig wählbar, server-seitig durchgeschleift.
- [ ] CSV-Export für Personas, Segmente, Claims funktioniert standalone und im ZIP-Bundle.
- [ ] PDF-Export bleibt Browser-Print, ist aber im Mode-Header markiert.
- [ ] E2E-Smokes blockieren Regressionen in CI.

---

## 6. Definition of Done für v1.0

- [ ] **Phase 1 grün:** Pflichtabschnitt-Validator + Persona-Floor + Schema-Drift-Gate.
- [ ] **Phase 2 grün:** Evidence-Anker-Pflicht + Low-Confidence-Marker + Hypotheses-Routing.
- [ ] **Phase 3 grün:** ReportV3 als Persistenz + Markdown-Tabellen-Renderer + Quote-Marker.
- [ ] **Phase 4 grün:** Drei Modi + CSV/ZIP-Export + E2E-Smokes.
- [ ] Externe Re-Bewertung gegen `agora_bewertung_komplett.md` Score ≥ 8,5/10.
- [ ] Alle Coverage-Gates (Backend ≥ 70 %, Frontend ≥ 60 %) grün.
- [ ] CI inklusive Schema-Drift, Contract-Gates, E2E-Smokes grün auf `release/**`.
- [ ] Release-Tag `v1.0.0` mit Changelog, SBOM, License-Report.

---

## 7. Arbeitsreihenfolge (PR-by-PR)

| PR | Slice | Aufwand | Blockiert |
|---|---|---|---|
| 1 | P1.1 Pflichtabschnitt-Validator | M | — |
| 2 | P1.2 Persona-Mindestanzahl | S | — |
| 3 | P1.3 Schema-Drift-Gate | S | — |
| 4 | P2.1 Evidence-Anker-Pflicht | M | PR 1 |
| 5 | P2.2 Low-Confidence-Marker | S | PR 4 |
| 6 | P2.3 Hypotheses-Slot | S | PR 4 |
| 7 | P3.1 ReportV3 als Persistenz | L | PR 1, PR 4 |
| 8 | P3.2 Markdown-Renderer | L | PR 7 |
| 9 | P3.3 Quote-Marker | S | PR 8 |
| 10 | P3.4 PDF-Print-Doku | S | PR 8 |
| 11 | P4.1 Report-Modi | M | PR 7, PR 8 |
| 12 | P4.2 CSV-Export | M | PR 7 |
| 13 | P4.3 ZIP-Bundle | S | PR 12 |
| 14 | P4.4 E2E-Smokes Modi | M | PR 11, PR 13 |

Reihenfolge ist linear sicher; PR 4 und PR 7 sind die zwei Engstellen.

---

## 8. Nächste Schritte (Stand 2026-05-10, post-Push)

Phase 1, P2.1, P3.1 und P4.2 sind auf `main` durch. Verbleibende Engstellen:

1. **P3.2-Verdrahtung** — `manager.finalize_report` ruft `render_report_v3()`, schreibt `report-v3.md` neben `report-v3.json`, Frontend `useReportExports.ts` wechselt Default-MD-Download auf v3 mit Fallback auf v2. Klein, aber Voraussetzung für P4.1.
2. **P4.1 Report-Modi `strict`/`balanced`/`explorative`** — `ReportV3.report_mode` + `?mode=`-Param + Manager-Verhalten + Frontend-Selector. Setzt P3.2 voraus.
3. **P4.3 ZIP-Bundle** — jszip als npm-Dependency installieren ODER server-seitiges ZIP-on-the-fly aus `report-v3.md`/`report-v3.json`/`evidence-map.json`/Personas-/Segmente-/Claims-CSV. Setzt P4.2 voraus (durch).
4. **P4.4 E2E-Smokes Modi** — drei Playwright-Smokes über die drei Modi. Setzt P4.1 voraus.
5. **Followups aus den letzten drei Slices**:
   - P3.1: Personas/Segments/FrictionPoints/TrustSignals werden derzeit als leere Listen aggregiert. Folge-Slice zieht echte Daten aus Persona-Storage + Segment-Aggregation.
   - P4.2: jszip-Install nachziehen (separater Slice mit `npm install jszip` und `downloadCsvBundle()`-Refactor auf echtes ZIP).
   - P2.3 läuft im Worktree `feat/m11-7c-report-hypotheses` und wird dort fertiggestellt.
3. **PR 7 vorbereiten:** v2→v3-Migration spec'en, bevor die Pipeline umgestellt wird (Migrationspfad ist die einzige Stelle, an der Bestandsdaten kippen können).
