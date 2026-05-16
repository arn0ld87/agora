# Report-Generation Performance: Slice B (Interview-Cache) + Slice C (Section-Parallelisierung)

**Status:** Draft · 2026-05-16
**Owner:** Alexander Schneider
**Motivation:** Heutige Report-Erstellung braucht ~80 min (11 Sections × ~7 min). Beobachtet im Live-Log am 2026-05-16 06:00–06:11. Ziel: < 15 min.

## Diagnose-Baseline (vor Optimierung)

Aus Backend-Log Run `report_182fb5248f82`, Modell `glm-5.1:cloud` (Ollama Cloud):

| Stage pro Section | Dauer | Anteil |
|---|---|---|
| `_select_agents_for_interview` | ~18 s | 4 % |
| `_generate_interview_questions` | **~2:36 min** | 37 % |
| `interview_agents_batch` (8 OASIS-Agents) | ~1:34 min | 22 % |
| Post-Processing Interview→Section-Kontext | ~1:13 min | 17 % |
| ReACT Section-Generation (3 Tool-Calls) | ~1:12 min | 17 % |
| Metadata + Save | ~0:55 min | 13 % |
| **Σ pro Section** | **~6:50–7:30 min** | |
| Σ Report (11 Sections, seriell) | **~75–80 min** | |

Code-Pointer:
- Section-Loop: [`backend/app/services/report_agent/workflow.py:586`](backend/app/services/report_agent/workflow.py:586) — `for i, section in enumerate(outline.sections)`
- Interview-Tool: [`backend/app/services/graph_tools.py:195`](backend/app/services/graph_tools.py:195) — `InterviewAgents.interview`
- ReACT-Section: [`backend/app/services/report_agent/workflow.py:104`](backend/app/services/report_agent/workflow.py:104) — `generate_section_react`

---

## Slice B — Interview-Cache pro Report

**Ziel:** Jede Section macht aktuell ein eigenes 8-Agent-Interview, obwohl die Datengrundlage (50 Profile, 1 simulation_id, 1 simulation_requirement) konstant ist. Cache 1× pro Report-Run, Sections greifen darauf zu.

**Erwarteter Gewinn:** Pro Section –3 bis –4 min (Schritte 1+2+3 entfallen für Sections 2–11). Total: **–35 bis –40 min**.

### B.1 — Contract anlegen

- Neuer Pydantic-Contract `ReportInterviewCache` in `backend/app/contracts/report_interview_cache_contract.py`:
  - `report_id: str`
  - `simulation_id: str`
  - `simulation_requirement: str` (Hash daraus als Cache-Key-Teil)
  - `interview_topic: str` (das `interview_requirement` aus dem Tool-Call)
  - `selected_agent_indices: list[int]`
  - `selection_reasoning: str`
  - `questions: list[str]`
  - `agent_responses: list[AgentInterviewResponse]` (existierendes DTO)
  - `created_at: datetime`
  - `ttl_seconds: int = 3600`
- Schema-Drift-Gate: `dump_schemas.py --check` muss byte-genau passen.
- **Tests** (`tests/contracts/test_report_interview_cache_contract.py`):
  - Valid-Roundtrip Pydantic ↔ JSON
  - Missing-Field-Fehler
  - TTL-Boundary

### B.2 — Cache-Store

- Neue Service-Datei `backend/app/services/report_interview_cache_store.py`:
  - In-Memory `dict[str, ReportInterviewCache]` keyed by `report_id`
  - Optional File-Backed via `ArtifactLocator.run_dir(run_id)/interview_cache.json` für Crash-Recovery
  - Locking via `threading.Lock` (Report-Generation läuft im Background-Thread, Slice C wird das auf ThreadPool umstellen)
- **Tests**: get/set/expire/concurrent-write.

### B.3 — Tool integrieren

**Architektur-Korrektur nach Code-Verifikation (2026-05-16):**
Es existiert **kein eigenes `InterviewAgents`-Class**, sondern die Method
[`GraphToolsService.interview_agents()`](backend/app/services/graph_tools.py:188).
`simulation_id` ist bereits ein **vom LLM gesetzter Tool-Parameter**.
`GraphToolsService` wird **pro Run einmal** in [`report.py:248`](backend/app/api/report.py:248)
bzw. [`runs.py:636`](backend/app/api/runs.py:636) konstruiert — heißt:
**eine Tool-Instance gehört zu genau einem Report**.

→ ContextVar entfällt. Cache wird Instance-Attribut auf `GraphToolsService`.

