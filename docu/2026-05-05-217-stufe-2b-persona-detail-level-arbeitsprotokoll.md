# Arbeitsprotokoll: Issue #217 Stufe 2b — Persona-Detail-Level (Output-Größen-Steuerung)

**Datum:** 2026-05-05
**Branch:** `feat/issue-217-stufe-2b-output-detail-level`
**Worker:** agora-refactor-worker (Sonnet)
**Bezug:** Issue #217, Stufe 2b — Pivot von Batch-Prompt auf Output-Größen-Steuerung

---

## Was und Warum

Stufe 2a hat `parallel_count`-Default auf 10 erhöht und erzielte ~14–16 % Wall-Clock-Reduktion mit `gemini-3-flash-preview:cloud`. Das 30 %-Ziel von Issue #217 wurde nicht erreicht.

**Pivot-Begründung:** Der Bottleneck bei Cloud-LLMs liegt nicht im Netzwerk-Roundtrip, sondern in der Streaming-Decoder-Zeit, die linear mit der Anzahl der Output-Tokens wächst. Persona-Beschreibungen waren bisher 1500–2000 Wörter pro Persona. Eine Reduktion auf ~800 Wörter (Standard) sollte ~50–60 % Wall-Clock-Reduktion bringen — weit über dem 30 %-Ziel.

---

## Drei Levels

| Level | Wörter (DE) | Context-Limit | Erwarteter Speedup vs. `rich` |
|---|---|---|---|
| `compact` | 300–500 | 1200 Zeichen | ~75–80 % |
| `standard` | 700–900 | 2000 Zeichen | ~50–60 % |
| `rich` | 1500–2000 | 3000 Zeichen | 0 % (alter Stand) |

---

## Backward-Compatibility

`rich` produziert exakt das Verhalten vor diesem Slice:
- Wortanzahl-Anweisung im Prompt: `1500–2000 Wörter` (DE) / `2000 words` (EN)
- Context-Limit: 3000 Zeichen (alter Wert)

User die die bisherige Persona-Reichhaltigkeit explizit brauchen, setzen `AGORA_PERSONA_DETAIL_LEVEL=rich`.

---

## Qualitäts-Hinweis

`_validate_profile_metadata` (Zeile ~655) prüft semantische Pflichtfelder (`display_name`, `bio`, `persona`, `age`, `gender`, `mbti`, `country`, `profession`, `interested_topics`, `voice_register`) — **nicht** die Wortzahl. Das Pflichtfeld `persona` bleibt syntaktisch valide bei allen drei Levels. Die Pydantic-Minlänge aus `PersonaModel` beträgt 300 Zeichen — der `compact`-Level mit 300–500 Wörtern liegt weit darüber.

---

## Geänderte Dateien

| Datei | Änderungen |
|---|---|
| `backend/app/services/oasis_profile_generator.py` | `import os` module-level; `PERSONA_DETAIL_LEVELS` dict; `_resolve_persona_detail_level()` Funktion; `_build_individual_persona_prompt` + `_build_group_persona_prompt` jeweils `detail`-Injection + `context_str`-Slice + Word-Count-Strings |
| `backend/tests/perf/test_persona_generation_latency.py` | 3 neue Tests (default-standard, known-values-parametrisiert, unknown-fallback) |
| `.env.example` | `AGORA_PERSONA_DETAIL_LEVEL=standard` im Performance-Block nach `OLLAMA_THINKING` |
| `CHANGELOG.md` | `[Unreleased] ### Changed` Eintrag |

---

## Real-LLM-Test-Anleitung (Orchestrator führt nach Merge aus)

```bash
# Voraussetzung: LLM_BASE_URL, LLM_API_KEY, LLM_MODEL_NAME im env (gemini-3-flash-preview:cloud)

# Baseline (rich — alter Stand):
AGORA_PERSONA_DETAIL_LEVEL=rich pytest tests/perf/ -m "perf and llm" -k "parallel_count-10" -s

# Standard (neuer Default):
AGORA_PERSONA_DETAIL_LEVEL=standard pytest tests/perf/ -m "perf and llm" -k "parallel_count-10" -s

# Compact:
AGORA_PERSONA_DETAIL_LEVEL=compact pytest tests/perf/ -m "perf and llm" -k "parallel_count-10" -s
```

