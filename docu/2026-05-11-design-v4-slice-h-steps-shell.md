# Design-v4 Slice H — Pipeline-Steps AppShell-Wrapper

**Datum:** 2026-05-11  
**Branch:** `feat/design-v4-slice-h-steps`  
**Worktree:** `/private/tmp/agora-v4-steps`  
**Basis:** Slice A (Tokens) + Merge von Slice B, C, D

---

## Ziel

Die 5 Pipeline-Step-Komponenten (Step1–Step5) erhalten AppShell-Wrapper-Views
fuer das `/v4/*`-Routing. Die Step-Komponenten selbst bleiben unverandert
(v2-typografiert) — ihre Inhalts-Migration ist ein eigener Folge-Slice.

---

## File-Map

### Neue Dateien

| Datei | Beschreibung |
|---|---|
| `frontend/src/components/v4/steps/PipelineStepper.vue` | Horizontaler 5-Step-Progress-Indicator (48px, done/active/future) |
| `frontend/src/components/v4/steps/__tests__/PipelineStepper.spec.ts` | 6 Specs fur PipelineStepper |
| `frontend/src/views/v4/steps/StepGraphBuildView.vue` | AppShell-Wrapper fur Step1GraphBuild |
| `frontend/src/views/v4/steps/StepEnvSetupView.vue` | AppShell-Wrapper fur Step2EnvSetup |
| `frontend/src/views/v4/steps/StepSimulationView.vue` | AppShell-Wrapper fur Step3Simulation |
| `frontend/src/views/v4/steps/StepReportView.vue` | AppShell-Wrapper fur Step4Report |
| `frontend/src/views/v4/steps/StepInteractionView.vue` | AppShell-Wrapper fur Step5Interaction |
| `frontend/src/views/v4/steps/__tests__/StepWrapperViews.spec.ts` | 20 Smoke-Specs fur alle 5 Wrapper-Views |

### Gepatchte Dateien

| Datei | Anderung |
|---|---|
| `frontend/src/router/index.ts` | 5 neue `/v4/*`-Routen ans Ende angehangt (keine bestehenden Routen verandert) |

---

## Routing-Eintrage

Alle neuen Routen nutzen `/v4/`-Prefix um Kollisionen mit bestehenden Routen
(Slice F und Legacy) zu vermeiden.

```
/v4/graph-build/:projectId   → StepGraphBuildView   (name: StepGraphBuild)
/v4/env-setup/:projectId     → StepEnvSetupView      (name: StepEnvSetup)
/v4/simulation/:simulationId → StepSimulationView    (name: StepSimulation)
/v4/report/:reportId         → StepReportView        (name: StepReport)
/v4/interaction/:reportId    → StepInteractionView   (name: StepInteraction)
```

Alle Routen nutzen `props: true` fur direkte Prop-Injection.

---

## Komponenten-Mapping

| Wrapper-View | Step-Komponente | currentStep | Breadcrumbs |
|---|---|---|---|
| `StepGraphBuildView` | `Step1GraphBuild` | 1 | Runs / projectId / Graph Build |
| `StepEnvSetupView` | `Step2EnvSetup` | 2 | Runs / projectId / Personas |
| `StepSimulationView` | `Step3Simulation` | 3 | Runs / simulationId / Simulation |
| `StepReportView` | `Step4Report` | 4 | Runs / reportId / Report |
| `StepInteractionView` | `Step5Interaction` | 5 | Runs / reportId / Interaktion |

---

## PipelineStepper

- 5 Schritte: Upload, Personas, Simulation, Report, Interaktion
- Hohe: 48px, kompakter Linearstil (Apple-Progress-Indicator-artig)
- Zustande: `done` (Haken + Accent-Blau), `active` (Nummer + Accent-Blau), `future` (Nummer + Grau)
- Done-Schritte sind klickbar (emit `navigate`)
- Barrierefrei: `aria-current="step"`, `aria-label` pro Knoten

---

## Bundle-Delta

Lazy-Chunks pro Step-View (Produktions-Build):

| Chunk | JS | gzip |
|---|---|---|
| `StepGraphBuildView` | 0.53 kB | 0.36 kB |
| `StepEnvSetupView` | 0.59 kB | 0.39 kB |
| `StepSimulationView` | 0.60 kB | 0.37 kB |
| `StepReportView` | 0.56 kB | 0.37 kB |
| `StepInteractionView` | 0.59 kB | 0.39 kB |
| `PipelineStepper` (shared) | 17.28 kB | 4.71 kB |

---

## Test-Counts

| Scope | Vorher | Nachher | Delta |
|---|---|---|---|
| Gesamt Frontend | 591 | 617 | +26 |
| PipelineStepper.spec.ts | 0 | 6 | +6 |
| StepWrapperViews.spec.ts | 0 | 20 | +20 |

---

## Bekannte Limits

1. **Step-Inhalte v2-typografiert**: Die Step*.vue-Komponenten selbst sind v2-Design.
   Ihre AppShell-interne Typografie-Migration ist ein eigener Folge-Slice.

2. **Step1GraphBuild hat kein `projectId`-Prop**: Die Komponente empfangt
   `projectData`/`graphData` via Pinia-Store (nicht via Prop). Der Wrapper
   ubergibt daher keinen `projectId`-Prop — die ID erscheint nur im Breadcrumb.

3. **Step2EnvSetup `simulationId`-Prop**: Der Wrapper-Route-Param heisst `projectId`
   (aus Konsistenz mit Schritt 1), wird aber als `simulationId` an Step2EnvSetup
   weitergegeben. Umbenennung beim Inhalts-Slice koordinieren.

4. **Sidebar active="runs"**: Alle Step-Views aktivieren via AppShell-auto-detect
   keinen eigenen Sidebar-Eintrag (Route-Namen starten mit `Step`, kein Match).
   Ein explizites `active`-Prop-Override oder eine Sidebar-Erweiterung um
   "Wizard"-Eintrage ist im Integrations-Slice zu diskutieren.

5. **`Sidebar.vue` nicht angefasst**: Die Sidebar-Erweiterung um Pipeline-Items
   ist Slice F / Integrations-Lead-Aufgabe.

---

## Merges

```
merge(design-v4): pull slice B into steps worktree
merge(design-v4): pull slice C into steps worktree
merge(design-v4): pull slice D into steps worktree
```
