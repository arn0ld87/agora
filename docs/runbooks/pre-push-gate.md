# Pre-Push-Gate

Datei: `docs/runbooks/pre-push-gate.md` · Stand: 2026-07-13 · Eingeführt mit: Onboarding Slice 4.3.3 Maintenance

## Zweck

Eine **einzige** ausführbare Datei, die lokal dieselben Checks fährt wie
CI (`Backend PR smoke gate` + `Frontend PR smoke gate` + `Schema-Drift
verhindern` + `STATUS.md Drift --check`). Damit gibt es keine
"lokal grün, CI rot"-Fälle mehr und kein `--no-verify`-Bypass.

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
| 9 | `vite build` | Frontend PR smoke gate | ja |
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

## Legacy-Picker-Check (Sub-Slice 5.5 Grep-Prep)

CI-Gate, das verhindert, dass v3-Picker-Stellen
(`ModelPicker.vue`, `LlmProfilePicker.vue`, `ActiveModelBadge.vue`,
`@/store/llmProviders|llmProfiles|llmRoutingDefaults`,
`@/composables/useRuntimeLlmOptions`) nach 5.5 zurück in den Code
kommen. Spiegel-Workflow: `.github/workflows/check-legacy-model-picker.yml`.

Lokal ausführen:

```bash
python3 .github/scripts/check_legacy_model_picker.py
# oder mit explizitem Ziel:
python3 .github/scripts/check_legacy_model_picker.py frontend/src
```

Exit-Codes: `0` clean · `1` Treffer · `2` Usage-Fehler.

**Opt-in für 5.5-Wrapper-Dateien:** Wenn eine Datei den v3-Pfad
weiterhin braucht (z. B. ein Read-Adapter-Shim), trägt sie genau
einen Magic-Comment in der **ersten Zeile**:

- `.ts` / `.spec.ts`: `// legacy-model-picker-allow: <reason>`
- `.vue`: `<!-- legacy-model-picker-allow: <reason -->`

Reason ist Pflicht (Audit-Spur). Leere Marker werden zurückgewiesen.
Subpfade wie `@/store/llmProviders/index` sind auch ohne Marker
erlaubt — der Check matcht nur den **genauen** Bare-Specifier.

Unit-Tests für den Check selbst:

```bash
python3 .github/scripts/test_check_legacy_model_picker.py
```

(8 Stdlib-`unittest`-Tests, kein `pip install nötig`.)
