# Agora — Onboarding für Claude Code

## Was ist Agora?

Lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen.
Stack: **Flask + Pydantic v2 + Vue 3 + Neo4j + Ollama + OASIS** (CAMEL-AI Subprozess).
Status: **v1.0.0 (2026-05-11)** · alle 14 PR-Slices der v1.0-Output-Vertrag-Roadmap aus [`PLAN.md`](PLAN.md) durch · Layer 0–10 grün · Test-Counts: [`docu/STATUS.md`](docu/STATUS.md) · [Release Notes](docu/2026-05-11-v1.0.0-release-notes.md).

**Graph-Stand:** Knowledge-Graph (code-review-graph) zuletzt aktualisiert 2026-05-15. 701 Files, 6657 Nodes, 56089 Edges, 6394 Embeddings über Python/TypeScript/Vue/JavaScript/Bash. Bei jedem Slice-Merge oder Worktree-Subagent-Run gilt: `code-review-graph update` ausführen, bevor Briefings erstellt werden.

## Sofort wichtig

- **Tool-Reihenfolge ist Pflicht** (Details § Tool-Pflicht): `code-review-graph::get_minimal_context_tool` → `context7::resolve-library-id`+`query-docs` → `sequential-thinking` → `context-mode` → **erst dann** `Read`/`rg`/`Bash`. Überspringen kostet Tokens und produziert Halluzinationen. Skip → eine Zeile im Worklog warum.
- **Branch-Hygiene:** Nie auf `main` direkt pushen. Branch-Namen: `feat/task-XX-kurztitel`. Riskante Backend-Änderungen: Label `needs-python314` setzen. Linear-FF-Merge auf main, keine Rewrites publizierter Commits.
- **Tests sind die Spec.** Pflichttests vor Refactor lesen. TDD: erst RED, dann GREEN, dann Commit.
- **Pakete unter Linux:** `nala` statt `apt`. Python-Deps via `uv`.
- **Layer-Reihenfolge ist verbindlich** (siehe unten).
- **Keine US-Cloud-Lock-ins.** Ollama-kompatibel als Fallback bleibt Pflicht.

## PR-Workflow (Pflicht)

Nach jedem `gh pr create`:

```bash
sleep 90
gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
```

**Gemini-Code-Assist** reviewed automatisch innerhalb ~60–120 s. Findings
sind nach `priority` markiert (HIGH / MEDIUM / LOW). Workflow:

1. **HIGH:** immer adressieren, bevor mergen — entweder direkt im
   gleichen Branch nachpatchen oder als Followup-Sub-Slice
   (`fix(scope): Gemini-Followup auf <PR#>`).
2. **MEDIUM:** je nach Scope. i18n-Misses, Exception-Specifity,
   stable-keys → meistens fixen. Style-Geschmack → explizit ablehnen
   im Arbeitsprotokoll, nicht stillschweigend ignorieren.
3. **LOW:** kann oft als „Out of Scope" gemerged werden, mit Verweis im
   Arbeitsprotokoll.

Erst nach Findings-Sichtung mergen — `git checkout main && git merge --ff-only <branch> && git push origin main`.

## Stack-Map

