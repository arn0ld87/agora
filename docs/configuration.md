# Konfiguration — Umgebungsvariablen

**Status:** Referenz zu Backend `0.8.0`. Konkrete Defaults und Beispiele liefert [`.env.example`](../.env.example) — bei Abweichung ist `.env.example` führend. Einstellungen werden über `pydantic-settings` geladen (ADR-0003). Geheimnisse 🔐 niemals committen, in Logs ausgeben oder in Doku schreiben — Secrets liegen im Vaultwarden bzw. im lokalen Secret Store.

Quelle für die Variablennamen ist der Code (Backend `os.getenv` / `pydantic-settings` `validation_alias`). Bei neuen Variablen: hier und in `.env.example` mit-pflegen.

---

## App & Core

| Variable | Zweck |
|---|---|
| `AGORA_DATA_DIR` | Basisverzeichnis für Laufzeitdaten |
| `AGORA_INSTANCE_DIR` | Instanzspezifisches Datenverzeichnis |
| `AGORA_ALLOW_ANONYMOUS` | anonyme Nutzung ohne Auth (nur lokal) |
| `AGORA_CORS_ALLOW_ALL` | CORS pauschal öffnen (Dev) |
| `AGORA_EXTRA_ORIGINS` | zusätzliche erlaubte CORS-Origins |
| `AGORA_PROXY_FIX_X_FOR` / `_X_HOST` / `_X_PORT` / `_X_PREFIX` / `_X_PROTO` | ProxyFix-Header für Reverse-Proxy-Betrieb |
| `AGORA_LOG_FORMAT` | Log-Format |
| `AGORA_WERKZEUG_LOG_LEVEL` | Werkzeug-Log-Level |
| `FLASK_HOST` / `FLASK_PORT` / `FLASK_DEBUG` | Flask-Run-Parameter |
| `WERKZEUG_RUN_MAIN` | Werkzeug-Reloader-Internal |
| `DOCKER_IPV4_ONLY` | Docker-IPv4-Beschränkung |
| `SECRET_KEY` 🔐 | Flask-Session-Signing |
| `AGORA_FERNET_KEY` 🔐 | symmetrische Verschlüsselung (Secrets-at-rest) — siehe [`secret-key-lifecycle.md`](secret-key-lifecycle.md) |
| `AGORA_MAX_UPLOAD_SIZE_MB` | Upload-Limit |
| `NLTK_DISABLE_IMPORT_SECURITY` | schaltet den Import-Hook von nltk ≥ 3.10 ab; nötig, weil die venv unter dem Arbeitsverzeichnis liegt (Container und `cd backend`). `backend/app/__init__.py`, das Dockerfile und die Testsuite setzen `1` bereits — siehe [`dependency-risk-register.md`](dependency-risk-register.md), Abschnitt „nltk-Baseline" |

## Auth & Tickets

| Variable | Zweck |
|---|---|
| `AGORA_AUTH_TOKEN` 🔐 | Bearer-Token für `/api/*` — siehe [`auth.md`](auth.md) |
| `AGORA_TICKET_RATE_LIMIT_MAX` / `_WINDOW_SECONDS` | Rate-Limit für signierte Tickets |
| `AGORA_ALLOW_ANONYMOUS` | (siehe App & Core) |

## Rate-Limits

| Variable | Zweck |
|---|---|
| `AGORA_LLM_TRIGGER_RATE_LIMIT_MAX` / `_WINDOW_SECONDS` | LLM-Trigger-Limit |
| `AGORA_REPORT_RATE_LIMIT_MAX` / `_WINDOW_SECONDS` | Report-Generierungs-Limit |
| `AGORA_UPLOAD_RATE_LIMIT_MAX` / `_WINDOW_SECONDS` | Upload-Limit |

## LLM & Provider

Provider-Erkennung: [`../backend/app/llm/providers/registry.py`](../backend/app/llm/providers/registry.py)::`detect_provider` ist SSoT. Strukturierte JSON-Calls laufen über `LLMClient.chat_json` mit Pydantic-Schema.

