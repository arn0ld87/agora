"""Scope-basierter Zugriffsschutz für API-Endpunkte (PR 4 Hardening §3.3).

Verwendung::

    from app.utils.scopes import require_scope

    @report_bp.route('/generate', methods=['POST'])
    @require_scope("report:write")
    def generate_report():
        ...

Scope-Hierarchie:
    - ``admin``  erfüllt jeden Scope.
    - ``write``  erfüllt ``*:write``, ``*:control``, ``*:read``.
    - ``read``   erfüllt ``*:read``.
    - Identisch passende fine-grained Scopes (z. B. ``report:read`` im Key) zählen direkt.

Master-Token:
    Ist ``AGORA_AUTH_TOKEN`` gesetzt und im Request vorhanden, wird ein
    synthetisches Admin-ApiKeyModel zurückgegeben. Master-Token-Inhaber haben
    damit immer Vollzugriff, konsistent mit ``install_blueprint_guard``.

Grace-Period:
    Endpunkte ohne ``@require_scope`` laufen weiterhin unter dem alten
    ``token_required``/``install_blueprint_guard``-Schutz. Deny-by-default
    kommt in einem späteren Slice (TODO-Kommentar im Code als Marker).
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import os
from functools import wraps
from typing import Callable

from flask import g, jsonify, request

from ..contracts.api_keys_contract import ApiKeyModel
from ..services.api_keys_store import get_api_keys_store

# Synthetisches Admin-Modell für den Master-Token-Pfad (lazy, thread-safe via GIL)
_SENTINEL_ADMIN: ApiKeyModel | None = None


def _get_sentinel_admin() -> ApiKeyModel:
    """Synthetisches Admin-ApiKeyModel für den Master-Token-Pfad.

    Wird NICHT persistiert, hat keinen echten Token-Hash und repräsentiert
    nur: "Master-Token vorhanden → Admin-Vollzugriff".
    """
    global _SENTINEL_ADMIN
    if _SENTINEL_ADMIN is None:
        _SENTINEL_ADMIN = ApiKeyModel(
            id="_master_token_sentinel_",
            label="master-token",
            prefix="ago_00000000",
            scopes=["admin"],
            status="active",
            hashed_token=hashlib.sha256(b"_sentinel_").hexdigest(),
            created_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        )
    return _SENTINEL_ADMIN


def _resolve_active_api_key(req) -> ApiKeyModel | None:
    """Extrahiert und validiert den API-Key aus dem Request.

    Akzeptiert (in Priorität):
    1. ``X-Agora-Api-Key: ago_xxx`` — Workspace API-Key
    2. ``Authorization: Bearer ago_xxx`` oder ``Bearer <master-token>``
    3. ``X-Agora-Token: ago_xxx`` oder ``<master-token>`` (backward-compat)

    Master-Token-Inhaber (``AGORA_AUTH_TOKEN``) erhalten ein synthetisches
    Admin-ApiKeyModel und passieren jeden Scope-Check.

    Returns:
        ``ApiKeyModel`` wenn aktiv, ``None`` wenn nicht gefunden oder revoked.
    """
    # Alle Token-Kandidaten sammeln
    candidates: list[str] = []

    header = req.headers.get("X-Agora-Api-Key", "")
    if header:
        candidates.append(header)

    auth = req.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        candidates.append(auth[7:].strip())

    legacy = req.headers.get("X-Agora-Token", "")
    if legacy:
        candidates.append(legacy)

    if not candidates:
        return None

    master_token = os.environ.get("AGORA_AUTH_TOKEN", "")
    store = get_api_keys_store()

    for token in candidates:
        if not token:
            continue

        # Master-Token — constant-time compare, Admin-Sentinel zurückgeben
        if master_token and hmac.compare_digest(token, master_token):
            return _get_sentinel_admin()

        # Workspace API-Key (ago_-Prefix)
        if token.startswith("ago_"):
            key = store.validate_token(token)
            if key is None:
                continue
            if key.status == "revoked":
                continue
            return key

    return None


def _scopes_cover(have: list[str], required: str) -> bool:
    """Prüft ob ``have`` den ``required``-Scope abdeckt.

    Match-Regeln (in Priorität):
    1. ``admin`` in ``have`` → erfüllt alles.
    2. Exakter String-Match (z. B. ``report:read`` in ``have``).
    3. ``write`` in ``have`` → erfüllt alle ``*:write``, ``*:control``, ``*:read``.
    4. ``read`` in ``have`` → erfüllt alle ``*:read``.
    """
    if "admin" in have:
        return True
    if required in have:
        return True
    if ":" in required:
        _, action = required.split(":", 1)
        # write deckt write, control UND read ab (übergeordneter Scope)
        if action in ("write", "control", "read") and "write" in have:
            return True
        if action == "read" and "read" in have:
            return True
    return False


def require_scope(required: str) -> Callable:
    """Decorator: 401 wenn kein API-Key/Master-Token, 403 wenn Scopes nicht ausreichen.

    Setzt ``flask.g.api_key`` auf das validierte ``ApiKeyModel``.

    Open-Mode (kein ``AGORA_AUTH_TOKEN`` konfiguriert):
        Kein Auth erforderlich — der Decorator lässt den Request durch, analog
        zu ``install_blueprint_guard`` im Open-Modus. Geändert sich das Auth-Verhalten
        in Zukunft (Deny-by-default), wird dieser Pfad entfernt.

    Args:
        required: Benötigter Scope-String, z. B. ``"report:write"``,
                  ``"simulation:control"``, ``"graph:write"``.
    """
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Open-Mode: kein AGORA_AUTH_TOKEN konfiguriert → kein Scope-Check
            # (konsistent mit install_blueprint_guard open-mode fallback)
            if not os.environ.get("AGORA_AUTH_TOKEN", ""):
                return fn(*args, **kwargs)

            key = _resolve_active_api_key(request)
            if key is None:
                return jsonify({"error": "unauthorized", "code": "no_api_key"}), 401
            if not _scopes_cover(list(key.scopes), required):
                return (
                    jsonify(
                        {
                            "error": "forbidden",
                            "code": "scope_missing",
                            "required": required,
                            "have": list(key.scopes),
                        }
                    ),
                    403,
                )
            g.api_key = key
            return fn(*args, **kwargs)

        return wrapper

    return deco
