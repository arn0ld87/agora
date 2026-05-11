#!/usr/bin/env bash
# switch-provider.sh – Provider/Modell zur Laufzeit wechseln
# Schreibt .codex/config.json und gibt export-Befehle aus
# Usage: eval $(./scripts/switch-provider.sh)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$REPO_ROOT/.codex/config.json"

# Aktuellen Status zeigen
if [ -f "$CONFIG_FILE" ]; then
  CURRENT_PROVIDER=$(jq -r '.provider' "$CONFIG_FILE")
  CURRENT_MODEL=$(jq -r '.model' "$CONFIG_FILE")
  echo "Aktuell: $CURRENT_PROVIDER / $CURRENT_MODEL" >&2
fi

echo "" >&2
echo "Provider wählen:" >&2
echo "  1) OpenAI" >&2
echo "  2) Gemini" >&2
echo "  3) Ollama" >&2
echo "  0) Abbrechen" >&2
read -rp "Auswahl [0-3]: " provider_choice >&2

case "$provider_choice" in
  0) echo "Abgebrochen." >&2; exit 0 ;;
  1) PROVIDER="openai" ;;
  2) PROVIDER="gemini" ;;
  3) PROVIDER="ollama" ;;
  *) echo "Ungültig." >&2; exit 1 ;;
esac

echo "" >&2
echo "Lade Modelle für $PROVIDER..." >&2
MODELS=$("$SCRIPT_DIR/list-models.sh" "$PROVIDER" 2>&1) || {
  echo "Fehler beim Laden der Modelle: $MODELS" >&2; exit 1
}

IFS=$'\n' read -rd '' -a MODEL_ARRAY <<< "$MODELS" || true
echo "" >&2
for i in "${!MODEL_ARRAY[@]}"; do
  printf "  %2d) %s\n" $((i+1)) "${MODEL_ARRAY[$i]}" >&2
done
echo "" >&2
read -rp "Modell [1-${#MODEL_ARRAY[@]}]: " model_choice >&2

SELECTED_MODEL="${MODEL_ARRAY[$((model_choice-1))]}"

# Config aktualisieren
jq --arg p "$PROVIDER" --arg m "$SELECTED_MODEL" --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.provider = $p | .model = $m | .updated_at = $t' \
  "$CONFIG_FILE" > /tmp/codex_config_tmp.json && mv /tmp/codex_config_tmp.json "$CONFIG_FILE"

echo "✓ Gewechselt zu: $PROVIDER / $SELECTED_MODEL" >&2

# Export-Befehle ausgeben (für eval)
echo "export CODEX_PROVIDER=$PROVIDER"
echo "export CODEX_MODEL=$SELECTED_MODEL"
