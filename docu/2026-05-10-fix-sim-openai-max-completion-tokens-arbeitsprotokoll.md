# 2026-05-10 — Hotfix: OpenAI GPT-5 / o-Series `max_completion_tokens`

## Symptom

Bei Simulation gegen direkten OpenAI-Endpunkt mit `gpt-5.4-mini` brachen alle Agent-Calls mit 400 ab:

```
openai.BadRequestError: Error code: 400 - {'error': {'message':
"Unsupported parameter: 'max_tokens' is not supported with this model.
Use 'max_completion_tokens' instead.", 'type': 'invalid_request_error',
'param': 'max_tokens', 'code': 'unsupported_parameter'}}
```

Pro Agent-Tick mehrere identische 400er → Sim erzeugte null Reaktionen.

Begleitendes BERT-Warning (`BertSdpaSelfAttention …falling back to manual attention`) ist kosmetisches Rauschen vom sentence-transformers-Embedder, kein Crash-Trigger und nicht Teil dieses Slices.

## Root Cause

OpenAI-API-Familie inkonsistent: GPT-5-Familie (`gpt-5*`) sowie Reasoning-Modelle `o1`/`o3`/`o4` haben `max_tokens` deprecated und akzeptieren ausschließlich `max_completion_tokens`. Ältere Modelle (`gpt-4o`, `gpt-4-turbo`, `gpt-3.5-turbo`) und alle nicht-OpenAI-Backends nutzen weiterhin `max_tokens`.

Die drei OASIS-Subprocess-Skripte schickten unkonditional `{"max_tokens": …}` über CAMEL `ModelFactory.create()`:

- `backend/scripts/run_parallel_simulation.py:1179`: `model_cfg = {"max_tokens": runtime_settings["completion_max_tokens"]}`
- `backend/scripts/run_reddit_simulation.py:497`: `{"max_tokens": 8192}`
- `backend/scripts/run_twitter_simulation.py:484`: `{"max_tokens": 8192}`

Der vorhergehende Provider-Awareness-Fix (Commit `33eb10e fix(sim): make CAMEL extra_body provider-aware`) hatte nur `extra_body.think` / `options.num_ctx` provider-aware gemacht, den Token-Key-Schlüsselnamen aber unangetastet gelassen.

## Fix

Spiegelpattern zu `build_camel_extra_body()`:

1. Neuer Helper `uses_max_completion_tokens(model)` in `backend/scripts/_sim_common.py` mit Familie-Heuristik (`gpt-5*`, `o1`/`o3`/`o4` als Standalone oder mit `-`-Suffix).
2. Neuer Builder `build_camel_completion_params(*, model, completion_max_tokens)` liefert exakt einen Schlüssel (`max_completion_tokens` oder `max_tokens`) — niemals beide, da OpenAI unbekannte Parameter strikt ablehnt.
3. Drei Sim-Skripte refaktoriert: alle `{"max_tokens": …}`-Hardcodes durch `build_camel_completion_params(...)` ersetzt.
4. Sanity-Log in `agent_tools.py` liest jetzt beide Keys (`model_cfg.get('max_completion_tokens', model_cfg.get('max_tokens', '?'))`), damit das Diagnose-Print bei GPT-5 nicht `?` zeigt.

## Verifikation

- `uv run pytest tests/scripts/test_sim_common_completion_params.py -v` → **32 passed**
- `uv run pytest tests/scripts/ -x -q` → **60 passed**
- `uv run python -m app.contracts.dump_schemas --check` → 12/12 Schemas drift-frei
- `uv run ruff check scripts/_sim_common.py scripts/run_*_simulation.py scripts/agent_tools.py tests/scripts/test_sim_common_completion_params.py` → All checks passed
- Sanity-Smoke (`build_camel_completion_params(model="gpt-5.4-mini", completion_max_tokens=4096)`) → `{"max_completion_tokens": 4096}`
- Sanity-Smoke (`build_camel_completion_params(model="gpt-4o", completion_max_tokens=8192)`) → `{"max_tokens": 8192}`

## Test-Cover

`backend/tests/scripts/test_sim_common_completion_params.py` (neu, 32 Tests in 5 Klassen):

- `TestUsesMaxCompletionTokensGpt5Family` — 7 GPT-5-Varianten inkl. case-Insensitivität.
- `TestUsesMaxCompletionTokensReasoningModels` — 7 o1/o3/o4-Varianten.
- `TestUsesMaxCompletionTokensLegacyOpenAI` — 5 Legacy-Modelle (`gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`).
- `TestUsesMaxCompletionTokensNonOpenAI` — 8 Non-OpenAI-Backends inkl. Empty-String-Edge.
- `TestBuildCamelCompletionParams` — 5 Builder-Asserts inkl. Single-Key-Garantie.

## Out of Scope

- BERT `attn_implementation="eager"`-Warning (kosmetisch, kommt aus sentence-transformers-Pfad, separater Slice falls überhaupt unser Code-Pfad).
- Hartkodierter `8192`-Default in Reddit/Twitter-Skripten — CLAUDE.md verbietet das nominell für `token_limit` (memory), nicht zwingend für `completion_max_tokens`. Migration auf `Config.LLM_MAX_OUTPUT_TOKENS` als separater Slice nachziehbar.
- CAMEL-Upstream-Patch — der ist durch `camel-oasis==0.2.5`-Hardpin blockiert (siehe CLAUDE.md).
