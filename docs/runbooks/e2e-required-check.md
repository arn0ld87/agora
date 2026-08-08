# E2E-Smokes als Required Check

Datei: `docs/runbooks/e2e-required-check.md` · Stand: 2026-08-08 (Status: Required-Erzwingung ist aktiv — `main` hat einen konfigurierten Branch-Protection-Regelsatz mit den sechs Playwright-Smokes und weiteren Checks als Pflicht) · Eingeführt mit: Issue #739, aktualisiert für Issue #1089

## Zweck

Der `pull_request`-Trigger des E2E-Workflows (`.github/workflows/e2e-smokes.yml`) ist aktiviert. Diese Anleitung beschreibt, wie man die sechs Kern-Smokes als **erforderliche Branch-Protection-Checks** für `main` konfiguriert — das verhindert PRs, wenn E2E rot ist. Der hier beschriebene Zielzustand ist inzwischen umgesetzt (siehe Status).

## Status

| Datum | Ereignis |
|---|---|
| 2026-07-19 | Trigger `on: pull_request` reaktiviert (#739); drei aufeinanderfolgende grüne Läufe auf `32bad751` (`29691168025`, `29691166308`, `29691165639`) — *nicht* repräsentativ für dauerhafte Stabilität |
| 2026-08-08 | Erhoben via `gh api repos/arn0ld87/agora/branches/main/protection`: Required-Erzwingung ist aktiv. Die sechs Playwright-Smokes sind Required Checks, ebenso `Backend PR smoke gate (ruff + mypy + pytest-contracts)` und `Frontend PR smoke gate (lint + typecheck + test + build)` (laut Issue #979, Punkt E5) sowie weitere Checks — vollständige Liste unten |

## Die sechs Kern-Smokes (Playwright)

Diese Job-Namen sind Teil der konfigurierten Required Checks:

1. `Playwright Health-Smoke`
2. `Playwright Upload+Graph-Smoke`
3. `Playwright Minimalreport-Smoke`
4. `Playwright Report-Modes-Smoke (P4.4)`
5. `Playwright Golden-Gate-Accessibility-Smoke (Slice 7.3.1)`
6. `Playwright AiModelPicker-Smoke (Slice 5.6 / 7.3.1)`

Der vollständige, per `gh api` erhobene Satz an Required Checks für `main` umfasst darüber hinaus (Stand 2026-08-08): `CodeQL (javascript-typescript)`, `CodeQL (python)`, `Dependency Review`, `Schema-Drift verhindern`, `Pydantic-Contract-Tests`, `Evidence-Quality-Gate`, `Frontend-Zod muss Backend-Schema spiegeln`, `Version-Drift-Check`, `Security scans`, `Backend PR smoke gate (ruff + mypy + pytest-contracts)`, `Frontend PR smoke gate (lint + typecheck + test + build)`. Dieses Runbook fokussiert auf die sechs Playwright-Smokes; die übrigen Checks werden von anderen Workflows definiert und sind hier nicht im Detail beschrieben.

## Konfiguration via GitHub UI

1. `Settings` → `Branches`
2. Branch-Protection-Regel für `main` öffnen (oder neu erstellen)
3. Checkbox `Require status checks to pass before merging` aktivieren
4. Im Suchfeld je einen Job-Namen eingeben und auswählen (mind. die sechs oben)
5. `Save changes`

Diese Schritte sind bereits umgesetzt und dienen hier als Referenz für spätere Anpassungen (z. B. weitere Checks ergänzen).

## Konfiguration via `gh api` (sicheres Read/merge/update-Beispiel)

```bash
# Voraussetzung: gh CLI und jq installiert, Auth konfiguriert.
# Vorhandene Required Checks inklusive ihrer App-Bindung lesen, die sechs
# Playwright-Smokes idempotent ergänzen und nur diesen Schutzbereich aktualisieren.
gh api repos/arn0ld87/agora/branches/main/protection \
  | jq '
      .required_status_checks as $current
      | [
          "Playwright Health-Smoke",
          "Playwright Upload+Graph-Smoke",
          "Playwright Minimalreport-Smoke",
          "Playwright Report-Modes-Smoke (P4.4)",
          "Playwright Golden-Gate-Accessibility-Smoke (Slice 7.3.1)",
          "Playwright AiModelPicker-Smoke (Slice 5.6 / 7.3.1)"
        ] as $required_playwright_checks
      | {
          strict: ($current.strict // true),
          checks: (
            ($current.checks // [])
            + (
                $required_playwright_checks
                - (($current.checks // []) | map(.context))
                | map({context: ., app_id: -1})
              )
          )
        }
    ' \
  | gh api --method PATCH \
      repos/arn0ld87/agora/branches/main/protection/required_status_checks \
      --input -
```

Das Beispiel verwendet bewusst nicht `PUT` auf dem gesamten Branch-Protection-Objekt: Ein Payload mit nur den sechs Playwright-Namen würde alle anderen Required Checks ersetzen. Bestehende Checks und ihre `app_id` bleiben erhalten; nur fehlende Playwright-Smokes werden mit `app_id: -1` (jede App) ergänzt. `strict: true` bedeutet, dass Checks auch bei neueren Commits erneut erforderlich sind.

## Absicherung gegen Flakes

Die Erzwingung ist aktiv. Bei wiederholten Flakes auf einem der sechs Playwright-Smokes gilt weiterhin: erst die Ursache im Workflow beheben, dann ggf. den betroffenen Check kurzzeitig über Option B (siehe Rollback) aus der Required-Liste nehmen — nicht dauerhaft, sondern nur für die Dauer der Fehlersuche.

## Rollback

Trigger wieder deaktivieren oder Required-Check-Häkchen entfernen:

### Option A: PR-Trigger entfernen (`workflow_dispatch` bleibt erhalten)

In `.github/workflows/e2e-smokes.yml` unter `on:` ausschließlich den `pull_request`-Block entfernen. Der `workflow_dispatch`-Trigger bleibt aktiv, damit das Team weiterhin manuell aus dem GitHub-UI oder per `gh workflow run` Läufe anstoßen kann.

```yaml
on:
  workflow_dispatch:
  schedule:
    - cron: "..."
```

Kein Komplett-Reset des Workflows — nur der `pull_request`-Zweig fällt weg.

### Option B: Required-Check entfernen (GitHub UI)

Settings → Branches → Rule → `Require status checks` **unchecken** oder Jobs aus der Liste entfernen.

## Siehe auch

- [Issue #739](https://github.com/arn0ld87/agora/issues/739)
- [docs/STATUS.md — E2E-Smokes](../STATUS.md#e2e-smokes)
- [`.github/workflows/e2e-smokes.yml`](../../.github/workflows/e2e-smokes.yml)
