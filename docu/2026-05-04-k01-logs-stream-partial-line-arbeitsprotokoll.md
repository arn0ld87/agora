# Slice K.0.1 — `/api/logs/stream` Partial-Line-Schutz

**Datum:** 2026-05-04
**Followup auf:** PR #254 (Slice K.0)
**Quelle:** Gemini-Code-Assist MEDIUM-Comment auf PR #254 (`backend/app/api/logs.py:266`)

## Problem

Nach dem K.0-Switch auf Binärmodus (`open('rb')`) konnte `fh.readline()` bei
EOF mitten in einer noch nicht ganz geschriebenen Zeile zurückkehren. Wir
haben die Halb-Zeile dann trotzdem dekodiert und `offset` ans Datei-Ende
verschoben. Konsequenzen:

1. Bei Multi-Byte-UTF-8 mid-write → `decode(errors='replace')` produziert
   ein Replacement-Char in der Zeile.
2. Der Anfang der echten vollständigen Zeile geht verloren, weil der
   Stream beim nächsten Poll-Zyklus erst nach dem alten EOF weiterliest.

Der Bug war latent — auf produktiv-langsamen Logwritern statistisch
unwahrscheinlich, bei hoher Last aber real.

## Lösung

Im `while True`-Read-Loop: wenn die zurückgelesene Zeile nicht auf `\n`
endet, **break** ohne `offset` vorzurücken. Im nächsten Poll-Zyklus
(`time.sleep(_STREAM_POLL_SEC)` → erneuter `current_path.stat()` →
`fh.seek(offset)`) wird die jetzt vollständige Zeile sauber gelesen.

```python
while True:
    line = fh.readline()
    if not line:
        break
    if not line.endswith(b'\n'):
        # Partial line at EOF — offset bleibt, retry im naechsten Poll
        break
    line_offset = fh.tell()
    offset = line_offset
    ...
```

Geminis Snippet 1:1 übernommen.

## Edge-Cases

- **Letzte Zeile ohne `\n` (abruptes Programmende):** wird nie gestreamt.
  Akzeptabel — Logger flushen ohnehin zeilenweise mit `\n`.
- **Leere Datei:** `readline()` gibt `b''`, erste `if not line: break` greift.
- **Datei-Rotation:** `if size < offset: offset = 0` außerhalb des
  Read-Loops — unverändert.

## Files geändert

- `backend/app/api/logs.py` — 6 Zeilen Patch im Read-Loop + Kommentar
- `backend/tests/api/test_logs_stream_reconnect.py` — neuer Test G
- `CHANGELOG.md` — `[Unreleased] ### Fixed`-Eintrag

## Tests

- **Test G** (`test_partial_line_at_eof_does_not_advance_offset`): schreibt
  `"vollständige Zeile mit Umlaut\nhalbe Zeile ohne newline"` (bewusst
  ohne abschließendes `\n`), erwartet exakt 1 data-Frame mit `id` nach
  Zeile 1 (nicht am Datei-Ende).
- **Bestehende 6 Tests** unverändert grün.
- **Volltest:** 1372 passed (1 mehr als nach K.0), 9 skipped.

## Risiken

Keine. Funktional identisch für log-Files mit ordentlichem `\n`-Abschluss
pro Zeile (Standard für Python `logging`-Handler, `journalctl`, `tail -f`).
