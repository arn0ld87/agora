"""PostgreSQL-Adapter des ``RunRepository``-Ports (§11, PR 8).

Der Adapter bedient die **Run-Manifeste** — den Inhalt von
``uploads/run_registry/<run_id>.json``. Singleton, Lock, Cache,
``canonical_status``, Events und Filter bleiben in ``RunRegistry``; der Port
ist nur die Ablage.

**``payload`` ist das Manifest, die Spalten sind abgeleitet.** Gespeichert
wird ``RunRecord.to_manifest()`` unverändert; ``get`` baut den Vertrag
ausschliesslich daraus. Die Spalten (Typ, Status, Zeitstempel,
``simulation_id``) werden bei jedem Schreiben aus demselben Manifest gezogen
und dienen Sortierung, Filter und Fremdschlüssel. Warum nicht der Schnitt
"Kernspalten + Rest" wie bei Projekten und Simulationen, steht im
Modell-Docstring: der Vertrag unterscheidet "fehlt" von "``null``".

**``save`` legt an oder aktualisiert** und stempelt nichts — wie der
Dateiadapter. ``updated_at`` setzt ``RunRegistry`` selbst, bevor es schreibt.
Das Schreiben ist ein einzelnes ``INSERT … ON CONFLICT DO UPDATE``: zwei
Prozesse, die denselben Run gleichzeitig zum ersten Mal schreiben, enden mit
einer Zeile statt mit einer Primärschlüsselverletzung.

**``simulation_id`` kommt aus ``linked_ids.simulation_id``.** Nennt ein
**neuer** Run eine Simulation, die es in ``agora.simulations`` nicht gibt,
scheitert ``save`` mit ``RunSimulationMissing``, statt den Verweis still zu
verwerfen. Ein **bestehender** Run, dessen Simulation inzwischen fehlt,
schreibt weiter — ``RunRegistry`` hält das Manifest im Cache, und ein
Statuswechsel nach dem Löschen der Simulation darf nicht scheitern (dieselbe
Lehre wie beim Projektverweis der Simulationen, Codex-Review auf #1598). Die
Spalte bleibt dann ``NULL``; der Verweis im Manifest bleibt erhalten.
"""

from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from ....contracts.run_record_contract import RunRecord
from ....utils.logger import get_logger
from ..models.run import RunModel
from ..models.simulation import SimulationModel
from ..session import Database, get_database
from ..workspace_scope import active_workspace_id, scoped, visible, workspace_for_write

logger = get_logger('agora.runs.postgres')

#: Manifest-Felder mit eigener Spalte. Schlüssel = Name im Manifest,
#: Wert = Spaltenname. ``simulation_id`` fehlt hier, es steht in
#: ``linked_ids`` und wird eigens aufgelöst.
_PROJECTED_KEYS: dict[str, str] = {
    'run_id': 'id',
    'run_type': 'run_type',
    'entity_id': 'entity_id',
    'status': 'status',
    'started_at': 'started_at',
    'updated_at': 'updated_at',
    'completed_at': 'completed_at',
}


class RunSimulationMissing(LookupError):
    """Ein neuer Run verweist auf eine Simulation, die nicht in
    ``agora.simulations`` steht.

    Tritt auf, wenn Simulationen und Runs nicht in der Reihenfolge "erst
    Simulationen, dann Runs" umgestellt wurden, oder bei einem Altbestand,
    dessen Simulation nicht migriert werden konnte.
    """


def _text_or_none(value: Any) -> Optional[str]:
    """Spaltenwert aus einem Manifestfeld. ``RunRecord`` typisiert die Felder
    als ``Optional[str]``; ein leerer Wert wird ``NULL``."""
    return value if isinstance(value, str) and value else None


def _linked_simulation_id(manifest: dict[str, Any]) -> Optional[str]:
    linked = manifest.get('linked_ids')
    if not isinstance(linked, dict):
        return None
    return _text_or_none(linked.get('simulation_id'))


def _to_row_values(record: RunRecord) -> dict[str, Any]:
    """Vertrag → Zeile. Das Manifest geht vollständig ins ``payload``."""
    manifest = record.to_manifest()
    values: dict[str, Any] = {
        column: _text_or_none(manifest.get(key))
        for key, column in _PROJECTED_KEYS.items()
    }
    values['id'] = record.run_id
    values['simulation_id'] = _linked_simulation_id(manifest)
    values['payload'] = manifest
    return values


def _to_contract(row: RunModel) -> RunRecord:
    """Zeile → Vertrag, allein aus dem Manifest.

    Die Spalte erzwingt kein JSON-Objekt; ein Skalar oder eine Liste zählt
    als unlesbar wie ein kaputtes Manifest (Codex-Review auf #1605).
    """
    if not isinstance(row.payload, dict):
        raise ValueError(f'payload of run {row.id} is not a JSON object')
    return RunRecord(**row.payload)


def _is_simulation_fk_violation(exc: IntegrityError) -> bool:
    return 'fk_runs_simulation_id_simulations' in str(exc.orig)


