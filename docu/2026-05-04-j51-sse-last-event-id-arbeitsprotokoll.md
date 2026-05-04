# Slice J.5.1 / Issue #233 — SSE-Reconnect: `id:`-Frames + `Last-Event-ID`

**Datum:** 2026-05-04
**Branch:** `fix/j5-1-sse-last-event-id`
**Basis:** `origin/main` HEAD `5bbcb16`
**Followup auf:** PR #232 (Slice J.5)

---

## Problem

J.5 hatte `retry: 5000` und bei `simulation_stream.py` bereits `id:`-Frames eingeführt.
Für `/api/logs/stream` fehlten jedoch:

1. **Datenverlust beim Reconnect:** Browser-`EventSource` verbindet sich nach einem
   Abbruch mit derselben URL neu — ohne `id:`-Frames kann er dem Server keinen
   Wiederaufsetzpunkt mitteilen. Der Server startete ab Datei-Ende (Default), alle
   Zeilen dazwischen gingen verloren.

2. **Duplikate bei statischem `?offset=`:** Wenn der Client `?offset=0` in der URL
   hatte, begann der Stream nach dem Reconnect erneut von Byte 0 — alle schon
   gesehenen Zeilen kamen doppelt.

Ursache: RFC 8895 §9.2 schreibt vor, dass der Browser beim Reconnect automatisch
`Last-Event-ID: <n>` sendet — aber nur, wenn der Server pro Event ein `id: <n>`-Frame
emittiert hatte und der Server diesen Header auch auswertet.

---

## Lösung

### `backend/app/api/logs.py`

- **`Last-Event-ID`-Header wird vor dem Generator ausgewertet** (Request-Funktion,
  nicht im Generator-Body). Parsing: `int()` mit `ValueError`-Catch; negatives
  Ergebnis wird verworfen.
- **Priorität im Generator:** `Last-Event-ID`-Header > `?offset=`-Query > Datei-Ende.
  Der bestehende Offset-Logik-Block wurde entsprechend umgebaut.
- **`id:`-Frame pro Datenzeile:** Das interne `readline()`-basierte Lesen (statt
  `splitlines()`) ermöglicht, `fh.tell()` direkt nach jeder Zeile als ID zu verwenden
  — kein Längen-Rekonstruktions-Hack, kein `\r\n`-Edge-Case.
- **Kein `event:`-Frame:** `LogDrawer.vue` lauscht via `onmessage` auf den
  Default-Event-Namen `message`. Ein expliziter `event: line`-Frame würde den
  Konsumenten stumm schalten (verifiziert via `rg`).

### `backend/app/api/simulation_stream.py`

- `Last-Event-ID`-Header wird gelesen und via `logger.info(...)` dokumentiert.
- **Kein Verhaltensänderung am Subscribe:** Der Bus (InMemoryEventBus) puffert keine
  vergangenen Events. Reconnect startet best-effort ab `now`. Volle Replay-Semantik
  braucht Persistenz im Bus (eigener Slice).
- Kommentar im Docstring der View-Funktion dokumentiert diese Einschränkung explizit.

---

## Geänderte Files

| Datei | Art |
|---|---|
| `backend/app/api/logs.py` | Geändert — `id:`-Frames + `Last-Event-ID`-Auswertung |
| `backend/app/api/simulation_stream.py` | Geändert — `Last-Event-ID`-Logging + Doku |
| `backend/tests/api/test_logs_stream_reconnect.py` | Neu — 5 pytest-Cases |
| `CHANGELOG.md` | Geändert — `[Unreleased] ### Fixed`-Eintrag |

---

## Tests

Neue Datei: `backend/tests/api/test_logs_stream_reconnect.py`

| Test | Kurzbeschreibung |
|---|---|
| A `test_stream_emits_id_frame_per_data_line` | Jeder `data:`-Frame hat ein vorangestelltes `id: <int>`-Frame; Werte monoton steigend; letzter Wert = Dateigröße |
| B `test_last_event_id_overrides_url_offset` | Header `Last-Event-ID` überstimmt `?offset=0`; erster empfangener Frame ist Zeile 4, nicht Zeile 1 |
| C `test_no_duplicates_on_reconnect` | Zweite Verbindung mit letztem `id:`-Wert liefert keine alten Zeilen; neue Zeilen vorhanden |
| D `test_invalid_last_event_id_falls_back_to_url_offset` | Garbage-Header → 200, Stream startet korrekt ab `?offset=0` |
| E `test_simulation_stream_logs_last_event_id` | `simulation_stream` loggt `Last-Event-ID`-Header (caplog via direktem Handler-Attach, da `propagate=False`) |

Alle 5 Tests grün. Gesamtes Backend: 1370 passed, 9 skipped.

---

## Risiken / Caveats

- **Bus-Replay fehlt:** `simulation_stream.py` kann beim Reconnect keine Events
  wiederholen — der InMemoryEventBus puffert nicht. Logging ist der einzige Effekt.
  Saubere Lösung braucht persistierten Event-Store (separater Slice).
- **Frontend-Konsument auf `message`:** `LogDrawer.vue` nutzt `onmessage`. Ein
  `event: line`-Frame würde den Konsumenten brechen. Der Verzicht auf `event:`-Frames
  ist bewusst und via `rg` verifiziert.
- **`scripts/`-Ruff-Fehler:** 16 pre-existing Fehler in OASIS-Subprozess-Wrappern
  (`scripts/run_*.py`, `scripts/security_verify.py`) — laut CLAUDE.md nicht anfassen.
  `app/` und `tests/` sind ruff-clean.
