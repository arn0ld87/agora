# Arbeitsprotokoll: F3 Gevent-Test Followup (PR #241, Gemini-HIGH)

**Datum:** 2026-05-04
**Branch:** `fix/f3-gunicorn-gevent`
**Scope:** `backend/tests/test_gevent_fork.py`

---

## Echter Fail-Grund (aus `gh run view 25293295430 --log-failed`)

Die pytest-Tests selbst liefen durch (1365 passed). Der CI-Exit-Code 1 kam
ausschliesslich vom ruff-Check:

```
F401 `gevent.monkey` imported but unused; consider using `importlib.util.find_spec`
  --> tests/test_gevent_fork.py:12:12
   |
10 | try:
11 |     import gevent
12 |     import gevent.monkey
   |            ^^^^^^^^^^^^^
13 |     GEEVENT_AVAILABLE = True
14 | except ImportError:
   |
help: Remove unused import: `gevent.monkey`

Found 1 error.
```

`gevent.monkey` wurde im Top-Level-Try-Block importiert (Zeile 12), aber
innerhalb von `test_gevent_importable` direkt per `patch_all()` benutzt —
ruff sieht den Top-Level-Import als ungenutzt.

Zusaetzlich erzeugte `patch_all()` im Test-Body eine `MonkeyPatchWarning`
(nur als Warning, kein Test-Failure in dieser pytest-Konfiguration, da kein
`filterwarnings = error` gesetzt):

```
MonkeyPatchWarning: Monkey-patching ssl after ssl has already been imported
may lead to errors ... Modules that had direct imports (NOT patched):
['urllib3.util', 'redis.asyncio.connection', 'anyio.streams.tls',
'urllib3.util.ssl_']
```

---

## Gemini-Finding-Zitat (PR #241, HIGH)

> Der Test `test_gevent_importable` wird fehlschlagen, sobald `gevent` in der
> Umgebung installiert ist. Die Funktion `gevent.monkey.is_module_patched("socket")`
> gibt nur dann `True` zurueck, wenn zuvor explizit `gevent.monkey.patch_all()`
> aufgerufen wurde. Da laut Changelog lediglich die "Importierbarkeit" geprueft
> werden soll, ist die Assertion auf den Patch-Status hier unzutreffend und
> sollte durch einen einfachen Check auf das Vorhandensein des Moduls ersetzt
> werden.

---

## Loesung

Zwei Aenderungen in `backend/tests/test_gevent_fork.py`:

1. **Top-Level-Try-Block:** `import gevent.monkey` entfernt (war unused, ruff F401).
   Nur `import gevent` bleibt — genuegt fuer den `GEEVENT_AVAILABLE`-Flag.
   `# noqa: F401` ergaenzt, da ruff den try-except-Presence-Check-Import
   korrekt als "nur fuer Seiteneffekt" einordnen muss.

2. **`test_gevent_importable`:** `patch_all()` und `is_module_patched()`-Assertion
   entfernt. Stattdessen:
   - `import gevent` + `import gevent.monkey` lokal (import-only check)
   - `assert gevent.__version__` als ehrlicher Importierbarkeits-Smoke

### Begruendung

`patch_all()` gehoert zur Worker-Init-Phase von gunicorn (CMD im Dockerfile),
nicht in die Test-Suite. Im Test-Kontext hat pytest den ssl-Stack bereits
importiert — `patch_all()` wirft dann `MonkeyPatchWarning` wegen
Post-Import-Patching. Selbst wenn die Warning kein hartes Failure erzeugt,
ist die Semantik falsch: der Test soll beweisen, dass `gevent` installiert
und importierbar ist — nicht, dass das Monkey-Patching in einer sauberen
Pre-Import-Umgebung funktioniert (das ist gunicorns Aufgabe).

`assert gevent.__version__` ist der minimale, semantisch korrekte Check.

---

## Verifikation

```
# Schemas: kein Drift
git diff --exit-code schemas/  -> sauber

# Gevent-Test isoliert
uv run pytest tests/test_gevent_fork.py -v
-> 2 passed in 3.70s (kein MonkeyPatchWarning)

# Ruff
uv run ruff check app/ tests/
-> All checks passed!

# Voller Backend-Lauf
uv run pytest -x -q
-> 1365 passed, 9 skipped, 4 deselected, 3 warnings in 77.17s
```

---

## Betroffene Dateien

- `backend/tests/test_gevent_fork.py` — F401-Fix + patch_all()-Entfernung
- `CHANGELOG.md` — [Unreleased] ### Fixed Eintrag
- `docu/2026-05-04-f3-gevent-test-followup-arbeitsprotokoll.md` — dieses File