class PostgresRunRepository:
    """Run-Manifeste in ``agora.runs``."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self._database = database

    @property
    def db(self) -> Database:
        # Erst beim Zugriff auflösen: ein konstruiertes, aber ungenutztes
        # Repository soll keine Verbindung aufbauen.
        return self._database or get_database()

    # -- Schreiben -----------------------------------------------------------

    def save(self, record: RunRecord) -> RunRecord:
        values = _to_row_values(record)
        try:
            with self.db.session() as session:
                target = workspace_for_write(
                    session,
                    session.get(RunModel, values['id']),
                    active_workspace_id(),
                    parent_model=SimulationModel,
                    parent_id=values['simulation_id'],
                    record_label=f"run {values['id']}",
                )
                self._resolve_simulation(session, values, target)
                statement = insert(RunModel).values(**values, workspace_id=target)
                # ``workspace_id`` steht bewusst nicht im Update: eine Zeile
                # wechselt nie den Workspace.
                statement = statement.on_conflict_do_update(
                    index_elements=[RunModel.id],
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
                raise self._missing(record, values) from exc
            raise
        return record

    def add_existing(self, record: RunRecord, workspace_id: Optional[UUID] = None) -> bool:
        """Legt einen Run mit **bestehender** Kennung an. ``False``, wenn die
        Kennung schon vorhanden ist.

        Der Weg für die Datenmigration: ein vorhandener Datensatz wird nicht
        überschrieben, damit ein zweiter Lauf nach dem Umschalten keine
        inzwischen in PostgreSQL geänderten Runs zurückdreht. Ein fehlender
        Simulationsverweis scheitert mit ``RunSimulationMissing`` — aber erst
        nach der Prüfung auf eine vorhandene Zeile: wurde die Simulation nach
        der ersten Migration gelöscht (``ON DELETE SET NULL``), zählt der Run
        bei einer Wiederholung als "schon da", nicht als Fehler
        (Codex-Review auf #1605).
        """
        values = _to_row_values(record)
        try:
            with self.db.session() as session:
                if session.get(RunModel, values['id']) is not None:
                    return False
                if (
                    values['simulation_id'] is not None
                    and session.get(SimulationModel, values['simulation_id']) is None
                ):
                    raise self._missing(record, values)
                target = workspace_id or workspace_for_write(
                    session,
                    None,
                    active_workspace_id(),
                    parent_model=SimulationModel,
                    parent_id=values['simulation_id'],
                )
                statement = (
                    insert(RunModel)
                    .values(**values, workspace_id=target)
                    .on_conflict_do_nothing(index_elements=[RunModel.id])
                    .returning(RunModel.id)
                )
                inserted = session.execute(statement).scalar_one_or_none()
        except IntegrityError as exc:
            if _is_simulation_fk_violation(exc):
                raise self._missing(record, values) from exc
            raise
        return inserted is not None

    def _resolve_simulation(
        self, session: Any, values: dict[str, Any], workspace_id: UUID
    ) -> None:
        """Prüft den Simulationsverweis vor dem Schreiben.

        Fehlt die Simulation, entscheidet, ob der Run schon existiert: ein
        neuer Run scheitert, ein bestehender behält seine Zeile mit
        ``simulation_id = NULL``.
        """
        wanted = values['simulation_id']
        # Nur eine Simulation im selben Workspace zählt; eine fremde ist für
        # diesen Run nicht vorhanden (der zusammengesetzte Fremdschlüssel
        # lehnte sie ohnehin ab).
        if wanted is None or visible(session.get(SimulationModel, wanted), workspace_id):
            return
        if session.get(RunModel, values['id']) is None:
            raise RunSimulationMissing(
                f"run {values['id']} references simulation {wanted}, "
                'which is not in agora.simulations'
            )
        logger.info(
            'Run %s keeps its detached simulation reference '
            '(simulation %s is not in agora.simulations)',
            values['id'],
            wanted,
        )
        values['simulation_id'] = None

    @staticmethod
    def _missing(record: RunRecord, values: dict[str, Any]) -> RunSimulationMissing:
        return RunSimulationMissing(
            f"run {record.run_id} references simulation {values['simulation_id']}, "
            'which is not in agora.simulations'
        )

    # -- Lesen ---------------------------------------------------------------

    def get(self, run_id: str) -> Optional[RunRecord]:
        """Record oder ``None``. Ein unlesbares Manifest zählt als fehlend —
        dieselbe Semantik wie beim Dateiadapter."""
        with self.db.session() as session:
            row = visible(session.get(RunModel, run_id), active_workspace_id())
            if row is None:
                return None
            return self._readable(row)

    def list_all(self, *, limit: int = 100_000) -> List[RunRecord]:
        """Alle Records, neueste zuerst.

        Sortierschlüssel wie im Dateiadapter: ``updated_at``, ersatzweise
        ``started_at``, sonst ``''``. Die Kennung bricht Gleichstände, damit
        die Reihenfolge nicht vom Planer abhängt. Unlesbare Manifeste werden
        übersprungen, **bevor** das Limit greift — ``limit=1`` liefert den
        neuesten lesbaren Run.
        """
        if limit <= 0:
            return []
        sort_key = func.coalesce(
            func.nullif(RunModel.updated_at, ''),
            func.nullif(RunModel.started_at, ''),
            '',
        )
        query = (
            scoped(select(RunModel), RunModel, active_workspace_id())
            .order_by(sort_key.desc(), RunModel.id.desc())
            .execution_options(yield_per=500)
        )
        records: List[RunRecord] = []
        with self.db.session() as session:
            for row in session.scalars(query):
                record = self._readable(row)
                if record is None:
                    continue
                records.append(record)
                if len(records) >= limit:
                    break
        return records

    @staticmethod
    def _readable(row: RunModel) -> Optional[RunRecord]:
        try:
            return _to_contract(row)
        except ValueError as exc:
            # ValueError deckt pydantic.ValidationError mit ab.
            logger.warning(
                'Skipping unreadable run row %s: %s', row.id, type(exc).__name__
            )
            return None
