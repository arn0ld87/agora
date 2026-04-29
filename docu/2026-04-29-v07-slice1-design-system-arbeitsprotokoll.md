# v0.7 Slice 1 — Design-System-Arbeitsprotokoll

Datum: 2026-04-29  
Repo: `/mnt/brain/Projekte/Agora`  
Branch: `main`

## Ziel

Slice 1 aus `docu/2026-04-29-v07-umsetzungsplan.md` weiterführen: vorhandene Agora-Design-Tokens produktiv nutzen und harte Hauptfarben im Frontend weiter reduzieren, ohne eine visuelle Neugestaltung vorzunehmen.

## Tool-Wahl

1. `sequential thinking`: genutzt für Planung, Risiken und Reihenfolge, weil der Slice mehrere Frontend-Dateien und bestehende Änderungen berührt.
2. `docfork`: geprüft; in dieser Sitzung nur als Dokumentations-Fetcher verfügbar, nicht als lokales Repo-/Patch-Tool.
3. `context7`: für Vue 3 SFC/CSS-Variablen geprüft; CSS Custom Properties in SFC-Styles sind für diesen Slice passend.
4. Fallback: `ssh cachyos` plus Shell-Kommandos im Repo, weil die Arbeit auf dem Remote-System `/mnt/brain/Projekte/Agora` erfolgen sollte.

## Durchgeführte Schritte

1. Per `ssh cachyos` in das Repo `/mnt/brain/Projekte/Agora` gewechselt.
2. `git status --short` gelesen, um vorhandene Änderungen und untracked Quellen vor weiteren Änderungen zu kennen.
3. `AGENTS.md` und `CLAUDE.md` gelesen und die Repo-Regeln bestätigt: kleine Slices, bestehende Änderungen nicht revertieren, nach Slice `npm run check`.
4. `docu/2026-04-29-v07-umsetzungsplan.md` gelesen und Slice 1 als aktuellen Scope bestätigt.
5. `docu/agora_weiterentwicklung.md` gelesen und das Zielbild Design-System aus Design-Quellen in Vue-Frontend übernommen.
6. `Agora_design/` inventarisiert.
7. `frontend/src/assets/styles/tokens.css` gelesen und gegen `Agora_design/agora-tokens.css` sowie `Agora_design/tokens.css` gemappt.
8. `frontend/src/assets/styles/global.css` gelesen, weil dort bereits viele Design-System-Primitives konsolidiert wurden.
9. Diffs der vom Nutzer genannten bereits geänderten Dateien gelesen, bevor weitere Edits erfolgt sind.
10. Harte Farben im Frontend mit `rg` gesucht.
11. Sichtbare Fehler-/Statusfarben in `frontend/src/views/Home.vue` von hartem Rot auf `var(--status-error)` umgestellt.
12. Globale Schatten-/Log-/Stepper-Akzente in `frontend/src/assets/styles/global.css` auf vorhandene Tokens umgestellt.
13. Graph-Basisfarben in `frontend/src/components/GraphPanel.vue` ersetzt: Kanten, Labels, Auswahl, Node-Strokes und Toggle-Farben nutzen nun Tokens.
14. Entity-Farbpalette in `frontend/src/components/graph/graphPanelUtils.js` von Hexwerten auf Agora-Tokens umgestellt.
15. Graph-Fallback-Farbe in `frontend/src/components/graph/graphPanelData.js` von `#999` auf `var(--fg-muted)` umgestellt.
16. Detailpanel in `frontend/src/components/graph/GraphDetailPanel.vue` von hellem Ad-hoc-Farbschema auf Agora-Panel-, Text-, Rule-, Status- und Font-Tokens umgestellt.
17. Modal-Overlay in `frontend/src/components/Step2EnvSetup.vue` von hartem `rgba(...)` auf `color-mix(... var(--bg) ...)` umgestellt.
18. Agent-Log-Hairlines in `frontend/src/components/Step4Report.vue` von hartem `rgba(...)` auf `var(--rule-soft)` bzw. `color-mix(... var(--accent) ...)` umgestellt.
19. `git diff --check` ausgeführt: keine Whitespace-/Patchfehler.
20. Farbscan erneut ausgeführt. Ergebnis: harte Farben bleiben nur in `tokens.css` als Token-Definitionen und im Standalone-HTML-Export-Stylestring von `Step4Report.vue`, der ohne App-CSS funktionieren soll.
21. `npm run check` ausgeführt.
22. Finalen `git status --short --untracked-files=all` und `git diff --stat` gelesen.
23. Diese Arbeitsnotiz angelegt, weil jeder Schritt nachvollziehbar dokumentiert werden soll.

## Design-Mapping

