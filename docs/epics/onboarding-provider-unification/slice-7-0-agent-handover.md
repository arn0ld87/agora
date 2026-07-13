# Agentenübergabe: Onboarding/Provider-Unification Slice 7.0

> Diese Übergabe ist für einen neuen KI-Agenten bestimmt. Sie soll ohne erneute
> Grundsatzanalyse zu demselben Ergebnis führen: ein belastbarer Docs-only-PR
> für den atomaren Subplan „Golden-Gate-System und Informationsarchitektur“,
> inklusive GitHub-Gemini-Sichtung, aber ohne Merge und ohne Produktcode.

## 1. Auftrag und Endzustand

Arbeite den bestehenden Slice 7.0 fertig. Der gewünschte Endzustand ist:

1. Branch `codex/onboarding-slice-7-prep` im Worktree
   `/Volumes/T7/Worktrees/agora/onboarding-slice-7-prep`.
2. Basis `origin/main` @ `686a53352820816fde0c45da428abc31f5f96036`
   oder ein späteres, konfliktfrei rebased `origin/main`.
3. Ausschließlich Dokumentationsänderungen. Keine UI-, CSS-, Router- oder
   Produktcodeänderung in Slice 7.0.
4. Fertige Dateien:
   - `docs/epics/onboarding-provider-unification/slice-7-subplan.md`
   - `docs/epics/onboarding-provider-unification/HANDOVER.md`
   - diese Agentenübergabe
5. Vollständige lokale Validierung.
6. Normaler Commit und Push ohne `--no-verify`, `--force` oder
   `--no-gpg-sign`.
7. Docs-only-PR gegen `main`.
8. GitHub-Gemini-Sichtung anfordern, Findings prüfen und alle berechtigten
   Findings bearbeiten.
9. Nach dem gesichteten PR stoppen. Nicht mergen.

## 2. Unverhandelbare Architekturgrenzen

- Keine Parallelkopie des Design-v4-Systems.
- `frontend/src/assets/styles/tokens-v3.css` und `states.css` sind die
  bestehenden Erweiterungspunkte.
- Keinen dritten Token-Namespace einführen.
- Keine zweite Komponentenbibliothek und keinen zweiten Model-Picker bauen.
- `frontend/src/components/v4/forms/AiModelPicker.vue` bleibt Zielkomponente.
- Provider-, `AiModelRef`- und Routing-Verträge nicht duplizieren.
- Slice 6 besitzt Persona-Count, Run-Vertrag, Step-2-Budgetlogik und die
  E2E-Werte 1, 5, 10, 30, 50, 100. Slice 7 darf diese Logik nicht ändern.
- `/settings-classic`, Legacy-Picker und Mock-Routing nur nach belegtem Import-
  und Impact-Nachweis deprecaten oder entfernen.
- WCAG AA, 320 px, Tastaturbedienung, sichtbare Focus States und Reduced Motion
  müssen in den späteren Implementierungs-PRs überprüfbare Gates sein.
- Kein Gemini-Sidecar. Die einzige Gemini-Aktion ist die GitHub-Sichtung des PR.
- Keine ungefragten Refactors und kein Merge.

## 3. Arbeitsumgebung und Schutzregeln

### Slice-Worktree

```text
/Volumes/T7/Worktrees/agora/onboarding-slice-7-prep
branch: codex/onboarding-slice-7-prep
base:   686a53352820816fde0c45da428abc31f5f96036
```

Der Worktree wurde korrekt mit `git worktree add` auf `origin/main` erstellt.
Abhängigkeiten wurden bereits mit `npm run setup:all` installiert:

- Root- und Frontend-Bun-Dependencies vorhanden.
- `backend/.venv` via `uv sync` vorhanden.

### Haupt-Worktree

```text
/Volumes/T7/Projekte/agora
branch: main
HEAD:   686a53352820816fde0c45da428abc31f5f96036
```

