"""Fernet-verschlüsselte JSON-Persistenz für API-Schlüssel (PR 4 Hardening).

Storage-Layout (``backend/data/api_keys.json`` — verschlüsselt):

    <fernet-base64-ciphertext>

Der gesamte JSON-Blob (``{key_id: {label, scopes, ...}}``) wird als eine
Fernet-Einheit verschlüsselt — kein einzelnes Feld ist im Klartext lesbar.

Master-Key:
    ``AGORA_FERNET_KEY`` (Pflicht in Prod). Ungesetzt:
    - Debug-Modus (``FLASK_DEBUG=true``): Auto-generieren + ``logger.warning``.
    - Prod-Modus: ``RuntimeError("AGORA_FERNET_KEY missing in non-debug mode")``.

Security:
    - Dateirechte 0o600 nach jedem Write.
    - Atomarer Write via tmp-File + ``os.replace`` (wie llm_provider_secrets_store).
    - ``fcntl.flock`` für Multi-Worker-Schutz (POSIX-only). Auf Windows fällt
      das Locking weg — mit ``gunicorn --workers 1`` (PR 1 Hardstop) gibt es
      nur einen Writer-Prozess, daher kein Korruptionsrisiko. Sobald Multi-
      Worker auf Windows angestrebt wird, sollte ``portalocker`` (cross-
      platform) eingeführt werden. Gemini-Review zu PR #524.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

from ..utils.logger import get_logger
from .data_dir import resolve_data_dir as _resolve_data_dir

try:  # POSIX-only — auf Windows nicht verfügbar
    import fcntl as _fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Plattform-spezifisch
    _fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False

logger = get_logger("agora.services.api_keys_persistence")

_FERNET_KEY_ENV = "AGORA_FERNET_KEY"
_STORE_FILENAME = "api_keys.json"

# Lazy-cached Fernet-Instanz (verändert sich mit Env-Wechsel in Tests)
_fernet_instance: Optional[Fernet] = None
_fernet_key_raw: Optional[str] = None


def _load_fernet() -> Fernet:
    global _fernet_instance, _fernet_key_raw

    current_raw = os.environ.get(_FERNET_KEY_ENV)

    # Cache-Invalidierung bei Env-Änderung (relevant für Tests)
    if _fernet_instance is not None and _fernet_key_raw == current_raw:
        return _fernet_instance

    if not current_raw:
        debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1")
        if debug_mode:
            generated = Fernet.generate_key().decode("utf-8")
            logger.warning(
                "AGORA_FERNET_KEY ist nicht gesetzt. Im Debug-Modus wird ein "
                "temporärer Schlüssel generiert — API-Keys sind nach Neustart NICHT "
                "entschlüsselbar. Für persistente Schlüssel AGORA_FERNET_KEY setzen."
            )
            _fernet_instance = Fernet(generated.encode("utf-8"))
            _fernet_key_raw = None  # Nicht cachen — jeder Start generiert neu
            return _fernet_instance
        raise RuntimeError(
            "AGORA_FERNET_KEY missing in non-debug mode. "
            "Erzeugen mit:\n"
            "  python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'\n"
            "Dann in der Umgebung exportieren (AGORA_FERNET_KEY=…)."
        )

    try:
        instance = Fernet(current_raw.encode("utf-8"))
        _fernet_instance = instance
        _fernet_key_raw = current_raw
        return instance
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"AGORA_FERNET_KEY ist kein gültiger Fernet-Key: {exc}"
        ) from exc


def load(*, data_dir: Optional[Path] = None) -> dict:
    """Lädt und entschlüsselt den API-Keys-Store.

    Returns:
        ``{key_id: dict}`` — Plain-Dict-Repräsentation der ApiKeyModel-Felder.
        Leeres Dict wenn Datei nicht existiert.

    Raises:
        RuntimeError: Crypto-Konfigurationsfehler (z. B. fehlender
            ``AGORA_FERNET_KEY`` in Prod). Caller soll das BEIM BOOT
            sichtbar machen — niemals schlucken.
        Andere Exceptions (``InvalidToken``, ``json.JSONDecodeError``,
        ``OSError``): Daten-/IO-Fehler. Caller darf in diesem Fall mit
        leerem Store starten, soll aber Warning loggen.
    """
    resolved = data_dir or _resolve_data_dir()
    path = resolved / _STORE_FILENAME

    if not path.exists():
        return {}

    # _load_fernet() raised RuntimeError bei Config-Problemen — bewusst
    # NICHT abfangen, damit Caller (`ApiKeysStore._load_from_disk`)
    # zwischen Config-Fehler (re-raise) und Daten-Fehler (leer-Start)
    # differenzieren kann (Gemini-Review zu PR #524).
    fernet = _load_fernet()

    ciphertext = path.read_bytes().strip()
    if not ciphertext:
        return {}
    plaintext = fernet.decrypt(ciphertext).decode("utf-8")
    return json.loads(plaintext)


def save(records: dict, *, data_dir: Optional[Path] = None) -> None:
    """Verschlüsselt und schreibt den API-Keys-Store atomar mit 0o600.

    Args:
        records: ``{key_id: dict}`` — Plain-Dict der ApiKeyModel-Felder.
        data_dir: Override für Tests; Default aus ``AGORA_DATA_DIR`` / ``backend/data``.
    """
    resolved = data_dir or _resolve_data_dir()
    resolved.mkdir(parents=True, exist_ok=True)

    path = resolved / _STORE_FILENAME
    plaintext = json.dumps(records, indent=2, sort_keys=True, default=str).encode("utf-8")
    fernet = _load_fernet()
    ciphertext = fernet.encrypt(plaintext)

    if _HAS_FCNTL and _fcntl is not None:
        lock_path = path.with_suffix(".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fh:
            _fcntl.flock(lock_fh, _fcntl.LOCK_EX)
            try:
                _atomic_write(path, ciphertext)
            finally:
                _fcntl.flock(lock_fh, _fcntl.LOCK_UN)
    else:
        # Windows / no fcntl: relies on PR-1 --workers 1 Hardstop, no
        # cross-process locking. Atomic os.replace is portable.
        _atomic_write(path, ciphertext)


def _atomic_write(path: Path, ciphertext: bytes) -> None:
    tmp_path = path.with_suffix(".tmp")
    fd = os.open(
        str(tmp_path),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        os.write(fd, ciphertext)
    finally:
        os.close(fd)
    os.replace(tmp_path, path)
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        logger.warning(
            "Konnte Rechte auf %s nicht auf 0600 setzen: %s", path, exc
        )
