### Security

- **Frontend:** `brace-expansion` 5.0.9 → 5.0.12 (GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p) und
  `undici` 7.29.0 → 7.30.0 (GHSA-rfgv-xxqx-mfg5, GHSA-w293-vg96-wgc3), jeweils über `overrides` in
  `frontend/package.json`. Beide kommen nur transitiv: über `minimatch` (eslint,
  typescript-eslint, `@vue/test-utils`) bzw. über jsdom. `bun audit --audit-level=high`
  im Job `Security scans` ist damit wieder grün. (#1751)
- **Proxy-Image:** `nginx:alpine`-Digest auf den aktuellen Stand. Der alte Pin hielt den
  GHA-Layer-Cache der `apk upgrade`-Schicht fest, sodass `pcre2` 10.48-r0 (CVE-2026-103111, high)
  im Image blieb, obwohl Alpine 3.24 bereits 10.49-r0 ausliefert. Der Trivy-Proxy-Scan in
  `build-only` schlug deshalb fehl. (#1751)
