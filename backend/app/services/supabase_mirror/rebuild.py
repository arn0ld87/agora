"""Rebuild-CLI fuer den Supabase-Metadaten-Spiegel.

Aufruf (Backend-Venv):
  cd backend && uv run python -m app.services.supabase_mirror.rebuild
  cd backend && uv run python -m app.services.supabase_mirror.rebuild --check

Rekonstruiert den kompletten Index (schema ``agora``: runs, run_events,
report_index, documents) aus der Wahrheit (Dateisystem + ProjectManager).
Exit-Kriterium Phase 1: Der Rebuild ist der Beweis, dass Postgres nur
Spiegel ist — beliebige Loeschung der Mirror-Zeilen ist verlustfrei.

--check macht einen Dry-Run: Es wird nur gezaehlt, was gespiegelt wuerde
(kein Netzwerk-Write), um Wahrheit und Erreichbarkeit vor dem Write zu
pruefen.
"""
from __future__ import annotations

import argparse
import sys

from ...utils.logger import get_logger
from .client import SupabaseMirrorError
from .mirror import get_supabase_mirror

logger = get_logger("agora.supabase_mirror.rebuild")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild the Supabase metadata mirror from local truth.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Dry-Run: SUPABASE_ENABLED/Endpoint-Pruefung + Healthcheck, kein Write.",
    )
    args = parser.parse_args(argv)

    mirror = get_supabase_mirror()
    if not mirror.enabled:
        logger.error(
            "Supabase mirror is disabled (SUPABASE_ENABLED=false or "
            "SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY missing). Nothing to do."
        )
        return 1

    client = mirror._get_client()
    if not client.healthcheck():
        logger.error(
            "Supabase unreachable or schema not exposed at %r — fix "
            "connectivity/db-schemas before rebuilding (no writes attempted).",
            client._base_url,
        )
        return 1
    logger.info("Supabase reachable at %r.", client._base_url)

    if args.check:
        logger.info("Dry-run OK: enabled + reachable. No writes performed.")
        return 0

    try:
        counts = mirror.rebuild_index()
    except SupabaseMirrorError as exc:
        logger.error("Rebuild failed: %s", exc)
        return 1

    logger.info(
        "Rebuild complete: runs=%d, run_events=%d, reports=%d, documents=%d",
        counts["runs"],
        counts["run_events"],
        counts["reports"],
        counts["documents"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
