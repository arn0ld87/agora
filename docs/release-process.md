# Release-Process

**Stand:** 2026-08-11, Europe/Berlin
**Scope:** Wie ein neuer Tag (`vX.Y.Z`) entsteht. Reihenfolge, Release-Notes,
Publish-Gate, Hotfix- und Rollback-Pfad. Linear-Git-Flow gegen `main`,
Release-Candidate-Branches nur als Smoke-Gate (`release/**`, `rc/**`).

> [!IMPORTANT]
> **Den Versions-Bump selbst beschreibt dieses Dokument nicht mehr.** Seit
> dem `VERSION`-Umbau ist [`runbooks/release-versioning.md`](runbooks/release-versioning.md)
> dafür die maßgebliche Quelle. Dieses Dokument setzt einen erfolgten
> Version-Cut voraus und beschreibt, was danach passiert.

Verwandte Dokumente:
- [`runbooks/release-versioning.md`](runbooks/release-versioning.md) — Version-Cut,
  `VERSION` als SSoT, Drift-Check.
- [`deployment-prod-like.md`](deployment-prod-like.md) — Update- und
  Rollback-Pfad für laufende Setups.
- [`operations.md`](operations.md) — Healthcheck nach Deployment.

---

## Release-Gates und Branch Protection

`docker-image.yml` ist das harte Publish-Gate fuer Container-Releases.
Der Workflow baut zuerst ein lokales Image-Artefakt, extrahiert fuer den
Reverse-Proxy-Smoke das Frontend-Bundle aus genau diesem Image und pushed erst
danach zu GHCR. Docker Hub ist bis zur Phase-3-Image-Verkleinerung ein
optionaler Mirror, weil der GitHub-Runner grosse Layer wiederholt mit
Docker-Hub-HTTP-400 abbrechen liess. Der Docker-Hub-Mirror darf nie vor einem
gruenen Smoke laufen, blockiert aber den GHCR-Release-Pfad nicht.

Branch-Protection-Regeln fuer `main`:

1. Pull Requests muessen linear gemerged werden; direktes Pushen auf `main` ist
   nicht erlaubt.
2. Pflicht-Checks: `ci.yml`, `contract-gates.yml` und fuer Release-Kandidaten
   `docker-image.yml / Smoke-Test Reverse-Proxy-Stack`.
3. Teure Docker-Smokes laufen automatisch fuer `main`, Tags `v*`,
   Branches `release/**` und `rc/**` sowie PRs von `release/**` oder `rc/**`
   nach `main`. Normale Feature-PRs bleiben vom Docker-Smoke ausgenommen.
4. `publish` darf nicht aus Pull Requests laufen und hat als einziger Job
   `packages: write`, `id-token: write` und `attestations: write`.
5. Tag-Pushes haben keinen Smoke-Bypass mehr. Ein Image-Publish zu GHCR erfolgt
   nur bei gruenem `prod-proxy-smoke`; `latest` wird nur bei Pushes auf den
   Default-Branch gesetzt. Der optionale Docker-Hub-Mirror folgt ebenfalls erst
   nach gruenem Smoke.
6. `workflow_dispatch.inputs.force_publish=true` ist ein dokumentierter
   Break-glass-Pfad fuer Maintainer. Er ist nicht Teil des normalen
   Release-Prozesses und muss im PR-/Release-Protokoll begruendet werden.

## Versionsquellen

**[`VERSION`](../VERSION) in der Repo-Root ist die einzige Quelle der Wahrheit.**
Alle Manifeste leiten sich davon ab und werden nicht von Hand gepflegt:

| Pfad | Wie es synchronisiert wird |
|---|---|
| [`backend/pyproject.toml`](../backend/pyproject.toml) (`[project].version`) | `check_version_drift.py --write` |
| [`package.json`](../package.json) (`version`, Root) | `check_version_drift.py --write` |
| [`frontend/package.json`](../frontend/package.json) (`version`) | `check_version_drift.py --write` |
| [`README.md`](../README.md) Version-Badge | `check_version_drift.py --write` |

```bash
cd backend
uv run python scripts/check_version_drift.py          # prüfen, Exit 0 = kein Drift
uv run python scripts/check_version_drift.py --write  # aus VERSION nachziehen
```

Der Drift-Check läuft in CI (`version-drift.yml`) und lokal über
`bash scripts/pre-push-gate.sh schemas`.

`backend/app/__init__.py::__version__` ist **keine** eigene Quelle mehr: der
Wert wird zur Laufzeit aus den Paket-Metadaten gelesen (Fallback: Regex auf
`pyproject.toml`), und genau er erscheint unter `/api/status.backend.version`.

> **Bekannter, wirkungsloser Altwert:** `frontend/src/i18n/locales/{de,en}.json`
> tragen unter `home.tags.version` noch `v0.9.1-dev`. Der Schlüssel wird
> ausschließlich in `Home.vue` gerendert, und `/home` leitet seit
> [ADR-0010](decisions/0010-vue-v4-route-consolidation.md) auf `/dashboard` um —
> der Wert ist damit nicht sichtbar und nicht Teil des Drift-Checks. Er wird
> bewusst nicht gepflegt und verschwindet mit `Home.vue` in `1.0.0`.

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

Zuerst offene Fragmente einsammeln — PRs schreiben seit 2026-08-08 nicht mehr
direkt in `CHANGELOG.md`, sondern legen Fragmente unter `changelog.d/` ab:

```bash
python3 scripts/collect-changelog.py   # faltet changelog.d/ unter [Unreleased]
python3 scripts/collect-changelog.py --check   # muss danach "OK" melden
```

