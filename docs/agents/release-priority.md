# Aktuelle Release-Priorität

> Kompakte Orientierung für Agenten. Die verbindliche Reihenfolge und Freigabekriterien stehen in [`../../ROADMAP.md`](../../ROADMAP.md); der verifizierte Istzustand in [`../STATUS.md`](../STATUS.md).

**Stand:** 26.09.2026. `v0.9.6` ist getaggt; nächster Schnitt ist `0.10.0-rc.1` (Feature-Freeze), danach `0.10.0` stabil, `1.0.0-rc.1`, sieben Tage Soak und `1.0.0` ([#1658](https://github.com/arn0ld87/agora/issues/1658)).

## Vor `0.10.0-rc.1`

1. **P0 zuerst:** Neo4j-Backup im Restore-Drill reparieren (#1633). Ein neuer P0 stoppt den RC-Schnitt sofort.
2. **Verhalten und Verträge vor dem Freeze:** `schema_version` (#1663), Kompatibilitäts-ADR (#1664), Cutover-Nachweise (#1592), Checksummen (#1661), Alias-/Koreferenz-Rest (#1470), Role-Leakage-Rest (#1323) und Test-Isolation (#1632).
3. **Release-Gates vor dem Freeze:** Supabase-Image-Scan/Ausnahmeregister (#1670), Backend-Ratchet (#1671), Frontend-Coverage (#1672) und Upgrade-Runbook (#1673).

## Bis `0.10.0` stabil

- P1-Fixes: rote Integration-CI (#1660), Supavisor-Start (#1634), Embedding-Runtime-SSoT (#1417), Eval-Seed-Leakage (#1240), echte Manifest-/Replay-Werte (#1274) und CodeQL-High-Triage (#1669). Offene P0/P1 im 0.10-Milestone verhindern den stabilen Tag.
- PostgreSQL ist auf armserver seit #1592 produktive Metadaten-Ablage, im Code-Default aber noch nicht. Für den unterstützten 1.0-Install-Pfad muss PostgreSQL kanonisch werden; der volle Supabase-Stack gehört dazu, Artefakte bleiben im Dateisystem ([#1654](https://github.com/arn0ld87/agora/issues/1654)).
- Zwischen RCs nur Fixes, Tests und Doku. Keine neue Feature- oder Vertragsarbeit ([#1658](https://github.com/arn0ld87/agora/issues/1658)).

## Im Freeze vor `1.0.0-rc.1`

- **Ops:** ein Fresh-Host-Install/Restore mit vollem Supabase-Stack, Referenzbestand, Graph, Lauf und Bericht (#766). Upgrade und Rollback werden über das CI-Gate #1589 und den realen Cutover #1592 belegt; ein trockenes Runbook ersetzt den Drill nicht ([#1659](https://github.com/arn0ld87/agora/issues/1659)).
- **Produkt:** AURORA mit je einem Lauf gegen Single-Prompt- und statische Persona-Baseline veröffentlichen (#1662, M3 aus #1603). Nachvollziehbarer qualitativer Vergleich, keine statistische Aussage und keine identische Ausgabe bei gleichem Seed ([#1656](https://github.com/arn0ld87/agora/issues/1656)).
- **Doku:** Grenzen und Non-Goals sichtbar machen (#1674), RC-Notes und Upgrade-Hinweise nach #1673. Vor dem 1.0-Tag müssen alle P0/P1 geschlossen sein; ein neuer P0/P1 setzt den siebentägigen Soak zurück ([#1653](https://github.com/arn0ld87/agora/issues/1653)).

## Bereits geschlossen / nicht wieder öffnen

- Restart-Recovery/Resume für Prepare, Report und Graph-Build (#1472); Out-of-Process-Worker bleibt #1551.
- Report-Parallelitätsproblem #1265 wurde an #1551 übergeben; Parallelität verschiedener Reports ist damit noch nicht bewiesen.
- Twitter-Recommender (#1236), Quantor-Evidence (#1345), Confidence/Claim-Typen (#1301/#1400), Hauptdomänen-Drift (#1471) und Single-Platform-Observation-Gate (#1224).
- Manifest-/Replay-Grundlage #763; die Reproduzierbarkeitslücken stehen ausschließlich in #1274.
- Budgets, Startup-Reconciliation und ehrliche `INCOMPLETE`-Reports (#1461/#1476/#1478/#1479).

## Nach 1.0

Multi-User/Workspaces/Auth/RLS/Realtime (ADR-0019), Supabase-Storage-Blobs, volle Kalibrierungs- und Baseline-Suite (#765), Out-of-Process-Worker (#1551), SaaS, Kubernetes, Federation und Plugin-System.

Details und Abnahme: [`../../ROADMAP.md`](../../ROADMAP.md), Istzustand: [`../STATUS.md`](../STATUS.md).
