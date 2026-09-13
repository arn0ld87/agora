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
#   backup    Backup des laufenden Stacks erzeugen
#   restore   Backup in die Zielinstallation zurückspielen
#   verify    Restore-Verifikation (backend/scripts/restore_verify.py)
#   upgrade   Zielversion ziehen, neu starten, erneut verifizieren
#   rollback  auf die vorherige Version zurück, erneut verifizieren
#   all       alle fünf in dieser Reihenfolge
#
# Exit-Codes:
#   0  Drill vollständig grün
#   1  ein Schritt ist fehlgeschlagen oder nicht belegt (der Protokolleintrag
#      nennt welcher — ein übersprungener Prüfpunkt ist kein Nachweis)
#   2  Aufruffehler

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

PHASE="all"
BACKUP_DIR=""
DATA_DIR="$REPO_ROOT/backend/uploads"
STORE_DIR="${AGORA_DATA_DIR:-$REPO_ROOT/backend/data}"
INSTANCE_DIR="$REPO_ROOT/backend/instance"
PROTOCOL=""
DRY_RUN=0
UPGRADE_REF=""
ROLLBACK_REF=""

usage() {
  sed -n '2,46p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
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
    -h|--help)      usage 0 ;;
    *) echo "Unbekannte Option: $1" >&2; usage 2 ;;
  esac
done

case "$PHASE" in
  backup|restore|verify|upgrade|rollback|all) ;;
  *) echo "Unbekannte Phase: $PHASE" >&2; usage 2 ;;
esac

if [ -z "$BACKUP_DIR" ]; then
  echo "--backup-dir ist erforderlich" >&2
  usage 2
fi

PROTOCOL="${PROTOCOL:-$REPO_ROOT/restore-drill-$(date -u +%Y%m%dT%H%M%SZ).log}"

log() {
  # Protokoll und Terminal bekommen denselben Text — der Nachweis ist die Datei.
  printf '%s  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$PROTOCOL"
}

run() {
  # Jeder ausgeführte Befehl steht im Protokoll, auch im Dry-Run. Ein Drill,
  # dessen Schritte man nicht nachlesen kann, beweist nichts.
  log "    \$ $*"
  if [ "$DRY_RUN" = "1" ]; then
    log "      (dry-run: nicht ausgeführt)"
    return 0
  fi
  "$@" >>"$PROTOCOL" 2>&1
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
archive() {
  local name="$1" dir="$2"
  if [ ! -d "$dir" ] && [ "$DRY_RUN" != "1" ]; then
    fail "Zu sicherndes Verzeichnis fehlt: $dir"
  fi
  run tar -czf "$BACKUP_DIR/$name.tar.gz" \
    --exclude '*.tmp' --exclude '*.lock' \
    -C "$(dirname "$dir")" "$(basename "$dir")"
}

unarchive() {
  local name="$1" dir="$2"
  [ -f "$BACKUP_DIR/$name.tar.gz" ] || [ "$DRY_RUN" = "1" ] \
    || fail "Backup fehlt: $BACKUP_DIR/$name.tar.gz"
  run tar -xzf "$BACKUP_DIR/$name.tar.gz" -C "$(dirname "$dir")"
}

phase_backup() {
  step "Phase 1/5 — Backup"
  run mkdir -p "$BACKUP_DIR"
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
  log "  Backup abgelegt unter $BACKUP_DIR"
}

phase_restore() {
  step "Phase 2/5 — Restore"
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

phase_verify() {
  step "${1:-Phase 3/5} — Verifikation"
  # Die Prosa-Checkliste aus docs/backup-restore.md, maschinell geprüft.
  # --store-dir zeigt auf backend/data: provider_connections.json liegt dort,
  # nicht unter uploads (app/services/data_dir.py::resolve_data_dir). Ohne den
  # Pfad übersprang der Prüfer den gesamten Provider/Secrets-Abschnitt.
  if [ "$DRY_RUN" = "1" ]; then
    log "    \$ uv run python scripts/restore_verify.py --data-dir $DATA_DIR --store-dir $STORE_DIR"
    log "      (dry-run: nicht ausgeführt)"
    return 0
  fi
  local rc=0
  set +e
  ( cd "$REPO_ROOT/backend" \
      && uv run python scripts/restore_verify.py \
           --data-dir "$DATA_DIR" --store-dir "$STORE_DIR" ) \
    | tee -a "$PROTOCOL"
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
  backup)   phase_backup ;;
  restore)  phase_restore ;;
  verify)   phase_verify ;;
  upgrade)  phase_upgrade ;;
  rollback) phase_rollback ;;
  all)
    phase_backup
    phase_restore
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
