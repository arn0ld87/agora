# Dependency Risk Register

**Stand:** 2026-05-01, Europe/Berlin
**Ausgeloest durch:** Repo-Review PR4 — CVE-Baseline aktiv abbauen.

Dieses Dokument trackt bewusst ignorierte `pip-audit`-Findings. Jedes Ignored-
CVE hat ein GitHub-Issue, eine Frist und einen Owner. Neue Findings duerfen
nicht hinzugefuegt werden ohne dass sie zuerst als Issue aufgenommen werden.

---

## Aktive Baseline

| CVE | Paket | Version | Owner | Frist | Status | Issue |
|---|---|---|---|---|---|---|
| CVE-2026-25990 | `pillow` | `10.3.0` | camel-ai | 2026-07-30 | open | #121 |
| CVE-2026-40192 | `pillow` | `10.3.0` | camel-ai | 2026-07-30 | open | #122 |
| CVE-2025-71176 | `pytest` | `8.2.0` | camel-oasis | 2026-07-30 | open | #123 |
| CVE-2026-1839 | `transformers` | `4.57.6` | sentence-transformers | 2026-07-30 | open | #124 |
| CVE-2024-46455 | `unstructured` | `0.13.7` | camel-oasis | 2026-07-30 | open | #125 |
| CVE-2025-64712 | `unstructured` | `0.13.7` | camel-oasis | 2026-07-30 | open | #126 |

### Pin-Begruendungen

| Paket | Pinned Version | Upstream-Pin | Erklaerung |
|---|---|---|---|
| `pillow` | `10.3.0` | `camel-ai==0.2.78` | `camel-ai` limitiert `pillow<11`. |
| `pytest` | `8.2.0` | `camel-oasis==0.2.5` | `camel-oasis` pinnt `pytest==8.2.0`. |
| `transformers` | `4.57.6` | `sentence-transformers==3.0.0` | `sentence-transformers` limitiert `transformers<5`. |
| `unstructured` | `0.13.7` | `camel-oasis==0.2.5` | `camel-oasis` pinnt `unstructured==0.13.7`. |

---

## Prozess

1. **Neues Finding:** `pip-audit` oder `npm audit` meldet eine Advisory.
2. **Pruefung:** Ist das Finding durch einen Upstream-Pin blockiert?
   - **Ja:** Issue erstellen (Titel: `security: track ignored <CVE> until
     upstream fix`), ins Register eintragen, Frist +90 Tage.
   - **Nein:** Sofort fixen, kein Register-Eintrag noetig.
3. **Review:** Alle 30 Tage Register-Inventur. Abgelaufene Fristen → P0
   Bug-Ticket.
4. **Abschluss:** Wenn upstream released und Dependency geupdated, Issue
   schliessen, Register-Eintrag nach `Abgeschlossen` verschieben.

---

## Abgeschlossen

| CVE | Paket | Aufloesung | Datum |
|---|---|---|---|
| — | — | — | — |
