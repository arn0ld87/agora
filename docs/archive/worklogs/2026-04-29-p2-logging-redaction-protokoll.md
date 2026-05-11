# P2 Logging-Review — Secret-Redaction & Token-Schutz

**Datum:** 2026-04-29
**Slice/PR:** `refactor/code-quality-pass` (P2 aus `docs/archive/old-plans/REFACTORING_PLAN.md`)
**Risiko:** Niedrig (defense-in-depth, kein API-/UX-Bruch)

## Ziel

Verhindern, dass Auth-Material (Bearer-Tokens, signierte Tickets, API-Keys, Passwörter) versehentlich im Klartext in `backend/logs/*.log`, in `stderr`/`docker logs` oder im Werkzeug-Access-Log landet.

Bisheriger Stand:

- Logging hatte **keine** Redaktionsschicht. Maskierung war eine reine Disziplinfrage der jeweiligen Aufrufer.
- Werkzeug protokollierte die volle Request-Line inklusive Query-String (`?token=`, `?ticket=`).
- `before_request` schrieb auf DEBUG-Level den kompletten JSON-Body — Login-/Ticket-Endpunkte hätten damit Tokens reflektieren können.

## Identifizierte Leak-Vektoren (vor dem Fix)

| Quelle | Beispiel | Risiko |
|---|---|---|
| Werkzeug-Access-Log | `GET /api/simulation/<id>/stream?ticket=eyJ... HTTP/1.1` | Tickets im Container-Log |
| `before_request`-Debug | `Request body: {"password": "...", "api_key": "..."}` | Sensitive POST-Bodies |
| `before_request`-Debug | `Request: GET /api/...` über `request.full_path` denkbar | Query-String-Leak |
| Beliebige `logger.error(...)`-Aufrufe mit Upstream-Response-Body | `Ollama HTTP error: ... text=...` | Token-Reflektion seitens Upstream |

## Umsetzung

### 1. Zentraler Redaction-Filter (`backend/app/utils/logger.py`)

- Neue Klasse `RedactionFilter(logging.Filter)` rendert die finale Message via `record.getMessage()` und maskiert konservative Patterns:
  - `Authorization: Bearer <value>` → `Bearer ***`
  - `X-Agora-Token: <value>` → `X-Agora-Token: ***`
  - Query- und Form-Parameter (`token=`, `ticket=`, `api_key=`, `secret=`, `password=`, …) → Wert wird durch `***` ersetzt.
  - JSON-Style `"password": "..."` etc. → Wert ersetzt.
  - Env-Stil `LLM_API_KEY=...`, `*_TOKEN=...`, `*_SECRET=...`, `*_PASSWORD=...` → Wert ersetzt.
- Filter ist idempotent (`install_redaction_filter`) und wird sowohl auf den Logger als auch auf alle Handler gesetzt — damit ist auch das Propagieren über Sub-Logger abgedeckt.
- `record.exc_text` wird ebenfalls gescrubbt.
- `setup_logger(...)` installiert den Filter automatisch auf jedem neu konfigurierten Agora-Logger.

### 2. Werkzeug-Access-Log gehärtet (`backend/app/__init__.py`)

`create_app()` ruft direkt nach `setup_logger('agora')` zusätzlich
`install_redaction_filter(logging.getLogger('werkzeug'))` auf. Damit greift der Filter auch für die WSGI-Access-Lines, die Werkzeug standardmäßig auf seinem eigenen Logger emittiert.

### 3. JSON-Body-Logging entfernt

Der frühere `before_request`-Hook schrieb den kompletten JSON-Body auf DEBUG. Das wurde komplett entfernt; geloggt werden nur noch Method+Path (kein Query-String, kein Body). Begründung:

- Tickets-/Auth-Endpoints reflektieren sonst Auth-Material.
- DEBUG-Logs landen in `backend/logs/<datum>.log` und sind in Docker-Setups oft persistiert.
- Body-Inspektion ist eine Debug-Maßnahme und gehört nicht in den Default-Pfad.

## Tests

Neue Datei `backend/tests/test_logger_redaction.py` deckt:

- Scrub-Helper gegen 7 typische Secret-Shapes (Tickets, Bearer, Header, JSON-Body, Env-Style, Query-Param).
- Negativtests: harmlose Strings (Sim-IDs, Pfade, „no token provided") bleiben unverändert.
- Filter im laufenden Logger: Format-Args, Query-Token, JSON-Password, Idempotenz, Handler-Propagation, Stabilität bei Nicht-String-Args.

Resultat: `uv run pytest tests/test_logger_redaction.py` → 17 passed.

Vollständiges Quality-Gate: `npm run check` → 340 passed, 2 skipped (Redis-only), Lint und Frontend-Build sauber.

## Nicht im Scope

- Änderung an Log-Levels einzelner Aufrufer (z. B. ob ein Service-Logger Upstream-Error-Bodies überhaupt loggen sollte). Der Filter neutralisiert den Worst-Case; Detail-Hygiene bleibt eigenständige Folgearbeit.
- Externe Sinks (z. B. Loki/ELK). Wenn Logs an externe Aggregatoren gestreamt werden, sollte der Sink-Adapter idealerweise denselben Filter verwenden.

## Rollback

`git revert` der zugehörigen Commits. Der Filter ist additiv — Entfernen reaktiviert lediglich den vorherigen Klartext-Pfad. Es gibt keine Daten-/Schema-Migration.

## Querverweise

- `backend/app/utils/logger.py` — Filter & Installation.
- `backend/app/__init__.py` — Werkzeug-Hook, Body-Logging entfernt.
- `backend/tests/test_logger_redaction.py` — Coverage.
- `docs/archive/old-plans/REFACTORING_PLAN.md` — P2 ist damit erledigt.
- `docs/2026-04-29-p0-2a-signed-tickets.md` / `…-p0-2c-frontend-tickets.md` — Kontext, warum URL-Tickets überhaupt vorkommen können.
