# Provider-Verbindungen — Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sichere, persistierte Provider-Verbindungen mit Test und
Modell-Discovery für alle API- und lokalen HTTP-Anbieter aus dem Master-Prompt.

**Architecture:** `ProviderConnection` bleibt die öffentliche Pydantic-SSoT;
eine neue Connection-Service-Schicht verwaltet Metadaten und Secret-Referenzen.
Kleine Adapter kapseln nur provider-spezifische Test-/Discovery-Protokolle. Die
API serialisiert ausschließlich secret-freie Response-Modelle und das Frontend
validiert die identische Semantik mit Zod.

**Tech Stack:** Python 3.12+, Flask, Pydantic v2, `httpx`, Fernet-Secret-Store,
Vue 3, TypeScript, Zod, pytest, Vitest.

## Globale Constraints

- Keine Klartext-Secrets in Responses, Logs, Browser-Storage, Tests oder Docs.
- Custom-HTTP akzeptiert ausschließlich öffentliche HTTP(S)-Base-URLs; lokales
  Ollama ist die einzige explizite Ausnahme.
- CLI-/Subscription-Bridges bleiben `unsupported`; keine Auth-Dateien, Cookies,
  Keychains oder inoffiziellen OAuth-Flows lesen.
- Es gibt genau eine fachliche Provider-Metadatenquelle; bestehende LLM-Presets
  und API-Key-Endpoints bleiben abwärtskompatibel.
- Jede Verhaltensänderung beginnt mit einem nachweislich roten Test.

---

## Task 1 — Provider-Typen und öffentliche Contracts erweitern

**Files:**
- Modify: `backend/app/contracts/provider_types.py`
- Modify: `backend/app/contracts/ai_provider_contract.py`
- Modify: `backend/app/contracts/__init__.py`
- Modify: `frontend/src/contracts/aiProviderContract.ts`
- Modify: `backend/tests/contracts/test_provider_types.py`
- Modify: `backend/tests/contracts/test_ai_provider_contract.py`
- Modify: `frontend/src/contracts/__tests__/aiProviderContract.spec.ts`

- [x] Zuerst Tests für `minimax` und `opencode_go`, für den lokalen
  Ollama-Transport und für die secret-freie Serialisierung schreiben. Der Test
  darf vor der Implementierung mit unbekanntem Provider-Typ bzw. fehlendem
  Request/Response-Vertrag fehlschlagen.
- [x] `ProviderType` und die Zod-Enum um `minimax` und `opencode_go` ergänzen.
  Die bestehenden `ProviderConnection`-Felder bleiben kompatibel; neue
  Lifecycle-Request-/Response-Modelle trennen Eingabegeheimnisse von der
  öffentlichen Connection:

  ```python
  class ProviderConnectionUpsertRequest(BaseModel):
      model_config = ConfigDict(extra="forbid")
      display_name: str = Field(min_length=1)
      provider_kind: ProviderType
      base_url: str | None = None
      enabled: bool = True
      api_key: SecretStr | None = Field(default=None, exclude=True)

  class ProviderConnectionResponse(BaseModel):
      model_config = ConfigDict(extra="forbid")
      connection: ProviderConnection
  ```

- [x] Für lokale Ollama-Verbindungen einen separaten Validator verwenden, der
  nur explizite lokale Loopback-URLs zulässt; `PublicBaseUrl` unverändert für
  alle Custom-HTTP-Verbindungen behalten.
- [x] Backend- und Frontend-Contract-Tests grün ausführen:

  ```bash
  cd backend && uv run pytest tests/contracts/test_provider_types.py tests/contracts/test_ai_provider_contract.py -q
  cd frontend && bun vitest run src/contracts/__tests__/aiProviderContract.spec.ts
  ```

  Erwartung: beide Befehle Exit 0; kein API-Key in `model_dump(mode="json")`.

## Task 2 — Connection-Metadaten additiv und atomar persistieren

**Files:**
- Create: `backend/app/services/provider_connection_store.py`
- Create: `backend/tests/services/test_provider_connection_store.py`
- Modify: `backend/app/services/llm_provider_secrets_store.py`

- [x] Rote Store-Tests für leeres Laden, Upsert, Status-Persistenz,
  Aktualisierungszeitpunkt, Delete und atomaren Rollback bei fehlerhaftem Write
  schreiben.
