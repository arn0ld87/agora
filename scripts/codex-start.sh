#!/usr/bin/env bash
# codex-start.sh – Interaktiver Codex-Start mit Provider-Auswahl
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$REPO_ROOT/.codex/config.json"

echo ""
echo "┌─────────────────────────────────────┐"
echo "│  Agora Codex – Provider wählen      │"
echo "├─────────────────────────────────────┤"
echo "│  1) OpenAI   (OPENAI_API_KEY nötig) │"
echo "│  2) Gemini   (GEMINI_API_KEY nötig) │"
echo "│  3) Ollama   (lokal, kein API-Key)  │"
echo "└─────────────────────────────────────┘"
echo ""
read -rp "Auswahl [1-3]: " provider_choice

case "$provider_choice" in
  1) PROVIDER="openai" ;;
  2) PROVIDER="gemini" ;;
  3) PROVIDER="ollama" ;;
  *) echo "Ungültige Auswahl. Abbruch."; exit 1 ;;
esac

echo ""
echo "Lade Modelle für $PROVIDER..."
MODELS=$("$SCRIPT_DIR/list-models.sh" "$PROVIDER")

if [ -z "$MODELS" ]; then
  echo "Fehler: Keine Modelle gefunden für $PROVIDER."
  echo "Prüfe API-Key oder Ollama-Verbindung."
  exit 1
fi

echo ""
echo "Verfügbare Modelle:"
echo "────────────────────"
IFS=$'\n' read -rd '' -a MODEL_ARRAY <<< "$MODELS" || true
for i in "${!MODEL_ARRAY[@]}"; do
  printf "  %2d) %s\n" $((i+1)) "${MODEL_ARRAY[$i]}"
done
echo ""
read -rp "Modell wählen [1-${#MODEL_ARRAY[@]}]: " model_choice

if ! [[ "$model_choice" =~ ^[0-9]+$ ]] || [ "$model_choice" -lt 1 ] || [ "$model_choice" -gt "${#MODEL_ARRAY[@]}" ]; then
  echo "Ungültige Auswahl. Abbruch."; exit 1
fi

SELECTED_MODEL="${MODEL_ARRAY[$((model_choice-1))]}"

# Config schreiben
mkdir -p "$(dirname "$CONFIG_FILE")"
jq --arg p "$PROVIDER" --arg m "$SELECTED_MODEL" --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.provider = $p | .model = $m | .updated_at = $t' \
  "$CONFIG_FILE" > /tmp/codex_config_tmp.json && mv /tmp/codex_config_tmp.json "$CONFIG_FILE"

echo ""
echo "✓ Provider: $PROVIDER  |  Modell: $SELECTED_MODEL"
echo "✓ Konfiguration gespeichert: .codex/config.json"
echo ""

# Codex starten (Provider-spezifisch)
case "$PROVIDER" in
  openai)
    if [ -z "${OPENAI_API_KEY:-}" ]; then
      echo "Fehler: OPENAI_API_KEY nicht gesetzt."; exit 1
    fi
    exec codex --model "$SELECTED_MODEL" "$@"
    ;;
  gemini)
    if [ -z "${GEMINI_API_KEY:-}" ]; then
      echo "Fehler: GEMINI_API_KEY nicht gesetzt."; exit 1
    fi
    # Gemini via OpenAI-kompatibler Endpoint
    exec codex \
      --model "$SELECTED_MODEL" \
      --provider gemini \
      "$@"
    ;;
  ollama)
    OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
    exec codex \
      --model "$SELECTED_MODEL" \
      --provider ollama \
      --api-base-url "$OLLAMA_URL/v1" \
      "$@"
    ;;
esac
