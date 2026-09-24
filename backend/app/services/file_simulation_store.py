"""Dateibasierter Adapter fuer Simulationsmetadaten (Issue #1578).

Das ist die bisherige Logik aus ``SimulationManager._save_simulation_state``
und ``_load_simulation_state``, hinter den Port gelegt — eine Umstrukturierung,
keine Neuimplementierung. Das Format von ``state.json`` bleibt unveraendert,
damit eine bestehende Installation nach diesem Umbau dieselben Dateien liest
und schreibt wie davor.

Der Adapter nutzt ``SimulationArtifactStore`` fuer den eigentlichen I/O;
er ergaenzt nur die Metadaten-Semantik (Typisierung, Sortierung, Branch-Filterung).

**Warum ``simulations_dir`` hereingereicht wird:**
``SimulationManager.SIMULATION_DATA_DIR`` ist ein Klassenattribut, das in Tests
auf ein temporaeres Verzeichnis umgebogen wird. Wuerde der Adapter den Pfad
selbst aus der Konfiguration ableiten, liefe er an diesen Patches vorbei.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, List, Optional

from ..contracts.simulation_record_contract import SimulationRecord
from ..services.artifact_store import (
    LocalFilesystemArtifactStore,
    SimulationArtifactStore,
    resolve_default_store,
)
from ..utils.logger import get_logger

logger = get_logger('agora.simulation.file_store')


class FileSimulationRepository:
    """Simulationsmetadaten als ``state.json`` je Simulationsverzeichnis.

    Alle Schreib- und Lesevorgaenge laufen ueber ``SimulationArtifactStore``.
    Der Adapter selbst kennt kein ``open()``.

    ``_known_ids`` verfolgt alle Simulationskennungen, die ueber ``save``
    geschrieben wurden. Das ist notwendig, damit ``list`` auch dann
    funktioniert, wenn kein ``simulations_dir`` gesetzt ist (z. B. bei
    ``InMemoryArtifactStore`` in Tests): der Store hat keine Methode, alle
    Simulationskennungen aufzuzaehlen.
    """

    def __init__(
        self,
        simulations_dir: Optional[str],
        store: Optional[SimulationArtifactStore] = None,
    ) -> None:
        self._simulations_dir = simulations_dir
        if store is not None:
            self._store = store
        elif simulations_dir is not None:
            self._store = LocalFilesystemArtifactStore(simulations_dir)
        else:
            self._store = resolve_default_store()

        # Verfolgt gespeicherte Kennungen fuer Store-basiertes Listing
        # (keine Dateisystem-Enumeration moeglich ohne simulations_dir)
        self._known_ids: set[str] = set()

    # --- Port -----------------------------------------------------------------

    def save(self, record: SimulationRecord) -> None:
        """Schreibt ``state.json`` und setzt ``updated_at`` auf jetzt.

        Analog zu ``FileProjectRepository.save``: das Stempeln gehoert hierher,
        nicht zum Aufrufer.
        """
        record.updated_at = datetime.now().isoformat()
        self._store.write_json(record.simulation_id, 'state', record.to_dict())
        self._known_ids.add(record.simulation_id)

    def get(self, simulation_id: str) -> Optional[SimulationRecord]:
        """Einen Datensatz oder ``None``, wenn es die Simulation nicht gibt."""
        if not self._store.exists(simulation_id, 'state'):
            return None

        data: Any = self._store.read_json(simulation_id, 'state', default=None)
        if not data:
            return None

        # Die Kennung ist der Verzeichnisname. Der fruehere Ladepfad nahm sie
        # von dort, nicht aus der Datei — ein Altbestand ohne das Feld bleibt
        # damit lesbar.
        return SimulationRecord.from_dict({**data, 'simulation_id': simulation_id})

    def _candidate_ids(self) -> List[str]:
        """Liefert alle Simulationskennungen fuer ``list``.

        Wenn ``simulations_dir`` gesetzt ist, werden Verzeichniseintraege
        aufgezaehlt (Produktionspfad). Andernfalls werden die intern
        gemerkten Kennungen verwendet (In-Memory- oder Store-basierter
        Betrieb ohne Dateisystem).
        """
        if self._simulations_dir is not None and os.path.exists(self._simulations_dir):
            return [
                entry
                for entry in os.listdir(self._simulations_dir)
                if not entry.startswith('.')
                and os.path.isdir(os.path.join(self._simulations_dir, entry))
            ]
        return list(self._known_ids)

    def list(self, project_id: Optional[str] = None) -> List[SimulationRecord]:
        """Alle Simulationen, optional gefiltert nach Projekt.

        Verzeichnisse ohne ``state.json`` werden uebersprungen. Ein unlesbarer
        Datensatz laesst die Liste stehen (Warnung statt Abbruch) — dieselbe
        Entscheidung wie in ``FileProjectRepository.list``.
        """
        result: list[SimulationRecord] = []

        for sim_id in self._candidate_ids():
            try:
                record = self.get(sim_id)
            except (ValueError, OSError) as exc:
                logger.warning(
                    'Skipping unreadable simulation record %s: %s',
                    sim_id,
                    type(exc).__name__,
                )
                continue

            if record is None:
                continue

            if project_id is not None and record.project_id != project_id:
                continue

            result.append(record)

        return result

    def list_branches(self, simulation_id: str) -> List[SimulationRecord]:
        """Alle Simulationen in derselben Branch-Familie.

        Die Familie ist durch ``root_simulation_id`` bestimmt: alle Datensaetze,
        deren ``root_simulation_id`` (oder, falls dieses Feld leer ist, deren
        ``simulation_id``) mit der Root der gegebenen Simulation uebereinstimmt.
        """
        source = self.get(simulation_id)
        if source is None:
            return []

        root_id = source.root_simulation_id or source.simulation_id

        all_records = self.list()
        return [
            record
            for record in all_records
            if (record.root_simulation_id or record.simulation_id) == root_id
        ]


def get_file_simulation_repository(
    simulations_dir: Optional[str] = None,
    store: object = None,
) -> FileSimulationRepository:
    """Baut den Dateiadapter.

    ``simulations_dir`` gibt den Ablageort vor. Ohne Angabe wird ``None``
    weitergegeben, und der Adapter baut sich selbst einen Store ueber
    ``resolve_default_store()``.

    ``store`` ist ein optionaler ``SimulationArtifactStore``; er wird bei
    Tests injiziert, um in-memory zu arbeiten.
    """
    artifact_store: Optional[SimulationArtifactStore] = (
        store if isinstance(store, SimulationArtifactStore) else None  # type: ignore[arg-type]
    )
    return FileSimulationRepository(
        simulations_dir=simulations_dir,
        store=artifact_store,
    )
