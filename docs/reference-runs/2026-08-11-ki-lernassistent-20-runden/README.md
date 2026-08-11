# Reference run 4: AI learning assistant, 20 rounds, Gemini 3.6 Flash

*English · [Deutsch](./README.de.md)*

> [!IMPORTANT]
> This run documents Agora's behavior in a simulated multi-agent environment. It is **not** evidence that the simulated personas represent real people or predict real human behavior.

## Why this is the current reference run

It is the first run in which evidence binding actually works. Five preceding reports across four model configurations bound **zero or one** claim; this one binds **39**. That makes the real limit measurable for the first time — and it sits somewhere other than the earlier runs suggested.

It is also the run with the best prose and the worst provenance. Those belong together: a stronger writing model argues more convincingly **and** invents more convincing source references, as long as nothing checks them.

It does not replace the earlier reference runs. The [third run](../2026-08-11-ki-lernassistent/README.md) describes mechanisms this one takes for granted.

## Run identity

| Field | Value |
|---|---|
| Report ID | `report_4786a1a3d4ea` |
| Simulation ID | `sim_eb9037a01fb4` |
| Graph ID | `951b6064-ad30-4b9d-a8e9-0b4790369817` |
| Report model | `models/gemini-3.6-flash` |
| NER / ontology model | `models/gemini-3.6-flash` |
| Persona model | `deepseek-v4-flash:0731` |
| Embedding | `gemini-embedding-2`, 3072 dim, OpenAI-compatible path |
| Report intent | `opinion`, 6 sections |
| Rounds | **20 / 20** (`max_rounds=20`) |

## Simulation snapshot

| Metric | Value |
|---|---:|
| configured persona profiles | **50** |
| agents in metrics snapshot | **42** |
| matched graph entities | 47 |
| actions Twitter / Reddit | 291 / 374 |
| comments (Reddit) | 84 |
| clusters | 6 |
| cluster sizes | 10 / 10 / 8 / 5 / 5 / 4 |
| echo chamber index | 0.5741 |
| bridge agents | 20, 12, 27, 7, 37 |

> [!WARNING]
> The population accounting discrepancy persists: 50 configured profiles against 42 agents in the snapshot. The third reference run showed 50 against 38.

## What works in this run

### Initial-post assignment is fully correct

For the first time every initial post lands on the semantically right persona — 8 of 8, zero `No matching agent` warnings:

```
ExecutiveManager    → Geschäftsführung (management)
WorksCouncilMember  → Betriebsrat (works council)
PermanentLecturer   → Dozenten (permanent teaching staff)
FreelanceLecturer   → Honorarkräfte (freelance lecturers)
RetrainingStudent   → Umschüler (retrainees)
ExamBoardMember     → IHK (chamber of commerce)
FundingAgency       → Agentur für Arbeit (employment agency)
HiringCompany       → Regionale Betriebe (regional employers)
```

The reason is structural: with domain-specific typing, **type ≈ role** — each type holds few entities, so the direct match cannot miss. Compare run `sim_76ef482a13e4` with a generic vocabulary (`Organization`, `Student`, `Professor`): there, one of nine seed posts was published by `Agora` itself, because `Organization` was a bucket of 22 entries and the match takes index 0.

### Evidence binding works

| | this run | five predecessors |
|---|---:|---:|
| validated claims | **39** | 0 – 1 |
| hypotheses | 141 | 129 – 157 |
| data gaps | 131 | 41 – 111 |
| `evidence_index` | 76 | 38 – 85 |

Evidence composition: 33 `agent_interview`, 17 `seed_document`, 14 `relationship_chain`, 8 `agent_action`, 4 `graph_metric`.

Gate decisions: `no_supporting_evidence` 131, `prose_fact_unsupported` 13.

### The prose gate scales correctly

Removed factual statements per section: **1, 7, 2, 3, 1** (section 3 reported none). The third reference run showed exactly one in six consecutive sections — that was a property of the writing model, not of the gate. `gemini-3.6-flash` writes with more numbers, so the filter finds more candidates.

### The report names observable events, not topics

The tipping point is stated as a concrete event rather than a theme:

