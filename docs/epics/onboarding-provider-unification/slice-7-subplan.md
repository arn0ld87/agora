# Subplan: Slice 7 — Golden-Gate-System und Informationsarchitektur

Stand: 2026-07-13
Basis der Inventur: `origin/main` @ `686a53352820816fde0c45da428abc31f5f96036`

## Ziel und Leitplanken

Slice 7 überträgt die Golden-Gate-Richtung in das bestehende Design-v4-System,
konsolidiert die Informationsarchitektur und beseitigt nachgewiesene
Parallelpfade. Der Slice wird als Folge kleiner, einzeln mergefähiger PRs
umgesetzt. Dieser Slice 7.0 ist ausschließlich Analyse und Dokumentation.

Verbindliche Quellen:

- [Current-State Map](./01-current-state-map.md)
- [Implementation Plan](./04-implementation-plan.md)
- [Handover](./HANDOVER.md)
- [Design Language v4](../../ui/design-language-v4.md)
- [Component Audit](../../ui/component-audit.md)
- [Slice-5-Subplan](./slice-5-subplan.md)

Architekturregeln für alle Folge-PRs:

1. `tokens-v3.css` und `states.css` bleiben die produktiven Sources of Truth.
2. Es entsteht weder ein Golden-Gate-Tokenpräfix noch eine zweite
   Komponentenbibliothek.
3. `AiModelPicker.vue`, `AiModelRef`, `ProviderConnection` und die bestehenden
   Routing-Verträge werden wiederverwendet, nicht nachgebaut.
4. Slice-6-Logik wird nicht verändert. Gemeinsame Dateien werden erst nach
   Slice-6-Merge und Rebase rein präsentational bearbeitet.
5. WCAG AA, 320 px, Tastatur, sichtbarer Fokus und Reduced Motion sind
   Merge-Gates, keine manuellen Nacharbeiten.
6. Deprecation oder Löschung erfolgt nur in einem eigenen PR mit erneutem
   Import- und Route-Nachweis.

## Verifizierter Bestand auf `origin/main`

### Design-v4 und wiederverwendbare Bausteine

Der lokale Graphify-AST-Lauf über 1.115 Code-Dateien ergab 17.951 Nodes und
33.528 Edges. Die anschließenden Traversals verbanden Shell, Settings,
Onboarding, Routing und Picker mit ihren realen Contracts und Konsumenten.
Klassische Import-Suchen bestätigten die konkreten Pfade.

Der produktive Namespace `frontend/src/components/v4/` enthält aktuell 64
Vue-Komponenten ohne Tests: 23 Shell-Dateien einschließlich Icons, 20 Forms,
7 Data, 6 Dashboard, 1 Step und 7 Sim-Feed. Die ältere
[Component-Audit-Zählung](../../ui/component-audit.md) ist damit als
historische Inventur nützlich, aber nicht mehr vollständig.

| Bestand | Nachgewiesene Nutzung | Entscheidung |
|---|---:|---|
| `AppShell.vue` | 24 Produktionsreferenzen | wiederverwenden; Slots und Responsive-Verhalten härten |
| `PageHeader.vue` | 19 Produktionsreferenzen | gemeinsame Seitenhierarchie |
| `Sidebar.vue`, `SidebarGroup.vue`, `SidebarItem.vue` | produktive AppShell-Navigation | bestehende IA in-place korrigieren |
| `Card.vue` | 21 Produktionsreferenzen | Golden-Gate-Surfaces über Tokens, nicht durch Fork |
| `Button.vue` | 19 Produktionsreferenzen | bestehende Interaktionszustände behalten |
| `Field.vue`, `Input.vue`, `Select.vue` | Settings- und Formularbasis | vorhandene Label-, Hint- und Error-Semantik nutzen |
| `Tabs.vue`, `Alert.vue`, `Dialog.vue`, `EmptyState.vue` | vorhandene Data-Komponenten | für Status, Dialog und leere Zustände nutzen |
| `SettingsSectionPanel.vue` | General und Integrationen | klassische Settings-Felder konsolidieren |
| `AiModelPicker.vue` | kanonischer connection-basierter Picker | einzige Zielkomponente für Modellauswahl |

