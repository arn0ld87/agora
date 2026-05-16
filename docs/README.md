# Agora — Dokumentation

Lebende Doku für das Agora-Projekt. Worklogs und Arbeitsprotokolle liegen
unter [`archive/`](archive/) und sind nicht für den Einstieg gedacht.

## Einstieg

- Projekt-Übersicht und Quickstart: [`../README.md`](../README.md)
- Mitarbeit: [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- Sicherheitsmeldungen: [`../SECURITY.md`](../SECURITY.md)
- Agenten-Konfiguration (Claude Code, Codex): [`../AGENTS.md`](../AGENTS.md)
- Roadmap und Slice-Plan: [`../PLAN.md`](../PLAN.md)

## Architektur und API

- [`architecture.md`](architecture.md) — Ziel-Architektur, Layer-Modell, Komponenten
- [`agent-tools.md`](agent-tools.md) — Integration von Agent-Tools (CAMEL, OASIS)
- [`api-contracts.md`](api-contracts.md) — Pydantic-Contracts + Zod-Spiegel
- [`glossary.md`](glossary.md) — Wording-Glossar (Layer 2)

## Development

- [`deployment-dev.md`](deployment-dev.md) — Lokales Dev-Setup
- [`provider-runtime-settings.md`](provider-runtime-settings.md) — LLM-/Embedding-Provider
- [`embedding-provider-switch.md`](embedding-provider-switch.md) — Wechsel des Embedding-Modells
- [`analytics.md`](analytics.md) — Auswertungspfade
- [`graphrag-speedup.md`](graphrag-speedup.md) — Performance-Tuning Graph

## Deployment und Operations

- [`deployment.md`](deployment.md) — Produktions-Deployment
- [`deployment-prod-like.md`](deployment-prod-like.md) — Prod-like Stack lokal
- [`release-process.md`](release-process.md) — Release-Cut, Tagging
- [`operations.md`](operations.md) — Betrieb
- [`operator-guide.md`](operator-guide.md) — Operator-Aufgaben
- [`backup-restore.md`](backup-restore.md) — Backup-Strategie

## Security

- [`security-hardening.md`](security-hardening.md) — Hardening-Maßnahmen
- [`security-threat-model.md`](security-threat-model.md) — Bedrohungsmodell
- [`secret-key-lifecycle.md`](secret-key-lifecycle.md) — Schlüssel-Rotation
- [`auth.md`](auth.md) — Authentifizierung
- [`dependency-risk-register.md`](dependency-risk-register.md) — Offene CVE-Watchlist

## Runbooks (für Mitwirkende und Agenten)

- [`runbooks/`](runbooks/) — PR-Workflow, Subagent-Routing, Worktree-Strategie, Tool-Pflicht

## Architekturentscheidungen (ADRs)

- [`decisions/`](decisions/) — Stabile Architekturentscheidungen

## Status und Planung

- [`STATUS.md`](STATUS.md) — Aktueller Slice- und Test-Status
- [`ROADMAP.md`](ROADMAP.md) — Mittelfristige Roadmap
- [`feature-roadmap.md`](feature-roadmap.md) — Feature-Pipeline
- [`refactoring-backlog.md`](refactoring-backlog.md) — Refactoring-Backlog
- [`plans/`](plans/) — Aktive Slice-Pläne (Observability u. a.)

## Design

- [`design/`](design/) — Design-Language v4, Komponenten-Token
- [`ui/`](ui/) — UI-Konzepte und Wireframes

## Archiv

- [`archive/worklogs/`](archive/worklogs/) — Historische Arbeitsprotokolle (~340 Stück)
- [`archive/plans/`](archive/plans/) — Abgeschlossene oder ersetzte Pläne
- [`archive/sessions/`](archive/sessions/), [`archive/history/`](archive/history/), [`archive/logs/`](archive/logs/), [`archive/prompts/`](archive/prompts/), [`archive/manual-smoke/`](archive/manual-smoke/) — Historische Materialien
- [`archive/root-junk/`](archive/root-junk/) — Aus dem Repo-Root verschobene Ad-hoc-Dokumente
