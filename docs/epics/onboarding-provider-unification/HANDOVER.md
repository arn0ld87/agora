# Handover — Onboarding/Provider-Unification Slice 4.3.4

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-4-3-4`
- Branch: `codex/embedding-neo4j-reembedder` (Basis: `main` @ `dcfba4a`,
  PR #693 gemergt)
- Slice: 4.3.4 — Echte Neo4j-Re-Embedding-Engine (`Neo4jReEmbedder`
  ersetzt `_NoopReEmbedder`; Read-Loop + Checkpoint + Resume)
- Arbeitsstand: implementiert, `bash scripts/pre-push-gate.sh` komplett
  grün (Backend + Frontend + Schemas + STATUS-Sync)
- Teststatus: Slice-Tests 90 passed (7 neue Engine-Tests, 2 neue
  Service-Tests, 2 neue Contract-Tests, 2 neue Frontend-Spec-Tests);
  Zahlen-SSoT in `docs/STATUS.md` (via `scripts/sync-status.sh`
  regeneriert, 3250 collected)
- context-mode: aktiv in dieser Session (ctx_batch_execute für Reads)
- code-review-graph: CLI in dieser Session nicht installiert;
  Discovery lief über context-mode-Batches

## Dokumentations-Sync

- README.md: geprüft, nicht betroffen (Operator-Doku der Migration
  bleibt gültig; Engine ist Implementierungsdetail hinter derselben API)
- AGENTS.md: geprüft, nicht betroffen
- CLAUDE.md: geprüft, nicht betroffen
- PLAN.md: aktualisiert (Abschnitt 12, Slice-4-Status)
- docs/STATUS.md: aktualisiert (sync-status.sh)
- CHANGELOG.md: aktualisiert (Added embedding-reembedder 2026-07-13)
- docs/tooling/agent-tools.md: geprüft, nicht betroffen

## Fertig (Sub-Slice 4.3.4)

- `backend/app/services/embedding_reembedder.py` (neu):
  `Neo4jReEmbedder` mit
  - `CREATE VECTOR INDEX <entity_embedding_vN> IF NOT EXISTS` auf der
    versionierten Property (niemals DROP — ADR-0007), Identifier-Guard
    gegen Cypher-Injection in der DDL,
  - Count + batchweisem Read-Loop über `(n:Entity)` sortiert nach
    `uuid` mit Cursor `uuid > $cursor`,
  - Embedding-Text = `coalesce(n.summary, name + ' (' + entity_type + ')')`
    (identisch zum Ingest-Pfad `ingestion_pipeline`),
  - Dimensionsprüfung pro Vektor; Mismatch → Knoten wird nicht
    geschrieben, zählt als `failed`, Endstatus `failed` (kein Switch),
  - Schreiben via `db.create.setNodeVectorProperty` (UNWIND-Batch),
  - Checkpoint-Aufruf nach jedem Batch.
- `backend/app/contracts/embedding_contract.py`:
  `EmbeddingMigrationProgress.last_processed_id: str | None = None`
  (Resume-Cursor; Alt-Payloads ohne Feld bleiben ladbar).
- `backend/app/services/embedding_migration.py`:
  - `ReEmbedder`-Protocol erweitert um `configuration` +
    `checkpoint`-Callback; der Service persistiert jeden Checkpoint
    (`_persist_checkpoint` → `_save_job`),
  - `run()` akzeptiert jetzt auch Status `running` = Crash-Resume
    (`started_at` bleibt erhalten),
  - `failed`-Pfade laden den Job vor dem Endzustand neu, damit
    Checkpoint-Progress nicht verloren geht.
- `backend/app/api/embedding_migrations.py`: `_service()` verdrahtet
  die echte Engine — Driver lazy via `GraphDatabase.driver(Config.NEO4J_*)`
  (eigener Driver, nicht der App-Pool), Embedder aus Konfiguration +
  `ProviderConnectionStore` + Secret-Store (analog Probe-Pfad).
  Gemini (`provider_kind="google"`) wird mit klarer Fehlermeldung
  abgelehnt (anderes URL-Schema als `EmbeddingService`).
- Frontend: `EmbeddingMigrationProgressSchema` um
  `last_processed_id: z.string().nullable().default(null)` ergänzt
  + 2 Spec-Tests.
- Schemas: `embedding-migration-job(.response)` regeneriert.
- Tests: `backend/tests/services/test_embedding_reembedder.py` (neu, 7),
  `test_embedding_migration.py` (+2: Checkpoint-Persistenz, Resume),
  `test_embedding_contract.py` (+2: Default/Roundtrip).

## Noch offen (bewusst, mit Begründung)

- **`RELATION.fact_embedding`-Re-Embed**: Der versionierte
  Index-Vertrag (`EmbeddingIndexVersion`) verwaltet nur
  `entity_embedding_vN`. Facts brauchen eine eigene Index-Versionierung
  → eigener Slice.
- **Search-Pfad nutzt weiter den unversionierten `entity_embedding`-Index**
  (`search_service.py` hardcodet `entity_embedding`/`fact_embedding`).
  Der Umschwenk der Query-Seite auf `entity_embedding_vN` ist der
  logische Folge-Sub-Slice nach dem ersten echten Re-Embed.
- **Gemini-Batch-Embedding**: `EmbeddingService` spricht nur
  Ollama-/OpenAI-kompatible Endpunkte. Gemini-Embed-Batch wäre ein
  eigener Adapter — bis dahin ehrliche Ablehnung.
- **`scope="project"`-Filter**: Zuordnung Projekt → Graph ist nicht
  Teil des Embedding-Vertrags; Engine läuft global.
- **Migration läuft synchron im Request** (`POST /migrations/<id>/run`):
  bei großen Graphen lange Requests. Resume macht das erträglich;
  Job-Queue/SSE-Streaming bleibt der bekannte offene Punkt aus 4.3.1.
- **i18n-Keys** für die Embedding-View (`embedding.title` etc.) —
  Mini-Folge-Aufgabe, nicht Teil dieses Slices.

## Entscheidungen

- Resume über `uuid`-Cursor (`last_processed_id`) statt Offset:
  stabil gegen parallel wachsende Graphen, kein Skip/Doppel-Embed.
- Job-Status `running` gilt bei `run()` als Resume (Crash-Recovery);
  ein Operator-Abbruch bleibt `rolled_back` und ist nicht resumebar.
- `failed > 0` ⇒ Endstatus `failed`, kein Index-Switch: ein
  unvollständig befüllter Index darf nie aktiv werden (ADR-0007
  Dimensionssicherheit).
- Eigener lazy Neo4j-Driver pro Migrationslauf statt App-Pool:
  langlaufender Operator-Vorgang soll den Flask-Pool nicht blockieren.
- Checkpoint-Persistenz macht der Service (nicht die Engine), damit
  die Engine ohne Kenntnis des Job-Speicherformats testbar bleibt.

## Bekannte Risiken

- Der neue versionierte Index wird von der Suche noch nicht abgefragt
  (siehe „Noch offen"). Nach einem Modellwechsel mit anderer Dimension
  liefert die Suche weiterhin Ergebnisse aus dem alten Index — der
  Operator sieht den Fortschritt nur im Migrations-Job.
- `EmbeddingService.embed_batch` cached in-memory pro Instanz
  (`_cache_max_size` 2000) — bei sehr großen Graphen unkritisch,
  aber erwähnt.
- Entities ohne `uuid`-Property (sehr alte Bestandsgraphen) werden
  bewusst übersprungen (`WHERE n.uuid IS NOT NULL`) und tauchen nicht
  in `total` auf.

## Geänderte Verträge und Migrationen

- `EmbeddingMigrationProgress` + `last_processed_id` (additiv,
  Default `None`; Schema-Dump + Zod-Spiegel synchron; Alt-Job-Dateien
  bleiben ladbar).
- Keine Datenbank-Migration; die Engine legt nur additiv
  `entity_embedding_vN`-Indizes und `embedding_vN`-Properties an.

## Nächste exakt ausführbare Schritte

1. PR gegen `main` eröffnen, 90 s warten, Gemini-Findings sichten,
   erst dann mergen.
2. Nach Merge: Codegraph auf `main` neu bauen (`uvx --from
   'code-review-graph==2.3.6' code-review-graph build`).
3. Slice 5 (gemeinsamer Model-Picker, Discovery-getrieben) beginnen;
   Search-Pfad-Umschwenk auf versionierte Indizes bleibt als
   dokumentierter Folge-Sub-Slice.

## Relevante Dateien

- `backend/app/services/embedding_reembedder.py`
- `backend/app/services/embedding_migration.py`
- `backend/app/contracts/embedding_contract.py`
- `backend/app/api/embedding_migrations.py`
- `frontend/src/contracts/embeddingContract.ts`
- `backend/tests/services/test_embedding_reembedder.py`

## Befehle zur Verifikation

```bash
cd /private/tmp/agora-onboarding-slice-4-3-4
bash scripts/pre-push-gate.sh
cd backend && uv run pytest tests/services/test_embedding_reembedder.py \
  tests/services/test_embedding_migration.py \
  tests/contracts/test_embedding_contract.py -q
```
