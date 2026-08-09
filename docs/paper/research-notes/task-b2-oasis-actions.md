# Task B2 — OASIS Social Actions, Netzwerk-Metriken, Sim-Determinismus

Slice-Untersuchung im Agora-Repo (`feat/1152-document-chunk-provenance`, HEAD `7e42ae34`).
Fokus: OASIS Social Actions, `echo_chamber_index`, Simulation-Runner-Determinismus,
`sim_action_log` → `agent_action`-Evidence. Nicht die ganze Simulation — nur dieser Slice.

## Sources

- `backend/app/services/simulation_runner.py:1-526` — Source-Type: official. Thin Delegator-Orchestrator (M11 Phase 5: Logik extrahiert nach `app.services.sim.*`).
- `backend/app/services/simulation_manager.py:1-425` — Source-Type: official. SimulationState/FSM, create/prepare/list, keine Runtime-Logik.
- `backend/app/services/network_analytics.py:1-463` — Source-Type: official. `NetworkAnalyticsService.compute_metrics`, Louvain + Betweenness, echo_chamber_index.
- `backend/app/contracts/sim_action_log_contract.py:1-100` — Source-Type: official. `RoundEndEvent`-Vertrag (Writer/Reader), `simulated_minutes`/`simulated_hours`.
- `backend/app/services/sim/action_log_reader.py:115-139` — Source-Type: official. Leser des `round_end`-Events, propagation in `SimulationRunState`.
- `backend/app/services/sim/run_state_store.py:104-239` — Source-Type: official. `SimulationRunState` mit `simulated_hours`/`twitter_simulated_hours`/`reddit_simulated_hours`.
- `backend/app/services/report_agent/agent.py:219-299` — Source-Type: official. `_collect_simulation_evidence_items` (sim-Aktionen → `agent_action`-Evidence).
- `backend/app/services/event_bus.py:40-599` — Source-Type: official. Channels: CONTROL, STATE, RPC_COMMAND, ACTION (reserved/Phase B), POST_CREATED.
- `backend/scripts/run_parallel_simulation.py:1423-1953` — Source-Type: official. OASIS-Subprocess: `random.*` ohne Seed, `log_round_end(simulated_minutes=...)`.
- `backend/scripts/action_logger.py:78-278` — Source-Type: official. Writer-Seite des `round_end`-Events.

## Findings

1. **`SimulationRunner` enthält keinen Seed/Random-Code** — `grep -nE 'seed|random|deterministic|uuid' simulation_runner.py` liefert keinen Treffer. Die Klasse ist seit M11 Phase 5 ein reiner Delegator (PRs 1–5), gesamte Logik in `app.services.sim.*` (`simulation_runner.py:86-105`).

2. **OASIS-Subprocess ist NICHT deterministisch** — `run_parallel_simulation.py` nutzt `random.uniform` (L1423), `random.random` (L1434), `random.sample` (L1437) zur Agenten-Auswahl, ohne jeglichen `random.seed(...)`-Aufruf (grep über `run_parallel*.py`, `run_twitter*.py`, `run_reddit*.py` liefert keine `seed(`-Aufrufe). Gleiche Config → unterschiedliche Action-Streams.

3. **`echo_chamber_index = intra / total`** — `network_analytics.py:426-432`. Über gewichtete Interaktionen (`weight` = Interaktionscount) auf Louvain-Communities (L389-405, `seed=42` für reproduzierbare Cluster-IDs). 1.0 = komplett isoliert, 0.0 = voll integriert.

4. **Aktionen, die in den Interaktionsgraphen fließen** — `network_analytics.py:38-48` `_DIRECTED_ACTIONS = {FOLLOW, LIKE_POST, DISLIKE_POST, REPOST, CREATE_COMMENT, LIKE_COMMENT, DISLIKE_COMMENT, MUTE, QUOTE_POST}`. `CREATE_POST` u.a. Broadcasts werden ignoriert (nicht paarweise). Target-Agent-Auflösung über 3 Tiers (Legacy-IDs → Comment-ID-Index → Name-Lookup, L197-252).