- [x] `ProviderConnectionStore` mit `AGORA_DATA_DIR/provider_connections.json`,
  `flock`, atomarem Tempfile-Replace und Modus `0600` implementieren. Der Store
  persistiert `ProviderConnection`, nie `api_key`.
- [x] Den bestehenden `LlmProviderSecretsStore` über seine öffentliche
  `upsert(provider_id, api_key)`-/`delete(provider_id)`-API nutzen. Die
  Connection speichert als `secret_ref` ausschließlich `provider_id`.
- [x] Folgende Service-Operationen einführen und vollständig testen:

  ```python
  def list_connections(self) -> list[ProviderConnection]: ...
  def upsert_connection(self, request: ProviderConnectionUpsertRequest) -> ProviderConnection: ...
  def delete_connection(self, connection_id: str) -> bool: ...
  def update_probe(
      self,
      connection_id: str,
      *,
      status: ProviderStatus,
      status_message: str | None,
      tested_at: datetime,
  ) -> ProviderConnection: ...
  ```

- [x] Ausführen: `cd backend && uv run pytest tests/services/test_provider_connection_store.py tests/services/test_llm_provider_secrets_store.py -q`.

## Task 3 — Registry und Adapter-Matrix vereinheitlichen

**Files:**
- Create: `backend/app/services/provider_connections/adapters.py`
- Create: `backend/app/services/provider_connections/service.py`
- Create: `backend/tests/services/provider_connections/test_adapters.py`
- Create: `backend/tests/services/provider_connections/test_service.py`
- Modify: `backend/app/services/llm_provider_registry.py`
- Modify: `backend/app/services/model_catalog_service.py`

- [x] Zuerst parametrische rote Adapter-Tests für OpenAI, Anthropic, Gemini,
  MiniMax, Ollama Cloud, OpenCode Go, OpenAI-kompatibel und lokales Ollama
  schreiben. Jeder Test liefert entweder Modelle oder einen normalisierten
  `ProviderProbeResult`, nie einen rohen Transportfehler.
- [x] Das Adapter-Protokoll und Resultat definieren; Task 3 mappt sein Resultat
  auf die primitive `ProviderConnectionStore.update_probe(...)`-Signatur aus
  Task 2:

  ```python
  @dataclass(frozen=True)
  class ProviderProbeResult:
      status: Literal["available", "unavailable", "invalid_credentials", "degraded", "unsupported"]
      status_message: str | None
      models: tuple[AiModel, ...] = ()

  class ProviderConnectionAdapter(Protocol):
      def probe(self, connection: ProviderConnection, api_key: str | None) -> ProviderProbeResult: ...
  ```

- [x] Die Registry als einzige Matrix für `provider_kind`, Display-Name,
  Transport, Auth-Modus, Standard-Base-URL und Adapter-Fabrik ausbauen. Sie
  enthält die acht freigegebenen HTTP-Verbindungen; Codex- und Claude-Code-
  Bridges bekommen ausschließlich `unsupported`-Metadaten.
- [x] Vor der konkreten URL-/Header-Implementierung jede Anbieterregel gegen
  die offizielle Dokumentation festhalten. Gemini nutzt die dokumentierte
  OpenAI-Kompatibilität mit `/v1beta/openai/` und `models.list`; die übrigen
  Adapter dürfen nicht aus unbestätigten Endpunkten abgeleitet werden.
- [x] `ModelCatalogService` nur hinter dem Adapter verwenden oder dessen
  vorhandene HTTP-Abstraktion extrahieren; kein zweiter Discovery-Codepfad.
- [x] Ausführen: `cd backend && uv run pytest tests/services/provider_connections -q`.

## Task 4 — Lifecycle-API ohne Secret-Leak ergänzen

**Files:**
- Modify: `backend/app/api/llm_providers.py`
- Create: `backend/tests/api/test_provider_connections_api.py`
- Modify: `backend/tests/api/test_provider_override_key_fallback.py`

- [x] Rote API-Tests für List, Upsert, Delete, Test und Discovery anlegen.
  Prüfen: 400 bei ungültiger URL, 404 bei unbekannter Connection, 409 bei
  unzulässigem Statusübergang und kein Klartext im JSON, auch wenn der Request
  einen Key enthielt.
