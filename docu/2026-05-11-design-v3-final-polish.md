# Design v3 Final Polish

Branch: `chore/design-v3-final-polish`
Worktree: `/private/tmp/agora-design-v3-polish`
Basis: `origin/main @ 7cd124e`
Datum: 2026-05-11

## Ziel

Restliche v2/Editorial-Spuren nach dem Design-Language-v3-Rollout
(PR #339 + #401) in einer kleinen, reviewbaren Slice schließen. Kein
v3-Neubau, keine `global.css`-Ausdünnung, kein Backend.

## Inventar (verifiziert via rg, 2026-05-11)

Quelle: `rg 'ff-serif|font-style:\s*italic|AuroraBackground|ThemeToggle|useTheme|data-theme="dark"' frontend/src` (ohne Compat-Layer `tokens-v3.css` und ohne `global.css`).

### Diese Slice migriert (Pflicht)

| Datei | Funde | Entscheidung |
|---|---|---|
| `frontend/src/App.vue` | `AuroraBackground` Import + Mount, `useTheme()` Call | Beides entfernen, `log-drawer-fab` auf v3-Tokens |
| `frontend/src/components/AppFooter.vue` | 1× `ff-serif` + `italic` (Autorlink) | sans, kein italic |
| `frontend/src/views/Home.vue` | 7× `ff-serif`, 1× `italic` | sans-Migration, hero ohne italic |
| `frontend/src/components/Step1GraphBuild.vue` | 2× `ff-serif` | sans-Migration |
| `frontend/src/components/Step5Interaction.vue` | 4× `ff-serif`, 2× `italic` | sans-Migration |
| `frontend/src/views/SettingsView.vue` | 3× `ff-serif` | sans-Migration |
| `frontend/src/views/RunsView.vue` | 1× `ff-serif` | sans-Migration |
| `frontend/src/composables/useTheme.ts` | Self-Definition | Datei löschen, wenn App.vue-Import weg |
| `frontend/src/components/ui/AuroraBackground.vue` | Self-Definition | Datei löschen, wenn App.vue-Mount weg |

### Bewusst zurückgestellt (Compat-Layer trägt)

`tokens-v3.css` aliasiert `--ff-serif: var(--font-sans)`, `--mesh-*: transparent`,
`--plasma-*/--brand-*/--neon-orange-* → --accent`. D. h. die folgenden Files
rendern bereits v3-korrekt; sie referenzieren nur noch Legacy-Token-Namen.
Cleanup als Folge-Slice (`global.css`-Ausdünnung + Side-Surface-Sweep):

- `frontend/src/components/HistoryDatabase.vue` (2×)
- `frontend/src/components/RunsDashboard.vue` (1×, `--ff-serif, serif` Fallback)
- `frontend/src/components/LogDrawer.vue` (1× `italic` für `.meta`)
- `frontend/src/components/Step3Simulation.vue` (1×)
- `frontend/src/components/Step4Report.vue` (3×, 1× `italic`)
- `frontend/src/components/step4/ReportOutlinePanel.vue` (3×, 1× `italic`)
- `frontend/src/components/step4/ReportEvidencePanel.vue` (1× `italic`)
- `frontend/src/components/step2/PersonaCardGrid.vue` (1×)
- `frontend/src/components/step2/AddPersonaModal.vue` (2×)
- `frontend/src/components/step2/PersonaDetailModal.vue` (3×, 1× `italic`)
- `frontend/src/composables/useReportExports.ts` (1× `italic` in HTML-Export-CSS)

`global.css` enthält ca. 25 weitere `ff-serif`/`plasma`/`brand-*`-Stellen
(Editorial-Layout, `.persona`, `.card-work`, `.serif`-Utility). Wird NICHT in
dieser Slice angefasst, weil:

1. Compat-Layer macht sie visuell korrekt.
2. Diff würde die Slice sprengen und Regressionsrisiko in Step2/Step4 erhöhen.
3. Folge-Slice mit gezielter `global.css`-v3-Refactor folgt.

## Decisions (vor Implementation)

- AuroraBackground.vue: gelöscht nach App.vue-Cleanup (rg ergibt 0 Imports).
- useTheme.ts: gelöscht nach App.vue-Cleanup (rg ergibt 0 externe Imports).
- log-drawer-fab in App.vue: migriert auf
  `--surface-elevated/--text-secondary/--hairline/--focus-ring`.
- `global.css` nicht ausdünnen — Folge-Slice.

## Validierung

- `cd frontend && npm run check`
- Stop-Condition: `rg -n 'ff-serif|font-style:\s*italic|AuroraBackground|ThemeToggle' frontend/src | rg -v 'tokens-v3.css|global.css' | wc -l` muss nach Slice deutlich kleiner (nur „bewusst zurückgestellt"-Liste).

## Bewusst beibehalten

- `tokens-v3.css` Compat-Layer (v2→v3-Aliase) bleibt unverändert.
- `global.css` v2-Editorial-Blöcke (Folge-Slice).
- Die in „bewusst zurückgestellt" gelisteten Files (Compat-Layer trägt visuell).

## Commits

Werden in der Reihenfolge des Briefs erstellt, je Schritt ein Commit.
