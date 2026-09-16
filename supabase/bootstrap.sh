#!/usr/bin/env bash
# Holt die Supabase-Config-Dateien, die `docker-compose.yml` unter `volumes/`
# einhaengt: DB-Init-SQL, Envoy-Gateway-Konfiguration und Supavisor-Config.
#
# Warum nicht im Repository: es sind rund 1500 Zeilen fremder Konfiguration aus
# supabase/supabase (Apache-2.0). Vendored muessten sie bei jedem Supabase-
# Update nachgezogen und reviewt werden. Stattdessen ein gepinnter Commit —
# reproduzierbar, und ein Update ist eine Zeile in diesem Skript.
#
# Aufruf:
#   ./bootstrap.sh            # holt SUPABASE_REF nach volumes/
#   ./bootstrap.sh --force    # ueberschreibt ein vorhandenes volumes/
#
# `volumes/` ist gitignored und enthaelt spaeter auch Laufzeitdaten.
set -euo pipefail

# Gepinnter Supabase-Stand. Muss zu den Image-Tags in `.env.example` passen.
SUPABASE_REF="${SUPABASE_REF:-e8547352c529ed99545fafbc8619dec42945d74e}"
SUPABASE_REPO="${SUPABASE_REPO:-https://github.com/supabase/supabase.git}"

cd "$(dirname "$0")"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
elif [[ $# -gt 0 ]]; then
  echo "unbekanntes Argument: $1" >&2
  echo "Aufruf: $0 [--force]" >&2
  exit 2
fi

# `volumes/.supabase-ref` ist der Beleg, dass dieses Skript das Verzeichnis
# angelegt hat. Nur auf `-d volumes` zu pruefen waere eine Falle: wer
# `docker compose up` VOR dem Bootstrap ausfuehrt, bekommt von Docker fuer
# jeden fehlenden Bind-Mount ein leeres VERZEICHNIS an Stelle der Datei
# (volumes/db/roles.sql/ statt roles.sql). Postgres initialisiert dann ohne
# Rollen, und ein reines Existenz-Kriterium wuerde die Reparatur auch noch
# verweigern.
if [[ -f volumes/.supabase-ref && $FORCE -eq 0 ]]; then
  echo "volumes/ steht auf $(cat volumes/.supabase-ref | cut -c1-12) — nichts getan." >&2
  echo "Mit --force neu holen." >&2
  exit 0
fi

if [[ -d volumes && ! -f volumes/.supabase-ref ]]; then
  echo "volumes/ existiert, stammt aber nicht aus diesem Skript." >&2
  echo "Typisch nach einem 'docker compose up' vor dem Bootstrap: Docker hat" >&2
  echo "die fehlenden Dateien als leere Verzeichnisse angelegt." >&2
  if [[ -d volumes/db/roles.sql ]]; then
    echo "Die Datenbank ist in dem Fall ohne Rollen initialisiert worden." >&2
    echo "Nach diesem Lauf einmal 'docker compose down -v' und neu starten." >&2
  fi
  echo "Wird ersetzt." >&2
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "hole supabase@${SUPABASE_REF:0:12} ..."
git -C "$WORK" init --quiet
git -C "$WORK" remote add origin "$SUPABASE_REPO"
git -C "$WORK" config core.sparseCheckout true
git -C "$WORK" sparse-checkout set --no-cone docker/volumes
git -C "$WORK" fetch --quiet --depth 1 origin "$SUPABASE_REF"
git -C "$WORK" checkout --quiet FETCH_HEAD

SRC="$WORK/docker/volumes"
for f in db/realtime.sql db/webhooks.sql db/roles.sql db/jwt.sql \
         db/_supabase.sql db/pooler.sql \
         api/envoy/envoy.yaml api/envoy/cds.yaml api/envoy/lds.template.yaml \
         api/envoy/docker-entrypoint.sh \
         pooler/pooler.exs; do
  if [[ ! -f "$SRC/$f" ]]; then
    echo "fehlt im Supabase-Stand ${SUPABASE_REF:0:12}: docker/volumes/$f" >&2
    echo "SUPABASE_REF passt nicht zu dieser docker-compose.yml." >&2
    exit 1
  fi
done

rm -rf volumes
mkdir -p volumes/db volumes/api/envoy volumes/pooler
cp "$SRC"/db/realtime.sql "$SRC"/db/webhooks.sql "$SRC"/db/roles.sql \
   "$SRC"/db/jwt.sql "$SRC"/db/_supabase.sql "$SRC"/db/pooler.sql volumes/db/
cp "$SRC"/api/envoy/envoy.yaml "$SRC"/api/envoy/cds.yaml \
   "$SRC"/api/envoy/lds.template.yaml "$SRC"/api/envoy/docker-entrypoint.sh \
   volumes/api/envoy/
cp "$SRC"/pooler/pooler.exs volumes/pooler/
chmod +x volumes/api/envoy/docker-entrypoint.sh
echo "$SUPABASE_REF" > volumes/.supabase-ref

echo "volumes/ steht auf ${SUPABASE_REF:0:12}."
echo "Naechster Schritt: .env fuellen, dann 'docker network create agora-backend'."
