# Aktuelle Release-Priorität

> Verbindliche Reihenfolge und Freigabekriterien: [ROADMAP](../../ROADMAP.md). Verifizierter Istzustand: [STATUS](../STATUS.md).

**Stand:** 02.10.2026, GitHub-Abgleich gegen `main@4cbf0eb8`. `v0.9.6` ist getaggt; nächster Schnitt ist `0.10.0-rc.1` (Feature-Freeze), danach `0.10.0` stabil, `1.0.0-rc.1`, sieben Tage Soak und `1.0.0` ([#1658](https://github.com/arn0ld87/agora/issues/1658)).

## Nächste Arbeit

1. **Aktuellen Security-Audit schließen:** CI-Run 36898610864 ist bei `pypdf 6.16.1` rot. [PR #1748](https://github.com/arn0ld87/agora/pull/1748) enthält den Fix, ist beim Abgleich aber offen. Nicht doppelt implementieren; finalen Audit-Nachweis prüfen. Gewöhnliche PR-CI führt den Python-Audit nicht aus.
2. **Test-Isolation #1632:** Tests dürfen keine Run-Manifeste im echten `uploads`-/`AGORA_DATA_DIR`-Bestand anlegen.
3. **Weitere Vor-Freeze-Verträge/Gates:** `schema_version` (#1663), Kompatibilitäts-ADR (#1664), Checksummen (#1661), Supabase-Image-Scan/Ausnahmeregister (#1670), Backend-Ratchet (#1671), Frontend-Coverage (#1672).
4. **Operative Abnahme #1592:** produktiver Metadaten-Cutover ist dokumentiert; formale Beobachtungs-/Drill-Nachweise und echter Embedding-Modellwechsel bleiben offen. Hostzugriff ist nötig.

Ein neuer P0 stoppt den RC-Schnitt. Historische Blockerlisten dürfen geschlossene Issues nicht erneut zur Arbeit erklären.

## Bis `0.10.0` stabil

- Eval-Seed-Leakage/Gegenlauf #1240 abschließen und alle erforderlichen Gates am finalen Commit grün nachweisen. Offene P0/P1 im 0.10-Milestone verhindern den stabilen Tag.
- PostgreSQL ist auf armserver produktiv, im Code-Default aber noch Legacy. Der unterstützte 1.0-Install-Pfad soll PostgreSQL und den vollen Supabase-Stack verwenden; Artefakte bleiben Dateien (#1654).
- Zwischen RCs nur Fixes, Tests und Doku, keine neue Feature-/Vertragsarbeit (#1658).

## Im Freeze vor `1.0.0-rc.1`

- **Ops:** Fresh-Host-Install/Restore mit vollem Supabase-Stack, Referenzbestand, Graph, Lauf und Bericht (#766). Upgrade-/Rollback-Werkzeuge und der Cutover ersetzen keinen realen Drill.
- **Produkt:** AURORA mit je einem Lauf gegen Single-Prompt- und statische Persona-Baseline (#1662, M3 aus #1603). Qualitativer Vergleich ohne statistische oder deterministische Ergebniszusage.
- **Doku:** Grenzen/Non-Goals #1674 und RC-Notes; der 0.9.x → 0.10-Upgrade-Sprung ist durch #1673 fertig, der 1.0-Abschnitt wird im Freeze ergänzt.
- Vor dem 1.0-Tag alle P0/P1 schließen; ein neuer P0/P1 setzt den siebentägigen Soak zurück (#1653).

## Geschlossen; Grenzen beibehalten

- Recovery/Resume für Prepare, Report und Graph-Build #1472; Out-of-Process-Worker und Report-Parallelität verbleiben bei #1551 (Rest von #1265).
- Twitter-Recommender #1236, Quantor-Evidence #1345, Confidence-/Claim-Typen #1301/#1400, Domänendrift #1471, Single-Platform-Observation-Gate #1224, Budgets und ehrliche `INCOMPLETE`-Reports.
- Alias-/Entitätsklassen #1470 und Role-Leakage-Markierung #1323: LLM-Koreferenz außerhalb des Scopes, Markieren statt Verwerfen.
- Manifest-/Replay #763/#1274: Prompt-/Input-/Route-Capture und Parameterübernahme umgesetzt; `random_seed=null` ist die Entscheidung, keine offene RNG-Aufgabe. Keine Garantie identischer Modellantworten.
- Neo4j-Backup #1633, Supavisor #1634, Integration-CI #1660, Embedding-SSoT #1417, CodeQL-Triage #1669 und Upgrade-Runbook #1673.

## Nach 1.0

Allgemeiner Multi-User-/Workspace-/Auth-/RLS-/Realtime-Betrieb (ADR-0019), Supabase-Storage-Blobs, volle Kalibrierungssuite #765, Out-of-Process-Worker #1551, SaaS, Kubernetes, Federation und Plugin-System. Die isolierte Bewerbungsdemo ist eine begrenzte Ausnahme nach ADR-0020.
