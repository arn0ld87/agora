# Agora UI-Regeln

Diese Regeln sind aus der bestehenden v4-Code-Realität abgeleitet (Stand 2026-05-15,
Commit `de933b9`). Sie kodifizieren Patterns, die in `components/v4/` bereits
konsistent gelebt werden, damit neue Komponenten nicht aus dem Rahmen fallen.

## Verzeichnis-Regeln

- Neue Komponenten landen unter `frontend/src/components/v4/<bucket>/`.
  Buckets: `shell`, `forms`, `data`, `dashboard`, `steps`.
- Falls keine bestehende Bucket passt: neuen Bucket anlegen, in
  [`component-audit.md`](./component-audit.md) eintragen.
- `frontend/src/components/ui/` ist **read-only Legacy-Zone**. Keine neuen Files.
  Bestehende Komponenten dürfen Bugfixes erhalten, aber keine Feature-Erweiterung.
- Views unter `frontend/src/views/` importieren bevorzugt v4-Bausteine, nicht
  Top-Level-Step-Container.
- Zugehörige Smoke-Tests liegen direkt neben der Komponente in
  `__tests__/<Component>.spec.ts`.

## Komponenten-API-Regeln

- **TypeScript first**: `<script setup lang="ts">`. JS-only erlaubt nur für
  Trivialfälle in `components/ui/`-Legacy.
- **Props via `defineProps<{}>()`** + `withDefaults` für Default-Werte.
- **Slots typisieren** über `defineSlots<{}>()` (siehe `EmptyState.vue`,
  `DataTable.vue`).
- **Generic-Slots** für Datenkomponenten: `<script setup lang="ts" generic="TRow extends Record<string, unknown>">`.
- **Events**: `defineEmits<{ … }>()`.
- **Composables** für geteilte Logik (z. B. `useShellStore`), nicht Mixins.

## Styling-Regeln

- `<style scoped>` pro Komponente. Keine globalen Klassen aus der Komponente
  selbst exportieren.
- Werte aus **CSS-Variablen** lesen, niemals hartkodierte Hex/RGBA:
  - Farben: `var(--surface-elevated)`, `var(--text-primary)`, `var(--accent)` …
  - Spacing: `var(--sp-4)` (4px-Raster).
  - Radius: `var(--r-3)`.
  - Shadows: `var(--shadow-1)`.
  - Typo: `var(--font-sans)`, `var(--fs-body)`.
- Fallback-Wert immer mitgeben: `var(--token, fallback)` — bei Theme-Wechsel
  oder fehlendem Token bleibt das Design stabil.
- Kein Tailwind, kein Sass, kein CSS-in-JS. Wenn dir CSS-Custom-Properties
  fehlen, lege sie in `tokens-v3.css` an und dokumentiere sie.

## Layout-Regeln

- AppShell ist der einzige Top-Level-Layout-Container. Views rendern in
  dessen `<slot />`.
- Padding-Defaults für Card-artige Container: `var(--sp-6)` rund.
- Gap-Defaults innerhalb Card: `var(--sp-4)`.
- Hairlines (1px) für Trennlinien, nicht Box-Shadows.

## Form-Regeln

- Jedes Input nutzt `<Field label hint error>` als Wrapper.
- API-Key-/Secret-Felder: `type="password"`, `autocomplete="off"`.
- Test-Connection-Button bei externen Provider-Forms (siehe `LlmProviderCard.vue`).
- Fehler-State pro Feld, nicht global, außer Submit-Errors.
- Submit/Cancel werden via `StickyActionBar` am unteren Rand fixiert,
  wenn die Form lang ist.

## Tabellen-Regeln

- `DataTable<TRow>` ist die kanonische Tabellenkomponente. Eigene
  `<table>`-HTML nur in Spezialfällen (Chart-Achsen, Persona-Diff-Matrix).
- Tabellen mit > 20 Zeilen brauchen Filter, Pagination oder
  Virtual-Scrolling. Bei Bedarf eigene Slice planen.
- Tabellen mit 0 Zeilen rendern `<EmptyState>` per `empty`-Slot, nicht leere
  `<tbody>`-Reihen.
- Aktionen pro Zeile via `actions`-Slot, rechts angeflanscht.

## Chart-Regeln

- Charts sitzen in einem Card-Container mit:
  - Titel (Pflicht)
  - Beschreibung (empfohlen)
  - Zeitraum (Pflicht, wenn zeitserie)
  - Einheit (Pflicht, wenn numerisch)
  - Interpretation/Legende (Pflicht, wenn nicht-trivial)
- D3 ist Standard. Keine Chart.js, keine ECharts. Wrapper-Komponente
  (`v4/data/Chart.vue`) ist offene Mini-Slice — siehe Audit.

## Empty-State-Regeln

- Jeder Listen-/Tabellen-/Card-Container mit dynamischen Daten braucht einen
  Empty-State.
- `<EmptyState title subtitle>` mit `actions`-Slot für Call-to-Action.
- Default-Titel ist deutsch ("Keine Daten"), aber konkretisieren wo möglich
  ("Noch keine Simulation gestartet").

