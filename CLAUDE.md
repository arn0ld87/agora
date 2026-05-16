# Agora — Onboarding für Claude Code

Diese Datei ist die Claude-spezifische Schwester zu [`AGENTS.md`](AGENTS.md). Sie ergänzt
Claude-eigene Eigenheiten (MCP-Tools, Slash-Commands, Subagent-Routing mit Modellmix) und referenziert für
den Rest die zentralen Runbooks unter [`docs/runbooks/`](docs/runbooks/).

## Was ist Agora?

Lokal-first Multi-Agent-Simulator für DACH-Zielgruppenreaktionen. Stack: **Flask + Pydantic v2 + Vue 3 +
Neo4j + Ollama + OASIS** (CAMEL-AI Subprozess). Status: v1.0.0 (2026-05-11), Layer-Status und Test-Counts
in [`docs/STATUS.md`](docs/STATUS.md).

## Pflicht-Reihenfolge (Tools vor Code)

`code-review-graph` → `context7` → `sequential-thinking` → `context-mode` → erst dann `Read`/`rg`/`Bash`.

Volle Pre-Flight-Checkliste, Tool-Tabelle, Anti-Pattern und Enforcement: [`docs/runbooks/tool-pflicht.md`](docs/runbooks/tool-pflicht.md).

Zusätzlich für Claude:

- **honcho-memory** bei jeder Frage über den User (Setup, Hardware, Präferenzen, Projekt-Historie).
- **episodic-memory:remembering-conversations** bei „wie hatten wir das damals gelöst", wiederkehrenden
  Workflows. Vor Code-Exploration aufrufen, nicht danach.
- **Skill-/Deferred-Tool-Liste der System-Reminder** zuerst scannen. Tool nur als Name sichtbar → über
  `ToolSearch query:"select:<name>"` laden, bevor „Tool fehlt" behauptet wird.

## Workflow-Regeln (Verweise auf Runbooks)

- **PR-Workflow** (Gemini-Sichtung, Findings-Behandlung, Merge-Regel): [`docs/runbooks/pr-workflow.md`](docs/runbooks/pr-workflow.md).
- **Worktree-Strategie** (Slice-Isolation, Multi-Slice-Epic): [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md).
- **Subagent-Briefing** (Pflichtinhalte, Verification-Gate): [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md).
- **Architektur-Layer + Pipeline** (Layer 0–10, Event-Bus, Production-Deployment, Gotchas): [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md).
- **Verbotsliste** (US-Marketing, Inline-Schemas, `?token=`-URLs, CAMEL-Floor): [`AGENTS.md`](AGENTS.md).

## Claude-spezifische Subagent-Routing-Mappe

Ziel-Mix: ~35 % Opus, ~55 % Sonnet, ~10 % Haiku. Bei Layer-0-Drift oder Wording-Glossar-Verstößen Senior-Review
trotz Token-Sparen.

| Aufgabe | Modell | Subagent | Anteil-Ziel |
|---|---|---|---|
| Architektur, Cross-Layer-Refactor, ambige Specs | Opus | (Lead, kein Subagent) | ~25 % |
| Code-Review kritischer Pfade (contracts, evidence_binder, report_agent) | Opus | `feature-dev:code-reviewer` | ~10 % |
| Refactor 2+ Dateien, Pydantic-Migration | Sonnet | `agora-refactor-worker` | ~25 % |
| Pydantic-Tests, FSM-Übergänge, Persona-Quoten | Sonnet | `agora-test-worker` | ~15 % |
| Vue/Pinia/Zod-Spiegel | Sonnet | `agora-frontend-worker` | ~10 % |
| Read-only Audit (Evidence, Wording-Glossar) | Sonnet | `agora-evidence-auditor` | ~5 % |
| Dokumentation, CHANGELOG, Worklogs | Haiku | `agora-doc-worker` | ~10 % |

### Opus-Trigger (überstimmen das Default-Routing)

- Layer-0 (Pydantic-Contracts) wird angefasst
- Mehrere Layer gleichzeitig betroffen
- Wording- oder Prompt-Semantik (Layer 2, Glossar v1)
- Spec ambig, Tests fehlen
- Pre-PR-Self-Review vor `gh pr create`

## Slash-Commands (`.claude/commands/`)

| Command | Zweck |
|---|---|
| `/agora-next-task` | Master-Orchestrator: pickt nächsten offenen Sub-Slice aus `PLAN.md`, dispatcht passenden Subagent, verifiziert, committet, pusht. |
| `/verify-after-subagent` | Pflicht-Verifikation nach jedem Subagent-Run (sequential gate). |
| `/fix-task-01..04-*` | Templates aus dem Layer-0–4-Refactor (abgearbeitet, archivierbar). |

## Verifikations-Disziplin

Bevor Variablen umbenannt oder Pfade angelegt werden, immer erst prüfen:

```bash
rg -n "<symbol>" backend/
find . -path "*<pattern>*"
```

LLM-Vorschläge sind oft präzise, aber Variablen-Namen sind manchmal halluziniert. Verifiziere immer.

## Hartanker — Evidence-Gating (ADR-0002)

Fünf Anker dürfen ohne Supersedes-ADR + User-Sign-off **nicht** geschwächt werden:

1. `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts.py`
2. Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`
3. Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`
4. Validator `cross_stakeholder_for_high`
5. Validator `reject_inferred_in_high_confidence`

Schwächungen („cross_stakeholder von 2 auf 1 absenken", „Hedge-Liste verkürzen", „inferred aus Enum
entfernen", „priority=hard durch soft-hint ersetzen") verlangen `0002-supersedes.md`, kein stilles
Refactor. Detail: [`docs/decisions/0002-evidence-gating.md`](docs/decisions/0002-evidence-gating.md).

## Token-Effizienz

- Niemals Files re-lesen, die gerade geschrieben oder editiert wurden — Edit/Write erkennen Drift selbst
- Keine Verifikations-Reruns von Commands, deren Ergebnis eindeutig war
- Große File-Inhalte nicht echo-zurückgeben außer auf Anfrage
- Verwandte Edits in einer Operation bündeln statt fünf separate Edits
- Keine Confirm-Strings wie „Ich fahre fort…" — direkt arbeiten
- Eine Tool-Aufgabe = ein Tool-Call. Vorher planen statt drei Versuche.

## Referenz

- [`AGENTS.md`](AGENTS.md) — zentrale Agent-Konfiguration
- [`docs/runbooks/`](docs/runbooks/) — Detail-Runbooks
- [`docs/STATUS.md`](docs/STATUS.md) — Test-Counts, Coverage, Milestones
- [`PLAN.md`](PLAN.md) — Operativer Slice-Plan
- [`docs/decisions/`](docs/decisions/) — ADRs
- [`CHANGELOG.md`](CHANGELOG.md) — Release-Notes
