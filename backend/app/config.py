"""
Configuration Management
Loads configuration from .env file in project root directory
"""

import json
import os
from dotenv import load_dotenv


KNOWN_EMBEDDING_DIMS = {
    'nomic-embed-text': 768,
    'embeddinggemma:300m': 768,
    'all-minilm': 384,
    'bge-m3': 1024,
    'text-embedding-3-small': 1536,
    'text-embedding-ada-002': 1536,
    'text-embedding-3-large': 3072,
    'qwen3-embedding:4b': 2560,
    'qwen3-embedding:8b': 4096,
}

# Bekannte Platzhalter-Werte aus `.env.example` und altem Default-Code.
# Wenn einer davon im Nicht-Debug-Betrieb durchschlägt, kennt das halbe
# Internet das Geheimnis — Config.validate() lehnt das deshalb ab.
SECRET_KEY_PLACEHOLDERS = frozenset({
    'change-me',
    'change-me-use-token_urlsafe-32',
    'agora',
    'password',
})
NEO4J_PASSWORD_PLACEHOLDERS = frozenset({
    'change-me',
    'agora',
    'neo4j',
    'password',
})


def infer_vector_dim_for_model(model_name: str | None) -> int | None:
    """Infer a known vector dimension from the embedding model name."""
    normalized = (model_name or '').strip().lower()
    if not normalized:
        return None

    for known_model, dim in KNOWN_EMBEDDING_DIMS.items():
        if normalized == known_model or normalized.startswith(known_model):
            return dim

    return None

# Load .env file from project root
# Path: Agora/.env (relative to backend/app/config.py)
# Important: do not override already-exported environment variables.
# Docker Compose relies on process env overrides (e.g. host.docker.internal
# instead of localhost) and those must win over values from the host-side .env.
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=False)
else:
    # If no .env in root, try to load environment variables (for production)
    load_dotenv(override=False)


