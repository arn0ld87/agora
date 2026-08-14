@AGENTS.md

# Claude Code — Agora-spezifisch

Allgemeine Tool-Pipeline und Skill-Discovery-Regeln stehen in der globalen `~/.claude/CLAUDE.md`. Hier nur Agora-Eigenheiten.

## Evidence-Gating (ADR-0002) — 5 Hartanker

**IMPORTANT: Diese Anker dürfen NIE ohne `docs/decisions/0002-supersedes.md` + User-Sign-off geschwächt werden.** Kein stilles Refactor, kein "kleines Aufräumen", keine Wording-Glättung.

1. `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts/sections.py`
2. Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`
3. Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`
4. Validator `cross_stakeholder_for_high`
5. Validator `reject_inferred_in_high_confidence`

## Issue-Orchestrierung

- `/agora-next-task`: genau ein release-relevantes Issue, ein isolierter Worker, ein lokaler Commit, Review, anschließend PR.
- `/agora-batch-issues`: maximal zwei nachweislich unabhängige Issues parallel; jedes Issue bleibt in eigenem Worktree, Commit und PR.
- Schreibende Worker verwenden `isolation: worktree`, pushen nicht und erzeugen genau einen lokalen Commit.
- Der Lead verifiziert Diff, Tests und Gate selbst. Worker-Zusammenfassungen gelten nicht als Nachweis.
- Vor Push und PR gilt ein **abgestuftes Review-Gate**:
  - **Regelfall — grünes Gate genügt.** Ein Issue-Commit braucht weder Reviewer-Subagent noch Nachweistext im PR. Erforderlich ist genau zweierlei: ein Regressionstest, der den Defekt trifft, und ein grünes `pre-push-gate.sh`. Dass der Test vor dem Fix fehlschlägt, prüft man beim Schreiben einmal lokal — das kostet einen Testlauf und fängt genau die Fehlerklasse, bei der #961, #966 und #985 nacheinander denselben Defekt am falschen Codepfad adressiert haben. Mehr als dieser eine Lauf ist nicht verlangt.
  - **Was ausdrücklich NICHT verlangt ist.** Kein RED/GREEN-Protokoll im PR-Text. Keine Mutationstests, kein absichtliches Kaputtmachen von Code zur Gegenprobe. Keine Einzelantwort auf Review-Bot-Kommentare. Keine Beweisführung, die länger dauert als der Fix selbst — bei Ein-Datei-Fixes, Schlüsseltausch, Tippfehlern und Doku-Änderungen entfällt jede zusätzliche Dokumentation.
  - **Review-Bots (CodeRabbit, Codex).** Einmal sichten, echte Blocker fixen, Rest ignorieren oder als Issue auslagern. Kommentare werden nicht einzeln beantwortet und nicht einzeln abgearbeitet; ein Bot-Kommentar ist ein Hinweis, kein Auftrag.
  - **Reviewer-Subagent — optional, nicht verpflichtend.** Auch bei Lead-Triggern (siehe [Subagent-Routing](#subagent-routing)) ist kein read-only Reviewer vorgeschrieben. Der Lead zieht einen hinzu, wenn er den Diff selbst nicht sicher beurteilen kann — etwa bei einer Schema- oder Migrationsänderung mit unklarer Rückwärtskompatibilität. Ein ausbleibendes `APPROVE` blockiert nichts mehr; die Entscheidung liegt beim Lead.

  **Ist-Zustand Reviewer:** der `/agora-next-task`-Skripttext ruft `agora-opus-reviewer` auf (Agent-Frontmatter: `model: opus`, echtes Claude-Opus) — nicht `agora-reviewer-m3`. Beide Reviewer-Definitionen existieren parallel (`.claude/agents/agora-opus-reviewer.md` und `.claude/agents/agora-reviewer-m3.md`); welche final bleibt, ist noch nicht entschieden ([#803](https://github.com/arn0ld87/agora/issues/803)). **Solange [#802](https://github.com/arn0ld87/agora/issues/802) offen ist, gilt eine leere Reviewer-Rückgabe als fehlgeschlagenes Review, nicht als Freigabe.**
- Keine Agent Teams für normale Issue-Arbeit. Subagenten reichen aus und halten die Kontexte getrennt.

## Subagent-Routing

Für jede Rolle existieren aktuell zwei parallele Agent-Definitionen unter `.claude/agents/`: eine mit `-m3`-Suffix und eine ohne. Issue [#803](https://github.com/arn0ld87/agora/issues/803) trackt die Konsolidierung dieser Dopplung — bis dahin sind beide Varianten gültige, registrierte Subagent-Typen. Diese Tabelle nennt die laut Routing-Absicht **bevorzugte** (`-m3`) Variante; welche ein konkreter Skript-/Slash-Command-Text tatsächlich aufruft, kann davon abweichen (siehe Hinweis oben zu `agora-opus-reviewer`) — im Zweifel gilt, was der jeweilige Skripttext wörtlich benennt.

**Der `-m3`-Suffix ist seit dem 31.07.2026 nur noch ein historischer Name, keine Modellangabe.** Die Definitionen trugen `model: MiniMax-M3`; dieses Modell ist in einer regulären Claude-Code-Session nicht auflösbar, jeder Dispatch brach sofort ab. Sie laufen jetzt auf Anthropic-Modellen. Damit unterscheiden sich die Paare fachlich nicht mehr — genau das ist der Gegenstand von #803. MiniMax-M3 bleibt über eine eigene Claude-Code-Instanz gegen `api.minimax.io/anthropic` nutzbar, nicht als `subagent_type` innerhalb einer laufenden Session.

| Aufgabe | Bevorzugtes Modell | Bevorzugter Subagent |
|---|---|---|
| Architektur, Cross-Layer, ambige Specs | Lead-Modell | kein Implementer-Subagent |
| Abschlussreview eines Issue-Commits (nur bei Lead-Trigger) | `opus` | `agora-reviewer-m3` |
| Backend-Refactor, Pydantic, Provider, Persistenz | `sonnet` | `agora-refactor-worker-m3` |
| Tests, FSM, E2E, Persona-Quoten | `sonnet` | `agora-test-worker-m3` |
| Vue, Pinia, Zod, A11y | `sonnet` | `agora-frontend-worker-m3` |
| Evidence/Wording-Audit | `sonnet` | `agora-evidence-auditor-m3` |
| Doku, CHANGELOG, Worklogs, ADR-Drafts | `sonnet` | `agora-doc-worker-m3` |

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
uv run ruff check .
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
uv run ruff check .
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
| [`docs/runbooks/e2e-local.md`](docs/runbooks/e2e-local.md) | Lokaler E2E-Lauf neben dem Dev-Stack |
| [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md) | Dispatch-, Parallelitäts- und Review-Workflow |
| [`docs/runbooks/architecture-layers.md`](docs/runbooks/architecture-layers.md) | Layer 0–10 |

## Worktree-Pfad

**Pflicht für manuell angelegte Worktrees:** Alle per `git worktree add` erzeugten Agora-Worktrees liegen unter `/Volumes/T7/Worktrees/agora/<slice-id>/`. `/private/tmp` ist verboten. T7-Mount wird vor dem Anlegen verifiziert (`test -d /Volumes/T7`).

**Ausnahme — harness-isolierte Subagenten:** Worker mit `isolation: worktree` bekommen ihren Worktree von der Agent-Runtime unter `.claude/worktrees/agent-<id>/` zugewiesen (Branch `worktree-agent-<id>`). Das ist zulässig und der Normalfall. Ein PreToolUse-Hook sperrt für solche Worker jede Git-Operation außerhalb ihres eigenen Worktrees — ein vom Lead auf T7 vorbereiteter Pfad ist für sie unerreichbar. Der Lead bereitet für diese Worker deshalb **keinen** T7-Worktree vor und gibt keinen Zielpfad im Briefing vor; er übernimmt den Commit anschließend per `git cherry-pick` auf einen sprechenden Branch.

Volle Strategie in [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md).

## Provider-Detection-SSoT

Bei Provider-Detection-Fragen („welcher Provider für diese URL/Modell", `ollama.com`-Handling, `think`/`num_ctx`-Gate) ist [`backend/app/llm/providers/registry.py`](backend/app/llm/providers/registry.py) → `detect_provider(base_url, model, *, mode="http"|"oasis")` die Single Source of Truth. Keine neuen lokalen Detection-Heuristiken pflegen.

## Embedding-Configuration (ADR-0007)

Aktive Konfiguration wird vom [`EmbeddingConfigurationStore`](backend/app/services/embedding_configuration_store.py) in einer flachen JSON-Datei unter `AGORA_DATA_DIR/embedding_configurations.json` persistiert (`flock`-Sperre, atomares Write via `os.replace`, Datei-Modus 0600) — **nicht** in Neo4j. Index-Versionen liegen in einer Sibling-JSON (`embedding_index_versions.json`). `EmbeddingConfiguration` ist ein Pydantic-Vertrag ([`backend/app/contracts/embedding_contract.py`](backend/app/contracts/embedding_contract.py)), kein Neo4j-Knoten. Lese-/Schreibpfade über `backend/app/services/embedding_service.py` und `embedding_migration.py`; Service-Logik in `backend/app/services/embedding_configurations/service.py`, Legacy-Read-Only-Adapter in `…/legacy.py`. Bei Modell-Wechsel: Migrations-Lifecycle `pending → running → validating → completed | failed | rolled_back`. Gemini-Re-Embedding ist explizit „noch nicht unterstützt“ — nicht vortäuschen.

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

[`CONTEXT.md`](CONTEXT.md) existiert seit dem 11.08.2026 und beschreibt die **Laufzeit-Mechanik**: vier Laufzeitphasen plus Run-Registry mit Artefakt-IDs, die vollständige Report-Pipeline (Planning → Section-ReAct mit parallelen Tool-Calls → Phase-Timing/Evidence-Binding), den `interview_agents`-Mechanismus, das Evidence-Modell mit seinen zwei getrennten Prüfstellen (`claim_extraction_and_evidence_binding` gegen `verify_prose`), Artefaktpfade im Container, das Sim-DB-Schema samt der `original_post_id`-Auswertungsfalle, das getrennte Embedding-Routing und eine Liste bekannter Fehlerbilder, die **nicht** als Neufund zu melden sind. Vor jeder Lauf-Beobachtung, -Auswertung oder -Fehlersuche lesen.

Verbindliche Quelle für Aufgaben bleibt die Reihenfolge aus [`AGENTS.md`](AGENTS.md): `README.md` → `docs/STATUS.md` → `ROADMAP.md` → GitHub Issues.

## Claude-Code-Konfiguration

- `.claude/settings.json` ist eine bewusst gepflegte und versionierte Projektdatei.
- Die vereinfachten Wildcard-Regeln sind beabsichtigt und dürfen nicht automatisch wieder in alte Einzelregeln zerlegt oder zurückgesetzt werden.
- Änderungen an `.claude/settings.json` nur auf ausdrückliche Anweisung des Nutzers.
- `.claude/settings.local.json` ist maschinenspezifisch, geheimnisfrei und nicht zu committen.

### Keine Claude-Code-Hooks in diesem Repo

**Das Repo definiert bewusst keine `hooks` in `.claude/settings.json`.** Frühere `Stop`- (pytest nach jeder Antwort) und `PostToolUse`-Hooks (ruff nach jedem `.py`-Edit) sind am 02.08.2026 entfernt worden, weil sie pro Turn eine vollständige Test-Suite bzw. pro Edit einen `uv`-Kaltstart auslösten und die Sitzung auf einem 16-GB-Rechner spürbar ausgebremst haben.

Das ändert nichts an den Pflichten: Das [Pre-Commit-Gate](#pre-commit-gate-pflicht-sequentiell-scope-abhängig) und das [Pre-Push-Gate](#pre-push-gate-ci-mirror-vor-jedem-push-pflicht) gelten unverändert und werden **manuell** ausgeführt. Die CI-Statuschecks auf `main` sind ohnehin die harte Absicherung. Wer Automatik will, hängt sie an einen Git-`pre-push`-Hook oder an CI — nicht an einen Claude-Code-Turn.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
