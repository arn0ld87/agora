# Sub-Slice 10 · DACH-Voice-Constraints (`voice_register` in Persona)

**Layer:** 2 — DACH-Voice + Prompt-Semantik
**Issue:** Closes #167
**Branch:** `feat/layer-2-task-10-dach-voice-register`
**Basis:** `origin/main` @ c7c7eaa

## Was

`voice_register`-Pflichtfeld pro Persona. Vier Werte: `formal-de | neutral-de | technical-de | skeptisch-de`. Pydantic-validiert, LLM-Persona-Prompt erweitert, Auto-Fallback bei fehlendem oder ungültigem Wert.

## Warum

Die OASIS-Persona-Generierung liefert bisher kein steuerbares Sprachregister. Konsequenz: Reports klingen homogen, DACH-Voice-Lint (Task 11) hat keinen Anker. Das `VoiceRegister`-Literal liegt seit Layer-0-Setup in `persona_contract.py:21`, war aber nicht verdrahtet.

## Wie (Edits)

### `backend/app/services/oasis_profile_generator.py`

- Z. 27: `VOICE_REGISTERS = ("formal-de", "neutral-de", "technical-de", "skeptisch-de")` als Modul-Konstante (gespiegelt aus dem Pydantic-Literal).
- Z. 64: `OasisAgentProfile.voice_register: Optional[str] = None`.
- Z. 99/137/163: `to_reddit_format`/`to_twitter_format`/`to_dict` propagieren das Feld nur, wenn gesetzt.
- Z. 345: `OasisAgentProfile(...)`-Konstruktion in `_generate_profile_with_llm` setzt `voice_register=profile_data.get("voice_register")`.
- Z. 583–589: Vor der allgemeinen Validation wird `result["voice_register"]` gegen `VOICE_REGISTERS` geprüft. Bei Miss → `logger.warning(...)`, dann auf `"neutral-de"` gesetzt. Kein Retry, kein Crash.
- Z. 684–686: `_validate_profile_metadata` ergänzt um expliziten `voice_register: invalid value '<x>'`-Eintrag, wenn der Wert nicht passt (für den Fall, dass das Feld extern gesetzt wurde, ohne Fallback zu durchlaufen).
- Z. 836–849 / 881–894: Persona-Prompts (DE und EN, Individual und Group) bekommen das Pflichtfeld plus die vier Werte plus eine knappe Anwendungsregel (Beruf → Register).
- `_rule_based_voice_register(entity_type, profession="")`: Minimal-Heuristik im rule-based-Fallback (Behörde→`formal-de`, Tech→`technical-de`, Aktivismus→`skeptisch-de`, Default→`neutral-de`).

### `backend/app/contracts/persona_contract.py`

- Z. 61: Default von `None` → `"neutral-de"`. Backwards-Compat bleibt erhalten, weil `Optional` belassen wurde — alte Daten ohne Feld fallen weiter durch.

### `backend/tests/contracts/test_persona_quota.py`

- Vier Roundtrip-Cases (einer pro Register) plus negativ-Case (`english-uk` → `ValidationError`).

### `backend/tests/services/test_oasis_voice_register.py` (neu)

- Mock auf `_generate_profile_with_llm`-Pfad: valides Register → landet im Profil.
- Ungültiges Register → Fallback `neutral-de`, `logger.warning` getriggert.
- Fehlender Key → Fallback `neutral-de`.
- `_rule_based_voice_register`-Heuristik liefert für jeden Anker-Typ ein gültiges Register.

### Doku

- `prompts/2026-05-02-voice-register-katalog.md` (neu) — Anker für Prompt-Ingenieure und Auditor, vier Register mit Beispielen und Abgrenzungen.
- `CHANGELOG.md` `[Unreleased] → Changed`-Bullet ergänzt.

### `schemas/persona.schema.json`

- Default-Wert von `null` auf `"neutral-de"` gehoben — direkte Folge der Contract-Änderung, intendiert.

## Akzeptanz-Verifikation

| Kriterium                                                                     | Status |
| ----------------------------------------------------------------------------- | ------ |
| `rg -n "voice_register" oasis_profile_generator.py` ≥6 Treffer                 | ✅ 17 Treffer |
| Pydantic-Roundtrip alle vier Register ohne Fehler                              | ✅      |
| LLM-Antwort ohne `voice_register` → Fallback `neutral-de` + Warning           | ✅      |
| Schema-Dump idempotent (nach Commit `git diff schemas/` clean)                 | ✅      |
| `pytest tests/contracts/ tests/services/test_oasis_voice_register.py` grün     | ✅ 47/47 |
| `pytest -x -q` Volltest                                                        | ⚠ 488 passed; 1 Fail `test_validate_process_uses_configured_entity_cap` ist **vorbestehend** (LLM_API_KEY-Setup-Bug auf origin/main reproduzierbar) |
| `ruff check .`                                                                 | ✅ 33 Fehler — gleich wie origin/main, keine neuen Lint-Schulden |

## Out of Scope

- DACH-Voice-Lint als CI-Check (Task 11, Layer 2) — separater Slice.
- `entity_type`-Mapping-Heuristik bleibt minimal; eine differenzierte Mapping-Tabelle ist Folge-Arbeit, falls die Persona-Verteilung schief läuft.
- Vorbestehender LLM_API_KEY-Bug in `test_ontology_generator.py::test_validate_process_uses_configured_entity_cap` wird in eigenem Slice gefixt (nicht durch Task 10 verursacht).

## Commit

```
feat(persona): voice_register-Pflichtfeld + DACH-Register-Mapping (Sub-Slice 10, Closes #167)
```
