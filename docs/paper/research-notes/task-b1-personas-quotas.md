# Task B1 — Personas, Stakeholder-Gruppen, Quoten, DACH-Targeting, persona_id-Identität

Untersuchungs-Slice: Persona-Generierung und -Identität (nicht die gesamte Simulation).
Repo-HEAD: `7e42ae34` (Branch `feat/1152-document-chunk-provenance`).
Datum: 2026-08-09.

## Sources

Source-Type: official (Agora-Backend-Code und -Tests am genannten HEAD).

| # | Referenz | Inhalt |
|---|---|---|
| S1 | [oasis_profile_generator.py:361-403](backend/app/services/oasis_profile_generator.py) | `OasisProfileGenerator.__init__` — Provider-Binding, Destatis-Quota-Default |
| S2 | [oasis_profile_generator.py:405-488](backend/app/services/oasis_profile_generator.py) | `generate_profile_from_entity` — Persona-Bau aus Entity, user_id von außen |
| S3 | [oasis_profile_generator.py:490-498](backend/app/services/oasis_profile_generator.py) | `_generate_username` — handle + random 3-stelliger Suffix |
| S4 | [oasis_profile_generator.py:52-76](backend/app/services/oasis_profile_generator.py) | `PersonaProfileSchema` — striktes Pydantic-Schema für LLM-JSON |
| S5 | [oasis_profile_generator.py:668-783](backend/app/services/oasis_profile_generator.py) | `_generate_profile_with_llm` — chat_json, Temperature, Retries |
| S6 | [oasis_profile_generator.py:119-165](backend/app/services/oasis_profile_generator.py) | `OasisAgentProfile`-Dataclass — Felder inkl. `source_entity_uuid`, `segment`, `generation_source` |
| S7 | [persona_quota_defaults.py:1-111](backend/app/services/persona_quota_defaults.py) | `default_dach_industry_quota` — Destatis WZ 2008 Branchen-Quota, IT-Cap ≤12 % |
| S8 | [persona_quota_defaults.py:114-181](backend/app/services/persona_quota_defaults.py) | `build_industry_quota_prompt_block` (DE/EN) — Prompt-Injektion der Soll-Verteilung |
| S9 | [persona_demographics.py:1-80](backend/app/services/persona_demographics.py) | `DACH_NAME_ORIGIN_QUOTAS` — Destatis Mikrozensus 2024, BFS, Statistik Austria |
| S10 | [simulation_config_generator.py:1072-1085](backend/app/services/simulation_config_generator.py) | `_validate_persona_quota` — Simulation-Floor ≥30 Personas |
| S11 | [simulation_config_generator.py:1087-1099](backend/app/services/simulation_config_generator.py) | `_ensure_skeptic_quota` — ≥20 % `stance="opposing"` |
| S12 | [prepare_service.py:506-634](backend/app/services/prepare_service.py) | `_apply_persona_floor_to_quota_plan` + `_validate_persona_quota` |
| S13 | [evidence_migrations.py:491-554](backend/app/services/evidence_migrations.py) | `_map_profile_to_persona` — `persona_id = f"persona_{user_id}"`, Segment-Aggregation |
| S14 | [report_agent/agent.py:372-413](backend/app/services/report_agent/agent.py) | `stakeholder_group`-Zuweisung bei Interview-Evidence |
| S15 | [report_contract.py:170-238](backend/app/contracts/report_contract.py) | `persona_stakeholder_group`-Pflichtfeld für `agent_quote` |
| S16 | [confidence_calculator.py:336-355](backend/app/services/confidence_calculator.py) | Cross-Stakeholder-Count aus `persona_stakeholder_group` |
| S17 | [report_prompts/sections.py:116-208](backend/app/services/report_prompts/sections.py) | `<simulated_quote persona_id="..." seed_anchor="...">`-Format |
| S18 | [test_persona_name_distribution.py:62-106](backend/tests/eval/test_persona_name_distribution.py) | DACH-Namens-Quoten- und Migrationsanteil-Tests |
| S19 | [test_persona_target.py:1-113](backend/tests/test_persona_target.py) | `compute_persona_target` — Nenner-Logik (Issue #1034) |
| S20 | [test_persona_industry_distribution.py:57-60](backend/tests/services/test_persona_industry_distribution.py) | `default_dach_industry_quota`-Pydantic-Validität |
| S21 | [test_report_agent_quote_anchors.py:101-186](backend/tests/services/test_report_agent_quote_anchors.py) | `persona_id`-Validierung in Quotes (fehlend/unbekannt) |
| S22 | [test_persona_entity_context_api.py:1-60](backend/tests/api/test_persona_entity_context_api.py) | Entity-Context-API, `source_entity_uuid`-Pfad vs. Legacy-Fallback |
| S23 | [persona_quality_service.py:1-90](backend/app/services/persona_quality_service.py) | Detektoren: `missing_entity_link`, `role_diversity`, `mbti_diversity` |

## Findings

### 1. persona_id entsteht deterministisch aus user_id, nicht als UUID
`user_id` ist ein int, der von außen an `generate_profile_from_entity` übergeben wird ([S2:407]). In der Massengenerierung ist das der Laufindex (`start_idx + i`). Für ReportV3 wird `persona_id = f"persona_{user_id}"` gebildet, mit Fallback `source_entity_uuid` oder `p{index:03d}` ([S13:493-494]). Im Report-Prompt erscheint das Format `persona_03` ([S17:192]). `user_name` hingegen ist nicht-deterministisch: handle + `random.randint(100,999)` ([S3:496-498]).

### 2. Stabiler Provenance-Anker ist source_entity_uuid, nicht persona_id
`OasisAgentProfile` speichert `source_entity_uuid = entity.uuid` und `source_entity_type` ([S6:146-147], [S2:480]). `_map_profile_to_persona` trägt `entity:<uuid>` in `evidence_refs` ein ([S13:513-515]). `test_persona_entity_context_api` verifiziert den Graph-Pfad für Profile mit `source_entity_uuid` und einen `source='fallback'`-Pfad für Legacy-Profile ohne ihn ([S22:1-60]). `PersonaQualityService.missing_entity_link` markiert auto-generierte Personas ohne Entity-Link als Warnung ([S23:30-32]).

### 3. persona_id geht in Quotes nicht verloren — Quote-Anchor-Validator prüft hart
`validate_quote_anchors` akzeptiert ein `<simulated_quote>` nur, wenn `persona_id` in der übergebenen `persona_ids`-Liste steht und `seed_anchor` in der EvidenceMap (oder mit `seed_doc:`-Prefix) aufgelöst wird ([S21:101-186]). Fehlt `persona_id` → `invalid_quotes`, `valid=False`; unbekannte `persona_id` → ebenfalls invalid ([S21:173-186]). Der Workflow prüft `persona_ids_for_validation` aus dem Agent-Kontext ([report_agent/workflow.py:1071-1082]).

### 4. stakeholder_group wird NICHT bei der Persona-Generierung zugewiesen
`OasisAgentProfile` hat kein `stakeholder_group`-Feld ([S6:119-165]). Das Profil trägt nur `segment = entity_type` (z. B. "Person", "Organization") als Quota-Plan-Dimension ([S2:462], [S6:149-150]). `persona_stakeholder_group` entsteht erst bei der Interview- bzw. agent_quote-Evidence-Erzeugung: `stakeholder_group = interview.agent_role or interview.agent_name or "unbekannt"` ([S14:388-392]). Die Stakeholder-Gruppe ist also eine Rollenbezeichnung des Interview-Agenten, keine persistente Persona-Eigenschaft.

### 5. stakeholder_group ist vertraglich Pflicht für agent_quote
`EvidenceItemModel.agent_quote_needs_stakeholder_group` wirft, wenn `source_kind == agent_quote` und `persona_stakeholder_group` fehlt ([S15:188-194], [S15:235-238]). `confidence_calculator` liest das Feld und zählt distinct Gruppen für die Cross-Stakeholder-Regel (`stakeholder_group_count`, [S16:336-355]). `cross_stakeholder_for_high` verlangt zwei verschiedene Gruppen für Confidence "high".

### 6. DACH-Branchen-Quota ist gegen Destatis WZ 2008 + BA + Statista kalibriert
`default_dach_industry_quota` verteilt `total_personas` nach WZ-2008-Buchstaben-Anteilen (Verarbeitendes Gewerbe 17 %, Handel 14 %, Gesundheit 13 %, IT 12 % hard-gecappt, …) per Largest-Remainder-Verfahren mit Clamp-Logik für kleine Pools ([S7:24-111]). Quelldokumentation im Modul-Docstring: Destatis WZ 2008, BA-Beschäftigtenstatistik Stand 2023, Statista 2022 ([S7:1-9]). Werte sind explizite Konstanten, nicht dynamisch bezogen.

### 7. DACH-Namens-/Migrations-Quota ist gegen Destatis Mikrozensus 2024 kalibriert
`DACH_NAME_ORIGIN_QUOTAS` definiert 7+ Buckets (german_native 74 %, turkish 4 %, arabic_levant 3 %, polish_eastern 4 %, ex_yu_balkan 3 %, russian_ukrainian 3 %, italian …) mit Beispiel-Namenlisten ([S9:30-80+]). Quelle: Destatis Mikrozensus 2024, BFS Schweiz, Statistik Austria, aggregiert; Werte bewusst als Konstanten, "damit Tests deterministisch bleiben" ([S9:3-6]).

### 8. Validierung gegen Populationsdaten ist Konstanten-Vergleich, kein Mikrodaten-Fit
`test_migration_share_in_quotas` prüft, dass der Migrationsanteil 24–28 % beträgt ([S18:63-68]). `test_persona_name_distribution_matches_dach_demographics` (LLM-markiert, in CI per `-m "not llm"` ausgeschlossen) prüft die reale Verteilung nach Generierung gegen 20–32 % Migrationsanteil ([S18:76-106]). `test_persona_industry_distribution` prüft Pydantic-Validität von `default_dach_industry_quota` ([S20:57-60]). Es gibt keinen Test, der generierte Profile gegen echte Volkszählungsmikrodaten oder eine Destatis-Tabelle mit Einzelzeilen fittet.

### 9. LLM-Call via chat_json-SSoT, Temperatur sinkt pro Retry, Budget-gebunden
`_generate_profile_with_llm` nutzt `LLMClient.chat_json` (nicht den rohen OpenAI-Client), `schema=PersonaProfileSchema`, `schema_name="persona_profile"`, `context="persona"`, `force_no_thinking=True` ([S5:725-733]). `temperature = 0.7 - (attempt * 0.1)` (0.7 → 0.6 → 0.5), 3 Versuche mit linearem Backoff ([S5:721-768]). `run_id` bindet jeden Call an den Budget-Enforcer des Prepare-Runs (#984, [S5:712-715]). Nach drei Fehlschlägen Fallback auf `_generate_profile_rule_based` mit gesetztem `generation_error` (Issue #1029, [S5:770-783]). `PersonaProfileSchema` erzwingt Pflichtfelder `display_name`, `handle`, `age` (18–75), `gender`, `mbti`, `country` (ISO), `voice_register` ([S4:66-76]).

### 10. Quota-Plan steuert LLM-Prompt aktiv, nicht nur Post-Hoc-Validierung
`build_industry_quota_prompt_block` (DE/EN) injiziert die Soll-Branchenverteilung als "### Branchenverteilung (Destatis WZ 2008)" in den Persona-Prompt und weist das LLM an, Beruf und Branche passend zu wählen — IT-Berufe nur für ~12 % ([S8:114-181]). `OasisProfileGenerator` lädt per Default `default_dach_industry_quota(100)`, falls kein Plan übergeben wird ([S1:401-403]). `_validate_persona_quota` in `prepare_service` prüft nach der Generierung, dass der Plan erfüllt ist ([S12:613-634]). Simulation-Floor ≥30 Personas, per `AGORA_ALLOW_SMALL_SIM=1` übersteuerbar ([S10:1073-1085]). Skeptiker-Quota ≥20 % `stance="opposing"` wird synthetisch aufgefüllt ([S11:1087-1099]).

## Provenance-Klassifizierung

- **persona_id stabil?** Ja, deterministisch aus `user_id` (int) gebildet als `persona_<user_id>` ([S13:494]). Stabilität hängt an der Persistenz der `user_id` im Run; ein Re-Run mit neuem `start_idx` erzeugt neue IDs. Der stabile Anker *über* Runs hinweg ist `source_entity_uuid` ([S2:480], [S6:146]), nicht `persona_id`. `user_name` ist nicht-deterministisch (Random-Suffix, [S3]).
- **stakeholder_group nachvollziehbar?** Nur bedingt. Die Gruppe wird nicht aus Seed/Graph oder Persona-Profil abgeleitet, sondern ad hoc aus `interview.agent_role`/`agent_name` bei der Interview-Evidence gebildet ([S14:388-392]). Keine stabile Stakeholder-Identität pro Persona; gleiche Persona kann in verschiedenen Interviews unterschiedliche Gruppen tragen. Für `agent_quote` vertraglich erzwungen ([S15:188-194]), aber der Wert ist eine Rollenbezeichnung, kein kodierter Stakeholder aus einer Taxonomie.
- **DACH-Targeting belegt?** Ja, mehrfach und gegen offizielle Statistiken kalibriert: Branchenverteilung gegen Destatis WZ 2008 / BA / Statista ([S7]), Namens-/Migrationsverteilung gegen Destatis Mikrozensus 2024 / BFS / Statistik Austria ([S9]). Kalibrierung erfolgt als explizite Konstanten (kein Live-Datenbezug); Tests vergleichen Summen und Anteile gegen Schwellen ([S18:62-106]), nicht gegen Mikrodaten. IT-Bias-Korrektur ist ein aktives Designziel (hard-cap 12 %, Prompt-Steuerung, [S8]).

## Gaps

- **`backend/app/contracts/persona_contract.py`** — im Task-Prompt vermutet, existiert nicht unter diesem Namen. Persona-Verträge sind `PersonaQuotaPlan` und `PersonaTargetContract` (importiert in [S19:21] aus `app.contracts`) sowie `PersonaProfileSchema` direkt im Generator ([S4]); kein dediziertes `persona_contract.py`-Modul.
- **`backend/tests/eval/test_persona_target.py`** — existiert unter `backend/tests/test_persona_target.py` (nicht unter `tests/eval/`). Inhaltlich prüft er `compute_persona_target` (Nenner-Logik Issue #1034), nicht demografische Target-Verteilung.
- **Validierung gegen echte Mikrodaten** — kein Test fittet generierte Profile gegen rohe Volkszählungs- oder Destatis-Einzelzeilen; alle Prüfungen nutzen die hartkodierten Konstanten aus `persona_demographics.py`/`persona_quota_defaults.py` als Ground Truth. Die "Ground Truth" ist also die im Code codierte Annahme, nicht ein externer Datensatz.
- **Stakeholder-Taxonomie** — keine kodierte Stakeholder-Gruppen-Taxonomie gefunden; `stakeholder_group` ist freie Rollenbezeichnung aus dem Interview-Agenten. Segment (entity_type) ist die einzige stabile Gruppierung auf Persona-Ebene.
- **persona_id-Determinismus über Re-Runs** — nicht gefunden: kein Test, der sicherstellt, dass dieselbe Entität bei Re-Generierung dieselbe `persona_id` erhält. `source_entity_uuid` ist stabil, `user_id`/`persona_id` nicht.
- **`persona_review_service.py`, `persona_eligibility.py`, `persona_library.py`** — per `ls` gefunden ([S23-Umfeld]), im Slice nicht tief analysiert; für Vollständigkeit einer Persona-Provenance-Aussage wären sie ergänzend zu prüfen.