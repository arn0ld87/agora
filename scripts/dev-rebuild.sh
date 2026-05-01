#!/usr/bin/env bash
# Dev-Rebuild Helper für Agora.
# quick: Container-Restart (Backend-Bind-Mount reload)
# deps:  npm install im Frontend-Volume + restart (nach package.json-Bump)
# full:  down, rebuild, up, deps, restart
set -euo pipefail

mode="${1:-quick}"
cd "$(dirname "$0")/.."

case "$mode" in
  quick)
    docker compose restart agora
    ;;
  deps)
    docker compose exec agora npm install --prefix frontend
    docker compose restart agora
    ;;
  full)
    docker compose down
    docker compose up -d --build
    sleep 3
    docker compose exec agora npm install --prefix frontend
    docker compose restart agora
    ;;
  *)
    echo "Usage: $0 {quick|deps|full}" >&2
    exit 1
    ;;
esac

echo
echo "Container-Status:"
docker compose ps agora
