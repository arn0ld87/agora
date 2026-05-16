# Worklog — FE-Redesign Slice 3 — State-Vokabular

Datum: 2026-05-15  
Branch: feat/fe-redesign-3-state-vocab  
Worktree: /private/tmp/agora-fe-redesign-3

## Vorgehen

**Tool-Reihenfolge (Pre-Flight):**
- code-review-graph: kein MCP-Server verfügbar im Worktree — Skip, direkte Inventarisierung via grep.
- context7: nicht erforderlich (keine Library-API-Fragen, reines CSS/Vue-Refactoring).
- sequential-thinking: nicht erforderlich (Single-File-Scope, klare Spec).

**Inventar (Step 1):**
`grep -rl ':hover|:focus-visible|:disabled'` auf `src/components/v4/` → 13 Dateien mit State-Regeln.
Kern-Ziel-Komponenten: Button, Input, Select, SegmentedControl, DropdownMenuItem, Tabs, SidebarItem.
Dashboard-Komponenten haben keine eigenen State-Regeln auf v4-Primitiven — kein Handlungsbedarf.

**states.css (Step 2):**
Exakt nach Plan-Spec geschrieben. Import nach `global.css` in `main.ts` eingefügt.

**Migrations-Entscheidungen (Step 3):**

1. **Button.vue:** `.btn`-Klassen in global.css haben bereits vollständige State-Regeln mit höherer
   Spezifität als `.v4-state-interactive`. Der Mixin liefert die semantische Deklaration;
   `.btn--*`-Varianten übersteuern sauber. Kein Duplikat-Problem.

2. **Input.vue + Select.vue:** `:focus` → `:focus-visible` migriert (war `outline: none` +
   `focus`-Kombinaton — a11y-Verbesserung). Hartkodiertes `var(--focus-ring)` → Token.
   `var(--text-tertiary)` als Hover-Border-Fallback entfernt → `var(--v4-state-hover-border)`.

3. **SegmentedControl.vue:** `.v4-state-selectable` passt besser als `.v4-state-interactive`,
   weil keine Border-Geometrie benötigt wird (Segmente sind borderlos innerhalb des Tracks).
   Hover-BG (neu durch Mixin) ist semantisch korrekt und leichte visuelle Verbesserung.

4. **DropdownMenuItem.vue:** Alle drei State-Blöcke (hover+data-highlighted, focus-visible,
   disabled) durch Mixin ersetzt. `transition` + `outline: none` aus Komponenten-CSS entfernt.
   Danger-Variante behält eigenen BG-Override (spezifisch, kein Token-Äquivalent).

5. **Tabs.vue:** Tab-Geometrie-spezifisches `border-radius: 2px` auf `:focus-visible` bleibt
   Komponenten-Override (nicht generalisierbar in Mixin). Alle anderen Values tokenisiert.

6. **SidebarItem.vue:** `rgba(0, 0, 0, 0.04)` als Hardcode-Fallback im Hover entfernt;
   `var(--v4-state-hover-bg)` ist der korrekte Token. `transition`-Duplikat entfernt.
   Inline-Fallback-Chain `var(--text-secondary, var(--fg-muted, #888))` auf einfachen Token
   reduziert.

## Verification

```
typecheck: PASS (0 errors)
tests:     839/839 PASS (108 test files)
build:     PASS (519ms)
lint:      PASS (0 warnings)
```

Bundle-Delta: states.css ~1.8 KB unminified (~0.7 KB gz) — Ziel ≈ 0 eingehalten (kein JS-Delta).

## Akzeptanzkriterien

- [x] mindestens 6 Komponenten konsumieren `.v4-state-interactive` oder `.v4-state-selectable` — 7 erreicht
- [x] Audit-Report mit vorher/nachher — `docu/2026-05-15-v4-state-audit.md`
- [x] Alle bestehenden Tests grün — 839/839
- [x] Bundle-Delta ≈ 0

## Geänderte Dateien

- `frontend/src/assets/styles/states.css` (neu)
- `frontend/src/main.ts` (import ergänzt)
- `frontend/src/components/v4/forms/Button.vue`
- `frontend/src/components/v4/forms/Input.vue`
- `frontend/src/components/v4/forms/Select.vue`
- `frontend/src/components/v4/forms/SegmentedControl.vue`
- `frontend/src/components/v4/forms/DropdownMenuItem.vue`
- `frontend/src/components/v4/data/Tabs.vue`
- `frontend/src/components/v4/shell/SidebarItem.vue`
- `docu/2026-05-15-v4-state-audit.md` (neu)

## Gaps / Offen

- Dashboard-Komponenten (ActiveRunsCard, HeroNewRun, QuickActionsRow, RecentReportsCard,
  SystemHealthCard) haben eigene State-Regeln, die direkt an DOM-Elemente binden, nicht
  an v4-Primitive. Diese sind nicht Teil des Slice-3-Scopes und bleiben für späteres
  Housekeeping offen.
- `DataTable.vue`: hat `:hover` auf `tr`-Rows (via global.css). Kein v4-State-Mixin-Kandidat,
  da Table-Row kein interaktives v4-Primitiv ist.
- `LlmProviderCard.vue`, `LlmProfileManager.vue`: haben `:hover` + `:focus-visible` auf
  internen DOM-Elementen; würden von einem `v4-state-interactive`-Mixin profitieren, waren
  aber nicht in der Mindest-6-Ziel-Liste und bleiben für Folge-Slice.
