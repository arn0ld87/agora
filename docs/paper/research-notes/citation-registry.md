# P3 — Citation Registry

AS_OF: 2026-08-09. Repo-HEAD: `7e42ae34` (Branch `feat/1152-document-chunk-provenance`).

Diese Untersuchung ist ein **Code-Audit eines einzelnen Repos**, keine Web-Recherche. Die Source-Governance der Deep-Research-Pipeline (≥30 % official, max Single-Source ≤25 %, ≥5 unique Domains) ist daher sinngemäß anzuwenden: die Quellen sind Code-Belege, ADRs, GitHub-Issues, Referenzlauf-Artefakte und wissenschaftliche Literatur. Der „official“-Anteil ist per Konstruktion sehr hoch (Code + ADRs + Referenzläufe des Repos selbst), da die Untersuchung die Frage beantwortet, ob der Code das tut, was er behauptet — externe Quellen dienen dem übergeordneten Kontext (Forschungsstand), nicht der Verifikation von Code-Aussagen.

**Zitier-Schema:** Präfix-IDs statt bloßer [n], weil Quellentypen heterogen sind und der Leser den Typ sofort erkennen soll.
- `C<n>` — Code-Beleg (`file:line`), Source-Type: official, Authority 10 (das Repo selbst ist Gegenstand der Untersuchung)
- `A<n>` — ADR (`docs/decisions/`), Source-Type: official, Authority 9
- `I<n>` — GitHub-Issue, Source-Type: community (mit Code verifiziert), Authority 6
- `R<n>` — Referenzlauf-Artefakt (Output-Datei in `backend/uploads/` oder `docs/reference-runs/`), Source-Type: official, Authority 8
- `L<n>` — Wissenschaftliche Literatur (arXiv/PMC), Source-Type: academic, Authority laut Task-F-Tabelle

Alle Code-Belege wurden am Branch-Stand `7e42ae34` verifiziert, nicht an README-Behauptungen.

## Code-Belege (C)

