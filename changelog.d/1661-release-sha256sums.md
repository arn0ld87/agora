### Added (Release-Checksummen — 2026-10-02)

- **`SHA256SUMS` am GitHub Release:** `docker-image.yml` erzeugt im Job `publish` zusätzlich eine SBOM für `agora-proxy`, hält beide Manifest-Digests in `agora-image-digests.txt` fest und bildet `SHA256SUMS` über Digest-Datei und beide SBOMs. Der neue Job `release-assets` prüft die Summen bei `v*`-Tags erneut und hängt alle vier Dateien ans Release (fehlt es noch, als Draft). Er ist der einzige Job mit `contents: write`. Verifikation: `docs/runbooks/release-artefakte-pruefen.md`. (#1661)
