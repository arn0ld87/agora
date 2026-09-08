# Konfiguration — Umgebungsvariablen

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Backend:** `0.9.5`

Die **exakte** Konfigurations-SSoT ist der Code plus [`.env.example`](../.env.example) bzw. [`.env.docker.example`](../.env.docker.example). Diese Seite erklärt die operativ relevanten Gruppen und Semantik. Bei einem neuen Schalter gewinnt deshalb nicht diese Tabelle, nur weil jemand vergessen hat, sie am selben Dienstag zu aktualisieren.

Geheimnisse niemals committen, in Logs ausgeben oder in Run-/Report-Artefakte schreiben.

---

## Installation und Pflicht-Secrets

`./install.sh` erzeugt bei einer frischen Installation `.env` aus der Vorlage und ersetzt bekannte Platzhalter durch sichere Werte. Seit #1483 erzeugt der Host-/Docker-Pfad unter anderem:

- `SECRET_KEY`
- `AGORA_AUTH_TOKEN`
- `AGORA_SECRET_KEY`
- `AGORA_FERNET_KEY`

`AGORA_SECRET_KEY` und `AGORA_FERNET_KEY` müssen **gültige Fernet-Keys** sein. Ein beliebiges `token_urlsafe(32)` ist dafür nicht automatisch geeignet.

`NEO4J_PASSWORD` bleibt eine Operator-Konfiguration, weil Agora das Passwort einer vorhandenen/externalen Neo4j-Instanz nicht erraten kann.

---

## App & Core

| Variable | Zweck |
|---|---|
| `AGORA_DATA_DIR` | Basisverzeichnis für persistente Anwendungsdaten |
| `AGORA_INSTANCE_DIR` | instanzspezifische Einstellungen |
| `AGORA_ALLOW_ANONYMOUS` | Open-Mode; nur bewusst in lokaler/dev Umgebung |
| `AGORA_CORS_ALLOW_ALL` | CORS pauschal öffnen; nicht für Prod |
| `AGORA_EXTRA_ORIGINS` | zusätzliche erlaubte Origins |
| `AGORA_PROXY_FIX_X_FOR`, `_X_HOST`, `_X_PORT`, `_X_PREFIX`, `_X_PROTO` | Reverse-Proxy-Headervertrauen |
| `AGORA_LOG_FORMAT` | Logformat (`text`/strukturierte Variante laut Code) |
| `AGORA_WERKZEUG_LOG_LEVEL` | Werkzeug-Log-Level |
| `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG` | Flask-Dev-Parameter |
| `AGORA_BIND_HOST` | Host-Bind des Compose-Stacks; Default Loopback |
| `AGORA_FRONTEND_PORT`, `AGORA_BACKEND_PORT` | Host-Ports |
| `AGORA_MAX_UPLOAD_SIZE_MB` | Upload-Limit |
| `NLTK_DISABLE_IMPORT_SECURITY` | Workaround für nltk-Import-Hook im Repo/venv-CWD |
| `DOCKER_IPV4_ONLY` | Docker-IPv4-Beschränkung |

## Auth & Secret Stores

| Variable | Zweck |
|---|---|
| `SECRET_KEY` 🔐 | Flask-Session-Signing |
| `AGORA_AUTH_TOKEN` 🔐 | Single-User-Mastertoken für geschützte API-Pfade |
| `AGORA_SECRET_KEY` 🔐 | Fernet-Master-Key für gespeicherte LLM-Provider-Secrets |
| `AGORA_FERNET_KEY` 🔐 | Fernet-Key u. a. für persistierte Agora-API-Keys / Hash-Secret-Fallback |
| `AGORA_TICKET_RATE_LIMIT_MAX`, `AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS` | Signed-Ticket-Rate-Limit |

Die beiden Fernet-Keys erfüllen unterschiedliche Persistenzaufgaben und sind nicht bloß zwei Namen für `SECRET_KEY`. Lebenszyklus/Recovery: [`secret-key-lifecycle.md`](secret-key-lifecycle.md).

Auth-Header werden in [`auth.md`](auth.md) beschrieben. Bevorzugt ist `Authorization: Bearer ...`; `X-Agora-Token` bleibt kompatibel.

## App-Rate-Limits

| Variable | Zweck |
|---|---|
| `AGORA_LLM_TRIGGER_RATE_LIMIT_MAX`, `_WINDOW_SECONDS` | LLM-Trigger |
| `AGORA_REPORT_RATE_LIMIT_MAX`, `_WINDOW_SECONDS` | Report-Generierung |
| `AGORA_UPLOAD_RATE_LIMIT_MAX`, `_WINDOW_SECONDS` | Uploads |

---

## LLM & Provider

Die Provider-Runtime wird heute primär durch `ProviderConnection` + Secret Store + `AiRoute`/`LlmRoute` gesteuert. Die `LLM_*`-Variablen sind wichtige Defaults/Legacy-/Bootstrap-Werte, aber **nicht** die kanonische Wahrheit, sobald eine konkrete Route aufgelöst wurde.

Details: [`provider-runtime-settings.md`](provider-runtime-settings.md).

