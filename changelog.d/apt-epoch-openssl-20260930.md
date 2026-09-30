### Security

- Prod-Image: `APT_SECURITY_EPOCH` auf 2026-09-30 gesetzt. Damit rebuildet der
  `apt-get upgrade`-Layer und zieht `openssl-provider-legacy` 3.5.7-1~deb13u3
  (CVE-2026-84782, CVE-2026-75804, beide HIGH). Der Trivy-Scan in `build-only`
  war dadurch auf allen PRs rot.
