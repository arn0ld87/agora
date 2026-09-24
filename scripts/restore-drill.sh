#!/usr/bin/env bash
# restore-drill.sh — Fresh-Host-Restore-, Upgrade- und Rollback-Drill (Issue #766).
#
# Warum es dieses Skript gibt
# ---------------------------
# docs/backup-restore.md beschreibt das Verfahren sorgfältig — als Prosa. Der
# Abnahmepunkt aus #766 verlangt aber einen *nachgewiesenen* Drill. Eine
# Checkliste, die ein Mensch abhakt, ist kein Nachweis: sie lässt sich im
# Zweifel auch abhaken, wenn niemand hingesehen hat, und sie hinterlässt nichts,
# was man einem Issue anheften könnte.
#
# Dieses Skript fährt die dokumentierte Reihenfolge ab und schreibt ein
# Protokoll mit Zeitstempel, Schritt, Ergebnis und Exit-Code.
#
# Was es NICHT tut
# ----------------
# Es ersetzt den Host nicht. Der Drill gehört auf einen frischen Host mit einem
# echten Backup aus einem echten Lauf; hier wird nur die Reihenfolge erzwungen
# und maschinell geprüft. `--dry-run` protokolliert jeden Schritt, ohne ihn
# auszuführen — damit lässt sich der Ablauf selbst prüfen (und genau das läuft
# in der Testsuite, siehe backend/tests/scripts/test_restore_drill_script.py).
#
# Verwendung:
#   scripts/restore-drill.sh --phase all      --backup-dir /srv/agora-backup
#   scripts/restore-drill.sh --phase restore  --backup-dir /srv/agora-backup
#   scripts/restore-drill.sh --phase all      --backup-dir /tmp/b --dry-run
#
# Verzeichnisse (docs/backup-restore.md, Tabelle „Kritikalität hoch"):
#   --data-dir      Artefakte und Runs        (Vorgabe backend/uploads)
#   --store-dir     Provider-/Routing-Stores  (Vorgabe backend/data, AGORA_DATA_DIR)
#   --instance-dir  Instanzsettings           (Vorgabe backend/instance)
#
# Phasen:
#   backup      Backup des laufenden Stacks erzeugen
#   restore     Backup in die Zielinstallation zurückspielen
#   pg_restore  PostgreSQL-Restore (#1583; nur wenn ein AGORA_*_BACKEND=postgres
#               aktiv ist), Schema agora aus dem pg_dump-Archiv
#   verify      Restore-Verifikation (backend/scripts/restore_verify.py)
#   upgrade     Zielversion ziehen, neu starten, erneut verifizieren
#   rollback    auf die vorherige Version zurück, erneut verifizieren
#   all         backup, restore, pg_restore, verify, upgrade, rollback in
#               dieser Reihenfolge
#
# PostgreSQL (#1583): `backup` sichert zusätzlich `agora` per `pg_dump -n
# agora -Fc`, aber NUR wenn mindestens ein `AGORA_*_BACKEND` auf `postgres`
# steht (app/infrastructure/postgres/backends.py::any_postgres_backend).
# `DATABASE_URL` muss dafür gesetzt sein. Das Passwort geht ausschließlich
# über die Umgebungsvariable `PGPASSWORD` an `pg_dump`/`pg_restore` — nie als
# Kommandozeilenargument, nie ins Protokoll.
#
# Exit-Codes:
#   0  Drill vollständig grün
#   1  ein Schritt ist fehlgeschlagen oder nicht belegt (der Protokolleintrag
#      nennt welcher — ein übersprungener Prüfpunkt ist kein Nachweis)
#   2  Aufruffehler

set -euo pipefail

# Die Archive enthalten backend/data (Fernet-Stores) und backend/instance
# (llm_profiles.db mit der api_key-Spalte im Klartext). Ohne diese Zeile erbt
# alles, was hier entsteht, den Prozess-Umask — auf den meisten Hosts 022, also
# world-readable.
umask 077

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd -P)

