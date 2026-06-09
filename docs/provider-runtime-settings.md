# Provider-Runtime-Optionen

Stand: 2026-05-10

Agora kann pro Simulation einen OpenAI-kompatiblen LLM-Provider aus der UI
nutzen. Die Modellauswahl aus Schritt 2 wird an Prepare, Start und Report
weitergereicht; ein späterer Start aktualisiert `simulation_config.json` bei
gesetztem `llm_model`.

## UI

In Schritt 2 öffnet `Provider-Optionen` ein Menü für:

- `Server-Standard` — nutzt `.env` / `instance/settings.json`.
- `Google Gemini` — setzt die OpenAI-kompatible Base-URL
  `https://generativelanguage.googleapis.com/v1beta/openai/`.
- `OpenAI` — setzt `https://api.openai.com/v1`.
- `OpenAI-kompatibel` — erwartet eine eigene Base-URL.

Der API-Key wird nur in `sessionStorage` des Browsers gehalten und bei
Prepare, Start und Report als Request-Body-Feld `llm_provider.api_key` an den
lokalen Backend-Prozess gesendet. `localStorage` speichert nur Provider und
Base-URL.

Wenn ein Runtime-Provider aktiv ist, zeigt die Modellauswahl providerpassende
Modelle statt lokaler Ollama-Modelle. Für `Google Gemini` sind die textfähigen
OpenAI-kompatiblen IDs aus der Gemini-Dokumentation hinterlegt:

- `gemini-3-flash-preview`
- `gemini-3.1-pro-preview`
- `gemini-3.1-flash-lite`
- `gemini-2.5-pro`
- `gemini-2.5-flash`
- `gemini-2.5-flash-lite`

`Custom` bleibt verfügbar, falls Google neue Modell-IDs veröffentlicht, bevor
Agora aktualisiert wurde.

## Backend

`backend/app/services/llm_runtime.py` validiert `llm_provider` zentral. API-Keys
werden nicht in Run-Metadata oder Simulation-Artefakte geschrieben. Persistiert
werden nur nicht-geheime Werte:

- `simulation_config.json::llm_model`
- `simulation_config.json::llm_base_url`
- Run-Metadata `llm_provider.api_key_set=true`

Für den OASIS-Subprozess injiziert `/api/simulation/start` die Runtime-Werte als
Environment (`LLM_API_KEY`, `OPENAI_API_KEY`, `LLM_BASE_URL`,
`OPENAI_BASE_URL`, `OPENAI_API_BASE`, `OPENAI_API_BASE_URL`) nur für diesen
Prozess. Die drei OpenAI-Base-URL-Aliase werden parallel gesetzt, damit
CAMEL/OASIS-Skripte und OpenAI-kompatible Clients mit unterschiedlichen
Konventionen dieselbe Runtime-Auswahl nutzen.

## JSON-Mode-Env-Vars

`backend/app/utils/llm_client.py` (`chat_json`) wertet folgende Env-Vars aus:

| Variable | Wirkung |
|---|---|
| `LLM_DISABLE_JSON_OBJECT_MODE=true` | Unterdrückt `response_format={"type":"json_object"}` bei schema-losen Aufrufen. Nützlich für OpenAI-Reasoning-Modelle, die mit `json_object` leere Antworten liefern. |
| `LLM_DISABLE_JSON_SCHEMA_MODE=true` | Unterdrückt strict `response_format={"type":"json_schema","strict":true}` auch wenn ein Schema übergeben wurde. Fällt auf `json_object` + post-hoc Pydantic-Validierung zurück. |
| `LLM_DISABLE_JSON_MODE=true` | **Veraltet.** Legacy-Alias für `LLM_DISABLE_JSON_OBJECT_MODE`. Gibt eine `DeprecationWarning` aus. Bitte auf den neuen Namen migrieren. Wird in einem künftigen Release entfernt. |

### Vier Kombinationen

| Schema | Env-Flag | `response_format` |
|---|---|---|
| keines | keines | `{"type": "json_object"}` |
| keines | `LLM_DISABLE_JSON_OBJECT_MODE=true` | keines (Freitext) |
| Pydantic-Modell | keines | `{"type": "json_schema", "strict": true}` |
| Pydantic-Modell | `LLM_DISABLE_JSON_SCHEMA_MODE=true` | `{"type": "json_object"}` + Pydantic-Validierung |
| Pydantic-Modell | `LLM_DISABLE_JSON_SCHEMA_MODE=true` und `LLM_DISABLE_JSON_OBJECT_MODE=true` | keines (Freitext) + Pydantic-Validierung |
