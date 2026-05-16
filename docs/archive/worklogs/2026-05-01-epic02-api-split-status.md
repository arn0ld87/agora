# EPIC-02 Status — API-Splitting bereits abgeschlossen

**Datum:** 2026-05-01
**Sprint:** v0.8.0 — Frontend Consolidation
**Issues:** #29 (Spike), #30, #31, #32, #33

## Zweck dieses Dokuments

EPIC-02 (Backend-API-Splitting) wurde im Backlog für v0.8.0 als offen geführt. Die Inventur zeigt: der Split ist seit **v0.4.0** vollständig umgesetzt. Dieses Dokument hält den IST-Zustand fest, sodass die fünf Backlog-Issues mit Verweis auf eine belastbare Quelle geschlossen werden können.

Quelle des Splits: [`CHANGELOG.md`](../CHANGELOG.md) Eintrag zu v0.4.0 — *„`backend/app/api/simulation.py` in fokussierte Module zerlegt (`simulation_lifecycle`, `simulation_prepare`, `simulation_profiles`, `simulation_run`, `simulation_interviews`, `simulation_history`)"*.

## Status der monolithischen Vorlage

[`backend/app/api/simulation.py`](../backend/app/api/simulation.py) ist auf **17 Zeilen** geschrumpft und reiner Compatibility-Shim. Der Modul-Docstring nennt die acht Zielmodule explizit. Es existieren keine Routen mehr in dieser Datei.

## Routen-Inventar (Stand v0.7.0)

Alle 48 Routen unter `simulation_bp` sind thematisch verteilt:

| Ziel-Modul | Routen | Zeilen | Bereich |
|---|---:|---:|---|
| [`simulation_lifecycle.py`](../backend/app/api/simulation_lifecycle.py) | 4 | 166 | `available-models`, `create`, `<simulation_id>`, `list` |
| [`simulation_prepare.py`](../backend/app/api/simulation_prepare.py) | 2 | 453 | `prepare`, `prepare/status` |
| [`simulation_run.py`](../backend/app/api/simulation_run.py) | 12 | 567 | `start`, `stop`, `<id>/pause`, `<id>/resume`, `<id>/console-log`, `<id>/run-status`, `<id>/run-status/detail`, `<id>/actions`, `<id>/timeline`, `<id>/agent-stats`, `env-status`, `close-env` |
| [`simulation_profiles.py`](../backend/app/api/simulation_profiles.py) | 16 | 596 | Branch (2), Profiles (5), Persona-Library (3), Profil-Quality/Approval (5), Config (3), Script-Download (1) |
| [`simulation_interviews.py`](../backend/app/api/simulation_interviews.py) | 4 | 230 | `interview`, `interview/batch`, `interview/all`, `interview/history` |
| [`simulation_history.py`](../backend/app/api/simulation_history.py) | 4 | 272 | `history`, `generate-profiles`, `<id>/posts`, `<id>/comments` |
| [`simulation_entities.py`](../backend/app/api/simulation_entities.py) | 3 | 91 | `entities/<gid>`, `entities/<gid>/<uuid>`, `entities/<gid>/by-type/<type>` |
| [`simulation_stream.py`](../backend/app/api/simulation_stream.py) | 1 | 154 | `<id>/stream` (SSE) |
| [`simulation_metrics.py`](../backend/app/api/simulation_metrics.py) | 2 | 181 | `<id>/metrics`, `<id>/metrics/export` |
| **Σ** | **48** | **2.710** | — |

Plus weitere Blueprints außerhalb von `simulation_bp`:

| Modul | Blueprint | Routen |
|---|---|---:|
| [`graph.py`](../backend/app/api/graph.py) | `graph_bp` | 12 |
| [`report.py`](../backend/app/api/report.py) | `report_bp` | 21 |
| [`runs.py`](../backend/app/api/runs.py) | `runs_bp` | 5 |
| [`status.py`](../backend/app/api/status.py) | `status_bp` | 1 |
| [`auth.py`](../backend/app/api/auth.py) | `auth_bp` | 1 |

## Gemeinsame Helfer

[`simulation_common.py`](../backend/app/api/simulation_common.py) (70 Zeilen) enthält:

- `logger` — `get_logger('agora.api.simulation')`
- `run_registry` — singleton `RunRegistry`
- `INTERVIEW_PROMPT_PREFIX` plus `optimize_interview_prompt()`
- `get_simulation_storage()` — Neo4j-Storage aus Flask-App-Context
- `get_artifact_store()` — `SimulationArtifactStore` aus DI-Container
- `simulation_run_artifacts(simulation_id)` — `ArtifactLocator`-Wrapper
- `simulation_resume_capability(simulation_id, state)` — Resume-Aktions-Logik

## Blueprint-Registrierung

[`backend/app/api/__init__.py`](../backend/app/api/__init__.py) erzeugt fünf Blueprints (`graph_bp`, `simulation_bp`, `report_bp`, `runs_bp`, `status_bp`) plus `auth_bp` (importiert) und lädt die zehn simulation-Module per `from . import simulation_*`. Die Reihenfolge ist seit v0.4.0 stabil.

## Mapping zu den Backlog-Issues

| Issue | Akzeptanzkriterium | Status |
|---|---|---|
| **#29** API-Splitting-Plan definieren | Routen-Inventar, Zielmodule, gemeinsame Helfer | ✅ retrospektiv durch dieses Dokument erfüllt |
| **#30** Lifecycle-Routen extrahieren | `simulation_lifecycle.py` existiert | ✅ erledigt in v0.4.0 |
| **#31** Prepare-Routen extrahieren | `simulation_prepare.py` existiert | ✅ erledigt in v0.4.0 |
| **#32** Run-Control-Routen extrahieren | `simulation_run.py` existiert | ✅ erledigt in v0.4.0 |
| **#33** Profiles/Interviews/Artifacts/Branches extrahieren | `simulation_profiles.py`, `simulation_interviews.py`, `simulation_history.py`, `simulation_entities.py` existieren | ✅ erledigt in v0.4.0 |

## Konsequenzen für v0.8.0

Der Milestone „v0.8.0 — Frontend Consolidation" reduziert sich von 13 auf **8 echte Issues**:

- **EPIC-04** (3): #34 GraphPanel zerlegen, #35 D3-Composable, #36 Graph-DTO
- **EPIC-05** (4): #37 usePolling, #38 useTaskPolling, #39 useIncrementalLogPolling, #40 SSE/WebSocket-Spike
- **EPIC-10** (1): #84 Frontend-Composable-Tests

## Folge-Aktionen

- Issues #29, #30, #31, #32, #33 schließen mit Verweis auf dieses Dokument plus CHANGELOG-Eintrag v0.4.0.
- Nächster Sub-Slice: **#34 EPIC-04-ST-01 — GraphPanel zerlegen**.
