"""Erzeugt das PostgreSQL-Backup-Manifest einzeln (Issue #1583).

Der Backup-Pfad von ``scripts/restore-drill.sh`` braucht dieses Skript nicht:
``pg_cli dump --manifest`` erhebt das Manifest unter demselben Snapshot wie
den Dump. Dieses Skript ist für einen manuellen Nachtrag gedacht und nutzt
dieselbe Logik (``app/infrastructure/postgres/backup_manifest.py``) — ohne
Snapshot-Garantie.

Aufruf (aus ``backend/``; ``DATABASE_URL`` aus Umgebung oder ``.env``)::

    uv run python scripts/postgres_backup_manifest.py --output /pfad/postgres-manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Config  # noqa: E402
from app.infrastructure.postgres.backup_manifest import build_manifest  # noqa: E402
from app.utils.logger import get_logger  # noqa: E402

logger = get_logger('agora.backup.manifest')

__all__ = ['build_manifest', 'main']


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--output', type=Path, required=True, help='Zielpfad für postgres-manifest.json'
    )
    args = parser.parse_args(argv)

    if not (Config.DATABASE_URL or '').strip():
        logger.error('DATABASE_URL is not set')
        return 1

    manifest = build_manifest(Config.DATABASE_URL)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    logger.info('Postgres-Manifest geschrieben: %s', args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
