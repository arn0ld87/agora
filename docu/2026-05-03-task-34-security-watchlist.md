# Security-Watchlist — ignorierte CVEs (Stand 2026-05-10)

**Refs:** #121 #122 #123 #124 #125 #126
**Status:** Watchlist konsolidiert. Issues bleiben offen, bis Upstream-Pins gelöst sind.

## Übersicht

| CVE | Issue | Paket | uv.lock-Version | Pinning-Source | Risk | Deadline |
|---|---|---|---|---|---|---|
| CVE-2026-25990 | #121 | pillow | 10.3.0 | camel-ai==0.2.78 (`pillow<11`) | Medium | 2026-07-30 |
| CVE-2026-40192 | #122 | pillow | 10.3.0 | camel-ai==0.2.78 (`pillow<11`) | Medium | 2026-07-30 |
| CVE-2025-71176 | #123 | pytest | 8.2.0 | camel-oasis==0.2.5 (`pytest==8.2.0`) | Low | 2026-07-30 |
| CVE-2026-1839 | #124 | transformers | 4.57.6 | sentence-transformers==3.0.0 (`transformers<5`) | Medium | 2026-07-30 |
| CVE-2024-46455 | #125 | unstructured | 0.13.7 | camel-oasis==0.2.5 (`unstructured==0.13.7`) | Medium | 2026-07-30 |
| CVE-2025-64712 | #126 | unstructured | 0.13.7 | camel-oasis==0.2.5 (`unstructured==0.13.7`) | Medium | 2026-07-30 |

Alle Versionen aus `backend/uv.lock` (Stand 2026-05-03) verifiziert. Pinning-Sources aus den Issue-Bodys übernommen.

## Pro CVE

### CVE-2026-25990 (Issue #121) — pillow

- **Paket:** `pillow==10.3.0`
- **Pinning-Source:** `camel-ai==0.2.78` (pinned by `camel-oasis==0.2.5`)
- **Risk:** Medium — image processing library; Agora nutzt Pillow im PDF-Vision-Pipeline-Downscaling und für Format-Konvertierung.
- **Betroffen in Agora:** PDF-Embedding-Pipeline (Vision-Workflows), Resampling und Format-Normalisierung.
- **Target-Version:** `pillow>=10.4.0` oder `>=11.0.0`, sobald camel-ai den Pin lockert.
- **Deadline:** 2026-07-30 (+90 Tage)
- **Action:**
  - Monitor: GitHub camel-ai/camel-ai Release-Channel + PyPI `camel-ai`-Releases.
  - Re-run-Trigger: nach jedem `uv lock --upgrade-package camel-ai` erneut `uv run pip-audit`.

### CVE-2026-40192 (Issue #122) — pillow