- [x] Unter `/api/llm/provider-connections` diese Routen implementieren:

  ```text
  GET    /provider-connections
  PUT    /provider-connections/<connection_id>
  DELETE /provider-connections/<connection_id>
  POST   /provider-connections/<connection_id>/test
  GET    /provider-connections/<connection_id>/models
  ```

- [x] Die alten `/providers`, `/providers/<id>/models`, `/test` und
  `/api-key`-Routen als Kompatibilitätsadapter behalten; sie delegieren an die
  neue Service-Schicht, statt parallele Secret-/Discovery-Logik zu behalten.
- [x] `handle_api_errors` und strukturiertes Logging verwenden; in Fehlern nur
  Connection-ID, Provider-Kind und normalisierte Kategorie loggen.
- [x] Ausführen: `cd backend && uv run pytest tests/api/test_provider_connections_api.py tests/api/test_provider_override_key_fallback.py -q`.

## Task 5 — Frontend-API und Settings-Verbindungen integrieren

**Files:**
- Create: `frontend/src/api/providerConnections.ts`
- Modify: `frontend/src/views/Settings/LlmProvidersView.vue`
- Modify: `frontend/src/store/llmProviders.ts`
- Create: `frontend/src/api/__tests__/providerConnections.spec.ts`
- Modify: `frontend/src/views/__tests__/LlmProvidersView.spec.ts`

- [x] Rote Vitest-Fälle für Zod-Validierung, maskierte Connection-Responses,
  Test-Status und den lokalen-Ollama-Flow schreiben.
- [x] API-Client mit `ProviderConnectionSchema` an jeder Response-Grenze
  implementieren; Eingabe-Keys nur im PUT-Body senden und nicht im Pinia-State
  speichern.
- [x] Den vorhandenen Settings-Provider-View auf Connection-Lifecycle
  umstellen: konfiguriert/nicht konfiguriert, Test-Ergebnis und Discovery
  sichtbar; Subscription-Bridges klar als nicht unterstützt markieren.
- [x] Ausführen: `cd frontend && bun vitest run src/api/__tests__/providerConnections.spec.ts src/views/__tests__/LlmProvidersView.spec.ts`.

## Task 6 — Verträge generieren, vollständige Qualitätsgates und Dokumentation

**Files:**
- Modify: `schemas/*.schema.json` (nur per Generator)
- Modify: `docs/epics/onboarding-provider-unification/HANDOVER.md`
- Modify: `PLAN.md`
- Modify: `docs/STATUS.md`
- Modify: `CHANGELOG.md`
- Review only: `README.md`, `AGENTS.md`, `CLAUDE.md`, `docs/tooling/agent-tools.md`

- [x] Schema-Generator ausführen und Drift prüfen:

  ```bash
  cd backend && uv run python -m app.contracts.dump_schemas
  git diff --exit-code schemas/
  ```

- [x] Vollständige Gates ausführen und Resultate mit exakten Zählwerten im
  Handover dokumentieren:

  ```bash
  cd backend && uv run ruff check . && uv run mypy app && uv run pytest -x -q
  cd frontend && bun run check
  bash scripts/sync-status.sh --check
  ```

- [x] `code-review-graph` inkrementell aktualisieren; Delta, Impact Radius,
  betroffene Tests und Testlücken für geänderte Dateien prüfen.
- [x] Doc-Impact-Tabelle im Handover führen: `aktualisiert`, `geprüft, nicht
  betroffen` oder `bewusst offen mit Begründung`. Danach nur konkrete Dateien
  stagen und atomar committen.

## Reihenfolge und Checkpoints

1. Tasks 1–2: Contracts und Persistenz, Commit `feat(providers): persist provider connections`.
2. Tasks 3–4: Adapter, Service und API, Commit `feat(providers): probe and discover connections`.
3. Task 5: Settings-Integration, Commit `feat(settings): manage provider connections`.
4. Task 6: Schemas, Gates und Handover, Commit `docs(epic): hand over provider connections slice`.

Jeder Checkpunkt setzt grüne zielgerichtete Tests voraus. Bei einer roten
Baseline oder nicht belegtem Provider-Protokoll wird gestoppt, die Ursache
festgehalten und kein Folgetask begonnen.
