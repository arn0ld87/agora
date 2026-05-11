# /provider-list – Verfügbare Modelle anzeigen

Zeigt alle verfügbaren Modelle des aktuellen oder eines angegebenen Providers.

## Verwendung

```
/provider-list
/provider-list openai
/provider-list gemini
/provider-list ollama
```

## Was passiert

1. Bestimme Provider (Argument oder aus `.codex/config.json`)
2. Rufe `scripts/list-models.sh <provider>` auf
3. Zeige Modelle als nummerierte Liste
4. Markiere aktuell aktives Modell mit `*`

## Schritte für Claude

```bash
# Provider aus Config lesen
PROVIDER=$(jq -r '.provider' .codex/config.json)
MODEL=$(jq -r '.model' .codex/config.json)

# Modelle abrufen und anzeigen
bash scripts/list-models.sh "$PROVIDER"
```

## Ausgabe-Beispiel

```
Verfügbare Modelle für openai:
───────────────────────────────
  1) gpt-3.5-turbo
  2) gpt-4o              ← aktiv
  3) gpt-4o-mini
  4) o1-mini
  5) o3
```
