# Supabase self-hosted für Agora

Eigenes Compose-Projekt neben dem Agora-Stack. Umsetzung von Phase 1 des
Migrationsplans [`docs/plans/supabase.md`](../docs/plans/supabase.md) §7:
Supabase läuft parallel, **Agora hängt fachlich noch nicht davon ab**.

In dieser Phase entsteht kein Anwendungscode. Was hier steht, ist Infrastruktur
und Betrieb — die SQLAlchemy-/Alembic-Grundlage kommt in Phase 2 (§8), das
Datenmodell in Phase 3 (§9).

## Warum ein zweites Compose-Projekt

Den kompletten Supabase-Stack in `docker-compose.yml` von Agora zu ziehen würde
zwei Lebenszyklen verkleben: ein Supabase-Update träfe dann jeden `docker
compose up` des Hauptstacks. Zwei Projekte, ein gemeinsames externes Netz.

```text
agora/
  docker-compose.yml          # Agora, Redis, Neo4j
supabase/
  docker-compose.yml          # dieser Stack
```

## Dienste

Enthalten:

| Dienst | Container | Rolle |
|---|---|---|
| `db` | `agora-supabase-db` | PostgreSQL 17, ab Phase 3 Source of Truth für App-Metadaten |
| `supavisor` | `agora-supabase-pooler` | Connection Pooler; Flask verbindet im Session Mode (§7) |
| `auth` | `agora-supabase-auth` | GoTrue; fachlich erst ab Phase 6 (§14) |
| `rest` | `agora-supabase-rest` | PostgREST für Studio und später das Frontend |
| `storage` | `agora-supabase-storage` | Artefakt-Ablage ab Phase 7 (§19) |
| `meta` | `agora-supabase-meta` | Schema-Introspektion für Studio |
| `studio` | `agora-supabase-studio` | Admin-UI, nur intern erreichbar |
| `realtime` | `realtime-dev.supabase-realtime` | Änderungen der Listen-Tabellen an den Browser (§23, #1618), nur über das Gateway |
| `api-gw` | `agora-supabase-gateway` | Envoy als API-Gateway, einziger Eingang |

Bewusst **nicht** enthalten (§7, „je weniger Container am Anfang, desto weniger
bewegliche Teile"): Edge Runtime, imgproxy, Analytics/Logflare.

Folgen davon:

- `/functions/v1` antwortet am Gateway mit 503. Der Envoy-Cluster existiert
  in der mitgelieferten Konfiguration, sein Host nicht — Envoy startet
  trotzdem (`STRICT_DNS`, Cluster bleibt leer).
- Storage läuft mit `ENABLE_IMAGE_TRANSFORMATION=false`.
- Die Log-Ansichten in Studio bleiben leer.

`PGRST_DB_SCHEMAS` führt in dieser Phase **kein** `agora` — das Schema entsteht
erst in Phase 3 (§9), und ein nicht existierendes Schema lässt PostgREST
dauerhaft unhealthy in einer Retry-Schleife laufen. Mit der ersten
Alembic-Migration wird die Liste erweitert.

Ein Dienst wird nachgezogen, wenn er gebraucht wird — nicht vorsorglich.

## Einrichtung

### Voraussetzungen

Der Supavisor-Container verlangt `nofile` ≥ 100000: das Image startet über
`/app/limits.sh` mit `RLIMIT_NOFILE=100000` und unter `set -euo pipefail`
stirbt der Start, wenn der Container sein Limit nicht anheben darf. Das
Compose setzt deshalb für den Service `ulimits.nofile` auf 100000/100000 —
Hosts mit restriktiven Docker-Defaults (`default-ulimits.nofile` in
`/etc/docker/daemon.json`, z. B. 65536) fallen sonst in eine
Restart-Schleife.

### 1. Konfiguration holen

`docker-compose.yml` hängt Supabase-Konfiguration unter `volumes/` ein:
DB-Init-SQL, die Envoy-Gateway-Konfiguration und die Supavisor-Config. Diese
Dateien stammen aus [supabase/supabase](https://github.com/supabase/supabase)
(Apache-2.0) und liegen **nicht** im Agora-Repository — rund 1500 Zeilen
Fremdkonfiguration, die bei jedem Supabase-Update nachgezogen und reviewt
werden müssten. Stattdessen holt ein Skript sie von einem gepinnten Commit:

```bash
./bootstrap.sh
```

Der Stand steht in `bootstrap.sh` (`SUPABASE_REF`) und muss zu den Image-Tags
in `.env.example` passen. `volumes/` ist gitignored und trägt später auch die
Storage-Laufzeitdaten.

Update auf einen neueren Supabase-Stand: `SUPABASE_REF` **und** die Image-Tags
gemeinsam anheben, dann `./bootstrap.sh --force`.

**Dieser Schritt kommt vor dem ersten `docker compose up`.** Andersherum legt
Docker für jeden fehlenden Bind-Mount ein leeres *Verzeichnis* an Stelle der
Datei an (`volumes/db/roles.sql/` statt `roles.sql`), und Postgres
initialisiert ohne Rollen — sichtbar erst später daran, dass `auth`, `rest` und
`storage` sich nicht anmelden können. `bootstrap.sh` erkennt so ein Verzeichnis
und ersetzt es; danach einmal `docker compose down -v` und neu starten, weil
die kaputt initialisierte Datenbank bestehen bleibt.

### 2. `.env` füllen

```bash
cp .env.example .env
```

Jedes Secret-Feld ist leer und muss gefüllt werden. Die Werte liegen in
Vaultwarden (`vw get <name>`), nie in einem Commit und nie im Chat.

`POSTGRES_PASSWORD` muss URI-sicher sein, also nur `[A-Za-z0-9]` enthalten.
Compose setzt das Passwort unkodiert in die Verbindungs-URLs von Supavisor,
GoTrue, PostgREST und Storage; ein `/`, `@`, `:` oder `+` zerlegt diese URLs,
und die Dienste melden sich mit falschen Zugangsdaten an, obwohl Postgres mit
dem wörtlichen Passwort initialisiert wurde. Erzeugen mit
`openssl rand -hex 32`, nicht mit `-base64`.

`ANON_KEY` und `SERVICE_ROLE_KEY` sind JWTs, die mit `JWT_SECRET` signiert sind
und `role: anon` bzw. `role: service_role` tragen — erzeugbar nach
[Supabase Self-Hosting](https://supabase.com/docs/guides/self-hosting/docker).

`SERVICE_ROLE_KEY` umgeht jede RLS-Policy. Er gehört ausschließlich in die
Backend-Umgebung: nie ins Frontend, nie in ein Image, nie in einen Log.

### 3. Gemeinsames Netz anlegen

```bash
docker network create agora-backend
```

Einmalig pro Host. Beide Compose-Projekte hängen sich daran; das Netz gehört
keinem von beiden, deshalb `external: true`.

### 4. Starten

```bash
docker compose up -d
```

### 5. Agora ans Netz hängen

Der Agora-Stack läuft weiter unverändert. Wer die Verbindung will, legt ein
Overlay dazu:

```bash
cd ..
docker compose -f docker-compose.yml \
  -f deploy/compose/docker-compose.supabase.yml up -d
```

Aus dem Agora-Container sind dann `api-gw:8000` und `supavisor:5432`
erreichbar. Redis und Neo4j bleiben außerhalb von `agora-backend` — Supabase
kommt an Graph und Event-Bus nicht heran. Der `db`-Container hängt bewusst
nicht in diesem Netz: Postgres ist nur über den Pooler erreichbar.

Der Benutzername am Pooler trägt die Tenant-ID als Suffix — nicht `postgres`,
sondern `postgres.${POOLER_TENANT_ID}`. Die Verbindungszeichenkette, die Phase 2
(§8) als `DATABASE_URL` bekommt, lautet damit:

```text
postgresql+psycopg://postgres.agora:<POSTGRES_PASSWORD>@supavisor:5432/postgres
```

## Exposition

Alle Host-Ports sind auf `127.0.0.1` gebunden. Nach außen geht ausschließlich
das Gateway, und nur über den Reverse Proxy:

```text
Reverse Proxy
    ├── agora.example.tld       → Agora
    └── supabase.example.tld    → api-gw:8000
```

Niemals öffentlich: PostgreSQL, Supavisor, Studio, die internen Supabase-
Dienste. Studio nur intern bzw. über VPN/Tailscale/Admin-Netz — davor steht am
Gateway zusätzlich Basic Auth (`DASHBOARD_USERNAME`/`DASHBOARD_PASSWORD`).

`SUPABASE_BIND_HOST` ändert das Bind des Gateways (z. B. auf eine
Tailscale-Adresse). Default bleibt `127.0.0.1`.

## Healthcheck

Abnahmekriterium von Phase 1 (§7):

```bash
curl -f -H "apikey: $ANON_KEY" http://127.0.0.1:8000/auth/v1/health
```

Antwort:

```json
{"version":"v2.196.0","name":"GoTrue","description":"GoTrue is a user registration and authentication API"}
```

Der `apikey`-Header ist nicht optional. Der Plan nennt in §7 ein nacktes
`curl -f …/auth/v1/health`; das Envoy-Gateway beantwortet jede Anfrage ohne
gültigen API-Schlüssel mit **401**, auch den Health-Endpunkt.

Und aus dem Agora-Container heraus, sobald das Overlay läuft:

```bash
docker compose exec agora python -c "import psycopg; print('db-driver-ok')"
```

Das ist kein Abnahmekriterium von Phase 1, sondern von Phase 2 (§8) — `psycopg`
kommt erst mit der SQLAlchemy-Grundlage in die Abhängigkeiten.

Container-Status:

```bash
docker compose ps
docker compose logs -f api-gw
```

## Betrieb

```bash
docker compose ps                  # Status
docker compose logs -f <dienst>    # Logs
docker compose down                # stoppen, Daten bleiben
docker compose pull                # Images nach Tag-Anhebung holen
```

Daten liegen in benannten Volumes (`db_data`, `db_config`, `storage_data`).
`docker compose down` lässt sie stehen, `docker compose down -v` löscht sie —
inklusive der Datenbank.

Backup und Restore der Datenbank kommen mit Phase 0 des Plans (§6,
`scripts/backup_postgres.sh`). Bis dahin trägt dieser Stack keine Daten, die
Agora braucht.

## Rückbau

Dieser Stack lässt sich ersatzlos entfernen, solange Agora ihn nicht nutzt:

Aus dem Repository-Root, mit ausdrücklich benannter Compose-Datei — ein
nacktes `docker compose down -v` im Root träfe den Agora-Stack und löschte
dessen Redis- und Neo4j-Volumes:

```bash
docker compose -f supabase/docker-compose.yml down -v   # Supabase inkl. Daten
docker compose up -d                                     # Agora ohne Overlay
docker network rm agora-backend
```

Im Agora-Code bleibt nichts zurück.

## Realtime (#1618)

Realtime liefert `postgres_changes` der Tabellen `agora.projects`,
`simulations`, `runs` und `reports` an den Browser, nur `INSERT` und `UPDATE`.
Das Frontend nimmt ein Ereignis nur als Signal zum Nachladen über die API.

1. `REALTIME_DB_ENC_KEY` in `.env` setzen (genau 16 Zeichen):

   ```bash
   # Schlüssel erzeugen und eintragen
   echo "REALTIME_DB_ENC_KEY=$(openssl rand -hex 8)" >> .env
   ```

2. Dienst starten und Migration einspielen:

   ```bash
   docker compose up -d realtime
   # im Agora-Backend: nimmt die Tabellen in die Publication auf
   cd ../backend && uv run alembic -c migrations/alembic.ini upgrade head
   ```

3. In der Agora-`.env` einschalten und das Backend neu starten:

   ```bash
   AGORA_SUPABASE_REALTIME=true
   ```

Prüfen:

```bash
# Erwartet: die vier Tabellen
docker exec agora-supabase-db psql -U postgres -tAc \
  "SELECT tablename FROM pg_publication_tables WHERE pubname = 'supabase_realtime' ORDER BY 1"
# Erwartet: "realtime_enabled": true
curl -s https://<agora-host>/api/auth/config
```
