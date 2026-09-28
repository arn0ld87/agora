### Added

- Every green push to `main` publishes `ghcr.io/arn0ld87/agora` and the new `ghcr.io/arn0ld87/agora-proxy` (nginx with the frontend bundle, no build-time token) as `sha-<7>` and `edge`, each with build-provenance attestation. The gate is the `build-only` job (build and Trivy for both images); `vX.Y.Z` and `latest` are still published only after a green reverse-proxy smoke.
- Opt-in overlay `deploy/compose/docker-compose.ghcr.yml` pulls both images from GHCR instead of building them; `AGORA_IMAGE_TAG` is required and has no default. Without the overlay Compose builds as before. Runbook: `docs/runbooks/ghcr-deploy.md`.

### Changed

- `latest` now means the latest release tag that passed the smoke, not the default branch. The bare-SHA tag is replaced by `sha-<7>`.
- The Docker Hub mirror runs only on release paths, no longer on `main`.
- Prod and proxy builds use separate GitHub Actions cache scopes (`prod`, `proxy`).

### Fixed

- The release smoke no longer builds the proxy image inside a job whose egress allowlist blocks the Alpine, Debian and npm package sources. It starts both images from `build-only` with `--no-build`. Before, the build hung until the 30-minute timeout (v0.9.6), and `publish` never ran.
- `publish` can reach Sigstore (`fulcio`, `rekor`, `tuf-repo-cdn` on `sigstore.dev`). The first real publish pushed `agora` and then failed at the provenance attestation with `ECONNREFUSED`, so `agora-proxy` was never published.
