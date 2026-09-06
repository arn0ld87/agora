"""
Status monitoring endpoint — unified health check for all system components.
Returns backend version, Neo4j reachability, Ollama availability, and disk usage in a single request.
"""

import os
import shutil
from datetime import datetime, timezone
from flask import current_app
import requests
from neo4j.exceptions import (
    AuthConfigurationError,
    AuthError,
    DatabaseUnavailable,
    RoutingServiceUnavailable,
    ServiceUnavailable,
    SessionExpired,
)

from . import status_bp
from .. import __version__
from ..config import Config
from ..contracts.system_status_contract import (
    StatusCheckError,
    StatusErrorCode,
    SystemStatusE2E,
    SystemStatusOllama,
)
from ..llm.json_mode import _read_active_config_safely
from ..llm.providers.registry import detect_provider, resolve_ollama_tags_url
from ..utils.gpu_probe import detect_gpu
from ..utils.logger import get_logger
from ..utils.api_responses import handle_api_errors, json_success

logger = get_logger('agora.api.status')

# Neo4j-Ausnahmen, die auf einen nicht erreichbaren Server hindeuten
# (Routing-/Cluster-Ausfall, Session verloren) statt auf eine
# Authentifizierungs- oder Programmierfehler-Klasse.
_NEO4J_UNREACHABLE_EXCEPTIONS = (
    ServiceUnavailable,
    SessionExpired,
    RoutingServiceUnavailable,
    DatabaseUnavailable,
)
_NEO4J_AUTH_EXCEPTIONS = (AuthError, AuthConfigurationError)


def _classify_status_error(exc: BaseException) -> StatusErrorCode:
    """Ordnet eine gefangene Probe-Exception einem geschlossenen Fehlercode zu.

    Gemeinsam genutzt von ``_get_neo4j_status``, ``_get_ollama_status`` und
    ``_get_disk_status`` — die drei Stellen, die bislang ``str(exc)`` roh in
    die Antwort schrieben (#1458). Der Rohtext selbst gehört nur ins
    strukturierte Log, nicht in diese Klassifikation.
    """
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)):
        return StatusErrorCode.TIMEOUT
    if isinstance(exc, (PermissionError,) + _NEO4J_AUTH_EXCEPTIONS):
        return StatusErrorCode.AUTH
    if isinstance(exc, requests.exceptions.HTTPError):
        response = getattr(exc, "response", None)
        if response is not None and getattr(response, "status_code", None) in (401, 403):
            return StatusErrorCode.AUTH
        return StatusErrorCode.UNEXPECTED
    if isinstance(
        exc,
        (ConnectionError, FileNotFoundError, requests.exceptions.ConnectionError)
        + _NEO4J_UNREACHABLE_EXCEPTIONS,
    ):
        return StatusErrorCode.UNREACHABLE
    return StatusErrorCode.UNEXPECTED


def _get_auth_mode():
    """Classify which auth posture the API runs under right now.

    Values:
    - ``"single_user_token"``: ``AGORA_AUTH_TOKEN`` is set; ``/api/*``
      requires it. The ``single_user_`` prefix reflects ADR-0001
      (``docs/decisions/0001-auth-model.md``): v1.0 is a Single-User-only
      simulator, the shared bearer token is the only auth principal.
      Renamed from ``"token"`` 2026-05-04 so operators reading
      ``/api/status`` see immediately that the app does not have a
      multi-user model.
    - ``"anonymous"``: ``AGORA_ALLOW_ANONYMOUS=true`` opt-out is active.
    - ``"open"``: no token, no opt-out, but ``FLASK_DEBUG=true`` (dev).
    - ``"misconfigured"``: no token, no opt-out, no debug — `Config.validate()`
      should have blocked this; we surface it loudly so an operator notices.

    Operators monitor this via backend.auth_mode to confirm
    that production is on ``"single_user_token"`` and not silently in one
    of the open modes.
    """
    if os.environ.get("AGORA_AUTH_TOKEN", "").strip():
        return "single_user_token"
    if os.environ.get("AGORA_ALLOW_ANONYMOUS", "false").lower() in ("true", "1", "yes"):
        return "anonymous"
    if os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1", "yes"):
        return "open"
    return "misconfigured"


def _get_backend_status():
    """Get backend health, version, and active auth mode.

    ``allow_small_sim`` ist entfallen: die harte Untergrenze von 30
    Personas gibt es nicht mehr, damit auch keinen Schalter, der sie
    aufhebt (Block B4).
    """
    return {
        "ok": True,
        "version": __version__,
        "auth_mode": _get_auth_mode(),
    }


