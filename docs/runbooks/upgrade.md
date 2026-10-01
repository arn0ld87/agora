# Runbook: Upgrade zwischen Release-Linien

Zugehöriges Issue: [#1673](https://github.com/arn0ld87/agora/issues/1673) (Release-Gate vor `0.10.0-rc.1`, siehe [`../../ROADMAP.md`](../../ROADMAP.md)).
**Stand:** 30.09.2026, Produktversion `0.9.6` ([`VERSION`](../../VERSION)). `0.10.0-rc.1` ist noch nicht geschnitten.

## Warum dieses Runbook existiert

Ein Upgrade besteht in Agora aus mehr als einem neuen Image: Ab `0.10` gehören ein PostgreSQL-Schema, fünf Umschalter für die Metadaten-Ablage und ein Supabase-Stack dazu. Die Einzelheiten stehen in Runbooks pro Thema. Dieses Dokument ist der **Einstieg** je Versionssprung: Es nennt die Reihenfolge, den Kurzbefehl je Schritt, die Prüfung und den Rückweg, und verweist für alles Weitere auf das Detail-Runbook. Es dupliziert deren Inhalt nicht.

| Sprung | Stand | Abschnitt |
|---|---|---|
| `0.9.x` → `0.10` | beschrieben | [unten](#09x--010) |
| `0.10` → `1.0` | Platzhalter, wird im Freeze gefüllt | [unten](#010--10) |

## Was dieses Runbook nicht ist

- **Kein Betriebsnachweis.** Belegt sind der reale Cutover auf armserver am 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592), Protokoll im Issue) und das CI-Gate [#1589](https://github.com/arn0ld87/agora/issues/1589) (Migration und Rückweg gegen PostgreSQL). Ein Fresh-Host-Restore mit vollem Supabase-Stack ist es nicht: Der Drill [#766](https://github.com/arn0ld87/agora/issues/766) ist offen, und ein trockenes Runbook ersetzt ihn nicht ([`../agents/release-priority.md`](../agents/release-priority.md)).
- **Keine Pflege-Ausrede.** Ändert ein PR Persistenz, Migrationen, Env-Defaults oder den Compose-Stack, zieht er dieses Runbook im selben PR nach ([`../../AGENTS.md`](../../AGENTS.md), Abschnitt „Arbeitsweise“).

---

## Persistenz-Änderungen außerhalb des Versionssprungs

Nicht jede neue persistierte Ablage gehört zu `0.9.x → 0.10` oder `0.10 → 1.0` — dieser Abschnitt sammelt Persistenz-Änderungen, die ein PR unabhängig vom Postgres-Umstieg eingeführt hat (AGENTS.md, Abschnitt „Arbeitsweise“, Punkt 6).

**Neuer `jev`-Eintrag im Provider-Secret-Store** (f005, Slice `jev-key-cli`). `backend/data/llm_provider_secrets.json` (Fernet-verschlüsselt mit `AGORA_SECRET_KEY`) bekommt neben den bestehenden LLM-Chat-Provider-Keys (`openai`, …) eine weitere, eigene Ref `jev` (`app.services.decisions.jev_provider.JEV_SECRET_REF`) für den TypeSafe-API-Key des Jev-Decision-Piloten.

- **Provisionierung:** `backend/scripts/bind_decision_secret.py jev` (nie `llm-secrets-doctor.py`, das akzeptiert jede `provider_id` und könnte versehentlich einen LLM-Chat-Key überschreiben). Details, inklusive Container-Aufruf: [`decision-secrets.md`](decision-secrets.md).
- **Entfernen:** `bind_decision_secret.py jev --delete`, danach zwingend `docker compose restart agora` — der Backend-Prozess cacht den Jev-Client samt Key, das Löschen des Store-Eintrags allein widerruft ihn operativ nicht.
- **Rollback-Implikation:** Ein Rückweg auf eine Agora-Version ohne Jev-Pilot lässt den `jev`-Eintrag in derselben Store-Datei unberührt zurück (keine Schema-Migration nötig — zusätzliche Ref im selben JSON-Objekt). Ein Master-Key-Wechsel (`AGORA_SECRET_KEY` rotieren) re-encryptet über `llm-secrets-doctor.py rotate` wie jeden anderen Eintrag auch automatisch mit.
- **Master-Key-Prüfung vor dem Schreiben:** Seit dieser Slice verweigert `bind_decision_secret.py` das Binden/Überschreiben, wenn der aktuelle `AGORA_SECRET_KEY` einen bereits vorhandenen Store-Eintrag nicht entschlüsseln kann (Exit `2`) — ein syntaktisch gültiger, aber falscher Master-Key hätte sonst klaglos überschrieben und den vorherigen Ciphertext unwiederbringlich verloren.

## Env-Default-Änderungen außerhalb des Versionssprungs

Nicht jede neue Umgebungsvariable gehört zu `0.9.x → 0.10` oder `0.10 → 1.0` — dieser Abschnitt sammelt Env-Defaults, die ein PR unabhängig vom Postgres-Umstieg eingeführt hat (AGENTS.md, Abschnitt „Arbeitsweise“, Punkt 6).

**`AGORA_DECISION_LAYER_MODE`** (f005/ADR-0016, Jev-Decision-Pilot). Default `disabled` — kein Verhaltenswechsel. `shadow` lässt zusätzlich einen `RuleProvider` parallel mitlaufen (nur Telemetrie). `authoritative` schaltet für den Use Case `local-search-relevance` echten Jev-Betrieb scharf: Jev entscheidet, `RuleProvider` ist Rückfall bei jedem Jev-Fehler/fehlendem Key. Ein Upgrade ändert diesen Wert nie automatisch — ein Betreiber, der `authoritative` setzt, sendet damit Suchanfrage und bestbewerteten Fakt im Klartext an TypeSafe (Maintainer-Datenschutzfreigabe 30.09.2026, Alexander Schneider, beschränkt auf genau diesen Modus mit Rule-Rückfall). Siehe [`../STATUS.md`](../STATUS.md), Abschnitt „Decision Layer (Jev-Pilot)“.

**`AGORA_JEV_TIMEOUT_S`** (float, Default `2.0`, gültiger Bereich `0 < Wert <= 30`, von `Config.validate()` erzwungen). Timeout-Budget für genau einen Jev-Aufruf im `authoritative`-Pfad. Wirkt nur, wenn `AGORA_DECISION_LAYER_MODE=authoritative` gesetzt ist; da `local-search-relevance` ein heißer Retrieval-Pfad ist, blockiert ein hängender Jev-Aufruf lokale Suchen höchstens um dieses Budget (plus ein interner Retry mit demselben Timeout), bevor der Rule-Rückfall greift. Kein Upgrade-Schritt nötig — reiner Opt-in über `AGORA_DECISION_LAYER_MODE`.

---

## 0.9.x → 0.10

### Was sich ändert

| Bereich | Änderung | Aktion |
|---|---|---|
| Metadaten-Ablage | fünf Domänen (LLM-Profile, Projekte, Simulationen, Runs, Reports) können in PostgreSQL liegen, Schema `agora`, per Alembic | Schritte 3 bis 9 |
| Supabase-Stack | eigenes Compose-Projekt unter [`supabase/`](../../supabase/README.md), PostgreSQL 17 hinter Supavisor | Schritt 3 |
| Neo4j, Redis, Artefakte unter `uploads/` | unverändert. Blob-Ablage hat keinen Adapter ([#1584](https://github.com/arn0ld87/agora/issues/1584), [#1586](https://github.com/arn0ld87/agora/issues/1586)) | keine |
| Supabase-Auth, JWT, Realtime, Workspaces | im Code inaktiv. `AGORA_AUTH_BACKEND=hybrid` verhält sich ohne `AGORA_SUPABASE_JWT_ISSUER` wie `legacy`, `AGORA_SUPABASE_REALTIME` ist aus. Multi-User folgt erst nach 1.0 (ADR-0019) | keine, nicht setzen |

**Die Umschalter stehen im Code auf Legacy und müssen explizit gesetzt werden.** Das sind die Werte aus `backend/app/config.py` und [`.env.example`](../../.env.example):

| Schalter | Code-Default (Legacy) | Ziel nach dem Upgrade | Rückweg-Wert |
|---|---|---|---|
| `AGORA_LLM_PROFILE_BACKEND` | `sqlite` | `postgres` | `sqlite` |
| `AGORA_PROJECT_BACKEND` | `file` | `postgres` | `file` |
| `AGORA_SIMULATION_BACKEND` | `file` | `postgres` | `file` |
| `AGORA_RUN_BACKEND` | `file` | `postgres` | `file` |
| `AGORA_REPORT_BACKEND` | `file` | `postgres` | `file` |

`AGORA_METADATA_BACKEND` bleibt `legacy`; maßgeblich sind die fünf Einzel-Schalter. Ob `0.10.0` die Defaults auf `postgres` dreht, ist **noch nicht festgelegt** (siehe [Offene Lücken](#offene-lücken), [#1654](https://github.com/arn0ld87/agora/issues/1654)). Wer die Schalter nicht setzt, bleibt mit dem neuen Stand auf den Legacy-Ablagen.

### Voraussetzungen

- Eine laufende `0.9.x`-Installation mit Legacy-Ablage, Zugriff auf Host, Docker und `uv`.
- Docker-Host, dessen `nofile`-Limit Supavisor erlaubt ([`supabase/README.md`](../../supabase/README.md), Abschnitt „Voraussetzungen“).
- Ein **Wartungsfenster** für Schritt 5 bis 8. Agora bleibt von der ersten Übertragung bis zum Neustart mit den neuen Schaltern angehalten ([`metadata-postgres-cutover.md`](metadata-postgres-cutover.md)).
- Der Secret-Wert `AGORA_SECRET_KEY` bleibt **derselbe**. Eine Rotation ohne Neuverschlüsselung macht die migrierten Profil-Schlüssel unbrauchbar ([`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md), Abschnitt „Der Sonderfall Schlüssel“).
- Secret-Werte kommen aus dem Secret-Store des Betreibers, nie in einen Commit, ein Log oder einen Chat.

### 1. Backup, mit geprobtem Restore

Vor jeder Änderung Dateiverzeichnisse und Neo4j sichern. Läuft der Stack mit mehreren Compose-Dateien, muss vorher `COMPOSE_FILE` genau diese Dateien nennen ([`restore-drill.md`](restore-drill.md), Abschnitt „Durchführung“).

```bash
bash scripts/restore-drill.sh --phase backup --backup-dir /srv/agora-backup
```

Neo4j ist für die Dauer des Dumps gestoppt. Solange kein Schalter auf `postgres` steht, ist der PostgreSQL-Teil des Backups ein No-Op. Der Restore muss vor dem Cutover geprobt sein, und zwar aus Sicht der Verifikation:

```bash
cd backend
uv run python scripts/restore_verify.py --data-dir uploads --store-dir data
```

Exit `0` ist bestanden. Exit `2` (etwas blieb ungeprüft) ist **kein** Erfolg. Einzelheiten und der vollständige Drill: [`restore-drill.md`](restore-drill.md), Verfahren in [`../backup-restore.md`](../backup-restore.md).

**Rückweg:** entfällt, der Schritt verändert nichts außer dem Backup-Verzeichnis.

### 2. Ziel-Stand einspielen, Schalter noch auf Legacy

Erst den Code, dann die Daten. Checkout oder Image des Ziel-Stands ausrollen, **ohne** einen Schalter zu setzen, und prüfen, dass die Installation wie zuvor läuft. Damit bleibt der Rückweg für den Code ein Tag-Wechsel. Den bisherigen Stand notieren (Image-Tag oder Commit).

Für Images aus GHCR: [`ghcr-deploy.md`](ghcr-deploy.md) (feste `sha-<7>`- oder `vX.Y.Z`-Tags, nie `edge`/`latest`). Für den lokalen Build: [`../deployment-prod-like.md`](../deployment-prod-like.md).

Das laufende Image und der Checkout, aus dem die Migration läuft, müssen **denselben Alembic-Head** kennen. Sonst bricht das Start-Gate ([#1582](https://github.com/arn0ld87/agora/issues/1582)) nach dem Umschalten ab, und der Container startet in einer Schleife neu (so geschehen bei #1592):

```bash
cd backend && uv run alembic -c migrations/alembic.ini heads
docker compose exec -T agora sh -c \
  'cd /app/backend && .venv/bin/alembic -c migrations/alembic.ini heads'
```

Beide Ausgaben müssen dieselbe Revision zeigen ([`metadata-postgres-cutover.md`](metadata-postgres-cutover.md), Abschnitt „Image und Checkout auf denselben Head prüfen“).

**Rückweg:** vorherigen Image-Tag oder Commit setzen und neu starten ([`ghcr-deploy.md`](ghcr-deploy.md), Abschnitt „Rollback“). Bis hier sind keine Daten angefasst.

### 3. Supabase-Stack aufsetzen

Ausführlich: [`supabase/README.md`](../../supabase/README.md), Abschnitt „Einrichtung“. Die Reihenfolge ist zwingend, `bootstrap.sh` kommt **vor** dem ersten `docker compose up`.

```bash
cd supabase
./bootstrap.sh                        # holt die Fremdkonfiguration nach volumes/ (gepinnter Commit)
cp .env.example .env                  # jedes Secret-Feld füllen, siehe README
docker network create agora-backend   # einmalig pro Host
docker compose up -d
curl -f -H "apikey: $ANON_KEY" http://127.0.0.1:8000/auth/v1/health
```

Der `apikey`-Header ist Pflicht, das Gateway antwortet sonst mit 401. Läuft der Stack, hängt das Overlay Agora ans gemeinsame Netz (weitere Overlays wie Prod, Proxy oder Host-Overlay bleiben dabei, das GHCR-Overlay steht als letztes `-f`, siehe [`ghcr-deploy.md`](ghcr-deploy.md)):

```bash
cd ..
docker compose -f docker-compose.yml \
  -f deploy/compose/docker-compose.supabase.yml up -d
```

Aus dem Agora-Container sind dann `api-gw:8000` und `supavisor:5432` erreichbar. Redis und Neo4j bleiben außerhalb von `agora-backend`.

Wer auf einem Host bereits einen self-hosted Supabase-Stack betreibt, kann Agora dort als eigenes Schema `agora` ansiedeln, wie auf armserver ([`../STATUS.md`](../STATUS.md), Abschnitt „Metadaten-Cutover armserver (#1592)“). Dann entfallen `bootstrap.sh` und der eigene Stack, alle übrigen Schritte gelten.

#### Sicherheitsminimum (Teilmenge aus Plan §37)

Plan [`§37 „Security Gates“`](../plans/supabase.md) gilt „vor Internet-Exposition“. Für die Einrichtung im Einzelnutzer-Betrieb (JWT und offene Registrierung bleiben aus, ADR-0019) sind aus §37 diese Punkte im Repo belegt und hier verbindlich:

- [ ] Standard-Secrets ersetzt: kein Secret-Feld in `supabase/.env` bleibt leer. `POSTGRES_PASSWORD` nur aus `[A-Za-z0-9]` (`openssl rand -hex 32`).
- [ ] `SERVICE_ROLE_KEY` nur in der Backend-Umgebung, nie im Frontend, in einem Image oder in einem Log.
- [ ] DB-Port und Studio nicht öffentlich: alle Host-Ports bleiben an `127.0.0.1` gebunden, nach außen geht nur das Gateway über den Reverse Proxy ([`supabase/README.md`](../../supabase/README.md), Abschnitt „Exposition“).
- [ ] Images gepinnt: `SUPABASE_REF` in `bootstrap.sh` und die Image-Tags in `supabase/.env.example` passen zusammen.
- [ ] Backup vorhanden und Restore geprobt (Schritt 1).
- [ ] RLS aktiv: kommt mit Alembic (Schritt 4); die Laufzeitrolle ohne RLS-Umgehung steht in Schritt 4.

Die übrigen §37-Punkte (HTTPS, CORS, Redirect-URLs, Rate-Limits, Login-Bruteforce, Audit) betreffen Internet-Exposition und offene Registrierung: [`offene-registrierung.md`](offene-registrierung.md), [`../security-hardening.md`](../security-hardening.md). Welche §37-Punkte für `0.10` verbindlich sind, ist nirgends festgelegt (siehe [Offene Lücken](#offene-lücken)).

**Rückweg:** solange Agora den Stack nicht nutzt, lässt er sich ersatzlos entfernen ([`supabase/README.md`](../../supabase/README.md), Abschnitt „Rückbau“). Dort steht auch, warum das `down -v` nur mit ausdrücklich benannter Compose-Datei läuft: Ein nacktes `docker compose down -v` im Repository-Root löscht die Volumes von Redis und Neo4j.

### 4. Datenbank-URL, Rollen und Schema

`DATABASE_URL` hat keinen Default und muss mit `postgresql+psycopg://` beginnen. Der Benutzername trägt am Pooler die Tenant-ID als Suffix (`postgres.<POOLER_TENANT_ID>`). Zwei Formen laut [`.env.example`](../../.env.example): `supavisor:5432` im Container, `127.0.0.1:5432` für Skripte auf dem Host.

Empfohlen ist die Trennung in eine Owner-Rolle (Alembic, Backup, `AGORA_MIGRATION_DATABASE_URL`) und die Laufzeitrolle `agora_app` ohne `BYPASSRLS` (`DATABASE_URL`). Einmandantig ist sie nicht erzwungen. Einrichtung und Prüfung: [`rls-rollen.md`](rls-rollen.md).

Schema auf den Head bringen:

```bash
cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

`alembic upgrade head` nimmt `AGORA_MIGRATION_DATABASE_URL`, falls gesetzt, sonst `DATABASE_URL`. Fehlt dieser Schritt, existieren die `agora.*`-Tabellen nicht, und jede Übertragung bricht ab, statt eine Tabelle zu raten ([`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md)).

**Rückweg:** solange nichts umgeschaltet ist, lässt sich das Schema mit `alembic downgrade` zurücknehmen. Die Ziel-Revisionen je Domäne stehen in der Tabelle von [`metadata-postgres-cutover.md`](metadata-postgres-cutover.md); `downgrade` auf die Revision **vor** der Domäne löscht deren Tabelle samt Inhalt und alle späteren. Für RLS: `alembic downgrade 14d60476b8ce` ([`rls-rollen.md`](rls-rollen.md), Abschnitt „Rückweg“).

### 5. Agora anhalten, Baseline vorher

```bash
docker compose stop agora
cd backend
uv run python scripts/migration_baseline.py --output /tmp/vorher.json
```

Laufende Graph-Builds, Simulationen und Report-Erzeugungen vorher beenden oder abbrechen. Das Manifest enthält keine Secrets, aber die vollständige ID-Liste der Installation: neben das Backup legen, nicht committen ([`migration-baseline.md`](migration-baseline.md)).

**Rückweg:** `docker compose up -d agora`. Es wurde nichts verändert.

### 6. Legacy → PostgreSQL übertragen

Die Reihenfolge folgt den Fremdschlüsseln und ist **nicht verhandelbar**: LLM-Profile → Projekte → Simulationen → Runs → Reports. Jedes Skript zählt vorher mit `--dry-run`, überträgt idempotent (bekannte Kennungen werden übersprungen, nie überschrieben) und prüft mit `--verify` feldweise. Erst weiter, wenn `--verify` Exit 0 liefert. Meldet ein Skript `Failed > 0`, erklärt das Detail-Runbook die Fehlerarten.

Die Skripte laufen im Verzeichnis `backend/` in der Umgebung des Backends (`DATABASE_URL`, für Profile zusätzlich `AGORA_SECRET_KEY`).

#### 6.1 LLM-Profile

```bash
uv run python scripts/migrate_llm_profiles_to_postgres.py --dry-run
uv run python scripts/migrate_llm_profiles_to_postgres.py
uv run python scripts/migrate_llm_profiles_to_postgres.py --verify
```

Detail: [`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md). Die Profil-Schlüssel wandern in den Fernet-Store `llm_profile_secrets.json`.

**Rückweg:** `AGORA_LLM_PROFILE_BACKEND=sqlite`. `instance/llm_profiles.db` wird nur mit `mode=ro` gelesen und bleibt unverändert; neu hinzugekommen ist nur der Fernet-Store. Profile, die nach dem Umschalten in PostgreSQL entstanden oder geändert wurden, fehlen in der SQLite.

#### 6.2 Projekte

```bash
uv run python scripts/migrate_projects_to_postgres.py --dry-run
uv run python scripts/migrate_projects_to_postgres.py
uv run python scripts/migrate_projects_to_postgres.py --verify
```

Detail: [`projekt-postgres-umstellung.md`](projekt-postgres-umstellung.md).

**Rückweg:** `AGORA_PROJECT_BACKEND=file`. Die `project.json`-Dateien wurden nie verändert. Nach dem Umschalten in PostgreSQL entstandene Änderungen fehlen dort.

#### 6.3 Simulationen

```bash
uv run python scripts/migrate_simulations_to_postgres.py --dry-run
uv run python scripts/migrate_simulations_to_postgres.py
uv run python scripts/migrate_simulations_to_postgres.py --verify
```

Voraussetzung: Projekte migriert und verifiziert. Detail: [`simulation-postgres-umstellung.md`](simulation-postgres-umstellung.md).

**Rückweg:** `AGORA_SIMULATION_BACKEND=file`, aber erst **nach** dem Rückweg von Runs und Reports. Die `state.json`-Dateien wurden nie verändert.

#### 6.4 Runs

```bash
uv run python scripts/migrate_runs_to_postgres.py --dry-run
uv run python scripts/migrate_runs_to_postgres.py
uv run python scripts/migrate_runs_to_postgres.py --verify
```

Voraussetzung: Simulationen migriert und verifiziert. Detail: [`run-postgres-umstellung.md`](run-postgres-umstellung.md).

**Rückweg:** `AGORA_RUN_BACKEND=file`. Die Manifeste unter `uploads/run_registry/` wurden nie verändert. Runs, die nach dem Umschalten entstanden, fehlen dort.

#### 6.5 Reports

```bash
uv run python scripts/migrate_reports_to_postgres.py --dry-run
uv run python scripts/migrate_reports_to_postgres.py
uv run python scripts/migrate_reports_to_postgres.py --verify
```

Voraussetzung: Simulationen migriert und verifiziert. Detail: [`report-postgres-umstellung.md`](report-postgres-umstellung.md).

**Rückweg:** `AGORA_REPORT_BACKEND=file`. Die `meta.json`-Dateien wurden nie verändert. Reports, die nach dem Umschalten entstanden, haben Inhalte unter `uploads/reports/`, aber keine `meta.json` und sind nach dem Rückweg nicht sichtbar.

### 7. Sammelprüfung

Baseline nachher, dann alle Prüfungen in Cutover-Reihenfolge. Die Sammelprüfung darf **vor** dem Umschalten laufen; die Ziel-Schalter werden dafür für den Aufruf gesetzt:

```bash
uv run python scripts/migration_baseline.py --output /tmp/nachher.json
AGORA_LLM_PROFILE_BACKEND=postgres AGORA_PROJECT_BACKEND=postgres \
AGORA_SIMULATION_BACKEND=postgres AGORA_RUN_BACKEND=postgres \
AGORA_REPORT_BACKEND=postgres \
uv run python scripts/verify_metadata_cutover.py --baseline /tmp/vorher.json /tmp/nachher.json
```

Exit `0` nur, wenn jeder Schritt `OK` ist. Exit `1`: mindestens ein `FEHLER`. Exit `2`: nichts rot, aber etwas `UNGEPRÜFT` (etwa Neo4j nicht erreichbar). Ein ungeprüfter Schritt ist kein Erfolg. Was jeder Schritt prüft: [`metadata-postgres-cutover.md`](metadata-postgres-cutover.md), Abschnitt „Baseline nachher und Sammelprüfung“.

**Rückweg:** entfällt, das Skript liest nur.

### 8. Umschalten und neu starten

Alle fünf Schalter in der Umgebung der Installation (`.env`) setzen, dann neu starten. Die Schalter werden beim Import der `Config` einmal gelesen; ohne Neustart greift nichts.

```bash
AGORA_LLM_PROFILE_BACKEND=postgres
AGORA_PROJECT_BACKEND=postgres
AGORA_SIMULATION_BACKEND=postgres
AGORA_RUN_BACKEND=postgres
AGORA_REPORT_BACKEND=postgres
```

```bash
docker compose up -d agora
```

`Config.validate()` verweigert den Start, wenn ein Schalter auf `postgres` steht und seine Voraussetzung nicht (`DATABASE_URL`, Fremdschlüssel-Reihenfolge). Das Start-Gate bricht ab, wenn das Schema nicht auf dem Head steht.

**Rückweg:** siehe [Rollback](#rollback-09x--010), Stufe 2.

### 9. Prüfen und Backup nachher

```bash
curl -fsS http://127.0.0.1:${AGORA_BACKEND_PORT:-5001}/readyz
```

Der Check `postgres` muss `ok` melden (`disabled` hieße: kein Schalter greift). Danach die Punkte „Prüfen, dass die Oberfläche arbeitet“ der fünf Detail-Runbooks nacheinander abarbeiten (Profilliste, Projektliste, Simulationsliste und Zweig, Run-Übersicht und Resume, Report-Liste und Export).

Dann ein Backup, das PostgreSQL enthält (`postgres.dump` und `postgres-manifest.json`, sobald ein Schalter auf `postgres` steht):

```bash
bash scripts/restore-drill.sh --phase backup --backup-dir /srv/agora-backup-nachher
```

Ein Datensatz, der beim Übertragen nicht ankam, ist nach dem Umschalten nicht mehr sichtbar. Deshalb sind Schritt 6 und 7 vor dem Umschalten vollständig durchzuarbeiten. Das Löschen der Legacy-Ablagen kommt frühestens zwei stabile Releases nach dem Cutover (Plan §35).

### Rollback (0.9.x → 0.10)

| Stufe | Situation | Weg | Daten |
|---|---|---|---|
| 1 | vor Schritt 8, nichts umgeschaltet | Agora starten (`docker compose up -d agora`). Optional Schema per `alembic downgrade` zurück und Supabase-Stack entfernen (Schritt 3, 4). | Legacy-Ablagen sind unberührt und die Wahrheit. |
| 2 | nach Schritt 8, Stunden bis wenige Tage | Schalter **in umgekehrter Reihenfolge** zurück, dann neu starten (unten). | Legacy-Daten sind unberührt, aber alles, was nur in PostgreSQL entstand oder geändert wurde, fehlt. |
| 3 | Code-Fehler im neuen Stand | vorherigen Image-Tag oder Commit ausrollen ([`ghcr-deploy.md`](ghcr-deploy.md), Abschnitt „Rollback“). | Macht keine Datenmigration und keine Alembic-Revision rückgängig. Stehen Schalter auf `postgres`, vorher Stufe 2 ausführen: Ein Stand ohne Postgres-Adapter liest nur die Legacy-Ablagen. |
| 4 | Daten unbrauchbar | Restore aus dem Backup aus Schritt 1 ([`restore-drill.md`](restore-drill.md), [`../backup-restore.md`](../backup-restore.md)). | Stand des Backups. Der Restore ist als Drill noch nicht nachgewiesen (#766). |

Stufe 2, in dieser Reihenfolge, sonst verweigert `Config.validate()` den Start:

```bash
export AGORA_REPORT_BACKEND=file
export AGORA_RUN_BACKEND=file
export AGORA_SIMULATION_BACKEND=file
export AGORA_PROJECT_BACKEND=file
export AGORA_LLM_PROFILE_BACKEND=sqlite
```

Ein Teil-Rückweg ist möglich, solange die Reihenfolge stimmt (Reports allein zurück geht, Simulationen allein nicht, solange Runs oder Reports auf `postgres` stehen). Der Rückweg ist für die ersten Stunden nach dem Cutover gedacht, nicht für Wochen später: Eine Migration in Gegenrichtung (PostgreSQL → Legacy) gibt es nicht ([`metadata-postgres-cutover.md`](metadata-postgres-cutover.md), Abschnitt „Rückweg“; [`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md), Abschnitt „Der Rückweg“). Der Ablauf Umschalten und Zurück ist als CI-Gate belegt (#1589).

---

## 0.10 → 1.0

**Platzhalter.** Dieser Abschnitt wird im Freeze vor `1.0.0-rc.1` gefüllt (ROADMAP: „RC-Notes und Upgrade-Hinweise nach [#1673](https://github.com/arn0ld87/agora/issues/1673)“). `0.10.0` stabil ist die Upgrade-Quelle für 1.0.

Noch nicht festgelegt, Eingaben für den Abschnitt:

- Ob und wie sich die Code-Defaults der Metadaten-Schalter ändern und wie der 1.0-Install-Pfad mit vollem Supabase-Stack aussieht ([#1654](https://github.com/arn0ld87/agora/issues/1654)).
- `schema_version` für Dateiartefakte ([#1663](https://github.com/arn0ld87/agora/issues/1663)) und die Kompatibilitäts- und Deprecation-Policy ([#1664](https://github.com/arn0ld87/agora/issues/1664)).
- Der Fresh-Host-Install/Restore als Nachweis ([#766](https://github.com/arn0ld87/agora/issues/766), [#1659](https://github.com/arn0ld87/agora/issues/1659)).

---

## Offene Lücken

Was im Repository nicht belegt ist, steht hier statt als Behauptung im Ablauf:

- **Zielversion:** `0.10.0-rc.1` und `0.10.0` sind nicht getaggt. Der Ziel-Stand in Schritt 2 ist bis dahin ein Commit von `main`, kein Tag.
- **Default-Umstellung:** Ob `0.10.0` die fünf `AGORA_*_BACKEND`-Defaults auf `postgres` dreht, ist noch nicht festgelegt ([#1654](https://github.com/arn0ld87/agora/issues/1654)). Im Code sind die Legacy-Defaults aktiv ([`../STATUS.md`](../STATUS.md), Abschnitt „0.10-Blocker aus heutiger Sicht“).
- **§37-Teilmenge:** Die Auswahl im Sicherheitsminimum ist aus `supabase/README.md`, Plan §37 und ADR-0018 abgeleitet. Eine verbindliche Liste für `0.10` gibt es nicht.
- **Fresh-Host-Nachweis:** Der Restore-Drill ([#766](https://github.com/arn0ld87/agora/issues/766)) ist nicht durchgeführt. Der reale Cutover (#1592) lief mit dem bestehenden Supabase des Hosts, nicht mit dem Stack aus `supabase/`; dessen Fresh-Install ist noch nicht nachgewiesen.
- **`agora_app` hinter Supavisor:** [`rls-rollen.md`](rls-rollen.md) zeigt die Laufzeit-URL ohne Tenant-Suffix. Wie der Benutzername der Rolle am Pooler lautet, ist dort nicht ausgeführt.
- **Compose-Servicename:** Die Detail-Runbooks schreiben `docker compose stop backend` mit dem Zusatz „oder der für die Installation übliche Weg“. Der Service in `docker-compose.yml` heißt `agora`, dieses Runbook nutzt ihn.
- **Dateiartefakt-Schemas:** Eine Migration bestehender Dateiartefakte auf neue Schema-Versionen ist nicht Teil des Sprungs ([#1663](https://github.com/arn0ld87/agora/issues/1663) offen).
