# Release-Artefakte prüfen

**Stand:** 2026-10-02 · Issue [#1661](https://github.com/arn0ld87/agora/issues/1661)

Jedes GitHub Release ab `0.10.0-rc.1` trägt vier Dateien, die `docker-image.yml` erzeugt und anhängt:

| Datei | Inhalt |
|---|---|
| `SHA256SUMS` | SHA-256 der drei folgenden Dateien, Format von `sha256sum` |
| `agora-image-digests.txt` | Manifest-Digests der publizierten Images, je Zeile `ghcr.io/arn0ld87/<image>@sha256:<digest>` |
| `agora-image.spdx.json` | SBOM von `ghcr.io/arn0ld87/agora` |
| `agora-proxy-image.spdx.json` | SBOM von `ghcr.io/arn0ld87/agora-proxy` |

Die Images selbst sind keine Release-Dateien. Sie sind über ihren Manifest-Digest adressiert; `SHA256SUMS` sichert die Digest-Datei, die Digest-Datei bindet die Images an das Release.

## 1. Dateien laden und Checksummen prüfen

```bash
TAG=v0.10.0-rc.1
gh release download "$TAG" --repo arn0ld87/agora --dir "release-$TAG" \
  --pattern SHA256SUMS \
  --pattern agora-image-digests.txt \
  --pattern '*.spdx.json'
cd "release-$TAG"

sha256sum -c SHA256SUMS              # Linux
shasum -a 256 -c SHA256SUMS          # macOS
```

Erwartet: drei Zeilen mit `OK`, Exit-Code 0. Ein `FAILED` heißt, die Datei am Release ist nicht die, die der Workflow erzeugt hat. Das Release dann nicht verwenden.

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
