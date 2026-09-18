"""Port fuer Projekt-Metadaten (docs/plans/supabase.md §11, PR 6).

Der Port beschreibt ausschliesslich die **Metadaten** eines Projekts — den
Inhalt von ``project.json``. Die Artefakte daneben (``files/``,
``extracted_text.txt``, ``extracted_documents.json``) bleiben Sache des
Dateisystems und tauchen hier bewusst nicht auf: sie wandern in keiner Phase
dieses Plans in eine Datenbank, und ein Port, der sie mitfuehrte, muesste von
jedem Adapter beantwortet werden, der sie gar nicht hat.

Die Semantik ist die des heutigen Dateispeichers und wird hier festgeschrieben,
damit ein zweiter Adapter sie nicht anders auslegt. Vier Punkte sind dabei
keine Geschmacksfrage:

``get`` gibt ``None`` zurueck, wenn es das Projekt nicht gibt — es wirft nicht.
Ein fehlendes Projekt ist ein erwarteter Fall, und die Aufrufer pruefen auf
``None``.

``list`` sortiert nach ``created_at`` absteigend und schneidet danach auf
``limit`` ab. Die Reihenfolge ist Teil der Zusage, nicht ein Nebenprodukt der
Ablage: die Projektliste der Oberflaeche zeigt das Neueste oben.

``create`` vergibt die Kennung selbst, im Format ``proj_<12 Hexstellen>``. Sie
ist zugleich der Verzeichnisname unter ``uploads/projects/``, weshalb sie
weder Form noch Erzeugungsregel wechseln darf, solange dort Artefakte liegen.

``delete`` entfernt **nur** den Metadatensatz und sagt, ob es einen gab. Das
Verzeichnis samt Artefakten raeumt der Aufrufer ab. Andernfalls haette jeder
Adapter eine Meinung zum Dateisystem zu haben, und der PostgreSQL-Adapter
haette sie faelschlich.
"""

from __future__ import annotations

import uuid
from typing import Optional, Protocol, runtime_checkable

from ..config import (
    Config,
    PROJECT_BACKENDS,
    PROJECT_BACKENDS_NOT_YET_AVAILABLE,
)
from ..contracts import Project

#: Praefix und Laenge der Projektkennung. Steht hier und nicht in einem
#: Adapter, weil jeder Adapter dieselbe Form erzeugen muss: die Kennung ist
#: zugleich der Verzeichnisname unter ``uploads/projects/``, und ein zweites
#: Format hiesse, dass ein migriertes Projekt seine Artefakte nicht faende.
PROJECT_ID_PREFIX = 'proj_'
PROJECT_ID_HEX_LENGTH = 12


def new_project_id() -> str:
    """Erzeugt eine Projektkennung der Form ``proj_<12 Hexstellen>``."""
    return f'{PROJECT_ID_PREFIX}{uuid.uuid4().hex[:PROJECT_ID_HEX_LENGTH]}'


class ProjectBackendUnavailable(RuntimeError):
    """Der konfigurierte Backend-Wert ist gueltig, aber es gibt keinen Adapter.

    Kein `ValueError`: der Wert ist nicht falsch, er ist noch nicht bedient.
    Der Unterschied steht in der Meldung, damit niemand nach einem Tippfehler
    sucht, den es nicht gibt.
    """


@runtime_checkable
class ProjectRepository(Protocol):
    """Lesen und Schreiben von Projekt-Metadaten, unabhaengig von der Ablage."""

    def create(self, name: str = 'Unnamed Project') -> Project:
        """Legt ein Projekt an und gibt es persistiert zurueck.

        Die Kennung vergibt das Repository (``proj_<12 Hexstellen>``),
        ``created_at`` und ``updated_at`` stehen beide auf dem Anlagezeitpunkt.
        """
        ...

    def save(self, project: Project) -> None:
        """Schreibt den Datensatz und setzt dabei ``updated_at`` auf jetzt.

        Das Stempeln gehoert hierher und nicht zum Aufrufer: sonst haengt es
        davon ab, ob jemand daran gedacht hat.

        Auf ein Projekt, das es nicht gibt, schlaegt ``save`` fehl — kein
        Adapter erfindet eines als Nebeneffekt eines Schreibvorgangs. **Der
        Fehlertyp ist adapterabhaengig** (Dateisystem- bzw. Datenbankfehler)
        und wird hier bewusst nicht festgeschrieben.

        Eine bekannte Ungenauigkeit: ruft jemand ``delete`` und danach ``save``
        **direkt am Port** auf, ohne den Weg ueber ``ProjectManager``, legt der
        Dateiadapter den Datensatz neu an — sein ``delete`` entfernt nur
        ``project.json``, das Verzeichnis bleibt stehen. Der PostgreSQL-Adapter
        schlaegt in derselben Lage fehl. Im Produktionspfad tritt das nicht
        auf, weil ``ProjectManager.delete_project`` das Verzeichnis mit
        abraeumt; fuer direkte Port-Aufrufer ist es real.
        """
        ...

    def get(self, project_id: str) -> Optional[Project]:
        """Ein Projekt oder ``None``, wenn es das nicht gibt."""
        ...

    def list(self, limit: int = 50) -> list[Project]:
        """Projekte, neuestes zuerst, hoechstens ``limit`` Stueck."""
        ...

    def delete(self, project_id: str) -> bool:
        """Entfernt den Metadatensatz. ``True``, wenn es einen gab.

        Artefakte bleiben unberuehrt — siehe Modul-Docstring.
        """
        ...


def get_project_repository(storage_root: str | None = None) -> ProjectRepository:
    """Die einzige Stelle, an der ein Consumer an ein Projekt-Repository kommt.

    Der Import des Adapters steht bewusst in der Funktion: ein Modul, das nur
    den Port braucht, soll die Ablage nicht mitladen.

    ``storage_root`` ist der Ort einer dateibasierten Ablage. Er steht hier,
    weil ``ProjectManager.PROJECTS_DIR`` zur Laufzeit umgebogen wird — von elf
    Testdateien und damit auch von jedem kuenftigen Aufrufer, der Projekte
    woanders hinlegen will. Ein Adapter ohne Dateiablage ignoriert den Wert.
    """
    backend = Config.PROJECT_BACKEND
    if backend not in PROJECT_BACKENDS:
        # Ein Tippfehler darf nicht still auf den Dateiadapter zurueckfallen.
        # Config.validate() lehnt ihn beim Start ab, aber wer das Repository
        # ohne Validierung erreicht — ein Test, ein Skript — bekaeme sonst
        # klaglos die Vorgabe und glaubte, er haette umgeschaltet.
        raise ProjectBackendUnavailable(
            f"AGORA_PROJECT_BACKEND has unknown value '{backend}' "
            f'(expected one of: {", ".join(sorted(PROJECT_BACKENDS))})'
        )
    if backend in PROJECT_BACKENDS_NOT_YET_AVAILABLE:
        # Dieselbe Aussage wie in Config.validate(), fuer den Fall, dass jemand
        # das Repository ohne vorherige Validierung erreicht — ein Test, ein
        # Skript, ein kuenftiger Aufrufer.
        raise ProjectBackendUnavailable(
            f'AGORA_PROJECT_BACKEND={backend} has no adapter yet'
        )
    if backend == 'postgres':
        from ..infrastructure.postgres.repositories import PostgresProjectRepository

        return PostgresProjectRepository()
    from ..services.file_project_store import get_file_project_repository

    return get_file_project_repository(storage_root)
