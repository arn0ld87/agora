# Arbeitsprotokoll — Slice E.1: Backend `model.active`-Event-Publishing + SSE-Channel

**Datum:** 2026-05-04
**Branch:** feat/task-E1-model-active-backend
**Issue:** #213 — Live-Anzeige des aktiven LLM-Modells im Frontend

---

## Architektur-Entscheidung: Neuer Bus statt SimulationEventBus erweitern

Der bestehende `SimulationEventBus` (und seine `InMemoryEventBus`-Implementierung) ist für Flask↔OASIS-Subprocess-IPC gebaut:

- `SimulationEvent` hat `simulation_id` als Pflichtfeld
- Der Bus ist multi-Kanal und unterstützt request/response-Korrelation
- `FilePollingEventBus` und `RedisEventBus` sind für persistente, zuverlässige IPC gedacht

LLM-Calls passieren auch außerhalb von Simulationen (Persona-Generierung, Report-Generierung, Graph-Build) und haben keine `simulation_id`. Eine Erweiterung des SimulationEventBus hätte erfordert:
- `simulation_id` optional zu machen (Breaking Change an bestehenden Consumers)
- Oder eine spezielle `None`-Fallback-Logik einzubauen (erhöhte Komplexität)

**Entscheidung: Neuer `ModelEventBus`** in `backend/app/services/model_event_bus.py`:
- Queue-basiertes Fan-out (eine Queue pro Subscriber)
- Drop-Oldest-Strategie bei Backpressure (kein blocking publish)
- Pydantic v2 `ModelActiveEvent` mit `extra="forbid"`
- Context-Manager-basiertes Subscribe für sauberes Cleanup

---

## Geänderte / neue Dateien

| Datei | Aktion | Beschreibung |
|---|---|---|
| `backend/app/services/model_event_bus.py` | neu | `ModelActiveEvent` Pydantic-Modell + `ModelEventBus` Singleton |
| `backend/app/utils/llm_client.py` | modifiziert | `_detect_provider()`, `_publish_model_active()`, `context`-Param in `chat()` + `chat_json()` |
| `backend/app/api/llm.py` | neu | Blueprint `llm_bp`, `GET /api/llm/model-stream` SSE-Endpoint |
| `backend/app/api/__init__.py` | modifiziert | `llm_bp` Blueprint registriert |
| `backend/app/__init__.py` | modifiziert | `llm_bp` in App-Factory importiert + registriert |
| `backend/app/api/auth.py` | modifiziert | `"llm-stream"` zu `_ALLOWED_SCOPE_PREFIXES` hinzugefügt |
| `backend/tests/services/test_model_event_bus.py` | neu | 16 Tests für Bus + Event-Modell |
| `backend/tests/api/test_llm_model_stream.py` | neu | 13 Tests für SSE-Endpoint |
| `backend/tests/utils/test_llm_client_publishes_model_active.py` | neu | 10 Tests für LLMClient-Integration |
| `backend/tests/test_llm_client.py` | modifiziert | Mock-Signaturen um `context`-Parameter erweitert |

---

## SSE-Endpoint-Details

- **Route:** `GET /api/llm/model-stream`
- **Auth:** `@allow_ticket_auth(lambda: "llm-stream", single_use=False)` — SSE-Tickets sind wiederverwendbar (EventSource-Reconnects innerhalb TTL)
- **Scope für Ticket-Issuance:** `"llm-stream"` via `POST /api/auth/ticket`
- **Frame-Format:**
  ```
  retry: 5000\n\n
  id: <hex-uuid>\ndata: <ModelActiveEvent JSON>\n\n
  : heartbeat\n\n   (alle 15 s bei Idle)
  ```

---

## Provider-Erkennung in `_detect_provider()`

Heuristik-Kette (Priorität absteigend):
1. Modell-Name endet auf `:cloud` → `"cloud"` (Ollama-Cloud-Proxy)
2. `base_url` enthält `11434` → `"ollama"` (lokales Ollama)
3. `base_url` enthält `openai.com` oder `api.openai` → `"openai"`
4. Fallback → `"unknown"`

---

## Test-Befunde

- Alle 39 neuen Tests sofort grün
- Ein Iterations-Problem in bestehenden `test_llm_client.py`-Tests: `mock_chat()`-Funktionen akzeptierten den neuen `context`-Keyword-Parameter nicht → alle 5 Mocks erweitert
- Blueprint-Isolation-Problem: `test_llm_model_stream.py` darf den globalen `auth_bp`-Singleton nicht ein zweites Mal mit `install_blueprint_guard` belegen (Flask-Assertion) → lokale Auth-Blueprint-Implementierung im Test

**Gesamtergebnis:** 1412 passed, 9 skipped, 4 deselected

---

## Offene Punkte für E.2 (Frontend)

- **SSE-URL:** `GET /api/llm/model-stream?ticket=<signed>`
- **Ticket-Issuance:** `POST /api/auth/ticket` mit Body `{"scope": "llm-stream"}`
- **Frame-Schema (TypeScript):**
  ```typescript
  interface ModelActiveEvent {
    model: string;
    context: "chat" | "chat_json" | "embedding" | "report" | "persona" | "graph" | "unknown";
    provider: "ollama" | "cloud" | "openai" | "unknown";
    ts: number;  // Unix timestamp (float)
    extra: Record<string, unknown> | null;
  }
  ```
- **STALE_AFTER_MS Idle-Fallback:** Heartbeats werden als SSE-Kommentare (`": heartbeat"`) gesendet, kein Modell-Name im Heartbeat. Frontend muss selbst einen Timer implementieren der das Badge nach N ms Idle ausgraut.
- **Pinia-Store `useActiveModelStore`** — bleibt für E.2
- **Komponente `ActiveModelBadge.vue`** — bleibt für E.2
- **aria-live + i18n** — vollständig in E.2

---

## Akzeptanz-Häkchen aus Issue #213 (Backend-Anteil)

- [x] `llm_client.chat()` publiziert vor jedem Modell-Call ein `model.active`-Event
- [x] `llm_client.chat_json()` publiziert ebenfalls (via `chat()`, mit `context="chat_json"`)
- [x] SSE-Channel `GET /api/llm/model-stream` vorhanden
- [x] Auth via Signed Ticket, Scope `"llm-stream"`, non-single-use
- [x] Drop-Oldest-Backpressure (kein blocking publish)
- [x] Fail-safe: publish-Fehler unterbricht den LLM-Call nicht
- [x] `ModelActiveEvent` Pydantic-Modell mit `extra="forbid"`
- [ ] Frontend Pinia-Store `useActiveModelStore` — bleibt für E.2
- [ ] Komponente `ActiveModelBadge.vue` — bleibt für E.2
- [ ] STALE_AFTER_MS Idle-Fallback im Frontend — bleibt für E.2
- [ ] aria-live + i18n — vollständig in E.2
