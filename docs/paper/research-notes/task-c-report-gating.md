# Task C — Report- und Evidence-Pipeline (Gating, Provenance, Traceability)

Rekonstruktion am Code (Branch `feat/1152-document-chunk-provenance`). Alle
Zeilenangaben beziehen sich auf den Stand zum Prüfungszeitpunkt. Keine
README-Aussagen; alle Belege stammen aus `backend/app/...` oder
`backend/tests/...`.

## Sources

Alle `official` (Quelle: Repo-Code bzw. ADRs):

- `backend/app/services/evidence_identity.py:18-57` — `build_evidence_id`, `build_producer_key`
- `backend/app/services/report_agent/evidence.py` — Normalisierung, `register_evidence_record`, `validate_quote_anchors`, `degrade_sections_for_violations`, `auto_downgrade_unsupported_high_claims`
- `backend/app/services/evidence_binder.py` — `bind_evidence_to_claim`, `detect_contradiction_penalty`
- `backend/app/services/evidence_entailment.py` — deterministische Entailment-Klassifikation, `extract_numeric_facts`
- `backend/app/services/confidence_calculator.py` — `compute_confidence`, `_has_contradiction` (MAI-14), `apply_echo_cap`
- `backend/app/contracts/report_contract.py` — `EvidenceSourceKind`, `EvidenceItemModel`, `ReportClaimModel`-Validatoren, `EvidenceMapModel`, `EvidenceOmissionModel`
- `backend/app/contracts/report_v3.py` — `ReportMode`, `ReportV3` (`schema_version=4`), `Claim.evidence_refs`
- `backend/app/services/report_prompts/sections.py` — `<evidence_gating priority="hard">`-Block, Provenance-Level
- `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt` — Hedge-Words (Anker 2)
- `backend/app/services/report_agent/agent.py` — `_build_claims_for_section`, `_finalize_section_claims`, `_save_evidence_section`, `_record_tool_evidence`, `_collect_simulation_evidence_items`
- `backend/app/services/report_agent/manager.py` — `build_report_v3` (Mode-Routing), `assemble_full_report`
- `backend/app/services/report_agent/markdown_renderer.py` — `render_report_v3`, `render_evidence_status`, Mode-Banner
- `backend/app/services/report_export.py` — `build_export_envelope`, `_normalized_evidence_map`, `build_zip_bundle`
- `backend/app/services/evidence_migrations.py` — `normalize_persisted_evidence_map` (kanonische Migrationskette)
- `backend/app/api/report.py` — `/generate` (mode-Param), `/<id>/evidence`, `/<id>/export`
- `backend/app/services/report_agent/workflow.py` — `generate_report_impl` (Red-Team, `apply_degradation_downgrade`)
- `backend/app/services/report_agent/hypothesis_cap.py` — `dedup_and_cap_hypotheses`
- `docs/decisions/0002*.md` und `0007*.md`, `0011-evidence-entailment-and-provenance.md`, `0013-seed-corpus-document-anchor.md`

## Findings (max 14, mit Beleg)

1. **Evidence-Identity ist deterministisch und run-lokal, ohne Inhaltstext.**
   `build_evidence_id(scope_id, source_kind, producer_key)` hasht
   SHA-256 über length-prefixed Teile und schneidet auf 32 Hex-Zeichen
   (`ev_<...>`). Der Fact-Text geht nicht in die Identität ein — derselbe
   Fakt über verschiedene Queries kollabiert bewusst NICHT, weil der
   `producer_key` die Query und den Fact-Text mischt
   (`evidence_identity.py:18-34`, `agent.py:309-327`).

2. **`producer_key` ist die kanonische Provenance-Quelle.**
   `build_producer_key(prefix, *parts)` baut `<prefix>:<sha256[:24]>` mit
   Längen-Präfix pro Teil (Kollisionsvermeidung `(ab,c)` vs `(a,bc)`).
   Graph-Fakten: `graph-fact:<hash(fact)>`; Interview:
   `interview:s<section>:<hash(topic, agent, question, response)>`;
   Web: `web:<url>`; Simulation: `simulation-metric:<field>` bzw.
   `simulation-action:<platform:round:agent:action:ts>`
   (`evidence_identity.py:37-57`, `agent.py:301-452`).

3. **Ohne `producer_key` verwirft `register_evidence_record` Evidence
   still.** Der Fix zu `report_06f654800817` (0 von ~40 Items im Index)
   erzwingt einen producer_key für jeden Typ (`agent.py:309-327`,
   `evidence.py` `register_evidence_record`). Risikofeld: neue Tool-Typen
   ohne Identitäts-Pipeline fallen still durch.