# Löst einen Pfad auf, bevor er verglichen wird: relativ zu absolut, `..` und
# Symlinks aufgelöst. Ohne das vergleicht der Zielschutz Zeichenketten, und
# `--data-dir backend/uploads` — genau die Schreibweise, die der Kopf dieses
# Skripts vorschlägt — liefe an ihm vorbei, obwohl sie zur Laufzeit im eigenen
# Checkout landet.
resolve_path() {
  local p="$1" parent
  case "$p" in /*) ;; *) p="$PWD/$p" ;; esac
  if [ -d "$p" ]; then
    (cd "$p" && pwd -P)
    return 0
  fi
  parent=$(dirname "$p")
  if [ -d "$parent" ]; then
    printf '%s/%s\n' "$(cd "$parent" && pwd -P)" "$(basename "$p")"
  else
    printf '%s\n' "$p"
  fi
}

PHASE="all"
BACKUP_DIR=""
DATA_DIR="$REPO_ROOT/backend/uploads"
STORE_DIR="${AGORA_DATA_DIR:-$REPO_ROOT/backend/data}"
INSTANCE_DIR="$REPO_ROOT/backend/instance"
PROTOCOL=""
DRY_RUN=0
UPGRADE_REF=""
ROLLBACK_REF=""
ALLOW_REPO_TARGET=0

usage() {
  sed -n '2,55p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --phase)        PHASE="${2:-}"; shift 2 ;;
    --backup-dir)   BACKUP_DIR="${2:-}"; shift 2 ;;
    --data-dir)     DATA_DIR="${2:-}"; shift 2 ;;
    --store-dir)    STORE_DIR="${2:-}"; shift 2 ;;
    --instance-dir) INSTANCE_DIR="${2:-}"; shift 2 ;;
    --protocol)     PROTOCOL="${2:-}"; shift 2 ;;
    --upgrade-ref)  UPGRADE_REF="${2:-}"; shift 2 ;;
    --rollback-ref) ROLLBACK_REF="${2:-}"; shift 2 ;;
    --dry-run)      DRY_RUN=1; shift ;;
    --allow-repo-target) ALLOW_REPO_TARGET=1; shift ;;
    -h|--help)      usage 0 ;;
    *) echo "Unbekannte Option: $1" >&2; usage 2 ;;
  esac
done

case "$PHASE" in
  backup|restore|pg_restore|verify|upgrade|rollback|all) ;;
  *) echo "Unbekannte Phase: $PHASE" >&2; usage 2 ;;
esac

if [ -z "$BACKUP_DIR" ]; then
  echo "--backup-dir ist erforderlich" >&2
  usage 2
fi

PROTOCOL="${PROTOCOL:-$REPO_ROOT/restore-drill-$(date -u +%Y%m%dT%H%M%SZ).log}"
# Prüfsummen liegen neben den Archiven, nicht beim Protokoll: ein Backup, das
# ohne sein Manifest umzieht, ist nicht mehr prüfbar.
MANIFEST="$BACKUP_DIR/MANIFEST.sha256"

# Das Protokoll ist zum Weitergeben gedacht — es gehört an #766. Heute nimmt
# kein verdrahteter Befehl ein Geheimnis als Argument entgegen, aber der vom
# Runbook selbst nahegelegte Health-Check trägt einen `Authorization: Bearer
# …`-Header, und per Copy-Paste in `run` wäre er sofort im Protokoll. Der Filter
# ist die Absicherung gegen den naheliegendsten nächsten Schritt, nicht gegen
# einen heutigen Fund.
redact() {
  # Das zweite Muster erfasst das oeffnende Anfuehrungszeichen mit: ohne es
  # laeuft der haeufigste Fall, ein JSON-Koerper wie {"api_key": "sk-…"}, am
  # Filter vorbei, weil die Wertklasse an der Position des Quotes nicht greift.
  sed -E \
    -e 's/(Authorization: ?(Bearer|Basic) )[^" ]+/\1[REDACTED]/gI' \
    -e 's/((token|secret|password|api[_-]?key)["'"'"']? ?[:=] ?["'"'"']?)[^"'"'"', ]+/\1[REDACTED]/gI'
}

log() {
  # Protokoll und Terminal bekommen denselben Text — der Nachweis ist die Datei.
  printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | redact | tee -a "$PROTOCOL"
}

run() {
  # Jeder ausgeführte Befehl steht im Protokoll, auch im Dry-Run. Ein Drill,
  # dessen Schritte man nicht nachlesen kann, beweist nichts.
  log "    \$ $*"
  if [ "$DRY_RUN" = "1" ]; then
    log "      (dry-run: nicht ausgeführt)"
    return 0
  fi
  "$@" 2>&1 | redact >>"$PROTOCOL"
}

step() { log ""; log "== $* =="; }

fail() {
  log "FEHLGESCHLAGEN: $*"
  log "Protokoll: $PROTOCOL"
  exit 1
}

# ---------------------------------------------------------------------------

# Ein Archiv je persistiertem Verzeichnis. Getrennt statt in einem Tarball,
# damit die Restore-Phase die dokumentierte Reihenfolge (data, instance,
# uploads) einhalten kann und ein fehlendes Verzeichnis benannt wird statt
# still zu fehlen.
# sha256 portabel: Linux bringt sha256sum, macOS shasum. Beide geben
# "<summe>  <pfad>" aus, sodass `-c` gegen dieselbe Manifestdatei arbeitet.
if command -v sha256sum >/dev/null 2>&1; then
  _sha256()       { sha256sum "$@"; }
  _sha256_check() { sha256sum -c "$@"; }
else
  _sha256()       { shasum -a 256 "$@"; }
  _sha256_check() { shasum -a 256 -c "$@"; }
fi

# PostgreSQL (#1583). Welche AGORA_*_BACKEND-Schalter aktuell auf `postgres`
# stehen — dieselbe Entscheidung wie backend/scripts/restore_verify.py, aus
# derselben Quelle (app/infrastructure/postgres/backends.py). Nur ein
# Attribute-Lookup, keine Verbindung: sicher auch im Dry-Run.
_postgres_backends() {
  ( cd "$REPO_ROOT/backend" && uv run python -c "
from app.config import Config
from app.infrastructure.postgres.backends import active_postgres_backends
print(' '.join(active_postgres_backends(Config)))
" )
}

archive() {
  local name="$1" dir="$2"
  if [ ! -d "$dir" ] && [ "$DRY_RUN" != "1" ]; then
    fail "Zu sicherndes Verzeichnis fehlt: $dir"
  fi
  run tar -czf "$BACKUP_DIR/$name.tar.gz" \
    --exclude '*.tmp' --exclude '*.lock' \
    -C "$(dirname "$dir")" "$(basename "$dir")"
  [ "$DRY_RUN" = "1" ] && return 0
  # Das Archiv trägt Fernet-Stores und Klartext-API-Keys; umask allein reicht
  # nicht, wenn tar eine bestehende Datei überschreibt.
  chmod 0600 "$BACKUP_DIR/$name.tar.gz"
  # Prüfsumme sofort, nicht am Ende: ein durch volle Platte abgebrochenes tar
  # hinterlässt sonst ein Archiv, das beim Backup grün durchläuft und erst beim
  # Restore auffällt — oder gar nicht.
  #
  # Erst berechnen, dann anhängen. Ein `_sha256 … >> manifest` würde bei einem
  # Fehlschlag mitten im Schreiben eine halbe Zeile im Manifest hinterlassen,
  # und die nähme der nächste Restore für eine Prüfsumme.
  local digest
  digest=$(cd "$BACKUP_DIR" && _sha256 "$name.tar.gz") \
    || fail "Prüfsumme nicht berechenbar: $BACKUP_DIR/$name.tar.gz"
  printf '%s\n' "$digest" >>"$MANIFEST"
  log "    Prüfsumme in $(basename "$MANIFEST") abgelegt"
}

unarchive() {
  local name="$1" dir="$2"
  [ -f "$BACKUP_DIR/$name.tar.gz" ] || [ "$DRY_RUN" = "1" ] \
    || fail "Backup fehlt: $BACKUP_DIR/$name.tar.gz"
  if [ "$DRY_RUN" != "1" ]; then
    if [ -f "$MANIFEST" ]; then
      (cd "$BACKUP_DIR" && grep " $name.tar.gz\$" "$(basename "$MANIFEST")" \
        | _sha256_check -) >/dev/null 2>&1 \
        || fail "Prüfsumme weicht ab oder fehlt im Manifest: $name.tar.gz"
      log "    Prüfsumme bestätigt: $name.tar.gz"
    else
      # Ein Archiv ohne Manifest stammt aus einem Lauf vor dieser Prüfung. Es
      # wird entpackt, aber der Punkt gilt als ungeprüft und darf den Drill
      # nicht grün färben.
      log "    WARNUNG: kein Manifest — $name.tar.gz wird ungeprüft entpackt"
    fi
  fi
  run tar -xzf "$BACKUP_DIR/$name.tar.gz" -C "$(dirname "$dir")"
}

phase_backup() {
  step "Phase 1/5 — Backup"
  # install -d setzt den Modus nur auf Verzeichnissen, die es selbst anlegt.
  # Ein aus einem frueheren Lauf oder von Hand angelegtes Backup-Verzeichnis
  # behielte sonst seine 0755 und zeigte fremden Nutzern die Archivnamen.
  run install -d -m 0700 "$BACKUP_DIR"
  run chmod 0700 "$BACKUP_DIR"
  # Frisches Manifest je Lauf: ein angehängtes würde die Prüfsumme des
  # Vorgängerarchivs mitführen, und `sha256sum -c` prüfte dann gegen einen
  # Stand, den niemand mehr hat.
  [ "$DRY_RUN" = "1" ] || : >"$MANIFEST"
  # llm_profiles.db läuft im WAL-Modus (app/services/llm_profiles_store.py).
  # Eine WAL-Datenbank besteht zur Laufzeit aus .db, .db-wal und .db-shm; ein
  # reines tar friert genau den Zwischenzustand ein, in dem die letzten
  # Schreibvorgänge noch im WAL stehen. Der Checkpoint schreibt sie in die
  # Hauptdatei zurück, bevor archiviert wird.
  if [ -f "$INSTANCE_DIR/llm_profiles.db" ] && command -v sqlite3 >/dev/null 2>&1; then
    run sqlite3 "$INSTANCE_DIR/llm_profiles.db" "PRAGMA wal_checkpoint(TRUNCATE);"
  elif [ -f "$INSTANCE_DIR/llm_profiles.db" ]; then
    log "  WARNUNG: sqlite3 fehlt — llm_profiles.db wird ohne WAL-Checkpoint gesichert"
  fi
  # Reihenfolge aus docs/backup-restore.md: erst die Dateiverzeichnisse, dann
  # Neo4j. Ein Neo4j-Dump ohne die zugehörigen Artefakte ist kein brauchbares
  # Backup — und Artefakte ohne backend/data (Provider-/Routing-/App-Stores)
  # und backend/instance (Instanzsettings) ebenso wenig: die Tabelle in
  # docs/backup-restore.md führt alle drei mit Kritikalität „hoch".
  # Lock-/Temp-Dateien sind Laufzeitartefakte und gehören nicht in den
  # restaurierten Anwendungszustand (dieselbe Ausnahmeliste wie im
  # Restic-Beispiel der Doku).
  archive uploads  "$DATA_DIR"
  archive data     "$STORE_DIR"
  archive instance "$INSTANCE_DIR"
  log "  Hinweis: Die neo4j-admin-Syntax hängt an der eingesetzten Neo4j-Version"
  log "  und Betriebsform und ist vor dem Drill gegen die laufende Version zu"
  log "  prüfen (docs/backup-restore.md). Dieses Skript pinnt sie bewusst nicht."
  run docker compose exec -T neo4j neo4j-admin database dump neo4j --to-path=/backups
  run docker compose cp neo4j:/backups "$BACKUP_DIR/neo4j"
  backup_postgres
  log "  Backup abgelegt unter $BACKUP_DIR"
}

# PostgreSQL-Backup (#1583). Nur wenn mindestens ein AGORA_*_BACKEND=postgres
# aktiv ist — Default ist ueberall Legacy, dann bleibt dieser Schritt ein
# reiner No-Op. Das Passwort geht ausschliesslich ueber PGPASSWORD an
# pg_dump, nie als Argument — `run()` loggt "$*", und ein Passwort dort waere
# sofort im weitergegebenen Protokoll.
backup_postgres() {
  local active
  active=$(_postgres_backends) || fail "PostgreSQL-Backend-Erkennung fehlgeschlagen"
  if [ -z "$active" ]; then
    log "  PostgreSQL-Backup uebersprungen: kein AGORA_*_BACKEND=postgres aktiv"
    return 0
  fi
  log "  Aktive PostgreSQL-Backends: $active"
  if [ -z "${DATABASE_URL:-}" ]; then
    fail "AGORA_*_BACKEND=postgres aktiv ($active), aber DATABASE_URL ist nicht gesetzt"
  fi

  if [ "$DRY_RUN" = "1" ]; then
    log "    \$ pg_dump --host=<host> --port=<port> --username=<user> --dbname=<db> -n agora -Fc -f $BACKUP_DIR/postgres.dump"
    log "      (dry-run: nicht ausgeführt)"
    log "    \$ uv run python scripts/postgres_backup_manifest.py --output $BACKUP_DIR/postgres-manifest.json"
    log "      (dry-run: nicht ausgeführt)"
    return 0
  fi

  # DATABASE_URL zerlegen, ohne das Passwort je als Argument oder auf stdout
  # (ausser in diese Variablen) zu haben. `postgresql+psycopg://` versteht
  # kein pg_dump — pg_cli liest deshalb nur die Bestandteile aus.
  local conn pg_host pg_port pg_user pg_db pg_pass
  mapfile -t conn < <(cd "$REPO_ROOT/backend" && uv run python -m app.infrastructure.postgres.pg_cli)
  if [ "${#conn[@]}" -lt 5 ]; then
    fail "DATABASE_URL konnte nicht zerlegt werden (pg_cli lieferte ${#conn[@]} Zeile(n))"
  fi
  pg_host="${conn[0]}"; pg_port="${conn[1]}"; pg_user="${conn[2]}"
  pg_db="${conn[3]}"; pg_pass="${conn[4]}"

  export PGPASSWORD="$pg_pass"
  run pg_dump --host="$pg_host" --port="$pg_port" --username="$pg_user" --dbname="$pg_db" \
    -n agora -Fc -f "$BACKUP_DIR/postgres.dump"
  unset PGPASSWORD
  [ -f "$BACKUP_DIR/postgres.dump" ] || fail "pg_dump hat keine Datei erzeugt: $BACKUP_DIR/postgres.dump"
  chmod 0600 "$BACKUP_DIR/postgres.dump"

  local digest
  digest=$(cd "$BACKUP_DIR" && _sha256 postgres.dump) \
    || fail "Prüfsumme für postgres.dump fehlgeschlagen"
  printf '%s\n' "$digest" >>"$MANIFEST"

  # Manifest mit Alembic-Head (live aus der Quelldatenbank) und Zeilenzahl je
  # Tabelle in agora — die Grundlage für restore_verify.py nach dem Restore.
  local rc
  set +e
  ( cd "$REPO_ROOT/backend" \
      && uv run python scripts/postgres_backup_manifest.py \
           --output "$BACKUP_DIR/postgres-manifest.json" ) \
    2>&1 | redact | tee -a "$PROTOCOL"
  rc=${PIPESTATUS[0]}
  set -e
  [ "$rc" = "0" ] || fail "Postgres-Manifest konnte nicht erzeugt werden (Exit $rc)"

  chmod 0600 "$BACKUP_DIR/postgres-manifest.json"
  digest=$(cd "$BACKUP_DIR" && _sha256 postgres-manifest.json) \
    || fail "Prüfsumme für postgres-manifest.json fehlgeschlagen"
  printf '%s\n' "$digest" >>"$MANIFEST"
}

# Die Vorgabewerte für die drei Zielverzeichnisse zeigen auf den eigenen
# Checkout. Für das Backup ist das richtig — man sichert die laufende
# Installation. Für den Restore ist es die gefährlichste Zeile im Skript: ein
# Aufruf mit --phase restore und ohne explizite Pfade überschreibt backend/data,
# backend/instance und backend/uploads des Rechners, auf dem er läuft. Das
# Runbook sagt „auf einem frischen Host"; ein Satz in einer Markdown-Datei hält
# niemanden auf.
guard_restore_target() {
  [ "$ALLOW_REPO_TARGET" = "1" ] && return 0
  local live="" resolved
  for dir in "$DATA_DIR" "$STORE_DIR" "$INSTANCE_DIR"; do
    resolved=$(resolve_path "$dir")
    case "$resolved" in
      "$REPO_ROOT"|"$REPO_ROOT"/*) live="$live $resolved" ;;
    esac
  done
  [ -z "$live" ] && return 0
  log "  Restore-Ziel liegt im Checkout:$live"
  fail "Restore würde in den eigenen Checkout schreiben. Entweder --data-dir, --store-dir und --instance-dir auf ein verwerfbares Ziel setzen, oder --allow-repo-target angeben."
}

phase_restore() {
  step "Phase 2/5 — Restore"
  guard_restore_target
  run docker compose down
  # Recovery-Reihenfolge aus docs/backup-restore.md, Schritte 3-6: erst die
  # Stores, dann die Instanzsettings, dann die Artefakte, dann Neo4j.
  unarchive data     "$STORE_DIR"
  unarchive instance "$INSTANCE_DIR"
  unarchive uploads  "$DATA_DIR"
  run docker compose up -d neo4j
  # `docker compose down` hat den alten Container mitgenommen; der neue startet
  # mit einem leeren /backups. Ohne dieses Zurückkopieren lädt der folgende
  # `neo4j-admin database load --from-path=/backups` nichts — und ein Drill,
  # der das nicht bemerkt, hat den Graphen nie restauriert. Der Punkt am Ende
  # des Quellpfads kopiert den *Inhalt* des Verzeichnisses, nicht das
  # Verzeichnis selbst.
  [ -d "$BACKUP_DIR/neo4j" ] || [ "$DRY_RUN" = "1" ] \
    || fail "Neo4j-Dump fehlt: $BACKUP_DIR/neo4j"
  run docker compose cp "$BACKUP_DIR/neo4j/." neo4j:/backups
  run docker compose exec -T neo4j neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
  run docker compose up -d
}

# PostgreSQL-Restore (#1583). Eigene Phase statt Teil von phase_restore: sie
# braucht eine erreichbare Datenbank statt eines Compose-Stacks und laeuft
# vor phase_verify (docs/backup-restore.md: „Postgres-Restore vor
# App-Start, dann restore_verify"). --clean --if-exists macht sie idempotent
# gegen eine bereits befuellte Zieldatenbank; ohne -n auf pg_restore, weil
# das Archiv durch `pg_dump -n agora` bereits auf das Fachschema begrenzt ist
# — ein zusaetzliches -n beim Restore unterdrueckt das CREATE SCHEMA im
# Archiv und laesst den Restore mit „schema agora does not exist" scheitern.
phase_pg_restore() {
  step "PostgreSQL-Restore (#1583)"
  local active
  active=$(_postgres_backends) || fail "PostgreSQL-Backend-Erkennung fehlgeschlagen"
  if [ -z "$active" ]; then
    log "  uebersprungen: kein AGORA_*_BACKEND=postgres aktiv"
    return 0
  fi
  log "  Aktive PostgreSQL-Backends: $active"
  if [ -z "${DATABASE_URL:-}" ]; then
    fail "AGORA_*_BACKEND=postgres aktiv ($active), aber DATABASE_URL ist nicht gesetzt"
  fi

  if [ "$DRY_RUN" = "1" ]; then
    log "    \$ pg_restore --host=<host> --port=<port> --username=<user> --dbname=<db> --clean --if-exists $BACKUP_DIR/postgres.dump"
    log "      (dry-run: nicht ausgeführt)"
    log "    \$ uv run alembic -c migrations/alembic.ini stamp <revision aus postgres-manifest.json>"
    log "      (dry-run: nicht ausgeführt)"
    return 0
  fi

  [ -f "$BACKUP_DIR/postgres.dump" ] || fail "PostgreSQL-Dump fehlt: $BACKUP_DIR/postgres.dump"
  if [ -f "$MANIFEST" ]; then
    (cd "$BACKUP_DIR" && grep " postgres.dump\$" "$(basename "$MANIFEST")" \
      | _sha256_check -) >/dev/null 2>&1 \
      || fail "Prüfsumme weicht ab oder fehlt im Manifest: postgres.dump"
    log "    Prüfsumme bestätigt: postgres.dump"
  fi

  local conn pg_host pg_port pg_user pg_db pg_pass
  mapfile -t conn < <(cd "$REPO_ROOT/backend" && uv run python -m app.infrastructure.postgres.pg_cli)
  if [ "${#conn[@]}" -lt 5 ]; then
    fail "DATABASE_URL konnte nicht zerlegt werden (pg_cli lieferte ${#conn[@]} Zeile(n))"
  fi
  pg_host="${conn[0]}"; pg_port="${conn[1]}"; pg_user="${conn[2]}"
  pg_db="${conn[3]}"; pg_pass="${conn[4]}"

  export PGPASSWORD="$pg_pass"
  run pg_restore --host="$pg_host" --port="$pg_port" --username="$pg_user" --dbname="$pg_db" \
    --clean --if-exists "$BACKUP_DIR/postgres.dump"
  unset PGPASSWORD

  # alembic_version liegt in `public` und ist nicht im Dump (-n agora). Ohne
  # Nachstempeln verweigert das Start-Gate (#1582) den App-Start. Die
  # Revision kommt aus dem Manifest, das beim Backup live erhoben wurde.
  [ -f "$BACKUP_DIR/postgres-manifest.json" ] \
    || fail "PostgreSQL-Manifest fehlt: $BACKUP_DIR/postgres-manifest.json"
  local revision
  revision=$(cd "$REPO_ROOT/backend" && uv run python -c \
    'import json, sys; print(json.load(open(sys.argv[1]))["revision"])' \
    "$BACKUP_DIR/postgres-manifest.json") \
    || fail "Revision aus postgres-manifest.json nicht lesbar"
  (cd "$REPO_ROOT/backend" && run uv run alembic -c migrations/alembic.ini stamp "$revision")
}

phase_verify() {
  step "${1:-Phase 3/5} — Verifikation"
  # Die Prosa-Checkliste aus docs/backup-restore.md, maschinell geprüft.
  # --store-dir zeigt auf backend/data: provider_connections.json liegt dort,
  # nicht unter uploads (app/services/data_dir.py::resolve_data_dir). Ohne den
  # Pfad übersprang der Prüfer den gesamten Provider/Secrets-Abschnitt.
  # --postgres-manifest zeigt auf das beim Backup erzeugte Manifest (#1583);
  # restore_verify.py prueft es nur, wenn Postgres ueberhaupt aktiv ist.
  if [ "$DRY_RUN" = "1" ]; then
    log "    \$ uv run python scripts/restore_verify.py --data-dir $DATA_DIR --store-dir $STORE_DIR --postgres-manifest $BACKUP_DIR/postgres-manifest.json"
    log "      (dry-run: nicht ausgeführt)"
    return 0
  fi
  local rc=0
  set +e
  # Auch hier durch redact: restore_verify.py bindet zwar bewusst nie einen
  # Klartextwert, aber der Filter darf nicht an der einen Stelle fehlen, an der
  # eine spaetere Erweiterung ihn braeuchte.
  ( cd "$REPO_ROOT/backend" \
      && uv run python scripts/restore_verify.py \
           --data-dir "$DATA_DIR" --store-dir "$STORE_DIR" \
           --postgres-manifest "$BACKUP_DIR/postgres-manifest.json" ) \
    | redact | tee -a "$PROTOCOL"
  rc=${PIPESTATUS[0]}
  set -e
  # Exit 2 heißt: kein Prüfpunkt ist rot, aber mindestens einer konnte gar
  # nicht geprüft werden. Das ist kein Nachweis und darf den Drill nicht grün
  # färben — genau deshalb hat restore_verify.py dafür einen eigenen Code.
  case "$rc" in
    0) ;;
    2) fail "Restore-Verifikation nicht belegt — übersprungene Prüfpunkte (Exit 2)" ;;
    *) fail "Restore-Verifikation (Exit $rc)" ;;
  esac
}

phase_upgrade() {
  step "Phase 4/5 — Upgrade"
  [ -n "$UPGRADE_REF" ] || { log "  übersprungen: --upgrade-ref nicht gesetzt"; return 0; }
  run git -C "$REPO_ROOT" fetch --tags
  run git -C "$REPO_ROOT" checkout "$UPGRADE_REF"
  run docker compose up -d --build
  phase_verify "Phase 4/5 (nach Upgrade)"
}

phase_rollback() {
  step "Phase 5/5 — Rollback"
  [ -n "$ROLLBACK_REF" ] || { log "  übersprungen: --rollback-ref nicht gesetzt"; return 0; }
  run git -C "$REPO_ROOT" checkout "$ROLLBACK_REF"
  run docker compose up -d --build
  phase_verify "Phase 5/5 (nach Rollback)"
}

# ---------------------------------------------------------------------------

log "Agora Restore-Drill (Issue #766)"
log "Phase: $PHASE   Backup: $BACKUP_DIR   Dry-Run: $DRY_RUN"
log "Artefakte: $DATA_DIR"
log "Stores:    $STORE_DIR"
log "Instanz:   $INSTANCE_DIR"
log "Repo: $REPO_ROOT"

case "$PHASE" in
  backup)     phase_backup ;;
  restore)    phase_restore ;;
  pg_restore) phase_pg_restore ;;
  verify)     phase_verify ;;
  upgrade)    phase_upgrade ;;
  rollback)   phase_rollback ;;
  all)
    phase_backup
    phase_restore
    phase_pg_restore
    phase_verify
    phase_upgrade
    phase_rollback
    ;;
esac

log ""
log "Drill abgeschlossen (Phase: $PHASE). Protokoll: $PROTOCOL"
if [ "$DRY_RUN" = "1" ]; then
  log "ACHTUNG: Dry-Run — dieser Lauf ist KEIN Betriebsnachweis."
fi
