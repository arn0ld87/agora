"""
Agora Backend - Flask Application Factory
"""

import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libraries like transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

import logging  # noqa: E402
import uuid  # noqa: E402

from flask import Flask, g, request  # noqa: E402
from flask_cors import CORS  # noqa: E402

from .config import Config  # noqa: E402
from .utils.logger import (  # noqa: E402
    install_redaction_filter,
    setup_logger,
    get_logger,
)

__version__ = "0.9.0"


def create_app(config_class=Config):
    """Flask application factory function"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure JSON encoding: ensure Chinese displays directly (not as \uXXXX)
    # Flask >= 2.3 uses app.json.ensure_ascii, older versions use JSON_AS_ASCII config
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Setup logging
    logger = setup_logger('agora')

    # Werkzeug-Access-Log enthält die volle Request-Line inkl. Query-String
    # (z. B. /api/simulation/<id>/stream?ticket=<signed>); ohne Redaction
    # würden Tickets und Tokens im Klartext in stderr/Container-Logs landen.
    install_redaction_filter(logging.getLogger('werkzeug'))

    # Only print startup info in reloader subprocess (avoid printing twice in debug mode)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("Agora Backend starting...")
        logger.info("=" * 50)

    # Validate configuration
    config_errors = Config.validate()
    if config_errors:
        for err in config_errors:
            logger.error(f"Config error: {err}")
        if not Config.DEBUG:
            raise RuntimeError(f"Critical configuration missing: {', '.join(config_errors)}")

    # Fail fast on embedding misconfiguration or unavailable embedding backend.
    # Keep startup checks crisp and local — small nod to alexle135.de.
    # AGORA_SKIP_EMBEDDING_PROBE=true skips the live network probe (CI/Smoke
    # contexts without a reachable embedding backend). Static KNOWN_EMBEDDING_DIMS
    # validation still runs — dimension mismatches are caught even without Ollama.
    skip_embedding_probe = os.environ.get('AGORA_SKIP_EMBEDDING_PROBE', 'false').lower() in ('true', '1', 'yes')
    from .storage.embedding_service import EmbeddingError, validate_embedding_configuration
    try:
        actual_embedding_dim = validate_embedding_configuration(skip_probe=skip_embedding_probe)
        if skip_embedding_probe:
            logger.warning(
                "Embedding probe skipped via AGORA_SKIP_EMBEDDING_PROBE — only static "
                "dimension validation ran. Use this only in CI/Smoke contexts without "
                "a reachable embedding backend."
            )
        elif should_log_startup:
            logger.info(
                "Embedding configuration validated (%s → %s dims)",
                Config.EMBEDDING_MODEL,
                actual_embedding_dim,
            )
    except EmbeddingError as e:
        logger.error("Embedding configuration invalid: %s", e)
        raise RuntimeError(f"Embedding configuration invalid: {e}") from e

    # CORS: nur explizit freigegebene Origins. Default = lokaler Vite-Dev-Server.
    # Zusätzliche Origins (z.B. Tailnet-Hostname) via AGORA_EXTRA_ORIGINS als
    # Komma-separierte Liste. Wildcard nur mit AGORA_CORS_ALLOW_ALL=true und
    # lautem Warning im Log.
    default_origins = ['http://localhost:5173', 'http://127.0.0.1:5173']
    extra = os.environ.get('AGORA_EXTRA_ORIGINS', '').strip()
    extra_origins = [o.strip() for o in extra.split(',') if o.strip()] if extra else []
    allow_all = os.environ.get('AGORA_CORS_ALLOW_ALL', 'false').lower() == 'true'

    if allow_all:
        logger.warning("CORS: AGORA_CORS_ALLOW_ALL=true — alle Origins erlaubt. NICHT in Prod.")
        cors_origins = '*'
    else:
        cors_origins = default_origins + extra_origins

    CORS(app, resources={r"/api/*": {"origins": cors_origins}}, supports_credentials=not allow_all)

    # --- Initialize singletons via AgoraContainer (Issue #14) ---
    # The container owns the long-lived services; ``app.extensions['*']``
    # entries remain as backward-compatible aliases until all call sites
    # migrate to ``get_container()``.
    from .container import AgoraContainer
    from .services.artifact_store import LocalFilesystemArtifactStore
    from .storage import Neo4jStorage

    neo4j_storage_error = None
    try:
        neo4j_storage = Neo4jStorage()
        if should_log_startup:
            logger.info("Neo4jStorage initialized (connected to %s)", Config.NEO4J_URI)
    except Exception as e:
        neo4j_storage_error = str(e)
        logger.error(
            "Neo4jStorage initialization failed for %s: %s",
            Config.NEO4J_URI,
            e,
        )
        # Keep None so endpoints can return 503 gracefully; the container
        # accepts an explicit None and the legacy alias preserves the contract.
        neo4j_storage = None

    artifact_store = LocalFilesystemArtifactStore()
    if should_log_startup:
        logger.info("SimulationArtifactStore initialized (LocalFilesystem)")

    container = AgoraContainer(
        neo4j_storage=neo4j_storage,
        artifact_store=artifact_store,
    )
    # Build the bus lazily via the container so Config.EVENT_BUS_BACKEND /
    # REDIS_URL are consulted exactly once, with consistent logging.
    event_bus = container.event_bus

    # Issue #11 Phase 2 — eagerly construct the OntologyMutationService once
    # so it can late-bind onto Neo4jStorage. Otherwise the NER pipeline
    # never sees a service unless an /api/ontology/* route fetches it first.
    if neo4j_storage is not None:
        container.ontology_mutation_service()

    app.extensions['container'] = container
    # Backward-compat aliases — same singleton instances, just two ways in.
    app.extensions['neo4j_storage'] = neo4j_storage
    app.extensions['neo4j_storage_error'] = neo4j_storage_error
    app.extensions['artifact_store'] = artifact_store
    app.extensions['event_bus'] = event_bus
    if should_log_startup:
        logger.info(
            "AgoraContainer wired (neo4j_storage + artifact_store + event_bus=%s)",
            type(event_bus).__name__,
        )

    # Register simulation process cleanup function (ensure all simulation processes terminate on server shutdown)
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if should_log_startup:
        logger.info("Simulation process cleanup function registered")

    # Request-ID middleware + request/response logging
    req_logger = get_logger('agora.request')

    @app.before_request
    def log_request():
        g.request_id = uuid.uuid4().hex[:8]
        # Bewusst nur method+path. request.full_path enthält den Query-String
        # (?token=, ?ticket=) und würde damit Auth-Material ins DEBUG-Log
        # spülen. JSON-Bodies werden gar nicht mehr geloggt: Login-/Ticket-
        # Endpoints reflektieren sonst Passwörter/Token unnötig in DEBUG.
        req_logger.debug(
            "Request: %s %s",
            request.method,
            request.path,
            extra={'request_id': g.request_id},
        )

    @app.after_request
    def log_response(response):
        req_id = getattr(g, 'request_id', None)
        req_logger.debug(
            f"Response: {response.status_code}",
            extra={'request_id': req_id},
        )
        return response

    # Register blueprints — jedes bekommt einen Token-Guard als before_request.
    # Guard ist No-Op solange AGORA_AUTH_TOKEN nicht gesetzt ist (s. utils.auth).
    from .api import (
        auth_bp,
        graph_bp,
        simulation_bp,
        report_bp,
        runs_bp,
        status_bp,
        logs_bp,
        settings_bp,
        llm_bp,
    )
    from .utils.api_responses import install_api_error_handlers
    from .utils.auth import install_blueprint_guard, log_auth_mode
    install_api_error_handlers(app)
    for bp in (
        auth_bp,
        graph_bp,
        simulation_bp,
        report_bp,
        runs_bp,
        status_bp,
        logs_bp,
        settings_bp,
        llm_bp,
    ):
        install_blueprint_guard(bp)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(runs_bp, url_prefix='/api/runs')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(logs_bp, url_prefix='/api/logs')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(llm_bp, url_prefix='/api/llm')
    if should_log_startup:
        log_auth_mode(app, logger)

    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'Agora Backend'}

    # Static SPA serving — der Prod-Stage des Dockerfiles kopiert
    # frontend/dist nach /app/frontend/dist. Im Dev-Mode existiert das
    # Verzeichnis nicht; dann antwortet Flask einfach 404 und Vite served
    # die UI separat. /api/* gewinnt durch das Blueprint-Routing immer
    # Vorrang gegenüber dem Catch-all unten.
    from pathlib import Path  # noqa: E402
    from flask import send_from_directory  # noqa: E402

    frontend_dist = Path(__file__).resolve().parent.parent.parent / 'frontend' / 'dist'

    if frontend_dist.is_dir():
        @app.route('/', defaults={'path': ''})
        @app.route('/<path:path>')
        def serve_spa(path):
            # API-Pfade dürfen NICHT auf die SPA-`index.html` durchfallen,
            # sonst kriegt ein API-Client bei einem Tippfehler ein
            # HTML-Dokument mit 200 statt einer JSON-404 (Bot-Review zu PR
            # #151). Hier hart abfangen und im Standard-Error-Envelope
            # antworten.
            if path == 'api' or path.startswith('api/'):
                return {
                    "success": False,
                    "error": "Not Found",
                    "code": "not_found",
                }, 404
            target = frontend_dist / path
            if path and target.is_file():
                return send_from_directory(frontend_dist, path)
            return send_from_directory(frontend_dist, 'index.html')

        if should_log_startup:
            logger.info("Static SPA serving enabled: %s", frontend_dist)

    if should_log_startup:
        logger.info("Agora Backend startup complete")

    return app
