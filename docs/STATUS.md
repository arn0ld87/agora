# Agora — Status

**Stand:** 20.09.2026  
**Geprüfte Main-Baseline:** `b62aea62`  
**Produktversion:** `0.9.6` (Zwischenrelease, Stability Beta)

Diese Datei ist die **Single Source of Truth für den verifizierten Istzustand**. Strategische Release-Ziele stehen in [`ROADMAP.md`](../ROADMAP.md), konkrete Arbeitspakete und Akzeptanzkriterien in [GitHub Issues](https://github.com/arn0ld87/agora/issues), ausgelieferte Änderungen in [`changelog.d/`](../changelog.d/README.md). Historische Audits, Pläne und Referenzläufe behalten ihren damaligen Stand und sind keine aktuelle Steuerungsquelle.

## Kurzurteil

Agora besitzt eine vollständige Single-User-Pipeline von Dokumentaufnahme und Knowledge Graph über Persona-Erzeugung und OASIS/CAMEL-Simulation bis zu evidenzorientiertem Report, Vergleich und Export. Die Stabilisierung der 0.9.x-Linie hat insbesondere Contracts, Run-Lifecycle, Crash-/Restart-Verhalten, Budgetdurchsetzung, Installationspfade und Evidence-Persistenz deutlich gehärtet.

Die `0.9.x`-Linie ist trotzdem **keine 1.0-Freigabe**. Die größten verbleibenden Release-Risiken liegen heute nicht mehr in der grundsätzlichen Web-App-Funktionalität, sondern in Job-Recovery außerhalb der OASIS-Simulation, Embedding-Konfigurations-SSoT, vollständiger Reproduzierbarkeit, Simulationstreue und externer Produktvalidierung.

**`0.9.6`-Linie (20.09.2026, über 330 Commits/184 Changelog-Fragmente seit `v0.9.5`):** ein Zwischenrelease, ausdrücklich **kein** `0.10.0` und ohne dessen Release-Gates. Neu dazugekommen sind vier LLM-Provider (inklusive `codex_cli` und `claude_cli` als CLI-/Session-Transporte sowie Amazon Bedrock), eine PostgreSQL-Schicht parallel zu den bestehenden JSON-/SQLite-Stores (gebaut, per Default nicht aktiv), ein zehnteiliges UI-Redesign, ein atomar geschriebenes Run-Manifest mit Replay-Grundlage sowie weitere Evidence-/Budget-/Restart-Härtung. Die fünf oben genannten Release-Risiken sind dadurch **teilweise**, nicht vollständig bearbeitet — Details je Punkt in [`docs/agents/release-priority.md`](agents/release-priority.md) und im Abschnitt „0.10-Blocker aus heutiger Sicht" unten.

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
- Die v4-Routen sind die einzige produktive Oberfläche; historische Parallel-Views sind entfernt oder Redirects.
- Pydantic-Verträge werden im Frontend durch Zod-Spiegel und eingecheckte JSON-Schemas abgesichert. **Der Spiegel ist nicht lückenlos**: das Gate `zod-mirror-drift` führt die vorhandenen Vertragstests aus, es erzwingt aber nicht, dass es zu einem Backend-Vertrag überhaupt einen Spiegel gibt. Wo einer fehlt und stattdessen ein handgeschriebenes Interface mit `[key: string]: unknown` steht, ist Drift unsichtbar — genau so zeigte das Projektregal jahrelang die rohe `project_id` statt des Namens (`useShelf` las `project_name`, das Backend liefert `name`). Projekte haben seitdem einen Spiegel (`contracts/projectContract.ts`, `.strict()`).
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

Drei Grenzen, damit daraus keine falsche Zusage wird: Die Terminalisierung passiert **nicht** im Signal-Handler, sondern beim Interpreter-Shutdown — wird der Worker nach Ablauf von `graceful_timeout` per SIGKILL beendet, greift weiterhin nur die Startup-Reconciliation (die dieselbe Checkpoint-Prüfung nutzt). Der Prepare-Checkpoint deckt nur die parallele Hauptgenerierung ab, nicht die sequenzielle Reject-Backfill-Nachbesetzung danach — wird der Prozess mitten in der Backfill-Phase beendet, generiert ein Resume die offenen Slots erneut. Und eine Heartbeat-/Lease-Mechanik, die einen verwaisten In-Process-Job zuverlässig von einem noch laufenden unterscheidet, existiert weiterhin nicht (Slice 1.5, #1472d, offen); #1472 als Ganzes bleibt offen. Der Redis-Event-Bus ist **keine persistente Jobqueue**.

Report-Generierungen sind seit Slice 1.2 (#1265) je Simulation **serialisiert**: ein zweiter Start wird mit `409 report_generate_in_progress` abgewiesen, solange ein Run mit `run_type=report_generate` in `pending` oder `processing` steht. Das ist eine bewusste Verhaltensänderung gegenüber 0.9.5 und eine Einschränkung für parallele Nutzung, keine Optimierung. Reportarbeit in einen eigenen Prozess zu verschieben bleibt 1.0-Vorarbeit.

## Graph und Ingestion

- Episode- und `RELATION`-Writes sind gegen Retry-after-commit idempotent (`MERGE` auf stabiler UUID), damit ein verlorenes Neo4j-ACK nicht zu Constraint-Fehlern oder stillen Dubletten führt (#1460).
- Dokument-/Chunk-Provenance wird durch die Ingestion- und Evidence-Pfade getragen (ADR-0013).
- Persona-Kandidaten werden vor teuren LLM-Gates typbasiert gefiltert; zusammengesetzte Nicht-Personen-Typen werden über Kopfnomen-Suffixe erkannt (#1473).

Offen bleiben Qualitätsthemen der Entitätsauflösung: Alias-/Koreferenzauflösung und kontrollierte semantische Entitätsklassen vor dem Persona-Cap ([#1470](https://github.com/arn0ld87/agora/issues/1470)).

## Persona-Erzeugung

- Der geroutete Provider erreicht die Persona-Generierung; CLI-Transporte fallen bei fehlender Base-URL nicht mehr auf fremde `.env`-HTTP-Werte zurück (#1418/#1422).
- Vollständiger regelbasierter Persona-Fallback ist blockierend; ein Lauf mit 20/20 Platzhalter-Personas wird nicht als normaler Erfolg weitergereicht.
- Ablehnungen werden nicht mehr als „erfolgreich generiert“ protokolliert; die Bilanz zählt Kandidaten, Ablehnungen und erzeugte Personas konsistent (#1455).
- Das harte LLM-Aufrufbudget reserviert laufende Calls pro Run und greift auch bei paralleler Persona-Generierung; `BudgetExceededError` wird nicht in Fallback-Personas verschluckt (#1461).

`detect_domain_drift` vergleicht seit [#1471](https://github.com/arn0ld87/agora/issues/1471) die Hauptdomäne der Persona (das Fach mit den meisten exakten Markertreffern) gegen die Quelldomänen, statt jede Schnittmenge als Entwarnung zu werten; ein Overlap nur in einer Nebendomäne oder ein Gleichstand ohne eindeutigen Sieger gilt als Drift. Eine Quelle ohne erkennbares Fach liefert `unverifiable=True` statt einer stillen Entwarnung. Die Taxonomie liegt in `backend/app/services/persona_domain_taxonomy.py` und deckt jetzt elf Domänen ab (zusätzlich `it/security`, `public-sector`, `retail`, `media`, `legal`, `energy`).

## Report, Evidence und Contracts

### Statuswahrheit

- Contract-invalid Reports dürfen nicht als normal `completed` ausgeliefert werden.
- Teilberichte aus Cancel-, Section-Failure- oder Fallback-Outline-Pfaden werden als `INCOMPLETE` klassifiziert; Resume bewahrt die Degradationsmarker und kann einen temporären Fallback-Outline neu planen (#1479).
- Ein `INCOMPLETE`-Report kann weiterhin auslieferbar sein; der tatsächliche Reportstatus steht in der Run-Metadaten-Sicht.

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

### Weiter offene Trust-Themen

- Quantifizierte Aussagen können noch Evidence referenzieren, die den Quantor nicht trägt ([#1345](https://github.com/arn0ld87/agora/issues/1345)).
- Die **Gewinnung** von Evidence aus dem Seed bleibt LLM-seitig: Zerlegt die Graph-Ingestion einen gebündelten Seed-Satz zu einem Teilfakt, fehlen die übrigen Angaben im Pool. #1492 hat die Prüfseite deterministisch repariert, nicht die Extraktion davor.
- Evaluation-Seeds können erwartete Antworten enthalten, die später als vermeintliche Simulationserkenntnis wiedergefunden werden ([#1240](https://github.com/arn0ld87/agora/issues/1240)).
- Claim-Typisierung und Confidence-Kalibrierung sind noch nicht vollständig abgeschlossen (#1301/#1400).

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

**#766 bleibt offen.** Das ist das Werkzeug, nicht der Nachweis: der Abnahmepunkt verlangt einen **durchgeführten** Fresh-Host-Restore-, Upgrade- und Rollback-Smoke mit echtem Backup. Ein Dry-Run-Protokoll ist keiner — das Skript schreibt diesen Satz selbst hinein. Durchführung: [`runbooks/restore-drill.md`](runbooks/restore-drill.md). Dokumentation ist kein Restore-Test, auch wenn Menschen seit Jahrzehnten tapfer so tun.

### Supabase: Infrastruktur vorhanden, ungenutzt

Unter [`supabase/`](../supabase/README.md) liegt ein **eigenes** Compose-Projekt mit self-hosted Supabase (PostgreSQL 17, Supavisor, GoTrue, PostgREST, Storage, postgres-meta, Studio, Envoy-Gateway). Realtime, Edge Runtime, imgproxy und Analytics laufen bewusst nicht mit.

Das ist Phase 1 des Migrationsplans [`plans/supabase.md`](plans/supabase.md) §7 und **ausschließlich Infrastruktur**: im Backend existiert kein PostgreSQL-Code, keine Abhängigkeit, kein Feature-Flag. Der Agora-Stack startet und läuft unverändert ohne diesen Stack; die Kopplung ans gemeinsame Docker-Netz `agora-backend` ist ein zusätzliches Overlay ([`deploy/compose/docker-compose.supabase.yml`](../deploy/compose/docker-compose.supabase.yml)), nie die Basis-`docker-compose.yml`.

Daraus folgt ausdrücklich **nicht**, dass Agora Postgres nutzt, dass Multi-User näher rückt oder dass Auth sich geändert hat. `AGORA_AUTH_TOKEN` und das API-Key-Scope-Modell sind unverändert die Auth-Wahrheit; GoTrue läuft mit `DISABLE_SIGNUP=true` mit und wird von nichts aufgerufen.

Die Supabase-Konfigurationsdateien (DB-Init-SQL, Envoy-Routing, Supavisor-Config) liegen nicht im Repository. `supabase/bootstrap.sh` holt sie von einem gepinnten supabase/supabase-Commit nach `supabase/volumes/` (gitignored) — ohne diesen Lauf startet der Stack nicht.

### PostgreSQL-Grundlage: installiert, im Default ungenutzt

`sqlalchemy`, `psycopg[binary]` und `alembic` sind Backend-Abhängigkeiten. Der zentrale Adapter liegt in `backend/app/infrastructure/postgres/` (`Database.session()` als einziger vorgesehener Weg zu einer Verbindung), Alembic unter `backend/migrations/` mit zwei Migrationen: die erste legt das Fachschema `agora` an, die zweite die Tabelle `agora.llm_profiles`.

Wirksam wird davon im Default nichts: `AGORA_METADATA_BACKEND=legacy` ist gesetzt, und solange er gilt, wird keine Verbindung aufgebaut. `DATABASE_URL` hat bewusst keinen Default; `Config.validate()` lehnt `AGORA_METADATA_BACKEND=postgres` ohne URL, einen unbekannten Backend-Wert und ein `postgresql://`-Schema (psycopg2 ist nicht installiert) beim Start ab.

Ab hier gilt die Regel aus Phase 2 des Plans: **das Datenbankschema wird ausschließlich über versionierte Migrationen geändert.** Kein `CREATE TABLE IF NOT EXISTS` in fachlichen Stores.

Für den Nachweis, dass eine Migration nichts verliert, existiert `backend/scripts/migration_baseline.py`: es erhebt je Objektklasse Anzahl, IDs, Zeitstempel, Statuswerte und Referenzen plus eine Prüfsumme je Artefaktdatei und vergleicht zwei solche Manifeste (Runbook: [`runbooks/migration-baseline.md`](runbooks/migration-baseline.md)). Erhoben wurde damit bisher nur der Ist-Stand; **kein Vorher/Nachher-Vergleich über eine echte Migrationsphase liegt vor**, weil noch keine gelaufen ist.

Die erste Fachtabelle existiert als Definition: `agora.llm_profiles` (SQLAlchemy-Modell `LlmProfileModel` plus Migration) hält LLM-Profil-Metadaten — Name, Provider, Basis-URL, Modellname, ein partieller Unique-Index, der höchstens ein Default-Profil erlaubt. Provider-Secrets bleiben im Fernet-Store, Workspace- und Auth-Spalten sind bewusst nicht vorgezogen. Solange `AGORA_METADATA_BACKEND=legacy` gilt, liest und schreibt die Tabelle niemand — das ist Phase 4.

Für die LLM-Profile existiert seit PR 3 ein Port (`app/repositories/llm_profile_repository.py`) mit genau einem Adapter: `SqliteLlmProfileRepository`, die umbenannte bisherige Klasse auf derselben `instance/llm_profiles.db`. `AGORA_LLM_PROFILE_BACKEND` schaltet die Ablage getrennt von `AGORA_METADATA_BACKEND` und steht im Default auf `sqlite`. Seit PR 4 existiert mit `PostgresLlmProfileRepository` ein zweiter Adapter: Metadaten aus `agora.llm_profiles`, Schlüssel aus dem Fernet-Store, IDs weiterhin als 32-Zeichen-`hex`, damit gespeicherte `profile:<id>`-Referenzen weiter zeigen. `backend/scripts/migrate_llm_profiles_to_postgres.py` überträgt den Bestand und lässt die SQLite unberührt; Ablauf und Rückweg stehen in [`runbooks/llm-profile-postgres-umstellung.md`](runbooks/llm-profile-postgres-umstellung.md).

**Umgeschaltet ist nichts.** Der Default bleibt `sqlite`, und in dieser Installation ist keine Migration gelaufen. Der Adapter ist gegen eine echte PostgreSQL-Instanz verifiziert (16 Integrationstests), nicht gegen einen produktiven Bestand.

Dazu gehört ein zweiter Baustein: `LlmProfileSecretsStore` (`app/services/llm_profile_secrets_store.py`) legt die API-Keys **pro Profil** Fernet-verschlüsselt unter `AGORA_DATA_DIR` ab, weil `agora.llm_profiles` bewusst keine `api_key`-Spalte hat und der bestehende Provider-Secret-Store pro **Provider** ablegt — zwei Profile desselben Providers dürfen aber verschiedene Schlüssel tragen. `backend/scripts/migrate_profile_secrets.py` füllt den Store aus der SQLite (read-only, `--verify` vergleicht feldweise). **Kein Lesepfad nutzt ihn bisher**: die SQLite bleibt die Wahrheit, der Store ist die Ablage, die PR 4 vorfinden wird.

### Projektmetadaten: Vertrag, Port und zwei Adapter — umgeschaltet ist nichts

Projekte hatten bis hierher keinen Vertrag: `Project` war eine Dataclass in `backend/app/models/project.py`, deren `to_dict()` über `GET /project/<id>`, `GET /project/list` und `POST /project/<id>/reset` ausgeliefert wird — eine Dataclass auf einer API-Grenze, was contracts-first ausschließt. Seit PR 6 liegt der Vertrag in `app/contracts/project_contract.py` (`project.schema.json`, `project-list-response.schema.json`), und `app/models/project.py` reicht `Project` und `ProjectStatus` nur noch weiter.

Daneben existiert ein Port `ProjectRepository` (`app/repositories/project_repository.py`) mit genau einem Adapter, `FileProjectRepository` (`app/services/file_project_store.py`) — die bisherige Dateilogik, umbenannt, nicht neu geschrieben. `ProjectManager` bleibt als Fassade stehen und delegiert seine fünf Metadatenmethoden dorthin; die sechs Artefaktmethoden (`files/`, `extracted_text.txt`, Dokument-Manifest) bleiben unverändert dateibasiert und wandern in keiner Phase des Plans in eine Datenbank. Keine der 52 Aufrufstellen in 13 Modulen wurde angefasst, und keine der 39 Testdateien mit Projektbezug musste angepasst werden.

Seit dem zweiten Teil von PR 6 gibt es den zweiten Adapter: `PostgresProjectRepository` (`app/infrastructure/postgres/repositories/project_repository.py`) auf der Tabelle `agora.projects` (Revision `7a3c1e84f209`). Der Spaltenschnitt ist Kern plus Nutzlast — `id`, `name`, `status`, `graph_id`, `llm_profile_id`, `created_at`, `updated_at` als Spalten, alle übrigen Vertragsfelder in `payload jsonb`. Die Aufteilung wird aus `Project.to_dict()` **abgeleitet**, nicht gepflegt: ein künftiges Vertragsfeld landet damit automatisch in der Nutzlast, statt beim Schreiben still verlorenzugehen. `backend/scripts/migrate_projects_to_postgres.py` überträgt den Dateibestand, lässt das Dateisystem unberührt und vergleicht mit `--verify` feldweise; Ablauf und Rückweg stehen in [`runbooks/projekt-postgres-umstellung.md`](runbooks/projekt-postgres-umstellung.md).

**Umgeschaltet ist nichts.** `AGORA_PROJECT_BACKEND` schaltet die Ablage getrennt von `AGORA_METADATA_BACKEND` und `AGORA_LLM_PROFILE_BACKEND` und steht im Default auf `file`; in dieser Installation ist keine Migration gelaufen. `Config.validate()` lehnt `postgres` ohne gesetzte `DATABASE_URL` beim Start ab. Der Adapter ist gegen eine echte PostgreSQL-17-Instanz verifiziert (17 Integrationstests, darunter ein Roundtrip über alle Vertragsfelder), nicht gegen einen produktiven Bestand.

Drei Festlegungen des Schemas: `project_id` behält sein Format `proj_<12 Hexstellen>` und wird **keine** `uuid`, weil es der Verzeichnisname unter `uploads/projects/` ist — die Kennung erzeugt seitdem der Port, damit beide Adapter dieselbe Form liefern. `created_at`/`updated_at` sind `text` und nicht `timestamptz`, weil der Vertrag ISO-Zeichenketten führt und ein Umweg über `timestamptz` beim Lesen eine andere Zeichenkette ergäbe. Und `workspace_id` kommt nicht vor, weil Multi-User eine eigene, freizugebende Phase ist.

### psycopg unter gevent: geprüft, kooperativ

Bis PR 4 stand hier als offener Punkt, psycopg 3 sei im Synchronmodus nicht gevent-kooperativ, während der Webprozess unter einem gunicorn-Worker mit gevent-Worker-Klasse läuft. **Die Annahme war falsch, und sie ist jetzt gemessen statt vermutet.** Acht gleichzeitige `SELECT pg_sleep(1)` in acht Greenlets brauchen 1,08 s direkt über psycopg und 1,04 s über `build_engine()`; seriell wären es acht. Die Gegenprobe ohne `gevent.monkey.patch_all()` braucht 8,19 s — der Unterschied liegt um eine Größenordnung auseinander, nicht im Messrauschen. Bei gepatchtem `select` wählt psycopg die Wartefunktion auf Python-Ebene; das ist die von psycopg ab 3.1.14 dokumentierte gevent-Unterstützung, `psycogreen` entfällt. Der Mindest-Pin liegt mit `>=3.2.0` darüber.

Bedingung dafür ist die Importreihenfolge: `gevent.monkey.patch_all()` muss vor dem ersten psycopg-Import laufen. Das ist keine neue Auflage, sondern dieselbe, die seit [#529](https://github.com/arn0ld87/agora/issues/529) `requests`/`ssl` schützt — `backend/wsgi.py` patcht als erstes Statement, das `Dockerfile` startet `wsgi:app`. Festgehalten wird das durch `backend/tests/integration/test_gevent_psycopg_cooperation.py`, nicht durch diese Notiz. Begründung und Grenzen: [ADR-0014](decisions/0014-psycopg-under-gevent-worker.md).

Ungeprüft bleibt das Verhalten hinter Supavisor unter Last. Der HARDSTOP `--workers 1` bleibt aus den in `backend/gunicorn.conf.py` genannten Gründen unberührt.

## Security

Aktueller Schwerpunkt:

- API-Token/API-Key-Scope-Modell und signierte Tickets.
- Secrets-at-rest für Provider-Keys; keine Klartext-Provider-Keys in Reports/Run-Manifests.
- strukturierte `/api/status`-Fehler statt roher Exception-Strings (#1459).
- Dependency-Risk-Register mit Hardstops; NLTK/PYSEC-2026-597 bleibt bis zur Upstream-Klärung verfolgt (#661, Hardstop 28.09.2026).
- Outbound-Fetches mit agenten-/modellgelieferten URLs laufen zentral über `backend/app/security/outbound_http.py` (Adressklassen, Redirect-Revalidierung, IP-Pinning, Byte-Limit). Der zuvor ungeschützte Pfad `scripts/agent_tools.py::web_fetch` ist damit geschlossen ([#1485](https://github.com/arn0ld87/agora/issues/1485)).
- Statische Security-Scans in CI: CodeQL für Python, JS/TS und GitHub-Actions-Workflows (Injection in `run:`-Blöcken), Ruff mit flake8-bandit-Regeln (`S`, Baseline-Ignores für S101/S110/S112/S311/S603/S607 in `backend/pyproject.toml`), Trivy für das Container-Image (blockierend ab HIGH) und für Dockerfile/Compose-Konfiguration (Kategorie `trivy-config`, vorerst nur berichtend).
- Eine Ablehnung durch dieselbe Policy gibt die untrusted URL nicht mehr weiter: `OutboundRequestBlocked` trägt in der Message nur den Grund und in `.url` nur die sichere Herkunft (Schema, Host, ggf. Port). Die frühere Userinfo-Redaktion ließ Token in Query, Fragment und Pfad stehen.

Bekannt offen: Simulation-`observation` wird noch nicht überall so strikt als untrusted Prompt-Input getrennt, wie für Prompt-Injection-Härtung gewünscht ([#1224](https://github.com/arn0ld87/agora/issues/1224)).

## Simulationstreue und Reproduzierbarkeit

Diese beiden Bereiche sind **nicht** mit technischer Laufstabilität gleichzusetzen.

Bekannte Simulationstreue-Grenzen:

- Rollenwechsel/Role Leakage in generierten Aktionen; Referenzbefund mindestens 23 von 234 texttragenden Aktionen (~9,8 %) ([#1323](https://github.com/arn0ld87/agora/issues/1323)).
- **[#1236](https://github.com/arn0ld87/agora/issues/1236) ist geschlossen (f006/sim-fidelity):** Der Twitter-Recommender rankte über `outputs.pooler_output` von `Twitter/twhin-bert-base` — verifiziert per Live-Load: `pooler.dense.weight`/`.bias` erscheinen im Transformers-Load-Report als `MISSING`, sind also bei jedem Prozessstart neu zufallsinitialisiert (torch-RNG, unabhängig vom Agora-eigenen `random.seed()` aus [#1160](https://github.com/arn0ld87/agora/issues/1160), Punkt F — reproduzierbare Zufallsentscheidungen im Simulationslauf). `install_recsys_mean_pooling_patch()` (`backend/scripts/_sim_common.py`) ersetzt `process_recsys_posts.process_batch` durch Mean-Pooling über `last_hidden_state` mit Attention-Maske — der Standardweg für Satz-Embeddings aus einem Encoder ohne trainierten Pooler. Das Modell lädt per Default in Eval-Modus (`model.training is False`, verifiziert), Dropout ist also inaktiv; ohne die zufälligen Pooler-Gewichte im Pfad ist der Forward bei festen Encoder-Gewichten und festem Input vollständig deterministisch, ganz ohne manuellen Seed für diesen Teil. Die zweite Zufallsquelle im Recommender-Pfad (`recsys.py::coarse_filtering` nutzt `random.sample()` oberhalb von 4000 Posts) läuft bereits über den globalen `random`-Zustand, den `seed_simulation_rng()` seedet — alle drei produktiven Einstiegspunkte (`run_twitter_simulation.py`, `run_reddit_simulation.py`, `run_parallel_simulation.py`) rufen das über die gemeinsame `SinglePlatformRunner`-Basis bzw. direkt auf. Verifiziert gegen das echte Modell: Ähnlichkeitsordnung für semantisch nahe vs. ferne Texte korrekt, zwei frisch geladene Modellinstanzen liefern für denselben Text identische Vektoren (`backend/tests/scripts/test_bert_memory_profile.py`, `pytest -m llm`).
- Alias-/Koreferenzprobleme der Entitätsauflösung bleiben offen ([#1470](https://github.com/arn0ld87/agora/issues/1470)). Die Domänendrift-Erkennung selbst wurde für Persona-Hauptdomänen verschärft (#1471, siehe Abschnitt „Persona-Erzeugung"); ob die Taxonomie und die Heuristik jeden realen Fall abdecken, bleibt Erfahrungswert.

Reproduzierbarkeit:

- Ein `RunManifest` existiert strukturell, ist aber noch kein vollständiger Reproduktionsanker.
- Prompt-Snapshots, Seed-Dokument-Hash/Dateiname, echte RNG-Wiring-Semantik, vollständige Replay-Parameter und einige Route-/Export-Grenzen sind in [#1274](https://github.com/arn0ld87/agora/issues/1274) offen.
- Deshalb ist die Aussage **„gleicher Seed = reproduzierbarer Agora-Run“ derzeit zu stark**. `0.10` muss kontrollierbare Inputs vollständig einfrieren und Replay-Abweichungen explizit machen (#763).

## 0.10-Blocker aus heutiger Sicht

Priorität vor neuen Features:

1. #1472 — **Teil erledigt.** Ein per SIGTERM abgeschnittener Prepare-/Report-/Graph-Build-Job wird beim nächsten Start als verwaist erkannt und auf `failed`/`process_restart` korrigiert, statt für immer auf `processing` zu stehen; die Liveness kommt aus der Prozess-Identität im Manifest (`app/jobs/identity.py`). Für **Graph-Build** gibt es seit Slice 1.3 (#1472b) zusätzlich einen echten Wiederaufnahme-Pfad: ein je Projekt persistierter Chunk-Checkpoint lässt `POST /api/runs/<id>/resume` nur die fehlenden Chunks nachholen statt neu zu beginnen. **Offen bleibt die Wiederaufnahme für Prepare und Report** (Slice 1.4/#1472c u. a.): `_BACKEND` ist weiterhin `"thread"`, es gibt keine persistente Queue und keinen wiederaufnehmbaren Zwischenstand. Eine Queue, die einen nicht-idempotenten Schritt erneut ausführt, verdoppelt Artefakte statt sie zu retten — idempotente Schritte kommen zuerst.
2. #1417 — **Teil erledigt.** Der Laufzeitpfad folgt der aktiven Store-Konfiguration statt ausschließlich der `.env`, eine Konfiguration, die nicht zum Inhalt des aktiven Index passt, wirft, seit Slice 2.1 lösen Reads und Writes ihre Index- und Property-Namen über den Store auf statt über Literale, und seit Slice 2.2 schaltet der Migrationsservice erst nach erfolgreicher Index-Prüfung gegen Neo4j atomar auf die neue Version um — ein laufender oder fehlgeschlagener Re-Embedding-Lauf schaltet den Betrieb nicht mehr vorzeitig um. **Offen bleiben** die `VECTOR_DIM`-SSoT (Slice 2.3), eine Legacy-View für Bestandsgraphen (Slice 2.4) und der Frontend-Zod-Spiegel für den neuen `building`-Status; ein Modellwechsel über die Oberfläche ist weiterhin nicht möglich — siehe Abschnitt „Embeddings".
3. #1470 — Entitätsauflösung (Alias-/Koreferenzauflösung), weiterhin offen. #1471 (Persona-Domänenkohärenz) ist mit Slice 4.1 auf einen Hauptdomänen-Vergleich statt Any-Overlap umgestellt.
4. #1236/#1323 — Recommender- und Rollen-Konsistenz der Simulation.
5. #1345/#1240 — Quantoren/Evidence und Eval-Leakage.
6. #763/#1274 — echtes Manifest und Replay.
7. #766 — Backup/Restore/Upgrade/Rollback nachweisen. Werkzeug und Runbook stehen; der Durchgang auf einem frischen Host fehlt.
8. #765 — Agora gegen einfachere LLM-/Persona-Baselines und reale Referenzen evaluieren.

Nicht priorisiert vor 1.0: Multi-User, Kubernetes/Helm, Federation, allgemeines Plugin-System oder ein weiterer großer Frontend-Rewrite.

## Dokumentationspflege

- Produkt und Einstieg: [`../README.md`](../README.md) / [`../README.de.md`](../README.de.md)
- Istzustand: **diese Datei**
- Release-Reihenfolge: [`../ROADMAP.md`](../ROADMAP.md)
- Architektur-Zielbild: [`architecture.md`](architecture.md)
- API: [`api.md`](api.md) und [`api-contracts.md`](api-contracts.md)
- Konfiguration: [`configuration.md`](configuration.md)
- Betrieb: [`operator-guide.md`](operator-guide.md), [`operations.md`](operations.md), [`backup-restore.md`](backup-restore.md)
- historische Pläne/Audits: nicht als Current-State-Quelle verwenden
