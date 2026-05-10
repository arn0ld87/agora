---
description: Layer 2 - "future prediction" / "rehearsal of the future" / "god's eye view" aus report_prompts.py rausoperieren (via Codex)
allowed-tools: Read, Bash, Grep, Agent
---

# /fix-task-03 — Prompt-Semantik entschärfen (Codex-Dispatch)

String-/Prompt-Last → günstiger Codex-Run mit `--effort low` und `--model gpt-5.3-codex-spark`.

## Vorab-Verifikation

```bash
cd /Volumes/T7/Projekte/agora
rg -n "future prediction|rehearsal of the future|god's eye view|how the future will unfold" backend/app/services/report_prompts.py
# Erwartet: 8 Treffer an Z. 24, 27, 30, 36, 89, 101, 110, 117 (verifiziert)
```

Falls 0 Treffer: Stop — Task 03 ist durch.

## Worktree

```bash
WT=/Volumes/T7/Projekte/agora-worktrees/feat-layer-2-task-03-prompt-semantik
git -C /Volumes/T7/Projekte/agora fetch origin --quiet
git -C /Volumes/T7/Projekte/agora worktree add -b feat/layer-2-task-03-prompt-semantik "$WT" origin/main
```

## Codex-Dispatch (Agent-Tool)

`subagent_type: "codex:codex-rescue"`, `description: "Codex fix-task-03 prompt semantik"`, `prompt`:

```
--write --effort low --model gpt-5.3-codex-spark

Arbeite ausschließlich im Worktree <WT>. Sub-Slice: Layer 2 / Task 03 — Prompt-Semantik entschärfen.

## Ziel

Aus backend/app/services/report_prompts.py alle 8 Stellen mit "future prediction", "rehearsal of the future", "god's eye view", "how the future will unfold" raus. Stattdessen: Sprache von Forecast → Szenario-Simulation. Unsicherheit explizit markieren.

## Konkrete Ersetzungen

- "future prediction reports" mit "god's eye view" → "simulation-based scenario reports"
- "prediction of what might happen in the future" / "rehearsal of the future" → "plausible reactions, tensions and trajectories under explicit assumptions. This is a scenario simulation, not a forecast."
- "future prediction report" → "simulation-based scenario report"
- "this is a future prediction report ... how will the future unfold" → "this is a scenario report — it shows plausible reactions, given the simulation assumptions"
- "how the future will unfold ... predicted future" → "plausible reactions, tensions, and uncertainties inside the simulated scenario" + "Explicitly mark uncertainty, sparse evidence, and assumption sensitivity" + "Do not imply certainty, forecasting authority, or real-world inevitability"
- "rehearsal of the future from a god's eye view" → "one scenario instance under specific assumptions"

Auch README.md prüfen: rg -n "future prediction|rehearsal" README.md — falls Treffer, analog ersetzen.

## Tests aktualisieren

backend/tests/test_report_prompts.py: rg -n "future prediction|rehearsal" — falls die alten Phrasen gepinnt werden, umstellen auf Verhaltens-Eigenschaften ("scenario" muss vorkommen, "prediction" darf nicht).

## Akzeptanz

- rg -n "future prediction|rehearsal of the future|god's eye view" backend/ → leer
- rg -n "future prediction|rehearsal of the future|god's eye view" README.md → leer
- cd backend && uv run pytest tests/test_report_prompts.py -v → grün
- cd backend && uv run pytest -x -q → grün

## Doku

- docu/<YYYY-MM-DD>-task-03-prompt-semantik-arbeitsprotokoll.md (knapp: 8 Stellen, Diff-Hunks)
- CHANGELOG.md [Unreleased]: "Layer 2: Prompt-Semantik von Forecast auf Szenario umgestellt (Sub-Slice 03)"

## NICHT

- Englische Reports nicht auf Deutsch übersetzen — Layer 2 dafür separat (Task 10).
- Keine OASIS-Source-Patches.
- NICHT committen.
```

## Verify

```bash
rg -n "future prediction|rehearsal of the future|god's eye view" "$WT/backend/" || echo "clean"
cd "$WT/backend" && uv run pytest tests/test_report_prompts.py -v
cd "$WT/backend" && uv run pytest -x -q
```

Commit via `/agora-next-task` oder manuell.
