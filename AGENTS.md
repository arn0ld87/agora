# AGENTS.md

Guidance für Codex, Claude Code und andere Agent-Runtimes in diesem Repository.

> **Progressive Disclosure:** diese Datei enthält nur die immer verbindlichen Regeln. Detail-Referenzen sind unter [`docs/agents/`](docs/agents/) ausgelagert und bei Bedarf zu laden — siehe [Detaillierte Referenzen](#detaillierte-referenzen).

## Dokumentationsquellen

Agenten verwenden genau diese Reihenfolge:

1. [`README.md`](README.md) — Produkt, Grenzen, Setup und Release-Linie
2. [`docs/STATUS.md`](docs/STATUS.md) — verifizierter Istzustand
3. [`ROADMAP.md`](ROADMAP.md) — strategische Release-Reihenfolge
4. [GitHub Issues](https://github.com/arn0ld87/agora/issues) — ausführbare Tasks und Akzeptanzkriterien

[`VISION.md`](VISION.md) — nicht-bindender North-Star (das *Warum* und die Langzeitrichtung), keine Planungsdatei und keine konkurrierende Roadmap.

ADRs, Architektur-, Security- und Runbook-Dateien sind verbindliche Referenzen, aber keine konkurrierenden Roadmaps. Historische Planung liegt unter [`docs/archive/planning/`](docs/archive/planning/).

## Projekt

Agora ist eine lokal oder kontrolliert hybrid betreibbare Multi-Agent-Analyseplattform für simulierte DACH-Zielgruppen-, Stakeholder- und Marktreaktionen.

**Aktueller Reifegrad:** `0.8.0` Technical Preview.  
**Ziel:** stabile Single-User-Version `1.0.0` gemäß [`ROADMAP.md`](ROADMAP.md).

**Stack:** Flask/Python 3.14, Pydantic v2, Vue 3, TypeScript, Vite, Pinia, Neo4j, Redis, OASIS/CAMEL und lokale oder OpenAI-kompatible Provider.

**Betriebsmodell:** Single User, lokal oder kontrolliert hybrid. Kein öffentliches SaaS.

## Verbindliche Arbeitsweise

1. Nie direkt auf `main` arbeiten. Eigener Branch und atomarer Pull Request.
2. Tests sind die Spezifikation. Verhaltensänderungen folgen RED → GREEN → Refactor.
3. Vor jedem Push das passende Gate ausführen:
   - `bash scripts/pre-push-gate.sh backend`
   - `bash scripts/pre-push-gate.sh frontend`
   - `bash scripts/pre-push-gate.sh schemas`
   - ohne Scope: vollständiges Gate
4. Kein `--no-verify` ohne ausdrückliche Freigabe.
5. Dokumentation im selben Slice synchronisieren:
   - Istzustand → `docs/STATUS.md`
   - strategische Release-Auswirkung → `ROADMAP.md`
   - konkrete Folgearbeit → GitHub Issue
   - ausgelieferte Änderung → `CHANGELOG.md`
6. Keine abgeschwächten Assertions, globalen Skips oder pauschalen Retries, um rote Tests kosmetisch grün zu machen.
7. Verträge zuerst, Consumer danach.
8. Kein neuer großer Produktbereich, wenn er nicht in der aktuellen Release-Stufe der Roadmap vorgesehen ist.

Runbooks:

- [`docs/runbooks/pr-workflow.md`](docs/runbooks/pr-workflow.md)
- [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md)
- [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md)
- [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md)

## Worktree-Pfad

**Pflicht:** Alle Agora-Worktrees liegen unter `/Volumes/T7/Worktrees/agora/<slice-id>/`. `/private/tmp` ist verboten. T7-Mount vor dem Anlegen prüfen (`test -d /Volumes/T7`). Volle Strategie in [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md).

## Verboten

- direkte Änderungen auf `main`
- Dataclasses oder handgeschriebene Inline-Schemas für API-Verträge
- lokale Provider-Detection-Heuristiken neben der Registry
- neue produktive Legacy-Picker oder neue parallele Frontends
- React-/Lovable-Rewrite ohne eigene Architekturentscheidung und Release-Scope
- API-Keys oder Secrets in Code, Logs, Fixtures oder Dokumentation
- neue Query-Tokens `?token=`; URL-Auth nur über signierte Tickets
- `print()` in Produktivcode statt strukturiertem Logging
- hartkodierte UI-Texte statt `vue-i18n`
- neue CVE-Ausnahmen ohne Issue, Owner, Deadline und Hardstop
- neue Planungsdateien neben README, STATUS, ROADMAP und Issues
- `apt`; auf Debian/Ubuntu `nala` verwenden

## Detaillierte Referenzen

Bei Bedarf laden (nicht verbindlich ständig im Kontext):

- [`docs/agents/tool-pipeline.md`](docs/agents/tool-pipeline.md) — Tool-Pipeline, Knowledge Graph, Token Efficiency
- [`docs/agents/architecture-ssot.md`](docs/agents/architecture-ssot.md) — Architektur-Single-Sources-of-Truth
- [`docs/agents/release-priority.md`](docs/agents/release-priority.md) — aktuelle Release-Priorität
- [`docs/agents/commands.md`](docs/agents/commands.md) — Backend-/Frontend-/Docker-Commands

## Wichtige Referenzen

- [`VISION.md`](VISION.md) — North-Star (nicht-bindend)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/api.md`](docs/api.md) — HTTP-Endpunkte nach Domänen
- [`docs/configuration.md`](docs/configuration.md) — Umgebungsvariablen
- [`docs/troubleshooting.md`](docs/troubleshooting.md) — bekannte Fehlerbilder
- [`docs/decisions/`](docs/decisions/)
- [`docs/dependency-risk-register.md`](docs/dependency-risk-register.md)
- [`docs/runbooks/`](docs/runbooks/)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`CLAUDE.md`](CLAUDE.md)