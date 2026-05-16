# Wording-Glossar v1 — Agora

**Status:** verbindlich seit 2026-05-02 (Slice „Wording-Glossar v1", Issue #175).
**Geltungsbereich:** README, `docs/`, alle Backend-Strings, die im Report sichtbar werden, und alle LLM-Prompts in `backend/app/services/`.

## Motivation

Agora ist ein **Persona-basierter Resonanz-Simulator**, kein Orakel. „Prediction"-, „Rehearsal"- und „God's-Eye"-Vokabular suggeriert Vorhersagekraft, die das System nicht hat, und passt nicht zur sachlichen DACH-Außendarstellung. Das Glossar fixiert die Begriffe, mit denen wir intern und extern über das Produkt sprechen.

## Glossar

| Vermeiden (EN) | Code & Prompts (EN) | UI / README / Docs (DE) |
|---|---|---|
| `prediction` | `scenario evaluation` | Szenario-Auswertung |
| `predict` (Verb) | `evaluate scenario` | Szenario auswerten |
| `future behavior` | `simulated reaction` | simulierte Reaktion |
| `rehearse the future` / `rehearsal of the future` | `test assumptions` | Annahmen testen |
| `public opinion prediction` | `persona-based resonance analysis` | Persona-basierte Resonanzanalyse |
| `high-fidelity digital world` | `reproducible simulation environment` | reproduzierbare Simulationsumgebung |
| `god's eye view` | `analytical observer perspective` | analytische Beobachtungsperspektive |
| `Agentic-Prediction-Engine` | `Agentic Scenario Evaluation Engine` | Persona-basierter Resonanz-Simulator |
| `prediction results` / `prediction findings` | `scenario evaluation results` | Auswertungsergebnisse |
| `simulation predictions` | `simulation observations` | Simulationsbeobachtungen |
| `predictions of future human behavior` | `simulated persona reactions` | simulierte Persona-Reaktionen |
| `future prediction reports` | `scenario evaluation reports` | Szenario-Auswertungsberichte |

## Anwendungsregeln

1. **Code- und Prompt-Strings** verwenden die EN-Spalte. Sie wirken direkt auf LLM-Output und müssen englisch bleiben, weil Modelle sonst die Sprache wechseln.
2. **README, `docs/`, UI-Texte und Commit-Bodies** verwenden die DE-Spalte.
3. **Historische Logs** (`docs/archive/logs/log_neu.md`, `docs/archive/logs/log1_analyse.md`) werden **nicht** rückwirkend angepasst — sie sind Zeitdokumente.
4. **Snapshot-Tests** in `backend/tests/services/` müssen bei Code-Änderungen mitgeführt werden.

## Verifikation

Vor jedem PR, der Reports oder Prompts berührt:

```bash
rg -ni "future prediction|rehearsal|public opinion|high.fidelity digital world|god.s eye|agentic-prediction-engine" \
   backend/app/ README.md docs/ \
   --glob '!docs/archive/logs/**'
```

Treffer = Glossar-Verstoß.

## Verwandte Slices

- Issue #175 — Wording-Glossar v1 (dieses Dokument).
- CLAUDE.md → Layer 2 (Prompt-Semantik).
- Hot-Spot-Liste in CLAUDE.md → `report_prompts.py:24/27/30/89/101/110/117`.
