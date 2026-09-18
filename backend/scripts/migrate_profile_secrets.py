"""Überträgt LLM-Profil-Schlüssel aus der SQLite in den verschlüsselten Store.

Warum das existiert
-------------------
``instance/llm_profiles.db`` hält den ``api_key`` im Klartext. Das Ziel-Modell
in PostgreSQL hat diese Spalte nicht (``docs/plans/supabase.md`` §10), also
braucht der PostgreSQL-Adapter aus PR 4 die Schlüssel woanders — im
Fernet-Store ``llm_profile_secrets.json``. Dieses Skript füllt ihn.

Was es NICHT tut
----------------
Es ändert die SQLite nicht. Kein Schlüssel wird dort gelöscht, keine Spalte
angefasst, kein Profil verändert. Solange ``AGORA_LLM_PROFILE_BACKEND=sqlite``
gilt, bleibt sie die Wahrheit, und dieses Skript legt nur eine zweite Kopie an
— erst PR 4 macht den Store zur Quelle.

Es ist idempotent: ein erneuter Lauf schreibt denselben Klartext erneut
verschlüsselt (Fernet erzeugt dabei ein anderes Ciphertext, das ist kein
Unterschied im Inhalt) und meldet, was er vorgefunden hat.

Aufruf::

    uv run python scripts/migrate_profile_secrets.py --dry-run
    uv run python scripts/migrate_profile_secrets.py
    uv run python scripts/migrate_profile_secrets.py --verify
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.llm_profile_secrets_store import (  # noqa: E402
    LlmProfileSecretsStore,
    ProfileSecretDecryptionError,
)


def _read_sqlite_keys(db_path: Path) -> List[Tuple[str, str]]:
    """``(profile_id, api_key)`` für jedes Profil mit nicht-leerem Schlüssel.

    Liest ausschliesslich; die Verbindung ist hart auf ``mode=ro`` gesetzt,
    damit ein Tippfehler im Pfad keine Datei anlegt und ein Fehler im Skript
    nichts schreiben kann.
    """
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, api_key FROM llm_profiles").fetchall()
    finally:
        conn.close()
    return [(str(r["id"]), r["api_key"]) for r in rows if r["api_key"]]


def migrate(
    db_path: Path, store: LlmProfileSecretsStore, *, dry_run: bool = False
) -> Tuple[int, int]:
    """Überträgt die Schlüssel. Gibt ``(uebertragen, uebersprungen)`` zurück."""
    pairs = _read_sqlite_keys(db_path)
    written = 0
    for profile_id, plaintext in pairs:
        if dry_run:
            written += 1
            continue
        store.set(profile_id, plaintext)
        written += 1
    return written, 0


def verify(db_path: Path, store: LlmProfileSecretsStore) -> List[str]:
    """Vergleicht beide Seiten feldweise. Leere Liste heisst: deckungsgleich.

    Der Vergleich entschlüsselt und stellt den Klartext gegenüber — eine
    Prüfung auf blosse Existenz würde einen Eintrag durchgehen lassen, der
    unter der falschen Profil-ID liegt oder aus einem früheren Lauf mit einem
    anderen Wert stammt.
    """
    findings: List[str] = []
    pairs = dict(_read_sqlite_keys(db_path))
    for profile_id, expected in pairs.items():
        try:
            actual = store.get_plaintext(profile_id)
        except ProfileSecretDecryptionError as exc:
            findings.append(f"{profile_id}: {exc}")
            continue
        if actual is None:
            findings.append(f"{profile_id}: in der SQLite vorhanden, im Store nicht")
        elif actual != expected:
            findings.append(f"{profile_id}: Klartext weicht ab")
    for profile_id in store.list_profile_ids():
        if profile_id not in pairs:
            # Kein Fehler, aber benennenswert: ein Profil wurde geloescht oder
            # sein Schluessel entfernt, der Store traegt ihn noch.
            findings.append(f"{profile_id}: im Store, in der SQLite nicht (verwaist)")
    return findings


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--db",
        type=Path,
        default=BACKEND_DIR / "instance" / "llm_profiles.db",
        help="Pfad zur llm_profiles.db (Vorgabe: backend/instance/llm_profiles.db)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Zielverzeichnis des Secret-Stores (Vorgabe: AGORA_DATA_DIR)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="nur zählen, nichts schreiben"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="beide Seiten vergleichen, statt zu übertragen",
    )
    args = parser.parse_args(argv)

    store = LlmProfileSecretsStore(data_dir=args.data_dir)

    if args.verify:
        findings = verify(args.db, store)
        if not findings:
            print("Deckungsgleich: jeder Schlüssel aus der SQLite liegt im Store.")
            return 0
        print(f"{len(findings)} Abweichung(en):")
        for line in findings:
            print(f"  - {line}")
        return 1

    written, _ = migrate(args.db, store, dry_run=args.dry_run)
    verb = "würden übertragen" if args.dry_run else "übertragen"
    print(f"{written} Schlüssel {verb}. Die SQLite bleibt unverändert.")
    if not args.dry_run and written:
        print("Gegenprüfung: scripts/migrate_profile_secrets.py --verify")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
