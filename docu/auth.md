# Auth-Dokumentation

**Stand:** 2026-05-01, Europe/Berlin
**Scope:** API-Token-Vertrag, Ticket-Flow, Frontend-Storage-Optionen.

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

Das Ticket ist 60 s gueltig, scope-bound und single-use. Kein Bearer im
URL, Proxy-Log oder Referer.

---

## Query-Token-Deprecation

`?token=<bearer>` ist noch aktiv, aber deprecated. Jeder Aufruf loggt ein
Warning. Neuer Code sollte `?ticket=<signed>` verwenden.

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
