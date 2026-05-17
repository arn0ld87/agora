# Design v4 — Slice C: Form Components Worklog

**Branch:** `feat/design-v4-slice-c-forms`
**Datum:** 2026-05-11
**Scope:** `frontend/src/components/v4/forms/`

---

## Komponenten-Liste

### Card

```vue
<Card title="LLM Routing" subtitle="Modell-Zuweisung konfigurieren" :pad="22">
  <template #right>
    <Badge tone="green">Aktiv</Badge>
  </template>
  Slot-Inhalt hier.
  <template #footer>
    <StickyActionBar>…</StickyActionBar>
  </template>
</Card>
```

**Slots:** default (Body), `#right` (rechts oben im Header), `#footer` (border-top separator).
**Props:** `title?`, `subtitle?`, `pad?` (default 22).
**LOC:** 93

---

### Field

```vue
<Field label="API-Schlüssel">
  <Input v-model="key" mono placeholder="sk-…" />
</Field>
```

**Slots:** default (das Control).
**Props:** `label` (required).
**LOC:** 39

---

### Input

```vue
<Input v-model="value" type="text" placeholder="Name" />
<Input v-model="token" mono placeholder="sk-…" />
<Input v-model="pw" type="password" :disabled="loading" />
```

**Props:** `modelValue` (required), `placeholder?`, `mono?`, `disabled?`, `type?: 'text'|'email'|'password'|'number'`.
**v-model:** `update:modelValue` emit.
**LOC:** 72

---

### Select

```vue
<Select
  v-model="provider"
  :options="[{ value: 'claude', label: 'Claude Haiku' }, { value: 'local', label: 'Ollama lokal' }]"
  placeholder="Bitte wählen"
/>
```

**Props:** `modelValue` (required), `options: Array<{value, label}>`, `placeholder?`, `disabled?`.
**Besonderheit:** Chevron-SVG inline — kein Dep auf `components/v4/shell/Icon.vue` (Slice B).
**LOC:** 84

---

### Badge / Pill

```vue
<Badge tone="green" :dot="true">Done</Badge>
<Badge tone="orange">Retry</Badge>
<Badge tone="red" :dot="false">Failed</Badge>
<Pill tone="teal">Queued</Pill>
```

**Tones:** `gray` (default), `green`, `orange`, `red`, `purple`, `teal`, `blue`.
**Props:** `tone?`, `dot?` (default true).
**Pill** ist eine Thin-Wrapper-Komponente über Badge (DS-Spec nutzt beide Bezeichnungen).
**LOC:** Badge 72, Pill 21

---

### SegmentedControl

```vue
<SegmentedControl
  v-model="effort"
  :options="[{ value: 'low', label: 'Low' }, { value: 'medium', label: 'Medium' }, { value: 'high', label: 'High' }]"
/>
```

**Props:** `modelValue` (required), `options: Array<{value, label}>`.
**v-model:** `update:modelValue` emit.
**LOC:** 65

---

### StickyActionBar

```vue
<StickyActionBar :dirty="hasChanges">
  <template #left>
    <button class="btn btn--secondary btn--sm">+ Override</button>
  </template>
  <template #right>
    <button class="btn btn--secondary">Verwerfen</button>
    <button class="btn btn--primary">Speichern</button>
  </template>
</StickyActionBar>
```

**Props:** `dirty?` (default false) — zeigt Fade-in "Ungespeicherte Änderungen"-Hint.
**Slots:** `#left`, `#right`.
**LOC:** 72

---

## Genutzte v3-Tokens

| Token | Komponenten |
|---|---|
| `--surface-elevated` | Card, Input, Select |
| `--surface-inset` | SegmentedControl, Input:disabled |
| `--surface-translucent` | StickyActionBar |
| `--hairline` | Card shadow, Input border, Select border |
| `--separator` | Card footer, StickyActionBar border-top |
| `--text-primary` | Input, Select, Card title, SegmentedControl active |
| `--text-secondary` | Field label, Card subtitle, Select chevron, Badge gray |
| `--text-tertiary` | Input placeholder, StickyActionBar dirty hint |
| `--font-sans` | alle Komponenten |
| `--font-mono` | Input mono-Variante |
| `--fs-callout` | Input, Select font-size (14px) |
| `--ctl-h-md` | Input, Select height (36px) |
| `--ctl-h-sm` | SegmentedControl seg height (28px) |
| `--r-4` | Input, Select border-radius (8px) |
| `--r-pill` | Badge, SegmentedControl border-radius |
| `--focus-ring` | Input, Select focus outline |
| `--accent` | Input focus border, Badge blue |
| `--accent-tint-bg` | Badge blue bg |
| `--shadow-control` | SegmentedControl active seg shadow |
| `--status-{tone}-bg` | Badge tone backgrounds |
| `--status-{tone}` | Badge tone text colors |
| `--gray-6` | SegmentedControl bg fallback |

