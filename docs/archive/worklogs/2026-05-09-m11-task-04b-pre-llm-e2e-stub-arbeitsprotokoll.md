# Arbeitsprotokoll: M11.4b-pre — LLM-Stub-Modus für E2E-Smokes

**Datum:** 2026-05-09
**Branch:** `feat/m11-task-04b-pre-llm-e2e-stub`
**Vertrag:** `docs/2026-05-09-m11-phase7-playwright-smokes-cut-analysis.md` Sektion 4.2 + 5

---

## Geänderte Dateien

| Datei | Typ | Zweck | LOC-Delta |
|---|---|---|---|
| `backend/app/utils/llm_e2e_stub.py` | NEU | Deterministischer Stub-Pfad für CI-Smokes | +175 |
| `backend/app/utils/llm_client.py` | PATCH | Früher Stub-Branch vor LLM-Call in `chat_json` | +18 |
| `backend/tests/test_llm_e2e_stub.py` | NEU | Pinning-Tests (12 Testfälle) | +195 |

---

## Was geändert wurde und warum

### `llm_e2e_stub.py`

- `_eleven_required_sections()`: Liest 11 Pflichtabschnittsnamen aus `tests/eval/snapshots/output-contract-required-sections.txt` — der Snapshot ist Single Source of Truth (M11.8b). Bei fehlender Datei: `ImportError` mit erklärender Message.
- `_is_report_v3_schema()`: Heuristik erkennt ReportV3-JSON-Schema an title/properties-Überlappung/required-Feld.
- `_stub_report_v3()`: Deterministisches, vollständiges ReportV3-Objekt mit allen 11 Pflichtfeldern, das `ReportV3.model_validate()` ohne Fehler besteht.
- `_STUB_TOOL_RETURNS`: Deterministischer Return für die vier registrierten Tools (`insight_forge`, `panorama_search`, `quick_search`, `interview_agents`) aus `report_agent/tools.py`. Kein fünfter Tool — `web_search`/`fetch_url` sind nur optional wenn `agent.web_tools.is_available()`.
- `e2e_stub_response()`: Entscheidungslogik: ReACT-Tool → Tool-Return; ReportV3-Schema → Stub-Report; Sonst → generischer Fallback.
- Kein I/O nach Modul-Import, kein Sleep, kein Random, kein `print()`.

### `llm_client.py` Patch

- Früher Branch ganz oben in `chat_json`, vor `disable_json_mode`-Check, vor allen LLM-Calls, vor Cache, vor Retry.
- Aktivierung nur via `os.environ.get("AGORA_E2E_LLM_MODE") == "stub"`.
- Logger-Call via `logger.info(...)` (gleicher Logger wie umgebender Code, kein `print()`).
- Schema-Normalisierung: Pydantic-Klasse → `model_json_schema()` → dict vor Übergabe an Stub.

### Tests

12 Testfälle in 5 Klassen:
1. `TestStubReturnsAllElevenRequiredSections` (2 Tests): Snapshot liefert 11, Stub-Response hat alle 11 ReportV3-Felder.
2. `TestStubValidatesAgainstReportV3DTO` (3 Tests): `model_validate()` passiert, schema=None-Fallback, Pydantic-dict-Schema.
3. `TestStubInactiveWithoutEnv` (1 Test): Env nicht gesetzt → Stub-Branch nicht betreten (kein `importlib.reload`, kein Config-State-Leak).
4. `TestStubActiveWithEnv` (1 Test): Env gesetzt → `OpenAI.chat.completions.create` nicht aufgerufen, Ergebnis valides ReportV3.
5. `TestStubReACTToolReturnsDeterministic` (5 Tests): 4 registrierte Tools + 1 unbekannter → generischer Fallback; bytewise idempotent.

---

## Akzeptanz-Checks

1. Import + Contract-Sanity: **OK**
2. Stub-Antwort valides ReportV3: **OK**
3. Schema-Drift: **Kein Drift** (git diff --exit-code schemas/ clean)
4. Neue Tests: **12/12 grün**
5. Volltest Backend: **1681 passed, 9 skipped** (vorher 1669 + 12 neu = 1681)
6. Ruff + MyPy: **Ruff: All checks passed / MyPy: no issues in 132 files**

---

## Self-Review

