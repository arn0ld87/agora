# Release-Process

**Stand:** 2026-05-01, Europe/Berlin
**Scope:** Wie ein neuer Tag (`vX.Y.Z`) entsteht. Versionsquellen, Reihenfolge,
Release-Notes, optionaler Container-Build. Linear-Git-Flow gegen `main`,
keine Release-Branches.

Verwandte Dokumente:
- [`deployment-prod-like.md`](deployment-prod-like.md) — Update- und
  Rollback-Pfad für laufende Setups.
- [`operations.md`](operations.md) — Healthcheck nach Deployment.

---

## Versionsquellen

Sechs Stellen halten die Versionsnummer. Eine Release-Sequenz ist nur
dann sauber durch, wenn alle sechs auf derselben SemVer stehen.

| # | Pfad | Format | Source-of-Truth-Hinweis |
|---|---|---|---|
| 1 | [`package.json`](../package.json) (`version`) | `0.9.0` | Root-Paket, gibt den NPM-Tag-Anker. |
| 2 | [`frontend/package.json`](../frontend/package.json) (`version`) | `0.9.0` | Frontend-Paket; muss synchron zur Root sein. |
| 3 | [`backend/pyproject.toml`](../backend/pyproject.toml) (`project.version`) | `0.6.1` (drift, siehe unten) | Backend-Paket-Metadaten. |
| 4 | [`backend/app/__init__.py`](../backend/app/__init__.py) (`__version__`) | `0.8.0` (drift, siehe unten) | Wird von `/api/status.backend.version` exposed. |
| 5 | [`README.md`](../README.md) Status-Block (Zeile ~24) und Top-Banner (Zeile ~11) | `v0.9.0 — released 2026-05-01` | Sichtbarkeit nach außen. |
| 6 | [`frontend/src/i18n/locales/de.json`](../frontend/src/i18n/locales/de.json) und [`en.json`](../frontend/src/i18n/locales/en.json) (`*.version`) | `v0.9.0 alpha` | Frontend-Startseite-Badge. |