Der frühere Dirty-State wurde **nicht gelöscht**, sondern reversibel gesichert:

```text
stash@{0}: On main: codex: clean main before onboarding slice 7.0
```

Wichtig:

- Den Stash nicht droppen, poppen oder überschreiben.
- Der Benutzer hat sein Prompt-Pack erneut unter
  `prompts/agora-gpt-5.6-sol-prompt-pack(1) 2/` abgelegt.
- Diesen Ordner weder löschen, verschieben, stagen noch erneut stashen.
- Der Haupt-Worktree darf wegen dieses untracked Prompt-Packs und des
  untracked `graphify-out/` als dirty erscheinen. Das gehört **nicht** in den
  Slice-7-PR.

### Geheimniswarnung

Im Chat wurde ein Gemini-Sidecar-Schlüssel offengelegt. Ihn weder wiederholen
noch verwenden, speichern, loggen oder committen. Für diesen Auftrag gilt
weiterhin „Kein Gemini-Sidecar“. Der Benutzer sollte den Schlüssel separat
rotieren.

## 4. Bereits erledigt

### Repository und Graphify

- `/Volumes/T7` ist als APFS-Volume gemountet.
- `git fetch origin` wurde ausgeführt.
- Der Haupt-Worktree wurde per Fast-Forward auf `origin/main` aktualisiert.
- Im sauberen Haupt-Worktree wurde ein frischer code-only Graph gebaut:

```text
/Volumes/T7/Projekte/agora/graphify-out/graph.json
17.951 Nodes
33.528 Kanten
```

Erzeugungsbefehl:

```bash
graphify extract . --code-only --no-cluster --out .
```

Der Graph ist untracked und bleibt im Haupt-Worktree. Er darf nicht in den PR.
Für Abfragen aus dem Slice-Worktree immer explizit verwenden:

```bash
graphify query "<Frage>" \
  --graph /Volumes/T7/Projekte/agora/graphify-out/graph.json
```

### Pflichtlektüre

Gelesen bzw. mit context-mode vollständig indexiert und gezielt ausgewertet:

- `AGENTS.md`
- `PLAN.md`
- `docs/epics/onboarding-provider-unification/01-current-state-map.md`
- `docs/epics/onboarding-provider-unification/04-implementation-plan.md`
- `docs/epics/onboarding-provider-unification/HANDOVER.md`
- `docs/ui/design-language-v4.md`
- `docs/ui/ui-rules.md`
- `docs/ui/component-audit.md`
- `docs/ui/shadcn-vue-evaluation.md`
- `frontend/src/assets/styles/tokens-v3.css`
- `frontend/src/assets/styles/states.css`
- aktuelle Shell-, Onboarding-, Settings-, Sidebar- und Model-Picker-Strukturen

context-mode-Projekt:

```text
/Volumes/T7/Worktrees/agora/onboarding-slice-7-prep
```

Index-Quellen:

- `onboarding-provider-unification`
- `design-v4-docs`
- `PLAN`
- `frontend-styles`

### Bereits erstellter Hauptplan

`slice-7-subplan.md` wurde bereits angelegt. Er enthält:

- Ziel und Architekturgrenzen;
- Graphify-/Importnachweise;
- wiederverwendbaren Design-v4-Bestand;
- Informationsarchitektur-Matrix;
- Slice-6-File-Ownership;
- neun Implementierungs-Sub-Slices;
- Reihenfolge, Test-/A11y-Gates und Risiken.

`HANDOVER.md` wurde um den Abschnitt
`Handover — Onboarding/Provider-Unification Slice 7.0` ergänzt.

Die Inhalte sind fachlich fertig, müssen aber noch geprüft, validiert,
committet, gepusht und im PR gesichtet werden.

## 5. Verifizierte technische Findings

### 5.1 `/settings-classic`