> Acceptance does not break at a technical hurdle, but at the exact moment a freelance lecturer dismisses an AI-generated exercise in front of the class as factually wrong. When the lecturer explicitly tells participants "forget what the assistant gives you, study from my slides instead", the retrainees lose trust in the system instantly.

Plus a causal chain no earlier run found: the system absorbs entry-level and routine questions → only dense, complex cases remain in classroom time → uncompensated work intensification.

## Critical finding 1: the provenance anchors are invented

For the first time each quote carries its **own** anchor instead of a shared one:

```
seed_doc:interview_ana_hodzic
seed_doc:interview_ali_demir
seed_doc:interview_katharina_weber
seed_doc:interview_clara_meyer
seed_doc:interview_luca_greco
```

**None of them appears in any `tool_result`.** The graph contains exactly one entity with "interview" in its name: `Stakeholder-Interviews`. The model constructs anchors following the pattern `interview_<persona_name>`, and nothing checks them, because the `seed_doc:` prefix bypasses the binding check in `backend/app/services/report_agent/evidence.py` entirely.

This is a **regression** relative to the predecessors, not an improvement. There, all quotes carried the same value — obviously wrong and immediately visible. Here each quote looks individually sourced and points at documents that do not exist. For a reader the second variant is more dangerous.

## Critical finding 2: the entailment judge is inconsistent

The same fact is judged both ways within one report.

**In section 1**, `claim_10` binds a paraphrase correctly:

```
CLAIM   : … die 31 auf der Personalliste geführten Honorarkräfte
EVIDENCE: 31 Honorarkräfte stehen auf der Personalliste des Trägers.
VERDICT : SUPPORTED  ("qualitative statement largely matches the evidence")
```

**In section 2**, the prose gate removes the same fact as unsupported:

```
"31 Honorarkr…"      before 1 → after 0   REMOVED
"2023"               before 1 → after 0   REMOVED
"22 festangestellte" before 1 → after 1   kept
```

Both removed statements exist verbatim in the same report's evidence pool. The structurally identical sentence about "22 permanent lecturers" survives.

So the judge *can* handle paraphrase — it just does not do so reliably. That is a different diagnosis from "it keys on surface similarity", and it moves the search toward consistency and thresholds.

## Critical finding 3: all 39 claims sit at `low`

```
confidence labels : {'low': 39}
confidence scores : [0.59]
```

Not a single claim reaches `medium` or `high`, and all 39 carry the identical score. A confidence measure that takes exactly one value across 39 cases measures nothing.

Furthermore, **22 of the 39 are plain `<simulated_quote>` tags** — a quote bound to the interview it came from, i.e. self-reference. That leaves **17 genuine prose claims** against 141 hypotheses: roughly 11 %.

## Critical finding 4: the data-gap section does not know its own gaps

Section 6 discusses the data gaps **of the training provider** at length — missing pilot data, unsupported benefit claims, unclear validity of the learning-progress records. It mentions "hypotheses" twice, both times meaning "optimistic hypotheses held by management".

About the report's own **141 hypotheses and 131 data gaps** it says nothing. Same blind spot as in the third reference run, here with eight times as many bound claims.

## Further findings

### `status: incomplete` with `missing_sections: []`

`meta.json` reports `status: incomplete` although all six sections were generated and saved and `missing_sections` is empty. The state contradicts itself.

### One hallucinated word inside a correctly sourced sentence

The report writes "nach den Erfahrungen der **Zeiterforderung** aus dem Jahr 2023". That word does not exist in German. The evidence correctly says "digitale **Zeiterfassung** im Jahr 2023" (digital time tracking) — year and substance are carried over correctly, the noun is mangled.

### No negative feedback, not even across 20 rounds

```
Twitter:  291 actions   0 dislike   0 comment_dislike
Reddit:   374 actions   0 dislike   0 comment_dislike
          74 likes, 6 comment likes, 84 comments, 0 dissent markers
```

This run removes the three obvious counter-explanations: **20 instead of 10 rounds**, **50 agents**, and `FreelanceLecturer` against `PermanentLecturer` for the first time as **separate, correctly assigned speakers** — precisely the two groups every report names as the core conflict. Not one rejecting action occurs.

