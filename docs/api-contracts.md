# API Contracts — Agora Backend ↔ Frontend

**Status:** Single Source of Truth seit v0.7.0
**Quelldateien:**
- Codes & Backend-Default-Messages: [`backend/app/utils/api_errors.py`](../backend/app/utils/api_errors.py)
- Frontend-UX-Texte & Retry-Mapping: [`frontend/src/api/errorMessages.ts`](../frontend/src/api/errorMessages.ts)
- Envelope-Mapper & `ApiError`-Klasse: [`frontend/src/api/envelope.ts`](../frontend/src/api/envelope.ts)
- Schema-Tests (31 über 7 Domänen): [`backend/tests/api/test_response_schemas.py`](../backend/tests/api/test_response_schemas.py)

Diese Datei spiegelt den Code-Stand. Bei Änderungen am Code: hier mit-pflegen, sonst driftet die Doku.

---

## Response-Envelopes

Alle `/api/*`-Endpunkte liefern strukturierte JSON-Envelopes. Frontend nutzt `unwrap()` aus [`envelope.ts`](../frontend/src/api/envelope.ts) zum Auspacken.

### Erfolg

```json
{
  "success": true,
  "data": <T>,
  "count": <number?>,
  "message": <string?>,
  "meta": <object?>
}
```

- `data` ist immer gesetzt; Typ hängt vom Endpunkt ab (siehe Schema-Tests).
- `count` nur bei Listen-Endpunkten.
- `message` für menschenlesbare Bestätigungen (selten).
- `meta` für Pagination, Cursor, Trace-IDs etc.

### Fehler

```json
{
  "success": false,
  "code": "<ApiErrorCode>",
  "error": "<string>",
  "details": <object?>
}
```

- `code` aus dem `ApiErrorCode`-Katalog (siehe unten).
- `error` ist die Backend-Default-Message (DE) oder eine kontextspezifische Override-Message.
- `details` optional, enthält strukturierte Zusatzinfos (`task_id`, `retry_after`, etc.).
- Backend ergänzt sporadisch zusätzliche Top-Level-Felder (`task_id`, …) — Frontend liest diese via `originalResponse` auf der `ApiError`-Instanz.

---

## ApiErrorCode-Katalog (23 Codes)

Spalten:
- **Code** — Wert aus `ApiErrorCode`-StrEnum (lowercase).
- **HTTP** — beobachteter HTTP-Status; Werte ohne aktuellen Aufrufer markiert mit `(Konvention)`.
- **Backend-Default** — DE-Message aus `DEFAULT_MESSAGES` (api_errors.py).
- **Frontend-UX** — DE-Toast-Text aus `ERROR_MESSAGES` (errorMessages.ts).
- **Retry** — `✓` wenn in `RETRYABLE_CODES` (frontend triggert Retry-UI).

### Validierung & Anfrage-Form

| Code | HTTP | Backend-Default | Frontend-UX | Retry |
|------|------|-----------------|-------------|-------|
| `invalid_id` | 400 | Ungültige ID | Ungültige ID — bitte erneut prüfen | — |
| `not_found` | 404 | Nicht gefunden | Eintrag nicht gefunden | — |
| `validation_failed` | 400 | Eingabe ungültig | Eingabe ungültig — bitte Werte prüfen | — |
| `bad_request` | 400 (Konvention) | Ungültige Anfrage | Anfrage ungültig | — |
| `method_not_allowed` | 405 (Konvention) | Methode nicht erlaubt | Methode nicht erlaubt | — |

### Auth

| Code | HTTP | Backend-Default | Frontend-UX | Retry |
|------|------|-----------------|-------------|-------|
| `auth_required` | 401 (Konvention) | Authentifizierung erforderlich | Anmeldung erforderlich | — |
| `auth_invalid` | 401 (Konvention) | Authentifizierung ungültig | Anmeldung ungültig — bitte neu einloggen | — |
| `auth_forbidden` | 403 (Konvention) | Zugriff verweigert | Zugriff verweigert | — |

### Rate-Limit & Timeout

| Code | HTTP | Backend-Default | Frontend-UX | Retry |
|------|------|-----------------|-------------|-------|
| `rate_limited` | 429 (Konvention) | Zu viele Anfragen | Zu viele Anfragen — bitte später erneut versuchen | ✓ |
| `timeout` | 504 (Konvention) | Zeitüberschreitung | Zeitüberschreitung — Backend antwortet zu langsam | ✓ |

### Infrastruktur (transient)

| Code | HTTP | Backend-Default | Frontend-UX | Retry |
|------|------|-----------------|-------------|-------|
| `service_unavailable` | 503 | Dienst nicht verfügbar | Backend offline oder nicht erreichbar | ✓ |
| `neo4j_unavailable` | 503 | Neo4j nicht erreichbar | Datenbank (Neo4j) nicht erreichbar | ✓ |
| `llm_unavailable` | 503 (Konvention) | LLM-Endpoint nicht erreichbar | LLM-Endpunkt nicht erreichbar | ✓ |

