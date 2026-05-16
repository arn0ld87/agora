# Worklog 2026-05-15 — Smoke-Fix Slice 02

**Datum:** 2026-05-15
**Branch:** `feat/smoke-fix-02-ollama-outline` → merged in `feat/smoke-fix-2026-05-15-welle2-epic`
**Layer:** 1 (Backend-Services, Report-Agent)
**Closes:** Befund #2 (Ollama-Fallback liefert leeren Output)

## Problem

Ollama-Fallback mit `kimi-k2.6` liefert nach 70 s Laufzeit leeren JSON-Output bei der Outline-Planung:

```
INFO: LLM chat returned model=kimi-k2.6 finish=stop tokens_out=4096 elapsed=70.2s max_tokens=4096 stream=False
ERROR: Outline planning failed: Invalid JSON format from LLM (len=0; likely truncated).
```

Root-Cause: `max_tokens=4096` ist zu klein für Modelle mit implizitem Thinking-Mode. Der Modell nutzt den gesamten Kontext für interne Reasoning und hat nichts für das finale JSON-Output übrig.

## Fix

1. **`backend/app/utils/llm_client.py`** — neuer optionaler Parameter `force_no_thinking: bool = False` an `chat()` und `chat_json()`. Bei `force_no_thinking=True` UND Ollama-Endpoint wird `extra_body["think"] = False` hart gesetzt (überschreibt das aus `reasoning_effort` abgeleitete `self._think`).
2. **`backend/app/services/report_agent/planning.py`** — `plan_outline()` ruft `chat_json` mit `max_tokens=16384`, `temperature=0.2`, `force_no_thinking=True` auf. Bei `ValueError` mit `"len=0"` oder `"Invalid JSON format from LLM"` wird **einmalig** mit `max_tokens=24576` und `temperature=0.1` retried. Bei zweitem Failure greift der bestehende Default-Fallback (3 Sections).
3. **`backend/app/services/report_agent/prompts.py`** — nur Modul-Docstring-Hinweis, kein Code-Change.
4. **Tests:** `backend/tests/services/test_outline_planning_ollama.py` (NEU, 4 Tests) plus 1 neuer Test in `backend/tests/test_llm_client.py`.

## Tests

Neu:
- `backend/tests/services/test_outline_planning_ollama.py` (4 Tests) — max_tokens-Pass-Through, force_no_thinking-Pass-Through, Retry bei empty Response, Fallback nach zwei Failures
- `backend/tests/test_llm_client.py` erweitert um `test_chat_force_no_thinking_overrides_extra_body_think` plus angepasste Mock-Stubs für `**kwargs`

**Test-Counts:** Backend +5 (4 neu + 1 neu, plus 5 Mock-Stub-Anpassungen) / Frontend 0

## Geänderte Dateien

- `backend/app/utils/llm_client.py` (+13 / -1)
- `backend/app/services/report_agent/planning.py` (+35 / -10)
- `backend/app/services/report_agent/prompts.py` (Docstring only, +1)
- `backend/tests/services/test_outline_planning_ollama.py` (NEU, 151 LOC)
- `backend/tests/test_llm_client.py` (+52 / -3)

## Risiken & Gaps

- Der Retry-Loop fängt bewusst nur `ValueError` (empty/invalid JSON). Netzwerk-Timeouts und andere Exceptions landen direkt im Default-Fallback — gewollt, weil ein Retry mit 24 576 Tokens bei toter Verbindung sinnlos wäre.
- `force_no_thinking=True` greift nur bei `_is_ollama()` (Substring-Check auf `11434`). Custom-Port-Deployments oder Ollama-Cloud-Proxy verlieren die Wirkung — pre-existing, nicht durch diesen Slice eingeführt.
- `max_tokens=16384` ist konservativ; für sehr große Seeds (>1000 Chunks) ggf. zu knapp. Eval-Snapshot zeigt ob Erhöhung nötig ist.

## Verifikations-Gate

```bash
cd backend && uv run pytest tests/services/test_outline_planning_ollama.py tests/test_llm_client.py -v
pytest -x -q  # volle Suite
ruff check app/ tests/
mypy app
```

Alle grün. Smoke-Test mit `kimi-k2.6` lokal 2× durchlaufen, leerer Output tritt nicht mehr auf.

## Slice-Commit-Hash

Siehe Branch-History `feat/smoke-fix-2026-05-15-welle2-epic`.
