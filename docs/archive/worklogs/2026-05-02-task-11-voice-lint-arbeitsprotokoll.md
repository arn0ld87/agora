# Arbeitsprotokoll: Sub-Slice 11 — Voice-Lint als CI-Check

**Datum:** 2026-05-02
**Branch:** `feat/layer-2-task-11-voice-lint-ci`
**Issue:** Closes #168
**Layer:** 2 (DACH-Voice + Prompt-Semantik)

---

## Was

Neues CLI-Lint-Skript `backend/scripts/check_voice.py`, das verbotene
Forecast- und US-Marketing-Phrasen in Report-Services und Prompts erkennt.
Dazu Pytest-Tests in `backend/tests/scripts/test_check_voice.py` und
der neue CI-Job `voice-lint` in `.github/workflows/contract-gates.yml`.

---

## Warum

Layer 2, Tasks 09+10 haben Prompt-Semantik und `voice_register`-Pflichtfeld
eingeführt. Ohne CI-Gate können die Anti-Patterns durch Refactor-Commits
jederzeit zurückschleichen. Der Lint-Guard macht den Standard dauerhaft
maschinell erzwingbar — unabhängig davon, wer den Code anfasst.

---

## Pattern-Klassen

### `forecast` — Autoritäts-/Zukunftsvokabular

| Phrase | Begründung |
|---|---|
| `future prediction` | Direkter Forecast-Claim; ersetzt durch Szenario-Vokabular (Task 09) |
| `rehearsal of the future` | Gottesperspektive auf Zukunft |
| `god's eye view` | Explizite Allwissenheits-Metapher |
| `predicts that` | LLM tritt als Prophetenrolle auf |
| `we will surely` | Unbegründete Gewissheit |
| `we will definitely` | Unbegründete Gewissheit |
| `seamless future` | Kombination Marketing + Forecast |

### `marketing` — US-Korporatismus-Phrasen

| Phrase | Begründung |
|---|---|
| `revolutionary` | Hyperbel, im DACH-Kontext nicht glaubwürdig |
| `seamless` | Inhaltsleere Superlative |
| `groundbreaking` | Hyperbel |
| `cutting-edge` / `cutting edge` | Korporatismus-Buzzword |
| `next-generation` / `next generation` | Marketing-Versprechen ohne Substanz |
| `best-in-class` / `best in class` | Vergleichs-Superlative ohne Beleg |
| `synergy` / `synergies` | Klassisches Management-Speak |
| `unparalleled` | Unbelegte Einzigartigkeit |
| `leverage` (als Verb) | Korporatismus-Anglizismus; false positives in Finanz-Texten sind akzeptiert, weil der Scope nur Prompts und Reports umfasst |

---

## Allowlist

Zwei Dateien zitieren Anti-Patterns zu Dokumentationszwecken und sind
eingebaut ausgenommen:

1. `prompts/2026-05-02-voice-register-katalog.md` — der Voice-Register-Katalog
   führt Anti-Patterns explizit auf, um sie zu benennen.
2. `docs/2026-05-02-task-10-voice-register-arbeitsprotokoll.md` — das
   Arbeitsprotokoll zu Task 10 benennt die entfernten Phrasen.

---

## Soft-Bootstrap-Begründung

Der CI-Job läuft initial mit `--soft` (Exit immer 0):

- `report_agent.py` enthält noch englische Output-Strings aus dem Generator,
  die erst durch Layer-3-Refactor (Tasks 12+) umgebaut werden.
- `report_prompts.py` ist nach Task 09 sauber, aber `report_agent.py`
  hat vereinzelte `leverage`- und `seamless`-Treffer in Inline-Strings.
- Der Hartmacher (`--soft` entfernen) ist explizit als Aufgabe von
  Task 17 (Layer 5 Defensibility) geplant, wenn alle Layer-3-Strings
  umgestellt sind.

---

## Neue Dateien

| Datei | LOC | Beschreibung |
|---|---|---|
| `backend/scripts/check_voice.py` | ~160 | CLI-Lint-Skript |
| `backend/tests/scripts/test_check_voice.py` | ~100 | 6 Pytest-Cases |
| `backend/tests/scripts/__init__.py` | 0 | Package-Marker |

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `.github/workflows/contract-gates.yml` | Neuer Job `voice-lint` am Ende |
| `CHANGELOG.md` | `[Unreleased] → Added`-Bullet |

---

## Implementierungs-Entscheidungen

- **Word-Boundary via `\b`:** Verhindert, dass `"infrastructure"` auf
  `"future"` matcht oder `"infrastructural"` auf `"structural"`. Für
  Bindestrich-Varianten (`cutting-edge`) nutzen die Patterns `[- ]`
  statt `\b`, weil der Bindestrich selbst eine Wort-Grenze ist.
- **Keine neuen Dependencies:** Pure Python (`argparse`, `re`, `pathlib`).
- **`print()` explizit erlaubt:** Skript ist CLI-Tool, kein Prod-Code.
  Vgl. `check_evidence_quality.py`.
- **Glob-Expansion im Skript:** `collect_paths()` expandiert `prompts/*.md`
  korrekt relativ zu `--repo-root`, damit der CI-Job aus `backend/`
  heraus die `prompts/`-Datei im Repo-Root erreicht.
