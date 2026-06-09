# v4 State-Audit — Slice FE-Redesign-3

Datum: 2026-05-15  
Branch: feat/fe-redesign-3-state-vocab

## Inventar (vor Migration)

### :hover

| Datei | Regeln |
|---|---|
| `v4/forms/Button.vue` | Keine eigenen :hover-Regeln (delegation an `.btn` in global.css) |
| `v4/forms/Input.vue` | `.v4-input:hover:not(:focus):not(:disabled) { border-color: var(--text-tertiary) }` |
| `v4/forms/Select.vue` | `.v4-select:hover:not(:focus) { border-color: var(--text-tertiary) }` |
| `v4/forms/SegmentedControl.vue` | `.v4-segmented__seg:hover:not(.active) { color: var(--text-primary) }` |
| `v4/forms/DropdownMenuItem.vue` | `.dmi-root:hover:not([data-disabled]) { background: var(--surface-hover) }` |
| `v4/data/Tabs.vue` | `.tabs-item:hover:not(.active):not(.disabled) { color: var(--text-primary) }` |
| `v4/shell/SidebarItem.vue` | `.sidebar-item:hover:not(.active) { background: var(--surface-hover, rgba(0,0,0,0.04)) }` |
| `v4/dashboard/ActiveRunsCard.vue` | Keine State-Regeln auf interaktiven Elementen |
| `v4/dashboard/HeroNewRun.vue` | Keine State-Regeln auf v4-Primitiven |
| `v4/dashboard/QuickActionsRow.vue` | Keine State-Regeln auf v4-Primitiven |
| `v4/dashboard/RecentReportsCard.vue` | Keine State-Regeln auf v4-Primitiven |
| `v4/dashboard/SystemHealthCard.vue` | Keine State-Regeln auf v4-Primitiven |
| `v4/data/Alert.vue` | Keine interaktiven States |

### :focus / :focus-visible

| Datei | Regeln |
|---|---|
| `v4/forms/Input.vue` | `.v4-input:focus { border-color: var(--accent); outline: 2px solid var(--focus-ring); outline-offset: -2px }` |
| `v4/forms/Select.vue` | `.v4-select:focus { border-color: var(--accent); outline: 2px solid var(--focus-ring); outline-offset: -2px }` |
| `v4/forms/DropdownMenuItem.vue` | `.dmi-root:focus-visible { outline: 2px solid var(--accent, currentColor); outline-offset: -2px }` |
| `v4/data/Tabs.vue` | `.tabs-item:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 2px }` |

### :disabled

| Datei | Regeln |
|---|---|
| `v4/forms/Button.vue` | Delegation an `.btn:disabled` in global.css |
| `v4/forms/Input.vue` | `.v4-input:disabled { opacity: 0.4; cursor: not-allowed; background: var(--surface-inset, #f2f2f7) }` |
| `v4/forms/Select.vue` | `.v4-select-wrap--disabled { opacity: 0.4; pointer-events: none }` |
| `v4/forms/DropdownMenuItem.vue` | `.dmi-root--disabled, .dmi-root[data-disabled] { opacity: 0.45; cursor: not-allowed }` |
| `v4/data/Tabs.vue` | `.tabs-item--disabled { opacity: 0.4; cursor: not-allowed }` |
| `v4/shell/SidebarItem.vue` | `.sidebar-item--disabled { opacity: 0.4; cursor: not-allowed; color: var(--text-secondary, var(--fg-muted, #888)) }` |

---

## Migrierte Komponenten — Vorher / Nachher

### 1. Button.vue

**Vorher:** Nur `.btn`-Klassen aus global.css. Keine direkte Mixin-Nutzung.

**Nachher:** Template erhält `class="btn v4-state-interactive"`. `.v4-state-interactive` liefert
`border`, `transition`, `cursor`, `:hover`, `:focus-visible`, `:disabled`. Die `.btn-*`-Varianten
in global.css übersteuern Hintergrund/Farbe mit höherer Spezifität. Kein Konflikt.

**Hartkodierte Werte entfernt:** keine (Button delegiert ohnehin nach global.css).

---

### 2. Input.vue

**Vorher:**
```css
.v4-input:focus {
  border-color: var(--accent);
  outline: 2px solid var(--focus-ring);
  outline-offset: -2px;
}
.v4-input:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  background: var(--surface-inset, #f2f2f7);
}
.v4-input:hover:not(:focus):not(:disabled) {
  border-color: var(--text-tertiary);
}
```

**Nachher:**
- `class="v4-input v4-state-interactive"` im Template.
- `:focus-visible` ersetzt `:focus` (a11y-konform).
- `opacity` und `cursor` bei disabled kommen aus `.v4-state-interactive:disabled`.
- `border-color: var(--text-tertiary)` ersetzt durch `var(--v4-state-hover-border)`.

```css
.v4-input:focus-visible {
  border-color: var(--accent);
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: -2px;
}
.v4-input:disabled {
  background: var(--surface-inset, #f2f2f7); /* nur BG override, rest via Mixin */
}
.v4-input:hover:not(:focus-visible):not(:disabled) {
  border-color: var(--v4-state-hover-border);
}
```

**Hartkodierte Werte entfernt:** `opacity: 0.4`, `cursor: not-allowed`, `2px solid var(--focus-ring)`.

---

### 3. Select.vue

**Vorher:**
```css
.v4-select:focus {
  border-color: var(--accent);
  outline: 2px solid var(--focus-ring);
  outline-offset: -2px;
}
.v4-select:hover:not(:focus) {
  border-color: var(--text-tertiary);
}
```

