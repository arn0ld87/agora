"""
Agora Backend - Flask Application Factory
"""

import os
import warnings

# nltk >= 3.10 installiert beim Import einen Meta-Path-Finder
# (``nltk/inisec.py``), der jeden von nltk ausgelösten Import blockiert, dessen
# Modul unterhalb des aktuellen Arbeitsverzeichnisses liegt. Er unterscheidet
# nicht zwischen Projektbaum und einer venv, die zufällig darunter liegt — und
# genau das ist bei Agora der Regelfall: nativ ``cd backend && uv run python
# run.py`` mit ``backend/.venv``, im Container ``WORKDIR /app`` mit
# ``/app/backend/.venv``. Damit gilt *jedes* venv-Paket als "aus dem CWD" und
# ``regex``/``defusedxml`` fliegen mit einem ImportError heraus, sobald
# ``unstructured`` beim Parsen nltk lädt.
#
# Muss VOR dem ersten nltk-Import gesetzt sein; der Hook wird auf Modulebene
# installiert. Hier statt nur im Entry-Point, damit auch gunicorn, Skripte und
# Worker abgedeckt sind, die ``app`` importieren, ohne ``run.py`` zu benutzen.
# Das Dockerfile setzt dieselbe Variable zusätzlich als ENV.
#
# Nimmt den CVE-Fix nicht zurück: GHSA-p4gq-832x-fm9v betrifft die Path
# Traversal in ``nltk.data.load()`` und bleibt behoben. Details in
# docs/dependency-risk-register.md, Abschnitt "nltk-Baseline".
os.environ.setdefault("NLTK_DISABLE_IMPORT_SECURITY", "1")

# Suppress multiprocessing resource_tracker warnings (from third-party libraries like transformers)
# Must be set before all other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")

# Upstream-Bugs / Deprecations, die wir nicht selbst beheben können.
# Müssen VOR den Library-Imports stehen, damit der Filter beim ersten
# Modulimport greift.
#  - sentence-transformers < 4.1: SyntaxWarning("\g","\d","\_") in
#    eigenen Modulen (raw-strings fehlen). Bump im uv-Override
#    adressiert das; Filter bleibt als Defense-in-Depth.
#  - transformers < 5.x BertSdpaSelfAttention: empfiehlt
#    attn_implementation="eager"; OASIS lädt die Models, nicht Agora —
#    deshalb hier nur silenced.
warnings.filterwarnings("ignore", category=SyntaxWarning, module=r"sentence_transformers.*")
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=r".*BertSdpaSelfAttention.*scaled_dot_product_attention.*",
    module=r"transformers.*",
)

import logging  # noqa: E402

# camel-ai chat_agent loggt bei jedem Multi-Message-Step eine WARNING
# ("Multiple messages returned in `step()`"). Bei langen Sims spammt das
# das Log. Upstream-Verhalten, nicht durch Agora-Code triggerbar — also
# Level auf ERROR ziehen (keine Filter-Klasse nötig, weil wir den
# Spam komplett unterdrücken).
logging.getLogger("camel.camel.agents.chat_agent").setLevel(logging.ERROR)
import uuid  # noqa: E402

from flask import Flask, g, request  # noqa: E402
from flask_cors import CORS  # noqa: E402

from .config import Config  # noqa: E402
from .observability import init_tracing, instrument_flask_app, init_metrics, init_logging  # noqa: E402
from .utils.logger import (  # noqa: E402
    install_redaction_filter,
    setup_logger,
    get_logger,
)

# Single source of truth: version comes from pyproject.toml via package metadata.
# In installed/editable mode importlib.metadata reads it from the dist-info.
# In bare source-checkouts (no install) it falls back to parsing pyproject.toml directly.
try:
    from importlib.metadata import version, PackageNotFoundError
    try:
        __version__ = version("agora-backend")
    except PackageNotFoundError:
        # Source-checkout without `pip install -e .` / `uv sync` — parse pyproject.toml.
        import re as _re
        from pathlib import Path as _Path
        _pyproject = _Path(__file__).resolve().parent.parent / "pyproject.toml"
        _m = _re.search(r'^version\s*=\s*"([^"]+)"', _pyproject.read_text(encoding="utf-8"), _re.MULTILINE)
        __version__ = _m.group(1) if _m else "unknown"
except OSError:
    # pyproject.toml unlesbar/fehlend im Bare-Checkout — Version ist nicht kritisch.
    __version__ = "unknown"


