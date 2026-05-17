# Agora — PLAN.md

> **Zweck:** Vollständiger Entwicklungsplan für das Agora-Projekt inkl. Multi-Provider-KI-System (Gemini · OpenAI · Ollama) mit dynamischem Modell-Switching.

---

## Inhaltsverzeichnis

1. [Projektübersicht](#1-projektübersicht)
2. [Multi-Provider-KI-System](#2-multi-provider-ki-system)
3. [Provider-Konfiguration & Modell-Discovery](#3-provider-konfiguration--modell-discovery)
4. [Session-Switching — Anbieter & Modell wechseln](#4-session-switching--anbieter--modell-wechseln)
5. [Slash Commands Übersicht](#5-slash-commands-übersicht)
6. [Dateistruktur](#6-dateistruktur)
7. [Implementierungs-Phasen](#7-implementierungs-phasen)
8. [Sicherheitsregeln](#8-sicherheitsregeln)
9. [Abgeschlossene Welle: Observability, Run-Control & Model-Picker UX (2026-05-16)](#9-abgeschlossene-welle-observability-run-control--model-picker-ux-2026-05-16)
10. [Aktive Welle: Report-Quality-Floor (2026-05-17)](#10-aktive-welle-report-quality-floor-2026-05-17)

---

## 1. Projektübersicht

Agora ist eine KI-gestützte Plattform. Dieses PLAN.md definiert den Ausbau des **Multi-Provider-KI-Layers**: Claude kann beim Start und **nach jedem Schritt** den Anbieter (Gemini, OpenAI, Ollama) sowie das konkrete Modell wechseln. Modelle werden **automatisch per API** geladen — keine manuellen Listen.

**Kernprinzipien:**
- Provider-agnostisch: ein Interface, mehrere Backends
- Modell-Discovery: immer aktuelle Modelllisten direkt von der API
- Zero-Secrets-in-Code: API Keys nur via `.env` / Umgebungsvariablen
- Switching jederzeit möglich — auch mitten in einer Aufgabe

---

## 2. Multi-Provider-KI-System

### Architektur

```
┌─────────────────────────────────────────────────────┐
│                  Agora AI Layer                     │
│                                                     │
│  ┌──────────────┐   ┌──────────────────────────┐   │
│  │  Provider    │   │   Model Registry         │   │
│  │  Selector    │──▶│   (Live API Discovery)   │   │
│  └──────────────┘   └──────────────────────────┘   │
│         │                        │                  │
│         ▼                        ▼                  │
│  ┌─────────────────────────────────────────────┐   │
│  │           Unified LLM Client                │   │
│  │   .complete(prompt, model, provider)        │   │
│  └──────────┬──────────────┬───────────────────┘   │
│             │              │           │             │
│        ┌────▼───┐   ┌──────▼──┐  ┌────▼────┐       │
│        │ OpenAI │   │ Gemini  │  │ Ollama  │       │
│        │ Client │   │ Client  │  │ Client  │       │
│        └────────┘   └─────────┘  └─────────┘       │
└─────────────────────────────────────────────────────┘
```

### Unterstützte Provider

| Provider | API Endpoint | Modell-Discovery | Auth |
|----------|-------------|-----------------|------|
| **OpenAI** | `https://api.openai.com/v1` | `GET /models` | `OPENAI_API_KEY` |
| **Gemini** | `https://generativelanguage.googleapis.com/v1beta` | `GET /models` | `GEMINI_API_KEY` |
| **Ollama** | `http://localhost:11434` (konfigurierbar) | `GET /api/tags` | kein Key nötig |

---

## 3. Provider-Konfiguration & Modell-Discovery

### Umgebungsvariablen (`.env`)

```env
# Provider: openai | gemini | ollama
AI_DEFAULT_PROVIDER=ollama

# API Keys
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...

# Ollama Basis-URL (Standard: localhost)
OLLAMA_BASE_URL=http://localhost:11434

# Fallback-Modell pro Provider (wenn Discovery fehlschlägt)
OPENAI_DEFAULT_MODEL=gpt-4o
GEMINI_DEFAULT_MODEL=gemini-1.5-pro
OLLAMA_DEFAULT_MODEL=llama3
```

### Modell-Discovery-Logik

Bei jeder neuen Session **und** bei jedem `/switch-provider`-Aufruf:

1. API aufrufen → Modellliste laden
2. Modelle filtern (nur Chat/Completion-fähige)
3. User zur Auswahl präsentieren (sortiert nach Relevanz)
4. Auswahl in Session-State speichern

```python
# Pseudocode — backend/services/ai/model_discovery.py
async def discover_models(provider: str) -> list[ModelInfo]:
    match provider:
        case "openai":
            resp = await openai_client.models.list()
            return [m for m in resp if "gpt" in m.id or "o1" in m.id]
        case "gemini":
            resp = await gemini_client.list_models()
            return [m for m in resp if "generateContent" in m.supported_generation_methods]
        case "ollama":
            resp = await httpx.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.json()["models"]
```

---

## 4. Session-Switching — Anbieter & Modell wechseln

### Start-Flow

```
1. Claude startet
2. → Fragt: "Welchen Provider? [openai/gemini/ollama]" (Default aus .env)
3. → Lädt Modelle per API
4. → Fragt: "Welches Modell?" (nummerierte Liste)
5. → Session beginnt mit gewähltem Provider + Modell
```

### Mid-Session-Switch (nach jedem Schritt)

Nach **jedem abgeschlossenen Schritt** steht folgendes zur Verfügung:

```
> Schritt abgeschlossen. Optionen:
  [Enter]        — Weiter mit aktuellem Provider/Modell (ollama/llama3)
  /switch        — Provider & Modell neu wählen
  /switch-model  — Nur Modell wechseln (gleicher Provider)
  /status        — Aktuellen Provider/Modell anzeigen
```

### Session-State-Schema

```typescript
interface AISession {
  provider: "openai" | "gemini" | "ollama";
  model: string;
  history: Message[];
  switchHistory: SwitchEvent[]; // Protokoll aller Wechsel
}

interface SwitchEvent {
  at: string;      // ISO timestamp
  from: { provider: string; model: string };
  to:   { provider: string; model: string };
  step: number;    // Nach welchem Schritt
}
```

---

## 5. Slash Commands Übersicht

Alle Slash Commands befinden sich in `.claude/commands/`.

| Command | Datei | Zweck |
|---------|-------|-------|
| `/switch` | `switch-provider.md` | Provider + Modell neu wählen |
| `/switch-model` | `switch-model.md` | Nur Modell wechseln |
| `/list-models` | `list-models.md` | Verfügbare Modelle anzeigen |
| `/status` | `ai-status.md` | Aktuellen AI-Status anzeigen |
| `/ai-init` | `ai-init.md` | AI-Session initialisieren |
| `/next-task` | `agora-next-task.md` | Nächste Aufgabe aus PLAN holen |
| `/repo-research` | `repo-research.md` | Repo-Analyse |
| `/verify` | `verify-after-subagent.md` | Nach Subagent verifizieren |

---

## 6. Dateistruktur

```
agora/
├── .claude/
│   ├── commands/
│   │   ├── ai-init.md              # NEU: Session-Start mit Provider-Auswahl
│   │   ├── switch-provider.md      # NEU: Provider + Modell wechseln
│   │   ├── switch-model.md         # NEU: Nur Modell wechseln
│   │   ├── list-models.md          # NEU: Modellliste anzeigen
│   │   ├── ai-status.md            # NEU: AI-Status
│   │   ├── agora-next-task.md      # bestehend
│   │   ├── repo-research.md        # bestehend
│   │   └── verify-after-subagent.md # bestehend
│   ├── agents/
│   └── settings.json
├── backend/
│   └── app/
│       ├── services/
│       │   ├── llm_routing_seed.py    # Multi-Provider-Routing (produktiv)
│       │   └── stage_model_router.py  # Stage→Modell-Mapping (produktiv)
│       └── utils/
│           └── llm_client.py          # Unified LLM-Client (produktiv, ersetzt geplantes services/ai/)
├── prompts/
│   ├── system/
│   │   ├── base.md                 # NEU: Basis-System-Prompt
│   │   ├── provider-init.md        # NEU: Provider-Auswahl-Prompt
│   │   └── step-transition.md      # NEU: Nach-Schritt-Prompt
│   └── (bestehende Prompts)
├── PLAN.md                         # diese Datei
├── CLAUDE.md
└── .env.example
```

---

## 7. Implementierungs-Phasen

### Phase 1 — Fundament (Status: nicht umgesetzt)

Das `backend/services/ai/`-Scaffold (model_discovery, unified_client, provider-Clients)
wurde 2026-05 entfernt — kein Import außerhalb des Pakets, nicht im Wheel-Build
(`packages = ["app"]`), nicht durch Tests abgedeckt. Produktiv läuft Multi-Provider-Routing
heute über:

- `app/services/llm_routing_seed.py` — Provider-/Modell-Mapping pro Stage
- `app/services/stage_model_router.py` — Stage→Modell-Auflösung
- `app/utils/llm_client.py` — Unified LLM-Client (`from_route()`)
- `app/services/llm_providers/github_copilot.py` — Provider-Auth

Backup-Tag des entfernten Codes: `archive/services-ai-pre-removal`.
Falls die Phase reaktiviert wird: neu in `app/services/llm/` aufsetzen, **nicht**
außerhalb von `app/` (sonst nicht im Wheel).

### Phase 2 — Session & Switching (Status: nicht umgesetzt)

Mid-Session-Provider-/Modell-Switch ist nicht implementiert. Aktueller Ersatz:
Stage-basiertes Routing in `stage_model_router.py` + Frontend-Settings für
Override pro Run.

### Phase 3 — Claude Integration (Priorität: MITTEL)
- [ ] Alle neuen Slash Commands erstellen
- [ ] System-Prompts in `prompts/system/` anlegen
- [ ] `CLAUDE.md` um AI-Provider-Sektion erweitern

### Phase 4 — Frontend (Priorität: NIEDRIG)
- [ ] Provider/Modell-Selector UI-Komponente
- [ ] Live-Status-Anzeige (welcher Provider/Modell aktiv)
- [ ] Switch-History-Anzeige in Dev-Tools

---

## 8. Sicherheitsregeln

- **Keine API Keys in Code** — ausschließlich via Umgebungsvariablen
- **Ollama** läuft lokal; kein Key erforderlich, aber `OLLAMA_BASE_URL` muss korrekt gesetzt sein
- API Keys werden nie geloggt oder in Fehlerausgaben sichtbar
- Bei fehlendem Key: graceful error mit konkretem Hinweis (`"OPENAI_API_KEY nicht gesetzt"`)
- Rate-Limiting und Timeout pro Provider konfigurierbar

---

## 9. Abgeschlossene Welle: Observability, Run-Control & Model-Picker UX (2026-05-16)

**Status:** ✅ Alle 8 Slices gemerged via PR #486 (`feat/observability-wave-2026-05`)
am 2026-05-16. Follow-up-Hotfixes #487 (Logo), #488 (Redis-Bus-Bridge),
#489 (OASIS-Provider-Dispatch), #490 (STATUS-Sync), #492 (Zod-Spiegel
`EvidenceItem.source_model`). Live-SigNoz-End-to-End-Smoke offen (manuelles
Compose-Profile `observability`).

Sechs-Defekt-Welle aus User-Bericht 2026-05-16 (Backend-Log-Rauschen, fehlende
Modell-Provenance, SSE-Reconnect, Aktiv-Modell-Anzeige, Stop-Button, Modell-
Picker-Konsolidierung). Vollständiger Brief mit Symptomen, Decisions und Datei-
Erstverdacht: `~/.claude/plans/nutze-code-review-graph-immer-derzeit-adaptive-iverson.md`.

**Decisions (User-Sign-off 2026-05-16):**
1. Stop → Teil-Report aus bereits erzeugten Stages, FSM `cancelled_partial`.
2. Modell-Provenance doppelt: `report.metadata.model_attribution[]` + `evidence.json` (pro Eintrag).
3. SSE-Reconnect unbegrenzt mit Exponential Backoff (1 s → 30 s cap).

**Slices (alle als PR gemerged):**

| # | Slice | Status |
|---|---|---|
| 1 | werkzeug-Logger silencen + Env-Flag | ✅ gemerged |
| 2 | `/api/models` Endpoint + Provider-Discovery (Ollama/OpenRouter/Gemini/OpenAI) | ✅ gemerged (+ Hotfix #489 Provider-Dispatch) |
| 3 | `<ModelPicker />` Vue-Komponente + `useAvailableModels` Composable | ✅ gemerged |
| 4 | SSE-Logs Heartbeat + Backoff-Reconnect + Traefik `X-Accel-Buffering` | ✅ gemerged (+ Hotfix #488 Redis-Channel-Bridge) |
| 5 | Active-Model-Push (Server) + `useActiveModel` Composable + stabile Anzeige | ✅ gemerged |
| 6 | Run-Cancel-Endpoint + FSM-State `cancelled_partial` + asyncio-Task-Cancel | ✅ gemerged (Commit `da17cb7`) |
| 7 | Report-Confirm-Dialog (Bestätigung nach Modell-Auswahl, kein Auto-Start) | ✅ gemerged |
| 8 | Modell-Provenance in ReportV3 + evidence.json + Frontend-Sektion | ✅ gemerged (Commit `af2949f`, + Zod-Hotfix #492) |

**Followup offen:**
- Live-SigNoz-End-to-End-Smoke (manuell über Compose-Profile `observability`, default-off via `OTEL_ENABLED=false`)
- Worklog `[Worklog] Cloud-LLM-Stabilisierung — Sub-Slices 05.1–05.9` (Issue #484)

---

## 10. Aktive Welle: Report-Quality-Floor (2026-05-17)

Fünf-Slice-Welle aus Reviewer-Feedback zu `report_4fe2dacd80ba` (Issues
#493–#497). Hebt den Boden für Evidence-Coverage, Confidence-Tiers,
Hypothesen-Cap, Simulation-Floor und Red-Team-Quoten. Heuristik und
Subagent-Mapping: [`docs/plans/plan.heuristic-2026-05-17.md`](docs/plans/plan.heuristic-2026-05-17.md).

**Decisions (Lead-Setzung 2026-05-17):**
1. Layer-0-Slices (1, 2) sequenziell, eigene PRs, kein gemeinsamer `report_v3.py`-Touch.
2. Hartanker ADR-0002 (cross_stakeholder, reject_inferred, EvidenceSourceKind, Hedge-Snapshot, `<evidence_gating priority="hard">`) bleiben unangetastet — Welle **verschärft**, schwächt nicht.
3. Frontend-Spiegel pro Slice im selben PR, eigener Commit.

**Slices (PR pro Slice, Reihenfolge bindend für Slice 1 → 2, danach 3/4/5 parallel):**

| # | Issue | Slice | Branch | Risiko | Owner-Modell |
|---|---|---|---|---|---|
| 1 | #493 | Evidence-Coverage-Floor (min=2 + Score-Cap < 0.60 wenn `len(evidence) < 2`) | `feat/report-quality-slice-1-evidence-floor` *(angelegt)* | medium | Sonnet (`agora-refactor-worker` + `agora-test-worker`) |
| 2 | #494 | Confidence-Tier-Expansion (`speculative`, `verified`) | `feat/report-quality-slice-2-confidence-tiers` | **high** | **Opus (Lead)** — Layer-0-Enum-Touch |
| 3 | #495 | Hypothesen-Cap max 5/Section + Dedup + Appendix | `feat/report-quality-slice-3-hypothesis-cap` | medium | Sonnet (Refactor + Frontend) |
| 4 | #496 | Simulation-Floor (≥30 Agenten, ≥10 Runden) | `feat/report-quality-slice-4-sim-floor` | low | Sonnet (Refactor + Frontend) |
| 5 | #497 | Echo-Chamber-Red-Team-Quote (≥2 Skeptic-Persona-Quotes/Section) | `feat/report-quality-slice-5-red-team` | **high** | **Opus (Lead)** — Persona-Quoten + Wording-Glossar |

**Verification (End-to-End nach allen Slices):**
1. Smoke-Report zeigt keinen High-Confidence-Claim mit < 2 Evidence-Refs
2. Confidence-Tiers `speculative` und `verified` werden in Frontend + Markdown gerendert
3. Sections enthalten max 5 sichtbare Hypothesen, Rest unter „Weitere Hypothesen"
4. Default-Simulation-Lauf spawnt ≥ 30 Agenten / ≥ 10 Runden ohne Manual-Override
5. Jede Section enthält mindestens 2 Quote-Marker aus Skeptic-Persona-Pool
6. Hartanker-Snapshot (`evidence-gating-hedge-words.txt`) unverändert
7. `pytest -q`, `ruff check app/ tests/`, `radon cc --min C`, `scripts/dump_schemas.py --check`, `scripts/sync-status.sh --check`, `python scripts/check_voice.py --strict` alle grün

**Out of Scope:** ADR-0002-Anker schwächen, neue Provider, OASIS-Source-Patches,
Report-Perf (Slice B/C aus [`docs/archive/plans/plan.report-perf.md`](docs/archive/plans/plan.report-perf.md) folgt eigenständig).

---

*Zuletzt aktualisiert: 2026-05-17 — Observability-Welle abgeschlossen, Report-Quality-Welle eröffnet.*
*Heuristik-SSoT: [`docs/plans/plan.heuristic-2026-05-17.md`](docs/plans/plan.heuristic-2026-05-17.md).*
