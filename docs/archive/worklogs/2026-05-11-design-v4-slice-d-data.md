# Design v4 — Slice D: DataTable + Tabs + EmptyState

**Datum:** 2026-05-11
**Branch:** feat/design-v4-slice-d-data
**Epic:** Design Language v4 (Slice A: Tokens, B: Shell, C: Forms, D: Data)

---

## Kontext

Slice D portiert die generischen Datendarstellungs-Primitiven aus der Design-Source
(`ds-screens-a.jsx :: DSA.LLMRouting`, `ds-screens-b.jsx :: DSB.Datasets`).
Scope: `frontend/src/components/v4/data/`.
Kein externes Table-Framework. Kein neues npm-Paket.

---

## Komponenten-API

### DataTable.vue

Generische Tabelle. Kein Sort/Filter/Pagination (kommen in Folge-Slices).

#### Props

| Prop | Typ | Default | Beschreibung |
|---|---|---|---|
| `columns` | `DataTableColumn[]` | — | Spalten-Definitionen |
| `rows` | `TRow[]` | — | Datensätze (`Record<string, unknown>`-Subtyp via generic) |
| `keyField` | `string` | `'id'` | Primär-Key-Feld; Fallback: `'key'`, dann Index |
| `rowClick` | `(row: TRow) => void` | `undefined` | Click-Handler; setzt `cursor: pointer` |
| `hover` | `boolean` | `true` | Hover-Highlighting |
| `sticky` | `boolean` | `true` | Sticky-Header (`position: sticky; top: 0`) |
| `compact` | `boolean` | `false` | Engerer Padding (6px statt 10px) |

#### DataTableColumn

```typescript
interface DataTableColumn {
  key: string
  label: string
  align?: 'left' | 'right' | 'center'   // default: left
  width?: string                          // CSS-Wert, z. B. '120px'
  mono?: boolean                          // font-family: var(--font-mono)
  secondary?: boolean                     // color: var(--text-secondary)
}
```

#### Slots

| Slot | Scope | Beschreibung |
|---|---|---|
| `cell-{key}` | `{ row, value, index }` | Custom-Renderer pro Spalte |
| `actions` | `{ row, index }` | Aktions-Spalte rechts (keine Header-Beschriftung) |
| `empty` | — | Empty-State (default: "Keine Daten") |

#### Beispiel: LlmRouting Stage-Overrides

```vue
<DataTable
  :columns="[
    { key: 'stage',    label: 'Stage',    mono: true },
    { key: 'provider', label: 'Provider', secondary: true },
    { key: 'model',    label: 'Model',    mono: true },
    { key: 'effort',   label: 'Effort',   secondary: true },
    { key: 'status',   label: 'Status' },
  ]"
  :rows="stageOverrides"
  key-field="stage"
>
  <template #cell-status="{ value }">
    <span :class="`pill pill--${value.color}`">
      <span class="dot" />{{ value.label }}
    </span>
  </template>
  <template #actions="{ row }">
    <button class="btn btn--secondary btn--sm" @click="editStage(row)">Edit</button>
  </template>
  <template #empty>
    <EmptyState title="Keine Stage-Overrides" subtitle="Globaler Default gilt für alle Stages." />
  </template>
</DataTable>
```

---

### Tabs.vue

URL-synced Tab-Bar. Schreibt/liest einen Query-Param (default: `tab`).

#### Props

| Prop | Typ | Default | Beschreibung |
|---|---|---|---|
| `modelValue` | `string` | — | Aktiver Tab-Key (v-model) |
| `tabs` | `TabItem[]` | — | Tab-Definitionen |
| `param` | `string` | `'tab'` | Query-Param-Name |
| `urlSync` | `boolean` | `true` | Wenn `false`: rein lokaler State, kein `router.replace` |

#### TabItem

```typescript
interface TabItem {
  key: string
  label: string
  badge?: string | number   // Badge rechts vom Label
  disabled?: boolean        // Tab nicht anklickbar
}
```

