# Agora Roadmap

**Stand:** 08.09.2026  
**Aktuelle Produktversion:** `0.9.5` Stability Beta  
**Istzustand:** [`docs/STATUS.md`](docs/STATUS.md)

Diese Datei beschreibt ausschließlich die **strategische Release-Reihenfolge**. Konkrete Arbeitspakete, Akzeptanzkriterien und Fortschritt werden als GitHub Issues gepflegt. Ein erledigter Commit gehört nicht als Mini-Changelog hier hinein; dafür existiert `changelog.d/`. Offenbar braucht selbst Dokumentation eine Gewaltenteilung.

## Verbindliche Dokumentationshierarchie

| Ebene | Aufgabe |
|---|---|
| [`README.md`](README.md) / [`README.de.md`](README.de.md) | Produkt, Einstieg, Grenzen, Schnellstart |
| [`docs/STATUS.md`](docs/STATUS.md) | verifizierter Istzustand |
| `ROADMAP.md` | Release-Ziele und Reihenfolge |
| [GitHub Issues](https://github.com/arn0ld87/agora/issues) | ausführbare Tasks und Abnahme |

ADRs, Architektur-, Security- und Runbook-Dokumente bleiben verbindliche Referenzen. Historische Planungsstände und Audits sind keine aktive Steuerungsquelle.

---

## Produktziel

Agora soll eine stabile, lokal oder kontrolliert hybrid betreibbare **Single-User-Plattform für evidenzorientierte Stakeholder-, Risiko- und Szenarioanalyse** werden.

Der Weg zu `1.0.0` folgt vier Regeln:

1. Stabilität und Trust vor neuen großen Produktflächen.
2. Eine kanonische Oberfläche sowie eine kanonische Provider-/Secret-/Routing-Wahrheit.
3. Reproduzierbarkeit und messbarer Erkenntnisgewinn vor Plattformausbau.
4. Kein Multi-User-/SaaS-/Kubernetes-Ausbau vor einem belastbaren Single-User-1.0.

---

# 0.9.x — Stability Beta

## Status

`0.9.5` besitzt die vollständige fachliche Pipeline und eine weitgehend konsolidierte Produktoberfläche. Die September-Stabilisierung hat unter anderem folgende Fehlerklassen geschlossen:

- Persona-Routing für CLI-Provider und Codex-CLI-Transport in OASIS (#1418/#1422, #1423/#1424)
- idempotente Neo4j-Writes bei Retry-after-commit (#1460)
- harte LLM-Call-Reservierung bei paralleler Persona-Erzeugung (#1461)
- korrekter Nutzer-Stop und Force-Restart-Monitoring (#1474)
- crash-konsistente Report-Sektionspersistenz (#1475)
- Startup-Reconciliation stale Simulationsläufe (#1476)
- Evidence-Envelope und Backend/Frontend-Contract-Parität (#1477/#1482)
- Budget-Guard/Ledger für Tool-, Vision- und Interview-Pfade (#1478)
- ehrliche `INCOMPLETE`-Teilberichte inklusive Resume-Semantik (#1479)
- echte Redis-/Neo4j-Integrationstests (#1481)
- Fresh-Install-Secret-Erzeugung und korrigierte Backup-Pfade (#1483)

## Was 0.9.x **noch nicht** behauptet

- vollständige Run-Reproduzierbarkeit
- wissenschaftlich validierte Verhaltensprognosen
- vollständig restart-sichere Prepare-/Report-/Graph-Jobs
- vollständig kanonische Embedding-Runtime-Konfiguration
- Multi-User-/SaaS-Betrieb

Die verbleibenden Punkte werden nicht durch weitere 0.9-Featureflächen verdeckt, sondern bilden den Übergang zu 0.10.

---

# 0.10.0 — Release Candidate

## Ziel

Agora soll nicht nur technisch funktionieren, sondern Ergebnisse **reproduzierbar beschreiben, budgetierbar ausführen, nach Abstürzen ehrlich fortsetzen bzw. beenden und evidenzseitig überprüfbar ausliefern**.

## P0 — Prozess- und Konfigurationswahrheit

- [ ] **Langlaufende Webprozess-Jobs restart-sicher:** Prepare, Report und Graph-Build dürfen bei SIGTERM nicht ohne persistierten Interrupted-/Resume-Zustand verschwinden ([#1472](https://github.com/arn0ld87/agora/issues/1472)).
- [ ] **Embedding-Runtime-SSoT:** aktive Embedding-Konfiguration aus Store/Connection/Secret-Store muss den produktiven Runtime-Pfad steuern; `.env` nur noch Legacy/Bootstrap-Fallback ([#1417](https://github.com/arn0ld87/agora/issues/1417)).
- [ ] **Budget vollständig über alle produktiven Pfade:** der separate `ParallelIPCHandler` des Default-Parallelrunners muss dieselbe Report-Budget-Attribution wie der normale IPC-Pfad erhalten (Follow-up zu #1478).
- [ ] **Report-Parallelität ohne Ein-Worker-Blockade:** entweder bewusst serialisieren oder Reportarbeit aus dem gevent-Webworker in einen eigenen Prozess/Worker verschieben ([#1265](https://github.com/arn0ld87/agora/issues/1265)).

## P0/P1 — Simulationstreue und Trust

- [ ] Alias-/Koreferenzauflösung und kontrollierte semantische Entitätsklasse vor Persona-Cap ([#1470](https://github.com/arn0ld87/agora/issues/1470)).
- [ ] Persona-Domänendrift zuverlässig erkennen, auch wenn nur eine Nebendomäne mit der Quelle überlappt ([#1471](https://github.com/arn0ld87/agora/issues/1471)).
- [ ] Role Leakage in texttragenden Simulationsaktionen messen und begrenzen ([#1323](https://github.com/arn0ld87/agora/issues/1323)).
- [ ] Twitter-Recommender nicht mehr auf untrainierten/neu initialisierten Pooler-Gewichten ranken lassen; identische Seed-Läufe müssen reproduzierbare Ranking-Matrizen liefern ([#1236](https://github.com/arn0ld87/agora/issues/1236)).
- [ ] Quantifizierte Claims nur dann als supported behandeln, wenn aggregierte Evidence die Quantorstärke trägt ([#1345](https://github.com/arn0ld87/agora/issues/1345)).
- [ ] Evaluation-Seeds von Erwartungs-/Lösungstext trennen und Evidence-Herkunft typisieren ([#1240](https://github.com/arn0ld87/agora/issues/1240)).
- [ ] Claim-Typen/Confidence-Kalibrierung abschließen (#1301/#1400).

## P1 — Reproduzierbare Runs

Parent: [#763](https://github.com/arn0ld87/agora/issues/763), Detail-Lücken: [#1274](https://github.com/arn0ld87/agora/issues/1274).

- [ ] rohen Input-Hash und Dateiname im Manifest speichern
- [ ] Prompt-Snapshots bytegenau erfassen
- [ ] echten Runtime-RNG-Seed speichern **und tatsächlich in die Simulation verdrahten**
- [ ] Provider, Modell, Route, Graph-/Embedding-Version und relevante Feature Flags einfrieren
- [ ] Replay übernimmt alle reproduzierbaren Originalparameter
- [ ] Varianten-Replay zeigt jede Abweichung explizit
- [ ] Legacy-Manifeste verwenden ehrliche `null`/`unknown`-Werte statt scheinbarer Daten
- [ ] Export besitzt eine Secret-Allowlist/Regressionstest

**Wichtig:** Der heutige `random_seed`-Eintrag allein ist **kein Nachweis eines reproduzierbaren Runs**. Solange der gespeicherte Wert nicht die tatsächlichen Zufallsquellen und alle relevanten Inputs kontrolliert, ist „same seed = same experiment“ eine zu starke Aussage.

## P1 — Betrieb und Release-Nachweis

Parent: [#766](https://github.com/arn0ld87/agora/issues/766).

- [ ] vollständiges Backup eines Referenzprojekts auf frischem Host wiederherstellen
- [ ] Graph, Runs, Reports, Provider-Konfiguration und verschlüsselte Secrets nach Restore prüfen
- [ ] Upgrade von unterstützter 0.9.x-Version auf 0.10.0 dokumentiert und durchgeführt
- [ ] Rollback nach absichtlich fehlgeschlagener Migration nachweisen
- [ ] frischen Docker- und Host-Installationspfad reproduzieren
- [ ] Release-Artefakte, Checksummen und SBOM erzeugen

`install.sh` und die Backup-Dokumentation sind inzwischen erheblich besser, aber **Dokumentation ist noch kein Restore-Nachweis**.

## P1 — Produktnachweis

Parent: [#765](https://github.com/arn0ld87/agora/issues/765).

Mindestens drei veröffentlichbare Referenzfälle sollen vergleichen:

1. einen guten Single-Prompt-Baseline-Ansatz,
2. eine einfache statische Persona-Liste,
3. den vollständigen Agora-Lauf,
4. soweit möglich reale Interviews, Reviews oder historische Referenzreaktionen.

Zu messen sind mindestens Treffer, Fehlannahmen, Abdeckung, Varianz, Kosten und Laufzeit. Negative Ergebnisse werden mitveröffentlicht.

## Feature-Freeze

Mit dem ersten `0.10.0`-Release-Candidate beginnt der Feature-Freeze. Danach werden bis `1.0.0` nur Fehler, Dokumentation, Migrationen, Security, Evaluation und nachgewiesene Release-Blocker bearbeitet.

---

# 1.0.0 — Stable Single-User Release

Parent-Gate: [#767](https://github.com/arn0ld87/agora/issues/767).

`1.0.0` bedeutet nicht „alles denkbare eingebaut“, sondern: Der definierte Single-User-Anwendungsbereich ist stabil, nachvollziehbar und operativ wiederherstellbar.

## Freigabekriterien

- [ ] versionierte API-, Report-, Run- und Persistenzverträge
- [ ] dokumentierte Kompatibilitäts- und Deprecation-Regeln
- [ ] Migrationen mit Test-, Resume- und Rollback-Pfaden
- [ ] genau eine produktive Oberfläche
- [ ] genau eine kanonische Provider-/Secret-/Routing-Architektur
- [ ] vollständig grüne erforderliche Backend-/Frontend-/Schema-/Security-/E2E-Gates
- [ ] keine offenen P0/P1-Release-Blocker
- [ ] keine ungeklärten Critical/High-Security-Findings ohne dokumentierte Ausnahme
- [ ] Fresh-Install, Backup, Restore, Upgrade und Rollback nachgewiesen
- [ ] Release-Artefakte, Checksummen und SBOM vorhanden
- [ ] mindestens ein öffentlich nachvollziehbarer, reproduzierbarer Referenzlauf
- [ ] dokumentierter Vergleich mit mindestens einer einfacheren LLM-Baseline
- [ ] sichtbare Grenzen und Non-Goals
- [ ] Feature-Freeze seit 0.10-RC
- [ ] finaler RC mindestens sieben Tage ohne neuen P0/P1-Blocker

---

## Nach 1.0.0

Erst danach werden größere Ausbaupfade neu bewertet:

- Team-/Rollenmodell und Multi-User
- Plugin-System
- Kubernetes/Helm
- Federation
- zusätzliche Branchen-/Analysepakete
- optionale gehostete Betriebsmodelle

Diese Punkte sind **keine Zusagen für 1.0.0**.

## Pflege dieser Roadmap

- Kleintasks und Abnahmekriterien gehören in Issues.
- Ausgelieferte Änderungen gehören als Fragment nach [`changelog.d/`](changelog.d/README.md).
- Der tatsächliche Iststand gehört in [`docs/STATUS.md`](docs/STATUS.md).
- Historische Planung wird nicht an diese Datei angehängt.
