# Auth-Dokumentation

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Master-Token, Workspace-API-Keys, Scopes, Ticket-Flow und Browser-Auth.

Code-Referenzen:

- [`../backend/app/utils/auth.py`](../backend/app/utils/auth.py) — Blueprint-/Token-Guard und Ticket-Auth
- [`../backend/app/utils/scopes.py`](../backend/app/utils/scopes.py) — Workspace-API-Key-Auflösung und Scope-Durchsetzung
- [`../backend/app/api/auth.py`](../backend/app/api/auth.py) — Ticket-Ausstellung
- [ADR-0001](decisions/0001-auth-model.md) — Architekturentscheidung

---

## 1. Auth-Modell

Agora ist weiterhin ein **Single-User-System**, besitzt aber zwei API-Credential-Klassen:

1. **Master-Token** `AGORA_AUTH_TOKEN` — administrativer Vollzugriff.
2. **Workspace-API-Keys** mit Präfix `ago_...` — persistiert, widerrufbar und scope-basiert.

Das ist kein vollständiges Human-Identity-/RBAC-System. Es gibt weder Benutzerkonten noch Teams/Rollenmodell; Scopes begrenzen API-Keys auf technische Fähigkeiten.

---

## 2. Empfohlene Header

Für neue Integrationen gelten diese Formen:

| Credential | Empfohlener Header | Beispiel |
|---|---|---|
| Master-Token | `Authorization: Bearer <AGORA_AUTH_TOKEN>` | Admin-/Operatorzugriff |
| Workspace-API-Key | `X-Agora-Api-Key: ago_...` | eingeschränkte Automation/Integration |
| Legacy | `X-Agora-Token: <token>` | Backward-Compatibility, nicht für neue Clients bevorzugen |

Wichtig: Die historische Blueprint-Guard-Implementierung akzeptiert weiterhin `X-Agora-Token` und `Authorization: Bearer`. Der Scope-Resolver priorisiert für Workspace-Keys dagegen ausdrücklich `X-Agora-Api-Key`. Die beiden Ebenen beschreiben denselben Authbereich aus unterschiedlichen Generationen des Codes; neue Doku und neue Clients sollen die obige Empfehlung verwenden.

---

## 3. Auth-Auflösung

### Blueprint-/Token-Guard

`install_blueprint_guard()` schützt `/api/*`-Blueprints und akzeptiert:

1. korrektes `AGORA_AUTH_TOKEN`,
2. aktiven Workspace-API-Key (`ago_...`),
3. für dafür markierte Endpunkte ein gültiges signiertes Ticket,
4. Open Mode nur, wenn kein Master-Token konfiguriert ist.

Der Master-Token-Vergleich ist timing-safe (`hmac.compare_digest`).

### Scope-Resolver

`_resolve_active_api_key()` in `scopes.py` prüft Credential-Kandidaten in dieser Reihenfolge:

1. `X-Agora-Api-Key: ago_...`
2. `Authorization: Bearer ...`
3. `X-Agora-Token: ...` als Backward-Compatibility

Ein gültiger Master-Token wird intern als synthetischer Admin-Key behandelt und passiert jeden Scope-Check.

---

## 4. Scope-Hierarchie

`@require_scope("...")` schützt sensitive Endpunkte zusätzlich zur allgemeinen Auth.

Regeln:

1. `admin` erfüllt jeden Scope.
2. Ein exakt passender fine-grained Scope erfüllt sich selbst, z. B. `report:read`.
3. `write` erfüllt `*:write`, `*:control` und `*:read`.
4. `read` erfüllt `*:read`.

Typische Scopes sind unter anderem:

- `report:read`
- `report:write`
- `simulation:control`
- `graph:write`

Die aktuelle, vollständige Durchsetzung steht im Code. Nicht jeder historische Endpoint besitzt bereits einen eigenen `@require_scope`; dort greift weiterhin der allgemeine Token-/API-Key-Guard. Deshalb darf aus der Existenz des Scope-Systems **kein Deny-by-default-RBAC für jede Route** abgeleitet werden.

### Fehler

- kein gültiges Credential → 401
- gültiger API-Key, aber Scope fehlt → 403
- widerrufener API-Key → abgelehnt

---

## 5. Open Mode

Wenn kein `AGORA_AUTH_TOKEN` gesetzt ist, kann der Auth-Guard technisch im Open Mode arbeiten.

Für aktuelle Setups gilt jedoch:

- lokale Entwicklung mit Debug kann diesen Modus bewusst verwenden,
- `AGORA_ALLOW_ANONYMOUS=true` ist ein ausdrückliches Opt-in,
- außerhalb von Debug/Opt-in soll `Config.validate()` eine fehlende Auth-Konfiguration blockieren,
- Open Mode ist **kein** akzeptabler Internet-/LAN-Produktionsmodus.

