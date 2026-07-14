# AGENTS.md

Guidance für Codex, Claude Code und andere Agent-Runtimes in diesem Repository.

Diese Datei bleibt bewusst operativ und knapp. Verifizierter Istzustand:
[`docs/STATUS.md`](docs/STATUS.md). Zukunft und Slice-Reihenfolge: [`PLAN.md`](PLAN.md).
Detail-Runbooks: [`docs/runbooks/`](docs/runbooks/).

## Projekt

Agora ist ein **lokal-first Multi-Agent-Simulator** für DACH-Zielgruppenreaktionen:
Dokument hochladen → Wissensgraph extrahieren → Personas erzeugen → OASIS-Simulation → DACH-Report.

**Stack:** Flask/Python 3.14, Pydantic v2, Vue 3, Vite, Pinia, Neo4j 5.18 CE,
Redis, OASIS (`camel-oasis`) und Ollama bzw. OpenAI-kompatible Provider.
Package-Manager: `uv` im Backend, `npm` im Frontend.

**Betriebsmodell:** Single-User, lokal oder kontrolliert hybrid. Kein öffentliches SaaS.
Siehe [ADR-0001](docs/decisions/0001-auth-model.md).

**Aktueller Stand:** v1.0.0. Onboarding und Provider-Unification sind weitgehend auf
`main`. Offene Prioritäten sind Issue #739 (E2E-Smokes/PR-Gate), Issue #740
(Slice 7.6d, letzter Legacy-Picker) sowie die dokumentierten Security-Hardstops.

## Verbindliche Arbeitsweise

1. **Nie direkt auf `main` arbeiten.** Eigener Branch und atomarer PR.
2. **Tests sind die Spezifikation.** Bei Verhaltensänderungen RED → GREEN → Refactor.
3. **Vor jedem Push das passende Gate ausführen:**
   - `bash scripts/pre-push-gate.sh backend`
   - `bash scripts/pre-push-gate.sh frontend`
   - `bash scripts/pre-push-gate.sh schemas`
   - ohne Scope: vollständiges Gate
4. **Kein `--no-verify`** ohne ausdrückliche Freigabe.
5. **Dokumentation im selben Slice synchronisieren.** `STATUS.md` beschreibt nur den
   Istzustand; `PLAN.md` nur Zukunft und Reihenfolge; historische Details gehören in
   `CHANGELOG.md`, ADRs, Worklogs oder Git-Historie.
6. **Keine abgeschwächten Assertions, globalen Skips oder pauschalen Retries**, um rote
   Tests kosmetisch grün zu machen.
7. **Layer-Reihenfolge respektieren.** Verträge zuerst, Consumer danach.

PR-Workflow: [`docs/runbooks/pr-workflow.md`](docs/runbooks/pr-workflow.md)
Pre-Push-Gate: [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md)
Worktrees: [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md)

## Tool-Pipeline

Für Architektur-, Delta- und Codebase-Analysen gilt:

1. `code-review-graph`
2. `context7`, wenn Bibliotheks- oder Frameworkverhalten betroffen ist
3. `ctx_batch_execute` für mehrere große Read-only-Abfragen
4. `ctx_execute` bzw. `ctx_execute_file`
5. direkte Dateiwerkzeuge nur für gezielte Bearbeitung und Verifikation

`context-mode` ist die Execution-Layer für große Ausgaben. Globale Konfiguration,
Auth-Dateien, Tokens, Browserprofile und Keychain-Inhalte werden niemals ins Repository
kopiert oder untersucht. Tool-Stand: [`docs/tooling/agent-tools.md`](docs/tooling/agent-tools.md).

## Architektur-Single-Sources-of-Truth

- API-Verträge: `backend/app/contracts/` mit Pydantic v2 und `extra="forbid"`
- Frontend-Spiegel: `frontend/src/contracts/` und generierte `schemas/`
- Provider-Erkennung: `backend/app/llm/providers/registry.py::detect_provider`
- Kanonischer Modell-Picker: `frontend/src/components/AiModelPicker.vue`
- Kanonische Modellreferenz: `AiModelRef`
- Kanonische Route: `AiRoute`/`LlmRoute` gemäß aktuellem Vertrag
- Embedding-Konfiguration und Chat-Routing bleiben strukturell getrennt
- Evidence-Gating-Hartanker aus ADR-0002 dürfen nicht geschwächt werden

