@AGENTS.md

# Claude Code — Agora-spezifisch

Allgemeine Tool-Pipeline und Skill-Discovery-Regeln stehen in der globalen `~/.claude/CLAUDE.md`. Hier nur Agora-Eigenheiten.

## Evidence-Gating (ADR-0002) — 5 Hartanker

**IMPORTANT: Diese Anker dürfen NIE ohne `docs/decisions/0002-supersedes.md` + User-Sign-off geschwächt werden.** Kein stilles Refactor, kein "kleines Aufräumen", keine Wording-Glättung.

1. `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts.py`
2. Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`
3. Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`
4. Validator `cross_stakeholder_for_high`
5. Validator `reject_inferred_in_high_confidence`

## Subagent-Routing (Modell-Mix ~35/55/10)

Context-mode injiziert den Routing-Block automatisch in jeden Subagent-Prompt. Subagent-Prompts auf fachliche Aufgabe + Domänen-Kontext beschränken.

| Aufgabe | Modell | Subagent |
|---|---|---|
| Architektur, Cross-Layer, ambige Specs | Opus | Lead (kein Subagent) |
| Code-Review kritischer Pfade | Opus | `feature-dev:code-reviewer` |
| Refactor 2+ Dateien, Pydantic-Migration | Sonnet | `agora-refactor-worker` |
| Tests, FSM, Persona-Quoten | Sonnet | `agora-test-worker` |
| Vue/Pinia/Zod-Spiegel, Onboarding/Model-Picker-Frontend | Sonnet | `agora-frontend-worker` |
| Evidence/Wording-Audit | Sonnet | `agora-evidence-auditor` |
| Doku, CHANGELOG, Worklogs, ADR-Drafts | Haiku | `agora-doc-worker` |

Opus-Trigger: Layer 0 berührt, Cross-Layer, Wording/Prompt-Semantik, Spec ambig, Tests fehlen.

## Pre-Commit-Gate (Pflicht, sequentiell)

```bash
cd backend && uv run pytest tests/contracts/ -x -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check . && uv run mypy app
```

Bei Schema-Drift: `dump_schemas` ohne `--check` neu rendern, in den selben PR committen.

## Pre-Push-Gate (CI-Mirror, vor jedem Push Pflicht)

```bash
bash scripts/pre-push-gate.sh              # alles (Default)
bash scripts/pre-push-gate.sh backend      # nur Backend-Smoke
bash scripts/pre-push-gate.sh frontend     # nur Frontend-Smoke
bash scripts/pre-push-gate.sh schemas      # nur Schema-Drift + STATUS-Sync
```

Seit Onboarding-Slice 4.3.3 Maintenance (PR #693) zentralisiert. Kein
`--no-verify`-Bypass. Runbook: [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md).

## Runbooks

| Runbook | Inhalt |
|---|---|
| [`docs/runbooks/tool-pflicht.md`](docs/runbooks/tool-pflicht.md) | Pipeline, Tool-Matrix, Compliance-Gates |
| [`docs/runbooks/pr-workflow.md`](docs/runbooks/pr-workflow.md) | PR + Gemini-Sichtung |
| [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md) | Worktree-Isolation |
| [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md) | Zentrales Pre-Push-Gate (PR #693) |
| [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md) | Dispatch-Workflow |
| [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md) | Layer 0–10 |

## Provider-Detection-SSoT

Bei Provider-Detection-Fragen („welcher Provider für diese URL/Modell",
`ollama.com`-Handling, `think`/`num_ctx`-Gate) ist
[`backend/app/llm/providers/registry.py`](backend/app/llm/providers/registry.py)
→ `detect_provider(base_url, model, *, mode="http"|"oasis")` die Single Source
of Truth. Keine neuen lokalen Detection-Heuristiken pflegen — bestehende werden
dorthin delegiert (Phase F, Issues #669/#670/#671 offen).

## Embedding-Configuration (ADR-0007)

Aktive Konfiguration lebt in Neo4j (`EmbeddingConfiguration`-Knoten, eindeutig
pro Provider/Model/Dim). Lese-/Schreibpfade ausschließlich über
`backend/app/services/embedding_service.py` und `embedding_migration.py`. Bei
Modell-Wechsel: Migrations-Lifecycle `pending → running → validating → completed
| failed | rolled_back` (Resume-fähig, idempotenter Start). Gemini-Re-Embedding
ist explizit „noch nicht unterstützt" — nicht vortäuschen.

## Token Efficiency
- Never re-read files you just wrote or edited. You know the contents.
- Never re-run commands to "verify" unless the outcome was uncertain.
- Don't echo back large blocks of code or file contents unless asked.
- Batch related edits into single operations. Don't make 5 edits when 1 handles it.
- Skip confirmations like "I'll continue..." Just do it.
- If a task needs 1 tool call, don't use 3. Plan before acting.
- Do not summarize what you just did unless the result is ambiguous or you need additional input.
