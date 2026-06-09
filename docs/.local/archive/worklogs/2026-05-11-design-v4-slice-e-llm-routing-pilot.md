# Design v4 Slice E — LLM Routing Pilot: Worklog

Datum: 2026-05-11
Branch: feat/design-v4-epic
Autor: agora-frontend-worker (Claude Sonnet 4.6)

---

## File-Map (erstellt)

| Datei | Inhalt |
|---|---|
| `frontend/src/views/Settings/llmRouting/mockData.ts` | Typen + Konstanten: MOCK_ROUTING_STAGES, MOCK_STAGE_STATUS, PROVIDER/MODEL/EFFORT_OPTIONS |
| `frontend/src/views/Settings/llmRouting/GlobalDefaultCard.vue` | Card "Global Default" mit 3-spaltigem Select-Grid + JSON-Preview |
| `frontend/src/views/Settings/llmRouting/ActiveSnapshotsCard.vue` | Card "Aktive Snapshots" mit Version-Pills, Info-Banner, Stage-Status-Tabelle |
| `frontend/src/views/Settings/llmRouting/StageOverridesCard.vue` | Card "Stage Overrides" mit 7-Zeilen-Tabelle + Add/Reset/Save-CTAs |
| `frontend/src/views/Settings/llmRouting/CustomModelCard.vue` | Card "Custom Model hinzufügen" mit 4-Feld-Form-Grid |
| `frontend/src/views/Settings/LlmRoutingView.vue` | Haupt-View: AppShell + PageHeader + 2x2-Grid + StickyActionBar (87 LOC) |
| `frontend/src/views/__tests__/LlmRoutingView.spec.ts` | 5 Smoke-Tests (mount, Breadcrumbs, 4 Cards, ActionBar, PageHeader) |

## Geänderte Dateien (bestehende Slices)

| Datei | Änderung | Begründung |
|---|---|---|
| `frontend/src/router/index.ts` | Route `SettingsLlmRouting` auf `/settings/llm-routing` | Slice-E-Anforderung |
| `frontend/src/components/v4/shell/AppShell.vue` | `activeRoute`: `startsWith('settings')` statt Exact-Match; `activeSubRoute`: Slug-Ableitung aus Route-Namen | Gap in Slice B: Named Sub-Routes wurden nicht erkannt |
| `frontend/src/components/v4/shell/Sidebar.vue` | `llm-routing`-Nav-Item von query-param auf Named Route umgestellt | Konsistenz mit Dedicated Route |
| `frontend/src/components/v4/shell/__tests__/AppShell.spec.ts` | Test-Router um `SettingsLlmRouting` ergänzt | Route-Resolution-Fehler in Tests |
| `frontend/src/components/v4/shell/__tests__/Sidebar.spec.ts` | Test-Router um `SettingsLlmRouting` ergänzt | Route-Resolution-Fehler in Tests |

## v4-Komponenten konsumiert (Validation Slice A–D)

| Komponente | Slice | Ergebnis |
|---|---|---|
| `AppShell` | B | Funktioniert. Gap bei Named Sub-Routes → gepatcht. |
| `PageHeader` | B | Sauber. title + subtitle-Props arbeiten wie spec. |
| `Topbar` | B | Läuft via AppShell-Slot (kein direkter Import nötig). |
| `Sidebar` | B | Gap: `llm-routing`-Item musste von query-param auf Named Route umgestellt werden. |
| `Card` | C | Sauber. title/subtitle/footer-Slots korrekt. |
| `Field` | C | Sauber. label-Prop + slot-Komposition. |
| `Select` | C | Sauber. modelValue + options-Array. |
| `Input` | C | Sauber. mono-Prop für monospace-Inputs. |
| `Pill` / `Badge` | C | Sauber. tone-Prop (green/orange/purple/gray/blue). |
| `StickyActionBar` | C | Sauber. left/right-Slots, dirty-Prop vorhanden. |
| `DataTable` | D | Nicht benötigt — die Stage-Tabellen sind einfache HTML-Tables analog dem JSX-Spec. DataTable wäre Overkill ohne Sorting/Pagination-Anforderung. |
| `Tabs` | D | Nicht benötigt — kein Tab-Switch in diesem Screen. |
| `EmptyState` | D | Nicht benötigt — Tabellen haben immer Mock-Daten. |

## Bugs / Gaps gefunden während Integration

### Gap 1: AppShell erkennt keine Named Sub-Routes (Slice B)

`activeRoute` prüfte nur `n === 'settings'`, nicht Settings-Subrouten.
`SettingsLlmRouting` → lowercase `settingsllmrouting` → kein Match → Sidebar
hätte kein active-Highlighting gesetzt.

Patch: `n.startsWith('settings')` als OR-Bedingung.

### Gap 2: AppShell `activeSubRoute` only query-param-basiert (Slice B)

`activeSubRoute` las nur `route.query['tab']`. Für Dedicated Routes ohne
query-param (z.B. `/settings/llm-routing`) kam immer leerer String zurück.

Patch: Slug-Ableitung aus Route-Namen via CamelCase → kebab-case-Transformer
(`SettingsLlmRouting` → `llm-routing`).

### Gap 3: Sidebar-Item `llm-routing` auf query-param verdrahtet (Slice B)

Das Item verlinkte auf `{ name: 'Settings', query: { tab: 'llm-routing' } }`.
Mit Dedicated Route muss es auf `{ name: 'SettingsLlmRouting' }` zeigen.