`frontend/src/main.ts` importiert `tokens-v3.css` und danach `states.css`
global. 16 produktive Vue-Komponenten konsumieren bereits
`.v4-state-interactive` oder `.v4-state-selectable`. Änderungen an Tokenwerten
haben daher einen hohen globalen Impact und müssen zunächst additiv bleiben.

### Bestehende Abweichung: `tokens-2026.css`

`origin/main` enthält bereits eine dritte, gesonderte Exploration:

- `frontend/src/main.ts` importiert global `tokens-2026.css`;
- `tokens-2026.css` definiert den eigenen `--a26-*`-Namespace;
- `/agora-2026` lädt `frontend/src/views/agora2026/Agora2026View.vue`;
- die Exploration besitzt eigene Shell-, Navigations- und Picker-Darstellungen.

Das ist kein Zielsystem für Slice 7. Golden-Gate-Arbeit ergänzt dort keine
Tokens und übernimmt keine Komponenten. Die statische Referenz unter
`frontend/public/design/v3/` darf als visuelle Quelle bleiben; die produktive
Runtime-Exploration wird in 7.8 nach erneutem Impact-Nachweis entfernt.

## Import- und Impact-Nachweis

### `/settings-classic`

- Einziger produktiver Einstieg ist die Lazy-Route in
  `frontend/src/router/index.ts` auf `frontend/src/views/SettingsView.vue`.
- Es gibt keinen Sidebar-Eintrag und keinen internen Produktionslink auf
  `/settings-classic`; weitere Treffer liegen in Docs, Changelog und dem
  eigenen View-Test.
- `SettingsSectionPanel.vue` rendert die klassische Schema-/Werte-Logik bereits
  gefiltert in `SettingsGeneralView.vue` und `SettingsIntegrationsView.vue`.
  Deren Allow-Lists decken `llm`, `logging`, `locale`, `ui`, `event_bus`,
  `security`, `neo4j`, `embedding`, `ontology`, `hybrid_search`, `agent_tools`,
  `webtools` und `oasis` ab.

Folgerung: Die Route ist nicht navigationskritisch, die View darf aber erst nach
einem automatisierten Paritätstest und einer Redirect-Phase entfernt werden.
Direkte Bookmarks sind das verbleibende Migrationsrisiko.

### Legacy- und kanonische Model-Picker

| Pfad | Vertrag | Produktions-Importer | Folgerung |
|---|---|---|---|
| `components/v4/forms/AiModelPicker.vue` | `AiModelRef` + `provider_connection_id` | Hero, Settings General, LLM Providers, Run-Routing, Step Override | kanonisch; Styling und A11y in-place |
| `components/ui/ModelPicker.vue` | `{ provider_id, model_id }` | keine; nur eigener Spec | nach erneutem Grep löschbar |
| `components/v4/forms/ModelPicker.vue` | `StageLLMRoute` | `Home.vue`, `ReportModelControls.vue`, `LlmProfileManager.vue` | nicht löschbar, bevor alle drei Consumer migriert sind |

`useAvailableModels.ts` bleibt die Discovery-Quelle des kanonischen Pickers.
Für `StageLLMRoute`-Consumer wird der bestehende `useAiModelRefAdapter`
verwendet. `LlmProfileManager` benötigt zusätzlich eine explizite, getestete
Abbildung von `ProviderConnection` auf den bestehenden `LlmProfile`-Vertrag;
ein neues Profil- oder Routing-DTO ist ausgeschlossen.

### Mock-Routing