- `GraphToolsService.__init__` erweitern: `interview_cache: ReportInterviewCacheStore | None = None`.
- `interview_agents()` Modifikation:
  - Vor Schritt 1 (`_load_agent_profiles`): falls `self.interview_cache is not None`, Lookup nach Key `(simulation_id, interview_requirement_hash)`.
  - Cache hit → direkt `InterviewResult` zurückgeben (Log: `cache HIT for sim=<id> topic=<hash>`).
  - Cache miss → existierender Pfad + Cache-Write am Ende.
- **Konstruktions-Sites — Cache nur an Pipeline-Stellen aktivieren:**
  | Site | Datei | Zeile | Cache aktiv? | Begründung |
  |---|---|---|---|---|
  | Report-Run (Sync) | `app/api/report.py` | 248 | **Ja** | Section-Loop → Cache greift |
  | Report-Run (Async/Worker) | `app/api/runs.py` | 636 | **Ja** | identischer Pipeline-Pfad |
  | Chat-Endpoint | `app/api/report.py` | 849 | Nein | One-Shot, kein wiederholtes Interview |
  | Section-Repair-Endpoint | `app/api/report.py` | 990 | Nein | Repair eines einzelnen Sections, irrelevant für Cache |
  | Section-Regen-Endpoint | `app/api/report.py` | 1005 | Nein | wie 990 |

- **Cache-Key**: `(simulation_id, sha256(normalized_interview_requirement)[:16])`. Topic-Normalisierung: lowercase, whitespace-collapse, optional Embedding-Similarity-Fallback in einem späteren Sub-Slice (siehe B.6 unten).
- **Wichtig**: weil das LLM den `interview_requirement`-String pro Section frei wählt, ist exakt-Match-Hit-Rate möglicherweise niedrig. Erstversion: exakt-Match (Telemetrie loggen). Wenn Hit-Rate < 50%, in B.6 auf Embedding-Similarity nachschärfen.

### B.4 — Invalidation

- Cache wird beim Report-Start (vor Outline-Planning) komplett für `report_id` gepurged.
- Bei Report-Failure: nichts tun (TTL läuft ab).

### B.5 — Verification Gate

```bash
uv run pytest tests/contracts/test_report_interview_cache_contract.py tests/services/test_report_interview_cache_store.py -v
uv run pytest tests/ -k "interview" -v
uv run python scripts/dump_schemas.py --check
```

Smoke (manuell):
1. Report-Run starten, Backend-Log beobachten.
2. Erwartung: `[InterviewAgents] cache HIT for report=…` ab Section 2.
3. Section 2–11 sollten je ~3 min sparen vs. Baseline.

**Aufwand-Schätzung:** 2–3 h für die 5 Sub-Sub-Slices, exkl. Smoke.

**Risiken:**
- Sections, die explizit unterschiedliche `interview_topic`-Formulierungen erzeugen (ReACT-Agent kann frei wählen) → niedrige Hit-Rate. **Mitigation:** Telemetrie in B.3 messen; bei < 50% Hit-Rate Slice **B.6** (Embedding-Similarity via `qwen3-embedding:4b` lokal) nachziehen.
- Cache-File-Race bei Slice C (mehrere Sections parallel schreiben). **Mitigation:** Slice B ohne File-Backed-Store starten; File-Backing in einem späteren Sub-Slice nach C.

### B.6 — (Optional, nach Telemetrie) Embedding-Similarity-Match

Nur nachziehen, wenn Hit-Rate in B.3-Telemetrie < 50%. Topic-Similarity via `qwen3-embedding:4b` lokal, Cosine ≥ 0.85 → Hit. Eigener Mini-PR, hängt nicht im kritischen Pfad.

---

## Slice C — Section-Parallelisierung

**Ziel:** Section-Loop in [`workflow.py:586`](backend/app/services/report_agent/workflow.py:586) auf `concurrent.futures.ThreadPoolExecutor(max_workers=4)` umstellen. 11 Sections in 4er-Batches → ~3 Wellen.

**Erwarteter Gewinn:** Wallclock 75–80 min → ~20 min (mit Slice B kombiniert: ~5–10 min).

### Bevor Slice C beginnt — Pre-Flight

1. **Slice B muss gemerged sein** — sonst hämmert jede parallele Section unkoordiniert eigene Interviews → Ollama-Cloud-Rate-Limit + Token-Costs explodieren.
2. **Sequential Verification Gate** auf main: Pydantic-Contracts + Schema-Drift + voller pytest grün.

### C.0 — Helper-Modul `section_dependency_resolver`

Vor C.1/C.2 als eigener Mini-PR: Pure-Function-Modul ohne Code-Anbindung, damit C.2 atomar bleibt.