- **Layer-0-clean:** Ja — kein Schema-Dump-Touch, kein Schreiben in `app/contracts/`. Nur Lesen aus `app.contracts.report_v3` für DTO-Konformität.
- **Wording-Glossar-clean:** Ja — Stub-Antworten sind technische Daten, keine Marketing-Phrasen. Keine verbotenen Terme (`prediction`, `rehearsal`, `god's eye view` etc.).
- **`print()`-frei:** Ja — ausschließlich `logger.info()`.
- **Stub inert ohne Env:** Ja — `os.environ.get("AGORA_E2E_LLM_MODE") == "stub"` ist der einzige Aktivierungspfad. Modul wird ohne Env-Var nicht importiert.
- **Test-Isolation:** Test `TestStubActiveWithEnv` nutzt `monkeypatch.setenv` (wird nach Test automatisch rückgängig gemacht) + `patch("app.utils.llm_client.OpenAI")`. Kein `importlib.reload`, keine direkten `Config`-Attribut-Mutationen. Ursprüngliche Version verursachte Test-Kontamination — korrigiert.

---

## Followup auf Gemini-Review PR #341

Adressiert nach Gemini-MEDIUM-Findings (2026-05-09):

- **Finding 1 (PEP-8 Imports):** Lokale `import re`, `import json`, `import pathlib` aus Funktionskörpern entfernt; alle drei als Modul-Top-Level-Imports in `llm_e2e_stub.py` verschoben.
- **Finding 2 (`_STUB_TOOL_RETURNS` als dict):** `dict[str, str]`-JSON-Strings durch typisierte `dict[str, dict[str, Any]]`-Literal ersetzt; `_STUB_TOOL_DEFAULT` analog auf `dict[str, Any]` umgestellt.
- **Finding 3 (Tool-Call-Regex robust):** Fragiles `r'<tool_call>\s*\{[^}]*"name"...'` durch `r"<tool_call>\s*(\{.*?\})\s*</tool_call>"` mit `re.DOTALL` ersetzt; Match-JSON via `json.loads` geparst, dann `name` ausgelesen — funktioniert auch bei `{"parameters":{}, "name": "x"}`.
- **Finding 4 (Cleanup `_get_tool_response`):** Tool-Return-Dispatch in `e2e_stub_response` reduziert auf `_STUB_TOOL_RETURNS.get(tool_name, _STUB_TOOL_DEFAULT)` — kein `json.loads`, kein `dict()`-Cast, kein `# type: ignore`.
- **Finding 5 (Test-Bug):** `test_stub_passes_pydantic_class_as_schema` übergibt jetzt `schema=ReportV3` (Klasse, nicht `None`) und validiert die Antwort via `ReportV3.model_validate(resp)`.
- **status.md-Sync:** `bash scripts/sync-status.sh` aktualisiert Backend-Test-Count 1683 → 1695 (weitere Tests seit letztem Sync zugekommen); `--check` bestätigt kein Drift.

## Followup-Risiken (Gemini-Vorausblick)

1. **ReACT-Erkennung fragil:** `_detect_react_tool_call` parst `<tool_call>` via Regex — könnte bei veränderten Prompt-Templates false-negative ergeben. Für M11.4b (Upload+Graph-Smoke) reicht es, da der ReACT-Loop im Smoke-Pfad nicht aktiv ist. Falls M11.4c (Minimalreport-Smoke) den ReACT-Pfad triggert, sollte der Pattern erweitert werden.
2. **Stub gibt 1 Persona zurück** (`MIN_PERSONA_TABLE_ROWS = 50` in contract_constants). Für M11.4c-Assertion "Persona-Tabelle ≥ 50 Zeilen" muss der Stub erweitert werden (50 Stub-Personas). Das ist bewusst für M11.4c separiert.
3. **`chat()`-Methode ohne Stub:** Der Branch ist nur in `chat_json` eingezogen. Wenn Smoke-Tests `chat()` direkt aufrufen, müssen sie anders isoliert werden. Für den aktuellen Scope (ReportV3-Generation via `chat_json`) korrekt.
4. **Optional Web-Tools (`web_search`, `fetch_url`):** Im Stub nicht implementiert, da sie nur optional sind. Wenn `TAVILY_API_KEY` in CI gesetzt wird, könnten echte Web-Calls entstehen — Smoke-CI muss sicherstellen, dass `TAVILY_API_KEY` leer ist oder `web_tools.is_available()` false bleibt.