`frontend/src/views/Settings/llmRouting/mockData.ts` wird ausschließlich von
`ActiveSnapshotsCard.vue`, `GlobalDefaultCard.vue` und
`StageOverridesCard.vue` importiert. Keine dieser drei Karten besitzt einen
Importer. `CustomModelCard.vue` ist ebenfalls unverdrahtet. Die produktive
Route `SettingsLlmRouting` rendert stattdessen den echten
`components/LlmRouting/LlmRoutingView.vue`-Pfad mit API- und Contract-Anbindung.

Folgerung: Mock-Daten und vier unverdrahtete Karten sind ein atomarer
Dead-Code-Kandidat. Vor der Löschung werden Route-, Import- und Test-Greps im
Cleanup-PR wiederholt.

### Design-v4-Komponenten, `tokens-v3.css` und `states.css`

- `AppShell`, `PageHeader`, `Card` und `Button` haben zweistellige
  Produktions-Importerzahlen. Forks würden sofort eine zweite Bibliothek
  erzeugen.
- `tokens-v3.css` wird einmal global importiert und enthält Surface-, Text-,
  Accent-, Status-, Spacing-, Radius-, Shadow-, Focus- und Typografie-Tokens
  samt Compat-Layer.
- `states.css` wird einmal global importiert und stellt Rest-, Hover-, Focus-,
  Active- und Disabled-Zustände sowie Reduced-Motion-Regeln bereit.
- 16 Komponenten verwenden die State-Klassen bereits. Änderungen an
  bestehenden Werten sind deshalb migrationspflichtig; neue semantische
  Tokens werden zuerst additiv eingeführt.

## Informationsarchitektur-Matrix

`implement MVP` ist für Slice 7 bewusst leer: Projekte, Datensätze, Vorlagen
und Monitoring gehören gemäß Implementation Plan in eigenständige Slice-8+-PRs.
Bis dahin sollen sie nicht als scheinbar verfügbare, deaktivierte Navigation
sichtbar sein.

| Eintrag oder Zugang | Entscheidung | Zielzustand in Slice 7 |
|---|---|---|
| Dashboard | `wire` | bestehende Dashboard-Route und AppShell behalten |
| Runs | `wire` | bestehende Runs- und Run-Detail-Routen behalten |
| Projekte | `hide` | Stub aus Sidebar entfernen; MVP auf Slice 8+ verschieben |
| Datensätze | `hide` | Stub aus Sidebar entfernen; MVP auf Slice 8+ verschieben |
| Vorlagen | `hide` | Stub aus Sidebar entfernen; MVP auf Slice 8+ verschieben |
| Monitoring | `hide` | Stub aus Sidebar entfernen; MVP auf Slice 8+ verschieben |
| Settings: General | `wire` | `SettingsGeneralView` |
| Settings: Integrationen | `wire` | `SettingsIntegrationsView` |
| Settings: Profil | `wire` | `SettingsProfileView`; Users-&-Teams-Redirect bleibt kompatibel |
| Settings: API Keys | `wire` | bestehende geschützte Route |
| Settings: LLM Providers | `wire` | connection-basierte Provider-Verwaltung |
| Settings: Embedding | `wire` | bestehende Embedding-Konfiguration |
| Settings: Audit Logs | `hide` | Coming-soon-Eintrag bis eigenem MVP aus Sidebar entfernen |
| Settings: LLM Routing | `hide` | run-spezifischen Zugang aus Settings entfernen; Routing im Run Detail bleibt `wire` |
| `/settings/users-teams` | `defer` | kompatiblen Redirect auf Profil behalten, nicht anzeigen |
| `/settings-classic` | `defer` | erst Redirect, dann Entfernung nach Paritäts- und Deep-Link-Test |

## File-Ownership und Konfliktgrenze zu Slice 6

