# p2 — Issue #132: Backend-Log-Viewer

**Issue:** [#132](https://github.com/arn0ld87/agora/issues/132)
**Branch:** `claude/issue-132-logs`
**Aufwand:** size-l (geplant), tatsächlich kompakt in einem Schub

## Umsetzung
- Backend: `backend/app/api/logs.py` mit `GET /api/logs` (Tail) und `GET /api/logs/stream` (SSE).
- Path-Traversal-Schutz: kein `?file=`-Parameter; Pfad wird hardcoded aus `LOG_DIR` + heutigem Datum gebildet, mit `relative_to`-Check als Defense-in-Depth.
- Auth: Standard-Blueprint-Guard (`AGORA_AUTH_TOKEN`), ablesbar im Test (Bearer-Header).
- Tail-Defaults: 200 Lines, Cap 2000.
- Level-Filter heuristisch (`error`/`warn`/`info`/`debug`).
- SSE: Heartbeat 15 s (gegen Reverse-Proxy-Idle-Timeouts), `X-Accel-Buffering: no`.
- Frontend: globaler `LogDrawer.vue` (Bottom-Drawer, max 50vh / 480 px), Toggle via FAB-Button und Hotkey `Ctrl+Shift+L` (in `App.vue`). Persistenz `localStorage` (`agora.ui.logDrawer.open`). Sticky-Scroll wiederverwendet aus #130. Level-Select, Suchfeld, Pause-Toggle. Ringpuffer 5000 Lines.
- i18n DE/EN für `logs.drawer.*`.

## Tests
- 9 neue Backend-Tests (`backend/tests/test_logs_api.py`): Tail-Default, Cap, Level-Filter, Auth-401-ohne-Token, 200-mit-Bearer, ungültige Tail-Werte, Path-Traversal-Schutz (Param wird ignoriert), leere Datei → 200.
- `npm run check` grün: 753 Backend, 65 Frontend.

## Out of Scope (Folge-Issues empfohlen)
- Multi-File-Auswahl (über mehrere Tage hinweg suchen) — heute nur die heutige Datei.
- Frontend-Tests für `LogDrawer.vue` (Komponente nutzt EventSource, das in JSDOM nicht trivial mockbar ist).

## Status
- [x] Backend implementiert + getestet
- [x] Frontend implementiert
- [x] i18n DE/EN
- [x] `npm run check` grün
- [ ] Browser-Smoke (durch User)