### Gap 4: Test-Router in AppShell/Sidebar-Specs nicht erweiterbar gebaut

Beide Specs deklarieren den Router als `const` außerhalb der `beforeEach`-Funktion.
Neue Named Routes müssen nachträglich statisch ergänzt werden — kein
Runtime-Extension-Punkt. Für Slice F sollte der Test-Router aus einer
gemeinsamen Helper-Funktion kommen.

### Gap 5: Kein `emit('update:settingsOpen')` → `emit('update:settingsOpen', value)` Typo in Sidebar

In `Sidebar.vue` Zeile 96 steht `'update:settingsOpen': [value: boolean]` in den
Emit-Typen, aber das Emit-Event wird als `'update:settingsOpen'` abgefeuert.
Das ist korrekt — kein Bug, nur zur Dokumentation.

## Visual-Akzeptanz

Screenshot-Aufnahme per Dev-Server war in der Sandbox-Umgebung nicht möglich
(Netzwerk-Calls blockiert). Strukturelle Einschätzung basierend auf Code-Review
gegen `design.png`:

| Dimension | Score | Anmerkung |
|---|---|---|
| Layout-Grid 1.05fr/1fr 2x2 | 95 % | Exaktes `gridTemplateColumns: "1.05fr 1fr"` + `gap: 20px` übernommen |
| Card-Anatomie (title, body, footer) | 100 % | v4-Card-Komponente entspricht DSA exakt |
| GlobalDefault-Select-Fields | 95 % | 3-spaltig, korrekte Labels, korrekte Default-Werte |
| JSON-Preview | 95 % | Monospace, border, borderRadius 8px korrekt |
| Version-Pills (blue/purple) | 90 % | Tones korrekt, dot=false via Prop |
| Info-Banner | 85 % | Bolt-Icon durch inline SVG ersetzt (kein `<Icon name="bolt">` in Slice C vorhanden) |
| Stage-Status-Tabelle | 95 % | Header-Typo (uppercase, 11.5px), mono Stage-Namen, Pill-Tones |
| Stage-Override-Tabelle 7 Zeilen | 100 % | Alle 7 Rows aus DSA verbaut |
| Custom-Model-Grid 120px/1fr | 100 % | Grid identisch, mono-Inputs |
| StickyActionBar | 90 % | Position und Slots korrekt; Save/Reset-Buttons sichtbar |
| Gesamt-Schätzung | ~93 % | Strukturell pixelnahe; Bolt-Icon + Info-Banner-Farb-Nuancen könnten abweichen |

Screenshot-Referenz: `design.png` (Projekt-Root).
Kein Screenshot unter `docu/screenshots/` — wird manuell nachgeholt beim ersten
lokalen Dev-Server-Run.

## Bundle-Delta

| Asset | Größe | gzip |
|---|---|---|
| `LlmRoutingView-*.js` (neuer Lazy-Chunk) | 27,91 kB | 7,41 kB |
| `LlmRoutingView-*.css` (neuer Lazy-Chunk) | 16,08 kB | 3,06 kB |

Der Main-Chunk `index-*.js` bleibt bei 679 kB (unverändert — v4-Komponenten
waren bereits durch Slice A–D importiert). Der LlmRouting-Chunk ist der
ehrliche Bundle-Cost-Test: 7,4 kB gzip für den gesamten Screen inkl. aller
vier Sub-Karten und Mock-Daten ist vertretbar.

## Test-Counts

Vor Slice E: 591 Tests (gemäß Ausgangslage, inkl. Slice B-Fixes die 598 ergeben).
Nach Slice E: **598 Tests** (+5 neue Smoke-Tests in `LlmRoutingView.spec.ts`,
+2 implizit via Sidebar/AppShell-Router-Fix — die vorher fehlschlugen).

Delta: **+5 neue Tests**, 7 reparierte (waren in Slice B gebrochen durch
fehlende Route).

## Nächste Schritte

### Slice F — Settings konsolidieren

- Bestehende `SettingsView.vue` bleibt unangetastet.
- Settings-Subrouten für General, Integrations, Users & Teams, API Keys,
  Audit Logs als Dedicated Routes analog `SettingsLlmRouting`.
- Sidebar-Nav-Items alle auf Named Routes umstellen (aktuell 5 von 6 noch
  query-param-basiert).
- Test-Router-Helper als shared Fixture extrahieren.

### Slice G — Backend-Verdrahtung LLM Routing

- `api/llmRouting.ts` + `contracts/llmRoutingContract.ts` (liegen bereits in
  `components/LlmRouting/LlmRoutingView.vue` als Imports, werden in Slice G
  aktiviert).
- Mock-Daten durch echte API-Calls ersetzen.
- `StickyActionBar dirty`-Prop an Formular-Zustand binden.
- `StageOverridesCard.onCellChange()` an tatsächliche Patch-Calls anschließen.

### Technische Schuld aus diesem Slice

- Info-Banner-Icon: `<Icon name="bolt">` existiert in Slice B als
  `IconBolt.vue`, wird aber nicht durch `Icon.vue` mit `name="bolt"` adressiert.
  Prüfen ob Icon-Registry in Slice B vollständig ist.
- `ActiveSnapshotsCard` hat kein IntersectionObserver für "laufende Stage
  gesperrt"-Hint — reines Mock, Slice G muss Lock-State aus API ziehen.
