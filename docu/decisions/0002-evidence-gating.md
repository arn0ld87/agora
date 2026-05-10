# ADR-0002 — Evidence-Gating für Report-Generation

**Status:** Accepted
**Datum:** 2026-05-10
**Accepted:** 2026-05-10
**Slice:** M11.7 (a + b + c, schrittweise)
**Autor:** arn0ld87 + Claude Opus 4.7
**Bezug:** [`PLAN.md`](../../PLAN.md) Layer 1 (Anti-Dekoration), Layer 3 (Original-Quotes), Wording-Glossar v1, [`backend/app/contracts/report_contract.py`](../../backend/app/contracts/report_contract.py), [`backend/app/services/report_prompts.py`](../../backend/app/services/report_prompts.py)

---

## Kontext

Der Report-Output von Agora hat bisher kein systematisches Provenance-Modell. Das LLM kann Claims als Fakten formulieren, ohne dass Evidence sie stützt — oder mit einer einzigen Stakeholder-Stimme als „high-confidence"-Aussage durchgehen. Konkrete Symptome aus früheren Test-Runs:

- Generika wie „Mitarbeiter werden die Maßnahme begrüßen" ohne jegliche Quote-Bindung.
- `confidence_label="high"` mit nur einer Persona-Gruppe als Quelle (Echo-Kammer).
- Konkurrenz-Quotes (strategische Gegenposition) als Konsens fehlinterpretiert.
- Vermischung von „im Korpus belegt" und „LLM-geschlussfolgert" in derselben Evidence-Liste.

**Was bereits existiert** (Stand vor M11.7):
- `ConfidenceLabel`-Enum (`low`/`medium`/`high`/`verified`)
- Validator `verified_needs_strong_match` (match_score ≥ 0.85 für `verified`)
- Validator `reject_orphan_high_confidence` (high/verified braucht ≥ 1 `supports_claim=True`)
- `EvidenceItemModel.quote` + `source_id_anchor` für Original-Zitat-Provenance (Layer 3, Task 12)

**Was fehlt:**
- Klassifikation der Evidence-Provenance (Korpus vs. Agent-Quote vs. Inferenz).
- Cross-Stakeholder-Konsistenz-Regel für `high`.
- Hedge-Pflicht für seed-only Claims.
- Hard-No für Inferenz-Evidence in `high`/`verified`.

---

## Entscheidung

Vier Provenance-Stufen werden als **harte** Architektur-Regel etabliert. Sie sind dreifach verankert:

1. **Prompt-Block** in `backend/app/services/report_prompts.py` weist das LLM zur Selbst-Klassifikation an. Block-Inhalt enthält `<evidence_gating priority="hard">` mit den vier Stufen, einer `<self_check>`-Reihenfolge und `<negative_examples>`.
2. **Schema + Validators** in `backend/app/contracts/report_contract.py`:
   - `EvidenceSourceKind` Enum mit `seed_corpus`, `agent_quote`, `graph_relation`, `inferred`
   - `EvidenceItemModel.source_kind` als Pflichtfeld (Default `seed_corpus` für backward-compat)
   - `EvidenceItemModel.persona_stakeholder_group` als Pflicht für `agent_quote`
   - Validator `cross_stakeholder_for_high` — `high`/`verified` verlangt agent_quote-Evidence aus ≥ 2 Stakeholder-Gruppen
   - Validator `reject_inferred_in_high_confidence` — `inferred`-Evidence darf `high`/`verified` nicht stützen
3. **Tests**: Snapshot-Pin auf Hedge-Wort-Liste, Drift-Guards auf Enum-Werte und Validator-Verhalten.

### Die vier Stufen

| Stufe | Max-Confidence | Pflicht-Bedingung |
|---|---|---|
| **hypothesis** | keine | Keine Evidence — Claim wird nicht in `claims[]` formuliert; entweder weglassen oder als Hypothese kennzeichnen (UI-Slot kommt mit M11.7c). |
| **seed_only** | `low` | Einzige Evidence ist `source_kind=seed_corpus`. Claim-Text MUSS Hedge-Wort enthalten (`vermutlich`, `deutet auf`, `die Quellenlage spricht für`, `Indizien legen nahe`). |
| **agent_grounded** | `medium` | Mind. 1 `source_kind=agent_quote` + mind. 1 `source_kind=seed_corpus`. Quote-Feld der Agent-Evidence ist Pflicht. |
| **cross_stakeholder** | `high` | Mind. 2 `agent_quote`-Evidences aus mind. 2 unterschiedlichen `persona_stakeholder_group`-Werten. Stakeholder-Gruppen werden im Claim-Text genannt. |
| **verified** | `verified` | Wie `cross_stakeholder` + match_score ≥ 0.85. **LLM setzt `verified` NICHT** — Validator vergibt es post-hoc. |

