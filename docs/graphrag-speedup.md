# Agora GraphRAG Build Speedup

Konkrete Schritte, um die GraphRAG-Build-Phase von „mehrere Minuten pro Dokument" auf „unter einer Minute" zu bringen. Getestet gegen Ollama Cloud.

Ziel-Repo: `nikmcfly/Agora`-Fork (oder kompatibel).

---

## Ausgangslage & Symptome

- Build-Phase zerlegt Dokument in viele kleine Chunks (`chunk_size=500`) und schickt sie **sequenziell** an das LLM für NER/RE-Extraktion.
- Pro Chunk 20–70 s Netzwerk-/Inferenzlatenz gegen Ollama Cloud.
- Ergebnis: 11 Chunks × ~30 s = 5–7 Min für ein 4 000-Zeichen-Dokument.

## Hebel (4 unabhängige Stellschrauben)

### 1. Modellwahl

`ministral-3:14b-cloud` ist zu schwach (Tool-Calling-Inkompatibilitäten, 400er). `gemma4:31b-cloud` ist langsam und liefert JSON teils als verschachtelte Dicts (`{"value": N, "reasoning": "..."}`).

**Empfehlung für Build + Report:** `qwen3-coder-next:cloud`
- Coder-Tuning → striktes JSON
- Tool-Calling offiziell stabil
- Thinking via API-Parameter deaktivierbar
- Gute deutsche Ausgabe

Setzen in `.env`:
```env
LLM_MODEL_NAME=qwen3-coder-next:cloud
OPENAI_MODEL_NAME=qwen3-coder-next:cloud
```

### 2. Thinking per API-Parameter abschalten

Ollama-Cloud-Modelle mit Reasoning (Qwen3-Familie, GPT-OSS, DeepSeek-R1) senden Think-Blöcke die Zeit kosten. Top-Level-Feld `think: false` im `extra_body` unterdrückt das.

`.env`:
```env
OLLAMA_THINKING=false
```

`backend/app/utils/llm_client.py` — im Konstruktor:
```python
self._think = os.environ.get('OLLAMA_THINKING', 'false').lower() in ('1', 'true', 'yes')
```

Im `chat()`-Aufruf, wenn `_is_ollama()`:
```python
if self._is_ollama():
    extra_body: Dict[str, Any] = {}
    if self._num_ctx:
        extra_body["options"] = {"num_ctx": self._num_ctx}
    extra_body["think"] = self._think
    kwargs["extra_body"] = extra_body
```

Ein `<think>…</think>`-Stripper als Fallback ist bereits in `chat()` verbaut — damit werden auch leere Thinking-Blöcke von Gemma 4 etc. abgefangen.

### 3. JSON-Mode abschalten

`response_format={"type":"json_object"}` bremst Ollama-Cloud-Modelle massiv und wird nicht von allen sauber unterstützt.

`.env`:
```env
LLM_DISABLE_JSON_MODE=true
```

`llm_client.py` prüft das bereits in `chat_json()`:
```python
disable_json_mode = os.environ.get('LLM_DISABLE_JSON_MODE', '').lower() in ('1', 'true', 'yes')
response = self.chat(
    ...,
    response_format=None if disable_json_mode else {"type": "json_object"}
)
```

Der Markdown-Fence-Stripper in `chat_json()` räumt ` ```json `-Blöcke vor dem `json.loads()` weg.

### 4. Chunk-Größe erhöhen + Parallelisierung

Der eigentliche Gamechanger. Zwei Änderungen:

**4a) Chunk-Größe von 500 → 1500** (weniger LLM-Calls bei identischer Qualität für NER).

`backend/app/config.py`:
```python
DEFAULT_CHUNK_SIZE = int(os.environ.get('GRAPH_CHUNK_SIZE', '1500'))
DEFAULT_CHUNK_OVERLAP = int(os.environ.get('GRAPH_CHUNK_OVERLAP', '150'))
GRAPH_PARALLEL_CHUNKS = int(os.environ.get('GRAPH_PARALLEL_CHUNKS', '4'))
```

**4b) `add_text_batches` parallelisieren** mit `ThreadPoolExecutor`. Neo4j-Driver und OpenAI-SDK sind thread-safe (jeder `storage.add_text`-Aufruf öffnet eine eigene `session`).

`backend/app/services/graph_builder.py`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def add_text_batches(self, graph_id, chunks, batch_size=3, progress_callback=None):
    total_chunks = len(chunks)
    if total_chunks == 0:
        return []

    max_workers = max(1, min(Config.GRAPH_PARALLEL_CHUNKS, total_chunks))
    logger.info(f"[graph_build] Starting: {total_chunks} chunks, parallel workers={max_workers}")

    episode_uuids: List[Optional[str]] = [None] * total_chunks

    def _process(idx: int, chunk: str) -> str:
        t0 = time.time()
        try:
            episode_id = self.storage.add_text(graph_id, chunk)
            logger.info(f"[graph_build] Chunk {idx + 1}/{total_chunks} done in {time.time()-t0:.1f}s")
            return episode_id
        except Exception as e:
            logger.error(f"[graph_build] Chunk {idx + 1}/{total_chunks} FAILED after {time.time()-t0:.1f}s: {e}")
            raise

    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process, idx, chunk): idx for idx, chunk in enumerate(chunks)}
        for future in as_completed(futures):
            idx = futures[future]
            episode_uuids[idx] = future.result()
            completed += 1
            if progress_callback:
                progress_callback(
                    f"Processed {completed}/{total_chunks} chunks...",
                    completed / total_chunks,
                )

    return [uuid for uuid in episode_uuids if uuid is not None]
```