- Neue Datei `backend/app/services/report_agent/section_dependency_resolver.py` mit:
  ```python
  def build_dependency_waves(
      sections: list[ReportSection],
      dep_map: SectionDependencyMap,
  ) -> list[list[int]]:
      """Kahn-Topologie: Liste von Indexwellen, die parallel laufen dürfen.
      Wirft DependencyCycleError, wenn der Graph nicht azyklisch ist."""

  def collect_deps(
      section_index: int,
      generated_sections: dict[int, str],
      dep_map: SectionDependencyMap,
  ) -> list[str]:
      """Liefert die Kontext-Sections-Inhalte, die der Section vorausgehen müssen,
      in stabiler Reihenfolge (sortiert nach section_index)."""

  class DependencyCycleError(ValueError):
      pass
  ```
- **Tests** (`tests/services/test_section_dependency_resolver.py`):
  - leerer Dep-Graph → 1 Welle mit allen Indexes
  - lineare Kette → N Wellen à 1 Section
  - Diamant (1→2, 1→3, 2→4, 3→4) → 3 Wellen
  - Zyklus → `DependencyCycleError`
  - `collect_deps` mit fehlender Vorgänger-Section → leerer Kontext (kein Crash)
- **Aufwand:** 1 h. Eigener PR vor C.1.

### C.1 — Section-Dependency-Modell anlegen

⚠️ **Senior-Review erforderlich:** Outline-Planner-Prompt-Erweiterung berührt **Layer 2 (Prompt-Semantik)**. CLAUDE.md → Opus-Lead-Review zwingend, **nicht** an Sonnet-Subagent delegieren. Wording-Glossar-Touch wahrscheinlich (neue Klassifikations-Begriffe in DE).

Aktuell wird `previous_sections: list[str]` als Kontext an jede Section weitergereicht. Bei Parallelisierung ist diese strikte Ordnung weg.

- Neuer Pydantic-Contract `SectionDependencyMap`:
  - `section_index: int → depends_on: list[int]`
  - Default: `[]` (unabhängig)
  - Outline-Planner-Prompt erweitern um Dependency-Klassifikation: welche Section braucht welche Vorgängerinhalte (z.B. Executive Summary depends_on Findings)
- `previous_sections`-Parameter in `generate_section_react` bleibt erhalten; intern wird er aus `collect_deps(...)` (C.0) gefüllt.
- **Tests**: Snapshot-Test gegen einen Outline-Planner-Output mit erwartetem Dep-Graph; Layer-2-Prompt-Diff im Worklog dokumentieren.

### C.2 — ThreadPool-Loop

Ersetze [`workflow.py:586`](backend/app/services/report_agent/workflow.py:586) durch eine Wave-Schleife:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

waves = build_dependency_waves(outline.sections, dep_map)
generated_sections: dict[int, str] = {idx: existing_sections[idx] for idx in existing_sections}

