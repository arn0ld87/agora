# Agora UI Component Audit

Stand: 2026-05-15 · Commit `de933b9` · Quelle: `frontend/src/components/**/*.vue`.

Dieser Audit listet **alle existierenden UI-Komponenten** im Repo, klassifiziert sie
nach Namespace und gibt eine Empfehlung pro Komponente: **keep** (so lassen),
**polish** (kleinere Verbesserungen), **migrate** (in v4 verschieben), **retire**
(im Cleanup-Slice J entfernen).

## Legacy Namespace: `components/ui/` (11 Files)

Diese Komponenten stammen aus der v3/early-v4-Phase. Cleanup-Slice J des
Design-v4-Epics plant ihren schrittweisen Abbau, sobald v4-Äquivalente existieren.

| Komponente | Zweck | Empfehlung | v4-Äquivalent |
|---|---|---|---|
| `AgoraGlyph.vue` | Marken-Glyph (Logo-Wortmarke) | keep | – |
| `Badge.vue` | Status-Badge mit Tone-Variants | migrate → `v4/forms/Badge.vue` (existiert dort schon) | `v4/forms/Badge.vue` |
| `Btn.vue` | Primary/Secondary/Ghost-Button | migrate → `v4/forms/Button.vue` (Lücke) | **fehlt in v4** |
| `Card.vue` | Container mit Label/Glass/Dark-Varianten | migrate → `v4/forms/Card.vue` (existiert) | `v4/forms/Card.vue` |
| `ConfidenceBadge.vue` | High/Medium/Low + Verified-Tag | polish — bleibt im Report-Domain | – |
| `Field.vue` | Form-Field-Wrapper (Label/Hint/Error) | migrate → `v4/forms/Field.vue` (existiert) | `v4/forms/Field.vue` |
| `Hairline.vue` | 1px-Separator | keep oder retire (CSS-Token `--separator` reicht meist) | – |
| `Kicker.vue` | Caption-Heading über Titeln | migrate → `v4/data/Kicker.vue` (Lücke) | **fehlt in v4** |
| `SectionHead.vue` | Sektion-Header mit Titel + Beschreibung | migrate → `v4/shell/PageHeader.vue` (existiert in shell) | `v4/shell/PageHeader.vue` |
| `Select.vue` | Native-Select-Wrapper | migrate → `v4/forms/Select.vue` (existiert) | `v4/forms/Select.vue` |
| `StickyScrollBanner.vue` | Persona-Review-Sticky-Banner | keep — Spezifikum für Step5 | – |

**Migration-Strategie**: kein hartes Renaming. Die v4-Versionen sind reicher,
neue Code-Pfade nutzen v4. Legacy-Komponenten bleiben, bis kein Top-Level-Step
sie mehr importiert. Erst dann retire.

## Aktueller Namespace: `components/v4/` (27 Files)

### `v4/shell/` (App-Skelett, 7 Files + Icon-Registry)

| Komponente | Zweck | Empfehlung |
|---|---|---|
| `AppShell.vue` | CSS-Grid Sidebar/Topbar/Main/Inspector | keep — robust, slot-driven |
| `Sidebar.vue` | Linke Navigation, kollabierbar | keep |
| `SidebarGroup.vue` | Gruppen-Container (Settings-Submenü) | keep |
| `SidebarItem.vue` | Einzeleintrag mit Active-State | keep |
| `Topbar.vue` | Header mit Breadcrumbs + Badges | keep |
| `Breadcrumbs.vue` | Pfadnavigation | keep |
| `PageHeader.vue` | Haupt-Seitenheader (Titel + Beschreibung + Actions-Slot) | keep |
| `Icon.vue` | SVG-Icon-Renderer mit Registry | keep |
| `icons/` | Lokale SVG-Registry | keep — kein lucide nötig |

### `v4/forms/` (Eingabekomponenten, 14 Files + index.ts)

| Komponente | Zweck | Empfehlung |
|---|---|---|
| `Badge.vue` | Status-/Tone-Badge | keep |
| `Card.vue` | Container, primäres Layout-Element | keep |
| `ComingSoonCard.vue` | Platzhalter für ungebaute Routen | keep |
| `Field.vue` | Label + Slot + Hint + Error | keep |
| `Input.vue` | Text-/Number-/Password-Input | keep |
| `LlmProfileManager.vue` | Multi-Profil-Verwaltung für LLM-Routing | keep |
| `LlmProviderCard.vue` | OpenAI/Gemini/Ollama-Provider-Config (203 LOC) | keep — **deckt Anleitung-Phase-14 vollständig ab** |
| `ModelPicker.vue` | Model-Dropdown mit Context-Limit-Anzeige | keep |
| `Pill.vue` | Kompakt-Tag (z. B. Persona-Quoten) | keep |
| `SegmentedControl.vue` | Apple-Style Tab-Switcher | keep |
| `Select.vue` | Stylable Select (über Native-Behavior) | keep |
| `SettingsSectionPanel.vue` | Settings-Page-Sektionscontainer | keep |
| `StepModelOverrideChip.vue` | Per-Step-Model-Override-Chip | keep |
| `StickyActionBar.vue` | Bottom-fixed Submit/Cancel-Bar | keep |
| `index.ts` | Barrel-Export | keep — Import-Ergonomie |

### `v4/data/` (Datenkomponenten, 3 Files)

