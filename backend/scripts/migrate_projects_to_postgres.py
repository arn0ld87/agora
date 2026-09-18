"""Überträgt Projekt-Metadaten vom Dateisystem nach PostgreSQL (§11, PR 6).

Was übertragen wird
-------------------
Der Inhalt jeder ``uploads/projects/<project_id>/project.json`` nach
``agora.projects``. Die Aufteilung auf Kernspalten und ``payload`` macht der
Adapter; dieses Skript reicht den Vertrag durch und erfindet nichts.

**Kennungen und Zeitstempel bleiben unverändert.** ``project_id`` ist zugleich
der Verzeichnisname, unter dem die Artefakte liegen — eine neue Kennung hiesse,
dass ein migriertes Projekt seine Dateien nicht mehr findet. ``created_at`` und
``updated_at`` werden übernommen, nicht neu gesetzt: eine Migration, die alles
auf „heute" stellt, verliert genau die Information, mit der sich später
nachvollziehen lässt, was wann entstand.

Was NICHT passiert
------------------
**Das Dateisystem wird nicht angefasst.** Weder die ``project.json`` noch die
Artefakte daneben werden verändert, verschoben oder gelöscht. Die Dateiablage
bleibt die Wahrheit, bis jemand ``AGORA_PROJECT_BACKEND=postgres`` setzt — und
auch danach bleibt sie als Rückweg liegen.

Artefakte wandern **nie** mit: ``files/``, ``extracted_text.txt`` und das
Dokument-Manifest bleiben auf der Platte, unabhängig davon, wo die Metadaten
liegen.

Aufruf::

    uv run python scripts/migrate_projects_to_postgres.py --dry-run
    uv run python scripts/migrate_projects_to_postgres.py
    uv run python scripts/migrate_projects_to_postgres.py --verify
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Config  # noqa: E402
from app.contracts import Project  # noqa: E402
from app.infrastructure.postgres.repositories.project_repository import (  # noqa: E402
    PostgresProjectRepository,
)

PROJECT_META_FILENAME = 'project.json'


def projects_dir() -> Path:
    """Dasselbe Verzeichnis, das ``ProjectManager.PROJECTS_DIR`` bildet."""
    return Path(Config.UPLOAD_FOLDER) / 'projects'


def read_file_projects(root: Path) -> List[Project]:
    """Liest den Bestand, ausschliesslich lesend.

    Ein Verzeichnis ohne ``project.json`` ist ein halb angelegtes Projekt und
    wird übersprungen. Eine **unlesbare** Datei dagegen bricht ab: eine
    Migration, die stillschweigend Datensätze auslässt, ist schlimmer als eine,
    die anhält und sagt, woran es lag.
    """
    if not root.exists():
        return []

    projects: List[Project] = []
    for entry in sorted(root.iterdir()):
        meta = entry / PROJECT_META_FILENAME
        if not entry.is_dir() or not meta.exists():
            continue
        with open(meta, 'r', encoding='utf-8') as handle:
            projects.append(Project.from_dict(json.load(handle)))
    return projects


def migrate(
    root: Path,
    *,
    dry_run: bool = False,
    repository: Optional[PostgresProjectRepository] = None,
) -> Dict[str, int]:
    """Schreibt den Bestand nach ``agora.projects``.

    Idempotent: ein Projekt, dessen Kennung schon in der Tabelle steht, wird
    übersprungen und nicht überschrieben. Ein zweiter Lauf nach einem
    Abbruch macht damit da weiter, wo der erste aufgehört hat, ohne einen
    inzwischen in PostgreSQL geänderten Datensatz zu überschreiben.

    ``repository`` ist der Einstiegspunkt für Tests. Ohne Angabe entsteht eines
    auf der konfigurierten ``DATABASE_URL`` — das ist der Weg über die
    Kommandozeile.
    """
    projects = read_file_projects(root)
    zaehler = {'gefunden': len(projects), 'uebertragen': 0, 'uebersprungen': 0}

    if dry_run:
        return zaehler

    ziel = repository or PostgresProjectRepository()
    for project in projects:
        if ziel.add_existing(project):
            zaehler['uebertragen'] += 1
        else:
            zaehler['uebersprungen'] += 1
    return zaehler


def verify(
    root: Path, *, repository: Optional[PostgresProjectRepository] = None
) -> List[str]:
    """Vergleicht beide Seiten feldweise und liefert die Abweichungen.

    Verglichen wird ``to_dict()`` gegen ``to_dict()`` — die Form, die auch in
    der Datei steht. Eine leere Liste heisst: jedes Feld jedes Projekts steht
    auf beiden Seiten gleich.
    """
    abweichungen: List[str] = []
    quelle = repository or PostgresProjectRepository()

    for datei_projekt in read_file_projects(root):
        db_projekt = quelle.get(datei_projekt.project_id)
        if db_projekt is None:
            abweichungen.append(
                f'{datei_projekt.project_id}: fehlt in agora.projects'
            )
            continue

        aus_datei = datei_projekt.to_dict()
        aus_db = db_projekt.to_dict()
        for feld in sorted(aus_datei):
            if aus_datei[feld] != aus_db.get(feld):
                abweichungen.append(
                    f'{datei_projekt.project_id}.{feld}: '
                    f'Datei={aus_datei[feld]!r} DB={aus_db.get(feld)!r}'
                )
    return abweichungen


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--projects-dir',
        type=Path,
        default=None,
        help='abweichendes Projektverzeichnis (Standard: <UPLOAD_FOLDER>/projects)',
    )
    parser.add_argument('--dry-run', action='store_true', help='nur zählen')
    parser.add_argument(
        '--verify',
        action='store_true',
        help='beide Seiten feldweise vergleichen, nichts schreiben',
    )
    args = parser.parse_args(argv)

    root = args.projects_dir or projects_dir()

    if args.verify:
        abweichungen = verify(root)
        if not abweichungen:
            sys.stdout.write('OK: Datei und agora.projects stimmen feldweise überein\n')
            return 0
        for zeile in abweichungen:
            sys.stdout.write(f'ABWEICHUNG: {zeile}\n')
        return 1

    zaehler = migrate(root, dry_run=args.dry_run)
    vorsatz = 'DRY-RUN: ' if args.dry_run else ''
    sys.stdout.write(
        f'{vorsatz}{zaehler["gefunden"]} Projekte gefunden, '
        f'{zaehler["uebertragen"]} übertragen, '
        f'{zaehler["uebersprungen"]} übersprungen (bereits vorhanden)\n'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