- Route: `frontend/src/router/index.ts:114-116`.
- Ziel: `frontend/src/views/SettingsView.vue`.
- Graphify findet für `SettingsView.vue` außer Selbstbezügen nur den Test
  `frontend/src/views/__tests__/SettingsView.spec.ts`.
- Dynamic Router Imports werden im AST-Graphen nicht zuverlässig als Kante
  aufgelöst; der Router-Quelltext ist deshalb zusätzlicher Pflichtnachweis.
- Konsequenz: nicht sofort löschen. Erst Feature-Parität, Deep-Link-Test,
  Query-/Hash-Erhalt und dann Redirect in eigenem PR.

### 5.2 Model-Picker

Kanonischer Ziel-Picker:

```text
frontend/src/components/v4/forms/AiModelPicker.vue
```

Produktive Konsumenten laut Graphify/Grep:

- `components/LlmRouting/LlmRoutingView.vue`
- `components/v4/dashboard/HeroNewRun.vue`
- `components/v4/forms/StepModelOverrideChip.vue`
- `views/Settings/LlmProvidersView.vue`
- `views/Settings/SettingsGeneralView.vue`

Legacy-Picker:

1. `components/ui/ModelPicker.vue`
   - nur Selbstbezug + Unit-Test;
   - kein produktiver Importer;
   - sicherster Löschkandidat, aber erst in eigenem Cleanup-PR mit erneutem
     Negativ-Grep und Graphify-Nachweis.
2. `components/v4/forms/ModelPicker.vue`
   - produktiv in `views/Home.vue`,
     `components/step4/ReportModelControls.vue` und
     `components/v4/forms/LlmProfileManager.vue`;
   - nicht löschen.
3. `components/llm/LlmProfilePicker.vue`
   - produktiv in `components/Step4Report.vue`,
     `components/step2/EnvSetupModelPanel.vue` und
     `components/step4/ReportBranchControls.vue`;
   - profilbasierter Read-Adapter, nicht löschen.

Wichtig: Slice 5.5 hat mehrere Adapter bereits mit `@deprecated` markiert.
Die ältere Datei `docs/ui/component-audit.md` ist an dieser Stelle stale und
nennt `v4/forms/ModelPicker.vue` noch `keep`. Aktueller Code und Slice-5-
Handover haben Vorrang.

### 5.3 Mock-Routing

Verwaister Unterbaum:

```text
frontend/src/views/Settings/llmRouting/mockData.ts
frontend/src/views/Settings/llmRouting/ActiveSnapshotsCard.vue
frontend/src/views/Settings/llmRouting/GlobalDefaultCard.vue
frontend/src/views/Settings/llmRouting/StageOverridesCard.vue
frontend/src/views/Settings/llmRouting/CustomModelCard.vue
```

- `mockData.ts` wird nur von drei Karten im selben Unterbaum importiert.
- Keine Karte hat einen externen Importer.
- Die produktive `views/Settings/LlmRoutingView.vue` verwendet stattdessen
  `components/LlmRouting/LlmRoutingView.vue` mit echten Run-IDs.
- Konsequenz: eigener reiner Orphan-Cleanup-PR; produktive Routing-View und
  Verträge unangetastet lassen.

### 5.4 Design v4

Wiederverwenden, nicht kopieren:

- Shell: `AppShell`, `Sidebar`, `SidebarGroup`, `SidebarItem`, `Topbar`,
  `Breadcrumbs`, `PageHeader`, `useShellStore`.
- Forms: `Card`, `Field`, `Input`, `Select`, `Button`, `SegmentedControl`,
  `StickyActionBar`, `Badge`, `Pill`, `Skeleton`, `DropdownMenu`,
  `AiModelPicker`.
- Data/Feedback: `Alert`, `Dialog`, `EmptyState`, `DataTable`, `Tabs`, `Chart`,
  `Kicker`.

Graphify-Nachweis:

- `AppShell.vue`: 22 externe Produktionskonsumenten.
- `Sidebar.vue`: produktiv vom `AppShell` konsumiert.

