"""Persona review state for the Slice 2 review foundation.

Adds a small ``review_status`` lifecycle (``pending``/``approved``/``rejected``)
on top of the existing ``reddit_profiles.json`` artifact, plus an editing path
so the UI can fix individual personas before approving them.

The service is deliberately thin: persistence stays in
:class:`SimulationArtifactStore`, no new on-disk format. The review status is
only treated as "missing" while the global :data:`Config.PERSONA_REVIEW_ENABLED`
flag is off; the API still allows explicit transitions for opt-in clients.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .artifact_store import SimulationArtifactStore, resolve_default_store

REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"

_VALID_STATUSES = {
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_REJECTED,
}

_EDITABLE_FIELDS = {
    "name",
    "bio",
    "persona",
    "age",
    "gender",
    "mbti",
    "country",
    "profession",
    "interested_topics",
    "language",
    "activity_level",
    "time_zone",
    "location",
    "verified",
    "source_entity_uuid",
    "source_entity_type",
}

_PROFILES_ARTIFACT = "reddit_profiles"


class PersonaNotFoundError(LookupError):
    """Raised when no persona with the requested username exists."""


class InvalidReviewStatusError(ValueError):
    """Raised when a caller tries to set an unknown review_status."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_status_for(profile: Dict[str, Any]) -> str:
    """Manually authored personas count as already curated → approved."""
    if profile.get("is_manual") is True:
        return REVIEW_STATUS_APPROVED
    return REVIEW_STATUS_PENDING


class PersonaReviewService:
    """Read/write persona review state for a single simulation."""

    def __init__(self, store: Optional[SimulationArtifactStore] = None) -> None:
        self._store = store or resolve_default_store()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def list_profiles(
        self, simulation_id: str, *, normalize: bool = True
    ) -> List[Dict[str, Any]]:
        """Return all reddit personas, optionally with normalized review fields.

        ``normalize=True`` ensures every persona has a ``review_status``,
        defaulting to ``pending`` (or ``approved`` for manual entries). The
        on-disk file is *not* mutated by this read; persistence only happens
        when a transition or edit is requested.
        """
        profiles = self._store.read_json(
            simulation_id, _PROFILES_ARTIFACT, default=[]
        ) or []
        if not isinstance(profiles, list):
            return []
        if not normalize:
            return [profile for profile in profiles if isinstance(profile, dict)]
        return [
            self._with_review_defaults(profile)
            for profile in profiles
            if isinstance(profile, dict)
        ]

    def get_profile(
        self, simulation_id: str, username: str
    ) -> Dict[str, Any]:
        for profile in self.list_profiles(simulation_id):
            if str(profile.get("username", "")) == username:
                return profile
        raise PersonaNotFoundError(
            f"Persona not found: {username}"
        )

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def set_status(
        self,
        simulation_id: str,
        username: str,
        status: str,
        *,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status not in _VALID_STATUSES:
            raise InvalidReviewStatusError(
                f"Invalid review_status: {status!r}; "
                f"expected one of {sorted(_VALID_STATUSES)}"
            )
        return self._mutate(
            simulation_id,
            username,
            mutator=lambda profile: self._apply_status(profile, status, notes),
        )

    def approve(
        self, simulation_id: str, username: str, *, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.set_status(
            simulation_id, username, REVIEW_STATUS_APPROVED, notes=notes
        )

    def reject(
        self, simulation_id: str, username: str, *, notes: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.set_status(
            simulation_id, username, REVIEW_STATUS_REJECTED, notes=notes
        )

    def edit(
        self,
        simulation_id: str,
        username: str,
        updates: Dict[str, Any],
    ) -> Dict[str, Any]:
        cleaned = self._clean_updates(updates)
        return self._mutate(
            simulation_id,
            username,
            mutator=lambda profile: self._apply_edit(profile, cleaned),
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _mutate(
        self,
        simulation_id: str,
        username: str,
        *,
        mutator,
    ) -> Dict[str, Any]:
        profiles = self.list_profiles(simulation_id, normalize=False)
        for idx, profile in enumerate(profiles):
            if str(profile.get("username", "")) != username:
                continue
            normalized = self._with_review_defaults(profile)
            updated = mutator(normalized)
            profiles[idx] = updated
            self._store.write_json(simulation_id, _PROFILES_ARTIFACT, profiles)
            return updated
        raise PersonaNotFoundError(f"Persona not found: {username}")

    @staticmethod
    def _with_review_defaults(profile: Dict[str, Any]) -> Dict[str, Any]:
        enriched = dict(profile)
        if not enriched.get("review_status"):
            enriched["review_status"] = _default_status_for(enriched)
        enriched.setdefault("review_notes", None)
        enriched.setdefault("reviewed_at", None)
        return enriched

    @staticmethod
    def _apply_status(
        profile: Dict[str, Any],
        status: str,
        notes: Optional[str],
    ) -> Dict[str, Any]:
        profile = dict(profile)
        profile["review_status"] = status
        profile["reviewed_at"] = _now()
        if notes is not None:
            profile["review_notes"] = notes.strip() or None
        return profile

    @staticmethod
    def _apply_edit(
        profile: Dict[str, Any], updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        profile = dict(profile)
        profile.update(updates)
        # An edit invalidates a prior approval/rejection: back to pending so
        # the reviewer must re-confirm. Manual personas keep their approved
        # default unless the edit explicitly overrides review_status.
        if "review_status" not in updates:
            profile["review_status"] = REVIEW_STATUS_PENDING
            profile["reviewed_at"] = None
        return profile

    @staticmethod
    def _clean_updates(updates: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(updates, dict):
            raise ValueError("updates must be a JSON object")
        cleaned: Dict[str, Any] = {}
        for key, value in updates.items():
            if key == "review_status":
                if value not in _VALID_STATUSES:
                    raise InvalidReviewStatusError(
                        f"Invalid review_status: {value!r}"
                    )
                cleaned[key] = value
                continue
            if key == "review_notes":
                if value is None:
                    cleaned[key] = None
                elif isinstance(value, str):
                    cleaned[key] = value.strip() or None
                else:
                    raise ValueError("review_notes must be a string or null")
                continue
            if key not in _EDITABLE_FIELDS:
                continue
            if key == "interested_topics" and isinstance(value, str):
                cleaned[key] = [
                    part.strip() for part in value.split(",") if part.strip()
                ]
                continue
            if isinstance(value, (str, int, float, bool, list)) or value is None:
                cleaned[key] = value
        if not cleaned:
            raise ValueError("No editable fields supplied")
        return cleaned


__all__ = [
    "PersonaReviewService",
    "PersonaNotFoundError",
    "InvalidReviewStatusError",
    "REVIEW_STATUS_PENDING",
    "REVIEW_STATUS_APPROVED",
    "REVIEW_STATUS_REJECTED",
]
