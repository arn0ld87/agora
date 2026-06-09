# Dependency Risk Register

**Stand:** 2026-06-09, Europe/Berlin
**Ausgeloest durch:** Repo-Review PR4 — CVE-Baseline aktiv abbauen.
Automation: [.github/workflows/cve-monitor.yml](../.github/workflows/cve-monitor.yml) läuft wöchentlich Mo 06:00 UTC pip-audit --strict ohne --ignore-vuln und schreibt das Ergebnis in das Workflow-Summary. Hardstop am 2026-07-30 — danach failt der Job, wenn ignored CVEs noch offen sind.
Supply-Chain-Baseline: [.github/workflows/scorecard.yml](../.github/workflows/scorecard.yml) läuft wöchentlich Mo 04:30 UTC und auf `push` nach `main`. SARIF-Ergebnisse werden ins Code-Scanning-Dashboard hochgeladen; der erste Remote-Run nach Merge ist die Scorecard-Baseline.

Dieses Dokument trackt bewusst ignorierte `pip-audit`-Findings und Trivy-Container-Scans.
Jedes Ignored-CVE hat ein GitHub-Issue, eine Frist und einen Owner. Neue Findings duerfen
nicht hinzugefuegt werden ohne dass sie zuerst als Issue aufgenommen werden.
Die hier gelisteten CVEs sind auch in der `.trivyignore`-Datei im Root-Verzeichnis
hinterlegt, um den Container-Scan nicht zu blockieren.

---

## Aktive Baseline (Hardstop 2026-07-30)

| CVE | Paket | Schweregrad | Fix verfügbar? | Owner | Frist | Status | Issue | Upstream-Release-Watch |
|---|---|---|---|---|---|---|---|---|
| CVE-2026-1839 | `transformers` | Medium | Nein (Upstream Pin) | sentence-transformers | 2026-07-30 | open | [#124](https://github.com/arn0ld87/agora/issues/124) | [UKPLab/sentence-transformers/releases](https://github.com/UKPLab/sentence-transformers/releases) |
| PYSEC-2026-139 | `torch` | unbekannt | Nein (kein Upstream-Fix released) | sentence-transformers | 2026-07-30 | open | [#623](https://github.com/arn0ld87/agora/issues/623) | [pytorch/pytorch/releases](https://github.com/pytorch/pytorch/releases) |
| PYSEC-2025-217 | `transformers` | unbekannt | Nein (kein Upstream-Fix released) | sentence-transformers | 2026-07-30 | open | [#624](https://github.com/arn0ld87/agora/issues/624) | [huggingface/transformers/releases](https://github.com/huggingface/transformers/releases) |

### Pin-Begruendungen

| Paket | Pinned Version | Upstream-Pin | Erklaerung |
|---|---|---|---|
| `transformers` | `4.57.6` | `sentence-transformers==4.1.0` (via `camel-oasis==0.2.5`) | `sentence-transformers` limitiert `transformers<5`; für PYSEC-2025-217 existiert zudem keine gefixte Version in der Advisory-DB. |
| `torch` | `2.9.1` | `sentence-transformers==4.1.0` (via `camel-oasis==0.2.5`) | PYSEC-2026-139 hat keine gefixte Version in der Advisory-DB — Upgrade behebt das Finding derzeit nicht. |

---

## Eskalationspfad (Hardstop 2026-07-30)

Wenn am 2026-07-30 noch CVEs in der aktiven Baseline offen sind, greift einer dieser Pfade:

1. **Upstream released bis dahin** — `--ignore-vuln`-Flags aus [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) entfernen, Issue schließen, Eintrag nach „Abgeschlossen" verschieben.
2. [ADR docs/decisions/0002-cve-upstream-escalation.md](decisions/0002-cve-upstream-escalation.md) entscheidet zwischen:
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
| CVE-2026-25990 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #121 schließen. | 2026-05-15 |
| CVE-2026-40192 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #122 schließen. | 2026-05-15 |
| CVE-2026-42308 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #296 schließen. | 2026-05-15 |
| CVE-2026-42310 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #297 schließen. | 2026-05-15 |
| CVE-2026-42311 | `pillow` | Resolved via `tool.uv.override-dependencies`: `pillow==12.2.0` installiert (verified via `uv export`). `--ignore-vuln`-Flag aus CI entfernt. Issues #298 schließen. | 2026-05-15 |
| CVE-2025-71176 | `pytest` | Resolved via `tool.uv.override-dependencies`: `pytest==9.0.3` installiert (verified via `uv run pytest --version`). `--ignore-vuln`-Flag aus CI entfernt. Issues #123 schließen. | 2026-05-19 |
| CVE-2024-46455 | `unstructured` | Resolved via `tool.uv.override-dependencies`: `unstructured>=0.18.18` installiert (verified via `uv run pip-audit`). `--ignore-vuln`-Flag aus CI entfernt. Issues #125 schließen. | 2026-05-19 |
| CVE-2025-64712 | `unstructured` | Resolved via `tool.uv.override-dependencies`: `unstructured>=0.18.18` installiert (verified via `uv run pip-audit`). `--ignore-vuln`-Flag aus CI entfernt. Issues #126 schließen. | 2026-05-19 |
