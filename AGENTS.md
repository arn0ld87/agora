# AGENTS.md

Verbindliche Regeln fuer Codex, Claude Code und jede andere Agent-Runtime in diesem Repository.

## Projekt

Agora: lokale Multi-Agent-Analyseplattform fuer simulierte DACH-Stakeholder-Reaktionen. Flask/Python 3.14, Pydantic v2, Vue 3/TypeScript, Neo4j, Redis. Single User, `0.9.5` Stability Beta, Ziel `1.0.0`.

## Contracts-first

Jede Aenderung beginnt beim Vertrag (`backend/app/contracts/`), nie beim Consumer. Kein Dataclass, kein Inline-Schema, kein handgeschriebenes Dict fuer API-Grenzen.

## Arbeitsweise

1. Eigener Branch, atomarer PR. Nie direkt auf `main`.
2. Jeder Verhaltensfix bringt einen Regressionstest mit.
3. Vor Push: `bash scripts/pre-push-gate.sh [backend|frontend|schemas]`.
4. Changelog-Fragment in `changelog.d/<nr>-<slug>.md` — nie `CHANGELOG.md` direkt.
5. Istzustand in `docs/STATUS.md` synchronisieren (Test-Zaehler ausgenommen).

## Verboten

- Secrets in Code, Logs, Fixtures, Dokumentation
- `--no-verify` ohne explizite Freigabe
- Provider-Detection-Heuristiken neben `registry.py::detect_provider`
- `print()` statt strukturiertem Logging
- Abgeschwaechte Assertions / globale Skips um Tests gruen zu machen
- Neue Produktbereiche ausserhalb der aktuellen Roadmap-Stufe
- `apt` auf Debian/Ubuntu (verwende `nala`)

## Dokumentationshierarchie

| Prio | Datei | Inhalt |
|------|-------|--------|
| 1 | [`README.md`](README.md) | Produkt, Setup, Release-Linie |
| 2 | [`docs/STATUS.md`](docs/STATUS.md) | verifizierter Istzustand |
| 3 | [`ROADMAP.md`](ROADMAP.md) | Release-Reihenfolge und Freigabekriterien |
| 4 | [GitHub Issues](https://github.com/arn0ld87/agora/issues) | ausfuehrbare Tasks |

Lade bei Bedarf (nicht staendig im Kontext):

- [`CONTEXT.md`](CONTEXT.md) — Laufzeit-Mechanik, Artefaktformen, Evidence-Modell. Laden bei: Run-Beobachtung, -Auswertung, -Debugging, Evidence-Arbeit.
- [`docs/agents/architecture-ssot.md`](docs/agents/architecture-ssot.md) — Single-Sources-of-Truth fuer Vertraege, Provider, Routing. Laden bei: Architektur- oder Vertragsfragen.
- [`docs/agents/commands.md`](docs/agents/commands.md) — Setup, Build, Pruefbefehle. Laden bei: Ersteinrichtung oder unbekanntem Befehl.
- [`docs/agents/release-priority.md`](docs/agents/release-priority.md) — aktuelle Milestone-Prioritaet. Laden bei: Priorisierungsfragen.
- [`docs/agents/tool-pipeline.md`](docs/agents/tool-pipeline.md) — Tool-Reihenfolge und Token-Effizienz. Laden bei: grossflaechiger Codebase-Analyse.
- [`docs/decisions/`](docs/decisions/) — ADRs. Laden wenn eine Architekturentscheidung beruehrt wird.
- [`docs/runbooks/`](docs/runbooks/) — Operative Anleitungen (PR-Workflow, Pre-Push-Gate, Worktree-Strategie, Subagent-Routing).

## Code-Review-Graph (CRG)

Dieses Projekt hat einen persistenten Knowledge Graph. Graph-Tools VOR Grep/Glob/Read verwenden.

| Aufgabe | Tool |
|---------|------|
| Code finden | `semantic_search_nodes` |
| Aenderungs-Impact | `get_impact_radius` |
| Code-Review | `detect_changes` + `get_review_context` |
| Abhaengigkeiten | `query_graph` (callers_of/callees_of/imports_of/tests_for) |
| Architektur | `get_architecture_overview` + `list_communities` |
| Refactoring planen | `refactor_tool` |

Grep/Glob/Read nur als Fallback wenn der Graph die Information nicht hat.
