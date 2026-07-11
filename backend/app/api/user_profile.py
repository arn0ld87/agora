"""User-Profile Blueprint (Onboarding Slice 2, Single-Workspace-Scope).

Endpunkte (hinter Standard-Blueprint-Guard, identisch zur restlichen
``/api/*``-Konvention):

  - GET    /api/profile          — aktuelles Profil (oder ``null``)
  - PUT    /api/profile          — partielles Update / Erstanlage
  - POST   /api/profile/avatar   — Avatar-Upload (multipart, Feld "file")
  - GET    /api/profile/avatar   — Avatar-Datei ausliefern
  - DELETE /api/profile/avatar   — Avatar entfernen

Der Avatar-Upload verlässt sich NIE nur auf den Content-Type-Header:
zusätzlich zur Allowlist in ``ALLOWED_AVATAR_MIME_TYPES`` werden die
Magic-Bytes der Datei geprüft — SVG und andere Formate werden damit
strukturell abgelehnt (Script-Injection-Schutz, siehe Contract-Docstring).
"""
from __future__ import annotations

import os
import uuid

from flask import Blueprint, request, send_from_directory
from pydantic import ValidationError

from ..contracts.user_profile_contract import (
    ALLOWED_AVATAR_MIME_TYPES,
    MAX_AVATAR_BYTES,
    UserProfileUpdateRequest,
)
from ..services.user_profile_store import get_user_profile_store
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.logger import get_logger

user_profile_bp = Blueprint("user_profile", __name__)
logger = get_logger("agora.api.user_profile")

# Magic-Bytes je erlaubtem Format. RIFF/WEBP hat einen 4-Byte-Präfix, eine
# 4-Byte-Chunk-Size und dann die "WEBP"-Signatur (Bytes 8-11).
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_RIFF_MAGIC = b"RIFF"
_WEBP_MAGIC = b"WEBP"

_EXT_TO_MIME: dict[str, str] = {
    ext: mime for mime, ext in ALLOWED_AVATAR_MIME_TYPES.items()
}


def _looks_like(content_type: str, data: bytes) -> bool:
    """Prüft die Magic-Bytes einer Datei gegen den angegebenen Content-Type."""
    if content_type == "image/png":
        return data.startswith(_PNG_MAGIC)
    if content_type == "image/jpeg":
        return data.startswith(_JPEG_MAGIC)
    if content_type == "image/webp":
        return (
            len(data) >= 12
            and data.startswith(_RIFF_MAGIC)
            and data[8:12] == _WEBP_MAGIC
        )
    return False


@user_profile_bp.route("", methods=["GET"])
@user_profile_bp.route("/", methods=["GET"])
@handle_api_errors
def get_profile():
    store = get_user_profile_store()
    profile = store.load()
    return json_success({"profile": profile.model_dump(mode="json") if profile else None})


@user_profile_bp.route("", methods=["PUT"])
@user_profile_bp.route("/", methods=["PUT"])
@handle_api_errors
def update_profile():
    payload = request.get_json(silent=True) or {}
    try:
        body = UserProfileUpdateRequest.model_validate(payload)
    except ValidationError as exc:
        return json_error(
            "Invalid request body",
            status=400,
            code="invalid_request",
            extra={"errors": exc.errors(include_url=False)},
        )
    store = get_user_profile_store()
    try:
        updated = store.update(body)
    except ValueError:
        return json_error(
            "display_name required to create profile",
            status=400,
            code="display_name_required",
        )
    return json_success({"profile": updated.model_dump(mode="json")})


@user_profile_bp.route("/avatar", methods=["POST"])
@handle_api_errors
def upload_avatar():
    file_storage = request.files.get("file")
    if file_storage is None:
        return json_error("no file uploaded", status=400, code="missing_file")

    store = get_user_profile_store()
    profile = store.load()
    if profile is None:
        return json_error(
            "profile must exist before an avatar can be uploaded",
            status=409,
            code="profile_required",
        )

    data = file_storage.read()
    if len(data) > MAX_AVATAR_BYTES:
        return json_error("avatar exceeds size limit", status=413, code="avatar_too_large")

    content_type = (file_storage.mimetype or "").lower()
    ext = ALLOWED_AVATAR_MIME_TYPES.get(content_type)
    if ext is None or not _looks_like(content_type, data):
        return json_error(
            "unsupported avatar file type",
            status=415,
            code="unsupported_media_type",
        )

    avatar_dir = store.avatar_dir
    filename = f"avatar-{uuid.uuid4().hex}{ext}"
    target_path = avatar_dir / filename
    fd = os.open(str(target_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)

    old_ref = profile.avatar_ref
    updated = store.set_avatar_ref(filename)

    if old_ref and old_ref != filename:
        old_path = avatar_dir / old_ref
        if old_path.exists():
            try:
                old_path.unlink()
            except OSError as exc:
                logger.warning("Konnte alten Avatar %s nicht löschen: %s", old_path, exc)

    return json_success({"profile": updated.model_dump(mode="json")}, status=201)


@user_profile_bp.route("/avatar", methods=["GET"])
@handle_api_errors
def get_avatar():
    store = get_user_profile_store()
    profile = store.load()
    if profile is None or not profile.avatar_ref:
        return json_error("no avatar set", status=404, code="avatar_not_found")
    avatar_path = store.avatar_dir / profile.avatar_ref
    if not avatar_path.exists():
        return json_error("avatar file missing", status=404, code="avatar_not_found")
    mimetype = _EXT_TO_MIME.get(avatar_path.suffix, "application/octet-stream")
    return send_from_directory(store.avatar_dir, profile.avatar_ref, mimetype=mimetype)


@user_profile_bp.route("/avatar", methods=["DELETE"])
@handle_api_errors
def delete_avatar():
    store = get_user_profile_store()
    profile = store.load()
    if profile is None:
        return json_error(
            "profile does not exist",
            status=409,
            code="profile_required",
        )
    if profile.avatar_ref:
        avatar_path = store.avatar_dir / profile.avatar_ref
        if avatar_path.exists():
            try:
                avatar_path.unlink()
            except OSError as exc:
                logger.warning("Konnte Avatar %s nicht löschen: %s", avatar_path, exc)
    updated = store.clear_avatar_ref()
    profile_data = updated.model_dump(mode="json") if updated else None
    return json_success({"profile": profile_data})
