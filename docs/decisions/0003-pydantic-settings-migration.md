# ADR-0003 — Pydantic-Settings-Migration für `app/config.py`

**Status:** Accepted
**Datum:** 2026-05-15
**Accepted:** 2026-05-15
**Slice:** Pydantic-Settings-Epic, PR 1 (Foundation)
**Autor:** arn0ld87 + Claude Opus 4.7
**Bezug:** [`backend/app/config.py`](../../backend/app/config.py), PR [#456](https://github.com/arn0ld87/agora/pull/456) (Quick-Fix `importlib.reload`-Bug), `anweisungen.md` Punkt 2 (Codex-Vorschlag)

---

## Kontext

`backend/app/config.py` (326 LoC) ist eine reine **Class-Attribute-Konfiguration**: 41 Felder werden zur Import-Zeit aus `os.environ` gelesen, ein `@classmethod validate()` prüft Pflichtfelder. Konsumiert wird sie als globaler Zustand:

```python
from app.config import Config

if Config.PERSONA_REVIEW_ENABLED:
    ...
```

Drei strukturelle Probleme:

1. **Globaler mutierbarer Zustand.** 11 Test-Files setzen Werte via `monkeypatch.setattr(Config, "X", value)`. Module wie `app.api.simulation_run` haben aber `from ..config import Config` zur Import-Zeit gezogen — Referenz auf die Klasse, nicht auf einen Accessor. Ein `importlib.reload(app.config)` (wie in `tests/services/report_agent/test_toolcall_mode_followup.py`) ersetzt `Config` durch ein neues Class-Objekt; andere Module sehen weiter das alte. Folge: `test_start_route_blocks_when_personas_pending` failed in der vollen Suite mit `400 == 409` — bereits in PR #456 per Quick-Fix entschärft, aber die Wurzel bleibt.
2. **Validation ist schwach.** `validate()` läuft nur, wenn jemand sie explizit aufruft (heute beim App-Start). Type-Casts passieren manuell mit `int(os.environ.get(...))`; Tippfehler in Env-Var-Namen werden stillschweigend zu Default-Werten. Whitelists (`REPORT_TOOLCALL_MODE: native|xml`) sind als prozeduraler Code in der Klasse, nicht als Schema.
3. **Constants und Settings vermischt.** `OASIS_TWITTER_ACTIONS`, `LLM_MODEL_PRESETS`, `ALLOWED_EXTENSIONS`, `MAX_CONTENT_LENGTH`, `JSON_AS_ASCII` sind keine Settings, sondern Konstanten — sie haben nichts in einer Env-getriebenen Config zu suchen.

`anweisungen.md` enthält einen Codex-Vorschlag für eine pydantic-settings-Migration. Sein `_ConfigProxy.__setattr__` hat **Bugs** (das Pattern `get_settings.__wrapped__ = lambda: new_settings` überschreibt den `lru_cache` nicht — `__wrapped__` ist read-only-Pointer auf die undecorated Funktion, kein Cache-Setter). Wir übernehmen die Richtung, aber nicht den Code.

## Entscheidung

Migration in **vier inkrementellen PRs**. Diese ADR-Datei wird mit PR 1 gemerged.

### Zielarchitektur

```python
# backend/app/settings.py — NEU (PR 1)
class AgoraSettings(BaseSettings):
    """Alle Laufzeit-Konfigurationen an einem Ort. Singleton via get_settings()."""
    secret_key: SecretStr = Field(default=SecretStr(""))
    debug: bool = Field(default=False, alias="FLASK_DEBUG")
    # ... 41 Felder total ...

@lru_cache(maxsize=1)
def get_settings() -> AgoraSettings:
    return AgoraSettings()
```

Tests rufen `get_settings.cache_clear()` (via conftest-Fixture). Produktiv-Code liest `get_settings().llm_api_key` statt `Config.LLM_API_KEY`.

### Field-Inventar (41 Felder)

Vollständiges Mapping `Config.X` → `AgoraSettings.x`. Default-Werte und Env-Aliases sind 1:1 aus `app/config.py` übernommen.

| Bereich | `Config.X` | Field | Type | Env-Alias | Default |
|---|---|---|---|---|---|
| Flask | `SECRET_KEY` | `secret_key` | `SecretStr` | `SECRET_KEY` | `""` |
| Flask | `DEBUG` | `debug` | `bool` | `FLASK_DEBUG` | `False` |
| LLM | `LLM_API_KEY` | `llm_api_key` | `SecretStr \| None` | `LLM_API_KEY` | `None` |
| LLM | `LLM_BASE_URL` | `llm_base_url` | `str` | `LLM_BASE_URL` | `"http://localhost:11434/v1"` |
| LLM | `LLM_MODEL_NAME` | `llm_model_name` | `str` | `LLM_MODEL_NAME` | `"qwen2.5:32b"` |
| LLM | `LLM_MAX_OUTPUT_TOKENS` | `llm_max_output_tokens` | `int` | `LLM_MAX_OUTPUT_TOKENS` | `8192` |
| LLM | `LLM_CONTEXT_LIMIT` | `llm_context_limit` | `int` | `LLM_CONTEXT_LIMIT` | `262144` |
| LLM | `LLM_MODEL_CONTEXT_LIMITS` | `llm_model_context_limits` | `dict[str,int]` | `LLM_MODEL_CONTEXT_LIMITS_JSON` (parsed) | `{}` |
| Neo4j | `NEO4J_URI` | `neo4j_uri` | `str` | `NEO4J_URI` | `"bolt://localhost:7687"` |
| Neo4j | `NEO4J_USER` | `neo4j_user` | `str` | `NEO4J_USER` | `"neo4j"` |
| Neo4j | `NEO4J_PASSWORD` | `neo4j_password` | `SecretStr` | `NEO4J_PASSWORD` | `""` |
| Agent-Tools | `ENABLE_AGENT_TOOLS` | `enable_agent_tools` | `bool` | `ENABLE_AGENT_TOOLS` | `False` |
| Agent-Tools | `MAX_TOOL_CALLS_PER_ACTION` | `max_tool_calls_per_action` | `int` | `MAX_TOOL_CALLS_PER_ACTION` | `2` |
| Embeddings | `EMBEDDING_MODEL` | `embedding_model` | `str` | `EMBEDDING_MODEL` | `"nomic-embed-text"` |
| Embeddings | `EMBEDDING_BASE_URL` | `embedding_base_url` | `str` | `EMBEDDING_BASE_URL` | `"http://localhost:11434"` |
| Embeddings | `EMBEDDING_API_KEY` | `embedding_api_key` | `SecretStr \| None` | `EMBEDDING_API_KEY` | `None` (Fallback: `llm_api_key`) |
| Embeddings | `VECTOR_DIM` | `vector_dim` | `int` | `VECTOR_DIM` | inferiert aus `embedding_model`, sonst `768` |
| Chunking | `DEFAULT_CHUNK_SIZE` | `default_chunk_size` | `int` | `GRAPH_CHUNK_SIZE` | `1500` |
| Chunking | `DEFAULT_CHUNK_OVERLAP` | `default_chunk_overlap` | `int` | `GRAPH_CHUNK_OVERLAP` | `150` |
| Chunking | `GRAPH_PARALLEL_CHUNKS` | `graph_parallel_chunks` | `int` | `GRAPH_PARALLEL_CHUNKS` | `4` |
| Ontology | `ONTOLOGY_MIN_ENTITY_TYPES` | `ontology_min_entity_types` | `int` | `ONTOLOGY_MIN_ENTITY_TYPES` | `8` |
| Ontology | `ONTOLOGY_MAX_ENTITY_TYPES` | `ontology_max_entity_types` | `int` | `ONTOLOGY_MAX_ENTITY_TYPES` | `16` |
| Ontology | `ONTOLOGY_MAX_EDGE_TYPES` | `ontology_max_edge_types` | `int` | `ONTOLOGY_MAX_EDGE_TYPES` | `12` |
| Ontology | `ONTOLOGY_MUTATION_MODE` | `ontology_mutation_mode` | `Literal["disabled","review_only","auto"]` | `ONTOLOGY_MUTATION_MODE` | `"disabled"` |
| Ontology | `ONTOLOGY_MUTATION_MIN_CONFIDENCE` | `ontology_mutation_min_confidence` | `float` | `ONTOLOGY_MUTATION_MIN_CONFIDENCE` | `0.6` |
| Search | `HYBRID_SEARCH_VECTOR_WEIGHT` | `hybrid_search_vector_weight` | `float` | `HYBRID_SEARCH_VECTOR_WEIGHT` | `0.7` |
| Search | `HYBRID_SEARCH_KEYWORD_WEIGHT` | `hybrid_search_keyword_weight` | `float` | `HYBRID_SEARCH_KEYWORD_WEIGHT` | `0.3` |
| GraphMemory | `GRAPH_MEMORY_QUEUE_MAX` | `graph_memory_queue_max` | `int` | `GRAPH_MEMORY_QUEUE_MAX` | `10000` |
| GraphMemory | `GRAPH_MEMORY_PUT_TIMEOUT` | `graph_memory_put_timeout` | `float` | `GRAPH_MEMORY_PUT_TIMEOUT` | `2.0` |
| OASIS | `OASIS_DEFAULT_MAX_ROUNDS` | `oasis_default_max_rounds` | `int` | `OASIS_DEFAULT_MAX_ROUNDS` | `10` |
| Report-Agent | `REPORT_TOOLCALL_MODE` | `report_toolcall_mode` | `Literal["native","xml"]` | `REPORT_TOOLCALL_MODE` | `"native"` (Whitelist-Fallback `"xml"`) |
| Report-Agent | `REPORT_AGENT_MAX_TOOL_CALLS` | `report_agent_max_tool_calls` | `int` | `REPORT_AGENT_MAX_TOOL_CALLS` | `5` |
| Report-Agent | `REPORT_AGENT_MAX_REFLECTION_ROUNDS` | `report_agent_max_reflection_rounds` | `int` | `REPORT_AGENT_MAX_REFLECTION_ROUNDS` | `2` |
| Report-Agent | `REPORT_AGENT_TEMPERATURE` | `report_agent_temperature` | `float` | `REPORT_AGENT_TEMPERATURE` | `0.5` |
| Sprache | `REPORT_LANGUAGE` | `report_language` | `str` | `REPORT_LANGUAGE` | `"German"` |
| Sprache | `AGENT_LANGUAGE` | `agent_language` | `str` | `AGENT_LANGUAGE` | `"de"` |
| Time/Persona | `TIME_PROFILE` | `time_profile` | `str` | `TIME_PROFILE` | `"dach_default"` |
| Persona | `PERSONA_REVIEW_ENABLED` | `persona_review_enabled` | `bool` | `PERSONA_REVIEW_ENABLED` | `False` |
| Logging | `AGORA_LOG_FORMAT` | `agora_log_format` | `Literal["text","json"]` | `AGORA_LOG_FORMAT` | `"text"` |
| Event-Bus | `REDIS_URL` | `redis_url` | `str` | `REDIS_URL` | `"redis://redis:6379/0"` |
| Event-Bus | `EVENT_BUS_BACKEND` | `event_bus_backend` | `Literal["redis","file","auto"]` | `EVENT_BUS_BACKEND` | `"auto"` |
| Rate-Limit | `AGORA_TICKET_RATE_LIMIT_MAX` | `agora_ticket_rate_limit_max` | `int` | `AGORA_TICKET_RATE_LIMIT_MAX` | `60` |
| Rate-Limit | `AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS` | `agora_ticket_rate_limit_window_seconds` | `int` | `AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS` | `60` |
| Rate-Limit | `AGORA_UPLOAD_RATE_LIMIT_MAX` | `agora_upload_rate_limit_max` | `int` | `AGORA_UPLOAD_RATE_LIMIT_MAX` | `10` |
| Rate-Limit | `AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS` | `agora_upload_rate_limit_window_seconds` | `int` | `AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS` | `60` |
| Rate-Limit | `AGORA_LLM_TRIGGER_RATE_LIMIT_MAX` | `agora_llm_trigger_rate_limit_max` | `int` | `AGORA_LLM_TRIGGER_RATE_LIMIT_MAX` | `20` |
| Rate-Limit | `AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS` | `agora_llm_trigger_rate_limit_window_seconds` | `int` | `AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS` | `60` |
| Rate-Limit | `AGORA_REPORT_RATE_LIMIT_MAX` | `agora_report_rate_limit_max` | `int` | `AGORA_REPORT_RATE_LIMIT_MAX` | `10` |
| Rate-Limit | `AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS` | `agora_report_rate_limit_window_seconds` | `int` | `AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS` | `60` |
| ProxyFix | `AGORA_PROXY_FIX_X_FOR` | `agora_proxy_fix_x_for` | `int` | `AGORA_PROXY_FIX_X_FOR` | `0` |
| ProxyFix | `AGORA_PROXY_FIX_X_PROTO` | `agora_proxy_fix_x_proto` | `int` | `AGORA_PROXY_FIX_X_PROTO` | `0` |
| ProxyFix | `AGORA_PROXY_FIX_X_HOST` | `agora_proxy_fix_x_host` | `int` | `AGORA_PROXY_FIX_X_HOST` | `0` |
| ProxyFix | `AGORA_PROXY_FIX_X_PORT` | `agora_proxy_fix_x_port` | `int` | `AGORA_PROXY_FIX_X_PORT` | `0` |
| ProxyFix | `AGORA_PROXY_FIX_X_PREFIX` | `agora_proxy_fix_x_prefix` | `int` | `AGORA_PROXY_FIX_X_PREFIX` | `0` |
| Auth | *(neu, war nur in `validate()`)* | `agora_auth_token` | `SecretStr \| None` | `AGORA_AUTH_TOKEN` | `None` |
| Auth | *(neu, war nur in `validate()`)* | `agora_allow_anonymous` | `bool` | `AGORA_ALLOW_ANONYMOUS` | `False` |

**Konstanten** (kein Env, kein Setting — bleiben in `app/config.py` als Module-Level-Konstanten oder ziehen in PR 2 nach `app/constants.py`):

- `KNOWN_EMBEDDING_DIMS`, `SECRET_KEY_PLACEHOLDERS`, `NEO4J_PASSWORD_PLACEHOLDERS`
- `JSON_AS_ASCII`, `MAX_CONTENT_LENGTH`, `UPLOAD_FOLDER`, `ALLOWED_EXTENSIONS`
- `OASIS_TWITTER_ACTIONS`, `OASIS_REDDIT_ACTIONS`, `OASIS_SIMULATION_DATA_DIR`
- `LLM_MODEL_PRESETS`
- Funktion `infer_vector_dim_for_model()`

### Validator-Inventar

Aus `Config.validate()` portiert plus pydantic-typische Constraints:

| Validator | Stufe | Regel | Fehlerverhalten |
|---|---|---|---|
| `_normalize_report_toolcall_mode` | `field_validator(mode="before")` | Strip + lower; nicht in `{"native","xml"}` → `"xml"` mit Warning | non-fatal |
| `_normalize_ontology_mutation_mode` | `field_validator(mode="before")` | Strip + lower; Literal-Typ enforced | ValidationError |
| `_normalize_event_bus_backend` | `field_validator(mode="before")` | Strip + lower; Literal-Typ enforced | ValidationError |
| `_normalize_agora_log_format` | `field_validator(mode="before")` | Strip + lower; Literal-Typ enforced | ValidationError |
| `_normalize_agent_language` | `field_validator(mode="before")` | Strip + lower | non-fatal |
| `_parse_llm_model_context_limits_json` | `field_validator(mode="before")` | JSON-Parse, fail-soft → `{}` | non-fatal |
| `_embedding_api_key_fallback_to_llm` | `model_validator(mode="after")` | Wenn `embedding_api_key is None`, übernimm `llm_api_key` | non-fatal |
| `_validate_vector_dim_matches_model` | `model_validator(mode="after")` | `vector_dim` muss `infer_vector_dim_for_model(embedding_model)` matchen, falls bekannt | ValidationError |
| `_validate_secrets_in_prod` | `model_validator(mode="after")` | Wenn nicht `debug`: `secret_key` nicht leer und nicht in `SECRET_KEY_PLACEHOLDERS` | ValidationError |
| `_validate_neo4j_password_in_prod` | `model_validator(mode="after")` | Wenn nicht `debug`: `neo4j_password` nicht leer und nicht in `NEO4J_PASSWORD_PLACEHOLDERS` | ValidationError |
| `_validate_auth_in_prod` | `model_validator(mode="after")` | Wenn nicht `debug`: `agora_auth_token` gesetzt **oder** `agora_allow_anonymous=True` | ValidationError |
| `_validate_llm_api_key_present` | `model_validator(mode="after")` | `llm_api_key` nicht leer (debug erlaubt `"dummy"`) | ValidationError |

**Side-Effect-Verhalten:** In `Config.validate()` wird heute bei fehlendem `SECRET_KEY` *im Debug-Modus* ein ephemerer `secrets.token_urlsafe(32)`-Wert in die Klasse geschrieben. Dieses Verhalten wird **nicht** in den Validator portiert (Settings sind read-only), sondern in einen separaten Helper `bootstrap_settings()` ausgelagert, der vom App-Start aufgerufen wird und vor dem `AgoraSettings()`-Konstruktor läuft.

### PR-Roadmap

| PR | Inhalt | LoC | Risiko |
|---|---|---|---|
| **1 (this)** | `app/settings.py` mit `AgoraSettings` (41 Felder + 12 Validators), `pydantic-settings>=2.5.0` als Dep, `tests/test_settings.py` (Defaults, Env-Override, jeder Validator, Cache-Clear), ADR 0003 — **kein** Touch von `app/config.py`, **keine** Call-Sites, **keine** conftest-Änderung außerhalb von `test_settings.py` | ~500 | LOW |
| **2** | `app/config.py` wird zu einem `_ConfigProxy`, der intern `get_settings()` delegiert. `Config.X` bleibt lesbar; `Config.X = value` (tests!) leitet auf eine Singleton-Override-Schicht. conftest-Fixture für globalen `get_settings.cache_clear()`. `bootstrap_settings()` ersetzt `Config.validate()` als App-Start-Helfer. | ~250 | MEDIUM — 11 Test-Files indirekt, alle Call-Sites indirekt |
| **3..N** *(optional)* | Direkt-Migration einzelner Module: `from app.settings import get_settings` statt `from app.config import Config`. Ein PR pro Modul-Domain (`api/`, `services/`, `storage/`, `utils/`, `scripts/`). | je ~50–150 | LOW per Modul |
| **Final** *(optional)* | `_ConfigProxy` entfernen, `Config`-Alias droppen, `app/config.py` zu pure-constants reduzieren oder nach `app/constants.py` verschieben. | ~50 | LOW |

PR 1 ist **abgeschlossen, sobald**: neue Tests grün, kein bestehender Test berührt, `mypy app` grün, kein Produktiv-Modul nutzt `AgoraSettings`. Mehrwert kommt mit PR 2 — PR 1 ist bewusst Foundation-only, damit Review-Surface klein bleibt und ADR-Spec validiert wird.

## Konsequenzen

**Positiv:**
- Test-Isolation: `get_settings.cache_clear()` ersetzt `importlib.reload(app.config)` (PR #456 Quick-Fix wird in PR 2 redundant und kann aufgeräumt werden).
- Type-safety: `int(os.environ.get(...))`-Tippfehler werden zu `ValidationError`.
- Whitelist-Validation: `REPORT_TOOLCALL_MODE`, `ONTOLOGY_MUTATION_MODE`, `EVENT_BUS_BACKEND`, `AGORA_LOG_FORMAT` als `Literal`-Typen.
- Constants und Settings sind getrennt.
- `SecretStr` für sensible Felder — `print(settings)` leakt nichts.

**Negativ / Risiko:**
- Migration verteilt sich über mehrere PRs; bis PR 2 mergt, existiert Code parallel.
- PR 2 ist die einzige PR mit High-Touch-Surface (alle Tests, alle Call-Sites indirekt) — muss sorgfältig reviewt werden.
- `_ConfigProxy.__setattr__` muss `monkeypatch.setattr(Config, "X", value)` weiter unterstützen, sonst brechen 11 Test-Files. Das wird in PR 2 designt, nicht hier.

**Verworfen:**
- *Direkter Cut ohne Compat-Shim:* zu viele Call-Sites + 11 Test-Files würden in einem PR brechen. Reviewbarkeit kaputt.
- *Codex' `_ConfigProxy.__wrapped__ = lambda`-Pattern aus `anweisungen.md`:* überschreibt den `lru_cache` faktisch nicht und führt zu schwer reproduzierbaren Cache-Bleeds.

## Referenzen

- PR [#456](https://github.com/arn0ld87/agora/pull/456) — Quick-Fix Test-Isolation
- `backend/app/config.py` (Stand vor Migration)
- pydantic-settings: <https://docs.pydantic.dev/latest/concepts/pydantic_settings/>
- ADR [0001 Auth-Model](0001-auth-model.md), ADR [0002 Evidence-Gating](0002-evidence-gating.md)
