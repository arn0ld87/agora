# Subagent-Routing

Datei: `docs/runbooks/subagent-routing.md` · Stand: 2026-05-17

## Prinzip

Komplexe Aufgaben werden an spezialisierte Subagents delegiert. Der Haupt-Claude
(Lead) plant, dispatched, verifiziert und committed — aber implementiert nicht
alles selbst.

---

## Routing-Matrix

Ziel-Mix über die Zeit: ~35 % Opus, ~55 % Sonnet, ~10 % Haiku.

| Aufgabe | Modell | Subagent | Trigger |
|---|---|---|---|
| Architektur-Entscheidung | **Opus** | Lead (kein Subagent) | Neue ADR, Layer-übergreifend |
| Ambige Spec klären | **Opus** | Lead | PLAN.md-Lücke, unklare Requirements |
| Code-Review kritischer Pfad | **Opus** | `feature-dev:code-reviewer` | contracts/, evidence_binder/, report_agent/ |
| Cross-Layer Refactor | **Opus** | Lead + `agora-refactor-worker` | 3+ Dateien in 2+ Layern |
| Pydantic-Migration | **Sonnet** | `agora-refactor-worker` | Layer 0 Contracts |
| Test-Suite schreiben | **Sonnet** | `agora-test-worker` | Neue Contracts, Coverage-Lücken |
| FSM-Übergänge | **Sonnet** | `agora-test-worker` | Simulation-State-Machine |
| Vue-Komponente | **Sonnet** | `agora-frontend-worker` | Step*.vue, neue Components |
| Zod-Spiegel | **Sonnet** | `agora-frontend-worker` | Pydantic → Zod Sync |
| Evidence-Audit | **Sonnet** | `agora-evidence-auditor` | Read-only Review von Outputs |
| Wording-Glossar-Check | **Sonnet** | `agora-evidence-auditor` | Read-only Textanalyse |
| CHANGELOG-Update | **Haiku** | `agora-doc-worker` | Release-Vorbereitung |
| Worklog schreiben | **Haiku** | `agora-doc-worker` | Slice-Abschluss |
| Feature-Bundle PRD | **Haiku** | `agora-doc-worker` | Neue Feature-Ideen |

---

## Opus-Trigger (überschreiben Default-Routing)

Diese Situationen verlangen Opus statt Sonnet/Haiku — unabhängig vom Default:

1. **Layer 0** (Pydantic-Contracts) wird angefasst
2. **Mehrere Layer gleichzeitig** betroffen
3. **Wording oder Prompt-Semantik** (Layer 2, Glossar v1)
4. **Spec ambig, Tests fehlen** — Erkundung nötig vor Implementation
5. **Pre-PR-Self-Review** vor `gh pr create`

---

## Dispatch-Workflow

### 1. Task identifizieren

Aus `PLAN.md` den nächsten offenen Sub-Slice auswählen.

### 2. Subagent wählen

Routing-Matrix konsultieren. Bei Unsicherheit: Opus (sicherer).

### 3. Briefing schreiben

Jedes Briefing MUSS enthalten:
- **Kontext:** 1 Satz was Agora ist + was der Slice tut
- **Constitution:** Relevante Verbote aus AGENTS.md/CLAUDE.md
- **Relevante Files:** Liste (nicht erraten — via code-review-graph ermitteln)
- **Expected Output:** Konkrete Dateien, die entstehen/geändert werden
- **Stop Conditions:** Wann der Subagent aufhören soll
- **Verification Gate:** Was nach dem Run geprüft wird

### 4. Dispatchen

```bash
# Subagent ausführen (der Subagent läuft im Worktree)
```

### 5. Verifizieren

Nach JEDEM Subagent-Run Sequential Verification Gate:

```bash
cd backend && uv run pytest tests/contracts/ -x -q
cd backend && uv run python -m app.contracts.dump_schemas --check
cd backend && uv run ruff check . && uv run mypy app
```

### 6. Commit + Push

Erst wenn Verification Gate grün. Commit durch Haupt-Claude, nicht Subagent.

---

## Anti-Pattern

- **"Sonnet ist billiger, ich nehm den für alles"** → Kosten sparen auf Kosten
  von Qualität. Opus für kritische Pfade ist Pflicht.
- **"Ich schreib das Briefing später"** → Ohne Briefing kein Dispatch. Briefing
  IST der Contract.
- **"Verification Gate kann ich mir sparen, der Subagent war gut"** →
  Sequential Gate ist PFLICHT. Kein Vertrauen ohne Verifikation.
