# plan.heuristic — 2026-05-17

> **Zweck:** Aktive Heuristik für Slice-Routing, Modell-Mix und Akzeptanz-Gates
> nach Abschluss der Observability/Run-Control/Model-Picker-Welle. Ablösung von
> [`docs/archive/plans/plan.heuristic.md`](../archive/plans/plan.heuristic.md)
> (Stand 2026-05-04) und [`plan.heuristic-mai.md`](../archive/plans/plan.heuristic-mai.md).

Begleitet [`PLAN.md`](../../PLAN.md) und [`docs/STATUS.md`](../STATUS.md). Verbindlich
sind die Hartanker aus [`docs/decisions/0002-evidence-gating.md`](../decisions/0002-evidence-gating.md)
und das Wording-Glossar v1 (Issue #175).

---

## 1. Repo-Snapshot (code-review-graph 2026-05-17)

| Metrik | Wert |
|---|---|
| Files | 825 |
| Nodes | 7 803 (Function 3 304, Test 3 194, Class 480, File 825) |
| Edges | 67 021 (CALLS 38 537, TESTED_BY 15 852) |
| Sprachen | Python, TypeScript, JavaScript, Vue, Bash |
| Embeddings | 8 469 Nodes |
| Last index | 2026-05-17T00:06 |
| Tests | Backend 2 263 passed / 9 skipped · Frontend 449 / 43 Spec-Files |
| Coverage | Backend 66 % (Gate 60 %) · Frontend 50 % statements (Gate 28 %) |
| Layer-Status | 0–6 grün, 7–8 teilweise, 9–10 grün |

Letzte Merges: PR #486 (Observability-Welle), #487 (Logo), #488 (Redis-Bus-Hotfix),
#489 (OASIS-Provider-Dispatch), #490 (STATUS-Sync), #491 (Plan-Refine),
#492 (Zod-Spiegel `EvidenceItem.source_model`). Offener PR: #482 (Agora-2026 Design).

---

## 2. ADR-Stand (verbindlich)

| ADR | Titel | Status |
|---|---|---|
| 0001 | Single-User-only-v1 | Accepted (2026-05-04, PR #277) |
| 0002 | Evidence-Gating-Hartanker | Accepted (5 Anker, Schwächung nur via Supersedes) |
| 0003 | Stack Flask + Pydantic v2 + Vue 3 + Neo4j + Ollama-kompatibel | Accepted |
| 0004 | Pydantic = Backend-Contract-SSoT, Zod = Frontend-Spiegel | Accepted |
| 0005 | Signed Tickets statt URL-Token | Accepted |
| 0006 | Gunicorn-gevent + nginx-Sidecar | Accepted |
| 0007 | Redis Eventbus bevorzugt, File-Fallback bleibt | Accepted |
| 0008 | Config fail-fast | Accepted |

**Geplant (offen):**
- 0009 — CVE-Upstream-Eskalation (CAMEL/OASIS/sentence-transformers, Hardstop 2026-07-30)
- 0010 — Prod-Observability (OTel default-off, Sampling, Retention) — auto-promovieren nach Live-SigNoz-Smoke
- 0011 — Report-Quality-Floor (Evidence-Coverage, Confidence-Tiers, Hypothesen-Cap, Simulation-Floor) — wird mit Welle Report-Quality besiegelt

---

## 3. Aktive Welle — Report-Quality (Issues #493–#497)

Reviewer-Feedback Report `report_4fe2dacd80ba` (Briefing-Plan
`~/.claude/plans/denk-ber-folgende-sachen-idempotent-owl.md`).
Ein Slice = ein Branch, ein PR, ein Verify-Gate, ein FF-Merge nach Gemini-Sichtung.

| # | Issue | Slice | Branch | Layer | Subagent | Modell | Akzeptanz (kopierbar) |
|---|---|---|---|---|---|---|---|
| 1 | #493 | Evidence-Coverage-Floor (min=2 + Score-Cap < 0.60 bei `len(evidence) < 2`) | `feat/report-quality-slice-1-evidence-floor` *(angelegt)* | 0+1 | `agora-refactor-worker` + `agora-test-worker` | Sonnet | `pytest -k "test_balanced_routes_single_evidence_to_hypothesis"` grün · `scripts/dump_schemas.py --check` ohne Drift · Zod-Spiegel synchron |
| 2 | #494 | Confidence-Tier-Expansion (`speculative`, `verified`) — neue Enum-Werte, Validatoren ziehen mit | `feat/report-quality-slice-2-confidence-tiers` | 0 | `agora-refactor-worker` + `agora-test-worker` | **Opus (Lead)** — Layer-0 + Enum-Touch | Enum-Werte exklusiv getestet · `cross_stakeholder_for_high` + `reject_inferred_in_high_confidence` unverändert · Frontend-Renderer kennt neue Tiers · Schema-Dump grün |
| 3 | #495 | Hypothesen-Cap max 5 pro Section + Dedup + Appendix-Verschiebung | `feat/report-quality-slice-3-hypothesis-cap` | 1 (+ Frontend) | `agora-refactor-worker` + `agora-frontend-worker` | Sonnet | Section ≤ 5 Hypothesen · Dedup nach `claim_text`-Embedding-Distanz · Appendix-Renderer zeigt overflow · Snapshot-Test |
| 4 | #496 | Simulation-Floor (Default ≥ 30 Agenten, ≥ 10 Runden) — Settings + Frontend-Hint | `feat/report-quality-slice-4-sim-floor` | 1 (+ Frontend) | `agora-refactor-worker` + `agora-frontend-worker` | Sonnet | `simulation_floor.py`-Validator + Settings-Default · Frontend warnt bei Unterschreitung · E2E-Stub bestätigt Default-Spawn |
| 5 | #497 | Echo-Chamber-Red-Team-Quote (mind. 2 Skeptic-Persona-Quotes pro Section) | `feat/report-quality-slice-5-red-team` | 1 (+ 2 Wording) | **Opus (Lead)** — Persona-Quoten-Logik + Wording-Glossar | Opus | Skeptic-Persona-Pool ≥ 2 pro Run · Section verifiziert Quote-Count · Wording-Glossar v1 nicht verletzt · Eval-Snapshot |

**Sequenzierung:** Slice 1 → Slice 2 (Layer-0-Verkettung), dann Slice 3 / 4 / 5 parallel
in eigenen Worktrees. Slice 5 erst nach Slice 2 (neue Tiers werden referenziert).

**Hartanker-Re-Check vor jedem Slice-Merge:** `<evidence_gating priority="hard">` im
Prompt-Block unverändert · `EvidenceSourceKind` unverändert · Hedge-Snapshot stabil
(`backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`).

---

## 4. Backlog (nicht in aktiver Welle, nach Report-Quality)

| Thema | Quelle | Modell-Hint |
|---|---|---|
| Report-Perf Slice B (Interview-Cache) + Slice C (Section-Parallelisierung) | [`plan.report-perf.md`](../archive/plans/plan.report-perf.md) | Sonnet (Refactor) |
| Frontend Redesign Slice 7+ (post-#482 Merge) | `docs/plans/2026-05-15-fe-redesign-slice-*.md` | Sonnet (Frontend) |
| Workspace-API-Key-Store (#461) | Offen | Sonnet (Refactor) |
| Prod-like Stub-E2E (#460) | Offen | Sonnet (Test) |
| Trivy / harden-runner Audit (#358, #359) | jules-Label | Sonnet (CI) |
| CVE-Watchlist #124, #126 (Hardstop 2026-07-30) | jules-Label | Sonnet (Doc + CI) |
| M11.4 Playwright-Smokes (3 Tests) | M11 Roadmap | Sonnet (Test) |
| M11.5 Komplexitäts-Gate (`radon`-Allowlist abbauen) | M11 Roadmap | Sonnet (Refactor) |
| M11.6 API-Envelope-Gate | M11 Roadmap | Sonnet (Test) |
| Live-SigNoz-End-to-End-Smoke (Observability-Welle Followup) | Slice-1-Worklog | Manuell + Doc |

---

## 5. Modell-Mix Ist vs. Ziel

| Modell | Ziel-Quote | Aktiv-Heuristik |
|---|---|---|
| **Opus (Lead)** | 25 % | Layer-0-Drift, Cross-Layer-Refactor, Wording-Semantik, Spec ambig, Pre-PR Self-Review |
| **Opus (Code-Review-Subagent)** | 10 % | `contracts/`, `evidence_binder`, `report_agent`, neue Validatoren |
| **Sonnet (`agora-refactor-worker`)** | 25 % | Refactor ≥ 2 Files, Pydantic-Migration, Service-Extraction |
| **Sonnet (`agora-test-worker`)** | 15 % | Pydantic-Contract-Tests, FSM-Übergänge, Persona-Quoten, Evidence-Dedup |
| **Sonnet (`agora-frontend-worker`)** | 10 % | Vue/Pinia/Zod-Spiegel, neue Components, Composables |
| **Sonnet (`agora-evidence-auditor`)** | 5 % | Read-only Audit vor Slice-2/5-Merge (Confidence + Wording) |
| **Haiku (`agora-doc-worker`)** | 10 % | CHANGELOG, STATUS-Sync, Worklogs, README-Patches |

**Opus-Trigger-Liste (überstimmen das Default-Routing):**
- Layer-0 (`contracts/`, `EvidenceSourceKind`, neue Tiers) — sofort Opus
- Wording-Glossar v1 (Issue #175) — Persona/Quote/Tier-Wording
- ≥ 2 Layer gleichzeitig betroffen
- Pre-PR Self-Review vor `gh pr create` bei Hardanker-Touch
- Spec ambig, keine bestehenden Tests

---

## 6. Reihenfolge-Heuristik (für Lead beim `/agora-next-task`)

**Sequenziell:**
1. STATUS-/PLAN-Drift bereinigen (Doc-Sync first).
2. Layer-0-Touch *immer* allein in einem Slice (kein gleichzeitiger Layer-2-Touch).
3. Frontend-Spiegel **nach** Backend-Schema-Bump in eigenem Commit, aber gleichem PR.
4. Coverage-Schwellen erst anheben, wenn Ist-Wert ≥ Schwelle + 2 (Fallback-Formel `floor(Ist - 2)`).
5. `scripts/sync-status.sh` *vor* `gh pr create` (MAI-16-Gate).

**Parallel zulässig** (verschiedene Worktrees, keine Datei-Konflikte):
- Slices 3/4/5 nach Slice 1+2.
- Doku-Slice + Test-Slice + Frontend-Slice ohne gemeinsame Backend-Datei.
- CVE-Doc-Updates parallel zu allem (nur `docs/`).

**Nicht parallel:**
- Mehrere Slices, die `report_v3.py` oder `evidence_binder.py` anfassen.
- Mehrere Slices, die das Wording-Glossar oder Prompt-Templates ändern.
- Zwei Slices, die denselben Pinia-Store bzw. Composable mutieren.

---

## 7. Verify-Gate vor jedem Slice-Merge

```bash
# Backend
cd backend
uv run ruff check app/ tests/
uv run pytest --cov=app --cov-fail-under=60 -q
uv run radon cc --min C app/  # mit gepinnter Allowlist

# Frontend
cd frontend
npm run lint
npm run typecheck
npm run test:run
npm run test:coverage  # threshold 28 %

# Schema-Drift
python scripts/dump_schemas.py --check

# STATUS-Drift
bash scripts/sync-status.sh --check

# Wording-Glossar
python scripts/check_voice.py --strict
```

PR-Body **muss** enthalten: `Closes #<issue>`, Liste der berührten Hartanker
(oder „keine"), Verify-Auszüge.

---

## 8. Hardstops (gelten weiterhin)

1. **Layer-0-Schwächung** ohne Supersedes-ADR → abbrechen.
2. **`?token=`** in jedem Pfad → abbrechen.
3. **Soft-Gates ohne Ablaufdatum** → ablehnen.
4. **LLM-Marketing-Vokabular** im Report-Voice (Glossar v1, Issue #175) → blockiert via `check_voice.py --strict`.
5. **Direkte `current_app.extensions`-Service-Suche** statt `AgoraContainer` → ablehnen.
6. **Hartkodierter `token_limit`** in CAMEL-/OASIS-Anbindung → ablehnen.
7. **`--no-verify` / `--force` / `--no-gpg-sign`** ohne expliziten User-Befehl → abbrechen.
8. **CVE-Ignores** ohne Issue, Owner, Deadline und Hardstop → blockiert.
9. **Hartanker-Schwächung** der 5 Anker aus ADR-0002 → braucht `0002-supersedes.md` und User-Sign-off.

---

## 9. Slash-Command-Stand

**Aktiv** (`.claude/commands/`):
- `/agora-next-task` — Master-Orchestrator
- `/verify-after-subagent` — Sequential-Gate Pflicht
- `/fix-mai-01..17-*` — Mai-Restwelle (überwiegend abgearbeitet, archivierbar)
- `/switch`, `/switch-model`, `/list-models`, `/status`, `/ai-init` — Provider-/Modell-Switch (UI-Layer offen)
- `/repo-research`, `/observability-slice-2.prompt` — Recherche/Wellen-Templates

**Geplant für Report-Quality-Welle:**
- `/fix-rq-01-evidence-floor` → Slice 1
- `/fix-rq-02-confidence-tiers` → Slice 2 (Opus-Trigger setzen)
- `/fix-rq-03-hypothesis-cap` → Slice 3
- `/fix-rq-04-sim-floor` → Slice 4
- `/fix-rq-05-red-team` → Slice 5 (Opus-Trigger setzen)

---

## 10. Tool-Pflicht-Reminder

Code-Exploration **erst** über `code-review-graph`:
`semantic_search_nodes` / `query_graph` / `get_impact_radius` / `get_affected_flows` /
`detect_changes`. Erst danach `Read`/`rg`. Bei Output > 20 Zeilen `context-mode`
(`ctx_batch_execute` / `ctx_execute_file`) statt Bash. Volle Tabelle:
[`docs/runbooks/tool-pflicht.md`](../runbooks/tool-pflicht.md).

---

*Erstellt 2026-05-17 nach Merge der Observability-Welle. Ablöser:*
*[`docs/archive/plans/plan.heuristic.md`](../archive/plans/plan.heuristic.md) (2026-05-04).*