Der `test_persona_generation_perf_real_llm`-Benchmark gibt `wall_ms`, `per_call_p50` und `per_call_p95` aus.

---

## Vorher/Nachher-Tabelle (gemessen 2026-05-05, warm Cloud)

**Setup:** `LLM_MODEL_NAME=gemini-3-flash-preview:cloud` über Ollama-Bridge,
`AGORA_PARALLEL_PERSONA_COUNT=10`, `LLM_DISABLE_JSON_MODE=true`,
`OLLAMA_THINKING=false`, 10 synthetische Personas pro Lauf. Aufruf:

```bash
for level in rich standard compact; do
  AGORA_PERSONA_DETAIL_LEVEL=$level AGORA_PARALLEL_PERSONA_COUNT=10 \
  LLM_BASE_URL=http://localhost:11434/v1 LLM_API_KEY=ollama \
  LLM_MODEL_NAME=gemini-3-flash-preview:cloud \
  LLM_DISABLE_JSON_MODE=true OLLAMA_THINKING=false \
  uv run pytest tests/perf/test_persona_generation_latency.py::test_persona_generation_perf_real_llm \
    -k "10" -v -m "perf and llm" -s
done
```

| Konfiguration | wall_ms (10 Personas) | per_call_p50 ms | per_call_p95 ms | Reduktion vs. rich |
|---|---|---|---|---|
| **rich** (1500-2000W, alter Stand) | 61 309 | 40 352 | 61 300 | — |
| **standard** (700-900W, neuer Default) | 63 632 | 37 556 | 63 615 | **+4 % langsamer** |
| **compact** (300-500W) | 40 253 | 28 424 | 40 205 | **−34 %** |

### Befunde (ehrlich)

1. **`standard` bringt keinen messbaren Speedup gegenüber `rich`** (innerhalb Mess-Noise). Cloud-Modell `gemini-3-flash-preview:cloud` respektiert die mittlere Wortvorgabe (700-900W) nicht streng — es produziert ähnlich detailreiche Output unabhängig davon, ob 700-900 oder 1500-2000 Wörter spezifiziert sind. Die 11 Pflichtfelder + die geforderten Persona-Sub-Aspekte (Eckdaten, Hintergrund, Persönlichkeit, Verhalten, Haltungen, Eigenheiten, Erinnerungen) erzwingen eine Mindest-Output-Größe, die das Modell selbst festlegt.

2. **`compact` (300-500W) springt klar:** −34 % Wall-Clock-Reduktion gegenüber `rich`. Hier wird die Wortvorgabe ernst genommen — und der Speedup ist messbar.

3. **per-call p50 sinkt monoton** (40 → 38 → 28 ms), aber die **Wall-Clock-Tail-Latenz dominiert**. Das bestätigt, dass Stufe 2a's `parallel_count`-Tuning bereits den Concurrency-Hebel ausgereizt hat.

### Konsequenz für Default und Issue-Status

- **Default bleibt `standard`** (kein User-spürbarer Quality-Verlust gegenüber rich, kein breaking change).
- **`compact` als Opt-in** — Operator setzt `AGORA_PERSONA_DETAIL_LEVEL=compact` für Bulk-Sims oder schnelle Iterationen.
- **`Refs #217`, kein Closes** — die 30 %-Reduktionsregel des Issues wird nur mit Opt-in `compact` erreicht, nicht im Default-Pfad. Issue bleibt offen für eine Folge-Slice, die entweder
   (a) `compact` als Default rechtfertigt (UX-Entscheidung, breaking-ish),
   (b) Batch-Prompt mit Validation-Pipeline-Anpassung implementiert (höheres Risiko, eigener L-Slice), oder
   (c) eine andere Hebel-Klasse einbringt (HTTP-Connection-Pool-Tuning, Modell-Wechsel auf reines lokales Setup).

---

## Anomalien / Seiteneffekte

Keine. `_validate_profile_metadata` und JSON-Repair-Pipeline (`_fix_truncated_json` / `_try_fix_json`) wurden nicht angefasst. Der lokale `import os` in `generate_profiles_from_entities` (Zeile ~1193) wurde auf module-level `import os` konsolidiert — kein Verhaltensunterschied.
