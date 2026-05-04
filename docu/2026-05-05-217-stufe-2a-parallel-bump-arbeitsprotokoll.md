# Arbeitsprotokoll: Issue #217 Stufe 2a — Persona-Latenz erste Optimierungs-Welle

Datum: 2026-05-05
Branch: `feat/issue-217-stufe-2a-parallel-bump`
Refs: #217 (Refs, kein Closes — Stufe 2b folgt)

## Was und Warum

Stufe 1 (PR e72058e) hat den `@measure_llm_latency`-Decorator auf
`OasisProfileGenerator._generate_profile_with_llm` verdrahtet. Damit ist
Baseline-Messung möglich. Stufe 2a liefert die erste Optimierungs-Welle:

1. **parallel_count 5 → 10 als Default** — Hartkodierter Default `parallel_count: int = 5`
   in `generate_profiles_from_entities` und `parallel_profile_count: int = 3` in
   `prepare_simulation` waren zu konservativ für Cloud-LLM-Setups. Beide Parameter
   wurden auf `Optional[int] = None` umgestellt; env-Override `AGORA_PARALLEL_PERSONA_COUNT`
   erlaubt Operatoren, den Wert ohne Code-Change anzupassen.

2. **env-Konfigurierbarkeit** — Auflösungsreihenfolge: explizit gesetzter Wert →
   `AGORA_PARALLEL_PERSONA_COUNT` (env) → Fallback 10. Defensive Auflösung mit
   `try/except ValueError → 10`. Auflösung erfolgt einmalig in `prepare_simulation`
   bevor `_phase_generate_profiles` gerufen wird — kein Dual-Resolution-Problem.

3. **`.env.example` dokumentiert** — `AGORA_PARALLEL_PERSONA_COUNT`, `LLM_DISABLE_JSON_MODE`
   und `OLLAMA_THINKING` waren im laufenden Container aktiv (`LLM_DISABLE_JSON_MODE=true`,
   `OLLAMA_THINKING=false`), aber nicht im Repo dokumentiert. Das macht Reproduzierbarkeit
   kaputt — beides ist jetzt als Kommentar-Block in `.env.example` nachgezogen.

## Cloud vs. lokal — Warum 10 als Default sinnvoll ist

| Setup | Empfehlung | Begründung |
|---|---|---|
| Cloud-LLM (Ollama-Bridge, gemini-3-flash, qwen3-coder:cloud) | 10–15 | Provider skaliert horizontal; kein KV-Cache-Trashing; `keep_alive` ist no-op |
| Lokales Ollama (qwen2.5:14b, llama3.1:8b, 1× GPU) | 3–5 | KV-Cache ist shared; zu viele parallele Requests degradieren p95-Latenz durch Cache-Eviction |
| Lokales Ollama (2× GPU / hohe VRAM) | 5–8 | Abhängig von VRAM und Batch-Größe |

Der Default 10 ist cloud-friendly und für lokale Setups per env herunterstellbar.
Der alte Default 5 war lokal-konservativ und hat Cloud-Setups unnötig gedrosselt.

## Geänderte Dateien

| Datei | Zeilen-Range | Was |
|---|---|---|
| `backend/app/services/oasis_profile_generator.py` | 1166–1200 | `parallel_count: int = 5` → `Optional[int] = None` + env-Resolution |
| `backend/app/services/prepare_service.py` | 382, 421–429 | `parallel_profile_count: int = 3` → `Optional[int] = None` + env-Resolution |
| `.env.example` | Ende (neu) | Performance-Kommentar-Block mit 3 Schlüsseln |
| `backend/tests/perf/test_persona_generation_latency.py` | Ende (neu) | 2 neue Tests (env-Resolution + Real-LLM-Bench) |
| `CHANGELOG.md` | `[Unreleased] ### Changed` | Eintrag Stufe 2a |

## Neue Tests

### `test_generate_profiles_from_entities_resolves_parallel_count_from_env`

Deterministisch, kein LLM-Call. Setzt `AGORA_PARALLEL_PERSONA_COUNT=7` via
`monkeypatch`, ruft `generate_profiles_from_entities(parallel_count=None)` mit
gepatchtem `OpenAI`-Client und gepatchter `generate_profile_from_entity`-Methode.
Prüft, dass `ThreadPoolExecutor(max_workers=7)` instanziiert wurde.

Läuft im Default-CI (`-m "not llm"`).

### `test_persona_generation_perf_real_llm` (parametrize: parallel_count=[5, 10, 15])

Real-LLM-Bench für Orchestrator-Messung. Benötigt `LLM_BASE_URL` im env, sonst
`pytest.skip`. Misst Wall-Clock-Latenz + Decorator-Records (p50/p95 per-call).
Print-Output für Vorher/Nachher-Tabelle.