| Bereich | Slice 6 exklusiv bis Merge | Slice 7 |
|---|---|---|
| Persona-Count-Einstieg | `HeroNewRun.vue`, `pendingUpload.ts`, zugehörige Specs/E2E-Werte | kein Touch vor Slice-6-Merge; danach nur Template/CSS ohne Count-Semantik |
| Step 2 und Quoten | `Step2EnvSetup.vue`, `AgentCapControl.vue`, `usePersonaQuota.ts`, `personaQuotaContract.ts` | kein Touch |
| Run-Vertrag | `api/simulation.ts`, Run-Contracts, Schemas und Persistenzpfade | keine Contract- oder Payload-Änderung |
| Backend-Budgetlogik | `simulation_prepare.py`, `prepare_service.py`, `simulation_config_generator.py`, OASIS-/Quota-Pfade und Tests | kein Touch |
| Slice-6-E2E | Werte 1, 5, 10, 30, 50, 100 und deren Fixtures | keine Selektoren oder Erwartungswerte ändern |
| Design Foundations | — | `tokens-v3.css`, `states.css` und deren Contract-Tests |
| Shell und IA | — | v4-Shell, Sidebar, Router-Navigation und zugehörige Tests |
| Onboarding | nur falls Slice 6 später ausdrücklich übernimmt | `OnboardingView.vue` ausschließlich präsentational; API-/Step-Vertrag bleibt unverändert |
| Settings und Picker | — | v4-Settings, `AiModelPicker`, Legacy-Migrationen und Tests |

Ein Folge-PR, der `HeroNewRun.vue` benötigt, startet erst nach Slice-6-Merge,
rebaset auf dessen Merge-Commit und darf `numAgents`, `pendingUpload`,
Run-Payloads oder Slice-6-Testwerte nicht verändern.

## Sub-Slices

### 7.1 — Additive Golden-Gate-Tokens und State-Verträge

- **Ziel:** Die visuelle Richtung als semantische Ergänzungen in den beiden
  bestehenden CSS-Sources of Truth abbilden. Geeignete Kategorien sind
  Glass-Surfaces, warmer Akzent, Korall-Statusakzent, Backdrop, kontrollierte
  Motion-Dauern und Focus-Kontrast. Es entsteht kein `--golden-*`-Präfix.
- **Nicht-Ziele:** globale Umfärbung, Komponentenumbau, `tokens-2026.css`,
  Seitenrouting oder Slice-6-Dateien.
- **Dateien:** `frontend/src/assets/styles/tokens-v3.css`,
  `frontend/src/assets/styles/states.css`, neu
  `frontend/src/assets/styles/__tests__/designTokens.spec.ts`.
- **Abhängigkeiten:** keine; direkter Start von `origin/main` möglich.
- **Ownership:** exklusiv Slice 7. Keine Überschneidung mit Slice 6.
- **TDD/Teststrategie:** RED-Test liest beide CSS-Dateien und fordert die
  vereinbarten semantischen Tokens, Focus-State, Reduced-Motion-Regel und das
  Verbot neuer Tokenpräfixe. Danach additive Definitionen implementieren.
- **Accessibility-Gates:** Focus-Indikator mindestens 2 px; Kontrastziel 3:1
  gegen angrenzende Fläche; Motion-Tokens besitzen eine Reduce-Entsprechung.
- **Migration/Rollback:** bestehende Tokenwerte bleiben unverändert. Rollback
  entfernt neue Definitionen und den Contract-Test ohne Consumer-Migration.
- **Akzeptanz:** kein neuer CSS-Import, kein neuer Namespace, Contract-Test und
  Frontend-Tests grün, visueller Smoke in Light/Dark.
- **PR-Schnitt:** ein Foundation-PR mit genau zwei produktiven CSS-Dateien und
  einem Test. Empfohlener erster Implementierungs-PR.

### 7.2 — Automatisierte Accessibility- und 320-px-Gates

- **Ziel:** Wiederverwendbare Playwright-Gates für Shell, Settings,
  Onboarding und Picker bereitstellen.
- **Nicht-Ziele:** komplette visuelle Migration oder beiläufige A11y-Refactors.
- **Dateien:** `frontend/package.json`, `frontend/bun.lock`,
  `frontend/tests/e2e/helpers/accessibility.ts`, neu
  `frontend/tests/e2e/golden-gate-accessibility.spec.ts`; Playwright-Konfig nur,
  falls für Reduced-Motion-Projekte nötig.
