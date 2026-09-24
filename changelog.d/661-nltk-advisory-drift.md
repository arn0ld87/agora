### Security

- Dependency-Risk-Register, `.trivyignore` und `backend/pyproject.toml` führen PYSEC-2026-597 / CVE-2026-12243 nicht mehr als „ohne Upstream-Fix“: das reviewte GitHub Advisory nennt seit 2026-08-13 nltk 3.10.0 als gefixte Version. Der wirkungslose `nltk==3.10.3`-Override ist begründet, neuere nltk-Advisories sind davon getrennt dokumentiert (#661).
