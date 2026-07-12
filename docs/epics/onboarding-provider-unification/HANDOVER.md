# Handover — Onboarding/Provider-Unification Slice 4.3.1

## Stand

- Datum: 2026-07-12
- Worktree: `/private/tmp/agora-onboarding-slice-4-3`
- Branch: `codex/onboarding-embedding-migration` (Basis: `main` @
  `bcc50ba`, PR #688 mit Slice 4.2 in main gemergt)
- Slice: 4.3.1 — Migrations-Service + Ollama-Download (Backend)
  (Frontend-Store + View + Onboarding-Anbindung kommt als
  Sub-Slice 4.3.2 in einer Folge-Session)
- Arbeitsstand: implementiert, alle Gates grün, Commit/PR in Arbeit
- Teststatus: Backend **3222 passed / 9 skipped / 7 deselected** (Exit 0);
  Contracts 363 passed (unverändert); Frontend 154 Testdateien / 1228
  Tests grün; ruff grün; mypy 0 Fehler; Schema-Dump `--check` grün für
  46 Schemas (kein struktureller Vertrags-Drift; nur ein neuer
  Sentinel-Wert in `EmbeddingMigrationJob`).
- context-mode: nicht in dieser Session aktiv.
- code-review-graph: CLI 2.3.6 via `uvx`; Worktree-Graph frisch
  gebaut.

## Dokumentations-Sync

- README.md: **geprüft, nicht betroffen** — Backend-only.
- AGENTS.md: **geprüft, nicht betroffen** — keine neuen allgemeinen
  Regeln.
- CLAUDE.md: **geprüft, nicht betroffen**.
- PLAN.md: **aktualisiert** — Slice 4.1/4.2 als gemergt markiert,
  Slice 4.3 in 4.3.1 (Backend, implementiert) + 4.3.2 (Frontend,
  offen) aufgeteilt.
- docs/STATUS.md: **aktualisiert via `scripts/sync-status.sh`**
  (Backend-Test-Count 3187 → 3222, +35).
- CHANGELOG.md: **aktualisiert** — neuer Abschnitt
  `### Added (embedding-migration — 2026-07-12)`.
- docs/decisions/0007: **keine Aenderung** — ADR-Status bleibt
  Accepted (Slice 4.3 setzt die in der ADR geforderten Garantien
  strukturell um; der Re-Embedding-Loop selbst kommt mit Neo4j-
  Anbindung in einem Folge-Slice).
- Epic-HANDOVER.md: **aktualisiert** — dieser Stand.
- docs/tooling/agent-tools.md: **geprüft, nicht betroffen**.

## Fertig (Sub-Slice 4.3.1, Backend)

- **`EmbeddingMigrationService`**
  (`backend/app/services/embedding_migration.py`):
  vollstaendiger Lifecycle mit Statusuebergaengen
  `pending → running → validating → completed | rolled_back | failed`,
  atomarer Switch nach erfolgreicher Validierung, idempotenter
  `start()` (doppelter Job fuer dieselbe Konfiguration wirft
  `ValueError`), explizites `cancel()` setzt auf `rolled_back` statt
  `failed` (Operator-Entscheidung), `ReEmbedder`-Protocol fuer
  injizierbaren Re-Embedding-Loop (Tests ohne Neo4j), No-Op-Default-
  Re-Embedder, Job-Persistenz als flache JSON-Dateien unter
  `AGORA_DATA_DIR/embedding_migration_<job_id>.json`.
- **`OllamaPullService`**
  (`backend/app/services/embedding_ollama_pull.py`): laedt ein
  Embedding-Modell von `POST {base_url}/api/pull` (NDJSON-Stream)
  und liefert einen strukturierten `OllamaPullReport`. Sicherheit:
  strikte Model-Name-Validierung (ASCII a-z, A-Z, 0-9, '-', '_',
  '.', ':', 1-100 Zeichen — schliesst Shell-Injection aus), keine
  Shell-Aufrufe (immer strukturierte JSON-Requests via
  `requests.post`), Loopback/Ollama-Cloud-Einschraenkung, 10-Minuten-
  Default-Timeout, 60-Sekunden-Stream-Read-Timeout,
  `resolve_ollama_base_url()`-Helper mit Loopback/Ollama-Cloud-
  Filterung.
- **Migrations-API** unter `/api/llm/embedding/migrations`:
  - `POST /` startet eine neue Migration
  - `GET /` listet alle Jobs (optional `?configuration_id=...`)
  - `GET /<job_id>` liefert einen einzelnen Job
  - `POST /<job_id>/run` zieht den Lifecycle durch
  - `POST /<job_id>/cancel` bricht ab
- **Ollama-Download-API** unter `/api/llm/embedding/ollama/pull`:
  synchroner Endpoint mit strukturiertem JSON-Report, kein
  Server-Sent-Event-Stream (UI-Setup-Wizard braucht das Ergebnis
  atomar). 502 `upstream_error` bei Ollama-Fehlern, 404 bei
  unbekannter Connection, 400 bei ungueltigem Model.
- **`EmbeddingMigrationJob`-Vertrag erweitert**:
  `source_index_version=0` ist jetzt der Cold-Start-Sentinel fuer
  Migrationen ohne Quell-Index. Vertrag stellt sicher, dass
  `source=0` nur mit `target=1` kombiniert wird und `source < target`
  immer gilt (sonst `ValueError`).
- **35 neue Tests**:
  - 12 × Migrations-Service (Start, Run, Cancel, Validation,
    Lifecycle, Idempotenz)
  - 23 × Ollama-Download (Model-Name-Validierung 6+10 parametrisiert,
    Base-URL-Validierung, Stream-Parsing, Auth-Fehler, Bearer-Header,
    Empty-Stream-Handling, Default-Timeout-Konfiguration)

## Noch offen (Sub-Slice 4.3.2, Frontend)

- **Frontend-Store** fuer Embedding-Konfigurationen (Pinia, analog
  zu `LlmProvidersView` / `providerConnections.ts`)
- **Frontend-View** mit Status-Badges, Probe-Button, Activate-Button,
  Migrations-Progress-Anzeige, Ollama-Download-Wizard
- **Zod-Spiegel** der Embedding-Verträge (analog zu
  `aiProviderContract.ts`)
- **Onboarding-Schritt `embeddings` an die echte Konfiguration
  anbinden** (analog zur Slice-3-Anbindung der Provider-Connections
  im `LlmProvidersView`)
- **Echte Neo4j-Re-Embedding-Engine**: konkrete `ReEmbedder`-
  Implementierung, die betroffene Knoten liest, neue Embeddings mit
  dem konfigurierten Provider erzeugt und in die neue Property
  schreibt. Aktuell ist die Re-Embedding-Schleife ein No-Op-Stub;
  der Slice-4.3-Service garantiert das Lifecycle, der Slice-4.3.2
  Service liefert die echte Daten-Mutation.

## Entscheidungen

- **Re-Embedder als Protocol injizierbar**: Tests laufen ohne Neo4j
  und ohne echte Embedding-Backends. Die echte Implementierung
  kommt mit Neo4j-Anbindung in einer Folge-Session; der Service
  bleibt davon unberuehrt.
- **`source_index_version=0` als Cold-Start-Sentinel**: die
  ursprueglich strengere Validierung (``source != target``) wurde
  gelockert, weil eine Erst-Migration logischerweise keinen
  Quell-Index hat. Sentinel 0 ist sprechend und kann ohne
  zusaetzliche Flags genutzt werden.
- **Kein SSE fuer den Ollama-Download**: der UI-Setup-Wizard braucht
  das Ergebnis atomar, nicht als Stream. Wenn eine Frontend-Streaming-
  UX noetig wird, kommt sie in Sub-Slice 4.3.2 mit Server-Sent-
  Events ueber einen separaten Endpoint.
- **Strikte Model-Name-Validierung**: ASCII-Zeichen + Bindestrich +
  Unterstrich + Doppelpunkt + Punkt, 1-100 Zeichen. Schliesst
  Shell-Injection auf der Modell-Bezeichnungs-Ebene aus, ohne
  die gaengigen Ollama-Naming-Conventions
  (``name:tag``, ``name.variant``) zu beschraenken.
- **Job-Persistenz als flache JSON-Dateien**: ein Job pro Datei
  unter `AGORA_DATA_DIR/embedding_migration_<id>.json`. Einfacher
  als eine zweite Collection im Embedding-Configuration-Store;
  unkompliziert fuer Folge-Slices, die z. B. nach ``completed``
  aufraeumen koennen.
- **Migrations-Service fuehrt KEIN `DROP INDEX` aus**: ADR-0007
  verbietet das bis zur expliziten Operator-Bestaetigung. Der
  `completed`-Pfad macht nur den Konfigurations-Switch und setzt
  den alten Index auf `superseded` (lesbar, nicht aktiv).
  Neo4j-Index-Switch (``CALL db.index.setProperty`` o. ae.)
  ist ein eigener Schritt, der in einem Folge-Slice nach
  Live-Tests abgesichert wird.

## Bekannte Risiken

- **Re-Embedder ist ein No-Op-Stub**: Migrationen laufen
  "durch" (Lifecycle completed), aber es werden null Knoten
  re-embedded. Solange die echte Neo4j-Implementierung fehlt,
  ist der Migrations-Service ehrlich gesagt ein
  "Switch-Operator": er macht nur den Konfigurations-Switch
  und Index-Status-Wechsel, nicht den eigentlichen Re-Embed.
  Bis der echte Loop steht, ist ein Operator-Aufruf von
  `POST /migrations/<id>/run` ein No-Op-Switch. Mitigation:
  Handover dokumentiert das prominent; Frontend sollte im
  Migrations-Wizard eine sichtbare Warnung zeigen, bis der
  echte Loop steht.
- **Ollama-Download-Endpoint ist synchron**: bei grossen
  Modellen kann der HTTP-Request 10 Minuten dauern und blockiert
  einen Worker. Mitigation: in Produktion hinter einem
  Job-Queue-Endpoint (geplant fuer 4.3.2), oder mit
  Async-Worker-Pattern.
- **`request.get_json(silent=True)`**: schluckt JSON-Parse-Fehler
  still; das ist Absicht (der Body-Validator fängt das mit
  `ValueError` ab und liefert 400). Aber Endpunkt-Aufrufer mit
  kaputten JSON-Body bekommen 400, nicht 415 — falls das
  jemals relevant wird, muss der Endpunkt auf
  `silent=False` umgestellt und `BadRequest` gefangen werden.

## Geänderte Verträge und Migrationen

- **`EmbeddingMigrationJob.source_index_version`** darf jetzt
  `0` sein (Sentinel fuer Cold-Start). Vertrag: `Field(ge=0)`
  statt `Field(ge=1)`. Service: `start()` setzt
  `source_index_version=0` wenn `next_version == 1`.
- **Keine JSON-Schema-Drift**: das OpenAPI-Schema aendert sich
  nur in der Minimum-Constraint, was die generierten Schemas
  nicht beruehrt (Schema-Drift-Check ist 46/46 gruen).
- **Keine Datenmigration** noetig — die Job-Dateien werden
  lazy angelegt, wenn der erste Job gestartet wird.

## Nächste exakt ausführbare Schritte

1. Atomarer Commit auf `codex/onboarding-embedding-migration`,
   Branch pushen, PR gegen `main` eroeffnen; Gemini-Findings
   sichten, erst danach mergen.
2. Nach Merge: `uvx --from 'code-review-graph==2.3.6'
   code-review-graph build` auf `main` + Delta pruefen.
3. Sub-Slice 4.3.2: Frontend-Store, View, Zod-Spiegel,
   Onboarding-Anbindung in einer Folge-Session.
4. Folge-Slice: echte Neo4j-Re-Embedding-Engine
   (`ReEmbedder`-Implementierung mit Neo4j-Read-Loop + Embedding-
   Service-Cache).

## Relevante Dateien

- `backend/app/services/embedding_migration.py`
- `backend/app/services/embedding_ollama_pull.py`
- `backend/app/api/embedding_migrations.py`
- `backend/app/api/__init__.py` (Import-Update)
- `backend/app/contracts/embedding_contract.py` (Sentinel-Erweiterung)
- `backend/tests/services/test_embedding_migration.py`
- `backend/tests/services/test_embedding_ollama_pull.py`
- `docs/epics/onboarding-provider-unification/04-implementation-plan.md`
- `docs/decisions/0007-embedding-configuration-and-index-migration.md`

## Befehle zur Verifikation

```bash
cd backend && uv run pytest tests/services/test_embedding_migration.py \
  tests/services/test_embedding_ollama_pull.py -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check app/ tests/
cd backend && uv run mypy app
cd backend && uv run pytest -q
cd frontend && bun run test
bash scripts/sync-status.sh --check
uvx --from 'code-review-graph==2.3.6' code-review-graph status --repo .
```
