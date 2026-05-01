# Slice A1 — `SimulationArtifactStore` deckt Issue #41 retrospektiv ab (Closes #41)

**Datum:** 2026-05-01
**Sprint:** v0.9.0 — Domain Cleanup
**Issue:** #41 (EPIC-06-ST-01) — SimulationRepository einführen

## Befund

Issue #41 fordert ein Repository, das `state.json`-Zugriffe kapselt und JSON-I/O zentralisiert. Genau das wurde bereits unter Issue #13 als hexagonal port implementiert: `backend/app/services/artifact_store.py` (271 LOC, Protocol + zwei Adapter). `SimulationManager` und `SimulationRunner` konsumieren den Store seit derselben Iteration durchgängig.

## Akzeptanzkriterien-Abgleich

| Kriterium | Status | Beleg |
|---|---|---|
| `SimulationManager` liest/schreibt JSON nicht mehr direkt überall selbst | ✓ erfüllt | `simulation_manager.py:150` (`__init__(store)`), 7+ `self._store.read_json/write_json`-Aufrufstellen |
| `state.json`-Zugriffe gekapselt | ✓ erfüllt | logischer Name `"state"` in `_ARTIFACT_FILENAMES` (`artifact_store.py:36`); Manager und Runner verwenden ausschließlich diese Abstraktion |
| Repository für Laden/Speichern anlegen | ✓ erfüllt | `SimulationArtifactStore` Protocol (`artifact_store.py:90`) + `LocalFilesystemArtifactStore` (Zeile 129) + `InMemoryArtifactStore` (Zeile 204) |
| Manager auf Repository umstellen | ✓ erfüllt | DI per Konstruktor mit Default-Fallback `resolve_default_store()`; ebenso `SimulationRunner` (`simulation_runner.py:23,310,1362-1366`) |
| File-Pfade zentralisieren | ✓ erfüllt | `backend/app/utils/artifact_locator.py` (81 LOC) + `_ARTIFACT_FILENAMES`-Dict |

## Konsumtions-Belege

**Manager** (`backend/app/services/simulation_manager.py`):
- Z. 150: `def __init__(self, store: Optional[SimulationArtifactStore] = None)`
- Z. 175: `self._store.write_json(state.simulation_id, "state", state.to_dict())`
- Z. 191: `self._store.read_json(simulation_id, "state", default=None)`
- Z. 479, 542, 591, 635: `simulation_config`-Read/Write
- Z. 710, 721, 765: `reddit_profiles`-Read/Write

**Runner** (`backend/app/services/simulation_runner.py`):
- Z. 23: `from .artifact_store import resolve_default_store`
- Z. 310: `store.read_json(simulation_id, "run_state", default=None)`
- Z. 449: `store.read_json(simulation_id, "simulation_config", default=None)`
- Z. 1362-1366: Stop-Pfad — `state` lesen → `status="stopped"` setzen → schreiben, alles über Store
- Z. 1522: `env_status`-Read; Z. 1689: `simulation_config`-Read

**Pfad-Zentralisierung** (`backend/app/utils/artifact_locator.py`):
- `simulation_file(simulation_id, filename)` als zentrale Pfad-Funktion
- `_ARTIFACT_FILENAMES`-Dict in `artifact_store.py:35` mappt logische Namen auf Dateinamen

## Restzugriffe ohne Store (out-of-scope für #41)

Diese verbleibenden direkten `open()`-Calls im Manager betreffen *nicht* den Simulation-State:

| Datei:Zeile | Zweck | Domain | Folge-Issue |
|---|---|---|---|
| `simulation_manager.py:663-664` | `open(meta_path, "r")` für `report_meta` | Reports | #46 (EPIC-07-ST-02) |
| `simulation_manager.py:726/744` | `open(twitter_path, ...)` für CSV-Personas | Twitter-Export (kein JSON-State) | — (legitimer Export, kein Refactor-Bedarf) |

## Konsequenz für v0.9.0

Issue #41 wird mit dieser Status-Doku geschlossen. Verbleibender v0.9.0-Backlog: **11 echte Issues** (EPIC-06 ×3, EPIC-07 ×5, EPIC-08 ×3).

## Folge-Slice

Slice A2 (Issue #44) — Branching-Logik aus `simulation_manager.py:544-747` in `services/branching_service.py` extrahieren.