- **Paket:** `pillow==10.3.0` (gleicher Pin wie #121, separate CVE)
- **Pinning-Source:** `camel-ai==0.2.78` (limits `pillow<11`)
- **Risk:** Medium — gleiche Begründung wie #121.
- **Target-Version, Deadline, Action:** s. #121 — wird mit derselben camel-ai-Pin-Lockerung geschlossen.

### CVE-2025-71176 (Issue #123) — pytest

- **Paket:** `pytest==8.2.0`
- **Pinning-Source:** `camel-oasis==0.2.5` (pins `pytest==8.2.0`)
- **Risk:** Low — Test-Runner, nicht im Prod-Runtime aktiv. Nur in `backend/tests/` und CI relevant.
- **Betroffen in Agora:** Test-Suite (`backend/tests/`); kein Impact auf laufende Simulationen.
- **Target-Version:** `pytest>=9.0.3` (Fix-Version laut pip-audit), sobald camel-oasis den Pin lockert.
- **Deadline:** 2026-07-30 (+90 Tage)
- **Action:**
  - Monitor: PyPI `camel-oasis`-Releases.
  - Re-run-Trigger: nach jedem camel-oasis-Bump erneut `uv run pip-audit`.

### CVE-2026-1839 (Issue #124) — transformers

- **Paket:** `transformers==4.57.6`
- **Pinning-Source:** `sentence-transformers==3.0.0` (limits `transformers<5`)
- **Risk:** Medium — HuggingFace-Transformers, genutzt indirekt über sentence-transformers für Embeddings (Knowledge-Graph-Indizierung, Evidence-Binder, Cluster-Naming).
- **Betroffen in Agora:** `backend/app/services/evidence_binder.py` (Embed-Funktion), Cluster-Embeddings im `network_analytics`-Pfad.
- **Target-Version:** `transformers>=4.58.0`, sobald sentence-transformers den Pin lockert.
- **Deadline:** 2026-07-30 (+90 Tage)
- **Action:**
  - Monitor: PyPI `sentence-transformers`-Releases (UKPLab/sentence-transformers).
  - Re-run-Trigger: nach jedem sentence-transformers-Bump erneut `uv run pip-audit`.

### CVE-2024-46455 (Issue #125) — unstructured

- **Paket:** `unstructured==0.13.7`
- **Pinning-Source:** `camel-oasis==0.2.5` (pins `unstructured==0.13.7`)
- **Risk:** Medium — Document-Parsing-Library, genutzt für Text-Extraktion aus PDF/DOCX im Onboarding-Pfad.
- **Betroffen in Agora:** PDF/DOCX-Upload-Pipeline (Step 1, Wissensquellen einlesen).
- **Target-Version:** `unstructured>=0.14.0`, sobald camel-oasis den Pin lockert.
- **Deadline:** 2026-07-30 (+90 Tage)
- **Action:** s. #123 — bündelt sich mit camel-oasis-Bump.

### CVE-2025-64712 (Issue #126) — unstructured

- **Paket:** `unstructured==0.13.7` (gleicher Pin wie #125, separate CVE)
- **Pinning-Source:** `camel-oasis==0.2.5` (pins `unstructured==0.13.7`)
- **Risk:** Medium — gleiche Begründung wie #125.
- **Target-Version, Deadline, Action:** s. #125 — wird mit derselben camel-oasis-Pin-Lockerung geschlossen.

## Konsolidierte Aktion

- **Wöchentlich:** `cd backend && uv run pip-audit --output json` und Diff gegen Vorwoche. Falls neue CVEs in den 4 Paketen auftauchen (pillow, pytest, transformers, unstructured) oder deren transitiven Deps: neuen Issue im Watchlist-Schema öffnen.
- **Bei jedem Upstream-Release** der Pinning-Sources `camel-ai`, `camel-oasis`, `sentence-transformers`: pip-audit, dann `uv lock --upgrade-package <name>`, dann Re-Audit.
- **Hardstop:** Wenn ein offener CVE auf High eskaliert (CVSS ≥ 7) oder die 90-Tage-Deadline (2026-07-30) ohne Pin-Lösung verstreicht — dann eigener P0-Slice für Drop oder Fork des betroffenen Subgraphs (z. B. camel-oasis-Fork mit relaxiertem unstructured-Pin).

## Out of Scope

- KEIN Dep-Upgrade in diesem Slice. `backend/pyproject.toml` und `backend/uv.lock` bleiben unverändert.
- KEINE Workarounds (z. B. Pillow-SIMD statt Pillow, eigener PDF-Parser statt unstructured) — bei Hardstop-Trigger separater Slice.
- KEIN Fork von camel-ai/camel-oasis — separater Architektur-Entscheid, nicht Watchlist-Scope.

## Verifikation (Stand 2026-05-10)

- [x] Alle 6 Issues konsolidiert
- [x] uv.lock-Versionen aus `backend/uv.lock` verifiziert (pillow 10.3.0, pytest 8.2.0, transformers 4.57.6, unstructured 0.13.7, camel-ai 0.2.78, camel-oasis 0.2.5, sentence-transformers 3.0.0)
- [x] Pinning-Sources aus Issue-Bodys verifiziert
- [x] Risk-Levels aus Issue-Bodys übernommen (5× Medium, 1× Low)
- [x] Deadlines konsistent (alle 2026-07-30, +90 Tage)
- [x] `pyproject.toml` und `uv.lock` unverändert

## Hinweis zum Slice-Verlauf

Initial-Generierung durch `agora-doc-worker` (Haiku) lieferte teilweise halluzinierte Paket-Daten (z. B. `cryptography`, `PyYAML`, `sentence-transformers` als CVE-betroffene Pakete — keines davon ist tatsächlich in einem der 6 Issues genannt). Die Doku wurde im Anschluss vom Orchestrator gegen die echten Issue-Bodys (`gh issue view`) und `backend/uv.lock` korrigiert. Voice-Lint via `backend/scripts/check_voice.py` läuft nach Korrektur sauber.
