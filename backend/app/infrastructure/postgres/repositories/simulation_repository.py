"""PostgreSQL-Adapter des ``SimulationRepository``-Ports (§11, PR 7).

Der Adapter bedient **nur Metadaten** — den Inhalt von ``state.json``.
``simulation_config.json``, Profile, Logs und IPC-Dateien bleiben im
Simulationsverzeichnis, unabhängig davon, wo die Metadaten liegen.

**Die Aufteilung auf Kernspalten und ``payload`` wird abgeleitet, nicht
gepflegt** — wie bei ``PostgresProjectRepository``. ``_CORE_KEYS`` nennt die
Felder mit eigener Spalte; alles, was ``SimulationRecord.to_dict()`` darüber
hinaus liefert, geht unbesehen ins ``payload``. Ein künftiges Vertragsfeld
landet damit automatisch im JSON, statt beim Schreiben verlorenzugehen.

**``save`` legt an oder aktualisiert.** Der Port kennt keinen eigenen
Anlegepfad: ``SimulationManager.create_simulation`` schreibt den ersten
Datensatz über ``save``, genau wie der Dateiadapter, dessen ``save`` die
``state.json`` neu anlegt. Ein ``save``, das auf eine unbekannte Kennung
scheiterte, legte jede neue Simulation lahm.

**``project_id`` ``''`` ↔ ``NULL``.** Der Vertrag kennt die leere Zeichenkette
als "kein Projekt", die Spalte ist ein Fremdschlüssel und hält dafür ``NULL``.
Beim Lesen wird ``NULL`` wieder zu ``''`` — der Roundtrip bleibt verlustfrei.
Verweist ein Datensatz auf ein Projekt, das es in ``agora.projects`` nicht
gibt, schlägt ``save`` mit ``SimulationProjectMissing`` fehl, statt den
Verweis still zu verwerfen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ....contracts.simulation_record_contract import SimulationRecord
from ....utils.logger import get_logger
from ..models.simulation import SimulationModel
from ..session import Database, get_database

logger = get_logger('agora.simulations.postgres')

#: Felder des Vertrags mit eigener Spalte. Schlüssel = Name in
#: ``SimulationRecord.to_dict()``, Wert = Spaltenname.
_CORE_KEYS: dict[str, str] = {
    'simulation_id': 'id',
    'project_id': 'project_id',
    'graph_id': 'graph_id',
    'status': 'status',
    'source_simulation_id': 'source_simulation_id',
    'root_simulation_id': 'root_simulation_id',
    'created_at': 'created_at',
    'updated_at': 'updated_at',
}


class SimulationProjectMissing(LookupError):
    """Der Datensatz verweist auf ein Projekt, das nicht in ``agora.projects`` steht.

    Tritt auf, wenn Projekte und Simulationen nicht in der Reihenfolge
    "erst Projekte, dann Simulationen" umgestellt wurden, oder bei einer
    Simulation, deren Projekt gelöscht ist.
    """


def _now() -> str:
    """Zeitstempel im Format der Ablage, wie im Dateiadapter."""
    return datetime.now().isoformat()


def _to_row_values(record: SimulationRecord) -> dict[str, Any]:
    """Vertrag → Spalten. Alles ohne eigene Spalte geht ins ``payload``."""
    data = record.to_dict()
    values: dict[str, Any] = {
        column: data[key] for key, column in _CORE_KEYS.items()
    }
    values['project_id'] = values['project_id'] or None
    values['payload'] = {
        key: value for key, value in data.items() if key not in _CORE_KEYS
    }
    return values


def _to_contract(row: SimulationModel) -> SimulationRecord:
    """Spalten → Vertrag. Die Kernspalten überschreiben das ``payload``."""
    data: dict[str, Any] = dict(row.payload or {})
    data.update(
        simulation_id=row.id,
        project_id=row.project_id or '',
        graph_id=row.graph_id,
        status=row.status,
        source_simulation_id=row.source_simulation_id,
        root_simulation_id=row.root_simulation_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return SimulationRecord.from_dict(data)


def _is_project_fk_violation(exc: IntegrityError) -> bool:
    return 'fk_simulations_project_id_projects' in str(exc.orig)


class PostgresSimulationRepository:
    """Simulationsmetadaten in ``agora.simulations``."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self._database = database

    @property
    def db(self) -> Database:
        # Erst beim Zugriff auflösen: ein konstruiertes, aber ungenutztes
        # Repository soll keine Verbindung aufbauen.
        return self._database or get_database()

    # -- Schreiben -----------------------------------------------------------

    def save(self, record: SimulationRecord) -> None:
        record.updated_at = _now()
        values = _to_row_values(record)
        try:
            with self.db.session() as session:
                row = session.get(SimulationModel, record.simulation_id)
                if row is None:
                    session.add(SimulationModel(**values))
                    return
                for column, value in values.items():
                    setattr(row, column, value)
        except IntegrityError as exc:
            if _is_project_fk_violation(exc):
                raise SimulationProjectMissing(
                    f'simulation {record.simulation_id} references project '
                    f'{record.project_id}, which is not in agora.projects'
                ) from exc
            raise

    def add_existing(self, record: SimulationRecord) -> bool:
        """Legt eine Simulation mit **bestehender** Kennung und ihren
        Zeitstempeln an. ``False``, wenn die Kennung schon vorhanden ist.

        Der Weg für die Datenmigration. Nicht ``save``: das stempelt
        ``updated_at`` auf jetzt und überschriebe einen inzwischen in
        PostgreSQL geänderten Datensatz. Idempotent aus demselben Grund wie
        ``PostgresProjectRepository.add_existing``; eine gleichzeitig
        angelegte Kennung (Primärschlüsselverletzung) gilt als "schon da".
        """
        with self.db.session() as session:
            if session.get(SimulationModel, record.simulation_id) is not None:
                return False

        try:
            with self.db.session() as session:
                session.add(SimulationModel(**_to_row_values(record)))
        except IntegrityError as exc:
            if _is_project_fk_violation(exc):
                raise SimulationProjectMissing(
                    f'simulation {record.simulation_id} references project '
                    f'{record.project_id}, which is not in agora.projects'
                ) from exc
            logger.info(
                'Simulation %s was inserted concurrently — treated as existing',
                record.simulation_id,
            )
            return False
        return True

    # -- Lesen ---------------------------------------------------------------

    def get(self, simulation_id: str) -> Optional[SimulationRecord]:
        with self.db.session() as session:
            row = session.get(SimulationModel, simulation_id)
            return None if row is None else _to_contract(row)

    def list(self, project_id: Optional[str] = None) -> List[SimulationRecord]:
        """Alle Simulationen, optional nach Projekt gefiltert.

        Sortiert nach ``created_at``, neueste zuerst — der Port verspricht
        keine Reihenfolge, eine feste ist trotzdem besser als eine zufällige.
        Ein unlesbarer Datensatz lässt die Liste stehen und wird mit seiner
        Kennung protokolliert, wie beim Dateiadapter.
        """
        query = select(SimulationModel).order_by(SimulationModel.created_at.desc())
        if project_id is not None:
            if project_id:
                query = query.where(SimulationModel.project_id == project_id)
            else:
                query = query.where(SimulationModel.project_id.is_(None))
        with self.db.session() as session:
            return self._readable(session.scalars(query).all())

    def list_branches(self, simulation_id: str) -> List[SimulationRecord]:
        """Alle Simulationen mit derselben Wurzel wie ``simulation_id``.

        Wurzel ist ``root_simulation_id`` oder, wenn leer, die eigene
        Kennung — dieselbe Regel wie im Dateiadapter.
        """
        source = self.get(simulation_id)
        if source is None:
            return []
        root_id = source.root_simulation_id or source.simulation_id

        family_root = func.coalesce(
            func.nullif(SimulationModel.root_simulation_id, ''),
            SimulationModel.id,
        )
        query = select(SimulationModel).where(family_root == root_id)
        with self.db.session() as session:
            return self._readable(session.scalars(query).all())

    @staticmethod
    def _readable(rows: Any) -> List[SimulationRecord]:
        records: List[SimulationRecord] = []
        for row in rows:
            try:
                records.append(_to_contract(row))
            except ValueError as exc:
                # ValueError deckt pydantic.ValidationError mit ab.
                logger.warning(
                    'Skipping unreadable simulation row %s: %s',
                    row.id,
                    type(exc).__name__,
                )
        return records
