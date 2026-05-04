# Arbeitsprotokoll — Task 45 / Issue #201: `_sim_common.py` extrahieren

**Datum:** 2026-05-04  
**Issue:** #201  
**Milestone:** v1.0.0 — Stable Release

## Ausgangslage

Gemessene LOC vor dem Slice:

```text
1954  backend/scripts/run_parallel_simulation.py
 943  backend/scripts/run_twitter_simulation.py
 933  backend/scripts/run_reddit_simulation.py
3830  total
```

Auffällige Duplikate in allen drei Runnern:
- Pfadberechnung (`_scripts_dir`, `_backend_dir`, `_project_root`)
- `.env`-Ladelogik
- `MaxTokensWarningFilter`
- OASIS-Log-Setup
- CLI-Parser für `--config`, `--max-rounds`, `--no-wait`

## Umsetzung

Neu extrahiert nach `backend/scripts/_sim_common.py`:
- `RuntimePaths`
- `resolve_runtime_paths()`
- `install_script_paths()`
- `load_project_env()`
- `should_filter_max_tokens_warning()`
- `MaxTokensWarningFilter`
- `install_max_tokens_warning_filter()`
- `UnicodeFormatter`
- `setup_oasis_logging()`
- `build_single_platform_parser()`
- `build_parallel_parser()`

Integriert in:
- `backend/scripts/run_twitter_simulation.py`
- `backend/scripts/run_reddit_simulation.py`
- `backend/scripts/run_parallel_simulation.py`

Zusätzlicher kleiner Härtungsschritt:
- `--help` wird jetzt in allen drei Runnern **vor** den schweren OASIS/CAMEL-Imports beantwortet, damit CLI-Smoke und Tooling nicht an Laufzeit-Dependencies hängen.
- `_sim_common` wird package-safe importiert (`from ._sim_common ...` mit Fallback für direkte Script-Ausführung).

## Testabdeckung

Neu: `backend/tests/scripts/test_sim_runner_help.py`

Abgedeckt:
- Pfadauflösung
- gemeinsamer Single-Platform-Parser
- Parallel-Parser inkl. Plattform-Switches
- Warning-Filter-Prädikat
- echte Subprocess-Smoke-Tests für
  - `run_twitter_simulation.py --help`
  - `run_reddit_simulation.py --help`
  - `run_parallel_simulation.py --help`

## Verifikation

Ausgeführt:

```bash
cd backend && uv run pytest tests/scripts/test_sim_runner_help.py -v
cd backend && uv run python -m compileall scripts/_sim_common.py scripts/run_twitter_simulation.py scripts/run_reddit_simulation.py scripts/run_parallel_simulation.py
python backend/scripts/run_twitter_simulation.py --help
python backend/scripts/run_reddit_simulation.py --help
python backend/scripts/run_parallel_simulation.py --help
```

Ergebnis:
- `pytest`: **8 passed**
- `compileall`: erfolgreich
- alle drei `--help`-Kommandos: Exit `0`

## LOC nach dem Slice

```text
 151  backend/scripts/_sim_common.py
1921  backend/scripts/run_parallel_simulation.py
 871  backend/scripts/run_twitter_simulation.py
 861  backend/scripts/run_reddit_simulation.py
3804  total
```

## Bewertung gegen Issue #201

Erfüllt:
- gemeinsamer Hilfsmodul-Schnitt vorhanden
- drei Runner kleiner als vorher
- CLI-Smoke vorhanden und grün
- keine offensichtliche Verhaltensänderung im Simulationspfad beabsichtigt
- Arbeitsprotokoll vorhanden

Offen / bewusst nicht in diesem Slice:
- keine aggressive Extraktion plattformspezifischer Simulationslogik
- `run_parallel_simulation.py` bleibt klar >1500 LOC und ist eher Kandidat für weiterführenden Schnitt als für diesen ersten DRY-Schritt
