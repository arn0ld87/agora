"""Readiness-Endpoint /readyz (Code-Review 2026-05-17, Finding 1.8).

Trennt Liveness (`/health`, weiter unverändert in ``create_app``) von
Readiness. ``/health`` muss grün bleiben, solange der Prozess lebt —
``/readyz`` muss rot werden, sobald eine kritische Abhängigkeit kippt:
Neo4j, Redis (nur wenn aktiv genutzt), Upload-Verzeichnis, Embedding-Konfig.

Beispielantwort bei vollständig gesundem Stack (Legacy-Default, kein
``AGORA_*_BACKEND`` auf ``postgres``):

    GET /readyz → 200
    {"status": "ready", "checks": {
        "neo4j": {"ok": true,  "detail": "ok"},
        "redis": {"ok": true,  "detail": "ok"},
        "upload_dir": {"ok": true, "detail": "/app/backend/uploads"},
        "embedding_config": {"ok": true, "detail": "qwen3-embedding:4b → dim=2560"},
        "embedding_index_version": {"ok": true, "detail": "no active index version (legacy view)"},
        "postgres": {"ok": true, "detail": "no AGORA_*_BACKEND is set to postgres", "state": "disabled"}
    }}

Beispielantwort bei kaputtem Neo4j:

    GET /readyz → 503
    {"status": "not_ready", "checks": {
        "neo4j": {"ok": false, "detail": "neo4j connectivity probe failed"},
        ...
    }}

Design-Entscheidungen:

* Keine LLM/Embedding-Live-Probe. Review §4.4 warnt explizit: Ollama-Cold-
  Start würde sonst den Container-Start blockieren. Wir prüfen nur die
  *Kohärenz* von ``EMBEDDING_MODEL`` und ``VECTOR_DIM``.
* Redis-Check wird übersprungen, wenn der konfigurierte Event-Bus nicht
  das Redis-Backend ist. Damit kann ein bewusster
  ``EVENT_BUS_BACKEND=file``-Betrieb nicht von /readyz rotgemacht werden.
* PostgreSQL-Check (#1581, docs/plans/supabase.md §29): trägt zusätzlich
  ``state`` (``ok``/``unavailable``/``disabled``, siehe
  ``app.contracts.readiness_contract.PostgresReadinessCheck``). Solange kein
  ``AGORA_*_BACKEND`` auf ``postgres`` steht, ist der Zustand ``disabled`` —
  es wird dann auch keine Engine gebaut; ``disabled`` macht /readyz NICHT rot.
  Erst wenn mindestens ein Backend aktiv ist, probt der Check `SELECT 1` und
  wird bei Fehlschlag zu ``unavailable`` (macht /readyz rot).
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

from .config import Config, infer_vector_dim_for_model
from .contracts.readiness_contract import PostgresReadinessCheck
from .infrastructure.postgres import Database
from .infrastructure.postgres.backends import any_postgres_backend
from .utils.logger import get_logger

CheckResult = Tuple[bool, str]
logger = get_logger("agora.readiness")

#: Kurzes Verbindungs-Timeout (Sekunden) für die /readyz-Postgres-Probe. Ohne
#: dieses Limit kann ein TCP-Connect gegen eine tote Adresse je nach OS-Timeout
#: Minuten hängen, statt den Check schnell als ``unavailable`` zu melden.
_POSTGRES_READINESS_CONNECT_TIMEOUT = 2.0


def _safe_probe_failure(check_name: str, exc: Exception) -> CheckResult:
    logger.warning("%s readiness probe failed: %s", check_name, exc, exc_info=True)
    return False, f"{check_name} connectivity probe failed"


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
        return _safe_probe_failure("neo4j", exc)
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
        return _safe_probe_failure("redis", exc)
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


def _check_embedding_index_version() -> CheckResult:
    """Prueft eine als ``active`` behauptete ``EmbeddingIndexVersion`` gegen
    die Neo4j-Realitaet (#1417, Slice 2.4 — "Legacy-View fuer Bestandsgraphen").

    Ohne aktive Indexversion gilt die Legacy-Ansicht aus ``Config.*``
    (bereits durch ``_check_embedding_config`` abgedeckt) — dann ist hier
    nichts zu pruefen. Existiert eine aktive Indexversion, muss der
    behauptete Index in Neo4j tatsaechlich ``ONLINE`` sein: ein
    Bestandssystem, dessen Migration vor Slice 2.2 mit dem alten
    Sofort-Umschalt-Verhalten gestartet wurde, traegt eine ``active``-
    Version, die nie fertig migriert oder validiert wurde, unveraendert
    weiter — Slice 2.2 repariert das nicht rueckwirkend. Reads/Writes
    wuerden dann still gegen einen unvollstaendigen oder nicht
    existierenden Index laufen (genau die Korruption, vor der #1417
    warnt), ohne dass dieser Check dies laut macht.
    """
    from .services.embedding_configuration_store import EmbeddingConfigurationStore

    # Der Store liest eine JSON-Datei und wirft ``RuntimeError``, wenn sie
    # unlesbar oder kaputt ist. Ohne diesen Guard wuerde daraus eine 500
    # statt der 503, die /readyz zusagt — und der Healthcheck koennte den
    # Unterschied zwischen "nicht bereit" und "Endpoint selbst kaputt"
    # nicht mehr melden.
    try:
        active = EmbeddingConfigurationStore().get_active_index_version()
    except Exception as exc:  # noqa: BLE001 — Probe-Fehler werden im Body sichtbar
        return _safe_probe_failure("embedding_index_version", exc)
    if active is None:
        return True, "no active index version (legacy view)"

    storage = current_app.extensions.get("neo4j_storage")
    if storage is None:
        return False, (
            f"cannot verify active index version v{active.version} "
            f"({active.index_name!r}) — neo4j_storage not initialized"
        )
    probe = getattr(storage, "index_state", None)
    if probe is None:
        return False, "neo4j_storage has no index_state()"
    try:
        state = probe(active.index_name)
    except Exception as exc:  # noqa: BLE001 — Probe-Fehler werden im Body sichtbar
        return _safe_probe_failure("embedding_index_version", exc)
    if state != "ONLINE":
        return False, (
            f"active index version v{active.version} ({active.index_name!r}) "
            f"is not ONLINE in Neo4j (state={state!r}) — possibly a migration "
            "started before Slice 2.2 that was never validated (#1417)"
        )
    return True, f"v{active.version} ({active.index_name}) ONLINE"


def _check_postgres() -> PostgresReadinessCheck:
    """PostgreSQL-Zustand für /readyz (docs/plans/supabase.md §29, Issue #1581).

    Drei Zustände, über ``state`` maschinenlesbar:

    * ``disabled``    — kein ``AGORA_*_BACKEND`` steht auf ``postgres``. Es
      wird KEINE Verbindung aufgebaut, nicht einmal eine Engine — der
      Legacy-Default bleibt unberührt. ``ok=True``, macht /readyz nicht rot.
    * ``ok``          — mindestens ein Backend ist aktiv, `SELECT 1` gelingt.
    * ``unavailable`` — mindestens ein Backend ist aktiv, die Probe scheitert.
      ``ok=False`` macht /readyz rot (503).

    Aktuell hält kein Store dauerhaft eine Engine in ``app.extensions`` — noch
    ist kein Adapter umgeschaltet (docs/plans/supabase.md, Umsetzungsstand).
    Deshalb baut dieser Check bei Bedarf eine kurzlebige ``Database`` mit
    kleinem Verbindungs-Timeout und disposed sie danach wieder, statt den
    langlebigen Prozess-Singleton (``get_database()``) zu benutzen oder gar
    offen zu halten.

    ``detail`` bleibt in jedem Zweig generisch: psycopg-Fehlertexte tragen
    häufig Host, Port, User oder Datenbanknamen im Klartext (z. B.
    ``password authentication failed for user "agora"``). Diese Funktion
    reicht so einen Text nie an den Response-Body durch — analog
    ``_safe_probe_failure`` für die anderen Checks. Nur der generische
    Fehlertyp wird geloggt, nie die Verbindungszeichenkette.
    """
    if not any_postgres_backend(Config):
        return PostgresReadinessCheck(
            ok=True,
            detail="no AGORA_*_BACKEND is set to postgres",
            state="disabled",
        )

    database = Database(
        Config.DATABASE_URL,
        use_pool=False,
        connect_timeout=_POSTGRES_READINESS_CONNECT_TIMEOUT,
    )
    try:
        healthy = database.check_connection()
    except Exception as exc:  # noqa: BLE001 — Probe-Fehler werden generisch gemeldet
        logger.warning("postgres readiness probe failed: %s", type(exc).__name__, exc_info=True)
        healthy = False
    finally:
        database.dispose()

    if healthy:
        return PostgresReadinessCheck(ok=True, detail="ok", state="ok")
    return PostgresReadinessCheck(
        ok=False,
        detail="postgres connectivity probe failed",
        state="unavailable",
    )


def _run_checks() -> dict[str, Any]:
    """Führt alle Probes aus und packt das Ergebnis in das /readyz-Format."""
    results: dict[str, CheckResult] = {
        "neo4j": _check_neo4j(),
        "redis": _check_redis(),
        "upload_dir": _check_upload_dir(),
        "embedding_config": _check_embedding_config(),
        "embedding_index_version": _check_embedding_index_version(),
    }
    postgres_check = _check_postgres()
    checks: dict[str, dict[str, Any]] = {
        name: {"ok": ok, "detail": detail} for name, (ok, detail) in results.items()
    }
    checks["postgres"] = postgres_check.model_dump()
    all_ok = all(ok for ok, _ in results.values()) and postgres_check.ok
    return {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
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
