# Release-Versionierung

**Stand:** 19.07.2026

## Versionierung ist einfach

Die Datei `VERSION` in der Repo-Root ist die einzige Quelle der Wahrheit für die Produktversion. Alle anderen Manifeste (`backend/pyproject.toml`, `package.json`, `frontend/package.json` und der README-Badge) leiten sich davon ab.

Es gibt keine lokalen Versionsangaben, die von `VERSION` abweichen dürfen.

## Version-Cut für einen Release

Folgende Schritte müssen in einem PR zusammen durchgeführt werden:

### (a) VERSION editieren

```bash
echo "0.9.0" > VERSION
git add VERSION
```

### (b) Drift-Fixer ausführen

```bash
cd backend
uv run python scripts/check_version_drift.py --write
```

Das schreibt den `VERSION`-Wert in:
- `backend/pyproject.toml` (`[project].version`, PEP 621)
- `package.json` (version, root)
- `frontend/package.json` (version)
- `README.md` (Version-Badge)

### (c) Backend-Lock updaten

```bash
cd backend
uv lock
```

### (d) STATUS-Tabelle synchronisieren

```bash
bash scripts/sync-status.sh
```

Das erneuert die E2E-Smoke-Tabelle und den Istzustand in `docs/STATUS.md`.

### (e) Drift verifizieren

```bash
cd backend
uv run python scripts/check_version_drift.py
# Exit-Code 0 = kein Drift
```

Ist der Exit-Code nicht 0, fehlt eine Datei im Drift-Check oder (b) ist fehlgeschlagen.

### (f) Committen

```bash
git add -A
git commit -m "chore(release): Version 0.9.0 (Closes #<NR>)"
git push -u origin <branch>
```

Alles in einem Commit, das entspricht dem atomaren Scope des Release-PRs.

## Wo der Drift-Check greift

**Automatisch auf CI:**
- `.github/workflows/version-drift.yml` wird bei Push getriggert
- CI-Job schlägt fehl (exit 1) bei Drift von `VERSION`

**Lokal vor Push (Pflicht):**
- `bash scripts/pre-push-gate.sh schemas` enthält den Check
- auch `bash scripts/pre-push-gate.sh` (vollständiges Gate) enthält ihn
- Kein `--no-verify` bypass erlaubt

## Backend-Paket-Version

`backend/app/__init__.__version__` wird **nicht** manuell geschrieben. Es wird stattdessen aus den Paket-Metadaten (PEP 621 `[project].version` in `backend/pyproject.toml`, via `uv`) abgeleitet.

## Out-of-Scope

Dieses Runbook deckt die **manifeste Versionssynchronisation** ab. Folgende Aufgaben gehören zu einem Release, werden aber hier nicht dokumentiert:

- Git-Tag setzen (z.B. `git tag 0.9.0`)
- Releases in GitHub ablegen
- Deployment und Rollout
- Änderlog außer dem Drift-Fix selbst

Diese gehören in ein separates Release-Playbook oder eine Ablauf-Dokumentation für Deployer.
