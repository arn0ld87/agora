#!/usr/bin/env python3
"""LLM Provider Secrets Doctor — Issue #450 P1.4.

Operatives CLI für den Multi-Provider-Hub-Secret-Store
(``backend/data/llm_provider_secrets.json``). Drei Subcommands:

* ``status`` — verifiziert ``AGORA_SECRET_KEY`` und listet die maskierten
  Provider-Einträge.
* ``verify`` — entschlüsselt jeden Eintrag einmal als Roundtrip-Test
  (Klartext landet nicht in stdout).
* ``rotate`` — re-encryptet alle Einträge mit einem neuen Fernet-Key. Der
  alte Key wird über ``--old-key-env`` gelesen, der neue über
  ``--new-key-env``. Niemals Keys als CLI-Argument übergeben.

Aufruf
======

Das Script importiert ``app.services.llm_provider_secrets_store`` und nutzt
deshalb das Backend-venv. Standard-Aufruf:

    cd <repo-root>
    uv run --project backend python scripts/llm-secrets-doctor.py status

Im Container (gunicorn-image):

    docker compose exec -T agora python /app/backend/../scripts/llm-secrets-doctor.py status

Pfade:

* Store-Verzeichnis ist standardmäßig ``backend/data/`` relativ zum
  Repo-Root; via ``AGORA_DATA_DIR`` oder ``--data-dir`` überschreibbar.

Beispiele:

    AGORA_SECRET_KEY=$(python -c \\
        'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())') \\
        uv run --project backend python scripts/llm-secrets-doctor.py status

    AGORA_SECRET_KEY=$OLD_KEY NEW_AGORA_SECRET_KEY=$NEW_KEY \\
        uv run --project backend python scripts/llm-secrets-doctor.py rotate \\
            --old-key-env AGORA_SECRET_KEY \\
            --new-key-env NEW_AGORA_SECRET_KEY

Exit-Codes:

* 0 — alles ok
* 1 — Konfigurationsfehler (Key fehlt, ist invalid)
* 2 — Roundtrip schlägt für mindestens einen Eintrag fehl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

# Repo-Root auflösen, damit ``backend/`` im sys.path landet.
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_PATH = REPO_ROOT / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from cryptography.fernet import Fernet, InvalidToken  # noqa: E402

from app.services.llm_provider_secrets_store import (  # noqa: E402
    LlmProviderSecretsStore,
)


def _fail(msg: str, code: int = 1) -> "int":
    print(f"[doctor] FEHLER: {msg}", file=sys.stderr)
    return code


def _resolve_data_dir(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    raw = os.environ.get("AGORA_DATA_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return BACKEND_PATH / "data"


def _ensure_valid_fernet(env_name: str) -> Fernet:
    raw = os.environ.get(env_name)
    if not raw:
        raise RuntimeError(
            f"{env_name} ist nicht gesetzt. "
            "Erzeuge einen Key mit:\n  "
            "python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'"
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"{env_name} ist kein gültiger Fernet-Key (URL-safe base64, 32 Bytes): {exc}"
        ) from exc


def cmd_status(args: argparse.Namespace) -> int:
    data_dir = _resolve_data_dir(args.data_dir)
    print(f"[doctor] Store-Verzeichnis: {data_dir}")
    try:
        _ensure_valid_fernet("AGORA_SECRET_KEY")
    except RuntimeError as exc:
        return _fail(str(exc))

    store_path = data_dir / "llm_provider_secrets.json"
    if not store_path.exists():
        print("[doctor] Kein Store-File vorhanden — Setup noch nicht durchgeführt.")
        return 0

    store = LlmProviderSecretsStore(data_dir=data_dir)
    entries = store.list_entries()
    print(f"[doctor] {len(entries)} Provider-Eintrag/e:")
    for entry in entries:
        last_ok = entry.last_validation_ok
        status_str = "ok" if last_ok else ("fehlgeschlagen" if last_ok is False else "ungeprüft")
        print(
            f"  - {entry.provider_id:<14} "
            f"masked={entry.masked_value:<14} "
            f"updated={entry.updated_at.isoformat()} "
            f"validation={status_str}"
        )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    data_dir = _resolve_data_dir(args.data_dir)
    try:
        _ensure_valid_fernet("AGORA_SECRET_KEY")
    except RuntimeError as exc:
        return _fail(str(exc))

    store_path = data_dir / "llm_provider_secrets.json"
    if not store_path.exists():
        print("[doctor] Kein Store-File vorhanden — nichts zu verifizieren.")
        return 0

    store = LlmProviderSecretsStore(data_dir=data_dir)
    entries = store.list_entries()
    failures: list[tuple[str, str]] = []
    for entry in entries:
        try:
            plaintext = store.get_plaintext(entry.provider_id)
            if plaintext is None or len(plaintext) < 4:
                failures.append((entry.provider_id, "leeres Plaintext nach Decrypt"))
                continue
            print(f"  - {entry.provider_id:<14} decrypt-roundtrip ok")
        except RuntimeError as exc:
            failures.append((entry.provider_id, str(exc)))

    if failures:
        print("[doctor] Fehlgeschlagene Provider:", file=sys.stderr)
        for pid, reason in failures:
            print(f"  - {pid}: {reason}", file=sys.stderr)
        return 2
    print(f"[doctor] {len(entries)} Einträge erfolgreich verifiziert.")
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    import fcntl  # POSIX-only; passt zum Rest des Stacks

    data_dir = _resolve_data_dir(args.data_dir)
    old_env = args.old_key_env
    new_env = args.new_key_env
    try:
        old_fernet = _ensure_valid_fernet(old_env)
        new_fernet = _ensure_valid_fernet(new_env)
    except RuntimeError as exc:
        return _fail(str(exc))

    store_path = data_dir / "llm_provider_secrets.json"
    lock_path = store_path.with_suffix(".lock")
    if not store_path.exists():
        print("[doctor] Kein Store-File vorhanden — nichts zu rotieren.")
        return 0

    # Race-Schutz (Copilot finding #3): Wir halten denselben fcntl.LOCK_EX
    # auf der Lock-Sidecar-Datei, den auch ``LlmProviderSecretsStore._write_raw``
    # verwendet, über die gesamte read-decrypt-re-encrypt-write-Sequenz. Sonst
    # könnte ein parallel laufender Gunicorn-Worker zwischen unserem Read und
    # Write einen ``upsert`` durchführen und seine Änderung würde von der
    # Rotation überschrieben.
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            try:
                raw = json.loads(store_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return _fail(f"Store-File ist nicht lesbar: {exc}")

            entries = raw.get("entries", {})
            rotated = 0
            failures: list[tuple[str, str]] = []
            for provider_id, payload in entries.items():
                ciphertext = payload.get("ciphertext")
                if not ciphertext:
                    continue
                try:
                    plaintext = old_fernet.decrypt(
                        ciphertext.encode("utf-8")
                    ).decode("utf-8")
                except InvalidToken as exc:
                    failures.append((provider_id, f"old-key passt nicht: {exc}"))
                    continue
                new_ciphertext = (
                    new_fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
                )
                payload["ciphertext"] = new_ciphertext
                rotated += 1
                # Klartext nicht länger im Memory halten als nötig
                del plaintext

            if failures:
                print(
                    "[doctor] Rotation abgebrochen — die folgenden Einträge konnten mit "
                    f"dem alten Key (${old_env}) nicht entschlüsselt werden:",
                    file=sys.stderr,
                )
                for pid, reason in failures:
                    print(f"  - {pid}: {reason}", file=sys.stderr)
                return 2

            # Im selben Lock atomic schreiben. Wir bauen den Tmp-File mit
            # 0600 direkt via os.open auf, analog zu _write_raw, und
            # rufen NICHT store._write_raw — der würde sonst doppelt
            # locken (gleicher Lock-Pfad, gleicher Prozess: das wäre für
            # fcntl re-entrant, aber wir vermeiden die Konstruktion
            # bewusst, damit die Semantik einfach bleibt).
            raw["version"] = 1
            tmp_path = store_path.with_suffix(".tmp")
            serialized = json.dumps(raw, indent=2, sort_keys=True).encode("utf-8")
            fd = os.open(
                str(tmp_path),
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600,
            )
            try:
                os.write(fd, serialized)
            finally:
                os.close(fd)
            os.replace(tmp_path, store_path)
            try:
                os.chmod(store_path, 0o600)
            except OSError:
                pass  # Volume-Mount-Edge-Case (s. _write_raw)

            print(
                f"[doctor] {rotated} Einträge erfolgreich re-encrypted. "
                f"Persistiere AGORA_SECRET_KEY=${new_env} in der produktiven .env."
            )
            return 0
        finally:
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="llm-secrets-doctor",
        description=(
            "Wartung des Multi-Provider-Hub-Secret-Stores "
            "(backend/data/llm_provider_secrets.json)."
        ),
    )
    # Damit ``--data-dir`` sowohl vor als auch nach dem Subcommand erlaubt ist,
    # registrieren wir es in jedem Subparser (statt im Main-Parser).
    common_data_dir = argparse.ArgumentParser(add_help=False)
    common_data_dir.add_argument(
        "--data-dir",
        help="Override für backend/data (Standard: $AGORA_DATA_DIR oder backend/data)",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "status",
        parents=[common_data_dir],
        help="AGORA_SECRET_KEY prüfen + Einträge listen",
    )
    sub.add_parser(
        "verify",
        parents=[common_data_dir],
        help="Decrypt-Roundtrip für jeden Eintrag",
    )
    rotate = sub.add_parser(
        "rotate",
        parents=[common_data_dir],
        help="Re-encrypten mit neuem Key",
    )
    rotate.add_argument(
        "--old-key-env",
        default="AGORA_SECRET_KEY",
        help="Env-Var-Name mit dem aktuellen Fernet-Key (default: AGORA_SECRET_KEY)",
    )
    rotate.add_argument(
        "--new-key-env",
        default="NEW_AGORA_SECRET_KEY",
        help="Env-Var-Name mit dem neuen Fernet-Key (default: NEW_AGORA_SECRET_KEY)",
    )

    args = parser.parse_args(argv)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "rotate":
        return cmd_rotate(args)
    return _fail(f"Unbekanntes Kommando: {args.cmd!r}")


if __name__ == "__main__":
    raise SystemExit(main())