Erst danach den Block umbenennen:

```diff
-## [Unreleased]
+## [0.10.0] — 2026-06-01
+
+Milestone „<Name>" abgeschlossen — N/N Issues geschlossen, M Tests grün.
+<Kurz-Synopsis>.
```

Den `[Unreleased]`-Block leeren oder eine neue leere Sektion drüber
setzen, sobald der erste Post-Release-Commit auf `main` landet.

### 2. Version-Cut

Vollständig beschrieben in [`runbooks/release-versioning.md`](runbooks/release-versioning.md).
Kurzform:

```bash
NEW=0.10.0
echo "$NEW" > VERSION
cd backend && uv run python scripts/check_version_drift.py --write && uv lock && cd ..
bash scripts/sync-status.sh
cd backend && uv run python scripts/check_version_drift.py   # Exit 0 erwartet
```

Der Status-Block in README.md (`**Current version:**` / `**Aktuelle Version:**`
in beiden Sprachfassungen) wird vom Drift-Fixer **nicht** angefasst — nur der
Badge. Diese zwei Zeilen bleiben Handarbeit.

### 3. Release-Notes schreiben

Datei: `docs/<YYYY-MM-DD>-v<NEW>-release-notes.md`.

> Die frühere Vorlage `docs/2026-05-01-v0.9.0-release-notes.md` liegt nicht
> mehr im Repository. Bis eine neue Vorlagendatei existiert, ist die
> folgende Blockliste die Vorgabe; der letzte veröffentlichte Release-Text
> steht unter `gh release view v<letzte-version>`.

Blöcke in dieser Reihenfolge:

1. **Header** — Versionsnummer, Datum, Milestone-Name.
2. **TL;DR** — 1–2 Absätze, was das Release macht; absolute Testzahlen.
3. **Highlights** — drei bis fünf Aufzählungspunkte mit Issue-/EPIC-Bezug.
4. **Migrations-Hinweise** — neue `.env`-Variablen, Schema-Änderungen,
   Pflicht-Schritte für bestehende Setups.
5. **Tests** — exakte Test-Counter, Skip-Begründungen.
6. **Bekannte offene Punkte** — Sub-Slices, die anschließend kommen.

### 4. Tag

```bash
git add VERSION CHANGELOG.md package.json frontend/package.json \
        backend/pyproject.toml backend/uv.lock \
        README.md README.de.md docs/STATUS.md \
        docs/<datum>-v<NEW>-release-notes.md
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
  --notes-file "docs/<datum>-v<NEW>-release-notes.md"
```

GitHub picks up die Notes-Datei. Anhang (Container-Image-SHAs, Demo-GIFs)
optional.

### 6. Container-Image (optional)

Nur wenn ein neues Image gepushed wird. Der regulaere Pfad ist der
GitHub-Actions-Workflow `docker-image.yml` aus dem Tag-Commit:

```bash
git push origin "v$NEW"
gh run list --workflow docker-image.yml --limit 3
gh run watch <RUN_ID> --exit-status
```

Der Workflow published nur nach gruenem Reverse-Proxy-Smoke. Manuelle lokale
`docker buildx --push`-Publishes sind fuer v1.0 nicht der Standardpfad, weil
sie das Smoke-Gate umgehen wuerden.

---

## Verifikation nach dem Tag

| Check | Wie |
|---|---|
| Tag im Remote vorhanden | `git ls-remote --tags origin v$NEW` |
| GitHub-Release sichtbar | `gh release view "v$NEW"` |
| `/api/status.backend.version` zeigt neue Version | `curl -H "X-Agora-Token: $TOKEN" https://<host>/api/status \| jq .backend.version` |
| Frontend-Badge zeigt neue Version | UI-Smoke nach Cache-Bust. |
| `pip-audit` und `bun audit` grün | CI-Job `Security scans` auf `main` post-Tag. |

Bei Mismatch zwischen `/api/status.backend.version` und Tag: `VERSION` und
`backend/pyproject.toml` stehen auseinander, oder das Backend läuft noch aus
einer alten installierten Paket-Metadata. `check_version_drift.py` ohne
`--write` zeigt den ersten Fall; der zweite verschwindet mit einem
Neu-Install der Umgebung (`uv sync`) bzw. einem Image-Rebuild.

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

- **Release-Notes-Vorlage** — es existiert keine Vorlagendatei mehr im
  Repository. Entweder eine anlegen oder die Blockliste aus Schritt 3
  als alleinige Vorgabe festschreiben.
- **`scripts/release.sh`** — die Sequenz aus den Schritten 1–5 als Skript
  zusammenziehen, damit kein Schritt manuell vergessen wird. Der
  Version-Cut selbst ist mit `check_version_drift.py --write` bereits
  automatisiert; offen sind Changelog-Fold, Tag und GitHub-Release.

Der frühere Followup „Versions-Sync-Slice" ist erledigt: alle
Versionsquellen laufen über `VERSION` und werden von CI und Pre-Push-Gate
gegen Drift geprüft.

---

## Quellen, die nicht hier stehen

- Was in den `[Unreleased]`-Block einfließt, regelt
  [`changelog.d/README.md`](../changelog.d/README.md) — ein Fragment pro PR,
  eingesammelt von `scripts/collect-changelog.py`.
- Der Version-Cut selbst steht in
  [`runbooks/release-versioning.md`](runbooks/release-versioning.md).
- Migrations-Inhalt von Releases steht in den jeweiligen
  Release-Notes-Dateien unter `docs/<datum>-v<X.Y.Z>-release-notes.md`.