```
backend/                    Python 3.11, uv, Flask, Pydantic v2, pytest
  app/
    contracts/              Layer 0: Single Source of Truth (Pydantic v2)
    api/                    HTTP-Routen (Flask Blueprints)
    services/               Business-Logik
      report_agent/         Package-Split (Sub-Slice M11.13, #202): agent.py, manager.py, planning.py, evidence.py, prompts.py, schemas.py, sections.py, storage.py, tools.py, workflow.py — Layer-0-Boundary in agent.py + planning.py
      sim/                  M11 Phase 5 Hotspot-Refactor (2026-05-08, 5 PRs): run_state_store, action_log_reader, monitor, interview_client, process_manager extrahiert. `simulation_runner.py` orchestriert nur noch.
      graph/                M11 Phase 5b Hotspot-Refactor (2026-05-08, 3 PRs): graph_dtos, graph_reader, insight_forge_tool extrahiert. `graph_tools.py` orchestriert.
      evidence_binder.py    Sub-Slice 07: Contradiction-Penalty, kein dekoratives Fallback
      confidence_calculator.py  Sub-Slice 08: Match-Score-Cap + Verified-Quellen-Gate
      oasis_profile_generator.py  voice_register-Pflichtfeld (Sub-Slice 10)
      prepare_service.py    Sub-Slice 20a/b/22: PersonaQuotaPlan-Pipeline komplett
      simulation_runner.py  Sub-Slice 21: OASIS_DB_PATH pro Sim
    models/                 Dataclasses (werden migriert)
    storage/                Neo4j-Adapter
    utils/llm_client.py     Sub-Slice 05: chat_json strict-Schema-Mode
    observability/          Observability Slice 1 (geplant 2026-05-15): init_tracing() + Redis-Trace-Propagator
  tests/
    contracts/              Pflicht für jeden Vertrag
    api/                    Schema-Tests, jsonschema-basiert
    services/
    eval/                   Sub-Slice 17: Baseline-Eval-Suite + Snapshots
    observability/          Observability Slice 1 (geplant): Tracing-Init, Subprocess-Propagation, Redis-Propagator
  scripts/                  OASIS-Subprozess + run_*_simulation.py
    subprocess_redis_bridge.py  Issue #17 Phase D: Redis-IPC-Bridge im OASIS-Eventloop
    _sim_common.py          CAMEL-Context-Floor + init_runner_tracing (Slice 1c geplant)
frontend/                   Vue 3 + TS + Pinia + Vitest + Zod
  src/
    contracts/              Zod-Spiegel zu backend/app/contracts/
      personaQuotaContract.ts  Sub-Slice 20c/24
      reportContract.ts        Sub-Slice 02b
    components/
      Step2EnvSetup.vue     Quoten-Editor (Sub-Slice 20c/24)
      Step4Report.vue       Sub-Slice 15: strict-Zod-Parse + Schema-Banner
    composables/useEventStream.ts  SSE-Consumer (Issue #9 Phase C), 10/10 TS
    api/stream.ts           EventSource-Factory mit signed-tickets (P0.2c)
    observability/          Observability Slice 1 (geplant): WebTracerProvider + SigNoz-Deep-Link
schemas/                    auto-generiert via app.contracts.dump_schemas
deploy/observability/       Observability Slice 1 (geplant): OTel-Collector-Config
docker-compose.observability.yml  Observability Slice 1 (geplant): SigNoz CE + OTel-Collector, Profile `observability`
docu/                       Architektur, Logs, Plans, Arbeitsprotokolle
prompts/                    UI-Prompt-Vorlagen
```

## Architektur-Layer (Status)

