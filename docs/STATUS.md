# Agora — Status

**Stand:** 26.09.2026

**Geprüfte Main-Baseline:** `cde0919f6`

**Produktversion:** `0.9.6` (getaggt, Stability Beta)

Diese Datei ist die **Single Source of Truth für den verifizierten Istzustand**. Strategische Release-Ziele stehen in [`ROADMAP.md`](../ROADMAP.md), konkrete Arbeitspakete und Akzeptanzkriterien in [GitHub Issues](https://github.com/arn0ld87/agora/issues), ausgelieferte Änderungen in [`changelog.d/`](../changelog.d/README.md). Historische Audits, Pläne und Referenzläufe behalten ihren damaligen Stand und sind keine aktuelle Steuerungsquelle.

## Kurzurteil

Agora besitzt eine vollständige Single-User-Pipeline von Dokumentaufnahme und Knowledge Graph über Persona-Erzeugung und OASIS/CAMEL-Simulation bis zu evidenzorientiertem Report, Vergleich und Export. Die Stabilisierung der 0.9.x-Linie hat insbesondere Contracts, Run-Lifecycle, Crash-/Restart-Verhalten, Budgetdurchsetzung, Installationspfade und Evidence-Persistenz deutlich gehärtet.

Die `0.9.x`-Linie ist trotzdem **keine 1.0-Freigabe**. Prepare, Report und Graph-Build besitzen inzwischen explizite Recovery/Resume-Pfade (#1472); Out-of-Process-Worker und Simulation-Resume bleiben spätere Arbeit. Die aktuellen Release-Risiken sind der P0-Restore-Fehler (#1633), offene P1-Kernpfade und Security-Triage, die Embedding-Konfigurations-SSoT, echte Manifest-/Replay-Werte sowie noch fehlende Ops- und Produktnachweise.

**`v0.9.6`-Tag (20.09.2026, über 330 Commits/184 Changelog-Fragmente seit `v0.9.5`):** ein Zwischenrelease, ausdrücklich **kein** `0.10.0` und ohne dessen Release-Gates. Zum Tag gehörten vier LLM-Provider, die noch nicht aktivierte PostgreSQL-Schicht, das zehnteilige UI-Redesign und eine Manifest-/Replay-Grundlage. Seitdem ist PostgreSQL auf armserver für fünf Metadaten-Domänen produktiv (#1592), während die Code-Defaults weiterhin Legacy nutzen. `v0.9.6` wurde nicht rückwirkend zu einem RC; nächste Schnitte und offene Nachweise stehen in [`ROADMAP.md`](../ROADMAP.md) und [`docs/agents/release-priority.md`](agents/release-priority.md).

## Versionsstatus

`VERSION` ist die Produkt-SSoT. Komponentenmanifeste werden dagegen geprüft.

<!-- BEGIN_AUTOGEN_VERSIONS -->
| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 0.9.6 |
| Frontend | `frontend/package.json` | 0.9.6 |
| Root | `package.json` | 0.9.6 |
<!-- END_AUTOGEN_VERSIONS -->

Die README-Badges müssen denselben Wert tragen. Der Versions-Cut ist in [`runbooks/release-versioning.md`](runbooks/release-versioning.md) beschrieben.

## Tests und Verifikation

Die Testzähler in diesem Markerblock werden **nur durch `scripts/sync-status.sh` erzeugt**. Sie werden nicht bei jedem PR manuell hochgerechnet, weil ein solcher Fantasiezähler zwar frisch aussieht, aber ungefähr so nützlich ist wie ein grüner Test, der nichts testet.

<!-- BEGIN_AUTOGEN_TESTS -->
| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | 5976 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Test-Files | 206 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' -o -name '*.test.ts' -o -name '*.test.js' \)` |
<!-- END_AUTOGEN_TESTS -->

**Wichtig:** Die beiden Zahlen oben sind der letzte generierte Counter-Snapshot und nicht als exakter 08.09.-Head-Count zu lesen. Für einen dedizierten Refresh: `bash scripts/sync-status.sh --no-cache` und den generierten Block committen.

Zusätzliche aktuelle Nachweise:

- PR #1461 dokumentiert einen vollständigen Backend-Lauf mit **6177 passed, 8 skipped, 1 xfailed** nach der Budget-Reservierungs-Härtung.
- PR #1480 dokumentiert danach ein grünes `pre-push-gate.sh backend`, nachdem eine durch #1475 sichtbar gewordene Testdouble-Lücke repariert wurde.
- PR #1479 dokumentiert `pytest tests/contracts` (700), die gezielten Backend-Suiten, `ruff`, `mypy`, Schema-Drift und `bun run check` mit **2163 Frontend-Tests** als grün.
- Ein geplanter `e2e-smokes`-Lauf auf `e6ced1a2` war am 08.09.2026 grün. Dieser Lauf liegt vor den anschließend gemergten PRs #1478/#1479 und den Dependabot-Merges; daraus wird **nicht** behauptet, dass bereits jeder Workflow auf `0c47737f` grün bestätigt wurde.
- Die label-gesteuerten Vollsuiten (`Backend tests + lint` / `Frontend build + lint`) griffen auf PRs bis 13.09.2026 nur für genau den Commit, auf dem das Label gesetzt wurde; jeder Folge-Push sprang auf `skipping`. Seither prüft die `if`-Bedingung den Label-Zustand des PR, nicht mehr nur das `labeled`-Event. Ein PR, der vor dem 13.09.2026 nach dem Labeln noch einmal gepusht wurde, hat die volle Suite auf seinem Endstand daher **nicht** gesehen.
- Echte Integrationstests unter `backend/tests/integration/` laufen gegen Redis und Neo4j. Der CI-Job setzt `AGORA_TEST_REQUIRE_SERVICES=1`, damit ein fehlender Dienst nicht als freundlicher Skip durchrutscht (#1481).

### Qualitäts-Gates

Drei Baseline-Gates halten Bestandsschuld sichtbar und am Wachsen gehindert. Sie reparieren nichts — sie verhindern, dass unbemerkt mehr dazukommt.

| Gate | Skript | Baseline | Gemessen am |
|---|---|---|---|
| Komplexität (radon, D+) | `backend/scripts/check_complexity.py` | `backend/radon-allowlist.txt` (47 Einträge) | laufend |
| mypy-Schuld hinter `ignore_errors` | `backend/scripts/check_mypy_debt.py` | `backend/mypy-debt-baseline.txt` — 266 Fehler in 55 Dateien | 11.09.2026 |
| Coverage (Line und Branch getrennt) | `backend/scripts/check_coverage.py` | `backend/coverage-baseline.json` — 82,8 % Line / 70,9 % Branch | 11.09.2026 |

Zum Coverage-Gate: der Istwert auf dem Messstand war **83,82 % Line** (26661/31806 Statements) und **71,94 % Branch** (6571/9134 Branches) über die vollständige Backend-Suite. Die Schwellen liegen je einen Punkt darunter — Puffer für Umgebungsunterschiede, kein Spielraum zum Absinken. Die vorherige Schwelle `--cov-fail-under=60` ohne Branch-Messung lag 24 Punkte unter dem Ist und konnte deshalb keine Regression erkennen ([#1495](https://github.com/arn0ld87/agora/issues/1495)).

Zum Typ-Gate: `pyproject.toml` schaltet mypy für `app`, `app.config`, `app.container`, `app.models.*`, `app.services.*`, `app.storage.*`, `app.utils.*` und `app.llm.*` per `ignore_errors` ab. `mypy app` ist deshalb grün, obwohl in genau diesen Bereichen die eigentliche Arbeit liegt. Die 266 Fehler sind **nicht behoben**, sondern gemessen und gedeckelt; die `ignore_errors`-Modulliste selbst darf ebenfalls nicht wachsen.

## Produktive Architektur

### Frontend

- Vue 3 / TypeScript / Vite / Pinia.
- Das Logo der Anwendung liegt unter `frontend/public/brand/`; der unreferenzierte Vorab-Exportordner `agora-logo-animation/` mit vier identischen Asset-Kopien und einer alten Vorschau ist entfernt. Die für README und Demo genutzten Assets unter `media/` bleiben erhalten.
- Die v4-Routen sind die einzige produktive Oberfläche; historische Parallel-Views sind entfernt oder Redirects.
- Pydantic-Verträge werden im Frontend durch Zod-Spiegel und eingecheckte JSON-Schemas abgesichert. **Der Spiegel ist nicht lückenlos**: das Gate `zod-mirror-drift` führt die vorhandenen Vertragstests aus, es erzwingt aber nicht, dass es zu einem Backend-Vertrag überhaupt einen Spiegel gibt. Wo einer fehlt und stattdessen ein handgeschriebenes Interface mit `[key: string]: unknown` steht, ist Drift unsichtbar — genau so zeigte das Projektregal jahrelang die rohe `project_id` statt des Namens (`useShelf` las `project_name`, das Backend liefert `name`). Projekte haben seitdem einen Spiegel (`contracts/projectContract.ts`, `.strict()`).
- Seit #1466 haben auch der Neo4j-/Disk-Teilbaum von `/api/status` (`SystemStatusNeo4j`/`SystemStatusDisk`, vorher handgeschriebene Dicts, nur Ollama/E2E waren seit #955/#1458 abgedeckt) sowie `GET /api/graph/task/<id>`/`GET /api/graph/tasks` (`TaskStatusResponse`, Spiegel von `Task.to_dict()`) einen Pydantic-Vertrag samt Zod-Spiegel (`contracts/systemStatusContract.ts`, `contracts/taskStatusContract.ts`) und Drift-Test. `_get_neo4j_status`/`_get_disk_status` serialisieren mit `exclude_unset=True`, um die zweigabhängige, bisherige Feldmenge (z. B. `is_connected`/`last_success_ts` fehlen ganz, solange kein Storage initialisiert ist) byte-genau zu erhalten. Dabei aufgedeckt: `GET /api/graph/tasks` rief bislang `t.to_dict()` auf den bereits von `TaskManager.list_tasks()` konvertierten Dicts auf — ein `AttributeError`, sobald der Endpunkt mit tatsächlich vorhandenen Tasks aufgerufen wurde; kein Test deckte diesen Pfad ab. Jetzt behoben, mit Regressionstest.
- Die Provider-Connection-Liste toleriert einen dem Frontend unbekannten `provider_kind` pro Eintrag: er wird auf `unknown` normalisiert (lokaler Transport behält die Loopback-URL-Prüfung), statt die ganze Liste zu verwerfen; andere Vertragsverstöße bleiben harte Fehler (#1414).
- Statusmeldungen von Prepare, Report, Graph-Tasks und seit #1557 auch der Run-Lifecycle (`RunDetail`, Regal/Dossier) tragen einen stabilen `message_key`; das Frontend übersetzt ihn über `resolveStatusMessage`, der Klartext bleibt Fallback. Auch der Runner-Sync aus `monitor_simulation` und die Restart-Reconciliation tragen einen Schlüssel (`run.runner_status_<status>`), sodass der Startschlüssel nicht beim ersten Poll verworfen wird.
- Die Modellwahl läuft in allen Schritten ausschließlich über `AiModelRef`/`AiModelPicker`. `useEnvForm` ist seit #903 nur noch Loader für Sprache und Runtime-Metadaten; die frühere Modellwahl-API (`modelOption`, `customModel`, `modelOptions`, `effectiveModel()`) ist entfernt.
- Seit #886 tragen auch Branch-Overrides (`POST /api/simulation/<id>/branch`) eine kanonische `ai_model_ref` (`BranchOverrides`-Contract, `backend/app/contracts/branch_request_contract.py`); der reine `llm_model`-String bleibt als deprecated Legacy-Key erhalten, die Kombination beider ist HTTP 400. Replay (`POST /api/runs/<id>/replay`) reicht seither das volle `AiModelRef` an `create_branch` durch statt nur die `model_id`.
- Das Premium-Redesign ist abgeschlossen; die Nachlese #1459 hat Radius-Tokens, Titel-Truncation, i18n und strukturierte Statusfehler bereinigt.

### Backend

- Flask Application Factory, Pydantic v2, Python 3.14, `uv`.
- Neo4j ist Knowledge-Graph-/Vektor-Persistenz; Redis dient Events, Live-Status und Teilen der IPC-/Ticket-Infrastruktur.
- Produktions-Gunicorn bleibt bewusst bei **einem Worker**. Seit [ADR-0015](decisions/0015-single-web-worker-hardstop.md) ist beziffert, was das Anheben kostet, und der bisherige Kommentar in `gunicorn.conf.py` erwies sich dabei als unvollständig. Der Zustand zerfällt in drei Klassen: verschiebbare Datenwerte ohne Ort (`_monitor_generations`, `sim/cancel_flag.py:28`, `sim/process_manager.py:101`); Fälle mit vorhandener Ablage, wo nur Cache oder Sperre fehlen (`RunRegistry`, `ApiKeysStore`, `TaskManager` — letzterer schreibt bereits über `RunRegistry().sync_task` durch); und **nicht verschiebbare** Betriebssystem-Handles (`SimulationRunner._processes`, `_action_queues`, offene Dateideskriptoren, `simulation_runner.py:102-116`). Die dritte Klasse ist durch keine geteilte Ablage lösbar, sondern nur dadurch, dass genau ein Prozess einen Lauf besitzt — also durch die persistente Job-Queue mit eigenen Workern, die [#1472](https://github.com/arn0ld87/agora/issues/1472) als Langfristlösung nennt. Das Anheben von `workers = 1` ist damit dessen Folge, keine Vorarbeit. Nicht haltbar wäre dagegen die Aussage, ein zweiter Worker brächte gar nichts: `FileParser.extract_text` läuft synchron im Request-Handler von `POST /api/graph/ontology/generate` (`api/graph_build.py:221`) und ist CPU-gebunden im Webprozess.
- OASIS/CAMEL läuft für Simulationen in separaten Subprozessen.

### LLM-Routing

Kanonische Begriffe und Pfade:

- Provider-Matrix: `backend/app/services/llm_provider_registry.py`
- Provider-Detection/Adapter: `backend/app/llm/providers/registry.py`
- Verbindung: `ProviderConnection`
- Modellreferenz/Routing: `AiModelRef`, `AiRoute`, `LlmRoute`
- strukturierte Calls: `LLMClient.chat_json`
- Modellauswahl: `AiModelPicker.vue`

Unterstützte Transportklassen sind `http`, `local` und `cli`. `codex_cli` ist ein echter CLI-/Session-Transport ohne HTTP-Base-URL und API-Key; der Fix für den früheren Persona-Route-Mix mit `.env` ist gemergt (#1418/#1422), ebenso der Codex-CLI-Transport für OASIS-Simulationsrunden (#1423/#1424). `claude_cli` (Claude-Abo statt Pay-per-Token-API) ist der zweite `cli`-Transport-Provider — anders als `codex_cli` mit `auth_mode="api_key"` (Langzeit-Token aus `claude setup-token`, kein Verzeichnis-Mount) und isoliertem `HOME` pro Subprozess-Aufruf statt einer gemounteten Login-Session.

`PUT /api/llm/active-config` übernimmt die `base_url` einer gespeicherten, aktivierten `ProviderConnection` (sonst Registry-Default) und prüft die Modell-Capabilities gegen genau diesen Endpunkt; eine `base_url` im Request-Body bleibt ignoriert, `cli`-/Session-Provider bekommen nie eine (#1289).

Die `max_completion_tokens`-/`temperature`-Heuristik (`app/llm/providers/openai.py`, gespiegelt in `scripts/_sim_common.py`) deckt die gesamte GPT-Reasoning-Major-Version `gpt-5`…`gpt-9` proaktiv sowie `o1`/`o3`/`o4` ab, statt jede neue Modellgeneration erst nach einem eigenen 400er-Incident nachzuziehen (#1572).

`frontend/src/views/Settings/LlmProvidersView.vue` rendert CLI-/Session-Provider seit #1415 nicht mehr wie HTTP-Provider: `codex_cli` (`auth_mode="session"`) zeigt weder Key- noch Base-URL-Feld, nur einen Hinweis auf die lokale `codex login`-Session; `claude_cli` (`auth_mode="api_key"`) behält das Key-Feld, verliert aber das Base-URL-Feld. `transport`/`auth_mode` liefert der `ProviderDescriptor` aus der Registry-Matrix; eine gespeicherte Connection gewinnt.

Ob ein Provider ohne eigenen Secret auskommt, entscheidet seit dem Fix für den
verworfenen `claude_cli`-Token ausschließlich `LlmProviderRegistry.uses_session_auth`
(`auth_mode == "session"`), nicht mehr der Transport. Vorher sprangen
Prepare-Route, Start-Route und die Profil-Verbindung für jeden `transport="cli"`
am Key-Guard vorbei; `claude_cli` verlor dadurch seinen aufgelösten Token, und
weil der Rückgabewert einmal in die effektive Runtime-Konfiguration des
Vorbereitungs-Jobs gegossen wird, fiel jede LLM-Phase nach dem Graph-Build aus.

Für Provider mit CLI-Transport endet die Key-Auflösung im `SecretResolver`
außerdem nach der provider-eigenen Quelle (Session, Store, `CLAUDE_CODE_OAUTH_TOKEN`)
und fällt **nicht** auf den globalen `Config.LLM_API_KEY` zurück. Der aufgelöste
Wert geht dort als Umgebungsvariable in einen Subprozess; ein Schlüssel eines
fremden Providers wäre ein Secret über Provider-Grenzen hinweg.

**Anthropic: nur Modell-Discovery, kein Chat-Transport (#1284).** Der
Registry-Eintrag (`adapter_kind="anthropic"`) bedient ausschließlich
`GET /v1/models` mit `X-Api-Key` — es gibt keinen nativen Anthropic-Chat-
Adapter, und die Base-URL (`https://api.anthropic.com`) trägt kein `/v1`-
Suffix für einen OpenAI-kompatiblen Chat-Pfad. Jede Chat-Routing-Auflösung,
die auf eine Anthropic-Connection zeigt — Legacy-Profil-Token, `AiModelRef`,
`llm_profile_id`, Legacy-`llm_provider`-Override oder eine bereits
gerouteten/wiederaufgenommene Stage — scheitert absichtlich mit einem
klaren Fehler statt still über `custom_openai` zu misrouten. Claude läuft
für Chat stattdessen über die Bedrock-Connection (#1282).

**Bedrock-Legacy-Config lädt (#1567).** Eine Server-Config mit Bedrock-
`LLM_BASE_URL` und ohne persistiertes `runtime_llm_routing.json` wird beim
Laden auf die Bedrock-Provider-ID gemappt statt mit `KeyError('bedrock')`
abzustürzen. Jeder Rückgabewert von `detect_provider(mode="http")` ist in
`_HTTP_DETECTION_TO_PROVIDER_ID` entweder gemappt oder — wie `anthropic`
(#1284) — bewusst als `ValueError` abgelehnt; ein roher `KeyError` ist nicht
mehr möglich.

### Decision Layer (Jev-Pilot): Vertrag, Port und vier Referenzadapter — umgeschaltet ist nichts

Für den Jev-Piloten (f005, ADR-0016/0017) gibt es seit dieser Slice einen eigenen, kleinen Vertrag statt eines generischen LLM-Calls: `app/contracts/decision_contract.py` modelliert `DecisionState` und drei diskriminierte Fragetypen — `ChoiceQuestion`, `ScoreQuestion`, `NoulQuestion` — sowie `DecisionResult` mit `provider="unresolved"` als eigenem Terminalzustand für eine erschöpfte Fallback-Kette. Der Port `DecisionProvider` (`app/repositories/decision_provider.py`) beantwortet genau eine Frage je Aufruf; anders als bei `LlmProfileRepository` gibt es bewusst **keine** Factory, die "den einen aktiven Provider" liefert. Der Grund ist der geplante Benchmark, nicht der heutige Code: dort muss ein Use Case Bestandspfad und Kandidat nebeneinander laufen lassen, um sie zu vergleichen. Der aktuell verdrahtete Use Case nutzt pro Aufruf genau einen Provider — die Adapter bleiben deshalb einzeln konstruierbar, statt hinter einer Auswahl zu verschwinden.

Vier Referenzadapter in `app/services/decisions/`: `RuleProvider` (deterministisch, keine LLM-Kosten), `FakeProvider` (Tests), `LLMProvider` (ruft ausschließlich `LLMClient.chat_json`, ADR-0017 — kein zweiter roher LLM-Pfad), `JevDecisionProvider` (mappt auf Jevs eigene fragen-batch-förmige API, prüft die Antwort auf Vollständigkeit je Fragen-ID und berechnet `cost_micros` über die bestehende `PricingRegistry` — ein `"jev"`-Preiseintrag in `model_pricing.json` mit USD 0,042/Mio. Input-Tokens, Output kostenlos).

`DecisionResult.cost_micros` unterscheidet drei Zustände statt sie auf eine Null zu verflachen: `0` heißt kostenfrei (Rule) oder anderswo gebucht (`LLMProvider` mit `run_id`, dessen Kosten `chat_json` selbst ins Run-Usage-Ledger schreibt), `> 0` sind bezifferte Kosten dieses Aufrufs, und `None` heißt **unbekannt** — kein Preiseintrag in der `PricingRegistry`, keine `usage`-Angabe in der Antwort, oder ein `LLMClient` ohne `run_id`, dessen Kosten nirgends gebucht werden. Damit geht eine Kostenlücke nicht als "kostenlos" durch; dieselbe Regel hält `pricing_registry.py` für ihren `unknown`-Status fest. Jev-Kosten werden gegen die **tatsächlich zurückgemeldete** Modellversion bepreist, nicht gegen den Pin — meldet Jev eine andere Version, wäre der Preis des gepinnten Modells der Preis eines anderen Modells.

**`typesafe-sdk` ist bewusst noch keine `pyproject.toml`-Abhängigkeit.** `JevDecisionProvider` nimmt wie `LLMProvider` einen bereits konstruierten Client entgegen (`client.system_one(...)`) statt selbst ein SDK zu importieren — verifizierter TypeSafe-Account-Zugang steht laut `docs/research/f005/jev-provider-evidence.md` noch aus, und ein erratener SDK-Klassenname wäre eine unbelegte Behauptung. `resolve_jev_api_key()` liest den Key bereits über den bestehenden verschlüsselten Provider-Secret-Store (Schlüssel `"jev"`); eine Fabrik, die daraus den echten SDK-Client baut, entsteht erst mit verifiziertem Zugang. Der Adapter wrappt seinen eigenen Aufruf nicht in eine zweite Retry-Schleife — TypeSafes SDK bringt laut Anbieterangabe eine eigene `RetryPolicy` mit, und die Doku warnt ausdrücklich vor verschachtelten Retry-Schleifen.

**Umgeschaltet ist nichts.** `Config.DECISION_LAYER_MODE` (`disabled`/`shadow`/`authoritative`) ist der einzige zentrale Schalter und steht im Default auf `disabled`. `decision_layer_mode(use_case_id)` nimmt die Use-Case-ID bereits entgegen, damit der spätere Umstieg auf Je-Use-Case-Granularität eine Stelle ändert statt jeden Aufrufer.

**Ein Use Case ist angebunden, ausschließlich im Shadow-Modus:** `app/services/graph/graph_reader.py::local_search` trifft nach seiner bestehenden Keyword-Sortierung genau eine zusätzliche Entscheidung über das bestbewertete Ergebnis — nicht eine je Treffer, weil `local_search` potenziell über alle Kanten/Knoten eines Graphen iteriert und ein Aufruf pro Treffer einen unbegrenzten neuen Kostenfaktor auf einem heißen Retrievalpfad wäre. Ausgewählt aus zwei in `docs/research/f005/decision-map.md` genannten Kandidaten (LocalSearch-Relevanzbewertung vs. Persona-Eligibility-Vorprüfung) — Letztere hätte tief in `oasis_profile_llm.py::_generate_profile_with_llm` eingreifen müssen, eine mehrfach für Randfälle korrigierte Funktion (#1246/#1247/#1461), und wurde deshalb als riskanter verworfen. `app/services/decisions/local_search_shadow.py` verwendet einen deterministischen `RuleProvider` (Schwellenwert auf dem bereits berechneten Keyword-Score, kostenlos, kein externer Call); das Ergebnis wird nur strukturiert geloggt (`decision_layer_shadow`-Log-Zeile), nie verwendet. `local_search` liefert bei `disabled` (Default) und in `shadow` denselben Rückgabewert; ein Fehler in der Decision Layer kann die Suche nicht beeinflussen.

**PR-#1547-Review (Codex) behoben:** Die Shadow-Telemetriezeile formatierte `cost_micros` mit `%d`; bei `None` (unbekannte Kosten) warf das einen `TypeError`, den der äußere `try/except` als Fehlschlag loggte — der erfolgreiche Aufruf erzeugte in genau den Unbekannt-Kosten-Fällen keine Telemetrie. Jetzt `%s`. Die Exception-Digests in `llm_provider.py`/`jev_provider.py` (`_bounded()`, truncated `repr()`) gaben bei kurzen Werten den vollen Inhalt preis; `_digest()` liefert jetzt ausschließlich Typ, Länge und einen irreversiblen SHA-256-Hash-Prefix — nie einen Ausschnitt des Werts selbst. `RuleOutcome` war ein `@dataclass` in `rule_provider.py`, obwohl es die exportierte Grenze zwischen aufruferdefinierten Regelfunktionen und dem Adapter ist; jetzt `pydantic.BaseModel` in `decision_contract.py` (Contracts-first). `AGORA_DECISION_LAYER_MODE=authoritative` ließ den Prozess bisher unauffällig starten, obwohl kein Use Case einen authoritativen Handler hat (`jev-choice`-Gate nicht bestanden) — `validate_decision_layer_mode()` lehnt den Wert jetzt mit erklärender Fehlermeldung ab, `DECISION_LAYER_MODES` führt ihn weiter als erkannten Zukunftswert.

## Run- und Simulations-Lifecycle

Die 0.9.5-Stabilisierung hat mehrere vorher stille Zustandsfehler geschlossen:

- Nutzer-Stop endet als `stopped` mit `termination_reason="user_stop"` statt als scheinbarer Fehler (#1474).
- Force-Restarts tragen Generation-Tokens; veraltete Monitor-Threads dürfen keine Zustände oder Ressourcen des neuen Prozesses überschreiben (#1474).
- Beim Start werden stale `pending`/`processing`/`paused` Simulation-Runs gegen die persistierte PID reconciled. Tote Prozesse werden als `failed/process_restart` markiert; `COMPLETED`/`STOPPED` werden ohne beweisbare Run-ID-Zuordnung nicht geraten (#1476).
- Gunicorn führt die Reconciliation auch in `post_fork` aus, damit Worker-Replacements unter `preload_app=True` erfasst werden (#1476).
- Starts derselben `simulation_id` sind serialisiert; ein frisches PID-loses `STARTING` erhält eine 30-s-Grace-Period (#1476).
- Compose setzt für den Agora-Service `init: true` und `stop_grace_period: 45s`.

### Bekannte Lifecycle-Grenze

Prepare-, Report- und Graph-Build-Jobs laufen weiterhin als daemonisierte Threads im Webprozess. Beendet sich der Worker regulär — etwa nach SIGTERM —, markiert ein `atexit`-Hook die Jobs dieses Prozesses noch im selben Lauf als `failed/process_restart` (Slice 1.1 aus #1472), statt auf die Startup-Reconciliation beim nächsten Start zu warten. Das Cancel-Flag wird kooperativ gesetzt.

Für **Graph-Build** ist die zweite Grenze aus Slice 1.1 seit Slice 1.3 (#1472b) geschlossen: `GraphBuilderService.add_text_batches` schreibt nach jedem committeten Chunk einen `GraphBuildCheckpoint` (Menge bereits abgeschlossener Chunk-Indizes, nicht nur ein Höchstwert-Cursor — die Chunks laufen parallel und schließen außerhalb ihrer Ursprungsreihenfolge ab) atomar ins Projektverzeichnis. `POST /api/runs/<id>/resume` verarbeitet bei einem passenden Checkpoint (gleicher Graph, gleiche Chunk-Größe/-Overlap/-Methode) nur noch die fehlenden Chunks, statt neu zu beginnen; `resume_capability` zeigt das jetzt auch für den SIGTERM- und den Startup-Reconciliation-Pfad korrekt an, nicht nur für einen In-Process-Fehlschlag. Passt der Checkpoint nicht mehr, fällt die Route sauber auf einen vollen Restart zurück.

Für **`simulation_prepare`** gilt seit Slice 1.4 (#1472c) dasselbe Prinzip mit eigener Mechanik: liegt beim Abbruch bereits ein Checkpoint mit mindestens einem generierten Persona-Profil vor (`backend/app/services/prepare_checkpoint.py`), landet der `SimulationState` auf dem neuen Status `INTERRUPTED` statt `FAILED`, und ein erneuter `prepare`-Aufruf setzt die Persona-Generierung fort. Die beim Original-Versuch getroffene Cap-/Quota-Auswahl wird dabei **nicht neu berechnet** — der Graph-Lesepfad hat kein `ORDER BY` und könnte sonst eine andere Typ-Verteilung liefern —, sondern per Entity-UUID aus dem Checkpoint übernommen. Ohne verwertbaren Zwischenstand bleibt es beim bisherigen `FAILED`. **`report_generate`** hat weiterhin keinen Checkpoint; dort bleibt es bei `FAILED` ohne Resume-Angebot.

Zwei Grenzen, damit daraus keine falsche Zusage wird: Die Terminalisierung passiert **nicht** im Signal-Handler, sondern beim Interpreter-Shutdown — wird der Worker nach Ablauf von `graceful_timeout` per SIGKILL beendet, greift weiterhin nur die Startup-Reconciliation (die dieselbe Checkpoint-Prüfung nutzt). Der Prepare-Checkpoint deckt nur die parallele Hauptgenerierung ab, nicht die sequenzielle Reject-Backfill-Nachbesetzung danach — wird der Prozess mitten in der Backfill-Phase beendet, generiert ein Resume die offenen Slots erneut. Der Redis-Event-Bus ist **keine persistente Jobqueue**.

Seit Slice 1.5 (Architekturentscheidung des Maintainers, 2026-09-24) trägt jeder In-Process-Job eine **Lease mit Heartbeat und TTL** statt des alten PID+Token-Stempels ohne Ablauf: `enqueue()` schreibt `owner_pid`/`owner_token`/`heartbeat_at`/`lease_ttl_s` (`JobLease`, `backend/app/contracts/job_lease_contract.py`), ein Heartbeat-Thread erneuert `heartbeat_at` periodisch (Default alle 20s, TTL 90s) und endet zuverlässig mit dem Job — auch nach einer Exception. Die Erneuerung ist an Fortschritt gekoppelt: schreibt der Job länger als `AGORA_JOB_LEASE_MAX_STALL_SECONDS` (Default 1800s) kein neues Run-Event, bleibt der Heartbeat aus und die Lease verfällt eine TTL später — ein hängender Job-Target blockiert `/resume` also nicht mehr dauerhaft. `Config.validate()` lehnt Lease-Zeiten ≤ 0 und ein Heartbeat-Intervall über der halben TTL beim Start ab. `reconcile_stale_jobs` markiert einen Job jetzt auch dann als verwaist, wenn die Prozessidentität formal noch passt, die Lease aber abgelaufen ist. `POST /api/runs/<id>/resume` lehnt einen **nicht-terminalen** (`pending`/`processing`) Run mit **gültiger** Lease mit `409 job_lease_active` ab; ein bereits terminaler Run (insbesondere `failed`/`process_restart`) darf trotz rechnerisch noch nicht abgelaufener Lease fortgesetzt werden. Ein Altbestand-Manifest ohne Lease-Felder verhält sich unverändert (reiner Token-Vergleich, keine TTL-Prüfung). Damit sind die Scope-Punkte „Ownership/Lease" und „Schutz gegen stale Worker" aus #1472 erfüllt; Out-of-Process-Worker (eigener Worker-Prozess) und ein Resume-Pfad für `simulation_run` bleiben eigene Issues.

Report-Generierungen sind seit Slice 1.2 (#1265) je Simulation **serialisiert**: ein zweiter Start wird mit `409 report_generate_in_progress` abgewiesen, solange ein Run mit `run_type=report_generate` in `pending` oder `processing` steht. Das ist eine bewusste Verhaltensänderung gegenüber 0.9.5 und eine Einschränkung für parallele Nutzung, keine Optimierung. Reportarbeit in einen eigenen Prozess zu verschieben bleibt 1.0-Vorarbeit.

## Graph und Ingestion

- Episode- und `RELATION`-Writes sind gegen Retry-after-commit idempotent (`MERGE` auf stabiler UUID), damit ein verlorenes Neo4j-ACK nicht zu Constraint-Fehlern oder stillen Dubletten führt (#1460).
- Dokument-/Chunk-Provenance wird durch die Ingestion- und Evidence-Pfade getragen (ADR-0013).
- Persona-Kandidaten werden vor teuren LLM-Gates typbasiert gefiltert; zusammengesetzte Nicht-Personen-Typen werden über Kopfnomen-Suffixe erkannt (#1473).

- Vor dem Persona-Cap fasst `resolve_aliases()` Namensvarianten deterministisch zusammen (Klammer-Expansion, eindeutige Token-Teilmengen bei Organisationen, eindeutige Nachnamen bei Personen; kein Merge über Klassengrenzen), und `SemanticEntityClass` schließt technische Komponenten, Orte und Konzepte ohne LLM-Call aus — auch wenn sie als `Organization`/`TechnologyProvider` getypt sind ([#1470](https://github.com/arn0ld87/agora/issues/1470)). Der Graph und sein MERGE-Schlüssel bleiben unverändert.

- Die NER bekommt je Chunk einen nur lesenden Kontext (letzte Überschrift bzw. Dokument-Marker, bis zu 300 Zeichen Vorlauf) und soll Pronomen darauf auflösen; reine Pronomen werden verworfen, auch als Relations-Endpunkt. Chunk-Grenzen bleiben unverändert. Ein substantieller Chunk ohne Entitäten wird geloggt (#1470, #1292).

Offen bleibt LLM-gestützte Koreferenz (#1470, laut Plan außerhalb des Scopes). Die Persona-Art folgt weiterhin dem Typ; die semantische Klasse ergäbe dieselbe Entscheidung.

## Persona-Erzeugung

- Der geroutete Provider erreicht die Persona-Generierung; CLI-Transporte fallen bei fehlender Base-URL nicht mehr auf fremde `.env`-HTTP-Werte zurück (#1418/#1422).
- Vollständiger regelbasierter Persona-Fallback ist blockierend; ein Lauf mit 20/20 Platzhalter-Personas wird nicht als normaler Erfolg weitergereicht.
- Ablehnungen werden nicht mehr als „erfolgreich generiert“ protokolliert; die Bilanz zählt Kandidaten, Ablehnungen und erzeugte Personas konsistent (#1455).
- Das harte LLM-Aufrufbudget reserviert laufende Calls pro Run und greift auch bei paralleler Persona-Generierung; `BudgetExceededError` wird nicht in Fallback-Personas verschluckt (#1461).

`detect_domain_drift` vergleicht seit [#1471](https://github.com/arn0ld87/agora/issues/1471) die Hauptdomäne der Persona (das Fach mit den meisten exakten Markertreffern) gegen die Quelldomänen, statt jede Schnittmenge als Entwarnung zu werten; ein Overlap nur in einer Nebendomäne oder ein Gleichstand ohne eindeutigen Sieger gilt als Drift. Eine Quelle ohne erkennbares Fach liefert `unverifiable=True` statt einer stillen Entwarnung. Die Taxonomie liegt in `backend/app/services/persona_domain_taxonomy.py` und deckt jetzt elf Domänen ab (zusätzlich `it/security`, `public-sector`, `retail`, `media`, `legal`, `energy`). Der Nachtrag zu #1471 schließt die beiden Restpunkte: Die Branchenquote im Persona-Prompt bleibt weg, sobald Zusammenfassung oder Kontext der Entität erkennbares Fachvokabular tragen (`has_domain_markers`) — quellengebundene Akteure behalten ihre Branche, nur bewusst synthetische werden gelenkt. Erkannte Drift leert nicht mehr nur `profession`, sondern lässt Beruf, Bio und Freitext über `LLMClient.chat_json` (`PersonaDriftCorrectionSchema`, jetzt in `backend/app/contracts/persona_drift_contract.py`) korrigieren; scheitert die Korrektur, bleibt die alte Linie (Beruf leer, Freitext stehen) und `generation_error` macht die Degradation sichtbar. `BudgetExceededError` wird dabei nie abgefangen. Die Drift-Prüfung selbst zieht seither auch die Bio heran, nicht mehr nur Beruf und Freitext — sonst erreichte eine Bio-only-Drift den Korrekturpfad nie. Der Korrekturprompt ist kollektiv- und sprachbewusst: Kollektiv-Personas fordern weder Beruf noch Demografie an, `language="en"` erzeugt einen englischen Prompt statt eines immer-deutschen. Die Korrekturantwort selbst wird nach der Regeneration erneut gegen die Quelle geprüft; bleibt sie driftend, gilt dieselbe konservative Linie wie bei einer gescheiterten Korrektur (Beruf leer, alte Bio und alter Freitext bleiben) — ohne zweiten LLM-Versuch.

## Report, Evidence und Contracts

### Statuswahrheit

- Contract-invalid Reports dürfen nicht als normal `completed` ausgeliefert werden.
- Teilberichte aus Cancel-, Section-Failure- oder Fallback-Outline-Pfaden werden als `INCOMPLETE` klassifiziert; Resume bewahrt die Degradationsmarker und kann einen temporären Fallback-Outline neu planen (#1479).
- Ein `INCOMPLETE`-Report kann weiterhin auslieferbar sein; der tatsächliche Reportstatus steht in der Run-Metadaten-Sicht.

### Abschnittsgenerierung (Section-ReACT)

- Ob ein Abschnittsentwurf angenommen wird oder der Loop weiteres Retrieval anfordert, entscheidet die Evidence-Deckung, nicht die Zahl der Tool-Calls (#1294): angenommen wird, wenn das Retrieval des Abschnitts bindbare Evidence registriert hat oder jede prüfbare Aussage des Entwurfs thematisch in der vorab geladenen Evidence (`global_evidence_refs`) vorkommt. Geprüft werden dieselben Claim-Einheiten wie beim Binding, gleiche Zahlen ohne thematische Überlappung zählen nicht, ein Entwurf ohne prüfbare Aussage ist nie gedeckt. Ein ergebnisloser Tool-Call genügt nicht mehr, ein gedeckter Entwurf braucht keinen.
- Erschöpft der Loop seine Iterationen, bleibt ein gültiger, nur mangels Deckung zurückgewiesener Entwurf stehen, statt durch eine erneute Endgenerierung ersetzt zu werden; der Abschnitt bleibt als `forced_final` markiert.

### Persistenz

- Sektions-Evidence wird **vor** Markdown persistiert; Markdown ist der Commit-Marker.
- JSON/Markdown werden atomar geschrieben, inklusive Directory-`fsync` dort, wo die Plattform es unterstützt.
- Verwaistes Markdown ohne passende Evidence wird vor der Regeneration entfernt und nicht als Prompt-Kontext für spätere Sektionen wiederverwendet (#1475).
- Echte POSIX-Permission-/Storagefehler werden nicht als „fsync unsupported“ verschluckt.

### Evidence-API

- `GET /api/report/<id>/evidence` besitzt einen Pydantic-/JSON-Schema-/Zod-Vertrag als echte Union aus Erfolgs- und `evidence_omitted`-Fall (#1477).
- Contract-invalid Alt-Evidence kann als HTTP 200 mit `evidence_omitted` und `reason=contract_violation` zurückkommen, damit der Bericht lesbar bleibt, ohne die Evidence als geprüft vorzutäuschen.
- Exportpfade bleiben strenger: Formate, die Evidence als geprüfte Datei ausgeben würden, lassen invalides Material aus oder antworten mit einem Contract-Fehler.
- Cross-Stakeholder-Zählung normalisiert Rollenfamilien konsistent; der Zod-Spiegel bildet Python-`casefold` für die relevanten Fälle nach (#1477/#1482).

### Fließtext-Faktenprüfung

- Jeder numerische Fakt wird mit seinem **eigenen** Textausschnitt gegen den Evidence-Pool gehalten. Bis [#1492](https://github.com/arn0ld87/agora/issues/1492) lief das Prädikat eines Fakts bis zum Satzende und trug die übrigen Zahlen desselben Satzes mit — gebündelte, wörtlich belegte Seed-Aussagen bekamen dadurch `[Beleg fehlt]`, und im Prozentfall wurden mit der Quelle identische Sätze als vermeintlicher Widerspruch entfernt.
- Absolutzahlen und Prozentangaben werden im selben Satz beide erfasst; vorher entfielen die Absolutzahlen, sobald der Satz eine Prozentangabe enthielt.
- Die strukturierte Beanstandung (`unverified_statements[].reason`) benennt die konkret unbelegte Zahl und unterscheidet „teilweise belegt" von „gar kein Beleg".
- Ausgeschriebene Zahlwörter („sechs Angebote") sind prüfbare Fakten. `ein`/`eine` bleibt bewusst ausgenommen — im Deutschen weit öfter unbestimmter Artikel als Zahlwort; mitgezählt entstünde aus „eine Lehrkraft berichtet" eine Mengenbehauptung, die der Satz nicht aufstellt.
- Zahlenspannen („sechs bis neun Stunden", „zwischen 40 und 60 Prozent") erzeugen **keinen** Punktfakt. Die Vergleichslogik kennt nur Punktwerte und Schranken; eine Spanne als `EXACT` zu führen war eine Genauigkeit, die der Satz nicht behauptet. `bis zu` bleibt eine Obergrenze und damit ein vollwertiger Fakt.

### Operative Zahlen: Abweichungen verbunden oder sichtbar

- Schwellenwerte tragen eine berichtsweite Kennung nach dem Claim-Muster (`T7_01` = erster Schwellenwert aus Abschnitt 7). Vorher deduplizierte der Metadaten-Merge über die pro Abschnitt frei gewählte Modell-ID; zwei Abschnitte mit `thr_01` verloren still den zweiten Wert — auch wenn er dem ersten widersprach ([#1359](https://github.com/arn0ld87/agora/issues/1359)).
- `Threshold.deviates_from` + `deviation_rationale` verbinden eine gewollte Abweichung mit dem anderen Wert derselben Größe; ohne Begründung, als Selbstverweis oder ins Leere ist der Verweis vertragswidrig (Pydantic und Zod). Die Metadaten-Extraktion eines Abschnitts sieht die bereits erfassten Zahlen früherer Abschnitte samt Kennung.
- Dieselbe Größe (Label-Stichworte, Einheit, Rolle) mit verschiedenen Werten ohne Verbindung wird deterministisch erkannt: als Warnung unter der Tabelle „Operative Zahlen“ im Markdown und als Red-Team-Befund — unabhängig vom Intent-Gate des LLM-Red-Teams. Der Reportstatus bleibt davon unberührt; es ist ein Inhaltsbefund, keine Pipeline-Degradation.
- Grenze: Die Erkennung vergleicht nur Einträge mit gleichen Label-Stichworten. „Pilotdauer“ und „Dauer des Pilotbetriebs“ gelten als verschiedene Größen; solche Fälle bleiben dem LLM-Red-Team überlassen.

### Weiter offene Trust-Themen

- Quantoren („alle", „nahezu alle", „die meisten", „niemand") gelten nur als gestützt, wenn eine Quelle selbst einen gleich starken Quantor bzw. Anteil nennt oder genug Interview-Stimmen verschiedener Rollenfamilien ohne Gegenstimme übereinstimmen ([#1345](https://github.com/arn0ld87/agora/issues/1345)). Grenze: gezählt wird, was der Binder nach `top_k` sieht.
- Die **Gewinnung** von Evidence aus dem Seed bleibt LLM-seitig: Zerlegt die Graph-Ingestion einen gebündelten Seed-Satz zu einem Teilfakt, fehlen die übrigen Angaben im Pool. #1492 hat die Prüfseite deterministisch repariert, nicht die Extraktion davor.
- Dokumente tragen eine Textsorte (`document_role`, beim Upload je Datei wählbar). Szenario-, Frage- und Erwartungstext stützt keinen Claim; ein Claim, der nur daran hängt, wird als Hypothese mit Hinweis auf den Testfall geführt, und in der Tool-Ausgabe steht solcher Text als „Vorgabe des Testfalls – kein Simulationsbefund" ([#1240](https://github.com/arn0ld87/agora/issues/1240)). Offen: der bereinigte Gegenprobe-Lauf gegen ein Seed ohne Meta-Text, und Seeds, die Szenario und Erwartung in **einer** Datei mischen, bleiben ungetrennt — die Rolle gilt je Dokument.
- Claims tragen einen Typ (`empirical`/`analytical`/`recommendation`/`structural`, [#1400](https://github.com/arn0ld87/agora/issues/1400)). Nicht-empirische Claims bleiben evidence-geprüft, bekommen mit Beleg aber einen Boden von höchstens `low`; unbelegte Empfehlungen und Struktursätze werden Hypothese ohne Datenlücke. Die Typ-Klassifikation ist regelbasiert und im Zweifel `empirical`; eine Kalibrierung an Referenzläufen steht aus.

## Run-Budgets

Preflight, Zeit-, Token-, Kosten- und LLM-Aufrufbudgets sind produktiv. Seit #1478 werden auch Tool-Calls, Vision und Interview-Pfade pro physischem Provider-Aufruf geprüft und im Ledger erfasst; harte Budgetabbrüche werden bis zum Runstatus propagiert.

**Bekannte Grenze:** Der Default-Parallelrunner `scripts/run_parallel_simulation.py` besitzt eine eigene `ParallelIPCHandler`-Implementierung ohne vollständige `SubprocessBudgetGuard`-Anbindung. Dieser Pfad ist ausdrücklich **nicht** als vollständig budget-accounted zu behandeln, bis der Follow-up-Slice geschlossen ist.

## Embeddings

Chat-Routing und Embedding-Konfiguration sind absichtlich getrennt. Die persistente Embedding-Konfiguration lebt im `EmbeddingConfigurationStore`, Migrationen besitzen einen eigenen Lifecycle.

Der Runtime-Pfad löst die Embedding-Route inzwischen über den Store auf: `EmbeddingService()` geht in der Reihenfolge ausdrückliche Argumente → aktive Store-Konfiguration → Legacy-Sicht aus `Config.*`. Der Migrationslauf übergibt seine Route weiterhin ausdrücklich und bleibt unberührt.

Drei Punkte gehören dazu und sind bewusst hart:

- Eine aktive Konfiguration, deren Verbindung fehlt, deaktiviert ist oder keine Basis-URL trägt, **wirft**, statt auf `Config.*` zurückzufallen. Ein Rückfall würde Modell aus dem Store mit dem Endpoint aus der `.env` mischen — dieselbe stille Provider-Vertauschung, gegen die der Chat-Pfad absichert.
- `activate()` lehnt einen Dimensionswechsel ab, solange keine Indexversion in der neuen Dimension existiert. Geprüft wird gegen die Indexversion, nicht gegen die abgelöste Konfiguration: nach einer abgeschlossenen Migration ist die Aktivierung genau der gewollte letzte Schritt.
- Die Auflösung lässt nur eine Konfiguration durch, die zu dem passt, was der **aktive Index tatsächlich enthält** (aktive `EmbeddingIndexVersion`, sonst die Legacy-Sicht aus `Config.EMBEDDING_MODEL`/`VECTOR_DIM`). Alles andere wirft.

**[#1417](https://github.com/arn0ld87/agora/issues/1417) ist damit weiterhin nicht vollständig geschlossen, aber der Cutover ist jetzt sicher.** Seit Slice 2.1 lösen Lese- und Schreibpfad Index- und Property-Namen über den Store auf (`resolve_active_entity_index()` / `resolve_active_fact_index()`). Seit Slice 2.2 legt `EmbeddingMigrationService.start()` die neue Index-Version nur noch mit Status `building` an und lässt die alte Version `active`, solange die Migration läuft — `get_active_index_version()` und die kanonische Auflösung liefern in dieser Zeit weiterhin die alten Namen. Erst nach erfolgreichem Re-Embedding, bestandener Fortschritts-Validierung und einer echten Index-Prüfung gegen Neo4j (`Neo4jReEmbedder.index_is_online()`, `SHOW INDEXES` gegen `state`) schaltet der Service atomar um: Ziel-Version zuerst `active`, danach erst Quell-Version `superseded`. Jeder Fehlschlag- oder Abbruchpfad setzt die Ziel-Version auf `rolled_back` zurück und lässt die Quell-Version unangetastet `active` — ein nicht erfolgreicher Lauf schaltet den Betrieb nie um. Vor Slice 2.2 hätte genau das umgekehrte Verhalten (Ziel sofort `active`, Quelle sofort `superseded`, unabhängig vom Migrationsfortschritt) zusammen mit der kanonischen Auflösung aus Slice 2.1 zu stillen Leerergebnissen bei Reads und zu Schreibungen des alten Modells in die neue Property geführt — genau die Korruption, vor der #1417 warnt.

Das Modell allein umzustellen wäre weiterhin riskant, wenn die hier beschriebenen Schutzmechanismen umgangen würden: bei gleicher Dimension landen Vektoren zweier Modelle im selben Index (genau die Korruption aus #1417), bei abweichender Dimension gehen inkompatible Query-Vektoren an den Altindex — der Dimensionswächter (#263) fängt nur letzteres, und auch das nur am Index, nicht am Modell. Der harte Riegel oben und der Cutover-Schutz aus Slice 2.2 verhindern beides: ein Modellwechsel **ohne** abgeschlossene Re-Embedding-Migration erreicht den Laufzeitpfad nicht und wird laut abgelehnt, statt vorgetäuscht zu werden. Der Weg *mit* Migration (Konfiguration anlegen → proben → Migration starten → Cutover) ist in der Oberfläche verdrahtet; ein durchgeführter Durchlauf gegen echtes Neo4j und ein echtes Embedding-Backend steht als Nachweis noch aus.

**Slice 2.3 (`VECTOR_DIM`-SSoT) und Slice 2.4 (Legacy-View für Bestandsgraphen) sind bearbeitet, aber nicht vollständig (f006/embedding-ssot).** `resolve_operational_vector_dim()` (`app/services/embedding_configurations/runtime.py`) löst die Dimension des Betriebsindex kanonisch aus der aktiven `EmbeddingIndexVersion` auf, sobald eine existiert — vorher blieb `validate_embedding_configuration()` für immer an `Config.VECTOR_DIM` hängen, einem Env-Wert, der nach einer Migration auf ein Modell anderer Dimension stehenbleibt. **Nicht umgestellt** sind bewusst die Bootstrap- und Stub-Pfade: `storage/neo4j_schema.py` legt den unversionierten Legacy-Index weiterhin mit `Config.VECTOR_DIM` an, `neo4j_storage._ensure_schema()` prüft dessen Dimension gegen dasselbe Literal, und der Stub-Modus (`AGORA_E2E_LLM_MODE=stub`) erzeugt Vektoren dieser Länge. Für eine Erstinbetriebnahme ohne jede Indexversion ist das die einzige verfügbare Quelle; „`VECTOR_DIM` kommt ausschließlich aus dem Store" gilt damit für den Laufzeit-Validierungspfad, nicht für den Bootstrap.

Für die Bestandsgraph-Lücke (eine vor Slice 2.2 mit dem alten Sofort-Umschalt-Verhalten gestartete Migration, deren `active`-Version nie fertig migriert wurde) prüft `/readyz` jetzt die Behauptung gegen die Neo4j-Realität: `_check_embedding_index_version()` verifiziert über `Neo4jStorage.index_state()`, dass eine als `active` geführte Indexversion tatsächlich `ONLINE` ist, und macht einen unvollständigen Bestandszustand damit beim Start laut, statt ihn still gegen einen unvollständigen Index laufen zu lassen. Dass ein abgebrochener oder fehlgeschlagener Wechsel den Lesepfad nie umschaltet, ist für alle fünf Rollback-Pfade auf der Auflösung selbst getestet (`tests/services/test_embedding_migration.py`), nicht nur am Statusfeld.

Die Oberfläche zeigt den Betriebsindex seit f006 explizit an: `GET /api/llm/embedding/index-versions` liefert die Indexversionen, die Einstellungen-Ansicht macht daraus sichtbar, welche Version Reads/Writes bedient und welche gerade `building` ist und den Betrieb noch **nicht** bedient.

Der Zod-Spiegel `frontend/src/contracts/embeddingContract.ts` (`EmbeddingIndexStatusSchema`) kennt den `building`-Status bereits seit Slice 2.1/2.2 (Commit `b62aea62e`) — die vormals hier vermerkte Frontend-Drift-Lücke war zum Zeitpunkt dieser Prüfung bereits geschlossen, nur diese Notiz war stehengeblieben.

## Installation und Betrieb

- `install.sh` erzeugt `.env` aus der Vorlage und ersetzt bekannte Platzhalter durch sichere Werte.
- Host- und Docker-Modus erzeugen `SECRET_KEY`, `AGORA_AUTH_TOKEN`, `AGORA_SECRET_KEY` und `AGORA_FERNET_KEY`; die Zufallsquelle fällt von `python3` auf `openssl` bzw. `/dev/urandom` zurück (#1483).
- `NEO4J_PASSWORD` für eine externe/individuelle Neo4j-Instanz bleibt Operator-Konfiguration.
- Reports liegen unter `backend/uploads/reports/`, nicht unter `backend/reports/` (#1483).
- Prod bindet Backend standardmäßig an Loopback und nutzt einen read-only Root-Filesystem-Ansatz mit expliziten Write-Pfaden.

Backup/Restore ist dokumentiert, und seit [#766](https://github.com/arn0ld87/agora/issues/766)-Vorarbeit auch **ausführbar**: [`scripts/restore-drill.sh`](../scripts/restore-drill.sh) fährt Backup → Restore → Verifikation → Upgrade → Rollback und protokolliert jeden Schritt; [`backend/scripts/restore_verify.py`](../backend/scripts/restore_verify.py) prüft die bisherige Prosa-Checkliste maschinell, wobei ein übersprungener Punkt ausdrücklich nicht als bestanden zählt.

Seit [#1583](https://github.com/arn0ld87/agora/issues/1583) kennt das Werkzeug PostgreSQL: steht ein `AGORA_*_BACKEND` auf `postgres`, sichert `--phase backup` zusätzlich `pg_dump -n agora -Fc` plus `postgres-manifest.json` (Revision, Zeilenzahl je Tabelle) aus demselben exportierten Snapshot, `--phase restore` spielt den Dump vor dem App-Start zurück und stempelt die Alembic-Revision nach (`--phase pg_restore` wiederholt nur diesen Teil), und `restore_verify.py` prüft Revision, Zeilenzahlen und `agora.projects` → Projektverzeichnis. `DATABASE_URL` kommt wie für die Anwendung aus Umgebung oder `.env`; das Passwort geht nur über `PGPASSWORD` an die CLI-Tools. Im Legacy-Default bleibt der Teil ein No-Op. Nachgewiesen per Roundtrip-Integrationstest (Dump → leere DB → Restore → Verifikation, dazu drei rote Fälle), nicht auf einem echten Host.

**#766 bleibt offen und liegt im 1.0-Milestone.** Der manuelle Nachweis ist nach [#1659](https://github.com/arn0ld87/agora/issues/1659) auf einen Fresh-Host-Install/Restore mit vollem Supabase-Stack und Referenzbestand verschlankt; Upgrade und Rollback deckt das CI-Gate #1589 zusammen mit dem realen Cutover #1592 ab. Der Drill läuft während des RC-Soaks und muss vor dem 1.0-Tag protokolliert sein. Das vorhandene Werkzeug und ein Dry-Run sind noch kein durchgeführter Restore.

### Supabase: Infrastruktur vorhanden, im Default ungenutzt

Unter [`supabase/`](../supabase/README.md) liegt ein **eigenes** Compose-Projekt mit self-hosted Supabase (PostgreSQL 17, Supavisor, GoTrue, PostgREST, Storage, postgres-meta, Studio, Envoy-Gateway). Realtime, Edge Runtime, imgproxy und Analytics laufen bewusst nicht mit.

Dazu gibt es inzwischen PostgreSQL-Adapter, Alembic-Migrationen, optionale JWT-Authentifizierung und eine Workspace-API; die Abschnitte darunter beschreiben deren Stand und Grenzen. Im ausgelieferten Default sind PostgreSQL und Supabase-JWT nicht aktiviert. Der Agora-Stack startet ohne diesen separaten Stack; die Kopplung ans gemeinsame Docker-Netz `agora-backend` ist ein zusätzliches Overlay ([`deploy/compose/docker-compose.supabase.yml`](../deploy/compose/docker-compose.supabase.yml)), nie die Basis-`docker-compose.yml`.

Der Default nutzt weiterhin die Legacy-Metadatenspeicher. `AGORA_AUTH_BACKEND=hybrid` verhält sich ohne `AGORA_SUPABASE_JWT_ISSUER` wie `legacy`; mit aktiviertem JWT greift der optionale Auth- und Workspace-Pfad. GoTrue erlaubt laut `supabase/docker-compose.yml` Registrierung standardmäßig, verlangt aber E-Mail-Bestätigung. Das macht die Default-Installation nicht zum Mehrbenutzersystem.
Der Metadaten-Cutover auf armserver nutzt den bestehenden self-hosted Supabase des Hosts, nicht das Compose-Projekt unter `supabase/`. Ohne `AGORA_SUPABASE_JWT_ISSUER` bleiben `AGORA_AUTH_TOKEN` und das API-Key-Scope-Modell für Agora maßgeblich; GoTrue ist im Agora-Auth-Pfad nicht aktiviert.

Die Supabase-Konfigurationsdateien (DB-Init-SQL, Envoy-Routing, Supavisor-Config) liegen nicht im Repository. `supabase/bootstrap.sh` holt sie von einem gepinnten supabase/supabase-Commit nach `supabase/volumes/` (gitignored) — ohne diesen Lauf startet der Stack nicht.

### PostgreSQL-Grundlage: installiert, im Default ungenutzt

`sqlalchemy`, `psycopg[binary]` und `alembic` sind Backend-Abhängigkeiten. Der zentrale Adapter liegt in `backend/app/infrastructure/postgres/` (`Database.session()` als einziger vorgesehener Weg zu einer Verbindung), Alembic unter `backend/migrations/` mit versionierten Migrationen für das Fachschema `agora`, LLM-Profile, Projekte, Simulationen, Runs, Reports und den noch inaktiven Workspace-Vorbau.

Wirksam wird davon im Default nichts: `AGORA_METADATA_BACKEND=legacy` ist gesetzt, und solange er gilt, wird keine Verbindung aufgebaut. `DATABASE_URL` hat bewusst keinen Default; `Config.validate()` lehnt `AGORA_METADATA_BACKEND=postgres` ohne URL, einen unbekannten Backend-Wert und ein `postgresql://`-Schema (psycopg2 ist nicht installiert) beim Start ab.

Ab hier gilt die Regel aus Phase 2 des Plans: **das Datenbankschema wird ausschließlich über versionierte Migrationen geändert.** Kein `CREATE TABLE IF NOT EXISTS` in fachlichen Stores.

Seit [#1582](https://github.com/arn0ld87/agora/issues/1582) erzwingt `create_app` das auch beim Start: steht irgendein `AGORA_*_BACKEND` auf `postgres`, muss die Alembic-Revision in der Datenbank dem Head aus `backend/migrations/` entsprechen — sonst bricht der Start mit einer Meldung ab, die beide Revisionen nennt (`app/infrastructure/postgres/schema_gate.py::verify_schema_at_head`, Exception `SchemaDriftError`). Mehrere Alembic-Heads oder eine leere Versionstabelle zählen ebenfalls als Drift. Legacy-Defaults bauen dabei weiterhin keine Verbindung auf.

Für den Nachweis, dass eine Migration nichts verliert, existiert `backend/scripts/migration_baseline.py`: es erhebt je Objektklasse Anzahl, IDs, Zeitstempel, Statuswerte und Referenzen plus eine Prüfsumme je Artefaktdatei und vergleicht zwei solche Manifeste (Runbook: [`runbooks/migration-baseline.md`](runbooks/migration-baseline.md)). Beim Metadaten-Cutover auf armserver am 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592)) lief damit der erste Vorher/Nachher-Vergleich über eine echte Migrationsphase: Anzahl, IDs, Felder und Prüfsummen unverändert (Details unten unter „Metadaten-Cutover armserver“).

Die erste Fachtabelle existiert als Definition: `agora.llm_profiles` (SQLAlchemy-Modell `LlmProfileModel` plus Migration) hält LLM-Profil-Metadaten — Name, Provider, Basis-URL, Modellname, ein partieller Unique-Index, der höchstens ein Default-Profil erlaubt. Provider-Secrets bleiben im Fernet-Store, Workspace- und Auth-Spalten sind bewusst nicht vorgezogen. Gelesen und geschrieben wird sie über `AGORA_LLM_PROFILE_BACKEND=postgres` (Phase 4, siehe unten), unabhängig von `AGORA_METADATA_BACKEND`; aktiv ist das auf armserver seit 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592)).

Für die LLM-Profile existiert seit PR 3 ein Port (`app/repositories/llm_profile_repository.py`) mit genau einem Adapter: `SqliteLlmProfileRepository`, die umbenannte bisherige Klasse auf derselben `instance/llm_profiles.db`. `AGORA_LLM_PROFILE_BACKEND` schaltet die Ablage getrennt von `AGORA_METADATA_BACKEND` und steht im Default auf `sqlite`. Seit PR 4 existiert mit `PostgresLlmProfileRepository` ein zweiter Adapter: Metadaten aus `agora.llm_profiles`, Schlüssel aus dem Fernet-Store, IDs weiterhin als 32-Zeichen-`hex`, damit gespeicherte `profile:<id>`-Referenzen weiter zeigen. `backend/scripts/migrate_llm_profiles_to_postgres.py` überträgt den Bestand und lässt die SQLite unberührt; Ablauf und Rückweg stehen in [`runbooks/llm-profile-postgres-umstellung.md`](runbooks/llm-profile-postgres-umstellung.md).

**Umgeschaltet auf armserver seit 25.09.2026 (#1592):** `AGORA_LLM_PROFILE_BACKEND=postgres`, 1 Profil übertragen, `--verify` deckungsgleich (Metadaten, Zeitstempel, Schlüssel). Der Default im Code bleibt `sqlite`. Der Adapter ist gegen eine echte PostgreSQL-Instanz verifiziert (16 Integrationstests). Seit #1577 laufen alle PostgreSQL-Integrationstests im CI-Job `integration` gegen einen `postgres:17`-Service (auf `push:main` und `workflow_dispatch`); vorher fehlten dort Service und `AGORA_TEST_POSTGRES_URL`, und der Job war rot.

Dazu gehört ein zweiter Baustein: `LlmProfileSecretsStore` (`app/services/llm_profile_secrets_store.py`) legt die API-Keys **pro Profil** Fernet-verschlüsselt unter `AGORA_DATA_DIR` ab, weil `agora.llm_profiles` bewusst keine `api_key`-Spalte hat und der bestehende Provider-Secret-Store pro **Provider** ablegt — zwei Profile desselben Providers dürfen aber verschiedene Schlüssel tragen. `backend/scripts/migrate_profile_secrets.py` füllt den Store aus der SQLite (read-only, `--verify` vergleicht feldweise). Seit PR 4 liest `PostgresLlmProfileRepository` die Schlüssel aus diesem Store. Mit dem Default `sqlite` bleibt die SQLite die Wahrheit; auf armserver seit 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592)) gilt `AGORA_LLM_PROFILE_BACKEND=postgres`: Metadaten in `agora.llm_profiles`, Schlüssel in diesem Store, die SQLite ist eingefroren und nur noch Rückweg.

### Projektmetadaten: Vertrag, Port und zwei Adapter

Projekte hatten bis hierher keinen Vertrag: `Project` war eine Dataclass in `backend/app/models/project.py`, deren `to_dict()` über `GET /project/<id>`, `GET /project/list` und `POST /project/<id>/reset` ausgeliefert wird — eine Dataclass auf einer API-Grenze, was contracts-first ausschließt. Seit PR 6 liegt der Vertrag in `app/contracts/project_contract.py` (`project.schema.json`, `project-list-response.schema.json`), und `app/models/project.py` reicht `Project` und `ProjectStatus` nur noch weiter.

Daneben existiert ein Port `ProjectRepository` (`app/repositories/project_repository.py`) mit genau einem Adapter, `FileProjectRepository` (`app/services/file_project_store.py`) — die bisherige Dateilogik, umbenannt, nicht neu geschrieben. `ProjectManager` bleibt als Fassade stehen und delegiert seine fünf Metadatenmethoden dorthin; die sechs Artefaktmethoden (`files/`, `extracted_text.txt`, Dokument-Manifest) bleiben unverändert dateibasiert und wandern in keiner Phase des Plans in eine Datenbank. Keine der 52 Aufrufstellen in 13 Modulen wurde angefasst, und keine der 39 Testdateien mit Projektbezug musste angepasst werden.

Seit dem zweiten Teil von PR 6 gibt es den zweiten Adapter: `PostgresProjectRepository` (`app/infrastructure/postgres/repositories/project_repository.py`) auf der Tabelle `agora.projects` (Revision `7a3c1e84f209`). Der Spaltenschnitt ist Kern plus Nutzlast — `id`, `name`, `status`, `graph_id`, `llm_profile_id`, `created_at`, `updated_at` als Spalten, alle übrigen Vertragsfelder in `payload jsonb`. Die Aufteilung wird aus `Project.to_dict()` **abgeleitet**, nicht gepflegt: ein künftiges Vertragsfeld landet damit automatisch in der Nutzlast, statt beim Schreiben still verlorenzugehen. `backend/scripts/migrate_projects_to_postgres.py` überträgt den Dateibestand, lässt das Dateisystem unberührt und vergleicht mit `--verify` feldweise; Ablauf und Rückweg stehen in [`runbooks/projekt-postgres-umstellung.md`](runbooks/projekt-postgres-umstellung.md).

**Umgeschaltet auf armserver seit 25.09.2026 (#1592):** `AGORA_PROJECT_BACKEND=postgres`, 244 Projekte übertragen, `--verify` feldweise gleich. `AGORA_PROJECT_BACKEND` schaltet die Ablage getrennt von `AGORA_METADATA_BACKEND` und `AGORA_LLM_PROFILE_BACKEND` und steht im Default auf `file`. `Config.validate()` lehnt `postgres` ohne gesetzte `DATABASE_URL` beim Start ab. Der Adapter ist gegen eine echte PostgreSQL-17-Instanz verifiziert (17 Integrationstests, darunter ein Roundtrip über alle Vertragsfelder).

Drei Festlegungen des Schemas: `project_id` behält sein Format `proj_<12 Hexstellen>` und wird **keine** `uuid`, weil es der Verzeichnisname unter `uploads/projects/` ist — die Kennung erzeugt seitdem der Port, damit beide Adapter dieselbe Form liefern. `created_at`/`updated_at` sind `text` und nicht `timestamptz`, weil der Vertrag ISO-Zeichenketten führt und ein Umweg über `timestamptz` beim Lesen eine andere Zeichenkette ergäbe. `workspace_id` kam damals nicht vor; seit #1614 gehört jedes Projekt einem Workspace (siehe „Workspace-Isolation der Metadaten“).

### Simulationsmetadaten: Vertrag, Port, zwei Adapter

Simulationsmetadaten (`state.json`) wurden bis hierher direkt in `SimulationManager._save_simulation_state` und `_load_simulation_state` gelesen und geschrieben — ohne Vertrag, ohne Port. Seit #1578 liegt der Vertrag in `app/contracts/simulation_record_contract.py` (`SimulationRecord`, Pydantic v2, kein Schema-Dump — interner Persistenzvertrag), und ein Port `SimulationRepository` (`app/repositories/simulation_repository.py`) mit genau einem Adapter, `FileSimulationRepository` (`app/services/file_simulation_store.py`) — die bisherige Dateilogik, umstrukturiert, nicht neu geschrieben. `SimulationManager` bleibt Fassade und delegiert seine Metadatenzugriffe (`save`/`get`/`list`/`list_branches`) an das Repository; `simulation_config.json`, Profile, Logs und `run_instructions` bleiben unverändert dateibasiert. Keine Aufrufstelle außerhalb von `SimulationManager` wurde angefasst.

Der Adapter nutzt `SimulationArtifactStore` für den eigentlichen I/O und kennt kein direktes `open()`.

Seit #1585 gibt es den zweiten Adapter: `PostgresSimulationRepository` (`app/infrastructure/postgres/repositories/simulation_repository.py`) auf `agora.simulations` (Revision `c4e8a1d93b56`, linear auf `7a3c1e84f209`). Kernspalten `id`, `project_id`, `graph_id`, `status`, `source_simulation_id`, `root_simulation_id`, `created_at`, `updated_at`, der Rest aus `SimulationRecord.to_dict()` abgeleitet in `payload jsonb`. `project_id` ist Fremdschlüssel auf `agora.projects(id)` (nullable, `ON DELETE SET NULL`; `''` im Vertrag ist `NULL` in der Spalte). `save` legt eine unbekannte Simulation an — so schreibt `create_simulation` den ersten Datensatz; die gegenteilige Formulierung im Port-Docstring war falsch und ist korrigiert. `backend/scripts/migrate_simulations_to_postgres.py` überträgt den Bestand mit `--dry-run`/`--verify`, idempotent, Dateien unberührt, Fehler (fehlendes Projekt, unlesbare `state.json`) einzeln; Ablauf und Rückweg in [`runbooks/simulation-postgres-umstellung.md`](runbooks/simulation-postgres-umstellung.md).

**Umgeschaltet auf armserver seit 25.09.2026 (#1592):** `AGORA_SIMULATION_BACKEND=postgres`, 88 Simulationen übertragen, `--verify` 88/88. Der Default im Code bleibt `file`. `Config.validate()` lehnt `postgres` bei `AGORA_PROJECT_BACKEND=file` (der Fremdschlüssel zeigte ins Leere) und ohne `DATABASE_URL` ab. Der Adapter ist gegen eine echte PostgreSQL-Instanz verifiziert (Integrationstests für Adapter und Migrations-Roundtrip). Alle Metadatenzugriffe laufen über das Repository — auch der Stop-Status im Runner-Cleanup und die Prüfung/Hochstufung in `check_simulation_prepared`, die vorher direkt `state.json` lasen und schrieben.

### psycopg unter gevent: geprüft, kooperativ

Bis PR 4 stand hier als offener Punkt, psycopg 3 sei im Synchronmodus nicht gevent-kooperativ, während der Webprozess unter einem gunicorn-Worker mit gevent-Worker-Klasse läuft. **Die Annahme war falsch, und sie ist jetzt gemessen statt vermutet.** Acht gleichzeitige `SELECT pg_sleep(1)` in acht Greenlets brauchen 1,08 s direkt über psycopg und 1,04 s über `build_engine()`; seriell wären es acht. Die Gegenprobe ohne `gevent.monkey.patch_all()` braucht 8,19 s — der Unterschied liegt um eine Größenordnung auseinander, nicht im Messrauschen. Bei gepatchtem `select` wählt psycopg die Wartefunktion auf Python-Ebene; das ist die von psycopg ab 3.1.14 dokumentierte gevent-Unterstützung, `psycogreen` entfällt. Der Mindest-Pin liegt mit `>=3.2.0` darüber.

Bedingung dafür ist die Importreihenfolge: `gevent.monkey.patch_all()` muss vor dem ersten psycopg-Import laufen. Das ist keine neue Auflage, sondern dieselbe, die seit [#529](https://github.com/arn0ld87/agora/issues/529) `requests`/`ssl` schützt — `backend/wsgi.py` patcht als erstes Statement, das `Dockerfile` startet `wsgi:app`. Festgehalten wird das durch `backend/tests/integration/test_gevent_psycopg_cooperation.py`, nicht durch diese Notiz. Begründung und Grenzen: [ADR-0014](decisions/0014-psycopg-under-gevent-worker.md).

Ungeprüft bleibt das Verhalten hinter Supavisor unter Last. Der HARDSTOP `--workers 1` bleibt aus den in `backend/gunicorn.conf.py` genannten Gründen unberührt.

### Run-Registry: Vertrag, Port, zwei Adapter

`RunRegistry` delegiert seit #1579 die Datei-I/O an `FileRunRepository`
(`backend/app/services/file_run_store.py`), hinter dem `RunRepository`-Protocol
(`backend/app/repositories/run_repository.py`).  Das Pydantic-v2-Modell
`RunRecord` (`backend/app/contracts/run_record_contract.py`) beschreibt die
persistierten Manifest-Felder; Lease-Felder (`worker_pid`, `worker_token`,
`heartbeat_at`, `lease_ttl_s`) bleiben in `metadata` und sind kein Bestandteil
des Port-Vertrags.  `RunRegistry` bleibt Fassade (Singleton, Lock,
canonical_status, Events, Aggregation).

Seit #1587 gibt es den zweiten Adapter: `PostgresRunRepository` (`app/infrastructure/postgres/repositories/run_repository.py`) auf `agora.runs` (Revision `3f9b2d7e6a41`, linear auf `c4e8a1d93b56`). Anders als bei Projekten und Simulationen ist `payload jsonb` das vollständige Manifest aus `RunRecord.to_manifest()`, und die Spalten `run_type`, `entity_id`, `status`, `simulation_id`, `started_at`, `updated_at`, `completed_at` sind daraus abgeleitete Projektionen — der Vertrag unterscheidet "Feld fehlt" von "Feld ist `null`" (`exclude_unset`), das kann nur das Manifest tragen. `simulation_id` kommt aus `linked_ids.simulation_id` und ist Fremdschlüssel auf `agora.simulations(id)` (nullable für Graph-Build-Runs, `ON DELETE SET NULL`). Ein neuer Run mit unbekannter Simulation scheitert mit `RunSimulationMissing`; ein bestehender, dessen Simulation inzwischen fehlt, schreibt weiter. `save` ist ein `INSERT … ON CONFLICT DO UPDATE` und stempelt nichts, wie der Dateiadapter. Lease und Heartbeat bleiben im Manifest (`metadata`), ohne eigene Spalte. Der Prozess-Adapter (`get_database()`) hat seitdem einen Verbindungs-Timeout von 10 s, weil die Start-Reconciliation die Registry liest. `backend/scripts/migrate_runs_to_postgres.py` überträgt den Bestand mit `--dry-run`/`--verify`, idempotent, Dateien unberührt, Fehler (fehlende Simulation, abweichende `run_id`, unlesbares Manifest) einzeln; Ablauf und Rückweg in [`runbooks/run-postgres-umstellung.md`](runbooks/run-postgres-umstellung.md).

**Umgeschaltet auf armserver seit 25.09.2026 (#1592):** `AGORA_RUN_BACKEND=postgres`, 594 Runs übertragen, `--verify` 594/594. Zwei Manifeste aus der Testsuite (Simulation `sim_abcdef012345` ohne `state.json`) wurden vorher archiviert statt übertragen. Der Default im Code bleibt `file`. `Config.validate()` lehnt `postgres` bei `AGORA_SIMULATION_BACKEND=file` (der Fremdschlüssel zeigte ins Leere) und ohne `DATABASE_URL` ab. Der Adapter ist gegen eine echte PostgreSQL-Instanz verifiziert (Integrationstests für Adapter, Migrations-Roundtrip und `POST /api/runs/<id>/resume` samt `409 job_lease_active`).

### Report-Metadaten: Vertrag, Port, zwei Adapter

`ReportManager` delegiert seit #1580 das Lesen/Schreiben der Metadaten-Datei
(`meta.json`, inkl. Legacy-Flachformat-Fallback `<report_id>.json`) an
`FileReportRepository` (`backend/app/services/file_report_store.py`), hinter
dem `ReportRepository`-Protocol (`backend/app/repositories/report_repository.py`).
Das Pydantic-v2-Modell `ReportRecord`
(`backend/app/contracts/report_record_contract.py`) beschreibt die
persistierten Metadatenfelder verlustfrei (inkl. `outline` und
`simulation_snapshot` als generische Dicts). Report-Inhalte (`report-v3.json`,
`outline.json`, `section_XX.md`, Logs; Plan §11 Klasse B) bleiben Dateien und
laufen NICHT über den Port — sie werden weiterhin direkt über
`report_agent/storage.py` gelesen/geschrieben. `ReportManager` bleibt Fassade;
keine Aufrufstelle außerhalb von `ReportManager` wurde angefasst. Der Port
liefert neben `list()` auch `list_ids()` mit den Ablageschlüsseln: Altbestände
mit abweichendem Ordnernamen finden ihre Artefakte weiter über den Ordner, nicht
über die `report_id` im Manifest. Seit Teil 1 von #1588 lesen auch
`branching_service.create_branch` (Report-Kopie in einen Zweig) und
`simulation_history._get_report_id_for_simulation` die Metadaten über den Port
statt `meta.json` direkt zu öffnen; der Zweig kopiert den Report-Ordner unter
dem Ablageschlüssel.

Seit Teil 2 von #1588 gibt es den zweiten Adapter: `PostgresReportRepository` (`app/infrastructure/postgres/repositories/report_repository.py`) auf `agora.reports` (Revision `8d6e0b3c2f15`, linear auf `3f9b2d7e6a41`). Primärschlüssel ist der **Ablageschlüssel** (Ordnername), nicht zwingend die `report_id` im Datensatz — Altbestände finden ihre Inhalte so weiter. `payload jsonb` hält den vollständigen Inhalt von `meta.json`; `report_id`, `simulation_id`, `status`, `created_at`, `completed_at` sind daraus abgeleitete Projektionen. `simulation_id` ist Fremdschlüssel auf `agora.simulations(id)` (nullable, `ON DELETE SET NULL`); gelesen und nach Simulation gefiltert wird aus dem `payload`, damit ein Report ohne Simulation dieselbe Antwort liefert wie in der Dateiablage. Der Port hat seitdem `delete()`: `ReportManager.delete_report` entfernt den Metadatensatz über das Repository und danach den Ordner. `backend/scripts/migrate_reports_to_postgres.py` überträgt den Bestand (Ordner- und Flachformat) mit `--dry-run`/`--verify`, idempotent, Dateien unberührt, Fehler einzeln; Ablauf und Rückweg in [`runbooks/report-postgres-umstellung.md`](runbooks/report-postgres-umstellung.md). Report-Inhalte bleiben Dateien.

**Umgeschaltet auf armserver seit 25.09.2026 (#1592):** `AGORA_REPORT_BACKEND=postgres`, 80 Reports übertragen, `--verify` 80/80. Der Default im Code bleibt `file`. `Config.validate()` lehnt `postgres` bei `AGORA_SIMULATION_BACKEND=file` und ohne `DATABASE_URL` ab. Der Adapter ist gegen eine echte PostgreSQL-Instanz verifiziert (Integrationstests für Adapter, Migrations-Roundtrip, Löschen über `ReportManager` und einen mit beiden Backends byte-gleichen Export).

### Workspaces: Tabellen und Principal-Vertrag

Seit #1612 gibt es `agora.workspaces` und `agora.workspace_members` (Alembic-Revision `5c2913c7ba4f`, linear auf `8d6e0b3c2f15`), inklusive Default-Workspace (`00000000-0000-0000-0000-000000000001`/Slug `default`/Name `Standard`), den die Migration selbst einfügt. `workspace_members.role` ist per Check-Constraint auf `owner|admin|member|viewer` begrenzt, `slug` per Check-Constraint auf `^[a-z0-9][a-z0-9-]{0,62}$` und eindeutig. `workspace_members.user_id` trägt **keinen** Fremdschlüssel auf `auth.users` — CI und lokale Testläufe laufen gegen reines PostgreSQL ohne das Supabase-`auth`-Schema, die referenzielle Integrität dorthin ist Sache der Anwendungsschicht. Dazu kommen der Port `WorkspaceRepository` (`backend/app/repositories/workspace_repository.py`) und der Adapter `PostgresWorkspaceRepository` (`backend/app/infrastructure/postgres/repositories/workspace_repository.py`, `get`/`get_by_slug`/`create`/`list_for_user`/`membership`/`add_member`/`remove_member`) sowie die Verträge `Workspace`/`WorkspaceMembership`/`WorkspaceRole` (`backend/app/contracts/workspace_contract.py`) und `Principal`/`AuthType` (`backend/app/contracts/auth_contract.py`). Anders als bei den übrigen Ports gibt es keinen Dateiadapter und kein Backend-Flag: `get_workspace_repository()` liefert immer den PostgreSQL-Adapter und verlangt nur `DATABASE_URL`.

**Stand:** Seit #1614 lesen und schreiben die PostgreSQL-Adapter `workspace_id` (unten), seit #1613 legt der Guard für jeden Request einen `Principal` ab. Auf armserver seit 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592)) liegen alle 244 Projekte, 88 Simulationen, 594 Runs und 80 Reports im Default-Workspace. Weitere Workspaces entstehen nur mit Supabase-JWT, und das ist nach ADR-0019 aus.


### Auth: Supabase-JWT und Principal (#1613)

Seit #1613 kennt der Guard `AGORA_AUTH_BACKEND=legacy|hybrid|supabase` (`backend/app/utils/auth.py`, ADR-0018). Der Default ist `hybrid`. Ohne `AGORA_SUPABASE_JWT_ISSUER` verhält sich `hybrid` exakt wie `legacy`; der Startlog sagt das.

- **JWT-Prüfung:** `backend/app/security/supabase_jwt.py` prüft Signatur (JWKS oder HS256), `iss`, `aud`, `exp`, `nbf` und `sub`.
- **Workspace-Wahl:** Sie läuft über `X-Agora-Workspace` und die Mitgliedschaft in `agora.workspace_members`.
- **Principal:** Jeder zugelassene Request legt einen `Principal` ab. `require_scope` leitet die Scopes aus der Rolle ab, Tickets sind an ihren Aussteller gebunden.
- **Betreiber-Endpunkte:** Settings, LLM-Profile, API-Keys, Logs, Onboarding, Profil und Modell-Stream sind für JWT-Nutzer gesperrt.

**Umgeschaltet ist nichts:** `AGORA_SUPABASE_JWT_ISSUER` ist nicht gesetzt. Verifiziert ist das mit Unit-Tests für Verifier, Guard, Scopes und Tickets sowie mit einem Integrationstest der Mitgliedschaftsprüfung gegen PostgreSQL.


### Workspace-Isolation der Metadaten (#1614)

Seit #1614 gehören Projekte, Simulationen, Runs und Reports je einem Workspace.
- **Migration:** Die Alembic-Revision `14d60476b8ce` legt `workspace_id` an, schreibt den Bestand auf den Default-Workspace zurück und setzt danach `NOT NULL`.
- **Fremdschlüssel:** Verweise sind zusammengesetzt (`(project_id, workspace_id)`, `(simulation_id, workspace_id)`) und können keine Workspace-Grenze überschreiten. `ON DELETE SET NULL (<spalte>)` lässt dabei die `workspace_id` stehen.
- **Adapter:** Die PostgreSQL-Adapter lesen, listen, schreiben und löschen im Request nur im Workspace des Principals. Außerhalb eines Requests (Hintergrund, Migration) erbt eine neue Zeile den Workspace ihres Elternteils.
- **Guard:** Für Supabase-Nutzer prüft er jede Kennung im Request vor der View (`app/security/resource_guard.py`).
- **LLM-Profile** bleiben prozessweit und sind Betreibern vorbehalten.

Verifiziert gegen PostgreSQL mit:
- Backfill eines Bestands samt `alembic check` und Rückweg
- abgelehnten Verweisen über die Workspace-Grenze
- Request-Isolation und System-Kontext
- Verweisprüfung im Guard

**Einzelbetrieb aktiv auf armserver seit 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592)):** Die Adapter arbeiten dort mit `workspace_id`. Ohne JWT ist der Principal der Legacy-Principal im Default-Workspace (`legacy_principal`), Hintergrundarbeit läuft im System-Kontext. Aus ist nur die Mandantentrennung zwischen Nutzern (kein `AGORA_SUPABASE_JWT_ISSUER`, ADR-0019).


### Row Level Security (#1615)

Seit #1615 stehen Projekte, Simulationen, Runs, Reports, Workspaces und Mitgliedschaften unter `ENABLE` und `FORCE ROW LEVEL SECURITY` (Alembic `e746a558dce5`).
- **Policy:** Sichtbar ist eine Zeile im Workspace der Transaktion (`agora.workspace_id`) oder im System-Kontext (`agora.system = on`). `Database.session()` setzt beides je Transaktion, aus dem Principal oder, ohne Principal, als System-Kontext. Eine Verbindung ohne Kontext sieht nichts.
- **Laufzeitrolle:** Das Start-Gate (`app/infrastructure/postgres/rls_gate.py`) verweigert im Tenant-Modus eine Rolle, die RLS umgeht (Superuser, `BYPASSRLS`, Owner). Migrationen, `pg_restore` und Backup nutzen `AGORA_MIGRATION_DATABASE_URL`, Rollen-Setup in [`runbooks/rls-rollen.md`](runbooks/rls-rollen.md).
- **Werkzeuge:** `pg_dump`/`pg_restore` laufen mit `--enable-row-security` im System-Kontext.
- **Supabase-Rolle `authenticated`:** darf nur lesen, gefiltert über `auth.uid()`. Die Policy wird nur angelegt, wenn das Schema `auth` existiert.

Verifiziert mit der Testmatrix aus §18 gegen PostgreSQL, roh unter einer eingeschränkten Rolle. **Aktiv auf armserver seit 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592)):** FORCE RLS greift, die App läuft als `agora_app` (`NOSUPERUSER NOBYPASSRLS`, besitzt keine Tabelle); ohne Kontext sieht sie 0 Zeilen. Requests laufen im Default-Workspace, Hintergrundarbeit im System-Kontext. Der Tenant-Modus (Rollen-Gate bricht den Start ab, Workspace aus dem JWT) ist aus, weil kein JWT-Issuer gesetzt ist (ADR-0019).

### Offene Registrierung und Workspace-API (#1616)

Seit #1616 gibt es `/api/workspaces` (Liste, Bootstrap, Mitglieder) und das öffentliche `GET /api/auth/config`.
- **Registrierung:** Jeder mit bestätigter E-Mail-Adresse bekommt ein Konto und über `POST /api/workspaces/bootstrap` genau einen persönlichen Workspace als Owner. Zugang zu fremden Workspaces vergeben nur deren Owner und Admins.
- **Mitglieder:** Owner-Rollen nur durch Owner, der letzte Owner bleibt, jeder darf sich selbst entfernen. Bootstrap und Mitgliederverwaltung sind rate-limitiert.
- **GoTrue** (`supabase/docker-compose.yml`): Registrierung offen, Bestätigung Pflicht, Passwort ab 12 Zeichen, Refresh-Token-Rotation, Stundenlimits, SMTP-Variablen. Runbook: [`runbooks/offene-registrierung.md`](runbooks/offene-registrierung.md).

Verifiziert gegen PostgreSQL mit signierten Tokens (`tests/integration/test_workspace_api.py`). **Umgeschaltet ist nichts:** ohne `AGORA_SUPABASE_JWT_ISSUER` bleibt Agora einmandantig.

### Frontend-Login mit Supabase (#1617)

Seit #1617 meldet sich das Frontend bei aktivem JWT über `@supabase/supabase-js` an. Der Client dient nur der Anmeldung, Fachdaten laufen weiter über Flask.
- **Store und Header:** Der Pinia-Store `auth` hält Konfiguration, Session, Workspaces und aktiven Workspace. Der Interceptor sendet `Authorization: Bearer` und `X-Agora-Workspace`, bei `401` erst einmal ein Refresh.
- **Views:** Login, Registrierung, Passwort-Reset und E-Mail-Bestätigung unter `/auth/*`. Ohne Session leitet der Guard auf den Login. Workspace-Wechsel und Abmelden stehen im Nutzermenü.
- **Session ohne Workspace:** Eine Session ohne aktiven Workspace (etwa die Recovery-Session aus dem Reset-Link) erreicht nur Passwort-Reset und Login, auch keine anderen `/auth/*`-Routen. Der Guard führt bei laufendem Reset zum Reset, sonst zum Login.
- **Abmelden:** Session, Token, Workspace und SSE-Tickets werden immer lokal verworfen. Scheitert die Abmeldung bei Supabase, löscht das Frontend die gespeicherte Session (`agora-supabase-auth`) direkt, ohne zweiten Netzaufruf. Eine Session unter dem früheren Standardschlüssel `sb-<ref>-auth-token` übernimmt der Client beim Start.
- **Legacy-Modus unverändert:** Ohne JWT bleiben Master-Token, Routen und Menü wie bisher.

Verifiziert mit Vitest (Store, Interceptor, Guard, Views, Nutzermenü) und dem Playwright-Smoke `auth-login.spec.ts` gegen gemockte Auth-Endpunkte, inklusive axe und 320-px-Prüfung.

### Realtime für Listen-Projektionen (#1618)

Seit #1618 lädt das Frontend Ablage und Run-Listen nach, sobald sich im aktiven Workspace ein Projekt, eine Simulation, ein Run oder ein Report ändert. Das Ereignis ist nur ein Signal: Die Daten kommen weiter über die Flask-API, der Payload wird nicht gelesen. Das SSE laufender Läufe bleibt unverändert, ebenso das Polling als Rückfallebene.
- **Datenbank:** Alembic `dc4e84e7c000` nimmt die vier Tabellen in die Publication `supabase_realtime` auf, nur für `INSERT` und `UPDATE`. `DELETE` kann Realtime nicht gegen RLS prüfen. Ohne Publication (reines PostgreSQL, CI) ist die Migration ein No-op.
- **Sichtbarkeit:** Realtime prüft je Abonnent die RLS-Policy für `authenticated` aus #1615. Das Frontend verwirft zusätzlich Ereignisse aus einem fremden Workspace und lädt höchstens einmal pro Sekunde und Tabelle nach.
- **Dienst:** `realtime` (`supabase/realtime:v2.134.10`) läuft im Supabase-Stack, ohne Host-Port und nur über das Gateway erreichbar (`/realtime/v1/`).
- **Schalter:** `AGORA_SUPABASE_REALTIME=true`, Default aus. `GET /api/auth/config` meldet `realtime_enabled` nur bei aktivem JWT.

Verifiziert mit Vitest (Kanal, Filter, fremder Workspace, Bündelung, Anbindung in Ablage und Run-Polling) und Integrationstests gegen PostgreSQL (Migration mit und ohne Publication, RLS-Matrix unter `authenticated` mit nachgebildetem `auth.uid()`). Eine Realtime-E2E-Prüfung gegen den laufenden Stack gibt es nicht. **Umgeschaltet ist nichts.**

### Metadaten-Migration: Rollback-Gate

Seit #1589 prüft `backend/tests/integration/test_metadata_migration_rollback.py` den ganzen Weg in einem Test (Plan §36): Ein Legacy-Bestand aus LLM-Profil (SQLite), Projekt, Simulation, Run und Report wird mit allen `migrate_*_to_postgres.py` übertragen, und jedes `--verify` muss mit Exit 0 enden. Dann startet `create_app()` mit allen fünf Schaltern auf `postgres`, während die Legacy-Metadateien versteckt sind. Anschließend startet die App erneut mit allen Schaltern auf Legacy. Die Antworten von zehn Lese-Endpunkten (Einzelabruf und Liste je Domäne) müssen in beiden Phasen gleich sein, und jeder Datensatz muss mit unveränderter Kennung da sein. Ein zweiter Test belegt, dass `Config.validate()` einen Rückweg in falscher Reihenfolge ablehnt. Der Test läuft im CI-Integration-Job gegen PostgreSQL; er schaltet keine Produktionsinstanz um. Der armserver-Cutover steht unten.

### Metadaten-Cutover: Sammelprüfung

Seit #1590 fährt `backend/scripts/verify_metadata_cutover.py` alle Prüfungen des Cutovers in einer Reihenfolge: Schalter-Konsistenz (dieselben Regeln wie `Config.validate()`, Fremdschlüssel-Reihenfolge LLM-Profile → Projekte → Simulationen → Runs → Reports), Alembic-Head (dieselbe Funktion wie das Start-Gate), das `verify` der fünf Migrationsskripte und `migration_baseline.py --compare`. Exit 0 nur, wenn jeder Schritt `OK` ist; `FEHLER` gibt 1, `UNGEPRÜFT` (etwa ohne `--baseline`) 2. Ein Schritt, der wirft, scheitert allein und nennt nur den Ausnahmetyp. Das Skript liest ausschließlich. [`runbooks/metadata-postgres-cutover.md`](runbooks/metadata-postgres-cutover.md) fasst die fünf Einzel-Runbooks in Cutover-Reihenfolge zusammen, samt Rückweg in umgekehrter Reihenfolge. Verifiziert mit Unit-Tests je Schritt und einem Integrationstest gegen PostgreSQL. Auf armserver lief die Sammelprüfung am 25.09.2026 vor dem Umschalten mit den fünf Zielschaltern und `--baseline` mit Exit 0 (8/8 `OK`).

### Metadaten-Cutover armserver (#1592)

Am 25.09.2026 auf armserver durchgeführt, Protokoll unter `/srv/agora-cutover-20260925.log` und im Issue [#1592](https://github.com/arn0ld87/agora/issues/1592). Alle fünf Metadaten-Domänen stehen auf `postgres`: `AGORA_LLM_PROFILE_BACKEND`, `AGORA_PROJECT_BACKEND`, `AGORA_SIMULATION_BACKEND`, `AGORA_RUN_BACKEND`, `AGORA_REPORT_BACKEND`.

- **Datenbank:** der bestehende self-hosted Supabase-Stack des Hosts (`/opt/supabase`, Studio „Default Project“), Schema `agora`, Alembic-Head `dc4e84e7c000`. Self-hosted Supabase kennt nur ein Projekt; Agora ist dort ein eigenes Schema neben anderen Anwendungen. Der Stack aus `supabase/` im Repository läuft auf diesem Host nicht.
- **Rollen:** Alembic und Backup als Owner (`postgres.<tenant>` über den Pooler), die App als `agora_app` (`NOSUPERUSER NOBYPASSRLS`, nur DML). Die Owner-URL liegt nicht in der `.env` der App. Der Agora-Container erreicht den Pooler über das Netz `supabase_default` (host-lokales Compose-Overlay).
- **Multi-User bleibt aus (ADR-0019):** `AGORA_SUPABASE_JWT_ISSUER` und `AGORA_SUPABASE_REALTIME` sind nicht gesetzt, `AGORA_AUTH_BACKEND` bleibt ungesetzt; der Startlog meldet „hybrid ohne AGORA_SUPABASE_JWT_ISSUER — JWT-Zweig inaktiv, Verhalten wie legacy“. Die Migration `dc4e84e7c000` hat die Publication `supabase_realtime` des gemeinsamen Stacks auf `insert, update` gesetzt (vorheriger Wert in `public.agora_realtime_baseline`).
- **Nachweis:** Baseline vorher/nachher gleich, `verify_metadata_cutover.py` Exit 0 (8/8), `/readyz` mit `postgres: ok`, API-Zählung 244/88/594/80/1 wie Baseline; Oberfläche geprüft (Profilliste, Profilauswahl, Ablage, Lauf-Detail). Ein neuer Lauf ist noch nicht gestartet.
- **Backup:** vorher `/srv/agora-backup-20260925` (Dateiverzeichnisse, Neo4j offline gedumpt), nachher `/srv/agora-backup-20260925-nachher` mit `postgres.dump` und `postgres-manifest.json` (Revision `dc4e84e7c000`).
- **Offen:** sieben Tage Beobachtung, danach Restore-Drill auf frischem Host inklusive PostgreSQL ([#766](https://github.com/arn0ld87/agora/issues/766)). Der Rückweg (Schalter in umgekehrter Reihenfolge, [`runbooks/metadata-postgres-cutover.md`](runbooks/metadata-postgres-cutover.md)) ist für die ersten Stunden gedacht.

### Readiness: `/readyz` kennt den PostgreSQL-Zustand

Seit #1581 trägt `/readyz` (`backend/app/readiness.py`) einen zusätzlichen Check `postgres` mit einem maschinenlesbaren `state` (`ok`/`unavailable`/`disabled`, Vertrag `app/contracts/readiness_contract.py::PostgresReadinessCheck`). `disabled` gilt, solange kein `AGORA_*_BACKEND` auf `postgres` steht — dann wird **keine** Verbindung aufgebaut, nicht einmal eine Engine, und der Check macht `/readyz` nicht rot. Steht mindestens ein Backend auf `postgres`, probt der Check `SELECT 1` über eine eigene `Database`-Instanz (NullPool, kleines Verbindungs-Timeout, statt des Prozess-Singletons). Seit #1642 wird sie pro Prozess einmal gebaut und wiederverwendet, statt bei jedem Healthcheck eine neue Engine anzulegen und meldet bei Fehlschlag `unavailable` (503). Fehlerdetails im Response-Body sind immer generisch — Host, Port, User, Passwort und Datenbankname aus `DATABASE_URL` tauchen weder dort noch im Log auf.

**Umgeschaltet auf armserver seit 25.09.2026 (#1592):** alle fünf Metadaten-Schalter stehen auf `postgres`, der Check meldet `postgres: ok`. Im Code-Default (ohne gesetzte Schalter) meldet er weiterhin `disabled`. `active_postgres_backends()`/`any_postgres_backend()` (`backend/app/infrastructure/postgres/backends.py`) sind die einzige Stelle, die alle `*_BACKEND`-Schalter kennt — Alembic-Drift-Gate (#1582) und Backup (#1583) nutzen dieselbe Funktion.

## Security

Aktueller Schwerpunkt:

- API-Token/API-Key-Scope-Modell und signierte Tickets.
- Secrets-at-rest für Provider-Keys; keine Klartext-Provider-Keys in Reports/Run-Manifests.
- strukturierte `/api/status`-Fehler statt roher Exception-Strings (#1459).
- Dependency-Risk-Register mit Hardstops; NLTK/PYSEC-2026-597 ist ab nltk 3.10.0 gefixt (GitHub Advisory, #661 geschlossen), nltk ist seit #1410 nicht mehr im Lock.
- Outbound-Fetches mit agenten-/modellgelieferten URLs laufen zentral über `backend/app/security/outbound_http.py` (Adressklassen, Redirect-Revalidierung, IP-Pinning, Byte-Limit). Der zuvor ungeschützte Pfad `scripts/agent_tools.py::web_fetch` ist damit geschlossen ([#1485](https://github.com/arn0ld87/agora/issues/1485)).
- Statische Security-Scans in CI: CodeQL für Python, JS/TS und GitHub-Actions-Workflows (Injection in `run:`-Blöcken), Ruff mit flake8-bandit-Regeln (`S`, Baseline-Ignores für S101/S110/S112/S311/S603/S607 in `backend/pyproject.toml`), Trivy für das Container-Image (blockierend ab HIGH) und für Dockerfile/Compose-Konfiguration (Kategorie `trivy-config`, vorerst nur berichtend).
- Der Security-Istabgleich [#1666](https://github.com/arn0ld87/agora/issues/1666) fand 67 offene CodeQL-High-Alerts; [#1669](https://github.com/arn0ld87/agora/issues/1669) triagiert sie als P1. False Positives brauchen eine begründete Dismissal, akzeptierte echte Risiken eine vom Maintainer freigegebene Ausnahme mit Frist; Supabase-Images gehören zum Stichtag-Scan [#1670](https://github.com/arn0ld87/agora/issues/1670).
- Eine Ablehnung durch dieselbe Policy gibt die untrusted URL nicht mehr weiter: `OutboundRequestBlocked` trägt in der Message nur den Grund und in `.url` nur die sichere Herkunft (Schema, Host, ggf. Port). Die frühere Userinfo-Redaktion ließ Token in Query, Fragment und Pfad stehen.

Der Single-Platform-Tool-Loop (`ToolAwareActionLoop.decide_action` in `backend/scripts/agent_tools.py`, genutzt von `run_twitter_simulation.py`/`run_reddit_simulation.py` bei aktivierten Agent-Tools) liest seit [#1224](https://github.com/arn0ld87/agora/issues/1224) die echte OASIS-Timeline (`agent.env.to_text_prompt()`; vorher kam dort immer ein leerer String an) und kapselt sowohl diese Observation als auch Tool-Ergebnisse (`web_search`/`web_fetch`) in `<untrusted_data source="...">...</untrusted_data>` und neutralisiert darin eingeschleuste Loop-Steuer-Tags sowie bare `{"action": ...}`-JSON, bevor der Prompt an das Modell geht. **Nicht abgedeckt** bleibt der parallele Simulationspfad (`run_parallel_simulation.py`, `tool_loop = None`): dort laufen Agentenaktionen über natives CAMEL-`LLMAction()` statt über diese Agora-Prompt-Assembly, eine dort fehlende Trust-Boundary wäre OASIS-intern und nicht Teil dieses Fixes. Ebenso ungeschützt sind Fallback-Runden im Single-Platform-Loop: Wirft das Modell, liefert es keine parsebare Aktion oder erschöpft `decide_action` seine Iterationen (bzw. wirft der Loop in `sim_runtime/platform_runner.py`), fällt die Runde auf natives `LLMAction()` zurück und die Observation erreicht OASIS ohne Kapselung.

## Simulationstreue und Reproduzierbarkeit

Diese beiden Bereiche sind **nicht** mit technischer Laufstabilität gleichzusetzen.

Bekannte Simulationstreue-Grenzen:

- Rollenwechsel/Role Leakage in generierten Aktionen; Referenzbefund mindestens 23 von 234 texttragenden Aktionen (~9,8 %) ([#1323](https://github.com/arn0ld87/agora/issues/1323)). Messbar ist das seit Slice 5.1 mit `backend/scripts/role_leakage_audit.py` (regelbasiert, Untergrenze; Baseline `sim_54c1c2a6a875`: 6 von 154 texttragenden Aktionen, 3,9 %, Runbook `docs/runbooks/role-leakage-audit.md`). Seit Slice 5.2 markiert der `action_log_reader` jede Aktion mit `role_conflict`, `run_state.json` zählt die Markierungen, und Aktionen mit Fremdrolle dienen im Report nicht als Stimme ihres Agents. Verworfen wird nichts; eine Schwelle gibt es bewusst nicht.
- **[#1646](https://github.com/arn0ld87/agora/issues/1646):** Fällt das BERT-Ladeprofil `auto` wegen knappem Container-RAM (< 4096 MB frei) auf fp16 zurück, steht das seit #1646 als Warnung im `simulation.log`. Vorher geschah das still, und der Lauf wirkte in der ersten Twitter-Runde hängend (~12 min pro Forward auf der CPU). Auf Supabase braucht `public.alembic_version` eine Lese-Policy für `agora_app`, sonst verweigert das Start-Gate den Start ([`rls-rollen.md`](runbooks/rls-rollen.md)).
- **[#1236](https://github.com/arn0ld87/agora/issues/1236) ist geschlossen (f006/sim-fidelity):** Der Twitter-Recommender rankte über `outputs.pooler_output` von `Twitter/twhin-bert-base` — verifiziert per Live-Load: `pooler.dense.weight`/`.bias` erscheinen im Transformers-Load-Report als `MISSING`, sind also bei jedem Prozessstart neu zufallsinitialisiert (torch-RNG, unabhängig vom Agora-eigenen `random.seed()` aus [#1160](https://github.com/arn0ld87/agora/issues/1160), Punkt F — reproduzierbare Zufallsentscheidungen im Simulationslauf). `install_recsys_mean_pooling_patch()` (`backend/scripts/_sim_common.py`) ersetzt `process_recsys_posts.process_batch` durch Mean-Pooling über `last_hidden_state` mit Attention-Maske — der Standardweg für Satz-Embeddings aus einem Encoder ohne trainierten Pooler. Das Modell lädt per Default in Eval-Modus (`model.training is False`, verifiziert), Dropout ist also inaktiv; ohne die zufälligen Pooler-Gewichte im Pfad ist der Forward bei festen Encoder-Gewichten und festem Input vollständig deterministisch, ganz ohne manuellen Seed für diesen Teil. Die zweite Zufallsquelle im Recommender-Pfad (`recsys.py::coarse_filtering` nutzt `random.sample()` oberhalb von 4000 Posts) läuft bereits über den globalen `random`-Zustand, den `seed_simulation_rng()` seedet — alle drei produktiven Einstiegspunkte (`run_twitter_simulation.py`, `run_reddit_simulation.py`, `run_parallel_simulation.py`) rufen das über die gemeinsame `SinglePlatformRunner`-Basis bzw. direkt auf. Verifiziert gegen das echte Modell: Ähnlichkeitsordnung für semantisch nahe vs. ferne Texte korrekt, zwei frisch geladene Modellinstanzen liefern für denselben Text identische Vektoren, und zwei Läufe von `rec_sys_personalized_twh` mit identischem Seed liefern dieselbe `rec`-Matrix (`backend/tests/scripts/test_bert_memory_profile.py`, `pytest -m llm`; alle drei Tests werden gegen den ungepatchten `pooler_output`-Pfad rot).

  **Präzisierung, die beim Messen sichtbar wurde:** „identische `rec`-Matrizen" allein — das zweite Akzeptanzkriterium von #1236 — ist ein **schwaches** Kriterium. Ohne den Fix kollabieren alle Nutzer- und Post-Vektoren durch die Zufallsprojektion plus sättigenden `tanh` auf nahezu dieselbe Richtung; die Matrix wird dadurch degeneriert (jeder Nutzer bekommt denselben Feed) und ist dabei *manchmal* trotzdem stabil, weil ein Beinahe-Gleichstand konstant gleich aufgelöst wird. Gemessen über zwei getrennte Prozesse: ungepatcht kippte die Matrix in einem Prozess zwischen zwei Läufen, im anderen nicht — die Nichtreproduzierbarkeit ist also real, aber nicht zuverlässig sichtbar. Der harte Diskriminator ist die **Personalisierung**: ungepatcht liefert der Pfad reproduzierbar dieselben zwei Posts für alle Nutzer, gepatcht bekommt jeder Nutzer die Posts seines eigenen Themas. Der Regressionstest prüft deshalb beides, und die Personalisierung ist der Teil, der deterministisch fehlschlägt.
- Alias-Auflösung, semantische Entitätsklassen und Chunk-Kontext für die NER laufen vor dem Persona-Cap; LLM-Koreferenz bleibt offen ([#1470](https://github.com/arn0ld87/agora/issues/1470)). Die Domänendrift-Erkennung ist für Persona-Hauptdomänen verschärft und korrigiert Drift seit dem Nachtrag zu #1471 per Regeneration statt nur den Beruf zu leeren (#1471, siehe Abschnitt „Persona-Erzeugung"); ob die Taxonomie und die Heuristik jeden realen Fall abdecken, bleibt Erfahrungswert.

Reproduzierbarkeit:

- Ein `RunManifest` existiert strukturell, ist aber noch kein vollständiger Reproduktionsanker.
- Prompt-Snapshots, Seed-Dokument-Hash/Dateiname, echte RNG-Wiring-Semantik, vollständige Replay-Parameter und einige Route-/Export-Grenzen sind in [#1274](https://github.com/arn0ld87/agora/issues/1274) offen.
- Deshalb ist die Aussage **„gleicher Seed = reproduzierbarer Agora-Run“ derzeit zu stark**. `0.10` muss kontrollierbare Inputs vollständig einfrieren und Replay-Abweichungen explizit machen (#763).

## 0.10-Blocker aus heutiger Sicht

Geschlossen sind die früheren Haupttickets #1472 (Prepare-/Report-/Graph-Build-Recovery), #1265 (Report-Parallelität an #1551 übergeben), #1236 (Twitter-Recommender), #1345 (Quantor-Evidence), #1301/#1400 (Confidence/Claim-Typen), #763 (Manifest-/Replay-Grundlage), #1224 (Observation-Gate im Single-Platform-Loop) und #1471 (Hauptdomänen-Drift). Ihre Grenzen bleiben sichtbar: #1551 behandelt später Out-of-Process-Worker und Report-Parallelität; #1274 enthält weiterhin die fehlenden Reproduzierbarkeitswerte. Die offenen Punkte #1470 (LLM-Koreferenz) und #1323 (Role Leakage) sind vor dem Feature-Freeze eingeplant.

**Vor `0.10.0-rc.1` (Feature-Freeze):** P0 #1633 (Neo4j-Backup) muss zu sein. Verhaltens-/Vertragsarbeit #1663, #1664, #1592, #1661, #1470, #1323 und Test-Isolation #1632 muss landen; ebenso Release-Gates #1670–#1673. Die auf armserver produktive PostgreSQL-Ablage ist belegt; #1592 bleibt für formale Cutover-Nachweise offen. Im Code sind die Legacy-Defaults noch aktiv.

**Bis `0.10.0` stabil:** P1 #1660 (rote Integration-CI), #1634 (Supavisor-Start), #1417 (Embedding-SSoT), #1240 (Eval-Seed-Gegenlauf), #1274 (Manifest-/Replay-Werte) und #1669 (CodeQL-High-Triage) schließen. Der erste RC erlaubt diese Fixes noch; P0/P1 im 0.10-Milestone verhindern den stabilen Tag. Security-Ausnahmen brauchen Maintainer-Freigabe und Frist ([#1666](https://github.com/arn0ld87/agora/issues/1666)).

**Im Freeze vor `1.0.0-rc.1`:** #766 weist einen Fresh-Host-Install/Restore mit vollem Supabase-Stack nach; #1662 veröffentlicht den AURORA-Referenzfall mit Single-Prompt- und Persona-Baseline (M3 aus #1603); #1674 dokumentiert Grenzen. Upgrade/Rollback stützen sich auf #1589 und den realen Cutover, ersetzen den manuellen Restore aber nicht. Der Produktvergleich ist qualitativ, nicht statistisch. Ein neuer P0/P1 während des siebentägigen Soaks verlangt Fix, neuen RC und neuen Soak ([#1653](https://github.com/arn0ld87/agora/issues/1653), [#1658](https://github.com/arn0ld87/agora/issues/1658)).

Der 1.0-Install-Pfad soll laut [#1654](https://github.com/arn0ld87/agora/issues/1654) PostgreSQL als kanonische Metadaten-Ablage und den vollen Supabase-Stack verwenden; Artefakte bleiben im Dateisystem. Code-Defaults und Fresh-Install-Nachweis sind noch nicht auf diesem Zielstand. Die volle Baseline-/Kalibrierungssuite #765 und Blob-Ablage sind nach 1.0 verschoben.

## Dokumentationspflege

- Produkt und Einstieg: [`../README.md`](../README.md) / [`../README.de.md`](../README.de.md)
- Istzustand: **diese Datei**
- Release-Reihenfolge: [`../ROADMAP.md`](../ROADMAP.md)
- Architektur-Zielbild: [`architecture.md`](architecture.md)
- API: [`api.md`](api.md) und [`api-contracts.md`](api-contracts.md)
- Konfiguration: [`configuration.md`](configuration.md)
- Betrieb: [`operator-guide.md`](operator-guide.md), [`operations.md`](operations.md), [`backup-restore.md`](backup-restore.md)
- UI: Der [visuelle Audit vom September 2026](ui/premium-redesign-2026-09/01-visual-audit.md) dokumentiert die Ausgangslage vor dem abgeschlossenen Redesign; [`ui/design-language-v4.md`](ui/design-language-v4.md) ist ein älterer Snapshot vom Mai 2026. Der aktuelle Istzustand steht oben unter „Frontend“.
- Repository-Hygiene: Ein unreferenzierter Playwright-MCP-Snapshot vom Mai 2026 ist entfernt; neue lokale Backups und Datenbank-Dumps werden ignoriert. Die bewusst versionierten Datenbanken des Referenzlaufs bleiben erhalten. Beispielkonfiguration und DNS-Overlay verwenden Platzhalter beziehungsweise eine gekennzeichnete Dokumentationsadresse statt privater Hostadressen.
- Der Observability-Slice-2-Command verweist im Markdown-Link und im Pflichtschritt auf den tatsächlich versionierten Plan unter `docs/plans/active/`.
- historische Pläne/Audits: nicht als Current-State-Quelle verwenden
- Historische Arbeits-Prompts vom Mai 2026 ohne Code- oder Workflow-Referenz sind entfernt. Der Voice-Register-Katalog unter `prompts/` bleibt, weil `backend/scripts/check_voice.py` ihn prüft.
- ADR-0010 verlinkt alle Belegstellen zu Vue-Routen und Tests auf den verifizierten Stand der ADR-Erstellung; der aktuelle Router bleibt die Tatsachenquelle.