5. **Social-Action-Logging via JSONL `sim_action_log`** — Writer `scripts/action_logger.py:90-101` (`log_round_end(round_num, actions_count, simulated_minutes=0)`) schreibt `RoundEndEvent` (Contract `sim_action_log_contract.py:45-100`); Reader `action_log_reader.py:119-139` parst es und propagiert `simulated_hours` in `SimulationRunState` (`run_state_store.py:114, 120-121, 170-177, 233-239`).

6. **`agent_action`-Evidence `producer_key`** — `report_agent/agent.py:285-295`. Format: `"simulation-action:" + ":".join((platform, round_num, agent_id, action_type, timestamp))`. Entspricht der User-Hypothese `<platform:round:agent:action:ts>`. Metric-Evidence separat: `"simulation-metric:<field>"` (L270) bzw. `"simulation-metric:status"` (L251) bei nicht-`ok`-Snapshot.

7. **Keine Sim-Validity-/Ground-Truth-Metrik** — `grep -rnE 'ground_truth|ground truth|destatis|census|sim_validity|validation_metric' backend/app/` liefert keinen Treffer (nur `validate_simulation_id`/`validate_path_id` als Path-Validatoren). Kein Abgleich der simulierten Demographie/Meinung gegen Census/Statista/DESTATIS.