- **Abhängigkeiten:** 7.1 für Token-/Focus-Erwartungen.
- **Ownership:** exklusiv Slice 7; keine Slice-6-Fixtures oder Persona-Werte.
- **TDD/Teststrategie:** Route für Route kleine Tests hinzufügen; bei einem
  Befund nur die jeweilige Route in ihrem späteren Surface-PR freischalten.
  Keine dauerhaften `.skip`-Marker.
- **Accessibility-Gates:** Axe ohne `serious`/`critical` Violations; Text 4,5:1,
  große Schrift und UI-Grenzen 3:1; 320×800 ohne horizontales Dokument-Scrollen;
  vollständige Tastaturbedienung; Focus sichtbar; `reducedMotion: 'reduce'`
  unterdrückt nicht essentielle Animation.
- **Migration/Rollback:** neue Dev-Dependency isoliert. Rollback entfernt
  Helper, Spec und Lockfile-Änderung gemeinsam.
- **Akzeptanz:** reproduzierbarer lokaler E2E-Befehl und CI-Ausführung sind im
  PR dokumentiert; keine Netzabhängigkeit.
- **PR-Schnitt:** Test-Infrastruktur-PR, getrennt von Surface-Code.

### 7.3 — AppShell und Sidebar-Informationsarchitektur

- **Ziel:** Matrixentscheidungen anwenden, mobile Shell bei 320 px härten und
  irreführende Stubs ausblenden.
- **Nicht-Ziele:** MVPs für Projekte/Datensätze/Vorlagen/Monitoring, neue Shell
  oder Settings-Fachlogik.
- **Dateien:** `AppShell.vue`, `Sidebar.vue`, `SidebarItem.vue`, optional
  `SidebarGroup.vue`, Router nur für nachgewiesene Redirects, DE/EN-i18n und
  eng zugehörige Shell-Specs.
- **Abhängigkeiten:** 7.1 und 7.2.
- **Ownership:** keine Slice-6-Datei. `HeroNewRun.vue` bleibt unberührt.
- **TDD/Teststrategie:** Sidebar-Specs zuerst auf die Matrix umstellen; mobile
  Drawer-Tests prüfen Escape, Backdrop, Focus-Rückgabe und 320 px.
- **Accessibility-Gates:** Navigation besitzt eindeutigen Namen, aktiver Zustand
  ist nicht nur farblich, Drawer ist tastaturbedienbar, Fokus geht beim Öffnen
  hinein und beim Schließen zurück.
- **Migration/Rollback:** Routen bleiben zunächst bestehen; nur Sichtbarkeit
  ändert sich. Revert stellt die alte Sidebar ohne Datenmigration wieder her.
- **Akzeptanz:** keine deaktivierten Zukunftsstubs sichtbar; alle `wire`-Ziele
  erreichbar; Audit Logs und Settings-LLM-Routing nicht in der Sidebar; Shell
  besteht die 320-px- und Tastatur-Gates.
- **PR-Schnitt:** ein Shell-/Navigation-PR, keine Surface-Neugestaltung.

### 7.4 — Settings-Konvergenz und `/settings-classic`

- **Ziel:** v4-Settings als einzigen navigierbaren Settings-Einstieg bestätigen,
  klassische Route kontrolliert über Redirect deprecaten und anschließend die
  Legacy-View entfernen.
- **Nicht-Ziele:** neue Settings-Backends, Secret-Verträge, Provider-/Routing-
  DTOs oder Run-Routing-Semantik.
- **Dateien:** `router/index.ts`, `SettingsGeneralView.vue`,
  `SettingsIntegrationsView.vue`, `SettingsSectionPanel.vue`,
  `SettingsView.vue`, Settings-Specs und DE/EN-i18n.
