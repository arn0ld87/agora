# MAI-11 · prod-proxy-smoke: PR-Smoke nur für RC/Release — Arbeitsprotokoll

**Datum:** 2026-05-14  
**Branch:** `feat/mai-11-pr-smoke-rc-only`  
**Worktree:** `/Volumes/T7/Projekte/agora-worktrees/mai-11/`  
**Scope:** `.github/workflows/docker-image.yml` (CI-Trigger-Guard)

---

## Ausgangslage

Laut `docu/STATUS.md` (Stand 2026-05-06): der `prod-proxy-smoke`-Job wurde wegen
~30 Minuten Laufzeit pro Iteration auf PR-Trigger deaktiviert. Vor v1.0 war geplant,
das neu zu bewerten. Nach dem v1.0-Release (2026-05-11) ist die stabile Konfiguration:

- **Automatisch** auf: `main`-Push, Tags `v*`, Push auf `release/**`/`rc/**`, `workflow_dispatch`.
- **Opt-in** auf Feature-PRs: Label `needs-prod-smoke` aktiviert den Smoke.

## Änderungen

### `.github/workflows/docker-image.yml`

**1. `pull_request` Trigger-Erweiterung:**
- `types: [opened, synchronize, ready_for_review, labeled]` hinzugefügt.
- Damit löst das `labeled`-Event den Workflow aus, wenn das Label `needs-prod-smoke`
  nachgereicht wird — ohne erneuten Push/Synchronize.

**2. `build-only` Job — `if`-Guard erweitert:**
```yaml
if: ${{ github.event_name != 'pull_request' || startsWith(github.head_ref, 'release/') || startsWith(github.head_ref, 'rc/') || contains(github.event.pull_request.labels.*.name, 'needs-prod-smoke') }}
```
`build-only` muss auch bei `needs-prod-smoke`-Label laufen, da `prod-proxy-smoke`
von `build-only` abhängt (via `needs: [build-only]`).

**3. `prod-proxy-smoke` Job — neuer `if`-Guard:**
```yaml
if: >-
  github.event_name == 'workflow_dispatch' ||
  (github.event_name == 'push' && (github.ref == 'refs/heads/main' ||
  startsWith(github.ref, 'refs/tags/v'))) ||
  (github.event_name == 'pull_request' && (startsWith(github.head_ref, 'release/') ||
  startsWith(github.head_ref, 'rc/') ||
  contains(github.event.pull_request.labels.*.name, 'needs-prod-smoke')))
```
Normaler Feature-PR ohne Label → Job wird übersprungen (`skipped`), keine 30-min-Penalty.

## GitHub-Label

```bash
gh label create needs-prod-smoke \
  --description "Erzwingt prod-proxy-smoke auf Feature-PRs (MAI-11)" \
  --color "FF8800"
```

Anwendung: `gh pr edit <N> --add-label needs-prod-smoke`

## Empfohlene Trigger-Szenarien für manuellen Test (nach Merge)

| Szenario | Erwartetes Ergebnis |
|---|---|
| Feature-PR ohne Label | `prod-proxy-smoke` → `skipped` |
| Feature-PR + Label `needs-prod-smoke` | `build-only` + `prod-proxy-smoke` → laufen |
| Branch `release/x.y.z` | Alle Jobs → laufen |
| Branch `rc/x.y.z` | Alle Jobs → laufen |
| Tag `v*` push | Alle Jobs → laufen |
| `workflow_dispatch` | Alle Jobs → laufen |

## Verifikation (lokal)

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-11
rg -n 'needs-prod-smoke' .github/workflows/docker-image.yml
# → mind. 3 Matches (types, build-only if, prod-proxy-smoke if)

rg -n 'startsWith.*release/' .github/workflows/docker-image.yml
# → mind. 2 Matches (build-only + prod-proxy-smoke)

gh label list | grep needs-prod-smoke
# → needs-prod-smoke sichtbar
```

## Warum dieser Ansatz?

- **Keine Regression:** Release-Pfade (main, Tags, rc/release-Branches) laufen
  unverändert vollständig durch.
- **Schnellere Feature-Iteration:** Normale PRs zahlen nicht mehr 30 min CI-Strafe.
- **Opt-in klar dokumentiert:** Label-Name ist self-explaining; kein verstecktes Verhalten.
- **`labeled`-Event als Trigger:** Smoke startet sofort wenn Label gesetzt wird,
  ohne erneuten Commit.

## Status

✅ Workflow-Datei editiert  
✅ CHANGELOG [Unreleased] aktualisiert  
✅ Label angelegt (via `gh label create`)  
✅ Arbeitsprotokoll erstellt  
⬜ PR erstellt (Aufgabe des Lead-Orchestrators)
