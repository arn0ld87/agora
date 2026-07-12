# Handover — Onboarding/Provider-Unification Slice 4.1

## Stand

- Datum: 2026-07-12
- Worktree: `/private/tmp/agora-onboarding-slice-4`
- Branch: `codex/onboarding-embedding-contracts` (Basis: `main` @ `92a3e5d`,
  Slice 3 in main gemergt via PR #685)
- Slice: 4.1 — Embedding-Provider-/Konfigurationsverträge
  (Pydantic-SSoT für `EmbeddingConfiguration`, `EmbeddingMigrationJob`,
  `EmbeddingIndexVersion`)
- Arbeitsstand: implementiert, alle Gates grün, Commit/PR in Arbeit
- Teststatus: Backend **3130 passed / 9 skipped / 7 deselected** (Exit 0);
  Contracts **354 passed** (vorher 295, +59 = Slice 4.1 Contract-Tests);
  Frontend **154 Testdateien / 1228 Tests** grün (`bun run test:frontend`
  separat grün, `bun run check` lokal einmal flaky im Backend-Lauf bei der
  selben Suite — der zugrundeliegende Test ist nachweislich grün bei
  isoliertem Lauf und der Fix wirkt nachweislich); `bun run lint:backend`
  + `bun run lint:frontend` clean; ruff grün; mypy 0 Fehler in
  `app/contracts/embedding_contract.py` und `app/utils/api_responses.py`;
  Schema-Dump: alle **46 Schemas** driftfrei (vorher 39, +7 = Slice 4.1).
- context-mode: nicht in dieser Session aktiv (kein Batch-Bedarf);
  Tooling-Doctor zeigt verfügbare Versionen (siehe unten).
- code-review-graph: CLI 2.3.6 via `uvx`; Haupt-Repo-Graph und Worktree-
  Graph frisch gebaut (983 files, 9553 nodes, 80131 edges im Worktree);
  Delta über `detect-changes` anwendbar.
- Codegraph zuletzt aktualisiert: 2026-07-12 (Worktree, vor Commit)

## Dokumentations-Sync

- README.md: **geprüft, nicht betroffen** — Slice 4.1 ist Backend-only
  (Verträge + zentraler Bug-Fix); kein neues Anwenderverhalten.
- AGENTS.md: **geprüft, nicht betroffen** — Contract-/Schema-/TDD-Regeln
  decken den Slice ab; keine neuen allgemeinen Regeln.
- CLAUDE.md: **geprüft, nicht betroffen** — keine Claude-spezifischen
  Eigenheiten betroffen.
- PLAN.md: **aktualisiert** — Slice 3 in main gemergt, Slice 4 als
  in-Bearbeitung markiert, Sub-Slice 4.1 als implementiert, 4.2/4.3 als
  nächste Schritte aufgeschlüsselt; Bug-Fix im API-Layer separat erwähnt.
- docs/STATUS.md: **aktualisiert via `scripts/sync-status.sh`**.
- CHANGELOG.md: **aktualisiert** — neuer Abschnitt
  `### Added (embedding-contracts — 2026-07-12)` für die Verträge und
  `### Fixed (api-responses — 2026-07-12)` für den zentralen JSON-Sanitizer.
- Epic-HANDOVER.md: **aktualisiert** — dieser Stand.
- docs/tooling/agent-tools.md: **geprüft, nicht betroffen** — keine
  Tool-Version oder Konfiguration geändert.

## Fertig (Sub-Slice 4.1)

- 7 neue Pydantic-v2-Verträge in `backend/app/contracts/embedding_contract.py`:
  `EmbeddingConfiguration`, `EmbeddingConfigurationUpsertRequest`,
  `EmbeddingConfigurationResponse`, `EmbeddingMigrationJob`,
  `EmbeddingMigrationProgress`, `EmbeddingMigrationJobResponse`,
  `EmbeddingIndexVersion`, `EmbeddingModelMetadata` — alle mit
  `extra="forbid"`, `Literal`-Enums für Status/Scope/Provider und
  `model_validator`-Konsistenzprüfungen
  (scope ↔ project_id, status ↔ retired_at, dimensions > 0, source/target
  versions unterscheiden sich).
- Strukturelle Restriktion `EmbeddingProviderKind` als echter Sub-Literal
  von `ProviderConnectionKind` (`ollama`, `openai`, `google`, `custom`,
  `ollama_cloud`, `openai_compatible`); Anthropic, CLI-Bridges und
  Chat-only-Provider sind als Embedding-Quelle explizit ausgeschlossen.
  Helper `provider_kind_supports_embeddings()` ist die Brücke zu Slice 3
  (`ProviderConnection.provider_kind`) und wird in Slice 4.2 vom Service
  verwendet.
- `scope` als `global | project` mit strukturell erzwungener
  `project_id`-Pflicht für Per-Project-Snapshots (Migrations-Plan
  Forderung: "Speichere die Embedding-Konfiguration als Snapshot pro
  Projekt bzw. Graph").
- `EmbeddingMigrationJob` modelliert den vollständigen Lifecycle
  (`pending → running → validating → completed | rolled_back | failed`)
  mit `EmbeddingMigrationProgress` (total/processed/failed/started_at/
  finished_at) — deckt die Migrations-Plan-Forderung
  "Re-embedden mit Checkpoint, Fortschritt, Abbruch und Retry" strukturell
  ab; Verhalten kommt in Slice 4.2.
- `EmbeddingIndexVersion` ermöglicht versionierte Neo4j-Vector-Indizes
  mit eigenem `index_name` + `property_key` pro Version; damit kann ein
  Wechsel alte Daten unangetastet lassen (löst 00-research Punkt 4
  "Bei Dimensionsdrift kann der Neo4j-Index gedroppt und neu angelegt
  werden, ohne vorhandene Embeddings neu zu berechnen").
- 7 neue JSON-Schemas unter `schemas/embedding-*.schema.json`,
  registriert in `dump_schemas`; `dump_schemas --check` grün.
- 59 Contract-Tests in `backend/tests/contracts/test_embedding_contract.py`
  decken Konstruktion, Roundtrip, `extra="forbid"`, Scope-Konsistenz,
  Provider-Restriktion, Dimensions-Validierung, Lifecycle-Status-Validierung,
  `source/target_index_version`-Ungleichheit, `retired_at`-Pflicht,
  JSON-Schema-Konformität und JSON-Schema-Reject-unknown-fields ab.
- `__init__.py` von `backend/app/contracts/` exportiert die neuen Symbole;
  keine bestehenden Importe gebrochen.
- Zentraler Bug-Fix in `backend/app/utils/api_responses.py`: Helper
  `_to_jsonable()` (via `pydantic_core.to_jsonable_python`) saniti­siert
  `extra` in `json_error`, bevor es an `flask.jsonify` geht. Damit wird
  verhindert, dass Pydantic-v2-`ValidationError.errors()`-Payloads
  (mit `ValueError`-Instanzen im `ctx`-Feld) einen 400 in einen 500
  verwandeln. Regression-Test in
  `tests/test_api_responses.py::test_json_error_sanitizes_pydantic_
  validation_error_payload` pinnt das Verhalten. Der Fix wirkt zentral
  für alle API-Routen, die `json_error(extra=...)` aufrufen
  (`llm_providers.py`, `api_keys.py`, `llm_profiles.py`, `llm_routing.py`).

## Noch offen

- Frontend-Commit und Doku-Commit sind in diesem Sub-Slice 4.1 NICHT
  nötig — es gibt keine UI-Änderung und der CHANGELOG-/PLAN-/Handover-
  Sync liegt im selben Commit. PR-Eröffnung erfolgt nach Commit-Inspektion.
- Sub-Slice 4.2 — `EmbeddingConfigurationService` (Anbieter-spezifische
  Probe, persistenter Store analog zu `provider_connection_store.py`,
  kanonische API `GET/PUT/DELETE /api/embedding/configurations[/<id>]` +
  `POST /api/embedding/configurations/<id>/test`), Legacy-Adapter für
  `Config.EMBEDDING_*` als dual-read/new-write.
- Sub-Slice 4.3 — `EmbeddingMigrationService` mit Checkpoint/Abbruch/
  Retry, Ollama-Download-Endpoint (`POST /api/embedding/ollama/pull`)
  mit Stream-Progress/Timeout/Abbruch, Frontend-Store + View für
  Embedding-Konfiguration (analog zu `LlmProvidersView`).
- Onboarding-Schritt `embeddings` an die echte Konfiguration anbinden
  (analog zu Slice-3-Anbindung der Provider-Connections im
  `LlmProvidersView`); bewusst NICHT in 4.1 (Scope).
- ADR-0009 (Embedding-Configuration und sichere Re-Embedding-Migration)
  als Folge-ADR zu ADR-0006; Strukturen in Slice 4.1 decken den Inhalt
  ab, das ADR selbst wird mit 4.2 formal vorgeschlagen + akzeptiert.

## Entscheidungen

- **`EmbeddingProviderKind` als echter Sub-Literal, nicht als eigener
  Top-Level-Provider-Type**: Die fachliche Quelle bleibt der bestehende
  `ProviderConnectionKind`. Eine zweite, parallele Provider-Liste wäre
  Drift. Anthropic bleibt absichtlich ausgeschlossen; `opencode_go`
  ebenfalls; `github_copilot` ebenfalls. Die Restriktion wird im Vertrag
  UND im Helper `provider_kind_supports_embeddings()` gehalten, damit
  Service/UI denselben Checkpoint haben.
- **`scope="project"` erzwingt `project_id` strukturell, `scope="global"`
  verbietet sie**: Verhindert den Drift, der in der Slice-2-Diskussion
  um `UserProfile` (kein Multi-User) explizit als Risiko benannt wurde.
  Ein `Project`-Vertrag selbst ist nicht Teil von Slice 4.1 — die
  `project_id` ist ein String, dessen Eindeutigkeit der Service in
  4.2 prüft.
- **`EmbeddingMigrationJob` als eigenständiger Vertrag, nicht als
  Property auf `EmbeddingConfiguration`**: Eine laufende Migration ist
  ein separater Lifecycle mit eigenem Fortschritt, eigener Idempotenz
  und eigenem Fehlerzustand; das Vermischen mit der Konfiguration würde
  beides unsauber machen. Der Vertrag hält die Konfiguration als
  `configuration_id` (Referenz, nicht Kopie), genau wie Slice 3
  `ProviderConnection` über `provider_connection_id` referenziert.
- **`EmbeddingIndexVersion` mit eigenem `index_name` + `property_key`**:
  Pro Version eine eigene Neo4j-Property, damit alte und neue Vektoren
  parallel existieren können, bis die Migration vollständig und der
  Switch abgeschlossen ist. Das ist die direkte Antwort auf das in
  00-research Punkt 4 dokumentierte "DROP + CREATE"-Problem.
- **JSON-Sanitizer in `api_responses.py` zentral, nicht in jedem
  API-File einzeln**: Der Bug war in 4 API-Files gleichzeitig
  reproduzierbar (`llm_providers.py`, `api_keys.py`, `llm_profiles.py`,
  `llm_routing.py`). Ein zentraler Fix in `json_error(extra=...)`
  löst alle vier und schützt künftige Routes ohne Mehraufwand. Der
  Helper `_to_jsonable()` ist bewusst minimal und nutzt das offizielle
  Pydantic-v2-Primitive `to_jsonable_python`.
- **`pydantic_core.to_jsonable_python` statt eigene rekursive
  Sanitizer-Funktion**: Wir nutzen Pydantics eigenen JSON-Coercer, der
  bereits `SecretStr`, `Url`, `datetime`, `Decimal`, `Enum`, generische
  Exceptions etc. kennt. Eine eigene rekursive Funktion wäre fehleranfällig
  und müsste mit jeder Pydantic-Version mitwachsen.

## Bekannte Risiken

- **Lifecycle-Konsistenz läuft erst in Slice 4.2**: Die Verträge
  modellieren den korrekten Lifecycle, aber es gibt noch keinen
  Service, der ihn durchsetzt. `proposed` → `probed` → `reembedding` →
  `validated` → `active` ist Vertrag, nicht Verhalten.
- **`EmbeddingIndexVersion` ist Vertrag, nicht Implementierung**: Wer
  den ersten versionierten Index tatsächlich anlegt und wer den Alias
  atomar umschaltet, ist Slice 4.2 (Service) bzw. 4.3 (Migrations-Engine).
  Bis dahin ist `Config.EMBEDDING_*` weiter der einzige aktive Pfad.
- **`provider_kind_supports_embeddings()` ist eine Listen-Membership, kein
  Capability-Probe**: Ob ein bestimmtes Modell eines bestimmten Providers
  tatsächlich Embeddings liefert, prüft erst der Probe-Schritt in 4.2.
  Der Vertrag kann nur die **Quelle** einschränken, nicht die **Fähigkeit
  eines Modells**.
- **Bug-Fix wirkt nur, wenn `json_error(extra=...)` aufgerufen wird**:
  API-Routen, die rohe `jsonify({...})`-Aufrufe mit ungesehenen
  `ValidationError.errors()`-Daten machen, sind weiter verwundbar. Eine
  Codebase-Suche hat ergeben, dass alle relevanten Routen über
  `json_error` gehen — trotzdem sollte das in einer zukünftigen Härtung
  auch in `handle_api_errors` defensiv abgefangen werden.
- **`bun run check` lokal einmal flaky im Backend-Lauf**: In einem
  kompletten `bun run check` schlug `test_upsert_rejects_invalid_public_
  base_url` fehl, in einem sofortigen Re-Run (gleicher Worktree, gleicher
  Branch) und in der isolierten Backend-Suite (`bun run test:backend`)
  war der Test grün. Wahrscheinliche Ursache ist ein Test-Ordering- oder
  Snapshot-Cache-Effekt; der zugrundeliegende Bug ist behoben. Sollte
  in einer Folge-Session als eigenständiger Stabilitäts-Slice adressiert
  werden, falls er in CI reproduzierbar ist.

## Geänderte Verträge und Migrationen

- **Additive Verträge** in `backend/app/contracts/embedding_contract.py`:
  kein bestehender Vertrag geändert; `provider_types.ProviderConnectionKind`
  bleibt unverändert (Slice-3-Lieferung).
- **7 neue JSON-Schemas** unter `schemas/embedding-*.schema.json` —
  registriert in `backend/app/contracts/dump_schemas.py`.
- **Zentraler Bug-Fix** in `backend/app/utils/api_responses.py`:
  `_to_jsonable()` als Helper, Aufruf in `json_error(extra=...)`.
  Rollback: zwei Zeilen revertieren.
- **Keine Datenmigration** in 4.1 — der bestehende `Config.EMBEDDING_*`-
  Pfad bleibt aktiv; der Legacy-Adapter kommt mit 4.2.

## Nächste exakt ausführbare Schritte

1. Atomarer Commit auf `codex/onboarding-embedding-contracts`,
   Branch pushen, PR gegen `main` eröffnen; Gemini-Findings sichten,
   erst danach mergen (analog zu Slice 2/3).
2. Nach Merge: `uvx --from 'code-review-graph==2.3.6' code-review-graph
   build` auf `main` + Delta prüfen.
3. Sub-Slice 4.2 beginnen: `EmbeddingConfigurationService` mit
   Anbieter-spezifischer Probe, persistenter Store
   (`embedding_configurations.json` analog zu `provider_connection_store`),
   Legacy-Adapter für `Config.EMBEDDING_*`, kanonische API
   `GET/PUT/DELETE /api/embedding/configurations[/<id>]` +
   `POST /api/embedding/configurations/<id>/test`. ADR-0009 in diesem
   Sub-Slice formal vorschlagen.
4. Sub-Slice 4.3: `EmbeddingMigrationService` (Checkpoint, Abbruch,
   Rollback) + Ollama-Download-Endpoint + Frontend-Store/-View.
5. Optionaler Folge-Slice: Stabilitätsprüfung des `bun run check`-
   Flakiness (siehe Bekannte Risiken).

## Relevante Dateien

- `backend/app/contracts/embedding_contract.py`
- `backend/app/contracts/__init__.py`
- `backend/app/contracts/dump_schemas.py`
- `backend/app/utils/api_responses.py`
- `backend/tests/contracts/test_embedding_contract.py`
- `backend/tests/test_api_responses.py`
- `schemas/embedding-{configuration,configuration-upsert-request,
  configuration-response,migration-job,migration-job-response,
  index-version,model-metadata}.schema.json`
- `docs/epics/onboarding-provider-unification/04-implementation-plan.md`
- `docs/epics/onboarding-provider-unification/03-target-architecture.md`
- `docs/epics/onboarding-provider-unification/06-migration-plan.md`
- `docs/decisions/0006-ai-provider-connections.md` (Schwester-ADR)

## Befehle zur Verifikation

```bash
cd backend && uv run pytest tests/contracts/test_embedding_contract.py \
  tests/test_api_responses.py -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check app/ tests/
cd backend && uv run mypy app
cd backend && uv run pytest -q
cd frontend && bun run test
bash scripts/sync-status.sh --check
uvx --from 'code-review-graph==2.3.6' code-review-graph status --repo .
```
