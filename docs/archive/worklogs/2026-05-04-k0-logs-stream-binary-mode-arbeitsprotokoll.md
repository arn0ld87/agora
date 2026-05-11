# Slice K.0 — Logs-Stream Binärmodus-Followup (Gemini HIGH auf PR #253)

**Datum:** 2026-05-04
**Branch:** `fix/j5-1-followup-binary-mode`
**Basis:** `origin/main`, HEAD `0e3758e`

## Problem

Gemini-Code-Assist hat nach dem Merge von PR #253 (Slice J.5.1) ein **HIGH-Finding** auf
`backend/app/api/logs.py:269` gepostet:

> Das Öffnen der Logdatei im Textmodus (`'r'`) in Kombination mit `fh.tell()` und
> `fh.seek()` für Byte-Offsets ist problematisch. In Python 3 liefert `tell()` bei
> Textstreams einen opaken Cookie (Integer), der nicht zwingend dem Byte-Offset entspricht.
> Zudem ist `seek()` mit einem Byte-Offset in Textstreams laut Dokumentation nicht
> unterstützt (außer für 0 und das Dateiende) und führt zu undefiniertem Verhalten. Dies
> kann insbesondere bei Zeilenumbruch-Konvertierungen (CRLF vs LF) oder Multi-Byte-Encodings
> dazu führen, dass Reconnects an falschen Positionen starten oder die Validierung gegen
> `file_size` fehlschlägt.

Auf Linux/macOS mit reinem LF/UTF-8 funktioniert es praktisch — die Semantik ist aber laut
CPython-Doku ungarantiert.

## Lösung

Datei im Binärmodus (`'rb'`) öffnen. `tell()` liefert dann garantiert Byte-Offsets.
Dekodierung erfolgt pro Zeile mit `line.decode('utf-8', errors='replace')`.

## Geänderte Dateien

| Datei | Art |
|---|---|
| `backend/app/api/logs.py` | Open-Mode `'r'` → `'rb'`, per-Zeilen-Dekodierung, Docstring-Ergänzung |
| `backend/tests/api/test_logs_stream_reconnect.py` | Neuer Test F: Multi-Byte-UTF-8-Byte-Offsets |
| `CHANGELOG.md` | `[Unreleased] ### Fixed`-Eintrag ergänzt |
| `docs/2026-05-04-k0-logs-stream-binary-mode-arbeitsprotokoll.md` | diese Datei |

## Tests

- Bestehende 5 Tests (A–E) unverändert, alle grün.
- Neuer Test F (`test_id_frames_correct_for_multibyte_utf8_lines`): schreibt zwei Zeilen
  mit Umlauten und Emoji (`Müller-Maße: 42 €`, `Test 🚀 läuft`) als raw bytes in die
  Logdatei und prüft, dass die `id:`-Werte exakt den Byte-Offsets (nicht Zeichen-Offsets)
  entsprechen.

## Risiken

Keine. Auf LF-only UTF-8-Dateien (Linux-Prod, macOS-Dev) ist das Verhalten funktional
identisch. Korrektheit ist jetzt für Multi-Byte-Zeichen und CRLF garantiert.
