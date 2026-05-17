"""Settings-Schema (Issue #133) — die Source-of-Truth dafür, welche
`.env`-Optionen im Frontend zur Laufzeit pflegbar sind, in welche
Sektion sie gehören und welche Sicherheits- bzw. Reload-Eigenschaften
sie haben.

Bewusst kein Pydantic in dieser Datei: das Schema ist eine *Liste von
deklarativen Field-Specs*, mit denen sowohl der Settings-Layer arbeitet
(GET/Source-Tracking) als auch der Validator in SUB2 (PUT). Pydantic
würde die Meta-Daten (Sektion, Reload-Flag, Secret-Flag) künstlich in
einen Class-Body pressen — eine flache Liste ist hier ehrlicher.

Die *Reihenfolge* in :data:`SECTIONS` und :data:`SETTINGS_FIELDS`
spiegelt die Reihenfolge in `.env.example` und ist die UI-Reihenfolge
in `SettingsView.vue` (Slice SUB3).
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any


# Sektionsschlüssel → i18n-Label-Key (`settings.sections.<id>`).
# UI rendert die Tabs in dieser Reihenfolge.
SECTIONS: tuple[str, ...] = (
    'llm',
    'neo4j',
    'embedding',
    'ontology',
    'hybrid_search',
    'agent_tools',
    'event_bus',
    'logging',
    'locale',
    'ui',
    'webtools',
    'oasis',
    'security',
)


@dataclass(frozen=True)
class FieldSpec:
    """Deklarative Beschreibung eines einzelnen Settings-Felds.

    Attribute:
        key: Name der Env-Variable bzw. JSON-Key in
            ``instance/settings.json``. Wird 1:1 in beiden Quellen
            verwendet.
        section: Sektions-ID (siehe :data:`SECTIONS`).
        type: ``string`` | ``int`` | ``float`` | ``bool`` | ``enum``.
        default: Code-Default. *Nicht* der `.env`-Default — das ist die
            Env-Quelle, nicht der Schema-Default. Diese Werte müssen
            mit den Defaults in :class:`app.config.Config` konsistent
            sein; ein Pin-Test in
            ``backend/tests/test_settings_layer.py`` fängt Drift ab.
        secret: Wenn ``True``, wird der Wert nie im GET-Response
            zurückgegeben — nur ``is_set: bool``. Setzen geschieht
            in SUB2 über einen separaten Endpunkt mit Bestätigung.
        reload_required: Wenn ``True``, hat eine Änderung erst nach
            Backend-Restart Wirkung. Frontend zeigt das per Badge.
        enum_values: Erlaubte Werte für ``type='enum'``.
        min_value / max_value: Optionale Bereichsgrenzen für
            ``int``/``float`` (vom SUB2-Validator genutzt).
    """

    key: str
    section: str
    type: str
    default: Any = None
    secret: bool = False
    reload_required: bool = False
    enum_values: tuple[str, ...] | None = None
    min_value: float | None = None
    max_value: float | None = None
    # Optionale Liste anderer Field-Keys, die zusammen validiert werden
    # müssen (z. B. ``EMBEDDING_MODEL`` ↔ ``VECTOR_DIM``). SUB2-Hook.
    cross_validates_with: tuple[str, ...] = dc_field(default_factory=tuple)


# Reihenfolge entspricht `.env.example`. Defaults sind 1:1 aus
# ``backend/app/config.py`` übernommen — siehe Pin-Test.
SETTINGS_FIELDS: tuple[FieldSpec, ...] = (
    # ===== LLM =====
    FieldSpec('LLM_API_KEY', 'llm', 'string', default='', secret=True,
              reload_required=True),
    FieldSpec('LLM_BASE_URL', 'llm', 'string',
              default='http://localhost:11434/v1', reload_required=True),
    # Leerer Default — Bootstrap-Profil wird nur erzeugt, wenn der Operator
    # ein konkretes Modell setzt. Vorher führte `qwen2.5:32b` zu 404 in
    # Cloud-Setups (Ollama Cloud / OpenAI / Gemini), weil das Auto-Profil
    # auf ein Tag verwies, das im aktiven Backend nicht existiert.
    FieldSpec('LLM_MODEL_NAME', 'llm', 'string', default=''),
    FieldSpec('LLM_MAX_OUTPUT_TOKENS', 'llm', 'int', default=8192,
              min_value=128, max_value=131072),
    FieldSpec('LLM_CONTEXT_LIMIT', 'llm', 'int', default=262144,
              min_value=1024, max_value=2_000_000),

    # ===== Neo4j =====
    FieldSpec('NEO4J_URI', 'neo4j', 'string',
              default='bolt://localhost:7687', reload_required=True),
    FieldSpec('NEO4J_USER', 'neo4j', 'string', default='neo4j',
              reload_required=True),
    FieldSpec('NEO4J_PASSWORD', 'neo4j', 'string', default='',
              secret=True, reload_required=True),

    # ===== Embedding =====
    FieldSpec('EMBEDDING_MODEL', 'embedding', 'string',
              default='nomic-embed-text', reload_required=True,
              cross_validates_with=('VECTOR_DIM',)),
    FieldSpec('EMBEDDING_BASE_URL', 'embedding', 'string',
              default='http://localhost:11434', reload_required=True),
    FieldSpec('VECTOR_DIM', 'embedding', 'int', default=768,
              min_value=64, max_value=8192, reload_required=True,
              cross_validates_with=('EMBEDDING_MODEL',)),

    # ===== Ontology =====
    FieldSpec('ONTOLOGY_MIN_ENTITY_TYPES', 'ontology', 'int', default=8,
              min_value=1, max_value=64),
    FieldSpec('ONTOLOGY_MAX_ENTITY_TYPES', 'ontology', 'int', default=16,
              min_value=1, max_value=64),
    FieldSpec('ONTOLOGY_MAX_EDGE_TYPES', 'ontology', 'int', default=12,
              min_value=1, max_value=64),
    FieldSpec('ONTOLOGY_MUTATION_MODE', 'ontology', 'enum',
              default='disabled',
              enum_values=('disabled', 'review_only', 'auto')),
    FieldSpec('ONTOLOGY_MUTATION_MIN_CONFIDENCE', 'ontology', 'float',
              default=0.6, min_value=0.0, max_value=1.0),

    # ===== Hybrid Search =====
    FieldSpec('HYBRID_SEARCH_VECTOR_WEIGHT', 'hybrid_search', 'float',
              default=0.7, min_value=0.0, max_value=1.0),
    FieldSpec('HYBRID_SEARCH_KEYWORD_WEIGHT', 'hybrid_search', 'float',
              default=0.3, min_value=0.0, max_value=1.0),

    # ===== Agent Tools =====
    FieldSpec('ENABLE_AGENT_TOOLS', 'agent_tools', 'bool', default=False),
    FieldSpec('MAX_TOOL_CALLS_PER_ACTION', 'agent_tools', 'int',
              default=2, min_value=0, max_value=20),

    # ===== Event Bus =====
    FieldSpec('EVENT_BUS_BACKEND', 'event_bus', 'enum', default='auto',
              enum_values=('auto', 'redis', 'file'),
              reload_required=True),
    FieldSpec('REDIS_URL', 'event_bus', 'string',
              default='redis://redis:6379/0', reload_required=True),

    # ===== Logging =====
    FieldSpec('AGORA_LOG_FORMAT', 'logging', 'enum', default='text',
              enum_values=('text', 'json'), reload_required=True),

    # ===== Locale =====
    FieldSpec('AGENT_LANGUAGE', 'locale', 'enum', default='de',
              enum_values=('de', 'en')),
    FieldSpec('TIME_PROFILE', 'locale', 'string', default='dach_default'),
    FieldSpec('REPORT_LANGUAGE', 'locale', 'string', default='German'),

    # ===== UI =====
    FieldSpec('RUNS_POLL_INTERVAL_MS', 'ui', 'int', default=5000,
              min_value=1000, max_value=60000),

    # ===== Webtools (ReportAgent) =====
    FieldSpec('ENABLE_WEB_TOOLS', 'webtools', 'bool', default=False),
    FieldSpec('TAVILY_API_KEY', 'webtools', 'string', default='',
              secret=True),

    # ===== Ontology (erweitert) =====
    FieldSpec('ONTOLOGY_MAX_TOKENS', 'ontology', 'int', default=12288,
              min_value=1024, max_value=131072),

    # ===== OASIS / CAMEL =====
    FieldSpec('OPENAI_API_KEY', 'oasis', 'string', default='ollama',
              secret=True),
    FieldSpec('OPENAI_API_BASE_URL', 'oasis', 'string',
              default='http://localhost:11434/v1'),
    FieldSpec('AGORA_PARALLEL_PERSONA_COUNT', 'oasis', 'int', default=10,
              min_value=1, max_value=50),
    FieldSpec('AGORA_PERSONA_DETAIL_LEVEL', 'oasis', 'enum',
              default='standard',
              enum_values=('compact', 'standard', 'rich')),

    # ===== Security / Secrets =====
    FieldSpec('SECRET_KEY', 'security', 'string', default='',
              secret=True, reload_required=True),
    FieldSpec('AGORA_AUTH_TOKEN', 'security', 'string', default='',
              secret=True, reload_required=True),
)


def field_by_key(key: str) -> FieldSpec | None:
    for spec in SETTINGS_FIELDS:
        if spec.key == key:
            return spec
    return None


def fields_by_section(section: str) -> tuple[FieldSpec, ...]:
    return tuple(spec for spec in SETTINGS_FIELDS if spec.section == section)
