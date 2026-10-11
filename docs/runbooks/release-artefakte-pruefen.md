# Release-Artefakte prüfen

**Stand:** 2026-10-11 · Issues [#1661](https://github.com/arn0ld87/agora/issues/1661), [#1592](https://github.com/arn0ld87/agora/issues/1592)

Jedes GitHub Release ab `0.10.0-rc.1` trägt vier Dateien, die `docker-image.yml` erzeugt und anhängt:

| Datei | Inhalt |
|---|---|
| `SHA256SUMS` | SHA-256 der drei folgenden Dateien, Format von `sha256sum` |
| `agora-image-digests.txt` | Manifest-Digests der publizierten Images, je Zeile `ghcr.io/arn0ld87/<image>@sha256:<digest>` |
| `agora-image.spdx.json` | SBOM von `ghcr.io/arn0ld87/agora` |
| `agora-proxy-image.spdx.json` | SBOM von `ghcr.io/arn0ld87/agora-proxy` |

Die Images selbst sind keine Release-Dateien. Sie sind über ihren Manifest-Digest adressiert; `SHA256SUMS` sichert die Digest-Datei, die Digest-Datei bindet die Images an das Release.

## Nachweis für den ersten RC-Tag `v0.10.0-rc.1`

Die Abschnitte 0 und 1 bilden zusammen den Nachweis, dass die Release-Artefakte des ersten RC-Tags vollständig und unverändert sind (Teil der Abnahme in [#1592](https://github.com/arn0ld87/agora/issues/1592)). Dafür gilt:

- **Erst nach der Veröffentlichung.** Der Nachweis setzt ein veröffentlichtes Release `v0.10.0-rc.1` voraus. Er ist kein Pre-Tag-Gate und darf den Tag-Schnitt nicht blockieren; die Bereitschaft vor dem Tag wird getrennt geprüft.
- **Dieses Runbook veröffentlicht nichts.** Tag und Release entstehen nach [`../release-process.md`](../release-process.md) §9 durch den Maintainer.
- **Jeder Befehl ist ein Urteil.** Ein Exit-Code ungleich 0 oder eine Ausgabe ohne `OK` heißt: Nachweis nicht erbracht. Dann nichts als bestanden festhalten, sondern die Ursache beheben und beide Abschnitte von vorn laufen lassen.
- **Ergebnis erst nach Ausführung festhalten** (Datum, Workflow-Lauf, Ausgabe) und im Issue #1592 ablegen. Bis dahin steht der Nachweis aus.

Die Abschnitte 2 und 3 sind weitere Prüfungen (Image-Tag, Provenance) und ersetzen den Nachweis nicht.

## 0. Tag, Veröffentlichung und Asset-Satz prüfen

```bash
TAG=v0.10.0-rc.1
REPO=arn0ld87/agora
meta=$(gh release view "$TAG" --repo "$REPO" --json tagName,isDraft,isPrerelease,assets)

# Tag-Identität, kein Draft, als Pre-Release gekennzeichnet
echo "$meta" | jq -e --arg tag "$TAG" \
  '.tagName == $tag and .isDraft == false and .isPrerelease == true'

# Genau der erwartete Asset-Satz: nichts fehlt, nichts kommt hinzu
EXPECTED='["SHA256SUMS","agora-image-digests.txt","agora-image.spdx.json","agora-proxy-image.spdx.json"]'
echo "$meta" | jq -e --argjson want "$EXPECTED" '([.assets[].name] | sort) == ($want | sort)'
```

Erwartet: beide `jq`-Aufrufe geben `true` aus und enden mit Exit-Code 0. Der Asset-Satz stammt aus dem Job `release-assets` in `docker-image.yml`.

- `tagName` weicht ab: Es wurde das falsche Release abgefragt, der Nachweis gilt nicht.
- `isDraft` ist `true`: Das Release ist nicht veröffentlicht. Den Draft nach [`../release-process.md`](../release-process.md) §9 veröffentlichen (siehe auch „Wenn Dateien fehlen").
- `isPrerelease` ist `false`: Das Release ist nicht als RC gekennzeichnet. Mit `gh release edit "$TAG" --repo "$REPO" --prerelease` korrigieren und den Nachweis wiederholen. Weder `docker-image.yml` noch §9 setzen das Flag.
- Asset-Satz weicht ab: fehlende Dateien nach „Wenn Dateien fehlen" nachliefern. Unerwartete Zusatzdateien klären, bevor der Nachweis gilt.

## 1. Dateien laden und Checksummen prüfen

```bash
gh release download "$TAG" --repo "$REPO" --dir "release-$TAG" \
  --pattern SHA256SUMS \
  --pattern agora-image-digests.txt \
  --pattern '*.spdx.json'
cd "release-$TAG"

# Heruntergeladen ist genau der erwartete Satz
[ "$(ls -1 | LC_ALL=C sort)" = "$(printf '%s\n' SHA256SUMS agora-image-digests.txt \
  agora-image.spdx.json agora-proxy-image.spdx.json | LC_ALL=C sort)" ]

# SHA256SUMS führt genau die drei gesicherten Dateien, keine mehr, keine weniger
[ "$(awk '{print $2}' SHA256SUMS | LC_ALL=C sort)" = "$(printf '%s\n' agora-image-digests.txt \
  agora-image.spdx.json agora-proxy-image.spdx.json | LC_ALL=C sort)" ]

sha256sum -c SHA256SUMS              # Linux
shasum -a 256 -c SHA256SUMS          # macOS
```

Erwartet: beide `[ … ]`-Prüfungen enden mit Exit-Code 0, danach drei Zeilen mit `OK` und Exit-Code 0. Ein `FAILED` heißt, die Datei am Release ist nicht die, die der Workflow erzeugt hat. Das Release dann nicht verwenden. Eine Abweichung in den `[ … ]`-Prüfungen heißt, Asset-Satz und Manifest passen nicht zusammen; die Checksummen allein belegen dann die Vollständigkeit nicht.

## 2. Tag und Digest abgleichen

Der Versions-Tag in GHCR muss auf genau den Digest zeigen, der im Release steht:

```bash
for image in agora agora-proxy; do
  expected=$(grep "/$image@" agora-image-digests.txt | cut -d@ -f2)
  actual=$(docker buildx imagetools inspect "ghcr.io/arn0ld87/$image:$TAG" \
    --format '{{json .Manifest}}' | jq -r .digest)
  [ "$expected" = "$actual" ] && echo "$image OK $actual" || echo "$image ABWEICHUNG: $expected != $actual"
done
```

Eine Abweichung heißt, der Tag wurde nach dem Release neu geschrieben. Für Deployments immer den Digest aus `agora-image-digests.txt` pinnen, nicht den Tag.

## 3. Provenance prüfen

```bash
while read -r ref; do
  gh attestation verify "oci://$ref" --repo arn0ld87/agora
done < agora-image-digests.txt
```

Details zur Attestation und zur SBOM-Auswertung mit syft/grype: [`../sbom-provenance.md`](../sbom-provenance.md).

## Wenn Dateien fehlen

- **Release ist ein Draft ohne Notes:** Der Tag-Push war schneller als `gh release create`. Den Draft nach [`../release-process.md`](../release-process.md) §9 mit `gh release edit … --draft=false` veröffentlichen.
- **Keine Assets am Release:** Im Workflow-Lauf des Tags den Job `release-assets` prüfen. Er läuft nur nach erfolgreichem `publish`. Die Dateien liegen zusätzlich 90 Tage als Workflow-Artefakt `agora-release-artifacts`; nach einem behobenen Fehler den Job neu starten (`gh run rerun <run-id> --job <job-id>`), er überschreibt vorhandene Assets mit `--clobber`.
