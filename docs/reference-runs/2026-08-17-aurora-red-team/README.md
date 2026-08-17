# Reference run 7 — AURORA decision report with red-team review

**Date:** 2026-08-17  
**Simulation:** `sim_c2108c7f543e` (24 of 24 rounds completed)  
**Report:** `report_b259e254ee3f` (mode `balanced`, ReportV3 schema 4)  
**Scenario:** fictional Städtischer Klinikverbund Falkenbrück / AURORA (`Nexora Triage Assist`)

This reference run evaluates the same decision as reference run 6: whether an AI-assisted triage and documentation system should launch simultaneously at two hospital sites, start as a staged pilot at Falkenbrück-Mitte, or be delayed.

Unlike reference run 6, this is **not a same-simulation comparison**. The run uses a new 24-round simulation and an extended report with seven instead of six sections. It is therefore not an isolated reporter regression, but the current reference for two new pipeline stages: the post-report red-team review, and the active routing of unsupported factual statements into the hypotheses slot.

## Run at a glance

| Metric | Value |
|---|---|
| Report runtime | 16:46 min (15:21:42 to 15:38:28), plus 13 s red-team review |
| Report sections | 7: executive summary, comparison dimensions, per-variant assessment, differences in reaction patterns, trade-off, uncertainties and data gaps, recommendation |
| Report prose | 3,926 words, 24 marked simulated persona quotes (2–4 per section) |
| Evidence records | 116 |
| Agent interviews | `interview_agents` in all 7 sections, 6–8 personas per section, 5 questions each, 49 responses drawn from 43 agent profiles |
| Claims | 29, each with at least one evidence reference (40 references total, 1–5 per claim) |
| Confidence | 29 of 29 `low`, scope consistently `simulation_consensus`, basis `persona` |
| Hypotheses | 136 |
| Data gaps | 126, all severity `medium` |
| Red-team findings | 9 (intent `comparison`, echo index 0.703) |
| Gating interventions | 10 unsupported factual statements removed from prose and carried as hypotheses (sections 1, 2, 3, 6, 7) |
| Export ids | section-qualified and collision-free: 29/29 claims, 126/126 data gaps, 136/136 hypotheses |

## What the run demonstrates

- **Red-team review as its own pipeline stage.** A separate review pass runs after the report (`gpt-5.6-luna`, 12.96 s) and returns 9 findings: unresolved tension between sections, unsupported effect claims, and missing counter-positions from individual stakeholder groups. The echo index of 0.703 quantifies how strongly the report repeats its input wording.
- **The export fix from [#1340](https://github.com/arn0ld87/agora/issues/1340), [#1341](https://github.com/arn0ld87/agora/issues/1341), and [#1342](https://github.com/arn0ld87/agora/issues/1342) is visible in the artifact.** The 9 findings and the review stage's model attribution survive the rebuild of the ReportV3 artifact instead of falling back to an empty list on the second write path. Claims (`C1_01`), data gaps (`G1_01`), and hypotheses (`H1_01`) carry section-qualified ids; all 29, 126, and 136 entries resolve uniquely.
- **Unsupported precision is rerouted, not merely softened.** Across five of seven sections, 10 factual statements were removed from the prose and carried forward as hypotheses.
- **Quote anchors resolve.** All 24 simulated persona quotes point to a concrete `ev_` id in the evidence index; generic `seed_doc:…#chunk:0` anchors no longer appear in quotes. This was an explicit regression expectation from reference run 6.
- **Four evidence kinds in combination.** The report draws on simulation statements, seed corpus, graph relations, and agent actions side by side instead of relying mostly on document retrieval.
- **Explicit comparison structure.** The report assesses four variants separately and recommends a **reversible pilot at Falkenbrück-Mitte only**, tied to seven named pieces of proof before approval, with a full delay of the go-live as the fallback.

## Evidence binding

| Evidence kind | Records | Bound to claims |
|---|---:|---:|
| `agent_quote` (interview responses) | 49 | 7 |
| `seed_corpus` (seed documents) | 31 | 17 |
| `graph_relation` (graph relations) | 28 | 0 |
| `agent_action` (simulation actions) | 8 | 0 |
| **Total** | **116** | **24** |

92 of the 116 evidence records are collected, persisted in the artifact, and shown in the Evidence Inspector, but carry no claim. Graph relations and simulation actions are entirely unbound. The simulation share of validated claims is correspondingly 10.34 percent (3 of 29 claims with simulation evidence).

## Why this is a reference run, not a showcase

Limitations visible in the artifact:

- **Confidence does not differentiate.** All 29 claims carry `low`, even where several stakeholder groups support the same statement. Cross-stakeholder promotion does not trigger anywhere in this run.
- **Interview and graph evidence stays mostly unbound.** 42 of the 49 interview responses and all 36 graph and action records are bound to no claim.
- **Data gap severity is constant.** 126 of 126 gaps are `medium`, which yields no prioritization.
- **Hypothesis volume far exceeds the claim base.** 136 hypotheses against 29 claims and 3,926 words of prose; some of them are redundant.
- **Provenance fields are incomplete.** 85 of the 116 evidence records have no `source_id_anchor`, one still carries a generic `#chunk:0` anchor. `source_model` is empty on all 116 records, and `model_attribution` is set for the red-team stage only.
- **Runtime increased against reference run 6** (16:46 min instead of 8:19 min). The causes are the seventh section, interviews in every section, and per-section postprocessing whose claim extraction and evidence binding takes between 14 and 59 seconds. A direct reporter comparison with reference run 6 is not valid, because the simulation differs.

The repository does **not** contain every artifact and replay input required to reproduce this run from a fresh checkout. It is therefore an **observational regression reference, not a fully reproducible Golden Run**.

## Regression expectations

Future pipeline changes should verify at least the following against this run:

1. Simulated persona quotes continue to point exclusively to resolvable `ev_` ids, never to generic seed anchors.
2. Statements carried by several stakeholder groups are not uniformly emitted as `low` confidence.
3. The binding ratio improves: interview responses, graph relations, and simulation actions must not accumulate as unbound inventory.
4. Data gaps are differentiated by severity instead of being emitted entirely as `medium`.
5. Hypothesis volume stays justifiable relative to the claim base, and duplicates are merged.
6. `source_id_anchor` and `source_model` are set per evidence record, and `model_attribution` covers every stage involved, not just the red-team review.
7. The red-team review remains a separate stage with a findings list and echo index, and is not folded back into section generation.

[Deutsche Version](./README.de.md)
