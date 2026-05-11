# Provider-Initialisierung

Du startest eine neue Agora-Session. Führe den User durch die Provider- und Modell-Auswahl.

## Ablauf

### Schritt 1 — Provider wählen

Frage den User:

```
Welchen KI-Anbieter möchtest du verwenden?

  1) OpenAI    (GPT-4o, o1, o3 ...)
  2) Gemini    (gemini-1.5-pro, gemini-2.0 ...)
  3) Ollama    (lokale Modelle: llama3, mistral ...)

  Standard: {{AI_DEFAULT_PROVIDER}} [Enter für Standard]
```

### Schritt 2 — Modelle laden

Nach Provider-Auswahl:
- OpenAI: `GET https://api.openai.com/v1/models` → filtere auf `gpt-*` und `o*`
- Gemini: `GET https://generativelanguage.googleapis.com/v1beta/models` → filtere auf `generateContent`-fähige
- Ollama: `GET {{OLLAMA_BASE_URL}}/api/tags` → alle installierten Modelle

### Schritt 3 — Modell wählen

Zeige nummerierte Liste der verfügbaren Modelle:

```
Verfügbare Modelle für [Provider]:

  1) modell-name-1    (kontextfenster, letzte Aktualisierung)
  2) modell-name-2
  3) ...

  Wähle eine Nummer [1]: 
```

### Schritt 4 — Bestätigung

```
✓ Session gestartet:
  Provider : [gewählter Provider]
  Modell   : [gewähltes Modell]

Du kannst jederzeit mit /switch wechseln.
```
