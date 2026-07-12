# Handover — Onboarding/Provider-Unification Slice 4.2

## Stand

- Datum: 2026-07-12
- Worktree: `/private/tmp/agora-onboarding-slice-4-2`
- Branch: `codex/onboarding-embedding-service` (Basis: `main` @ `f3fd310`,
  Slice 4.1 in main gemergt via PR #686 + #687)
- Slice: 4.2 — Embedding-Configuration-Service + API + Legacy-Adapter
  (Slice 4.1 = Verträge ist gemergt; Slice 4.3 = Migrations-Engine +
  Ollama-Download + Frontend folgt)
- Arbeitsstand: implementiert, alle Gates grün, Commit/PR in Arbeit
- Teststatus: Backend **3182 passed / 9 skipped / 7 deselected** (Exit 0);
  Contracts 363 passed (unverändert); Frontend 154 Testdateien / 1228 Tests
  grün (`bun run test:frontend` separat grün); `bun run lint:backend` +
  `bun run lint:frontend` clean; ruff grün; mypy 0 Fehler; Schema-Dump
  `--check` grün für 46 Schemas (kein Vertrags-Drift).
- context-mode: nicht in dieser Session aktiv (kein Batch-Bedarf);
  Tooling-Doctor zeigt verfügbare Versionen.
- code-review-graph: CLI 2.3.6 via `uvx`; Worktree-Graph frisch gebaut
  (Codegraph auf main bereits in PR #686-Sitzung aktualisiert, hier
  nicht erneut nötig).
- Codegraph zuletzt aktualisiert: 2026-07-12 (Slice 4.1, Worktree)

## Dokumentations-Sync

- README.md: **geprüft, nicht betroffen** — Slice 4.2 ist Backend-only
  (Service + API + Store); kein neues Anwenderverhalten.
- AGENTS.md: **geprüft, nicht betroffen** — Contract-/Schema-/TDD-Regeln
  decken den Slice ab; keine neuen allgemeinen Regeln.
- CLAUDE.md: **geprüft, nicht betroffen**.
- PLAN.md: **aktualisiert** — Slice 4.1 als gemergt markiert,
  Slice 4.2 als implementiert, 4.3 als offen.
- docs/STATUS.md: **aktualisiert via `scripts/sync-status.sh`**
  (Backend-Test-Count 3144 → 3182, +38 aus Slice 4.2).
- CHANGELOG.md: **aktualisiert** — neuer Abschnitt
  `### Added (embedding-service — 2026-07-12)` + ADR-0007-Accepted.
- docs/decisions/0007-embedding-configuration-and-index-migration.md:
  **aktualisiert** — Status von Proposed auf Accepted, mit
  konkreter Umsetzungs-Referenz auf Slice 4.1+4.2.
- Epic-HANDOVER.md: **aktualisiert** — dieser Stand.
- docs/tooling/agent-tools.md: **geprüft, nicht betroffen**.

## Fertig (Sub-Slice 4.2)

- **Persistenter Store** (`backend/app/services/embedding_configuration_store.py`):
  atomarer File-basierter Store mit `flock`-Prozesssperre, `os.replace`-
  basiertem atomarem Write, Modus 0600, getrennten Dateien
  (`embedding_configurations.json` + `embedding_index_versions.json`).
  Methoden: `list_configurations(scope=...)`, `get_configuration`,
  `get_active_global_configuration`, `upsert_configuration`,
  `update_configuration_status`, `delete_configuration`,
  `list_index_versions`, `get_index_version`, `get_active_index_version`,
  `next_index_version`, `upsert_index_version`, `supersede_index_version`.
- **Anbieter-spezifische Probe-Adapter** (`adapters.py`):
  `_OllamaAdapter` (lokal + Cloud, gemeinsam), `_OpenAICompatibleAdapter`
  (OpenAI + Custom), `_GeminiAdapter`. Jeder Adapter macht ein
  Test-Embedding, liefert `EmbeddingProbeResult(status, status_message,
  actual_dimensions)`. Registry über `adapter_for_provider(kind)`.
- **Service** (`service.py`): orchestriert Probe, Lifecycle, Legacy-Sync.
  Probe übersetzt Adapter-Status auf Konfigurations-Status
  (`available → probed`, alles andere → `failed`). Dimensions-Mismatch
  zwischen deklarierter und tatsächlicher Dimension führt zu
  `status="failed"` mit beschreibendem `status_message`. Lifecycle-
  Wechsel: `activate()` setzt eine Konfiguration auf `active` und
  markiert vorherige aktive Konfigurationen desselben Scopes als
  `rolled_back`. `rollback()` ist explizite Operator-Aktion.
  `sync_legacy()` materialisiert `Config.EMBEDDING_*` als
  nicht-persistente Konfiguration — no-op, wenn bereits eine aktive
  globale Konfiguration existiert.
- **Legacy-Adapter** (`legacy.py`): `build_legacy_view()`,
  `legacy_view_to_configuration()`, `legacy_view_to_provider_connection()`.
  Heuristik: Loopback/ollama.com → Ollama, alles mit Key → OpenAI,
  ohne Key → custom. Kein stilles Schreiben in den Store (kein
  Startup-Repair).
- **API-Routen** (`backend/app/api/embedding_configurations.py`):
  - `GET  /api/llm/embedding/configurations[?scope=...]`
  - `GET  /api/llm/embedding/configurations/active`
  - `GET  /api/llm/embedding/configurations/<id>`
  - `PUT  /api/llm/embedding/configurations/<id>` (id="new" = anlegen)
  - `DELETE /api/llm/embedding/configurations/<id>`
  - `POST /api/llm/embedding/configurations/<id>/test`
  - `POST /api/llm/embedding/configurations/<id>/activate`
- **43 neue Tests**:
  - 13 × Store (`test_embedding_configuration_store.py`)
  - 9 × Service (`test_service.py`)
  - 7 × Legacy (`test_legacy.py`)
  - 14 × API (`test_embedding_configurations_api.py`)
- **ADR-0007 von Proposed auf Accepted gehoben** (Slice 4.1+4.2 setzen
  die in der ADR geforderten Garantien strukturell um; Migrations-Engine
  und Ollama-Download kommen mit 4.3).

## Noch offen

- **Sub-Slice 4.3**: `EmbeddingMigrationService` mit Checkpoint/Abbruch/
  Retry, Ollama-Download-Endpoint (`POST /api/embedding/ollama/pull`) mit
  Stream-Progress/Timeout/Abbruch, Frontend-Store + View für
  Embedding-Konfiguration (analog zu `LlmProvidersView`). Onboarding-
  Schritt `embeddings` an die echte Konfiguration anbinden.
- **Frontend-Commit** (analog zu Slice 3: separater Commit im selben PR
  oder Folge-PR; hier kein Frontend-Code, daher bewusst entkoppelt).
- **Optionaler Maintenance**: `scripts/pre-push-gate.sh` als
  hartes Pre-Push-Gate (dump_schemas + sync-status + schema-drift-check).
  Aus den Erfahrungen mit dem CI-Fail aus PR #687 vorgeschlagen.

## Entscheidungen

- **Konfigurationen und Index-Versionen in getrennten Dateien**:
  Konfigurations-Updates (häufig, nach jedem Probe) berühren den
  Index-Katalog (selten, bei Migration) nicht. Beide Dateien teilen
  denselben Data-Dir und dieselbe Lock-Konvention.
- **Index-Versionsnummern monoton steigend ab 1** (kein zufälliger
  Salt), damit Neo4j-Indexnamen `entity_embedding_vN` lesbar bleiben
  und die Versionsnummer in Logs/UI sprechend ist.
- **Dimensions-Mismatch = failed, nicht probed**: Wenn der
  Test-Embedding-Endpoint eine andere als die deklarierte Dimension
  liefert, ist die Konfiguration nicht verifizierbar. `probed` darf
  nur gesetzt werden, wenn Probe + Dimension übereinstimmen.
- **`sync_legacy()` ist explizit no-op bei aktiver Konfiguration**:
  Der Legacy-Pfad darf eine vom Operator aktiv gepflegte Konfiguration
  niemals überschreiben. Die `Config.EMBEDDING_*`-Werte bleiben
  unangetastet, bis der Operator explizit auf den kanonischen Pfad
  migriert (Slice 4.3-Folgescope).
- **`active` ist eindeutig pro Scope**: `activate()` rollt alle
  anderen `active` Konfigurationen desselben Scopes auf
  `rolled_back` zurück. Das verhindert zwei gleichzeitige `active`
  Konfigurationen, die das Routing verwirren würden.
- **Provider-Connection wird beim PUT geprüft**: Wenn die
  `provider_connection_id` nicht existiert, antwortet die API mit
  404 — kein Anlegen einer Embedding-Konfiguration, die auf eine
  nicht-existente Verbindung verweist. Verbindung muss explizit
  über Slice 3 angelegt werden.

## Bekannte Risiken

- **`LegacyEmbeddingView.provider_connection_id="legacy-embedding"`**
  ist ein feststehender String; eine echte `ProviderConnection` mit
  derselben ID würde den Probe-Pfad verwirren. Der Service
  stellt sicher, dass die Legacy-Connection **nicht** im
  `ProviderConnectionStore` liegt (sonst gibt es einen Konflikt).
  Getestet ist das Verhalten **nicht** explizit; falls ein
  Operator eine reale `ProviderConnection` namens `legacy-embedding`
  anlegt, schlägt der Legacy-Probe fehl. Mitigation in 4.3:
  Operatoren bekommen einen Hinweis beim Anlegen, dass diese ID
  reserviert ist.
- **Probe ohne Retry**: ein flackernder Endpoint führt zu
  `failed`; der Operator muss den Probe manuell wiederholen.
  Retry-Logik ist bewusst nicht hier, sondern gehört in eine
  optionale Watchdog-Komponente (offen für 4.3 oder später).
- **Dimension-Probe ohne Cache**: jeder Probe-Request kostet einen
  HTTP-Call. Für hochfrequente Probe-Workflows in 4.3 ist ein
  In-Memory-Cache sinnvoll, mit TTL.
- **Kein Pre-Push-Gate-Script**: das ist aus den Erfahrungen mit
  PR #687 (Schema-Drift, STATUS-Drift) die richtige Lehre, aber
  nicht in diesem Slice umgesetzt. Vorschlag: separater kleiner
  PR mit `scripts/pre-push-gate.sh`.

## Geänderte Verträge und Migrationen

- **Keine Vertragsänderungen** — die Verträge aus Slice 4.1 sind
  unverändert geblieben; Service + API + Store nutzen sie nur.
- **ADR-0007** von Proposed auf Accepted (Umsetzungs-Referenz
  hinzugefügt, kein inhaltlicher Wandel).
- **Keine Datenmigration** — `embedding_configurations.json` und
  `embedding_index_versions.json` werden lazy angelegt, wenn der
  erste Schreibvorgang erfolgt. Vorher (ohne Slice 4.2) gab es
  diese Dateien nicht; der Migrations-Bedarf ist null.
- **Legacy-Werte** (`Config.EMBEDDING_*`) bleiben unangetastet.

## Nächste exakt ausführbare Schritte

1. Atomarer Commit auf `codex/onboarding-embedding-service`, Branch
   pushen, PR gegen `main` eröffnen; Gemini-Findings sichten, erst
   danach mergen.
2. Nach Merge: `uvx --from 'code-review-graph==2.3.6' code-review-graph
   build` auf `main` + Delta prüfen.
3. Sub-Slice 4.3: `EmbeddingMigrationService` (Checkpoint/Abbruch/
   Rollback) + Ollama-Download-Endpoint + Frontend-Store/-View.
4. Optional: separater kleiner PR mit `scripts/pre-push-gate.sh`,
   der `dump_schemas` + `sync-status.sh --check` + Schema-Drift-Check
   als hartes Gate vor `git push` erzwingt.

## Relevante Dateien

- `backend/app/services/embedding_configuration_store.py`
- `backend/app/services/embedding_configurations/__init__.py`
- `backend/app/services/embedding_configurations/adapters.py`
- `backend/app/services/embedding_configurations/service.py`
- `backend/app/services/embedding_configurations/legacy.py`
- `backend/app/api/embedding_configurations.py`
- `backend/app/api/__init__.py` (Import-Update)
- `backend/tests/services/test_embedding_configuration_store.py`
- `backend/tests/services/embedding_configurations/test_service.py`
- `backend/tests/services/embedding_configurations/test_legacy.py`
- `backend/tests/api/test_embedding_configurations_api.py`
- `docs/decisions/0007-embedding-configuration-and-index-migration.md`
  (Status Accepted)
- `docs/epics/onboarding-provider-unification/04-implementation-plan.md`

## Befehle zur Verifikation

```bash
cd backend && uv run pytest tests/services/test_embedding_configuration_store.py \
  tests/services/embedding_configurations/ \
  tests/api/test_embedding_configurations_api.py -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check app/ tests/
cd backend && uv run mypy app
cd backend && uv run pytest -q
cd frontend && bun run test
bash scripts/sync-status.sh --check
uvx --from 'code-review-graph==2.3.6' code-review-graph status --repo .
```