### Wording-Glossar-Konformität

Der Prompt-Block hält Glossar v1 (siehe `docu/glossary-wording.md`) ein — keine Forecast-/Prediction-/Rehearsal-Vokabeln. Hedge-Wörter sind alle DACH-Voice-konform.

---

## Konsequenzen

### Positiv

- **Reproduzierbare Confidence-Vergabe**: high/verified können nicht mehr aus einer einzelnen Persona kommen.
- **Anti-Halluzination**: inferred-Evidence wird sichtbar markiert und blockt high.
- **UI-Hook**: Frontend kann `source_kind` als Badge anzeigen, hypothesis-Block separat rendern.
- **Anti-Echo-Kammer-Marker**: Cross-Stakeholder-Konsens ist explizit gemacht, nicht implizit erhofft.

### Negativ

- **Mehr LLM-Token-Last**: Prompt wird ~ 80 Zeilen länger.
- **Migrations-Aufwand**: Bestehende Code-Pfade, die Evidence erzeugen, müssen `source_kind` setzen (Default `seed_corpus` puffert).
- **UI-Anpassung nötig** (M11.7c): Frontend muss `hypotheses[]` und `source_kind` im Renderer berücksichtigen.

### Risiko

- LLMs unterschiedlicher Qualität halten sich verschieden gut an die Regeln. Die Pydantic-Validators sind das Auffangnetz — bricht das LLM die Cross-Stakeholder-Regel, wird der Claim mit `high` abgelehnt, fällt entweder auf `medium` zurück oder muss im Snapshot-Eval als Regression erkannt werden.

---

## Pflicht-Anker (nicht ohne Supersedes entfernen)

Die folgenden fünf Anker sind die operative Realisierung dieses ADR. Wer einen davon entfernt oder schwächt, supersedet diesen ADR und muss `0002-supersedes.md` o. ä. anlegen.

1. **Prompt-Block** `<evidence_gating priority="hard">` in `backend/app/services/report_prompts.py`.
2. **Hedge-Snapshot** `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt` mit den 4 Hedge-Wörtern.
3. **Enum** `EvidenceSourceKind` in `backend/app/contracts/report_contract.py` mit den 4 Werten.
4. **Validator** `cross_stakeholder_for_high` auf `ReportClaimModel`.
5. **Validator** `reject_inferred_in_high_confidence` auf `ReportClaimModel`.

Schwächungs-Beispiele, die ein Supersedes erfordern:
- `cross_stakeholder_for_high`-Schwelle von 2 auf 1 Gruppe absenken.
- `inferred` aus dem Enum entfernen.
- Hedge-Wort-Liste verkürzen.
- Den Prompt-Block in einen "soft-hint"-Block umformulieren ohne `priority="hard"`.

---

## Roll-Out

| Slice | Inhalt | Status |
|---|---|---|
| **M11.7a** | Prompt-Block + Hedge-Snapshot-Test | Accepted |
| **M11.7b** | Schema + Validators + Drift-Guards | Accepted |
| **M11.7c** | `ReportSectionModel.hypotheses[]` + Frontend-Renderer | Implementiert |
| **M11.7d** | Snapshot-Eval-Suite mit fixierten Bad-/Good-Cases | offen |

---

## Referenzen

- PLAN.md F8/Layer 1/Layer 3
- [`docu/glossary-wording.md`](../glossary-wording.md) (Wording-Glossar v1)
- [`backend/app/contracts/report_contract.py`](../../backend/app/contracts/report_contract.py)
- [`backend/app/services/report_prompts.py`](../../backend/app/services/report_prompts.py)
- [`backend/tests/test_evidence_gating_prompt.py`](../../backend/tests/test_evidence_gating_prompt.py)
- ADR-0001 (Auth-Modell) als Format-Vorlage
