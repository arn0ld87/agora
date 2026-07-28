# AGENTS.md

Guidance für Codex, Claude Code und andere Agent-Runtimes in diesem Repository.

## Dokumentationsquellen

Agenten verwenden genau diese Reihenfolge:

1. [`README.md`](README.md) — Produkt, Grenzen, Setup und Release-Linie
2. [`docs/STATUS.md`](docs/STATUS.md) — verifizierter Istzustand
3. [`ROADMAP.md`](ROADMAP.md) — strategische Release-Reihenfolge
4. [GitHub Issues](https://github.com/arn0ld87/agora/issues) — ausführbare Tasks und Akzeptanzkriterien

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

## Tool-Pipeline

Für Architektur-, Delta- und Codebase-Analysen:

1. `code-review-graph`
2. `context7` bei Bibliotheks- oder Frameworkfragen
3. `ctx_batch_execute` für große Read-only-Abfragen
4. `ctx_execute` beziehungsweise `ctx_execute_file`
5. direkte Dateiwerkzeuge nur für gezielte Bearbeitung und Verifikation

Globale Konfiguration, Tokens, Browserprofile, Keychain-Inhalte und private Host-Dateien werden niemals ins Repository kopiert.

## Architektur-Single-Sources-of-Truth

- API-Verträge: `backend/app/contracts/` mit Pydantic v2
- Frontend-Spiegel: `frontend/src/contracts/` und generierte `schemas/`
- Provider-Erkennung: `backend/app/llm/providers/registry.py::detect_provider`
- Provider-Verbindung: `ProviderConnection`
- strukturierte JSON-LLM-Calls: `backend/app/llm/client.py::LLMClient.chat_json` mit Pydantic-Schema — roher `OpenAI`-Client nicht für JSON-Outputs
- kanonische Modellauswahl: `frontend/src/components/v4/forms/AiModelPicker.vue`
- kanonische Modellreferenz: `AiModelRef`
- kanonische Route: `AiRoute` / `LlmRoute`
- Embedding-Konfiguration: `embedding_service.py` und `embedding_migration.py`
- Evidence-Gating: ADR-0002-Hartanker

Chat-Routing und Embedding-Konfiguration bleiben strukturell getrennt.

## Aktuelle Release-Priorität

### 0.8.0 → 0.9.0

Erledigt: E2E-Smokes repariert (#739), Provider-/Secret-/Routing-SSoT abgeschlossen (#761), Dependency-SSoT bereinigt (#762), Produkt-/Manifest-Version automatisiert synchronisiert (#759).

Offen:

- E2E als Required Check aktivieren (Läufe sind stabil grün, `main` besitzt aber noch keine Branch-Protection)
- Vue-v4 als einziges Produktfrontend festlegen (Issue #760; Umsetzungskarte [#829](https://github.com/arn0ld87/agora/issues/829))

### 0.9.0 → 0.10.0

- reproduzierbare Run-Manifeste und Replay
- Kosten-, Token- und Zeitbudgets
- Backup, Restore, Upgrade und Rollback
- Kalibrierungs- und Baseline-Vergleich
- Feature-Freeze vor `1.0.0`

Details und Freigabekriterien: [`ROADMAP.md`](ROADMAP.md)

## Commands

```bash
# Setup und Entwicklung
bun run setup:all
bun run dev
bun run backend
bun run frontend

# Gesamtprüfung
bun run check
bash scripts/pre-push-gate.sh

# Backend
cd backend && uv run pytest -x -q
cd backend && uv run ruff check .
cd backend && uv run mypy app
cd backend && uv run python -m app.contracts.dump_schemas

# Frontend
cd frontend && bun run check
cd frontend && bun run test

# Produktionsnaher lokaler Stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
```

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

## Wichtige Referenzen

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/decisions/`](docs/decisions/)
- [`docs/dependency-risk-register.md`](docs/dependency-risk-register.md)
- [`docs/runbooks/`](docs/runbooks/)
- [`CHANGELOG.md`](CHANGELOG.md)
- [`CLAUDE.md`](CLAUDE.md)

## Knowledge Graph

Wenn `graphify-out/graph.json` vorhanden ist, bei Codebase-Fragen zuerst eine gezielte Graph-Abfrage verwenden. Nach strukturellen Codeänderungen `graphify update .` ausführen. Graphresultate ersetzen weder direkte Codeprüfung noch Tests.

## Token Efficiency
- Never re-read files you just wrote or edited. You know the contents.
- Never re-run commands to "verify" unless the outcome was uncertain.
- Don't echo back large blocks of code or file contents unless asked.
- Batch related edits into single operations. Don't make 5 edits when 1 handles it.
- Skip confirmations like "I'll continue..." Just do it.
- If a task needs 1 tool call, don't use 3. Plan before acting.
- Do not summarize what you just did unless the result is ambiguous or you need additional input.
