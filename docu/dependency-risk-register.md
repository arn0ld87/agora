# Dependency Risk Register

**Stand:** 2026-05-04, Europe/Berlin
**Ausgeloest durch:** Repo-Review PR4 — CVE-Baseline aktiv abbauen.
Automation: [.github/workflows/cve-monitor.yml](../.github/workflows/cve-monitor.yml) läuft wöchentlich Mo 06:00 UTC pip-audit --strict ohne --ignore-vuln und schreibt das Ergebnis in das Workflow-Summary. Hardstop am 2026-07-30 — danach failt der Job, wenn ignored CVEs noch offen sind.

Dieses Dokument trackt bewusst ignorierte `pip-audit`-Findings. Jedes Ignored-
CVE hat ein GitHub-Issue, eine Frist und einen Owner. Neue Findings duerfen
nicht hinzugefuegt werden ohne dass sie zuerst als Issue aufgenommen werden.

---

## Aktive Baseline (Hardstop 2026-07-30)

| CVE | Paket | Version | Owner | Frist | Status | Issue | Upstream-Release-Watch |
|---|---|---|---|---|---|---|---|
| CVE-2026-25990 | `pillow` | `10.3.0` | camel-ai | 2026-07-30 | open | [#121](https://github.com/arn0ld87/agora/issues/121) | [camel-ai/releases](https://github.com/camel-ai/camel/releases) |
| CVE-2026-40192 | `pillow` | `10.3.0` | camel-ai | 2026-07-30 | open | [#122](https://github.com/arn0ld87/agora/issues/122) | [camel-ai/releases](https://github.com/camel-ai/camel/releases) |
| CVE-2025-71176 | `pytest` | `8.2.0` | camel-oasis | 2026-07-30 | open | [#123](https://github.com/arn0ld87/agora/issues/123) | [camel-ai/oasis/releases](https://github.com/camel-ai/oasis/releases) |
| CVE-2026-1839 | `transformers` | `4.57.6` | sentence-transformers | 2026-07-30 | open | [#124](https://github.com/arn0ld87/agora/issues/124) | [UKPLab/sentence-transformers/releases](https://github.com/UKPLab/sentence-transformers/releases) |
| CVE-2024-46455 | `unstructured` | `0.13.7` | camel-oasis | 2026-07-30 | open | [#125](https://github.com/arn0ld87/agora/issues/125) | [camel-ai/oasis/releases](https://github.com/camel-ai/oasis/releases) |
| CVE-2025-64712 | `unstructured` | `0.13.7` | camel-oasis | 2026-07-30 | open | [#126](https://github.com/arn0ld87/agora/issues/126) | [camel-ai/oasis/releases](https://github.com/camel-ai/oasis/releases) |

### Pin-Begruendungen

| Paket | Pinned Version | Upstream-Pin | Erklaerung |
|---|---|---|---|
| `pillow` | `10.3.0` | `camel-ai==0.2.78` | `camel-ai` limitiert `pillow<11`. |
| `pytest` | `8.2.0` | `camel-oasis==0.2.5` | `camel-oasis` pinnt `pytest==8.2.0`. |
| `transformers` | `4.57.6` | `sentence-transformers==3.0.0` | `sentence-transformers` limitiert `transformers<5`. |
| `unstructured` | `0.13.7` | `camel-oasis==0.2.5` | `camel-oasis` pinnt `unstructured==0.13.7`. |

---

## Eskalationspfad (Hardstop 2026-07-30)

Wenn am 2026-07-30 noch CVEs in der aktiven Baseline offen sind, greift einer dieser Pfade:

1. **Upstream released bis dahin** — `--ignore-vuln`-Flags aus [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) entfernen, Issue schließen, Eintrag nach „Abgeschlossen" verschieben.
2. [ADR docu/decisions/0002-cve-upstream-escalation.md](decisions/0002-cve-upstream-escalation.md) entscheidet zwischen:
   - **Vendoring** der betroffenen Subkomponenten,
   - **Soft-Fork** mit Patch-Ringen,
   - **Replacement** durch andere Pakete (z.B. `langgraph` statt `camel-oasis`).
3. **Risikoakzeptanz-PR** mit expliziter Verlängerung der `--ignore-vuln`-Flags um maximal 60 Tage und neuem Hardstop-Datum. Erfordert User-Sign-off.

Der CVE-Monitor-Workflow erzwingt die Entscheidung: ab Hardstop-Datum schlägt er bei jedem Run fehl, bis eine der drei Optionen umgesetzt ist.

## Prozess

1. **Neues Finding:** `pip-audit` oder `npm audit` meldet eine Advisory. Der wöchentliche CVE-Monitor entdeckt neue Findings automatisch.
2. **Pruefung:** Ist das Finding durch einen Upstream-Pin blockiert?
   - **Ja:** Issue erstellen (Titel: `security: track ignored <CVE> until
     upstream fix`), ins Register eintragen, Frist +90 Tage, in `ci.yml` `--ignore-vuln`-Flag ergänzen.
   - **Nein:** Sofort fixen, kein Register-Eintrag noetig.
3. **Wöchentliche Sichtung:** [CVE-Monitor-Workflow](../.github/workflows/cve-monitor.yml) → Workflow-Summary lesen. Wenn ein CVE aus der Baseline verschwindet, ist Upstream gepatcht.
4. **30-Tage-Inventur:** Register-Inventur. Abgelaufene Fristen → P0 Bug-Ticket.
5. **Abschluss:** Wenn upstream released und Dependency geupdated, Issue
   schliessen, Register-Eintrag nach `Abgeschlossen` verschieben, `--ignore-vuln`-Flag aus `ci.yml` entfernen.

---

## Abgeschlossen

| CVE | Paket | Aufloesung | Datum |
|---|---|---|---|
| — | — | — | — |
