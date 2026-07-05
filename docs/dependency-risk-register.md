# Dependency Risk Register

**Stand:** 2026-07-06, Europe/Berlin
**Ausgeloest durch:** Security Fix CVE-2026-4372 — Transformers Upgrade.
Automation: [.github/workflows/cve-monitor.yml](../.github/workflows/cve-monitor.yml) läuft wöchentlich Mo 06:00 UTC pip-audit --strict ohne --ignore-vuln und schreibt das Ergebnis in das Workflow-Summary. Hardstop am 2026-07-30 — danach failt der Job, wenn ignored CVEs noch offen sind.
Supply-Chain-Baseline: [.github/workflows/scorecard.yml](../.github/workflows/scorecard.yml) läuft wöchentlich Mo 04:30 UTC und auf `push` nach `main`. SARIF-Ergebnisse werden ins Code-Scanning-Dashboard hochgeladen; der erste Remote-Run nach Merge ist die Scorecard-Baseline.

Dieses Dokument trackt bewusst ignorierte `pip-audit`-Findings und Trivy-Container-Scans.
Jedes Ignored-CVE hat ein GitHub-Issue, eine Frist und einen Owner. Neue Findings duerfen
nicht hinzugefuegt werden ohne dass sie zuerst als Issue aufgenommen werden.
Die hier gelisteten CVEs sind auch in der `.trivyignore`-Datei im Root-Verzeichnis
hinterlegt, um den Container-Scan nicht zu blockieren.

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

## Aktive Baseline (Hardstop 2026-07-30)

| CVE | Paket | Schweregrad | Fix verfügbar? | Owner | Frist | Status | Issue | Upstream-Release-Watch |
|---|---|---|---|---|---|---|---|---|
| PYSEC-2026-597 | `nltk` | unbekannt | Nein (kein Upstream-Fix released) | NLTK | 2026-07-30 | open | [#661](https://github.com/arn0ld87/agora/issues/661) | [nltk/nltk/releases](https://github.com/nltk/nltk/releases) |

## Trivy Container Scan Baseline (Hardstop 2026-08-30)

Trivy-Findings aus `.github/workflows/docker-image.yml` (`exit-code: "1"`, `ignore-unfixed: true`).
Diese CVEs sind in transitiven Dependencies der Basis-Image-Layer (nicht in Python-Packages per pip-audit).
Fix erfordert Basis-Image-Update; kein Paket-Pin möglich.

| CVE | Quelle | Schweregrad | Fix verfügbar? | Owner | Frist | Status | Blocker |
|---|---|---|---|---|---|---|---|
| CVE-2026-24049 | `wheel` (OS-Layer, transitive) | High | Nein (Base-Image Update erforderlich) | alex | 2026-08-30 | open | Basis-Image in `Dockerfile` |
| CVE-2026-23949 | `jaraco.context` (OS-Layer, transitive) | High | Nein (Base-Image Update erforderlich) | alex | 2026-08-30 | open | Basis-Image in `Dockerfile` |

### Pin-Begruendungen

| Paket | Pinned Version | Upstream-Pin | Erklaerung |
|---|---|---|---|
| `transformers` | `>=5.3.0` | — | Upgrade auf v5 via `tool.uv.override-dependencies` unblocked durch `sentence-transformers>=5.3.0`. Behebt CVE-2026-4372, CVE-2026-1839 und PYSEC-2025-217. |
| `nltk` | `3.9.4` | — (kein Pin) | PYSEC-2026-597 hat keine gefixte Version in der Advisory-DB — Upgrade behebt das Finding derzeit nicht. |

---

## Eskalationspfad (Hardstop 2026-07-30)

Wenn am 2026-07-30 noch CVEs in der aktiven Baseline offen sind, greift einer dieser Pfade:

1. **Upstream released bis dahin** — `--ignore-vuln`-Flags aus [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) entfernen, Issue schließen, Eintrag nach „Abgeschlossen" verschieben.
2. **ADR docs/decisions/0004-cve-upstream-escalation.md** (geplant) entscheidet zwischen:
   - **Vendoring** der betroffenen Subkomponenten,
   - **Soft-Fork** mit Patch-Ringen,
   - **Replacement** durch andere Pakete (z.B. `langgraph` statt `camel-oasis`).
3. **Risikoakzeptanz-PR** mit expliziter Verlängerung der `--ignore-vuln`-Flags um maximal 60 Tage und neuem Hardstop-Datum. Erfordert User-Sign-off.

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