### Non-stakeholders and role duplicates persist

44 distinct entity names collapse into 12 types. The distribution shows both problems:

```
RetrainingStudent (10):  Absolventen · Jüngere Teilnehmende · Teilnehmende mit Migrationsgeschichte · …
Organization (8):        Auswertungsfunktion · ChatGPT · IHK · KI-Lernassistent · Moodle · …
FundingAgency (6):       Agentur für Arbeit · Jobcenter · Kostenträger · kommunale Jobcenter
PermanentLecturer (5):   Dozenten · Festangestellte · Festangestellte Fachdozenten · Ältere Dozenten
```

The blocklist in `backend/app/services/persona_eligibility.py` fired once in this run (`Der Assistent`, type `Technology`). It cannot include `Organization`, because that is a legitimate stakeholder type — which is why `ChatGPT`, `Moodle` and `Auswertungsfunktion` still take part as personas.

Note the trade-off: `gemini-3.6-flash` produces the most domain-faithful typing of all runs — `FreelanceLecturer` against `PermanentLecturer` is exactly the scenario's conflict line — and **for that very reason** has the highest fallback share (36 of 48, 75 %), because none of those types appear in the known list. Good domain modeling is currently penalized.

## Comparison of the four reference runs

| | Run 1 | Run 2 | Run 3 | **Run 4** |
|---|---|---|---|---|
| Domain | domain migration | domain migration | retraining | retraining |
| Report model | Gemini 3.6 Flash | — | deepseek-v4-flash | **gemini-3.6-flash** |
| Rounds | — | — | 10 | **20** |
| Agents configured / snapshot | 33 / 24 | 30 / 30 | 50 / 38 | **50 / 42** |
| validated claims | 17 unique | 0 | 1 | **39** (17 prose) |
| hypotheses | 157 | — | 129 | 141 |
| initial-post assignment | — | — | 10/10 (by luck) | **8/8 (structural)** |
| provenance anchors | — | — | one constant value | **invented per quote** |

## What this run demonstrates

- Evidence binding works in principle — the earlier runs were not measuring a broken binder but a weaker report model.
- Domain-specific typing makes initial-post assignment structurally correct rather than accidental.
- The prose gate scales with the share of quantitative statements.
- Twenty rounds with correctly assigned conflict parties still produce no negative feedback.

## What this run explicitly does not demonstrate

- **No dependable provenance.** Anchors are invented per quote and never verified.
- **No working confidence measure.** 39 claims, a single score.
- **No self-report on its own evidence base.** 141 hypotheses appear nowhere in the text.
- **No validity of the analysis**, as long as the test case ships its own answers (#1240).

## Remediation priority

1. **Close the `seed_doc:` bypass** (#1226). This run shows a stronger model exploits the gap more systematically than a weaker one.
2. **Entailment consistency** (#1209). The same fact must not bind in section 1 and be removed in section 2.
3. **Differentiate confidence.** One score across all claims is not a measure.
4. **Extend the prose gate beyond numbers** (#1209). Qualitative assertions remain unchecked.
5. **Check persona eligibility independently of type** (#1226). The blocklist is correct but is bypassed via `Organization`.
6. **Extend the known type list with domain types** instead of pushing NER toward generic ones.
7. Clean up **population accounting** and `status: incomplete` with an empty `missing_sections`.

## Artifacts

- Simulation: `backend/uploads/simulations/sim_eb9037a01fb4/`
- Report: `backend/uploads/reports/report_4786a1a3d4ea/`
- Machine-readable summary: [`artifacts/run-summary.json`](./artifacts/run-summary.json)

## Conclusion

This run separates two qualities that coincided in every predecessor. **Prose quality** rises visibly with the model: sharper tipping points, real causal chains, clean answers to the questions asked. **Provenance quality** falls in the same step: anchors invented per quote, one confidence value for everything, a judge that rules on the same fact twice in opposite directions.

For a platform meant to keep supported statements separable from conjecture, that is the more uncomfortable insight: a better language model improves the report and degrades its verifiability, as long as the checking layer leaves gaps it can fill.