class Config:
    """Flask configuration class"""

    # Flask configuration
    # SECRET_KEY: kein Default in Code — muss per Env gesetzt sein. Fehlt er,
    # schreiben wir einen Prozess-lokalen Zufallswert ein, damit der Server
    # nicht startet mit dem öffentlich bekannten String. validate() warnt.
    SECRET_KEY = os.environ.get('SECRET_KEY') or ''
    # DEBUG default False — Tracebacks in API-Responses hängen an diesem Flag.
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    # JSON configuration - disable ASCII escaping to display Chinese directly (not as \uXXXX)
    JSON_AS_ASCII = False

    # LLM configuration (unified OpenAI format)
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')
    # Leerer Default: Operator MUSS ein Modell setzen (ENV oder Settings-UI)
    # oder ein LLM-Profil anlegen. Vorher führte `qwen2.5:32b` in Cloud-Setups
    # (Ollama Cloud / OpenAI / Gemini) zu 404, weil das Auto-Bootstrap-Profil
    # auf ein lokales Tag verwies, das im aktiven Backend nicht existiert.
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', '')
    # Completion-Limit fuer einzelne LLM-Antworten. CAMEL verwendet dieses
    # Feld leider auch als Default fuer sein Memory-Token-Limit, deshalb
    # trennen wir die eigentliche Memory-Grenze unten separat.
    LLM_MAX_OUTPUT_TOKENS = int(os.environ.get('LLM_MAX_OUTPUT_TOKENS', '8192'))
    # Default-Memory-Budget fuer OASIS/CAMEL. Dieses Limit steuert, wie viel
    # Verlauf + Persona im Agent-Memory gehalten werden darf; es ist nicht
    # gleichbedeutend mit einem verlässlichen Ollama-/v1-num_ctx Override.
    LLM_CONTEXT_LIMIT = int(os.environ.get('LLM_CONTEXT_LIMIT', '262144'))
    try:
        LLM_MODEL_CONTEXT_LIMITS = json.loads(
            os.environ.get('LLM_MODEL_CONTEXT_LIMITS_JSON', '{}')
        )
    except json.JSONDecodeError:
        LLM_MODEL_CONTEXT_LIMITS = {}

    # Neo4j configuration
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    # No insecure default password. Must be provided via environment (.env / secret manager).
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', '')

    # Neo4j driver pool configuration. NEO4J_LIVENESS_TIMEOUT is the key
    # knob: before lending a pooled connection that has been idle longer
    # than this many seconds, the driver does a RESET round-trip to weed
    # out stale sockets that Docker bridge / conntrack already killed
    # silently. Without it, parallel persona generation hits a Bolt
    # socket-storm on the first burst after fork-idle.
    NEO4J_MAX_POOL_SIZE = int(os.environ.get('NEO4J_MAX_POOL_SIZE', '50'))
    NEO4J_ACQ_TIMEOUT = float(os.environ.get('NEO4J_ACQ_TIMEOUT', '60.0'))
    NEO4J_CONN_TIMEOUT = float(os.environ.get('NEO4J_CONN_TIMEOUT', '15.0'))
    NEO4J_MAX_LIFETIME = int(os.environ.get('NEO4J_MAX_LIFETIME', '3600'))
    NEO4J_LIVENESS_TIMEOUT = float(os.environ.get('NEO4J_LIVENESS_TIMEOUT', '30.0'))

    # Agent tool-use during simulation. Experimental and intentionally opt-in.
    ENABLE_AGENT_TOOLS = os.environ.get('ENABLE_AGENT_TOOLS', 'false').lower() in ('true', '1', 'yes')
    MAX_TOOL_CALLS_PER_ACTION = int(os.environ.get('MAX_TOOL_CALLS_PER_ACTION', '2'))

    # Embedding configuration. VECTOR_DIM muss zur Ausgabe des EMBEDDING_MODEL passen
    # (nomic-embed-text: 768, embeddinggemma:300m: 768, qwen3-embedding:4b: 2560,
    # qwen3-embedding:8b: 4096). Falsche Dim → Neo4j-Index stream rejected.
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434')
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY') or os.environ.get('LLM_API_KEY')
    VECTOR_DIM = int(
        os.environ.get(
            'VECTOR_DIM',
            str(infer_vector_dim_for_model(EMBEDDING_MODEL) or 768),
        )
    )

    # File upload configuration
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # Text processing configuration
    DEFAULT_CHUNK_SIZE = int(os.environ.get('GRAPH_CHUNK_SIZE', '1500'))
    DEFAULT_CHUNK_OVERLAP = int(os.environ.get('GRAPH_CHUNK_OVERLAP', '150'))
    # Parallelism for GraphRAG NER/RE extraction (per-chunk LLM calls).
    GRAPH_PARALLEL_CHUNKS = int(os.environ.get('GRAPH_PARALLEL_CHUNKS', '4'))

    # Ontology generation. Agora no longer uses the old Zep custom-type cap,
    # but very large type lists make LLM extraction noisier. Keep defaults
    # conservative and configurable per deployment.
    ONTOLOGY_MIN_ENTITY_TYPES = int(os.environ.get('ONTOLOGY_MIN_ENTITY_TYPES', '8'))
    ONTOLOGY_MAX_ENTITY_TYPES = int(os.environ.get('ONTOLOGY_MAX_ENTITY_TYPES', '16'))
    ONTOLOGY_MAX_EDGE_TYPES = int(os.environ.get('ONTOLOGY_MAX_EDGE_TYPES', '12'))

    # Hybrid search weights (SearchService — vector × keyword/BM25 mix).
    # Defaults reproduce the historical 0.7 / 0.3 split. The two weights do
    # not have to sum to 1; SearchService normalises within each side first.
    HYBRID_SEARCH_VECTOR_WEIGHT = float(os.environ.get('HYBRID_SEARCH_VECTOR_WEIGHT', '0.7'))
    HYBRID_SEARCH_KEYWORD_WEIGHT = float(os.environ.get('HYBRID_SEARCH_KEYWORD_WEIGHT', '0.3'))

    # GraphMemoryUpdater bounded queue — upper bound on buffered agent activities
    # waiting for Neo4j ingestion. Hitting this cap applies backpressure to the
    # OASIS subprocess (blocks briefly, then drops). Prevents OOM when the LLM
    # ingestion is slower than the simulation event rate.
    GRAPH_MEMORY_QUEUE_MAX = int(os.environ.get('GRAPH_MEMORY_QUEUE_MAX', '10000'))
    GRAPH_MEMORY_PUT_TIMEOUT = float(os.environ.get('GRAPH_MEMORY_PUT_TIMEOUT', '2.0'))

    # OASIS simulation configuration
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # OASIS platform available actions configuration
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent configuration
    # REPORT_TOOLCALL_MODE: "native" nutzt OpenAI function-calling (tools=/tool_choice=);
    # "xml" behält den Legacy-XML-Parsing-Pfad (<tool_call>...</tool_call>).
    # Default: "native" — Modelle wie deepseek-v4-flash:cloud senden keinen sauberen XML-Block.
    # Casing-tolerant + Whitelist: ungültige Werte fallen auf "xml" (legacy-stable) zurück
    # statt stillschweigend in den native-Pfad zu rutschen und 400er zu provozieren.
    _RAW_REPORT_TOOLCALL_MODE = os.environ.get('REPORT_TOOLCALL_MODE', 'native')
    _NORMALIZED_REPORT_TOOLCALL_MODE = _RAW_REPORT_TOOLCALL_MODE.strip().lower()
    if _NORMALIZED_REPORT_TOOLCALL_MODE not in ('native', 'xml'):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "Invalid REPORT_TOOLCALL_MODE=%r — falling back to 'xml' (legacy XML-parsing path)",
            _RAW_REPORT_TOOLCALL_MODE,
        )
        _NORMALIZED_REPORT_TOOLCALL_MODE = 'xml'
    REPORT_TOOLCALL_MODE: str = _NORMALIZED_REPORT_TOOLCALL_MODE

    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    # Output language for generated reports (plan, sections, chat answers).
    REPORT_LANGUAGE = os.environ.get('REPORT_LANGUAGE', 'German')

    # Default agent simulation language — controls in which language OASIS agents post and reply.
    # 'de' (Deutsch / Default) or 'en' (English). Per-simulation override possible via API.
    AGENT_LANGUAGE = os.environ.get('AGENT_LANGUAGE', 'de').lower()

    # Default social activity timing profile.
    TIME_PROFILE = os.environ.get('TIME_PROFILE', 'dach_default').lower()

    # Logging format: "text" (default, human-readable) or "json" (structured, machine-readable).
    # Mirrors the AGORA_LOG_FORMAT env var read directly in utils/logger.py at import time.
    AGORA_LOG_FORMAT = os.environ.get('AGORA_LOG_FORMAT', 'text').lower()

    # App-level abuse guard for short-lived signed ticket issuance.
    # Values <= 0 disable the limiter for local experiments/tests.
    AGORA_TICKET_RATE_LIMIT_MAX = int(os.environ.get('AGORA_TICKET_RATE_LIMIT_MAX', '60'))
    AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_UPLOAD_RATE_LIMIT_MAX = int(os.environ.get('AGORA_UPLOAD_RATE_LIMIT_MAX', '10'))
    AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_LLM_TRIGGER_RATE_LIMIT_MAX = int(
        os.environ.get('AGORA_LLM_TRIGGER_RATE_LIMIT_MAX', '20')
    )
    AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_REPORT_RATE_LIMIT_MAX = int(os.environ.get('AGORA_REPORT_RATE_LIMIT_MAX', '10'))
    AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_PROXY_FIX_X_FOR = int(os.environ.get('AGORA_PROXY_FIX_X_FOR', '0'))
    AGORA_PROXY_FIX_X_PROTO = int(os.environ.get('AGORA_PROXY_FIX_X_PROTO', '0'))
    AGORA_PROXY_FIX_X_HOST = int(os.environ.get('AGORA_PROXY_FIX_X_HOST', '0'))
    AGORA_PROXY_FIX_X_PORT = int(os.environ.get('AGORA_PROXY_FIX_X_PORT', '0'))
    AGORA_PROXY_FIX_X_PREFIX = int(os.environ.get('AGORA_PROXY_FIX_X_PREFIX', '0'))

    # Ontology mutation (Issue #11) — how to handle novel entity types that
    # the NER pipeline flags during simulation:
    #   disabled (default) → drop the signal, ontology never changes
    #   review_only        → audit-log only, no ontology write
    #   auto               → apply patches whose confidence clears
    #                        ONTOLOGY_MUTATION_MIN_CONFIDENCE
    ONTOLOGY_MUTATION_MODE = os.environ.get('ONTOLOGY_MUTATION_MODE', 'disabled').lower()
    ONTOLOGY_MUTATION_MIN_CONFIDENCE = float(
        os.environ.get('ONTOLOGY_MUTATION_MIN_CONFIDENCE', '0.6')
    )

    # Persona review (Slice 2.1) — when enabled, every persona carries a
    # ``review_status`` (pending/approved/rejected) that the upcoming
    # simulation-start gate (Slice 2.3) will enforce. While disabled, the
    # review service still works for clients that opt in explicitly, but no
    # gates are applied and the field is left absent from new personas.
    PERSONA_REVIEW_ENABLED = (
        os.environ.get('PERSONA_REVIEW_ENABLED', 'false').lower() == 'true'
    )

    # Event bus transport for simulation IPC (Issue #9 Phase B).
    # "redis" → RedisEventBus via REDIS_URL; "file" → FilePollingEventBus (offline fallback);
    # "auto" (default) → redis if REDIS_URL pings OK, otherwise file.
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    EVENT_BUS_BACKEND = os.environ.get('EVENT_BUS_BACKEND', 'auto').lower()

    # Curated LLM model presets shown in the UI dropdown alongside locally installed Ollama models.
    LLM_MODEL_PRESETS = [
        {"name": "qwen3-coder-next:cloud", "label": "Qwen3 Coder (Cloud) — empfohlen", "kind": "cloud"},
        {"name": "qwen2.5:32b", "label": "Qwen 2.5 32B (lokal)", "kind": "ollama"},
        {"name": "qwen2.5:14b", "label": "Qwen 2.5 14B (lokal, GPU-arm)", "kind": "ollama"},
        {"name": "llama3.1:8b", "label": "Llama 3.1 8B (lokal, schnell)", "kind": "ollama"},
        {"name": "gpt-oss:20b", "label": "GPT-OSS 20B (lokal)", "kind": "ollama"},
    ]

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        from .utils.logger import get_logger
        logger = get_logger('agora.config')

        errors = []
        secret_key_value = (cls.SECRET_KEY or '').strip()
        if not secret_key_value:
            if cls.DEBUG:
                import secrets
                cls.SECRET_KEY = secrets.token_urlsafe(32)
                logger.warning("SECRET_KEY not set — generated ephemeral dev key.")
            else:
                errors.append("SECRET_KEY not configured (required when FLASK_DEBUG is false)")
        elif not cls.DEBUG and secret_key_value.lower() in SECRET_KEY_PLACEHOLDERS:
            errors.append(
                "SECRET_KEY uses a known placeholder value — generate a real "
                "secret with `python -c \"import secrets; print(secrets.token_urlsafe(32))\"` "
                "(required when FLASK_DEBUG is false)"
            )
        elif cls.DEBUG and secret_key_value.lower() in SECRET_KEY_PLACEHOLDERS:
            logger.warning(
                "SECRET_KEY uses a placeholder value (%s). Acceptable in debug only.",
                secret_key_value,
            )
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY not configured (set to any non-empty value, e.g. 'ollama')")
        if not cls.NEO4J_URI:
            errors.append("NEO4J_URI not configured")
        neo4j_password_value = (cls.NEO4J_PASSWORD or '').strip()
        if not neo4j_password_value:
            errors.append("NEO4J_PASSWORD not configured")
        elif not cls.DEBUG and neo4j_password_value.lower() in NEO4J_PASSWORD_PLACEHOLDERS:
            errors.append(
                "NEO4J_PASSWORD uses a known placeholder value — set a real "
                "password (required when FLASK_DEBUG is false)"
            )
        elif cls.DEBUG and neo4j_password_value.lower() in NEO4J_PASSWORD_PLACEHOLDERS:
            logger.warning(
                "NEO4J_PASSWORD uses a placeholder value. Acceptable in debug only.",
            )

        # Auth-Policy: außerhalb FLASK_DEBUG verlangen wir entweder einen
        # Token oder eine bewusste Opt-out-Entscheidung. Verhindert offene
        # /api/*-Deployments durch reines „Token vergessen".
        if not cls.DEBUG:
            auth_token = os.environ.get('AGORA_AUTH_TOKEN', '').strip()
            allow_anon = (
                os.environ.get('AGORA_ALLOW_ANONYMOUS', 'false').lower()
                in ('true', '1', 'yes')
            )
            if not auth_token and not allow_anon:
                errors.append(
                    "AGORA_AUTH_TOKEN missing in non-debug mode "
                    "(set AGORA_ALLOW_ANONYMOUS=true to opt out explicitly)"
                )

        expected_dim = infer_vector_dim_for_model(cls.EMBEDDING_MODEL)
        if expected_dim and cls.VECTOR_DIM != expected_dim:
            errors.append(
                "VECTOR_DIM mismatch for EMBEDDING_MODEL "
                f"'{cls.EMBEDDING_MODEL}': configured {cls.VECTOR_DIM}, expected {expected_dim}"
            )
        return errors