| Variable | Zweck |
|---|---|
| `LLM_API_KEY` 🔐 | generischer Fallback-Key |
| `LLM_BASE_URL` | generischer Fallback-Endpoint |
| `LLM_MODEL_NAME` | generisches Fallback-Modell |
| `LLM_CONTEXT_LIMIT` | Kontextlimit |
| `LLM_MAX_OUTPUT_TOKENS` | Ausgabe-Limit |
| `LLM_MAX_RETRIES`, `LLM_RETRY_INITIAL_DELAY`, `LLM_RETRY_MAX_DELAY` | Retry-Verhalten |
| `LLM_FORCE_STREAM` | Streaming erzwingen |
| `LLM_MODEL_CONTEXT_LIMITS_JSON` | modellspezifische Context-Limits |
| `LLM_MODEL_OUTPUT_LIMITS_JSON` | modellspezifische Ausgabe-Limits |
| `LLM_MAX_TOKENS_FLOOR` | Untergrenze für `max_tokens` je Call |
| `AGORA_LLM_ALLOW_INSECURE_HTTP` | dokumentierte Ausnahme für Credential-over-HTTP außerhalb sicherer lokaler/private Hosts |
| `LLM_DISABLE_JSON_OBJECT_MODE` | `json_object`-Modus deaktivieren |
| `LLM_DISABLE_JSON_SCHEMA_MODE` | nativen Strict-JSON-Schema-Modus deaktivieren; Pydantic bleibt Grenze |
| `LLM_DISABLE_JSON_MODE` | veralteter Legacy-Alias |

