# Handover — Onboarding/Provider-Unification Slice 5.3

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-3`
- Branch: `codex/onboarding-model-picker-slice-5-3`
- Basis: `origin/main` @ `331193d7` (Slice 5.2, PR #699, gemergt)
- Slice: 5.3 — Backend-Routing-Hierarchie (`AiRoute`)

## Fertig (Sub-Slice 5.3)

- Die bestehende Contract-SSoT `AiRoute` in
  `backend/app/contracts/ai_provider_contract.py` wurde additiv um die
  Quellen `run_override`, `project`, `workspace`, `provider_fallback` sowie
  `resolved_at` und `fallback_reason` erweitert. Es gibt bewusst keinen
  zweiten `ai_route_contract.py`.
- `ai_route_resolver.py` löst deterministisch
  `Stage-Override > Run-Override > Project > Workspace > Provider-Fallback`
  auf und lehnt fehlende bzw. capability-inkompatible Kandidaten typisiert ab.
- Stage-Snapshots werden crash- und race-sicher per atomarem First-writer-wins
  publiziert. Der bestehende `ResolvedRoute`-Snapshot bleibt als v3-Read-
  Adapter erhalten; zusätzlich wird pro Stage ein kanonischer, secret-freier
  `AiRoute`-Snapshot geschrieben.
- `ai_route_audit.py` persistiert pro Stage genau ein secret-freies
  `routing_resolved`-Event mit UTC-Zeit, Quelle und Fallback-Begründung.
- Die bestehenden `llm-routing`-Endpunkte liefern `ai_route` additiv. Alte
  Felder und Request-Shapes bleiben unverändert; die Frontend-Response-Typen
  markieren sie mit `@deprecated`. Der öffentliche Serializer entfernt den
  internen Legacy-Marker sowie nicht kanonische bzw. geheime Optionen.
- Backend-, Zod- und JSON-Schema-Spiegel sind synchron; lokale Ollama-
  Loopback-URLs bleiben im kanonischen Route-Vertrag zulässig.

## Verifikation

- Fokussierter Backend-Lauf: 96 passed.
- `ruff` und fokussiertes `mypy`: grün.
- Contract-/Frontend-Gates und voller Pre-Push-Gate: siehe PR-Checks.
- `graphify update .`: Graph auf 19.488 Nodes / 31.044 Edges aktualisiert.

## Bewusst offen

- 5.4 migriert die produktiven Auswahlstellen auf den neuen Resolver. Die
  bestehende, bereits verflachte `RuntimeLlmRouting` bleibt bis dahin ein
  Legacy-Read-Adapter und erfindet keine Project-/Workspace-Provenienz.
- 5.5 deprecatet alte Picker/Stores vollständig.
- 5.6 ergänzt Playwright-E2E einschließlich Run-Snapshot.
- Danach folgen Slice 6 (Persona-Count) und Slice 7 (Golden-Gate-Designsystem).

## Sub-Slice 5.5 — Grep-Prep

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-5-grep-prep`
- Branch: `codex/onboarding-model-picker-slice-5-5-grep-prep`
- Basis: `origin/main` @ `165d22f5` (PR #700, gemergt)
- PR: [#702](https://github.com/arn0ld87/agora/pull/702)
- Slice: 5.5 (Vorbereitung) — Grep-CI-Check gegen v3-Picker-Importe

### Notiz an 5.5 (Deprecation)

Check ist scharf, Opt-in-Marker existiert, Wrapper-Dateien können sich
freischalten via `<!-- legacy-model-picker-allow: ... -->` bzw.
`// legacy-model-picker-allow: ...`. Subpfade wie
`@/store/llmProviders/index` sind auch ohne Marker erlaubt — der Check
matcht nur den genauen Bare-Specifier.

Aktuell tragen 18 v3-Importe einen Grandfather-Marker
(`pre-5.5 v3 picker importer — see slice-5-subplan.md`); mit der
Migration in 5.4/5.5 sind die Importe zu entfernen (damit fällt der
Marker automatisch mit weg). Leere Opt-in-Reason-Strings werden
zurückgewiesen — der Reason bleibt Pflicht für die Audit-Spur.

CI-Workflow: `.github/workflows/check-legacy-model-picker.yml`
(triggert auf `pull_request` mit `paths: frontend/src/**`).
Lokaler Aufruf: `python3 .github/scripts/check_legacy_model_picker.py`
(Spiegel siehe `docs/runbooks/pre-push-gate.md`, Abschnitt
„Legacy-Picker-Check").
---

# Handover — Onboarding/Provider-Unification Slice 5.6-Prep

## Stand

- Datum: 2026-07-13
- Worktree: `/private/tmp/agora-onboarding-slice-5-6-prep`
- Branch: `codex/onboarding-model-picker-slice-5-6-prep`
- Basis: `origin/main` @ `165d22f5` (PR #700 gemergt, AiRoute +
  AiModelPicker Discovery in `main`)
- Slice: **5.6-Prep** — Playwright-E2E-Skeleton fuer AiModelPicker.
  Diese Vorbereitung laeuft PARALLEL zu Sub-Slice 5.4
  (`codex/onboarding-model-picker-slice-5-4`, derzeit offen) in einem
  separaten Branch. Der Prep-Branch haengt **nicht** von 5.4 ab und
  darf gemergt werden, sobald die Spec lauffaehig (mit `test.describe.skip()`)
  ist. 5.6 final muss dann nur die `.skip`-Annotation entfernen und
  ggf. Selektor-Pfade an die in 5.4 konkret migrierten Routen anpassen.

## Daten-testid-SSoT

`frontend/src/contracts/testIds.ts` (neu) — wird sowohl von der
Komponente (`AiModelPicker.vue` importiert `@/contracts/testIds`) als
auch von den E2E-Helpern (`frontend/tests/e2e/helpers/testIds.ts`
re-exportiert ueber relativen Pfad, weil
`tsconfig.playwright.json` keinen `@/`-Alias hat) verwendet.

Vergabe-Schema (collision-safe ueber Namespace-Prefix `ai-model-picker-*`):

| Konstante                  | data-testid-Wert           | Wer rendert                                                       |
| -------------------------- | -------------------------- | ----------------------------------------------------------------- |
| `AiModelPickerTestId.root`   | `ai-model-picker`            | Root-Container `<div class="ai-model-picker">`                      |
| `AiModelPickerTestId.input`  | `ai-model-picker-input`      | Trigger-Input (ComboboxInput)                                       |
| `AiModelPickerTestId.search` | `ai-model-picker-search`     | Such-Input im geoeffneten Content                                   |
| `AiModelPickerTestId.group`  | `ai-model-picker-group`      | ComboboxGroup, zusaetzlich `data-provider-connection-id`            |
| `AiModelPickerTestId.option` | `ai-model-picker-option`     | ComboboxItem, zusaetzlich `data-provider-connection-id` + `data-model-id` |
| `AiModelPickerTestId.status` | `ai-model-picker-status`     | Group-Status-Badge (Reserviert; aktuell nicht im Template, fuer 5.4) |
| `AiModelPickerTestId.empty`  | `ai-model-picker-empty`      | ComboboxEmpty (Empty-State)                                          |

5.4 muss in den migrierten Views (HeroNewRun, SettingsGeneralView,
LlmRoutingView, StepModelOverrideChip) **dieselben IDs** vergeben.
Sollte 5.4 weitere Selektoren brauchen, bitte hier ergaenzen — kein
String-Drift zwischen Komponente und Spec.

## data-testid-Anpassungen an `AiModelPicker.vue`

Klein, sauber, additiv. Keine Logik-Aenderung, keine CSS-Anpassung.
Component-Unit-Tests (AiModelPicker.spec.ts + AiModelPicker.discovery.spec.ts)
bleiben gruen (14/14). `vue-tsc` und `eslint` ohne Befund.

- `providerGroups`-Computed: Typ um `provider_connection_id: string`
  erweitert (wird als `data-provider-connection-id` auf der Group
  gerendert). Filter- und Sort-Logik unveraendert.
- `data-testid` an: root `<div>`, Trigger-`<ComboboxInput>`, Such-
  `<ComboboxInput>`, `<ComboboxEmpty>`, `<ComboboxGroup>`, `<ComboboxItem>`.
- Group erhaelt zusaetzlich `:data-provider-connection-id="group.provider_connection_id"`.
- Item erhaelt zusaetzlich `:data-provider-connection-id` und
  `:data-model-id`.

Damit kann eine E2E-Spec gezielt auf eine Provider-Gruppe oder ein
Modell zugreifen, ohne sich auf den (i18n-lokalisierbaren) Display-
Namen verlassen zu muessen.

## Spec-Struktur (Skeletons)

`frontend/tests/e2e/ai-model-picker.spec.ts` (neu) — `test.describe.skip()`,
damit CI gruen bleibt bis 5.4 die Komponente in den Ziel-Views mountet.

Drei Test-Gruppen (jeweils mit `// 5.4: aktiveren sobald ...` Kommentar):

1. **Tastatur-Navigation** (2 Tests)
   - `↓↓↑Enter` oeffnet Combobox, wandert Auswahl, committed.
   - Suche filtert Optionen, Pfeile wandern ueber Treffer.

2. **Provider offline** (2 Tests)
   - Modell mit `status=unavailable` hat `data-disabled` /
     `aria-disabled` UND sichtbares Error-Badge
     (`.ai-model-picker__badge--err`).
   - Provider-Group rendert Status-Label im Group-Header.

3. **Run-Snapshot** (1 Test)
   - GET `/api/runs/<run_id>/llm-routing` liefert
     `ai_route.provider_connection_id` und `ai_route.model_id` passend
     zur Picker-Auswahl; `ai_route.source === 'stage-override'`.
   - Setzt voraus, dass 5.3 (PR #700, gemergt in main) das `ai_route`-
     Feld liefert und 5.4 die Stage-Override-UI auf AiModelPicker
     umgestellt hat.

`frontend/tests/e2e/helpers/aiModelPicker.ts` (neu) — Locator- und
Action-Funktionen ausschliesslich auf `data-testid`-Basis:

- `login(page|context, token?)` — Wrapper fuer `injectAuthToken`
  (Single-User-Token-Mode).
- `getPicker`, `getPickerInput`, `getPickerSearch`,
  `getGroupByConnectionId`, `getOption` — Locator-Builder.
- `openPicker`, `selectOptionByClick`, `drillKeyboard`,
  `readSelectedLabel` — Action-Helfer.

Kein Klassen- oder ARIA-Selector — die Helper sind immun gegen
CSS-Refactors und i18n-Aenderungen.

## Verifikation (lokal)

- `bash scripts/pre-push-gate.sh` — grun (Backend + Frontend + Schemas).
  Spec-File alleine bricht das Gate nicht.
- `vitest run src/components/v4/forms/__tests__/AiModelPicker` —
  14/14 Tests pass (Component-Aenderungen sind additiv).
- `vue-tsc --noEmit` — sauber.
- `tsc --noEmit -p tsconfig.playwright.json` — nur der pre-existing
  Fehler in `tests/e2e/minimal-report.spec.ts:69` (`import.meta` mit
  `module: CommonJS`), nicht von diesen Aenderungen verursacht.
- `playwright test --list tests/e2e/ai-model-picker.spec.ts` —
  5 Tests gelistet, alle als skip markiert.

## Out of Scope (bewusst)

- Echte Migrations-Schritte → Sub-Slice 5.4.
- Store-Konsolidierung → Sub-Slice 5.5.
- 5.6 final: `test.describe.skip()` entfernen, Seed-Daten aus
  5.4 ableiten (konkrete `provider_connection_id` + `model_id`),
  ggf. Save-Button-`data-testid` in der Stage-Override-View ergaenzen,
  grun laufen lassen.

## Naechste Schritte (5.6 final)

1. PR mergen (Prep-Skeleton ist grun, 5.4 unabhaengig).
2. Sobald 5.4 den Picker in einer View gemountet hat: `beforeEach`-
   `goto` in `ai-model-picker.spec.ts` an die echte Route anpassen.
3. Skip-Annotation entfernen, Seed-Daten fest verdrahten
   (Empfehlung: dedizierter Test-Provider mit `status=unavailable` im
   global-setup oder im ProviderConnectionStore-Seed).
4. `bash scripts/pre-push-gate.sh` final grun halten.

## Relevante Dateien (Diff zu `origin/main`)

- `frontend/src/components/v4/forms/AiModelPicker.vue` (data-testid +
  provider_connection_id in providerGroups-Type)
- `frontend/src/contracts/testIds.ts` (neu)
- `frontend/tests/e2e/helpers/testIds.ts` (neu, Re-Export)
- `frontend/tests/e2e/helpers/aiModelPicker.ts` (neu)
- `frontend/tests/e2e/ai-model-picker.spec.ts` (neu)
- `docs/epics/onboarding-provider-unification/HANDOVER.md` (dieser Abschnitt)