- **Abhängigkeiten:** 7.1–7.3; vollständiger Paritätstest vor Entfernung.
- **Ownership:** exklusiv Slice 7.
- **TDD/Teststrategie:** zuerst ein Schema-Section-Paritätstest für alle
  klassischen Sektionen; dann Redirect-Test für `/settings-classic`; erst in
  einem zweiten Commit/PR-Schritt View und alte Specs entfernen.
- **Accessibility-Gates:** Überschriftenhierarchie, Tab-/Section-Navigation,
  Fehlermeldungen, Secret-Dialog-Fokus und 320-px-Tabellenlayout.
- **Migration/Rollback:** Redirect mindestens einen Release-Zyklus behalten.
  Direkte Bookmarks funktionieren weiter. Rollback stellt die Lazy-Route wieder
  her; Settings-Daten bleiben unverändert.
- **Akzeptanz:** jede klassische Section ist in General oder Integrationen
  erreichbar; kein interner Link nutzt `/settings-classic`; Redirect-Test grün;
  View-Löschung erst nach erneutem Importnachweis.
- **PR-Schnitt:** 7.4a Parität + Redirect, 7.4b spätere View-Entfernung.

### 7.5 — Onboarding-Golden-Gate-Präsentation

- **Ziel:** bestehendes resumierbares Onboarding mit v4-Komponenten und den
  neuen Tokens visuell vereinheitlichen.
- **Nicht-Ziele:** Step-Reihenfolge, Provider-/Embedding-Anforderungen,
  Onboarding-API, Persona-Count, Run-Vertrag oder Step-2-Budget.
- **Dateien:** `views/onboarding/OnboardingView.vue`, dessen Spec und DE/EN-i18n.
  Vorhandene `Card`, `Alert`, `Button`, `PageHeader` und `AiModelPicker` werden
  importiert, nicht kopiert.
- **Abhängigkeiten:** 7.1 und 7.2; parallel zu Slice 6 möglich, solange dessen
  Ownership unverändert bleibt.
- **Ownership:** `OnboardingView.vue`-Template/CSS bei Slice 7; Script-Logik und
  Contracts bleiben unverändert.
- **TDD/Teststrategie:** bestehende Resume-/Dismiss-/409-Tests als
  Verhaltensschutz; neue Tests für Landmarken, Fokusreihenfolge und Status-
  Semantik vor dem Styling.
- **Accessibility-Gates:** 320 px, Zoom 200 %, logisch fortlaufender Tab-Order,
  Status nicht nur farblich, Fokus nach Schrittwechsel auf die neue Überschrift,
  Reduced Motion.
- **Migration/Rollback:** rein präsentational und per Revert rücksetzbar; keine
  gespeicherten Onboarding-Zustände werden migriert.
- **Akzeptanz:** bestehende Onboarding-Tests unverändert grün; keine neue
  Business-Branch; alle visuellen Werte stammen aus v4-Tokens.
- **PR-Schnitt:** ein Onboarding-Surface-PR.

### 7.6 — Einziger Model-Picker, in drei atomaren PRs

#### 7.6a — Kanonischen `AiModelPicker` visuell härten

- **Ziel:** Golden-Gate-Surface, Focus und Responsive-Verhalten in-place.
- **Nicht-Ziele:** Discovery, Capability-Filter, `AiModelRef` oder Emits ändern.
- **Dateien:** `AiModelPicker.vue`, dessen Unit-/Discovery-Specs und bestehende
  Picker-E2E.
- **Abhängigkeiten:** 7.1 und 7.2.
- **Ownership/Konflikt:** Slice 7; keine Slice-6-Werte oder Hero-Logik ändern.
- **TDD/Accessibility:** Reka-Keyboardpfad, Suche, Offline-Optionen, Focus,
  320 px und Reduced Motion zuerst testen.
- **Migration/Rollback:** kein Vertragswechsel; Styling-Revert genügt.
- **Akzeptanz/PR-Schnitt:** bestehende Picker-E2E plus A11y-Gate grün; ein
  komponentenfokussierter PR.

