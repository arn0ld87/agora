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

- `/agora-next-task`: genau ein release-relevantes Issue, ein isolierter Worker, ein lokaler Commit, Review, anschließend PR.
- `/agora-batch-issues`: maximal zwei nachweislich unabhängige Issues parallel; jedes Issue bleibt in eigenem Worktree, Commit und PR.
- Schreibende Worker verwenden `isolation: worktree`, pushen nicht und erzeugen genau einen lokalen Commit.
- Der Lead verifiziert Diff, Tests und Gate selbst. Worker-Zusammenfassungen gelten nicht als Nachweis.
- Vor Push und PR prüft ein read-only Reviewer den Issue-Commit. Nur `APPROVE` erlaubt die Veröffentlichung. **Aktueller Ist-Zustand:** der `/agora-next-task`-Skripttext ruft `agora-opus-reviewer` auf (Agent-Frontmatter: `model: opus`, echtes Claude-Opus) — nicht `agora-reviewer-m3`. Beide Reviewer-Definitionen existieren parallel (`.claude/agents/agora-opus-reviewer.md` und `.claude/agents/agora-reviewer-m3.md`); welche final bleibt, ist noch nicht entschieden.
- Keine Agent Teams für normale Issue-Arbeit. Subagenten reichen aus und halten die Kontexte getrennt.

## Subagent-Routing

Für jede Rolle existieren aktuell zwei parallele Agent-Definitionen unter `.claude/agents/`: eine mit `-m3`-Suffix (`model: MiniMax-M3`) und eine ohne Suffix (echte Anthropic-Modelle, z. B. `agora-refactor-worker` mit `model: sonnet`, `agora-opus-reviewer` mit `model: opus`). Issue [#803](https://github.com/arn0ld87/agora/issues/803) trackt die Konsolidierung dieser Dopplung — bis dahin sind beide Varianten gültige, registrierte Subagent-Typen. Diese Tabelle nennt die laut Routing-Absicht **bevorzugte** (`-m3`) Variante; welche ein konkreter Skript-/Slash-Command-Text tatsächlich aufruft, kann davon abweichen (siehe Hinweis oben zu `agora-opus-reviewer`) — im Zweifel gilt, was der jeweilige Skripttext wörtlich benennt.

| Aufgabe | Bevorzugtes Modell | Bevorzugter Subagent |
|---|---|---|
| Architektur, Cross-Layer, ambige Specs | Lead (MiniMax-M3) | kein Implementer-Subagent |
| Abschlussreview eines Issue-Commits | MiniMax-M3 | `agora-reviewer-m3` |
| Backend-Refactor, Pydantic, Provider, Persistenz | MiniMax-M3 | `agora-refactor-worker-m3` |
| Tests, FSM, E2E, Persona-Quoten | MiniMax-M3 | `agora-test-worker-m3` |
| Vue, Pinia, Zod, A11y | MiniMax-M3 | `agora-frontend-worker-m3` |
| Evidence/Wording-Audit | MiniMax-M3 | `agora-evidence-auditor-m3` |
| Doku, CHANGELOG, Worklogs, ADR-Drafts | MiniMax-M3 | `agora-doc-worker-m3` |

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

## Worktree-Pfad

**Pflicht:** Alle Agora-Worktrees liegen unter `/Volumes/T7/Worktrees/agora/<slice-id>/`. `/private/tmp` ist für Agora-Worktrees verboten — `git worktree add` ohne T7-Pfad wird vom Lead zurückgewiesen. T7-Mount wird vor dem Anlegen verifiziert (`test -d /Volumes/T7`). Volle Strategie in [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md).

## Provider-Detection-SSoT

Bei Provider-Detection-Fragen („welcher Provider für diese URL/Modell", `ollama.com`-Handling, `think`/`num_ctx`-Gate) ist [`backend/app/llm/providers/registry.py`](backend/app/llm/providers/registry.py) → `detect_provider(base_url, model, *, mode="http"|"oasis")` die Single Source of Truth. Keine neuen lokalen Detection-Heuristiken pflegen.

## Embedding-Configuration (ADR-0007)

Aktive Konfiguration lebt in Neo4j (`EmbeddingConfiguration`-Knoten, eindeutig pro Provider/Model/Dim). Lese-/Schreibpfade ausschließlich über `backend/app/services/embedding_service.py` und `embedding_migration.py`. Bei Modell-Wechsel: Migrations-Lifecycle `pending → running → validating → completed | failed | rolled_back`. Gemini-Re-Embedding ist explizit „noch nicht unterstützt“ — nicht vortäuschen.

## Structured-JSON-LLM-Calls (chat_json-SSoT)

**IMPORTANT:** Strukturierte LLM-Calls mit JSON-Output MÜSSEN über [`backend/app/llm/client.py::LLMClient.chat_json`](backend/app/llm/client.py) mit einem Pydantic-Schema laufen. Der rohe `OpenAI`-Client (`client.chat.completions.create`) darf nicht direkt für strukturierte JSON-Outputs verwendet werden — er umgeht Provider-Detection (MiniMax `thinking.type: disabled`), den strict-json_schema-Modus und die zentrale JSON-Repair-Logik. Legacy-Flags wie `LLM_DISABLE_JSON_MODE` nicht neu verwenden (werden vorübergehend noch aus Kompatibilitätsgründen unterstützt); das Pydantic-Schema macht sie obsolet.

## Token Efficiency
- Never re-read files you just wrote or edited. You know the contents.
- Never re-run commands to "verify" unless the outcome was uncertain.
- Don't echo back large blocks of code or file contents unless asked.
- Batch related edits into single operations. Don't make 5 edits when 1 handles it.
- Skip confirmations like "I'll continue..." Just do it.
- If a task needs 1 tool call, don't use 3. Plan before acting.
- Do not summarize what you just did unless the result is ambiguous or you need additional input.

## Agent Skills

Konfiguration für externe Skill-Sammlungen, die dieses Repository als Kontext lesen. Diese Dateien beschreiben nur, wie das Repo funktioniert — sie ersetzen keine Regel aus `AGENTS.md` oder diesem Dokument.

| Thema | Datei | Inhalt |
|---|---|---|
| Issue-Tracker | [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md) | Issues und PRDs liegen in GitHub Issues; `gh`-Konventionen für Lesen, Anlegen, Labeln und Schließen |
| Triage-Labels | [`docs/agents/triage-labels.md`](docs/agents/triage-labels.md) | die fünf kanonischen Labels `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` — unverändert übernommen |
| Domänen-Doku | [`docs/agents/domain.md`](docs/agents/domain.md) | Single-Context-Layout: ADRs unter `docs/decisions/`, optionales `CONTEXT.md` |

`CONTEXT.md` existiert derzeit nicht und wird erst angelegt, wenn tatsächlich Begriffe oder Entscheidungen festzuhalten sind. Sein Fehlen ist kein Defekt und wird nicht gemeldet.

Verbindliche Quelle für Aufgaben bleibt die Reihenfolge aus [`AGENTS.md`](AGENTS.md): `README.md` → `docs/STATUS.md` → `ROADMAP.md` → GitHub Issues.

## Claude-Code-Konfiguration

- `.claude/settings.json` ist eine bewusst gepflegte und versionierte Projektdatei.
- Die vereinfachten Wildcard-Regeln sind beabsichtigt und dürfen nicht automatisch wieder in alte Einzelregeln zerlegt oder zurückgesetzt werden.
- Änderungen an `.claude/settings.json` nur auf ausdrückliche Anweisung des Nutzers.
- `.claude/settings.local.json` ist maschinenspezifisch, geheimnisfrei und nicht zu committen.
