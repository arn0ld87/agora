# Handover — Onboarding/Provider-Unification Slice 3

## Stand

- Datum: 2026-07-12
- Worktree: `/private/tmp/agora-onboarding-slice-3`
- Branch: `codex/onboarding-provider-connections` (Basis: `main` @ `5b3b77a`,
  Slice 2 gemergt via PR #684)
- Slice: 3 — Provider-Verbindungen (Connection-Lifecycle, Test/Discovery,
  Statusmodell)
- Arbeitsstand: implementiert, alle Gates grün, Commit/PR in Arbeit
- Teststatus: Backend 3070 passed / 9 skipped / 7 deselected (Exit 0);
  Contracts 295 passed; Frontend 154 Testdateien / 1228 Tests grün;
  `bun run check` (Lint + Typecheck + Coverage-Tests + Build) Exit 0;
  ruff grün; mypy 214 Dateien, 0 Fehler; Schema-Dump: alle 39 Schemas
  driftfrei
- context-mode: funktionsfähig (Batch-Analysen und Session-Memory in dieser
  Session)
- code-review-graph: CLI 2.3.6 via `uvx`; MCP-Anbindung war in dieser Session
  nicht verbunden (Fallback: CLI, gemäß Tooling-Policy §10 dokumentiert).
  Haupt-Repo-Graph am 2026-07-12 auf `main` @ `5b3b77a` neu gebaut
  (973 Dateien, 9366 Knoten, 78746 Kanten) — das war der offene
  Slice-2-Follow-up. Worktree-Graph frisch gebaut (980 Dateien, 9517 Knoten,
  79694 Kanten); `detect-changes` diesmal belastbar.
- Codegraph zuletzt aktualisiert: 2026-07-12 (Haupt-Repo und Worktree)

## Dokumentations-Sync

- README.md: geprüft, nicht betroffen — kein neues Anwenderverhalten
  außerhalb der Settings-View, die dort nicht dokumentiert ist.
- AGENTS.md: geprüft, nicht betroffen — Contract-/Schema-/TDD-Regeln decken
  den Slice ab; Provider-Detection-SSoT unverändert.
- CLAUDE.md: geprüft, nicht betroffen.
- PLAN.md: aktualisiert — Slice 2 gemergt (#684), Slice 3 implementiert.
- docs/STATUS.md: aktualisiert via `scripts/sync-status.sh`.
- CHANGELOG.md: aktualisiert — Connection-Lifecycle, Settings-UI und
  Zod-Enum-Drift-Fix unter `[Unreleased]`.
- Epic-HANDOVER.md: aktualisiert — dieser Stand.
- docs/tooling/agent-tools.md: geprüft, nicht betroffen — keine Tool-Version
  oder Konfiguration geändert.

## Fertig

- Tasks 1–4 des Implementierungsplans (Vortagssession, Commits
  `31dc0d0`…`825946c`): kanonische Lifecycle-Contracts
  (`ProviderConnectionUpsertRequest`, Probe-/Response-Modelle,
  `minimax`/`opencode_go` in `ProviderType`), atomarer
  `ProviderConnectionStore` (`provider_connections.json`, flock, 0600),
  gehärteter Secret-Store, Adapter-Schicht + `ProviderConnectionService`
  (Probe/Discovery), kanonische API `/api/llm/provider-connections*` mit
  Legacy-Routen als Kompatibilitätsadapter.
- Diese Session: RED→GREEN des hinterlassenen Tests — 409
  `provider_unsupported` greift in den kanonischen Routen jetzt VOR
  Body-Validierung und Store-/Service-Zugriff (`814b8dd`); mypy-saubere
  Verengung der Legacy-Adapter (`fc3f5d0`); Legacy-Discovery-Test auf den
  Connection-Service umgestellt (`85b2a90`); Requirements-Docstring
  ehrlich gemacht (`feed5f1`).
- Task 5 (Frontend, agora-frontend-worker): `providerConnections.ts`
  API-Client mit Zod-Validierung an jeder Response-Grenze + 9 Specs;
  `LlmProvidersView.vue` vollständig auf Connection-Lifecycle umgestellt
  (Status-Badges, Test-Ergebnis, Discovery-Liste, lokaler Ollama-Flow,
  Unsupported-Hinweis statt Formular) + 8 View-Specs; additiver
  Lifecycle-State in `store/llmProviders.ts` (Legacy-API unverändert,
  ModelPicker/LlmRoutingView hängen weiter daran); i18n de/en;
  Response-Wrapper-Schemas in `aiProviderContract.ts` ergänzt.
- Task 6: Gates (s. Teststatus), CRG-Delta, Doku-Sync, dieser Handover.

## Noch offen

- Frontend-Commit und Doku-Commit erstellen, Branch pushen, PR eröffnen
  (kein Merge ohne Gemini-Findings-Sichtung).
- CRG-Testlücken-Heuristik meldet die neuen Pinia-Store-Actions
  (`loadConnections`, `upsertConnection`, `testConnection`, …) als ohne
  direkten Test — bewusst offen: die Flows sind über
  `LlmProvidersView.spec.ts` und `providerConnections.spec.ts` indirekt
  abgedeckt; ein dedizierter Store-Unit-Test wäre ein sauberes Follow-up.
- Onboarding-Schritte providers/chat_model an die echte Discovery anbinden:
  bewusst NICHT in diesem Slice (Scope laut
  `docs/superpowers/specs/2026-07-12-provider-connections-design.md` ist die
  Lifecycle-Schicht selbst); folgt mit dem einheitlichen Model Picker
  (Slice 5). Der frühere Docstring, der das für Slice 3 versprach, ist
  korrigiert.
- Subscription-/CLI-Bridges bleiben unsupported (409); Umsetzung nur nach
  separatem positivem Security-Spike.

## Entscheidungen

- Unsupported-Guard sitzt VOR Body-Validierung und Store-Zugriff: ein
  Provider, der nie eine Connection werden darf, soll 409 statt 400/404
  liefern und keine Seiteneffekte auslösen.
- `provider_kind`-Verengung in den Legacy-Adaptern als `cast` mit
  Laufzeit-Absicherung durch den bestehenden `BeforeValidator` — kein
  zweiter Validierungspfad.
- `ProviderDescriptorSchema.type` (Zod) additiv auf die volle
  Backend-Literal-Menge erweitert (vorbestehender Drift, aufgedeckt durch
  Typecheck im neuen View-Code).
- Der transiente `test:coverage`-Exit-1 im ersten Composite-Lauf war nicht
  reproduzierbar; zwei unabhängige Wiederholungen (isoliert und im vollen
  `bun run check`) liefen mit Exit 0.

## Bekannte Risiken

- Discovery/Probe ist zeitgebundene Beobachtung (best effort), kein
  Verfügbarkeitsversprechen; Status wird persistiert und kann veralten.
- SSRF-Grenze: lokale Ollama-Connections nur Loopback, alle übrigen nur
  öffentliche HTTP(S)-URLs — durch Store-, Pydantic- und Zod-Tests belegt.
- Credential-Rotation aus der Slice-1-Prozessdiagnose bleibt separat
  erforderlich (Wert nie reproduzieren).

## Geänderte Verträge und Migrationen

- Nur additive Verträge (Lifecycle-Requests/-Responses, Probe-Status);
  `ai-provider-connection.schema.json` erweitert, 39 Schemas driftfrei.
- Neuer Store legt `provider_connections.json` lazy an; keine Migration
  bestehender Daten. Rollback: neue Module + Routen entfernen; Datendateien
  unter `AGORA_DATA_DIR` sind unabhängig.

## Nächste exakt ausführbare Schritte

1. Frontend- und Doku-Änderungen atomar committen, Branch pushen,
   PR gegen `main` eröffnen; Gemini-Findings sichten, erst danach mergen.
2. Nach Merge: `uvx code-review-graph build` auf `main` + Delta prüfen.
3. Slice 4 (Embedding-Setup und sichere Re-Embedding-Migration) gemäß
   `04-implementation-plan.md` beginnen; dabei den Onboarding-Schritt
   embeddings an die Embedding-Konfiguration anbinden.
4. Optionales Follow-up: Store-Unit-Tests für die neuen Pinia-Actions.

## Relevante Dateien

- `backend/app/contracts/ai_provider_contract.py`, `provider_types.py`
- `backend/app/services/provider_connection_store.py`
- `backend/app/services/provider_connections/{adapters,service}.py`
- `backend/app/services/{llm_provider_registry,llm_provider_secrets_store,model_catalog_service}.py`
- `backend/app/api/llm_providers.py`
- `backend/tests/api/test_provider_connections_api.py`,
  `backend/tests/services/test_provider_connection_store.py`,
  `backend/tests/services/provider_connections/`
- `frontend/src/api/providerConnections.ts` (+ `__tests__`)
- `frontend/src/views/Settings/LlmProvidersView.vue`
  (+ `frontend/src/views/__tests__/LlmProvidersView.spec.ts`)
- `frontend/src/store/llmProviders.ts`
- `frontend/src/contracts/{aiProviderContract,llmRoutingContract}.ts`
- `docs/superpowers/plans/2026-07-12-provider-connections-implementation.md`
- `docs/superpowers/specs/2026-07-12-provider-connections-design.md`
- `docs/decisions/0006-ai-provider-connections.md`

## Befehle zur Verifikation

```bash
cd backend && uv run pytest tests/api/test_provider_connections_api.py \
  tests/services/test_provider_connection_store.py \
  tests/services/provider_connections/ -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check app/ tests/ && uv run mypy app
cd backend && uv run pytest -q
cd frontend && bun run check
bash scripts/sync-status.sh --check
```
