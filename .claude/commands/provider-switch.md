# /provider-switch – Provider & Modell wechseln

Wechsle den aktiven KI-Anbieter und das Modell für Codex. Modelle werden automatisch per API abgerufen.

## Verwendung

```
/provider-switch
```

Ohne Argumente: interaktives Menü.

```
/provider-switch openai gpt-4o
/provider-switch gemini gemini-2.0-flash
/provider-switch ollama llama3:8b
```

Mit Argumenten: direkter Wechsel ohne Menü.

## Was passiert

1. Lese `.codex/config.json` – zeige aktuellen Provider/Modell
2. Falls kein Argument: zeige Provider-Menü (openai / gemini / ollama)
3. Rufe `scripts/list-models.sh <provider>` auf – zeige verfügbare Modelle
4. Schreibe gewählten Provider + Modell in `.codex/config.json`
5. Bestätige den Wechsel

## Schritte für Claude

```bash
# Aktuellen Status lesen
cat .codex/config.json

# Modelle abrufen (Beispiel Ollama)
bash scripts/list-models.sh ollama

# Config aktualisieren
bash scripts/switch-provider.sh
```

## Hinweise
- API-Keys werden aus Umgebungsvariablen gelesen, nie aus Dateien
- Ollama benötigt keinen API-Key, nur eine laufende Instanz auf Port 11434
- Der Wechsel wirkt ab dem nächsten Codex-Aufruf
- Gemini nutzt den OpenAI-kompatiblen Endpoint
