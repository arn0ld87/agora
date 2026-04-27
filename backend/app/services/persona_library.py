"""Persistent reusable persona templates for local simulations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .artifact_store import LocalFilesystemArtifactStore, SimulationArtifactStore

_LIBRARY_ID = "_persona_library"
_LIBRARY_ARTIFACT = "persona_library"

_PROFILE_FIELDS = {
    "username",
    "name",
    "bio",
    "persona",
    "age",
    "gender",
    "mbti",
    "country",
    "profession",
    "interested_topics",
    "source_entity_uuid",
    "source_entity_type",
    "language",
    "activity_level",
    "time_zone",
    "location",
    "verified",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PersonaLibrary:
    """Small local template library backed by the simulation artifact store."""

    def __init__(self, store: Optional[SimulationArtifactStore] = None) -> None:
        self._store = store or LocalFilesystemArtifactStore()

    def list_templates(self) -> List[Dict[str, Any]]:
        templates = self._store.read_json(_LIBRARY_ID, _LIBRARY_ARTIFACT, default=[]) or []
        if not isinstance(templates, list):
            return []
        return sorted(
            [template for template in templates if isinstance(template, dict)],
            key=lambda item: item.get("updated_at") or item.get("created_at") or "",
            reverse=True,
        )

    def save_template(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        templates = self.list_templates()
        incoming_id = str(profile.get("template_id") or profile.get("id") or "").strip()
        template = self._normalize(profile, incoming_id or uuid4().hex[:12])
        username_key = str(template.get("username") or "").lower()
        replaced = False
        for idx, existing in enumerate(templates):
            existing_username = str(existing.get("username") or "").lower()
            if existing.get("template_id") == template["template_id"] or (
                not incoming_id and username_key and existing_username == username_key
            ):
                template["template_id"] = existing.get("template_id") or template["template_id"]
                template["created_at"] = existing.get("created_at") or template["created_at"]
                templates[idx] = template
                replaced = True
                break
        if not replaced:
            templates.append(template)
        self._store.write_json(_LIBRARY_ID, _LIBRARY_ARTIFACT, templates)
        return template

    def delete_template(self, template_id: str) -> bool:
        templates = self.list_templates()
        remaining = [item for item in templates if item.get("template_id") != template_id]
        if len(remaining) == len(templates):
            return False
        self._store.write_json(_LIBRARY_ID, _LIBRARY_ARTIFACT, remaining)
        return True

    def _normalize(self, profile: Dict[str, Any], template_id: str) -> Dict[str, Any]:
        now = _now()
        template = {
            "template_id": template_id,
            "created_at": profile.get("created_at") or now,
            "updated_at": now,
        }
        for key in _PROFILE_FIELDS:
            value = profile.get(key)
            if value in (None, ""):
                continue
            if key == "interested_topics" and isinstance(value, str):
                value = [part.strip() for part in value.split(",") if part.strip()]
            if isinstance(value, (str, int, float, bool, list)):
                template[key] = value
        if not template.get("username"):
            template["username"] = f"persona_{template_id[:8]}"
        if not template.get("name"):
            template["name"] = template["username"]
        template["is_template"] = True
        return template
