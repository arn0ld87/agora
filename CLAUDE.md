@AGENTS.md

# Claude Code — Agora

## Evidence-Gating (ADR-0002) — 5 Hartanker

**IMPORTANT: Diese Anker duerfen NIE ohne `docs/decisions/0002-supersedes.md` + User-Sign-off geschwaecht werden.**

1. `<evidence_gating priority="hard">`-Block in `backend/app/services/report_prompts/sections.py:31`
2. Hedge-Snapshot `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`
3. Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`
4. Validator `cross_stakeholder_for_high`
5. Validator `reject_inferred_in_high_confidence`

## Issue-Orchestrierung

- `/agora-next-task`: ein Issue, ein Worker (`isolation: worktree`), ein lokaler Commit, dann PR.
- `/agora-batch-issues`: maximal zwei unabhaengige Issues parallel, je eigener Worktree und PR.
- Worker pushen nicht. Der Lead verifiziert Diff, Tests und Gate selbst.
- **Review-Gate:** Regressionstest + gruenes `pre-push-gate.sh` genuegen fuer die lokale Schnellpruefung. CI-Smoke-Gates bleiben erforderlich; fuer lokale Vollverifikation `GATE_FULL=1` setzen. Kein RED/GREEN-Protokoll, keine Mutationstests, keine Bot-Kommentar-Einzelantworten.
- **Reviewer-Subagent:** optional. Der Lead zieht einen hinzu wenn der Diff unklar ist (Schema-Migration, Rueckwaertskompatibilitaet). Ein ausbleibendes APPROVE blockiert nicht.
- **Ist-Zustand:** `/agora-next-task` ruft `agora-opus-reviewer` auf. Beide Varianten (mit/ohne `-m3`) existieren parallel bis [#803](https://github.com/arn0ld87/agora/issues/803) konsolidiert.

## Subagent-Routing

| Aufgabe | Modell | Subagent |
|---------|--------|----------|
| Architektur, Cross-Layer, ambige Specs | Lead | keiner |
| Abschlussreview (bei Lead-Trigger) | `opus` | `agora-opus-reviewer` |
| Backend-Refactor, Pydantic, Provider | `sonnet` | `agora-refactor-worker-m3` |
| Tests, FSM, E2E, Persona-Quoten | `sonnet` | `agora-test-worker-m3` |
| Vue, Pinia, Zod, A11y | `sonnet` | `agora-frontend-worker-m3` |
| Evidence/Wording-Audit | `sonnet` | `agora-evidence-auditor-m3` |
| Doku, CHANGELOG, ADR-Drafts | `sonnet` | `agora-doc-worker-m3` |

Lead-Trigger: Layer 0, Cross-Layer, Prompt-Semantik, Security, Auth, Secrets, Datenmigration, Provider-Routing, ambige Specs.

## Parallelitaet

Zwei Issues parallel nur wenn: keine Abhaengigkeit, keine geteilten Dateien/Contracts, unabhaengig testbar. Bei Unsicherheit: eins nach dem anderen. Max zwei schreibende Worker gleichzeitig.

## Pre-Commit-Gate

Scope-abhaengig, sequentiell mit Exit 0:

```bash
# Backend
cd backend && uv run pytest tests/contracts/ -x -q && uv run python -m app.contracts.dump_schemas --check && uv run ruff check . && uv run mypy app

# Schemas-only (kein Ruff/mypy)
cd backend && uv run pytest tests/contracts/ -x -q && uv run python -m app.contracts.dump_schemas --check

# Frontend
cd frontend && bun run test && bun run check

# Cross-Layer: beide Bloecke nacheinander
```

Bei Schema-Drift: `dump_schemas` ohne `--check` rendern, in denselben Commit aufnehmen.

## Pre-Push-Gate

```bash
bash scripts/pre-push-gate.sh [backend|frontend|schemas]
```

Ohne Scope = vollstaendig. Runbook: [`docs/runbooks/pre-push-gate.md`](docs/runbooks/pre-push-gate.md).

## Worktree-Pfad

Manuell angelegte Worktrees: `/Volumes/T7/Worktrees/agora/<slice-id>/`. T7-Mount pruefen (`test -d /Volumes/T7`). Harness-isolierte Worker (`isolation: worktree`) nutzen `.claude/worktrees/agent-<id>/` — der Lead legt fuer sie keinen T7-Pfad an.

## Architektur-SSoT (Schnellreferenz)

| Konzept | Kanonischer Pfad |
|---------|-----------------|
| API-Vertraege | `backend/app/contracts/` (Pydantic v2) |
| Provider-Detection | `backend/app/llm/providers/registry.py::detect_provider` |
| Strukturierte LLM-Calls | `backend/app/llm/client.py::LLMClient.chat_json` mit Pydantic-Schema |
| Embedding-Config | `backend/app/services/embedding_configuration_store.py` → JSON in `AGORA_DATA_DIR` |
| Frontend-Spiegel | `frontend/src/contracts/` + generierte `schemas/` |

Roher `OpenAI`-Client fuer JSON-Outputs ist verboten (umgeht Provider-Detection, strict-mode, Repair-Logik).

## Claude-Code-Konfiguration

- `.claude/settings.json` ist versioniert und bewusst gepflegt. Aenderungen nur auf Anweisung.
- Keine Hooks in diesem Repo. Pre-Commit- und Pre-Push-Gates werden manuell ausgefuehrt.
- `.claude/settings.local.json` ist maschinenspezifisch und nicht zu committen.