def _get_e2e_status():
    """Report whether this backend process serves stubbed LLM answers.

    Liest ``AGORA_E2E_LLM_MODE`` bei jedem Request frisch — dieselbe Variable,
    die ``LLMClient.chat_json`` auswertet, bevor es den Provider-Call
    überspringt. Damit ist der Wert an der API genau das, was der LLM-Pfad
    tatsächlich tut, und nicht eine Nebenbuchführung.

    ``stub_active`` vergleicht den **Rohwert** exakt gegen ``"stub"`` — ohne
    ``strip()``. Das ist bewusst dieselbe Operation wie in
    ``llm/client.py:596``/``:994``, ``llm/tool_calls.py:165`` und
    ``storage/embedding_service.py:157``. Ein ``strip()`` hier würde bei einem
    gepolsterten Wert wie ``" stub "`` ``stub_active=True`` melden, während der
    LLM-Pfad denselben Wert als Nicht-Stub liest und den echten Provider ruft —
    die E2E-Diagnose würde dann genau den ungültigen Lauf freigeben, den sie
    verhindern soll. ``llm_mode`` bleibt der Rohwert, damit ein solcher
    Tippfehler in der Fehlermeldung sichtbar wird statt weggeputzt zu werden.

    Rückgabe folgt dem Contract ``SystemStatusE2E``.
    """
    raw = os.environ.get("AGORA_E2E_LLM_MODE")
    return SystemStatusE2E(
        llm_mode=raw or None,
        stub_active=raw == "stub",
    ).model_dump(mode="json")


def _get_neo4j_status():
    """Check Neo4j connectivity."""
    storage = current_app.extensions.get('neo4j_storage')

    if storage is None:
        return {
            "reachable": False,
            "error": current_app.extensions.get('neo4j_storage_error') or "Storage not initialized",
            "uri": Config.NEO4J_URI,
        }

    try:
        # Go through the storage's public probe so the fork-reset
        # lazy-reconnect path is honored. Reaching into ``storage._driver``
        # directly would crash with "'NoneType' object has no attribute
        # 'verify_connectivity'" right after a gunicorn worker fork.
        storage.verify_connectivity()
        last_success = getattr(storage, 'last_success_ts', None)
        return {
            "reachable": True,
            "error": None,
            "uri": Config.NEO4J_URI,
            "is_connected": getattr(storage, 'is_connected', True),
            "last_success_ts": last_success.isoformat() if last_success else None,
        }
    except Exception as e:  # noqa: BLE001 — probe result; exc used in status dict
        last_error = getattr(storage, 'last_error', None) or e
        logger.warning(
            "Neo4j connectivity probe failed",
            extra={"neo4j_uri": Config.NEO4J_URI, "error": str(last_error)},
        )
        return {
            "reachable": False,
            "error": StatusCheckError(
                code=_classify_status_error(last_error)
            ).model_dump(mode="json"),
            "uri": Config.NEO4J_URI,
            "is_connected": getattr(storage, 'is_connected', False),
            "last_success_ts": (storage.last_success_ts.isoformat()
                                if getattr(storage, 'last_success_ts', None) else None),
        }


