# Task G — Tests & Referenzläufe

Audit der Test-Abdeckung der Evidence-Chain-Stufen im Agora-Repo.
Basis: Branch `feat/1152-document-chunk-provenance` (HEAD 7e42ae34). 363 Test-Dateien
in `backend/tests/`, davon 95 in `services/`, 59 in `api/`, 36 in `contracts/`, 6 in
`eval/`. Keine separate `e2e/`-Suite — E2E läuft über Playwright-Smokes in
`.github/workflows/e2e-smokes.yml`.

## Sources (Datei:Zeile, Source-Type: official)

- backend/tests/eval/test_eval_baselines.py:1-66 — Snapshot-Metriken-Drift (official)
- backend/tests/eval/expected_metrics.json:1-23 — 3 Fixtures × 5 Metriken (official)
- backend/tests/eval/test_evidence_routing.py:1-298 — Orphan-Claim-Routing (official)
- backend/tests/eval/test_orphan_claim_routing.py:1-38 — 1 Orphan-Test (official)
- backend/tests/eval/test_evidence_gating_snapshot.py:1-269 — ADR-0002-Hartanker (official)
- backend/tests/eval/test_output_contract_snapshot.py:1-59 — Section-Liste pinnt (official)
- backend/tests/eval/test_persona_name_distribution.py:1-106 — Persona-Namen (official)
- backend/tests/eval/snapshots/evidence-gating-hedge-words.txt:1-4 — 4 Hedge-Wörter (official)
- backend/tests/eval/snapshots/output-contract-required-sections.txt:1-11 — 11 Section-Titel (official)
- backend/tests/services/test_report_agent_provenance.py:1-48 — 6 Helper-Tests (official)
- backend/tests/services/test_report_agent_quote_anchors.py:1-268 — 11 Quote-Anchor-Tests (official)
- backend/tests/contracts/test_evidence_identity_contract.py:1-96 — build_evidence_id deterministisch (official)
- backend/tests/regression/test_report_pipeline_trust.py:1-813 — Referenzlauf sim_7058c126da03 (official)
- backend/tests/test_ingestion_pipeline.py:1-245 — NER+RE + Batch-Embedding mit Mock (official)
- backend/tests/test_llm_e2e_stub.py:1-249 — LLM-Stub-Validierung (official)
- backend/tests/test_project_manager.py:75 — document_id in Fixture (official)
- backend/tests/utils/test_file_parser.py:152-274 — derive_document_id, chunk_id, ADR-0013 (official)
- backend/tests/test_confidence_calculator.py:19-182 — Confidence + Contradiction-Penalty (official)
- backend/tests/services/test_evidence_migrations_aggregation.py:133-378 — Legacy-Migration (official)
- .github/workflows/e2e-smokes.yml:1-703 — 7 Playwright-Smoke-Jobs (official)
- backend/tests/contracts/test_report_contract.py:332-340 — test_evidence_without_provenance_still_valid (official)
- docs/decisions/0013-seed-corpus-document-anchor.md — ADR-0013 Chunk-Provenance (official)

## Findings (max 12)

1. **eval/snapshots/ enthält KEINE Report-Outputs.** Nur zwei Wortlisten
   (`evidence-gating-hedge-words.txt` = 4 Hedge-Wörter, `output-contract-required-sections.txt`
   = 11 Section-Titel). Es gibt keinen committeten Golden-Report, gegen den ein
   echter LLM-Output bytegleich fixiert würde.

2. **`test_eval_baselines.py` ist KEIN Baseline-Vergleich Agora vs Single-Prompt.**
   Er vergleicht berechnete Metriken (`evidence_coverage`, `claim_support_ratio`,
   `orphan_claim_rate`, `dedup_rate`, `concentration_index`) dreier synthetischer
   JSON-Fixtures (`clean_small`, `medium_with_dedup`, `orphan_heavy`) gegen
   `expected_metrics.json` — ein Metriken-Drift-Guard, kein A/B-Vergleich.

3. **E2E-Smokes sind Frontend-Playwright-Tests gegen einen LLM-Stub.** 7 Jobs in
   `e2e-smokes.yml` (health, upload-graph, minimal-report, report-modes, golden-gate,
   ai-model-picker, run-budget) — alle mit `AGORA_E2E_LLM_MODE=stub`, keiner assertiert
   Evidence-Chain-Provenance. Sie prüfen UI-Flows, nicht dass eine doc_id durch die
   Pipeline bis ins Report-JSON überlebt.

