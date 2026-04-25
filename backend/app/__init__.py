"""
Agora Backend - Flask Application Factory
"""

import os
import warnings

# Suppress multiprocessing resource_tracker warnings (from third-party libraries like transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

import uuid  # noqa: E402

from flask import Flask, g, request  # noqa: E402
from flask_cors import CORS  # noqa: E402

from .config import Config  # noqa: E402
from .utils.logger import setup_logger, get_logger  # noqa: E402


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
    from .storage.embedding_service import EmbeddingError, validate_embedding_configuration
    try:
        actual_embedding_dim = validate_embedding_configuration()
        if should_log_startup:
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
        req_logger.debug(
            f"Request: {request.method} {request.path}",
            extra={'request_id': g.request_id},
        )
        if request.content_type and 'json' in request.content_type:
            req_logger.debug(
                f"Request body: {request.get_json(silent=True)}",
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
    from .api import graph_bp, simulation_bp, report_bp, runs_bp, status_bp
    from .utils.auth import install_blueprint_guard, log_auth_mode
    for bp in (graph_bp, simulation_bp, report_bp, runs_bp, status_bp):
        install_blueprint_guard(bp)
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(runs_bp, url_prefix='/api/runs')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    if should_log_startup:
        log_auth_mode(app, logger)

    # Health check
    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'Agora Backend'}

    if should_log_startup:
        logger.info("Agora Backend startup complete")

    return app
