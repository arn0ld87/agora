# Issue #40 (EPIC-05-ST-04) — SSE/WebSocket-Strategie: Status-Dokumentation

**Datum:** 2026-05-01  
**Issue:** [#40](https://github.com/arn0ld87/agora/issues/40) — EPIC-05-ST-04 — SSE/WebSocket-Strategie untersuchen  
**Typ:** Spike  
**Fazit:** Untersuchung durch Implementierung abgeschlossen. SSE ist der gewählte und produktiv laufende Ansatz.

## Fragestellung des Spikes (aus Issue #40)

> Vergleich SSE (aktuell, läuft) vs. WebSocket. Bewertung Wartung, Browser-Kompatibilität, Mehrwert für bestehende Use-Cases (Run-Live-Updates, Report-Stream).

## IST-Zustand

| Aspekt | Bewertung |
|---|---|
| **SSE-Implementierung** | `frontend/src/composables/useEventStream.js` — SSE-backed, gleiche API-Signatur wie `usePolling` |
| **Backend-Stream** | `GET /api/simulation/<id>/stream` mit 15-s-Heartbeat (Issue #9 Phase C) |
| **Browser-Kompatibilität** | `EventSource` nativ in allen modernen Browsern, kein Polyfill nötig |
| **Auth** | Signed Tickets (`?ticket=<signed>`) via `POST /api/auth/ticket`, scope-bound, single-use, 60 s TTL (P0.2) |

## SSE vs. WebSocket — praktische Entscheidung

Die Entscheidung fiel implizit mit Issue #9 (Event-Driven IPC). SSE wurde gewählt weil:

1. **Unidirektional ausreichend**: Run-Live-Updates und Report-Stream sind Server→Client. Client→Server läuft über REST.
2. **Einfachere Infrastruktur**: Kein WS-Upgrade-Handling nötig, kein eigener WS-Server-Prozess, kein `websockets`-Package.
3. **Auto-Reconnect**: `EventSource` hat natives Reconnect — kein eigener Retry-Layer wie bei WebSocket.
4. **HTTP/2-kompatibel**: SSE streamed über Standard-HTTP, WS braucht eigenes Protokoll-Upgrade.

WebSocket hätte keinen messbaren Mehrwert für die bestehenden Use-Cases gebracht (kein bidirektionaler Echtzeit-Chat, kein Kollaborations-Editing).

## Referenzen

- Issue #9 (Event-Driven IPC): SSE-Bridge als Phase C
- `frontend/src/composables/useEventStream.js`: "SSE-backed sibling of usePolling (Issue #9 Phase C)"
- `frontend/src/api/stream.js`: SSE-URL-Builder mit Auth-Token
- `backend/app/api/simulation_run.py`: SSE-Stream-Route

Issue #40 kann geschlossen werden.
