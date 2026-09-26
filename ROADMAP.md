# Agora Roadmap

**Stand:** 26.09.2026

**Geprüfte Main-Baseline:** `cde0919f6`

**Aktuelle Produktversion:** `0.9.6` (getaggt, Stability Beta) — nächster Schnitt `0.10.0-rc.1`
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

Agora soll eine stabile, lokal oder kontrolliert hybrid betreibbare **Plattform für evidenzorientierte Stakeholder-, Risiko- und Szenarioanalyse** werden — für Einzelnutzer. Mehrere Nutzer in getrennten Workspaces folgen nach 1.0 ([ADR-0019](docs/decisions/0019-multi-user-after-1-0.md)).

Der Weg zu `1.0.0` folgt vier Regeln:

1. Stabilität und Trust vor neuen großen Produktflächen.
2. Eine kanonische Oberfläche sowie eine kanonische Provider-/Secret-/Routing-Wahrheit.
3. Reproduzierbarkeit und messbarer Erkenntnisgewinn vor Plattformausbau.
4. Kein Multi-User-/SaaS-/Kubernetes-Ausbau vor 1.0. Multi-User mit Workspaces, Supabase Auth und RLS folgt nach 1.0 ([ADR-0019](docs/decisions/0019-multi-user-after-1-0.md), Epic [#1610](https://github.com/arn0ld87/agora/issues/1610)); der bereits gemergte Code bleibt per Default inaktiv.

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
- prozessgetrennte Jobausführung und Resume der OASIS-Simulation
- vollständig kanonische Embedding-Runtime-Konfiguration
- Multi-User-/SaaS-Betrieb

Die verbleibenden Punkte werden nicht durch weitere 0.9-Featureflächen verdeckt, sondern bilden den Übergang zu 0.10.

---

## 0.9.6 — Zwischenrelease

`0.9.6` liegt zwischen `0.9.5` (11.08.2026) und `0.10.0` und enthält mehr als 330 Commits sowie 184 Changelog-Fragmente seit `v0.9.5`. Es ist ausdrücklich **kein** `0.10.0` und erfüllt dessen Release-Gates (siehe unten) nicht — Feature-Freeze beginnt erst mit dem ersten `0.10.0`-RC.

### Was `0.9.6` enthält

- **Vier LLM-Provider** inklusive der beiden neuen CLI-/Session-Transporte `codex_cli` (ChatGPT-Abo, #1406/#1423/#1424) und `claude_cli` (Claude-Abo statt Pay-per-Token-API, #1531) sowie Amazon Bedrock als OpenAI-kompatibler Provider (#1282).
- **PostgreSQL-Schicht zum Zeitpunkt des Tags parallel zu JSON-/SQLite-Stores**: Supabase-Compose als eigene Infrastruktur (#1504), SQLAlchemy-/Alembic-Grundlage (#1505) und Repository-Adapter (ADR-0014). Seit dem Tag sind auf armserver alle fünf Metadaten-Domänen produktiv auf PostgreSQL umgeschaltet; die Code-Defaults bleiben Legacy und müssen für den unterstützten 1.0-Install-Pfad angeglichen werden ([#1592](https://github.com/arn0ld87/agora/issues/1592), [#1654](https://github.com/arn0ld87/agora/issues/1654)). Details in [`docs/STATUS.md`](docs/STATUS.md).
- **UI-Redesign über zehn PRs** (#1427–#1449) plus Nachlese (#1459): Design-Tokens, Shell-Chrome, Ablage, Controls, Report-Leseumgebung, Simulations-Vollbildansicht, Runs-Tabelle, Settings-Overlay, Löschen unerreichbarer Legacy-Views.
- **Run-Manifest und Replay** (#1273): atomar geschriebene Manifeste, kanonischer `AiModelRef` im Replay-Override, strukturierte Fehler-Envelopes. Das ist eine Manifest-/Replay-**Grundlage**, keine Reproduzierbarkeits-**Garantie** — siehe P1 „Reproduzierbare Runs" unten und [`docs/agents/release-priority.md`](docs/agents/release-priority.md).
- **Evidence- und Report-Härtung**: satzgenaue Fließtext-Faktenprüfung statt satzweiter Bündelung (#1492), Budget-Guard/Ledger für Tool-, Vision- und Interview-Pfade inklusive `ParallelIPCHandler` (#1478/#1527), SIGTERM-Terminalisierung für In-Process-Jobs (Slice 1.1 aus #1472), Embedding-Index-Auflösung und korruptionssicherer Cutover (#1417, Slices 2.1/2.2), Restore-Drill mit Zielschutz und Migrationsbaseline (#1514).

### Was `0.9.6` nicht behauptet

Der Tag `v0.9.6` erfüllt die 0.10-/1.0-Gates nicht. Nach dem Tag geschlossene Slices stehen unten als erledigt; die offenen Freigabekriterien bleiben in [`docs/STATUS.md`](docs/STATUS.md) und [`docs/agents/release-priority.md`](docs/agents/release-priority.md) sichtbar.

---

# 0.10.0 — Release Candidate

## Ziel

Agora soll nicht nur technisch funktionieren, sondern Ergebnisse **reproduzierbar beschreiben, budgetierbar ausführen, nach Abstürzen ehrlich fortsetzen bzw. beenden und evidenzseitig überprüfbar ausliefern**.

## Release-Sequenz

`v0.9.6` ist getaggt. Der beschlossene Weg ([#1651](https://github.com/arn0ld87/agora/issues/1651), [#1658](https://github.com/arn0ld87/agora/issues/1658)) lautet:

1. `0.10.0-rc.1`: Feature-Freeze, sobald der P0-Blocker geschlossen und alle verhaltens- oder vertragsändernden Nicht-Bugs gelandet sind.
2. Weitere `0.10.0-rc.N`: nur Fixes, Tests und Dokumentation. `0.10.0` stabil erst ohne offene P0/P1 im 0.10-Milestone; es ist die Upgrade-Quelle für 1.0.
3. Freeze-Phase: Ops-, Produkt- und Release-Nachweise abschließen; dann `1.0.0-rc.1` schneiden.
4. Sieben Tage Soak ohne neuen P0/P1-Blocker; ein neuer P0/P1 verlangt Fix, neuen RC und einen neuen Soak. Danach `1.0.0`.

## Geschlossene Slices, nicht erneut als offene Arbeit planen

- [x] Restart-Recovery und explizites Resume für Prepare, Report und Graph-Build ([#1472](https://github.com/arn0ld87/agora/issues/1472)); prozessgetrennte Worker und Simulation-Resume bleiben eigene Arbeit.
- [x] Report-Parallelitätsproblem abgegrenzt und Restarbeit an [#1551](https://github.com/arn0ld87/agora/issues/1551) übergeben ([#1265](https://github.com/arn0ld87/agora/issues/1265)); damit ist eine parallele Ausführung verschiedener Reports noch nicht nachgewiesen.
- [x] Twitter-Recommender ohne zufällig initialisierten Pooler ([#1236](https://github.com/arn0ld87/agora/issues/1236)).
- [x] Quantor-gestützte Evidence-Prüfung ([#1345](https://github.com/arn0ld87/agora/issues/1345)).
- [x] Single-Source-Confidence und Claim-Typen ([#1301](https://github.com/arn0ld87/agora/issues/1301), [#1400](https://github.com/arn0ld87/agora/issues/1400)).
- [x] Manifest-/Replay-Grundlage ([#763](https://github.com/arn0ld87/agora/issues/763)); echte Reproduzierbarkeitslücken bleiben in [#1274](https://github.com/arn0ld87/agora/issues/1274).
- [x] Observation im Single-Platform-Tool-Loop als untrusted Input behandeln ([#1224](https://github.com/arn0ld87/agora/issues/1224)); native OASIS-Fallbacks sind damit nicht pauschal abgedeckt.
- [x] Hauptdomänen-Drift erkennen und korrigieren ([#1471](https://github.com/arn0ld87/agora/issues/1471)).

## Vor `0.10.0-rc.1` — Feature-Freeze

- [ ] **P0:** Neo4j-Backup im Restore-Drill reparieren ([#1633](https://github.com/arn0ld87/agora/issues/1633)).
- [ ] **Verträge und Persistenz:** `schema_version` für Dateiartefakte ([#1663](https://github.com/arn0ld87/agora/issues/1663)), Kompatibilitäts-/Deprecation-Policy ([#1664](https://github.com/arn0ld87/agora/issues/1664)), Cutover-Nachweise ([#1592](https://github.com/arn0ld87/agora/issues/1592)) und Release-Checksummen ([#1661](https://github.com/arn0ld87/agora/issues/1661)).
- [ ] **Trust und Testbarkeit:** Alias-/Koreferenz-Rest ([#1470](https://github.com/arn0ld87/agora/issues/1470)), Role-Leakage-Rest ([#1323](https://github.com/arn0ld87/agora/issues/1323)) und Test-Isolation ([#1632](https://github.com/arn0ld87/agora/issues/1632)).
- [ ] **Release-Gates:** Supabase-Image-Scan und Ausnahmeregister ([#1670](https://github.com/arn0ld87/agora/issues/1670)), Backend-Ratchet ([#1671](https://github.com/arn0ld87/agora/issues/1671)), Frontend-Coverage ([#1672](https://github.com/arn0ld87/agora/issues/1672)) und Upgrade-Runbook ([#1673](https://github.com/arn0ld87/agora/issues/1673)).

## Bis `0.10.0` stabil — P1-Fixes

- [ ] Rote Integration-CI ([#1660](https://github.com/arn0ld87/agora/issues/1660)), Supavisor-Start ([#1634](https://github.com/arn0ld87/agora/issues/1634)), Embedding-Runtime-SSoT ([#1417](https://github.com/arn0ld87/agora/issues/1417)), Eval-Seed-Leakage ([#1240](https://github.com/arn0ld87/agora/issues/1240)), vollständige Manifest-Werte/Replay-Parameter ([#1274](https://github.com/arn0ld87/agora/issues/1274)) und CodeQL-High-Triage ([#1669](https://github.com/arn0ld87/agora/issues/1669)).

Der `random_seed`-Eintrag allein belegt keinen reproduzierbaren Lauf. Bis #1274 geschlossen ist, bleibt „gleicher Seed = gleiches Ergebnis“ unzulässig.

## Im Freeze vor `1.0.0-rc.1`

- [ ] **Ops-Nachweis:** Ein Fresh-Host-Restore mit vollem Supabase-Stack, Graph, Lauf und Bericht ([#766](https://github.com/arn0ld87/agora/issues/766)); Upgrade und fehlgeschlagener Rollback werden durch das CI-Gate [#1589](https://github.com/arn0ld87/agora/issues/1589) und den realen Cutover [#1592](https://github.com/arn0ld87/agora/issues/1592) belegt ([#1659](https://github.com/arn0ld87/agora/issues/1659)).
- [ ] **Produktnachweis:** AURORA mit je einem Lauf gegen Single-Prompt- und statische Persona-Baseline sowie Messung M3 aus [#1603](https://github.com/arn0ld87/agora/issues/1603) veröffentlichen ([#1662](https://github.com/arn0ld87/agora/issues/1662)). Das ist ein nachvollziehbarer qualitativer Vergleich, kein statistischer Wirksamkeits- oder Determinismusnachweis.
- [ ] **Release-Doku:** sichtbare Grenzen und Non-Goals ([#1674](https://github.com/arn0ld87/agora/issues/1674)); RC-Notes und Upgrade-Hinweise nach [#1673](https://github.com/arn0ld87/agora/issues/1673).

Die volle Kalibrierungs-/Baseline-Suite [#765](https://github.com/arn0ld87/agora/issues/765) folgt nach 1.0. Zwischen den RCs landen nur Fixes, Tests und Dokumentation, keine Features oder Vertragsänderungen.

---

# 1.0.0 — Stable Release

Parent-Gate: [#767](https://github.com/arn0ld87/agora/issues/767).

`1.0.0` bedeutet nicht „alles denkbare eingebaut“, sondern: Der definierte Anwendungsbereich (Einzelnutzer, ADR-0019) ist stabil, nachvollziehbar und operativ wiederherstellbar.

## Freigabekriterien

- [ ] versionierte API-, Report-, Run- und Persistenzverträge
- [ ] dokumentierte Kompatibilitäts- und Deprecation-Regeln
- [ ] Migrationen mit Test-, Resume- und Rollback-Pfaden
- [ ] genau eine produktive Oberfläche
- [ ] genau eine kanonische Provider-/Secret-/Routing-Architektur sowie PostgreSQL als kanonische Metadaten-Ablage im unterstützten Install-Pfad; Artefakte bleiben dateibasiert ([#1654](https://github.com/arn0ld87/agora/issues/1654))
- [ ] vollständig grüne erforderliche Backend-/Frontend-/Schema-/Security-/E2E-Gates
- [ ] keine offenen P0/P1-Release-Blocker
- [ ] keine ungeklärten Critical/High-Security-Findings ohne dokumentierte Ausnahme
- [ ] Fresh-Install, Backup, Restore, Upgrade und Rollback nachgewiesen
- [ ] Release-Artefakte, Checksummen und SBOM vorhanden
- [ ] ein öffentlich nachvollziehbarer Referenzfall mit Eingaben, Manifest, Prompts und Route, ohne Gleichheitsbehauptung bei erneutem Lauf ([#1662](https://github.com/arn0ld87/agora/issues/1662))
- [ ] dokumentierter Vergleich mit Single-Prompt- und statischer Persona-Baseline ([#1662](https://github.com/arn0ld87/agora/issues/1662))
- [ ] sichtbare Grenzen und Non-Goals
- [ ] Feature-Freeze seit 0.10-RC
- [ ] finaler RC mindestens sieben Tage ohne neuen P0/P1-Blocker

---

## Nach 1.0.0

Erst danach werden größere Ausbaupfade neu bewertet:

- Plugin-System
- Kubernetes/Helm
- Federation
- zusätzliche Branchen-/Analysepakete
- optionale gehostete Betriebsmodelle
- Multi-User, Supabase Auth/RLS/Realtime und Blob-Ablage in Supabase Storage ([#1654](https://github.com/arn0ld87/agora/issues/1654), ADR-0019)
- volle Kalibrierungs-/Baseline-Suite ([#765](https://github.com/arn0ld87/agora/issues/765)) und Out-of-Process-Worker ([#1551](https://github.com/arn0ld87/agora/issues/1551))

Diese Punkte sind **keine Zusagen für 1.0.0**.

## Pflege dieser Roadmap

- Kleintasks und Abnahmekriterien gehören in Issues.
- Ausgelieferte Änderungen gehören als Fragment nach [`changelog.d/`](changelog.d/README.md).
- Der tatsächliche Iststand gehört in [`docs/STATUS.md`](docs/STATUS.md).
- Historische Planung wird nicht an diese Datei angehängt.
