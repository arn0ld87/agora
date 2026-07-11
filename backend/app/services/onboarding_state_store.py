"""Persistenter JSON-Store für den resumierbaren Onboarding-Zustand (Slice 2).

Storage-Pfad: ``backend/data/onboarding_state.json`` (überschreibbar via
``AGORA_DATA_DIR``-Env). Locking-Muster identisch zu
:mod:`app.services.user_profile_store` / :mod:`app.services.workspace_routing_store`.

Fachliche Completion-Voraussetzungen (ADR-0008: gültiges Profil + konfiguriertes
Chat-Modell + gültige Embedding-Konfiguration) werden hier serverseitig
geprüft — der Contract in ``app.contracts.user_profile_contract`` sichert nur
die strukturelle Schritt-Konsistenz (z. B. keine Duplikate, "completed"
erfordert die Pflicht-Schritte).
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

from ..contracts.user_profile_contract import (
    ONBOARDING_STEP_ORDER,
    REQUIRED_ONBOARDING_STEPS,
    OnboardingRequirements,
    OnboardingState,
    OnboardingStepId,
    OnboardingStepUpdateRequest,
)
from ..settings import get_settings
from ..utils.logger import get_logger
from .user_profile_store import get_user_profile_store

logger = get_logger("agora.services.onboarding_state_store")

_DATA_DIR_ENV = "AGORA_DATA_DIR"
_STORE_FILENAME = "onboarding_state.json"


class OnboardingIncompleteError(Exception):
    """Wird geworfen, wenn ``complete()`` ohne erfüllte Voraussetzungen aufgerufen wird."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(
            "onboarding cannot be completed, missing: " + ", ".join(missing)
        )


def _resolve_data_dir() -> Path:
    raw = os.environ.get(_DATA_DIR_ENV)
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _first_open_step(completed_steps: list[OnboardingStepId]) -> OnboardingStepId:
    completed = set(completed_steps)
    for step in ONBOARDING_STEP_ORDER:
        if step not in completed:
            return step
    return "summary"


class OnboardingStateStore:
    """File-backed JSON-Store für den Onboarding-Wizard-Zustand."""

    def __init__(self, *, data_dir: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._data_dir = data_dir or _resolve_data_dir()
        self._path = self._data_dir / _STORE_FILENAME
        self._lock_path = self._path.with_suffix(".lock")

    @contextmanager
    def _file_lock(self) -> Iterator[IO[str]]:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield lock_fh
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def load(self) -> OnboardingState:
        with self._lock:
            return self._load_unlocked()

    def _load_unlocked(self) -> OnboardingState:
        if not self._path.exists():
            return OnboardingState()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning(
                "Onboarding-State-Store konnte nicht gelesen werden (%s): %s — "
                "verwende Default-Zustand",
                self._path,
                exc,
            )
            return OnboardingState()
        except json.JSONDecodeError as exc:
            logger.warning(
                "Onboarding-State-Store ist korrupt (%s): %s — "
                "verwende Default-Zustand. Bitte Datei manuell prüfen.",
                self._path,
                exc,
            )
            return OnboardingState()
        try:
            return OnboardingState.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — defensiv, geloggt, kein Crash beim Boot
            logger.warning(
                "Onboarding-State-Store enthält ungültige Daten (%s): %s — "
                "verwende Default-Zustand",
                self._path,
                exc,
            )
            return OnboardingState()

    def _save_unlocked(self, state: OnboardingState) -> OnboardingState:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        payload = state.model_copy(update={"updated_at": _now()})
        serialized = json.dumps(
            payload.model_dump(mode="json"), indent=2, sort_keys=True
        ).encode("utf-8")
        tmp_path = self._path.with_suffix(".tmp")
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            os.write(fd, serialized)
        finally:
            os.close(fd)
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

    def save(self, state: OnboardingState) -> OnboardingState:
        with self._lock, self._file_lock():
            return self._save_unlocked(state)

    def complete_step(self, request: OnboardingStepUpdateRequest) -> OnboardingState:
        """Markiert einen Schritt als abgeschlossen (idempotent) und rückt den
        Wizard auf den nächsten offenen Schritt vor."""
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            completed = list(current.completed_steps)
            if request.step not in completed:
                completed.append(request.step)
            updates: dict[str, object] = {"completed_steps": completed}
            if request.operating_mode is not None:
                updates["operating_mode"] = request.operating_mode
            if current.status != "completed":
                updates["status"] = "in_progress"
            updates["current_step"] = _first_open_step(completed)
            updated = current.model_copy(update=updates)
            return self._save_unlocked(updated)

    def dismiss(self) -> OnboardingState:
        """Setzt den Status auf 'dismissed' — no-op, falls bereits 'completed'."""
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            if current.status == "completed":
                return current
            updated = current.model_copy(update={"status": "dismissed"})
            return self._save_unlocked(updated)

    def reopen(self) -> OnboardingState:
        """Setzt den Wizard zurück auf 'in_progress' und behält completed_steps
        bei (Resume ab dem ersten offenen Schritt)."""
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            updated = current.model_copy(
                update={
                    "status": "in_progress",
                    "current_step": _first_open_step(list(current.completed_steps)),
                }
            )
            return self._save_unlocked(updated)

    def complete(self, requirements: OnboardingRequirements) -> OnboardingState:
        """Schliesst das Onboarding ab — wirft ``OnboardingIncompleteError``,
        falls Voraussetzungen (ADR-0008) oder Pflicht-Schritte fehlen."""
        with self._lock, self._file_lock():
            current = self._load_unlocked()
            missing: list[str] = []
            if not requirements.profile_valid:
                missing.append("profile_valid")
            if not requirements.chat_model_configured:
                missing.append("chat_model_configured")
            if not requirements.embedding_configured:
                missing.append("embedding_configured")
            missing_steps = REQUIRED_ONBOARDING_STEPS - set(current.completed_steps)
            missing.extend(sorted(missing_steps))
            if missing:
                raise OnboardingIncompleteError(missing)
            updated = current.model_copy(update={"status": "completed"})
            return self._save_unlocked(updated)

    def reset_for_tests(self) -> None:
        with self._lock:
            if self._path.exists():
                self._path.unlink()
            if self._lock_path.exists():
                self._lock_path.unlink()


def compute_onboarding_requirements() -> OnboardingRequirements:
    """Berechnet die fachlichen Completion-Voraussetzungen (ADR-0008).

    ``chat_model_configured`` prüft bewusst nur die Konfiguration, keine
    Live-Erreichbarkeit — der Erreichbarkeitscheck kommt mit der
    Provider-Discovery in Slice 3.
    """
    settings = get_settings()
    profile_valid = get_user_profile_store().load() is not None
    chat_model_configured = bool(settings.llm_model_name.strip())
    embedding_configured = (
        bool(settings.embedding_model.strip()) and settings.vector_dim > 0
    )
    return OnboardingRequirements(
        profile_valid=profile_valid,
        chat_model_configured=chat_model_configured,
        embedding_configured=embedding_configured,
    )


_store_singleton: Optional[OnboardingStateStore] = None
_singleton_lock = threading.Lock()


def get_onboarding_state_store() -> OnboardingStateStore:
    global _store_singleton
    if _store_singleton is None:
        with _singleton_lock:
            if _store_singleton is None:
                _store_singleton = OnboardingStateStore()
    return _store_singleton


def reset_onboarding_state_store_for_tests() -> None:
    global _store_singleton
    with _singleton_lock:
        _store_singleton = None