def _get_ollama_status():
    """Check Ollama availability and list models.

    Übersprungen wird nur bei einem Provider, der ``/api/tags`` garantiert
    nicht kennt (MiniMax/OpenAI/Google) — dort lieferte die alte, pauschale
    Abfrage 404er im Log. Selbstgehostete Ollamas auf Nicht-Standard-Ports
    (``detect_provider`` → ``"unknown"``) werden weiterhin geprobt.

    Rückgabe folgt dem Contract ``SystemStatusOllama``; ``reachable`` ist
    dreiwertig (True/False/None). ``None`` heißt "übersprungen", nicht
    "offline".

    Folgebefund zu #1418: sowohl die Probe-Entscheidung als auch der
    angezeigte Provider stammten ausschliesslich aus ``Config.LLM_*``, also
    aus der ``.env`` des Containers. Damit meldete das Dashboard dauerhaft
    den ``.env``-Provider, unabhaengig davon, welche Verbindung unter
    Einstellungen → LLM-Anbieter aktiviert war — beobachtet als "aktiver
    Provider ist MiniMax", waehrend die aktive Auswahl codex_cli war. Die
    aktive Konfiguration hat jetzt Vorrang, die ``.env`` bleibt Fallback
    fuer Installationen, die nie eine Verbindung aktiviert haben.
    """
    active = _read_active_config_safely() or {}
    effective_base_url = active.get("base_url") or Config.LLM_BASE_URL
    effective_model = active.get("model") or Config.LLM_MODEL_NAME

    base = resolve_ollama_tags_url(
        effective_base_url,
        effective_model,
        explicit_base_url=os.environ.get('OLLAMA_BASE_URL'),
    )

    if base is None:
        # ``reachable=None`` (nicht False) signalisiert "nicht ermittelt".
        # ``skipped_provider`` ist der maschinenlesbare Schlüssel für den
        # i18n-Lookup im Frontend; ``reason`` bleibt reines Debug-Feld und
        # darf nicht in der UI gerendert werden.
        #
        # Die ``provider_id`` der aktiven Auswahl schlaegt die URL-Heuristik:
        # sie benennt die tatsaechlich aktivierte Verbindung, waehrend
        # ``detect_provider`` nur aus der Base-URL raten kann — und fuer
        # Provider ohne HTTP-Endpunkt (codex_cli, #1405) gar nichts hat.
        provider = active.get("provider_id") or detect_provider(
            effective_base_url, effective_model, mode="http"
        )
        return SystemStatusOllama(
            reachable=None,
            skipped=True,
            skipped_provider=provider,
            reason=f"Active provider is {provider}",
            base_url=None,
            models_available=[],
            default_model=effective_model,
            error=None,
        ).model_dump(mode="json")

    status = SystemStatusOllama(
        reachable=False,
        skipped=False,
        base_url=base,
        default_model=effective_model,
    )

    try:
        resp = requests.get(f"{base}/api/tags", timeout=2.5)
        resp.raise_for_status()
        payload = resp.json() or {}

        models = []
        for m in payload.get('models', []) or []:
            name = m.get('name')
            if name:
                models.append(name)

        status.reachable = True
        status.models_available = models
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        status.error = StatusCheckError(code=_classify_status_error(e))
        logger.debug(
            "Could not reach Ollama",
            extra={"ollama_base_url": base, "error": str(e)},
        )

    return status.model_dump(mode="json")


def _get_disk_status():
    """Check disk usage for uploads directory."""
    uploads_path = os.path.join(os.path.dirname(__file__), '../../uploads')
    uploads_path = os.path.abspath(uploads_path)

    try:
        usage = shutil.disk_usage(uploads_path)
        return {
            "uploads": {
                "path": uploads_path,
                "total_bytes": usage.total,
                "free_bytes": usage.free,
                "used_pct": round((usage.used / usage.total * 100), 2) if usage.total > 0 else 0,
            }
        }
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(
            "Could not check disk usage",
            extra={"uploads_path": uploads_path, "error": str(e)},
        )
        return {
            "uploads": {
                "path": uploads_path,
                "total_bytes": None,
                "free_bytes": None,
                "used_pct": None,
                "error": StatusCheckError(
                    code=_classify_status_error(e)
                ).model_dump(mode="json"),
            }
        }


@status_bp.route('', methods=['GET'])
@handle_api_errors
def get_status():
    """
    Unified status endpoint.

    Returns health information for all system components in a single request:
    - backend: version and operational status
    - neo4j: connectivity and URI
    - ollama: reachability, available models, and default model
    - e2e: whether this process serves stubbed LLM answers
    - disk: usage statistics for the uploads directory
    - timestamp: ISO-8601 UTC timestamp

    No component failure causes a 5xx error — all checks are defensive.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        gpu = detect_gpu()
    except Exception as e:  # detect_gpu is documented to never raise, but be defensive.  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.debug(f"GPU probe failed unexpectedly: {e}")
        gpu = {"nvidia_smi_available": False, "ollama_uses_gpu": None, "hints": [f"probe error: {e}"]}

    # json_success normally wraps data in "data" field.
    # The original endpoint returned the dict directly at top level.
    # To preserve this, we can pass the dict as extra arguments or just use json_success's behavior
    # Actually, original return was:
    # return jsonify({
    #     "backend": _get_backend_status(),
    #     ...
    # }), 200

    # json_success(data=None, **extra) -> {"success": True, **extra}

    return json_success(
        backend=_get_backend_status(),
        neo4j=_get_neo4j_status(),
        ollama=_get_ollama_status(),
        e2e=_get_e2e_status(),
        disk=_get_disk_status(),
        gpu=gpu,
        timestamp=timestamp
    )
