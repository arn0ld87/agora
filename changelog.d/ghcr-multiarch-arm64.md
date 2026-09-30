### Changed

- GHCR-Images `agora` und `agora-proxy` werden jetzt als Multi-Arch-Manifest
  (`linux/amd64` + `linux/arm64`) publiziert, mit unveränderten Tags
  (`sha-<7>`, `edge`, `vX.Y.Z`, `latest`). arm64 wird nativ auf
  `ubuntu-24.04-arm` gebaut (kein QEMU), per Digest gepusht und in einem
  Merge-Job zur Manifest-Liste zusammengeführt; Provenance und SBOM beziehen
  sich auf den Manifest-Digest. Das Smoke-Gate bleibt unverändert. Der
  produktive Host armserver ist aarch64 und zog bisher ein amd64-Image; die
  falschen "amd64-Host"-Kommentare in Workflow, Compose-Override und Runbook
  sind korrigiert.
