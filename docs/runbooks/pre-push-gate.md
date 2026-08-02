# Pre-Push-Gate

Datei: `docs/runbooks/pre-push-gate.md` · Stand: 2026-07-13 · Eingeführt mit: Onboarding Slice 4.3.3 Maintenance

## Zweck

Eine **einzige** ausführbare Datei, die lokal die Checks der CI fährt
(`Backend PR smoke gate` + `Frontend PR smoke gate` + `Schema-Drift
verhindern` + `STATUS.md Drift --check`) und "lokal grün, CI rot"
verhindert, ohne `--no-verify`-Bypass.

**Eine bewusste Ausnahme:** Der `vite build` läuft lokal nur mit
`GATE_BUILD=1`, in der CI dagegen immer. Er ist der mit Abstand teuerste
Schritt und fängt nach ESLint, `vue-tsc` und Vitest praktisch nichts
mehr ab. Ein CI-Fehler, den das lokale Gate durchlässt, ist damit auf
reine Bundler-Fehler beschränkt (etwa ein fehlender dynamischer Import).
Wer eine Vite-Config, ein Alias oder eine Chunk-Strategie anfasst, setzt
`GATE_BUILD=1` — dort ist die Lücke real.

## Verwendung

```bash
# Alles (Default — vor jedem Push Pflicht)
bash scripts/pre-push-gate.sh

# Sub-Sets (z. B. nach Backend-only-Änderung)
bash scripts/pre-push-gate.sh backend
bash scripts/pre-push-gate.sh frontend
bash scripts/pre-push-gate.sh schemas
```

Exit-Codes: `0` = alle Gates grün · `1` = mind. ein Gate rot · `2` = falscher Sub-Scope.

## Gate-Katalog

| # | Gate | CI-Mirror | Pflicht? |
|---|---|---|---|
| 1 | `ruff check app/ tests/` | Backend PR smoke gate | ja |
| 2 | `mypy app` | Backend PR smoke gate | ja |
| 3 | `pytest tests/contracts/ -x -q` | Backend PR smoke gate + Pydantic-Contract-Tests | ja |
| 4 | `dump_schemas --check` | Schema-Drift verhindern | ja |
| 5 | `sync-status.sh --check` | STATUS.md Drift | ja |
| 6 | `eslint .` (frontend) | Frontend PR smoke gate | ja |
| 7 | `vue-tsc --noEmit` | Frontend PR smoke gate | ja |
| 8 | `vitest run` | Frontend PR smoke gate | ja |
| 9 | `vite build` | Frontend PR smoke gate | nur mit `GATE_BUILD=1` |
| 10 | Schema-Spiegel-Smoke | Frontend-Zod muss Backend-Schema spiegeln | ja |

## Warum lokales Gate?

Drei teure Failure-Modes, die wir damit ausschließen:

1. **Schema-Drift vergessen** — Contract geändert, aber `dump_schemas`
   nicht regeneriert. `sync-status` zählt das auch nicht. CI-Hook
   `Schema-Drift verhindern` ist die einzige Quelle der Wahrheit.
2. **F401-Unused-Imports** — wachsen über Slices an, weil `ruff` nicht
   in `package.json` (frontend) und der Root-CI-Lint hängen — sondern
   nur im Backend-PR-Smoke. Lokal fängt sie der Pre-Push-Gate ab.
3. **Frontend-Build-Ok aber typecheck rot** — z. B. neues `embedding_source`-
   Feld im Zod-Spiegel, vergessen in `OnboardingView.spec.ts` Fixture.
   Typecheck läuft nicht im `vitest run` allein.

## Wenn ein Gate rot wird

Niemals `--no-verify` benutzen. Statt dessen:

- **Schemata rot** → `cd backend && uv run python -m app.contracts.dump_schemas && git add schemas/` und committen
- **STATUS.md rot** → `bash scripts/sync-status.sh` und committen
- **Test rot** → fix + neuen Test, dann nochmal
- **Lint rot** → `cd backend && uv run ruff check app/ tests/ --fix` (autofix), manuell nachprüfen, committen
- **Typecheck rot** → meist fehlende Fixture-Keys in Tests; gezielt fixen

## CI-Spiegel-Disziplin

Wenn die CI ein neues Gate bekommt (z. B. `bandit`, `pip-audit`),
MUSS `scripts/pre-push-gate.sh` in derselben PR erweitert werden —
sonst driftet die Pipeline. Reihenfolge: Gate zuerst in CI einführen
(sofort wirksam), dann im selben Release-Cycle lokal spiegeln.

## Legacy-Picker-Check (Sub-Slice 5.5)

CI-Gate, das verhindert, dass v3-Picker-Stellen
(`ModelPicker.vue`, `LlmProfilePicker.vue`, `ActiveModelBadge.vue`,
`@/store/llmProviders|llmProfiles|llmRoutingDefaults`,
`@/composables/useRuntimeLlmOptions`) nach 5.5 in **neuen** Code
kommen. Spiegel-Workflow: `.github/workflows/check-legacy-model-picker.yml`.

Lokal ausführen:

```bash
python3 .github/scripts/check_legacy_model_picker.py
# oder mit explizitem Ziel:
python3 .github/scripts/check_legacy_model_picker.py frontend/src
```

Exit-Codes: `0` clean · `1` Treffer · `2` Usage-Fehler.

**Read-Adapter-Freigabe via `@deprecated` (seit 5.5):** Der
Opt-in-Marker `legacy-model-picker-allow` ist entfallen. Ein verbotener
Import ist jetzt genau dann erlaubt, wenn das **importierte Ziel** selbst
ein `@deprecated`-JSDoc-Tag trägt — also ein sanktionierter Read-Adapter
im Deprecation-/Read-only-Fenster ist.
Da inzwischen alle Komponenten-Ausnahmen in `REMOVED_PATHS` stehen und
allein durch ihre Existenz blockiert werden, greift diese Freigabe faktisch
nur noch für verbliebene Stores und Composables
(z. B. `Step2EnvSetup.vue`/`Step3Simulation.vue` → `useRuntimeLlmOptions.ts`).
Jeder *neu* eingeführte, nicht-deprecatete v3-Pfad wird hart blockiert.

**Entfernte Dateien (`REMOVED_PATHS`):** Zusätzlich zur Import-Prüfung
blockiert der Check die *Rückkehr* gelöschter v3-Dateien — hier reicht die
bloße Existenz, ein Import ist nicht nötig, und ein `@deprecated`-Tag
rettet sie nicht. Erfasst sind `components/ui/ModelPicker.vue` und die
Mock-Routing-UI unter `views/Settings/llmRouting/` (beide Slice 7.7),
`components/llm/LlmProfilePicker.vue` (in Issue #834 entfernt), sowie
`components/ActiveModelBadge.vue` (in Issue #911 entfernt).

Die Alt-Stores (`llmProviders`/`llmProfiles`/`llmRoutingDefaults`)
existieren nach 5.5 nicht mehr (konsolidiert in `@/store/aiModels`); ihr
Import resolved auf kein Ziel → keine `@deprecated`-Freigabe möglich →
Verstoß. Subpfade wie `@/store/llmProviders/index` matcht der Check ohnehin
nicht (nur der **genaue** Bare-Specifier ist verboten).

Unit-Tests für den Check selbst:

```bash
python3 .github/scripts/test_check_legacy_model_picker.py
```

(10 Stdlib-`unittest`-Tests, kein `pip install nötig`.)