---

## Unterschied zu bestehenden `ui/`-Komponenten

### `ui/Card.vue` vs `v4/forms/Card.vue`

`ui/Card.vue` (53 LOC) ist eine minimalistische Container-Komponente: ein `label`-Prop (String), `dark`- und `glass`-Modifier. Kein strukturierter Header, kein `right`-Slot, kein `footer`-Slot, kein `pad`-Prop.

`v4/forms/Card.vue` portiert `DSCard` aus `ds-shell.jsx` vollständig: strukturierter Header mit title/subtitle/right, footer-Slot mit separator, konfigurierbares Padding. Entspricht dem Layout-Muster aus den Settings-Screens (LLM Routing, Integrations).

### `ui/Select.vue` vs `v4/forms/Select.vue`

`ui/Select.vue` (77 LOC) enthält einen Label-Wrapper (kombiniert Label + Select in einem Compound), erwartet `options: Array` wobei Objekte oder Strings akzeptiert werden, kein `placeholder`-Prop für leere Auswahl, Chevron via CSS `::after`.

`v4/forms/Select.vue` ist ein reines Control ohne Label (das übernimmt `Field.vue`), strikt typisierte `options: Array<{value, label}>`, explizites `placeholder`-Option, Inline-SVG-Chevron (keine CSS-Tricks), `disabled`-Prop.

### `ui/Badge.vue` vs `v4/forms/Badge.vue`

`ui/Badge.vue` nutzt eine generische `variant`-String-Prop ohne Typ-Einschränkung und zeigt kein DS-konformes Styling. `v4/forms/Badge.vue` hat einen Union-Type `tone`, mappt auf die Status-Token-Paare (`--status-{tone}-bg`/`--status-{tone}`) aus `agora-v3.css` und ist damit konsistent mit den Pill-Klassen aus `ab3-foundations.jsx`.

---

## Migration-Pfad für Folge-Slices

1. **Slice D (Settings-Screens):** `Step2EnvSetup.vue` und die LLM-Routing-View können direkt auf `v4/forms/Card`, `Field`, `Input`, `Select`, `SegmentedControl` umsteigen — alle bestehenden ui/-Importe ersetzt.

2. **Slice E (Icon-Integration):** Den inline-SVG-Chevron in `Select.vue` durch `<Icon name="chevronD" />` aus `components/v4/shell/Icon.vue` (Slice B) ersetzen. Eine Zeile Änderung, kein Props-Breaking-Change.

3. **v3-Komponenten-Sunset:** `ui/Card.vue`, `ui/Select.vue`, `ui/Badge.vue`, `ui/Field.vue` können deprecated werden, sobald alle Aufrufer auf `v4/forms/` umgestellt sind. Reihenfolge: zuerst Settings-Views (Slice D), dann Step4Report (Step5), dann Step2EnvSetup.

4. **`Pill`-Entscheidung festhalten:** Pilot-Alias-Pattern (Pill wraps Badge) bewährt sich für DS-Spec-Konsistenz ohne Code-Duplikation. Gleiches Muster anwendbar auf zukünftige DS-Alias-Paare.

---

## Test-Counts

| Spec | Tests |
|---|---|
| Card.spec.ts | 7 |
| Field.spec.ts | 3 |
| Input.spec.ts | 6 |
| Select.spec.ts | 5 |
| Badge.spec.ts | 6 |
| Pill.spec.ts | 2 |
| SegmentedControl.spec.ts | 3 |
| StickyActionBar.spec.ts | 4 |
| **Gesamt neu** | **36** |
| Vorher (Slice A) | 501 |
| **Total** | **537** |
