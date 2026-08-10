# Auth-Dokumentation

**Stand:** 2026-08-11, Europe/Berlin
**Scope:** API-Token-Vertrag, Workspace-API-Keys, Scopes, Ticket-Flow, Frontend-Storage-Optionen.
**Code:** [`../backend/app/utils/auth.py`](../backend/app/utils/auth.py), [`../backend/app/utils/scopes.py`](../backend/app/utils/scopes.py), [`../backend/app/api/auth.py`](../backend/app/api/auth.py), [ADR-0001](decisions/0001-auth-model.md)

---

## Token-Header-Vertrag

Agora schuetzt alle `/api/*`-Routen mit einem statischen Bearer-Token
(`AGORA_AUTH_TOKEN` im Backend, `VITE_AGORA_TOKEN` oder
`localStorage.agora_token` im Frontend).

| Header | Wert | Verwendung |
|---|---|---|
| `X-Agora-Token` | `<token>` | Primaerer Weg; Axios-Interceptor haengt ihn automatisch an. |
| `Authorization` | `Bearer <token>` | Fallback, z.B. fuer curl/Postman. |

Der Token-Vergleich im Backend ist timing-safe (`hmac.compare_digest`).

---

## Die drei Auth-Wege

`_extract_token()` liest genau einen Wert (Header zuerst), und die Guards
pruefen ihn danach in fester Reihenfolge:

1. **Master-Token** — `AGORA_AUTH_TOKEN`, timing-safe verglichen.
2. **Workspace-API-Key** — jeder Token mit Praefix `ago_` wird gegen den
   API-Key-Store geprueft und muss `status == "active"` tragen. Ein
   widerrufener Key wird abgelehnt und protokolliert. Verwaltung ueber
   `/api/api-keys`.
3. **Open Mode** — ist **kein** `AGORA_AUTH_TOKEN` gesetzt, laesst der Guard
   jeden Aufruf durch. Das ist kein Fehler, sondern der lokale
   Bequemlichkeitsmodus — und der Grund, warum `/api/status` den Auth-Modus
   (`token` / `anonymous` / `open` / `misconfigured`) ausweist. Fuer jeden
   Betrieb ausserhalb des eigenen Rechners ist er unzulaessig.

## Scopes

API-Keys tragen Scopes; einzelne Routen fordern sie ueber
`@require_scope("report:read")`, `"report:write"`, `"simulation:control"`,
`"graph:write"` und weitere. Der Master-Token unterliegt keiner
Scope-Pruefung. Katalog und Ableitungslogik: [`scopes.py`](../backend/app/utils/scopes.py).

---

## Ticket-Flow (URL-Auth)

Fuer Ressourcen, die Browser nicht per Custom-Header anfragen koennen
(SSE-Streams, Download-Links), stellt das Backend
`POST /api/auth/ticket` bereit.

1. Client holt Ticket via Header-Auth:
   ```bash
   curl -H "X-Agora-Token: $TOKEN" \
     -X POST http://localhost:5001/api/auth/ticket \
     -d '{"scope": "sse:sim_123", "ttl_seconds": 60}'
   ```
2. Backend liefert `{"ticket": "v1.<exp>.<scope>.<sig>"}`.
3. Client baut URL mit `?ticket=<signed>`.
4. Backend prueft Signatur, Scope und Single-Use via Redis (Multi-Worker-
   safe) oder In-Memory-Fallback.

Das Ticket ist scope-bound und single-use. `ttl_seconds` ist optional:
Default **60 s**, Maximum **300 s** — darueber antwortet der Endpunkt mit
400 und `code=invalid_ttl`. Kein Bearer im URL, Proxy-Log oder Referer.

---

## Query-Token: in Produktion abgeschaltet

`?token=<bearer>` wird **ausserhalb des Flask-Debug-Modus verworfen** — der
Wert wird nicht ausgewertet, der Aufruf laeuft in den Auth-Fehler, und das
Backend protokolliert das auf Log-Level `error`. Nur mit `FLASK_DEBUG` wird
er noch als Fallback akzeptiert und mit einer Warnung quittiert.

Neue Query-Tokens sind projektweit untersagt; URL-Auth laeuft
ausschliesslich ueber `?ticket=<signed>`.

---

## Frontend-Token-Storage

### Option A: localStorage (Dev-Default)

```javascript
localStorage.setItem('agora_token', 'mein-token')
```

**Risiko:** XSS kann `localStorage.getItem('agora_token')` auslesen. Token
ueberlebt Page-Reload und ist persistent.

**Wann:** Lokale Entwicklung, vertrauenswuerdige Browser.

### Option B: Memory-Mode (Prod-Empfehlung)

```bash
# .env oder Build-Time
VITE_AGORA_TOKEN_STORAGE=memory
```

```javascript
import { setAgoraToken } from '@/api'
setAgoraToken('mein-token')  // Lebt nur im JS-Heap
```

**Vorteil:** Keine Persistence; XSS-Exploit muss im aktiven Tab passieren.
Token ueberlebt keinen Reload.

**Nachteil:** Nach Page-Reload muss der Token erneut gesetzt werden (z.B.
durch erneutes Login oder injiziertes Secret bei SPA-Reload).

### Option C: HttpOnly-Cookie (Zielarchitektur)

Die sauberste Prod-Loesung ist ein Session-Backend, das den Token als
`HttpOnly; Secure; SameSite=Strict`-Cookie setzt. Der Frontend-Code
braucht dann keinen Token mehr zu kennen; der Browser sendet das Cookie
automatisch.

Dies erfordert:
- Einen `/api/auth/login`-Endpoint, der das Cookie setzt.
- CSRF-Protection fuer state-changing Requests.
- Session-Storage im Backend (Redis oder DB).

Agora hat aktuell keinen Session-Login; das ist eine geplante
Nachfolgearbeit.

---

## Empfohlene Konfiguration

| Umgebung | Storage | Begruendung |
|---|---|---|
| Dev (lokal) | `localStorage` | Bequem, Page-Reload ueberlebt, Dev-Maschine ist vertrauenswuerdig. |
| Prod (Docker, Tailscale) | `memory` | Keine Persistence, minimiert XSS-Residuum. Token nach Deployment-Restart via Login/Inject erneut setzen. |
| Prod (Internet-exposed) | HttpOnly-Cookie | Nicht implementiert; empfohlen fuer Follow-Up. |
