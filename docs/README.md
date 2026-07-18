# Agora — Dokumentation

Die Dokumentation ist in aktive Steuerungsquellen und technische Referenzen getrennt. Historische Pläne sind ausdrücklich keine aktuellen Taskquellen.

## Aktive Steuerungsquellen

1. [`../README.md`](../README.md) — Produkt, Einstieg, Grenzen und Release-Linie
2. [`STATUS.md`](STATUS.md) — verifizierter Istzustand
3. [`../ROADMAP.md`](../ROADMAP.md) — strategische Release-Ziele
4. [GitHub Issues](https://github.com/arn0ld87/agora/issues) — konkrete Arbeitspakete

Weitere Einstiegspunkte:

- Mitarbeit: [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- Sicherheitsmeldungen: [`../SECURITY.md`](../SECURITY.md)
- Agentenregeln: [`../AGENTS.md`](../AGENTS.md)
- Claude-spezifische Regeln: [`../CLAUDE.md`](../CLAUDE.md)

## Architektur und Verträge

- [`architecture.md`](architecture.md) — Architektur, Domänen und Komponenten
- [`api-contracts.md`](api-contracts.md) — Pydantic-Verträge und Frontend-Spiegel
- [`decisions/`](decisions/) — Architekturentscheidungen
- [`glossary.md`](glossary.md) — verbindliches Produktvokabular
- [`agent-tools.md`](agent-tools.md) — OASIS-/CAMEL- und Agent-Tool-Integration

## Entwicklung

- [`deployment-dev.md`](deployment-dev.md) — lokales Entwicklungssetup
- [`provider-runtime-settings.md`](provider-runtime-settings.md) — LLM- und Embedding-Provider
- [`embedding-provider-switch.md`](embedding-provider-switch.md) — Wechsel des Embedding-Modells
- [`analytics.md`](analytics.md) — Analysepfade
- [`graphrag-speedup.md`](graphrag-speedup.md) — Graph-Performance

## Deployment und Betrieb

- [`deployment.md`](deployment.md) — Deployment
- [`deployment-prod-like.md`](deployment-prod-like.md) — produktionsnaher lokaler Stack
- [`release-process.md`](release-process.md) — Release-Cut und Tagging
- [`operations.md`](operations.md) — Betrieb
- [`operator-guide.md`](operator-guide.md) — Operator-Aufgaben
- [`backup-restore.md`](backup-restore.md) — Backup und Wiederherstellung

## Security

- [`security-hardening.md`](security-hardening.md)
- [`security-threat-model.md`](security-threat-model.md)
- [`secret-key-lifecycle.md`](secret-key-lifecycle.md)
- [`auth.md`](auth.md)
- [`dependency-risk-register.md`](dependency-risk-register.md)

## Runbooks

- [`runbooks/`](runbooks/) — PR-Workflow, Subagent-Routing, Worktrees, Tool-Pflicht und Gates

## UI und Design

- [`ui/`](ui/) — Golden-Gate-Zielbild, Komponenten und Designreferenzen
- [`../design/v3-source/`](../design/v3-source/) — vendorierte historische Designquelle

## Audits und historische Unterlagen

- [`audits/`](audits/) — Audit-Berichte
- [`archive/planning/`](archive/planning/) — ersetzte Roadmaps und Backlogs als Git-Historienindex
- [`plans/archive/`](plans/archive/) — abgeschlossene technische Pläne
- [`worklogs/archive/`](worklogs/archive/) — historische Arbeitsprotokolle

Verzeichnisse wie `plans/active/`, Epic-Handovers und Superpowers-Pläne dürfen als umsetzungsnahe Referenz zu einem GitHub Issue bestehen. Sie sind nie die führende Prioritäts- oder Statusquelle.
