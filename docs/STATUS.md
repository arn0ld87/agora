# Agora — Status

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Produktversion:** `0.9.5` Stability Beta

Diese Datei ist die **Single Source of Truth für den verifizierten Istzustand**. Strategische Release-Ziele stehen in [`ROADMAP.md`](../ROADMAP.md), konkrete Arbeitspakete und Akzeptanzkriterien in [GitHub Issues](https://github.com/arn0ld87/agora/issues), ausgelieferte Änderungen in [`changelog.d/`](../changelog.d/README.md). Historische Audits, Pläne und Referenzläufe behalten ihren damaligen Stand und sind keine aktuelle Steuerungsquelle.

## Kurzurteil

Agora besitzt eine vollständige Single-User-Pipeline von Dokumentaufnahme und Knowledge Graph über Persona-Erzeugung und OASIS/CAMEL-Simulation bis zu evidenzorientiertem Report, Vergleich und Export. Die Stabilisierung der 0.9.x-Linie hat insbesondere Contracts, Run-Lifecycle, Crash-/Restart-Verhalten, Budgetdurchsetzung, Installationspfade und Evidence-Persistenz deutlich gehärtet.

`0.9.5` ist trotzdem **keine 1.0-Freigabe**. Die größten verbleibenden Release-Risiken liegen heute nicht mehr in der grundsätzlichen Web-App-Funktionalität, sondern in Job-Recovery außerhalb der OASIS-Simulation, Embedding-Konfigurations-SSoT, vollständiger Reproduzierbarkeit, Simulationstreue und externer Produktvalidierung.

## Versionsstatus

`VERSION` ist die Produkt-SSoT. Komponentenmanifeste werden dagegen geprüft.

<!-- BEGIN_AUTOGEN_VERSIONS -->
| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 0.9.5 |
| Frontend | `frontend/package.json` | 0.9.5 |
| Root | `package.json` | 0.9.5 |
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
- Echte Integrationstests unter `backend/tests/integration/` laufen gegen Redis und Neo4j. Der CI-Job setzt `AGORA_TEST_REQUIRE_SERVICES=1`, damit ein fehlender Dienst nicht als freundlicher Skip durchrutscht (#1481).

## Produktive Architektur

### Frontend

- Vue 3 / TypeScript / Vite / Pinia.
- Die v4-Routen sind die einzige produktive Oberfläche; historische Parallel-Views sind entfernt oder Redirects.
- Pydantic-Verträge werden im Frontend durch Zod-Spiegel und eingecheckte JSON-Schemas abgesichert.
- Das Premium-Redesign ist abgeschlossen; die Nachlese #1459 hat Radius-Tokens, Titel-Truncation, i18n und strukturierte Statusfehler bereinigt.

### Backend

- Flask Application Factory, Pydantic v2, Python 3.14, `uv`.
- Neo4j ist Knowledge-Graph-/Vektor-Persistenz; Redis dient Events, Live-Status und Teilen der IPC-/Ticket-Infrastruktur.
- Produktions-Gunicorn bleibt bewusst bei **einem Worker**. Prozesslokale Run-/Monitor-Zustände machen `workers > 1` weiterhin unsicher; das ist kein Performance-Tuning-Schalter.
- OASIS/CAMEL läuft für Simulationen in separaten Subprozessen.

### LLM-Routing

Kanonische Begriffe und Pfade:

- Provider-Matrix: `backend/app/services/llm_provider_registry.py`
- Provider-Detection/Adapter: `backend/app/llm/providers/registry.py`
- Verbindung: `ProviderConnection`
- Modellreferenz/Routing: `AiModelRef`, `AiRoute`, `LlmRoute`
- strukturierte Calls: `LLMClient.chat_json`
- Modellauswahl: `AiModelPicker.vue`

Unterstützte Transportklassen sind `http`, `local` und `cli`. `codex_cli` ist ein echter CLI-/Session-Transport ohne HTTP-Base-URL und API-Key; der Fix für den früheren Persona-Route-Mix mit `.env` ist gemergt (#1418/#1422), ebenso der Codex-CLI-Transport für OASIS-Simulationsrunden (#1423/#1424).

## Run- und Simulations-Lifecycle

Die 0.9.5-Stabilisierung hat mehrere vorher stille Zustandsfehler geschlossen:

- Nutzer-Stop endet als `stopped` mit `termination_reason="user_stop"` statt als scheinbarer Fehler (#1474).
- Force-Restarts tragen Generation-Tokens; veraltete Monitor-Threads dürfen keine Zustände oder Ressourcen des neuen Prozesses überschreiben (#1474).
- Beim Start werden stale `pending`/`processing`/`paused` Simulation-Runs gegen die persistierte PID reconciled. Tote Prozesse werden als `failed/process_restart` markiert; `COMPLETED`/`STOPPED` werden ohne beweisbare Run-ID-Zuordnung nicht geraten (#1476).
- Gunicorn führt die Reconciliation auch in `post_fork` aus, damit Worker-Replacements unter `preload_app=True` erfasst werden (#1476).
- Starts derselben `simulation_id` sind serialisiert; ein frisches PID-loses `STARTING` erhält eine 30-s-Grace-Period (#1476).
- Compose setzt für den Agora-Service `init: true` und `stop_grace_period: 45s`.

### Bekannte Lifecycle-Grenze

Prepare-, Report- und Graph-Build-Jobs laufen weiterhin als daemonisierte Threads im Webprozess. Ein SIGTERM kann diese Jobs beenden, ohne einen vollständig persistierten `interrupted`-/Resume-Zustand zu erzeugen. Das ist in [#1472](https://github.com/arn0ld87/agora/issues/1472) offen und ein 0.10-Release-Thema. Der Redis-Event-Bus ist **keine persistente Jobqueue**.

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

Bekannt offen: `detect_domain_drift` kann Drift übersehen, sobald Quell- und Persona-Domänen irgendeine Schnittmenge besitzen ([#1471](https://github.com/arn0ld87/agora/issues/1471)).

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

### Weiter offene Trust-Themen

- Quantifizierte Aussagen können noch Evidence referenzieren, die den Quantor nicht trägt ([#1345](https://github.com/arn0ld87/agora/issues/1345)).
- Evaluation-Seeds können erwartete Antworten enthalten, die später als vermeintliche Simulationserkenntnis wiedergefunden werden ([#1240](https://github.com/arn0ld87/agora/issues/1240)).
- Claim-Typisierung und Confidence-Kalibrierung sind noch nicht vollständig abgeschlossen (#1301/#1400).

## Run-Budgets

Preflight, Zeit-, Token-, Kosten- und LLM-Aufrufbudgets sind produktiv. Seit #1478 werden auch Tool-Calls, Vision und Interview-Pfade pro physischem Provider-Aufruf geprüft und im Ledger erfasst; harte Budgetabbrüche werden bis zum Runstatus propagiert.

**Bekannte Grenze:** Der Default-Parallelrunner `scripts/run_parallel_simulation.py` besitzt eine eigene `ParallelIPCHandler`-Implementierung ohne vollständige `SubprocessBudgetGuard`-Anbindung. Dieser Pfad ist ausdrücklich **nicht** als vollständig budget-accounted zu behandeln, bis der Follow-up-Slice geschlossen ist.

## Embeddings

Chat-Routing und Embedding-Konfiguration sind absichtlich getrennt. Die persistente Embedding-Konfiguration lebt im `EmbeddingConfigurationStore`, Migrationen besitzen einen eigenen Lifecycle.

**Offener SSoT-Bruch:** Der produktive Runtime-Pfad kann weiterhin `Config.EMBEDDING_*` aus der Umgebung verwenden, obwohl in der UI eine andere aktive Embedding-Konfiguration gewählt wurde. Bei zwei Modellen gleicher Dimension schützt der Dimensionswächter nicht vor einem semantisch inkompatiblen Vektorraum. Siehe [#1417](https://github.com/arn0ld87/agora/issues/1417). Bis zur Behebung gilt die UI-Aktivierung **nicht** als Beweis dafür, dass jeder Runtime-Consumer dieselbe Konfiguration nutzt.

## Installation und Betrieb

- `install.sh` erzeugt `.env` aus der Vorlage und ersetzt bekannte Platzhalter durch sichere Werte.
- Host- und Docker-Modus erzeugen `SECRET_KEY`, `AGORA_AUTH_TOKEN`, `AGORA_SECRET_KEY` und `AGORA_FERNET_KEY`; die Zufallsquelle fällt von `python3` auf `openssl` bzw. `/dev/urandom` zurück (#1483).
- `NEO4J_PASSWORD` für eine externe/individuelle Neo4j-Instanz bleibt Operator-Konfiguration.
- Reports liegen unter `backend/uploads/reports/`, nicht unter `backend/reports/` (#1483).
- Prod bindet Backend standardmäßig an Loopback und nutzt einen read-only Root-Filesystem-Ansatz mit expliziten Write-Pfaden.

Backup/Restore ist dokumentiert, aber der 0.10-Abnahmepunkt verlangt weiterhin einen **nachgewiesenen Fresh-Host-Restore-, Upgrade- und Rollback-Smoke** ([#766](https://github.com/arn0ld87/agora/issues/766)). Dokumentation ist kein Restore-Test, auch wenn Menschen seit Jahrzehnten tapfer so tun.

## Security

Aktueller Schwerpunkt:

- API-Token/API-Key-Scope-Modell und signierte Tickets.
- Secrets-at-rest für Provider-Keys; keine Klartext-Provider-Keys in Reports/Run-Manifests.
- strukturierte `/api/status`-Fehler statt roher Exception-Strings (#1459).
- Dependency-Risk-Register mit Hardstops; NLTK/PYSEC-2026-597 bleibt bis zur Upstream-Klärung verfolgt (#661, Hardstop 28.09.2026).

Bekannt offen: Simulation-`observation` wird noch nicht überall so strikt als untrusted Prompt-Input getrennt, wie für Prompt-Injection-Härtung gewünscht ([#1224](https://github.com/arn0ld87/agora/issues/1224)).

## Simulationstreue und Reproduzierbarkeit

Diese beiden Bereiche sind **nicht** mit technischer Laufstabilität gleichzusetzen.

Bekannte Simulationstreue-Grenzen:

- Rollenwechsel/Role Leakage in generierten Aktionen; Referenzbefund mindestens 23 von 234 texttragenden Aktionen (~9,8 %) ([#1323](https://github.com/arn0ld87/agora/issues/1323)).
- Twitter-Recommender nutzt in OASIS einen problematischen `twhin-bert`-Pooler mit nicht trainierten/neu initialisierten Gewichten; dadurch sind Rankingqualität und Cross-Run-Reproduzierbarkeit fragwürdig ([#1236](https://github.com/arn0ld87/agora/issues/1236)).
- Persona-Domänendrift und Alias-/Koreferenzprobleme (#1471/#1470).

Reproduzierbarkeit:

- Ein `RunManifest` existiert strukturell, ist aber noch kein vollständiger Reproduktionsanker.
- Prompt-Snapshots, Seed-Dokument-Hash/Dateiname, echte RNG-Wiring-Semantik, vollständige Replay-Parameter und einige Route-/Export-Grenzen sind in [#1274](https://github.com/arn0ld87/agora/issues/1274) offen.
- Deshalb ist die Aussage **„gleicher Seed = reproduzierbarer Agora-Run“ derzeit zu stark**. `0.10` muss kontrollierbare Inputs vollständig einfrieren und Replay-Abweichungen explizit machen (#763).

## 0.10-Blocker aus heutiger Sicht

Priorität vor neuen Features:

1. #1472 — langlebige Prepare-/Report-/Graph-Jobs restart-/interrupt-sicher machen.
2. #1417 — Embedding-Runtime auf eine kanonische aktive Konfiguration führen.
3. #1470/#1471 — Entitätsauflösung und Persona-Domänenkohärenz.
4. #1236/#1323 — Recommender- und Rollen-Konsistenz der Simulation.
5. #1345/#1240 — Quantoren/Evidence und Eval-Leakage.
6. #763/#1274 — echtes Manifest und Replay.
7. #766 — Backup/Restore/Upgrade/Rollback nachweisen.
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
