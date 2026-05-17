@AGENTS.md

## Claude Code — Spezifische Ergänzungen

Diese Datei ergänzt [`AGENTS.md`](AGENTS.md) um Claude-Code-eigene Fähigkeiten.
Allgemeine Regeln (Verbote, Commands, Konfiguration) stehen in AGENTS.md.

## CRITICAL: Tool-Pipeline (harmonisiert mit context-mode)

**Diese Reihenfolge ist bindend.** Vor jedem Read/Bash-Call MUSS diese Pipeline
durchlaufen sein:

```
code-review-graph → context7 → ctx_batch_execute → ctx_execute → Read/Bash
```

Context-mode ist die Execution-Layer — seine PreToolUse-Hooks greifen aktiv ein:
Bash ist auf git/fs/nav limitiert, Read nur zum Editieren, WebFetch für kleine Lookups.
Arbeite MIT diesen Regeln, nicht dagegen.

Detail: [`docs/runbooks/tool-pflicht.md`](docs/runbooks/tool-pflicht.md).

## CRITICAL: Skills vor Code-Exploration

Bevor du Code liest oder schreibst, prüfe die verfügbaren Skills.
Wenn auch nur 1 % Chance auf Match: invoken. Skills liefern WAS — context-mode definiert WIE.

Anti-Pattern (SOFORT STOPPEN):
- "Nur eine schnelle Frage" → Jede Frage = Aufgabe.
- "Ich schau erst in den Code" → Skills + context-mode zuerst.

## Evidence-Gating (ADR-0002) — 5 Hartanker

Diese Anker dürfen NIE ohne Supersedes-ADR + User-Sign-off geschwächt werden:

1. `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts.py`
2. Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`
3. Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`
4. Validator `cross_stakeholder_for_high`
5. Validator `reject_inferred_in_high_confidence`

Schwächungen verlangen `docs/decisions/0002-supersedes.md`, kein stilles Refactor.

## Subagent-Routing

Context-mode injiziert seinen Routing-Block automatisch in jeden Subagent-Prompt.
Subagent-Prompts sollen sich auf fachliche Aufgabe und Domänen-Kontext beschränken.

Ziel-Mix: ~35 % Opus, ~55 % Sonnet, ~10 % Haiku.

| Aufgabe | Modell | Subagent |
|---|---|---|
| Architektur, Cross-Layer, ambige Specs | Opus | Lead (kein Subagent) |
| Code-Review kritischer Pfade | Opus | `feature-dev:code-reviewer` |
| Refactor 2+ Dateien, Pydantic-Migration | Sonnet | `agora-refactor-worker` |
| Tests, FSM-Übergänge, Persona-Quoten | Sonnet | `agora-test-worker` |
| Vue/Pinia/Zod-Spiegel | Sonnet | `agora-frontend-worker` |
| Evidence/Wording-Audit | Sonnet | `agora-evidence-auditor` |
| Doku, CHANGELOG, Worklogs | Haiku | `agora-doc-worker` |

Opus-Trigger: Layer 0 berührt, mehrere Layer betroffen, Wording/Prompt-Semantik,
Spec ambig, Tests fehlen.

Detail: [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md).

## Verifikation vor Commit

```bash
cd backend && uv run pytest tests/contracts/ -x -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check . && uv run mypy app
```

## Wichtige Runbooks

| Runbook | Inhalt |
|---|---|
| [`docs/runbooks/tool-pflicht.md`](docs/runbooks/tool-pflicht.md) | Pipeline, Tool-Matrix, Compliance-Gates |
| [`docs/runbooks/pr-workflow.md`](docs/runbooks/pr-workflow.md) | PR-Workflow, Gemini-Sichtung |
| [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md) | Worktree-Isolation, Hygiene |
| [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md) | Dispatch-Workflow, Modell-Mix |
| [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md) | Layer 0–10, Status, Gotchas |
