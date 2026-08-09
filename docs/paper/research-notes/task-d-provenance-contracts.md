# Task D — Provenance-Verträge, Issue #1152, ADRs

## Sources (Source-Type: official, As Of: 2026-08-09)
- [D1] `backend/app/contracts/report_contract.py:36-159` — EvidenceType, EvidenceSourceKind, EvidenceItemModel (official)
- [D2] `backend/app/contracts/document_manifest_contract.py:1-85` — DocumentManifest / DocumentAnchoredChunk, „Teil A" (official)
- [D3] `backend/app/services/report_agent/evidence.py:44-90, 179-198, 270-352` — _TYPE_TO_SOURCE_KIND, has_agent_grounded_evidence, _SEED_DOC_PREFIX, opake Anker-Akzeptanz (official)
- [D4] `backend/app/services/graph_build.py:350, 439` — Blob-Chunking (official)
- [D5] `backend/app/api/graph_build.py:231-238` — derive_document_id (nur Sidecar) (official)
- [D6] `docs/decisions/0013-seed-corpus-document-anchor.md` — ADR-0013 (official)
- [D7] `docs/decisions/0011-evidence-entailment-and-provenance.md` — ADR-0011 (official)
- [D8] `docs/decisions/0002-evidence-gating.md` — ADR-0002 (official, Referenz)
- [D9] GitHub Issue #1152 (Triage-Notizen, verifiziert am Code Stand d7d9f0a4) — community (Hinweis, gegen Code verifiziert)
- [D10] `backend/app/services/evidence_identity.py` — build_evidence_id(scope_id, source_kind, producer_key), source_kind im Hash (Referenz aus ADR-0013 §4)

