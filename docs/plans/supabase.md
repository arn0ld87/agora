# Agora → Supabase Self-Hosted: Migrations- und Architekturplan

**Stand:** 21.08.2026  
**Basis:** `arn0ld87/agora`, geprüft gegen Commit `883c1d264de193973e9095c10e8c1d943d13c9fd`  
**Ziel:** Agora schrittweise um PostgreSQL, Supabase Auth und Supabase Storage erweitern, ohne Neo4j, Redis oder die Flask-Domänenlogik vorschnell zu ersetzen.

---

## Umsetzungsstand (24.09.2026)

Der Plantext unten ist der Entwurf vom 21.08.2026 und wird nicht rückwirkend
umgeschrieben. Offene Checkboxen in den Phasenabschnitten sind **kein**
Fortschrittsanzeiger. Maßgeblich sind diese Tabelle, [`docs/STATUS.md`](../STATUS.md)
und das Epic [#1576](https://github.com/arn0ld87/agora/issues/1576).

**Umgeschaltet ist nichts.** Gebaut sind bisher genau zwei PostgreSQL-Adapter,
`PostgresLlmProfileRepository` und `PostgresProjectRepository`; beide sind per
Default inaktiv (`AGORA_METADATA_BACKEND=legacy`, `AGORA_LLM_PROFILE_BACKEND=sqlite`,
`AGORA_PROJECT_BACKEND=file`). Simulationen, Runs, Reports und Blobs haben noch
keinen Adapter (siehe Tabelle).

| Plan (§38) | Inhalt | Stand |
|---|---|---|
| Phase 0 | Baseline, Restore-Drill | gemergt (#1514) |
| PR 1 | Self-hosted Supabase als eigenes Compose-Projekt | gemergt (#1504) |
| PR 2 | SQLAlchemy + Alembic | gemergt (#1505, #1508), ADR-0014 (#1518) |
| PR 3 | LLM-Profil-Modell und Repository-Port | gemergt (#1507, #1511, #1515) |
| PR 4 | Postgres-Adapter LLM-Profile, Datenmigration | gemergt (#1517), Fernet-Store pro Profil (#1516) |
| PR 6 | Projekt-Vertrag, Port, Postgres-Adapter, Datenmigration | gemergt (#1519, #1522) |
| PR 7 | Simulationsmetadaten | Port gemergt (#1595, Issue #1578), Adapter: #1585 |
| PR 8 | Run-Registry | Port gemergt (#1596, Issue #1579), Adapter: #1587 |
| PR 9 | Report-Metadaten | Port: #1580, Adapter: #1588 |
| PR 13/14 | Blob-Store-Port, Supabase-Storage-Adapter | #1584, #1586 (optional) |
| PR 15 | Cutover Metadaten-Backend | Prüfskript #1590, Cutover armserver #1592 |
| — | CI-Postgres, Readiness, Alembic-Drift, Backup, Rollback-Gate | CI gemergt (#1594, Issue #1577); offen: #1581, #1582, #1583, #1589 |

**Zurückgestellt (ROADMAP: nicht vor 1.0):** PR 5 und §16 (Workspaces), PR 10–12
und §14/15/17/18 (Supabase Auth, JWT, RLS), §22/23 (Frontend-Client, Realtime),
§24/25 (pgvector, `PostgresGraphStorage`), §26 (LLM-Secrets in DB/Vault).

**Abstimmung mit 0.10.0:** [`plans/active/0.10.0-rc-plan.md`](active/0.10.0-rc-plan.md)
führt die Linie unter E5 als pausiert (19.09.2026) und außerhalb des 0.10.0-Scopes.
Die Tickets unter #1576 laufen daneben, nicht als Teil der 0.10.0-Gates.

---

## 1. Entscheidung in einem Satz

Nicht „Agora auf Supabase umschreiben“, sondern:

> **Flask bleibt Backend und Orchestrator, Supabase liefert PostgreSQL + Auth + Storage, Neo4j bleibt Knowledge-Graph, Redis bleibt Event-/RPC-Bus.**

Das ist der geringste Risikopfad und passt zur bereits vorhandenen Adapter-/DI-Architektur.

---

# 2. Zielarchitektur

```text
                           ┌─────────────────────┐
                           │      Vue SPA        │
                           └──────────┬──────────┘
                                      │
                         Login        │ API / SSE
                      ┌───────────────┼────────────────┐
                      │               │                │
                      ▼               ▼                │
               Supabase Auth      Flask API            │
                                      │                │
                 ┌────────────────────┼──────────────┐ │
                 │                    │              │ │
                 ▼                    ▼              ▼ ▼
           PostgreSQL               Neo4j          Redis
           (Supabase)               Graph       Events / RPC
                 │
                 ├── Workspaces
                 ├── Projects
                 ├── Simulations
                 ├── Runs
                 ├── Reports
                 ├── Personas
                 ├── LLM-Profile
                 ├── Audit Events
                 └── Artifact-Metadaten

                     Supabase Storage
                            │
                            ├── Uploads
                            ├── Exports
                            ├── Report-Dateien
                            └── große/immutable Artefakte
```

## Was ausdrücklich **nicht** passiert

- Flask wird nicht durch Edge Functions ersetzt.
- Neo4j wird in der ersten Migration nicht entfernt.
- Redis wird nicht durch Supabase Realtime ersetzt.
- Die bestehenden API-Verträge werden nicht gleichzeitig neu erfunden.
- Das Frontend erhält zunächst keinen direkten CRUD-Zugriff auf Fach-Tabellen.
- JSON-/Datei-State wird nicht blind vollständig in Object Storage gekippt.
- Kein Big-Bang-Cutover.

---

# 3. Warum diese Aufteilung

| Bereich | Zielsystem | Grund |
|---|---|---|
| Benutzer / Login | Supabase Auth | fertige Session-/Token-Infrastruktur |
| Workspaces / Projekte | PostgreSQL | relationale Daten, Constraints, Queries |
| Simulation-Metadaten | PostgreSQL | langlebige, strukturierte Daten |
| Runs / Reports | PostgreSQL | Analytics, Status, Beziehungen |
| Knowledge Graph | Neo4j | Traversals, Beziehungen, temporale Kanten |
| Event/RPC | Redis | schnelle Runtime-Kommunikation |
| Uploads / Exports | Supabase Storage | Blob-/Object-Storage |
| Runtime-State | Redis/PostgreSQL | nicht Object Storage |
| Embeddings | zunächst Neo4j | kein unnötiger Doppelbestand |
| Embeddings später | pgvector-PoC | nur nach Benchmark |

---

# 4. Leitprinzipien

1. **Strangler-Migration:** Neues System wird parallel eingeführt.
2. **Additive Migrationen:** Erst neue Strukturen hinzufügen, später alte entfernen.
3. **Ports/Adapter nutzen:** Fachcode kennt nicht „Supabase“, sondern Interfaces.
4. **Eine Source of Truth je Domäne.**
5. **Feature Flags für jeden Cutover.**
6. **Rollback muss vor dem Cutover funktionieren.**
7. **Keine Secrets im Frontend.**
8. **Keine `service_role`-Credentials im Browser.**
9. **Keine Datenmigration ohne Verifikation.**
10. **Neo4j erst ersetzen, wenn Messwerte es rechtfertigen.**

---

# 5. Ziel-Verzeichnisstruktur

Empfohlene Ergänzungen:

```text
backend/
  app/
    auth/
      principal.py
      provider.py
      legacy_provider.py
      supabase_provider.py

    repositories/
      workspace_repository.py
      project_repository.py
      simulation_repository.py
      run_repository.py
      report_repository.py
      persona_repository.py
      llm_profile_repository.py
      audit_repository.py

    infrastructure/
      postgres/
        engine.py
        session.py
        models/
        repositories/
      supabase/
        auth.py
        storage.py

    services/
      artifact_store.py
      event_bus.py

  migrations/
    alembic.ini
    versions/

infra/
  supabase/
    docker-compose.yml
    .env.example
    README.md

scripts/
  migrate_sqlite_to_postgres.py
  migrate_simulation_metadata.py
  verify_postgres_migration.py
  verify_workspace_isolation.py
  backup_postgres.sh
  restore_postgres.sh
```

Bestehende Module müssen dafür nicht schlagartig verschoben werden.

---

# 6. Phase 0: Baseline und Sicherheitsnetz

**Aufwand:** 1–2 Arbeitstage  
**Risiko:** niedrig

## Ziel

Vor dem ersten Datenumbau muss klar sein, welcher Stand als „funktioniert“ gilt.

## Aufgaben

- [ ] dedizierten Branch anlegen, z. B. `feat/supabase-foundation`
- [ ] aktuellen Commit dokumentieren
- [ ] bestehende Unit-/Integration-/E2E-Tests komplett ausführen
- [ ] aktuelle Persistenzquellen inventarisieren
- [ ] Beispieldatensatz mit echten Agora-Projekten sichern
- [ ] Backup der aktuellen Neo4j-Daten erzeugen
- [ ] Backup von `backend/uploads/`
- [ ] Backup von `backend/instance/`
- [ ] Backup von `backend/data/`
- [ ] Redis als nicht-dauerhafte Source of Truth klassifizieren
- [ ] Migrationsmetriken definieren

## Migrationsmetriken

Mindestens:

```text
Projects
Simulations
Runs
Reports
Personas
LLM profiles
Graph nodes
Graph edges
Artifacts
```

Für jede Klasse:

```text
old_count == new_count
IDs bleiben identisch
Timestamps bleiben identisch
Statuswerte bleiben identisch
Referenzen sind vollständig
```

## Abnahmekriterium

Ein dokumentierter Baseline-Lauf liefert vor und nach jeder späteren Phase
dieselben stabilen Migrationsinvarianten: Anzahl, IDs, Timestamps, Statuswerte,
Referenzen und Artefaktprüfsummen. LLM- und Simulationsausgaben werden nicht
byteweise verglichen; ein gespeicherter Seed macht einen Lauf nicht
reproduzierbar.

---

# 7. Phase 1: Supabase parallel deployen

**Aufwand:** 1–3 Arbeitstage  
**Risiko:** niedrig

## Ziel

Supabase läuft parallel, ohne dass Agora fachlich davon abhängt.

## Empfehlung

Supabase als **eigenes Compose-Projekt** betreiben.

Nicht den kompletten Supabase-Stack in `docker-compose.yml` von Agora hineinquetschen.

```text
agora/
  docker-compose.yml

supabase/
  docker-compose.yml
```

Beide können über ein gemeinsames internes Docker-Netz sprechen.

## Netzwerk

Beispiel:

```bash
docker network create agora-backend
```

Beide Compose-Projekte hängen an:

```yaml
networks:
  agora-backend:
    external: true
```

## Exposition

Extern nur:

```text
Reverse Proxy
    │
    ├── agora.example.tld
    └── auth.example.tld / supabase.example.tld
```

Nicht öffentlich exponieren:

```text
PostgreSQL
Supavisor intern
Studio
interne Supabase Services
```

Supabase Studio nur intern bzw. über VPN/Tailscale/Admin-Netz.

## Supabase-Dienste zunächst

Behalten:

```text
PostgreSQL
Auth
Storage
PostgREST
Supavisor
Studio
Gateway
```

Optional zunächst deaktivieren:

```text
Realtime
Edge Runtime
imgproxy
Analytics/Logflare
```

Je weniger Container am Anfang, desto weniger bewegliche Teile.

## DB-Verbindung für Flask

Empfohlen:

```text
SQLAlchemy 2.x
+
psycopg
+
Alembic
```

Flask soll nicht überall `supabase-py` verwenden.

Supabase ist Infrastruktur; PostgreSQL bleibt über Standard-SQL erreichbar.

## Verbindungsmodus

Für Flask zunächst:

```text
Supavisor Session Mode
```

oder interne direkte PostgreSQL-Verbindung.

Transaction Pooling erst später prüfen.

## Abnahmekriterium

```bash
curl -f https://<supabase-host>/auth/v1/health
```

Außerdem:

```text
Agora funktioniert weiterhin komplett ohne neue Supabase-Funktion.
```

---

# 8. Phase 2: PostgreSQL-Grundlage in Agora

**Aufwand:** 2–4 Arbeitstage  
**Risiko:** niedrig bis mittel

## Pakete

Python:

```text
sqlalchemy
psycopg[binary]
alembic
```

## Konfiguration

Neue Variablen:

```env
DATABASE_URL=postgresql+psycopg://...
AGORA_METADATA_BACKEND=legacy
```

Später:

```env
AGORA_METADATA_BACKEND=postgres
```

## Engine

Ein zentraler Adapter:

```python
class Database:
    def session(self):
        ...
```

Keine freien `psycopg.connect()`-Aufrufe quer durch Services.

## Alembic

Ab jetzt gilt:

> Datenbankschema wird ausschließlich über versionierte Migrationen geändert.

Keine `CREATE TABLE IF NOT EXISTS`-Strings mehr innerhalb fachlicher Stores.

## Abnahmekriterium

Aus dem Agora-Container:

```bash
python -c "import psycopg; print('db-driver-ok')"
```

Der Treiber kommt erst mit dieser Phase in die Abhängigkeiten; in Phase 1 kann
die Prüfung nicht bestehen.

---

# 9. Phase 3: Ziel-Datenmodell anlegen

**Aufwand:** 2–5 Arbeitstage  
**Risiko:** mittel

## Schema-Aufteilung

Empfehlung:

```text
auth.*      -> Supabase verwaltet
storage.*   -> Supabase verwaltet
agora.*     -> Agora Fachschema
public.*    -> möglichst leer / nur bewusst exponierte Views
```

Damit liegen Fach-Tabellen nicht versehentlich in einem direkt exponierten API-Schema.

**Umsetzungsbeschluss vom 17.09.2026:** Phase 3 wird nicht als vollständiges
Schema auf einmal ausgerollt. PR 3 legt ausschließlich das Single-User-Modell
`agora.llm_profiles` an und hält SQLite als Laufzeit-Default. Die folgenden
Tabellen beschreiben weiterhin das langfristige Ziel; Workspace-, Membership-
und Auth-Abhängigkeiten entstehen erst in der dafür freigegebenen Phase.

## Kern-Tabellen

### `agora.workspaces`

```text
id uuid PK
name text
slug text UNIQUE
created_at timestamptz
updated_at timestamptz
```

### `agora.workspace_members`

```text
workspace_id uuid FK
user_id uuid FK -> auth.users
role text
created_at timestamptz

PK(workspace_id, user_id)
```

### `agora.projects`

```text
id uuid PK
workspace_id uuid FK
name text
description text
graph_id text NULL
created_at timestamptz
updated_at timestamptz
```

### `agora.simulations`

```text
id uuid PK
workspace_id uuid FK
project_id uuid FK
graph_id text NULL
status text
question text
parent_simulation_id uuid NULL
config jsonb
created_at timestamptz
updated_at timestamptz
```

### `agora.simulation_runs`

```text
id uuid PK
workspace_id uuid FK
simulation_id uuid FK
status text
started_at timestamptz NULL
finished_at timestamptz NULL
model_profile_id uuid NULL
metrics jsonb
error jsonb NULL
created_at timestamptz
```

### `agora.reports`

```text
id uuid PK
workspace_id uuid FK
simulation_id uuid FK
run_id uuid NULL
status text
title text
summary text NULL
metadata jsonb
created_at timestamptz
updated_at timestamptz
```

### `agora.personas`

```text
id uuid PK
workspace_id uuid FK
name text
profile jsonb
source_type text
source_id text NULL
created_at timestamptz
updated_at timestamptz
```

### `agora.llm_profiles`

```text
id uuid PK
name text
provider text
base_url text
model_name text
is_default boolean
created_at timestamptz
updated_at timestamptz
```

Persistenzmatrix für den ersten Single-User-Schnitt:

| Feld / Invariante | Pydantic/API | Legacy-SQLite | PostgreSQL ab PR 3 |
|---|---|---|---|
| `id` | `str`, servergenerierte UUID | `TEXT`, `uuid4().hex` | `uuid`, beim Migrieren unverändert |
| `name` | 1–80 Zeichen | `TEXT NOT NULL` | `text NOT NULL`, Länge 1–80 |
| `provider` | `ProviderType` | `TEXT NOT NULL` | `text NOT NULL`; der Contract validiert den Wert |
| `base_url` | nicht leer | `TEXT NOT NULL` | `text NOT NULL`, nicht leer |
| `model_name` | nicht leer | `TEXT NOT NULL` | `text NOT NULL`, nicht leer |
| `api_key` | optionales Schreibfeld, in Antworten redigiert | aus Kompatibilitätsgründen vorerst vorhanden | **keine Spalte**; Secrets bleiben im verschlüsselten Secret-Store |
| `is_default` | `bool`, Default `false` | höchstens ein Profil wird gesetzt | `boolean NOT NULL`; höchstens ein Profil darf `true` sein |
| `created_at` / `updated_at` | timezone-aware `datetime` | ISO-8601-Text in UTC | `timestamptz NOT NULL` |
| `workspace_id` | nicht vorhanden | nicht vorhanden | **noch keine Spalte**; folgt erst mit der freigegebenen Multi-User-Phase |

Damit ist `agora.llm_profiles` zunächst bewusst ein Single-User-Modell. Die
spätere Workspace-Migration ergänzt `workspace_id` samt per-Workspace-Default,
ohne die heutige Roadmap durch Auth- oder Membership-Abhängigkeiten vorzuziehen.

## API-Schlüssel nicht im Klartext

```text
agora.api_keys

id
workspace_id
name
key_prefix
key_hash
scopes
status
created_at
last_used_at
revoked_at
```

Nur der Hash wird gespeichert.

## Audit

```text
agora.audit_events

id
workspace_id
actor_type
actor_id
event_type
resource_type
resource_id
metadata jsonb
created_at
```

---

# 10. Phase 4: Erste echte Migration – LLM Profiles

**Aufwand:** 1–2 Arbeitstage  
**Risiko:** niedrig

Das ist der ideale Pilot, weil der heutige SQLite-Store klein und klar abgegrenzt ist.

## Neue Abstraktion

```python
class LlmProfileRepository(Protocol):
    def list(...): ...
    def get(...): ...
    def create(...): ...
    def update(...): ...
    def delete(...): ...
    def set_default(...): ...
```

Adapter:

```text
SqliteLlmProfileRepository
PostgresLlmProfileRepository
```

## Feature Flag

```env
AGORA_LLM_PROFILE_BACKEND=sqlite
```

später:

```env
AGORA_LLM_PROFILE_BACKEND=postgres
```

## Migrationsablauf

1. PR 3 legt Modell und PostgreSQL-Tabelle an; SQLite bleibt aktiv.
2. PR 3 zieht den SQLite-Pfad hinter `LlmProfileRepository`.
3. PR 4 liest die SQLite-Daten.
4. IDs und Timestamps unverändert übernehmen.
5. Daten nach PostgreSQL schreiben.
6. Anzahl und Datensätze feldweise vergleichen.
7. Postgres-Adapter in Tests aktivieren.
8. Feature Flag umschalten.
9. SQLite-Datei noch nicht löschen.

## Wichtiger Punkt: API Keys / Provider-Secrets

Provider-Secrets nicht einfach als normales `api_key`-Feld in die neue Tabelle übernehmen.

Empfehlung zunächst:

```text
Metadaten -> PostgreSQL
Secrets   -> bestehender verschlüsselter Secret-Store
```

Später kann ein separater Secret-Adapter gebaut werden.

---

# 11. Phase 5: Projekt- und Simulationsmetadaten

**Aufwand:** 5–8 Arbeitstage  
**Risiko:** mittel

Jetzt kommt der größte sinnvolle Datengewinn.

## Nicht alles aus JSON migrieren

JSON-Artefakte in drei Klassen teilen.

### A: Dauerhafte Fachmetadaten → PostgreSQL

Beispiele:

```text
Simulation-ID
Projekt-ID
Status
Fragestellung
Graph-ID
Parent/Branch
Erstellzeit
Run-Liste
Report-Zuordnung
Persona-Satz-Zuordnung
```

### B: Große immutable Dateien → Storage

```text
Seed-Dokumente
Uploads
PDF-/Markdown-Exports
Report-Dateien
große Log-Archive
```

### C: Flüchtiger Runtime-State → Redis / Runtime Store

```text
pause
resume
stop
RPC command
RPC response
Live events
kurzlebiger run progress
```

## Warum

Häufig veränderte `state.json`-Dateien einfach in Object Storage zu verschieben wäre keine Verbesserung.

Die eigentliche Verbesserung lautet:

```text
strukturiert -> PostgreSQL
Blob         -> Object Storage
Runtime      -> Redis
Graph        -> Neo4j
```

---

# 12. Repository-Schicht einführen

Pro Domäne ein Port.

Beispiel:

```python
class SimulationRepository(Protocol):
    def create(self, simulation): ...
    def get(self, simulation_id): ...
    def list_for_workspace(self, workspace_id): ...
    def update_status(self, simulation_id, status): ...
    def update_config(self, simulation_id, config): ...
```

Adapter:

```text
LegacySimulationRepository
PostgresSimulationRepository
```

Services dürfen nicht wissen, wo die Daten liegen.

---

# 13. Strangler-Cutover pro Repository

Für jede Domäne identischer Ablauf:

```text
1. PostgreSQL-Schema
2. neuer Repository-Adapter
3. Contract Tests
4. Migration Script
5. Shadow Read
6. optional Dual Write
7. Parity Check
8. Read Cutover
9. Beobachtungsphase
10. Legacy Write deaktivieren
11. Legacy Daten erst später löschen
```

## Shadow Read

Beispiel:

```python
legacy = legacy_repo.get(id)
modern = postgres_repo.get(id)

assert normalize(legacy) == normalize(modern)
```

Nicht im kritischen Request-Pfad dauerhaft aktiv lassen.

Besser:

```text
CLI-Verifikation
CI-Migrationstest
periodischer Admin-Check
```

---

# 14. Phase 6: Supabase Auth

**Aufwand:** 5–10 Arbeitstage  
**Risiko:** mittel bis hoch

Das ist fachlich wichtiger als pgvector oder Realtime.

## Ziel

Menschen:

```text
Supabase Auth
```

Automatisierungen / API-Zugriffe:

```text
Agora Workspace API Keys
```

Beides läuft in Flask auf eine gemeinsame Identität:

```python
@dataclass
class Principal:
    auth_type: str
    user_id: str | None
    workspace_id: str
    scopes: set[str]
    roles: set[str]
```

## Übergangsmodus

```env
AGORA_AUTH_BACKEND=hybrid
```

Reihenfolge:

```text
Supabase JWT
    ↓
Workspace API Key
    ↓
Legacy Master Token
```

Später:

```env
AGORA_AUTH_BACKEND=supabase
```

Der Master Token bleibt dann nur noch für Break-Glass/Admin oder verschwindet vollständig.

---

# 15. JWT-Verifikation in Flask

Frontend:

```text
Supabase Login
    ↓
Access Token
    ↓
Authorization: Bearer <JWT>
    ↓
Flask
```

Flask:

```text
1. Signatur prüfen
2. issuer prüfen
3. audience prüfen
4. expiry prüfen
5. user_id lesen
6. Workspace-Mitgliedschaft laden
7. Principal erzeugen
```

Keine Autorisierung nur anhand vom Frontend behaupteter `workspace_id`.

---

# 16. Workspace-Modell

Ein Benutzer kann Mitglied mehrerer Workspaces sein.

```text
auth.users
    │
    └── workspace_members
              │
              └── workspaces
                     │
                     ├── projects
                     ├── simulations
                     ├── reports
                     ├── personas
                     └── llm_profiles
```

Rollen zunächst klein halten:

```text
owner
admin
member
viewer
```

Nicht sofort ein 47-stufiges IAM-System bauen.

---

# 17. Row Level Security

Da Flask direkt per SQLAlchemy auf PostgreSQL zugreift, muss RLS bewusst entworfen werden.

Supabase-RLS mit `auth.uid()` funktioniert automatisch bei PostgREST-Aufrufen mit Benutzer-JWT.

Bei direktem SQLAlchemy-Zugriff nicht automatisch.

## Empfohlener Weg

Flask verwendet einen eingeschränkten DB-Account:

```text
agora_app
```

Kein:

```text
SUPERUSER
BYPASSRLS
Table Owner
```

Pro Transaktion:

```sql
SET LOCAL app.user_id = '...';
SET LOCAL app.workspace_id = '...';
```

Policy:

```sql
CREATE POLICY workspace_isolation
ON agora.simulations
USING (
    workspace_id =
    current_setting('app.workspace_id', true)::uuid
);
```

Zusätzlich:

```sql
ALTER TABLE agora.simulations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agora.simulations FORCE ROW LEVEL SECURITY;
```

## Defense in Depth

Weiterhin im Repository:

```python
WHERE workspace_id = :workspace_id
```

RLS ist zweite Schranke, kein Ersatz für saubere Queries.

---

# 18. RLS-Testmatrix

Mindestens zwei Benutzer und zwei Workspaces:

```text
User A -> Workspace A
User B -> Workspace B
```

Tests:

- [ ] A kann A lesen
- [ ] A kann A ändern
- [ ] A kann B nicht lesen
- [ ] A kann B nicht ändern
- [ ] B kann A nicht lesen
- [ ] API-Key A kann B nicht lesen
- [ ] manipulierte Resource-ID liefert keinen Datenleak
- [ ] Listen-Endpunkte mischen keine Workspaces
- [ ] Reports referenzieren nur eigene Simulationen
- [ ] Foreign Keys können nicht workspace-übergreifend missbraucht werden

---

# 19. Phase 7: Supabase Storage

**Aufwand:** 2–5 Arbeitstage  
**Risiko:** niedrig bis mittel

## Nicht als State-Datenbank benutzen

Supabase Storage ist für:

```text
Uploads
Dokumente
Exports
große Reports
immutable Artefakte
```

Nicht primär für:

```text
control_state.json
run_state.json
RPC
häufig mutierende Statusobjekte
```

## Bucket

```text
agora-artifacts
```

Pfad:

```text
<workspace_id>/
    projects/<project_id>/
    simulations/<simulation_id>/
        uploads/
        exports/
        reports/
        logs/
```

## Neue Abstraktion

Bestehenden `SimulationArtifactStore` nicht unkontrolliert aufblasen.

Mittelfristig splitten:

```text
RuntimeStateStore
BlobArtifactStore
```

Beispiel:

```python
class BlobArtifactStore(Protocol):
    def put(...): ...
    def get(...): ...
    def delete(...): ...
    def list(...): ...
```

Adapter:

```text
LocalBlobArtifactStore
SupabaseBlobArtifactStore
```

---

# 20. Artifact-Metadaten in PostgreSQL

Die Datei liegt in Storage, die fachliche Zuordnung in PostgreSQL.

```text
agora.artifacts

id uuid
workspace_id uuid
project_id uuid NULL
simulation_id uuid NULL
run_id uuid NULL
kind text
bucket text
object_key text
content_type text
size_bytes bigint
sha256 text
created_at timestamptz
```

Vorteil:

```text
Storage enthält Bytes
PostgreSQL weiß, was die Bytes bedeuten
```

---

# 21. Upload-Ablauf

```text
Browser
   ↓
Flask
   ↓
Berechtigung prüfen
   ↓
Storage Upload
   ↓
Hash berechnen
   ↓
Artifact-Metadaten in PostgreSQL
   ↓
Projekt aktualisieren
```

Optional später:

```text
Signed Upload URL
```

Aber nicht in Phase 1.

---

# 22. Phase 8: Frontend-Anpassung

**Aufwand:** 3–6 Arbeitstage  
**Risiko:** mittel

## Frontend darf

Direkt mit Supabase Auth sprechen:

```text
login
logout
refresh session
password reset
```

## Frontend darf zunächst nicht

Direkt:

```text
projects.select()
simulations.insert()
reports.delete()
```

Fachdaten weiterhin:

```text
Vue -> Flask API
```

Damit bleiben:

```text
Validierung
Business Rules
Audit
Workspace Checks
API Contracts
Fehlerformat
```

zentral.

## Frontend-State

Neuer Auth Store:

```text
session
user
activeWorkspace
roles
tokenExpiry
```

Axios/FETCH-Interceptor:

```text
Authorization: Bearer <supabase access token>
```

---

# 23. Phase 9: Realtime nur dort, wo es lohnt

**Aufwand:** 2–5 Arbeitstage  
**Priorität:** optional

Redis bleibt Event-Bus.

Supabase Realtime kann später für UI-Projektionen genutzt werden.

Beispiel:

```text
Run Worker
   ↓
PostgreSQL run.status
   ↓
Supabase Realtime
   ↓
Browser
```

Aber nur wenn es gegenüber bestehendem SSE einen echten Gewinn bringt.

Wenn SSE bereits funktioniert:

> nicht ersetzen, nur weil WebSockets moderner aussehen.

---

# 24. Phase 10: pgvector-PoC

**Aufwand:** 5–10 Arbeitstage  
**Risiko:** mittel  
**Priorität:** nachrangig

Ziel ist nicht „Neo4j loswerden“.

Ziel ist:

> messen, ob PostgreSQL + pgvector bestimmte Suchaufgaben besser oder einfacher abbildet.

## Testdaten

Export eines realistischen Agora-Graphs:

```text
50k Nodes
200k Edges
100k Embeddings
```

Wenn real verfügbare Graphen kleiner sind, echte Größen nehmen.

## Benchmarks

```text
Node Lookup
1-Hop Neighbours
2-Hop Traversal
Entity Filter
Temporal Edge Query
Keyword Search
Vector Search
Hybrid Search
Graph Export
Provenance Query
```

## Metriken

```text
p50 latency
p95 latency
p99 latency
RAM
CPU
Disk
Index build time
write throughput
code complexity
```

---

# 25. PostgresGraphStorage nur als Experiment

Dank `GraphStorage` wäre möglich:

```python
class PostgresGraphStorage(GraphStorage):
    ...
```

Aber erst nach einem Contract-Testpaket.

## Contract-Test

Jede Implementierung muss identisches Verhalten liefern für:

```text
create_graph
delete_graph
set_ontology
get_ontology
add_text
add_text_batch
get_all_nodes
get_node
get_node_edges
get_nodes_by_label
get_filtered_entities_with_edges
get_all_edges
get_edges_at_round
reinforce_relation
tombstone_relation
get_episode_provenance
search
get_graph_info
get_graph_data
```

## Entscheidungskriterium

Neo4j darf nur entfernt werden, wenn PostgreSQL:

```text
funktional vollständig
+
hinreichend schnell
+
einfacher zu betreiben
+
weniger komplex im Code
```

ist.

Nur „eine Datenbank weniger“ reicht nicht.

---

# 26. Secrets

Nicht in:

```text
Vue
Git
Docker Image
Datenbank-Logs
plain JSON
```

## Kategorien

### Supabase-System-Secrets

```text
Postgres password
JWT signing key
anon key
service role key
SMTP credentials
```

### Agora-Secrets

```text
LLM provider keys
API keys
encryption keys
```

## Empfehlung

Initial:

```text
Docker secrets / geschützte Env
+
bestehender verschlüsselter Agora Secret Store
```

LLM-Secrets erst in einer eigenen späteren Migration anfassen.

---

# 27. Backup-Strategie

Self-hosted Supabase bedeutet:

> Backups sind Deine Verantwortung.

## Minimum

Täglich:

```text
PostgreSQL logical dump
Storage backup
Agora config backup
Neo4j backup
```

## Besser

```text
PostgreSQL physical backup
+
WAL archiving
+
off-host Kopie
+
regelmäßiger Restore-Test
```

## 3-2-1

```text
3 Kopien
2 verschiedene Medien/Systeme
1 Kopie außerhalb des Hosts
```

Ein Backup, das nie restored wurde, ist eine optimistische Datei.

---

# 28. Restore-Test

Monatlich oder vor größeren Migrationen:

1. neue leere Umgebung
2. PostgreSQL restore
3. Storage restore
4. Neo4j restore
5. Agora starten
6. Testprojekt laden
7. Simulation öffnen
8. Report öffnen
9. Auth testen
10. Workspace-Isolation testen

Erst dann gilt das Backup als brauchbar.

---

# 29. Observability

Mindestens:

```text
PostgreSQL connections
DB size
slow queries
failed auth
failed RLS checks
Storage errors
Redis availability
Neo4j availability
migration errors
background jobs
run failures
```

Health Endpoint:

```json
{
  "postgres": "ok",
  "supabase_auth": "ok",
  "storage": "ok",
  "neo4j": "ok",
  "redis": "ok"
}
```

Keine Secrets oder interne URLs darin ausgeben.

---

# 30. Deployment-Strategie

## Entwicklungsumgebung

```text
Agora Compose
Supabase Compose
Neo4j
Redis
```

## Produktion

Empfehlung bei ausreichend Infrastruktur:

```text
VM / Host A
  Agora
  Redis

VM / Host B
  Supabase
  PostgreSQL

VM / Host C oder B
  Neo4j
```

Für kleine Setups geht ein Host, aber Ressourcenlimits setzen.

Der vollständige Supabase-Stack benötigt bereits mehrere GB RAM; Neo4j besitzt ebenfalls einen relevanten Heap/Pagecache-Bedarf.

---

# 31. Update-Strategie für Supabase

Nie:

```yaml
image: irgendwas:latest
```

für zentrale Produktionsdienste.

Stattdessen Versionen pinnen.

Ablauf:

```text
Release Notes lesen
Backup
Staging Update
Migrationstests
Smoke Tests
Produktionsupdate
Health Check
```

---

# 32. Feature Flags

Empfohlene Übergangsflags:

```env
AGORA_METADATA_BACKEND=legacy|postgres
AGORA_LLM_PROFILE_BACKEND=sqlite|postgres
AGORA_AUTH_BACKEND=legacy|hybrid|supabase
AGORA_BLOB_BACKEND=filesystem|supabase
EVENT_BUS_BACKEND=redis|file|auto
AGORA_GRAPH_BACKEND=neo4j
```

Optional später:

```env
AGORA_GRAPH_BACKEND=neo4j|postgres
```

Nicht früher.

---

# 33. Migration von vorhandenen Daten

Für jedes Script:

```bash
python scripts/migrate_*.py --dry-run
```

Dann:

```bash
python scripts/migrate_*.py --execute
```

Dann:

```bash
python scripts/verify_*.py
```

## Anforderungen

Scripts müssen:

- idempotent sein
- vorhandene IDs behalten
- Dry-Run unterstützen
- Fortschritt loggen
- Fehler einzeln protokollieren
- am Ende eine Zusammenfassung liefern
- keine Quelldaten löschen

Beispiel:

```text
Scanned:   412
Inserted:  410
Skipped:     2
Failed:      0
Verified:  412/412
```

---

# 34. Keine Dual-Write-Orgie

Dual Write nur kurzzeitig und nur dort, wo nötig.

Problem:

```text
Legacy Write erfolgreich
Postgres Write fehlgeschlagen
```

Dann existieren zwei Wahrheiten.

Deshalb:

1. Daten migrieren
2. verifizieren
3. kurze Shadow-Phase
4. Read-Cutover
5. Postgres wird Source of Truth
6. Legacy bleibt read-only als Fallback
7. später entfernen

---

# 35. Rollback

Jeder Cutover braucht einen Rückweg.

Beispiel LLM Profiles:

```text
AGORA_LLM_PROFILE_BACKEND=postgres
```

Fehler:

```text
AGORA_LLM_PROFILE_BACKEND=sqlite
```

Voraussetzung:

SQLite wurde noch nicht gelöscht.

Dasselbe Prinzip für:

```text
Metadata
Auth
Storage
```

## Destruktive Migrationen

Erst mindestens zwei stabile Releases nach erfolgreichem Cutover.

---

# 36. CI/CD Gates

Jeder PR der Migration muss mindestens bestehen:

```text
Backend Unit Tests
Repository Contract Tests
Migration Tests
Frontend Tests
Typecheck
Lint
Build
Security Scan
E2E Smoke Test
```

## Neue spezielle Gates

### Datenmigration

Fixture:

```text
legacy fixture
    ↓ migrate
PostgreSQL
    ↓ verify
identische Fachwerte
```

### Tenant Isolation

```text
Workspace A
Workspace B
Cross-Tenant Access = 0
```

### Rollback

```text
postgres -> legacy backend flag
```

muss ohne Datenverlust starten können.

---

# 37. Security Gates

Vor Internet-Exposition:

- [ ] HTTPS
- [ ] Supabase Standard-Secrets ersetzt
- [ ] Studio nicht öffentlich
- [ ] DB-Port nicht öffentlich
- [ ] service-role niemals im Frontend
- [ ] RLS aktiv und getestet
- [ ] CORS eingeschränkt
- [ ] Auth Redirect URLs eingeschränkt
- [ ] Rate Limiting
- [ ] Login-Bruteforce-Schutz
- [ ] Audit Events
- [ ] Backup vorhanden
- [ ] Restore erfolgreich getestet
- [ ] Container keine unnötigen Privilegien
- [ ] Images gepinnt
- [ ] Dependency Scan
- [ ] Secrets Scan

---

# 38. Reihenfolge der Pull Requests

Nicht ein 20.000-Zeilen-PR.

## PR 1

```text
infra: self-hosted Supabase foundation
```

Nur Infrastruktur und Doku.

## PR 2

```text
feat(db): SQLAlchemy + Alembic foundation
```

Noch keine Fachmigration.

## PR 3

```text
feat(llm): LLM profile model + repository boundary
```

Legt `agora.llm_profiles` ohne Secrets, Workspace oder Auth-Abhängigkeiten an,
führt die Repository-Abstraktion ein und lässt SQLite als Default aktiv.

## PR 4

```text
feat(llm): PostgreSQL LLM profile adapter + data migration
```

## PR 5

```text
feat(workspaces): relational workspace model
```

## PR 6

```text
feat(projects): PostgreSQL project repository
```

## PR 7

```text
feat(sim): PostgreSQL simulation metadata repository
```

## PR 8

```text
feat(runs): PostgreSQL run repository
```

## PR 9

```text
feat(reports): PostgreSQL report metadata
```

## PR 10

```text
feat(auth): Supabase JWT provider
```

## PR 11

```text
feat(auth): workspace membership + hybrid auth
```

## PR 12

```text
security(db): workspace RLS
```

## PR 13

```text
feat(storage): blob store abstraction
```

## PR 14

```text
feat(storage): Supabase storage adapter
```

## PR 15

```text
chore(migration): cutover metadata backend
```

Erst danach pgvector-PoC.

---

# 39. Aufwand

## Nur technische Machbarkeit / PoC

```text
5–8 Arbeitstage
```

Enthält:

```text
Supabase
PostgreSQL
SQLAlchemy
Alembic
eine Pilot-Tabelle
erste Auth-Probe
```

## Sinnvolle Hybridmigration

```text
18–30 Arbeitstage
```

Enthält:

```text
PostgreSQL Business Metadata
LLM Profiles
Repositories
Migration Scripts
Grundlegende Workspaces
Storage
```

## Produktionsreif inklusive Auth/RLS/Ops

```text
30–45 Arbeitstage
```

Enthält zusätzlich:

```text
Supabase Auth
Workspace Isolation
RLS
Backup/Restore
Monitoring
Security Hardening
vollständige E2E Migrationstests
```

## Neo4j komplett ersetzen

Zusätzlich:

```text
15–30+ Arbeitstage
```

Nur nach Benchmark überhaupt anfangen.

## Gesamtrisiko

| Bereich | Risiko |
|---|---|
| Supabase parallel deployen | niedrig |
| SQLite → PostgreSQL | niedrig |
| Projektmetadaten | mittel |
| Simulation-Metadaten | mittel |
| Storage | niedrig-mittel |
| Auth | mittel |
| RLS | hoch |
| Redis ersetzen | unnötig |
| Neo4j ersetzen | hoch |

---

# 40. Empfohlener Meilensteinplan

## M1 – Infrastruktur steht

Ergebnis:

```text
Supabase läuft parallel.
Agora ist unverändert funktionsfähig.
PostgreSQL ist aus Flask erreichbar.
```

## M2 – Erste Daten in PostgreSQL

Ergebnis:

```text
Das LLM-Profil-Schema und die Repository-Abstraktion sind aktiv.
SQLite bleibt bis PR 4 Default; Datenmigration und Rollback funktionieren dort.
```

## M3 – Business Metadata

Ergebnis:

```text
Projects
Simulations
Runs
Reports
```

liegen in PostgreSQL.

Neo4j/Redis unverändert.

## M4 – Multi-User

Ergebnis:

```text
Supabase Auth
Users
Workspaces
Membership
Hybrid Auth
```

## M5 – Isolation

Ergebnis:

```text
RLS
Tenant Tests
Audit
```

## M6 – Blob Storage

Ergebnis:

```text
Uploads/Exports in Supabase Storage
Metadaten in PostgreSQL
```

## M7 – Produktionsbetrieb

Ergebnis:

```text
Backups
Restore
Monitoring
Security
Runbooks
```

## M8 – Graph-Evaluierung

Ergebnis:

```text
Neo4j vs PostgreSQL/pgvector Benchmark
```

Danach erst Entscheidung über Neo4j.

---

# 41. Definition of Done für die Gesamtmigration

Die Hybridmigration gilt als abgeschlossen, wenn:

- [ ] Flask bleibt einzige fachliche API
- [ ] Benutzer authentifizieren sich über Supabase Auth
- [ ] Workspace-Isolation ist technisch getestet
- [ ] PostgreSQL ist Source of Truth für Business-Metadaten
- [ ] Neo4j ist Source of Truth für Graphdaten
- [ ] Redis ist Source of Truth für Live-Event-/RPC-Transport
- [ ] Storage enthält Blob-Artefakte
- [ ] keine wichtigen Daten hängen mehr von zufälligen lokalen Pfaden ab
- [ ] alle Migrationen sind versioniert
- [ ] Backup und Restore funktionieren
- [ ] Legacy-Stores können kontrolliert entfernt werden
- [ ] API-Verträge des Frontends sind weiterhin stabil
- [ ] E2E-Tests sind grün
- [ ] Security Tests für Cross-Workspace-Zugriffe sind grün
- [ ] Betriebsdokumentation existiert

---

# 42. Meine konkrete Empfehlung

## Jetzt bauen

```text
1. Supabase parallel
2. SQLAlchemy + Alembic
3. LLM Profiles als Pilot
4. Workspaces
5. Projects / Simulations / Runs / Reports
6. Supabase Auth
7. RLS
8. Supabase Storage
9. Backup/Restore
```

## Jetzt nicht bauen

```text
PostgresGraphStorage
Redis-Ersatz
Edge-Functions-Umbau
Frontend-Direktzugriff auf alle Tabellen
komplettes Realtime-Redesign
```

## Später messen

```text
pgvector
Postgres Full Text Search
Graph Traversal Performance
Neo4j-Betriebsaufwand
```

---

# 43. Wichtigster Architekturentscheid

Die zentrale Grenze sollte lauten:

```text
Supabase ist Infrastruktur.
Agora bleibt das Produkt.
```

Damit kann Supabase später notfalls ersetzt werden, ohne dass die gesamte Fachlogik neu geschrieben werden muss.

PostgreSQL bleibt Standard-PostgreSQL, Auth und Storage sitzen hinter Adaptern, Neo4j und Redis behalten die Aufgaben, für die sie heute bereits sinnvoll eingesetzt werden.

Das ist die Variante mit dem besten Verhältnis aus Nutzen, Risiko, Wartbarkeit und späterer SaaS-Fähigkeit.
