# /ai-init — KI-Session initialisieren

> Startet eine neue AI-Session mit Provider- und Modell-Auswahl.

## Was dieser Command tut

1. Lädt verfügbare Provider aus der Konfiguration
2. Fragt welchen Provider der User nutzen möchte
3. Ruft die Modell-API des gewählten Providers auf
4. Zeigt alle verfügbaren Modelle zur Auswahl
5. Speichert die Auswahl im Session-State
6. Bestätigt die Konfiguration

## Anleitung für Claude

Führe exakt diese Schritte durch:

### 1. Provider-Auswahl

```
Verfügbare Anbieter:
  1) openai   — OpenAI API (GPT-4o, o1, o3-mini ...)
  2) gemini   — Google Gemini (gemini-1.5-pro, 2.0 ...)
  3) ollama   — Lokale Modelle (llama3, mistral, phi4 ...)

Standard aus .env: $AI_DEFAULT_PROVIDER
Wähle [1/2/3 oder Name]: 
```

### 2. Modell-Discovery

Rufe die entsprechende API auf:

**OpenAI:**
```bash
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  | jq '[.data[] | select(.id | test("gpt|o1|o3")) | .id] | sort'
```

**Gemini:**
```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?key=$GEMINI_API_KEY" \
  | jq '[.models[] | select(.supportedGenerationMethods[] | contains("generateContent")) | .name] | sort'
```

**Ollama:**
```bash
curl $OLLAMA_BASE_URL/api/tags | jq '[.models[].name] | sort'
```

### 3. Modell-Auswahl

Zeige die Modelle nummeriert. User wählt eine Nummer.

### 4. Bestätigung ausgeben

```
✓ AI-Session aktiv
  Provider : [provider]
  Modell   : [model]

Nächste Steps:
  /status        — Status anzeigen
  /switch        — Wechseln
  /next-task     — Erste Aufgabe laden
```
