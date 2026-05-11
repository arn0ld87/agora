# Frontend-Fixes & Persona-Qualität — Implementierungsplan

**Stand:** 2026-05-03
**Repo:** [`arn0ld87/agora`](https://github.com/arn0ld87/agora) · post `v0.9.0`, Layer 0–6 grün
**Auslöser:** User-Bugreport vom 2026-05-03 mit 10 zusammenhängenden Befunden zu Persona-Generierung, Modell-Auswahl, Live-Settings, Step3→Step4-Übergang, Backend-Request-Rate.
**Workflow:** Jeder Sub-Slice via `/agora-next-task` → Subagent (überwiegend **Sonnet**, **kein Haiku**) → `/verify-after-subagent` → Commit → PR → Gemini-Review-Cycle → FF-Merge auf `main`.
**Branch-Schema:** `feat/task-XX-kurztitel` (siehe `CLAUDE.md`).

---

## Befunds-Cluster

| ID | Befund (User-Wortlaut verkürzt) | Cluster | Schwere | Sub-Slice |
|---|---|---|---|---|
| **B1** | „Persona-Erstellung dauert teils ewig" | Performance | hoch | I |
| **B2** | „Modellauswahl im Frontend wird komplett ignoriert" | Settings-Wiring | hoch | C |
| **B3** | „Will env-Settings im Frontend setzen, sofort wirksam" | Settings-Wiring | hoch | D |
| **B4** | „Backend hat extrem viele Zugriffe, mehrere/Sekunde — normal?" | Performance / Diagnose | mittel | J |
| **B5** | „Modelle stellen manchmal keine Beziehungen zwischen Entitäten her" | Persona-/Graph-Qualität | mittel | H |
| **B6** | „Ausschließlich deutsche Namen — soll demographische Verteilung sein" | Persona-Qualität | mittel | F |
| **B7** | „Will sehen, welches Modell gerade arbeitet" | UX / Observability | mittel | E |
| **B8** | „Fast nur IT-Personas, Agora ist nicht nur für IT" | Persona-Qualität | mittel | G |
| **B9** | „Manuell hinzugefügte Personas werden ignoriert" | Pipeline-Bug | hoch | B |
| **B10** | „Nach Simulation kein Button mehr zur Berichterstellung" | UX-Blocker | **kritisch** | A |

---

## Reihenfolge

1. **A** (Step3→Step4-Button) — kritischer UX-Blocker, kleinster Diff, sofort wertstiftend.
2. **B** (Manuelle Personas ignoriert) — Datenpfad-Bug, blockiert sinnvolle Simulationen.
3. **J** (Request-Rate-Audit, **read-only**) — bevor wir was ändern, wissen wir, was passiert.
4. **C** (Frontend-Modellwahl durchsetzen) — Backend-Wiring-Bug.
5. **D** (Live-Settings im Frontend) — baut auf C auf, braucht erweitertes `settings_layer.py`.
6. **E** (Live-Modell-Anzeige) — kann parallel zu D laufen, gleicher Event-Bus.
7. **F** (Demographische Namen) — Prompt-Engineering, isoliert.
8. **G** (IT-Bias raus) — Prompt-Engineering + Quoten-Default, baut auf F auf.
9. **H** (Entity-Relationships) — Graph-Builder-Prompt-Engineering.
10. **I** (Persona-Latenz-Fix) — nach J + C + D, weil dort schon Hebel adressiert.

---

## Subagent- und Modell-Routing

User-Vorgabe: **Sonnet bevorzugen, Haiku komplett vermeiden.**
Doku-Sub-Slices werden ausnahmsweise nicht an `agora-doc-worker` (Haiku) delegiert, sondern als Anhang zum jeweiligen Code-Sub-Slice mitgepflegt.

| Sub-Slice | Lead | Subagent | Modell |
|---|---|---|---|
| A — Step3→Step4-Button | Lead Opus (Cross-FSM) | `agora-frontend-worker` | Sonnet |
| B — Manuelle Personas | Lead Opus (Layer 0+1+4 Touch) | `agora-refactor-worker` + `agora-test-worker` | Sonnet |
| C — Modellwahl durchsetzen | Lead Sonnet | `agora-refactor-worker` + `agora-frontend-worker` | Sonnet |
| D — Live-Settings | **Lead Opus** (Layer-0-Schema) | `agora-refactor-worker` + `agora-frontend-worker` | Sonnet |
| E — Modell-Anzeige | Lead Sonnet | `agora-refactor-worker` + `agora-frontend-worker` | Sonnet |
| F — Demographische Namen | Lead Opus (Wording-Glossar / Prompt-Semantik = Layer 2) | `agora-refactor-worker` | Sonnet |
| G — IT-Bias raus | Lead Sonnet | `agora-refactor-worker` | Sonnet |
| H — Entity-Relationships | Lead Sonnet | `agora-refactor-worker` + `agora-evidence-auditor` | Sonnet |
| I — Persona-Latenz | Lead Sonnet | `agora-refactor-worker` | Sonnet |
| J — Request-Rate-Audit | Lead Sonnet | `agora-evidence-auditor` (read-only) | Sonnet |

> **Opus-Trigger laut `CLAUDE.md`:** Layer-0 (Pydantic-Contracts) → D. Wording-/Prompt-Semantik (Layer 2, Glossar v1) → F. Cross-Layer / FSM-Übergänge → A, B. In diesen Slices die Spezifikations- und Review-Phase im Lead-Opus-Kontext, die Implementierung an Sonnet-Subagent.

---

## Sub-Slice A — Step3→Step4 Transition-Button (UX-Blocker)

| Feld | Wert |
|---|---|
| Layer | 4 (Frontend) + 1 (Simulation-FSM Kontrolle) |
| Branch | `fix/task-A-step3-to-step4-button` |
| Subagent | `agora-frontend-worker` (Sonnet) |
| Slash-Befehl | `/agora-next-task` (mit Slice-ID „A" überschreiben) |

### Befund (verifiziert)

`Step3Simulation.vue` zeigt nach dem FSM-Endzustand keinen „Weiter zum Bericht"-Knopf mehr. Vermutlich weil ein Watch oder ein berechneter Disabled-State auf eine Variable hängt, die beim FSM-Endzustand `null` wird (siehe Followup-Commit `5e93046 fix(frontend): Step3 — Unread-Counter beim resetState mitziehen`).

### Vorgehen (TDD)

1. **RED** — Test in `frontend/src/components/__tests__/Step3Simulation.spec.ts`:
   ```ts
   it('zeigt "Weiter zum Bericht"-Button, wenn FSM in COMPLETED', async () => {
     const { wrapper } = mount(...)
     simulationStore.setState('COMPLETED')
     await flushPromises()
     expect(wrapper.find('[data-test="goto-report-btn"]').exists()).toBe(true)
     expect(wrapper.find('[data-test="goto-report-btn"]').attributes('disabled')).toBeUndefined()
   })
   ```
2. `cd frontend && npm test -- --run Step3Simulation` → muss FAIL.
3. **GREEN** — `Step3Simulation.vue`: `canProceed`-Computed an `simulationStore.state === 'COMPLETED' || 'FINALIZED'` knüpfen, Button mit `data-test="goto-report-btn"` hinzufügen, `@click="$emit('next-step')"` (Pattern wie `Step2EnvSetup.vue`).
4. App lokal hochfahren (`npm run dev`), durchklicken bis Step3 abgeschlossen — Button muss erscheinen, Klick → Step4.
5. `npm run check` lokal grün.
6. Commit: `fix(frontend): Step3 — Weiter-zum-Bericht-Button bei COMPLETED-State (Sub-Slice A, schließt B10)`
7. PR + Gemini-Review-Cycle (siehe `CLAUDE.md` § PR-Workflow).

### Akzeptanz

- Vitest-Test im `__tests__`-Ordner deckt COMPLETED- und IN_PROGRESS-State ab (kein Button bei IN_PROGRESS).
- Lokaler Smoke: voller Wizard-Durchlauf von Step1 bis Step4 ohne Maus-Trick.
- Kein Watch-Memleak: `resetState` nullt das Flag wieder, Test deckt Re-Run einer zweiten Simulation ab.

---

## Sub-Slice B — Manuell hinzugefügte Personas werden ignoriert (Pipeline-Bug)

| Feld | Wert |
|---|---|
| Layer | 0 (PersonaQuotaPlan), 1 (`prepare_service.py`), 4 (`Step2EnvSetup.vue`) |
| Branch | `fix/task-B-manual-personas-respektieren` |
| Subagent | `agora-test-worker` (Sonnet, RED) → `agora-refactor-worker` (Sonnet, GREEN) |

### Befund (Hypothese, in Slice zu verifizieren)

Wenn der User in `Step2EnvSetup.vue` nach `POST /api/personas/generate` zusätzliche Personas im Editor anlegt, übergibt der Sim-Start-Payload entweder
**(a)** nur die ursprünglich generierte Liste,
**(b)** überschreibt manuelle Personas mit Quoten-Generator-Output, oder
**(c)** verwirft Personas, die nicht den `PersonaQuotaPlan`-Buckets zugeordnet sind.

### Vorgehen

1. **Verify-First (rg, kein Code-Change):**
   ```bash
   rg -n "manualPersonas|customPersonas|personas\.value" frontend/src/components/Step2EnvSetup.vue
   rg -n "personas:" backend/app/api/simulation*.py backend/app/services/prepare_service.py
   ```
2. **RED — Backend-Test:** `backend/tests/services/test_prepare_service.py`
   ```python
   def test_prepare_service_keeps_manual_personas():
       plan = PersonaQuotaPlan(...)
       generated = [_persona("p1", source="generator")]
       manual = [_persona("p2", source="manual")]
       result = prepare_simulation(plan=plan, personas=generated + manual)
       assert {p.id for p in result.personas} == {"p1", "p2"}
       assert next(p for p in result.personas if p.id == "p2").source == "manual"
   ```
3. **RED — Frontend-Test:** `Step2EnvSetup.spec.ts` — Mock-Persona im Editor anlegen, `startSimulation`-Payload assertieren, `personas` muss beide enthalten und Reihenfolge stabil halten.
4. `pytest -x backend/tests/services/test_prepare_service.py` und `npm test -- --run Step2EnvSetup` → beide FAIL.
5. **GREEN:**
   - `PersonaQuotaPlan` (Layer 0) ggf. um optionales Feld `manual_personas: list[Persona] = []` ergänzen — falls noch nicht vorhanden. Schema dump (`uv run python -m app.contracts.dump_schemas`) committen.
   - `prepare_service.py`: Merge-Logik `generated ∪ manual`, manuelle Personas zählen **nicht** gegen Quote (sonst kürzt der Quoten-Algorithmus sie weg).
   - `Step2EnvSetup.vue`: Beim Sim-Start Payload mit kombinierter Liste senden, `source: "manual" | "generated"` durchreichen.
   - Zod-Spiegel in `frontend/src/contracts/personaQuotaContract.ts` aktualisieren.
6. `cd backend && uv run pytest -x -q` und `cd frontend && npm run check` müssen grün sein.
7. `git diff --exit-code schemas/` darf NICHT failen, sonst Schema neu dumpen.
8. Commit-Sequenz:
   - `feat(contracts): manual_personas im PersonaQuotaPlan (Sub-Slice B, Layer 0)`
   - `fix(backend): prepare_service merged manuelle Personas (Sub-Slice B, schließt B9)`
   - `fix(frontend): Step2 sendet manuelle Personas mit (Sub-Slice B)`
9. PR + Gemini-Review.

### Akzeptanz

- Pytest deckt Merge, Reihenfolge, Quoten-Neutralität von manuellen Personas, sowie Idempotenz bei doppeltem `id` ab.
- Vitest deckt Editor → Payload-Roundtrip ab.
- Manueller End-to-End: 5 Personas generieren, 2 manuell hinzufügen → Sim-Start zeigt 7 Personas im LogDrawer.

---

## Sub-Slice J — Backend-Request-Rate-Audit (read-only Diagnose)

| Feld | Wert |
|---|---|
| Layer | Diagnose / 7 (Runs/Polling) |
| Branch | `chore/task-J-request-rate-audit` (nur Doku-PR) |
| Subagent | `agora-evidence-auditor` (Sonnet, **read-only**) |

### Auftrag an Subagent

Read-only Audit — Subagent darf **keinen Code** schreiben, nur Doku.

1. Alle Frontend-Polling-Loops finden:
   ```bash
   rg -n "setInterval|setTimeout.*fetch|EventSource|useEventSource|usePolling" frontend/src/
   ```
2. Alle Backend-Endpoints listen, die in `Step3Simulation.vue`, `RunsDashboard*.vue`, `LogDrawer.vue`, `GraphPanel.vue`, `Step1GraphBuild.vue` aufgerufen werden, mit Frequenz und Ausgangs-Component.
3. Für SSE-Endpoints (`/api/simulation/*/stream`, `/api/runs/*/events`) klären: Re-Connect-Backoff, Heartbeat-Frequenz, Closing-Verhalten bei Tab-Switch.
4. Für jeden Endpoint Heuristik-Bewertung „erwartet vs. zu hoch":
   - Akzeptabel: 1× pro 2–5 s für FSM-Status während laufender Sim.
   - Verdächtig: dauerhaft mehrfach/Sekunde, oder weiterlaufend nach Sim-Ende.
5. Ergebnis als `docs/2026-05-03-request-rate-audit.md` ablegen mit Tabelle: Component → Endpoint → Frequenz → Trigger → Bewertung → Empfehlung.

### Akzeptanz

- Doku-PR ohne Code-Diff.
- Mindestens 5 konkrete Empfehlungen (z. B. „SSE-Reconnect-Backoff in `useEventSource` fehlt", „LogDrawer pollt `/api/logs` alle 500 ms statt SSE", „RunsDashboard pollt `/api/runs` auch ohne offenen Tab").
- Aus dem Doku-Output ergeben sich Folge-Sub-Slices (J.1, J.2, …), die später per `/agora-next-task` aufgegriffen werden.

---

## Sub-Slice C — Frontend-Modellauswahl wird vom Backend respektiert

| Feld | Wert |
|---|---|
| Layer | 0 (`SimulationConfig`?), 1 (`llm_client.py`, `oasis_profile_generator.py`, `report_agent.py`), 4 (`Step2EnvSetup.vue`) |
| Branch | `fix/task-C-frontend-model-respektieren` |
| Subagent | `agora-refactor-worker` (Sonnet) + `agora-frontend-worker` (Sonnet) |

### Befund

`Step2EnvSetup.vue` hat ein Modell-Dropdown, aber Backend nimmt weiterhin `OLLAMA_MODEL` aus der Env. Verifizieren mit:
```bash
rg -n "OLLAMA_MODEL|model_name|llm_model|primary_model" backend/app/utils/llm_client.py backend/app/services/oasis_profile_generator.py backend/app/services/report_agent.py
rg -n "selectedModel|llmModel|primaryModel" frontend/src/components/Step2EnvSetup.vue frontend/src/contracts/
```

### Vorgehen

1. **Verify-First** mit obigen `rg`-Befehlen, Output ins Arbeitsprotokoll.
2. **RED — Backend:** `backend/tests/api/test_simulation_uses_request_model.py`
   ```python
   def test_simulation_uses_request_model(monkeypatch, client):
       called = {}
       monkeypatch.setattr(llm_client, "chat", lambda model, **kw: called.setdefault("m", model) or "ok")
       client.post("/api/simulation/start", json={..., "llm": {"primary_model": "qwen3:14b"}})
       assert called["m"] == "qwen3:14b"
   ```
3. **GREEN:**
   - Layer-0: Bestehenden `SimulationConfig`-Contract um `llm: LLMSettings`-Block erweitern (`primary_model`, `embedding_model`, `temperature`, `top_p`, `seed`). Falls schon vorhanden, prüfen, dass `extra="forbid"` greift.
   - `llm_client.py`: Default aus Env nur als **Fallback**, nicht als Override. Signatur: `chat(prompt, model: str | None = None, ...)` — wenn `model is None`, dann Env, sonst Argument.
   - `oasis_profile_generator.py`, `report_agent.py`, `prepare_service.py`, `evidence_binder.py`, `confidence_calculator.py`: alle LLM-Aufrufe nehmen Modell aus `SimulationConfig.llm.*` durch — kein direkter `os.getenv("OLLAMA_MODEL")` mehr in den Services.
   - Frontend: `Step2EnvSetup.vue` schreibt Modell in `SimulationConfig`-Payload, Zod-Spiegel ergänzen.
4. **Cross-cutting Test:** `rg -n "os.getenv\(['\"]OLLAMA_MODEL" backend/app/services/` → muss leer sein.
5. Smoke: zwei Simulationen mit unterschiedlichen Modellen starten, im Log-Drawer (oder Backend-Log) verifizieren, dass das richtige Modell genutzt wurde.
6. Commit-Sequenz pro Schicht (Contracts → Services → Frontend), Schemas dumpen.
7. PR + Gemini-Review.

### Akzeptanz

- `rg`-Beweis: kein `os.getenv("OLLAMA_MODEL")` mehr in `backend/app/services/`.
- Pytest deckt: Modell aus Request übergeben, Modell-Default fallback auf Env wenn Request-Feld leer.
- Frontend-Test deckt: Dropdown-Wahl landet im Payload.

---

## Sub-Slice D — Live-Settings im Frontend statt `.env`-Edit

| Feld | Wert |
|---|---|
| Layer | **0 (settings_schema)**, 1 (`settings_layer.py`, `settings_validator.py`), 4 (Settings-Panel) |
| Branch | `feat/task-D-live-settings-frontend` |
| Subagent | Lead **Opus** + `agora-refactor-worker` (Sonnet) + `agora-frontend-worker` (Sonnet) + `agora-test-worker` (Sonnet) |

### Auftrag

Settings, die aktuell in `.env` leben (LLM-Modell, Temperatur, Persona-Defaults, Polling-Intervalle, Feature-Flags), sollen im Frontend bearbeitet und **sofort wirksam** angewandt werden — ohne Container-Restart.

### Vorgehen

1. **Inventur** (im Lead-Kontext, kein Subagent):
   ```bash
   cat backend/.env.example
   rg -n "os.getenv|os.environ\[" backend/app/services/ backend/app/api/ backend/app/utils/
   cat backend/app/services/settings_schema.py backend/app/services/settings_layer.py backend/app/services/settings_validator.py
   ```
   Ergebnis: Tabelle „Setting-Key → Default → wo gelesen → laufzeit-änderbar?".
2. **Layer-0 (Opus-Lead):** `SettingsModel` (Pydantic v2, `extra="forbid"`) erweitern um Sektionen `llm`, `personas`, `simulation`, `ui`. Felder mit `Field(..., description="...")` für JSON-Schema-Aussagekraft. Zod-Spiegel in `frontend/src/contracts/settingsContract.ts`.
3. **RED — Backend-Tests** durch `agora-test-worker`:
   - `GET /api/settings` liefert aktuelle effektive Settings (env-merged, redacted bei Secrets).
   - `PUT /api/settings` validiert via Pydantic, persistiert in `var/runtime-settings.json` (oder Redis-Key), broadcastet `event_bus`-Event `settings.changed`.
   - Service-Hot-Path liest aus `settings_layer.get()` statt `os.getenv` (testet, dass `PUT` ohne Restart durchschlägt).
4. **GREEN — Backend** durch `agora-refactor-worker`:
   - `settings_layer.py`: In-Memory-Cache + persistente Backing-Datei, Thread-safe (Lock).
   - `api/settings.py`: `GET`/`PUT`-Routen mit Pydantic-Validation, Audit-Log via `app.logger`.
   - Services migrieren von `os.getenv` → `settings_layer.get_*()`-Accessor (siehe Sub-Slice C, kann parallel oder vorher gemerged sein).
   - Secrets (`OLLAMA_TOKEN`, JWT-Keys etc.) bleiben in `.env`, werden im `GET`-Response als `"***"` redacted und sind im `PUT`-Body verboten (`extra="forbid"` im Subschema).
5. **Frontend** durch `agora-frontend-worker`:
   - Neuer Tab/Drawer „Einstellungen" in `App.vue` oder `Step2EnvSetup.vue` (Sub-Drawer, kein Vollbild-Wechsel).
   - Pinia-Store `useSettingsStore`, lädt beim Mount via `GET /api/settings`, sendet Patches via `PUT`, hört auf `settings.changed` via SSE/EventSource.
   - i18n-Keys in `de.json` und `en.json`, **keine** hartkodierten Strings (siehe `CLAUDE.md` § Verboten).
   - Form-Validierung via Zod-Schema, Inline-Fehlermeldungen.
6. **Smoke:** Modell im Frontend ändern, sofort eine neue Persona-Generierung starten, im Log-Drawer verifizieren, dass das neue Modell verwendet wurde — ohne Container-Restart.
7. Schemas dumpen, Commits pro Schicht, PR mit ausführlicher Beschreibung der Whitelist (welche Keys sind über UI änderbar).

### Akzeptanz

- `GET /api/settings` und `PUT /api/settings` jsonschema-konform (Test im `tests/api/`-Ordner).
- Live-Test: Polling-Intervall via UI ändern, Effekt sofort messbar.
- Secrets sind weder im `GET`-Klartext noch via `PUT` setzbar.
- i18n-Coverage: `npm run lint` (i18n-key-Plugin) grün.

---

## Sub-Slice E — Live-Anzeige „aktives Modell"

| Feld | Wert |
|---|---|
| Layer | 1 (`event_bus.py`), 4 (Frontend Header/Badge) |
| Branch | `feat/task-E-active-model-badge` |
| Subagent | `agora-refactor-worker` (Sonnet) + `agora-frontend-worker` (Sonnet) |

### Vorgehen

1. **Backend:** In `llm_client.py` vor jedem Modell-Call `event_bus.publish("model.active", {"model": name, "context": "persona|graph|report", "ts": ...})`. Fire-and-forget, kein Blocking.
2. SSE-Channel `/api/events/stream?topic=model.active` (oder bestehenden `event_bus_redis.py`-Channel mitnutzen) — Auth via Signed Ticket (Sub-Slice 02b).
3. **Frontend:**
   - Pinia-Store `useActiveModelStore` mit `currentModel`, `lastChanged`, `context`.
   - Komponente `ActiveModelBadge.vue` im `App.vue`-Header rechts: Punkt + Modell-Name + Kontext-Icon, Hover-Tooltip mit Zeitstempel und Roundtrip-Latenz.
   - Bei `null` → grauer Punkt + „idle".
4. **Tests:**
   - Backend-Pytest: Event wird mit korrektem Schema publiziert.
   - Vitest: Badge zeigt Modell, wechselt bei neuer Event-Nachricht, fällt auf „idle" zurück nach `STALE_AFTER_MS`.
5. i18n-Keys.
6. Commit + PR + Gemini.

### Akzeptanz

- Während laufender Sim wechselt der Badge sichtbar zwischen Personas-Modell, Graph-Modell, Report-Modell.
- Badge ist barrierefrei (`aria-live="polite"`).

---

## Sub-Slice F — Demographische Namen-Verteilung statt Deutsch-Only

| Feld | Wert |
|---|---|
| Layer | 2 (Prompt-Semantik, **Wording-Glossar relevant**) + 1 (`oasis_profile_generator.py`) |
| Branch | `fix/task-F-namen-demographie` |
| Subagent | Lead **Opus** + `agora-refactor-worker` (Sonnet) + `agora-evidence-auditor` (Sonnet, Validation) |

### Befund

Aktuelle Persona-Prompts erzwingen DACH-Namen 1:1, ohne Migrationsanteile abzubilden. Realität DACH 2026: ~26 % Bevölkerung mit Migrationshintergrund (Destatis). Personas wirken künstlich monokulturell.

### Vorgehen

1. **Quellen sichten:** Destatis 2024/2025, BFS (CH), Statistik Austria — Anteile nach den 10 häufigsten Herkunftsregionen, Generation 1 vs. 2. Quote als Konstanten in `backend/app/services/persona_demographics.py` (neue Datei).
2. **RED — Eval-Test:** `backend/tests/eval/test_persona_name_distribution.py`
   ```python
   def test_persona_name_distribution_matches_dach_demographics():
       personas = generate_personas(n=200, locale="DE", seed=42)
       buckets = classify_names_by_origin(personas)  # nutzt persona_demographics.NAME_PATTERNS
       assert 0.20 <= buckets["migration"] / 200 <= 0.32
       assert buckets["migration_subbucket_TR"] >= 4  # mindestens 2 % türkisch-stämmig
       # weitere Erwartungen pro Subbucket
   ```
3. **GREEN — Prompt-Engineering:** In `oasis_profile_generator.py` den Persona-Prompt um eine **Quoten-Tabelle** ergänzen, die das LLM zwingt, Namen entsprechend der Verteilung zu sampeln (nicht „seien Sie divers", sondern „erzeuge 26 % Namen mit nicht-deutschem Sprachursprung, davon X % türkisch, Y % arabisch, …").
4. Wording-Glossar v1 (`docs/glossary-wording.md`) prüfen — keine `prediction`-Phrasen, keine US-Marketing-Buzzwords im neuen Prompt.
5. **Audit durch `agora-evidence-auditor`:** Read-only — generiert 3× 50 Personas, prüft Verteilung, dokumentiert Drift.
6. Wenn Drift > ±5 %: zweiter Prompt-Iteration-Zyklus.
7. Commit + PR + Gemini.

### Akzeptanz

- Eval-Test grün (deterministischer Seed).
- Auditor-Doku zeigt 3 Sample-Runs, Verteilung im Akzeptanzkorridor.
- Glossar-Compliance verifiziert: `rg -n "prediction|rehearsal|god.s eye view" backend/app/services/oasis_profile_generator.py` leer.

---

## Sub-Slice G — IT-Bias raus, Branchenverteilung realistisch

| Feld | Wert |
|---|---|
| Layer | 1/2 (`oasis_profile_generator.py` + Quoten-Defaults) |
| Branch | `fix/task-G-branche-statt-it-bias` |
| Subagent | `agora-refactor-worker` (Sonnet) |

### Vorgehen

1. Default-`PersonaQuotaPlan` in `prepare_service.py` / `simulation_config_generator.py` prüfen — falls IT-lastig hard-coded, durch Branchenverteilung nach Destatis WZ-Klassen ersetzen (Handel, Gesundheit, Verarbeitendes Gewerbe, Bildung, Bau, IT etc.).
2. Persona-Prompt: explizite Branchenliste mit Soll-Anteilen, **kein** „arbeitet bei einem Tech-Startup"-Bias.
3. **RED — Test:** Verteilung über 100 Personas, IT-Anteil ≤ 12 % (Destatis IKT-Branche ~3 %, plus IT-affine Berufe in anderen Branchen).
4. **GREEN — Prompt-Iteration**, wenn nötig 2 Runden.
5. UI: Im Quoten-Editor (`Step2EnvSetup.vue`) sollten Branchen-Slider sichtbar sein — falls nicht, Sub-Slice ggf. in G.1 (Backend-Quoten) und G.2 (UI-Slider) splitten.
6. PR + Gemini.

### Akzeptanz

- IT-Anteil ≤ 12 % (statt aktuell vermuteter > 50 %).
- Mindestens 7 verschiedene Branchen in einem 50-Personas-Sample.
- User-Smoke: Eine Sim mit Default-Quoten → Persona-Liste sichtbar branchenrealistisch.

---

## Sub-Slice H — Entitäten-Beziehungen werden zuverlässig erstellt

| Feld | Wert |
|---|---|
| Layer | 1/2 (`graph_builder.py`, `ontology_generator.py`, evtl. `entity_reader.py`) |
| Branch | `fix/task-H-entity-relationships` |
| Subagent | `agora-refactor-worker` (Sonnet) + `agora-evidence-auditor` (Sonnet) |

### Vorgehen

1. **Reproduzieren:** Mit aktuellem Stand 5 Mini-Inputs (3–5 Sätze) durch die Graph-Pipeline schicken, Beziehungen pro Input zählen. Schwellwert „akzeptabel": ≥ 1 Beziehung pro 2 Entitäten.
2. **Audit (read-only, Auditor):** Identifiziere Failure-Modes — kein Beziehungs-Schema im Prompt? LLM-Output wird verworfen weil `extra="forbid"` zu strikt? `chat_json` Strict-Mode verwirft valide Edges? `evidence_binder.py` filtert Edges weg?
3. **GREEN — schichtweise**:
   - Wenn Prompt-Issue: Few-Shot-Beispiele mit klaren Edge-Beispielen ergänzen, Edge-Schema explizit in der System-Prompt nennen.
   - Wenn Strict-Schema-Issue: Edge-Subschema gegen Prompt-Beispiele validieren, ggf. `Optional`-Felder lockern (mit Test, dass essenziellen Felder Pflicht bleiben).
4. **RED-Test:** `backend/tests/services/test_graph_builder.py::test_minimum_edge_yield_per_entity_pair` — auf 3 Fixture-Inputs.
5. PR + Gemini.

### Akzeptanz

- Edge-Yield ≥ 1 pro 2 Entitäten auf Fixture-Set.
- Auditor-Doku zeigt Vorher/Nachher mit konkreten Sample-Outputs.

---

## Sub-Slice I — Persona-Generierung-Latenz reduzieren

| Feld | Wert |
|---|---|
| Layer | 1 (`oasis_profile_generator.py`, `llm_client.py`) |
| Branch | `perf/task-I-persona-latenz` |
| Subagent | `agora-refactor-worker` (Sonnet) |
| **Voraussetzung** | Sub-Slices C + D + J abgeschlossen — sonst optimieren wir Symptome statt Ursachen. |

### Vorgehen

1. **Messen vor Ändern:**
   - `time` um `generate_personas(n=20)` legen, Wall-Clock + LLM-Roundtrips loggen (wenn nicht vorhanden, Decorator `@measure_llm_latency` ergänzen, mit Output ins strukturierte Log).
   - Erwartung: 20 Personas in < 60 s mit 7B-Modell, < 180 s mit 14B-Modell.
2. **Hebel prüfen** (in dieser Reihenfolge, jeweils messen):
   - Sequentiell vs. parallel: gibt es bereits `asyncio.gather` oder werden Personas streng seriell generiert?
   - Prompt-Länge: Wie viele Tokens pro Persona? Lassen sich System-Prompt + Few-Shots cachen (Ollama `keep_alive`, `num_keep`)?
   - Modell-Größe: Default-Modell zu groß? Sub-Slice C/D erlauben User-Wahl, Default sollte ein 7B/8B sein.
   - Batch-Generierung: 1 LLM-Call → 5 Personas (JSON-Array) statt 5 Calls?
3. **RED — Performance-Budget-Test:** `backend/tests/perf/test_persona_generation_latency.py`
   ```python
   @pytest.mark.perf
   def test_persona_generation_under_budget(small_model):
       t0 = time.monotonic()
       personas = generate_personas(n=10, model=small_model)
       elapsed = time.monotonic() - t0
       assert elapsed < 30.0  # 3 s pro Persona oberes Limit
       assert len(personas) == 10
   ```
   (Mit pytest-Mark `perf`, in CI per `-m "not perf"` ausgeschlossen, lokal `-m perf` ausführbar.)
4. **GREEN — gezielter Hebel** (max 2 pro PR, sonst weiterer Slice).
5. Vorher/Nachher-Tabelle in Commit-Body.
6. PR + Gemini.

### Akzeptanz

- Performance-Budget-Test grün auf Default-Modell.
- Vorher/Nachher-Messung dokumentiert (mind. 30 % Reduktion oder explizite Begründung warum nicht).

---

## Querschnitts-Disziplin (gilt für alle Slices)

- **Tests sind die Spec** — RED-GREEN-COMMIT pro Schritt.
- **Verify-First** — keine `os.getenv`, kein Pinia-Property, kein Pydantic-Feld umbenennen ohne `rg`-Beweis vorab.
- **Schemas-Drift** — nach jeder Layer-0-Änderung `cd backend && uv run python -m app.contracts.dump_schemas`, `git diff --exit-code schemas/` muss grün sein.
- **i18n-Pflicht** — keine hartkodierten UI-Strings.
- **Wording-Glossar** — `docs/glossary-wording.md` nicht verletzen.
- **Gemini-Review-Cycle** — nach jedem `gh pr create`:
  ```bash
  sleep 90
  gh api repos/arn0ld87/agora/pulls/<NR>/reviews --jq '.[] | {author, body, state}'
  gh api repos/arn0ld87/agora/pulls/<NR>/comments --jq '.[] | {path, line, body}'
  ```
  HIGH-Findings adressieren, MEDIUM bewerten, LOW ggf. „Out of Scope"-mergen mit Begründung.
- **Verifikation** nach Subagent-Run: `/verify-after-subagent`.

---

## Slash-Command-Sequenz (pro Sub-Slice)

```
/agora-next-task <slice-id>          # nimmt nächsten Slice oder konkreten Slice (A, B, …)
# Subagent läuft (Sonnet)
/verify-after-subagent               # Pflicht-Gate (kein Skip)
# Wenn rot: nachjustieren, sonst:
git push origin <branch>
gh pr create --title "..." --body "..."
sleep 90 && gh api .../reviews ...   # Gemini-Findings sichten
# Findings adressieren oder Followup-Sub-Slice eröffnen
git checkout main && git merge --ff-only <branch> && git push origin main
```

---

## Erfolgskriterien (User-Sicht)

| User-Beschwerde | Verifikation nach Plan |
|---|---|
| „Persona-Erstellung dauert ewig" (B1) | I: Performance-Budget-Test grün, Vorher/Nachher-Tabelle ≥ 30 % schneller. |
| „Modellauswahl wird ignoriert" (B2) | C: `rg`-Beweis kein `OLLAMA_MODEL`-getenv mehr in services, Pytest deckt Modell-Override ab. |
| „Will Settings im Frontend setzen, sofort wirksam" (B3) | D: UI-Drawer mit Live-`PUT /api/settings`, Smoke-Test ohne Restart. |
| „Backend extrem viele Zugriffe" (B4) | J: Audit-Doku + Folge-Slices J.1ff. |
| „Keine Beziehungen zwischen Entitäten" (B5) | H: Edge-Yield-Test grün, Auditor-Vergleich. |
| „Nur deutsche Namen" (B6) | F: Eval-Test mit DACH-Demographie-Quote. |
| „Will sehen welches Modell arbeitet" (B7) | E: Active-Model-Badge im Header, Vitest deckt Wechsel ab. |
| „Nur IT-Personas" (B8) | G: Branchenverteilung-Test, IT ≤ 12 %. |
| „Manuelle Personas ignoriert" (B9) | B: Pytest deckt Merge-Pfad, manueller Smoke. |
| „Kein Weiter-Knopf nach Sim" (B10) | A: Vitest deckt COMPLETED-State, manueller Wizard-Smoke. |

---

## Was dieser Plan **nicht** macht

- Kein Refactor von `report_agent.py`, `simulation_runner.py` oder `Step2EnvSetup.vue` (Hot-Spots aus `PLAN.md` F7/F8 — eigener Slice).
- Kein neues Auth-Modell (F2 — eigener Slice).
- Keine Reverse-Proxy-Arbeit (F1 — Issue #106).
- Keine CVE-Watchlist-Updates (F4).

Diese sind im Master-`PLAN.md` getrackt und werden separat per `/agora-next-task` aufgegriffen.
