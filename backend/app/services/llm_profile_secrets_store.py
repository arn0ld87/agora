"""Fernet-verschlüsselter Store für API-Keys **pro LLM-Profil**.

Warum es diesen Store zusätzlich gibt
-------------------------------------
Der Schlüssel eines LLM-Profils liegt heute im Klartext in einer Spalte von
``instance/llm_profiles.db``. Das Ziel-Datenmodell in PostgreSQL
(``agora.llm_profiles``) hat diese Spalte bewusst nicht: Provider-Secrets
gehören in den verschlüsselten Store, nicht in eine Tabelle, die PostgREST
prinzipiell exponieren kann (``docs/plans/supabase.md`` §10).

Der bestehende ``LlmProviderSecretsStore`` kann die Lücke nicht füllen, weil er
**pro Provider** ablegt (``get_plaintext("openai")``). Profile sind feiner
geschnitten: es gibt keinen Unique-Constraint auf ``provider``, zwei Profile
desselben Providers dürfen verschiedene Schlüssel tragen, und der
Laufzeit-Resolver zieht den Schlüssel pro Profil. Würde der PostgreSQL-Adapter
auf den Provider-Store zurückfallen, teilten sich diese Profile stillschweigend
einen Schlüssel — ein Verhaltenswechsel, der erst auffiele, wenn das
Feature-Flag längst umgelegt ist.

Storage-Layout (``<AGORA_DATA_DIR>/llm_profile_secrets.json``)::

    {
      "version": 1,
      "entries": {
        "<profile_id>": {
          "ciphertext": "<fernet-base64>",
          "created_at": "2026-...",
          "updated_at": "2026-..."
        }
      }
    }

Master-Key ist ``AGORA_SECRET_KEY``, derselbe wie beim Provider-Store: ein
zweiter Master-Key wäre eine zweite Sache, die bei einer Rotation vergessen
werden kann.

Was dieser Store nicht tut
--------------------------
Er gibt keine maskierte Darstellung aus. Der Provider-Store hat eine, weil sein
Bestand in der Oberfläche auftaucht; ein Profil-Schlüssel tut das nie — die
API gibt ihn grundsätzlich nicht heraus. Eine Maskierung wäre eine Repräsentation,
die niemand anzeigt und die trotzdem aus dem Klartext abgeleitet werden müsste.

Er ist auch noch an keinen Lesepfad angeschlossen. SQLite bleibt die Wahrheit,
bis PR 4 den PostgreSQL-Adapter bringt; dieser Store ist die Ablage, die dieser
Adapter dann vorfindet.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator, Optional

from cryptography.fernet import Fernet, InvalidToken

from ..utils.logger import get_logger
from .data_dir import resolve_data_dir as _resolve_data_dir

logger = get_logger("agora.services.llm_profile_secrets_store")

_SECRET_KEY_ENV = "AGORA_SECRET_KEY"  # noqa: S105 - Name der Env-Variable, kein Secret
_STORE_FILENAME = "llm_profile_secrets.json"


class ProfileSecretDecryptionError(RuntimeError):
    """Ein Eintrag ließ sich mit dem aktuellen Master-Key nicht entschlüsseln.

    Eigene Klasse statt eines allgemeinen Fehlers, weil der Aufrufer die beiden
    Fälle unterscheiden muss: „es gibt keinen Schlüssel" ist normal und wird mit
    ``None`` beantwortet, „es gibt einen, aber der Master-Key passt nicht" ist
    ein Betriebsfehler und darf nicht als „kein Schlüssel" durchgehen.
    """


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_fernet() -> Fernet:
    raw = os.environ.get(_SECRET_KEY_ENV)
    if not raw:
        raise RuntimeError(
            f"{_SECRET_KEY_ENV} ist nicht gesetzt. Erzeugen mit:\n"
            "  python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'\n"
            f"Anschließend in der Umgebung exportieren ({_SECRET_KEY_ENV}=…)."
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"{_SECRET_KEY_ENV} ist kein gültiger Fernet-Key: {exc}"
        ) from exc


class LlmProfileSecretsStore:
    """Dateibasierter, Fernet-verschlüsselter Schlüsselspeicher je Profil-ID.

    Thread-safe über einen internen Lock, prozessübergreifend über ``flock`` —
    dieselbe Begründung wie beim Provider-Store: ``threading.Lock`` schützt nur
    innerhalb eines Prozesses, und auch bei einem Gunicorn-Worker greifen
    Wartungsskripte nebenher auf dieselbe Datei zu.

    Klartext wird nie zwischengespeichert: jeder ``get_plaintext``-Aufruf macht
    einen Decrypt-Roundtrip.
    """

    def __init__(self, *, data_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or _resolve_data_dir()
        self._path = self._data_dir / _STORE_FILENAME
        self._fernet_instance: Optional[Fernet] = None
        self._fernet_key_raw: Optional[str] = None

    def _fernet(self) -> Fernet:
        """Lazy gecachte Fernet-Instanz, invalidiert bei Key-Wechsel."""
        current_key_raw = os.environ.get(_SECRET_KEY_ENV)
        if self._fernet_instance is None or self._fernet_key_raw != current_key_raw:
            self._fernet_instance = _load_fernet()
            self._fernet_key_raw = current_key_raw
        return self._fernet_instance

    def _read_raw(self) -> dict:
        if not self._path.exists():
            return {"version": 1, "entries": {}}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Konnte Profil-Secret-Store nicht lesen ({self._path}): {exc}"
            ) from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("entries"), dict):
            raise RuntimeError(
                f"Konnte Profil-Secret-Store nicht lesen ({self._path}): "
                "erwartet ein Objekt mit einem 'entries'-Objekt"
            )
        return raw

    @contextmanager
    def _file_lock(self) -> Iterator[IO[str]]:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self._path.with_suffix(".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield lock_fh
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def _write_raw(self, raw: dict) -> None:
        """Atomisch schreiben, 0600 schon beim Anlegen der Temp-Datei.

        Erst schreiben und danach chmod-en hieße, dass der Ciphertext zwischen
        Write und ``os.replace`` mit dem Umask-Default herumliegt.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(raw, indent=2, sort_keys=True).encode("utf-8")
        tmp_path = self._path.with_suffix(".tmp")
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise OSError(
                        "Konnte vollständigen Profil-Secret-Payload nicht schreiben"
                    )
                offset += written
        finally:
            os.close(fd)
        os.replace(tmp_path, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError as exc:
            # Auf manchen NFS-/Volume-Mounts ist chmod nicht erlaubt. Das ist
            # kein Grund, den Schreibvorgang scheitern zu lassen — die
            # Temp-Datei wurde bereits mit 0600 angelegt.
            logger.warning(
                "Konnte Rechte auf %s nicht auf 0600 setzen: %s", self._path, exc
            )

    # -- öffentliche Schnittstelle ------------------------------------------

    def get_plaintext(self, profile_id: str) -> Optional[str]:
        """Der Schlüssel des Profils, oder ``None`` wenn keiner hinterlegt ist.

        Wirft ``ProfileSecretDecryptionError``, wenn ein Eintrag existiert, sich
        aber nicht entschlüsseln lässt — dieser Fall darf nicht als „kein
        Schlüssel" durchgehen, sonst läuft ein Profil nach einer Key-Rotation
        stillschweigend ohne Authentifizierung weiter.
        """
        with self._lock:
            entry = self._read_raw()["entries"].get(profile_id)
        if not entry:
            return None
        ciphertext = entry.get("ciphertext")
        if not ciphertext:
            return None
        try:
            return self._fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ProfileSecretDecryptionError(
                f"Schlüssel für Profil {profile_id} ist mit dem aktuellen "
                f"{_SECRET_KEY_ENV} nicht entschlüsselbar"
            ) from exc

    def set(self, profile_id: str, plaintext: str) -> None:
        """Legt den Schlüssel ab. Ein leerer Wert **löscht** den Eintrag.

        Dieselbe Bedeutung, die ein leerer ``api_key`` im SQLite-Store hat: kein
        Schlüssel. Ein verschlüsselter leerer String wäre ein Eintrag, der
        vorgibt, einen Schlüssel zu haben.
        """
        if not plaintext:
            self.delete(profile_id)
            return
        token = self._fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")
        now = _now().isoformat()
        with self._lock, self._file_lock():
            raw = self._read_raw()
            existing = raw["entries"].get(profile_id) or {}
            raw["entries"][profile_id] = {
                "ciphertext": token,
                "created_at": existing.get("created_at") or now,
                "updated_at": now,
            }
            self._write_raw(raw)

    def delete(self, profile_id: str) -> bool:
        """``True``, wenn ein Eintrag entfernt wurde."""
        with self._lock, self._file_lock():
            raw = self._read_raw()
            if profile_id not in raw["entries"]:
                return False
            del raw["entries"][profile_id]
            self._write_raw(raw)
            return True

    def has(self, profile_id: str) -> bool:
        """Ob ein Eintrag existiert — ohne ihn zu entschlüsseln.

        Nützlich für Bestandsprüfungen nach einer Migration, die keinen
        Master-Key zur Hand haben müssen.
        """
        with self._lock:
            return bool(self._read_raw()["entries"].get(profile_id))

    def list_profile_ids(self) -> list[str]:
        """Alle Profil-IDs mit hinterlegtem Schlüssel, sortiert."""
        with self._lock:
            return sorted(self._read_raw()["entries"])


_store_singleton: Optional[LlmProfileSecretsStore] = None


def get_llm_profile_secrets_store() -> LlmProfileSecretsStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = LlmProfileSecretsStore()
    return _store_singleton


def reset_singleton_for_tests() -> None:
    global _store_singleton
    _store_singleton = None
