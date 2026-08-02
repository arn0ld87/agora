# Dependency Risk Register

**Stand:** 2026-07-06, Europe/Berlin
**Ausgeloest durch:** Security Fix CVE-2026-4372 — Transformers Upgrade.
Automation: [.github/workflows/cve-monitor.yml](../.github/workflows/cve-monitor.yml) läuft wöchentlich Mo 06:00 UTC pip-audit --strict ohne --ignore-vuln und schreibt das Ergebnis in das Workflow-Summary. Hardstop am 2026-09-28 — danach failt der Job, wenn ignored CVEs noch offen sind.

> **Risikoakzeptanz 2026-07-06 (ALE-20 / ADR-0004):** Der nltk-Hardstop wurde einmalig von
> 2026-07-30 auf **2026-09-28** verlängert (max. +60 Tage laut Prozess). Grund: kein
> Upstream-Fix, nltk nur transitiv über `unstructured`, verwundbarer Pfad
> (`nltk.data.load()` mit user-kontrolliertem Pfad) in Agora nicht erreichbar. Entscheidung
> und Restrisiko dokumentiert in [docs/decisions/0004-cve-upstream-escalation.md](decisions/0004-cve-upstream-escalation.md).
> Erfordert User-Sign-off (Alex) im Risikoakzeptanz-PR. Betrifft **nur** die beiden
> nltk-Advisories (PYSEC-2026-597, GHSA-p4gq-832x-fm9v); die Trivy-Baseline (2026-08-30)
> bleibt unberührt. — **Nachtrag 2026-07-31:** Die Trivy-Baseline ist inzwischen aufgelöst
> (Issue #772), ihr Hardstop 2026-08-30 entfällt ersatzlos. Siehe Abschnitt unten.
> — **Nachtrag 2026-08-02:** Beide nltk-Advisories sind aufgelöst (nltk 3.9.4 → 3.10.1,
> Issue #995), der Hardstop 2026-09-28 entfällt für sie. GHSA-p4gq-832x-fm9v hat einen
> echten Upstream-Fix (nltk 3.10.0). PYSEC-2026-597 hat **keinen** — es fällt nur aus dem
> affected-Set der Advisory-DB (OSV `last_affected: 3.9.4`), Tooling flaggt es deshalb
> nicht mehr, ohne dass die Schwachstelle behoben wäre. Tracking bleibt offen in
> [#661](https://github.com/arn0ld87/agora/issues/661); [#672](https://github.com/arn0ld87/agora/issues/672)
> war die ursprüngliche Konsolidierungs-Referenz und ist seit 2026-07-27 geschlossen.
> Details unten unter „nltk-Baseline".
Supply-Chain-Baseline: [.github/workflows/scorecard.yml](../.github/workflows/scorecard.yml) läuft wöchentlich Mo 04:30 UTC und auf `push` nach `main`. SARIF-Ergebnisse werden ins Code-Scanning-Dashboard hochgeladen; der erste Remote-Run nach Merge ist die Scorecard-Baseline.

Dieses Dokument trackt bewusst ignorierte `pip-audit`-Findings und Trivy-Container-Scans.
Jedes Ignored-CVE hat ein GitHub-Issue, eine Frist und einen Owner. Neue Findings duerfen
nicht hinzugefuegt werden ohne dass sie zuerst als Issue aufgenommen werden.
Die CVEs der **aktiven** Baseline sind auch in der `.trivyignore`-Datei im Root-Verzeichnis
hinterlegt, um den Container-Scan nicht zu blockieren. Für Einträge im Status `resolved` gilt das
ausdrücklich nicht — sie bleiben hier nur als Historie stehen und sind aus `.trivyignore` entfernt
(so geschehen mit CVE-2026-24049 und CVE-2026-23949 am 2026-07-31).

**Maschinenlesbare Quelle:** [docs/dependency-risk-exceptions.json](dependency-risk-exceptions.json) —
wird von CI ([.github/workflows/cve-monitor.yml](../.github/workflows/cve-monitor.yml)) bei jedem Run
automatisch auf abgelaufene Deadlines geprüft. Abgelaufene Einträge failen den Workflow sofort.

### Wann ist eine Ausnahme zulässig?

Eine temporäre Dependency-Risk-Ausnahme darf nur eingetragen werden, wenn **alle** folgenden
Bedingungen erfüllt sind:

1. **Kein Upstream-Fix verfügbar:** Die Advisory-DB weist für das Paket in der verwendeten
   Version keinen Fix aus, oder der Fix ist durch einen transitiven Pin (z.B. via
   `sentence-transformers`) nicht installierbar.
2. **Issue vorhanden:** Das Finding ist als GitHub-Issue erfasst (Titel-Schema:
   `security: track ignored <CVE> until upstream fix`).
3. **Deadline gesetzt:** Die Frist beträgt maximal 90 Tage ab Eintragung. Verlängerungen
   erfordern einen expliziten Risikoakzeptanz-PR mit User-Sign-off.
4. **Owner benannt:** Eine Person oder ein Team übernimmt die Verantwortung für die
   Auflösung.
5. **Blocker dokumentiert:** Die URL oder das Issue, das den Fix blockiert, ist angegeben.

Ohne erfüllte Bedingungen gilt: sofort fixen, kein Register-Eintrag.

---

## Aktive Baseline

Aktuell keine aktiven pip-audit-Ausnahmen. Die bisher einzigen Einträge betrafen
`nltk` (Hardstop 2026-09-28) und sind am 2026-08-02 aufgelöst — siehe „nltk-Baseline"
unten.

## nltk-Baseline — aufgelöst 2026-08-02 (vormals Hardstop 2026-09-28)

pip-audit-Findings für `nltk==3.9.4` (transitiv über `unstructured`/`camel-oasis`),
zuvor per `--ignore-vuln` in [.github/workflows/ci.yml](../.github/workflows/ci.yml)
unterdrückt und in [.trivyignore](../.trivyignore) für den Container-Scan eingetragen.

**Status: `nltk` auf `3.10.1` gehoben (Issue #995), verifiziert per vollem Backend-
Testlauf (4159 passed, keine durch den Bump verursachte Regression). Beide
`--ignore-vuln`-Flags und die `.trivyignore`-Einträge sind entfernt.** Die zwei
betroffenen Advisories lösen sich dabei unterschiedlich ehrlich auf:

| Advisory | Schweregrad | Auflösung | Status | Issue |
|---|---|---|---|---|
| GHSA-p4gq-832x-fm9v (Alias CVE-2026-54293, PYSEC-2026-2078) | High | Echter Upstream-Fix in nltk 3.10.0. | resolved | [#995](https://github.com/arn0ld87/agora/issues/995) |
| PYSEC-2026-597 (Alias CVE-2026-12243) | unbekannt | **Kein echter Upstream-Fix.** OSV weist weiterhin kein `fixed`-Event aus, nur `last_affected: 3.9.4`. Ab nltk 3.10.0 fällt das installierte Paket aus dem affected-Set, pip-audit/Trivy melden den Fund deshalb nicht mehr — das ist eine Aufschubentscheidung durch Versions-Drift, keine Behebung der Schwachstelle. | resolved (Tooling flaggt nicht mehr) — **Issue bleibt offen** | [#661](https://github.com/arn0ld87/agora/issues/661) (offen) |

`#672` war die ursprüngliche Konsolidierungs-Referenz für beide Advisories und ist
seit 2026-07-27 geschlossen; beide Zeiger sind jetzt auf die jeweils zutreffenden
Issues korrigiert (#995 bzw. #661).

## Trivy Container Scan Baseline — aufgelöst 2026-07-31 (vormals Hardstop 2026-08-30)

Trivy-Findings aus `.github/workflows/docker-image.yml` (`exit-code: "1"`, `ignore-unfixed: true`).

**Status: erledigt. Der Hardstop 2026-08-30 entfällt, die `.trivyignore`-Einträge sind entfernt.**

| CVE | Quelle | Schweregrad | Owner | Status | Auflösung |
|---|---|---|---|---|---|
| CVE-2026-24049 | `wheel` — **nicht OS-Layer**, sondern `setuptools/_vendor/wheel` in der Backend-`.venv` | High | alex | resolved 2026-07-31 | `setuptools 80.9.0 → 83.0.0` (`33b3f310`, PR #828) hebt vendored `wheel` auf 0.46.3 (fixed ≥ 0.46.2) |
| CVE-2026-23949 | `jaraco.context` — **nicht OS-Layer**, sondern `setuptools/_vendor/jaraco` in der Backend-`.venv` | High | alex | resolved 2026-07-31 | derselbe Bump hebt vendored `jaraco.context` auf 6.1.0 (fixed ≥ 6.1.0) |

**Ursachenkorrektur:** Die ursprüngliche Begründung „Basis-Image-Update erforderlich" (Eintrag vom
2026-07-05, `63e923db`) war eine Fehldiagnose. `python:3.14-slim` liefert nur `pip` aus — der
CPython-Build nutzt `--with-ensurepip`, und `ensurepip` bündelt seit Python 3.12 weder `setuptools`
noch `wheel`. Beide Pakete kamen ausschließlich über `setuptools/_vendor/` in die `.venv`. Sachlich
richtig gewesen wäre „setuptools-Bump erforderlich"; ein Basis-Image-Update hätte die Findings nie
beheben können. Verifiziert am real gebauten Prod-Image (siehe unten).

**Verifikation (2026-07-31, lokal, linux/arm64):** Vollständiger Build der Prod-Stage, Scan mit
`trivy image --scanners vuln --severity CRITICAL,HIGH --ignore-unfixed` **ohne** `.trivyignore`.
Ergebnis: beide CVEs nicht mehr vorhanden; die `.venv` enthält `setuptools-83.0.0` mit
`_vendor/wheel-0.46.3` und `_vendor/jaraco_context-6.1.0`.

Vollständige Belege inkl. Primärquellen: [2026-07-31-issue-772-cve-basisimage-research.md](2026-07-31-issue-772-cve-basisimage-research.md).

**Prozess-Lehre:** Die beiden CVEs standen nie in `dependency-risk-exceptions.json`, weshalb die
Deadline-Prüfung in `cve-monitor.yml` ihre Frist nie überwacht hat — der Hardstop existierte nur als
Fließtext. Künftig gehört **jede** `.trivyignore`-Zeile auch in die JSON.

### Pin-Begruendungen

| Paket | Pinned Version | Upstream-Pin | Erklaerung |
|---|---|---|---|
| `transformers` | `>=5.3.0` | — | Upgrade auf v5 via `tool.uv.override-dependencies` unblocked durch `sentence-transformers>=5.3.0`. Behebt CVE-2026-4372, CVE-2026-1839 und PYSEC-2025-217. |
| `nltk` | `3.10.1` | — (kein Upstream-Pin) | Override-Pin `nltk==3.10.1` (2026-08-02, #995) löst GHSA-p4gq-832x-fm9v (echter Fix in 3.10.0) real auf. PYSEC-2026-597 bleibt ohne echten Upstream-Fix (kein `fixed`-Event in OSV), fällt aber ab 3.10.0 aus dem affected-Set (`last_affected: 3.9.4`) und wird deshalb nicht mehr geflaggt — Tracking bleibt offen in #661. Agora nutzt nltk weiterhin nur transitiv (via `unstructured`/`camel-oasis`). |

---

## Eskalationspfad (Hardstop 2026-09-28)

**Hinweis 2026-08-02:** Die Baseline, auf die sich dieser Pfad ursprünglich bezog
(PYSEC-2026-597, GHSA-p4gq-832x-fm9v), ist aufgelöst — siehe „nltk-Baseline" oben.
Der Abschnitt bleibt als Prozess-Vorlage für künftige Baseline-Einträge stehen.

Wenn am 2026-09-28 noch CVEs in der aktiven Baseline offen sind, greift einer dieser Pfade:

1. **Upstream released bis dahin** — `--ignore-vuln`-Flags aus [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) entfernen, Issue schließen, Eintrag nach „Abgeschlossen" verschieben.
2. **ADR [docs/decisions/0004-cve-upstream-escalation.md](decisions/0004-cve-upstream-escalation.md)** (Accepted 2026-07-06) entscheidet zwischen:
   - **Vendoring** der betroffenen Subkomponenten,
   - **Soft-Fork** mit Patch-Ringen,
   - **Replacement** durch andere Pakete (z.B. `langgraph` statt `camel-oasis`).
3. **Risikoakzeptanz-PR** mit expliziter Verlängerung der `--ignore-vuln`-Flags um maximal 60 Tage und neuem Hardstop-Datum. Erfordert User-Sign-off.
   → **2026-07-06 gewählt (ALE-20):** Hardstop von 2026-07-30 auf 2026-09-28 verlängert (+60 Tage),
   weil Upstream weiterhin keinen Fix released hat und Option „Replacement/Vendoring" für nur
   transitiv genutztes, nicht erreichbares nltk unverhältnismäßig wäre. Details in ADR-0004.

Der CVE-Monitor-Workflow erzwingt die Entscheidung: ab Hardstop-Datum schlägt er bei jedem Run fehl, bis eine der drei Optionen umgesetzt ist.

## Prozess

1. **Neues Finding:** `pip-audit` oder `npm audit` meldet eine Advisory. Der wöchentliche CVE-Monitor entdeckt neue Findings automatisch.
2. **Pruefung:** Ist das Finding durch einen Upstream-Pin blockiert?
   - **Ja:** Issue erstellen (Titel: `security: track ignored <CVE> until
     upstream fix), ins Register eintragen, Frist +90 Tage, in [.github/workflows/ci.yml](../.github/workflows/ci.yml) --ignore-vuln-Flag ergänzen.
   - **Nein:** Sofort fixen, kein Register-Eintrag noetig.
3. **Wöchentliche Sichtung:** [CVE-Monitor-Workflow](../.github/workflows/cve-monitor.yml) → Workflow-Summary lesen. Wenn ein CVE aus der Baseline verschwindet, ist Upstream gepatcht.
4. **30-Tage-Inventur:** Register-Inventur. Abgelaufene Fristen → P0 Bug-Ticket.
5. **Abschluss:** Wenn upstream released und Dependency geupdated, Issue
   schliessen, Register-Eintrag nach Abgeschlossen verschieben, --ignore-vuln-Flag aus [.github/workflows/ci.yml](../.github/workflows/ci.yml) entfernen.

---

## Abgeschlossen

| CVE | Paket | Aufloesung | Datum |
|---|---|---|---|
| CVE-2026-4372 | `transformers` | Resolved via Upgrade auf `transformers>=5.3.0` (unblocked durch `sentence-transformers>=5.3.0`). `--ignore-vuln`-Flag aus CI entfernt. Issue #662 schließen. | 2026-07-06 |
| CVE-2026-1839 | `transformers` | Resolved via Upgrade auf `transformers>=5.3.0` (unblocked durch `sentence-transformers>=5.3.0`). `--ignore-vuln`-Flag aus CI entfernt. Issue #124 schließen. | 2026-07-06 |
| PYSEC-2025-217 | `transformers` | Resolved via Upgrade auf `transformers>=5.3.0` (unblocked durch `sentence-transformers>=5.3.0`). `--ignore-vuln`-Flag aus CI entfernt. Issue #624 schließen. | 2026-07-06 |
| PYSEC-2026-139 | `torch` | Resolved via Upgrade auf `torch==2.12.1` (verified via `uvx pip-audit --strict`: Finding feuert nicht mehr). `--ignore-vuln`-Flag aus CI entfernt. Issue #623 schließen. | 2026-07-05 |
| CVE-2026-25990 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #121 schließen. | 2026-05-15 |
| CVE-2026-40192 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #122 schließen. | 2026-05-15 |
| CVE-2026-42308 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #296 schließen. | 2026-05-15 |
| CVE-2026-42310 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #297 schließen. | 2026-05-15 |
| CVE-2026-42311 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #298 schließen. | 2026-05-15 |
| CVE-2025-71176 | `pytest` | Resolved via `tool.uv.override-dependencies`: `pytest==9.0.3` installiert (verified via `uv run pytest --version`). `--ignore-vuln`-Flag aus CI entfernt. Issues #123 schließen. | 2026-05-19 |
| CVE-2024-46455 | `unstructured` | Resolved via `tool.uv.override-dependencies`: `unstructured>=0.18.18` installiert (verified via `uv run pip-audit`). `--ignore-vuln`-Flag aus CI entfernt. Issues #125 schließen. | 2026-05-19 |
| CVE-2025-64712 | `unstructured` | Resolved via `tool.uv.override-dependencies`: `unstructured>=0.18.18` installiert (verified via `uv run pip-audit`). `--ignore-vuln`-Flag aus CI entfernt. Issues #126 schließen. | 2026-05-19 |
