# /provider-status – Aktiven Provider anzeigen

Zeigt den aktuell konfigurierten Provider, das Modell und den Verbindungsstatus.

## Verwendung

```
/provider-status
```

## Was passiert

1. Lese `.codex/config.json`
2. Zeige Provider, Modell, letztes Update
3. Prüfe Verbindung (API erreichbar? Key gesetzt?)
4. Zeige Warnung wenn Key fehlt oder Ollama nicht läuft

## Schritte für Claude

```bash
# Config anzeigen
cat .codex/config.json | jq .

# Verbindung prüfen
case "$(jq -r '.provider' .codex/config.json)" in
  openai)
    [ -n "${OPENAI_API_KEY:-}" ] && echo "✓ API-Key gesetzt" || echo "✗ OPENAI_API_KEY fehlt"
    ;;
  gemini)
    [ -n "${GEMINI_API_KEY:-}" ] && echo "✓ API-Key gesetzt" || echo "✗ GEMINI_API_KEY fehlt"
    ;;
  ollama)
    curl -sf http://localhost:11434/api/tags > /dev/null && echo "✓ Ollama läuft" || echo "✗ Ollama nicht erreichbar"
    ;;
esac
```

## Ausgabe-Beispiel

```
╔══════════════════════════════╗
║  Codex Provider Status       ║
╠══════════════════════════════╣
║  Provider:  ollama           ║
║  Modell:    llama3:8b        ║
║  Updated:   2026-05-11       ║
╠══════════════════════════════╣
║  ✓ Ollama läuft (localhost)  ║
╚══════════════════════════════╝
```
