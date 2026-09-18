"""Dateibasierter Adapter fuer Projekt-Metadaten (PR 6).

Das ist die bisherige Logik aus ``ProjectManager``, hinter den Port gelegt —
eine Umbenennung, keine Neuimplementierung. Pfadbildung, Dateiname und der
Inhalt von ``project.json`` bleiben unveraendert, damit eine bestehende
Installation nach diesem Umbau dieselben Dateien liest und schreibt wie davor.

**Warum das Verzeichnis hereingereicht wird und nicht hier steht:**
``ProjectManager.PROJECTS_DIR`` ist ein Klassenattribut, das elf Testdateien
zur Laufzeit auf ein temporaeres Verzeichnis umbiegen. Wuerde der Adapter den
Pfad selbst aus ``Config.UPLOAD_FOLDER`` ableiten oder ihn beim Import
einfrieren, liefe er an diesen Patches vorbei und die Tests schrieben in das
echte Upload-Verzeichnis. Der Aufrufer bleibt deshalb die Quelle des Pfades.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from ..config import Config
from ..contracts import Project, ProjectStatus
from ..repositories.project_repository import new_project_id
from ..utils.logger import get_logger
from ..utils.validation import join_within

logger = get_logger('agora.projects.file_store')

PROJECT_META_FILENAME = 'project.json'


class FileProjectRepository:
    """Projekt-Metadaten als ``project.json`` je Projektverzeichnis."""

    def __init__(self, projects_dir: str) -> None:
        self.projects_dir = projects_dir

    # --- Pfade ------------------------------------------------------------

    def _ensure_projects_dir(self) -> None:
        os.makedirs(self.projects_dir, exist_ok=True)

    def _project_dir(self, project_id: str) -> str:
        # ``join_within`` statt ``os.path.join``: hier wird aus einem
        # Bezeichner ein Pfad, und das ist die Stelle, an der ein ``..`` zu
        # verhindern ist — unabhaengig davon, ob ein Aufrufer vorher
        # validiert hat.
        return join_within(self.projects_dir, project_id)

    def _meta_path(self, project_id: str) -> str:
        return os.path.join(self._project_dir(project_id), PROJECT_META_FILENAME)

    # --- Port -------------------------------------------------------------

    def create(self, name: str = 'Unnamed Project') -> Project:
        """Legt Projektverzeichnis und Metadatensatz an.

        Das Projektverzeichnis gehoert hierher, weil ``project.json`` darin
        liegt — ohne das Verzeichnis gibt es den Datensatz nicht. Das
        ``files/``-Unterverzeichnis ist dagegen Artefaktsache und bleibt beim
        Aufrufer.
        """
        self._ensure_projects_dir()

        # Die Kennung erzeugt der Port, nicht dieser Adapter: der
        # PostgreSQL-Adapter muss dieselbe Form liefern, sonst faende ein
        # migriertes Projekt seine Artefakte nicht wieder.
        project_id = new_project_id()
        now = datetime.now().isoformat()

        project = Project(
            project_id=project_id,
            name=name,
            status=ProjectStatus.CREATED,
            created_at=now,
            updated_at=now,
        )

        os.makedirs(self._project_dir(project_id), exist_ok=True)
        self.save(project)

        return project

    def save(self, project: Project) -> None:
        """Schreibt ``project.json`` und stempelt ``updated_at``.

        Legt bewusst kein Verzeichnis an: ``save`` auf ein Projekt, das es
        nicht gibt, soll scheitern statt stillschweigend eines zu erfinden.
        Das war vorher so und bleibt so.
        """
        project.updated_at = datetime.now().isoformat()

        with open(self._meta_path(project.project_id), 'w', encoding='utf-8') as handle:
            json.dump(project.to_dict(), handle, ensure_ascii=False, indent=2)

    def get(self, project_id: str) -> Optional[Project]:
        meta_path = self._meta_path(project_id)

        if not os.path.exists(meta_path):
            return None

        with open(meta_path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)

        return Project.from_dict(data)

    def list(self, limit: int = 50) -> list[Project]:
        """Projekte, neuestes zuerst.

        Die Ablage kennt keinen Index: jedes Verzeichnis wird geoeffnet.
        Verzeichnisse ohne ``project.json`` fallen heraus, weil ``get`` dort
        ``None`` liefert.

        **Ein unlesbarer Datensatz laesst die Liste stehen**, statt sie
        abzubrechen. Das ist eine bewusste Abweichung von ``get``, und der
        Grund ist der Unterschied im Schadensbild: wer ein bestimmtes Projekt
        anfordert, soll den Fehler sehen; wer die Uebersicht oeffnet, soll
        nicht wegen eines einzigen kaputten Verzeichnisses vor einer leeren
        Seite stehen. Vor dem Vertrag war das kaum zu treffen — die alte
        ``from_dict`` pruefte keine Typen und warf fast nie. Pydantic pruefet
        jedes Feld, und damit waeren aus einem beschaedigten Datensatz
        schlagartig alle Projekte unerreichbar geworden.

        Uebersprungen heisst nicht verschwiegen: jeder Fall wird mit seiner
        Projektkennung als Warnung protokolliert.
        """
        self._ensure_projects_dir()

        projects = []
        for project_id in os.listdir(self.projects_dir):
            try:
                project = self.get(project_id)
            except (ValueError, OSError) as exc:
                # ValueError deckt json.JSONDecodeError und pydantic.
                # ValidationError ab, OSError den unlesbaren Datentraeger.
                logger.warning(
                    'Skipping unreadable project record %s: %s',
                    project_id,
                    type(exc).__name__,
                )
                continue
            if project:
                projects.append(project)

        projects.sort(key=lambda item: item.created_at, reverse=True)

        return projects[:limit]

    def delete(self, project_id: str) -> bool:
        """Entfernt ``project.json``. ``True``, wenn es sie gab.

        Das Projektverzeichnis mit den Artefakten bleibt stehen — es abzuraeumen
        ist Sache des Aufrufers, siehe Port-Docstring.
        """
        meta_path = self._meta_path(project_id)

        if not os.path.exists(meta_path):
            return False

        os.remove(meta_path)
        return True


def get_file_project_repository(projects_dir: str | None = None) -> FileProjectRepository:
    """Baut den Dateiadapter.

    Ohne Angabe faellt der Pfad auf ``<UPLOAD_FOLDER>/projects`` zurueck —
    derselbe Ausdruck, den ``ProjectManager.PROJECTS_DIR`` bildet. Der
    Regelfall ist aber, dass der Aufrufer ihn mitgibt.
    """
    if projects_dir is None:
        projects_dir = os.path.join(Config.UPLOAD_FOLDER, 'projects')
    return FileProjectRepository(projects_dir)
