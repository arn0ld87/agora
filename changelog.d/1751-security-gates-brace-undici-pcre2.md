### Security

- **Frontend:** `brace-expansion` 5.0.9 → 5.0.12 (GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p) und
  `undici` 7.29.0 → 7.30.0 (GHSA-rfgv-xxqx-mfg5, GHSA-w293-vg96-wgc3), jeweils über `overrides` in
  `frontend/package.json`. Beide kommen nur transitiv: über `minimatch` (eslint,
  typescript-eslint, `@vue/test-utils`) bzw. über jsdom. `bun audit --audit-level=high`
  im Job `Security scans` ist damit wieder grün. (#1751)
- **Proxy-Image:** Der GHA-Layer-Cache hielt die `apk upgrade`-Schicht der `proxy`-Stage fest,
  sodass `pcre2` 10.48-r0 (CVE-2026-103111, high) im Image blieb, obwohl Alpine 3.24 bereits
  10.49-r0 ausliefert. Der Trivy-Proxy-Scan in `build-only` schlug deshalb fehl. Beide
  Proxy-Builds in `docker-image.yml` laufen jetzt mit `no-cache-filters: proxy`; die
  `frontend-build`-Stage bleibt gecacht. Der `nginx:alpine`-Digest ist auf dem aktuellen Stand,
  enthält aber selbst noch 10.48-r0. (#1751)
