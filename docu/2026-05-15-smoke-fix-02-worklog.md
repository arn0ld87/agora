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

1. **`backend/app/utils/llm_client.py`** — neue Konstante `OUTLINE_PLANNING_MAX_TOKENS = 16384` für Outline-Steps, unabhängig vom Provider.
2. **`backend/app/services/report_agent/planning.py`** — `plan_outline()` nutzt `max_tokens=16384` statt global-konfig, explizit `force_no_thinking=True` für Ollama-Anfragen.
3. **`backend/app/services/report_agent/prompts.py`** — Retry-Loop hinzugefügt: falls JSON-Output `len=0`, bis zu 3× erneut versuchen mit `max_tokens *= 1.2`.
4. **Test:** `backend/tests/services/test_outline_planning_ollama.py` (NEU) — Smoke-Test mit Ollama-Mock, prüft dass `len(outline) > 0` auch bei lange Laufzeit.

## Tests

Neu: 
- `backend/tests/services/test_outline_planning_ollama.py` (3 Tests) — Outline-Robustness mit Ollama-Parametern
- `backend/tests/test_llm_client.py` erweitert um 2 Tests für `OUTLINE_PLANNING_MAX_TOKENS`

Betroffene bestehende Tests laufen grün nach Anpassung der erwarteten `max_tokens`-Assertion.

**Test-Counts:** Backend +5 / Frontend 0

## Geänderte Dateien

- `backend/app/utils/llm_client.py` (+12 LOC)
- `backend/app/services/report_agent/planning.py` (+18 LOC)
- `backend/app/services/report_agent/prompts.py` (+25 LOC, Retry-Logik)
- `backend/tests/services/test_outline_planning_ollama.py` (+67 LOC, NEU)
- `backend/tests/test_llm_client.py` (+8 LOC)

## Risiken & Gaps

- Retry-Loop könnte bei LLM-Fehler (z. B. Netzwerk) hängen — Timeout ist auf 5 min Gesamtlaufzeit pro `plan_outline()` begrenzt.
- `force_no_thinking=True` ist Ollama-spezifisch; andere Provider ignorieren den Header. Kein Regressionsrisiko.
- `OUTLINE_PLANNING_MAX_TOKENS = 16384` ist ggf. für sehr große Seeds (>1000 Chunks) noch knapp — Eval-Snapshot sollte aufzeigen ob Erhöhung nötig ist.

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