8. **`simulated_hours` erreicht die API-Oberfläche NICHT (Issue #1018 bestätigt)** — Writer schreibt `simulated_minutes` (seit B-28/Slice 6), Reader propagiert `simulated_hours` in `run_state.json` (`run_state_store.py:170-177`). Aber `grep -nE 'simulated_hours|simulated_minutes' backend/app/api/simulation_run.py` und `frontend/src/` liefern keine Treffer. Status-Endpoint exponiert den Wert nicht; Frontend liest ihn nicht.

9. **Cluster/Communities werden NICHT persistiert** — `NetworkAnalyticsService` ist zustandslos (`network_analytics.py:17-20` Docstring "stateless"): `compute_metrics` gibt ein `PolarizationMetrics`-DTO zurück, kein Neo4j-/Disk-Schreib. `snapshot_id` (`metrics_<sha1[:12]>`, L327-328) und `calculated_at` (UTC ISO, L325-326) werden deterministisch berechnet, aber nur ins DTO gehängt. Bridge-Agents und Cluster-Labels (`_derive_cluster_label` L78-127, TF-Top-3) sind transient.

10. **Event-Bus hat keinen aktiven Action-Channel** — `event_bus.py:43` `CHANNEL_ACTION = "action"` ist "reserved for Phase B (live action events)". Aktive Channels: CONTROL (L40), STATE (L41, für `run_state.json`-Updates), RPC_COMMAND (L42), POST_CREATED (L44, Slice 5-pre). Live-Action-Events fließen nicht über den Bus, sondern werden über das JSONL-Action-Log gelesen (`action_log_reader.read_action_log_chunk`).

## Determinismus & Reproduzierbarkeit

**Nein.** Die OASIS-Simulation ist nicht deterministisch. Beleg:
- `run_parallel_simulation.py:1423` `target_count = int(random.uniform(base_min, base_max) * multiplier)`
- `run_parallel_simulation.py:1434` `if random.random() < activity_level:`
- `run_parallel_simulation.py:1437` `selected_ids = random.sample(...)`
- Kein `random.seed(...)` im Subprocess oder in `process_manager.py`/`simulation_runner.py`.

Einzige Determinismus-Insel: `NetworkAnalyticsService._analyse` (`network_analytics.py:405`) ruft `louvain_communities(graph, weight="weight", seed=42)` auf — die Metrikberechnung ist bei identischem Action-Input reproduzierbar, aber der Input selbst (die Actions) ist es nicht. Cluster-Labels sind deterministisch (TF-Top-3, sortiert nach `(-count, alpha)`, L125).

## echo_chamber_index Mechanik

**Formel:** `echo_chamber_index = intra / total`  (`network_analytics.py:426-432`)

```
intra = #Interaktionen (src, tgt) mit agent_to_cluster[src] == agent_to_cluster[tgt]
total = #alle paarweisen Interaktionen
```

**Pipeline** (`compute_metrics`, L305-355):
1. Action-Liste (optional sliding window `window_size_rounds`, L313-320).
2. `_iter_interactions` (L359-382): Filter auf `_DIRECTED_ACTIONS`, Target-Agent-Auflösung über Lookup-Indizes (`_build_lookup_indexes` L255-294), Self-Loops verworfen.
3. `_analyse` (L384-451): Undirected weighted `nx.Graph` (weight = count).
4. `louvain_communities(graph, weight="weight", seed=42)` (L405), sortiert nach `len` desc → `agent_to_cluster`-Map.
5. Echo = intra/total über ursprüngliche (gerichtete) Interaktionen.
6. Bridge-Agents: `nx.betweenness_centrality` (L436, weight, normalized) → Top-k mit mind. einem Nachbarn in anderem Cluster (L437-449).

**Einfließende Actions:** `FOLLOW, LIKE_POST, DISLIKE_POST, REPOST, CREATE_COMMENT, LIKE_COMMENT, DISLIKE_COMMENT, MUTE, QUOTE_POST` (L38-48). `CREATE_POST`/Broadcasts ausgeschlossen.

**Schwelle:** Keine harte Schwelle. `echo_chamber_index ∈ [0.0, 1.0]`; `_get_echo_index` (`report_agent/workflow.py:142-162`) reicht den Rohwert an den Report-Workflow. Hoher Wert triggert Red-Team-Findings (`test_red_team_review.py:39` `test_findings_not_empty_when_high_echo_index`).

**Status-Sentinel:** Bei nur Broadcasts (keine paarweisen Interaktionen) → `status="no_pairwise_interactions"` (L153, `METRICS_STATUS_NO_PAIRWISE`); bei gar keinen Actions → `status="no_actions"` (L152). Report-Agent emittiert dann ein `graph_metric_status`-Item statt Pseudo-Nullen (`agent.py:240-251`).

## Gaps

- **G1 — Determinismus fehlt.** Kein `random.seed` im OASIS-Subprocess. Für Paper-Reproduzierbarkeit müsste ein Seed in `run_parallel_simulation.py` (und twitter/reddit-Varianten) injiziert und durchgereicht werden. Aktuell sind zwei Läufe mit identischer Config nicht bit-identisch.
- **G2 — Keine Ground-Truth-Validierung.** Kein Abgleich der simulierten Verteilungen (Alter/Geschlecht/Meinung) gegen Census/DESTATIS/Statista. Sim-Validity-Metrik existiert nicht. Für ein Paper wäre eine "sim vs. ground truth"-Validierung ein methodischer Leerstellen.
- **G3 — `simulated_hours` nicht in API/Frontend (Issue #1018).** Wert steht in `run_state.json` (`run_state_store.py:170`), wird aber vom Status-Endpoint nicht exponiert und vom Frontend nicht gelesen. Reporter/Reviewer können die Sim-Dauer nicht ohne Raw-JSON-Inspektion sehen.
- **G4 — Cluster nicht persistiert.** Louvain-Communities, Bridge-Agents und Cluster-Labels werden bei jedem `compute_metrics`-Aufruf neu berechnet; nicht in Neo4j oder als Sibling-JSON abgelegt. Vergleiche über Zeitpunkte/Branches erfordern Re-Berechnung aus dem Action-Log.
- **G5 — `producer_key` für sim-Actions nur 5-stellig.** `simulation-action:<platform>:<round>:<agent>:<action>:<ts>` (`agent.py:293`). Duplikat-Handling (gleicher Agent, gleiche Action, gleiche Sekunde) ist dem `register_evidence_record` überlassen — bei fehlender `timestamp` fällt das Item ohne `producer_key` still heraus (`agent.py:292`).
- **G6 — Live-Action-Channel reserviert, ungenutzt.** `CHANNEL_ACTION` (`event_bus.py:43`) ist "reserved for Phase B", nicht aktiv. Live-Action-Events werden über JSONL-Datei-Read (`action_log_reader`) gepollt, nicht über den Bus gestreamt.
- **G7 — Target-Agent-Auflösung best-effort.** `_extract_target_agent` (`network_analytics.py:197-252`) bricht bei Namens-Kollisionen (non-unique `agent_name`) deterministisch nach "first observation" (L262) — OASIS-Default ist unique, aber nicht erzwungen. Nicht auflösbare Actions fließen nicht in den Graphen.