> **Bekannter Drift (Stand 2026-05-01):** Quelle 3 (`pyproject.toml`,
> `0.6.1`) und Quelle 4 (`__init__.py`, `0.8.0`) sind hinter v0.9.0
> zurück. Wird in einem eigenen Sync-Slice nachgezogen — siehe
> [Followups](#followups).

---

## SemVer-Regeln

Agora folgt [SemVer](https://semver.org/lang/de/) im Stil von Keep-a-
Changelog:

- **MAJOR** (z. B. `0.x → 1.0`): Wire-Breaks am API-Vertrag, Storage-
  Migration ohne Auto-Upgrade, Pflicht-Schritt für User.
- **MINOR** (z. B. `0.8 → 0.9`): neue Features, neue Endpoints, neue
  `.env`-Variablen. Default-Verhalten bleibt rückwärtskompatibel.
- **PATCH** (z. B. `0.9.0 → 0.9.1`): Bugfixes, Security-Patches,
  Doku-Sweeps, Dependency-Updates ohne API-Wirkung.

Pre-1.0-Realität: Minor-Bumps können trotzdem Verhalten brechen — der
[CHANGELOG](../CHANGELOG.md) ist die ehrliche Wahrheit. Status „alpha"
in der Frontend-Badge bleibt gesetzt, solange wir <1.0 sind.

---

## Reihenfolge

Sechs Schritte, in genau dieser Reihenfolge. Skipping macht inkonsistente
Tags.

### 1. CHANGELOG `[Unreleased]` → finale Version

```diff
-## [Unreleased]
+## [0.10.0] — 2026-06-01
+
+Milestone „<Name>" abgeschlossen — N/N Issues geschlossen, M Tests grün.
+<Kurz-Synopsis>.
```

Den `[Unreleased]`-Block leeren oder eine neue leere Sektion drüber
setzen, sobald der erste Post-Release-Commit auf `main` landet.

### 2. SemVer-Bump in allen sechs Quellen

```bash
NEW=0.10.0
# Quelle 1+2: Root-NPM und Frontend-NPM
npm version --no-git-tag-version --workspaces=false "$NEW"
( cd frontend && npm version --no-git-tag-version "$NEW" )

# Quelle 3: Backend pyproject
sed -i 's/^version = ".*"/version = "'"$NEW"'"/' backend/pyproject.toml

# Quelle 4: Backend __init__.py
sed -i 's/^__version__ = ".*"/__version__ = "'"$NEW"'"/' backend/app/__init__.py

# Quelle 5: README — manuell, weil Banner + Status-Block + Engineering-Stand
#   sich nicht regex-sicher behandeln lassen. Drei Stellen anfassen.

# Quelle 6: i18n-Locales
sed -i 's/"version": "v[^"]*"/"version": "v'"$NEW"' alpha"/' \
  frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json
```

`uv lock --check` und `npm run check` müssen nach dem Bump grün sein.

### 3. Release-Notes schreiben

Datei: `docu/<YYYY-MM-DD>-v<NEW>-release-notes.md`. Vorlage:
[`docu/2026-05-01-v0.9.0-release-notes.md`](2026-05-01-v0.9.0-release-notes.md).

Blöcke (Reihenfolge wie im v0.9.0-File):

1. **Header** — Versionsnummer, Datum, Milestone-Name.
2. **TL;DR** — 1–2 Absätze, was das Release macht; absolute Testzahlen.
3. **Highlights** — drei bis fünf Aufzählungspunkte mit Issue-/EPIC-Bezug.
4. **Migrations-Hinweise** — neue `.env`-Variablen, Schema-Änderungen,
   Pflicht-Schritte für bestehende Setups.
5. **Tests** — exakte Test-Counter, Skip-Begründungen.
6. **Bekannte offene Punkte** — Sub-Slices, die anschließend kommen.

### 4. Tag

```bash
git add CHANGELOG.md package.json frontend/package.json \
        backend/pyproject.toml backend/app/__init__.py \
        frontend/src/i18n/locales/de.json frontend/src/i18n/locales/en.json \
        README.md docu/<datum>-v<NEW>-release-notes.md
git commit -m "release: v$NEW"
git tag -a "v$NEW" -m "Agora v$NEW"
git push origin main "v$NEW"
```

Linear-Git: kein Release-Branch, kein Merge-Commit. Tag zeigt auf den
SemVer-Bump-Commit.

### 5. GitHub-Release

```bash
gh release create "v$NEW" \
  --title "Agora v$NEW" \
  --notes-file "docu/<datum>-v<NEW>-release-notes.md"
```

GitHub picks up die Notes-Datei. Anhang (Container-Image-SHAs, Demo-GIFs)
optional.

### 6. Container-Image (optional)

Nur wenn ein neues Image gepushed wird. Build aus dem Tag-Commit:

```bash
docker buildx build \
  --target prod \
  --tag ghcr.io/arn0ld87/agora:"$NEW" \
  --tag ghcr.io/arn0ld87/agora:latest \
  --push \
  .

docker buildx build \
  --target prod \
  --tag alexle135/agora-agora:"$NEW" \
  --tag alexle135/agora-agora:latest \
  --push \
  .
```

GHCR-Login per `gh auth token | docker login ghcr.io -u arn0ld87
--password-stdin`. Docker-Hub-Login per Token.

---

## Verifikation nach dem Tag

| Check | Wie |
|---|---|
| Tag im Remote vorhanden | `git ls-remote --tags origin v$NEW` |
| GitHub-Release sichtbar | `gh release view "v$NEW"` |
| `/api/status.backend.version` zeigt neue Version | `curl -H "X-Agora-Token: $TOKEN" https://<host>/api/status \| jq .backend.version` |
| Frontend-Badge zeigt neue Version | UI-Smoke nach Cache-Bust. |
| `pip-audit` und `npm audit` grün | CI auf `main` post-Tag. |

Bei Mismatch zwischen `/api/status.backend.version` und Tag: Quelle 4
(`__init__.py`) wurde nicht synchronisiert. Hotfix-Bump als
PATCH-Release.

---

## Hotfix-Pfad

Pre-1.0 fahren wir keine separaten Patch-Branches. Hotfix = neuer
PATCH-Bump direkt auf `main`:

1. Fix-Commit mit konventionellem Message (`fix: …`).
2. Direkt in dieselbe Sequenz wie oben (CHANGELOG-Eintrag unter
   `[X.Y.Z+1]`, alle Versionen sync, Tag, Release).
3. Image-Rebuild + Push.

Wenn die `main`-Tip bereits weitere unveröffentlichte Features hat, gilt
der Repo-Stand zum Zeitpunkt des Hotfix-Tags. Cherry-Pick auf einen
separaten Branch ist nur dann nötig, wenn man bewusst ohne die
zwischenzeitlichen Features patchen will — bei einem Single-User-Setup
fast nie der Fall.

---

## Rollback eines Tags

Tag-Korrekturen sind **destructive**. Nur, wenn der Tag noch nicht
verteilt wurde (kein `gh release` veröffentlicht, kein Image gepushed):

```bash
git tag -d "v$BAD"
git push origin ":refs/tags/v$BAD"
```

Sonst: neuer PATCH-Bump (`+1`) und alten Tag im Release als
„yanked" kennzeichnen (`gh release edit "v$BAD" --notes "Yanked, see
v$NEXT."`).

---

## Followups

- **Versions-Sync-Slice** — `backend/pyproject.toml` (`0.6.1`) und
  `backend/app/__init__.py` (`__version__ = "0.8.0"`) auf `0.9.0` heben.
  Eigenes Sub-Slice, weil das einen `git tag`-Pfad anschneidet, den
  diese Doku nur beschreibt.
- **`scripts/release.sh`** — die Bump-Sequenz aus Schritt 2 als Skript
  zusammenziehen, damit kein Step manuell vergessen wird. Kandidat für
  ein eigenes Slice nach dem Versions-Sync.

---

## Quellen, die nicht hier stehen

- Was im `[Unreleased]`-Block landet, regelt der Slice-Workflow im
  [`MEMORY.md`](https://github.com/arn0ld87/agora/blob/main/CLAUDE.md)
  (siehe „Slice-Workflow" und „CHANGELOG.md ist tracked").
- Migrations-Inhalt von Releases steht in den jeweiligen
  Release-Notes-Dateien unter `docu/<datum>-v<X.Y.Z>-release-notes.md`.