| Design-Quelle | Frontend-Ziel | Status |
|---|---|---|
| `Agora_design/agora-tokens.css` | `frontend/src/assets/styles/tokens.css` | Produktiver Token-Stand, bereits übernommen und weiter genutzt |
| `Agora_design/tokens.css` | `frontend/src/assets/styles/tokens.css` | Referenz für lokale Fonts und Basis-Tokens |
| `Agora_design/fonts/GeistSans-Variable.woff2` | `frontend/src/assets/fonts/` | Bereits übernommen |
| `Agora_design/fonts/GeistMono-Variable.woff2` | `frontend/src/assets/fonts/` | Bereits übernommen |
| `Agora_design/agora-glyph.jsx` | `frontend/src/components/ui/AgoraGlyph.vue` | Bereits begonnen, nicht in diesem Schritt verändert |
| `Agora_design/ab-workspace.jsx` | `frontend/src/layouts/`, `frontend/src/views/` | Referenz für spätere Konsolidierung |
| `Agora_design/ab-pipeline.jsx` | `frontend/src/components/Step*.vue` | Referenz für Pipeline-Views |
| `Agora_design/ab-controls.jsx` | `frontend/src/components/ui/`, `global.css` | Referenz für Buttons, Badges, Controls |
| `Agora_design/ab-overlays.jsx` | Graph-/Drawer-/Modal-Flächen | Teilweise in `GraphDetailPanel.vue` und `Step2EnvSetup.vue` genutzt |

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `frontend/src/views/Home.vue` | Fehlerrot und Status-Bad-Farbe auf `var(--status-error)` umgestellt |
| `frontend/src/assets/styles/global.css` | Tooltip-Schatten, Log-Hintergrund und Stepper-Glow auf Tokens umgestellt |
| `frontend/src/components/GraphPanel.vue` | D3-/SVG-Farben, Edge-Labels, Node-Strokes, Auswahlfarben und Toggle-Farben auf Tokens umgestellt |
| `frontend/src/components/graph/graphPanelUtils.js` | Entity-Palette auf Design-Tokens umgestellt |
| `frontend/src/components/graph/graphPanelData.js` | Graph-Fallback-Farbe auf `var(--fg-muted)` umgestellt |
| `frontend/src/components/graph/GraphDetailPanel.vue` | Detailpanel auf Agora-Panel-, Text-, Rule-, Font- und Status-Tokens konsolidiert |
| `frontend/src/components/Step2EnvSetup.vue` | Modal-Overlay auf Token-basierte `color-mix()`-Farbe umgestellt |
| `frontend/src/components/Step4Report.vue` | Sichtbare Agent-Log-Linien auf Tokens umgestellt |

## Bewusst nicht geändert

1. `Agora_design/` wurde nur gelesen und als Quelle erhalten.
2. Bereits vorhandene Änderungen wurden nicht revertiert.
3. Der Standalone-HTML-Export-Stylestring in `Step4Report.vue` behält feste Farben, weil das erzeugte HTML ohne App-CSS/Tokens eigenständig lesbar bleiben soll.
4. Keine große visuelle Neugestaltung, keine Layout-Umbauten, keine neuen Dependencies.

## Verifikation

```bash
npm run check
```

Ergebnis:

```text
lint:backend: All checks passed
pytest: 223 passed, 2 skipped
lint:frontend: grün
build:frontend: Vite build grün
```

Zusätzlich:

```bash
git diff --check
```

Ergebnis: keine Fehler.

## Finaler Diff-Umfang

```text
8 files changed, 104 insertions(+), 104 deletions(-)
```

## Fortsetzung 1

24. Fortsetzung nach Nutzerfreigabe gestartet.
25. `sequential thinking` erneut genutzt, um den nächsten risikoarmen Slice-1-Schritt festzulegen.
26. Geplanter nächster Prüfschritt: UI-Basis-Komponenten `Btn`, `Badge`, `Field`, `Card`, `Select` und verbleibende Token-/Farbkonsistenz lesen.
27. UI-Basis-Komponenten `Btn.vue`, `Badge.vue`, `Field.vue`, `Card.vue`, `Select.vue` gelesen.
28. `SectionHead.vue` zusätzlich geprüft, weil es ebenfalls unter `frontend/src/components/ui/` liegt.
29. `Card.vue` von Legacy-Aliasen `--paper-1`, `--bg-dark`, `--fg-on-dark` auf semantische Tokens `--bg-elevated`, `--bg-inverse`, `--fg-on-inverse` umgestellt.
30. `SectionHead.vue` von `--ink-0` auf `--fg` umgestellt.
31. `Select.vue` vom hart codierten SVG-Data-URI-Chevron auf ein CSS-Chevron mit `var(--fg-muted)` umgestellt.
32. Farbscan erneut ausgeführt. Ergebnis: harte Farbwerte bleiben nur in `tokens.css` als Token-Definitionen und im bewusst eigenständigen Standalone-HTML-Export von `Step4Report.vue`.
33. `git diff --check` erneut ausgeführt: keine Fehler.
34. Diff-Umfang nach UI-Komponenten-Konsolidierung geprüft: 11 Dateien mit Frontend-Codeänderungen.
35. `npm run check` nach der UI-Komponenten-Konsolidierung erneut ausgeführt.
36. Ergebnis: Backend-Lint grün, Backend-Tests `223 passed, 2 skipped`, Frontend-Lint grün, Vite-Build grün.

