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
