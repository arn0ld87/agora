"""PostgreSQL-Adapter des ``ReportRepository``-Ports (§11, PR 9).

Der Adapter bedient **nur Metadaten** — den Inhalt von ``meta.json``.
``report-v3.json``, Outline, Sections, Evidence-Map und Logs bleiben unter
``uploads/reports/<Ablageschlüssel>/``, unabhängig davon, wo die Metadaten
liegen (Plan §11 Klasse B).

**Ablageschlüssel und ``report_id``.** Der Port adressiert Reports über den
Ablageschlüssel (``list_ids``/``get``), den Ordnernamen der Inhalte. Der
Primärschlüssel der Tabelle ist genau dieser Schlüssel. ``save`` schreibt
unter ``record.report_id`` — wie der Dateiadapter, der ``meta.json`` unter
``reports/<report_id>/`` ablegt. Nur die Datenmigration legt Zeilen unter
einem abweichenden Schlüssel an (``add_existing``), damit ein Altbestand
seine Inhalte weiter findet.

**``payload`` ist der Datensatz, die Spalten sind abgeleitet** — dieselbe
Aufteilung wie bei ``agora.runs``. ``get`` baut den Vertrag allein aus dem
``payload``; ein ``ON DELETE SET NULL`` auf ``simulation_id`` ändert den
gelesenen Datensatz deshalb nicht. Aus demselben Grund filtert ``list`` auf
``payload->>'simulation_id'`` und nicht auf die Spalte: dieselbe Antwort wie
der Dateiadapter, auch für einen Report, dessen Simulation gelöscht ist.

**``save`` legt an oder aktualisiert** (``INSERT … ON CONFLICT DO UPDATE``) und
stempelt nichts. Nennt ein **neuer** Report eine Simulation, die es in
``agora.simulations`` nicht gibt, scheitert ``save`` mit
``ReportSimulationMissing``. Ein **bestehender** Report, dessen Simulation
inzwischen fehlt, schreibt weiter — die Report-Erzeugung hält das
``Report``-Objekt über den ganzen Lauf im Speicher (dieselbe Lehre wie beim
Projektverweis der Simulationen, Codex-Review auf #1598).
"""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from ....contracts.report_record_contract import ReportRecord
from ....utils.logger import get_logger
from ..models.report import ReportModel
from ..models.simulation import SimulationModel
from ..session import Database, get_database

logger = get_logger('agora.reports.postgres')


class ReportSimulationMissing(LookupError):
    """Ein neuer Report verweist auf eine Simulation, die nicht in
    ``agora.simulations`` steht.

    Tritt auf, wenn Simulationen und Reports nicht in der Reihenfolge "erst
    Simulationen, dann Reports" umgestellt wurden, oder bei einem Altbestand,
    dessen Simulation nicht migriert werden konnte.
    """


def _text_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _to_row_values(key: str, record: ReportRecord) -> dict[str, Any]:
    """Vertrag → Zeile. Der Datensatz geht vollständig ins ``payload``."""
    data = record.to_dict()
    return {
        'id': key,
        'report_id': record.report_id,
        'simulation_id': _text_or_none(record.simulation_id),
        'status': record.status,
        'created_at': _text_or_none(record.created_at),
        'completed_at': _text_or_none(record.completed_at),
        'payload': data,
    }


def _is_simulation_fk_violation(exc: IntegrityError) -> bool:
    return 'fk_reports_simulation_id_simulations' in str(exc.orig)


def _missing(key: str, simulation_id: Any) -> ReportSimulationMissing:
    return ReportSimulationMissing(
        f'report {key} references simulation {simulation_id}, '
        'which is not in agora.simulations'
    )


