# Agora Roadmap

**Stand:** 27.07.2026  
**Aktuelle Produktversion:** `0.8.0` Technical Preview

Diese Datei beschreibt ausschließlich die strategische Reihenfolge der nächsten Releases. Konkrete Arbeitspakete, Akzeptanzkriterien und Fortschritt werden als GitHub Issues gepflegt.

## Verbindliche Dokumentationshierarchie

| Ebene | Aufgabe |
|---|---|
| [`README.md`](README.md) | Produkt, Einstieg, Grenzen und Release-Linie |
| [`docs/STATUS.md`](docs/STATUS.md) | verifizierter Istzustand |
| `ROADMAP.md` | Release-Ziele und Reihenfolge |
| [GitHub Issues](https://github.com/arn0ld87/agora/issues) | ausführbare Tasks |

ADRs, Architektur-, Security- und Runbook-Dokumente bleiben verbindliche Referenzen. Sie ersetzen weder Roadmap noch Issues.

Historische Planungsstände: [`docs/archive/planning/`](docs/archive/planning/)

---

## Produktziel

Agora wird eine stabile, lokal oder kontrolliert hybrid betreibbare Single-User-Plattform für evidenzorientierte Stakeholder-, Zielgruppen- und Marktreaktionssimulationen.

Der Weg zu `1.0.0` folgt vier Regeln:

1. Stabilität vor weiteren großen Features.
2. Eine kanonische Oberfläche und eine kanonische Provider-/Routing-Wahrheit.
3. Reproduzierbarkeit und messbarer Erkenntnisgewinn vor Plattformausbau.
4. Keine öffentliche SaaS- oder Multi-User-Erweiterung vor `1.0.0`.

---

# 0.8.0 — Technical Preview

## Bedeutung

Der aktuelle Stand besitzt eine vollständige fachliche Grundpipeline:

- Onboarding und Provider-Verbindungen
- Dokument- und Webseitenaufnahme
- Wissensgraph und Embeddings
- Persona-Erzeugung und Review
- Multi-Agenten-Simulation
- Run-Steuerung und Live-Ereignisse
- Evidence-orientierte Reports
- Compare-, Export- und Observability-Grundlagen

Der Stand ist trotzdem keine stabile `1.0`, weil die Vue-v4-Konsolidierung noch nicht abgeschlossen ist (verbleibend: `/home`-Redirect [#915](https://github.com/arn0ld87/agora/issues/915), Migration der v3-Inhaltskomponenten [#922](https://github.com/arn0ld87/agora/issues/922)) und die E2E-Pipeline noch nicht als verpflichtender Pull-Request-Check erzwungen wird.

## Erreicht

Die ursprünglichen Voraussetzungen für den `0.8.0`-Stand sind abgeschlossen: die sechs Kern-E2E-Smokes sind repariert (Issue #739) und laufen seit mehreren Tagen durchgehend grün, die Dokumentation ist auf vier aktive Ebenen reduziert, die Versionslinie ist auf `0.8.0` zurückgesetzt, und Provider-/Secret-/Dependency-Drifts aus dieser Phase sind geschlossen (Issues #759, #761, #762). Offene Arbeit für den nächsten Schritt steht unter `0.9.0` unten.

---

# 0.9.0 — Stability Beta

## Ziel

Agora soll als zusammenhängendes Produkt zuverlässig installierbar, bedienbar und testbar sein. Neue große Produktbereiche sind in dieser Phase nachrangig.

## Freigabekriterien

### Kernpipeline

- [x] Health, Upload + Graph, Minimalreport, Report-Modi, Accessibility und AiModelPicker sind stabil grün (20/20 aufeinanderfolgende `e2e-smokes`-Läufe auf `push` und `pull_request`, 21.–22.07.2026)
- [x] E2E-Smokes laufen mehrfach ohne Flakes (siehe oben)
- [ ] E2E ist als verpflichtender Pull-Request-Check aktiviert (Branch-Protection auf `main` aktuell nicht gesetzt — Läufe sind grün, aber nicht erzwungen)
- [ ] keine Skips, abgeschwächten Assertions oder pauschalen Retries als Ersatz für Fehlerbehebung

### Frontend

- [ ] Vue-v4 ist die einzige produktive Oberfläche
- [ ] klassische Prozess-Views besitzen Lösch- oder Redirect-Entscheidungen
- [x] `/agora-2026` ist kein produktiv gerouteter Parallelentwurf — als Designreferenz unter `docs/design-reference/agora-2026/` archiviert ([PR #878](https://github.com/arn0ld87/agora/pull/878)), Regressionstest pinnt `/agora-2026` → NotFound
- [x] kein produktiv verdrahteter React-/Lovable-Rewrite — ein Lovable-Prototyp existiert, liegt aber außerhalb dieses Repos, ist unveröffentlicht und in keinem Auslieferungspfad referenziert, siehe [`docs/epics/frontend-next/2026-STATUS.md`](docs/epics/frontend-next/2026-STATUS.md)
- [ ] Responsive- und Accessibility-Gates sind grün

### Provider und Routing

- [x] `ProviderConnection`, `AiRoute` und `AiModelPicker` sind die kanonischen Pfade
- [x] Legacy-Profile greifen nicht mehr bevorzugt auf eigene Secrets oder Routingwerte zu
- [x] explizite Provider-Konfiguration gewinnt vor URL-/Modell-Heuristiken
- [x] Frontend- und Backend-Provider-Vokabular sind synchron
- [x] Chat-Routing und Embedding-Konfiguration bleiben getrennt

### Betrieb und Supply Chain

- [x] `pyproject.toml` und `uv.lock` sind einzige Backend-Dependency-SSoT (Issue #762)
- [x] `requirements.txt` ist entfernt oder automatisch generiert (`backend/requirements.txt` existiert nicht mehr)
- [x] Produktversion und Komponentenmanifest-Versionen werden automatisch synchronisiert (Issue #759, `.github/workflows/version-drift.yml`, `pre-push-gate.sh schemas`)
- [x] offene CVE-Ausnahmen besitzen aktuelle Owner, Fristen und Auflösungsweg (siehe `docs/dependency-risk-register.md`; Hardstops NLTK 28.09.2026, Trivy 30.08.2026)
- [ ] Readiness, Auth, Tickets und Secret Stores sind durch produktnahe Smokes abgedeckt

### Dokumentation

- [x] README, STATUS, ROADMAP und Issues widersprechen sich nicht (Stand 27.07.2026 — laufend bei jeder größeren Änderung neu zu verifizieren)
- [ ] `docs/STATUS.md` wird automatisch erzeugt oder CI-geprüft — `scripts/sync-status.sh` regeneriert nur die markierten Versions-/Test-Blöcke, nicht die Fließtext-Abschnitte; die STATUS-Sync-Prüfung läuft ausschließlich lokal über `pre-push-gate.sh schemas`. Der CI-Job dafür wurde am 17.05.2026 entfernt (`.github/workflows/ci.yml`, Kommentar „2026-05-17 entfernt: status-sync (MAI-16)"), `docs/STATUS.md` bleibt laut diesem Kommentar bewusst manuell pflegbar
- [ ] historische Pläne liegen ausschließlich im Archiv
- [ ] Installations- und Betriebsanleitung sind gegen einen frischen Host geprüft

## Nicht Bestandteil von 0.9.0

- Multi-User- oder Teamverwaltung
- öffentliches SaaS-Hosting
- Helm-Chart
- Federation mehrerer Agora-Instanzen
- allgemeines Plugin-System
- vollständiger Frontend-Rewrite

---

# 0.10.0 — Release Candidate

## Ziel

Agora soll nicht nur technisch laufen, sondern Ergebnisse reproduzierbar, budgetierbar und überprüfbar erzeugen.

## Freigabekriterien

### Reproduzierbarkeit

- [ ] jeder Run speichert Eingangsdaten-Hash, Graph-Version, Modelle, Provider, Routing-Snapshot, Prompt-Versionen und Seeds
- [ ] ein vorhandener Run kann mit gleicher oder bewusst geänderter Konfiguration reproduziert werden
- [ ] Exporte enthalten ein maschinenlesbares Run-Manifest
- [ ] Datenmigrationen besitzen Resume-, Rollback- und Fehlerpfade

### Kosten und Ressourcen

- [ ] erwartete Modelle, Token, Kosten und Laufzeit werden vor dem Start angezeigt
- [ ] Token-, Kosten- und Zeitlimits können pro Run gesetzt werden
- [ ] Abbrüche und Budgetüberschreitungen erzeugen nachvollziehbare Zustände
- [ ] Hardware-Tiers werden durch reproduzierbare Benchmarks statt Schätzwerte beschrieben

### Produktnachweis

- [ ] mindestens drei reale Referenzfälle sind dokumentiert
- [ ] Agora wird gegen eine Single-Prompt-Baseline verglichen
- [ ] wiederholte Runs zeigen Varianz und Stabilität
- [ ] Confidence-Werte werden gegen Evidence-Abdeckung kalibriert
- [ ] bekannte Fehlannahmen und Grenzen werden veröffentlicht, nicht versteckt

### Betrieb

- [ ] Backup und Restore für Projekte, Graph, Secrets und Konfiguration sind dokumentiert und getestet
- [ ] Upgrade- und Rollback-Pfad zwischen unterstützten Versionen ist dokumentiert
- [ ] ein frischer Docker- und ein Host-Installationspfad sind reproduzierbar
- [ ] keine offenen kritischen Security- oder Datenintegritätsblocker
- [ ] Release-Artefakte, SBOM und Checksummen sind verfügbar

## Feature-Freeze

Mit dem ersten `0.10.0`-Release-Candidate beginnt der Feature-Freeze. Danach werden bis `1.0.0` nur Fehler, Dokumentation, Migrationen, Security und nachgewiesene Release-Blocker bearbeitet.

---

# 1.0.0 — Stable Single-User Release

## Definition

`1.0.0` bedeutet nicht „alle denkbaren Features vorhanden“. Es bedeutet, dass der definierte Single-User-Anwendungsbereich stabil und nachvollziehbar unterstützt wird.

## Freigabekriterien

- [ ] stabile und versionierte API-, Report- und Persistenzverträge
- [ ] dokumentierte Kompatibilitäts- und Deprecation-Regeln
- [ ] eine unterstützte produktive Oberfläche
- [ ] eine kanonische Provider-, Secret- und Routing-Architektur
- [ ] vollständig grüne verpflichtende CI- und E2E-Gates
- [ ] reproduzierbare Installation, Upgrade, Backup und Restore
- [ ] mindestens ein öffentlich nachvollziehbarer Referenzlauf
- [ ] messbarer Mehrwert gegenüber einer einfachen LLM-Baseline
- [ ] keine bekannten P0-/P1-Release-Blocker
- [ ] Release Notes, Migrationshinweise, SBOM und signierte Artefakte

---

## Nach 1.0.0

Erst nach einer stabilen Single-User-Version werden größere Ausbaupfade bewertet:

- Team- und Rollenmodell
- Plugin-System
- Kubernetes/Helm
- Federation
- weitere Analysepakete und Branchenvorlagen
- optionale gehostete Betriebsmodelle

Diese Punkte sind keine Zusagen für `1.0.0` und erhalten erst nach dem stabilen Release eigene Problemstatements und Entscheidungen.

---

## Pflege dieser Roadmap

- Die Roadmap enthält keine ausführbaren Kleintasks.
- GitHub Issues enthalten Scope, Akzeptanzkriterien, Owner und Abhängigkeiten.
- Ausgelieferte Änderungen gehören in `CHANGELOG.md`.
- Der tatsächliche Stand gehört in `docs/STATUS.md`.
- Erledigte historische Planung wird nicht an diese Datei angehängt.