`.env`:
```env
GRAPH_CHUNK_SIZE=1500
GRAPH_CHUNK_OVERLAP=150
GRAPH_PARALLEL_CHUNKS=4
```

Parallelität bei Ollama Cloud: 4 ist der Sweet Spot. Höhere Werte triggern gelegentlich Rate-Limits.

---

## Wichtige Fallstricke

### Docker-Restart reicht NICHT

`docker compose restart agora` **lädt weder `.env` neu noch aktualisiert es den Image-Code**. Der Container behält Env-Vars aus dem Startzeitpunkt und bakt den Quellcode beim `build` ein.

Nach **Env-Änderung**:
```bash
docker compose up -d --force-recreate --no-deps agora
```

Nach **Code-Änderung** (z. B. `graph_builder.py` oder `llm_client.py`):
```bash
docker compose build agora
docker compose up -d --force-recreate --no-deps agora
```

Verifizieren:
```bash
docker exec agora env | grep -E "LLM_MODEL|GRAPH_"
docker exec agora grep -c "ThreadPoolExecutor" /app/backend/app/services/graph_builder.py
```

### Simulation friert Modell ein

Die `simulation_config.json` pro Simulation enthält `llm_model` aus dem Zeitpunkt der Vorbereitung. Wechselst du nach der Agent-Persona-Generierung das Modell in `.env`, läuft die Simulation weiter mit dem alten Wert.

Patchen:
```bash
docker exec agora python3 -c "
import json
p='/app/backend/uploads/simulations/<sim_id>/simulation_config.json'
d=json.load(open(p)); d['llm_model']='qwen3-coder-next:cloud'
json.dump(d, open(p,'w'), indent=2)
"
```

Danach laufenden Subprozess killen und Simulation in der UI neu starten:
```bash
docker exec agora ps -ef | grep run_parallel_simulation
docker exec agora kill -9 <PID>
```

Falls `run_state.json` auf `"runner_status": "failed"` steht, auf `"ready"` zurücksetzen — sonst reagiert der Start-Button nicht.

### Gemma-4-spezifischer Bug

Gemma 4 verpackt manchmal Skalare als `{"value": N, "reasoning": "..."}` in seinen JSON-Output. Im `simulation_config_generator.py` defensiv parsen mit einem `_coerce_int()`-Helper:

```python
@staticmethod
def _coerce_int(value, default):
    if isinstance(value, dict):
        for key in ("value", "val", "n", "amount", "count"):
            if key in value:
                value = value[key]
                break
        else:
            return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
```

Bei Wechsel auf Qwen3-Coder tritt der Fehler nicht mehr auf — die Coercion bleibt aber als Safety-Net nützlich.

---

## Benchmark

| Konfiguration | Chunks | Dauer |
|---|---|---|
| `ministral-3:14b` + chunk 500 + seriell | 11 | 5–10 min (+ 400er-Errors) |
| `qwen3-coder-next` + chunk 500 + seriell | 11 | ~4–5 min |
| `qwen3-coder-next` + chunk 1500 + 4× parallel | ~3 | **unter 1 min** |

---

## Checkliste für den nachmachenden Agenten

1. `.env` anpassen: `LLM_MODEL_NAME`, `OPENAI_MODEL_NAME`, `OLLAMA_THINKING=false`, `LLM_DISABLE_JSON_MODE=true`, `GRAPH_CHUNK_SIZE=1500`, `GRAPH_PARALLEL_CHUNKS=4`.
2. `llm_client.py`: `think`-Flag in `extra_body` einbauen.
3. `config.py`: `GRAPH_CHUNK_SIZE`, `GRAPH_CHUNK_OVERLAP`, `GRAPH_PARALLEL_CHUNKS` aus Env.
4. `graph_builder.py`: `add_text_batches` auf `ThreadPoolExecutor` umstellen.
5. `simulation_config_generator.py`: `_coerce_int`/`_coerce_int_list` gegen Dict-Wrapping (optional, für Gemma-Fallback).
6. `docker compose build agora && docker compose up -d --force-recreate --no-deps agora`.
7. Container-Env prüfen: `docker exec agora env | grep GRAPH_`.
8. Neuen Build in der UI starten und Log beobachten: `docker logs -f agora | grep graph_build`.