| Komponente | Zweck | Empfehlung |
|---|---|---|
| `DataTable.vue` | Generisches `<DataTable<TRow>>` mit sticky-Header, cell-Slots, Actions, compact-Modus, Empty-Slot | keep — **deckt Anleitung-Phase-17 vollständig ab** |
| `EmptyState.vue` | Icon + Titel + Subtitle + Actions-Slot | keep — **deckt Anleitung-Phase-12 vollständig ab** |
| `Tabs.vue` | Tab-Bar mit Indikator | keep |

### `v4/dashboard/` (Dashboard-Cards, 6 Files)

| Komponente | Zweck | Empfehlung |
|---|---|---|
| `ActiveRunsCard.vue` | Live-Liste laufender Simulationen | keep |
| `HeroNewRun.vue` | Großer „Neue Simulation"-CTA | keep |
| `QuickActionsRow.vue` | Schnellaktionen-Reihe | keep |
| `RecentReportsCard.vue` | Letzte abgeschlossene Reports | keep |
| `StatsRow.vue` | KPI-Karten-Reihe (Personas/Entitäten/Relationen) | keep — **deckt Anleitung-Phase-11 (MetricCard) vollständig ab** |
| `SystemHealthCard.vue` | Backend/Neo4j/OASIS-Status | keep |

### `v4/steps/` (Step-Komponenten)

| Komponente | Zweck | Empfehlung |
|---|---|---|
| `PipelineStepper.vue` | Step1–5-Navigationsanzeige | keep |

## Top-Level + Spezial-Namespaces

| Pfad | Anzahl | Empfehlung |
|---|---|---|
| `components/` Top-Level (Step1…5*.vue, RunsDashboard, AppFooter, …) | ~12 | polish — Container, die v4-Bausteine zusammensetzen. Hotspots `Step2EnvSetup.vue` (667 LOC) und `Step4Report.vue` (797 LOC) bleiben offen (Issue #203, Phase-5/5b-analoge Schnitte). |
| `components/compare/` | – | keep — Domain-spezifisch |
| `components/graph/` | – | keep — D3-Graph-Visualisierung |
| `components/icons/` | – | keep — SVG-Registry |
| `components/step2/`, `components/step4/` | – | keep — Step-Spezifika |
| `components/LlmRouting/` | – | keep — Settings-Sub-Panel |

## Gap-Analyse: Was die Anleitung wollte vs. was existiert

| Anleitung-Phase | Vorschlag | Realität |
|---|---|---|
| 11 (MetricCard) | shadcn-vue `Card` adaptieren | ✅ `v4/dashboard/StatsRow.vue` deckt das ab |
| 12 (EmptyState) | shadcn-vue Pattern | ✅ `v4/data/EmptyState.vue` existiert (deutsche Defaults, Actions-Slot) |
| 13 (SectionHeader) | eigene Komponente | ✅ `v4/shell/PageHeader.vue` existiert |
| 14 (ProviderForm) | shadcn-vue Form | ✅ `v4/forms/LlmProviderCard.vue` (203 LOC) + `LlmProfileManager.vue` |
| 16 (Chart) | shadcn-vue Chart / Unovis | ⚠️ D3 direkt — kein Wrapper. **Echte Lücke**: kein generischer `Chart`-Slot wie in Anleitung-§16. |
| 17 (DataTable) | TanStack + shadcn-vue Table | ✅ `v4/data/DataTable.vue` mit Generics, Sticky-Header, Slots |

**Echte Lücken** (Empfehlung: in separatem Slice angehen):

1. `v4/forms/Button.vue` — derzeit nur Legacy `ui/Btn.vue`. Migration in
   v4-Namespace wäre konsistent.
2. `v4/data/Chart.vue` (oder `v4/charts/*`) — Wrapper-Komponente mit
   einheitlichem Header (Titel, Beschreibung, Zeitraum, Einheit, Interpretation)
   um D3-Charts. Anleitung-§16 hat hier einen validen Punkt.
3. `v4/data/Kicker.vue` — Migration von `ui/Kicker.vue`.

Diese drei Lücken rechtfertigen für sich genommen **keine Tailwind/shadcn-vue-Migration**.
Sie sind kleine eigene Slices.

## Komponenten-Komplexitäts-Hotspots

Aus CLAUDE.md (Issue #203, bereits in Bearbeitung):

| Datei | LOC | Status |
|---|---:|---|
| `Step2EnvSetup.vue` | 667 (war 1804, −63 %) | unter Schwelle, weitere Aufteilung optional |
| `Step4Report.vue` | 797 (war 1287, −38 %) | unter Schwelle, weitere Aufteilung optional |

## Tests-Coverage

`components/v4/**/__tests__/` und `components/ui/__tests__/` enthalten Smoke-Tests
für jede aktive Komponente. Coverage-Threshold in `vite.config.js` aktuell
**28 %** für lines/functions/branches/statements (Ist-Werte 2026-05-10 alle
deutlich über 28 %).

## Empfohlene nächste Mini-Slices (jeder = 1 PR)

| Slice | Scope | Risiko |
|---|---|---|
| UI-A | `v4/forms/Button.vue` aus `ui/Btn.vue` portieren + Tests | niedrig |
| UI-B | `v4/data/Chart.vue` Wrapper-Komponente einführen | mittel |
| UI-C | `ui/Kicker.vue` → `v4/data/Kicker.vue` migrieren | niedrig |
| UI-D | Cleanup-Slice J: alle `components/ui/`-Importe ablösen | mittel |

Kein Big-Bang-Refactor nötig.