Dokumentationsrisiko:

`docs/ui/design-language-v4.md` verweist auf die nicht vorhandene Datei
`docs/2026-05-11-design-v4-app-shell-epic.md`. Nicht im Slice-7.0-PR nebenbei
reparieren, sondern als offenes Doku-Risiko dokumentieren.

### 5.5 Tokens und States

- Globale Imports in `frontend/src/main.ts:12` und `:14`.
- `tokens-v3.css` enthält bereits Surface-, Text-, Accent-, Status-, Spacing-,
  Radius-, Shadow-, Density- und Compat-Tokens.
- `states.css` enthält Rest/Hover/Pressed/Active/Selected/Disabled/Loading,
  `.v4-state-interactive`, `.v4-state-selectable`, `:focus-visible` und
  `prefers-reduced-motion`.
- CSS-Imports erscheinen nicht als Graphify-AST-Kanten. Dieser Extractor-
  Grenzfall muss im Plan ehrlich benannt bleiben.

### 5.6 Informationsarchitektur

Die im Subplan festgelegte Matrix:

| Eintrag | Entscheidung |
|---|---|
| Dashboard | `wire` |
| Runs | `wire` |
| Projekte | `defer` |
| Datensätze | `defer` |
| Vorlagen | `defer` |
| Monitoring | `defer` |
| Settings Allgemein | `wire` |
| Settings Integrationen | `implement MVP` |
| Settings Profil | `wire` |
| Settings API Keys | `wire` |
| Settings Audit Logs | `hide` |
| Settings LLM Providers | `wire` |
| Settings LLM Routing | `hide` in Settings, unter Runs verdrahten |
| Settings Embedding | `wire` |
| Users & Teams | `hide` |
| `/settings-classic` | `hide`, später Redirect |

### 5.7 Slice-6-Konfliktflächen

Bis Slice 6 gemergt ist, exklusiv für Slice 6 reservieren:

- `frontend/src/components/v4/dashboard/HeroNewRun.vue` und Persona-/Run-
  relevante Specs;
- `frontend/src/store/pendingUpload.ts`;
- `frontend/src/api/simulation.ts`;
- `frontend/src/components/Step2EnvSetup.vue`;
- `frontend/src/components/step2/AgentCapControl.vue` und Specs;
- `backend/app/api/simulation_prepare.py`;
- `backend/app/services/prepare_service.py`;
- `backend/app/services/simulation_config_generator.py`;
- Persona-/Quota-Verträge und Tests;
- E2E-Werte 1, 5, 10, 30, 50, 100;
- Persona-/Budget-Wording in `de.json` und `en.json`.

Sub-Slices 7.5b und 7.9c warten deshalb auf den Slice-6-Merge.

## 6. Geplante Implementierungsreihenfolge

Der Docs-only-PR implementiert nichts davon, muss aber exakt diese Empfehlung
enthalten:

```text
7.1 → 7.2 → 7.3 → 7.4 → 7.7 → 7.8
  └────────→ 7.6 → 7.9a → 7.9b → 7.9c
7.1 + 7.2 + Slice 6 gemergt → 7.5/7.5b
```

Sub-Slices:

1. **7.1** Golden-Gate-Tokens und State-Vertrag.
2. **7.2** Shell-A11y und 320-px-Grundgerüst.
3. **7.3** Sidebar-Informationsarchitektur.
4. **7.4** produktive Settings-Flächen konvergieren.
5. **7.5/7.5b** Onboarding und später Dashboard-Oberfläche.
6. **7.6** kanonischen `AiModelPicker` polieren.
7. **7.7** verwaistes Mock-Routing entfernen.
8. **7.8** `/settings-classic` nach Parität deprecaten.
9. **7.9a-c** Legacy-Picker-Consumer stufenweise migrieren und Adapter erst bei
   null produktiven Importern entfernen.