## Aktuelle Restarbeiten

### Issue #739: E2E-Smokes und PR-Gate

Der Stack bootet im Runner, der Health-Smoke ist grün. Fünf Specs sind rot:
Upload + Graph, Minimalreport, Report-Modi, Golden-Gate Accessibility und
AiModelPicker. Ursachen einzeln beheben; danach `pull_request`-Trigger reaktivieren
und als Required Check führen.

### Issue #740: Slice 7.6d

`LlmProfileManager.vue` auf `AiModelPicker`/`AiModelRef` migrieren. Danach den letzten
produktiven `ModelPicker.vue` inklusive verwaister Exporte, Tests und Styles löschen.
Keine neue Kompatibilitätsschicht und keine zweite Provider-Erkennung einführen.

### Weitere offene Punkte

- Persona-Count-E2E-Matrix 1/5/10/30/50/100 zentral nachweisen
- Responsive und visuelle Golden-Gate-Regressionen schließen
- `--agora-*`-Tokenwechsel als eigenes migrationspflichtiges Slice
- Phase-F-Restpunkt #671 entscheiden
- Security-Hardstops aus `docs/dependency-risk-register.md` einhalten

## Commands

```bash
# Setup und Entwicklung
npm run setup:all
npm run dev
npm run backend
npm run frontend

# Gesamtprüfung
npm run check
bash scripts/pre-push-gate.sh

# Backend
cd backend && uv run pytest -x -q
cd backend && uv run ruff check .
cd backend && uv run mypy app
cd backend && uv run python -m app.contracts.dump_schemas

# Frontend
cd frontend && npm run check
cd frontend && npm test -- --run

# Produktionsnaher lokaler Stack
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml up -d --build
curl -fsS http://localhost/healthz
```

## Verboten

- Dataclasses oder handgeschriebene Inline-Schemas für API-Verträge
- lokale Provider-Detection-Heuristiken neben der Registry
- produktive Verwendung des Legacy-`ModelPicker.vue` nach Slice 7.6d
- API-Keys oder Secrets in Code, Logs, Fixtures oder Dokumentation
- neue Query-Tokens `?token=`; URL-gebundene Auth nur über signierte Tickets
- `print()` in Produktivcode statt strukturiertem Logging
- hartkodierte UI-Texte statt `vue-i18n`
- hartkodierte CAMEL/OASIS-Kontextlimits statt zentraler Resolver
- neue CVE-Ausnahmen ohne Issue, Owner, Deadline und Hardstop
- `apt`; auf Debian/Ubuntu `nala` verwenden

## Wichtige Referenzen

- [`docs/STATUS.md`](docs/STATUS.md) – verifizierter Istzustand, Testzahlen, Gates
- [`PLAN.md`](PLAN.md) – priorisierte Zukunft und Slice-Reihenfolge
- [`docs/epics/onboarding-provider-unification/`](docs/epics/onboarding-provider-unification/) – aktive Epic-Unterlagen
- [`docs/epics/e2e-smoke-specs/`](docs/epics/e2e-smoke-specs/) – E2E-Defektanalyse
- [`docs/dependency-risk-register.md`](docs/dependency-risk-register.md) – Security-Hardstops
- [`CHANGELOG.md`](CHANGELOG.md) – ausgelieferte Änderungen
- [`CLAUDE.md`](CLAUDE.md) – Claude-spezifische Hinweise

## Knowledge Graph

Wenn `graphify-out/graph.json` vorhanden ist, bei Codebase-Fragen zuerst eine gezielte
Graph-Abfrage verwenden. Nach strukturellen Codeänderungen `graphify update .` ausführen.
Graphresultate ersetzen weder direkte Codeprüfung noch Tests.