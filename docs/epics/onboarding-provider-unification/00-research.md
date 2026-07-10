# Phase 0 — Research

Stand: 2026-07-10
Branch: `codex/onboarding-provider-unification`
Basis: `bb2b3ea243c1becbf27de3434d4923098f716130`

## Auftrag und Grenzen

Dieser Epic vereinheitlicht Benutzerprofil, Provider-Verbindungen, Modellkatalog,
Routing, Embeddings, Persona-Anzahl und die dazugehörige Oberfläche. Phase 0
ändert keinen Produktcode. Secrets, Auth-Dateien, Browserprofile und Keychain-
Inhalte wurden nicht gelesen.

Nicht-Ziele dieser Phase:

- kein Multi-User- oder Team-System;
- keine produktive Subscription-Bridge;
- kein destruktiver Neo4j-Indexwechsel;
- kein Design-Rewrite parallel zur laufenden Design-v4-Integration;
- keine Reparatur bereits vorhandener Baseline-Fehler.

## Geprüfter Repository-Stand

- Provider-IDs: `backend/app/contracts/provider_types.py`.
- Routing-Verträge: `backend/app/contracts/llm_routing_contract.py`.
- Detection-SSoT: `backend/app/llm/providers/registry.py::detect_provider`.
- Provider-Metadaten: `backend/app/services/llm_provider_registry.py`.
- Live-Modellkatalog: `backend/app/services/model_catalog_service.py`.
- Routing: `llm_routing_seed.py` → `runtime_llm_routing.json` →
  `stage_model_router.py`.
- Embeddings: `backend/app/config.py`, `backend/app/settings.py`,
  `backend/app/storage/embedding_service.py`, Neo4j-Schema-Aufbau.
- Persona-Fluss: `HeroNewRun.vue`, `pendingUpload.ts`, `MainView.vue`,
  `simulation_prepare.py`, `prepare_service.py`,
  `simulation_config_generator.py`, OASIS-Runner.
- Frontend: v4-Shell, Settings-Routen, Model-Picker, Provider-Store,
  Pending-Upload- und Workspace-Flows.

## Verifizierte Defekte und Architekturdrift

1. Provider-Metadaten, Fallbackmodelle und Fähigkeiten sind nicht kanonisch.
   `LlmProviderRegistry` und `ModelCatalogService` enthalten parallele Listen;
   `ollama_cloud` hat bewusst unterschiedliche Fallback-Semantik.
2. `LlmProfile`, `RuntimeLlmConfig`, `ProviderDescriptor`, `ModelEntry` und
   `StageLLMRoute` überlappen fachlich und benötigen mehrere Übersetzungen.
3. Embedding-Konfiguration wird sowohl über die Legacy-`Config` als auch über
   `AgoraSettings` validiert. `EmbeddingService` erkennt Provider unabhängig
   von der Provider-Registry.
4. Bei Dimensionsdrift kann der Neo4j-Index gedroppt und neu angelegt werden,
   ohne vorhandene Embeddings neu zu berechnen. Ein Re-Embedding-Job fehlt.
5. Der im Dashboard gewählte Persona-Wert wird als `num_agents` an den
   Graph-Build gesendet, dort aber nicht gelesen oder persistiert.
6. Ein separater Step-2-Pfad nutzt eigene Defaults und Floors. Quotenlogik,
   Profilgenerator und Simulationsgenerator können 10, 30 oder 50 erzwingen.
   Die gewünschte Anzahl ist daher keine End-to-End-Invariante.
7. Für Provider-, Embedding- und Persona-Flüsse fehlen übergreifende E2E-Tests.
8. Es existiert noch kein Onboarding-Pfad: keine Route, View, Store,
   Completion-Logik oder Tests.
9. Im Frontend existieren zwei Model-Picker, mehrere Profil-/Route-DTOs und ein
   alter Browser-Runtime-Pfad mit eigener Local-/Session-Storage-Semantik.
10. `/settings-classic` dupliziert weiterhin Provider-/Modellkonfiguration;
    `Users & Teams` und `Audit Logs` sind reine Coming-soon-Views.
11. Projekte, Datensätze, Vorlagen und Monitoring sind deaktivierte
    Sidebar-Stubs ohne Route. Ein Benutzerprofil fehlt vollständig.
12. Der produktive v4-Model-Picker hat Lücken bei Labeling, Focus-Visible,
    ARIA-Fehlerzuständen und mobiler Mindestbreite.

Details und Datenflüsse stehen in [01-current-state-map.md](01-current-state-map.md).

## Baseline