Empfehlung für den ersten Implementierungs-PR: **7.1**. Er ist additiv,
testbar, rollback-freundlich und berührt keine Slice-6-Datei.

## 7. Noch auszuführende Arbeit

### Schritt A — Status und Scope prüfen

Im Slice-Worktree:

```bash
git status --short --branch
git diff -- docs/epics/onboarding-provider-unification/
```

Erwartet sind nur:

- neue `slice-7-subplan.md`;
- geänderte `HANDOVER.md`;
- neue `slice-7-0-agent-handover.md`.

Es kann zusätzlich ein untracked `.planning/` existieren. Das wurde nicht für
den Benutzer erstellt und gehört nicht in den PR. Vor dem Staging prüfen und
entfernen, sofern es weiterhin ausschließlich die automatisch erzeugten Dateien
`task_plan.md`, `findings.md`, `progress.md` enthält. Nie pauschal fremde
untracked Dateien löschen.

### Schritt B — Dokumentqualität prüfen

Prüfe insbesondere:

- Jeder Sub-Slice enthält Ziel, Nicht-Ziele, konkrete Dateien/Komponenten,
  Abhängigkeiten, File-Ownership, Slice-6-Grenze, TDD-/Teststrategie,
  Accessibility-Gates, Migration/Rollback, Akzeptanzkriterien und PR-Schnitt.
- IA-Matrix nutzt ausschließlich `wire | implement MVP | hide | defer`.
- Keine Aussage behauptet, dass `v4/forms/ModelPicker.vue` oder
  `LlmProfilePicker.vue` verwaist sei.
- Mock-Routing wird als Orphan-Unterbaum, nicht als produktive Route bezeichnet.
- CSS-Graphify-Grenze ist dokumentiert.
- Keine produktive Implementierung wird in diesem PR vorgeschoben.

### Schritt C — Markdown-Pfade und Links prüfen

Mindestens:

```bash
git diff --check
```

Zusätzlich alle Markdown-Links in den drei geänderten Dateien auf existierende
lokale Ziele prüfen. Ein kleines read-only Script ist erlaubt. Die bekannte,
bereits bestehende kaputte Referenz in `docs/ui/design-language-v4.md` ist kein
neuer Link dieses PRs und darf das Ergebnis nur als dokumentiertes Risiko
erscheinen lassen.

### Schritt D — Pflicht-Gate

```bash
bash scripts/pre-push-gate.sh
```

Das Gate vollständig laufen lassen. Output über context-mode oder in eine
Datei routen und nur Exit-Code/Fehlerzusammenfassung in den Agentenkontext
nehmen. Keine Auto-Fix-Schleife. Bei Fehlern erst Ursache klassifizieren:

1. eigene Dokuänderung;
2. bekannte Baseline-/Umgebungsabweichung;
3. neue echte Regression.

Nur Kategorie 1 im Slice-PR beheben. Kategorie 2/3 transparent dokumentieren
und nicht durch Produktcodeänderungen kaschieren.

### Schritt E — Graphify aktualisieren

Der Benutzer verlangte Graphify nach den Änderungen. Der Graph liegt im
Haupt-Worktree und ist code-only; Dokuänderungen erzeugen deshalb kein
AST-Delta. Trotzdem den Update-Check ausführen und das Ergebnis dokumentieren:

```bash
graphify update /Volumes/T7/Projekte/agora
```

Keinen Graph-Artefakt in den Slice-PR stagen. Falls der Befehl wegen des
untracked Prompt-Packs oder eines fehlenden Manifests ungeeignet ist, nicht
forcieren. Stattdessen den vorhandenen Graph unverändert lassen und im PR
ehrlich festhalten: frischer Basisgraph gebaut, Docs-only-Diff, kein Codegraph-
Delta.

### Schritt F — Commit und Push

Nur die drei Doku-Dateien explizit stagen:

