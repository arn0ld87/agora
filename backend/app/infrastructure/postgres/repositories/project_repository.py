"""PostgreSQL-Adapter des ``ProjectRepository``-Ports (§11, PR 6).

Der Adapter bedient **nur Metadaten**. Die Artefakte eines Projekts —
``files/``, ``extracted_text.txt``, das Dokument-Manifest — bleiben auf dem
Dateisystem, unabhängig davon, wo die Metadaten liegen. Entsprechend entfernt
``delete`` hier ausschliesslich die Zeile; das Verzeichnis räumt der Aufrufer
ab (``ProjectManager.delete_project``).

**Die Aufteilung auf Kernspalten und ``payload`` wird abgeleitet, nicht
gepflegt.** ``_CORE_KEYS`` nennt die Felder mit eigener Spalte; alles, was
``Project.to_dict()`` darüber hinaus liefert, geht unbesehen ins ``payload``.
Das ist der Grund, warum diese Klasse kein Feld verlieren kann: ein künftiges
Vertragsfeld landet automatisch im JSON, statt beim Schreiben stillschweigend
unter den Tisch zu fallen. Umgekehrt verwirft ``Project.from_dict`` unbekannte
Schlüssel aus einem alten ``payload``, statt daran zu scheitern.

**Die Kennung bleibt, wie sie ist.** ``proj_<12 Hexstellen>``, erzeugt über
dieselbe Funktion wie im Dateiadapter, weil sie zugleich der Verzeichnisname
unter ``uploads/projects/`` ist. Ein zweites Format hier hiesse, dass ein
migriertes Projekt seine Artefakte nicht mehr findet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ....contracts import Project
from ....repositories.project_repository import new_project_id
from ....utils.logger import get_logger
from ..models.project import ProjectModel
from ..session import Database, get_database

logger = get_logger('agora.projects.postgres')

#: Felder des Vertrags mit eigener Spalte. Der Schlüssel ist der Name in
#: ``Project.to_dict()``, der Wert der Spaltenname — sie unterscheiden sich
#: genau einmal, bei ``project_id`` / ``id``.
_CORE_KEYS: dict[str, str] = {
    'project_id': 'id',
    'name': 'name',
    'status': 'status',
    'graph_id': 'graph_id',
    'llm_profile_id': 'llm_profile_id',
    'created_at': 'created_at',
    'updated_at': 'updated_at',
}


class ProjectNotStored(LookupError):
    """``save`` auf ein Projekt, das es nicht gibt.

    Das Gegenstück zum ``FileNotFoundError`` des Dateiadapters: dort scheitert
    das Schreiben, weil das Projektverzeichnis fehlt. Beide Adapter erfinden
    kein Projekt als Nebeneffekt eines Speichervorgangs.
    """


def _now() -> str:
    """Zeitstempel im Format der Ablage.

    ``datetime.now().isoformat()`` — dieselbe Erzeugung wie im Dateiadapter,
    damit ein Datensatz nach der Migration nicht plötzlich ein anderes
    Zeitformat trägt.
    """
    return datetime.now().isoformat()


def _to_row_values(project: Project) -> dict[str, Any]:
    """Vertrag → Spalten. Alles ohne eigene Spalte geht ins ``payload``."""
    data = project.to_dict()
    values: dict[str, Any] = {
        column: data[key] for key, column in _CORE_KEYS.items()
    }
    values['payload'] = {
        key: value for key, value in data.items() if key not in _CORE_KEYS
    }
    return values


def _to_contract(row: ProjectModel) -> Project:
    """Spalten → Vertrag.

    Die Kernspalten überschreiben das ``payload``, nicht umgekehrt: läge dort
    durch einen früheren Fehler ein abweichender Wert, gilt die Spalte.
    """
    data: dict[str, Any] = dict(row.payload or {})
    data.update(
        project_id=row.id,
        name=row.name,
        status=row.status,
        graph_id=row.graph_id,
        llm_profile_id=row.llm_profile_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return Project.from_dict(data)


class PostgresProjectRepository:
    """Projekt-Metadaten in ``agora.projects``."""

    def __init__(self, database: Optional[Database] = None) -> None:
        self._database = database

    @property
    def db(self) -> Database:
        # Erst beim Zugriff aufloesen: ein konstruiertes, aber ungenutztes
        # Repository soll keine Verbindung aufbauen.
        return self._database or get_database()

    # -- Schreiben -----------------------------------------------------------

    def create(self, name: str = 'Unnamed Project') -> Project:
        now = _now()
        project = Project(
            project_id=new_project_id(),
            name=name,
            created_at=now,
            updated_at=now,
        )
        with self.db.session() as session:
            session.add(ProjectModel(**_to_row_values(project)))
        return project

    def add_existing(self, project: Project) -> bool:
        """Legt ein Projekt mit seiner **bestehenden** Kennung und ihren
        Zeitstempeln an. ``False``, wenn die Kennung schon vorhanden ist.

        Das ist der Weg für die Datenmigration, und er ist bewusst nicht
        ``create``: der vergibt eine neue Kennung und stempelt die Zeit auf
        jetzt. Beides wäre hier falsch — die Kennung ist der Verzeichnisname
        der Artefakte, und ein Bestand, dessen Zeitstempel alle auf den Tag der
        Migration zeigen, hat seine Entstehungsgeschichte verloren.

        Idempotent, damit ein zweiter Lauf nach einem Abbruch weitermacht,
        statt einen inzwischen geänderten Datensatz zu überschreiben.

        Die Vorabprüfung allein genügt dafür nicht: zwischen ihr und dem
        Schreiben liegt ein Fenster, in dem ein zweiter gleichzeitiger Lauf
        dieselbe Kennung anlegen könnte. Deshalb wird die
        Primärschlüsselverletzung zusätzlich abgefangen und als „schon da"
        gewertet — die Datenbank ist hier die verlässlichere Instanz als ein
        vorheriger Blick.
        """
        with self.db.session() as session:
            if session.get(ProjectModel, project.project_id) is not None:
                return False

        try:
            with self.db.session() as session:
                session.add(ProjectModel(**_to_row_values(project)))
        except IntegrityError:
            logger.info(
                'Project %s was inserted concurrently — treated as existing',
                project.project_id,
            )
            return False
        return True

    def save(self, project: Project) -> None:
        project.updated_at = _now()
        values = _to_row_values(project)
        with self.db.session() as session:
            row = session.get(ProjectModel, project.project_id)
            if row is None:
                raise ProjectNotStored(
                    f'project {project.project_id} does not exist'
                )
            for column, value in values.items():
                setattr(row, column, value)

    def delete(self, project_id: str) -> bool:
        """Entfernt nur die Zeile. Artefakte raeumt der Aufrufer ab."""
        with self.db.session() as session:
            row = session.get(ProjectModel, project_id)
            if row is None:
                return False
            session.delete(row)
        return True

    # -- Lesen ---------------------------------------------------------------

    def get(self, project_id: str) -> Optional[Project]:
        with self.db.session() as session:
            row = session.get(ProjectModel, project_id)
            return None if row is None else _to_contract(row)

    def list(self, limit: int = 50) -> list[Project]:
        """Projekte, neuestes zuerst.

        Sortiert wird über die Spalte ``created_at``, die ISO-8601-Zeichenketten
        führt — für dieses Format ist die lexikografische Ordnung die
        chronologische, genau wie beim Dateiadapter. Der Index
        ``ix_projects_created_at`` liegt darauf.

        **Ein unlesbarer Datensatz laesst die Liste stehen**, statt sie
        abzubrechen — dieselbe Zusage wie beim Dateiadapter, und aus demselben
        Grund: eine Zeile, deren ``payload`` nicht mehr zum Vertrag passt,
        darf nicht die gesamte Projektuebersicht abschalten. Uebersprungen
        heisst nicht verschwiegen; jeder Fall wird mit seiner Kennung
        protokolliert.
        """
        with self.db.session() as session:
            rows = session.scalars(
                select(ProjectModel)
                .order_by(ProjectModel.created_at.desc())
                # Ein negativer Wert waere in SQL ein Fehler, im Dateiadapter
                # dagegen ein Python-Slice. Hier gleichgezogen.
                .limit(max(0, limit))
            ).all()

            projects: list[Project] = []
            for row in rows:
                try:
                    projects.append(_to_contract(row))
                except ValueError as exc:
                    # ValueError deckt pydantic.ValidationError mit ab.
                    logger.warning(
                        'Skipping unreadable project row %s: %s',
                        row.id,
                        type(exc).__name__,
                    )
            return projects