| Variable | Zweck |
|---|---|
| `LLM_API_KEY` 🔐 | genereller LLM-API-Key |
| `LLM_BASE_URL` | genereller LLM-Endpoint |
| `LLM_MODEL_NAME` | generelles Modell |
| `LLM_CONTEXT_LIMIT` / `LLM_MAX_OUTPUT_TOKENS` | Token-Limits |
| `LLM_MAX_RETRIES` / `LLM_RETRY_INITIAL_DELAY` / `LLM_RETRY_MAX_DELAY` | Retry-Verhalten |
| `LLM_FORCE_STREAM` | Streaming erzwingen |
| `LLM_BOOST_API_KEY` 🔐 / `LLM_BOOST_BASE_URL` / `LLM_BOOST_MODEL_NAME` | Boost-Provider |
| `LLM_MODEL_CONTEXT_LIMITS_JSON` | modellspezifische Context-Limits (JSON) |
| `OPENAI_API_KEY` 🔐 / `OPENAI_BASE_URL` | OpenAI-kompatibel |
| `GEMINI_API_KEY` 🔐 / `GOOGLE_API_KEY` 🔐 | Google/Gemini |
| `OLLAMA_API_KEY` 🔐 / `OLLAMA_BASE_URL` / `OLLAMA_NUM_CTX` / `OLLAMA_THINKING` | Ollama (lokal/Cloud) |
| `TAVILY_API_KEY` 🔐 | Tavily-Web-Suche (Agent-Tools) |
| `AGENT_LANGUAGE` | Agenten-Sprache |
| `AGORA_LLM_ALLOW_INSECURE_HTTP` | dokumentierte Ausnahme (CWE-319, [`app/llm/transport_security.py`](../backend/app/llm/transport_security.py)): erlaubt `http://` mit API-Key gegen einen öffentlichen Host. Default aus/sicher — `http://` mit Credential ist sonst nur für lokale/private Hosts (loopback, RFC1918, CGNAT/Tailscale, Docker-Compose-/Host-Gateway-Namen) zulässig, alles andere bricht mit `InsecureTransportError` ab. |

## Embedding

Embedding-Konfiguration wird vom [`EmbeddingConfigurationStore`](../backend/app/services/embedding_configuration_store.py) in einer JSON-Datei unter `AGORA_DATA_DIR/embedding_configurations.json` persistiert (Index-Versionen in einer Sibling-JSON). Embedding-Arbeit läuft über `embedding_service.py`, der Migrations-Lifecycle über `embedding_migration.py` (ADR-0007).

| Variable | Zweck |
|---|---|
| `EMBEDDING_API_KEY` 🔐 / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | Embedding-Provider |
| `VECTOR_DIM` | Vektor-Dimension (muss zum Modell passen — siehe [`embedding-provider-switch.md`](embedding-provider-switch.md)) |
| `AGORA_SKIP_EMBEDDING_PROBE` | Embedding-Preflight überspringen |

## Neo4j

