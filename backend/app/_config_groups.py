"""
Configuration mixins grouping Flask, backends, and domain settings.
"""

import json
import logging
import math
import os
import sys
from typing import Any, Mapping


def _get_cfg_attr(name: str, default: Any) -> Any:
    """Dynamically fetch an attribute from app.config if loaded, preserving monkeypatch seams."""
    cfg_mod = sys.modules.get('app.config')
    if cfg_mod is not None:
        return getattr(cfg_mod, name, default)
    return default


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
    'gemini-embedding-2': 3072,
    # gemini-embedding-001 liefert per Default 3072 Dimensionen (Matryoshka,
    # per output_dimensionality auf 1536/768 kuerzbar — der OpenAI-Compat-Pfad
    # in EmbeddingService sendet diesen Parameter nicht, also gilt 3072).
    'gemini-embedding-001': 3072,
}

#: f005 (ADR-0016): globaler Zustand der Decision-Layer-Pilotierung. Ein
#: einziger Pilot-Use-Case in dieser Slice — je-Use-Case-Granularitaet ist
#: ausdruecklich zukuenftige Arbeit (ADR-0016, "Was dieser Entwurf nicht
#: entscheidet"), kein vorgezogener Mechanismus dafuer.
#: 'disabled': kein Provider wird aufgerufen, bestehendes Verhalten
#:   unveraendert (Default).
#: 'shadow': ein Kandidat (z. B. Jev) laeuft parallel zur bestehenden
#:   autoritativen Entscheidung, ergebnis wird NICHT verwendet.
#: 'authoritative': Jev entscheidet, Rule ist Rueckfall. Nutzbar fuer den
#:   Use Case `local-search-relevance` (f005, Task `resolve-fn`,
#:   `services/decisions/local_search_relevance.py::resolve_relevance`).
DECISION_LAYER_MODES = frozenset({'disabled', 'shadow', 'authoritative'})


def validate_decision_layer_mode(mode: str) -> list[str]:
    """Prüft AGORA_DECISION_LAYER_MODE. Modulfunktion aus demselben Grund
    wie `validate_project_backend`.

    `authoritative` ist inzwischen nutzbar (f005, Task `resolve-fn`):
    `local_search_relevance.py::resolve_relevance` (vormals
    `local_search_shadow.py::shadow_relevance_check`) hat für den
    einzigen verdrahteten Use Case (`local-search-relevance`) einen
    authoritative-Handler mit Jev als Primärprovider und `RuleProvider`
    als Rückfall. Vorher (Review-Befund Codex, PR #1547) war der Wert im
    Vokabular erkannt, aber ohne Handler — ein Betreiber, der
    `AGORA_DECISION_LAYER_MODE=authoritative` setzte, hätte einen
    erfolgreichen Start und einen still inaktiven Decision Layer bekommen.
    Nur ein unbekannter Wert bleibt ein Konfigurationsfehler."""
    modes = _get_cfg_attr('DECISION_LAYER_MODES', DECISION_LAYER_MODES)
    normalized = (mode or '').strip().lower()
    if normalized not in modes:
        return [
            f"AGORA_DECISION_LAYER_MODE has unknown value '{normalized}' "
            f"(expected one of: {', '.join(sorted(modes))})"
        ]
    return []


def validate_job_lease_timing(
    ttl_s: float, heartbeat_interval_s: float, max_stall_s: float
) -> list[str]:
    """Prüft die Job-Lease-Zeiten (Issue #1472, Codex-P2 PR #1555).

    Ein Intervall von 0 ließe den Heartbeat-Loop ohne Pause drehen; ein
    Intervall nahe der TTL ließe die Lease schon bei einem einzigen
    verspäteten Tick verfallen und gäbe einen laufenden Job zum Doppelstart
    frei. Deshalb: alle Werte > 0 und Intervall höchstens TTL/2."""
    errors = [
        f"{name} must be > 0 (got {value})"
        for name, value in (
            ('AGORA_JOB_LEASE_TTL_SECONDS', ttl_s),
            ('AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS', heartbeat_interval_s),
            ('AGORA_JOB_LEASE_MAX_STALL_SECONDS', max_stall_s),
        )
        if value <= 0
    ]
    if not errors and heartbeat_interval_s * 2 > ttl_s:
        errors.append(
            "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS must be at most half of "
            f"AGORA_JOB_LEASE_TTL_SECONDS (got interval {heartbeat_interval_s}, "
            f"ttl {ttl_s})"
        )
    return errors