4. **`test_llm_e2e_stub.py` ist der einzige python-E2E-Test, testet aber nur den Stub.**
   Validiert ReportV3-Schema-Konformanz und byteweise Determinismus des Stubs — keine
   Ingestion→Report-Kette.

5. **Chunk-Provenance-Tests existieren nur auf Parser-Ebene.** `test_file_parser.py`
   prüft `derive_document_id` (Länge≤120, Dedup-Suffix), dokumentinterne `chunk_id` ab 0,
   und dass der ADR-0013-Anchor `seed_doc:<document_id>#chunk:<chunk_id>` gültig ist.
   `test_project_manager.py` erwähnt `document_id` in genau einer Fixture. Kein Test
   verfolgt die Chunk-Provenance durch Ingestion → Graph → Retrieval → Evidence → Claim
   bis ins finale Report-JSON.

6. **`test_report_contract.py::test_evidence_without_provenance_still_valid` akzeptiert
   explizit Evidence ohne Provenance.** Dieser Test sichert bewusst eine Lücke —
   `source_id_anchor` ist optional. Für ein Provenance-Audit ist das ein Rotton: die
   Contract-Ebene erlaubt Evidence ohne verfolgbaren Ursprung.

7. **Provenance-Bruch-Tests prüfen nur „keine Evidence“, nicht „verlorene IDs“.**
   `test_evidence_routing.py` und `test_orphan_claim_routing.py` testen Claims OHNE
   Evidence → Routing zu `hypotheses`/`data_gaps`. `test_report_agent_quote_anchors.py`
   testet `unbound_evidence_refs` (seed_anchor nicht in EvidenceMap). Aber kein Test
   konstruiert den Fall: Evidence hat `source_id_anchor="seed_doc:docX#chunk:5"`, aber
   `docX`/`chunk:5` existiert nicht im Dokument-Manifest.

8. **`test_evidence_identity_contract.py` sichert Determinismus der `evidence_id`,
   nicht Report-Reproduzierbarkeit.** `build_evidence_id` ist run-local +
   content-independent deterministisch — stark für ID-Stabilität, aber kein Test, der
   „selber Seed → selbes Report-JSON“ verifiziert.

9. **`test_report_pipeline_trust.py` ist der einzige echte Referenzlauf-Test.** Er
   leitet 11 Invarianten aus dem realen Lauf `report_d9023bd1f55a` / `sim_7058c126da03`
   ab (30 Agents, 315 Interaktionen): Zahlenwanderung, Thought-Leak, Fallback-Text,
   Provenance-Mapping, JSON≡Markdown. Sehr stark für Trust/Quality — aber er prüft
   Entailment-Verhalten, nicht Chunk-Provenance.

10. **`test_report_agent_provenance.py` testet nur statische Helper.** `_build_source_id_anchor`
    und `_attach_provenance` als pure Funktionen — kein Pipeline-Test, der prüft, dass
    Provenance beim Persistieren/Aggregieren/Renderen nicht verloren geht.

11. **Branch-Vergleich (`test_simulation_compare.py`, `test_branch_comparison.py`,
    `test_compare_service.py`) ist KEIN Single-Prompt-Baseline.** Vergleicht zwei
    Simulations-Branches (A vs B) mit Metriken-Deltas — Agora-intern, nicht
    Agora-vs-Einzel-Prompt.

12. **`test_evidence_migrations_aggregation.py::test_persona_evidence_exports_only_minimal_provenance`
    akzeptiert „minimale Provenance“ für Persona-Evidence.** Auch hier: Contract-Ebene
    erlaubt eine Dünn-Provenance, die für ein Traceability-Audit nicht ausreicht.

## Stufen-Test-Matrix (Stufe → Testdateien → Abdeckung stark/mittel/keine)

