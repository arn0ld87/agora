# Sub-Slice 05 — `chat_json` auf strict-Schema-Mode — Arbeitsprotokoll

**Datum:** 2026-05-02
**Branch:** `feat/layer-1-task-05-chat-json-strict`
**Layer:** 1 (Backend-Hardening)
**Aufwand:** M

---

## Was geändert

### `backend/app/utils/llm_client.py`

| Bereich | Alt | Neu |
|---|---|---|
| Imports (Z. 10–12) | `from typing import Optional, Dict, Any, List` + `from openai import OpenAI` | `+ Type, Union` + `from pydantic import BaseModel` |
| Module-Level (Z. 18–27) | nur `logger` | `+ JsonSchemaLike = Union[Type[BaseModel], Dict[str, Any]]` + `_STRICT_UNSUPPORTED_HINTS` Tuple |
| Neue Methode `_maybe_validate` (Z. 263–282) | nicht vorhanden | Validiert `parsed` gegen Pydantic-Modell via `model_validate().model_dump(mode="json")`; Dict-Schema wird durchgereicht |
| `chat_json` Signatur (Z. 284–291) | `(self, messages, temperature, max_tokens)` | `+ schema: Optional[JsonSchemaLike] = None, schema_name: str = "structured_response"` |
| `chat_json` Body: INFO-Log | nicht vorhanden | Log mit schema-Klassen-Name + schema_name wenn schema gesetzt (Z. 319–325) |
| `chat_json` Body: response_format-Aufbau | immer `{"type": "json_object"}` oder `None` | dreizweigig: `None` bei disable_json_mode, strict json_schema bei schema, json_object als Legacy (Z. 327–345) |
| `chat_json` Body: Chat-Aufruf | einfacher Aufruf | Strict-Pfad mit try/except: bei Provider-Unsupported-Fehler Fallback auf json_object + Warn-Log (Z. 347–381) |
| `chat_json` Body: Parse + Validate | `return json.loads(...)` | `parsed = json.loads(...); return self._maybe_validate(parsed, schema)` (Z. 389–415) |

### Warum

`LLM_DISABLE_JSON_MODE=true` in der .env zeigt, dass der echte Provider kein json_object unterstützt. Trotzdem müssen Caller, die ein Pydantic-Schema übergeben, sicherstellen, dass das geparste Dict schema-konform ist. Mit dem neuen `schema`-Parameter wird:
1. Bei strict-fähigen Providern eine strukturierte Anfrage gestellt (`json_schema`-Format).
2. Bei nicht-unterstützenden Providern automatisch auf `json_object` gefallen, mit Warn-Log.
3. Das Ergebnis gegen das Pydantic-Modell validiert — unabhängig davon, welcher Pfad genommen wurde.

Dies reduziert Schema-Drift zwischen LLM-Output und Pydantic-Contracts (Layer-1-Ziel).

---

## Tests

Neue Datei: `backend/tests/test_llm_client.py` — 6 Tests, alle Mock-only.

| Test | Prüft |
|---|---|
| `test_chat_json_legacy_no_schema_keeps_json_object` | Ohne schema bleibt `{"type": "json_object"}` |
| `test_chat_json_strict_schema_uses_json_schema_response_format` | Mit Pydantic-Schema: type=json_schema, strict=True, korrekter schema_name |
| `test_chat_json_strict_validates_against_pydantic` | Valider Response → korrekte Typen; invalider Response → ValidationError propagiert |
| `test_chat_json_strict_falls_back_on_unsupported` | Provider-Exception mit "unknown response_format" → Fallback auf json_object, Warn-Log, Pydantic-Validation trotzdem |
| `test_chat_json_disable_json_mode_skips_both` | LLM_DISABLE_JSON_MODE=true → response_format=None |
| `test_chat_json_dict_schema_no_server_validation` | Dict-Schema → json_schema-Format, kein Pydantic-Re-Check |

### Echter pytest-Output

```
tests/test_llm_client.py::TestChatJsonLegacy::test_chat_json_legacy_no_schema_keeps_json_object PASSED
tests/test_llm_client.py::TestChatJsonStrictSchema::test_chat_json_strict_schema_uses_json_schema_response_format PASSED
tests/test_llm_client.py::TestChatJsonStrictSchema::test_chat_json_strict_validates_against_pydantic PASSED
tests/test_llm_client.py::TestChatJsonStrictSchema::test_chat_json_strict_falls_back_on_unsupported PASSED
tests/test_llm_client.py::TestChatJsonStrictSchema::test_chat_json_disable_json_mode_skips_both PASSED
tests/test_llm_client.py::TestChatJsonStrictSchema::test_chat_json_dict_schema_no_server_validation PASSED
6 passed in 0.42s
```

Volltest: `929 passed, 2 skipped` (event_bus-Timing-Flap ist pre-existing, isoliert grün).

---

## Verbleibende Lücken

- **Keine Caller umgestellt:** `report_agent.py`, `graph_tools.py`, `ner_extractor.py`, `ontology_generator.py` rufen `chat_json(...)` weiterhin ohne `schema` auf. Die Backwards-Compat ist zwingend — Caller-Migration ist separater Slice pro Caller.
- **mypy-Fehler in `chat`-Methode** (Z. 172/196: `llm_call_with_retry`-kwargs-Typing) sind pre-existing und nicht durch diesen Slice eingeführt.
- **Dict-Schema ohne Server-Validation:** Wenn `schema` ein plain JSON-Schema-Dict ist, wird das LLM-Ergebnis nicht server-seitig re-validiert. Pydantic-Validation läuft nur bei Pydantic-Modell-Klassen.
