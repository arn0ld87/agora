# Handover · Evidence-Gating M11.7 (2026-05-10)

**Letzter eigener Push:** `75e6d30` — Sub-Slice **M11.7a** (Prompt-Block + ADR-0002 + CLAUDE.md-Verboten-Eintrag).
**Aktueller `origin/main`:** `d727c89` (3 Fremd-Commits zu `report-agent-tools` parallel reingekommen, kein Konflikt zu meinem Stand).

---

## Was an dieser Session erledigt ist

| Slice | Commit | Status |
|---|---|---|
| M11.4-Followup-5 (FilePollingEventBus tmp-Race) | `b1871ef` | ✅ gepushed |
| M11.4-Followup-5-Sync (STATUS-Test-Count 1706) | `34e0463` | ✅ gepushed |
| M11.2/M11.3 Coverage-Step1 (53→55, 24→26) | `f117b7b` | ✅ gepushed |
| M11.5a Backend Komplexitäts-Gate (radon) | `1b18c64` | ✅ gepushed |
| **M11.7a Evidence-Gating Prompt-Block + ADR-0002** | **`75e6d30`** | **✅ gepushed** |

Phase 7 (E2E-Smokes) komplett abgeschlossen — alle drei Smokes (Health, Upload+Graph, Minimalreport) grün auf main.

---

## Was als Nächstes ansteht — **M11.7b**

Sub-Slice **M11.7b · `EvidenceItemModel.source_kind` + zwei Validators (Layer 0)**.

ADR-0002 (`docs/adr/0002-evidence-gating.md`) ist die **verbindliche Spec**. Slice A hat die Anker 1 (Prompt) + 2 (Hedge-Snapshot) gesetzt, Slice B muss Anker 3 (Enum) + 4 (`cross_stakeholder_for_high`) + 5 (`reject_inferred_in_high_confidence`) setzen.

### Files für Slice B

- `backend/app/contracts/report_contract.py` — neue Enum `EvidenceSourceKind` mit 4 Werten (`seed_corpus`, `agent_quote`, `graph_relation`, `inferred`); `EvidenceItemModel.source_kind` (Default `seed_corpus`); `EvidenceItemModel.persona_stakeholder_group` (Optional, Pflicht für `agent_quote`); 3 neue Validators.
- `backend/app/contracts/__init__.py` — `EvidenceSourceKind` re-exportieren.
- `backend/tests/contracts/test_evidence_source_kind.py` (NEU) — 6 Drift-Guard-Tests.
- `schemas/report-contract.schema.json`, `schemas/report.schema.json` — Auto-Sync via `python -m app.contracts.dump_schemas`.
- `docs/2026-05-10-m11-7b-evidence-source-kind-arbeitsprotokoll.md` (NEU).
- `CHANGELOG.md` `[Unreleased] ### Added` Bullet.

### Validator-Wortlaut (aus ADR-0002 abgeleitet)

```python
class EvidenceSourceKind(str, Enum):
    seed_corpus = "seed_corpus"
    agent_quote = "agent_quote"
    graph_relation = "graph_relation"
    inferred = "inferred"

# in EvidenceItemModel:
@model_validator(mode="after")
def agent_quote_needs_stakeholder_group(self) -> "EvidenceItemModel":
    if self.source_kind == EvidenceSourceKind.agent_quote and not self.persona_stakeholder_group:
        raise ValueError("source_kind=agent_quote verlangt persona_stakeholder_group.")
    return self

# in ReportClaimModel, nach reject_orphan_high_confidence:
@model_validator(mode="after")
def cross_stakeholder_for_high(self) -> "ReportClaimModel":
    if self.confidence_label not in (ConfidenceLabel.high, ConfidenceLabel.verified):
        return self
    agent_quotes = [e for e in self.evidence if e.source_kind == EvidenceSourceKind.agent_quote]
    groups = {e.persona_stakeholder_group for e in agent_quotes if e.persona_stakeholder_group}
    if len(groups) < 2:
        raise ValueError(
            f"Label '{self.confidence_label.value}' verlangt agent_quote-Evidence aus "
            f"mindestens 2 unterschiedlichen Stakeholder-Gruppen. "
            f"Gefunden: {sorted(groups) if groups else '∅'}."
        )
    return self

@model_validator(mode="after")
def reject_inferred_in_high_confidence(self) -> "ReportClaimModel":
    if self.confidence_label not in (ConfidenceLabel.high, ConfidenceLabel.verified):
        return self
    if any(e.source_kind == EvidenceSourceKind.inferred for e in self.evidence):
        raise ValueError(
            f"Label '{self.confidence_label.value}' duldet keine source_kind=inferred-Evidence."
        )
    return self
```

