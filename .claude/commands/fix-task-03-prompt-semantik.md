---
description: Layer 2 - "future prediction" / "rehearsal of the future" / "god's eye view" aus report_prompts.py rausoperieren
allowed-tools: Read, Edit, Grep, Bash
---

# /fix-task-03 — Prompt-Semantik entschärfen

## Vorab-Verifikation (im Code bestätigt)

```bash
# 8 Treffer in report_prompts.py:
rg -n "future prediction|rehearsal of the future|god's eye view|how the future will unfold" backend/app/services/report_prompts.py
```

Die Phrasen stehen tatsächlich an Z. 24, 27, 30, 36, 89, 101, 110, 117 — kein
Halluzinations-Risiko, ChatGPT hat hier verifiziert recht.

## Implementierung

`backend/app/services/report_prompts.py`:

```diff
-You are an expert in writing "future prediction reports" with a "god's eye view"
+You are an expert in writing simulation-based scenario reports

-The evolution result of the simulated world is a prediction of what might happen
-in the future. What you're observing is not "experimental data" but a "rehearsal
-of the future".
+The simulated world produces plausible reactions, tensions and trajectories
+under explicit assumptions. This is a scenario simulation, not a forecast.

-Write a "future prediction report" that answers:
+Write a simulation-based scenario report that answers:

-✅ This is a future prediction report based on simulation, revealing "if this
-happens, how will the future unfold"
+✅ This is a scenario report — it shows plausible reactions, given the
+simulation assumptions

-✅ Focus on "how the future will unfold" - simulation results are the predicted
-future
+✅ Focus on plausible reactions, tensions, and uncertainties inside the
+simulated scenario
+✅ Explicitly mark uncertainty, sparse evidence, and assumption sensitivity
+❌ Do not imply certainty, forecasting authority, or real-world inevitability

-You are observing a rehearsal of the future from a "god's eye view"
+You are observing one scenario instance under specific assumptions
```

Dann auch in `README.md` prüfen: existieren ähnliche Phrasen dort? `rg`-Check.

## Tests aktualisieren

`backend/tests/test_report_prompts.py` (existiert laut Code):

```bash
rg -n "future prediction|rehearsal" backend/tests/test_report_prompts.py
```

Wenn Tests die alten Phrasen pinnen → Tests müssen mit. Stil: nicht exakte
Phrase pinnen, sondern Verhaltens-Eigenschaften (z. B. "scenario" muss vorkommen,
"prediction" darf nicht).

## Verifikation

```bash
rg -n "future prediction|rehearsal of the future|god's eye view" backend/    # leer
cd backend && uv run pytest tests/test_report_prompts.py -v                  # grün
cd backend && uv run pytest -x -q                                            # grün
```

## NICHT machen

- Keine englischen Reports auf Deutsch übersetzen — Layer 2 dafür separat.
- Keine OASIS-Source-Patches.