| Stufe | Testdateien | Abdeckung |
|---|---|---|
| 1 Ingestion/Chunking | `test_ingestion_pipeline.py` (Mock-NER+Embedding), `test_file_parser.py` (document_id/chunk_id, ADR-0013), `test_project_manager.py` (1 Fixture) | **mittel** — Parser-Ebene stark, Pipeline-Durchreichung fehlt |
| 2 Graph Build | `test_graph_dtos.py`, `test_graph_export.py`, `test_graph_memory_updater.py`, `test_graph_diff_api.py`, `test_graph_build_*` (rollback/race/routing), `test_graph_quality_gate.py` | **mittel** — Struktur/Build stark, kein Provenance-Durchgriff |
| 3 Retrieval | `test_neo4j_filtered_entities.py`, `test_entity_reader.py`, `test_neo4j_mappings.py` | **dünn** — Entity-Reader, keine Provenance-Assertion |
| 4 Persona/Simulation/Interviews | `test_simulation_*` (API-Contract), `test_persona_name_distribution.py`, `test_persona_target.py`, `test_persona_entity_context_api.py`, `test_graph_tools_interview_*` | **mittel** — API-Contract stark, Interview-Evidence-Provenance nicht durchgetestet |
| 5 Evidence-Normalization/Identity | `test_evidence_identity_contract.py`, `test_model_attribution.py`, `test_evidence_source_kind.py`, `test_evidence_migrations_aggregation.py` | **stark** — ID-Determinismus + Source-Kind-Mapping |
| 6 Claim-Binding/Gating/Confidence | `test_evidence_gating_snapshot.py` (ADR-0002-Hartanker), `test_evidence_routing.py`, `test_orphan_claim_routing.py`, `test_confidence_calculator.py`, `test_evidence_auto_downgrade.py`, `test_anti_dekoration.py` | **stark** — Gating + Confidence + Contradiction-Penalty |
| 7 Renderer/Output | `test_output_contract_snapshot.py`, `test_report_pipeline_trust.py`, `test_report_agent_quote_anchors.py`, `test_report_agent_provenance.py`, `test_report_modes_workflow.py` | **mittel** — Quote-Anchors stark, Section-Liste nur syntaktisch |
| 8 E2E/Referenzlauf | `test_llm_e2e_stub.py` (Stub), `e2e-smokes.yml` (7 Playwright-Smokes), `test_report_pipeline_trust.py` (Referenzlauf) | **mittel** — UI-Smokes + 1 Referenzlauf, keine Chain-Assertion |
| 9 Chunk-Provenance (ADR-0013) | `test_file_parser.py`, `test_project_manager.py` | **dünn** — nur Parser-Ebene, keine End-to-End-Durchreichung |

## Provenance-Bruch-Tests (gibt es welche?)

Ja, aber nur für zwei Bruch-Klassen:

- **„keine Evidence gebunden“**: `test_evidence_routing.py` (11 Tests),
  `test_orphan_claim_routing.py` (1 Test) — Claims ohne Evidence →
  `hypotheses` + `data_gaps` mit `gap_reason="no_evidence_bound"`.
- **„seed_anchor nicht in EvidenceMap“**: `test_report_agent_quote_anchors.py`
  (`TestUnboundSeedAnchor`) — Quote referenziert `ev_999`, nicht in Map →
  `unbound_evidence_refs`, `valid=False`.

**Nicht abgedeckte Bruch-Klassen:**

- **„verlorene doc_id/chunk_id“**: Kein Test konstruiert den Fall, dass ein
  `source_id_anchor="seed_doc:docX#chunk:5"` auf ein Dokument/Chunk verweist, der im
  Dokument-Manifest nicht existiert. Gerade ADR-0013 führt diese Anchor-Form ein —
  die Validate-Funktion dafür fehlt in den Tests.
- **„Provenance nach Migration verloren“**: `test_evidence_migrations_aggregation.py`
  prüft, dass Persona-Evidence „nur minimale Provenance“ exportiert — das ist eine
  Akzeptanz, kein Bruch-Schutz.
- **„Contract erlaubt Evidence ohne Provenance“**:
  `test_report_contract.py::test_evidence_without_provenance_still_valid` sichert
  bewusst, dass `source_id_anchor` optional ist. Das ist kein Bruch-Test, sondern ein
  Bruch-Akzeptanz-Test.

## Reproduzierbarkeits-Tests

**Keine echten Reproduzierbarkeits-Tests vorhanden.**

- `test_evidence_identity_contract.py::test_build_evidence_id_is_deterministic_run_local_and_content_independent`
  sichert Determinismus der `evidence_id`-Konstruktion (gleicher run+source+content →
  gleiche ID). Das ist ID-Stabilität, nicht Report-Reproduzierbarkeit.
- `test_llm_e2e_stub.py::test_stub_react_tool_returns_deterministic` prüft
  byteweise Identität des Stub-Outputs — Determinismus des Stubs, nicht des Reports.
- Kein Test füttert dieselbe Simulation + denselben Seed zweimal und vergleicht das
  Report-JSON auf Gleichheit. Die LLM-Calls sind per Stub deterministisch, aber die
  Pipeline davor/dahinter (Aggregation, Merge, Render) hat keinen Reproduzierbarkeits-Test.

