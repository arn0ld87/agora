"""Readiness-Endpoint /readyz (Code-Review 2026-05-17, Finding 1.8).

Trennt Liveness (`/health`, weiter unverändert in ``create_app``) von
Readiness. ``/health`` muss grün bleiben, solange der Prozess lebt —
``/readyz`` muss rot werden, sobald eine kritische Abhängigkeit kippt:
Neo4j, Redis (nur wenn aktiv genutzt), Upload-Verzeichnis, Embedding-Konfig.

Beispielantwort bei vollständig gesundem Stack:

    GET /readyz → 200
    {"status": "ready", "checks": {
        "neo4j": {"ok": true,  "detail": "ok"},
        "redis": {"ok": true,  "detail": "ok"},
        "upload_dir": {"ok": true, "detail": "/app/backend/uploads"},
        "embedding_config": {"ok": true, "detail": "qwen3-embedding:4b → dim=2560"}
    }}

Beispielantwort bei kaputtem Neo4j:

    GET /readyz → 503
    {"status": "not_ready", "checks": {
        "neo4j": {"ok": false, "detail": "bolt://neo4j:7687 unreachable: ..."},
        ...
    }}

Design-Entscheidungen:

* Keine LLM/Embedding-Live-Probe. Review §4.4 warnt explizit: Ollama-Cold-
  Start würde sonst den Container-Start blockieren. Wir prüfen nur die
  *Kohärenz* von ``EMBEDDING_MODEL`` und ``VECTOR_DIM``.
* Redis-Check wird übersprungen, wenn der konfigurierte Event-Bus nicht
  das Redis-Backend ist. Damit kann ein bewusster
  ``EVENT_BUS_BACKEND=file``-Betrieb nicht von /readyz rotgemacht werden.
* Keine Authentifizierung — die Routen werden außerhalb der
  Blueprint-Guards registriert (analog zum bestehenden ``/health``).
* Probe-Funktionen sind klein und stateless, damit Tests Fakes via
  ``app.extensions`` / ``app.config`` einspeisen können, ohne den
  ``create_app``-Boot durchlaufen zu müssen.
"""

from __future__ import annotations

import os
from typing import Any, Tuple

from flask import Flask, Response, current_app, jsonify

from .config import infer_vector_dim_for_model

CheckResult = Tuple[bool, str]


def _check_neo4j() -> CheckResult:
    """Neo4j ist verfügbar, wenn ``app.extensions['neo4j_storage']``
    gesetzt ist und eine simple Connectivity-Probe durchläuft.

    Schlägt der Storage-Init beim Boot fehl, hinterlegt ``create_app``
    den Grund unter ``neo4j_storage_error`` — den geben wir 1:1 weiter.
    """
    storage = current_app.extensions.get("neo4j_storage")
    init_error = current_app.extensions.get("neo4j_storage_error")
    if storage is None:
        return False, init_error or "neo4j_storage not initialized"
    probe = getattr(storage, "verify_connectivity", None)
    if probe is None:
        return False, "neo4j_storage has no verify_connectivity()"
    try:
        probe()
    except Exception as exc:  # noqa: BLE001 — Probe-Fehler werden im Body sichtbar
        return False, str(exc)
    return True, "ok"


def _check_redis() -> CheckResult:
    """Probet den Event-Bus über ``verify_connectivity()``.

    Vertrag: Backends mit echter Netzwerk-Abhängigkeit (``RedisEventBus``)
    exposieren ``verify_connectivity()`` und werfen, wenn Redis nicht
    erreichbar ist. Backends ohne Netzwerk-Abhängigkeit
    (``FilePollingEventBus``) exposieren die Methode bewusst NICHT — der
    Check meldet dann ``skipped``, statt fälschlicherweise zu pingen.

    Vorgängerversion hat über ``type(bus).__name__`` und drei Attribut-
    Kandidaten geraten — fragil und in der Praxis kaputt, weil
    ``RedisEventBus`` den Client unter ``_redis`` hält. Gemini-Review
    (PR #519) hat darauf gedeutet, und die Probe wurde auf das explizite
    Interface umgestellt.
    """
    bus = current_app.extensions.get("event_bus")
    if bus is None:
        return False, "event_bus not initialized"
    probe = getattr(bus, "verify_connectivity", None)
    if probe is None:
        return True, f"skipped (event_bus={type(bus).__name__} has no probe)"
    try:
        probe()
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, "ok"


def _check_upload_dir() -> CheckResult:
    """Upload-Verzeichnis muss existieren und schreibbar sein.

    Stateless: die Probe legt das Verzeichnis NICHT an. Ein fehlendes
    Upload-Dir ist ein Setup-Fehler, den /readyz sichtbar machen soll —
    Dockerfile und Compose-Bootstrap erzeugen den Pfad bereits beim
    Image-Build bzw. via Bind-Mount.
    """
    folder = current_app.config.get("UPLOAD_FOLDER")
    if not folder:
        return False, "UPLOAD_FOLDER not configured"
    if not os.path.isdir(folder):
        return False, f"upload dir does not exist: {folder}"
    if not os.access(folder, os.W_OK):
        return False, f"upload dir not writable: {folder}"
    return True, str(folder)


def _check_embedding_config() -> CheckResult:
    """``EMBEDDING_MODEL`` und ``VECTOR_DIM`` müssen zusammenpassen.

    Eine falsche Dimension lässt Neo4j-Vector-Index-Inserts beim ersten
    Persist-Aufruf scheitern — fail-fast in /readyz, statt im
    Graph-Build-Job.
    """
    model = current_app.config.get("EMBEDDING_MODEL")
    dim = current_app.config.get("VECTOR_DIM")
    if not model:
        return False, "EMBEDDING_MODEL not configured"
    if dim is None:
        return False, "VECTOR_DIM not configured"
    expected = infer_vector_dim_for_model(model)
    try:
        dim_int = int(dim)
    except (TypeError, ValueError):
        return False, f"VECTOR_DIM not an integer: {dim!r}"
    if expected and dim_int != expected:
        return False, (
            f"VECTOR_DIM mismatch for EMBEDDING_MODEL '{model}': "
            f"configured {dim_int}, expected {expected}"
        )
    return True, f"{model} → dim={dim_int}"


def _run_checks() -> dict[str, Any]:
    """Führt alle Probes aus und packt das Ergebnis in das /readyz-Format."""
    results: dict[str, CheckResult] = {
        "neo4j": _check_neo4j(),
        "redis": _check_redis(),
        "upload_dir": _check_upload_dir(),
        "embedding_config": _check_embedding_config(),
    }
    return {
        "status": "ready" if all(ok for ok, _ in results.values()) else "not_ready",
        "checks": {
            name: {"ok": ok, "detail": detail} for name, (ok, detail) in results.items()
        },
    }


def register_readiness_routes(app: Flask) -> None:
    """Hängt ``/health`` (Liveness) und ``/readyz`` (Readiness) an ``app``.

    Beide Routen werden bewusst außerhalb der Blueprint-Auth-Guards
    registriert (Docker-Healthcheck hat keinen Token). ``/health`` bleibt
    abhängigkeitsfrei: solange der Prozess lebt, ist die Antwort 200.
    """

    @app.route("/health", methods=["GET"])
    def health() -> tuple[Response, int]:
        return jsonify({"status": "ok", "service": "Agora Backend"}), 200

    @app.route("/readyz", methods=["GET"])
    def readyz() -> tuple[Response, int]:
        payload = _run_checks()
        status_code = 200 if payload["status"] == "ready" else 503
        return jsonify(payload), status_code