```bash
git add \
  docs/epics/onboarding-provider-unification/slice-7-subplan.md \
  docs/epics/onboarding-provider-unification/HANDOVER.md \
  docs/epics/onboarding-provider-unification/slice-7-0-agent-handover.md
```

Vor Commit nochmals `git diff --cached --check` und Scope prüfen.

Empfohlener Commit:

```text
docs(onboarding): plan slice 7 golden gate rollout
```

Dann normal pushen:

```bash
git push -u origin codex/onboarding-slice-7-prep
```

Keine Bypass- oder Force-Flags.

### Schritt G — PR erstellen

Empfohlener Titel:

```text
docs(onboarding): plan Slice 7 Golden Gate rollout
```

Base: `main`

PR-Body muss enthalten:

```markdown
## Summary
- documents the verified Design-v4 and information-architecture baseline
- splits Slice 7 into independently mergeable implementation PRs
- defines Slice-6 ownership boundaries and accessibility gates

## Evidence
- fresh Graphify code graph: 17,951 nodes / 33,528 edges
- import/impact proof for settings-classic, legacy pickers and mock routing
- static CSS import proof for tokens-v3.css and states.css

## Validation
- git diff --check
- Markdown link/path check
- bash scripts/pre-push-gate.sh
- Graphify update/check: docs-only, no codegraph delta

## Scope
Docs only. No production UI, routing or contract changes.
```

PR standardmäßig als Draft anlegen, außer die Repository-Konvention verlangt
für gesichtete Docs-PRs direkt „ready for review“. Vor Gemini-Sichtung muss der
PR reviewbar sein.

### Schritt H — GitHub-Gemini-Sichtung

1. Repository-/PR-Runbook lesen:
   `docs/runbooks/pr-workflow.md`.
2. Genau den dort dokumentierten Mechanismus für GitHub Gemini verwenden.
3. Kein Gemini-Sidecar und keinen Chat-Schlüssel verwenden.
4. Nach Anforderung die vorgeschriebene Wartezeit einhalten und PR-Kommentare,
   Reviews und Checks abrufen.
5. Findings klassifizieren:
   - korrekt und im Scope: Doku anpassen, fokussiert validieren, committen,
     pushen;
   - falsch/überholt: mit konkretem Code-/Graph-Nachweis begründet beantworten;
   - außerhalb Scope: offen dokumentieren, nicht als ungefragten Refactor
     umsetzen.
6. Nach Änderungen die Sichtung erneut prüfen, bis keine berechtigten Findings
   offen sind.
7. Nicht mergen.

## 8. Erwarteter Abschlussbericht

Der Abschlussbericht an den Benutzer muss knapp, aber vollständig enthalten:

- PR-URL;
- Basis-Commit;
- vorgeschlagene Reihenfolge:
  `7.1 → 7.2 → 7.3 → 7.4 → 7.7 → 7.8` sowie paralleler
  Picker-Pfad `7.6 → 7.9a → 7.9b → 7.9c`;
- Konfliktflächen mit Slice 6:
  `HeroNewRun`, Step 2, Persona-/Run-Vertrag, Persona-i18n und E2E-Werte;
- Empfehlung: 7.1 als erster Implementierungs-PR;
- Verifikationsstatus jedes Gates;
- Gemini-Sichtungsstatus und bearbeitete Findings;
- offene Risiken: stale Design-Doku, kaputte historische Design-v4-Referenz,
  CSS-Regressionsradius, Dynamic-Import-Grenze von Graphify, Slice-6-Rebase;
- explizit: PR nicht gemergt.

## 9. Stop-Bedingung

Stoppe erst, wenn:

- der Docs-only-PR existiert;
- Branch und PR aktuell sind;
- alle berechtigten GitHub-Gemini-Findings bearbeitet wurden;
- der PR ungemergt bleibt;
- der Benutzer den Abschlussbericht erhalten hat.

Keine Implementierung von 7.1 oder später in diesem Auftrag beginnen.