### Test-Set für `test_evidence_source_kind.py`

1. `test_source_kind_default_seed_corpus` — backward-compat
2. `test_agent_quote_requires_stakeholder_group` — Pflicht-Feld
3. `test_high_needs_two_stakeholder_groups` — Cross-Stakeholder-Regel
4. `test_high_rejects_inferred_evidence` — Anti-Halluzination
5. `test_low_and_medium_unaffected` — untere Stufen frei
6. `test_enum_values_pinned` — genau 4 Werte (Drift-Guard zu Slice A's Prompt)

### Dispatch im neuen Fenster

```bash
# Worktree von aktuellem origin/main anlegen
cd /Volumes/T7/Projekte/agora
git fetch origin --quiet
git worktree add -b feat/m11-7b-evidence-source-kind \
  /Volumes/T7/Projekte/agora-wt/m11-7b-source-kind origin/main

# Dann /agora-next-task → Plan vorschlagen → ok → Subagent agora-refactor-worker (Sonnet)
```

Subagent-Prompt-Template steht in der vorletzten Assistant-Message dieser Session, kann 1:1 wiederverwendet werden.

---

## Was nach M11.7b kommt (Welle 2 + 3)

| Slice | Inhalt | Subagent | Aufwand |
|---|---|---|---|
| M11.7c | `ReportSectionModel.hypotheses[]` + Frontend-Renderer in `Step4Report.vue` | `agora-refactor-worker` (Backend) + `agora-frontend-worker` (Frontend) | M |
| M11.7d | Snapshot-Eval-Suite mit fixen Bad-/Good-Cases gegen Evidence-Gating | `agora-test-worker` | M |

Reihenfolge ist **strikt sequentiell** (M11.7c hängt an M11.7b's Schema, M11.7d pinnt das Endergebnis).

---

## Bekannte parallele Session

Im Repo läuft eine zweite Worktree-Session (`fix/report-agent-tools-diagnose` bei `.worktrees/report-agent-tools-diagnose`). Die letzten 3 Commits auf main (`b7e5833`, `b92d8e6`, `d727c89`) stammen vermutlich von dort. Kein direkter Konflikt zu M11.7b zu erwarten — `report_contract.py` wurde nicht angefasst, nur `report_agent/tools.py` und CI-Gates.

Vor Slice-B-Dispatch noch einmal `git fetch && git log origin/main --oneline -5` checken, um sicherzugehen.

---

## Offene Hot-Spots im Backlog (PLAN.md PR-Liste)

- PR 13: M11.5b Frontend Komplexitäts-Gate (ESLint complexity + size-limit) — eigener Slice nach M11.7-Welle.
- PR 14: M11.6 API-Envelope abschließen.
- PR 15: F8 Frontend-Hotspots (#203 zum Schließen vorbereiten).
- M10/M11.7-Folgekram: CVE-Watchlist-Refresh #296/#297/#298.

---

## Repo-State

- Hauptrepo: `/Volumes/T7/Projekte/agora` auf `d727c89` (main).
- Aktive Worktrees:
  - `agora-wt/task-46-step2-rounds-card` — fremder Worktree (Layer 4, nicht meine Session).
  - `agora/.worktrees/report-agent-tools-diagnose` — fremder Worktree (parallele report-Diagnose).
- Eigene Worktrees: alle aufgeräumt.