4. **Normalisierung mappt `EvidenceType` → `EvidenceSourceKind`, aber
   `source_kind` gewinnt.** Fallback ist `inferred`, NIE `seed_corpus`
   (`evidence.py` `_TYPE_TO_SOURCE_KIND`, `normalize_source_kind`).
   `seed_corpus` ist ausschließlich den dokument-verankerten Ingest-Items
   vorbehalten (ADR-0013). LLM-Freetext wird `model_generated_inference`
   (source_quality-Gewicht 0.0 in `confidence_calculator`).

5. **Claim-Binding ist zweistufig: Cosine-Retrieval (threshold=0.55 im
   Agent, 0.65 Default) + deterministisches Entailment.**
   `bind_evidence_to_claim` liefert `retrieval_score`/`match_score`, danach
   `classify_evidence` aus `evidence_entailment.py`. Der LLM-Judge ist
   OPTIONAL und darf SUPPORTED nur abschwächen, nie erfinden
   (`evidence_binder.py`, `evidence_entailment.py`, `agent.py:474`).

6. **Entailment ist regelbasiert mit drei Pfaden.** Numerisch
   (asymmetrische PREDICATE-COVERAGE ≥0.75), Mengen (majority/minority
   markers), qualitativ (topic-overlap). `FactModality` trennt FACTUAL vs
   NORMATIVE (Zielvorgabe vs Ist-Wert) — Normativ-Fakten validieren keine
   IST-Aussagen (`evidence_entailment.py`).

7. **Confidence-Formel (deterministisch):**
   `0.40*relevance + 0.25*source_quality + 0.20*specificity + 0.15*consistency
   − penalty`. `_SOURCE_WEIGHTS`: graph_fact=1.0, relationship_chain=0.95,
   agent_behavior=0.75, agent_action=0.7, model_generated_inference=0.0.
   Caps: <2 Items → max 0.59; alle match_scores<0.55 → max 0.64;
   verified braucht ≥0.85 + 2 Quellen (`confidence_calculator.py`).

8. **MAI-14 Sentiment-Widerspruch straft mit 0.20.** `_has_contradiction`:
   `pstdev > 0.6` ODER `(min < −0.3 UND max > 0.3)` → Penalty 0.20.
   `detect_contradiction_penalty` addiert +0.15 pro bool-Flag/Stance-Konflikt
   (max 0.5) (`confidence_calculator.py`, `evidence_binder.py`).

9. **Echo-Cap drosselt Cross-Stakeholder-Claims** mit `echo_index > 0.75`
   auf max 0.84/medium — verhindert polarisierte Echo-Kammern als "hoch"
   zu rangieren (`confidence_calculator.py::apply_echo_cap`).

