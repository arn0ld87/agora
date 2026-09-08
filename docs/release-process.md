# Release-Prozess

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Scope:** Version-Cut, Changelog, Gates, Release Notes, Tag, Container-Publish und Rollback.

> [!IMPORTANT]
> `VERSION` in der Repo-Root ist die kanonische Produktversion. Der aktuelle Release-Prozess soll keine Versionszahl an mehreren Stellen von Hand „erfinden“.

Verwandte Dokumente:

- [`runbooks/release-versioning.md`](runbooks/release-versioning.md)
- [`../ROADMAP.md`](../ROADMAP.md)
- [`STATUS.md`](STATUS.md)
- [`deployment-prod-like.md`](deployment-prod-like.md)
- [`backup-restore.md`](backup-restore.md)

---

## 1. Release-Grundsätze

1. Release-Arbeit läuft über PR/CI, nicht per Direkt-Push auf `main`.
2. `VERSION` ist die Versions-SSoT.
3. `changelog.d/` sammelt Änderungen pro PR; `CHANGELOG.md` wird beim Release-Cut daraus erzeugt.
4. `docs/STATUS.md` enthält verifizierten Iststand/Testnachweise, nicht die README.
5. Release Notes nennen bekannte Grenzen explizit.
6. Ein Tag wird erst gesetzt, wenn der zugehörige Commit die vorgesehenen Gates erfüllt.
7. Für `0.10.0` und `1.0.0` gelten zusätzlich die Release-Gates aus [`ROADMAP.md`](../ROADMAP.md) / Issue #767.

---

## 2. Versionsquellen

Kanonisch:

```text
VERSION
```

Abgeleitete/verifizierte Stellen:

- `backend/pyproject.toml`
- `package.json`
- `frontend/package.json`
- `README.md`-Versionsbadge
- Runtime `backend/app/__init__.__version__`
- `README.de.md`-Versionsbadge und sichtbare Versionsangaben
- `docs/STATUS.md`-Versionsblock

### Automatischer Drift-Check

Aktuell prüft `backend/scripts/check_version_drift.py`:

1. `VERSION`
2. Backend-`pyproject.toml`
3. Root-`package.json`
4. Frontend-`package.json`
5. **englischen** `README.md`-Badge
6. Runtime-`__version__`

Der Checker erfasst **nicht automatisch `README.de.md`**. Genau deshalb konnte die deutsche README noch `0.9.4` zeigen, während `VERSION` längst `0.9.5` war. Bis der Checker beide Sprachfassungen abdeckt, ist `README.de.md` ein expliziter Release-Check.

```bash
cd backend
uv run python scripts/check_version_drift.py
```

Schreiben aus `VERSION`:

```bash
cd backend
uv run python scripts/check_version_drift.py --write
```

Danach zusätzlich:

```bash
grep -n "badge/version-" README.md README.de.md
grep -n "Current product version\|Aktuelle Produktversion\|Current version\|Aktuelle Version" \
  README.md README.de.md docs/STATUS.md || true
```

Langfristig soll der Drift-Checker beide README-Sprachen prüfen; bis dahin ist diese manuelle Zusatzprüfung Bestandteil des Release-Prozesses.

---

## 3. Changelog-Fragmente

Jeder normale PR legt ein Fragment nach folgendem Muster an:

```text
changelog.d/<pr-number>-<slug>.md
```

Beim Release-Cut:

```bash
python3 scripts/collect-changelog.py
python3 scripts/collect-changelog.py --check
```

Keine parallele Handpflege derselben Änderung zusätzlich in `CHANGELOG.md`.

---

## 4. STATUS vor dem Release aktualisieren

Für normale Feature-/Fix-PRs werden Testzähler nicht ständig neu gesammelt, um unnötige Konflikte zu vermeiden.

Für einen **Release-Cut** ist dagegen ein dedizierter Refresh angemessen:

```bash
bash scripts/sync-status.sh --no-cache
bash scripts/sync-status.sh --check --no-cache
```

Das aktualisiert die markierten Versions-/Testblöcke. Der Fließtext in `docs/STATUS.md` bleibt redaktionell und muss gegen die tatsächlichen Release-Blocker geprüft werden.

Keine Testzahl aus einem alten PR in Release Notes kopieren, wenn ein frischer Release-Candidate andere Ergebnisse hat.

---

## 5. Release-Readiness

Vor einem Tag müssen mindestens geprüft werden:

- vorgesehene Required Checks auf dem Release-Commit,
- Schema-/Contract-Drift,
- Version-Drift,
- Changelog-Fragment-Fold,
- relevante Backend-/Frontend-/E2E-Gates,
- Security-/Dependency-Gates,
- Dokumentationslinks und Versionsangaben,
- migrations-/betriebsrelevante Änderungen,
- bekannte Blocker im jeweiligen Release-Gate.

Für `1.0.0` reicht „CI grün“ ausdrücklich nicht. Zusätzlich verlangt die Roadmap unter anderem Fresh Install, Backup/Restore/Upgrade/Rollback, reproduzierbaren Referenzlauf, Baseline-Vergleich und einen RC-Zeitraum ohne neue P0/P1-Blocker.

---

## 6. Version-Cut

Beispiel für `0.10.0`:

```bash
NEW=0.10.0
printf '%s\n' "$NEW" > VERSION

cd backend
uv run python scripts/check_version_drift.py --write
uv lock
cd ..

# README.de ist derzeit nicht Teil des automatischen Drift-Writers:
# Badge/sichtbare Version dort bewusst synchronisieren.

bash scripts/sync-status.sh --no-cache
```

Danach prüfen:

