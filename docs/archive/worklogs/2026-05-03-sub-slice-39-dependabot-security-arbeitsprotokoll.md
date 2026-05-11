# Sub-Slice 39 — Dependabot + SECURITY.md (Layer 10)

**Datum:** 2026-05-03
**Layer:** 10 (Security Watchlist / Repo-Hygiene)
**Vorgänger:** Sub-Slice 31 (Security-Watchlist-Tracking #121–#126), Sub-Slice 34 (Plan-/Onboarding-Doku)

## Was

Zwei neue Dateien im Repo-Root bzw. `.github/`:

### 1. `.github/dependabot.yml`

Vier Update-Streams, alle wöchentlich montags 06:00 Europe/Berlin:

| Ecosystem        | Verzeichnis | Limit | Labels                | Gruppierung               |
|------------------|-------------|-------|-----------------------|---------------------------|
| `pip`            | `/backend`  | 5     | `dependencies,backend`| `python-minor-patch`      |
| `npm`            | `/frontend` | 5     | `dependencies,frontend`| `npm-minor-patch`         |
| `docker`         | `/`         | 3     | `dependencies,docker` | (einzeln)                 |
| `github-actions` | `/`         | 3     | `dependencies,ci`     | (einzeln)                 |

Major-Bumps bleiben separat (Risk-Triage), minor+patch werden gesammelt.
Commit-Prefix für Application-Deps: `chore(deps)`, für Workflows:
`chore(ci)` — passt zur bestehenden Conventional-Commits-Linie.

### 2. `SECURITY.md` (Repo-Root)

- **Disclosure-Kanal:** Mail an `schneider@alexle135.de`,
  optional GitHub Private Vulnerability Reporting.
- **Supported Versions:** Tabelle, nur 0.9.x supported (alles davor `:x:`).
- **Response-SLA (informell):** 72 h Bestätigung, 7 d Einschätzung,
  30 d Fix-Best-Effort. Explizit als nicht-kommerzieller SLA markiert.
- **Watchlist-Verweis** auf Issues #121–#126 + `docs/`-Tracking
  (Sub-Slice 31, Layer 10).
- **AGPL-Klausel** für Fork-Service-Betreiber explizit erwähnt.

## Warum

Aus dem `/repo-research`-Smoke-Run gegen das eigene Repo:

- `gh api repos/arn0ld87/agora/contents/SECURITY.md` → 404
- `gh api repos/arn0ld87/agora/contents/.github/dependabot.yml` → 404

Beides hebt das `isSecurityPolicyEnabled`-Flag im GitHub-UI und schließt
den manuellen CVE-Tracking-Loop, den Sub-Slice 31 nur dokumentiert hat.
Keine Code-Änderung im Backend/Frontend, deshalb auch keine Test-Suite-
oder Schema-Drift-Auswirkungen.

## Verifikation

```bash
# YAML-Lint
cd backend && uv run python -c \
  "import yaml; yaml.safe_load(open('../.github/dependabot.yml')); print('ok')"
# → ok

# Dateipfade existieren am erwarteten Ort
ls -la .github/dependabot.yml SECURITY.md
```

Backend-/Frontend-Tests nicht angefasst — nur Repo-Hygiene-Files.
`npm run check` / `uv run pytest` deshalb nicht erforderlich
(keine Source-Änderung).

## Out of Scope

- **Issue-Closes:** Watchlist-Tickets #121–#126 werden _bedient_, aber nicht
  geschlossen — sie tracken Upstream-Fixes, nicht „dependabot fehlt".
  Schließen, sobald die jeweiligen Upstreams patchen und Dependabot den
  Bump-PR liefert.
- **Renovate/Snyk:** kein Setup — Dependabot reicht für AGPL-Stack im
  aktuellen Maintainer-Footprint (Bus-Faktor 1).
- **CODEOWNERS / Branch Protection:** separat, sobald mehr als ein
  aktiver Maintainer existiert.
- **`uv`-natives Update-Backend:** Dependabot kennt `uv` noch nicht
  nativ; `pip`-Ecosystem liest aber `pyproject.toml` (PEP 621) korrekt
  und erzeugt PRs gegen die Pin-Ranges.
