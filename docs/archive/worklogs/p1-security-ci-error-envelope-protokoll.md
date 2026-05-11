# P1 Security-Scans und Error-Envelope — Arbeitsprotokoll

**Datum:** 2026-04-29  
**Branch:** `ci/p1-security-checks`  
**Scope:** `docs/archive/old-plans/REFACTORING_PLAN.md` P1

## Ziel

- Security-Scans fest in CI verankern: Frontend Dependency Audit, Python Dependency Audit, Secret Scan.
- API-Fehlerhülle vereinheitlichen und 5xx-Fehler im Nicht-Debug-Modus ohne interne Exception-Details ausliefern.
- Änderungen klein halten und ohne neue Runtime-Abhängigkeiten umsetzen.

## Umsetzung

| Bereich | Änderung | Risiko |
|---|---|---|
| CI | Neuer Job `security` in `.github/workflows/ci.yml` | Niedrig; Scans können bei bestehenden Findings rot werden. |
| Frontend Audit | `npm audit --audit-level=high` im `frontend/`-Lockfile-Kontext | Niedrig; nutzt vorhandenes `package-lock.json`. |
| Python Audit | `uv export --frozen --no-dev --no-hashes --no-emit-project` plus `uvx pip-audit --strict -r ...` | Niedrig-Mittel; bekannte transitive CVEs schlagen künftig hart an. |
| Secret Scan | `gitleaks/gitleaks-action@v2` mit voller Git-Historie | Niedrig-Mittel; historische echte Secrets erfordern Rotation und Bereinigung. |
| Secret Baseline | `.gitleaksignore` mit zwei Fingerprint-genauen False Positives | Niedrig; neue Secret-Findings bleiben blockierend. |
| API-Envelope | `handle_api_errors()` gibt bei 500/504 sichere Standardmeldungen plus Codes aus | Niedrig; Debug-Details bleiben nur bei `Config.DEBUG=true`. |
| Framework-Errors | App-weite API-Handler für generische `HTTPException` und ungefangene API-Exceptions | Niedrig; Nicht-API-Routen bleiben unverändert. |

## Security-Entscheidungen

- 4xx-Fehler bleiben konkret, weil sie Client-Eingaben betreffen und für UI/Tests steuerbar sein müssen.
- 5xx-Fehler liefern im Nicht-Debug-Modus nur `internal server error`; konkrete Exception-Texte werden geloggt.
- `Config.DEBUG=true` ergänzt `debug_error` und `traceback`, damit lokale Entwicklung weiterhin schnell debuggbar bleibt.
- `pip-audit` scannt Runtime-Dependencies (`--no-dev`), um produktionsrelevante Findings im Standard-Gate zu priorisieren.
- 39 Python-Advisories wurden durch ein konservatives `uv.lock`-Upgrade behoben. 6 verbleibende Advisories sind als temporäre Baseline im CI ignoriert, weil sie durch feste Upstream-Pins blockiert sind.
- Gitleaks scannt mit `fetch-depth: 0`, damit versehentlich committete Secrets in der Historie auffallen.
- Lokaler Gitleaks-Smoke-Check fand zwei False Positives aus der Historie; beide sind fingerprint-genau in `.gitleaksignore` dokumentiert.

## Temporäre pip-audit-Baseline

| Advisory | Paket | Blocker |
|---|---|---|
| `CVE-2026-25990` | `pillow==10.3.0` | `camel-ai==0.2.78` begrenzt `pillow<11`. |
| `CVE-2026-40192` | `pillow==10.3.0` | `camel-ai==0.2.78` begrenzt `pillow<11`. |
| `CVE-2025-71176` | `pytest==8.2.0` | `camel-oasis==0.2.5` pinnt `pytest==8.2.0`. |
| `CVE-2026-1839` | `transformers==4.57.6` | `sentence-transformers==3.0.0` begrenzt `transformers<5`. |
| `CVE-2024-46455` | `unstructured==0.13.7` | `camel-oasis==0.2.5` pinnt `unstructured==0.13.7`. |
| `CVE-2025-64712` | `unstructured==0.13.7` | `camel-oasis==0.2.5` pinnt `unstructured==0.13.7`. |

Diese Baseline ist bewusst eng: neue Advisories oder gelöste Upstream-Pins sollen den CI-Job wieder rot machen.

## Gitleaks-Baseline

| Fingerprint | Bewertung |
|---|---|
| `c92385bbfca1e16b246c5827f7145a1f0f304c1e:backend/app/utils/auth.py:generic-api-key:90` | False Positive: historischer Auth-Helper-Attributname, kein Secret. |
| `92cfdf99188a76b51b18543eacd16d3eae48e92b:backend/tests/test_signed_ticket.py:generic-api-key:55` | False Positive: absichtlich ungültiger Signed-Ticket-Teststring. |

## Verifikation

Geplante Checks nach Patch:

```bash
cd backend
uv run pytest tests/test_api_responses.py
uv run ruff check app/utils/api_responses.py tests/test_api_responses.py

cd ../frontend
npm audit --audit-level=high

cd ../backend
uv export --frozen --no-dev --no-hashes --no-emit-project \
  --format requirements.txt --output-file /tmp/agora-backend-requirements.txt \
  > /dev/null
uvx pip-audit --strict \
  --ignore-vuln CVE-2026-25990 \
  --ignore-vuln CVE-2026-40192 \
  --ignore-vuln CVE-2025-71176 \
  --ignore-vuln CVE-2026-1839 \
  --ignore-vuln CVE-2024-46455 \
  --ignore-vuln CVE-2025-64712 \
  -r /tmp/agora-backend-requirements.txt
```

## Rollback

```bash
git revert <commit>
```

Alternativ kann der neue CI-Job `security` temporär aus `.github/workflows/ci.yml` entfernt werden, falls ein externes Advisory kurzfristig einen Release-Blocker erzeugt.
