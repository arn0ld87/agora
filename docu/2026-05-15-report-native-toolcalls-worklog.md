# Slice — Native function-calling für ReACT-Report

- **Branch:** `feat/task-report-native-toolcalls`
- **Worktree:** `/private/tmp/agora-report-native-toolcalls/`
- **Base:** `origin/main` @ `6e46771`
- **Started:** 2026-05-15
- **Lead:** Opus 4.7 (Cross-Layer-Entscheidung), Implementation via `agora-refactor-worker`, Tests via `agora-test-worker`
- **Schließt:** kein offenes Issue (Bug aus Live-Run 2026-05-15 03:51–03:55, Report `report_a3c014f77ed3` / `report_cb521d2d493f`)

## Root Cause

`backend/app/services/report_agent/workflow.py:163,173` ruft `agent.llm.chat(...)` und
parst Tool-Calls per Regex aus dem Antwort-Text (`<tool_call>...</tool_call>`).
`LLMClient.chat` (`backend/app/utils/llm_client.py:355-502`) hat **keinen** `tools=`
Parameter — Tool-Use läuft ausschließlich über Prompt-Engineering + XML-Parsing.

Beobachteter Bug: `deepseek-v4-flash:cloud` emittiert narrativen Selbstkommentar
("Ich rufe nun das erste Tool auf"), aber **keinen** `<tool_call>`-Block. 5 leere
Iterationen → Force-Generate → `confidence=high`-Claims ohne Evidence →
`EvidenceMapModel`-Validator killt den gesamten Report.

## Ziel

Native function-calling auf der `LLMClient`-Ebene + ReACT-Loop nutzt
`message.tool_calls` statt Text-Regex. XML-Pfad bleibt als Legacy-Fallback hinter
Feature-Flag bestehen, damit Modelle ohne Tool-Use-Support nicht abreißen.

## Provider-Smoke-Matrix (Akzeptanz)

| Provider | Modell | tool_calls native | Notiz |
|---|---|---|---|
| Ollama-lokal | qwen3:8b | TBD | TDD-Pflicht |
| Ollama-Cloud | gpt-oss | TBD | TDD-Pflicht |
| Ollama-Cloud | qwen3-coder-next | TBD | TDD-Pflicht |
| Ollama-Cloud | deepseek-v4-flash | TBD | erwartet: **nicht** native — Fallback-Pfad |
| Anthropic | claude-sonnet-4-6 | TBD | TDD-Pflicht |

## Slices (intern)

- B-1 — `LLMClient.chat_with_tools` Vertrag + Provider-Adapter (Opus-Lead)
- B-2 — Tools als OpenAI-Schema deklarieren (`tools.py`)
- B-3 — ReACT-Loop auf native umstellen, XML als Fallback
- B-4 — Provider-Smoke-Matrix als parametrisierter Test
- B-5 — Frontend: kein Touch (Backend-only)

## Verboten

- ADR-0002 (Evidence-Gating) anfassen — Validator bleibt streng
- Legacy-XML-Pfad löschen — bleibt Fallback hinter Flag
- Default-Flag auf `xml` lassen — Default ist `native` nach Smoke-Grün

## Verifikations-Gates

```bash
cd /private/tmp/agora-report-native-toolcalls/backend
uv run pytest -x -q tests/services/report_agent/
uv run pytest tests/services/report_agent/test_native_toolcalls.py -v
uv run ruff check app/ tests/
uv run mypy app
```

## Status

- [x] Worktree angelegt
- [x] B-1 Test-Scaffold RED → commit `ca18303`
- [x] B-2 Tools-Schema (`get_openai_tools_schema`) → commit `a465e62`
- [x] B-3 `LLMClient.chat_with_tools` + Streaming-Pfad + E2E-Stub → commit `a465e62`
- [x] B-4 ReACT-Loop + chat()-Loop migriert (native/xml Flag) → commit `da8dc89`
- [x] B-5 `_get_openai_tools_schema()` in agent.py → commit `da8dc89`
- [x] chore: `REPORT_TOOLCALL_MODE` Feature-Flag default native → commit `70a66ae`
- [x] Gates grün (9/9 neue Tests, 2084 bestehende bestehen, 0 neue ruff/mypy-Fehler)
- [ ] Provider-Smoke-Matrix Live-Tests (Follow-up nach Code-Review)
- [ ] PR eröffnet (Push-Verbot laut Brief — wartet auf Lead-Freigabe)

## Implementierungs-Notizen

### Abweichungen vom Brief

- `tool_validation.py` und `tool_execution.py` liegen in `app/services/` (nicht `report_agent/`) — korrekte Pfade via `rg`-Verifikation gefunden.
- `TypedDict`-Import für `ToolCallResponse`/`ToolCallItem` inline im Modul-Scope nach der Klasse (kein separates `llm_types.py` nötig, da Umfang überschaubar).
- `e2e_stub_chat_with_tools_response` importiert `ToolCallResponse`/`ToolCallItem` lazy aus `llm_client` (zirkulären Import vermieden).

### Streaming-Reassembly

Der Akkumulator in `_accumulate_streaming_tool_calls()` verwaltet einen Index-basierten dict (`tc_acc`) und konkateniert `function.arguments`-Deltas. Das entspricht exakt dem OpenAI-Streaming-Protokoll für parallel tool_calls (mehrere Indizes möglich).

### Soft-Fallback

Wenn `chat_with_tools` `tool_calls=[]` zurückgibt und `content` einen `<tool_call>`-Block enthält, ruft der ReACT-Loop einmalig `agent._parse_tool_calls(response)` auf. Damit funktioniert der Legacy-Pfad als Sicherheitsnetz ohne explizite Flag-Umschaltung.