#### v-model

```vue
<Tabs v-model="activeTab" :tabs="pageTabs" />
```

#### Beispiel mit URL-Sync

```vue
<script setup lang="ts">
import { ref } from 'vue'
import Tabs from '@/components/v4/data/Tabs.vue'

const activeTab = ref('overview')
const tabs = [
  { key: 'overview',  label: 'Übersicht' },
  { key: 'routing',   label: 'LLM Routing', badge: 7 },
  { key: 'snapshots', label: 'Snapshots' },
]
</script>

<template>
  <Tabs v-model="activeTab" :tabs="tabs" param="section" />
  <!-- URL: ?section=routing -->
</template>
```

---

### EmptyState.vue

Zentrierter leerer Zustand. Vorbereitet für Slice-B-Icon-Anbindung (prop `icon` reserviert).

#### Props

| Prop | Typ | Default | Beschreibung |
|---|---|---|---|
| `title` | `string` | `'Keine Daten'` | Haupttext |
| `subtitle` | `string` | `undefined` | Erklärungstext |
| `icon` | `string` | `'table'` | Icon-Name-Stub (derzeit Inline-SVG) |

#### Slot

| Slot | Beschreibung |
|---|---|
| `actions` | CTA-Buttons unter dem Text |

#### Beispiel

```vue
<EmptyState
  title="Keine Datasets"
  subtitle="Lade ein Seed-Dokument hoch, um den Graph zu befüllen."
>
  <template #actions>
    <button class="btn btn--primary" @click="openUpload">Dataset hochladen</button>
  </template>
</EmptyState>
```

---

## Test-Counts

| Spec | Tests |
|---|---|
| DataTable.spec.ts | 7 |
| Tabs.spec.ts | 6 |
| EmptyState.spec.ts | 4 |
| **Gesamt Slice D** | **17** |

Gesamt-Suite nach Slice D: **52 Files / 518 Tests** (alle grün).

---

## LOC

| Datei | LOC |
|---|---|
| DataTable.vue | 247 |
| Tabs.vue | 172 |
| EmptyState.vue | 91 |
| DataTable.spec.ts | 120 |
| Tabs.spec.ts | 140 |
| EmptyState.spec.ts | 58 |
| **Gesamt** | **828** |

---

## Bekannte Grenzen (explizit Out-of-Scope)

- **Sort:** kein clientseitiges Sortieren. Agora-Tabellen sind klein (< 100 Zeilen),
  Sortier-Logik bleibt Verantwortung des Konsumenten oder kommt in Slice E+.
- **Filter:** analog — kein Column-Filter in DataTable.
- **Pagination:** nicht benötigt; alle existierenden Tabellen sind vollständig geladen.
- **Icon-Registry:** EmptyState nutzt Inline-SVG. Sobald Slice B eine Icon-Component
  liefert, reicht ein Prop-Swap (`<Icon :name="icon" />`), keine Refactor-Pflicht.
- **Virtualisierung:** nicht geplant. Bei > 500 Zeilen Slice N evaluieren.

---

## Empfehlung Slice E (LlmRouting-Pilot)

Slice E sollte `LlmRouting/LlmRoutingView.vue` (oder ein neues `v4/`-Pendant)
als ersten echten Konsumenten von `DataTable` bauen:

1. Stage-Overrides-Tabelle via `<DataTable>` + `#cell-status`-Slot für Pill.
2. Aktive-Snapshots-Tabelle via `<DataTable>` + `compact` Prop.
3. `<Tabs>` für die zwei Card-Tabs (Global Default / Stage Overrides).
4. Dabei `<EmptyState>` im `#empty`-Slot wenn noch keine Overrides konfiguriert.

Das validiert alle drei Primitiven in einem realen Screen und schafft die Brücke
zwischen Slice D (Primitiven) und dem bestehenden `LlmRouting/`-Verzeichnis.
