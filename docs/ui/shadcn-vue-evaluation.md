# shadcn-vue + Tailwind — Evaluation und Entscheidung

Stand: 2026-05-15 · Trigger: externer UI-Adaptions-Guide schlug Migration auf
**Bun + shadcn-vue + Tailwind + daisyUI** vor.

Diese Doku ist die einseitige Antwort: **Wir migrieren nicht**. Hier die Gründe,
damit die Entscheidung später nicht ohne Kontext aus dem Boden gezogen wird.

## TL;DR

- Bun-Migration: **bereits durch** (`bun.lock` committed, alle Scripts laufen
  über Bun).
- code-review-graph: **bereits durch** (v2.3.3 installiert, Graph aktuell).
- Tailwind-Installation: **abgelehnt**. Dupliziert das vorhandene
  CSS-Custom-Property-Tokensystem in `tokens-v3.css` ohne Mehrwert.
- shadcn-vue-Installation: **abgelehnt**. Die vorgeschlagenen Komponenten
  (DataTable, Card, EmptyState, ProviderForm, Dialog) existieren in
  `components/v4/` bereits in mindestens gleicher Qualität.
- daisyUI: **abgelehnt** als Produktiv-Library, optional als Inspirations-Quelle
  in einem Wegwerf-Branch.

## Was die Anleitung wollte

1. Bun als Standard (Migration npm/pnpm → Bun).
2. code-review-graph als Pflicht-Tool für Architektur-Reviews.
3. shadcn-vue als Komponenten-Quelle: Button, Card, Input, Label, Dialog, Alert,
   Skeleton, Table, Tabs, DropdownMenu, Chart.
4. Tailwind als Styling-Engine.
5. Agora-Wrapper über shadcn-vue (`AgoraMetricCard`, `AgoraEmptyState`, …).
6. daisyUI als Pattern-Inspirations-Quelle.

## Was Agora bereits hat (Auszug)

| Anleitung-Wunsch | Status im Repo |
|---|---|
| Bun | ✅ 1.3.14, `bun.lock` in `/` und `frontend/` |
| code-review-graph | ✅ 2.3.3 installiert |
| `Button` | ✅ `components/ui/Btn.vue` (Legacy, v4-Port offen) |
| `Card` | ✅ `components/v4/forms/Card.vue` + Legacy |
| `Input` | ✅ `components/v4/forms/Input.vue` |
| `Label`/`Field` | ✅ `components/v4/forms/Field.vue` |
| `Select` | ✅ `components/v4/forms/Select.vue` |
| `Tabs` | ✅ `components/v4/data/Tabs.vue` + `SegmentedControl.vue` |
| `Table` / `DataTable` | ✅ `components/v4/data/DataTable.vue` (Generics, Sticky, Slots) |
| `EmptyState` | ✅ `components/v4/data/EmptyState.vue` |
| `Skeleton` | ✅ `components/v4/forms/Skeleton.vue` (Slice UI-D, 2026-05-15) |
| `Dialog` | ✅ `components/v4/data/Dialog.vue` Focus-Trap + Scroll-Lock (Slice UI-E, 2026-05-15) |
| `Alert` / Toast | ✅ `components/v4/data/Alert.vue` inline (Slice UI-F, 2026-05-15); Toast offen |
| `DropdownMenu` | ✅ `components/v4/forms/DropdownMenu.vue` + Item (Slice UI-G, 2026-05-15) |
| `Chart` | ✅ `components/v4/data/Chart.vue` D3-Wrapper (Slice UI-B, 2026-05-15) |
| Tokens-System | ✅ `tokens-v3.css` (430 LOC, Light + Dark, Apple-System-Tokens) |

Die echten Lücken sind: **Skeleton, Dialog, Alert, DropdownMenu, Chart-Wrapper**.
Das sind ~5 Komponenten — keine 50. Plus `Button`/`Kicker`-Ports macht 7 Komponenten,
**alle in diesem Epic implementiert** (siehe Audit, UI-A bis UI-G).

## Kosten einer shadcn-vue + Tailwind Migration

### Direkte Kosten

1. **Build-Layer-Erweiterung**: `tailwindcss`, `@tailwindcss/vite`,
   `tailwindcss-animate`, `class-variance-authority`, `clsx`, `tailwind-merge`,
   `lucide-vue-next`, `reka-ui` als neue Dependencies. Aktuell **null** davon installiert.
2. **CSS-Duplikation**: Tailwind-Tokens (`primary`, `secondary`, `muted`,
   `accent`, …) müssen 1:1 auf die existierenden CSS-Variablen gemappt werden,
   sonst entstehen zwei parallele Designsysteme.
3. **Namespace-Kollision**: shadcn-vue installiert standardmäßig nach
   `src/components/ui/`. Dort liegen aber **11 existierende Agora-Komponenten**.
   Init-Skript könnte überschreiben.
4. **API-Inkompatibilität**: Bestehende Komponenten nutzen scoped CSS + Tokens.
   shadcn-vue nutzt Tailwind-Utility-Klassen. Mischung führt zu zwei
   Styling-Idiomen, die Reviewer parallel halten müssen.

### Indirekte Kosten

5. **Test-Migration**: ~70 existierende Tests in `__tests__/` referenzieren
   konkrete Komponenten und Klassennamen. Migration bricht Tests.
