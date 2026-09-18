"""
Project Context Management
Persists project state on server to avoid frontend passing large data between interfaces
"""

import os
import shutil
import uuid
from typing import Dict, List, Optional
from ..config import Config
from ..contracts.document_manifest_contract import DocumentManifest
from ..contracts.project_contract import Project, ProjectStatus
from ..repositories.project_repository import (
    ProjectRepository,
    get_project_repository,
)
from ..utils.validation import join_within

# ``Project`` und ``ProjectStatus`` leben seit PR 6 im Vertrag
# (``app/contracts/project_contract.py``) und werden hier nur
# weitergereicht. Die Namen bleiben importierbar, wo sie immer waren —
# 13 Module und 39 Testdateien greifen darauf zu.
__all__ = ['Project', 'ProjectStatus', 'ProjectManager']


class ProjectManager:
    """Project Manager - handles project persistence and retrieval"""

    # Project storage root directory
    PROJECTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'projects')

    @classmethod
    def _repository(cls) -> ProjectRepository:
        """Das Repository fuer die Metadaten dieses Aufrufs.

        Pro Aufruf gebaut und nicht zwischengespeichert, weil ``PROJECTS_DIR``
        zur Laufzeit umgebogen wird — elf Testdateien tun das. Ein gecachtes
        Repository hielte den Pfad fest, den es beim ersten Zugriff gesehen
        hat, und schriebe danach am Patch vorbei. Das Objekt ist ein Wrapper
        um einen Pfad; es neu zu bauen kostet nichts.
        """
        return get_project_repository(storage_root=cls.PROJECTS_DIR)

    # ``_ensure_projects_dir`` ist mit dem Port entfallen: das Wurzelverzeichnis
    # anzulegen gehoert dem Adapter, der darin schreibt.

    @classmethod
    def _get_project_dir(cls, project_id: str) -> str:
        """Get project directory path.

        ``join_within`` statt ``os.path.join``: aus dieser Methode speist sich
        ``delete_project``, das ein ganzes Verzeichnis abraeumt. Ein ``..`` im
        Bezeichner traefe dort nicht das Projekt, sondern dessen Nachbarn.
        """
        return join_within(cls.PROJECTS_DIR, project_id)

    # ``_get_project_meta_path`` ist mit dem Port entfallen: den Pfad zu
    # ``project.json`` kennt nur noch der Dateiadapter. Zwei Stellen, die
    # denselben Dateinamen bilden, waeren genau die Doppelwahrheit, die der
    # Port beseitigen soll.

    @classmethod
    def _get_project_files_dir(cls, project_id: str) -> str:
        """Get project file storage directory"""
        return os.path.join(cls._get_project_dir(project_id), 'files')

    @classmethod
    def _get_project_text_path(cls, project_id: str) -> str:
        """Get project extracted text storage path"""
        return os.path.join(cls._get_project_dir(project_id), 'extracted_text.txt')

    @classmethod
    def _get_project_documents_path(cls, project_id: str) -> str:
        """Get project document-manifest sidecar storage path (ADR-0013 Slice 1, Teil A).

        Sidecar neben ``extracted_text.txt``: ordnet Zeichen-Offsets im Blob
        den Quelldateien zu, ohne den Blob selbst um Marker-Parsing zu
        erweitern (Issue #1152).
        """
        return os.path.join(cls._get_project_dir(project_id), 'extracted_documents.json')

    @classmethod
    def create_project(cls, name: str = "Unnamed Project") -> Project:
        """
        Create new project

        Args:
            name: Project name

        Returns:
            Newly created Project object
        """
        project = cls._repository().create(name)

        # Das Artefaktverzeichnis gehoert nicht ins Repository: es haelt
        # Uploads, keine Metadaten, und bleibt auf dem Dateisystem, egal
        # welches Backend die Metadaten traegt.
        os.makedirs(cls._get_project_files_dir(project.project_id), exist_ok=True)

        return project

    @classmethod
    def save_project(cls, project: Project) -> None:
        """Save project metadata"""
        cls._repository().save(project)

    @classmethod
    def get_project(cls, project_id: str) -> Optional[Project]:
        """
        Get project

        Args:
            project_id: Project ID

        Returns:
            Project object, or None if not found
        """
        return cls._repository().get(project_id)

    @classmethod
    def list_projects(cls, limit: int = 50) -> List[Project]:
        """
        List all projects

        Args:
            limit: Result count limit

        Returns:
            Project list, sorted by creation time (descending)
        """
        return cls._repository().list(limit)

    @classmethod
    def delete_project(cls, project_id: str) -> bool:
        """
        Delete project and all its files

        Args:
            project_id: Project ID

        Returns:
            Whether deletion succeeded
        """
        # Zwei Schritte, weil zwei Dinge verschwinden muessen: das
        # Artefaktverzeichnis und der Metadatensatz (wo auch immer er liegt).
        # Beim Dateibackend faellt beides zusammen; sobald die Metadaten in
        # PostgreSQL liegen, nicht mehr.
        #
        # **Die Artefakte zuerst.** Scheitert das Aufraeumen des Verzeichnisses
        # — gesperrte Datei, fehlende Berechtigung, ein parallel schreibender
        # graph_build —, dann bleibt der Metadatensatz erhalten und das Projekt
        # sichtbar. Der Nutzer sieht einen Fehler und kann es erneut versuchen.
        # In der umgekehrten Reihenfolge waere der Datensatz bereits weg und
        # die hochgeladenen Dokumente laegen unerreichbar auf der Platte, ohne
        # dass eine Route sie noch findet.
        project_dir = cls._get_project_dir(project_id)
        directory_existed = os.path.exists(project_dir)
        if directory_existed:
            shutil.rmtree(project_dir)

        removed_record = cls._repository().delete(project_id)

        # ``True``, wenn es irgendetwas zu loeschen gab. Ein Projektverzeichnis
        # ohne lesbare project.json hat vorher ``True`` geliefert und tut es
        # weiterhin.
        return removed_record or directory_existed

    @classmethod
    def save_file_to_project(cls, project_id: str, file_storage, original_filename: str) -> Dict[str, str]:
        """
        Save uploaded file to project directory

        Args:
            project_id: Project ID
            file_storage: Flask FileStorage object
            original_filename: Original filename

        Returns:
            File information dictionary {filename, path, size}
        """
        from werkzeug.utils import secure_filename
        from ..utils.validation import validate_project_id

        if not validate_project_id(project_id):
            raise ValueError(f"Invalid project_id: {project_id}")

        files_dir = cls._get_project_files_dir(project_id)
        os.makedirs(files_dir, exist_ok=True)

        # Generate safe filename
        safe_orig = secure_filename(original_filename)
        ext = os.path.splitext(safe_orig)[1].lower()
        safe_filename = f"{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(files_dir, safe_filename)

        # Ensure we are still within the projects directory (defensive)
        if not os.path.abspath(file_path).startswith(os.path.abspath(cls.PROJECTS_DIR)):
            raise ValueError("Path traversal attempt detected")

        # Save file
        file_storage.save(file_path)

        # Get file size
        file_size = os.path.getsize(file_path)

        return {
            "original_filename": original_filename,
            "saved_filename": safe_filename,
            "path": file_path,
            "size": file_size
        }

    @classmethod
    def save_extracted_text(cls, project_id: str, text: str) -> None:
        """Save extracted text"""
        text_path = cls._get_project_text_path(project_id)
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(text)

    @classmethod
    def get_extracted_text(cls, project_id: str) -> Optional[str]:
        """Get extracted text"""
        text_path = cls._get_project_text_path(project_id)

        if not os.path.exists(text_path):
            return None

        with open(text_path, 'r', encoding='utf-8') as f:
            return f.read()

    @classmethod
    def save_document_manifest(cls, project_id: str, manifest: DocumentManifest) -> None:
        """Persist das Dokument-Manifest-Sidecar neben ``extracted_text.txt``.

        ADR-0013 Slice 1, Teil A (Issue #1152).
        """
        documents_path = cls._get_project_documents_path(project_id)
        with open(documents_path, 'w', encoding='utf-8') as f:
            f.write(manifest.model_dump_json(indent=2))

    @classmethod
    def get_document_manifest(cls, project_id: str) -> Optional[DocumentManifest]:
        """Lädt das Dokument-Manifest-Sidecar, falls vorhanden.

        Altprojekte ohne Sidecar liefern ``None`` — das ist KEIN Fehler
        (ADR-0013 §3: Bestandsgraphen werden nicht nachgerüstet).
        """
        documents_path = cls._get_project_documents_path(project_id)

        if not os.path.exists(documents_path):
            return None

        with open(documents_path, 'r', encoding='utf-8') as f:
            return DocumentManifest.model_validate_json(f.read())

    @classmethod
    def get_project_files(cls, project_id: str) -> List[str]:
        """Get all project file paths"""
        files_dir = cls._get_project_files_dir(project_id)

        if not os.path.exists(files_dir):
            return []

        return [
            os.path.join(files_dir, f)
            for f in os.listdir(files_dir)
            if os.path.isfile(os.path.join(files_dir, f))
        ]