**Nachher:**
- `class="v4-select v4-state-interactive"` im Template.
- `:focus-visible` ersetzt `:focus`.
- `border-color: var(--text-tertiary)` ersetzt durch Token.
- Disabled-Handling: `.v4-select-wrap--disabled` für Wrapper-Opacity bleibt (Select-Element selbst nutzt Mixin nicht direkt, da `<select>` kein direktes CSS-scoped-Border erbt).

```css
.v4-select:focus-visible {
  border-color: var(--accent);
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: -2px;
}
.v4-select:hover:not(:focus-visible) {
  border-color: var(--v4-state-hover-border);
}
```

**Hartkodierte Werte entfernt:** `2px solid var(--focus-ring)`, `var(--text-tertiary)`.

---

### 4. SegmentedControl.vue

**Vorher:**
```css
.v4-segmented__seg:hover:not(.v4-segmented__seg--active) {
  color: var(--text-primary);
}
```

**Nachher:**
- `class="v4-segmented__seg v4-state-selectable"` pro Button im Template.
- `.v4-state-selectable` liefert `background: var(--v4-state-hover-bg)` beim Hover.
- Farb-Override bleibt als komponentenspezifisches Ergänzungs-Property:

```css
.v4-segmented__seg:hover:not(.v4-segmented__seg--active) {
  color: var(--v4-state-hover-fg);
}
```

**Hartkodierte Werte entfernt:** `color: var(--text-primary)` → Token.

---

### 5. DropdownMenuItem.vue

**Vorher:**
```css
.dmi-root:hover:not([data-disabled]),
.dmi-root[data-highlighted]:not([data-disabled]) {
  background: var(--surface-hover);
}
.dmi-root:focus-visible {
  outline: 2px solid var(--accent, currentColor);
  outline-offset: -2px;
}
.dmi-root--disabled,
.dmi-root[data-disabled] {
  opacity: 0.45;
  cursor: not-allowed;
}
```

**Nachher:**
- `class="dmi-root v4-state-selectable"` im Template.
- `.v4-state-selectable` deckt `:hover` + `[data-highlighted]` + `:focus-visible` ab.
- `transition: background 80ms ease` + `outline: none` aus Komponente entfernt (Mixin liefert).
- Disabled via eigene Regeln mit Tokens (`.v4-state-selectable` hat kein Disabled-Muster).

```css
/* Disabled: Token-Override */
.dmi-root--disabled,
.dmi-root[data-disabled] {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
}
```

**Hartkodierte Werte entfernt:** `background: var(--surface-hover)`, `2px solid var(--accent)`,
`opacity: 0.45`, `cursor: not-allowed`.

---

### 6. Tabs.vue

**Vorher:**
```css
.tabs-item:hover:not(.tabs-item--active):not(.tabs-item--disabled) {
  color: var(--text-primary);
}
.tabs-item--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.tabs-item:focus-visible {
  outline: 2px solid var(--focus-ring);
  outline-offset: 2px;
  border-radius: 2px;
}
```

**Nachher:**
- `class="tabs-item v4-state-selectable"` im Template.
- Farbe beim Hover über Token (statt Hardcode).
- Focus-Ring aus Token (Border-Radius bleibt komponentenspezifisch).
- `opacity: 0.4` → `var(--v4-state-disabled-opacity)`.

```css
.tabs-item:hover:not(.tabs-item--active):not(.tabs-item--disabled) {
  color: var(--v4-state-hover-fg);
}
.tabs-item--disabled {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
}
.tabs-item:focus-visible {
  outline: var(--v4-state-focus-ring-width) solid var(--v4-state-focus-ring);
  outline-offset: var(--v4-state-focus-ring-offset);
  border-radius: 2px;
}
```

**Hartkodierte Werte entfernt:** `2px solid var(--focus-ring)`, `opacity: 0.4`, `cursor: not-allowed`.

---

### 7. SidebarItem.vue

**Vorher:**
```css
.sidebar-item:hover:not(.sidebar-item--active) {
  background: var(--surface-hover, rgba(0, 0, 0, 0.04));
}
.sidebar-item--disabled {
  opacity: 0.4;
  cursor: not-allowed;
  color: var(--text-secondary, var(--fg-muted, #888));
}
```

**Nachher:**
- `class="sidebar-item v4-state-selectable"` im Template.
- Hover-BG über Token (kein Fallback-Literal).
- `transition: background 100ms ease, color 100ms ease` entfernt (Mixin liefert).
- `opacity: 0.4` → Token, `cursor: not-allowed` → Token, Fallback-Literal entfernt.

```css
.sidebar-item:hover:not(.sidebar-item--active) {
  background: var(--v4-state-hover-bg);
}
.sidebar-item--disabled {
  opacity: var(--v4-state-disabled-opacity);
  cursor: var(--v4-state-disabled-cursor);
  color: var(--text-secondary);
}
```

**Hartkodierte Werte entfernt:** `rgba(0, 0, 0, 0.04)`, `var(--fg-muted, #888)`, `opacity: 0.4`,
`cursor: not-allowed`, duplizierter `transition`-Block.

---

## Akzeptanzkriterien-Check

| Kriterium | Status |
|---|---|
| Mindestens 6 Komponenten konsumieren `.v4-state-interactive` oder `.v4-state-selectable` | 7 (Button, Input, Select, SegmentedControl, DropdownMenuItem, Tabs, SidebarItem) |
| Audit-Report mit vorher/nachher | Dieses Dokument |
| Alle bestehenden Tests grün | 839/839 |
| Bundle-Delta ≈ 0 | states.css < 2 KB, keine JS-Änderungen |
