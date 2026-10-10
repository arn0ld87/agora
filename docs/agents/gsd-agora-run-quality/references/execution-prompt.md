# Ausführungsprompt

```text
Nutze $gsd-agora-run-quality und arbeite Epic https://github.com/arn0ld87/agora/issues/1831 von der Triage bis zur verifizierten Beseitigung ab. Falls der Skill noch nicht entdeckt wird, lies docs/agents/gsd-agora-run-quality/SKILL.md im Repository.

Referenz: ssh gns3, Container agora, Deployment 328d2b8d, Projekt proj_7c045c5ac0f5, Simulation sim_c56d9430b50a, Report report_e5f1df6f5f2c. Lies die Case-Referenz, den aktuellen Epic-/Child-Status und vorhandene PRs zuerst; keine Doppelimplementierung. Bewahre Originalartefakte und unterscheide Deployment von aktuellem Code.

Ziel: Quellenidentität und belegte Rollen erhalten; echte gültige Antworten und ausreichenden sichtbaren Kontext in der Simulation ermöglichen; eine deutsche, vom Modell aus Fragestellung und Daten geplante Gliederung erzeugen. Keine festen Titelpresets oder Ersatzgliederungen bei Fehlern. Inhalts-/Evidence-Gates und ehrliche Fehler-/Vollständigkeitszustände bleiben erhalten. Alte Fallbacks beim Resume neu planen.

Triagiere #1832–#1836 nach Beleg, Priorität, Root Cause, Abhängigkeit, Fix und Regression. Bericht #1832 zuerst als Ende-zu-Ende-Tracer; Betrieb #1834, Persona #1833, Dialog #1835 und Stage-Eval #1836 danach. Verwende die tatsächlich installierten GSD-Plan-/Execute-/Verify-Workflows und vorhandenen Projektstate; kein ungefragter Projektneustart. Schreibe ausführbare atomare PLAN.md, SUMMARY.md und VERIFICATION.md. Lasse den Plan und jeden lokalen Issue-Commit gemäß Repo-Routing unabhängig prüfen.

Beachte: Der beobachtete Report scheiterte vor einer Modellantwort an codex_cli/Permission denied. Workspace report_generation war codex_cli/gpt-6-astra, Personas und Simulation openai/gpt-6-luna. Bezeichne den Berichtsfehler deshalb nicht als Luna-Schwäche. Prüfe tatsächliche historische Stage-Routen und alle Confounds.

Vergleiche Luna anschließend stageweise mit einer verfügbaren stärkeren Route bei identischen Quellen, Prompts, Verträgen, Tools, Feeds und vergleichbaren Budgets. Mindestens drei Pilotwiederholungen pro kritischer Bedingung; deterministische Identitäts-/Contractchecks und verblindete Paarbewertung; Single-Prompt-/Persona-Baseline, Kosten und Latenz. Keine Mindestquote für Dissens, Posts oder Positionswechsel. Urteil je Stage; fehlende Evals ehrlich NICHT BELEGT. Einen vorhandenen Kostenrahmen respektieren; falls keiner besteht, Harness und konkrete Kostenschätzung fertigstellen und nur die kostenpflichtige Ausführung offenlassen.

Arbeite auf eigenen Branches/Worktrees, Contracts-first, Regressionstests, Pre-Push-Gate, Changelog-Fragmente, STATUS und gegebenenfalls Upgrade-Runbook. Erstelle atomare PRs und verknüpfe sie im Epic. Keine Secrets ausgeben, keine Originalruns überschreiben, kein stiller Modellwechsel oder automatischer Merge/Deployment. Stoppe nicht bei allgemeinen Empfehlungen: liefere konkrete reviewbare Änderungen und Nachweise; markiere verbleibende externe Voraussetzungen präzise.
```
