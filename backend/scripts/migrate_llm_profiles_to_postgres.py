"""Überträgt LLM-Profile aus der SQLite nach PostgreSQL (§10, PR 4, Schritt 3–6).

Was übertragen wird
-------------------
Die Metadaten nach ``agora.llm_profiles``, die Schlüssel in den Fernet-Store
``llm_profile_secrets.json``. Zwei Ziele, weil das Datenmodell bewusst keine
``api_key``-Spalte hat.

**IDs und Zeitstempel bleiben unverändert.** Die SQLite-ID ist ein
``uuid4().hex`` (32 Zeichen), die Spalte in PostgreSQL ist ``UUID`` — dieselbe
Zahl, andere Schreibweise. Der Adapter gibt sie wieder als ``.hex`` aus, sodass
gespeicherte Referenzen wie ``llm_model: "profile:<id>"`` weiter zeigen, wohin
sie zeigen sollen. ``created_at`` und ``updated_at`` werden übernommen, nicht
neu gesetzt: eine Migration, die alles auf „heute" stellt, verliert genau die
Information, mit der sich später nachvollziehen lässt, was wann entstand.

Was NICHT passiert
------------------
Die SQLite wird nicht verändert und nicht gelöscht (§10 Schritt 9). Sie bleibt
die Wahrheit, bis jemand ``AGORA_LLM_PROFILE_BACKEND=postgres`` setzt — und
selbst dann bleibt sie als Rückweg liegen.

Aufruf::

    uv run python scripts/migrate_llm_profiles_to_postgres.py --dry-run
    uv run python scripts/migrate_llm_profiles_to_postgres.py
    uv run python scripts/migrate_llm_profiles_to_postgres.py --verify

Voraussetzungen: ``DATABASE_URL``, ``AGORA_SECRET_KEY``, und ein
``alembic upgrade head`` gegen dieselbe Datenbank.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.infrastructure.postgres.models.llm_profile import LlmProfileModel  # noqa: E402
from app.infrastructure.postgres.session import get_database  # noqa: E402
from app.services.llm_profile_secrets_store import (  # noqa: E402
    LlmProfileSecretsStore,
    ProfileSecretDecryptionError,
)

#: Genau die Felder, die eine Migration unverändert lassen muss.
_COMPARED = ("name", "provider", "base_url", "model_name", "is_default")


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def read_sqlite_profiles(db_path: Path) -> List[Dict[str, Any]]:
    """Alle Profile aus der SQLite, read-only."""
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, provider, base_url, model_name, api_key, "
            "is_default, created_at, updated_at FROM llm_profiles"
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def migrate(
    db_path: Path, secrets: LlmProfileSecretsStore, *, dry_run: bool = False
) -> int:
    """Überträgt Profile und Schlüssel. Gibt die Anzahl zurück."""
    profiles = read_sqlite_profiles(db_path)
    if dry_run or not profiles:
        return len(profiles)

    database = get_database()
    with database.session() as session:
        for row in profiles:
            pid = uuid.UUID(row["id"])
            existing = session.get(LlmProfileModel, pid)
            values = {
                "name": row["name"],
                "provider": row["provider"],
                "base_url": row["base_url"],
                "model_name": row["model_name"],
                "is_default": bool(row["is_default"]),
                "created_at": _parse_ts(row["created_at"]),
                "updated_at": _parse_ts(row["updated_at"]),
            }
            if existing is None:
                session.add(LlmProfileModel(id=pid, **values))
            else:
                # Wiederholbar: ein zweiter Lauf aktualisiert statt zu brechen.
                for key, value in values.items():
                    setattr(existing, key, value)

    # Schlüssel erst nach dem Commit der Metadaten: ein Schlüssel ohne Zeile
    # wäre eine Leiche im Store.
    for row in profiles:
        if row["api_key"]:
            secrets.set(row["id"], row["api_key"])
    return len(profiles)


def verify(db_path: Path, secrets: LlmProfileSecretsStore) -> List[str]:
    """Feldweiser Vergleich beider Seiten. Leere Liste heisst: deckungsgleich."""
    findings: List[str] = []
    source = {row["id"]: row for row in read_sqlite_profiles(db_path)}

    database = get_database()
    with database.session() as session:
        target = {
            row.id.hex: row
            for row in session.scalars(select(LlmProfileModel)).all()
        }

        if len(source) != len(target):
            findings.append(f"Anzahl: {len(source)} in SQLite, {len(target)} in PostgreSQL")

        for pid, row in source.items():
            pg = target.get(pid)
            if pg is None:
                findings.append(f"{pid}: fehlt in PostgreSQL")
                continue
            for field in _COMPARED:
                expected = row[field]
                actual = getattr(pg, field)
                if field == "is_default":
                    expected, actual = bool(expected), bool(actual)
                if expected != actual:
                    findings.append(f"{pid}.{field}: {expected!r} -> {actual!r}")
            for field in ("created_at", "updated_at"):
                if _parse_ts(row[field]) != getattr(pg, field):
                    findings.append(
                        f"{pid}.{field}: {row[field]} -> {getattr(pg, field).isoformat()}"
                    )
            # Der Schlüssel gehört zum Datensatz, auch wenn er woanders liegt.
            try:
                stored = secrets.get_plaintext(pid)
            except ProfileSecretDecryptionError as exc:
                findings.append(f"{pid}.api_key: {exc}")
                continue
            expected_key = row["api_key"] or None
            if (stored or None) != expected_key:
                findings.append(f"{pid}.api_key: weicht ab oder fehlt im Secret-Store")

        for pid in target:
            if pid not in source:
                findings.append(f"{pid}: in PostgreSQL, in der SQLite nicht")

    return findings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--db",
        type=Path,
        default=BACKEND_DIR / "instance" / "llm_profiles.db",
        help="Pfad zur llm_profiles.db",
    )
    parser.add_argument(
        "--data-dir", type=Path, help="Zielverzeichnis des Secret-Stores"
    )
    parser.add_argument("--dry-run", action="store_true", help="nur zählen")
    parser.add_argument(
        "--verify", action="store_true", help="beide Seiten feldweise vergleichen"
    )
    args = parser.parse_args(argv)

    secrets = LlmProfileSecretsStore(data_dir=args.data_dir)

    if args.verify:
        findings = verify(args.db, secrets)
        if not findings:
            print(
                "Deckungsgleich: Anzahl, IDs, Felder, Zeitstempel und Schlüssel "
                "stimmen überein."
            )
            return 0
        print(f"{len(findings)} Abweichung(en):")
        for line in findings:
            print(f"  - {line}")
        return 1

    count = migrate(args.db, secrets, dry_run=args.dry_run)
    verb = "würden übertragen" if args.dry_run else "übertragen"
    print(f"{count} Profil(e) {verb}. Die SQLite bleibt unverändert.")
    if not args.dry_run and count:
        print(
            "Gegenprüfung: scripts/migrate_llm_profiles_to_postgres.py --verify\n"
            "Erst danach AGORA_LLM_PROFILE_BACKEND=postgres setzen."
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
