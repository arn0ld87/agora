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

## Issue-Orchestrierung

- `/agora-next-task`: genau ein release-relevantes Issue, ein isolierter Worker, ein lokaler Commit, Opus-Review, anschließend Draft-PR.
- `/agora-batch-issues`: maximal zwei nachweislich unabhängige Issues parallel; jedes Issue bleibt in eigenem Worktree, Commit und Draft-PR.
- Schreibende Worker verwenden `isolation: worktree`, pushen nicht und erzeugen genau einen lokalen Commit.
- Der Lead verifiziert Diff, Tests und Gate selbst. Worker-Zusammenfassungen gelten nicht als Nachweis.
- Vor Push und PR prüft `agora-opus-reviewer` read-only den Issue-Commit. Nur `APPROVE` erlaubt die Veröffentlichung.
- Keine Agent Teams für normale Issue-Arbeit. Subagenten reichen aus und halten die Kontexte getrennt.

## Subagent-Routing

| Aufgabe | Modell | Subagent |
|---|---|---|
| Architektur, Cross-Layer, ambige Specs | Opus oder Lead | kein Implementer-Subagent |
| Abschlussreview eines Issue-Commits | Opus high | `agora-opus-reviewer` |
| Backend-Refactor, Pydantic, Provider, Persistenz | Sonnet high | `agora-refactor-worker` |
| Tests, FSM, E2E, Persona-Quoten | Sonnet medium | `agora-test-worker` |
| Vue, Pinia, Zod, A11y | Sonnet medium | `agora-frontend-worker` |
| Evidence/Wording-Audit | Sonnet medium | `agora-evidence-auditor` |
| Doku, CHANGELOG, Worklogs, ADR-Drafts | Haiku low | `agora-doc-worker` |

Lead-Trigger: Layer 0, Cross-Layer, Wording/Prompt-Semantik, Security, Auth, Secrets, Datenmigration, Provider-Routing, ambige Specs oder fehlende Tests.

## Parallelitätsregeln

Zwei Issues dürfen nur parallel laufen, wenn:

- keine Parent-/Child- oder Blocked-by-Beziehung besteht,
- keine gleichen oder eng gekoppelten Dateien betroffen sind,
- keine gemeinsamen Contracts, Schemas oder Migrationen geändert werden,
- keine gemeinsame Fehlerursache wahrscheinlich ist,
- jedes Issue unabhängig testbar und rückrollbar ist.

Bei Unsicherheit nur ein Issue ausführen. Maximal zwei schreibende Worker gleichzeitig.

## Pre-Commit-Gate (Pflicht, sequentiell, scope-abhängig)

Backend-Scope, sequentiell mit Exit 0 (ein einziger Wechsel nach `backend`):

```bash
cd backend
uv run pytest tests/contracts/ -x -q
uv run python -m app.contracts.dump_schemas --check
uv run ruff check app/ tests/
uv run mypy app
```

Schemas-/Contracts-Scope — nur Contract-Tests und Schema-Check, kein Ruff, kein mypy:

```bash
cd backend
uv run pytest tests/contracts/ -x -q
uv run python -m app.contracts.dump_schemas --check
```

Reiner Frontend-Scope führt diese Backend-Prüfungen nicht aus, sondern:

```bash
cd frontend
bun run test
bun run check
```

Cross-Layer-Scope führt beide Blöcke nacheinander aus:

```bash
cd backend
uv run pytest tests/contracts/ -x -q
uv run python -m app.contracts.dump_schemas --check
uv run ruff check app/ tests/
uv run mypy app
cd ../frontend
bun run test
bun run check
```

Maßgeblich ist die Scope-Matrix in [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md).

Bei Schema-Drift: `dump_schemas` ohne `--check` neu rendern, in denselben Issue-Commit aufnehmen.

## Pre-Push-Gate (CI-Mirror, vor jedem Push Pflicht)

Genau ein zum Scope passender Pfad — nicht alle:

```bash
bash scripts/pre-push-gate.sh              # Cross-Layer / vollständig
bash scripts/pre-push-gate.sh backend      # nur Backend-Smoke
bash scripts/pre-push-gate.sh frontend     # nur Frontend-Smoke
bash scripts/pre-push-gate.sh schemas      # nur Schema-Drift + STATUS-Sync
```

Kein `--no-verify`-Bypass. Runbook: [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md).

## Runbooks

| Runbook | Inhalt |
|---|---|
| [`docs/runbooks/tool-pflicht.md`](docs/runbooks/tool-pflicht.md) | Pipeline, Tool-Matrix, Compliance-Gates |
| [`docs/runbooks/pr-workflow.md`](docs/runbooks/pr-workflow.md) | PR + Gemini-Sichtung |
| [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md) | Worktree-Isolation |
| [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md) | Zentrales Pre-Push-Gate |
| [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md) | Dispatch-, Parallelitäts- und Review-Workflow |
| [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md) | Layer 0–10 |

## Provider-Detection-SSoT

Bei Provider-Detection-Fragen („welcher Provider für diese URL/Modell", `ollama.com`-Handling, `think`/`num_ctx`-Gate) ist [`backend/app/llm/providers/registry.py`](backend/app/llm/providers/registry.py) → `detect_provider(base_url, model, *, mode="http"|"oasis")` die Single Source of Truth. Keine neuen lokalen Detection-Heuristiken pflegen.

## Embedding-Configuration (ADR-0007)

Aktive Konfiguration lebt in Neo4j (`EmbeddingConfiguration`-Knoten, eindeutig pro Provider/Model/Dim). Lese-/Schreibpfade ausschließlich über `backend/app/services/embedding_service.py` und `embedding_migration.py`. Bei Modell-Wechsel: Migrations-Lifecycle `pending → running → validating → completed | failed | rolled_back`. Gemini-Re-Embedding ist explizit „noch nicht unterstützt“ — nicht vortäuschen.

## Token Efficiency

- Never re-read files you just wrote or edited. You know the contents.
- Never re-run commands unless a frischer Verifikationsnachweis erforderlich ist oder das Ergebnis unsicher war.
- Don't echo large blocks of code or file contents unless asked.
- Batch related edits into single operations.
- Skip confirmations like "I'll continue...".
- If a task needs one tool call, don't use three.
- Do not summarize implementation details beyond Commit, Diff, Tests, Gate, Review and Risiken.
