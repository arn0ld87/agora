"""Persistenter JSON-Store für das lokale Single-User-Profil (Onboarding Slice 2).

Storage-Pfad: ``backend/data/user_profile.json`` (überschreibbar via
``AGORA_DATA_DIR``-Env), Avatare unter ``<data_dir>/avatars/``. Locking auf
zwei Ebenen — analog zu :mod:`app.services.workspace_routing_store`:

- ``threading.Lock`` schützt innerhalb eines Python-Prozesses.
- ``fcntl.flock`` auf einer ``.lock``-Sidecar-Datei schützt prozessübergreifend
  (mehrere Gunicorn-Worker). Read-modify-write-Operationen (``update``,
  ``set_avatar_ref``, ``clear_avatar_ref``) halten den File-Lock über den
  gesamten Roundtrip — sonst gehen parallele Updates verloren (Lost Update).

Atomic write über tmp-File + ``os.replace``; geschriebene Dateien bekommen
``0600`` (Profil enthält keine Secrets, aber Konsistenz mit den übrigen
Daten-Stores bleibt gewahrt).
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..contracts.user_profile_contract import UserProfile, UserProfileUpdateRequest
from ..utils.logger import get_logger
from .json_file_store import JsonFileStore

logger = get_logger("agora.services.user_profile_store")

_STORE_FILENAME = "user_profile.json"
_AVATAR_DIRNAME = "avatars"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserProfileStore(JsonFileStore):
    """File-backed JSON-Store für das lokale Benutzerprofil.

    Pfad, Prozess- und Dateisperre kommen aus ``JsonFileStore``.
    """

    def __init__(self, *, data_dir: Optional[Path] = None) -> None:
        super().__init__(_STORE_FILENAME, data_dir=data_dir)

    @property
    def avatar_dir(self) -> Path:
        directory = self._data_dir / _AVATAR_DIRNAME
        os.makedirs(directory, exist_ok=True)
        return directory

    def load(self) -> Optional[UserProfile]:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> Optional[UserProfile]:
        if not self._path.exists():
            return None
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning(
                "User-Profile-Store konnte nicht gelesen werden (%s): %s — "
                "behandle als 'kein Profil vorhanden'",
                self._path,
                exc,
            )
            return None
        except json.JSONDecodeError as exc:
            logger.warning(
                "User-Profile-Store ist korrupt (%s): %s — "
                "behandle als 'kein Profil vorhanden'. Bitte Datei manuell prüfen.",
                self._path,
                exc,
            )
            return None
        try:
            return UserProfile.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — defensiv, geloggt, kein Crash beim Boot
            logger.warning(
                "User-Profile-Store enthält ungültige Daten (%s): %s — "
                "behandle als 'kein Profil vorhanden'",
                self._path,
                exc,
            )
            return None

    def _save_unlocked(self, profile: UserProfile) -> UserProfile:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = profile.model_copy(update={"updated_at": _now()})
        serialized = json.dumps(
            payload.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode("utf-8")
        tmp_path = self._path.with_suffix(".tmp")

        def _opener(path: str, flags: int) -> int:
            return os.open(path, flags, 0o600)

        with open(tmp_path, "wb", opener=_opener) as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError as exc:
            logger.warning(
                "Konnte Rechte auf %s nicht auf 0600 setzen: %s",
                self._path,
                exc,
            )
        return payload

    def save(self, profile: UserProfile) -> UserProfile:
        with self._lock, self._file_lock():
            return self._save_unlocked(profile)

    def update(self, request: UserProfileUpdateRequest) -> UserProfile:
        """Merged nur gesetzte Felder in ein bestehendes Profil.

        Existiert noch kein Profil, wird eines neu angelegt — dafür ist
        ``display_name`` im Request Pflicht.
        """
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            updates = request.model_dump(exclude_unset=True)
            if current is None:
                display_name = updates.get("display_name")
                if not display_name:
                    raise ValueError("display_name required to create profile")
                new_profile = UserProfile(**updates)
                return self._save_unlocked(new_profile)
            updated = current.model_copy(update=updates)
            return self._save_unlocked(updated)

    def set_avatar_ref(self, ref: str) -> UserProfile:
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            if current is None:
                raise ValueError("no profile exists to attach an avatar to")
            merged = {**current.model_dump(mode="json"), "avatar_ref": ref}
            # model_validate statt model_copy: erzwingt die Contract-Pattern-
            # Validierung von ``avatar_ref`` (Path-Traversal/Fremdnamen-Schutz).
            updated = UserProfile.model_validate(merged)
            return self._save_unlocked(updated)

    def clear_avatar_ref(self) -> Optional[UserProfile]:
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            if current is None:
                return None
            updated = current.model_copy(update={"avatar_ref": None})
            return self._save_unlocked(updated)



_store_singleton: Optional[UserProfileStore] = None
_singleton_lock = threading.Lock()


def get_user_profile_store() -> UserProfileStore:
    global _store_singleton
    if _store_singleton is None:
        with _singleton_lock:
            if _store_singleton is None:
                _store_singleton = UserProfileStore()
    return _store_singleton


def reset_user_profile_store_for_tests() -> None:
    global _store_singleton
    with _singleton_lock:
        _store_singleton = None
