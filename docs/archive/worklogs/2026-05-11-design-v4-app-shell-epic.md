# EPIC: Design Language v4 — App Shell Reskin

**Status:** Slice A abgeschlossen · Slice B–J ausstehend
**Owner:** Alexander Schneider (`arn0ld87`)
**Branch-Pattern:** `feat/design-v4-slice-*`
**Quelle:** `design/v3-source/agora-v3.css` (568 LOC, nach agora-v4-tokens Worktree vendored)

## Motivation

v3 wurde 2026-05-09 bis 2026-05-11 als vollstaendige Apple-Enterprise-Reskin
eingefuehrt und ist auf `main` gemerged. v4 ist **kein Brand-Pivot** — die Token-Werte
bleiben identisch. Ziel ist eine saubere Trennlinie:

- `tokens-v3.css` explizit auf `agora-v3.css` als Source-of-Truth ausrichten
- Compat-Aliase dokumentieren und mit Epic-Scope versehen
- App-Shell-Komponenten (Header, Layout, Navigation) schrittweise auf native v4-Tokens
  ohne Compat-Umwege migrieren
- Compat-Layer in Slice J schrittweise abbauen

## Uebergang v3 → v4

| Achse | v3 (Main) | v4 (dieses Epic) |
|---|---|---|
| Token-Werte | Apple Enterprise Blue, SF Pro / Geist, light-only | Identisch — kein Wert-Drift |
| Datei-Name | `tokens-v3.css` | Bleibt `tokens-v3.css` (Umbennen in Slice J) |
| @font-face | In `fonts.css` (korrekt) | Identisch — keine Duplikate |
| Compat-Layer | vorhanden, undokumentiert | Dokumentiert, mit Epic-Scope und Cleanup-Plan |
| Native Token-Anzahl | ~85 | 77 (exakt gezaehlt nach agora-v3.css :root) |
| Compat-Alias-Anzahl | ~125 | 133 (vollstaendig inventarisiert) |

## Slices

| Slice | Titel | Status | Inhalt |
|---|---|---|---|
| **A** | Token-Port | **abgeschlossen** | `agora-v3.css` als Basis fuer `tokens-v3.css`; Compat-Layer dokumentiert; Worklog in `docu/2026-05-11-design-v4-slice-a-tokens.md` |
| **B** | App-Shell native Tokens | ausstehend | `WorkspaceHeader`, `WorkspaceLayout`, `WorkspaceSplit` direkt auf `--surface-*`, `--text-*`, `--accent` ohne Compat-Umwege |
| **C** | Navigation native | ausstehend | `WorkspaceModeSwitch`, `WorkspaceStepStatus`, `WorkspaceBrandLink`, Sidebar-Nav auf `--surface-tint`, `--hairline`, `--sb-*` |
| **D** | UI-Kit native | ausstehend | `components/ui/Btn`, `Badge`, `Field`, `Card`, `SectionHead` auf native v4-Tokens; Legacy `.btn-*` Klassen aus `global.css` bereinigen |
| **E** | Step1–2 native | ausstehend | `Step1GraphBuild`, `Step2EnvSetup` + `step2/*`-Subkomponenten auf native v4 |
| **F** | Step3–4 native | ausstehend | `Step3Simulation`, `Step4Report` auf native v4; Confidence-Badge und Quote-Anchor auf `--status-*` direkt |
| **G** | Step5 + Graph native | ausstehend | `Step5Interaction`, `GraphPanel`, `graph/*`, `compare/*` auf native v4 |
| **H** | Settings + Runs native | ausstehend | `SettingsView`, `RunsDashboard`, `RunDetailView`, `PersonaReview` auf native v4 |
| **I** | global.css Cleanup | ausstehend | v1/v2-Utility-Klassen (`ink-*`, `plasma-*`, `neon-*`, `paper-*`) aus `global.css` entfernen; nur v4-native Utility-Klassen behalten |
| **J** | Compat-Layer Abbau | ausstehend | Compat-Aliase schrittweise entfernen (Gruppe fuer Gruppe, je nach Slice-B-I-Fortschritt); abschliessend `tokens-v3.css` -> `tokens-v4.css` umbenennen |

## Token-Inventar (Stand Slice A)

### Native v4-Tokens (77 Stueck, aus `agora-v3.css :root`)

**Surfaces (8):** `--surface-base`, `--surface-canvas`, `--surface-elevated`,
`--surface-translucent`, `--surface-tint`, `--surface-inset`, `--surface-hover`,
`--surface-pressed`

**Borders (4):** `--hairline`, `--hairline-strong`, `--separator`, `--focus-ring`

**Text (5):** `--text-primary`, `--text-secondary`, `--text-tertiary`,
`--text-quaternary`, `--text-on-accent`

**Accent (6):** `--accent`, `--accent-hover`, `--accent-pressed`, `--accent-tint-bg`,
`--accent-tint-bg-strong`, `--accent-tint-text`

**Status (12):** je Farbe `--status-{green,orange,red,purple,teal,gray}` + `-bg`

**Grays (6):** `--gray-1` bis `--gray-6`

