# Reference run 8: Geburtshilfe Hollerau

**Date:** 2026-09-25  
**Role:** visual end-to-end showcase; **not** a reproducibility or trust-golden run.

## Scenario

This run uses a fully fictional municipal scenario about the future of obstetric care in the Hollerau district. It explores which risks become visible if the Brenkhausen delivery ward is closed before a decision on a possible service-availability subsidy, and which groups carry those risks.

The seed is intentionally awkward: it contains 318 versus 341 births for Brenkhausen under different counting rules, travel times from Kleinwiese and Moorhagen above the stated 40-minute guideline, and unresolved questions around the subsidy, liability, an additional ambulance, and midwife transfer willingness.

## Run identity

| Field | Value |
|---|---|
| Simulation | `sim_8fd9a6e4bc97` |
| Report | `report_e315511c2cb9` |
| Simulation state | 24 of 24 rounds completed |
| Report mode | `explorative` |
| Evidence schema | 3 |
| Evidence records | 46 |
| Evidence types | 14 seed documents, 12 agent interviews, 8 agent actions, 8 relationship chains, 4 graph metrics |
| Graph in the UI capture | 59 entities, 46 relationships, 14 entity types |

## Why this is the showcase run

- It shows the current product surface end to end: Graph Build, simulation, live feed, and report inspection.
- The scenario produces visibly competing stakeholder positions rather than a single linear answer.
- Published screenshots and video contain only the Agora interface; browser chrome, dock, menu bar, and unrelated desktop content are excluded.
- Report limitations stay visible instead of being edited out for presentation value.

## Evidence status and known degradations

The exported ReportV3 contains **2 validated claims**, **31 hypotheses**, and **6 data gaps**. Both validated claims have simulation evidence; one of them is supported by an observed agent action.

Five report sections failed generation because of LLM errors and are represented as data gaps: central risks, friction/escalation paths, countermeasures, uncertainties/data gaps, and the recommendation section. This is why Reference run 7 remains the technical Report-/Trust-pipeline regression reference.

Persona quotations and agent actions are **synthetic model outputs**, not empirical user research and not predictions of human behavior. A stored `random_seed` does not make the run reproducible; “same seed = same run” explicitly does not apply.

## Media

- [Composite showcase screenshot](../../../media/agora-demo-poster.jpg)
- [Edited showcase video](../../../media/agora-demo.mp4)

The media shows only Agora views from this run; browser and operating-system chrome have been removed.
