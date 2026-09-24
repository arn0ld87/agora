"""Port fuer Simulationsmetadaten (Issue #1578).

Der Port beschreibt ausschliesslich die **Metadaten** einer Simulation —
den Inhalt von ``state.json``. Die Laufzeit-Artefakte (``simulation_config.json``,
Profile, Logs, IPC-Nachrichten) sind keine Metadaten und wandern in keiner
Phase dieses Plans in eine Datenbank.

Die Semantik ist die des heutigen Dateispeichers und wird hier festgeschrieben,
damit ein zweiter Adapter sie nicht anders auslegt:

``get`` gibt ``None`` zurueck, wenn es die Simulation nicht gibt — es wirft
nicht. Ein fehlendes Datensatz ist ein erwarteter Fall, und die Aufrufer
pruefen auf ``None``.

``list`` liefert alle Simulationen, optional gefiltert nach ``project_id``.
Die Reihenfolge ist adapterabhaengig — kein Sortierversprechen hier, weil der
heutige Konsument (``SimulationManager.list_simulations``) selbst nicht
sortiert.

``list_branches`` liefert alle Simulationen mit demselben ``root_simulation_id``
wie die gegebene Simulation (einschliesslich der Simulation selbst, falls sie
Root ist). Sortierung: adapterabhaengig.

``save`` schreibt den Datensatz und setzt ``updated_at`` auf jetzt. Gibt es
die Simulation noch nicht, legt ``save`` sie an: der Port hat keinen eigenen
Anlegepfad, und ``SimulationManager.create_simulation`` schreibt den ersten
Datensatz genau darueber (#1585 hat die fruehere, gegenteilige Formulierung
hier an das tatsaechliche Verhalten beider Adapter angeglichen).

Die Fabrik ``get_simulation_repository`` ist die einzige Stelle, an der ein
Consumer an ein Repository kommt. ``AGORA_SIMULATION_BACKEND`` waehlt zwischen
Dateiadapter (Default ``file``) und PostgreSQL-Adapter (#1585).
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from ..config import SIMULATION_BACKENDS, Config
from ..contracts.simulation_record_contract import SimulationRecord


class SimulationBackendUnavailable(RuntimeError):
    """``AGORA_SIMULATION_BACKEND`` traegt einen Wert, den keine Ablage bedient.

    ``Config.validate()`` lehnt ihn beim Start ab; dieser Fehler faengt den
    Weg ohne Validierung ab (Test, Skript), statt still auf die Datei
    zurueckzufallen.
    """


@runtime_checkable
class SimulationRepository(Protocol):
    """Lesen und Schreiben von Simulationsmetadaten, unabhaengig von der Ablage."""

    def save(self, record: SimulationRecord) -> None:
        """Schreibt den Datensatz und setzt ``updated_at`` auf jetzt.

        Das Stempeln gehoert hierher: sonst haengt es davon ab, ob ein
        Aufrufer daran gedacht hat. Eine noch unbekannte Simulation wird
        angelegt — das ist der Anlegepfad von ``create_simulation``.
        """
        ...

    def get(self, simulation_id: str) -> Optional[SimulationRecord]:
        """Ein Datensatz oder ``None``, wenn es die Simulation nicht gibt."""
        ...

    def list(self, project_id: Optional[str] = None) -> List[SimulationRecord]:
        """Alle Simulationen, optional gefiltert nach Projekt.

        Reihenfolge: adapterabhaengig. Der Konsument
        (``SimulationManager.list_simulations``) macht keine Sortierannahmen.
        """
        ...

    def list_branches(self, simulation_id: str) -> List[SimulationRecord]:
        """Alle Simulationen in derselben Branch-Familie.

        Eine Branch-Familie ist durch ``root_simulation_id`` bestimmt: sie
        umfasst alle Simulationen, deren ``root_simulation_id`` (oder, falls
        dieses Feld leer ist, deren ``simulation_id``) mit dem ``root_simulation_id``
        der gegebenen Simulation uebereinstimmt.

        Reihenfolge: adapterabhaengig.
        """
        ...


def get_simulation_repository(
    simulations_dir: Optional[str] = None,
    store: object = None,
) -> SimulationRepository:
    """Die einzige Stelle, an der ein Consumer an ein Simulations-Repository kommt.

    Der Import des Adapters steht bewusst in der Funktion: ein Modul, das nur
    den Port braucht, soll die Ablage nicht mitladen.

    ``simulations_dir`` ist der Ort einer dateibasierten Ablage. Er wird
    direkt an den Adapter weitergegeben.

    ``store`` ist ein optionaler ``SimulationArtifactStore``. Wird er nicht
    angegeben, baut sich der Adapter selbst einen.

    ``AGORA_SIMULATION_BACKEND=postgres`` liefert den PostgreSQL-Adapter;
    ``simulations_dir`` und ``store`` bleiben dann unbenutzt; die Laufzeit-Artefakte
    daneben verwaltet ``SimulationManager`` selbst.
    """
    backend = Config.SIMULATION_BACKEND
    if backend not in SIMULATION_BACKENDS:
        raise SimulationBackendUnavailable(
            f"AGORA_SIMULATION_BACKEND has unknown value '{backend}' "
            f'(expected one of: {", ".join(sorted(SIMULATION_BACKENDS))})'
        )
    if backend == 'postgres':
        from ..infrastructure.postgres.repositories import (
            PostgresSimulationRepository,
        )

        return PostgresSimulationRepository()

    from ..services.file_simulation_store import get_file_simulation_repository

    return get_file_simulation_repository(simulations_dir=simulations_dir, store=store)
