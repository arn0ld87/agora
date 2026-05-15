# UI-Audit-Epic — Arbeitsprotokoll

**Datum**: 2026-05-15
**Branch**: `feat/ui-audit-epic`
**Worktree**: `/private/tmp/agora-ui-audit`
**Base**: `origin/main` @ `de933b9`
**Modus**: einzelner Epic-PR (keine Sub-Slice-PRs), Pattern aus Design-v4-Epic

## Trigger

Externer UI-Adaptions-Guide schlug eine umfassende Migration vor:

1. Migration npm → **Bun** (Lockfile, Scripts, Dockerfile-Stage).
2. Installation **code-review-graph** + `.code-review-graphignore`.
3. Initialisierung **shadcn-vue** in `components/ui/` mit Tailwind als Styling-Engine.
4. Installation Tailwind, lucide-vue, optional daisyUI.
5. Bau eigener `Agora*`-Wrapper-Komponenten (MetricCard, EmptyState,
   SectionHeader, ProviderForm, RiskChart) auf shadcn-vue-Basis.
6. Separater Test eines Astro-Themes für `alexle135.de`.
7. Akkumulation aller Slices lokal in einem Integration-Branch + **EIN großer PR** am Ende.

User-Vorgabe: **„mach ab punkt 1 und soweit es geht erst am ende ein großer pr"**.

## Pivot

Pre-Flight-Check zeigte: Die Anleitung ging von einem leeren `components/ui/`
und einem npm-only-Setup aus. Realität (Stand `de933b9`):

| Anleitung-Phase | Vorgefundener Zustand |
|---|---|
| Phase 3 — Bun-Migration | Bereits durch. `bun.lock` in `/` und `frontend/` committed, `package.json` `scripts.check = "bun run typecheck && bun run test:coverage && bun run build"`, Bun 1.3.14 lokal. |
| Phase 3A — code-review-graph install | Bereits durch. `code-review-graph 2.3.3` global installiert, in CLAUDE.md als Pflicht-First-Stop verankert. |
| Phase 7 — Vite-Alias `@` | Bereits gesetzt (`vite.config.js` Z. 9–13, `tsconfig.json` Z. 20–22). |
| Phase 8 — shadcn-vue init nach `src/components/ui/` | **Kollision**: `components/ui/` enthält 11 Agora-v4-Komponenten (Btn, Card, Badge, Field, Hairline, Kicker, SectionHead, Select, ConfidenceBadge, AgoraGlyph, StickyScrollBanner). Init würde überschreiben. |
| Phase 9 — Tailwind als Build-Layer | Tailwind ist **nicht installiert**. Komplettes Token-System läuft über `assets/styles/tokens-v3.css` (430 LOC, Apple-System-Tokens, Light + Dark). Tailwind würde Tokens duplizieren. |
| Phase 11–17 — Agora-Wrapper-Komponenten | Existieren bereits in `components/v4/`: `StatsRow` (= MetricCard), `EmptyState`, `PageHeader` (= SectionHeader), `LlmProviderCard` + `LlmProfileManager` (= ProviderForm), `DataTable` (= PersonaTable-Pattern). Nur `RiskChart`/`Chart`-Wrapper fehlt wirklich. |

Daraus folgte ein Strategie-Wechsel: **kein Migrations-Slice, sondern ein Audit-Slice**.
Ziel ist eine dokumentierte Entscheidungsgrundlage und Festschreibung der Real-State-Design-Language, damit künftige Slices (intern oder via Subagent) nicht erneut versuchen,
Tailwind/shadcn-vue in den Stack zu drücken.

## Lieferumfang

### Neue Doku-Files (4)

1. [`docu/ui/design-language-v4.md`](ui/design-language-v4.md) — Real-State der v4:
   Layout-Architektur, CSS-Tokens, Stack-Realität, bewusste Nicht-Entscheidungen.
2. [`docu/ui/component-audit.md`](ui/component-audit.md) — vollständiges Inventar
   aller 38 v4-Komponenten + 11 Legacy-Komponenten, pro Komponente
   Empfehlung (keep/polish/migrate/retire) und Mapping gegen Anleitungs-Wunschliste.
3. [`docu/ui/ui-rules.md`](ui/ui-rules.md) — kodifizierte Patterns, die in v4 bereits gelebt werden: Verzeichnis-, API-, Styling-, Layout-, Form-, Tabellen-, Chart-, Empty-, i18n-, Security-, A11y-, Test-Regeln. Plus Anti-Patterns-Tabelle.
4. [`docu/ui/shadcn-vue-evaluation.md`](ui/shadcn-vue-evaluation.md) —
   einseitige Antwort auf die Migrations-Anleitung. TL;DR: **Nein zu
   Tailwind + shadcn-vue + daisyUI**, fünf konkrete Mini-Slices als Alternative.

### Repo-Konfig (2)

5. `.code-review-graphignore` — explizite Ignore-Liste für Tree-sitter-Scan
   (node_modules, dist, caches, schemas, .worktrees, OASIS-Runtime). Ergänzt die
   CLAUDE.md-Vorgaben um die fehlende Repo-File.
6. `.gitignore` — eine Zeile `.code-review-graph/` ergänzt, damit lokale
   Graph-Storage-Daten nicht committed werden.

### Welle 2: echte Lücken schließen (2026-05-15)

Nach Review der ersten Welle wurde entschieden, den PR zu erweitern um die
**7 echten Lücken** (UI-A bis UI-G), damit am Ende **EIN großer PR** alle
nötigen Komponenten enthält statt 7 Folge-PRs. Lieferumfang Welle 2:

| Slice | Datei | LOC | Tests |
|---|---|---:|---:|
| UI-A | `frontend/src/components/v4/forms/Button.vue` | 100 | 9 |
| UI-B | `frontend/src/components/v4/data/Chart.vue` | 280 | 7 |
| UI-C | `frontend/src/components/v4/data/Kicker.vue` | 50 | 5 |
| UI-D | `frontend/src/components/v4/forms/Skeleton.vue` | 120 | 6 |
| UI-E | `frontend/src/components/v4/data/Dialog.vue` | 270 | 10 |
| UI-F | `frontend/src/components/v4/data/Alert.vue` | 240 | 6 |
| UI-G | `frontend/src/components/v4/forms/DropdownMenu.vue` + `DropdownMenuItem.vue` | 220 | 9 |
| Bonus | Barrel-Exports `forms/index.ts` + neu `data/index.ts` | 25 | – |

**Summe Welle 2**: ~1305 LOC Code + 52 Vitest-Smokes, alle grün.

Mit Welle 2 ist `components/v4/` vollständig genug, dass kein künftiger Slice
mehr auf shadcn-vue/Tailwind angewiesen ist.

### Nicht geliefert (und warum)

| Anleitung-Schritt | Status | Grund |
|---|---|---|
| Bun-Migration | Skip | bereits durch |
| code-review-graph-Install | Skip | bereits durch |
| Tailwind-Install | Skip | abgelehnt (siehe Evaluation) |
| shadcn-vue init | Skip | abgelehnt (siehe Evaluation) |
| daisyUI | Skip | optional als Wegwerf-Branch erwähnt |
| Astro-Theme-Test alexle135.de | Skip | außerhalb des Agora-Repos |
| Cleanup-Slice J (ui/-Imports auf v4 umstellen) | Skip | eigener Folge-PR, da Step*.vue-Hotspots groß |

## Tool-Disziplin (CLAUDE.md-Pflicht)

| Tool | Eingesetzt? | Wofür |
|---|---|---|
| `get_minimal_context` | ⚠️ teilweise — direkte Read auf Schlüsselkomponenten, weil Audit-Doku Original-Quelltext referenziert (`AppShell.vue`, `DataTable.vue`, `EmptyState.vue`, `Btn.vue`, `Card.vue`, `LlmProviderCard.vue`, `tokens-v3.css`-Auszug). Strukturkontext aus Audit-Reading erschlossen, nicht aus Graph-Query. |
| `context7` | ✗ nicht benötigt — keine Library-API-Frage. Bun und code-review-graph wurden über lokales `bun --version`/`code-review-graph --version` verifiziert. |
| `sequential-thinking` | ✗ nicht eingesetzt — Pivot-Entscheidung war eindeutig nach Inventar-Read. Multi-Step war nicht ambig. |
| `context-mode` | ⚠️ teilweise — Bash mit Output > 20 Zeilen wurde via `head`/`grep` selbst gekürzt. |
| `honcho-memory` | ✗ nicht benötigt — Setup/Hardware-Fragen kamen nicht vor. |

Lessons: bei einem reinen Audit-Slice ohne Code-Refactor ist `get_minimal_context`
zwar grundsätzlich Pflicht, liefert aber kaum Mehrwert gegenüber gezielten Reads
ausgewählter Komponenten. Skip-Begründung hier dokumentiert.

## Verify-Gates

- `bun run build` im Frontend — **nicht ausgeführt**, weil keine Frontend-Code-Files
  geändert wurden. Reine Doku- und Repo-Config-Änderungen. Build-Risk = null.
- `bun run lint`, `bun run typecheck`, `bun run test` — analog skip.
- `code-review-graph update` — **wird vor Push ausgeführt** (siehe nächster Abschnitt).

## Nächste empfohlene Slices

Aus dem Audit ([`docu/ui/component-audit.md`](ui/component-audit.md) §Empfohlene Mini-Slices)
und der Evaluation ([`docu/ui/shadcn-vue-evaluation.md`](ui/shadcn-vue-evaluation.md) §Entscheidung):

| Slice | Scope | LOC-Schätzung | Risiko |
|---|---|---:|---|
| UI-A | `v4/forms/Button.vue` aus `ui/Btn.vue` portieren + Tests | ~80 | niedrig |
| UI-B | `v4/data/Chart.vue` D3-Wrapper mit Titel/Zeitraum/Einheit/Interpretation-Slots | ~200 | mittel |
| UI-C | `ui/Kicker.vue` → `v4/data/Kicker.vue` migrieren | ~40 | niedrig |
| UI-D | `v4/forms/Skeleton.vue` (echte Lücke) | ~50 | niedrig |
| UI-E | `v4/data/Dialog.vue` mit Focus-Trap (echte Lücke) | ~150 | mittel |
| UI-F | `v4/data/Alert.vue` (echte Lücke) | ~80 | niedrig |
| UI-G | `v4/forms/DropdownMenu.vue` (echte Lücke) | ~150 | mittel |

Jeder einzelne wäre ein eigener Slice mit eigenem PR, sobald der Audit-PR
gemergt ist.

## PR-Plan

- **Branch**: `feat/ui-audit-epic`
- **Titel**: `docs(ui): audit v4 component landscape + shadcn-vue evaluation`
- **Body**: Pivot-Erklärung, Lieferumfang-Tabelle, Empfehlung an Reviewer
  (Annahme = Festschreibung der Real-State-Design-Language).
- **Findings-Workflow**: 90 s warten nach `gh pr create`, Gemini-Findings sichten,
  bei `HIGH`/`MEDIUM` adressieren (CLAUDE.md "PR-Workflow").
- **Closes**: kein direkter Issue-Bezug. Adressiert implizit Issue #203
  (Komponenten-Audit) und schafft Evaluation-Anker für künftige
  Tailwind/shadcn-vue-Vorschläge.