Änderungen nur **layer-aufwärts**. Layer 1 ohne Layer 0 ist verboten.

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts + Zod-Spiegel + JSON-Schema-Dump | grün (Sub-Slice 02a–c) |
| 1 | Backend-Hardening (Quoten, Evidence-Dedup, Confidence) | grün (06–08, 20a/b/22, 32) |
| 2 | DACH-Voice + Prompt-Semantik (`future prediction` weg) | grün (09, 11, Wording-Glossar v1) |
| 3 | Reader-Honesty (Quotes, Time-Series, Section-Dedup) | grün (12–14) |
| 4 | Frontend (Zod-strikt, Diff/Confidence-UI, Quoten) | grün (15, 16a/b, 20c/24) |
| 5 | Eval/Baseline (Fixtures, Snapshot-Tests) + v1→v2-Migration | grün (17, 25) |
| 6 | Frontend-TypeScript-Migration (API, Composables, Pinia) | grün (26, 27, 28 — #71/#72/#73) |
| 7 | Graph / Runs / Compare | teilweise — done: 29 (#65), 33 (#62), 35 (#64). Offen: 22 #74 (Graph-Diff), 24 #66 (Compare-API), 25 #67 (Compare-UI), 27 #63 (RunsDashboard) |
| 8 | Persona Review + UX | teilweise — done: 30 (#141 Sticky-Scroll). Offen: 29 #69 (Persona-Diff), 30 #70 (Approve/Reject/Regenerate), 32 #137 (Graph-Build-Batch-Marker) |
| 9 | Production Deployment | grün — M11 Phase 1–4 Hardening (Release-Gating, Static-Analysis-Gates, Multi-Stage `prod`-Image ohne Node/npm/curl + `read_only: true`, Supply Chain) abgeschlossen 2026-05-07. Reverse-Proxy ✅, gevent ✅, Bundle-Token-Gate ✅, `?token=`-Block in Prod ✅, signed-tickets-Frontend ✅, Prod-Stack-Smoke auf `main`/Tags/`workflow_dispatch` ✅ (`docker-image.yml::prod-proxy-smoke`). PR-Trigger seit 2026-05-06 wegen ~30 min Laufzeit pausiert und vor Release neu zu bewerten. |
| 10 | Security Watchlist (CVE-Tracking, pip-audit) | grün — CVE-Monitor wöchentlich (`.github/workflows/cve-monitor.yml`, `pip-audit --strict` ohne `--ignore-vuln`), Hardstop 2026-07-30 verdrahtet (Workflow failt ab dann), Risk-Register mit Eskalationspfad (`docu/dependency-risk-register.md`). Issues #121–#126 bleiben open bis Upstream patcht. Zusätzlich CVE-Tracker #296/#297/#298 seit 2026-05-07 unter Beobachtung. Phase 4 Supply Chain (`dependency-review.yml`, `codeql.yml`, GHCR Build-Provenance-Attestation, SPDX-JSON-SBOM-Artefakt) zusätzlich aktiv. |

## Aktive Hot-Spots / offene Hauspflicht

Layer-0–6 + 9–10 sind durch. **v1.0-Output-Vertrag-Pfad** (PLAN.md): Phase 1 + P2.1/P2.2/P3.1/P3.3/P3.4/P4.2 stehen, **offen sind P3.2-Verdrahtung, P4.1 (Report-Modi), P4.3 (ZIP-Bundle), P4.4 (E2E-Smokes)**. P2.3 läuft separat im Worktree `feat/m11-7c-report-hypotheses`. Daneben aktuelle M11-Baustellen:

- **Coverage-Gate-Anhebung** (M11.2/M11.3): Aktuelle Schwellen Backend 53 % / Frontend 24 %. Ziel Backend 70 % / Frontend 60 % schrittweise. Coverage-Reports als Artifacts `backend-coverage` / `frontend-coverage` (14 Tage Retention) in `ci.yml`.
- **Phase 6 Contract-Generation + Status-Sync:** Contract-Dump reproduzierbar machen, Frontend-Zod-Spiegel automatisiert gegen Pydantic prüfen, `scripts/sync-status.sh` als CI-Pflichtschritt.
- **Phase 7 / M11.4 Playwright-Smokes:** Drei stabile E2E-Smokes — Health/Login, Upload+Graph, Minimalreport. Keine 90-Test-Pyramide.
- **M11.5 Komplexitäts-Gate:** `radon` Backend, ESLint/size-limit Frontend.
- **M11.6 API-Envelope:** Error-/Success-Envelopes vollständig durchziehen.
- **Frontend-Hotspots (Issue #203):** `Step2EnvSetup.vue` 667 LOC (war 1804, -63 %), `Step4Report.vue` 797 LOC (war 1287, -38 %) — bereits durch Phase-5/5b-analoge Schnitte reduziert, unter Schwelle. Issue #203 zum Schließen vorbereiten (separater Slice).
- **gevent ↔ OASIS-Subprozess Smoke:** `subprocess.Popen` läuft bei aktivem `gevent.monkey.patch_all()` standardmäßig durch den Patch — bei jedem Slice, der den OASIS-Pfad anfasst, per `scripts/verify-deploy.sh` smoken.
- **Init-Logs doppelt:** Folge-Slice braucht Fork-Safety-Verifikation der Neo4j/Redis-Pools vor `--preload`-Aktivierung.
- **Dependabot-Aufräumen:** Offene PRs #323 (`mistune` 3.1.4 → 3.2.1), #326 (`pygments` 2.19.2 → 2.20.0). PR #315 (`camel-ai`) bleibt blockiert durch `camel-oasis==0.2.5` hard pin.
- **Live-Settings #212 (P2):** Erst nach M11-Stabilisierung.
- **Observability Slice 1 (geplant 2026-05-15):** End-to-End-Tracing der Sim-Pipeline mit SigNoz CE + OpenTelemetry. Vier seltene Hops: gevent↔OTel, `subprocess.Popen`-Boundary, Redis-pub/sub-Propagator, SSE-Frame-Korrelation. Plan: [`docu/plans/2026-05-15-observability-slice-1.md`](docu/plans/2026-05-15-observability-slice-1.md). Geschätzter Aufwand ~8–10 Tage in 6 atomic Sub-Slices (1a–1f). Default `OTEL_ENABLED=false` — kein Overhead solange ungenutzt.

## Kommandos (immer diese)

```bash
# Backend
cd backend && uv sync --group dev
cd backend && uv run pytest -x -q
cd backend && uv run pytest tests/contracts/ -v          # Contract-Tests
cd backend && uv run python -m app.contracts.dump_schemas # Schemas regenerieren
cd backend && uv run ruff check . && uv run mypy app

# Frontend
cd frontend && npm ci
cd frontend && npm run check        # lint + test + build (alles)
cd frontend && npm test -- --run    # nur tests
cd frontend && npm run lint
cd frontend && npm run build

# Container (Prod-Stack lokal)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker exec agora curl -fsS http://localhost:5001/health

# CI lokal simulieren
git diff --exit-code schemas/    # nach dump_schemas darf nichts driften
```

## Tool-Pflicht (nicht verhandelbar)

Die häufigste Quelle für Rework und Token-Verschwendung in diesem Repo ist: **Claude greift direkt zu `rg`/`Read` statt zu Knowledge-Graph oder Live-Docs**. Das produziert
veraltete Annahmen, halluzinierte Symbole, doppelte Recherche und unnötig große Kontextfenster.

**Diese Sektion überschreibt das Default-Verhalten. Sie ist nicht verhandelbar.** Skip-Begründungen gehören ins Worklog — nicht in den Chat.

### TL;DR-Entscheidungsbaum

```
Frage über…             →   Pflicht-Tool (zuerst)            →   Fallback
─────────────────────────────────────────────────────────────────────────
Symbol/Funktion/Klasse  →   code-review-graph                →   rg (nur wenn Graph leer)
Caller/Callee/Tests     →   code-review-graph::query_graph   →   —
Blast-Radius/Impact     →   code-review-graph::impact_radius →   manuelles Import-Tracing
Library/SDK/Framework   →   context7                         →   Training-Wissen (verboten)
Multi-File / ambig      →   sequential-thinking (3–5)        →   direkter Edit (verboten)
Große Tool-/Log-Outputs →   context-mode (ctx_execute_*)     →   Bash + Read (verboten)
Eigene Vorgeschichte    →   honcho-memory / episodic-memory  →   git log
Skill in System-Reminder →  Skill-Tool invoken               →   Eigenimplementierung
Deferred MCP-Tool       →   ToolSearch select:<name>         →   „Tool fehlt" behaupten (verboten)
Bash/yml/Markdown/Schemas → Read / rg / Bash                 →   —
```

### Pre-Flight-Checkliste (bevor du erste Bash/Read absetzt)

Für jede Task — auch „nur eine kurze Frage" — laufe diese Reihenfolge **strikt**:

1. **Skill-Liste scannen.** Die System-Reminder listet alle Skills auf. Falls einer matcht: zuerst invoken. „Quick question" zählt nicht als Ausnahme.
2. **Deferred-Tool-Liste scannen.** Wenn ein potenziell passendes MCP-Tool nur als Name in der System-Reminder steht (keine Schema-Daten), lade es via `ToolSearch query:"select:<name>"` **bevor** du behauptest, eine Fähigkeit fehle.
3. **`mcp__code-review-graph__get_minimal_context_tool`** mit `task: "<one-liner>"` aufrufen. Pflicht für Token-Sparen: liefert Risk-Score + relevante Communities + Tool-Empfehlungen in ~100 Tokens statt ganze Files in den Kontext zu ziehen. **Auch wenn du glaubst, du kennst den Pfad.**
4. **`mcp__claude_ai_Context7__resolve-library-id` + `query-docs`** wenn die Task eine Library/Framework/SDK/CLI berührt (Vue 3, Pydantic v2, Flask, Neo4j-Driver, OASIS/CAMEL, Ollama, Vite, pytest, uv, gh, docker, …). Training-Cutoff ist Anfang 2026 — Repo lebt auf neueren Versionen.
5. **`mcp__MCP_DOCKER__sequentialthinking`** wenn die Task ambig ist, Multi-File-Scope hat, oder eine Pipeline-Grenze überschreitet (graph ↔ env ↔ simulation ↔ report). Mindestens 3 Thoughts, gerne mit Revisions. Output: konkretes Akzeptanzkriterium.
6. **`context-mode`** für große Tool-Ausgaben, Doku-/Wissensinhalte, Log-/JSON-Analyse und kompakte On-Demand-Suche nutzen (`ctx_index`, `ctx_search`, `ctx_execute_file`, `ctx_batch_execute`), statt Rohdaten in den Chat zu ziehen. Bash mit erwartetem Output >20 Zeilen → automatisch `ctx_batch_execute`/`ctx_execute`.
7. **honcho-memory / episodic-memory** prüfen, bevor du den User nach Setup/Präferenzen/Projekt-Historie fragst.
8. **Dann erst** `Read`/`rg`/`Bash`.

Wenn du einen Schritt überspringst, schreibe **eine Zeile** ins Arbeitsprotokoll warum (z. B. „get_minimal_context war out-of-date, deshalb direkter Read"). Diese Zeile fehlt → der nächste Run wiederholt den Fehler.

### code-review-graph — Pflicht-First-Stop

Der Graph ist Tree-sitter-basiert und persistent. Strukturkontext (Caller/Callee/Tests/Imports/Communities) ist da, **ohne** dass du Files öffnest.

| Frage | Graph-Tool | Statt |
|---|---|---|
| Pre-Flight für jede Task | `get_minimal_context_tool` | Annahme |
| Code-Review eines Diff | `detect_changes_tool` + `get_review_context_tool` | komplette Files via `Read` |
| Blast-Radius einer Änderung | `get_impact_radius_tool` | manuelles Import-Tracing |
| Welche Flows sind betroffen? | `get_affected_flows_tool` | `rg` durch alle Service-Files |
| Wer ruft `<symbol>` auf? | `query_graph_tool` `pattern=callers_of` | `rg "<symbol>"` |
| Caller/Callee/Tests für `<symbol>` | `query_graph_tool` `pattern=callees_of` / `tests_for` | `rg` |
| Funktion/Klasse finden | `semantic_search_nodes_tool` | `rg "def <name>"` |
| Architektur-Überblick | `get_architecture_overview_tool` + `list_communities_tool` | mehrere `Read` über `__init__.py` |
| Refactor-Hot-Spots | `find_large_functions_tool` + `get_hub_nodes_tool` | manuelle `git grep` |
| Refactor-Planung (Renames, Dead-Code) | `refactor_tool` | manuelle Cross-Repo-Suche |
| Token-effizientes Context-Snippet | `get_minimal_context_tool` | `Read` ganzer Files |

**Update-Rhythmus.** Der Graph hat einen Auto-Update-Hook bei File-Writes, aber er kann nach längeren Sessions oder externen Tools (Subagenten in Worktrees!) driften. Drei Trigger für manuelles Refresh:

```bash
code-review-graph update    # CLI im Repo-Root
```

- Nach **jedem Slice-Merge** (mehrere Files in einem Schritt geändert).
- Wenn `query_graph_tool` Knoten zurückliefert, die du gerade gelöscht/umbenannt hast.
- Vor einem großen Refactor-Briefing an einen Subagent, damit dessen Empfehlungen nicht auf altem Graph basieren.

**Fallback** auf `rg`/`grep`/`Read` nur für: Bash-Skripte, GitHub-Workflow-yml, Markdown, Config-Files, generierte Schemas. Bei Vue/TS/Python-Code immer **erst** Graph.

### context-mode — Kontext-Sandbox & Retrieval

`context-mode` ist Pflicht, sobald ein Tool- oder Datei-Read voraussichtlich große Rohdaten in den Kontext laden würde.

- **Doku/Wissen indexieren:** `ctx_index` für große Markdown-/Doku-/Tool-Ausgaben; danach `ctx_search` für gezielte Abrufe.
- **Dateien analysieren:** `ctx_execute_file` nutzen, wenn du aus Logs, JSON, CSV, Markdown oder großen Source-Dateien nur kompakte Fakten brauchst.
- **Mehrere Checks bündeln:** `ctx_batch_execute` für mehrere unabhängige Read-/Status-Kommandos plus Suchfragen; keine langen Rohoutputs in den Chat ziehen.
- **Nicht ersetzen:** `context-mode` ersetzt nicht den `code-review-graph` für Strukturkontext und nicht `context7` für Live-Docs; es schützt den Kontext und macht Retrieval gezielt.

### context7 — Live-Docs vor Code

Für jede Task die eine externe Lib berührt:

1. `mcp__claude_ai_Context7__resolve-library-id` mit `libraryName: "vue 3"` (oder Pinia, Vite, Neo4j, …).
2. `mcp__claude_ai_Context7__query-docs` mit dem gefundenen `libraryID` + spezifischer Frage.

Beispiele wann zwingend:
- Vue-3-Komposition-API-Pattern (`<script setup>` Reactivity-Edge-Cases, Suspense, Teleport)
- Pydantic-v2-Validator-Signaturen (haben sich gegen v1 geändert)
- Neo4j-Driver async/sync, Bookmark-Management
- OASIS / CAMEL Memory-Limits, Tool-Use-Payloads
- Vite-Plugin-API, manualChunks-Strategy
- pytest-Fixtures + parametrize-Edge-Cases
- uv-Lock-File-Konflikte

**Niemals** auf Training-Wissen verlassen wenn Context7 verfügbar ist. Training-Cutoff ist Anfang 2026; Repo lebt auf Library-Versionen, die danach erschienen sind.

### sequential-thinking — für Multi-Step-Probleme

`mcp__MCP_DOCKER__sequentialthinking` ist Pflicht bei:

- Multi-File-Refactors (z. B. Vue-Komponenten aufteilen + Tests + Pinia-Store anpassen).
- Pipeline-Grenzen-Debug (graph → env → simulation → report).
- Flask ↔ OASIS-Subprozess-Probleme (gevent, Redis-Pub-Sub, Ticket-Auth).
- Token-Budget-Limits in CAMEL-Memory.
- Unklare Spec-Pfade ohne Tests.

Mindestens 3 Thoughts, gerne mit Revisions (`revises_thought_number`). Output: konkretes Akzeptanzkriterium für den nächsten Subagent-Brief.

### honcho-memory & episodic-memory

- **honcho-memory** — bei jeder Frage über den User selbst (Setup, Hardware, Präferenzen, Projekt-Historie über mehrere Sessions hinweg).
- **episodic-memory:remembering-conversations** — bei „wie hatten wir das damals gelöst", „der bekannte Bug X", wiederkehrenden Workflows. **Vor** Codeexploration aufrufen, nicht danach.

### GitHub / `gh`

- Vor PR-Merge: `sleep 90` und Gemini-Findings ziehen (siehe PR-Workflow oben).
- Third-Party-Bug-Hunt: zuerst `gh search issues --repo <upstream>` gegen Upstream spiegeln, dann Workaround.
- Niemals `gh pr merge --auto` ohne Findings-Sichtung.

### Anti-Pattern (sofort stoppen, wenn du dich dabei ertappst)

| Gedanke | Realität |
|---|---|
| „Ich weiß die Antwort, brauche kein Graph" | Graph ist 50× schneller und korrekter als dein Memory |
| „Ein schneller `rg` reicht" | `rg` findet Strings, Graph findet Symbole + Beziehungen |
| „Library kenne ich auswendig" | Training-Cutoff ist veraltet, Context7 fragen |
| „Sequential-thinking ist Overkill für so eine kleine Aufgabe" | Wenn du das denkst, ist es selten klein |
| „Der Subagent klärt das schon" | Subagent läuft auf deinem Briefing — Brief = Risiko |
| „Tool ist gerade ConnectING" | `ToolSearch` ruft die Tools im Connecting-State auf und wartet |
| „Das Tool steht nicht im Tool-Header" | Deferred Tools sind unsichtbar bis `ToolSearch` — erst prüfen, dann behaupten |
| „Ich mache nur eine Klarstellungsfrage" | Klärung = Aufgabe. Skill- und Tool-Check kommt **vor** der Frage |
| „Ich kann den Pfad raten" | Raten → Halluzination. `semantic_search_nodes_tool` braucht ~50 Tokens |
| „Das war im letzten Run schon mal so" | Sessions starten ohne Memory. `episodic-memory` oder `git log` ziehen |

Defaults, keine Eskalation. Wenn du eins davon überspringst, **eine Zeile** im Worklog notieren — damit der nächste Run den Fehler nicht wiederholt.

### Enforcement-Protokoll

Im Pre-PR-Self-Review oder Code-Review eines Subagent-Branches gilt:

- Worklog enthält **kein** Sign-off von Graph-Query / Context7-Lookup / Sequential-Thoughts trotz Multi-File-Scope → Slice ist **nicht** review-ready, nochmal durch.
- Subagent-Briefing zitiert Symbole/Pfade ohne Graph-Beleg → Brief ist unvollständig, Worker wird Halluzinationen produzieren.
- Library-Pattern im Diff ohne Context7-Beleg im Worklog → Senior-Review-Pflicht, nicht direkt mergen.

## Verifikations-Disziplin

Bevor du Variablen umbenennst oder Pfade anlegst, **immer erst** `rg`-prüfen:

```bash
rg -n "<symbol>" backend/
find . -path "*<pattern>*"
```

ChatGPT/Claude-LLM-Vorschläge sind oft präzise, aber Variablen-Namen
sind manchmal halluziniert. Verifiziere **immer**.

## Worktree-Strategie (Pflicht für Slice-Arbeit)

Trait des Users: **Isolation-driven**. Jeder Slice läuft in einem eigenen
Worktree unter `/private/tmp/agora-<slice-id>/`, nicht im Haupt-Workspace.

```bash
git worktree add -b feat/<scope-slice-id> /private/tmp/agora-<slice-id> origin/main
ln -sfn /Volumes/T7/Projekte/agora/frontend/node_modules /private/tmp/agora-<slice-id>/frontend/node_modules
```

### Strategie für Multi-Slice-Epics

Wenn ein Epic aus mehreren Slices besteht (A → B → C → … → Z):

1. **Slice A** baut auf `origin/main`.
2. **Slice B/C/D parallel** bauen auf Slice A (gleicher Base-Branch). Disjunkte
   Verzeichnis-Scopes Pflicht, sonst Merge-Konflikte.
3. **Integration-Branch** `feat/<epic>-epic` mergt alle Slices lokal mit `--no-ff`.
4. **Lokale Gates** pro Slice und auf Integration: `typecheck && test && build && lint`.
5. **GitHub-CI** erst am Schluss mit **einem** PR (`feat/<epic>-epic` → main).
   Nicht jeden Slice einzeln pushen — das verbraucht CI-Minuten ohne Mehrwert
   und lässt halbfertige PRs offen liegen.

Diese Regel überschreibt den Default-PR-Workflow für Mehrwert-Slices. Einzelne
Bugfixes/Followups dürfen weiterhin sofort als PR rausgehen.

## Subagent-Briefing (Lead → Worker)

Wenn du Subagents spawnst, **brief sie so dass sie ohne Rückfrage durchziehen können**.
Pflicht im Briefing:

1. **Kontext** in 3–5 Zeilen: Welche Slice, welche Phase, welche Vor-Slices laufen.
2. **Worktree-Setup** (exakte Pfade + Symlink-Befehl).
3. **Disjunkter Verzeichnis-Scope** (z. B. `frontend/src/components/v4/shell/`).
4. **Konkrete Datei-Liste** mit LOC-Erwartung.
5. **Tokens/Constants** (welche v4-Tokens, welche Pinia-Stores, welche i18n-Keys).
6. **Tests-Pflicht** (mindestens N Smokes) mit Stil-Verweis auf existierende Specs.
7. **Doku-Pflicht** (`docu/YYYY-MM-DD-<slice>-worklog.md` Schema).
8. **Lokale Gates** (typecheck/test/build/lint) als Abnahmekriterium.
9. **Push-Verbot** wenn Teil eines Epics: explizit „KEIN push, KEIN gh pr create".
10. **Rückmeldungs-Format** (Branch + letzter Commit-Hash + Test-Delta + Bundle-Delta + Gaps).

Worker-Briefings sind keine Tickets, sondern Verträge. Wenn ein Slice
mehrfach aufgerufen werden muss, dann war das Brief unvollständig.

### Subagent-Verification-Gate

Nach jedem Subagent-Run **Pflicht**:

```bash
# Im Slice-Worktree:
cd /private/tmp/agora-<slice-id>/frontend
npm run typecheck && npm test -- --run && npm run build && npm run lint

# Backend, falls Python-Slice:
cd backend && uv run pytest -x -q && uv run ruff check . && uv run mypy app
```

Falls rot: NICHT mergen, sondern Worker mit präzisem Fix-Brief erneut anstoßen.
`/verify-after-subagent` Slash-Command führt das Gate ggf. automatisiert aus.

## Subagent-Routing (Max-Plan)

Optimierungsziel ist **Rework-Vermeidung plus gezieltes Token-Sparen**.
`code-review-graph` ist Pflicht, damit kleinere Modelle und Subagents mit
präzisem Strukturkontext arbeiten können; bei Layer-0-Drift oder
Wording-Glossar-Verstößen hat trotzdem Senior-Review Vorrang vor blindem
Sparen.

Ziel-Mix: ~35 % Opus, ~55 % Sonnet, ~10 % Haiku.

| Aufgabe | Modell | Subagent | Anteil-Ziel |
|---|---|---|---|
| Architektur-Entscheidung, Cross-Layer-Refactor, ambige Specs | Opus | (Lead, kein Subagent) | ~25 % |
| Code-Review kritischer Pfade (contracts, evidence_binder, report_agent) | Opus | `feature-dev:code-reviewer` | ~10 % |
| Refactor 2+ Dateien, Pydantic-Migration | Sonnet | `agora-refactor-worker` | ~25 % |
| Pydantic-Tests, FSM-Übergänge, Persona-Quoten | Sonnet | `agora-test-worker` | ~15 % |
| Vue/Pinia/Zod-Spiegel | Sonnet | `agora-frontend-worker` | ~10 % |
| Read-only Audit (Evidence, Wording-Glossar) | Sonnet | `agora-evidence-auditor` | ~5 % |
| Dokumentation, CHANGELOG, Arbeitsprotokolle | Haiku | `agora-doc-worker` | ~10 % |

### Opus-Trigger (überstimmen das Default-Routing)

Auch wenn ein Sonnet-Subagent für die Aufgabe definiert ist — bei diesen
Signalen direkt Opus ziehen:

- Layer-0 (Pydantic-Contracts) wird angefasst
- Mehrere Layer gleichzeitig betroffen
- Wording-/Prompt-Semantik (Layer 2, Glossar v1)
- Spec ist ambig oder Tests fehlen noch
- Pre-PR-Self-Review **vor** `gh pr create` (fängt Drift bevor Gemini sie sieht)

## Slash-Commands (im Repo, Cloud-portabel)

`.claude/commands/`:

- `/agora-next-task` — Master-Orchestrator: pickt nächsten offenen
  Sub-Slice aus PLAN.md, dispatched passenden Subagent, verifiziert,
  committet, pusht.
- `/verify-after-subagent` — Pflicht-Verifikation nach jedem
  Subagent-Run (sequential gate).
- `/fix-task-01..04-*` — Templates aus dem Layer-0–4-Refactor
  (inhaltlich abgearbeitet; können archiviert werden).

## Aktive Epics

- **Design Language v4 — App-Shell-Port** (2026-05-11 → laufend).
  Spec: [`docu/2026-05-11-design-v4-app-shell-epic.md`](docu/2026-05-11-design-v4-app-shell-epic.md).
  Quellen vendoriert unter [`design/v3-source/`](design/v3-source/). Integration-Branch
  `feat/design-v4-epic`. Strategie: lokale Slices A–J, **EIN PR am Ende**.
  Stand: Slices A (Tokens), B (Shell), C (Forms), D (Data), E (LlmRouting-Pilot)
  durch; F (Settings + Views in AppShell) läuft. Visual-Akzeptanz gegen
  `design.png` ~93 % nach Slice E.

  Wichtigste Mechanik:
  - Neue v4-Komponenten in `frontend/src/components/v4/{shell,forms,data}/`
    (disjunkter Namespace zu legacy `components/ui/`).
  - `frontend/src/assets/styles/tokens-v3.css` ist die portierte v4-Tokens-Datei
    (Apple-System-Tokens + Compat-Layer für v1/v2-Aliase).
  - Backend nicht angefasst.

- **v1.0-Output-Vertrag** (PLAN.md) — offen: P3.2-Verdrahtung, P4.1, P4.3, P4.4.
  Status-Tabelle in [`docu/STATUS.md`](docu/STATUS.md).

- **Observability Slice 1 — End-to-End-Tracing** (2026-05-15 geplant, Plan abgenommen, Implementation offen).
  Plan: [`docu/plans/2026-05-15-observability-slice-1.md`](docu/plans/2026-05-15-observability-slice-1.md).
  Treiber: Lerneffekt + Story (System-Integration-Career, Q3 2026) + lokal-first Observability für AI-Stack. **Kein** Performance-/Wartbarkeits-Schmerz.
  Stack: SigNoz Community Edition (Apache 2.0, self-hosted) + OpenTelemetry-Collector + Tempo-Style-Traces über ClickHouse.
  Branch: `feat/observability-slice-1`. Strategie: lokale Slices 1a–1f, ein gemeinsamer PR am Ende des End-to-End-Pfads (analog Design-v4-Epic).

  Wichtigste Mechanik:
  - Trace-Context propagiert via W3C-`traceparent` durch vier Hops: gevent-monkey-patched Flask, `subprocess.Popen`-Env-Var, Redis-pub/sub-Payload-Feld (`_otel_traceparent`), SSE-Frame-`trace_id`.
  - Frontend rendert SigNoz-Deep-Link aus aktueller `trace_id` im SimDetail-Panel.
  - Backend nutzt drei Service-Namen: `agora-frontend`, `agora-backend`, `agora-oasis-runner`.
  - Default-Off: ohne `OTEL_ENABLED=true` startet Agora unverändert (keine Layer-9-Hardening-Re-Validation in Slice 1).

## Verboten

- Dataclasses für API-Verträge → Pydantic v2 (`extra="forbid"`)
- Inline-JSON-Schemas → immer aus Pydantic ableiten via `model_json_schema()`
- `apt` (nutze `nala`)
- US-Marketing-Phrasen in Reports („revolutionary", „seamless", „prediction of the future")
- Wording-Glossar v1 verletzen (siehe [`docu/glossary-wording.md`](docu/glossary-wording.md), Issue #175): `prediction`, `rehearsal`, `god's eye view`, `high-fidelity digital world`, `public opinion prediction`, `Agentic-Prediction-Engine` → durch Glossar-Equivalente ersetzen
- `print()` in Prod-Code → strukturiertes Logging via `app.logger`
- Schema-Strings inline kopieren → über Re-Export aus `app.contracts`
- `git push --no-verify` ohne explizite User-Freigabe
- Auf `main` mergen ohne Gemini-Findings-Sichtung (siehe PR-Workflow oben)
- Hartkodierte UI-Strings in `Step*.vue` — immer `vue-i18n` (`t(...)`) + Keys in `de.json`+`en.json`
- **Neue OASIS/CAMEL-Runner-Skripte ohne `apply_camel_context_floor()` + `enforce_memory_token_limit()`-Aufruf nach `generate_*_agent_graph(...)`.** Sonst kappt CAMELs `ScoreBasedContextCreator` jeden Agent-Memory bei 8192 Tokens — unabhängig vom realen Modell-Context. Floor wird zentral in `backend/scripts/_sim_common.py::apply_camel_context_floor()` gepflegt; Pro-Modell-Heuristik in `backend/scripts/agent_tools.py::_heuristic_context_limit()`. User-Override via `LLM_CONTEXT_LIMIT` und `LLM_MODEL_CONTEXT_LIMITS_JSON` (Vorrang vor Heuristik)
- Hartkodierte `token_limit`-Defaults in CAMEL-/OASIS-Anbindungen (8192, 4096, 16384) — immer aus `_resolve_memory_token_limit(model_name)` lesen, damit Frontend-gewählte Cloud-Modelle (Gemini 3 ≈ 1 M, Qwen3-Coder 256 k, GPT-OSS 128 k) ihren echten Context-Window nutzen können
- **Evidence-Gating-Pflicht-Anker (ADR-0002) entfernen oder schwächen.** Fünf Anker sind hart verankert in [`docu/decisions/0002-evidence-gating.md`](docu/decisions/0002-evidence-gating.md): (1) `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts.py`, (2) Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`, (3) Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`, (4) Validator `cross_stakeholder_for_high`, (5) Validator `reject_inferred_in_high_confidence`. Schwächungen wie „cross_stakeholder von 2 auf 1 Gruppe absenken", „Hedge-Liste verkürzen", „inferred aus Enum entfernen" oder „priority=hard durch soft-hint ersetzen" verlangen einen Supersedes-ADR (`0002-supersedes.md`) mit User-Sign-off, kein stilles Refactor.