with ThreadPoolExecutor(max_workers=int(os.environ.get("AGORA_REPORT_SECTION_PARALLEL", "4"))) as executor:
    for wave in waves:
        futures = {
            executor.submit(
                generate_section_react,
                agent=agent,
                section=outline.sections[idx - 1],
                outline=outline,
                previous_sections=_collect_deps(idx, generated_sections, dep_map),
                progress_callback=_make_progress(idx, base_progress),
                section_index=idx,
            ): idx
            for idx in wave if idx not in existing_sections
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            generated_sections[idx] = fut.result()
            ReportManager.save_section(report_id, idx, generated_sections[idx])
```

- ENV-Knopf `AGORA_REPORT_SECTION_PARALLEL=4` (default 4, =1 für sequentiell-Fallback).
- Wave-Berechnung via Kahn-Topologie.

### C.3 — Thread-Safety-Audit

- `ReportAgent.evidence_map` wird in `generate_section_react` gelesen UND geschrieben (Persona-Quote-Validation). **Lock** auf `agent._evidence_lock` einbauen.
- `ReportManager.save_section`/`update_progress` schreibt SQLite — bereits thread-safe? Verifizieren via Code-Review-Graph: `query_graph callers_of save_section`.
- LLM-Client (HTTP gegen Ollama Cloud) — Connection-Pool? `requests.Session` ist thread-safe für GET/POST, aber pro-Worker eigene Session ist robuster.

### C.4 — Progress-Reporting + Lock-ADR

`progress_callback` aktuell als Linear-Increment. Bei Parallel: pro Section eigener Wave-Anteil. Neue Helper-Funktion `make_wave_progress(wave_idx, total_waves, section_in_wave, wave_size)`.

⚠️ **ADR-Kandidat:** Mit C.3 wird der **erste explizite Lock** im `report_agent`-Modul eingeführt (Code-Verifikation 2026-05-16 bestätigt: aktuell kein `threading.Lock`/`RLock` im Modul). Begründung + Granularität + Failure-Modes (Deadlock-Risiko, Lock-Reihenfolge) gehören in `docs/decisions/0003-report-agent-locks.md`. ADR vor PR 4 schreiben, im PR-Body referenzieren.

### C.5 — Verification Gate

```bash
uv run pytest tests/services/test_report_section_waves.py -v   # Topologie + Cycle-Detection
uv run pytest tests/services/test_report_agent_threadsafety.py -v   # Locks + race conditions
uv run pytest tests/ -m "not llm" -k "report"   # Report-Pfad grün ohne Live-LLM
AGORA_REPORT_SECTION_PARALLEL=1 uv run pytest tests/  # Fallback-Pfad
```

Smoke (manuell):
1. Report-Run starten, Wallclock messen.
2. Erwartung mit B+C: 5–10 min statt 80.
3. Output-Qualität gegen ein Baseline-Report-Snapshot prüfen (manuelle Diff-Sichtung — automatisierte Equality wäre flaky wegen LLM-Nondeterminismus).

**Aufwand-Schätzung:** 4–6 h (C.1 + C.2 = 2–3 h, C.3 Audit = 1–2 h, C.4 = 30 min, Tests = 1 h).

**Risiken:**
- **Quote-Validation in [`workflow.py:617`](backend/app/services/report_agent/workflow.py:617)** ruft `validate_quote_anchors` auf `agent.evidence_map` — wenn zwei parallele Sections gleichzeitig schreiben, kann die Map korrumpieren. Lock zwingend (C.3).
- **Dependency-Klassifikation des Outline-Planners** kann falsch sein → Section bekommt unvollständigen Kontext → Qualitätsverlust. Mitigation: Default `depends_on = [all previous]` für sicheren Fallback; LLM-Klassifikation nur opt-in via `AGORA_REPORT_SECTION_DEPS=auto` (default `chain` = alle vorherigen, sequentiell-äquivalent semantisch).
- **Ollama-Cloud-Rate-Limit** bei 4 parallelen LLM-Streams. Mitigation: ENV-Knopf erlaubt Reduktion auf 2 oder 1.

---

## Reihenfolge & PRs

| PR | Slice | Branch | Depends on | Review-Modell |
|---|---|---|---|---|
| 1 | B.1 + B.2 (Contract + Store, ohne Tool-Integration) | `feat/report-interview-cache-store` | — | Sonnet |
| 2 | B.3 + B.4 (Tool-Integration + Invalidation) | `feat/report-interview-cache-wired` | PR 1 | Sonnet |
| 3 | C.0 (Resolver-Helper-Modul + Tests) | `feat/report-section-dep-resolver` | — | Sonnet |
| 4 | C.1 (Dependency-Map-Contract + Outline-Planner-Prompt) | `feat/report-section-deps` | PR 3 | **Opus** (Layer 2) |
| 5 | ADR-0003 (Locks im report_agent) | `docs/adr-report-agent-locks` | — | Opus |
| 6 | C.2 + C.3 + C.4 (ThreadPool + Locks + Progress) | `feat/report-section-parallel` | PR 2 + PR 4 + PR 5 | **Opus** (Cross-Layer + erstes Lock) |
| 7 | (Optional) B.6 (Embedding-Similarity) — nur wenn Hit-Rate < 50% | `feat/report-interview-cache-similarity` | PR 2 in Prod | Sonnet |

**Atomic Slicing:** je PR ≤ 400 LOC, eigener Worklog unter `docs/archive/worklogs/`.

## Rollback-Strategie

- Slice B: Cache-Lookup hinter `AGORA_REPORT_INTERVIEW_CACHE_ENABLED=true` Flag (default `true` nach Bake-In, in PR-1 default `false`).
- Slice C: `AGORA_REPORT_SECTION_PARALLEL=1` schaltet zurück auf Seriell — Code-Pfad bleibt strukturell gleich, nur die Pool-Size ändert sich.

## Out of scope (eigene Slices, nicht in B/C)

- **Slice A** (Schnelles LLM für Helper-Stages): kleinste Änderung, höchster ROI/Stunde, eigener Mini-PR vorher.
- **Slice D** (Outline-Planner anweisen, max 6 Sections statt 11): Prompt-Engineering im Layer 2, eigener PR, betrifft Wording-Glossar (Senior-Review).
- **Slice E** (`max_agents` reduzieren von 8 → 3 für non-DACH-Sections): Knob existiert schon, nur Config-Default + UI-Toggle nötig.

## Memory-Verknüpfungen

Verwandt: [[project-vector-index-dim-drift]] (Embedding-Topic für B.1 Cache-Key-Similarity).
