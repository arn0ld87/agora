# Slice 01 — Verifikation (#1832)

Stand: 10.10.2026. Geprüft im isolierten Worktree, noch kein Produktcode-Deployment auf gns3.

- `bash scripts/pre-push-gate.sh backend`: Exit 0. Ruff, Komplexitäts- und Typ-Schuld-Gate grün; 1355 Contract-Tests bestanden, zwei bestehende ausschließlich für Subprozesse vorgesehene Tests übersprungen. Keine Baselines oder Assertions abgeschwächt. Alle 146 generierten Schemas passen; STATUS-Prüfung grün.
- `bash scripts/pre-push-gate.sh frontend`: Exit 0. Lint, Typecheck und Contract-Mirror-Smoke grün. Der Standard-Gate führt weder vollständige Frontend-Suite noch Build aus.
- `bash scripts/pre-push-gate.sh schemas`: Exit 0. Alle 146 Schemas, Versionsabgleich und STATUS-Prüfung grün.
- Gezielter Frontend-Vertragstest: 51 bestanden; neue Fälle zuvor achtmal rot gegen den alten Vertrag.
- Backend-Regressionsgruppen: 40 Outline-/Resume-/Partial-Tests, 19 Requirement-/Status-/Zitat-Tests und weitere 62 Checker-/Evidence-/Terminal-/Budgettests bestanden. Der alte HEAD-Vertrag weist freie Szenariotitel nachweislich zurück.
- Nach Korrektur eines invarianten Listen-Overrides in `PlanResponse`: 34 Strict-Schema-/JSON-Mode-Tests bestanden, Typ-Schuld-Gate Exit 0. Keine neue Typ-Schuld (262 Fehler, Baseline 264).
- Abschließender gemeinsamer Lauf aus acht betroffenen Testdateien (Outline, Struktur, Workflow, Partial, Strict-Schema, Contract, Partial-Status, Prompts): 166 bestanden.
- Skill: `quick_validate.py` meldet `Skill is valid!`; unabhängige Plan- und Skill-Prüfung bestanden.

Logs: `/tmp/agora-1832-backend-gate.log`, `/tmp/agora-1832-frontend-gate.log`, `/tmp/agora-1832-schemas-gate.log` auf dem Entwicklungshost. Keine vollständige neue Simulation und kein vollständiger neuer Bericht behauptet. Modellqualität bleibt bis zur kontrollierten Stage-Evaluation (#1836) offen.
