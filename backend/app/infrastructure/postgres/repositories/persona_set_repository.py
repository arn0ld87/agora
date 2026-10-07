"""PostgreSQL-Adapter des ``PersonaSetRepository``-Ports (Issue #1807, Etappe 7).

Der Adapter bedient dieselben Zusagen wie ``FilePersonaSetRepository``
(``app/repositories/persona_set_repository.py``).

**Die Aufteilung auf Kernspalten und ``payload`` wird abgeleitet, nicht
gepflegt** — wie bei ``PostgresSimulationRepository``. ``_CORE_KEYS`` nennt die
Felder mit eigener Spalte; alles, was der Vertrag darüber hinaus liefert
(Beschreibung, Einträge, ``used_by_simulation_ids``, ``schema_version``), geht
unbesehen ins ``payload``. Ein künftiges Vertragsfeld landet damit automatisch
im JSON, statt beim Schreiben verloren zu gehen.

**``save`` legt an oder aktualisiert** und lässt die Sperre eines bestehenden
Satzes unberührt (``locked_at``, ``used_by_simulation_ids``): die ändert nur
``mark_used``. Beide sperren die Zeile (``SELECT … FOR UPDATE``), damit ein
gleichzeitiges ``save`` und ``mark_used`` einander nicht überschreiben.

``mark_used`` ist atomar und idempotent; die Zeilensperre ersetzt das
prozessweite Lock des Dateiadapters.

Es gibt keine Fremdschlüssel: ``graph_id``/``project_id`` sind Verweise ohne
Integritätsbindung (siehe Modell-Docstring).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import select

from ....contracts.persona_set_contract import PersonaSetRecord
from ....utils.logger import get_logger
from ..models.persona_set import PersonaSetModel
from ..session import Database, get_database
from ..workspace_scope import active_workspace_id, scoped, visible, workspace_for_write

logger = get_logger('agora.persona_sets.postgres')

#: Felder des Vertrags mit eigener Spalte. Schlüssel = Name in
#: ``PersonaSetRecord.model_dump()``, Wert = Spaltenname.
_CORE_KEYS: dict[str, str] = {
    'id': 'id',
    'name': 'name',
    'graph_id': 'graph_id',
    'project_id': 'project_id',
    'locked_at': 'locked_at',
    'created_at': 'created_at',
    'updated_at': 'updated_at',
}

_USED_BY = 'used_by_simulation_ids'


def _now() -> str:
    """Zeitstempel im Format der Ablage, wie im Dateiadapter."""
    return datetime.now().isoformat()


def _to_row_values(record: PersonaSetRecord) -> dict[str, Any]:
    """Vertrag → Spalten. Alles ohne eigene Spalte geht ins ``payload``."""
    data = record.model_dump(mode='json')
    values: dict[str, Any] = {column: data[key] for key, column in _CORE_KEYS.items()}
    values['payload'] = {
        key: value for key, value in data.items() if key not in _CORE_KEYS
    }
    return values


def _to_contract(row: PersonaSetModel) -> PersonaSetRecord:
    """Spalten → Vertrag. Die Kernspalten überschreiben das ``payload``."""
    data: dict[str, Any] = dict(row.payload or {})
    data.update(
        id=row.id,
        name=row.name,
        graph_id=row.graph_id,
        project_id=row.project_id,
        locked_at=row.locked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return PersonaSetRecord.model_validate(data)


class PostgresPersonaSetRepository:
    """Personasätze in ``agora.persona_sets``."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self._database = database

    @property
    def db(self) -> Database:
        # Erst beim Zugriff auflösen: ein konstruiertes, aber ungenutztes
        # Repository soll keine Verbindung aufbauen.
        return self._database or get_database()

    # -- Schreiben -----------------------------------------------------------

    def save(self, record: PersonaSetRecord) -> None:
        record.updated_at = _now()
        workspace_id = active_workspace_id()
        with self.db.session() as session:
            row = session.get(PersonaSetModel, record.id, with_for_update=True)
            target = workspace_for_write(
                session,
                row,
                workspace_id,
                record_label=f'persona set {record.id}',
            )
            if row is not None:
                # Die Sperre ändert nur ``mark_used`` (Port-Docstring).
                record.locked_at = row.locked_at
                record.used_by_simulation_ids = list(
                    (row.payload or {}).get(_USED_BY) or []
                )
            values = _to_row_values(record)
            if row is None:
                session.add(PersonaSetModel(**values, workspace_id=target))
                return
            for column, value in values.items():
                setattr(row, column, value)

    def delete(self, set_id: str) -> bool:
        with self.db.session() as session:
            row = visible(session.get(PersonaSetModel, set_id), active_workspace_id())
            if row is None:
                return False
            session.delete(row)
            return True

    def mark_used(
        self, set_id: str, simulation_id: str
    ) -> Optional[PersonaSetRecord]:
        if not simulation_id:
            raise ValueError('simulation_id must not be empty')
        with self.db.session() as session:
            row = visible(
                session.get(PersonaSetModel, set_id, with_for_update=True),
                active_workspace_id(),
            )
            if row is None:
                return None
            payload: dict[str, Any] = dict(row.payload or {})
            used = list(payload.get(_USED_BY) or [])
            if simulation_id not in used:
                now = _now()
                used.append(simulation_id)
                payload[_USED_BY] = used
                # Neu zuweisen: eine In-Place-Änderung am JSONB-Wert bliebe
                # ohne ``MutableDict`` unbemerkt.
                row.payload = payload
                if row.locked_at is None:
                    row.locked_at = now
                row.updated_at = now
            return _to_contract(row)

    # -- Lesen ---------------------------------------------------------------

    def get(self, set_id: str) -> Optional[PersonaSetRecord]:
        with self.db.session() as session:
            row = visible(session.get(PersonaSetModel, set_id), active_workspace_id())
            return None if row is None else _to_contract(row)

    def list(self) -> List[PersonaSetRecord]:
        """Alle Sätze, neuester zuerst (``created_at``, dann ``id``, absteigend).

        Ein unlesbarer Datensatz lässt die Liste stehen und wird mit seiner
        Kennung protokolliert, wie beim Dateiadapter.
        """
        query = scoped(
            select(PersonaSetModel), PersonaSetModel, active_workspace_id()
        ).order_by(PersonaSetModel.created_at.desc(), PersonaSetModel.id.desc())
        with self.db.session() as session:
            return self._readable(session.scalars(query).all())

    @staticmethod
    def _readable(rows: Any) -> List[PersonaSetRecord]:
        records: List[PersonaSetRecord] = []
        for row in rows:
            try:
                records.append(_to_contract(row))
            except ValueError as exc:
                # ValueError deckt pydantic.ValidationError mit ab.
                logger.warning(
                    'Skipping unreadable persona set row %s: %s',
                    row.id,
                    type(exc).__name__,
                )
        return records