## i18n-Regeln

**Faustregel**: Konsumenten-seitige Strings durch `vue-i18n`, Library-seitige
Strings durch overridebare Props.

- **Step*.vue, Views, Composable-Outputs**: alle user-facing Strings über
  `vue-i18n` (`t('…')`). Keys in `frontend/src/i18n/de.json` UND `en.json`.
  Hartkodierte deutsche Strings sind ausdrücklich verboten (siehe
  Top-Level-CLAUDE.md "Verboten").
- **v4-Library-Komponenten** (`components/v4/**`): dürfen deutsche Defaults für
  sichtbare Labels haben (`EmptyState.title: 'Keine Daten'`, `Alert.dismissLabel:
  'Schließen'`, `Chart.labels.timeRange: 'Zeitraum'` etc.) — diese Defaults
  müssen aber **immer per Prop überschreibbar** sein. Konsument übergibt dann
  `t('emptyState.title')`/`t('alert.close')` etc.
- **Aktuell sichergestellt** (Stand 2026-05-15): `EmptyState.title/subtitle`,
  `Alert.dismissLabel`, `Chart.labels.{timeRange,unit,loading}`,
  `DropdownMenu` (alle Texte slot-driven), `Dialog.{title,description,ariaLabel}`.

## Security-Regeln

- API-Keys werden **nie** dauerhaft im Frontend persistiert. Eingabe →
  Backend → verschlüsselt server-seitig (siehe `backend/data/llm_provider_secrets.lock`).
- Kein `localStorage`/`sessionStorage` für Secrets.
- DOMPurify-Pflicht für jedes `v-html`-Rendering (Markdown, externer HTML-Content).
- Niemals Demo-API-Keys in Code, Tests oder Storybook-Stories committen.
- ESLint-Regel `vue/no-v-html` ist warn — explizit begründen, wenn aktiv.

## A11y-Regeln

- Dekorative SVGs: `aria-hidden="true"`.
- Icon-Only-Buttons: `aria-label`.
- Fokus-Ring sichtbar via `--focus-ring`-Token, niemals `outline: none` ohne Ersatz.
- Tab-Reihenfolge im AppShell: Sidebar → Topbar → Main → Inspector.

## Test-Regeln

- Pro v4-Komponente ein Vitest-Smoke-Test in `__tests__/<Component>.spec.ts`.
- Mounting via `@vue/test-utils`. JSDom-Environment ist global in `vite.config.js`
  gesetzt.
- Composable-Tests separat in `frontend/src/composables/__tests__/`.
- E2E-Pflicht-Smokes laufen unter `frontend/tests/e2e/` via Playwright.
- Coverage-Schwellen aktuell 28 %, Ziel 60 % (CLAUDE.md M11.3 Step).

## Lint/Typecheck-Pflicht vor Commit

```bash
cd frontend
bun run typecheck
bun run lint
bun run test
bun run build
```

`bun run check` führt typecheck + test:coverage + build in einem Rutsch aus.

> Anmerkung: Die Top-Level-`CLAUDE.md` zeigt im aktuellen Stand teilweise noch
> `npm`-Befehle. Faktisch ist Bun (1.3+) der Standard im Repo — Lockfile ist
> `bun.lock` und `packageManager` ist Bun. Eine Synchronisierung der
> `CLAUDE.md`-Beispiele auf `bun run`-Form ist als separater Doku-Slice empfohlen.

## Anti-Patterns (sofort raus)

| Pattern | Warum nicht | Statt dessen |
|---|---|---|
| Hartkodierte Hex-Farben in Components | bricht Theme-Switch | `var(--accent)` etc. |
| Tailwind-Utility-Klassen | nicht installiert + dupliziert Tokens | scoped CSS + Tokens |
| Globale Klassennamen aus Components | leakt Styling | scoped + Tokens |
| Mixin-basierte Logik-Wiederverwendung | unklare Composition | Composables |
| `axios.get()` direkt in Components | mischt Layers | `src/api/*.ts` |
| `localStorage` für API-Keys | Security | Backend-Secrets |
| `console.log` in Prod-Code | Lärm | Im Frontend: dev-only `console.warn` mit Komponenten-Präfix oder `tracing.recordEvent`; im Backend: `app.logger` |
| Hartkodierte deutsche Strings in Step-Files | i18n-Bypass | `vue-i18n` |
| `<div>`-Tabellen für Listen-Layout | A11y + Styling-Overhead | `<DataTable>` oder semantisches HTML |
| Inline-CSS-Strings | bricht Tokens | scoped `<style>` |

## Referenzen

- Design-Language: [`design-language-v4.md`](./design-language-v4.md)
- Component-Audit: [`component-audit.md`](./component-audit.md)
- shadcn-vue-Entscheidung: [`shadcn-vue-evaluation.md`](./shadcn-vue-evaluation.md)
- Epic-Doku: [`docs/2026-05-11-design-v4-app-shell-epic.md`](../2026-05-11-design-v4-app-shell-epic.md)
