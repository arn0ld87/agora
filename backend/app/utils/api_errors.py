"""Zentraler Katalog für API-Fehlercodes plus deutsche Default-Messages.

Codes sind ``StrEnum`` und können überall dort verwendet werden, wo bisher
String-Literale wie ``code="not_found"`` standen — Vergleich mit Strings bleibt
funktionsgleich (Backwards-Compat).

Verwendung::

    from app.utils.api_errors import ApiErrorCode
    from app.utils.api_responses import json_error

    return json_error(ApiErrorCode.INVALID_ID, status=400)
    # → {"success": false, "code": "invalid_id", "error": "Ungültige ID"}
"""

from __future__ import annotations

from enum import StrEnum


class ApiErrorCode(StrEnum):
    """Enumerierter Code-Katalog. Wert == lowercase Name."""

    INVALID_ID = "invalid_id"
    NOT_FOUND = "not_found"
    VALIDATION_FAILED = "validation_failed"
    BAD_REQUEST = "bad_request"
    METHOD_NOT_ALLOWED = "method_not_allowed"

    AUTH_REQUIRED = "auth_required"
    AUTH_INVALID = "auth_invalid"
    AUTH_FORBIDDEN = "auth_forbidden"

    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"

    SERVICE_UNAVAILABLE = "service_unavailable"
    NEO4J_UNAVAILABLE = "neo4j_unavailable"
    LLM_UNAVAILABLE = "llm_unavailable"

    ONTOLOGY_MISSING = "ontology_missing"
    ONTOLOGY_GENERATION_FAILED = "ontology_generation_failed"

    SIMULATION_NOT_PREPARED = "simulation_not_prepared"
    SIMULATION_ALREADY_RUNNING = "simulation_already_running"
    PERSONA_REVIEW_REQUIRED = "persona_review_required"

    GRAPH_BUILD_IN_PROGRESS = "graph_build_in_progress"

    UPLOAD_TOO_LARGE = "upload_too_large"
    UNSUPPORTED_FORMAT = "unsupported_format"

    INTERNAL_ERROR = "internal_error"
    NOT_IMPLEMENTED = "not_implemented"


DEFAULT_MESSAGES: dict[ApiErrorCode, str] = {
    ApiErrorCode.INVALID_ID: "Ungültige ID",
    ApiErrorCode.NOT_FOUND: "Nicht gefunden",
    ApiErrorCode.VALIDATION_FAILED: "Eingabe ungültig",
    ApiErrorCode.BAD_REQUEST: "Ungültige Anfrage",
    ApiErrorCode.METHOD_NOT_ALLOWED: "Methode nicht erlaubt",

    ApiErrorCode.AUTH_REQUIRED: "Authentifizierung erforderlich",
    ApiErrorCode.AUTH_INVALID: "Authentifizierung ungültig",
    ApiErrorCode.AUTH_FORBIDDEN: "Zugriff verweigert",

    ApiErrorCode.RATE_LIMITED: "Zu viele Anfragen",
    ApiErrorCode.TIMEOUT: "Zeitüberschreitung",

    ApiErrorCode.SERVICE_UNAVAILABLE: "Dienst nicht verfügbar",
    ApiErrorCode.NEO4J_UNAVAILABLE: "Neo4j nicht erreichbar",
    ApiErrorCode.LLM_UNAVAILABLE: "LLM-Endpoint nicht erreichbar",

    ApiErrorCode.ONTOLOGY_MISSING: "Ontologie fehlt",
    ApiErrorCode.ONTOLOGY_GENERATION_FAILED: "Ontologie-Generierung fehlgeschlagen",

    ApiErrorCode.SIMULATION_NOT_PREPARED: "Simulation noch nicht vorbereitet",
    ApiErrorCode.SIMULATION_ALREADY_RUNNING: "Simulation läuft bereits",
    ApiErrorCode.PERSONA_REVIEW_REQUIRED: "Persona-Review erforderlich",

    ApiErrorCode.GRAPH_BUILD_IN_PROGRESS: "Graph-Build läuft bereits",

    ApiErrorCode.UPLOAD_TOO_LARGE: "Upload zu groß",
    ApiErrorCode.UNSUPPORTED_FORMAT: "Format nicht unterstützt",

    ApiErrorCode.INTERNAL_ERROR: "Interner Serverfehler",
    ApiErrorCode.NOT_IMPLEMENTED: "Nicht implementiert",
}


__all__ = ["ApiErrorCode", "DEFAULT_MESSAGES"]