**Type (2 Familien + 13 Skalen x 3 = 41):** `--font-sans`, `--font-mono`,
`--fs-*`, `--lh-*`, `--tr-*` (largeTitle bis caption-2 + hero + display)

**Radii (10):** `--r-2` bis `--r-9`, `--r-pill`

**Shadows (6):** `--shadow-1` bis `--shadow-4`, `--shadow-control`, `--shadow-inset`

**Spacing (10):** `--sp-1` bis `--sp-10`

**Control Heights (3):** `--ctl-h-sm`, `--ctl-h-md`, `--ctl-h-lg`

### Compat-Aliase (133 Stueck, nach Cleanup in Slice J)

| Gruppe | Anzahl | Beispiel |
|---|---|---|
| Brand-Axis | 4 | `--brand-aurora` → `--accent` |
| Neutral-Scale | 11 | `--ink-0..1000` |
| Surfaces v2 | 8 | `--bg`, `--bg-elevated`, `--bg-sunken` |
| Foreground v2 | 5 | `--fg`, `--fg-muted`, `--fg-meta` |
| Lines v2 | 3 | `--rule`, `--rule-strong`, `--rule-soft` |
| Mesh (deaktiviert) | 5 | `--mesh-1..4`, `--mesh-alpha` |
| Accent-Variants | 5 | `--accent-ink`, `--accent-soft`, `--glow-*` |
| Status v2 | 6 | `--ok`, `--warn`, `--err` + `-soft` |
| Status-Long-Form | 7 | `--status-success`, `--status-error` |
| Shadows/Glows v2 | 8 | `--shadow-glass`, `--shadow-popover`, `--glow-accent` |
| Type-Familien v2 | 3 | `--ff-sans`, `--ff-mono`, `--ff-serif` |
| Type-Sizes v2 | 20 | `--fs-11..120` |
| LH/LS v2 | 11 | `--lh-tight`, `--ls-display` |
| Spacing v2 | 10 | `--s-1..10` |
| Radii v2 | 2 | `--r-0`, `--r-1` |
| Controls v2 | 1 | `--ctl-pad-x` |
| Grid | 3 | `--grid-max`, `--grid-gutter`, `--grid-cols` |
| Background | 2 | `--bg-grid`, `--bg-page` |
| Mono-Scale v1 | 11 | `--mono-50..950` |
| Neon/Plasma/Paper v1 | 12 | `--neon-orange`, `--plasma-*`, `--paper-*` |
| Ink v1 | 5 | `--ink-1..5` |
| Dark-Mode-Stubs | 3 | `--bg-dark`, `--fg-on-dark` |

## CSS-Bundle-Delta (Slice A)

| Metrik | Vor v4 (main) | Nach Slice A | Delta |
|---|---|---|---|
| `tokens-v3.css` raw | 15 250 bytes | 16 035 bytes | +785 bytes |
| `tokens-v3.css` Zeilen | 427 | 441 | +14 |
| CSS-Bundle (Vite, minified) | 160.17 kB | 159.92 kB | -250 bytes |
| CSS-Bundle (gzip) | 24.10 kB | 24.07 kB | -30 bytes |

Minimal kleiner, weil doppelte `@font-face`-Deklarationen nicht eingefuehrt wurden
(agora-v3.css hat eigene @font-face — Slice A hat diese bewusst weggelassen, da
`fonts.css` bereits korrekt importiert ist).

## Lokale Gate-Ergebnisse (nach Slice A)

```
npm run typecheck  → 0 Fehler
npm test -- --run  → 49 Test Files, 501 Tests, alle passed
npm run build      → CSS 159.92 kB (gzip 24.07 kB), keine neuen Fehler
npm run lint       → 0 Fehler
```

## Architektur-Entscheidungen

### @font-face nicht duplizieren

`agora-v3.css` definiert eigene `@font-face`-Bloecke fuer Geist Sans/Mono.
Slice A hat diese **nicht** in `tokens-v3.css` uebernommen, da `fonts.css`
(mit korrekten relativen Pfaden `../fonts/`) bereits vor `tokens-v3.css` in
`main.ts` importiert wird. Doppeldeklarationen wuerden zu Netto-Null-Aenderung
im Browser fuehren, aber unnoetige CSS-Groesse addieren.

### --lh-* Ratio-Ueberschreibung (bewusst)

`agora-v3.css` definiert `--lh-body: 20px` und `--lh-display: 52px` als Pixel-Werte.
Der Compat-Layer ueberschreibt sie mit `--lh-body: 1.55` und `--lh-display: 1.08`
(Ratios), weil bestehende Komponenten diese als Ratios nutzen. Diese Ueberschreibung
ist dokumentiert und bleibt bis Slice J aktiv.

### Keine Vendor-Pfade in tokens-v3.css

`design/v3-source/` ist ein Vendor-Verzeichnis (Read-only Reference).
`tokens-v3.css` ist die einzige konsumierte Datei; alle anderen JSX-Dateien
sind Referenz-Implementierungen fuer spaetere Slice-B-I-Migrationen.

## Naechste Schritte

Slice B (App-Shell native Tokens) beginnt nach Integration von Slice A in den
Epic-Integrationsbranch. Kein Push/PR pro Slice — ein integrierter PR am Ende
des gesamten v4-Epics.
