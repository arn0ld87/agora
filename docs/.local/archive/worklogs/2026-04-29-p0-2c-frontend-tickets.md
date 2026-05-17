# P0.2c — Frontend-Migration auf Tickets

**Datum:** 2026-04-29
**Slice:** P0.2c (siehe `PLAN.md`)
**Branch:** `security/repo-hardening`

## Ziel

Den einzigen verbleibenden `?token=`-Pfad im Frontend (SSE) auf signierte Tickets umstellen. Downloads laufen alle über axios mit Header-Auth — kein Frontend-Eingriff nötig.

## Änderungen

- `frontend/src/api/stream.js`
  - Neuer Helper `fetchStreamTicket(simulationId)` — `POST /api/auth/ticket` mit Scope `sse:<id>` über die bestehende axios-Instance (Header-Auth wird vom Interceptor angehängt).
  - `buildSimulationStreamUrl` und `openSimulationStream` sind jetzt `async` und hängen `?ticket=...` statt `?token=...` an.
  - Im open-Mode-Backend (kein Token verfügbar) wird gar kein Ticket gefordert — die alten Local-Setups funktionieren weiter.
- `frontend/src/composables/useEventStream.js`
  - `start()` ist jetzt `async`, das Ticket-Fetching passiert vor dem `EventSource`-Open. Fehler beim Ticket-Fetch landen im selben `error`-Handler wie bisher Network-Probleme.
  - Caller (`Step3Simulation.vue`) ändert sich nicht — `statusStream.start()` läuft weiter fire-and-forget.

### Backend-Begleitänderung

Damit EventSource-Reconnects innerhalb der Ticket-TTL nicht durch Single-Use ausgehebelt werden:

- `allow_ticket_auth(..., single_use=False)` für SSE.
- Default bleibt `single_use=True` — Downloads sind weiterhin Replay-geschützt.
- Tests in `test_auth_ticket.py` decken beide Pfade ab (SSE reusable / Download single-use).

## Verifikation

- `npm run check` → Backend 321/321 + 2 skipped (Redis), Frontend-Lint clean, Vite-Build clean.
- Manueller Smoke (lokal): Backend mit `AGORA_AUTH_TOKEN=…` starten, Frontend öffnen, eine Simulation starten und prüfen dass im Browser-Devtools die SSE-URL `?ticket=v1.…` enthält und keine `?token=` mehr.

## Bekannte Lücken

- `?token=` Query-Pfad ist serverseitig weiter aktiv (mit Deprecation-Warning). Hard-Removal in einem separaten Slice nach kurzer Beobachtungs-Phase (Telemetrie-Ticket folgt).
- Reconnect-TTL: Nach 60 s ohne erfolgreiche Verbindung bricht der Stream ab, weil das Ticket abgelaufen ist. Akzeptabel — `useEventStream` hat eh `MAX_RECONNECT_ATTEMPTS=5` und ein neuer `start()` holt ein frisches Ticket.

## Status

**Erledigt 2026-04-29.**
