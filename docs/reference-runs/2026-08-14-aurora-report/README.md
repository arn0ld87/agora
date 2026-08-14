# Reference run 6 — AURORA rollout decision report

**Date:** 2026-08-14  
**Simulation:** `sim_4245ff3d7b23`  
**Report:** `report_3c594fcc7613`  
**Scenario:** fictional Städtischer Klinikverbund Falkenbrück / AURORA (`Nexora Triage Assist`)

This reference run evaluates a decision about whether an AI-assisted triage and documentation system should launch simultaneously at two hospital sites, start in a staged pilot at Falkenbrück-Mitte, or be delayed.

The report was intentionally regenerated from the **same completed simulation** used by the preceding AURORA report. This makes it an observational reporter/pipeline reference: changes in output quality and runtime can be compared without introducing a different stochastic simulation trace.

## What the run demonstrates

- six report sections generated from the same completed simulation,
- source retrieval through `insight_forge`, `panorama_search`, and `quick_search`,
- targeted `interview_agents` calls across the report rather than only near the end,
- an Evidence Inspector that exposes claims, hypotheses, confidence and bound evidence,
- direct `agent_interview` evidence cards next to report claims,
- post-generation evidence gating that removes or downgrades unsupported precision,
- materially lower report-generation time than the preceding report over the same simulation.

The resulting recommendation is a **conditioned, staged rollout** beginning at Falkenbrück-Mitte, with explicit safety, training, worker-representation and fallback conditions before expansion.

## Evidence Inspector

[![AURORA report with Evidence Inspector, section list, claims and hypotheses](../../assets/screenshots/reference-runs/2026-08-14-aurora/01-evidence-inspector.jpg)](../../assets/screenshots/reference-runs/2026-08-14-aurora/01-evidence-inspector.jpg)

The screenshot is clickable and opens the repository image directly. The inspector is intentionally shown because the report is not evaluated by prose alone: claims and hypotheses can be inspected alongside their bound evidence records.

## Agent interviews as evidence

[![AURORA report with simulated persona quote and agent interview evidence cards](../../assets/screenshots/reference-runs/2026-08-14-aurora/02-agent-interviews.jpg)](../../assets/screenshots/reference-runs/2026-08-14-aurora/02-agent-interviews.jpg)

This view shows the connection between generated report prose, a simulated persona statement and `agent_interview` evidence records. This is the part of the workflow that distinguishes the report from a document-only RAG summary.

## Why this is a reference run, not a showcase

Known limitations visible in the artifact include:

- a documented seed fact about **38 cases with a different urgency suggestion** is still downgraded as if no matching numerical evidence existed in some sections,
- some interview quote anchors still resolve to the generic `seed_doc:seed_aurora#chunk:0` anchor instead of a precise interview record,
- confidence can remain `low` even for strongly matching `SUPPORTED` evidence,
- the ReportV3 artifact can still fail validation while the overall report task reaches a completed state,
- simulation-network metrics such as cluster/bridge structure are present in the evidence data but are underused in the final prose.

The repository currently does **not** contain every artifact, fixture and replay input required to reproduce this exact run from a fresh checkout. It is therefore an **observational regression reference, not a fully reproducible Golden Run**.

## Regression expectations

Future report-pipeline changes can compare against this run and should verify at least:

1. the `38 cases` seed fact is bound as supported evidence wherever the claim does not overreach the source;
2. simulated persona quotes point to concrete `agent_interview` evidence rather than a generic seed anchor;
3. `SUPPORTED` source facts are not automatically emitted as `low` confidence;
4. a failed canonical report contract cannot produce a misleading fully-completed state;
5. prompt requirements for early-warning indicators, stop/expand criteria and actor reaction chains remain represented in the final report.

[Deutsche Version](./README.de.md)