## Findings (code-verifiziert)
1. `EvidenceType` (report_contract.py:36) kennt KEIN `seed_document` — aber `_TYPE_TO_SOURCE_KIND` mappt bereits fiktiv `"seed_document" → "seed_corpus"` (evidence.py:46), ein Vorgriff auf ADR-0013 §5, der im Contract noch nicht umgesetzt ist. [D1][D3][D6]
2. `EvidenceSourceKind` (report_contract.py:51) hat sechs Werte: seed_corpus, agent_quote, agent_action, graph_relation, web_source, inferred. Default an `EvidenceItemModel.source_kind` ist `inferred` (report_contract.py:159) — ADR-0011 hat den früheren Default `seed_corpus` bewusst ersetzt („unbekannte Herkunft ist abgeleitet, nicht belegt"). [D1][D7]
3. `_TYPE_TO_SOURCE_KIND` (evidence.py:44) mappt `graph_fact/graph_metric/relationship_chain/entity_summary` → `graph_relation`, `agent_post/agent_quote/agent_interview` → `agent_quote`, `agent_action/agent_behavior` → `agent_action`, `web_*` → `web_source`. `seed_corpus`/`seed_document` → `seed_corpus`. Alles Unbekannte → `inferred`. [D3]
4. **Seed-Aussagen erreichen den evidence_index nur als `graph_relation`.** Die Graph-Tool-DTOs `SearchResult.facts` etc. sind `List[str]` ohne Herkunft (ADR-0013 §1, gh #1152). `_record_tool_evidence` mappt einen Fakt ohne Dokumentbezug auf `source_kind=graph_relation` — ein echtes `seed_corpus`-Item entsteht so nicht. [D3][D6][D9]
5. **`has_agent_grounded_evidence` (evidence.py:179) verlangt mind. 1 `agent_quote` UND 1 `seed_corpus`.** Da `seed_corpus`-Items faktisch nicht entstehen (Finding 4), ist die Confidence-Stufe `medium` (ADR-0002) im laufenden System **nicht erreichbar**. ADR-0013 §3 bestätigt das. [D3][D6]
6. **Der `seed_doc:`-Anker ist opak und unverifiziert.** `evidence.py:352`: `# seed_doc:-Prefix ist immer akzeptiert (opaque Referenz)`. Einziges Kriterium: non-`seed_doc:`-Anker müssen in `known_anchors` stehen. Ein `seed_doc:<irgendwas>`-String wird ungeprüft akzeptiert — das LLM benennt seine eigene Quelle, niemand prüft nach (ADR-0013 §1.3). [D3][D6]
7. **Dokumentidentität existiert im Graph-Layer nicht.** `services/graph_build.py:350` holt `text = ProjectManager.get_extracted_text(project_id)` (konkatenierter Blob) und chunkt mit `TextProcessor.split_text` (graph_build.py:439) — nicht mit dem dokumentbewussten `split_text_into_chunks_with_documents`. `document_id`/`chunk_id` kommen in `services/graph_build.py` und `services/graph/` nicht vor (grep leer). [D4][D5]
8. **Teil A (Sidecar) existiert, Teil B (Neo4j-Persistenz + Retrieval → echter Anker) fehlt.** `api/graph_build.py:231` ruft `derive_document_id` auf und schreibt den Manifest-Sidecar (Teil A). Der Service-Layer nutzt ihn nicht fürs Chunking/Episoden. `DocumentAnchoredChunk.document_id/chunk_id` sind ohne Manifest `None` — „geraten wird nicht" (document_manifest_contract.py:68). [D2][D5][D6]
9. `Neo4jGraphStorage.add_text` erzeugt `episode_id = uuid4()` ohne Dateibezug (ADR-0013 §1.2). Bestandsgraphen können nicht nachgerüstet werden (ADR-0013 §3, „kein Backfill, kein Reingest-Zwang"). [D6]
10. `build_evidence_id(scope_id, source_kind, producer_key)` nimmt `source_kind` in den Hash auf (evidence_identity.py, ADR-0013 §4). Ein Downgrade (seed_corpus → inferred) ist ein **Identitätswechsel**, kein Label-Update: `evidence_index`-Keys und alle Claim-Bindungen müssen atomar umgeschlüsselt werden, sonst HTTP 422. [D6][D10]
11. `normalize_persisted_evidence_map` (evidence_migrations.py) stuft persistierte `seed_corpus`-Items ohne verifizierten Anker beim Lesen ab (idempotent, Datei wird nicht mutiert). Claim verliert agent-grounded Basis → `medium` auf `low`. [D6]
12. ADR-0011 führte zweistufiges Binding ein: `retrieval_score` (Cosine, „gleiches Thema?") vs `entailment` (SUPPORTED/CONTRADICTED/RELATED_ONLY/INSUFFICIENT). `supports_claim=True` nur bei SUPPORTED. Deterministische Checks (Zahl/Bezugsgruppe/Modalität) haben Vorrang vor Embedding. Optionaler LLM-Judge darf regelbasiertes SUPPORTED nur abschwächen, nie erzeugen. [D7]
13. ADR-0011 trennt `source_fidelity` (quellentreue Wiedergabe) von `simulation_consensus` (breite Unterstützung unabhängiger simulierter Stakeholder-Gruppen). „Ein korrekt wiedergegebener Seed-Fakt ist ausdrücklich keine Aussage über die reale Bevölkerung." [D7]

## Provenance-Klassifizierung pro Evidence-Typ
| Evidence-Typ / source_kind | Provenance-Status | Begründung (Code-Beleg) |
|---|---|---|
| `seed_corpus` (Zielzustand ADR-0013) | **nicht ausreichend auditierbar (aktuell)** | Anchor opak (evidence.py:352); Teil B fehlt; medium unerreichbar (Finding 5) |
| `agent_quote` (Persona-Interview) | **teilweise provenance-gesichert** | persona_id + stakeholder_group + quote; aber Persona ist LLM-generiert, Opinion-Provenance limitiert (Task B) |
| `agent_action` (Simulation) | **teilweise provenance-gesichert** | sim_action_log; aber rein synthetisch, keine empirische Evidenz |
| `graph_relation` (Graph-Fakt) | **nur syntaktisch referenzierbar** | `List[str]` ohne doc_id/chunk_id; Fakt ohne Dokumentbezug (Finding 4) |
| `web_source` | **teilweise provenance-gesichert** | URL im Anker; aber Fetch-Echtzeit, ggf. verfallen |
| `inferred` (Default) | **LLM-abgeleitet** | bewusst „nicht belegt" — ehrlich, aber kein Beleg |

## Traceability-Check (Kernfrage)
> Kann eine finale Report-Aussage rückwärts bis zu einer konkreten Quelle verfolgt werden?

**Aktuell: Nein, nicht für Seed-Dokumente.** Der Pfad Claim → evidence_id → producer_key → source_kind=seed_corpus → seed_doc:<document_id>#chunk:<chunk_id> bricht an zwei Stellen:
  1. `seed_doc:` ist opak (evidence.py:352) — keine Auflösung gegen echtes Retrieval.
  2. Das Retrieval liefert keine Dokument-/Chunk-Identität (graph_build.py:439, DTOs `List[str]`).
Für `agent_quote`/`agent_action`/`web_source` ist eine syntaktische Referenz vorhanden, aber die Unabhängigkeit der Quelle (Persona-Provenance) ist die Schwachstelle (→ Task B).

## Was für echte End-to-End-Source-Provenance fehlt (ADR-0013 Umsetzung)
1. **Teil B:** `split_text_into_chunks_with_documents` im Service-Layer nutzen statt `TextProcessor.split_text` (graph_build.py:439).
2. `document_id`/`chunk_id` in Neo4j-Episode persistieren (Cypher + Schema).
3. Retrieval-Query liefert `document_id`/`chunk_id` zurück (nicht nur `edge["fact"]`).
4. DTOs `SearchResult.facts` etc. tragen `document_id`/`chunk_id` (kein `List[str]` mehr).
5. `_record_tool_evidence` erzeugt `seed_doc:<document_id>#chunk:<chunk_id>` serverseitig aus Retrieval-Ergebnis; LLM darf ihn weder erfinden noch überschreiben.
6. Opake Akzeptanz (evidence.py:352) wird ersetzt durch Lookup gegen den Sidecar/Retrieval.
7. `EvidenceType.seed_document` wird additiv in den Contract aufgenommen (ADR-0013 §5).
8. Regressionstests für Cross-Reference-Validierung beim Downgrade (Identitätswechsel, Finding 10).

## Gaps
- Confidence-Stufe `verified`: im Contract (report_contract.py:33) definiert, aber welcher Validator sie vergibt, aus Task D nicht ersichtlich (→ Task C).
- `gate_decision_log`: in ADR-0013 §4 referenziert, aber konkrete Persistenz-Struktur in Task D nicht geprüft (→ Task C).
- Ob `_extract_known_anchors` (evidence.py:284) jemals Seed-Anker findet, hängt an Teil B — aktuell leer.
- `producer_key`-Konstruktion im Detail nicht geprüft (→ Task C, evidence_identity).