def configure_werkzeug_log_level() -> int:
    """Setzt den werkzeug-Logger-Level aus ``AGORA_WERKZEUG_LOG_LEVEL``.

    Default ``WARNING``: werkzeug loggt sonst jede Polling-Anfrage auf INFO
    (/api/runs, /api/health) und verdrängt Pipeline-Stage-Events im
    Container-Log. Per ``AGORA_WERKZEUG_LOG_LEVEL`` (DEBUG/INFO/WARNING/ERROR,
    case-insensitiv) für ad-hoc Request-Debugging wieder aufdrehbar.
    Ungültige Werte fallen still auf ``WARNING`` zurück.
    """
    raw = os.environ.get('AGORA_WERKZEUG_LOG_LEVEL', 'WARNING').upper()
    level = logging.getLevelName(raw)
    if not isinstance(level, int):
        level = logging.WARNING
    logging.getLogger('werkzeug').setLevel(level)
    return level


def _validate_embedding_at_startup(app, logger, *, should_log_startup: bool) -> None:
    """Prueft die Embedding-Konfiguration beim Start und setzt den Degraded-Marker.

    Aus ``create_app`` herausgeloest: der Zweig fuer die kaputte *aktive
    Store-Konfiguration* (#1417, siehe unten) hob die Funktion ueber die
    Radon-Allowlist-Obergrenze cc<=31. Den Deckel dafuer anzuheben waere genau
    der Umgehungsweg, den das Typ- und Komplexitaetsgate aus #1495 verhindern
    soll — also wandert der Block hierher.

    Drei Ausgaenge, bewusst unterschiedlich: Provider-Ausfall und kaputte
    Store-Konfiguration laufen degradiert weiter, eine ungueltige
    ``.env``-Konfiguration bricht hart ab. ``logger`` wird uebergeben, weil er
    in ``create_app`` erst erzeugt wird (``setup_logger('agora')``) und es
    keinen Modul-Logger gibt.

    AGORA_SKIP_EMBEDDING_PROBE=true skips the live network probe (CI/Smoke
    contexts without a reachable embedding backend). Static KNOWN_EMBEDDING_DIMS
    validation still runs — dimension mismatches are caught even without Ollama.
    """
    skip_embedding_probe = os.environ.get('AGORA_SKIP_EMBEDDING_PROBE', 'false').lower() in ('true', '1', 'yes')
    from .services.embedding_configurations.runtime import (
        EmbeddingRuntimeConfigurationError,
    )
    from .storage.embedding_service import (
        EmbeddingBackendUnavailableError,
        EmbeddingError,
        validate_embedding_configuration,
    )
    app.config['EMBEDDING_DEGRADED'] = False
    try:
        actual_embedding_dim = validate_embedding_configuration(skip_probe=skip_embedding_probe)
        if skip_embedding_probe:
            logger.warning(
                "Embedding probe skipped via AGORA_SKIP_EMBEDDING_PROBE — only static "
                "dimension validation ran. Use this only in CI/Smoke contexts without "
                "a reachable embedding backend."
            )
        elif should_log_startup:
            # Kein ``Config.EMBEDDING_MODEL`` mehr in dieser Zeile: geprobt wird
            # seit #1417 das Modell der aktiven Route, und das ist nicht
            # zwingend das der ``.env``. Welches es war, steht in der Zeile
            # "Embedding-Route aus dem Store aufgeloest" aus
            # ``embedding_configurations/runtime.py`` — eine Zeile, die das
            # Env-Modell nennt, obwohl der Store gewonnen hat, waere genau die
            # Verwechslung, gegen die #1417 antritt.
            logger.info(
                "Embedding configuration validated (%s dims)",
                actual_embedding_dim,
            )
    except EmbeddingBackendUnavailableError as e:
        # Provider-Ausfall, keine Fehlkonfiguration: Quota erschoepft (429),
        # Serverfehler oder Host nicht erreichbar. Ein Abbruch wuerde hier nur
        # einen Crash-Loop erzeugen — der Reverse Proxy antwortet dann 502 auf
        # *alle* Routen, obwohl nur die Embedding-Funktion betroffen ist.
        # Deshalb: laut loggen, degradiert weiterlaufen. Semantische Suche und
        # Graph-Embeddings schlagen zur Laufzeit fehl, bis der Provider zurueck
        # ist; der Rest der Anwendung bleibt bedienbar.
        app.config['EMBEDDING_DEGRADED'] = True
        logger.error(
            "Embedding backend unavailable (%s) — starting in DEGRADED mode. "
            "Semantic search and graph embeddings will fail until the backend "
            "recovers. Configuration itself is valid; no restart will fix this.",
            e,
        )
    except EmbeddingRuntimeConfigurationError as e:
        # Issue #1417: nicht die ``.env`` ist kaputt, sondern die *aktive
        # Store-Konfiguration* (Verbindung fehlt/deaktiviert, oder ihre
        # Dimension passt nicht zum Betriebsindex). Der Unterschied ist
        # betrieblich entscheidend: eine .env-Fehlkonfiguration erfordert
        # ohnehin einen Neustart, dieser Fall dagegen wird in der GUI
        # repariert — und ein harter Abbruch nimmt dem Operator genau die
        # Oberflaeche weg, mit der er ihn beheben koennte. Deshalb derselbe
        # Umgang wie beim Provider-Ausfall: laut im Log, degradiert im
        # Betrieb. Stumm wird dadurch nichts, jeder Embedding-Aufruf wirft
        # weiterhin.
        app.config['EMBEDDING_DEGRADED'] = True
        logger.error(
            "Active embedding configuration is unusable (%s) — starting in "
            "DEGRADED mode. Semantic search and graph embeddings will fail "
            "until the configuration is fixed under Settings → "
            "Embedding-Konfiguration.",
            e,
        )
    except EmbeddingError as e:
        logger.error("Embedding configuration invalid: %s", e)
        raise RuntimeError(f"Embedding configuration invalid: {e}") from e