```bash
cd backend
uv run python scripts/check_version_drift.py
cd ..

bash scripts/sync-status.sh --check --no-cache
grep -n "badge/version-$NEW-" README.md README.de.md
```

Wenn einer dieser Checks rot ist, wird nicht getaggt. Das ist der Moment, in dem Versionsdrift billig ist. Nach dem Publish wird derselbe Fehler plötzlich „Release Engineering“ genannt und bekommt Meetings.

---

## 7. Release Notes

Dateiformat:

```text
docs/<YYYY-MM-DD>-v<VERSION>-release-notes.md
```

Empfohlene Struktur:

1. **Header** — Version, Datum, Release-Linie.
2. **TL;DR** — was ändert sich für Nutzer/Operatoren.
3. **Highlights** — relevante Änderungen mit Issue-/PR-Bezug.
4. **Migration/Upgrade** — neue Variablen, Storage-/Schemaänderungen, Pflichtschritte.
5. **Verifikation** — welche Gates/Tests auf dem Release-Candidate tatsächlich liefen.
6. **Bekannte Grenzen** — ehrlich und konkret.
7. **Rollback** — falls release-spezifische Besonderheiten existieren.

Keine Marketingbehauptung „reproduzierbar“, solange #763/#1274 nicht abgenommen sind. Keine Behauptung „Production Ready“, solange die entsprechenden 1.0-Gates offen sind.

---

## 8. Commit und Tag

Nach vollständigem Cut:

```bash
git status --short

git add \
  VERSION \
  CHANGELOG.md \
  package.json \
  frontend/package.json \
  backend/pyproject.toml \
  backend/uv.lock \
  README.md \
  README.de.md \
  docs/STATUS.md \
  docs/<datum>-v<NEW>-release-notes.md

git commit -m "release: v$NEW"
```

Erst nach grünem Release-Commit:

```bash
git tag -a "v$NEW" -m "Agora v$NEW"
git push origin main
git push origin "v$NEW"
```

Branch-Protection-/Repository-Regeln bleiben führend. Wenn `main` keinen direkten Push zulässt, entsteht der Release-Commit über einen Release-PR und der Tag wird auf den gemergten Commit gesetzt.

---

## 9. GitHub Release

```bash
gh release create "v$NEW" \
  --title "Agora v$NEW" \
  --notes-file "docs/<datum>-v<NEW>-release-notes.md"
```

Bei bereits veröffentlichtem Tag niemals still den Tag auf einen anderen Commit bewegen. Korrekturen erfolgen als neues Patch-Release.

---

## 10. Container-Publish

Der normale Container-Release läuft über die GitHub-Actions-Release-/Image-Pipeline. Publish darf nicht der erste Schritt sein.

Reihenfolge:

```text
Build
→ Security/SBOM/Gates
→ prod-like / reverse-proxy smoke (wo konfiguriert)
→ Publish
→ Attestation/Checksums/Release-Artefakte
```

Break-glass-/force-publish-Pfade sind Ausnahmen und müssen im Release-Protokoll begründet werden.

Manuelle lokale `docker buildx --push`-Publishes sind kein gleichwertiger Ersatz für die definierte CI-Pipeline, weil sie deren Beweiskette umgehen.

---

## 11. Post-Release-Verifikation

Mindestens:

| Check | Erwartung |
|---|---|
| Remote-Tag | zeigt auf den freigegebenen Release-Commit |
| GitHub Release | Notes und Assets vorhanden |
| `/api/status.backend.version` | entspricht `VERSION` |
| README EN/DE | beide zeigen dieselbe Version |
| Container-Image | Digest/Tag entspricht Release |
| SBOM/Checksummen | vorhanden, wenn Release-Gate verlangt |
| Fresh-/Upgrade-Smokes | gemäß Release-Linie dokumentiert |

---

## 12. Hotfix

Pre-1.0 ist der normale Hotfix ein neuer PATCH-Bump über `main`:

1. Fix-PR.
2. Changelog-Fragment.
3. vollständiger Release-Cut für `X.Y.Z+1`.
4. neuer Tag/Release/Image.

Kein bestehender veröffentlichter Tag wird „korrigiert“.

Wenn `main` bereits nicht freizugebende Änderungen enthält, braucht der Hotfix einen bewusst gewählten Maintenance-Branch. Das ist eine explizite Release-Entscheidung und kein automatischer Cherry-Pick-Zirkus.

---

## 13. Rollback

### Code/Image

Rollback bedeutet auf einen bekannten guten Release-Commit/Image-Digest zurückzugehen.

### Daten

Wenn ein Release Persistenz oder Migrationen verändert, muss der dokumentierte Backup-/Restore-/Rollback-Pfad gelten. Ohne Restore-Test ist ein `git checkout` **kein vollständiger Rollback**.

Siehe [`backup-restore.md`](backup-restore.md) und Release-Gate #766.

### Tag

Ein bereits veröffentlichtes/verbrauchtes Tag nicht verschieben oder löschen. Stattdessen neues Patch-Release und altes Release klar als fehlerhaft/yanked kennzeichnen.

---

## 14. Feature Freeze Richtung 1.0

Mit dem ersten `0.10.0`-RC beginnt laut Roadmap der Feature-Freeze. Bis 1.0 gehören danach nur noch:

- Fehlerbehebungen,
- Security,
- Dokumentation,
- Migration/Recovery,
- Evaluation,
- nachgewiesene Release-Blocker

in die Release-Linie.

Neue Provider, Plattformflächen oder UI-Großumbauten sind kein legitimer Weg, einen unfertigen Release-Kern interessanter aussehen zu lassen.