#### 7.6b — `StageLLMRoute`-Consumer migrieren

- **Ziel:** `Home.vue` und `ReportModelControls.vue` über den bestehenden
  `useAiModelRefAdapter` auf `AiModelPicker` umstellen.
- **Nicht-Ziele:** neues Routing-DTO, Backend-Route oder Profilverwaltung.
- **Dateien:** beide Consumer, Adapter nur bei nachgewiesener Lücke, zugehörige
  Specs.
- **Abhängigkeiten:** 7.6a; Slice-6-Merge, falls `Home.vue` oder gemeinsame
  Fixtures dort zwischenzeitlich geändert wurden.
- **Ownership/Konflikt:** kein `HeroNewRun.vue`, kein Persona-/Run-Count.
- **TDD/Accessibility:** Roundtrip `AiModelRef -> StageLLMRoute` einschließlich
  `null`, unbekannter Connection und Fallback; Picker-Tastatur-Smoke.
- **Migration/Rollback:** alte Komponente bleibt bis 7.6c vorhanden; Revert pro
  Consumer möglich.
- **Akzeptanz/PR-Schnitt:** keine direkte `ModelPicker.vue`-Referenz in den zwei
  Consumern; Run-Snapshot bleibt vertragsgleich; ein Adapter-Migrations-PR.

#### 7.6c — `LlmProfileManager` migrieren und v4-Legacy-Picker löschen

- **Ziel:** letzten Produktionsimporter migrieren und
  `components/v4/forms/ModelPicker.vue` samt Specs entfernen.
- **Nicht-Ziele:** `LlmProfile` neu erfinden oder Connection-Secrets in die UI
  spiegeln.
- **Dateien:** `LlmProfileManager.vue`, `useAiModelRefAdapter.ts` nur falls die
  bestehende Abbildung genügt, Store-/Component-Specs, Legacy-Picker und Spec.
- **Abhängigkeiten:** 7.6b und geklärte Abbildung
  `ProviderConnection -> bestehender LlmProfile`.
- **Ownership/Konflikt:** Slice 7; kein Slice-6-Pfad.
- **TDD/Accessibility:** Profil erstellen/bearbeiten/default setzen, unbekannte
  Connection als validierten Fehler behandeln, Picker komplett per Tastatur.
- **Migration/Rollback:** Legacy-Picker erst im letzten Commit löschen. Revert
  stellt ihn und den vorherigen Manager gemeinsam wieder her.
- **Akzeptanz/PR-Schnitt:** Produktions-Grep findet nur `AiModelPicker`; keine
  neue Contract-Klasse; Legacy-CI-Check und Profiltests grün.

### 7.7 — Verwaisten v3-Picker und Mock-Routing entfernen

- **Ziel:** nachgewiesenen Dead Code atomar löschen.
- **Nicht-Ziele:** produktive Run-Routing-View oder kanonischen Picker ändern.
- **Dateien:** `components/ui/ModelPicker.vue` plus eigener Spec;
  `views/Settings/llmRouting/mockData.ts`, vier unverdrahtete Karten und
  gegebenenfalls der bestehende Legacy-Grep-Check.
- **Abhängigkeiten:** keine fachliche; nach 7.1 empfohlen, damit die Foundation
  vor parallelen Cleanup-Arbeiten steht.
- **Ownership/Konflikt:** exklusiv Slice 7.
- **TDD/Teststrategie:** vor Löschung erneut `rg`/Graphify; danach Build,
  Router-Spec, Settings-Routing-Spec und Legacy-Check.
- **Accessibility-Gates:** keine sichtbare Route darf verschwinden; produktive
  Settings- und Run-Routing-Gates bleiben grün.
- **Migration/Rollback:** reine Code-Löschung ohne persistierte Daten. Revert
  stellt alle Dateien gemeinsam wieder her.
- **Akzeptanz:** kein Import der gelöschten Pfade, produktive Route unverändert,
  keine Mock-Optionen im Build.
