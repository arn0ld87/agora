# Arbeitsprotokoll: Issue #217 Stufe 1 – LLM-Latenz-Messung (Persona-Generierung)

**Datum:** 2026-05-05
**Branch:** feat/issue-217-persona-latency-measure
**Scope:** Stufe 1 (Messung). Stufe 2 (Optimierung) folgt als separater Slice.
**Refs:** Issue #217 — „Erstellen von Personas dauert teils ewig"

---

## Scope-Abgrenzung

Diese Slice implementiert ausschließlich die **Messinstrumentierung**:

- `@measure_llm_latency`-Decorator in `backend/app/utils/llm_latency.py`
- Anwendung auf `OasisProfileGenerator._generate_profile_with_llm`
- `perf`-Marker in `pyproject.toml`
- 5 deterministisch lauffähige Tests in `tests/perf/`

Issue #217 wird **nicht** mit dieser Slice geschlossen. Closes #217 erfolgt
erst nach Stufe 2, wenn ein Optimierungs-Hebel (asyncio.gather, keep_alive-Cache,
Modell-Größe, Batch-Generierung) eine Latenz-Reduktion von ≥ 30 % gegenüber der
Stufe-1-Baseline nachweist.

---

## Begründung: Decorator auf `_generate_profile_with_llm`, nicht auf Public-Wrapper

`generate_profile_from_entity` (Public-Wrapper) umschließt neben dem LLM-Roundtrip
auch Kontext-Aufbau, JSON-Repair, Voice-Register-Validation und Fallback-Logik.
Würde der Decorator dort angewendet, würde die gemessene Latenz all diese
Nebenarbeiten einschließen — und beim Vorher/Nachher-Vergleich von Stufe 2 wäre
unklar, ob eine Messzahl-Änderung vom LLM oder von einer Änderung im Validation-
Pfad kommt.

`_generate_profile_with_llm` ist der direkte Wrapper um `client.chat.completions.create`.
Hier ist die Messung chirurgisch genau.

---

## Strukturierte Logfelder (`agora.llm_latency`-Logger)

| Feld | Typ | Bedeutung |
|---|---|---|
| `operation` | `str` | Logischer Operationsname (`'persona_generation'` oder Fallback auf `func.__qualname__`) |
| `function` | `str` | `func.__qualname__` der dekorierten Funktion |
| `latency_ms` | `float` | Wall-Clock-Zeit in Millisekunden (gerundet auf 2 Dezimalstellen) |
| `roundtrips` | `int` | Anzahl LLM-Roundtrips (Stufe 1: immer 1; Stufe 2 kann via `contextvars` zählen) |
| `success` | `bool` | `True` wenn die Funktion normal zurückgekehrt ist, `False` bei Exception |
| `model` | `Optional[str]` | Modellname aus `self.model_name` (via `extract_model`-Extractor) |
| `prompt_chars` | `Optional[int]` | Summe der Prompt-Längen; Stufe 1: `None` (Prompts in `_generate_profile_with_llm` werden als lokale Variable innerhalb der Methode gebaut, nicht als Parameter übergeben) |
| `error_type` | `Optional[str]` | Name der Exception-Klasse bei `success=False`, sonst `None` |

---

## Warum `prompt_chars=None` in Stufe 1

Die Methode `_generate_profile_with_llm` baut ihren Prompt intern (`self._build_individual_persona_prompt` /
`self._build_group_persona_prompt`) und übergibt ihn nicht als Parameter. Ein
`extract_prompt_chars`-Extractor hätte entweder die interne Methodenlogik dupliziert
oder ein flüchtiges Attribut auf `self` gesetzt — beide Ansätze sind fehleranfälliger
als `None`. In Stufe 2 kann der Extractor nachgerüstet werden, wenn Prompt-Größe
als Optimierungs-Indikator relevant wird.

---

## Test-Strategie

Alle 5 Tests in `tests/perf/` sind **deterministisch** und laufen ohne Ollama:

1. **`test_measure_llm_latency_emits_structured_log`** — Prüft alle Log-Felder bei
   erfolgreichem Call (inkl. `latency_ms ≥ 10 ms` durch `time.sleep(0.01)`).
2. **`test_measure_llm_latency_logs_on_exception`** — Prüft `success=False`,
   `error_type='RuntimeError'`; verifiziert dass Exception sauber re-raised wird.
3. **`test_generate_profile_with_llm_decorator_applied`** — Prüft via `__wrapped__`
   (gesetzt durch `@functools.wraps`), dass der Decorator auf der echten Methode
   angewendet wurde. Kein Mocking von Neo4j/EntityNode nötig.
4. **`test_measure_llm_latency_extract_model`** — Prüft dass `extract_model`-Extractor
   `self.model_name` korrekt in den Log-Record schreibt.
5. **`test_measure_llm_latency_extractor_exception_is_swallowed`** — Prüft dass
   eine Exception im Extractor den eigentlichen Call nicht unterbricht (Hardstop-Anforderung).

### Logging-Capture-Workaround

`setup_logger` in `app/utils/logger.py` setzt `propagate=False` auf dem `agora`-
Parent-Logger. pytest's `caplog`-Fixture hängt am Root-Logger und erfasst daher
keine `agora.*`-Records. Stattdessen wird ein eigener `_RecordCapture`-Handler
direkt an `logging.getLogger('agora.llm_latency')` gehängt und nach dem Test
wieder entfernt. Dieses Muster ist im Repo bereits etabliert (siehe
`tests/api/test_logs_stream_reconnect.py`, `tests/test_llm_client.py`).

---

## Folge-Slice-Hinweis (Stufe 2)

Stufe 2 ist separat zu planen und umfasst:

- Messung der Baseline-Latenz mit echtem Ollama (Marker: `@pytest.mark.perf and llm`)
- Implementierung eines Optimierungs-Hebels (Kandidaten: `asyncio.gather` für
  Batch-Generierung, keep_alive-Cache via Ollama-Header, kleineres Modell für
  Draft-Pass)
- Nachweis ≥ 30 % Latenz-Reduktion in `tests/perf/test_persona_generation_latency.py`
  Stufe-2-Test
- Erst dann: `Closes #217` im Commit-Message/PR

---

## Geänderte Dateien

| Datei | Typ | LOC (netto) |
|---|---|---|
| `backend/app/utils/llm_latency.py` | neu | +80 |
| `backend/app/services/oasis_profile_generator.py` | geändert | +7 (Import + Decorator) |
| `backend/pyproject.toml` | geändert | +1 (perf-Marker) |
| `backend/tests/perf/__init__.py` | neu | 0 |
| `backend/tests/perf/test_persona_generation_latency.py` | neu | +160 |
| `CHANGELOG.md` | geändert | +2 |
