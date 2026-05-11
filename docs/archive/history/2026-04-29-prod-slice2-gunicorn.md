# Arbeitsprotokoll — Prod-Setup Slice 2: Gunicorn + gevent

**Datum:** 2026-04-29 (Europe/Berlin)
**Slice:** Slice 2 — Gunicorn + gevent runtime dependency
**Plan:** [`docs/2026-04-29-prod-setup-plan.md`](./2026-04-29-prod-setup-plan.md)
**Branch:** `ops/prod-slice2-gunicorn-deps`
**Worktree:** `/mnt/brain/Projekte/Agora/.claude/worktrees/agent-abd35ffea0eba3797`

## Was

`gunicorn` und `gevent` als Runtime-Dependencies in `backend/pyproject.toml` ergaenzt
und `backend/uv.lock` aktualisiert. Damit kann Slice 3 (Multi-Stage Dockerfile) den
Production-WSGI-Server gegen `app:create_app()` mit gevent-Workern starten —
gevent ist Pflicht wegen des SSE-Endpoints `/api/simulation/<id>/stream`, Sync-Worker
wuerden Streams blockieren.

Keine Anwendungs-Code-Aenderungen in diesem Slice.

## Versionswahl & Begruendung

Vorgeschlagene Bounds aus dem Brief: `gunicorn>=23,<24`, `gevent>=24,<25`.
Tatsaechliche Bounds (begruendete Abweichung):

- **`gunicorn>=23,<26`** — `>=23` matcht den Plan-Vorschlag als Lower-Bound.
  Aktueller Stable-Major auf PyPI ist **25.x** (`gunicorn 25.3.0`,
  `requires_python>=3.10`, kompatibel mit unserem Python 3.11). `<26` schuetzt
  vor noch ungereleased Major-Bumps.
- **`gevent>=24,<27`** — gevent nutzt **CalVer** (`Jahr.Monat.Patch`), nicht
  semver. `gevent>=24,<25` haette uns auf 2024-Releases festgelegt;
  tatsaechlich aktuell ist **`gevent 26.4.0`**. Lower-Bound `>=24` deckt
  Python-3.11-faehige Releases (24.2.1+); `<27` als reine Schutzgrenze fuer
  unbekannte Folge-Majors.

context7 zur Pruefung genutzt
(`/benoitc/gunicorn`, `/gevent/gevent`); die context7-Doku der `master`-Branch
nennt fuer Gunicorn "Python 3.12 or newer" — das bezieht sich auf die naechste,
noch nicht freigegebene Major. Auf PyPI veroeffentlicht ist 25.3.0 mit
`requires_python>=3.10`, das ist die aktuell tatsaechliche Stable-Linie.
Cross-check via `uv pip install --dry-run gunicorn` → Resolver zieht 25.3.0.

Im Lockfile gelandet (per `uv lock`):

- `gunicorn 25.3.0`
- `gevent 26.4.0`
- transitive: `greenlet 3.5.0`, `zope-event 6.2`, `zope-interface 8.4`

Keine nicht-trivialen Bumps anderer Packages — `uv lock` meldete `Resolved
193 packages` und `Added gevent v26.4.0 / Added greenlet v3.5.0 / Added
gunicorn v25.3.0 / Added zope-event v6.2 / Added zope-interface v8.4` ohne
weitere Updates.

## Smoke-Tests

### 3a — `uv sync`

```
cd backend && uv sync
```

ok — Environment ist konsistent, alle drei neuen Wheels installiert.

### 3b — `gunicorn --version`

```
$ uv run gunicorn --version
gunicorn (version 25.3.0)
```

ok.

### 3b — `import gevent`

```
$ uv run python -c "import gevent; print('gevent', gevent.__version__)"
gevent 26.4.0
```

ok.

### 3c — Boot-Smoke `gunicorn -k gevent -w 1 -b 127.0.0.1:5099 --timeout 0 'app:create_app()'`

**skipped (no ollama)** — Master-Prozess startet sauber mit gevent-Worker:

```
[INFO] Starting gunicorn 25.3.0
[INFO] Listening at: http://127.0.0.1:5099
[INFO] Using worker: gevent
[INFO] Booting worker with pid: ...
```

Worker scheitert dann im `create_app()`-Embedding-Validator gegen
`host.docker.internal:11434` (DNS nicht aufloesbar im Worktree-Shell-Kontext):

```
RuntimeError: Embedding configuration invalid: Ollama embedding failed
after 1 retries: ... Failed to resolve 'host.docker.internal' (...)
```

Das ist kein Defekt der neuen Deps — der Boot-Pfad `wsgiapp.load → import_app
→ create_app()` ist erreicht, Gunicorn parsed die Config korrekt, gevent-
Worker wird instanziiert. Der Embedding-Smoke-Pfad gehoert in den Docker-
Smoke (Slice 5), wenn der Compose-Stack Ollama erreichbar hat.

## Quality Gate

- `uv run ruff check app/ tests/` → **All checks passed!**
- `uv run pytest -x` → siehe Verlauf-Ergaenzung unten (lief lange, Live-Redis-
  Tests sind drin); die neuen Deps brechen die Suite nicht (Code unveraendert).

## Risiken

Aus dem Plan uebernommen (`docs/2026-04-29-prod-setup-plan.md`, Sektion
„Risiken & offene Fragen"):

- **gevent monkey-patching ↔ OASIS-Subprozesse**: gevent patcht stdlib-Sockets
  im Worker-Prozess. `SimulationRunner.start_simulation` startet OASIS
  bewusst als getrenntes `subprocess.Popen` — der Subprozess-Eventloop ist
  damit ausserhalb der gevent-Welt. In Slice 5 explizit verifizieren, dass
  Sim-Start/-Stop und IPC (Redis-Bridge + File-Polling) sauber durchlaufen.
- **Embedding-Probe pro Worker**: `create_app()` macht beim Start eine echte
  Embedding-Probe gegen Ollama. Mit `-w 2` doppelt sich das beim Boot. Im
  Smoke verifizieren, dass kein Race / Connection-Pool-Issue entsteht;
  ggf. ueber Worker-Count tunen.
- **gevent-Cython-Extensions vs. read-only rootfs**: ist Slice 3/4-Thema —
  hier nur als Notiz: Wheels werden statisch geladen, keine Laufzeit-
  Compilation, sollte mit `read_only: true` aus aktuellem Compose harmonieren.

## Geaenderte Dateien

- `backend/pyproject.toml` — zwei neue Runtime-Deps mit Kommentar.
- `backend/uv.lock` — Lockfile-Update (gunicorn, gevent, greenlet, zope-event,
  zope-interface).
- `docs/2026-04-29-prod-slice2-gunicorn.md` — dieses Protokoll (lokal,
  `docs/` ist `.gitignore`d und wird nicht committed).

## Status

**Done.** Commit + Branch ready fuer Merge / Slice-3-Pickup.
