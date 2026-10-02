### Security

- `pypdf` 6.16.1 → 6.19.0 in `backend/uv.lock`. Das Paket kommt nur
  transitiv über `unstructured-client` (`pypdf>=6.2.0`) ins Lock; Agora
  selbst liest PDFs über PyMuPDF. Acht Advisories (PYSEC-2026-4153 bis
  -4160, Aliasse CVE-2026-102993 bis CVE-2026-103000, behoben zwischen 6.17.0
  und 6.19.0) ließen den Python-Dependency-Audit im Job `Security scans` auf
  `main` fehlschlagen (Run 36898610864). Ohne `--ignore-vuln`, ohne
  Override. (#1748)