- **PR-Schnitt:** ein Dead-Code-PR, nicht mit 7.6b/7.6c vermischen.

### 7.8 — `/agora-2026`-Runtime-Exploration retiren

- **Ziel:** die vorhandene Parallel-Shell und den dritten `--a26-*`-Namespace
  aus der produktiven Runtime entfernen, nachdem relevante visuelle Motive in
  7.1–7.6 semantisch übernommen wurden.
- **Nicht-Ziele:** statische Designreferenzen in `frontend/public/design/v3/`
  oder das produktive v4-System löschen.
- **Dateien:** `main.ts`, `router/index.ts`, `tokens-2026.css`,
  `views/agora2026/**`, Router-/Build-Tests und betroffene Dokumentation.
- **Abhängigkeiten:** 7.1–7.6; erneuter Route-/Importnachweis.
- **Ownership/Konflikt:** Slice 7; keine Slice-6-Datei.
- **TDD/Teststrategie:** Route-Negativtest oder expliziter Redirect, Build-Grep
  gegen `--a26-`, anschließend vollständiger Frontend-Build.
- **Accessibility-Gates:** produktive v4-Routen bleiben vollständig abgedeckt;
  keine A11y-Gate-Ausnahme verweist auf `/agora-2026`.
- **Migration/Rollback:** opt-in Route kann für einen Release als Redirect auf
  Dashboard bestehen. Revert stellt Runtime-Exploration ohne Datenmigration
  wieder her.
- **Akzeptanz:** kein globaler `tokens-2026.css`-Import, kein produktiver
  `--a26-*`-Consumer, statische Designreferenz bleibt verfügbar.
- **PR-Schnitt:** eigener Retirement-PR wegen großer Löschdiff.

## Empfohlene Implementierungsreihenfolge

1. **7.1** — additive Tokens und State-Verträge.
2. **7.2** — automatisierte A11y-/320-px-Gates.
3. **7.7** — bereits nachgewiesenen Dead Code entfernen.
4. **7.3** — Shell und Sidebar-IA.
5. **7.4a** — Settings-Parität und `/settings-classic`-Redirect.
6. **7.5** — Onboarding-Präsentation; parallel zu Slice 6 möglich.
7. **7.6a** — kanonischen Picker visuell härten.
8. **7.6b** — Stage-Routing-Consumer migrieren.
9. **7.6c** — Profilmanager migrieren und v4-Legacy-Picker löschen.
10. **7.4b** — klassische Settings-View nach Redirect-Zyklus entfernen.
11. **7.8** — `agora-2026`-Runtime-Exploration retiren.

7.3–7.8 starten jeweils von aktuellem `origin/main` und erhalten eigene PRs.
Nur 7.5 darf parallel zu Slice 6 laufen; ein später notwendiger
`HeroNewRun.vue`-Polish wird ausdrücklich auf nach Slice 6 verschoben.

## Gemeinsame Verifikations- und Merge-Gates

Jeder Implementierungs-PR führt mindestens fokussierte Tests, Frontend-Lint,
Typecheck und Build aus. Vor Merge folgen das vollständige
`bash scripts/pre-push-gate.sh` und die für den Surface relevanten Playwright-
Gates. Zusätzlich gilt:

- `git diff --check` ohne Befund;
- Import-/Route-Grep vor jeder Deprecation und nach jeder Löschung;
- keine neuen `--a26-*`, `--golden-*` oder sonstigen Tokenpräfixe;
- keine zweite Picker-Komponente und kein duplizierter Provider-/Routing-
  Vertrag;
- 320×800 ohne horizontales Dokument-Scrollen;
- WCAG-AA-Kontrast, sichtbarer `:focus-visible`-State und vollständiger
  Tastaturpfad;
- `prefers-reduced-motion: reduce` für nicht essentielle Animation;
- GitHub-Gemini-Sichtung pro PR; Findings werden vor Merge bearbeitet oder mit
  nachvollziehbarer Begründung beantwortet.
