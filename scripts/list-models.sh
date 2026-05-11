#!/usr/bin/env bash
# list-models.sh – Modelle per API abrufen
# Usage: ./list-models.sh <openai|gemini|ollama>
set -euo pipefail

PROVIDER="${1:-openai}"

case "$PROVIDER" in
  openai)
    if [ -z "${OPENAI_API_KEY:-}" ]; then
      echo "Fehler: OPENAI_API_KEY nicht gesetzt" >&2; exit 1
    fi
    curl -sf https://api.openai.com/v1/models \
      -H "Authorization: Bearer $OPENAI_API_KEY" \
      | jq -r '.data[].id' \
      | grep -E 'gpt-4|gpt-3\.5|o1|o3|codex' \
      | sort
    ;;
  gemini)
    if [ -z "${GEMINI_API_KEY:-}" ]; then
      echo "Fehler: GEMINI_API_KEY nicht gesetzt" >&2; exit 1
    fi
    curl -sf "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" \
      | jq -r '.models[] | select(.supportedGenerationMethods[] | contains("generateContent")) | .name' \
      | sed 's|models/||' \
      | grep gemini \
      | sort
    ;;
  ollama)
    OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
    curl -sf "$OLLAMA_URL/api/tags" \
      | jq -r '.models[].name' \
      | sort
    ;;
  *)
    echo "Unbekannter Provider: $PROVIDER" >&2
    echo "Gültige Optionen: openai, gemini, ollama" >&2
    exit 1
    ;;
esac