Provider-spezifische Secret-/Endpoint-Variablen existieren für Bootstrap/Legacy-Pfade, z. B. `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `AWS_BEARER_TOKEN_BEDROCK`. Die aktuelle öffentliche Provider-Matrix steht in `backend/app/services/llm_provider_registry.py`.

### CLI-Transport

`codex_cli` benötigt keine Base-URL und keinen API-Key im Agora-Store. Die Authentifizierung stammt aus der lokalen `codex login`-Session. `AGORA_LLM_TRANSPORT=cli` ist ein internes Runtime-Signal an Subprozesspfade; Operatoren sollen daraus **keine zweite Provider-Konfiguration** bauen.

---

## Embeddings

| Variable | Zweck |
|---|---|
| `EMBEDDING_API_KEY` 🔐 | Legacy/Bootstrap-Embedding-Key |
| `EMBEDDING_BASE_URL` | Legacy/Bootstrap-Endpoint |
| `EMBEDDING_MODEL` | Legacy/Bootstrap-Modell |
| `VECTOR_DIM` | Vektordimension |
| `AGORA_SKIP_EMBEDDING_PROBE` | Preflight bewusst überspringen |

Persistente Konfigurationen liegen im `EmbeddingConfigurationStore`; Migrationen verwenden den eigenen Lifecycle aus ADR-0007.

**Bekannter SSoT-Bruch:** Einige Runtime-Consumer lesen weiterhin `Config.EMBEDDING_*`, obwohl die UI eine andere Konfiguration als aktiv markiert. Siehe [#1417](https://github.com/arn0ld87/agora/issues/1417). Bis zur Behebung ist die Env-Konfiguration für produktive Graph-/Evidence-Pfade weiterhin relevant.

---

## Neo4j

| Variable | Zweck |
|---|---|
| `NEO4J_URI` | Bolt-URI |
| `NEO4J_USER` | Benutzer |
| `NEO4J_PASSWORD` 🔐 | Passwort |
| `NEO4J_MAX_POOL_SIZE`, `NEO4J_MAX_LIFETIME` | Pool-Limits |
| `NEO4J_ACQ_TIMEOUT`, `NEO4J_CONN_TIMEOUT`, `NEO4J_LIVENESS_TIMEOUT` | Timeouts |
| `NEO4J_STARTUP_RETRY_MAX`, `NEO4J_STARTUP_RETRY_DELAY` | Startup-Retry |

---

## Redis, Event Bus und Reconciliation

| Variable | Zweck |
|---|---|
| `REDIS_URL` | Redis für Event-/Live-Infrastruktur |
| `EVENT_BUS_BACKEND` | `auto`/`redis`/`file` gemäß Event-Bus-Implementierung |
| `AGORA_STARTUP_RECONCILIATION` | stale Simulations-Runs beim App-/Workerstart prüfen; Default `true` (#1476) |

Startup-Reconciliation korrigiert persistierte Simulation-Runs mit toter PID. Sie ersetzt **keine** persistente Jobqueue für Prepare/Report/Graph; siehe #1472.

---

## Graph & Ontologie

| Variable | Zweck |
|---|---|
| `GRAPH_CHUNK_SIZE`, `GRAPH_CHUNK_OVERLAP` | Chunking |
| `GRAPH_PARALLEL_CHUNKS` | Build-Parallelität |
| `GRAPH_MIN_ENTITIES` | minimale Entitätsqualitätsschwelle |
| `GRAPH_MIN_RELATIONS` | minimale Relationsschwelle; kann blockierend sein |
| `GRAPH_MIN_CHUNK_SUCCESS_RATIO` | Anteil erfolgreicher Chunks |
| `GRAPH_MEMORY_PUT_TIMEOUT`, `GRAPH_MEMORY_QUEUE_MAX` | Graph-Memory-Backpressure |
| `ONTOLOGY_MAX_ENTITY_TYPES`, `ONTOLOGY_MAX_EDGE_TYPES`, `ONTOLOGY_MIN_ENTITY_TYPES` | Ontologie-Grenzen |
| `ONTOLOGY_MUTATION_MODE`, `ONTOLOGY_MUTATION_MIN_CONFIDENCE` | Mutation |
| `HYBRID_SEARCH_VECTOR_WEIGHT`, `HYBRID_SEARCH_KEYWORD_WEIGHT` | Hybrid-Suche |

---

## Simulation & OASIS

| Variable | Zweck |
|---|---|
| `OASIS_DEFAULT_MAX_ROUNDS` | Standardrunden |
| `AGORA_AGENTS_PER_BATCH` | Persona-/Agent-Batching |
| `AGORA_ALLOW_SMALL_SIM` | kleine Simulationen bewusst erlauben |
| `PERSONA_REVIEW_ENABLED` | Review-Gate |
| `ENABLE_AGENT_TOOLS` | Agent-Tools aktivieren |
| `MAX_TOOL_CALLS_PER_ACTION` | Tool-Limit pro Aktion |

Ein persistierter `random_seed` ist derzeit **noch kein vollständiger Reproduktionsanker**. Siehe #763/#1274.

---

## Report

| Variable | Zweck |
|---|---|
| `REPORT_LANGUAGE` | Berichtssprache |
| `REPORT_AGENT_TEMPERATURE` | Agent-Temperatur |
| `REPORT_AGENT_MAX_REFLECTION_ROUNDS` | ReAct-/Reflection-Limit |
| `REPORT_AGENT_MAX_TOOL_CALLS` | Tool-Limit |
| `REPORT_TOOLCALL_MODE` | Toolcall-Modus: `native` (Default) oder `xml`. Ungültige Werte fallen auf `native` zurück. |
| `REPORT_REQUIREMENT_CHECKER_ENABLED` | Requirement-Check aktivieren/deaktivieren, primär für kontrollierte Tests/Debug |

Run-Budgets werden nicht durch diese Report-Variablen ersetzt; Budgetgrenzen sind eigene Run-Verträge.

---

## Vision & PDF

| Variable | Zweck |
|---|---|
| `ENABLE_PDF_VISION` | PDF-Vision |
| `VISION_MODEL_NAME` | Vision-Modell |
| `VISION_MAX_CALLS_PER_UPLOAD` | Call-Cap |
| `VISION_MAX_DIM` | Bilddimension |
| `VISION_MIN_IMAGE_AREA` | Mindestfläche |
| `VISION_PAGE_SCAN_THRESHOLD` | Scan-Schwelle |

Vision-Aufrufe werden seit #1478 in Budget-Guard und Ledger erfasst.

---

## Observability

| Variable | Zweck |
|---|---|
| `OTEL_ENABLED` | OpenTelemetry-Schalter |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP-Endpunkt |
| `OTEL_METRICS_ENABLED`, `OTEL_LOGS_ENABLED` | Exportarten |
| `OTEL_METRIC_EXPORT_INTERVAL`, `OTEL_SERVICE_NAME` | Export-Intervall/Name |
| `AGORA_DEBUG_MEMORY`, `AGORA_BERT_MEMORY_PROFILE` | Memory-Diagnose |
| `TIME_PROFILE`, `TRACEPARENT` | Profiling/Tracing |

---

## Tests und echte Integrationsdienste

Unit-/Contract-Tests sollen nicht von der lokalen `.env` abhängen (#1462).

Für echte Service-Integrationstests:

| Variable | Zweck |
|---|---|
| `AGORA_TEST_REDIS_URL` | Redis-Server für Integrationstest |
| `AGORA_TEST_NEO4J_URI` | Neo4j-URI |
| `AGORA_TEST_NEO4J_USER` | Neo4j-Testuser |
| `AGORA_TEST_NEO4J_PASSWORD` 🔐 | Neo4j-Testpasswort |
| `AGORA_TEST_REQUIRE_SERVICES` | wenn `1`, fehlende Services sind Fail statt Skip (#1481) |
| `AGORA_E2E_LLM_MODE` | E2E-LLM-Modus |
| `AGORA_SKIP_PREFLIGHT` | gezielter Test-/Debug-Bypass |

Historische `TEST_REDIS_URL`-Verwendungen existieren eventuell noch in älteren Tests/Dokumenten; für die neue echte Integrationsschicht sind die `AGORA_TEST_*`-Variablen maßgeblich.

---

## Praktische Regel

Bei Konfigurationsproblemen zuerst [`.env.example`](../.env.example), dann `backend/app/config.py` und die jeweilige SSoT lesen. **Nicht** einen alten Screenshot oder eine im Browser gespeicherte Provider-Auswahl als Runtime-Wahrheit behandeln.
