# Smoke-Report 2026-05-15 — Dev-Stack via Chrome DevTools

**Branch:** `test/smoke-2026-05-15`
**Stack:** Dev (Vite-Dev :5180 + Backend :5001 + Neo4j + Redis), Docker
**LLM-Profil:** OpenAI `gpt-5.4-nano` (Ontologie + Persona-Erstellung), Ollama `kimi-k2.6` (Report-Generation)
**Tester:** Claude Code (Opus 4.7, 1M)
**Repo-Stand:** `main` HEAD `f430bf5` (Merge PR #457 pydantic-settings foundation)

## Container-Status (Setup)

| Container | Status | Ports |
|---|---|---|
| agora | Up 20 min (healthy) | 5001 (Flask), 5180→5173 (Vite) |
| agora-redis | Up 21 min (healthy) | 6379 |
| agora-neo4j | Up 20 min (healthy) | 7474, 7687 (loopback only) |

## Befund-Übersicht

| # | Severity | Flow | Symptom |
|---|---|---|---|
| 1 | **P1** | E (Report) | OpenAI 400 — `report_plan`-Schema verletzt strict mode (`Missing 'description'` in `required`) |
| 2 | **P1** | E (Report) | Ollama-Fallback (kimi-k2.6) liefert `len=0` nach 70 s — kein gültiges Outline-JSON |
| 3 | **P1** | C (EnvSetup) | Override-Provider erbt OpenAI-Key nicht aus Settings → manuelles Re-Eintragen nötig |
| 4 | **P1** | C (EnvSetup) | `auth/ticket`-TTL läuft ab, Re-Auth liefert ebenfalls 401 → Frontend gestrandet (Workaround: Reload) |
| 5 | **P2** | A (Nav) | Sidebar-Stubs Projects/Datasets/Templates/Monitoring routen alle auf `/dashboard` |
| 6 | **P2** | C (EnvSetup) | Slider/Spinbutton „Max. Agenten" hat hartes `valuemin=50` — kein Test mit kleineren Pools möglich |
| 7 | **P2** | E (Report) | `Modell für Report`-Combobox zeigt `qwen2.5:32b`, aber Backend nutzt tatsächlich OpenAI → Anzeige-Drift zwischen Workspace-Default und Report-Step |
| 8 | **P3** | A/D/E (i18n) | Englische Section-Titel und Logs („WAITING FOR ONTOLOGY GENERATION", „Chunking text", Persona Reaction Analysis) trotz DE-Locale |
| 9 | **P3** | A (i18n) | `dashboard.active.phase.ontology_generate` fehlt in `de.json` und `en.json` (6× geloggt pro Render) |
| 10 | **P3** | A (i18n) | `graph.edgeLabels.*` fehlen in beiden Locale-Files (REPRESENTS, COMMENTS_ON, PLANS_WITH, OWNERSHIP_STAKE, LEADS, SELF_RELATIONS_(1)) |
| 11 | **P2** | A (a11y) | „No label associated with a form field" + „form field should have id/name" — File-Drop und Provider-Inputs ohne Form-Hülle (Browser-Autofill kaputt) |
| 12 | **P3** | LLM Providers | API-Key-Inputs sind kein `<form>` → 5× „Password field is not contained in a form"-Warning |
| 13 | **P3** | Step1 | Modell-Dropdown im HeroNewRun mischt Profile (`Standard — …`), Cloud-Aliase und „(Ollama)"-Einträge wahllos; ~140 Einträge im Settings-Default-Picker ohne Filter (Image, Audio, TTS, Embeddings) |
| 14 | **P3** | C | OpenAI-Provider zeigt Gemini-URL als Base-URL-Placeholder |
| 15 | **P3** | Dashboard | „Disk 91.52%" zeigt keine Warnfarbe; `Ø CONFIDENCE` der letzten Reports überall „—" |
| 16 | **P3** | Dashboard | Run-IDs „proj_xxx" statt menschenlesbarer Projekt-Slug |
| 17 | **P1** | Auth | Aus dem Hot-Spot in CLAUDE.md bestätigt: `OPENAI_API_KEY=ollama` + `OPENAI_API_BASE_URL=http://localhost:11434/v1` im Container — die Env-Var routet auf Ollama. Echter Key liegt nur in Settings-DB. Bei Override-Path im Frontend wird der DB-Key nicht propagiert. |

## P1 — Detail

### #1 OpenAI Strict-Schema-Fehler beim Outline-Planning

**Symptom (Console-Log + Backend-Log):**
```
ERROR: Outline planning failed: Error code: 400 - {'error': {'message': 
"Invalid schema for response_format 'report_plan': In context=(), 'required' 
is required to be supplied and to be an array including every key in properties. 
Missing 'description'.", 'type': 'invalid_request_error', 'param': 'response_format'}}
```

**Root-Cause:** [`backend/app/services/report_agent/schemas.py:46-72`](../backend/app/services/report_agent/schemas.py)

```python
class PlanSection(BaseModel):
    model_config = _STRICT
    title: str = Field(min_length=1, description="Abschnittstitel")
    description: str = Field(default="—", description="Kurze Inhaltsbeschreibung …")
```

`description` hat `default="—"` → Pydantic v2 generiert JSON-Schema mit `required: ["title"]` (ohne `description`). OpenAI strict structured outputs verlangt jedoch `required[]` muss **alle** Properties enthalten. Gleiches Problem trifft `PlanResponse.summary` und `PlanResponse.sections` (alle haben Defaults).

**Fix-Vorschlag:**
```python
class PlanSection(BaseModel):
    model_config = _STRICT
    title: str = Field(..., min_length=1, description="Abschnittstitel")
    description: str = Field(..., description="Kurze Inhaltsbeschreibung …")
```
Plus: in `llm_client.py` beim Schema-Dump für OpenAI explizit `additionalProperties=False` und `required = list(properties.keys())` erzwingen.

**Layer:** 0 (Pydantic-Contracts) — Sub-Slice nach Layer-Reihenfolge.

### #2 Ollama-Fallback liefert leeren Output

**Symptom:**
```
INFO: LLM chat returned model=kimi-k2.6 finish=stop tokens_out=4096 elapsed=70.2s max_tokens=4096 stream=False
ERROR: Outline planning failed: Invalid JSON format from LLM (len=0; likely truncated). Head: 
```

`tokens_out=4096 == max_tokens=4096 finish=stop`. Modell hat 4096 Tokens generiert (vermutlich Thinking-Mode), aber **kein finales JSON**. Konsistent mit Honcho-Hinweis `OLLAMA_THINKING=false` als Pflicht-ENV — wird hier offenbar nicht gesetzt oder vom Modell ignoriert.

**Workarounds zu prüfen:**
1. `max_tokens` für Outline-Step ausschließlich erhöhen (z. B. 16k)
2. `OLLAMA_THINKING=false` in Container-Env setzen
3. Bei `kimi`-Familie explizit Thinking-Suffix entfernen / Header `X-Ollama-No-Think: 1` setzen

### #3 + #17 OpenAI-Key wird nicht propagiert bei Override

Beim Settings → LLM Providers ist der Key gespeichert (`sk-...MLUA`, Status „verbunden"). Sobald in Step 2 (EnvSetup) `Provider = OpenAI` als Override gewählt wird, ist das Feld **„API-Key (Nur für diese Browser-Sitzung)"** leer, und der gespeicherte DB-Key wird nicht autom. mitgenutzt. Backend antwortet 401 / Auth-Fehler bis Key manuell eingetragen wird.

Container-ENV-Diagnose:
```
OPENAI_API_KEY=ollama
OPENAI_API_BASE_URL=http://localhost:11434/v1
```
Die `OPENAI_API_*`-Variablen sind hier zweckentfremdet als Ollama-Adapter — der echte OpenAI-Key liegt nur in der Settings-DB. Override-Pfad muss diesen DB-Key fetchen, wenn das Feld leer ist.

**Layer:** 1 (Backend-Auth + Settings) + 4 (Frontend-Override).

### #4 Auth-Ticket-Loop

Nach ~5 min Browser-Idle in Step 2:
```
GET /api/simulation/sim_xxx → 401
POST /api/auth/ticket → 401   ← Re-Auth selbst failt
```
Frontend hat keinen Refresh-Path und bleibt mit Status `Fehler` hängen. Workaround: Reload (Session-Cookie initiiert neues Ticket).

## P2 — Detail

### #5 Sidebar-Stub-Links
[`frontend/src/components/v4/shell/AppSidebar.vue`](../frontend/src/components/v4/shell/AppSidebar.vue) — Projects/Datasets/Templates/Monitoring haben `to="/dashboard"` als Platzhalter. Entweder Route bauen oder Link `disabled` setzen (mit Tooltip „bald verfügbar").

### #6 Persona-Limit min 50

```
uid=16_0 slider valuemin=50 valuemax=500
uid=16_1 spinbutton valuemin=50 valuemax=2000
```
Bei Test-Seeds mit < 50 Graph-Entitäten oversized. `valuemin` auf 5 oder 10 senken; ggf. Warnung „kleine Pools < Quote-Vorgabe können Persona-Quote brechen".

### #7 Modell-Anzeige-Drift Step 4

`Modell für Report`-Combobox: selected = `qwen2.5:32b`, Backend-Log zeigt aber OpenAI-Call. Workspace-Default (Step 1) und Report-Default sind getrennte Stores ohne Sync. Pinia-Store-Pfade prüfen: `agora.runtimeLlm.*` vs. report-spezifische.

## Erfolgreiche Flows

- **Step 1 → Ontologie (gpt-5.4-nano):** Fertig in **20 s** nach Submit. 14 Entitätstypen + 9 Relationstypen erkannt.
- **Step 1 → Graph-Build (gpt-5.4-nano):** **14 s** für 15 Chunks → 31 Entitäten, 22 Beziehungen in Neo4j.
- **Step 2 → Personas (gpt-5.4-nano):** 50/50 Personas erzeugt (nach Key-Override). Deutsche Persona-Namen, plausible Bios, voice_register pro Persona.
- **Step 3 → Simulation (5 Runden, 50 Agenten, gpt-5.4-nano):** „Abgeschlossen — 5 Runden", **keine Errors** im „Nur Fehler"-Filter. Tool-Call-Log zeigt `[Common LLM] model=gpt-5.4-nano, base_url=https://api.openai.com/v1, memory_token_limit=262144, ollama_num_ctx=262144`.

## Screenshots

- `docu/2026-05-15-smoke-step2-error.png` — Auth-401-Loop in Step 2
- `docu/2026-05-15-smoke-step4-schema400.png` — OpenAI strict-mode 400
- `docu/2026-05-15-smoke-step4-kimi-empty.png` — Ollama kimi-k2.6 leerer Output

## Empfohlene Folge-Slices

1. **P1 #1 (Layer 0):** `PlanSection.description` + `PlanResponse.summary/sections` auf required setzen. Plus `llm_client.dump_schema_for_openai_strict()` Helper, der `required = list(properties.keys())` + `additionalProperties=False` erzwingt. Schema-Dump-Test gegen `tests/contracts/`.
2. **P1 #2:** Outline-Step bekommt eigenen `max_tokens=16384`-Override und harten `enable_thinking=False`-Header für Ollama-Provider. Smoke-Test mit `kimi-k2.6` als Eval-Snapshot.
3. **P1 #3+#17:** Wenn Override-Provider gleich Settings-Provider, DB-Key autom. mitnehmen; sonst Hinweis „Server hat Key, aber Override-Modus erzwingt Eingabe — entweder leer lassen oder neu eintragen".
4. **P1 #4:** Auth-Refresh-Hook im Frontend (`api/auth/refresh` mit Cookie); Backend muss `/api/auth/ticket` ohne X-Ticket-Header funktionieren, solange Session-Cookie gültig.
5. **P2 #5:** Sidebar-Items markieren oder Routes anlegen.
6. **P2 #6:** `valuemin=10`, Test mit Mini-Seed.
7. **P2 #7:** Pinia-Store-Konsolidierung Workspace-Default ↔ Report-Step.
8. **P3 #8–#10:** i18n-Audit: alle fehlenden Keys in `de.json`/`en.json` ergänzen, Englisch-Strings in Vue-Komponenten durch `t('…')` ersetzen.

## Zusammenfassung

- **3 von 4 Pipeline-Stufen funktional grün** (Ontologie, Graph-Build, Personas, Simulation) — gpt-5.4-nano arbeitet schnell und stabil.
- **Step 4 (Report) ist gebrochen** auf beiden Providern. Zwei verschiedene P1-Bugs blockieren den v1.0-Output-Vertrag.
- **Auth- und Modell-Routing zwischen Steps** ist fragmentiert; mehrere lokale State-Stores ohne Single Source of Truth.
- **i18n-Drift** signifikant — DACH-Use-Case verlangt durchgängiges Deutsch, hier Englisch in Logs, Section-Titeln und Graph-Edge-Labels.
- UI-Stubs (Sidebar) lassen den Eindruck eines unfertigen Produkts entstehen — entweder Routen liefern oder Platzhalter klar kennzeichnen.
