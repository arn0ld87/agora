# Issue #850: Event-Wiring der v4-Step-Views

**Datum:** 2026-07-22  
**Issue:** [#850](https://github.com/arn0ld87/agora/issues/850)  
**Status:** Freigegeben

## Ziel

Die durch PR #849 getrennten v4-Step-Wrapper übernehmen wieder die Navigationsereignisse ihrer eingebetteten Step-Komponenten. Dadurch funktionieren die Vorwärts- und Rückwärtsübergänge zwischen Graph Build, Persona-Setup und Simulation wieder über die kanonischen v4-Routen.

## Scope

Geändert werden ausschließlich:

- `frontend/src/views/v4/steps/StepGraphBuildView.vue`
- `frontend/src/views/v4/steps/StepEnvSetupView.vue`
- `frontend/src/views/v4/steps/StepSimulationView.vue`
- deren fokussierte Specs unter `frontend/src/views/v4/steps/__tests__/`
- `CHANGELOG.md`

Ausgeschlossen bleiben:

- `add-log`- und `update-status`-Verdrahtung
- `StepReportView.vue` und `StepInteractionView.vue`
- Änderungen an den eingebetteten Step-Komponenten
- ein gemeinsames Navigation-Composable oder anderer Wrapper-Refactor
- `PipelineStepper`-Synchronisierung

## Gewählter Ansatz

Jeder Wrapper erhält explizite lokale Event-Handler. Die Handler übersetzen genau ein Child-Event in genau einen benannten `router.push(...)`-Aufruf. Es entsteht keine neue Abstraktionsschicht und kein zusätzlicher globaler Zustand.

Verworfene Alternativen:

1. Ein echter Memory-Router in allen fokussierten Specs würde die Router-Auflösung integrierter prüfen, aber Routendefinitionen duplizieren und den Testaufbau verbreitern. Die kanonischen Routen werden bereits separat geprüft.
2. Ein gemeinsames Navigation-Composable würde drei kleine Handler zentralisieren, wäre jedoch ein ausdrücklich ausgeschlossener Wrapper-Refactor.

## Architektur und Übergänge

### `StepGraphBuildView.vue`

`Step1GraphBuild` erhält `@next-step="handleNextStep"`.

`handleNextStep` navigiert zu:

```ts
{
  name: 'StepEnvSetup',
  params: { projectId: props.projectId },
}
```

`Step1GraphBuild` emittiert dieses Event derzeit nicht aktiv. Die Verdrahtung ist absichtlich vorhanden, damit der Wrapper seinen deklarierten Übergang vollständig abbildet, ohne die Child-Komponente in diesem Slice zu ändern.

### `StepEnvSetupView.vue`

Die View bindet `useRouter()` ein. `Step2EnvSetup` erhält:

- `@next-step="handleNextStep"`
- `@go-back="handleGoBack"`

Das echte `next-step`-Payload ist direkt aufgebaut:

```ts
{
  simulationId: string,
  maxRounds?: number,
  simulationDays?: number,
}
```

`handleNextStep` liest ausschließlich `simulationId` und navigiert zu:

```ts
{
  name: 'StepSimulation',
  params: { simulationId },
  query: { projectId: props.projectId },
}
```

Die `projectId` wird zusätzlich als `query`-Parameter mitgegeben, damit die Simulation-View sie beim Rückwärtsübergang aus `route.query.projectId` auflösen kann — die `StepSimulation`-Route selbst führt nur `simulationId`, nicht `projectId`. Fehlt eine nichtleere `simulationId`, findet keine Navigation statt. Weitere Payload-Felder bleiben Eigentum der eingebetteten Simulation-Komponente und werden vom Wrapper nicht persistiert oder transformiert.

`handleGoBack` navigiert zu:

```ts
{
  name: 'StepGraphBuild',
  params: { projectId: props.projectId },
}
```

### `StepSimulationView.vue`

`Step3Simulation` erhält `@go-back="handleGoBack"`.

`handleGoBack` navigiert zu:

```ts
{
  name: 'StepEnvSetup',
  params: { projectId: <aus route.query.projectId>,
}
```

Dabei liest der Handler `projectId` aus `route.query.projectId` (von `StepEnvSetupView.handleNextStep` als `query`-Parameter gesetzt). Die `StepSimulation`-Route führt selbst kein `projectId`; die Auflösung über die Query ist Voraussetzung für die Rückwärtsnavigation. Fehlt die Query oder ist sie leer, findet keine Navigation statt.

Die vorhandene Tab-Navigation und die interne Report-Navigation von `Step3Simulation` bleiben unverändert.

## Datenfluss und Fehlerverhalten

1. Eine eingebettete Step-Komponente emittiert `next-step` oder `go-back`.
2. Der Wrapper nimmt das Event lokal entgegen.
3. Der Wrapper baut eine benannte Vue-Router-Location mit dem für die Zielroute erwarteten Parameter.
4. Vue Router aktualisiert URL und Ziel-View.

Die Wrapper erzeugen keine Logs, Statusänderungen oder neuen Fehlerzustände. Ein ungültiges `next-step`-Payload ohne `simulationId` wird verworfen, damit keine unvollständige Route und kein Router-Warning entsteht.

## TDD-Strategie

### `StepGraphBuildView.spec.ts`

Die vorhandene fokussierte Spec wird um einen Test ergänzt:

- Child emittiert `next-step`.
- Erwartet wird `router.push({ name: 'StepEnvSetup', params: { projectId } })`.

### `StepEnvSetupView.spec.ts`

Neue fokussierte Spec mit drei Fällen:

1. `next-step` mit `{ simulationId: 'sim_x' }` navigiert zu `StepSimulation` mit `simulationId: 'sim_x'`.
2. `next-step` ohne gültige `simulationId` navigiert nicht.
3. `go-back` navigiert zu `StepGraphBuild` mit dem `projectId` der View.

### `StepSimulationView.spec.ts`

Neue fokussierte Spec:

- `go-back` navigiert zu `StepEnvSetup` und mappt `props.simulationId` auf den Route-Parameter `projectId`.

Die fokussierten Specs stubben die eingebetteten Step-Komponenten und `useRouter()`. Sie prüfen den exakten Router-Aufruf. `StepWrapperViews.spec.ts` bleibt als breite Mount- und Shell-Smoke-Suite unverändert.

## Verifikation

Die Prüfungen laufen in dieser Reihenfolge:

1. Neue und erweiterte fokussierte Specs zunächst rot ausführen.
2. Nach der Implementierung dieselben Specs grün ausführen.
3. Gesamte Frontend-Test-Suite: `cd frontend && bun run test`.
4. Frontend-Typecheck/Lint/Build-Checks: `cd frontend && bun run check`.
5. CI-Mirror: `bash scripts/pre-push-gate.sh frontend`.
6. Browser-Smoke für Vorwärts- und Rückwärtsnavigation, soweit der lokale Stack verfügbar ist.
7. Read-only Review des Issue-Commits vor Veröffentlichung.

## Akzeptanzinterpretation

Das erste Acceptance Criterion des Issues nennt für den Übergang von `StepGraphBuildView` die URL `/v4/graph-build/<id>`, obwohl der konkret spezifizierte Handler zu `StepEnvSetup` und damit `/v4/env-setup/<id>` navigiert. Für diesen Slice sind die expliziten Handler-Mappings und die dazugehörige TDD-Strategie maßgeblich. Es wird keine zusätzliche Route oder abweichende Navigation eingeführt.
