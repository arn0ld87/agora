# E2E-Smokes als Required Check

Datei: `docs/runbooks/e2e-required-check.md` · Stand: 2026-07-19 · Eingeführt mit: Issue #739

## Zweck

Der `pull_request`-Trigger des E2E-Workflows (`.github/workflows/e2e-smokes.yml`) ist aktiviert. Diese Anleitung beschreibt, wie man die sechs Kern-Smokes als **erforderliche Branch-Protection-Checks** für `main` konfiguriert — das verhindert PRs, wenn E2E rot ist.

## Status

| Datum | Ereignis |
|---|---|
| 2026-07-19 | Trigger `on: pull_request` reaktiviert (#739), alle sechs Smokes stabil grün |
| offen | Branch-Protection-Erzwingung durch Owner manuell konfigurieren |

## Die sechs Required Checks

Diese Job-Namen müssen als erforderlich konfiguriert werden:

1. `Playwright Health-Smoke`
2. `Playwright Upload+Graph-Smoke`
3. `Playwright Minimalreport-Smoke`
4. `Playwright Report-Modes-Smoke (P4.4)`
5. `Playwright Golden-Gate-Accessibility-Smoke (Slice 7.3.1)`
6. `Playwright AiModelPicker-Smoke (Slice 5.6 / 7.3.1)`

## Konfiguration via GitHub UI

1. `Settings` → `Branches`
2. Branch-Protection-Regel für `main` öffnen (oder neu erstellen)
3. Checkbox `Require status checks to pass before merging` aktivieren
4. Im Suchfeld je einen Job-Namen eingeben und auswählen (mind. die sechs oben)
5. `Save changes`

## Konfiguration via `gh api` (Beispiel)

```bash
# Voraussetzung: gh CLI installiert, Auth konfiguriert
gh api repos/arn0ld87/agora/branches/main/protection \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Playwright Health-Smoke",
      "Playwright Upload+Graph-Smoke",
      "Playwright Minimalreport-Smoke",
      "Playwright Report-Modes-Smoke (P4.4)",
      "Playwright Golden-Gate-Accessibility-Smoke (Slice 7.3.1)",
      "Playwright AiModelPicker-Smoke (Slice 5.6 / 7.3.1)"
    ]
  },
  "enforce_admins": true,
  "dismiss_stale_reviews": false,
  "require_code_owner_reviews": false,
  "require_last_push_approval": false,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

Beachte: `strict: true` bedeutet, dass Checks auch bei neueren Commits erneut erforderlich sind.

## Absicherung gegen Flakes

**Erst nach mehreren grünen Läufen erzwingen.** Der Workflow ist neu reaktiviert; gib dem Team Zeit, um zu verifizieren, dass die Checks stabil grün sind.

## Rollback

Trigger wieder deaktivieren oder Required-Check-Häkchen entfernen:

### Option A: Trigger deaktivieren (`.github/workflows/e2e-smokes.yml`)
```yaml
# on:
#   pull_request:
#     branches: [main]
```

### Option B: Required-Check entfernen (GitHub UI)
Settings → Branches → Rule → `Require status checks` **unchecken** oder Jobs aus der Liste entfernen.

## Siehe auch

- [Issue #739](https://github.com/arn0ld87/agora/issues/739)
- [docs/STATUS.md — E2E-Smokes](../STATUS.md#e2e-smokes)
- [.github/workflows/e2e-smokes.yml](.github/workflows/e2e-smokes.yml)
