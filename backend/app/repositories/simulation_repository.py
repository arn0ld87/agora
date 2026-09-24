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

``save`` schreibt den Datensatz und setzt ``updated_at`` auf jetzt. Auf eine
Simulation, die es nicht gibt, schlaegt ``save`` mit einem adapterabhaengigen
Fehler fehl — kein Adapter erfindet einen Datensatz als Nebeneffekt.

Die Fabrik ``get_simulation_repository`` ist die einzige Stelle, an der ein
Consumer an ein Repository kommt. Heute liefert sie ausschliesslich den
Dateiadapter; der PostgreSQL-Adapter folgt in #1585 ohne Konfigurationsschalter
in diesem Commit.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from ..contracts.simulation_record_contract import SimulationRecord


@runtime_checkable
class SimulationRepository(Protocol):
    """Lesen und Schreiben von Simulationsmetadaten, unabhaengig von der Ablage."""

    def save(self, record: SimulationRecord) -> None:
        """Schreibt den Datensatz und setzt ``updated_at`` auf jetzt.

        Das Stempeln gehoert hierher: sonst haengt es davon ab, ob ein
        Aufrufer daran gedacht hat. Auf eine Simulation, die es nicht gibt,
        schlaegt ``save`` mit einem adapterabhaengigen Fehler fehl — kein
        Adapter erfindet einen Datensatz als Nebeneffekt eines Schreibvorgangs.
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

    Heute wird ausschliesslich der Dateiadapter geliefert. Ein Konfigurationsschalter
    kommt nicht — der PostgreSQL-Adapter folgt in #1585.
    """
    from ..services.file_simulation_store import get_file_simulation_repository

    return get_file_simulation_repository(simulations_dir=simulations_dir, store=store)