## Baseline-Vergleichs-Tests (existieren? wenn nein, feststellen)

**Nein, es existiert kein Baseline-Vergleich Agora vs Single-Prompt.**

- `test_simulation_compare.py` / `test_branch_comparison.py` /
  `test_compare_service.py` vergleichen zwei Simulations-Branches (A vs B) mit
  Metriken-Deltas (`echo_chamber_delta`, `cluster_delta`, …) — das ist ein
  Agora-interner Vergleich, kein Vergleich gegen einen Single-Prompt-Baseline.
- `test_eval_baselines.py` ist ein Metriken-Drift-Guard gegen `expected_metrics.json`
  (3 synthetische Fixtures), kein Verfahrensvergleich.
- Nirgends im Testbaum wird ein Single-Prompt-Report erzeugt und gegen einen
  Agora-Report gestellt. Die evaluative Aussage „Agora liefert bessere/sicherere
  Evidence als ein Einzel-Prompt" ist testtechnisch nicht belegt.

## Coverage-Lücken (welche Stufen ungesichert)

1. **Chunk-Provenance-End-to-End-Flow** (ADR-0013): Parser-Ebene getestet, aber kein
   Test, der `seed_doc:docX#chunk:5` vom Upload durch Ingestion → Graph → Retrieval →
   Evidence → Claim → Report-JSON verfolgt und am Ende verifiziert, dass die Anchor
   noch da und gültig ist.
2. **Dokument-Manifest-Konsistenz**: Kein Test, der prüft, dass jeder `seed_doc:*`-Anchor
   in der finalen EvidenceMap auf einen existierenden Eintrag im Dokument-Manifest
   verweist. ADR-0013 Slice 1 Teil A führte das Manifest ein, aber die
   Kreuzvalidierung Anchor↔Manifest ist nicht test-gesichert.
3. **Provenance-Bruch bei partieller Evidence**: Tests decken „keine Evidence“ und
   „unbound seed_anchor“ ab, aber nicht „Evidence mit kaputtem/halbem Anchor“.
4. **Reproduzierbarkeit**: Kein Same-Seed-Same-Report-Test.
5. **Baseline-Vergleich**: Kein Agora-vs-Single-Prompt-Test.
6. **Golden-Report-Snapshot**: Kein committeter Real-LLM-Report, gegen den ein
   Pipeline-Lauf fixiert würde. `test_report_pipeline_trust.py` pinnt Invarianten
   eines Referenzlaufs, aber nicht den Report selbst.
7. **Retrieval-Provenance**: Entity-Reader/Neo4j-Tests prüfen keine Provenance-Durchreichung.
8. **Interview-Evidence-Provenance**: `test_graph_tools_interview_*` testet
   Soft-Fail und Direct-Path, aber nicht, dass Interview-Antworten mit gültigem
   `source_id_anchor` und `persona_id` persistiert werden.

## Gaps

- **Contract erlaubt Evidence ohne Provenance** (`test_evidence_without_provenance_still_valid`):
  Die schwächste Stelle für ein Traceability-Audit. Solange dieser Test grün ist,
  ist die Contract-Ebene nicht in der Lage, Provenance-Brüche auf Evidence-Ebene
  abzulehnen.
- **„minimal provenance“ als akzeptierter Zustand** (`test_persona_evidence_exports_only_minimal_provenance`):
  Persona-Evidence darf mit reduziertem Provenance-Footprint exportiert werden —
  das ist für eine Traceability-Analyse ein struktureller Data-Loss.
- **ADR-0013 ist Slice 1 Teil A** (Manifest + Parser), die Slice-1-Teil-B-Tests
  (Anchor-Validierung gegen Manifest bei Report-Build) fehlen noch.
- **E2E-Smokes assertieren kein Provenance-Feld**: Kein Playwright-Smoke prüft, dass
  im Report-JSON `source_id_anchor` oder `evidence_id` für jede Evidence gesetzt ist.
- **Kein negativer E2E-Test**: Es gibt keinen Test, der absichtlich eine doc_id
  fallen lässt und verifiziert, dass die Pipeline das ablehnt.
- **`check_evidence_quality.py`** liegt unter `backend/scripts/` (nicht `scripts/`);
  `test_eval_baselines.py` importiert es korrekt via
  `Path(__file__).parent.parent.parent / "scripts"`. Kein Gap, nur ein Pfad-Hinweis
  für spätere Skript-Reproduktionen.