| Variable | Zweck |
|---|---|
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` 🔐 | Verbindung |
| `NEO4J_MAX_POOL_SIZE` / `NEO4J_MAX_LIFETIME` | Pool-Konfiguration |
| `NEO4J_ACQ_TIMEOUT` / `NEO4J_CONN_TIMEOUT` / `NEO4J_LIVENESS_TIMEOUT` | Timeouts |
| `NEO4J_STARTUP_RETRY_MAX` / `NEO4J_STARTUP_RETRY_DELAY` | Startup-Retry |

## Redis & Event Bus

| Variable | Zweck |
|---|---|
| `REDIS_URL` | Redis-Verbindung (Events, Status, IPC) |
| `TEST_REDIS_URL` | Redis für Tests |
| `EVENT_BUS_BACKEND` | Event-Bus-Backend |

## Graph & Ontologie

| Variable | Zweck |
|---|---|
| `GRAPH_CHUNK_SIZE` / `GRAPH_CHUNK_OVERLAP` | Chunking beim Graph-Build |
| `GRAPH_PARALLEL_CHUNKS` | Parallelität beim Build |
| `GRAPH_MIN_ENTITIES` | Qualitätsschwelle: Entitäten im fertigen Graphen (Default `3`). Darunter eine Warnung |
| `GRAPH_MIN_RELATIONS` | Qualitätsschwelle: Beziehungen (Default `1`). Darunter **blockierend** — der Schritt erreicht „bereit" nicht |
| `GRAPH_MIN_CHUNK_SUCCESS_RATIO` | Anteil der Chunks, die Entitäten oder Beziehungen liefern müssen (Default `0.5`; `0.0` schaltet die Prüfung ab) |
| `GRAPH_MEMORY_PUT_TIMEOUT` / `GRAPH_MEMORY_QUEUE_MAX` | Graph-Memory-Backpressure |
| `ONTOLOGY_MAX_ENTITY_TYPES` / `_MAX_EDGE_TYPES` / `_MIN_ENTITY_TYPES` | Ontologie-Grenzen |
| `ONTOLOGY_MUTATION_MODE` / `_MUTATION_MIN_CONFIDENCE` | Ontologie-Mutation |
| `HYBRID_SEARCH_VECTOR_WEIGHT` / `_KEYWORD_WEIGHT` | Hybrid-Search-Gewichtung |

## Simulation & OASIS

| Variable | Zweck |
|---|---|
| `OASIS_DEFAULT_MAX_ROUNDS` | Standard-Simulationsrunden |
| `AGORA_AGENTS_PER_BATCH` | Agenten pro Batch |
| `AGORA_ALLOW_SMALL_SIM` | kleine Simulationen erlauben |
| `PERSONA_REVIEW_ENABLED` | Persona-Review-Pflicht |
| `ENABLE_AGENT_TOOLS` / `MAX_TOOL_CALLS_PER_ACTION` | Agent-Tools |

## Report

| Variable | Zweck |
|---|---|
| `REPORT_LANGUAGE` | Report-Sprache |
| `REPORT_AGENT_TEMPERATURE` | Report-Agent-Temperatur |
| `REPORT_AGENT_MAX_REFLECTION_ROUNDS` / `_MAX_TOOL_CALLS` | Report-Agent-Limits |
| `REPORT_TOOLCALL_MODE` | Toolcall-Modus |

## Vision & PDF

| Variable | Zweck |
|---|---|
| `ENABLE_PDF_VISION` | PDF-Vision-Extraktion |
| `VISION_MODEL_NAME` | Vision-Modell |
| `VISION_MAX_CALLS_PER_UPLOAD` / `VISION_MAX_DIM` / `VISION_MIN_IMAGE_AREA` / `VISION_PAGE_SCAN_THRESHOLD` | Vision-Limits |

## Observability (OpenTelemetry)

| Variable | Zweck |
|---|---|
| `OTEL_ENABLED` | OTEL-Schalter |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP-Endpoint |
| `OTEL_METRICS_ENABLED` / `OTEL_LOGS_ENABLED` | Metrics/Logs-Export |
| `OTEL_METRIC_EXPORT_INTERVAL` / `OTEL_SERVICE_NAME` | Export-Interval / Service-Name |
| `AGORA_DEBUG_MEMORY` / `AGORA_BERT_MEMORY_PROFILE` | Memory-Debug |
| `TIME_PROFILE` / `TRACEPARENT` | Profiling / Traceparent |

## Testing & E2E

| Variable | Zweck |
|---|---|
| `AGORA_E2E_LLM_MODE` | E2E-LLM-Stub-Modus (z. B. `stub`, `compact`). Der aktive Wert ist unter `GET /api/status` im `e2e`-Teilbaum sichtbar (`llm_mode`, `stub_active`) — die E2E-Suite assertiert hart darauf. |
| `AGORA_SKIP_PREFLIGHT` | Preflight überspringen |
| `AGORA_RUN_ID` | Run-ID für Tests |

---

Siehe auch: [`deployment-dev.md`](deployment-dev.md), [`deployment.md`](deployment.md), [`provider-runtime-settings.md`](provider-runtime-settings.md), [`secret-key-lifecycle.md`](secret-key-lifecycle.md).