## Fortsetzung 2 — Layout-Komponenten

37. Nutzerfreigabe für den nächsten Schritt erhalten.
38. `sequential thinking` genutzt, um den Layout-Block als nächsten risikoarmen Slice-1-Schritt festzulegen.
39. Geplanter Scope: Legacy-Aliase in `frontend/src/layouts/` semantisch ersetzen, ohne Layout/UX umzubauen.
40. Layout-Komponenten gelesen: `WorkspaceModeSwitch.vue`, `WorkspaceHeader.vue`, `WorkspaceLayout.vue`, `WorkspaceStepStatus.vue`.
41. Alias-Scan für `frontend/src/layouts/` ausgeführt und die betroffenen Stellen identifiziert.
42. `--paper-0` in Layout-Flächen auf `--bg` umgestellt.
43. `--paper-1` im Mode-Switch auf `--bg-elevated` umgestellt.
44. `--ink-0` in Layout-Textzuständen auf `--fg` umgestellt.
45. Layout-Alias-Scan erneut ausgeführt: keine `--paper-*`, `--ink-*`, `--bg-dark` oder `--fg-on-dark` mehr in `frontend/src/layouts/`.
46. `npm run check` nach Layout-Konsolidierung ausgeführt.
47. Ergebnis: Backend-Lint grün, Backend-Tests `223 passed, 2 skipped`, Frontend-Lint grün, Vite-Build grün.

## Commit und Push

48. Nutzerfreigabe fuer Commit und Push auf main erhalten.
49. Git-Status, Branch und Remotes geprueft: Branch main, Push-Remote origin.
50. Fuer den Commit werden nur die aktuellen Slice-1-Frontend-Dateien und diese Arbeitsprotokoll-MD gestaged.
51. Commit erstellt mit Message: Consolidate frontend design tokens.

## Fortsetzung 3 — Step1 und HistoryDatabase

52. Nutzerfreigabe fuer den naechsten kleinen Slice-1-Block erhalten.
53. Arbeitsbaum und letzter Commit geprueft: HEAD 377da83, Arbeitsbaum sauber.
54. Dateien gelesen: frontend/src/components/Step1GraphBuild.vue und frontend/src/components/HistoryDatabase.vue.
55. Alias-Scan fuer beide Dateien ausgefuehrt und die Legacy-Token-Stellen identifiziert.
56. Legacy-Aliase in Step1GraphBuild.vue und HistoryDatabase.vue ersetzt.
57. Alias-Scan fuer beide Dateien erneut ausgefuehrt: keine Legacy-Aliase mehr.
58. git diff --check ausgefuehrt: keine Fehler.
59. npm run check ausgefuehrt: Backend-Lint gruen, Backend-Tests 223 passed/2 skipped, Frontend-Lint gruen, Vite-Build gruen.

## Fortsetzung 4 — Step2 und Step3

60. Nutzerfreigabe fuer den naechsten Slice-1-Block erhalten.
61. Arbeitsbaum und letzter Commit geprueft: HEAD bc16bfd, Arbeitsbaum sauber.
62. Dateien gelesen: frontend/src/components/Step2EnvSetup.vue und frontend/src/components/Step3Simulation.vue.
63. Alias-Scan fuer beide Dateien ausgefuehrt und die Legacy-Token-Stellen identifiziert.
64. Legacy-Aliase in Step2EnvSetup.vue und Step3Simulation.vue ersetzt.
65. Alias-Scan fuer beide Dateien erneut ausgefuehrt: keine Legacy-Aliase mehr.
66. git diff --check ausgefuehrt: keine Fehler.
67. npm run check ausgefuehrt: Backend-Lint gruen, Backend-Tests 223 passed/2 skipped, Frontend-Lint gruen, Vite-Build gruen.

## Fortsetzung 5 — Step5 Interaction

68. Nutzerfreigabe fuer den naechsten Slice-1-Block erhalten.
69. Arbeitsbaum und letzter Commit geprueft: HEAD 1739545, Arbeitsbaum sauber.
70. Datei gelesen: frontend/src/components/Step5Interaction.vue.
71. Alias-Scan fuer Step5Interaction.vue ausgefuehrt und die Legacy-Token-Stellen identifiziert.
72. Legacy-Aliase in Step5Interaction.vue ersetzt.
73. Alias-Scan fuer Step5Interaction.vue erneut ausgefuehrt: keine Legacy-Aliase mehr.
74. git diff --check ausgefuehrt: keine Fehler.
75. npm run check ausgefuehrt: Backend-Lint gruen, Backend-Tests 223 passed/2 skipped, Frontend-Lint gruen, Vite-Build gruen.
