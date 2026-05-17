# Spec — Projektweites ModelPicker + Backend-Key-Passthrough ohne .env

**Datum:** 2026-05-17
**Branch:** `feat/llm-dropdown-and-key-passthrough`
**Scope:** Frontend-UI-Konsolidierung + Backend-Subprocess-Env-Fix

---

## Problem

1. **Aufgabe 1 — Inkonsistente Modell-Auswahl im Frontend.** Auf `/settings/llm-providers` zeigt der „Workspace-Default"-Card ein gruppiertes/alphabetisch sortiertes Dropdown (alle Provider mit hinterlegtem Key, OptGroup pro Provider). An anderen Stellen wird die Modell-Auswahl **nicht** über diese Komponente gemacht:
   - `LlmRoutingView.vue` baut eigenes `<select>` mit `modelsFor(provider_id)` und fällt für Ollama auf ein `<input>` zurück.
   - `Step4Report.vue` nutzt einen externen Sub-Component `ReportModelControls` mit getrennten v-models für `reportModelOption` und `customReportModel`.
   - `HeroNewRun.vue` bindet `modelOption` an einen String (Profile-IDs, Presets, Ollama-Modelle).

2. **Aufgabe 2 — `.env`-Zwang für Gemini-Runs.** Auch wenn der User unter `/settings/llm-providers` einen Google-API-Key speichert (`LlmProviderSecretsStore`, Fernet-verschlüsselt), schlägt der Sim-Start fehl, weil der OASIS-Subprocess `os.environ["GOOGLE_API_KEY"]` liest. `build_route_subprocess_env` (`backend/app/services/llm_routing_seed.py`) injiziert pro Subprocess nur `LLM_API_KEY` und `OPENAI_API_KEY`, aber **nicht** `GOOGLE_API_KEY`. Ergebnis: `.env` ist Pflicht für Gemini, obwohl der Key bereits verschlüsselt im Backend-Store liegt.

---

## Lösung

### A. Frontend — Canon-ModelPicker projektweit

Canon-Komponente: `frontend/src/components/v4/forms/ModelPicker.vue`. Sie wird bereits in `LlmProvidersView.vue` für den Workspace-Default genutzt, hat OptGroup-Rendering, sortiert nach Provider-Label, versteckt Provider ohne Key (Ausnahme: github_copilot), emittiert `StageLLMRoute`.

**Migrations:**

| Datei | Aktuell | Ziel |
|---|---|---|
| `components/LlmRouting/LlmRoutingView.vue` | Eigenes `<select>` + Ollama-`<input>` fallback | `<ModelPicker v-model>` für `global_default` und jeden Stage-Override |
| `components/Step4Report.vue` (über `ReportModelControls`) | `v-model:report-model-option` + `v-model:custom-report-model` | `<ModelPicker v-model>` für gewähltes Modell; Custom-Text-Fall bleibt Spezial-Eingabe (Ollama-Custom-Model), aber Provider+Modell-Quelle ist Picker |
| `components/v4/dashboard/HeroNewRun.vue` | Single-String `modelOption` mit Profilen/Presets/Ollama | Hybrid: Profile/Preset-Picker bleibt, ZUSÄTZLICH `<ModelPicker>` für „Direkt Provider+Modell auswählen". Optional, kein UX-Bruch. |

**Datenquelle:** `useLlmProvidersStore` (Pinia). `availableProviders` (mit Key) → `store.models[provider_id]` (live-discovery). Keine Hardcoded-Listen.

**Erweiterung ModelPicker:** Falls für `Step4Report`/`HeroNewRun` nötig, ein optionales `allow-empty` und `placeholder`-Prop (existieren schon) reichen aus. Kein `allowCustom` als Erweiterung — das übernimmt der Eltern-Code, der Custom-Text-Fall ist außerhalb der Picker-Verantwortung.

### B. Backend — Provider-spezifische Env-Vars im Subprocess

**Fix-Punkt:** `backend/app/services/llm_routing_seed.py::build_route_subprocess_env`.

**Vorher:**
```python
env: dict[str, str] = {"LLM_MODEL_NAME": route.model}
if api_key:
    env["LLM_API_KEY"] = api_key
    env["OPENAI_API_KEY"] = api_key
```

**Nachher:**
```python
env: dict[str, str] = {"LLM_MODEL_NAME": route.model}
if api_key:
    env["LLM_API_KEY"] = api_key
    env["OPENAI_API_KEY"] = api_key
    # Provider-spezifische Env-Vars für OASIS-Subprocess.
    # OASIS liest GOOGLE_API_KEY für Gemini, ANTHROPIC_API_KEY für Anthropic.
    provider_type = _provider_type_for(route.provider_id)
    if provider_type == "google":
        env["GOOGLE_API_KEY"] = api_key
    elif provider_type == "anthropic":
        env["ANTHROPIC_API_KEY"] = api_key
```

Helfer `_provider_type_for` konsultiert `LlmProviderRegistry`.

**Auflösungsreihenfolge bleibt unverändert** (`SecretResolver.get_api_key`):
1. Frontend-Override (Session-Key, runtime payload)
2. `LlmProviderSecretsStore` (verschlüsselter Disk-Store, vom Frontend gespeichert)
3. `os.environ` (`.env`-Fallback)

Heißt: wer eine `.env` hat, behält sie. Wer keine hat, kommt mit dem Frontend-Store aus.

### C. Sicherheit

- Plaintext-Keys bleiben im **Backend-Memory** während des Sim-Start-Requests. Frontend bekommt nur `masked_value` zurück.
- Subprocess-Env-Vars sind nicht in Logs sichtbar (`build_route_subprocess_env` wird nicht geloggt; nur die Tatsache, dass ein Run gestartet wurde).
- Keine neue Storage-Form: keine `localStorage`-Keys, keine HTTP-Header mit Plaintext-Keys.

---

## Out of Scope

- Komplette HeroNewRun-Umbau (LLM-Profile + Presets + Ollama-Quick-Pick). Bleibt funktional; ModelPicker wird **zusätzlich** als „Direkt-Auswahl"-Option angeboten, nicht als Ersatz.
- LiteLLM-Routing-Migration. Aktueller Routing-Stack (`StageModelRouter`, `ResolvedRoute`) bleibt.
- Neue Crypto. `LlmProviderSecretsStore` (Fernet) bleibt unverändert.

---

## Tests

- **Backend:** Erweitere `backend/tests/services/test_llm_routing_seed.py` um Cases:
  - `build_route_subprocess_env(route_with_provider_id="google", api_key="X")` → `env["GOOGLE_API_KEY"] == "X"`.
  - Idempotent für openai/anthropic.
  - Kein `GOOGLE_API_KEY` im Env wenn `api_key=None`.
- **Frontend:** vorhandene ModelPicker-Unit-Tests laufen weiter; neue Integration: `LlmRoutingView.vue` rendert `<ModelPicker>` und speichert via `setGlobalDefault`.

## Verification

- `cd backend && ruff check app/ tests/ && pytest tests/services/test_llm_routing_seed.py tests/scripts/test_oasis_provider_dispatch.py -x`
- `cd frontend && pnpm typecheck && pnpm test:unit --run`
- Manuell auf `localhost:5180`: `/settings/llm-providers` Workspace-Default Dropdown unverändert; `/settings/llm-routing` zeigt jetzt gleichen Dropdown-Stil.
- Manuell: Sim-Start mit Gemini-Provider ohne `.env`-Eintrag → läuft durch.

## PR

Titel: `feat(llm): projektweiter ModelPicker + Subprocess-Env-Fix für Gemini`

Body verweist auf dieses Spec.
