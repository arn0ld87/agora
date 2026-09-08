# Agora — Dokumentation

**Stand:** 08.09.2026  
**Produktversion:** `0.9.5`

Die Dokumentation ist nach **aktueller Steuerungsquelle**, **lebender technischer Referenz** und **historischem Beleg** getrennt. Ein altes Audit wird nicht durch ein neues Datum aktueller; es wird nur schwerer zu erkennen, dass es alt ist.

---

## 1. Verbindliche Steuerungsquellen

In dieser Reihenfolge:

1. [`../README.md`](../README.md) / [`../README.de.md`](../README.de.md) — Produkt, Einstieg, Grenzen, Quickstart
2. [`STATUS.md`](STATUS.md) — verifizierter aktueller Istzustand
3. [`../ROADMAP.md`](../ROADMAP.md) — Release-Ziele und Reihenfolge
4. [GitHub Issues](https://github.com/arn0ld87/agora/issues) — konkrete Arbeitspakete und Akzeptanzkriterien

Ausgelieferte Einzeländerungen stehen in [`../changelog.d/`](../changelog.d/README.md); `CHANGELOG.md` wird beim Release-Cut aus den Fragmenten erzeugt.

---

## 2. Orientierung für Maintainer und Agenten

- [`../AGENTS.md`](../AGENTS.md) — Repo-Regeln, Gates, Branch-/PR-Disziplin
- [`../CLAUDE.md`](../CLAUDE.md) — Claude-Code-spezifische Regeln
- [`../CONTEXT.md`](../CONTEXT.md) — Laufzeit-, Evidence- und Begriffsorientierung
- [`agents/architecture-ssot.md`](agents/architecture-ssot.md) — kanonische Pfade pro Architekturkonzept
- [`agents/release-priority.md`](agents/release-priority.md) — kompakte 0.10-Priorität, ROADMAP bleibt führend
- [`runbooks/`](runbooks/) — konkrete Entwicklungs-/Release-/Gate-Abläufe

---

## 3. Architektur und Verträge

- [`architecture.md`](architecture.md) — **aktuelle Istarchitektur**, Baseline 08.09.2026
- [`runbooks/architecture-layers.md`](runbooks/architecture-layers.md) — Schichtenkarte
- [`api.md`](api.md) — HTTP-Endpunkte nach Domänen
- [`api-contracts.md`](api-contracts.md) — Envelopes, Fehlercodes und Vertragsgrenzen
- [`configuration.md`](configuration.md) — Konfigurations-/Environment-Referenz
- [`provider-runtime-settings.md`](provider-runtime-settings.md) — ProviderConnection, Routing, CLI-/HTTP-Transporte
- [`decisions/`](decisions/) — ADRs; sie sind für ihre jeweilige Entscheidung verbindlich, bis sie superseded werden
- [`glossary.md`](glossary.md) — Produktvokabular

Der Code bleibt für konkrete Feld-/Routen-/Defaultwerte führend. Doku soll den Code erklären, nicht eine zweite geheime Implementierung erfinden.

---

## 4. Entwicklung

- [`deployment-dev.md`](deployment-dev.md) — lokales Entwicklungssetup
- [`troubleshooting.md`](troubleshooting.md) — aktuelle bekannte Fehlerbilder
- [`embedding-provider-switch.md`](embedding-provider-switch.md) — Embedding-Wechsel/Migration
- [`agent-tools.md`](agent-tools.md) — Agent-/OASIS-Toolintegration
- [`analytics.md`](analytics.md) — Analysepfade
- [`graphrag-speedup.md`](graphrag-speedup.md) — Graph-/Retrieval-Performance

Bei widersprüchlichen Aussagen zu aktuellem Status gewinnt [`STATUS.md`](STATUS.md), bei Architekturpfaden der Code/ADR.

---

## 5. Deployment und Betrieb

- [`deployment.md`](deployment.md) — Deployment-Einstieg
- [`deployment-prod-like.md`](deployment-prod-like.md) — gehärteter Single-User-Stack
- [`operator-guide.md`](operator-guide.md) — Operator-Abläufe
- [`operations.md`](operations.md) — Health, Logs, Ausfälle, Runtime-Besonderheiten
- [`backup-restore.md`](backup-restore.md) — Backup-/Restore-Verfahren und noch offene Abnahmegrenzen
- [`release-process.md`](release-process.md) — Version-Cut, Gates, Tag/Release/Rollback

Wichtig: Eine dokumentierte Backup-Prozedur ist noch kein bestandener Restore-Drill. Der Release-Nachweis dazu ist #766.

---

## 6. Auth und Security

- [`auth.md`](auth.md) — Master-Token, Workspace-API-Keys, Scopes, Tickets
- [`secret-key-lifecycle.md`](secret-key-lifecycle.md) — `SECRET_KEY`, `AGORA_AUTH_TOKEN`, `AGORA_SECRET_KEY`, `AGORA_FERNET_KEY`
- [`security-threat-model.md`](security-threat-model.md) — aktuelle Trust Boundaries und Restrisiken
- [`security-hardening.md`](security-hardening.md) — Hardening-Chronik/Migrationshinweise
- [`dependency-risk-register.md`](dependency-risk-register.md) — aktive Dependency-Ausnahmen/Hardstops
- [`../SECURITY.md`](../SECURITY.md) — Vulnerability-Reporting

---

## 7. Referenzläufe und Evaluation

- [`reference-runs/README.md`](reference-runs/README.md) — Index und Regeln
- [`reference-runs/2026-08-17-aurora-red-team/`](reference-runs/2026-08-17-aurora-red-team/README.md) — aktueller dokumentierter Referenzlauf

Referenzläufe sind **eingefrorene Beobachtungen eines damaligen Code-/Datenstands**. Sie werden nicht nachträglich so umgeschrieben, als wären sie auf dem heutigen `main` erzeugt worden.

Sie belegen auch keine vollständige Reproduzierbarkeit. Der aktuelle Replay-/Manifest-Stand steht in #763/#1274 und [`STATUS.md`](STATUS.md).

---

## 8. UI und Design

- [`ui/`](ui/) — Design-/Komponentenreferenzen und Audits
- [`design-reference/agora-2026/`](design-reference/agora-2026/README.md) — eingefrorene historische Designexploration, nicht produktiv geroutet
- [`../design/v3-source/`](../design/v3-source/) — vendorierte historische Designquelle

Ein UI-Audit mit altem Datum ist ein historischer Befund, keine aktuelle Komponentenliste, sofern es nicht ausdrücklich erneut gegen den Code verifiziert wurde.

---

## 9. Historische Unterlagen

Diese Verzeichnisse/Dateitypen dienen der Nachvollziehbarkeit und sind **keine aktuellen Steuerungsquellen**:

- [`audits/`](audits/)
- [`archive/planning/`](archive/planning/)
- [`plans/archive/`](plans/archive/)
- [`worklogs/archive/`](worklogs/archive/)
- datierte Referenzläufe
- datierte Lessons-Learned-/Arbeitsprotokolle

`plans/active/` oder Epic-Handovers können als umsetzungsnahe Referenz zu einem offenen Issue existieren. Priorität, Status und Abnahme kommen trotzdem aus ROADMAP/Issues.

---

## 10. Dokumentationspflege

Bei einer Änderung prüfen:

| Änderung | Mindestens prüfen |
|---|---|
| Produkt-/Release-Status | README, STATUS, ROADMAP |
| API-/Contract-Änderung | `api.md`, `api-contracts.md`, Schemas/Zod |
| Provider-/Routing-Änderung | `provider-runtime-settings.md`, `agents/architecture-ssot.md` |
| Secret-/Auth-Änderung | `auth.md`, `secret-key-lifecycle.md`, Threat Model |
| Deployment-/Persistenz-Änderung | deployment, operations, backup/restore |
| Trust-/Evidence-Änderung | STATUS, CONTEXT, relevante ADRs |
| Release-Prozess | `release-process.md`, Release-Versioning-Runbook |

Keine schnell alternden Testzahlen in mehrere Dateien kopieren. Der aktuelle Nachweis gehört in `docs/STATUS.md`; Release Notes dürfen die für ihren konkreten Release-Candidate gemessenen Werte einfrieren.