### Domänen-Konflikte (Workflow-spezifisch)

| Code | HTTP | Backend-Default | Frontend-UX | Retry |
|------|------|-----------------|-------------|-------|
| `ontology_missing` | 400 | Ontologie fehlt | Ontologie fehlt — bitte zuerst generieren | — |
| `ontology_generation_failed` | 500 (Konvention) | Ontologie-Generierung fehlgeschlagen | Ontologie-Generierung fehlgeschlagen — erneut versuchen | ✓ |
| `simulation_not_prepared` | 409 (auch 404 beobachtet) | Simulation noch nicht vorbereitet | Simulation noch nicht vorbereitet — Schritt /prepare ausführen | — |
| `simulation_already_running` | 409 | Simulation läuft bereits | Simulation läuft bereits | — |
| `persona_review_required` | 409 | Persona-Review erforderlich | Persona-Review erforderlich, bevor die Simulation startet | — |
| `graph_build_in_progress` | 409 | Graph-Build läuft bereits | Graph-Build läuft bereits — bitte warten | — |

### Upload

| Code | HTTP | Backend-Default | Frontend-UX | Retry |
|------|------|-----------------|-------------|-------|
| `upload_too_large` | 413 (Konvention) | Upload zu groß | Datei zu groß | — |
| `unsupported_format` | 400 | Format nicht unterstützt | Format nicht unterstützt | — |

### Generisch

| Code | HTTP | Backend-Default | Frontend-UX | Retry |
|------|------|-----------------|-------------|-------|
| `internal_error` | 500 (Konvention) | Interner Serverfehler | Interner Serverfehler | — |
| `not_implemented` | 501 (Konvention) | Nicht implementiert | Funktion noch nicht verfügbar | — |

**Hinweis zu `(Konvention)`:** Diese Codes sind im Katalog definiert, haben aber zum Zeitpunkt v0.7.0 keinen aktiven `json_error()`-Aufrufer mit explizitem `status=`-Argument. Die genannten HTTP-Werte folgen der RFC-Standardkonvention und sind die geplante Vergabe, sobald entsprechende Endpunkte den Code nutzen.

---

## Domänen-Schemas

Alle Response-Schemas werden in `backend/tests/api/test_response_schemas.py` per `jsonschema.validate()` enforced. 31 Tests über 7 Domänen:

| Domäne | Schema-Test-Klasse | Zweck |
|--------|-------------------|-------|
| Project | `TestProjectSchemas` | `/api/projects` CRUD-Responses |
| Simulation | `TestSimulationSchemas` | `/api/simulations` State, Branches |
| RunStatus | `TestRunStatusSchemas` | `/api/runs/<id>/status` Polling-Antwort |
| ReportStatus | `TestReportStatusSchemas` | `/api/reports/<id>` Generation-Status |
| GraphData | `TestGraphDataSchemas` | `/api/graph/<id>` Nodes/Edges/Triples |
| OntologyDefinition | `TestOntologySchemas` | `/api/graph/<id>/ontology` Entity-Types |
| Persona | `TestPersonaSchemas` | `/api/personas/*` lokale Persona-Bibliothek |

Bei Schema-Änderungen: Schema-Test anpassen, neuen Validierungs-Snapshot committen, Frontend-Konsumenten gegenchecken.

---

## Frontend-Konsumtion

```typescript
import { unwrap, isApiError, ApiError } from './api/envelope'
import { userMessageFor, isRetryable } from './api/errorMessages'

try {
  const data = unwrap(envelope)            // T bei Erfolg, sonst ApiError-throw
  // ...
} catch (e) {
  if (isApiError(e)) {
    showToast(userMessageFor(e))            // semantischer DE-Text
    if (isRetryable(e)) showRetryButton()   // nur bei transient-Codes
  } else {
    showToast('Unbekannter Fehler')
  }
}
```

`ApiError` exposiert `code`, `status`, `message`, `details`, `originalResponse` — UI kann auf `code` switchen statt String-Matching auf `message`.

---

## Migrations-Hinweis (vor v0.7.0 → v0.7.0)

- Backend `json_error()` akzeptiert jetzt `ApiErrorCode` als Argument; positional-string-Aufrufe (198 Stellen) bleiben Backwards-Compat.
- Frontend wirft seit v0.7.0 `ApiError` aus dem Response-Interceptor (`frontend/src/api/index.js`); Komponenten, die noch `res.data` lesen, funktionieren weiter (additive Migration).
- 5xx-Antworten sind security-safe: ungefangene Exceptions liefern außerhalb von `Config.DEBUG=true` nur generische Meldungen plus `code` — Details bleiben im Log.
