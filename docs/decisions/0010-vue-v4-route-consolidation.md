# ADR-0010: Vue-v4-Referenzrouten und Deep-Link-Lebenszyklus

- Status: **Accepted** (2026-07-28, im Zuge von #839 — alle referenzierten Umsetzungs-Tickets #830–#838, #890, #922 sind geschlossen, der produktive Router entspricht der hier festgehaltenen Entscheidungsmatrix)
- Datum: 2026-07-22
- Basis: `origin/main` @ `35929dbe9205829dbfc42cecff32f5d406c84807`
- Entscheidung: [Issue #830](https://github.com/arn0ld87/agora/issues/830)
- Parent: [Issue #829](https://github.com/arn0ld87/agora/issues/829)
- Tracking: #760, #758
- Release-Ziel: 0.9.0 Stability Beta

Dieses ADR hält die stabile Routen- und Lebenszyklusentscheidung fest. Es ist
**keine Task- oder Scopequelle**: ausführbare Arbeit, Akzeptanzkriterien und
Fortschritt bleiben ausschließlich in GitHub Issues. In #830 wird kein Code
geändert.

## Ausführungsstatus (2026-07-28)

Die Entscheidungsmatrix unten ist eine Zeitpunktaufnahme vom Erstellungsdatum
(2026-07-22) und wird als Entscheidungsprotokoll nicht nachträglich
umgeschrieben. Stand 2026-07-28 sind alle für `0.9.0` vorgesehenen Löschungen
vollzogen: `MainView.vue`, `SimulationView.vue`, `SimulationRunView.vue`,
`ReportView.vue`, `InteractionView.vue`, `SettingsView.vue`,
`SettingsUsersTeamsView.vue` und `AppShellDemoView.vue` existieren nicht mehr;
die zugehörigen Routen sind reine Redirects ohne Komponente. `Home.vue`
besteht wie geplant weiter (Entfernungsrelease `1.0.0`). Verifiziert in
[#760](https://github.com/arn0ld87/agora/issues/760)/[#839](https://github.com/arn0ld87/agora/issues/839)
gegen `frontend/src/router/index.ts` als Tatsachenquelle — dort nachschlagen
für den Istzustand, nicht in der Matrix unten.

## Kontext

Der produktive Router ist die Tatsachenquelle für den Istzustand. Vue-v4 und
die klassischen Prozessrouten verwenden teilweise dieselben fachlichen
Step-Module, besitzen aber unterschiedliche Route-Wrapper und teils eigene
Orchestrierung. Die Entscheidung ist nach Umsetzung über mehrere Routen und
Consumer schwer umkehrbar, ohne diesen Kontext überraschend und das Ergebnis
eines echten Trade-offs zwischen Deep-Link-Kompatibilität, Altlastenabbau und
dem Erhalt geteilter Module. Damit erfüllt sie die ADR-Kriterien.

- [`frontend/src/router/index.ts`](../../frontend/src/router/index.ts#L1) ist
  die SSoT für alle hier referenzierten Routen.
- #829 und seine ausführbaren Kind-Issues bleiben die kanonischen Taskquellen.
- Wrapper-/Consumer-Behauptungen werden direkt gegen den aktuellen Code belegt.

## Glossar

- **Referenzroute**: Die einzige produktive Route für eine fachliche Hauptfunktion in `0.9.0`.
- **Wrapper-View**: Routenkomponente, die eine fachliche Step-Komponente in
  eine Shell einbettet. Ein geteilter Step-Import beweist noch keine
  Funktionsparität; Wrapper-eigene Orchestrierung muss vor einer Löschung
  inventarisiert und migriert sein.
- **Geteilte Step-Komponente**: Fachliche Komponente (`Step1GraphBuild`,
  `Step2EnvSetup`, `Step3Simulation`, `Step4Report`, `Step5Interaction`),
  die von klassischen und v4-Routenkomponenten importiert wird. Sie bleibt
  erhalten, solange ein produktiver Consumer existiert.
- **Produktive Route**: Aktuell erreichbarer Pfad, der reale Funktionalität ausliefert.
- **Designreferenz**: Code mit gestalterischer Exploration, der **nicht** produktiv geroutet werden darf. Bleibt im Repo, ohne Route.
- **Redirect**: Expliziter Vue-Router-Redirect auf eine Referenzroute. Im
  aktuellen Router werden keine `alias`-Einträge verwendet.
- **Delete**: Direkte Routen- oder Datei-Löschung mit konkretem Release.
- **Retain**: Datei oder Route bleibt wegen belegter produktiver Consumer.
- **Deep-Link-Kompatibilität**: Unterstützte eingehende Pfade bleiben vor ihrer
  endgültigen Entfernung mindestens ein Release als Redirect erhalten.
  Ausnahmen benötigen begründetes 404-Verhalten und einen Router-Test.
- **Funktionale Parität**: Muss Parameter-Mapping, Wrapper-eigene Orchestrierung
  und Router-Verhalten abdecken. Ein geteilter Step-Import allein reicht nicht.

## Entscheidungsmatrix

Spalten: Pfad/View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis.

### Produktive Routen (Hauptpfade)

| Pfad / View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis |
|---|---|---|---|---|---|---|---|---|---|
| `/` | — (Router-Default) | alle Browser-Sessions | bestehender Redirect | redirect | `/dashboard` | — | nie | Dauerhafter Root-Redirect; kein Vue-Router-Alias | [router/index.ts:8-11](../../frontend/src/router/index.ts#L8) |
| `/dashboard` | `DashboardView.vue` (v4) | AppShell + v4-Dashboard-Karten | produktive Route | canonical | — | — | nie | Default-Entry nach 0.9.0 | [router/index.ts:21-25](../../frontend/src/router/index.ts#L21); [DashboardView.vue:9-19](../../frontend/src/views/v4/DashboardView.vue#L9) |
| `/v4/graph-build/:projectId` | `StepGraphBuildView.vue` (v4) | AppShell + Step1GraphBuild | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Referenz für Graph-Build | [router/index.ts:151-156](../../frontend/src/router/index.ts#L151); [StepGraphBuildView.vue:24-29](../../frontend/src/views/v4/steps/StepGraphBuildView.vue#L24) |
| `/v4/env-setup/:projectId` | `StepEnvSetupView.vue` (v4) | AppShell + Step2EnvSetup | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Referenz für Env-Setup | [router/index.ts:158-162](../../frontend/src/router/index.ts#L158); [StepEnvSetupView.vue:23-28](../../frontend/src/views/v4/steps/StepEnvSetupView.vue#L23) |
| `/v4/simulation/:simulationId` | `StepSimulationView.vue` (v4) | AppShell + Step3Simulation | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Referenz für Run-Konfiguration + Live-Tab | [router/index.ts:164-168](../../frontend/src/router/index.ts#L164); [StepSimulationView.vue:42-49](../../frontend/src/views/v4/steps/StepSimulationView.vue#L42) |
| `/v4/simulation/:simulationId/feed` | `StepSimulationFeedView.vue` (v4) | FeedColumn, RedditThread, TwitterPost, SimulationPulseBar | produktive Route (Feed-View, nicht AppShell-Wrapper) | canonical | — | — | nie | Dedizierte Feed-Ansicht ohne 1:1-Klassik-Äquivalent; importiert KEIN AppShell und KEIN Step3Simulation | [router/index.ts:170-174](../../frontend/src/router/index.ts#L170); [StepSimulationFeedView.vue:11-17](../../frontend/src/views/v4/steps/StepSimulationFeedView.vue#L11) |
| `/v4/report/:reportId` | `StepReportView.vue` (v4) | AppShell + Step4Report | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Referenz für Report-Ansicht | [router/index.ts:176-180](../../frontend/src/router/index.ts#L176); [StepReportView.vue:23-28](../../frontend/src/views/v4/steps/StepReportView.vue#L23) |
| `/v4/interaction/:reportId` | `StepInteractionView.vue` (v4) | AppShell + Step5Interaction | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Referenz für Interaktion | [router/index.ts:182-186](../../frontend/src/router/index.ts#L182); [StepInteractionView.vue:19-23](../../frontend/src/views/v4/steps/StepInteractionView.vue#L19) |
| `/v4/compare/:simulationId` | `CompareView.vue` (v4) | AppShell + BranchComparePanel | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Referenz für Branch-Compare | [router/index.ts:189-194](../../frontend/src/router/index.ts#L189); [CompareView.vue:28-32](../../frontend/src/views/v4/CompareView.vue#L28) |
| `/v4/history` | `HistoryView.vue` (v4) | AppShell + HistoryDatabase | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Referenz für Run-/Branch-Historie | [router/index.ts:195-199](../../frontend/src/router/index.ts#L195); [HistoryView.vue:1-19](../../frontend/src/views/v4/HistoryView.vue#L1) |
| `/runs` | `RunsAppShellView.vue` | AppShell + `RunsView.vue` | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Run-Liste produktiv | [router/index.ts:33-37](../../frontend/src/router/index.ts#L33); [RunsAppShellView.vue:1-17](../../frontend/src/views/v4/RunsAppShellView.vue#L1); [AppShellWrappers.spec.ts](../../frontend/src/views/__tests__/AppShellWrappers.spec.ts) |
| `/runs/:id` | `RunDetailAppShellView.vue` | AppShell + `RunDetailView.vue` | produktive Route (AppShell-Wrapper) | canonical | — | — | nie | Run-Detail produktiv | [router/index.ts:38-43](../../frontend/src/router/index.ts#L38); [RunDetailAppShellView.vue:1-26](../../frontend/src/views/v4/RunDetailAppShellView.vue#L1); [AppShellWrappers.spec.ts](../../frontend/src/views/__tests__/AppShellWrappers.spec.ts) |
| `/onboarding` | `OnboardingView.vue` | Welcome + Profil + Provider + Modelle | produktive Route | canonical | — | — | nie | Resumierbares Onboarding | [router/index.ts:46-50](../../frontend/src/router/index.ts#L46) |
| `/settings/general` | `SettingsGeneralView.vue` | AppShell + AiModelPicker + LlmProfileManager | produktive Route | canonical | — | — | nie | Allgemeine Einstellungen | [router/index.ts:58-62](../../frontend/src/router/index.ts#L58) |
| `/settings/integrations` | `SettingsIntegrationsView.vue` | AppShell + SettingsSectionPanel | produktive Route | canonical | — | — | nie | Integrationen | [router/index.ts:63-67](../../frontend/src/router/index.ts#L63) |
| `/settings/profile` | `SettingsProfileView.vue` | AppShell + ProfileForm | produktive Route | canonical | — | — | nie | Benutzer-Profil | [router/index.ts:68-72](../../frontend/src/router/index.ts#L68) |
| `/settings/api-keys` | `SettingsApiKeysView.vue` | AppShell + Key-Verwaltung | produktive Route | canonical | — | — | nie | API-Keys | [router/index.ts:80-85](../../frontend/src/router/index.ts#L80) |
| `/settings/audit-logs` | `SettingsAuditLogsView.vue` | AppShell + ComingSoonCard | produktive Route | canonical | — | — | nie | Audit-Logs (geplant) | [router/index.ts:86-91](../../frontend/src/router/index.ts#L86) |
| `/settings/llm-routing` | `Settings/LlmRoutingView.vue` | AppShell + Routing UI | produktive Route | canonical | — | — | nie | LLM-Routing | [router/index.ts:92-97](../../frontend/src/router/index.ts#L92) |
| `/settings/llm-providers` | `Settings/LlmProvidersView.vue` | AppShell + Provider-Liste | produktive Route | canonical | — | — | nie | LLM-Provider | [router/index.ts:99-103](../../frontend/src/router/index.ts#L99); [LlmProvidersView.vue:23-37](../../frontend/src/views/Settings/LlmProvidersView.vue#L23) |
| `/settings/embedding` | `Settings/EmbeddingConfigurationsView.vue` | AppShell + Embedding-Configs | produktive Route | canonical | — | — | nie | Embedding-Configs | [router/index.ts:106-111](../../frontend/src/router/index.ts#L106) |
| `/:pathMatch(.*)*` | `NotFoundView.vue` | Catch-all | produktive Route | canonical | — | — | nie | Standard-404 | [router/index.ts:210-214](../../frontend/src/router/index.ts#L210) |

### Redirect-Routen (Deep-Link-Kompatibilität)

| Pfad / View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis |
|---|---|---|---|---|---|---|---|---|---|
| `/v4/dashboard` | — | UX-Konsistenz | bestehender Redirect | redirect | `/dashboard` | — | 1.0.0 | Kompatibilitäts-Redirect; kein Vue-Router-Alias | [router/index.ts:27-30](../../frontend/src/router/index.ts#L27) |
| `/settings` | — | Marketing-/Landing-Traffic | bestehender Redirect | redirect | `/settings/general` | — | nie | Dauerhafter Settings-Einstieg; kein Vue-Router-Alias | [router/index.ts:54-57](../../frontend/src/router/index.ts#L54) |
| `/settings/users-teams` | `SettingsUsersTeamsView.vue` (Datei vorhanden, nicht im Router) | verwaiste Datei + Test-Mount | bestehender Redirect | redirect | `/settings/profile` | — | 1.0.0 | Datei in 0.9.0 entfernen; Deep-Link-Redirect bis 1.0.0 erhalten | [router/index.ts:75-79](../../frontend/src/router/index.ts#L75); [SettingsUsersTeamsView.vue:1-27](../../frontend/src/views/Settings/SettingsUsersTeamsView.vue#L1); [SettingsSubViews.spec.ts:99](../../frontend/src/views/__tests__/SettingsSubViews.spec.ts#L99) |
| `/settings-classic` | — | Marketing-/Fallback-Traffic | bestehender Redirect | redirect | `/settings/general` | — | 1.0.0 (**Deferred**; nach Paritäts- und Deep-Link-Test) | Eindeutig auf 1.0.0 verschoben; bis dahin testabgedeckter Deep-Link | [router/index.ts:113-116](../../frontend/src/router/index.ts#L113) |

### Klassische Prozess-Routen (Route → REDIRECT, Wrapper-View → DELETE)

Die Route wird in 0.9.0 zum Redirect. Der bisherige Wrapper darf im selben
Release nur nach inventarisierter und migrierter Orchestrierung entfallen; der
Kompatibilitäts-Redirect bleibt bis 1.0.0.

| Pfad / View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis |
|---|---|---|---|---|---|---|---|---|---|
| `/process/:projectId` | `MainView.vue` | WorkspaceLayout-Familie + Step1GraphBuild + Step2EnvSetup | produktive Route (Wrapper-View) | redirect | `/v4/graph-build/:projectId` | bestehende ID → 1:1; `new` → erst Projekt/Graph erzeugen, dann konkrete ID | 1.0.0 | Kein reiner Router-Redirect für `new`: Pending-Upload-Orchestrierung aus MainView an einen geteilten Seam verlagern; erst danach Wrapper löschen | [router/index.ts:120-124](../../frontend/src/router/index.ts#L120); [MainView.vue:6-13](../../frontend/src/views/MainView.vue#L6) |
| `/simulation/:simulationId` | `SimulationView.vue` | WorkspaceLayout-Familie + Step2EnvSetup | produktive Route (Wrapper-View) | redirect | `/v4/env-setup/:projectId` | `:simulationId` → `:projectId` (Wert bleibt die Simulation-ID) | 1.0.0 | V4 benennt den Prop `projectId`, reicht ihn aber als `simulationId` an Step2EnvSetup; Mapping und Orchestrierung vor Redirect testen | [router/index.ts:126-130](../../frontend/src/router/index.ts#L126); [SimulationView.vue:6-17](../../frontend/src/views/SimulationView.vue#L6) |
| `/simulation/:simulationId/start` | `SimulationRunView.vue` | WorkspaceLayout-Familie + Step3Simulation | produktive Route (Wrapper-View) | redirect | `/v4/simulation/:simulationId` | `:simulationId` → `:simulationId` | 1.0.0 | In 0.9.0 nach geprüfter Orchestrierungsparität auf die v4-Run-Ansicht umstellen | [router/index.ts:132-136](../../frontend/src/router/index.ts#L132); [SimulationRunView.vue:6-12](../../frontend/src/views/SimulationRunView.vue#L6) |
| `/report/:reportId` | `ReportView.vue` | WorkspaceLayout-Familie + Step4Report | produktive Route (Wrapper-View) | redirect | `/v4/report/:reportId` | `:reportId` → `:reportId` | 1.0.0 | In 0.9.0 nach geprüfter Orchestrierungsparität auf die v4-Report-Ansicht umstellen | [router/index.ts:138-142](../../frontend/src/router/index.ts#L138); [ReportView.vue:6-18](../../frontend/src/views/ReportView.vue#L6) |
| `/interaction/:reportId` | `InteractionView.vue` | WorkspaceLayout-Familie + Step5Interaction | produktive Route (Wrapper-View) | redirect | `/v4/interaction/:reportId` | `:reportId` → `:reportId` | 1.0.0 | In 0.9.0 nach geprüfter Orchestrierungsparität auf die v4-Interaktion umstellen | [router/index.ts:144-148](../../frontend/src/router/index.ts#L144); [InteractionView.vue:6-18](../../frontend/src/views/InteractionView.vue#L6) |
| `/home` | `Home.vue` | HistoryDatabase + AiModelPicker + Pending-Upload-Flow | produktive Legacy-Route | redirect | `/dashboard` | — | 1.0.0 | In 0.9.0 zum Redirect umstellen; `Home.vue` separat löschen, nachdem der Dashboard-Upload-Flow verifiziert ist | [router/index.ts:13-18](../../frontend/src/router/index.ts#L13); [Home.vue:5-19](../../frontend/src/views/Home.vue#L5) |
| `/agora-2026` | `Agora2026View.vue` + `screens/` | isolierte Design-Exploration | opt-in Designroute | delete | — | — | 0.9.0 | Begründete Deep-Link-Ausnahme: kein unterstützter Produktpfad; nach Entfernung muss der Catch-all `NotFound` liefern und ein Router-Test dies belegen. Designcode bleibt ungeroutet erhalten | [router/index.ts:201-207](../../frontend/src/router/index.ts#L201); [Agora2026View.vue:3-4](../../frontend/src/views/agora2026/Agora2026View.vue#L3) |

### Wrapper-View-Dateien (zu löschende Dateien)

| Pfad / View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis |
|---|---|---|---|---|---|---|---|---|---|
| `frontend/src/views/MainView.vue` | wie oben | nur `/process/:projectId` | Wrapper-View mit Orchestrierung | delete | — | — | 0.9.0 | Erst nach Migration von `initProject`/`handleNewProject` samt Pending-Upload-, Ontologie- und Graph-Build-Ablauf | [MainView.vue:6-13](../../frontend/src/views/MainView.vue#L6) |
| `frontend/src/views/SimulationView.vue` | wie oben | nur `/simulation/:simulationId` | Wrapper-View | delete | — | — | 0.9.0 | s. o. | [SimulationView.vue:6-17](../../frontend/src/views/SimulationView.vue#L6) |
| `frontend/src/views/SimulationRunView.vue` | wie oben | nur `/simulation/:simulationId/start` | Wrapper-View | delete | — | — | 0.9.0 | s. o. | [SimulationRunView.vue:6-12](../../frontend/src/views/SimulationRunView.vue#L6) |
| `frontend/src/views/ReportView.vue` | wie oben | nur `/report/:reportId` | Wrapper-View | delete | — | — | 0.9.0 | s. o. | [ReportView.vue:6-18](../../frontend/src/views/ReportView.vue#L6) |
| `frontend/src/views/InteractionView.vue` | wie oben | nur `/interaction/:reportId` | Wrapper-View | delete | — | — | 0.9.0 | s. o. | [InteractionView.vue:6-18](../../frontend/src/views/InteractionView.vue#L6) |
| `frontend/src/views/Home.vue` | wie oben | nur `/home` | Wrapper-View | delete | — | — | 0.9.0 | s. o. | [Home.vue:5-19](../../frontend/src/views/Home.vue#L5) |
| `frontend/src/views/SettingsView.vue` | klassische SettingsView, 853 Z. | nur Test (`SettingsView.spec.ts`) | unerreichte View | delete | — | — | 0.9.0 | Datei nicht im Router, nur Test-Consumer; Spec muss mit entfernt werden | [SettingsView.vue:1-3](../../frontend/src/views/SettingsView.vue#L1); [SettingsView.spec.ts:35,51](../../frontend/src/views/__tests__/SettingsView.spec.ts#L35) |
| `frontend/src/views/Settings/SettingsUsersTeamsView.vue` | AppShell + ComingSoonCard, 27 Z. | nur Test (`SettingsSubViews.spec.ts:99`) | unerreichte View | delete | — | — | 0.9.0 | Datei nicht im Router (nur Redirect-Route); Test-Consumer; Spec entfernen | [SettingsUsersTeamsView.vue:1-27](../../frontend/src/views/Settings/SettingsUsersTeamsView.vue#L1); [SettingsSubViews.spec.ts:99](../../frontend/src/views/__tests__/SettingsSubViews.spec.ts#L99) |
| `frontend/src/views/v4/AppShellDemoView.vue` | AppShell + Verifikations-Logik | nur Self-Reference | unerreichte View | delete | — | — | 0.9.0 | Verifikations-View Slice B ohne Router-Eintrag; siehe Eigen-Kommentar | [AppShellDemoView.vue:2](../../frontend/src/views/v4/AppShellDemoView.vue#L2) |

### Geteilte Step-Komponenten (RETAIN — nicht löschbar)

| Pfad / View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis |
|---|---|---|---|---|---|---|---|---|---|
| `frontend/src/components/Step1GraphBuild.vue` | Step1GraphBuild | MainView + StepGraphBuildView | geteilte Komponente | retain | — | — | nie | Wird von v4-Step-View nach Wrapper-Löschung weiter benötigt | [MainView.vue:6](../../frontend/src/views/MainView.vue#L6), [StepGraphBuildView.vue:27](../../frontend/src/views/v4/steps/StepGraphBuildView.vue#L27) |
| `frontend/src/components/Step2EnvSetup.vue` | Step2EnvSetup | MainView + SimulationView + StepEnvSetupView | geteilte Komponente | retain | — | — | nie | s. o. | [MainView.vue:7](../../frontend/src/views/MainView.vue#L7), [SimulationView.vue:6](../../frontend/src/views/SimulationView.vue#L6), [StepEnvSetupView.vue:26](../../frontend/src/views/v4/steps/StepEnvSetupView.vue#L26) |
| `frontend/src/components/Step3Simulation.vue` | Step3Simulation | SimulationRunView + StepSimulationView | geteilte Komponente | retain | — | — | nie | s. o. | [SimulationRunView.vue:6](../../frontend/src/views/SimulationRunView.vue#L6), [StepSimulationView.vue:45](../../frontend/src/views/v4/steps/StepSimulationView.vue#L45) |
| `frontend/src/components/Step4Report.vue` | Step4Report | ReportView + StepReportView | geteilte Komponente | retain | — | — | nie | s. o. | [ReportView.vue:6](../../frontend/src/views/ReportView.vue#L6), [StepReportView.vue:26](../../frontend/src/views/v4/steps/StepReportView.vue#L26) |
| `frontend/src/components/Step5Interaction.vue` | Step5Interaction | InteractionView + StepInteractionView | geteilte Komponente | retain | — | — | nie | s. o. | [InteractionView.vue:6](../../frontend/src/views/InteractionView.vue#L6), [StepInteractionView.vue:22](../../frontend/src/views/v4/steps/StepInteractionView.vue#L22) |

### App-Shell-Wrapper-Views (canonical, weil produktiv genutzt)

| Pfad / View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis |
|---|---|---|---|---|---|---|---|---|---|
| `frontend/src/views/v4/RunsAppShellView.vue` | AppShell + RunsView | `/runs` | Wrapper-View (produktiv) | canonical | — | — | nie | Produktive App-Shell-View, kein düner Wrapper | [router/index.ts:33-37](../../frontend/src/router/index.ts#L33); [RunsAppShellView.vue:1-17](../../frontend/src/views/v4/RunsAppShellView.vue#L1) |
| `frontend/src/views/RunsView.vue` | RunsView-Tabelle | nur `RunsAppShellView.vue` | geteilte Komponente | retain | — | — | nie | Innere Komponente der App-Shell-View | [RunsAppShellView.vue:5-6](../../frontend/src/views/v4/RunsAppShellView.vue#L5) |
| `frontend/src/views/v4/RunDetailAppShellView.vue` | AppShell + RunDetailView | `/runs/:id` | Wrapper-View (produktiv) | canonical | — | — | nie | Produktive App-Shell-View | [router/index.ts:38-43](../../frontend/src/router/index.ts#L38); [RunDetailAppShellView.vue:1-26](../../frontend/src/views/v4/RunDetailAppShellView.vue#L1) |
| `frontend/src/views/RunDetailView.vue` | RunDetail-Panel | nur `RunDetailAppShellView.vue` | geteilte Komponente | retain | — | — | nie | Innere Komponente der App-Shell-View | [RunDetailAppShellView.vue:8-9](../../frontend/src/views/v4/RunDetailAppShellView.vue#L8) |

### Designreferenz (Agor-2026)

| Pfad / View | Aktuelle Komponente | Tatsächliche Consumer | Typ | Entscheidung | Zielroute | Parameter-Mapping | Entfernungsrelease | Begründung | Nachweis |
|---|---|---|---|---|---|---|---|---|---|
| `frontend/src/views/agora2026/Agora2026View.vue` | volumes | Design-Exploration | Designreferenz | retain | — | — | nie | Code bleibt ohne Router-Eintrag als Inspiration für 1.0.0 | [Agora2026View.vue:3-4](../../frontend/src/views/agora2026/Agora2026View.vue#L3) |
| `frontend/src/views/agora2026/screens/DashboardScreen.vue` | DashboardScreen | nur Agora2026View | Designreferenz | retain | — | — | nie | s. o. | [Agora2026View.vue:3](../../frontend/src/views/agora2026/Agora2026View.vue#L3) |
| `frontend/src/views/agora2026/screens/RunsScreen.vue` | RunsScreen | nur Agora2026View | Designreferenz | retain | — | — | nie | s. o. | [Agora2026View.vue:4](../../frontend/src/views/agora2026/Agora2026View.vue#L4) |

## Begründung

### Warum Wrapper-Löschung von Komponenten-Löschung getrennt wird

Die fünf klassischen Prozess-Views importieren dieselben Step-Module wie ihre
v4-Gegenstücke, besitzen aber teils zusätzliche Navigation, Datenladung und
Orchestrierung. Nach der Deletion-Test-Heuristik darf diese Komplexität nicht
verschwinden: Vor der Dateilöschung muss sie migriert oder nachweislich
entbehrlich sein. Die geteilten Step-Module bleiben wegen produktiver
v4-Consumer erhalten.

### Warum `/settings-classic`, `/v4/dashboard`, `/settings/users-teams` Redirects bleiben

- `/settings-classic` ist ausdrücklich auf 1.0.0 **Deferred**; vorher müssen
  Paritäts- und Deep-Link-Tests bestehen.
- `/settings/users-teams` und `/v4/dashboard` bleiben bis 1.0.0 als
  Kompatibilitäts-Redirects.
- `/settings` bleibt dauerhaft als Redirect. Keiner dieser Einträge ist ein
  Vue-Router-`alias`.

### Warum `/agora-2026` als Designreferenz erhalten bleibt

Der Code unter `frontend/src/views/agora2026/` bleibt als ungeroutete
Designreferenz erhalten. Der Pfad ist kein unterstützter Produkt-Deep-Link und
wird deshalb als begründete Ausnahme in 0.9.0 direkt entfernt; danach muss der
Catch-all `NotFound` liefern und ein Router-Test dieses Verhalten sichern.

### Warum `/home` zuerst Redirect wird

`Home.vue` besitzt weiterhin einen Pending-Upload-Flow, dessen v4-Gegenstück
in `HeroNewRun.vue` liegt. In 0.9.0 wird der Pfad nach verifizierter Parität
zum Redirect auf `/dashboard`; die endgültige Pfadentfernung folgt in 1.0.0.

### Warum `SettingsView.vue` und `SettingsUsersTeamsView.vue` gelöscht werden können

Beide sind nicht im Router (Pfad `/settings` ist Redirect, `/settings/users-teams` ist Redirect). Die einzigen Consumer sind Spec-Tests (`SettingsView.spec.ts`, `SettingsSubViews.spec.ts`). Die Spec-Tests müssen mit gelöscht werden.

### Warum `AppShellDemoView.vue` gelöscht werden kann

Eigen-Kommentar in der Datei bestätigt: "Wird in Slice F in den Router eingebunden (aktuell kein Router-Eintrag)". Da Slice F in 0.9.0 nicht mehr startet, ist die View verwaist.

### Warum Composables und Stores nicht Teil der Löschentscheidung sind

`useRuntimeLlmOptions` war zum Zeitpunkt dieser Analyse (2026-07-22) durch
`Step2EnvSetup` und `Step3Simulation` noch produktiv genutzt; das Composable
wurde in [#922](https://github.com/arn0ld87/agora/issues/922) entfernt,
nachdem beide Consumer auf den Kanon-Pfad migriert waren (siehe
Ausführungsstatus oben). `useEnvForm` wird zusätzlich von
[`HeroNewRun`](../../frontend/src/components/v4/dashboard/HeroNewRun.vue#L19)
verwendet. `pendingUpload` verbindet
[`HeroNewRun`](../../frontend/src/components/v4/dashboard/HeroNewRun.vue#L18)
und [`Home`](../../frontend/src/views/Home.vue#L16) mit
[`MainView`](../../frontend/src/views/MainView.vue#L15). #830 trifft deshalb
keine Löschentscheidung für diese oder andere Layout-/Store-/Composable-Dateien;
deren vollständige Inventur gehört in das jeweilige Umsetzungs-Issue.

### Parametermappings und der `new`-Sonderfall

Bei `/process/:projectId` ist eine bestehende Projekt-ID 1:1 abbildbar.
`/process/new` ist dagegen kein zulässiger Router-Redirect:
[`HeroNewRun`](../../frontend/src/components/v4/dashboard/HeroNewRun.vue#L241)
schreibt `pendingUpload`, während
[`MainView.handleNewProject`](../../frontend/src/views/MainView.vue#L115) den
Upload konsumiert, Ontologie und Graph erzeugt und erst danach eine konkrete
Projekt-ID besitzt. Vor der Redirect-Umstellung muss diese Sequenz hinter einen
geteilten Orchestrierungs-Seam verschoben werden; sein Ergebnis ist die
konkrete `projectId` für `/v4/graph-build/:projectId`. Tests müssen den
bestehenden-ID- und den `new`-Pfad getrennt abdecken.

`projectId`, `simulationId` und `reportId` bleiben in den übrigen vier
Übergängen namensgleich. Die Ausnahme ist `/simulation/:simulationId`:
`/v4/env-setup/:projectId` benennt denselben Wert als `projectId`, reicht
ihn in `StepEnvSetupView.vue` jedoch als `simulationId` an
`Step2EnvSetup.vue` weiter. Dieser ungewöhnliche Seam muss im
Redirect-Test explizit abgesichert werden.

## Out-of-Scope

- ~~Picker-Migration: `LlmProfilePicker` wird aktuell von `Step4Report`, `EnvSetupModelPanel`, `ReportBranchControls` verwendet — Verstoß gegen #760 Akzeptanzkriterium 3.~~ Erledigt in [#834](https://github.com/arn0ld87/agora/issues/834): `LlmProfilePicker.vue` ist entfernt, keine produktiven Referenzen mehr (Stand 2026-07-28).
- Workspace-/Store-/Picker-Abhängigkeiten: eigentliche Umsetzung in #831–#839.
- Lovable/React-Rewrite: bleibt vor 1.0.0 nicht freigegeben (siehe `docs/epics/frontend-next/brief.md`).
- `store/` vs `stores/`-Verzeichnisdopplung: ohne belegten funktionalen Anlass ausgeschlossen.

## Konsequenzen

- Referenzrouten bilden ein kleines stabiles Router-Interface; Redirects
  konzentrieren Deep-Link-Kompatibilität an diesem Seam.
- Klassische Wrapper dürfen erst entfallen, wenn ihre zusätzliche
  Orchestrierung migriert oder nachweislich entbehrlich ist.
- Geteilte Step-Module sowie `useEnvForm` und `pendingUpload` bleiben
  erhalten. `useRuntimeLlmOptions` wurde in [#922](https://github.com/arn0ld87/agora/issues/922)
  entfernt, nachdem seine letzten Consumer auf den Kanon-Pfad migriert waren.
- `/settings-classic` ist konsistent auf 1.0.0 **Deferred**.
- `/agora-2026` ist die dokumentierte Ausnahme von der Übergangsredirect-Regel
  und muss nach Entfernung über den Catch-all als `NotFound` enden.

## Ausführungsgrenze

Dieses ADR liefert Architekturconstraints und Belege, aber keine
Umsetzungs-Tickets. Scope, Akzeptanzkriterien, Reihenfolge und Fortschritt
bleiben in #829, #830 und den dort verknüpften GitHub Issues. Die eigentlichen
Router-, View- und Teständerungen sind ausdrücklich nicht Teil von #830.
