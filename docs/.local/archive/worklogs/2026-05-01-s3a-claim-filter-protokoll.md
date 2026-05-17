# S3a — Claim-Filter (Header & Bold-Section-Titel) · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** S3a

## Implementierung

Neue Helper-Methode `ReportAgent._is_claim_candidate(text)` in `backend/app/services/report_agent.py`. Filterregeln:

- Strings, die mit `#` beginnen → Markdown-Header → kein Claim
- Reine `**…**`-Zeilen mit < 8 Wörtern → Section-Titel → kein Claim
- Bullet-Items wie `- **Was passiert ist**` → kein Claim
- Leerstrings/Whitespace-only → kein Claim

`_build_claims_for_section` ruft den Filter direkt nach dem Chunk-Split an, bevor Evidence gebunden wird.

## Tests (2 neu)

- `test_is_claim_candidate_filters_markdown_headers_and_bold_titles`
- `test_build_claims_for_section_drops_headers`

501 Backend-Tests grün, 40 Frontend, Build clean.