class PostgresReportRepository:
    """Report-Metadaten in ``agora.reports``."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self._database = database

    @property
    def db(self) -> Database:
        # Erst beim Zugriff auflösen: ein konstruiertes, aber ungenutztes
        # Repository soll keine Verbindung aufbauen.
        return self._database or get_database()

    # -- Schreiben -----------------------------------------------------------

    def save(self, record: ReportRecord) -> ReportRecord:
        values = _to_row_values(record.report_id, record)
        try:
            with self.db.session() as session:
                self._resolve_simulation(session, values)
                statement = insert(ReportModel).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=[ReportModel.id],
                    set_={
                        column: statement.excluded[column]
                        for column in values
                        if column != 'id'
                    },
                )
                session.execute(statement)
        except IntegrityError as exc:
            if _is_simulation_fk_violation(exc):
                # Die Simulation verschwand zwischen Prüfung und Schreiben.
                raise _missing(values['id'], values['simulation_id']) from exc
            raise
        return record

    def add_existing(self, key: str, record: ReportRecord) -> bool:
        """Legt einen Report unter seinem **bestehenden** Ablageschlüssel an.
        ``False``, wenn der Schlüssel schon vorhanden ist.

        Der Weg für die Datenmigration: ein vorhandener Datensatz wird nicht
        überschrieben, damit ein zweiter Lauf nach dem Umschalten keine
        inzwischen in PostgreSQL geänderten Reports zurückdreht. Ein fehlender
        Simulationsverweis scheitert mit ``ReportSimulationMissing`` — aber
        erst nach der Prüfung auf eine vorhandene Zeile, damit eine
        Wiederholung nach dem Löschen der Simulation "schon da" meldet
        (dieselbe Lehre wie beim Run-Adapter, Codex-Review auf #1605).
        """
        values = _to_row_values(key, record)
        try:
            with self.db.session() as session:
                if session.get(ReportModel, key) is not None:
                    return False
                if (
                    values['simulation_id'] is not None
                    and session.get(SimulationModel, values['simulation_id']) is None
                ):
                    raise _missing(key, values['simulation_id'])
                statement = (
                    insert(ReportModel)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=[ReportModel.id])
                    .returning(ReportModel.id)
                )
                inserted = session.execute(statement).scalar_one_or_none()
        except IntegrityError as exc:
            if _is_simulation_fk_violation(exc):
                raise _missing(key, values['simulation_id']) from exc
            raise
        return inserted is not None

    def delete(self, report_id: str) -> bool:
        """Entfernt nur die Zeile. Die Inhalte räumt ``ReportManager`` ab."""
        with self.db.session() as session:
            result = session.execute(
                delete(ReportModel)
                .where(ReportModel.id == report_id)
                .returning(ReportModel.id)
            )
            return result.scalar_one_or_none() is not None

    def _resolve_simulation(self, session: Any, values: dict[str, Any]) -> None:
        """Prüft den Simulationsverweis vor dem Schreiben.

        Fehlt die Simulation, entscheidet, ob der Report schon existiert: ein
        neuer Report scheitert, ein bestehender behält seine Zeile mit
        ``simulation_id = NULL``; der Verweis im Datensatz bleibt erhalten.
        """
        wanted = values['simulation_id']
        if wanted is None or session.get(SimulationModel, wanted) is not None:
            return
        if session.get(ReportModel, values['id']) is None:
            raise _missing(values['id'], wanted)
        logger.info(
            'Report %s keeps its detached simulation reference '
            '(simulation %s is not in agora.simulations)',
            values['id'],
            wanted,
        )
        values['simulation_id'] = None

    # -- Lesen ---------------------------------------------------------------

    def get(self, report_id: str) -> Optional[ReportRecord]:
        """Datensatz unter dem Ablageschlüssel oder ``None``. Ein unlesbarer
        Datensatz zählt als fehlend — dieselbe Semantik wie beim Dateiadapter."""
        with self.db.session() as session:
            row = session.get(ReportModel, report_id)
            return None if row is None else self._readable(row)

    def list_ids(self) -> List[str]:
        """Ablageschlüssel aller Reports, nach Schlüssel sortiert."""
        with self.db.session() as session:
            return list(
                session.scalars(select(ReportModel.id).order_by(ReportModel.id)).all()
            )

    def list(self, simulation_id: Optional[str] = None) -> List[ReportRecord]:
        """Alle lesbaren Reports, optional nach Simulation gefiltert.

        Gefiltert wird auf den Datensatz (``payload``), nicht auf die
        Fremdschlüsselspalte — siehe Modul-Docstring. Reihenfolge: nach
        Schlüssel; der Port verspricht keine, ``ReportManager`` sortiert selbst.
        """
        query = select(ReportModel).order_by(ReportModel.id)
        if simulation_id is not None:
            query = query.where(
                ReportModel.payload['simulation_id'].astext == simulation_id
            )
        records: List[ReportRecord] = []
        with self.db.session() as session:
            for row in session.scalars(query):
                record = self._readable(row)
                if record is not None:
                    records.append(record)
        return records

    @staticmethod
    def _readable(row: ReportModel) -> Optional[ReportRecord]:
        try:
            if not isinstance(row.payload, dict):
                # Die Spalte erzwingt kein JSON-Objekt (Codex-Review auf #1605).
                raise ValueError(f'payload of report {row.id} is not a JSON object')
            return ReportRecord.from_dict(row.payload)
        except (KeyError, TypeError, ValueError) as exc:
            # ValueError deckt pydantic.ValidationError mit ab.
            logger.warning(
                'Skipping unreadable report row %s: %s', row.id, type(exc).__name__
            )
            return None
