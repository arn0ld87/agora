"""Migrations-Skript: persistierte v1-Evidence-Maps auf schema_version=2 heben.

Aufruf (aus backend/):
    python -m scripts.migrate_reports_v1_to_v2 <pfad> [--dry-run] [--glob "*.json"]

``pfad`` kann eine einzelne Datei oder ein Verzeichnis sein.
Bei Verzeichnis: rekursiv mit dem angegebenen Glob-Pattern (Standard: ``*.json``).

Pro Datei:
- JSON laden (robust gegen kaputte Dateien).
- schema_version prüfen; falls bereits CURRENT_SCHEMA_VERSION: no-op.
- Falls v1 (oder kein Feld + v1-Heuristik): migrate_v1_to_v2() aufrufen.
- Migriertes Dict gegen EvidenceMapModel revalidieren.
- Backup <datei>.v1.bak.json anlegen (nur wenn noch nicht vorhanden, idempotent).
- Atomic write via <datei>.tmp + os.replace.

Exit-Code: 0 bei Erfolg (auch bei N=0), 1 bei mindestens einem Fehler.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import pathlib
import sys
from typing import Optional

from pydantic import ValidationError

from app.contracts import EvidenceMapModel
from app.services.evidence_migrations import CURRENT_SCHEMA_VERSION, migrate_v1_to_v2

logger = logging.getLogger("migrate_reports_v1_to_v2")

_STATUS_MIGRATED = "migrated"
_STATUS_SKIPPED = "skipped"
_STATUS_ERROR = "error"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _collect_files(path: pathlib.Path, glob_pattern: str) -> list[pathlib.Path]:
    """Einzeldatei oder rekursives Glob-Ergebnis."""
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob(glob_pattern))
    return []


def _is_v1_heuristic(payload: dict) -> bool:
    """Heuristik für Payloads ohne schema_version-Feld.

    Trifft zu, wenn report_id + simulation_id vorhanden sind —
    das sind die Pflichtfelder von EvidenceMapModel v1.
    """
    return "report_id" in payload and "simulation_id" in payload


def _strip_section_schema_version(payload: dict) -> None:
    """Entfernt schema_version aus Section-Dicts.

    migrate_v1_to_v2 setzt schema_version auf Section-Ebene zur internen
    Nachverfolgung, aber ReportSectionModel kennt dieses Feld nicht
    (extra='forbid'). Das kanonische schema_version ist nur auf
    EvidenceMapModel-Ebene.
    """
    for section in payload.get("sections") or []:
        if isinstance(section, dict):
            section.pop("schema_version", None)


def _process_file(
    file_path: pathlib.Path,
    dry_run: bool,
) -> tuple[str, Optional[str]]:
    """Verarbeitet eine einzelne JSON-Datei.

    Gibt (status, error_msg) zurück:
    - (_STATUS_MIGRATED, None)  — erfolgreich migriert (oder dry-run simuliert)
    - (_STATUS_SKIPPED, None)   — kein Handlungsbedarf
    - (_STATUS_ERROR, str)      — Fehler mit Beschreibung
    """
    # Laden
    try:
        raw_text = file_path.read_text(encoding="utf-8")
        payload = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        return _STATUS_ERROR, f"Laden fehlgeschlagen: {exc}"

    if not isinstance(payload, dict):
        return _STATUS_ERROR, "Kein JSON-Objekt (dict erwartet)"

    current_version = payload.get("schema_version")

    # Bereits aktuell
    if current_version == CURRENT_SCHEMA_VERSION:
        logger.debug(
            "%s: schema_version=%s — bereits aktuell",
            file_path,
            CURRENT_SCHEMA_VERSION,
        )
        return _STATUS_SKIPPED, None

    # Migrations-Kandidat bestimmen
    needs_migration = current_version == 1 or (
        current_version is None and _is_v1_heuristic(payload)
    )
    if not needs_migration:
        logger.info(
            "%s: schema_version=%r unbekannt, keine v1-Heuristik — übersprungen",
            file_path,
            current_version,
        )
        return _STATUS_SKIPPED, None

    logger.info(
        "%s: schema_version=%r → migriere auf v%s",
        file_path,
        current_version,
        CURRENT_SCHEMA_VERSION,
    )

    # Migration
    migrated = migrate_v1_to_v2(copy.deepcopy(payload))
    if migrated is None:
        return _STATUS_ERROR, "migrate_v1_to_v2 hat None zurückgegeben"

    _strip_section_schema_version(migrated)

    # Re-Validation gegen Pydantic-Contract
    try:
        EvidenceMapModel.model_validate(migrated)
    except ValidationError as exc:
        short = "; ".join(
            f"{e['loc']}: {e['msg']}"
            for e in exc.errors(include_url=False)[:3]
        )
        return _STATUS_ERROR, f"Validation nach Migration fehlgeschlagen: {short}"

    if dry_run:
        logger.info("%s: --dry-run aktiv — schreibe nichts", file_path)
        return _STATUS_MIGRATED, None

    # Backup (idempotent: nur beim ersten Lauf)
    backup_path = file_path.with_name(file_path.stem + ".v1.bak.json")
    if not backup_path.exists():
        try:
            backup_path.write_text(raw_text, encoding="utf-8")
            logger.info("%s: Backup → %s", file_path, backup_path.name)
        except OSError as exc:
            return _STATUS_ERROR, f"Backup-Schreiben fehlgeschlagen: {exc}"
    else:
        logger.debug(
            "%s: Backup %s existiert bereits — übersprungen",
            file_path,
            backup_path.name,
        )

    # Atomic write
    tmp_path = file_path.with_suffix(".tmp")
    try:
        migrated_text = json.dumps(migrated, ensure_ascii=False, indent=2)
        tmp_path.write_text(migrated_text, encoding="utf-8")
        os.replace(tmp_path, file_path)
    except OSError as exc:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return _STATUS_ERROR, f"Atomic-Write fehlgeschlagen: {exc}"

    logger.info("%s: erfolgreich auf v%s migriert", file_path, CURRENT_SCHEMA_VERSION)
    return _STATUS_MIGRATED, None


def _run(target: pathlib.Path, glob_pattern: str, dry_run: bool) -> int:
    """Kern-Loop: verarbeitet alle Dateien, gibt Exit-Code zurück."""
    files = _collect_files(target, glob_pattern)
    if not files:
        logger.info(
            "Keine Dateien gefunden unter %s mit Pattern '%s'",
            target,
            glob_pattern,
        )
        return 0

    migrated_count = 0
    skipped_count = 0
    error_count = 0

    for file_path in files:
        status, error_msg = _process_file(file_path, dry_run=dry_run)
        if status == _STATUS_MIGRATED:
            migrated_count += 1
        elif status == _STATUS_SKIPPED:
            skipped_count += 1
        else:
            logger.error("%s: %s", file_path, error_msg)
            error_count += 1

    logger.info(
        "Abgeschlossen — migrated=%d, skipped=%d, errors=%d",
        migrated_count,
        skipped_count,
        error_count,
    )
    return 1 if error_count > 0 else 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI-Einstiegspunkt — direkt aufrufbar ohne Subprozess.

    Parameters
    ----------
    argv:
        Argument-Liste (ohne Programmname). None = sys.argv[1:].

    Returns
    -------
    int
        Exit-Code: 0 = OK, 1 = mindestens ein Fehler.
    """
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="migrate_reports_v1_to_v2",
        description="Hebt gespeicherte v1-Reports auf schema_version=2.",
    )
    parser.add_argument(
        "path",
        type=pathlib.Path,
        help="Datei oder Verzeichnis (rekursiv).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Nur loggen, nichts schreiben (kein Backup, kein Atomic-Write).",
    )
    parser.add_argument(
        "--glob",
        default="*.json",
        metavar="PATTERN",
        help="Glob-Pattern für Verzeichnis-Suche (Standard: *.json).",
    )

    args = parser.parse_args(argv)
    target: pathlib.Path = args.path

    if not target.exists():
        logger.error("Pfad existiert nicht: %s", target)
        return 1

    return _run(target, args.glob, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