`/api/status` weist den Authzustand aus. Bei unerwartetem Open Mode zuerst die Startup-Logs und `.env` prüfen.

---

## 6. Signierte Tickets für URL-Auth

Browser-APIs wie `EventSource` oder direkte Download-Navigation können nicht immer den normalen Custom-/Bearer-Header verwenden. Dafür existiert `POST /api/auth/ticket`.

Ablauf:

1. Client authentifiziert den Ticket-Request normal per Master-Token oder Workspace-API-Key.
2. Backend erzeugt ein kurzlebiges, scope-gebundenes Ticket.
3. Client hängt `?ticket=<signed>` an die freigegebene SSE-/Download-URL.
4. Backend prüft Signatur, Ablauf und erwarteten Scope.

Beispiel:

```bash
curl \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST http://localhost:5001/api/auth/ticket \
  -d '{"scope":"sse:sim_123","ttl_seconds":60}'
```

### Single-Use ist endpointabhängig

`allow_ticket_auth(..., single_use=True)` konsumiert ein Ticket beim ersten erfolgreichen Zugriff. Der Default ist `True`.

SSE-Endpunkte können `single_use=False` verwenden, damit ein `EventSource` innerhalb der kurzen Ticket-TTL reconnecten kann. Dort begrenzt die TTL den Replay-Zeitraum. Deshalb nicht pauschal dokumentieren: „jedes Agora-Ticket ist single-use“.

---

## 7. `?token=` ist kein Produktionspfad

Der alte Query-Parameter `?token=<bearer>` ist außerhalb des Flask-Debug-Modus deaktiviert und wird protokolliert.

Für URL-Auth gilt:

```text
?ticket=<signed-short-lived-ticket>
```

Nicht:

```text
?token=<master-secret>
```

Dadurch landet der langfristige Master-Token nicht unnötig in Browser-History, Proxy-Logs oder Referer-Kontexten.

---

## 8. Workspace-API-Key-Persistenz

Workspace-API-Keys werden nicht nur im Prozessspeicher gehalten. Der Store wird unter `backend/data/api_keys.json` persistiert und als kompletter JSON-Blob mit Fernet verschlüsselt.

Master-Key:

```text
AGORA_FERNET_KEY
```

In Produktion ist ein stabiler Schlüssel Pflicht. Ein nur im Debug-Modus temporär generierter Fernet-Key macht den persistierten Store nach einem Neustart unlesbar und ist deshalb kein Produktionssetup.

Details: [`secret-key-lifecycle.md`](secret-key-lifecycle.md).

---

## 9. Frontend-Token-Speicherung

Das Browser-Frontend muss für das Single-User-Master-Token einen Client-seitigen Zustand halten, solange kein serverseitiger Session-/HttpOnly-Cookie-Login existiert.

Sicherheitsgrenze:

- Jeder Token im JavaScript-Kontext kann durch eine erfolgreiche XSS im selben Origin kompromittiert werden.
- Persistenter Browser-Storage vergrößert das Zeitfenster.
- Memory-Storage reduziert Persistenz, ist aber keine XSS-Sandbox.

Agora besitzt aktuell keinen vollständigen Benutzer-Login mit HttpOnly-Session-Cookie und CSRF-Modell. Ein solcher Ausbau gehört in ein späteres Multi-User-/Identity-Design und ist **nicht** Voraussetzung dafür, den aktuellen Single-User-Stack korrekt zu betreiben.

---

## 10. Praktische Beispiele

### Master-Token

```bash
curl -fsS \
  -H "Authorization: Bearer $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

### Workspace-API-Key

```bash
curl -fsS \
  -H "X-Agora-Api-Key: $AGORA_API_KEY" \
  http://localhost:5001/api/report/<report_id>
```

### Legacy-Kompatibilität

```bash
curl -fsS \
  -H "X-Agora-Token: $AGORA_AUTH_TOKEN" \
  http://localhost:5001/api/status
```

Funktioniert weiterhin, ist aber nicht die bevorzugte Form für neue Integrationen.

---

## 11. Sicherheitsregeln

- Master-Token niemals in URL, Issue, Chat, Screenshot oder Log schreiben.
- Workspace-API-Keys möglichst mit minimal nötigem Scope erzeugen.
- Keys nach Leak-Verdacht widerrufen/rotieren.
- `AGORA_FERNET_KEY` und `AGORA_AUTH_TOKEN` getrennt sichern.
- Public Exposure nur hinter dem gehärteten Deployment-/TLS-/VPN-Konzept aus [`deployment-prod-like.md`](deployment-prod-like.md).
- Authentifizierung ersetzt keine Prompt-Injection-Härtung von untrusted Inhalten (#1224).
