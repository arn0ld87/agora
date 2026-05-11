# Arbeitsprotokoll: M11.8a — Section-Cap raus + required_sections-Variable

**Datum:** 2026-05-09
**Branch:** feat/m11-8a-prompt-section-cap
**Worktree:** /Volumes/T7/Projekte/.agora-m11-8a

---

## Slice

M11.8a — Section-Cap raus + required_sections-Variable

## Ziel + Root-Cause

Externe Agora-Output-Bewertung (5,8/10, `docs/2026-05-09-output-vertrag-bewertung-evidence-quality.md`) zeigt: Das Report-LLM liefert nur 2–5 Sections statt der vom User-Prompt geforderten 11 Pflichtabschnitte.

Root-Cause: `backend/app/services/report_prompts.py` Zeilen 42–46 (vor dem Fix) enthielten einen harten `[Section Number Limit]`-Block:
```
- Minimum 2 sections, maximum 5 sections
```
Dieser Cap überstimmte strukturell jeden User-Prompt. Zusätzlich hatte das `PLAN_USER_PROMPT_TEMPLATE` keine `{required_sections}`-Variable, sodass die gewünschten 11 DACH-Abschnitte dem LLM nie kommuniziert wurden.

## Geänderte Dateien

| Datei | Änderungen |
|---|---|
| `backend/app/services/report_prompts.py` | `[Section Number Limit]` → `[Section Requirements]`; Note-Satz aktualisiert; `{required_sections}` in `PLAN_USER_PROMPT_TEMPLATE`; `DEFAULT_REPORT_SECTIONS` (11-Einträge) + `format_required_sections()` neu; `__all__` ergänzt |
| `backend/app/services/report_agent/planning.py` | Import der neuen Symbole; `required_sections: Optional[list[tuple[str, str]]] = None` Parameter; harter `2 <= len <= 5`-Check entfernt; `required_sections` an `.format(...)` durchgereicht |
| `backend/app/services/report_agent/agent.py` | `plan_outline()`-Wrapper: `required_sections` als optionaler Parameter ergänzt |
| `backend/tests/test_report_prompts.py` | `{required_sections}` in PROMPT_SPECS; `__all__`-Test angepasst; Section-Cap-Test umgeschrieben; `.format()`-Call ergänzt; 2 neue Tests (`test_default_report_sections_has_eleven_entries`, `test_format_required_sections_renders_numbered_markdown`) |
| `CHANGELOG.md` | `[Unreleased] ### Changed`-Eintrag für M11.8a |

## Architektur-Entscheidung

`required_sections` als optionaler Parameter mit `DEFAULT_REPORT_SECTIONS`-Fallback:
- Backward-Compat: Alle bestehenden Aufrufer (Workflow, Tests) übergeben `required_sections=None` → Default-Pfad, kein Verhaltens-Diff für Legacy-Calls.
- Erweiterungspunkt: Frontend kann in einem Folge-Slice eine eigene `required_sections`-Liste durchreichen (z. B. projektspezifische Abschnitte).
- `DEFAULT_REPORT_SECTIONS` als `list[tuple[str, str]]` — kein Pydantic-Modell, da reine Prompt-Konstruktions-Hilfsdaten ohne Serialisierungs-Anforderung.

## Out-of-Scope (explizit nicht angefasst)

- **M11.8c:** ReportV3-Pydantic-DTOs — kein neues DTO.
- **M11.8d:** JSON-Schema-Forced-Output — kein Strict-Mode-Umbau.
- **M11.8e:** Quote-Markup — keine Änderungen an Section-Generierung.
- **Frontend:** `required_sections` aus User-Prompt-Frontend ist Zukunfts-Slice. Keine `*.vue`-Dateien angefasst.
- **Layer 0:** Keine Pydantic-Contract-Änderungen. Schema-Dump idempotent.

## Verifikation

```
ruff check app/ tests/   → All checks passed!
mypy app                 → Success: no issues found in 129 source files
pytest tests/test_report_prompts.py -x -v  → 53 passed
pytest tests/services/test_report_agent_outline.py -x -v  → 4 passed
pytest -x -q             → 1600 passed, 9 skipped
python scripts/check_voice.py  → Voice-Lint: OK
git diff --exit-code schemas/  → Schemas clean (kein Drift)
grep -c "minimum 2 sections|maximum 5 sections" report_prompts.py  → 0 (Cap weg)
grep -c "required_sections" report_prompts.py  → 6 (>= 2 erwartet)
grep -c "DEFAULT_REPORT_SECTIONS" report_prompts.py planning.py  → 2 (def + import)
```
