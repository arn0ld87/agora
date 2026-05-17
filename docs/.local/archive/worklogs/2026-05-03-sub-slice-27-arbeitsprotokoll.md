# Sub-Slice 27 — Composables .js → .ts Migration (Layer 6, Refs #72)

Datum: 2026-05-03
Branch: `feat/layer-6-task-20-composables-ts`

## Ziel

Migration aller 10 JavaScript-Composables in `frontend/src/composables/` auf TypeScript
sowie Umbenennung der 5 zugehörigen Test-Dateien auf `.spec.ts`.

## Migrierte Composables

| Modul | Zeilen (TS) | Wesentliches typisiert |
|---|---|---|
| `useEventStream.ts` | 94 | `UseEventStreamReturn`, `SimulationId`-Union-Typ (Ref/Getter/string), `StreamHandlers` aus `api/stream.ts` |
| `useGraphRender.ts` | 420 | `UseGraphRenderArgs`, `UseGraphRenderReturn`, `EntityTypeEntry`, D3-Internals via `D3Selection`/`D3Simulation any`-Aliases mit `// reason:`-Kommentaren |
| `useIncrementalLogPolling.ts` | 99 | Generics `TRaw`/`TEntry`, `LogPage<T>`, `StickyScrollBridge`, `UseIncrementalLogPollingReturn<TEntry>`, `UsePollingReturn` importiert aus `usePolling.ts` |
| `usePersonaReview.ts` | 161 | `IssueSeverity`, `IssueSeverityEntry`, `QualityEnvelope`, `ProfileEnvelope`, alle API-Typen aus `api/simulation.ts` importiert; Service-Envelope-Mismatch via `as unknown as` mit `// reason:` |
| `usePolling.ts` | 82 | `UsePollingOptions`, `UsePollingStartOptions`, `UsePollingReturn`, `ReturnType<typeof setInterval>` |
| `useStickyScroll.ts` | 133 | `UseStickyScrollReturn`, `Ref<HTMLElement | null>`, rAF-Fallback-Typ `(cb: () => void) => ...` |
| `useSystemLog.ts` | 46 | `SystemLogEntry`, `UseSystemLogOptions`, `UseSystemLogReturn`, `Ref<SystemLogEntry[]>` |
| `useTheme.ts` | 79 | `ThemeValue = 'light' | 'dark'`, `UseThemeReturn`, `Ref<ThemeValue>` |
| `useWorkspaceMode.ts` | 74 | `WorkspaceMode`, `WorkspaceModeOption`, `PanelStyle`, `UseWorkspaceModeReturn`, `ComputedRef<PanelStyle>` |
| `useWorkspaceStatus.ts` | 60 | `StatusMapEntry`, `UseWorkspaceStatusOptions`, `UseWorkspaceStatusReturn`, `ComputedRef<string>` |

## Migrierte Test-Dateien

| Datei | Anpassungen |
|---|---|
| `useEventStream.spec.ts` | `mountStream` typisiert mit `UseEventStreamReturn`; Mock-Factory `...args: any[]` mit `// reason:`; `capturedHandlers: any` mit `// reason:` |
| `useIncrementalLogPolling.spec.ts` | `parseLine = (raw: string) => ...` |
| `usePolling.spec.ts` | `mountPolling` typisiert mit `UsePollingReturn`, `UsePollingOptions`; `mockResolvedValue(undefined)`; `resolveTask?: (v: any) => void` mit `// reason:` |
| `useStickyScroll.spec.ts` | `makeContainer` Destrukturierung typisiert; `nextFrame(): Promise<void>`; `containerRef: Ref<HTMLElement | null>` |
| `useWorkspaceStatus.spec.ts` | `mountStatus` typisiert mit `UseWorkspaceStatusOptions`, `UseWorkspaceStatusReturn`; i18n-Mock `(key: string) => ...` |

## Importierte Types aus api/*

| Composable | Import |
|---|---|
| `useEventStream.ts` | `StreamHandlers` aus `../api/stream` |
| `usePersonaReview.ts` | `ProfileRecord`, `approveSimulationProfile`, `editSimulationProfile`, `getSimulationProfilesQuality`, `rejectSimulationProfile` aus `../api/simulation` |
| `useIncrementalLogPolling.ts` | `UsePollingReturn` aus `./usePolling` |

## Besonderheiten

### D3-Typen (useGraphRender)

D3 v7 bringt keine eigenen `.d.ts`-Dateien mit — sie müssen über `@types/d3` bezogen werden.
Da `@types/d3` nicht in `devDependencies` war, wurde es hinzugefügt (`npm install --save-dev @types/d3`).

Die internen D3-Selection- und Simulation-Generics sind mit den JSDoc-`@typedef`-Typen aus
`graphPanelData.js` (`checkJs: false`) nicht direkt kompatibel. Alle D3-internen Aufrufe
(`forceSimulation`, `zoom`, `drag`) sind daher mit `any`-Casts versehen, jeweils mit
`// reason:`-Kommentar. Die **öffentliche Composable-API** (`UseGraphRenderArgs`,
`UseGraphRenderReturn`) ist vollständig typisiert.

### Service-Envelope-Mismatch (usePersonaReview)

Die API-Funktion `getSimulationProfilesQuality` ist in `api/simulation.ts` als
`Promise<ProfileQualityResponse>` typisiert (unwrappter Typ). Zur Laufzeit liefert der
Axios-Interceptor aber das rohe Envelope-Body-Objekt (mit `success`, `data`, ...).
Das Composable prüft `res?.success` — deshalb wird via `as unknown as QualityEnvelope`
gecastet, mit `// reason:`-Kommentar. Dies ist eine pre-existing Mismatch in der API-Schicht.

### .js-Imports in Konsumenten

Zwei Vue-Komponenten importierten `useTheme` mit expliziter `.js`-Endung:
- `frontend/src/App.vue`
- `frontend/src/components/ui/ThemeToggle.vue`

Beide wurden auf endungslosen Import aktualisiert (TS-Resolver findet `.ts` automatisch).

## Verifikation

- `npm run check` (vue-tsc + vitest + vite build): grün, 137 Tests, 16 Dateien
- `rg -n ".composables/use.*.js"`: keine Treffer
- `uv run pytest -x -q`: 1282 passed, 9 skipped
