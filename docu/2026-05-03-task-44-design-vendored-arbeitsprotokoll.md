# Arbeitsprotokoll — Task 44: design/ als linguist-vendored markieren

**Datum:** 2026-05-03
**Branch:** `feat/task-44-design-vendored`
**Scope:** LOC-Hygiene, kein Code-Verhalten

## Anlass

LOC-Audit (siehe Session 2026-05-03) zeigte ~4 400 JSX-LOC unter
`design/Agora/` und `design/Agora/export/src/` (1:1-Duplikat). Das sind
statische Design-Mockups (HTML + JSX-Sketches + CSS-Token-Studien),
keine produktiven Frontend-Quellen.

Verifikation:

```bash
grep -rn "from design\|import.*design/" backend/ frontend/src/   # leer
grep -rn "design/" docker-compose*.yml Dockerfile*               # leer
```

Niemand importiert daraus, weder Backend noch Frontend, weder Compose
noch Dockerfile. Reine Studio-Artefakte.

## Änderung

Neue Datei `.gitattributes`:

```
design/**  linguist-vendored=true
schemas/** linguist-generated=true
```

## Auswirkung

- GitHub-Linguist zählt `design/` nicht mehr als Hauptsprache → Sprach-Bar
  im Repo wird ehrlich.
- LOC-Audits mit `cloc`/`tokei` können `--vcs=git` + `.gitattributes`
  nutzen, um Vendor-Code automatisch auszuschließen.
- `schemas/` (auto-generiert via `app.contracts.dump_schemas`) wird
  zusätzlich als generated markiert — aus dem gleichen Grund.

## Nicht-Auswirkung

- Keine Datei gelöscht oder verschoben.
- Build, Tests, Runtime unverändert.
- `git ls-files design/` liefert weiterhin alle Dateien.

## Verifikation

```bash
git diff --stat HEAD       # nur .gitattributes + dieses Protokoll
cd backend && uv run pytest -x -q  # erwartet: grün (Touch-frei)
cd frontend && npm test -- --run    # erwartet: grün (Touch-frei)
```

## Folge-Slices

- **Task 45 (offen):** `scripts/_sim_common.py` extrahieren — drei
  Sim-Runner (`run_parallel_simulation.py`, `run_twitter_simulation.py`,
  `run_reddit_simulation.py`, zusammen ~3 800 LOC) teilen Argparse +
  Setup + Subprocess-Bridge.
- **Task 46 (offen):** `services/report_agent.py` (2 400 LOC) in
  `report_agent/`-Paket aufsplitten. Kandidat für Opus +
  `agora-refactor-worker`.
