# Worklog FE-Redesign Slice 6 — Density-Toggle

**Datum:** 2026-05-15
**Branch:** `feat/fe-redesign-6-density`
**Worktree:** `/private/tmp/agora-fe-redesign-6`

## Pre-Flight

- Branch `feat/fe-redesign-6-density` aktiv ✓
- `frontend/node_modules` symlinked ✓
- Baseline typecheck sauber ✓

## Tool-Skip-Protokoll

- `code-review-graph::get_minimal_context_tool`: nicht verfügbar (Tool-Name stimmt nicht mit Registry überein; direkte Recherche via Read stattdessen).
- `context7`: nicht benötigt — kein Library/Framework-Lookup nötig (Vue 3 Composition API, CSS Custom Properties, Vitest — alles bekannt aus Projekt-Kontext).
- `sequential-thinking`: kein Multi-File-Ambigiuität; Plan-Dokument definiert alle Schritte exakt.

## Task 1: useDensity Composable

**RED:** Spec geschrieben, Module fehlend → 6 FAIL bestätigt.

**Anpassung gegenüber Plan:**
- Plan-Spec nutzt `localStorage.clear()` direkt — in Vitest jsdom-Umgebung ist `localStorage` nur über `vi.stubGlobal` verfügbar (analog `usePersonaQuota.spec.ts`). Spec auf Stub-Pattern umgestellt.
- `setDensity` setzt DOM-Attribut + localStorage synchron (nicht via `watch`), damit Tests ohne `nextTick` funktionieren. Macht API robuster.
- `_resetForTesting()` als named property auf der exportierten Funktion implementiert (TypeScript-kompatibel: `useDensity._resetForTesting = ...`).

**GREEN:** 6/6 Tests.

## Task 2: tokens-v3.css

- Shell-Chrome Density-Tokens im ersten `:root`-Block definiert: `--topbar-h/px`, `--sidebar-item-py/px`, `--sidebar-group-trigger-py`, `--sidebar-group-gap`, `--table-cell-py/px`, `--text-body-fs/lh`.
- `[data-density="compact"]`-Override-Block am Datei-Ende ergänzt.
- `Topbar.vue`: hartkodierte `height: 64px` und `padding: 0 24px` auf `var(--topbar-h, 64px)` / `var(--topbar-px, 24px)` umgestellt + CSS-`transition` für sanftes Umschalten.
- Andere Shell-Komponenten (Sidebar, SidebarGroup, SidebarItem) NICHT angefasst — Scope-Grenze eingehalten. DataTable-Variablen sind definiert, aber DataTable-Komponenten nutzen sie noch nicht (Followup nötig, falls vorhanden).

## Task 3: DensityToggle.vue

- `aria-pressed` korrekt gesetzt (Boolean-Attribut als String in Vue-Test-Utils: `'false'`/`'true'`).
- Spec nutzt selbes localStorage-Stub-Pattern wie Task 1.
- Topbar: `<DensityToggle />` vor `topbar__user` eingefügt, Import ergänzt.
- 6/6 bestehende Topbar-Tests unverändert grün.

## Task 4: main.ts Bootstrap

- `useDensity().applyOnMount()` nach `initFrontendTracing()` und `data-theme`-Attribut-Setzung eingebaut.
- Reihenfolge: Observability → Theme → Density → `createApp`.

## Verification Gates

| Gate | Ergebnis |
|------|----------|
| typecheck | ✓ (vue-tsc sauber) |
| test (820 Tests) | ✓ 820/820 |
| coverage (Schwelle 28 %) | ✓ Stmt 55 % / Branch 45 % / Fn 46 % / Lines 57 % |
| build | ✓ 513 ms |
| lint | ✓ (keine Findings) |

## Commits

1. `0006dc5` — `feat(composables): useDensity (compact/comfortable + persistence)`
2. `467c46e` — `feat(tokens): density-compact override block + Topbar konsumiert --topbar-h/px`
3. `730d61b` — `feat(shell): DensityToggle.vue + Topbar-Integration`
4. `bb8f4d5` — `feat(bootstrap): applyOnMount() vor app.mount() für FOUC-Schutz`

## Gaps / Followups

- `Sidebar.vue`, `SidebarGroup.vue`, `SidebarItem.vue`: nutzen noch hartkodierte Padding-Werte — können auf `--sidebar-item-py/px` und `--sidebar-group-gap` umgestellt werden (eigenständiger Slice, scope-konform).
- DataTable: `--table-cell-py/px` definiert, aber kein DataTable-Konsument im v4-Namespace vorhanden. Wert steht bereit.
- Dark/Light-Toggle: out-of-scope für Slice 6, wie im Plan dokumentiert.
- Visual-Smoke (Toggle persistiert über Reload): manuell nicht durchgeführt (kein Dev-Server gestartet), aber Mechanismus durch Tests abgedeckt.