6. **Wording-Drift**: shadcn-vue Defaults sind englisch. Agora ist deutsch
   (siehe `EmptyState.vue` `title: 'Keine Daten'`). Re-Translation-Aufwand.
7. **Lighthouse/Bundle-Size**: Tailwind PurgeCSS + Reka-UI ist zwar getreed,
   aber das Initial-Bundle wächst messbar. Aktuelle Bundle-Size-Gates (M11.5)
   müssten neu kalibriert werden.
8. **Layer-9-Hardening-Re-Validation**: Production-Stack-Smokes
   (`docker-image.yml::prod-proxy-smoke`) müssten gegen das neue
   Frontend-Bundle neu verifiziert werden.
9. **Review-Overhead Gemini**: Cross-Cutting-Change → Gemini-Findings auf
   jedem PR. CLAUDE.md `Pflicht`: 90s warten + Findings-Sichtung pro PR.

### Opportunitätskosten

10. **Aktive Hot-Spots** verzögern sich: v1.0-Output-Vertrag P3.2/P4.1/P4.3/P4.4
    sind offen, Observability Slice 1 ist geplant. Bun+shadcn-Migration würde
    sich quer durch beide ziehen.

## Was eine Migration nicht bringt

- **Konsistenz**: bereits vorhanden, durchgängiges Token-System.
- **Theming**: bereits vorhanden, Light/Dark via `data-theme`.
- **A11y**: shadcn-vue ist gut, aber Reka-UI = Radix-Vue ist Custom-Build.
  Aktuelle v4 nutzt native HTML + manuelle ARIA — vergleichbar.
- **TypeScript-Generics**: `DataTable<TRow>` ist bereits generisch.
- **Slot-driven Composition**: bereits Standard in v4.
- **Geschwindigkeit**: Vue+Vite+Bun ist bereits am Stack-Maximum.

## Was eine Migration in Wahrheit bringen würde

- **Optik-Variation**: andere Default-Looks. Wer Agora-v4-Designs als zu nüchtern
  empfindet, würde durch shadcn-vue „mehr Bewegung" sehen. Das ist Geschmack,
  kein Engineering-Argument.
- **Externe Bekanntheit**: shadcn-vue ist ein bekanntes Pattern, neue
  Mitarbeiter finden schneller rein. **Aber**: Agora hat kein Team außer Alex.
  Für Solo-Maintenance ist die eigene v4 lesbarer (430 LOC Tokens vs.
  Tailwind-Config + globals + components.json).

## Entscheidung

**Nein zu Tailwind + shadcn-vue + daisyUI für Agora.**

Stattdessen wurden die echten Lücken in **eigenen Mini-Slices** in diesem Epic geschlossen:

1. ✅ `v4/forms/Skeleton.vue` (UI-D) — Loading-State für DataTable, Cards, etc.
2. ✅ `v4/data/Dialog.vue` (UI-E) — modaler Container mit Focus-Trap + Scroll-Lock.
3. ✅ `v4/data/Alert.vue` (UI-F) — inline-Banner Info/Success/Warning/Danger, dismissible.
4. ✅ `v4/forms/DropdownMenu.vue` + `DropdownMenuItem.vue` (UI-G) — Action-Menü mit ESC-Close.
5. ✅ `v4/data/Chart.vue` (UI-B) — D3-Wrapper mit standardisiertem Header (Titel,
   Zeitraum, Einheit, Interpretation).

Plus die Audit-Empfehlungen:

6. ✅ `v4/forms/Button.vue` (UI-A) — typesafe Wrapper über bestehende `.btn`-CSS.
7. ✅ `v4/data/Kicker.vue` (UI-C) — typesafe Port von `ui/Kicker.vue`.

Jedes davon ist 30–250 LOC, eigenständig testbar, kein Build-Layer-Eingriff.
Test-Coverage pro Komponente: 5–10 Vitest-Smokes, 52 Tests insgesamt grün.

## Was Bun und code-review-graph angeht

Beide sind bereits Standard. Keine weitere Aktion nötig. Die Anleitung-Phasen 3,
3A und 7 sind effektiv schon erledigt:

- `vite.config.js` Alias `@` → `src` ist gesetzt.
- `tsconfig.json` `paths: { "@/*": ["src/*"] }` ist gesetzt.
- `package.json` `packageManager`/`scripts` laufen über Bun.
- `.code-review-graphignore` und Auto-Update sind in CLAUDE.md verankert.

Lediglich der explizite `.code-review-graphignore` im Repo-Root kann ergänzt
werden, falls noch nicht vorhanden — das ist eine Trivialität.

## Optional: daisyUI als Sandbox

Wenn Pattern-Inspiration gesucht wird (z. B. Stats-Card-Variation,
Stepper-Idee), kann daisyUI in einem **Wegwerf-Branch** `test/daisyui-patterns`
installiert werden. **Nicht main, nicht in einen PR.** Pattern visuell
abgreifen, dann in `v4/`-Style nachbauen.

## Referenzen

- [`design-language-v4.md`](./design-language-v4.md) — Real-State der v4
- [`component-audit.md`](./component-audit.md) — Komponentenliste + Empfehlungen
- [`ui-rules.md`](./ui-rules.md) — Implementierungsregeln
- Top-Level [`CLAUDE.md`](../../CLAUDE.md) — Branch-/PR-/Verbots-Regeln
- Epic-Doku: [`docs/2026-05-11-design-v4-app-shell-epic.md`](../2026-05-11-design-v4-app-shell-epic.md)