10. **ADR-0002 hat 5 Hartanker, die NIE ohne `0002-supersedes.md` +
    User-Signoff geschwächt werden dürfen** (CLAUDE.md, verbindlich):
    (a) `<evidence_gating priority="hard">`-Block in `sections.py`;
    (b) Hedge-Words-Snapshot `evidence-gating-hedge-words.txt` (4 Worte:
    „vermutlich, deutet auf, die Quellenlage spricht für, Indizien legen
    nahe");
    (c) Enum `EvidenceSourceKind`;
    (d) Validator `cross_stakeholder_for_high`;
    (e) Validator `reject_inferred_in_high_confidence`.

11. **Graceful Degradation (Issue #1006) trennt zwei Logs.**
    `gate_decision_log` protokolliert das REGULÄRE Routing (Claim→Hypothese
    bei <2 evidence_refs, medium/high ohne Evidence → data_gap).
    `degradation_log` protokolliert Validator-Reparaturen via
    `degrade_sections_for_violations` (3 Regeln: `downgraded_to_low`,
    `moved_to_hypotheses`, `dropped`) — und `apply_degradation_downgrade`
    senkt einen `COMPLETED`-Report auf `INCOMPLETE`, wenn die lokale
    Degradierung zugeschlagen hat (`agent.py:843+`,
    `workflow.py:1216-1219`, `report_contract.py` `EvidenceMapModel`).

12. **Mode-Routing ist deterministisch und ungleich.**
    `balanced`/`explorative`: Claims ohne Evidence werden übersprungen;
    `strict`: speculative/low-Claims werden gedroppt; `<2 evidence_refs`
    → Hypothese; `verified` ohne starke Evidence → Hypothese + data_gap.
    Stable Re-IDs `H{section}_{i:02d}`, `HA{section}_{i:02d}`
    (`manager.py:244-413`, `report_v3.py` `DEFAULT="balanced"`).

13. **`<simulated_quote seed_anchor="ev_...|seed_doc:...">` ist die
    Text↔Evidence-Brücke.** `validate_quote_anchors` parst das Tag und
    prüft gegen `known_anchors` + `persona_ids`; kosmetische Quotes ohne
    Anchor werden verworfen. Der Prompt blockiert unter
    `<critical_distinction>` die Verwechslung mit dem strukturierten
    `evidence[]`-Feld (`sections.py`, `evidence.py`).

14. **Export ist Provenance-erhaltend, aber nicht verlustfrei.** Die
    kanonische Migrationskette `normalize_persisted_evidence_map`
    (Issue #1036) läuft in JSON, ZIP und CSV über EINE Stelle
    (`_normalized_evidence_map`), so dass orphan medium-Claims in allen
    Formaten nach `data_gaps` migriert werden. Schlägt die Migration
    fehl (`contract_violation`), fällt die Evidence-Map STUMM aus dem
    Envelope — dokumentiert via `EvidenceOmissionModel` (Issue #987):
    Report-Rumpf bleibt, aber Evidence ist weg. Traceability endet dann
    beim Report, nicht bei der Quelle (`report_export.py:87-132`,
    `evidence_migrations.py`).

## Stufen-Analyse (10 Standardfragen kompakt)

### Stufe 1 — Report Tools (InsightForge, Panorama, Search, Interview, Web)

- **Rein:** LLM-Tool-Call (tool_name, parameters); strukturierter
  InsightForgeResult/PanoramaResult/SearchResult/InterviewResult/dict.
- **Raus:** `EvidenceItem`-Dicts mit `type`, `producer_key`, `snippet`,
  `raw`, `agent_log_ref`; bei Interview zusätzlich `quote` +
  `persona_stakeholder_group` (Pflicht für `agent_quote`).
- **Provenance:** `producer_key` (deterministisch pro Typ); `agent_log_ref`
  behält `section_index` + `tool_name`.
- **Transformiert:** Roh-Resultat → flache Evidence-Items; Fakten werden auf
  10/8/6 pro Kategorie gecappt; Interviews auf 10; Web auf 8.
- **Verloren:** Query-String wird nicht Teil der Identity (bewusst). Bei
  Web ohne URL fehlt der `producer_key` → Item fällt still.
- **LLM vs det.:** Tool-Call ist LLM-getrieben; Evidence-Extraktion aus dem
  Resultat ist deterministisch (`_record_tool_evidence`).
- **Auditierbar:** Ja via `agent_log_ref` + `producer_key`; LLM-Tool-Input
  im `agent_log`.
- **Risiko:** Stummes Fallen bei fehlendem `producer_key` (neue Tool-Typen).
- **Tests:** `test_report_agent_provenance.py`, `test_evidence_routing.py`.

### Stufe 2 — Evidence Normalization (`evidence.py`)

- **Rein:** Rohe `EvidenceItem`-Dicts aus dem Tool-Layer.
- **Raus:** Validiertes `EvidenceRecordModel` mit kanonischer `evidence_id`,
  `source_kind`, `quote?`, `persona_stakeholder_group?`, normalisierten
  Scores.
- **Provenance:** `source_kind` aus `_TYPE_TO_SOURCE_KIND` oder explizit;
  `producer_key` wird durchgereicht.
- **Transformiert:** Typ→SourceKind-Mapping; `auto_downgrade_unsupported_high_claims`
  (high/verified ohne Cross-Stakeholder → medium/low); Hedge-Wort-Scan.
- **Verloren:** Explizites `source_kind` überschreibt Mapping; Fallback
  `inferred`, NIE `seed_corpus`.
- **LLM vs det.:** Deterministisch. LLM nur indirekt (Tool-Resultat).
- **Auditierbar:** Ja — `evidence_id` ist reproduzierbar aus
  (scope, kind, producer_key).
- **Risiko:** `inferred`-Fallback verwässert Source-Quality (Gewicht 0.0),
  aber die Zuordnung zur falschen Quelle ist möglich, wenn das Mapping
  fehlt.
- **Tests:** `test_evidence_identity_contract.py`, Snapshot-Test gegen
  Hedge-Words.

### Stufe 3 — Evidence Identity (`evidence_identity.py`)

- **Rein:** `(scope_id, source_kind, producer_key)`.
- **Raus:** `ev_<sha256[:32]>` + `<prefix>:<sha256[:24]>`.
- **Provenance:** Identity TRÄGT die Provenance (source_kind, producer_key
  sind Hash-Material).
- **Transformiert:** Length-prefixed SHA-256; kein Inhaltstext in der ID.
- **Verloren:** Nichts — aber der Fact-Text ist NICHT in der ID. Zwei
  inhaltsgleiche Facts mit verschiedenen Queries sind zwei Evidence-Items
  (bewusst, sonst Kollisionsrisiko).
- **LLM vs det.:** Rein deterministisch (Hash).
- **Auditierbar:** Ja — ID reproduzierbar nachrechenbar.
- **Risiko:** Run-lokal: über Runs hinweg ist `scope_id` zu prüfen, sonst
  entstehen Pseudo-Dupes oder Pseudo-Neue.
- **Tests:** `test_evidence_identity_contract.py`.

### Stufe 4 — Evidence Index (in-memory im Agent, persistiert als
`evidence-map.json`)

- **Rein:** Validierte `EvidenceRecordModel`-Objekte.
- **Raus:** Lookup nach `evidence_id` für Claim-Binding und Rendering.
- **Provenance:** `evidence_index` trägt `producer_key` + `source_kind`
  pro Eintrag; persistiert in `evidence-map.json` mit `schema_version=3`.
- **Transformiert:** Dedup über `evidence_id`.
- **Verloren:** Kein Inhaltstext in der ID (bewusst).
- **LLM vs det.:** Deterministisch.
- **Auditierbar:** Ja — persistiertes JSON + Migrationskette.
- **Risiko:** Schema-Drift bei alten Maps → Migration nötig; bei
  ValidationError fällt die ganze Map still aus (Issue #987 →
  `EvidenceOmissionModel`).
- **Tests:** `test_output_contract_snapshot.py`, `test_report_pipeline_trust.py`.

### Stufe 5 — Claim Binding (`evidence_binder.py` + `evidence_entailment.py`)

- **Rein:** `claim_text`, `candidates` (Evidence-Items), optional
  `embed` + `judge`.
- **Raus:** Binding mit `retrieval_score`, `match_score`, `entailment`,
  `supports_claim`/`contradicts_claim`, `sentiment_score`.
- **Provenance:** evidence_id wird durchgereicht; Producer-Daten bleiben
  am Item.
- **Transformiert:** Cosine-Ranking (top_k=5, threshold=0.55 im Agent),
  danach regelbasiertes Entailment; optionaler LLM-Judge darf nur
  abschwächen.
- **Verloren:** Items unter Threshold werden nicht gebunden (bewusst).
- **LLM vs det.:** Retrieval det. (Embeddings statisch), Entailment det.
  (Regeln), Judge optional LLM.
- **Auditierbar:** Ja — Scores und Entscheidung pro Binding.
- **Risiko:** Schwaches Embedding-Modell → niedrige Retrieval-Scores →
  Claim wird zur Hypothese (Cascade).
- **Tests:** `test_evidence_routing.py`, `test_orphan_claim_routing.py`.

### Stufe 6 — Evidence Gating (Contract-Validatoren, ADR-0002)

- **Rein:** `ReportClaimModel` mit `confidence`, `evidence_refs`,
  `aggregation_basis`, `source_kind`-Verteilung.
- **Raus:** Validiertes Claim oder ValidationError →
  `degrade_sections_for_violations`.
- **Provenance:** Validatoren prüfen, dass die Confidence zur
  Source-Quality passt (`verified_needs_strong_match` ≥0.85,
  `cross_stakeholder_for_high` fordert ≥2 Stakeholder,
  `reject_inferred_in_high_confidence` verweigert `inferred` bei high).
- **Transformiert:** Claims werden nicht umgeschrieben, sondern
  weggeroutet (Hypothese/data_gap) oder gedowngraded.
- **Verloren:** Claims werden nicht gelöscht, sondern umklassifiziert.
- **LLM vs det.:** Deterministisch (Pydantic-Validatoren).
- **Auditierbar:** Ja — `gate_decision_log` pro Routing-Entscheidung.
- **Risiko:** Validator-Versagen → `degradation_log` → harte Entfernung
  im 2. Versuch (`agent.py:_save_evidence_section`).
- **Tests:** Contract-Tests in `tests/contracts/`, Snapshot
  `evidence-gating-hedge-words.txt`, `test_report_agent_quote_anchors.py`.

### Stufe 7 — Confidence (`confidence_calculator.py`)

- **Rein:** Evidence-Items mit Scores + `contradiction_penalty`.
- **Raus:** `(score, label)` + Breakdown (`source_fidelity`,
  `simulation_consensus`).
- **Provenance:** Source-Quality fließt als Gewicht ein (`graph_fact=1.0`
  … `model_generated_inference=0.0`).
- **Transformiert:** Gewichtete Summe + Caps + Penalties + Echo-Cap.
- **Verloren:** Caps sind bewusst konservativ (wenig Evidence → max 0.59).
- **LLM vs det.:** Deterministisch.
- **Auditierbar:** Ja — `compute_confidence_breakdown` liefert Komponenten.
- **Risiko:** `model_generated_inference`-Only-Claims erreichen nie eine
  Confidence > 0 — sie enden als Hypothese (korrekt).
- **Tests:** `test_report_pipeline_trust.py`.

### Stufe 8 — Hypothesen / Data Gaps

- **Rein:** Claims, die das Gating nicht bestanden haben (<2 evidence_refs,
  0 supporting, medium/high/verified ohne Evidence, LLM-proposed
  Hypothesen).
- **Raus:** `Hypothesis` (mit `rationale`, `suggested_evidence`) oder
  `DataGap` (mit `severity`, `suggested_fixes`).
- **Provenance:** Hypothesen haben KEINE `evidence_refs` (bewusst).
- **Transformiert:** `dedup_and_cap_hypotheses` (rapidfuzz ≥0.88), sortiert
  nach `suggested_evidence`-Länge (NICHT `confidence_score`, Issue #1083),
  visible ≤5, Appendix ≤50 (Contract-Limit).
- **Verloren:** Appendix-Überhang wird verworfen (`hypothesis_cap.py:101`).
- **LLM vs det.:** Det. Dedup/Cap; Hypothesen-Text aus LLM.
- **Auditierbar:** Ja — `gate_decision_log` dokumentiert den
  Reviewer-Floor (`reviewer_floor_insufficient_evidence`).
- **Risiko:** Stummes Verwerfen im Appendix-Cap.
- **Tests:** `test_orphan_claim_routing.py`.

### Stufe 9 — Renderer (`markdown_renderer.py`)

- **Rein:** `ReportV3`-Objekt (schema_version=4).
- **Raus:** Markdown mit Mode-Banner, `Evidenzstatus`-Tabelle,
  Tabellen für Personas/Segments/Claims/Hypothesen/Data Gaps.
- **Provenance:** Claims-Tabelle zeigt `evidence_refs` (kommasepariert).
  Simulierte Quotes haben den Hinweis „Simulationsevidenz, keine empirische
  Nutzerforschung" (`render_evidence_status`).
- **Transformiert:** Structured → Tabellen; keine Neuerzeugung.
- **Verloren:** Producer-Keys erscheinen NICHT im Markdown-Report (nur
  `evidence_refs` als IDs).
- **LLM vs det.:** Deterministisch.
- **Auditierbar:** Bedingt — ID sichtbar, aber Producer nur über
  `evidence-map.json` auflösbar.
- **Risiko:** Leser sieht nur die ID, nicht die Quelle (außer via Export).
- **Tests:** `test_output_contract_snapshot.py`.

### Stufe 10 — Export (`report_export.py`, `evidence_migrations.py`)

- **Rein:** `report_id`, `raw_evidence_map`.
- **Raus:** `ReportContractModel` (JSON), ZIP-Bundle
  (report-v3.md/json, evidence-map.json, personas/segments/claims.csv,
  usage/budget.json), CSV-Tabellen.
- **Provenance:** `evidence-map.json` enthält den vollständigen
  `evidence_index` + `sections` + `gate_decision_log` + `degradation_log`.
  `_normalized_evidence_map` (Issue #1036) migriert kanonisch für ALLE
  Formate.
- **Transformiert:** Migration `v1→v2→v3`, Omission-Modell bei
  ValidationError.
- **Verloren:** Bei `contract_violation` fällt die Evidence-Map STUMM aus
  Envelope, dokumentiert via `EvidenceOmissionModel` (`reason`,
  `detail`, `validation_errors`). Report-Rumpf bleibt.
- **LLM vs det.:** Deterministisch.
- **Auditierbar:** Ja — Envelope trägt `exported_at`,
  `schema_version=2`; Omission ist explizit sichtbar.
- **Risiko:** Ein Report ohne gültige Evidence-Map ist von einem ohne
  Evidence nur über das Omission-Modell unterscheidbar (vor #987 stumm).
- **Tests:** `test_output_contract_snapshot.py`, Export-Tests.

## Claim-Binding-Mechanismus (Maschinenlesbarkeit / Auditierbarkeit)

Der Binding-Pfad (`evidence_binder.bind_evidence_to_claim`) ist
MASCHINENLESBAR und AUDITIERBAR:

1. **Retrieval (Stage 1):** Cosine-Embedding über Claim-Text vs.
   Evidence-Snippet → `retrieval_score`. `top_k=5`, Threshold 0.55 im
   Agent-Pfad (Default 0.65 im Binder). Deterministisch gegeben festes
   Embedding-Modell.
2. **Entailment (Stage 2):** `classify_evidence` aus
   `evidence_entailment.py` — drei regelbasierte Pfade (numerisch, Mengen,
   qualitativ) mit `NumericFact` (`value`, `unit`, `subject`,
   `predicate`, `modality`). Ausgabe: `SUPPORTED`/`CONTRADICTED`/
   `NEUTRAL`. `SUPPORTED` setzt `supports_claim=True`;
   `CONTRADICTED` setzt `contradicts_claim=True`.
3. **LLM-Judge (optional):** Darf `SUPPORTED` nur zu `NEUTRAL`
   abschwächen, niemals hochsetzen oder erfinden.
4. **Persistenz:** `ClaimEvidenceBindingModel` referenziert die
   `evidence_id` (nicht den Text), zusätzlich `match_score`,
   `retrieval_score`, `entailment`, `supports_claim`, `contradicts_claim`,
   `sentiment_score`. `EvidenceMapModel.validate_evidence_cross_references`
   prüft referenzielle Integrität der `evidence_refs` gegen den Index.
5. **Traceability-Kette (verifiziert am Code):**
   - Report-Aussage (Claim) trägt `evidence_refs: ["ev_<hash>"]`.
   - `ev_<hash>` ist deterministisch aus `(scope_id, source_kind,
     producer_key)`.
   - `producer_key` trägt den Fact-Text (Graph) bzw. die Interview-Metain
     (Topic/Agent/Frage/Antwort) bzw. die URL (Web).
   - `agent_log_ref` zeigt auf `section_index` + `tool_name` → Tool-Log.
   - Exportiert als `evidence-map.json` mit `evidence_index` + `sections`
     + `gate_decision_log` + `degradation_log`.
   - `<simulated_quote seed_anchor="ev_...">` bindet Fließtext an dieselbe
     ID; `validate_quote_anchors` prüft das.

   **Lücke:** Der Markdown-Renderer zeigt nur die `evidence_refs`-IDs,
   nicht die Producer-Details. Der Leser muss das `evidence-map.json`
   hinzuziehen, um die Quelle zu sehen. Im reinen Markdown-Export (ohne
   ZIP) ist Traceability nur ID-basiert.

## Gate-Entscheidungen & Degradation (strict/balanced/explorative)

- **Mode-Default:** `balanced` (`report_v3.py`). Mode kommt via Query-Param
  `mode` in `/api/report/<id>/generate` und wird in
  `_resolve_report_mode()` gegen `Literal["strict","balanced","explorative"]`
  validiert (`api/report.py`).
- **`balanced`/`explorative`:** Claims ohne Evidence werden übersprungen
  (nicht zu Hypothesen), `speculative`/`low` Claims werden behalten.
  `explorative` lässt alle Claims durch, markiert sie aber.
- **`strict`:** `speculative`/`low`-Claims werden GEDROPPED (nicht
  routen). Claims ohne Evidence werden gedroppt. `<2 evidence_refs` →
  Hypothese. `verified` ohne starke Evidence → Hypothese + data_gap.
- **`gate_decision_log` (regulär):** Pro Routing-Entscheidung mit
  `reason` (z.B. `reviewer_floor_insufficient_evidence`,
  `cross_stakeholder_missing`, `orphan_medium_to_data_gap`). Bleibt im
  `EvidenceMapModel`.
- **`degradation_log` (Reparatur):** Wird nur bei ValidationError durch
  `degrade_sections_for_violations` geschrieben — drei Reparaturregeln:
  `downgraded_to_low`, `moved_to_hypotheses`, `dropped`. Trägt
  `apply_degradation_downgrade`, das ein `COMPLETED` auf `INCOMPLETE`
  senkt, wenn repariert wurde (Issue #1006, `workflow.py:1216`).
- **2. Versuch:** Wenn die reparierte Map noch immer ValidationError
  wirft, folgt harte Entfernung der fehlerhaften Claims
  (`agent.py:_save_evidence_section`).
- **Degradation-Risiken:** Die harte Entfernung kann Claims still
  verschwinden lassen, die eigentlich nur ein Validator-Edgecase waren
  (z.B. bei Schema-Drift). Der `degradation_log` macht das aber
  nachträglich sichtbar.

## Confidence-Berechnung & Widerspruchserkennung

- **Formel:** `0.40*relevance + 0.25*source_quality + 0.20*specificity
  + 0.15*consistency − penalty` (`confidence_calculator.py`).
- **`relevance`:** Durchschnitt der `match_score`-Werte der gebundenen
  Evidence.
- **`source_quality`:** Maximaler Source-Weight der gebundenen Items
  (graph_fact=1.0, relationship_chain=0.95, agent_quote/agent_behavior≈0.75,
  agent_action=0.7, model_generated_inference=0.0).
- **`specificity`:** Misst, wie eng die Evidence zum Claim passt
  (Topic-Overlap + numerische Coverage).
- **`consistency`:** `1 − pstdev(sentiment_score)` normalisiert.
- **Caps:** `<2 Items → max 0.59`; `alle match_scores<0.55 → max 0.64`;
  `verified → ≥0.85 + ≥2 Quellen`.
- **Widerspruch (MAI-14):** `_has_contradiction` feuert, wenn
  `pstdev(sentiment) > 0.6` ODER `(min < −0.3 UND max > 0.3)` → Penalty
  `0.20`. Zusätzlich `detect_contradiction_penalty`: +0.15 pro
  `supports_claim=False`/`contradicts_claim=True`-Flag oder Stance-Konflikt,
  max 0.5.
- **`confidence_scope`:** Lokal pro Claim; es gibt keine globale
  Confidence. Globale Signale (Echo-Index) wirken über `apply_echo_cap`
  (Cross-Stakeholder-Claim mit `echo_index>0.75` → max 0.84/medium).
- **Label-Schwellen:** `verified` ≥ 0.85, `high` ≥ 0.7, `medium` ≥ 0.5,
  `low` < 0.5, `speculative` < 0.35.

## Provenance im Export (bleibt sie erhalten?)

**Ja, mit einer wichtigen Lücke:**

- **JSON-Export (`?format=json`):** `ReportContractModel` mit
  `evidence: EvidenceMapModel` — enthält `evidence_index` (alle Items mit
  `producer_key`, `source_kind`, `quote?`), `sections` (Claims mit
  `evidence_refs` + Bindings), `gate_decision_log`, `degradation_log`,
  `schema_version`. Vollständige Traceability.
- **ZIP-Export:** `evidence-map.json` (normalisiert via
  `_normalized_evidence_map`), `report-v3.json`, `report-v3.md`,
  `personas.csv`, `segments.csv`, `claims.csv`, `usage.json`,
  `budget.json`. Claims-CSV referenziert `evidence_refs`. Traceability
  intakt, wenn `evidence-map.json` mitgeliefert wird.
- **CSV-Export (`?format=csv&table=claims`):** Nur Claims-Tabelle —
  `evidence_refs` als kommaseparierte IDs. KEINE Producer-Details. Um
  die Quelle aufzulösen, muss der Konsument das JSON/ZIP hinzuziehen.
- **Markdown-Export (`?format=md`):** Nur `render_report_v3`-Output —
  IDs sichtbar, Producer-Details fehlen. Reiner MD-Export ist nur
  ID-basiert traceable.
- **Omission-Modell:** Schlägt die Migration fehl, fällt die Map aus dem
  Envelope, dokumentiert via `EvidenceOmissionModel` mit
  `reason="contract_violation"`, `detail`, `validation_errors`. Report
  bleibt, aber Traceability endet beim Report.

**Traceability-Check (kritisch):** Eine finale Report-Aussage IST
rückwärts bis zur Quelle verfolgbar — ABER nur, wenn (a) der Konsument das
`evidence-map.json` mitliest (ZIP/JSON) und (b) die Migration nicht
fehlgeschlagen ist. Im reinen Markdown-Export ist die Quelle nur als
`ev_<hash>`-ID sichtbar, ohne Producer-Auflösung. Das ist eine bewusste
Trennung (MD für Menschen, JSON/ZIP für Audit), aber eine
Konsumenten-Seite-Risiko.

## LLM im Report-Pfad

- **Section-Generation:** LLM erzeugt den Section-Inhalt nach
  `SECTION_SYSTEM_PROMPT_TEMPLATE` inkl. `<evidence_gating priority="hard">`.
  LLM darf nur Claims schreiben, für die es `evidence[]` im
  Section-Kontext hat (Anti-Dekorations-Guard in `_build_claims_for_section`).
- **Outline-Planning:** LLM baut die Outline.
- **Red-Team-Review:** `_run_red_team_review` (Track 3b) — LLM-Judge
  prüft Claims auf Schwächen; `BudgetExceededError` wird durchgereicht,
  nicht verschluckt (`workflow.py:1273-1284`, Issue #978).
- **Entailment-Judge (optional):** LLM darf SUPPORTED nur abschwächen.
- **Kein LLM:** Identity, Normalisierung, Binding (Cosine+Regeln),
  Confidence, Gating-Validatoren, Hypothesen-Cap, Renderer, Export.

## Gaps

1. **Markdown-Export ohne Producer-Auflösung.** Reiner `?format=md`
   zeigt nur `ev_<hash>`-IDs. Konsument muss JSON/ZIP ziehen, um die
   Quelle zu sehen. Für einen menschlichen Leser ist Traceability
   unvollständig, es sei denn, er kennt die ID-Mapping-Datei.
2. **Stummes Fallen bei fehlendem `producer_key`** für neue Tool-Typen.
   `register_evidence_record` verwirft Items ohne Key still — ein
   Audit-Flag wäre wünschenswert.
3. **Omission ist sichtbar, aber nicht blockierend.** Bei
   `contract_violation` fällt die ganze Evidence-Map aus dem Envelope.
   Der Report-Rumpf bleibt, aber die Traceability-Kette bricht. Es gibt
   keinen Hardstop, der den Export verweigern würde.
4. **`inferred`-Fallback verwässert Source-Quality.** Items ohne klares
   Mapping werden `inferred` (Gewicht 0.0) und ziehen die Confidence
   runter, ohne dass der Leser sofort sieht, dass die Zuordnung fehlte.
5. **Run-lokale Identity.** `evidence_id` hängt von `scope_id` ab. Bei
   Cross-Run-Vergleichen müssen Scope-IDs stabil sein, sonst entstehen
   Pseudo-Dupes. Aktuell nicht explizit dokumentiert.
6. **Appendix-Cap verwirft still.** `dedup_and_cap_hypotheses` dropt
   Hypothesen >50 im Appendix (Contract-Limit). Log-Eintrag existiert,
   aber der Leser des Reports sieht nur die verbleibenden.
7. **2. Versuch der harten Entfernung.** Wenn `degrade_sections_for_violations`
   die Map nicht reparieren kann, werden Claims hart entfernt. Das ist
   ein Risiko bei Schema-Drift, der `degradation_log` macht es aber
   nachträglich sichtbar.
8. **Echo-Index benötigt Cross-Stakeholder-Claims.** `apply_echo_cap`
   greift nur bei Cross-Stakeholder. Echo-Kammern innerhalb einer
   Stakeholder-Gruppe werden nicht separat bestraft.

## 14-Zeilen-Zusammenfassung

1. Evidence-Identity ist deterministisch via SHA-256 über
   (scope_id, source_kind, producer_key) — KEIN Inhaltstext in der ID.
2. `producer_key` trägt die Provenance (Fact-Text bei Graph,
   Topic/Agent/Frage/Antwort bei Interview, URL bei Web).
3. Claim-Binding ist zweistufig: Cosine-Retrieval (threshold 0.55/0.65)
   + regelbasiertes Entailment; LLM-Judge optional und nur abschwächend.
4. Confidence-Formel: 0.40·relevance + 0.25·source_quality + 0.20·specificity
   + 0.15·consistency − penalty, mit Caps (<2 Items → 0.59) und
   source_quality-Gewichtungen (graph_fact=1.0, inferred=0.0).
5. MAI-14 Sentiment-Widerspruch straft mit 0.20 (pstdev>0.6 oder
   min<−0.3 ∧ max>0.3); Echo-Cap drosselt Cross-Stakeholder-Echo auf 0.84.
6. ADR-0002 hat 5 Hartanker (hard-Prompt-Block, Hedge-Words-Snapshot,
   Enum, Cross-Stakeholder-Validator, Reject-Inferred-Validator) —
   unantastbar ohne `0002-supersedes.md` + User-Signoff.
7. Mode-Routing: balanced/explorative überspringen Claims ohne Evidence,
   strict dropt speculative/low; `<2 evidence_refs` → Hypothese;
   verified ohne starke Evidence → Hypothese + data_gap.
8. Graceful Degradation (Issue #1006) trennt `gate_decision_log`
   (regulär) von `degradation_log` (Validator-Reparatur mit 3 Regeln);
   `apply_degradation_downgrade` senkt COMPLETED → INCOMPLETE.
9. `<simulated_quote seed_anchor="ev_...|seed_doc:...">` ist die
   Text↔Evidence-Brücke; `validate_quote_anchors` prüft gegen
   `known_anchors` + `persona_ids`.
10. Hypothesen werden via `dedup_and_cap_hypotheses` (rapidfuzz ≥0.88)
    dedupliziert, nach `suggested_evidence`-Länge sortiert (Issue #1083
    kein `confidence_score`), visible ≤5, Appendix ≤50.
11. Red-Team-Review läuft als LLM-Judge nach Section-Assembly;
    `BudgetExceededError` wird durchgereicht (Issue #978), nicht
    verschluckt.
12. Export ist Provenance-erhaltend in JSON/ZIP via
    `normalize_persisted_evidence_map` (Issue #1036 — eine kanonische
    Stelle für alle Formate); CSV/MD zeigen nur `evidence_refs`-IDs.
13. Bei `contract_violation` fällt die Evidence-Map STUMM aus dem
    Envelope, dokumentiert via `EvidenceOmissionModel` (Issue #987) —
    Report-Rumpf bleibt, Traceability endet beim Report.
14. Traceability-Kette ist im Code verifizierbar: Claim.evidence_refs →
    evidence_id (SHA-256) → producer_key → agent_log_ref (tool_name,
    section_index) → Tool-Log; Lücke: reiner MD-Export zeigt nur IDs,
    nicht die Producer-Details.