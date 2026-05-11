# /list-models — Verfügbare Modelle anzeigen

> Zeigt alle verfügbaren Modelle des aktuellen oder eines gewählten Providers.

## Verwendung

```
/list-models           — Modelle des aktuellen Providers
/list-models openai    — Modelle von OpenAI
/list-models gemini    — Modelle von Gemini
/list-models ollama    — Lokal installierte Ollama-Modelle
/list-models all       — Alle Provider zusammen
```

## Ausgabe-Format

```
Modelle für [Provider]:
──────────────────────────────────────
  ✓ gpt-4o              [aktuell aktiv]
    gpt-4o-mini
    o1
    o1-mini
    o3-mini
──────────────────────────────────────
Geladen um: [Timestamp]

Zum Wechseln: /switch-model
```

## API-Aufrufe

Jeweils frische Daten von der API laden — keine gecachten Listen verwenden.

**OpenAI:** `GET /v1/models` (filtere auf `gpt-*`, `o1*`, `o3*`)
**Gemini:** `GET /v1beta/models` (filtere auf `generateContent`-Support)
**Ollama:** `GET /api/tags` (alle installierten Tags)

## Fehlerbehandlung

- API nicht erreichbar → klare Fehlermeldung + Hinweis auf `.env`-Variable
- Kein API-Key gesetzt → `"OPENAI_API_KEY nicht in .env gefunden"` (kein Key im Output!)
- Ollama nicht gestartet → `"Ollama nicht erreichbar unter $OLLAMA_BASE_URL — läuft der Dienst?"`