**Läuft NICHT im Default-CI** — Pflicht-Marker `@pytest.mark.llm`.
Aufruf: `pytest -m 'perf and llm' tests/perf/ -v -s`

## Vorher/Nachher-Tabelle (gemessen 2026-05-05, Cloud-LLM)

**Setup:** `LLM_MODEL_NAME=gemini-3-flash-preview:cloud` über Ollama-Bridge
(`LLM_BASE_URL=http://localhost:11434/v1`), `LLM_DISABLE_JSON_MODE=true`,
`OLLAMA_THINKING=false`, 10 synthetische Personas, je 3 Konfigurationen,
2 Wiederholungs-Runs (cold + warm Cloud). Aufruf:

```bash
LLM_BASE_URL=http://localhost:11434/v1 LLM_API_KEY=ollama \
LLM_MODEL_NAME=gemini-3-flash-preview:cloud \
LLM_DISABLE_JSON_MODE=true OLLAMA_THINKING=false \
uv run pytest tests/perf/ -v -m "perf and llm" -s
```

| parallel_count | wall_ms (cold) | wall_ms (warm) | p50 (warm) | p95 (warm) | Δ wall vs. 5 |
|---|---|---|---|---|---|
| **5 (Baseline)** | 89 170 | 89 170 | 42 184 | 47 435 | — |
| **10 (Stufe 2a Default)** | 177 533 | 76 738 | 56 743 | 76 723 | **−14 %** (warm) / **+99 %** (cold) |
| **15 (Cloud-Upper)** | 124 828 | 74 878 | 57 704 | 74 868 | **−16 %** (warm) / **+40 %** (cold) |

### Befunde

1. **Bei warm Cloud:** parallel_count=10 spart ~14 %, parallel_count=15 nur unwesentlich mehr (~16 %). Marginal-Nutzen kollabiert nach 10.
2. **Bei cold Cloud (erster Call eines neuen Routers):** parallel_count=10 ist **schlechter** (177s vs. 89s) — Cloud-Throttling/Queue-Effekt bei `gemini-3-flash-preview:cloud`. Nach Warmup verschwindet das.
3. **Per-Call-Latenz steigt** mit höherem parallel_count (p50 42→57s), Wall-Clock sinkt aber. Klassischer Latency-vs-Throughput-Trade-off.
4. **15 % Reduktion** ist ehrlich, aber **kein Closes-Wert für #217** — Issue verlangt ≥ 30 %.

### Empfehlung Default

`AGORA_PARALLEL_PERSONA_COUNT=10` als Default beibehalten:
- Sweet-Spot Wall-Clock vs. Cold-Risiko
- 15 bringt nur marginal mehr und höheres Cold-Risiko bei Cloud-Routerwechsel
- Operatoren mit lokalem Ollama sollten 3–5 setzen (KV-Cache-Trashing)

### Folge-Slice 2b ist Pflicht für Closes #217

Stufe 2a allein erreicht das 30%-Ziel **nicht**. Echter Hebel ist Batch-Prompt
(1 LLM-Call → N Personas), der Roundtrip-Overhead eliminiert. Geschätzt
zusätzliche 40–60 % Reduktion möglich. Closes #217 erst dann.

## Real-LLM-Test: Stufe 2b-Voraussetzungen

Der Test ist als voll-funktionsfähige Variante gebaut (kein Skip-Platzhalter).
`OasisProfileGenerator()` ohne explizite Args liest `LLM_API_KEY`, `LLM_BASE_URL`,
`LLM_MODEL_NAME` aus dem env — wenn `LLM_BASE_URL` nicht gesetzt ist, skippt der Test.
`EntityNode` wird synthetisch erzeugt (keine Neo4j-Verbindung nötig).

Für Stufe 2b (Batch-Prompt) wird der gleiche Test-Frame genutzt; nur
`generate_profiles_from_entities` erhält dann den Batch-Pfad.

## Folge-Slice 2b

Batch-Prompt-Optimierung: statt N einzelne LLM-Roundtrips bündelt ein
Batch-Call mehrere Personas in einem Request. Validation-Pipeline-Anpassung
erforderlich (L-Slice, höheres Risiko). Closes #217 mit Vorher/Nachher-Tabelle
erst in 2b.

## Verify-Checkliste (alle grün)

- [x] `uv run pytest tests/perf/ -v -m "not llm"` — 6 passed, 3 deselected
- [x] `uv run pytest -x -q` — 1480 passed, 9 skipped
- [x] `uv run ruff check app/ tests/` — All checks passed
- [x] `uv run python -m app.contracts.dump_schemas && git diff --exit-code schemas/` — no drift
- [x] sig-check: `parallel_count` default ist `None` (resolved at runtime)
- [x] `.env.example` enthält Performance-Block mit `AGORA_PARALLEL_PERSONA_COUNT`