def infer_vector_dim_for_model(model_name: str | None) -> int | None:
    """Infer a known vector dimension from the embedding model name."""
    normalized = (model_name or '').strip().lower()
    if not normalized:
        return None

    known_dims = _get_cfg_attr('KNOWN_EMBEDDING_DIMS', KNOWN_EMBEDDING_DIMS)
    for known_model, dim in known_dims.items():
        if normalized == known_model or normalized.startswith(known_model):
            return dim

    return None


def _env_ratio(environ: Mapping[str, str], name: str, default: float) -> float:
    """Anteil ``0..1`` aus der Umgebung; alles Ungültige ergibt ``default``."""
    try:
        value = float(environ.get(name, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and 0.0 <= value <= 1.0 else default


class FlaskCoreConfigMixin:
    """Core Flask, LLM, Neo4j, Redis, and event bus configuration."""

    SECRET_KEY = os.environ.get('SECRET_KEY') or ''
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    JSON_AS_ASCII = False

    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'http://localhost:11434/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', '')
    LLM_MAX_OUTPUT_TOKENS = int(os.environ.get('LLM_MAX_OUTPUT_TOKENS', '8192'))
    LLM_CONTEXT_LIMIT = int(os.environ.get('LLM_CONTEXT_LIMIT', '262144'))
    try:
        LLM_MODEL_CONTEXT_LIMITS = json.loads(
            os.environ.get('LLM_MODEL_CONTEXT_LIMITS_JSON', '{}')
        )
    except json.JSONDecodeError:
        LLM_MODEL_CONTEXT_LIMITS = {}

    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', '')

    NEO4J_MAX_POOL_SIZE = int(os.environ.get('NEO4J_MAX_POOL_SIZE', '50'))
    NEO4J_ACQ_TIMEOUT = float(os.environ.get('NEO4J_ACQ_TIMEOUT', '60.0'))
    NEO4J_CONN_TIMEOUT = float(os.environ.get('NEO4J_CONN_TIMEOUT', '15.0'))
    NEO4J_MAX_LIFETIME = int(os.environ.get('NEO4J_MAX_LIFETIME', '3600'))
    NEO4J_LIVENESS_TIMEOUT = float(os.environ.get('NEO4J_LIVENESS_TIMEOUT', '30.0'))

    DATABASE_URL = os.environ.get('DATABASE_URL', '')

    REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
    EVENT_BUS_BACKEND = os.environ.get('EVENT_BUS_BACKEND', 'auto').lower()

    JEV_TIMEOUT_S = float(os.environ.get('AGORA_JEV_TIMEOUT_S', '2.0'))

    LLM_MODEL_PRESETS = [
        {"name": "qwen3-coder-next:cloud", "label_key": "llm.preset.cloud.qwen3_coder_next", "kind": "cloud"},
        {"name": "qwen2.5:32b", "label_key": "llm.preset.ollama.qwen2_5_32b", "kind": "ollama"},
        {"name": "qwen2.5:14b", "label_key": "llm.preset.ollama.qwen2_5_14b", "kind": "ollama"},
        {"name": "llama3.1:8b", "label_key": "llm.preset.ollama.llama3_1_8b", "kind": "ollama"},
        {"name": "gpt-oss:20b", "label_key": "llm.preset.ollama.gpt_oss_20b", "kind": "ollama"},
        {"name": "openai.gpt-oss-120b", "label_key": "llm.preset.bedrock.gpt_oss_120b", "kind": "bedrock"},
        {"name": "qwen.qwen3-235b-a22b-2507", "label_key": "llm.preset.bedrock.qwen3_235b_a22b_2507", "kind": "bedrock"},
        {"name": "minimax.minimax-m2.5", "label_key": "llm.preset.bedrock.minimax_m2_5", "kind": "bedrock"},
        {"name": "mistral.devstral-2-123b", "label_key": "llm.preset.bedrock.devstral_2_123b", "kind": "bedrock"},
        {"name": "nvidia.nemotron-super-3-120b", "label_key": "llm.preset.bedrock.nemotron_super_3_120b", "kind": "bedrock"},
        {"name": "zai.glm-4.7-flash", "label_key": "llm.preset.bedrock.glm_4_7_flash", "kind": "bedrock"},
    ]


class BackendsConfigMixin:
    """Storage, auth, and backend configuration."""

    METADATA_BACKEND = os.environ.get('AGORA_METADATA_BACKEND', 'legacy').strip().lower()
    LLM_PROFILE_BACKEND = os.environ.get('AGORA_LLM_PROFILE_BACKEND', 'sqlite').strip().lower()
    PROJECT_BACKEND = os.environ.get('AGORA_PROJECT_BACKEND', 'file').strip().lower()
    SIMULATION_BACKEND = os.environ.get('AGORA_SIMULATION_BACKEND', 'file').strip().lower()
    RUN_BACKEND = os.environ.get('AGORA_RUN_BACKEND', 'file').strip().lower()
    REPORT_BACKEND = os.environ.get('AGORA_REPORT_BACKEND', 'file').strip().lower()
    PERSONA_SET_BACKEND = os.environ.get('AGORA_PERSONA_SET_BACKEND', 'file').strip().lower()

    AUTH_BACKEND = os.environ.get('AGORA_AUTH_BACKEND', 'hybrid').strip().lower()
    SUPABASE_JWT_ISSUER = os.environ.get('AGORA_SUPABASE_JWT_ISSUER', '')
    SUPABASE_JWT_AUDIENCE = os.environ.get('AGORA_SUPABASE_JWT_AUDIENCE', 'authenticated')
    SUPABASE_JWKS_URL = os.environ.get('AGORA_SUPABASE_JWKS_URL', '')
    SUPABASE_JWT_SECRET = os.environ.get('AGORA_SUPABASE_JWT_SECRET', '')
    SUPABASE_URL = os.environ.get('AGORA_SUPABASE_URL', '')
    SUPABASE_ANON_KEY = os.environ.get('AGORA_SUPABASE_ANON_KEY', '')
    SUPABASE_REALTIME = os.environ.get(
        'AGORA_SUPABASE_REALTIME', 'false'
    ).strip().lower() in ('1', 'true', 'yes', 'on')

    DECISION_LAYER_MODE = os.environ.get('AGORA_DECISION_LAYER_MODE', 'disabled').strip().lower()


class DomainConfigMixin:
    """Domain processing, simulation, limits, and runtime flags."""

    ENABLE_AGENT_TOOLS = os.environ.get('ENABLE_AGENT_TOOLS', 'false').lower() in ('true', '1', 'yes')
    MAX_TOOL_CALLS_PER_ACTION = int(os.environ.get('MAX_TOOL_CALLS_PER_ACTION', '2'))

    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')
    EMBEDDING_BASE_URL = os.environ.get('EMBEDDING_BASE_URL', 'http://localhost:11434')
    EMBEDDING_API_KEY = os.environ.get('EMBEDDING_API_KEY')
    VECTOR_DIM = int(
        os.environ.get(
            'VECTOR_DIM',
            str(infer_vector_dim_for_model(EMBEDDING_MODEL) or 768),
        )
    )

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    DEFAULT_CHUNK_SIZE = int(os.environ.get('GRAPH_CHUNK_SIZE', '1500'))
    DEFAULT_CHUNK_OVERLAP = int(os.environ.get('GRAPH_CHUNK_OVERLAP', '150'))
    GRAPH_PARALLEL_CHUNKS = int(os.environ.get('GRAPH_PARALLEL_CHUNKS', '4'))

    ONTOLOGY_MIN_ENTITY_TYPES = int(os.environ.get('ONTOLOGY_MIN_ENTITY_TYPES', '8'))
    ONTOLOGY_MAX_ENTITY_TYPES = int(os.environ.get('ONTOLOGY_MAX_ENTITY_TYPES', '16'))
    ONTOLOGY_MAX_EDGE_TYPES = int(os.environ.get('ONTOLOGY_MAX_EDGE_TYPES', '12'))

    GRAPH_MIN_ENTITIES = int(os.environ.get('GRAPH_MIN_ENTITIES', '3'))
    GRAPH_MIN_RELATIONS = int(os.environ.get('GRAPH_MIN_RELATIONS', '1'))
    GRAPH_MIN_CHUNK_SUCCESS_RATIO = float(
        os.environ.get('GRAPH_MIN_CHUNK_SUCCESS_RATIO', '0.5')
    )

    HYBRID_SEARCH_VECTOR_WEIGHT = float(os.environ.get('HYBRID_SEARCH_VECTOR_WEIGHT', '0.7'))
    HYBRID_SEARCH_KEYWORD_WEIGHT = float(os.environ.get('HYBRID_SEARCH_KEYWORD_WEIGHT', '0.3'))

    GRAPH_MEMORY_QUEUE_MAX = int(os.environ.get('GRAPH_MEMORY_QUEUE_MAX', '10000'))
    GRAPH_MEMORY_PUT_TIMEOUT = float(os.environ.get('GRAPH_MEMORY_PUT_TIMEOUT', '2.0'))

    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    _RAW_REPORT_TOOLCALL_MODE = os.environ.get('REPORT_TOOLCALL_MODE', 'native')
    _NORMALIZED_REPORT_TOOLCALL_MODE = _RAW_REPORT_TOOLCALL_MODE.strip().lower()
    if _NORMALIZED_REPORT_TOOLCALL_MODE not in ('native', 'xml'):
        logging.getLogger(__name__).warning(
            "Invalid REPORT_TOOLCALL_MODE=%r — falling back to default 'native'",
            _RAW_REPORT_TOOLCALL_MODE,
        )
        _NORMALIZED_REPORT_TOOLCALL_MODE = 'native'
    REPORT_TOOLCALL_MODE: str = _NORMALIZED_REPORT_TOOLCALL_MODE

    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    REPORT_INTERVIEW_MAX_PER_PERSONA = int(
        os.environ.get('REPORT_INTERVIEW_MAX_PER_PERSONA', '2')
    )
    REPORT_REQUIREMENT_CHECKER_ENABLED = os.environ.get(
        'REPORT_REQUIREMENT_CHECKER_ENABLED', 'true'
    ).strip().lower() in ('1', 'true', 'yes', 'on')
    REPORT_POSITIONING_RATIO_MIN = _env_ratio(
        os.environ, 'AGORA_REPORT_POSITIONING_RATIO_MIN', 0.5
    )
    REPORT_LANGUAGE = os.environ.get('REPORT_LANGUAGE', 'German')
    AGENT_LANGUAGE = os.environ.get('AGENT_LANGUAGE', 'de').lower()
    TIME_PROFILE = os.environ.get('TIME_PROFILE', 'dach_default').lower()

    AGORA_LOG_FORMAT = os.environ.get('AGORA_LOG_FORMAT', 'text').lower()

    AGORA_TICKET_RATE_LIMIT_MAX = int(os.environ.get('AGORA_TICKET_RATE_LIMIT_MAX', '60'))
    AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_UPLOAD_RATE_LIMIT_MAX = int(os.environ.get('AGORA_UPLOAD_RATE_LIMIT_MAX', '10'))
    AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_MAX_UPLOAD_SIZE_MB = int(os.environ.get('AGORA_MAX_UPLOAD_SIZE_MB', '50'))
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
    AGORA_WORKSPACE_RATE_LIMIT_MAX = int(os.environ.get('AGORA_WORKSPACE_RATE_LIMIT_MAX', '30'))
    AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS = int(
        os.environ.get('AGORA_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS', '60')
    )
    AGORA_PROXY_FIX_X_FOR = int(os.environ.get('AGORA_PROXY_FIX_X_FOR', '0'))
    AGORA_PROXY_FIX_X_PROTO = int(os.environ.get('AGORA_PROXY_FIX_X_PROTO', '0'))
    AGORA_PROXY_FIX_X_HOST = int(os.environ.get('AGORA_PROXY_FIX_X_HOST', '0'))
    AGORA_PROXY_FIX_X_PORT = int(os.environ.get('AGORA_PROXY_FIX_X_PORT', '0'))
    AGORA_PROXY_FIX_X_PREFIX = int(os.environ.get('AGORA_PROXY_FIX_X_PREFIX', '0'))

    AGORA_STARTUP_RECONCILIATION = (
        os.environ.get('AGORA_STARTUP_RECONCILIATION', 'true').lower() in ('true', '1', 'yes')
    )

    AGORA_JOB_LEASE_TTL_SECONDS = int(os.environ.get('AGORA_JOB_LEASE_TTL_SECONDS', '90'))
    AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS = int(
        os.environ.get('AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS', '20')
    )
    AGORA_JOB_LEASE_MAX_STALL_SECONDS = int(
        os.environ.get('AGORA_JOB_LEASE_MAX_STALL_SECONDS', '1800')
    )

    ONTOLOGY_MUTATION_MODE = os.environ.get('ONTOLOGY_MUTATION_MODE', 'disabled').lower()
    ONTOLOGY_MUTATION_MIN_CONFIDENCE = float(
        os.environ.get('ONTOLOGY_MUTATION_MIN_CONFIDENCE', '0.6')
    )

    PERSONA_REVIEW_ENABLED = (
        os.environ.get('PERSONA_REVIEW_ENABLED', 'false').lower() == 'true'
    )

    AGORA_ROLE_LEAKAGE_MARKING = (
        os.environ.get('AGORA_ROLE_LEAKAGE_MARKING', 'true').lower() in ('true', '1', 'yes')
    )