- Backend: `2881 passed, 9 skipped, 7 deselected`.
- Contract-Tests: `211 passed`.
- Frontend: `145` Testdateien und `1132` Tests bestanden, der Lauf endet aber
  mit Exit 1 wegen vier `EnvironmentTeardownError`-Rejections aus
  `HistoryView.spec.ts` über den verzögerten Style-Import von
  `CommandPalette.vue`.
- Die Phase-0-Arbeit repariert diesen bestehenden Fehler nicht. Er ist vor dem
  ersten Frontend-Produkt-Slice separat zu klären.
- Setup wählte lokal Python 3.14.6, obwohl das Projekt Python 3.12 als Ziel
  dokumentiert. Die Warnungsflut von `pytest-asyncio` wird als
  Umgebungsabweichung festgehalten.

## Agent-Tooling

- `context-mode` 1.0.169: MCP, Storage, FTS5 und Hooks funktionieren. Doctor
  meldet `[features].hooks` als fehlend in der globalen Codex-Konfiguration,
  obwohl die Plugin-Hooks geladen sind. Kein globales Auto-Upgrade im Epic.
- `code-review-graph` 2.3.6 wurde gegen PyPI verifiziert. Ein globaler
  `uv tool install` kollidiert mit einem vorhandenen Executable; daher kein
  `--force`. Reproduzierbarer Fallback: gepinntes `uvx`.
- MCP-Graph im Worktree: 944 Dateien, 8.803 Knoten, 74.776 Kanten,
  624 Flows und 11 Communities; keine Build-Fehler.

Siehe [07-agent-tooling.md](07-agent-tooling.md) und
[`docs/tooling/agent-tools.md`](../../tooling/agent-tools.md).

## Offizielle Primärquellen

Geprüft am 2026-07-10:

- OpenAI: [API-Authentifizierung](https://platform.openai.com/docs/api-reference/backward-compatibility),
  [Modelle](https://platform.openai.com/docs/api-reference/models),
  [Embeddings](https://platform.openai.com/docs/api-reference/embeddings),
  [Codex mit ChatGPT-Plan](https://help.openai.com/en/articles/11369540-using-codex-with-chatgpt),
  [`codex exec`](https://github.com/openai/codex/blob/main/codex-rs/README.md).
- Anthropic: [API-Authentifizierung](https://platform.claude.com/docs/en/manage-claude/authentication),
  [Modelle und Fähigkeiten](https://platform.claude.com/docs/en/api/models),
  [Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs),
  [Claude Code Setup](https://docs.anthropic.com/en/docs/claude-code/getting-started),
  [CLI Print Mode](https://docs.anthropic.com/en/docs/claude-code/cli-usage).
- Google: [Gemini API](https://ai.google.dev/gemini-api/docs),
  [Function Calling](https://ai.google.dev/gemini-api/docs/function-calling),
  [Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output),
  [Embeddings](https://ai.google.dev/gemini-api/docs/embeddings).
- Ollama: [Authentifizierung](https://docs.ollama.com/api/authentication),
  [Tool Calling](https://docs.ollama.com/capabilities/tool-calling),
  [Embeddings](https://docs.ollama.com/capabilities/embeddings).
- MiniMax: [API Overview](https://platform.minimax.io/docs/api-reference/api-overview),
  [Modelle](https://platform.minimax.io/docs/guides/models-intro).
- OpenCode Go: [Provider-Dokumentation](https://opencode.ai/docs/providers),
  [Go-Plan und Modelle](https://dev.opencode.ai/docs/go/).
- Tooling: [`code-review-graph` 2.3.6](https://pypi.org/project/code-review-graph/),
  [`context-mode`](https://github.com/mksglu/context-mode),
  [Codex Plugins](https://help.openai.com/en/articles/20001256-plugins-in-codex/).

## Offene Fragen vor Slice 1

- Der sichtbare Persona-Wert bedeutet künftig die tatsächlich simulierte
  Gesamtzahl, nicht einen Entity-Cap. Floors werden Warnungen.
- Projekt-Defaults werden als Routingstufe vorgesehen, aber erst mit einem
  klaren Projektvertrag aktiviert.
- CLI-Bridges bleiben ein separater lokaler Security-Spike. Offizielle
  Nichtinteraktivität allein reicht nicht als Produktionsfreigabe.
- Der Embedding-Wechsel braucht einen versionierten Re-Embedding-Job, bevor
  destruktive Indexoperationen entfernt werden können.
- Die Golden-Gate-Referenz wird auf bestehende semantische Agora-Tokens
  abgebildet. Kein dritter Token-Namespace und keine kopierten Referenz-Assets.