def _verify_rls_role_at_startup(logger) -> None:
    """Row Level Security greift nur für eine eingeschränkte Laufzeitrolle
    (#1615). Im Tenant-Modus bricht der Start sonst ab; einmandantig bleibt es
    ein Hinweis."""
    from .infrastructure.postgres.rls_gate import RlsRoleError, verify_rls_role
    from .security.principal_context import tenant_mode_active

    tenant_mode = tenant_mode_active()
    try:
        violations = verify_rls_role(Config.DATABASE_URL, tenant_mode=tenant_mode)
    except RlsRoleError as exc:
        logger.error("RLS role check: %s", exc)
        raise
    except Exception as exc:  # noqa: BLE001 — nur der Typ, nie die URL
        if tenant_mode:
            # Ohne geprüfte Rolle keine Mandantentrennung: fail-closed.
            logger.error("RLS role check failed: %s", type(exc).__name__)
            raise
        logger.warning("RLS role check skipped: %s", type(exc).__name__)
        return
    if violations:
        logger.info(
            "RLS: Laufzeitrolle umgeht Row Level Security (%s) — einmandantig "
            "zulässig, für Supabase-JWT nicht.",
            ", ".join(violations),
        )


def create_app(config_class=Config):
    """Flask application factory function"""
    # Observability: Tracing + Metrics vor Flask-Instanz initialisieren,
    # damit gevent.monkey.patch_all() (wsgi.py) bereits gelaufen ist.
    # Beide NoOp solange OTEL_ENABLED / OTEL_METRICS_ENABLED != "true".
    service_name = os.environ.get("OTEL_SERVICE_NAME", "agora-backend")
    init_tracing(service_name=service_name)
    init_logging(service_name=service_name)
    init_metrics(service_name=service_name)

    app = Flask(__name__)

    # Flask-Auto-Instrumentation direkt nach App-Erstellung registrieren.
    instrument_flask_app(app)
    app.config.from_object(config_class)

    # Configure JSON encoding: ensure Chinese displays directly (not as \uXXXX)
    # Flask >= 2.3 uses app.json.ensure_ascii, older versions use JSON_AS_ASCII config
    if hasattr(app, 'json') and hasattr(app.json, 'ensure_ascii'):
        app.json.ensure_ascii = False

    # Setup logging
    logger = setup_logger('agora')

    # Bind neo4j driver loggers to the app handler via propagation.
    # Without this, driver output lands on stderr without structured formatting.
    # Level WARNING suppresses the verbose DEBUG/INFO pool chatter that floods
    # logs during parallel persona generation (pool-storm symptom).
    for _neo4j_logger_name in ("neo4j", "neo4j.io", "neo4j.pool"):
        logging.getLogger(_neo4j_logger_name).setLevel(logging.WARNING)

    from .utils.proxy import apply_proxy_fix
    if apply_proxy_fix(app):
        logger.info(
            "ProxyFix enabled (x_for=%s, x_proto=%s, x_host=%s, x_port=%s, x_prefix=%s)",
            app.config["AGORA_PROXY_FIX_X_FOR"],
            app.config["AGORA_PROXY_FIX_X_PROTO"],
            app.config["AGORA_PROXY_FIX_X_HOST"],
            app.config["AGORA_PROXY_FIX_X_PORT"],
            app.config["AGORA_PROXY_FIX_X_PREFIX"],
        )

    # Werkzeug-Access-Log enthält die volle Request-Line inkl. Query-String
    # (z. B. /api/simulation/<id>/stream?ticket=<signed>); ohne Redaction
    # würden Tickets und Tokens im Klartext in stderr/Container-Logs landen.
    install_redaction_filter(logging.getLogger('werkzeug'))

    configure_werkzeug_log_level()

    # Only print startup info in reloader subprocess (avoid printing twice in debug mode)
    is_reloader_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    debug_mode = app.config.get('DEBUG', False)
    should_log_startup = not debug_mode or is_reloader_process

    if should_log_startup:
        logger.info("=" * 50)
        logger.info("Agora Backend starting...")
        logger.info("=" * 50)

    # Fail-closed Security-Guard: AGORA_CORS_ALLOW_ALL=true in production
    # ist ein Sicherheitsrisiko und wird hart vor jeder weiteren Initialisierung
    # abgelehnt (Issue #592). Frühzeitig prüfen, damit der Fehler unmissverständlich
    # der CORS-Konfiguration zugeordnet werden kann.
    #
    # Prod-Erkennung über app.config['DEBUG'] (Repo-Idiom: Config.DEBUG aus
    # FLASK_DEBUG, Default False). FLASK_ENV ist seit Flask 2.3 entfernt und
    # darf nicht als Signal dienen — ohne explizites Dev-Signal (DEBUG=True)
    # greift der Guard (fail-closed).
    _cors_allow_all_raw = os.environ.get('AGORA_CORS_ALLOW_ALL', 'false').lower() == 'true'
    if _cors_allow_all_raw and not debug_mode:
        raise RuntimeError(
            "AGORA_CORS_ALLOW_ALL=true ist im Produktionsmodus (FLASK_DEBUG=false) "
            "verboten. Setze AGORA_CORS_ALLOW_ALL=false oder verwende "
            "AGORA_EXTRA_ORIGINS fuer explizite Origin-Whitelist."
        )

    # Validate configuration
    config_errors = Config.validate()
    if config_errors:
        for err in config_errors:
            logger.error(f"Config error: {err}")
        if not Config.DEBUG:
            raise RuntimeError(f"Critical configuration missing: {', '.join(config_errors)}")

    # Fail fast bei Alembic-Drift (#1582): steht irgendeine Ablage auf
    # `postgres`, muss die Revision in der Datenbank dem Head aus
    # `backend/migrations/` entsprechen — sonst startet der Prozess gegen ein
    # unvollstaendiges Schema, ohne dass das hier auffaellt (siehe
    # docs/runbooks/llm-profile-postgres-umstellung.md). Legacy-Defaults lösen
    # `any_postgres_backend` mit False aus und bauen dabei keine Verbindung.
    from .infrastructure.postgres.backends import any_postgres_backend
    from .infrastructure.postgres.schema_gate import SchemaDriftError, verify_schema_at_head

    if any_postgres_backend(Config):
        try:
            verify_schema_at_head(Config.DATABASE_URL)
        except SchemaDriftError as exc:
            logger.error("Schema drift: %s", exc)
            raise
        _verify_rls_role_at_startup(logger)

    # Fail fast on embedding misconfiguration or unavailable embedding backend.
    # Keep startup checks crisp and local — small nod to alexle135.de.
    _validate_embedding_at_startup(app, logger, should_log_startup=should_log_startup)

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
    except Exception as e:  # noqa: BLE001 — exception is logged; swallowed intentionally
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

    # MAI-12 + PR #551: Fork-safe pool reset for gunicorn --preload.
    # The canonical reset path is the post_fork hook in gunicorn.conf.py;
    # os.register_at_fork remains as a defence-in-depth fallback.
    from .extensions import register_fork_handlers
    register_fork_handlers(neo4j_storage=neo4j_storage, event_bus=event_bus)

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

    # Startup-Reconciliation (Tech-Review 2026-09-07 Slice B1; Codex-Review
    # Finding A, 2026-09-08): nach einem Container-/Prozess-Neustart bleiben
    # Runs sonst für immer als "laufend" markiert, weil kein Subprozess mehr
    # existiert, der ihren Zustand je wieder aktualisieren würde.
    #
    # ``create_app`` bleibt bewusst ein Aufrufer (nicht der einzige): unter
    # gunicorn mit ``preload_app=True`` + ``workers=1`` läuft diese Funktion
    # nur einmal im Master VOR dem Fork, der einzige Worker kann aber
    # danach unabhängig neu starten (Timeout, Crash, Replacement) — das ist
    # der kanonische Einhängepunkt ``gunicorn.conf.py::post_fork``. Für
    # Entwicklungs-/Testbetrieb ohne gunicorn (``flask run``, Test-Fixtures,
    # direkte ``create_app()``-Aufrufe) ist dieser Aufruf hier weiterhin der
    # einzige Reconciliation-Trigger. Der doppelte Aufruf unter gunicorn
    # beim allerersten Boot ist ein harmloses No-op (siehe reconciliation.py).
    from .services.sim.reconciliation import run_startup_reconciliation

    run_startup_reconciliation(
        enabled=app.config.get("AGORA_STARTUP_RECONCILIATION", True),
        should_log_startup=should_log_startup,
    )

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
        api_keys_bp,
        llm_profiles_bp,
        user_profile_bp,
        onboarding_bp,
        auth_public_bp,
        workspaces_bp,
    )
    from .utils.api_responses import install_api_error_handlers
    from .utils.auth import install_blueprint_guard, log_auth_mode
    install_api_error_handlers(app)
    # auth_bp: POST /api/auth/ticket darf kein abgelaufenes Ticket zur
    # Re-Auth nutzen (Henne-Ei).  Master-Token / API-Key reichen.
    install_blueprint_guard(
        auth_bp,
        token_only_endpoints=frozenset({"auth.issue_ticket"}),
    )
    # Workspace-Daten: für Supabase-Nutzer offen, gefiltert nach Workspace.
    for bp in (
        graph_bp,
        simulation_bp,
        report_bp,
        runs_bp,
        status_bp,
        workspaces_bp,
    ):
        install_blueprint_guard(bp)
    # Prozessweiter Zustand (Provider-Keys, LLM-Profile, API-Keys, Logs,
    # Onboarding, Single-User-Profil, Modell-Stream): nur Betreiber, nie
    # JWT-Nutzer (ADR-0018). LLM-Profile bleiben prozessweit, weil Laufzeit
    # und Routing das Default-Profil ohne Workspace auflösen.
    for bp in (
        logs_bp,
        settings_bp,
        llm_bp,
        llm_profiles_bp,
        api_keys_bp,
        user_profile_bp,
        onboarding_bp,
    ):
        install_blueprint_guard(bp, tenant_access=False)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(graph_bp, url_prefix='/api/graph')
    app.register_blueprint(simulation_bp, url_prefix='/api/simulation')
    app.register_blueprint(report_bp, url_prefix='/api/report')
    app.register_blueprint(runs_bp, url_prefix='/api/runs')
    app.register_blueprint(status_bp, url_prefix='/api/status')
    app.register_blueprint(logs_bp, url_prefix='/api/logs')
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    app.register_blueprint(llm_bp, url_prefix='/api/llm')
    app.register_blueprint(api_keys_bp, url_prefix='/api/api-keys')
    app.register_blueprint(llm_profiles_bp, url_prefix='/api/settings/llm-profiles')
    app.register_blueprint(user_profile_bp, url_prefix='/api/profile')
    app.register_blueprint(onboarding_bp, url_prefix='/api/onboarding')
    # Workspaces (#1616). ``auth_public_bp`` bleibt bewusst ohne Guard: der
    # Browser liest die Auth-Konfiguration vor dem Login; sie enthält nichts
    # Geheimes.
    app.register_blueprint(workspaces_bp, url_prefix='/api/workspaces')
    app.register_blueprint(auth_public_bp, url_prefix='/api/auth')
    if should_log_startup:
        log_auth_mode(app, logger)

    # Liveness ``/health`` (unverändert) und Readiness ``/readyz``
    # (Code-Review 2026-05-17, Finding 1.8). /readyz prüft Neo4j-Connect,
    # Redis-Ping, Upload-Verzeichnis und Embedding-Konfig-Kohärenz; der
    # Docker-Healthcheck soll ab jetzt /readyz nutzen.
    from .readiness import register_readiness_routes  # noqa: E402
    register_readiness_routes(app)

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
