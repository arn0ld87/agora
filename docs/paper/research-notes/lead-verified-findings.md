# Lead — selbst verifizierte Findings (ergänzend zu Subagent-Notes)

## L1 — Echo-Chamber-Index & apply_echo_cap (Anti-Self-Confirmation, code-verifiziert)
- `network_analytics.py:13`: echo-chamber index = share of interactions staying within a single community (intra-cluster / total). 1.0 = everyone only talks to own tribe; 0.0 = fully integrated. Berechnet aus OASIS-Actions (FOLLOW/LIKE_POST/REPOST/CREATE_COMMENT/...) via Louvain community detection + Betweenness centrality.
- `confidence_calculator.py:363 apply_echo_cap`: wenn `echo_index > 0.75` UND `is_cross_stakeholder=True` → Score gedeckelt auf max 0.84, Label `high`/`verified` → `medium`. Schwellen hartkodiert (`_ECHO_CAP_THRESHOLD`, `_ECHO_CAP_MAX_SCORE=0.84`).
- `report_agent/workflow.py:142 _get_echo_index`: liest echo_chamber_index live aus Simulations-Metriken.
- `test_red_team_review.py::test_findings_not_empty_when_high_echo_index`: Red-Team-Review erzeugt Findings bei hohem Echo-Index.
- `report_agent/workflow.py:165 _RED_TEAM_SYSTEM_PROMPT`: Wording-Glossar v1 — VERBOTEN „Vorhersage/Prognose/wird eintreten“; ERLAUBT „Simulation/Szenarienanalyse/Reaktionsmuster/Einschätzung“.

**Bewertung:** Konkreter, code-level Anti-Self-Confirmation-Mechanismus, den ein Single-Prompt nicht besitzt. Caveats: (a) Echo-Cap greift NUR bei `is_cross_stakeholder`; nicht-cross-stakeholder-Claims unberührt. (b) Cap downgraded nur Confidence, entfernt Claim nicht. (c) echo_index misst synthetische Homogenität, keine reale Populationsvalidität. (d) Schwellen hartkodiert, nicht kalibriert/evaluiert.

## L2 — ADR-0011 Referenzlauf (echte Selbstkritik im Repo)
- ADR-0011 nennt realen Lauf `report_d9023bd1f55a` (sim_7058c126da03, 30 Agents, 315 Interaktionen, 5 Cluster, Echo-Chamber-Index 0.4317, Modus balanced), der „formal valide, inhaltlich aber nicht vertrauenswürdig“ war. Sieben code-belegte Ursachen (Thought-Leak, Seed-Zahl-Fehlzuordnung, Similarity=Beleg, Default seed_corpus, Claim-Floor, Metadata-Verlust, status=COMPLETED trotz fehlgeschlagenen Sections). → Agora dokumentiert eigene Fehler学史 offen. Das ist ein starkes Signal für Engineering-Honesty, if auch für Evidence-Defizite.

## L3 — Wording-Glossar / Anti-Prediction
- Red-Team-Prompt verbietet prädiktive Sprache. AGENTS.md/CLAUDE.md verbietet „future prediction“/„god's eye view“ in report_prompts. → Agora positioniert sich bewusst als Szenarienanalyse, nicht als Vorhersage._STMT

## L4 — Teil-B-Provenance fehlt (code-verifiziert, siehe task-d)
- graph_build.py:439 nutzt `TextProcessor.split_text` (Blob), nicht `split_text_into_chunks_with_documents`. document_id/chunk_id nicht im Graph-Layer. seed_doc: opak (evidence.py:352). → End-to-End-Source-Provenance aktuell NICHT vorhanden; ADR-0013 nur Teil A umgesetzt.