# 2026-05-01 OASIS-Sim Guardrails

## Anlass

Run `sim_f5e9c2b615a5` lief mit `ministral-3:14b-cloud`, Agent-Tools und `max_iteration=4`.
Der Reddit-Branch traf einen OpenAI-kompatiblen 400er, weil eine Assistant-History-Message ohne
`content` und ohne `tool_calls` wieder an den Provider gesendet wurde. Parallel drifteten mehrere
Persona-Freitexte von den strukturierten OASIS-Feldern ab: im Text standen z. B. `ENTP`, `48`,
`DE`, persistiert wurden aber `ISTJ`, `30`, `US`.

## Änderungen

- `backend/app/services/oasis_profile_generator.py`
  - Validiert LLM-Personas jetzt hart auf `age`, `gender`, `mbti`, `country`.
  - Normalisiert `age`, `gender`, `mbti`, `country`, bevor Profile weitergereicht werden.
  - Retryt LLM-Antworten, wenn strukturierte Pflichtfelder fehlen.
  - Fällt nach ausgeschöpften Retries auf regelbasierte vollständige Profile zurück, statt stille
    Defaults wie `ISTJ/other/30/US` in die Simulation zu schreiben.
  - Ersetzt nach der Generierung nicht nur exakt doppelte Display-Namen, sondern auch doppelte
    Nachnamen, damit Persona-Sets nicht in Weber-/Hoffmann-Klonfamilien kippen.

- `backend/scripts/agent_tools.py`
  - Installiert beim Tool-Attach pro Agent einen Memory-Sanitizer.
  - Droppt leere Assistant-Memory-Records mit `content=None` und ohne `tool_calls`, bevor CAMEL sie
    wieder an den Provider serialisiert.
  - Behält freie Modellwahl bei; es gibt keinen hart codierten Wechsel auf Qwen.
  - Script-Lint-Schulden behoben: unnötige Imports entfernt, notwendige Backend-Imports lazy geladen,
    Bare-Except ersetzt und mehrdeutige `l`-Variablen umbenannt.

- Tests
  - `backend/tests/test_oasis_profile_format.py`
    - Deckt Retry bei fehlenden Persona-Pflichtfeldern ab.
    - Deckt vollständigen regelbasierten Fallback ab.
    - Deckt Nachnamen-Deduplikation ab.
  - `backend/tests/test_simulation_runtime.py`
    - Deckt Sanitizing leerer Assistant-Records ab.
    - Deckt Installation des Memory-Sanitizers über `attach_tools_to_agents()` ab.

## Verifikation

- `cd backend && uv run pytest tests/test_oasis_profile_format.py tests/test_simulation_runtime.py`
- `cd backend && uv run ruff check scripts/agent_tools.py`
- `npm run lint:backend`
- `cd backend && uv run python -m compileall app scripts`
- `git diff --check`
- `npm run check`

Stand nach Umsetzung: `npm run check` lief grün mit 525 Backend-Tests, 40 Frontend-Tests und
erfolgreichem Frontend-Build. Zwei Redis-Integrationstests wurden wie erwartet geskippt, weil
`TEST_REDIS_URL` nicht erreichbar war. Frontend meldete ein bestehendes ESLint-Warning in
`Step4Report.vue` und Vite ein bestehendes Chunk-Size-Warning.