| ID | Beleg | Aufgabe | Aussage |
|---|---|---|---|
| C1 | `backend/app/contracts/report_contract.py:36-48` | D | `EvidenceType`-Enum kennt kein `seed_document` |
| C2 | `backend/app/contracts/report_contract.py:51-72` | D | `EvidenceSourceKind`: 6 Werte (seed_corpus, agent_quote, agent_action, graph_relation, web_source, inferred) |
| C3 | `backend/app/contracts/report_contract.py:159` | D | `source_kind`-Default ist `inferred` (nicht `seed_corpus`) |
| C4 | `backend/app/contracts/report_contract.py:130` | A | `source_id_anchor` (max_length=200), optional |
| C5 | `backend/app/contracts/report_contract.py:284-290` | E | `verified` braucht match_score ≥0.85 + ≥2 Stakeholder |
| C6 | `backend/app/contracts/document_manifest_contract.py:26-85` | A,D | `DocumentManifestEntry`/`DocumentManifest`/`DocumentAnchoredChunk` — Teil A Sidecar |
| C7 | `backend/app/services/report_agent/evidence.py:44-90` | D,C | `_TYPE_TO_SOURCE_KIND`: graph_fact→graph_relation (nie seed_corpus) |
| C8 | `backend/app/services/report_agent/evidence.py:179-198` | D,C | `has_agent_grounded_evidence`: agent_quote UND seed_corpus nötig → medium unerreichbar aktuell |
| C9 | `backend/app/services/report_agent/evidence.py:270,352` | A,D,C | `_SEED_DOC_PREFIX="seed_doc:"`, opake Akzeptanz ohne Lookup |
| C10 | `backend/app/services/report_prompts/sections.py:196-197` | A,D,C | `seed_doc:`-Präfix als opake Referenz ohne Lookup akzeptiert (Anker 1: `<evidence_gating priority="hard">`-Block in derselben Datei) |
| C11 | `backend/app/services/graph_build.py:350,439` | A,D | `TextProcessor.split_text` (Blob), nicht `split_text_into_chunks_with_documents` → Teil B nicht gewired |
| C12 | `backend/app/api/graph_build.py:231-238` | A,D | `derive_document_id` nur für Sidecar (Teil A) |
| C13 | `backend/app/utils/file_parser.py:222-250` | A | `derive_document_id` (Suffix-Kollision, ≤120 Zeichen) |
| C14 | `backend/app/utils/file_parser.py:525-723` | A | `split_text_into_chunks` + `split_text_into_chunks_with_documents` (existiert, wird nicht konsumiert) |
| C15 | `backend/app/storage/neo4j_write.py:244` | A | `episode_id = str(uuid.uuid4())` ohne Dateibezug |
| C16 | `backend/app/storage/neo4j_write.py:306-318` | A | `Episode.data` speichert rohen Chunk-String, kein document_id/chunk_id |
| C17 | `backend/app/storage/neo4j_write.py:443-458` | A | `RELATION` trägt `episode_ids`, keine Dokument-Referenz |
| C18 | `backend/app/storage/ner_extractor.py:158-163` | A | `chat_json` mit temperature=0.1, max_tokens=8192; `fact` ist LLM-Freetext, kein Zitat |
| C19 | `backend/app/services/graph/graph_reader.py:57-88` | A,C | `SearchResult.facts: List[str]` ohne Herkunft |
| C20 | `backend/app/services/graph/graph_dtos.py:12-38` | A,C | DTOs `List[str]` — keine doc_id/chunk_id |
| C21 | `backend/app/services/report_agent/agent.py:315-327` | A,C | `_record_tool_evidence`: Graph-Fakten ohne `source_id_anchor` → source_kind=graph_relation |
| C22 | `backend/app/services/report_agent/agent.py:301-452` | C | `producer_key`-Konstruktion pro Typ (graph-fact, interview, web, simulation) |
| C23 | `backend/app/services/evidence_identity.py:18-57` | C,D | `build_evidence_id` (SHA-256 über scope_id+source_kind+producer_key); source_kind im Hash |
| C24 | `backend/app/services/evidence_binder.py` | C,E | zweistufiges Binding: retrieval_score (Cosine) + match_score (Entailment) |
| C25 | `backend/app/services/evidence_entailment.py` | C,E | regelbasiertes Entailment (SUPPORTED/CONTRADICTED/RELATED_ONLY/INSUFFICIENT), deterministische Checks vor Embedding |
| C26 | `backend/app/services/confidence_calculator.py:363-386` | L1,C,E | `apply_echo_cap`: echo_index>0.75 UND cross_stakeholder → max 0.84, high/verified→medium |
| C27 | `backend/app/services/confidence_calculator.py:57-351` | C,E | Confidence-Formel: 0.40·relevance + 0.25·source_quality + 0.20·specificity + 0.15·consistency − penalty; Caps |
| C28 | `backend/app/services/network_analytics.py:13` | L1 | echo-chamber index = intra-cluster/total |
| C29 | `backend/app/services/report_agent/workflow.py:142-162` | L1 | `_get_echo_index` liest echo_chamber_index live |
| C30 | `backend/app/services/report_agent/workflow.py:165` | L1,C | `_RED_TEAM_SYSTEM_PROMPT`: Wording-Glossar (verbietet Vorhersage) |
| C31 | `backend/app/services/report_agent/workflow.py:1216` | C | `apply_degradation_downgrade`: COMPLETED→INCOMPLETE bei Validator-Reparatur (Issue #1006) |
| C32 | `backend/app/services/report_agent/workflow.py:1273-1284` | C | Red-Team-Review; `BudgetExceededError` wird durchgereicht (Issue #978) |
| C33 | `backend/app/services/report_agent/workflow.py:428,545,630` | E | `min_tool_calls=3` erzwungen; `MAX_TOOL_CALLS_PER_SECTION=5` |
| C34 | `backend/app/services/report_agent/agent.py:93` | E | `MAX_TOOL_CALLS_PER_SECTION=5` |
| C35 | `backend/app/services/report_agent/manager.py:244-413` | C | Mode-Routing: balanced/explorative überspringen Claims ohne Evidence; strict dropt speculative/low |
| C36 | `backend/app/services/report_agent/hypothesis_cap.py` | C | `dedup_and_cap_hypotheses` (rapidfuzz ≥0.88), sortiert nach suggested_evidence-Länge (Issue #1083) |
| C37 | `backend/app/services/report_export.py:87-152` | C | Export: `normalize_persisted_evidence_map` (Issue #1036); EvidenceOmissionModel (Issue #987) — Evidence-Map fällt stumm bei contract_violation |
| C38 | `backend/app/services/evidence_migrations.py` | C,D | `normalize_persisted_evidence_map` — Downgrade persistierter seed_corpus-Items ohne Anker beim Lesen |
| C39 | `backend/app/services/report_agent/markdown_renderer.py` | C | Renderer: zeigt nur `evidence_refs`-IDs, nicht Producer-Details |
| C40 | `backend/app/llm/providers/registry.py:7-60,136-381` | E | `detect_provider` — SSoT; bewusste Divergenz http/oasis |
| C41 | `backend/app/services/oasis_profile_generator.py` (1796 LOC) | E | größter Einzel-Block OASIS/CAMEL ~5500 LOC |
| C42 | `backend/app/services/simulation_runner.py:1-60` | E | keine Determinismus/seed-Flags |
| C43 | `backend/app/contracts/report_v3.py` | C | `ReportMode`, `ReportV3` (schema_version=4), `Claim.evidence_refs` |
| C44 | `backend/app/api/report.py` | C | `/generate` (mode-Param), `/<id>/evidence`, `/<id>/export` |
| C45 | `backend/app/services/network_analytics.py:426-432` | B2 | `echo_chamber_index = intra/total` über Louvain-Communities auf gewichtetem Interaktionsgraph |
| C46 | `backend/scripts/run_parallel_simulation.py:1423,1434,1437` | B2 | `random.uniform/random.random/random.sample` **ohne** `random.seed()` — Simulation nicht deterministisch |
| C47 | `backend/app/services/network_analytics.py:405` | B2 | `louvain_communities(graph, weight="weight", seed=42)` — einzige Determinismus-Insel (nur Metrik, nicht Action-Input) |
| C48 | `backend/app/services/report_agent/agent.py:293-295` | B2 | `agent_action` producer_key = `simulation-action:<platform>:<round>:<agent>:<action>:<ts>` |
| C49 | `backend/app/services/report_agent/evidence.py:120-122` | B3 | `register_evidence_record`: `if not producer_key: return None` — stiller Drop (Pre-Fix-Breachstelle des Interview-Binding) |
| C50 | `backend/app/services/report_agent/agent.py:365-413` | B3 | Interview-Zweig (Fix `d7d9f0a4`): setzt nun `producer_key`, `quote`, `persona_stakeholder_group`, `type=agent_interview`; setzt **nicht** `supports_claim` |
| C51 | `backend/app/services/evidence_identity.py:37-57` | B3 | `build_producer_key(f"interview:s{section}", topic, agent, question, response)` — deterministisch |
| C52 | `backend/app/services/persona_quota_defaults.py:1-111` | B1 | `default_dach_industry_quota` — Destatis WZ 2008 / BA / Statista, IT-Cap ≤12 % (Issue #215), Largest-Remainder |
| C53 | `backend/app/services/persona_demographics.py:1-80` | B1 | `DACH_NAME_ORIGIN_QUOTAS` — Destatis Mikrozensus 2024 / BFS / Statistik Austria; Konstanten |
| C54 | `backend/app/services/simulation_config_generator.py:1072-1085` | B1 | Simulation-Floor ≥30 Personas (`AGORA_ALLOW_SMALL_SIM=1` übersteuerbar); Skeptiker-Quota ≥20 % `stance="opposing"` |
| C55 | `backend/tests/services/test_report_tool_evidence.py:110` | B3 | `test_interview_response_gets_canonical_evidence_id` — verifiziert Fix-Pfad: 2 Interviews → 2 `agent_interview`-Records mit gültiger `evidence_id` |
| C56 | `backend/app/services/report_agent/agent.py:388-404` | B1,B3 | `persona_stakeholder_group`-Zuweisung bei Interview (Fallback `agent_role → agent_name → "unbekannt"`); `supports_claim` nicht gesetzt |
| C57 | `backend/app/services/sim/run_state_store.py:170` + `backend/app/api/simulation_run.py` (leer) | B2 | `simulated_hours` in `run_state.json`, aber nicht in API/Frontend exponiert (Issue #1018 bestätigt) |

## ADRs (A)

| ID | ADR | Status | Aussage |
|---|---|---|---|
| A1 | `docs/decisions/0002-evidence-gating.md` | akzeptiert | 5 Hartanker: hard-Prompt-Block, Hedge-Words-Snapshot, Enum `EvidenceSourceKind`, `cross_stakeholder_for_high`, `reject_inferred_in_high_confidence` — unantastbar ohne `0002-supersedes.md` + User-Signoff |
| A2 | `docs/decisions/0007-embedding-configuration-and-index-migration.md` | akzeptiert | Embedding-Config in JSON-Datei (nicht Neo4j); Migrations-Lifecycle pending→running→validating→completed/failed/rolled_back |
| A3 | `docs/decisions/0011-evidence-entailment-and-provenance.md` | akzeptiert (2026-07-27) | Default source_kind=inferred (ersetzt seed_corpus); zweistufiges Binding; Referenzlauf report_d9023bd1f55a (sim_7058c126da03), „formal valide, inhaltlich nicht vertrauenswürdig“; 7 code-belegte Ursachen |
| A4 | `docs/decisions/0013-seed-corpus-document-anchor.md` | akzeptiert (2026-08-09) | `seed_doc:<document_id>#chunk:<chunk_id>` Anker verpflichtend für seed_corpus; Teil A (Sidecar) umgesetzt, Teil B (Neo4j-Persistenz+Retrieval) offen; „Das LLM benennt seine eigene Quelle, niemand prüft nach“ |
| A5 | `docs/decisions/0012-run-budgets.md` | akzeptiert | Run-Budgets, BudgetExceededError |

## Issues (I)

| ID | Issue | Status | Relevanz |
|---|---|---|---|
| I1 | #1152 | Branch/ offen | Seed-Chunk-Provenance — Slice 1 Teil A umgesetzt, Teil B offen |
| I2 | #1153 | offen | ADR-0013 |
| I3 | #1155 | offen | Codex-Findings zu PR (Teil A) |
| I4 | #1086 | offen | Entscheidungsvorlage ADR-0013 |
| I5 | #1008 | offen | Vorarbeit ADR-0013 |
| I6 | #1006 | verifiziert am Code | Graceful Degradation: gate_decision_log vs degradation_log |
| I7 | #1036 | verifiziert am Code | eine kanonische Migrationsstelle für alle Export-Formate |
| I8 | #987 | verifiziert am Code | EvidenceOmissionModel — Evidence-Map fällt stumm bei contract_violation |
| I9 | #978 | verifiziert am Code | BudgetExceededError wird durchgereicht |
| I10 | #1083 | verifiziert am Code | Hypothesen-Sortierung nach suggested_evidence-Länge, nicht confidence_score |
| I11 | #1012 | offen | herabgestufter Claim behält ungehedgten Wortlaut (Downgrade-Pfad) |
| I12 | #263 | offen | Vector-Index IF-NOT-EXISTS-Falle bei Embedding-Wechsel |

## Referenzläufe (R)

| ID | Artefakt | Datum | Befund |
|---|---|---|---|
| R1 | `backend/uploads/reports/report_e2e_trust01/evidence_map.json` + `report-v3.json` | historisch | 25 Claims alle medium, 125 Evidence 100% inferred, 0 source_id_anchor — Vor-Fix-Zustand ADR-0011 |
| R2 | `docs/reference-runs/2026-08-09-domain-migration-v2/` | 2026-08-09 | 0 validierte Claims, 30 Hypothesen, 12 Evidence-Items (8 agent_action, 4 graph_metric), Interview→Evidence-Binding-Defekt, validated_claims_total:0 |
| R3 | `docs/reference-runs/2026-08-09-domain-migration/` | 2026-08-09 | Vorgängerlauf v1 |
| R4 | ADR-0011 Referenzlauf `report_d9023bd1f55a` (sim_7058c126da03) | 2026-07-27 | 30 Agents, 315 Interaktionen, 5 Cluster, Echo-Index 0.4317, „formal valide, inhaltlich nicht vertrauenswürdig“ — Ursprung der Evidence-Pipeline |

## Literatur (L)

Vollständige Tabelle in `task-f-literature.md`. Kern-Quellen für diese Untersuchung:

| ID | Kurztitel | Authority | Verwendung |
|---|---|---|---|
| L1 | Park et al. 2023 — Generative Agents (arxiv:2304.03442) | 9/10 | Kontext: OASIS-Vorläufer, qualitative Validierung, nicht populationsrepräsentativ |
| L2 | Argyle et al. 2022 — Silicon Samples (arxiv:2209.06899) | 9/10 | Kontext: LLM-Persona-Conditioning reproduziert Antwortverteilungen, aber prompt-abhängig |
| L3 | Bail 2024 — GenAI in social science (PMC11127003) | 9/10 | Kontext: Warnt vor Homogenität, Halluzination, fehlender Validierung |
| L4 | Edge et al. 2024 — GraphRAG (arxiv:2404.16130) | 9/10 | Kontext: GraphRAG überlegen bei globalen QFS-Fragen |
| L5 | Du et al. 2023 — Multiagent Debate (arxiv:2305.14325) | 8/10 | Kontext: MAD verbessert Factuality, sättigt bei großen Modellen |
| L6 | Wang et al. 2022 — Self-Consistency (arxiv:2203.11171) | 9/10 | Kontext: Self-Consistency; nuanciert durch L7 |
| L7 | arxiv:2407.05778 — Consistency ≠ Truth | 6/10 | Kontext: Konsistenz korreliert nur bedingt mit Korrektheit |
| L8 | arxiv:2404.05090 — Model Collapse (ICML'24) | 8/10 | Kontext: rekursives Training auf synthetischen Daten verengt Verteilung |
| L9 | arxiv:2605.06635 — Cited but Not Verified | 7/10 | Kontext: Inline-Zitationen häufig fehlerhaft/irrelevant — direkter Bezug zu Agoras Evidence-Gating |
| L10 | arxiv:2503.13657 — MAST-Data (Why Do MAS Fail?) | 7/10 | Kontext: MAS-Fehler-Klassifikation, Benchmark-Gewinne oft minimal |
| L11 | arxiv:2505.11556 — HiddenBench | 6/10 | Kontext: Kollektivreasoning versagt am Hidden-Profile-Problem (30,1% vs 80,7%) |
| L12 | arxiv:2509.13397 — Analytic Flexibility | 7/10 | Kontext: 252 Konfigurationen — Ergebnis hängt stark an Prompt/Sampling/Modell (P-Hacking-Äquivalent) |
| L13 | arxiv:2504.08260 — UAS Digital Twins | 6/10 | Kontext: unvollständige Replikation realer Survey-Daten, persistenter Bias |
| L14 | Horton 2023 — Homo Silicus (arxiv:2301.07543) | 8/10 | Kontext: LLMs als wirtschaftliche Agenten, qualitative Replikation |

## Stats

- **Gesamt-Quellen:** 57 Code-Belege (C1–C57) + 5 ADRs (A1–A5) + 12 Issues (I1–I12) + 4 Referenzläufe (R1–R4) + 14 Literatur-Quellen (L1–L14, von 22 in Task-F) = **92 eindeutige Quellen**.
- **Official-Anteil (Code+ADRs+Referenzläufe):** 66/92 ≈ **72 %** — weit über 30 %-Schwelle (Standard). Begründet durch Code-Audit-Charakter.
- **Academic-Anteil:** 14/92 ≈ 15 % — Kontext, nicht Code-Verifikation.
- **Community (Issues):** 12/92 ≈ 13 % — alle mit Code verifiziert.
- **Single-Source-Max:** kein einzelner Code-Beleg trägt >25 % der Aussagen; jede Kernaussage ruht auf ≥2 Belegen (Cross-Validierung im Code).
- **Unique Domains:** github.com (Issues), arxiv.org/PMC (Literatur), lokales Repo (Code/ADRs/Referenzläufe) — 3 Domänen, aber Code-Audit-Charakter macht die Domain-Schwelle hier nicht anwendbar (die „Domains“ sind Dateipfade im Repo).
- **Nachzug Simulations-Verifikation:** C45–C57 (13 Belege) aus drei Mini-Workern (B1 Personas/Quoten, B2 OASIS-Actions/Echo-Index, B3 Interview-Binding); korrigierten drei Befunde (Interview-Fix in HEAD, DACH-Quoten kalibriert, Nicht-Determinismus code-belegt).

## Dropped Sources

Keine Quellen verworfen. Hinweis: README.md und docs/architecture.md wurden als **nicht-verifizierbare sekundäre Beschreibungen** behandelt — Aussagen daraus fließen nur dann in den Bericht ein, wenn sie am Code bestätigt wurden. Das VISION.md wurde als nicht-bindender North-Star nicht als Beleg verwendet.

## Vertrauenswürdigkeits-Hinweis

Code-Belege (`C<n>`) sind zum Prüfungszeitpunkt verifizierte Zeilennummern am Branch-Stand `7e42ae34`. Bei zukünftigen Refactors können Zeilennummern driften — die referenzierten Symbole (Funktions-/Klassennamen) bleiben jedoch stabil. ADRs (`A<n>`) sind datiert und Status-behaftet; ihre Aussagen sind zum jeweiligen Datum gültig. Referenzläufe (`R<n>`) sind eingefrorene Output-Artefakte — ihr Befund ist ein Snapshot, kein live-Verhalten.