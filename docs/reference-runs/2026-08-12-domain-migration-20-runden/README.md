# Reference run 5: domain migration, 20 rounds, post-hardening trust audit

*English · [Deutsch](./README.de.md)*

> [!IMPORTANT]
> This run documents Agora's behavior in a simulated multi-agent environment. It is **not** evidence that the simulated personas represent real people, that the recommendation is correct, or that the simulation predicts human behavior.

## Why this is the current reference run

This run moves the reference question one layer deeper than [reference run 4](../2026-08-11-ki-lernassistent-20-runden/README.md).

Reference run 4 established that evidence binding can work at useful scale: 39 validated claims after five predecessor reports had bound zero or one. Its dominant failures were still mechanical, including invented provenance anchors, a confidence measure with one value, inconsistent entailment, and non-stakeholder personas.

The 2026-08-12 domain-migration run is more useful as a reference for the current trust architecture because the binding pipeline now survives long enough to expose a harder failure class: **Agora can bind a statement to the correct source fragment while still losing the epistemic status of that fragment.** A sentence that the seed document explicitly marks as unsupported can therefore reappear as a validated world-fact merely because the sentence occurs in the source.

That is a more mature failure than "no evidence was bound", but also a more dangerous one: the output looks auditable while the audit semantics are incomplete.

## Run identity

| Field | Value |
|---|---|
| Report ID | `report_fb5dfaf69ffa` |
| Generated | `2026-08-12T13:57:13.249205+00:00` |
| Scenario | migration `alexle135.de` → `alex-schneider.dev` |
| Report mode | `balanced` |
| Rounds | **20 / 20**, simulation already finished when report generation started |
| Report model | not exported in the supplied Markdown artifact |
| Simulation ID | not exported in the supplied Markdown artifact |
| Graph ID | not exported in the supplied Markdown artifact |

The missing model/run identifiers are recorded as missing metadata instead of being reconstructed from surrounding logs.

## Report snapshot

| Metric | Value |
|---|---:|
| validated claim rows | **46** |
| unique rendered claim IDs | **22** |
| hypotheses | **141** |
| data gaps | **133** |
| post-generation downgrades | **0** |
| evidence-index entries | **70** |
| claim confidence | 45 `low`, 1 `medium` |
| rendered confidence scope | 46 × `Simulationskonsens` |
| rendered claim basis | 46 × `persona` |
| total interactions | **109** |
| clusters | **3** |
| echo chamber index | **0.5963** |

Evidence-index composition: 33 simulated agent quotes, 16 seed-document items, 13 graph relations/metrics, and 8 simulated agent actions.

For the 46 validated claim rows, the support composition is more revealing: **38 are seed-only**, 6 quote-only, 1 seed plus quote, and 1 action-only. That conflicts with the renderer labeling every validated claim as `Simulationskonsens` with basis `persona`.

## What works in this run

- All **20 of 20 rounds** completed before report generation.
- Evidence binding is active at useful scale instead of producing zero or one bound claim.
- Canonical evidence classes reach the report: seed document, simulated quote, simulated action, and graph relation.
- Unsupported numerical targets are routed to insufficient/unsupported states instead of silently becoming facts.
- The strong statement that Option B is the "only viable" strategy is not accepted as a supported fact.
- The report keeps **141 hypotheses** and **133 data gaps** visible rather than folding them into validated claims.

## Critical finding 1: source occurrence is mistaken for source truth

The adversarial seed deliberately contains the statement that the old domain is "practically worthless for Google" **and explicitly classifies that statement as unsupported**.

The report nevertheless validates a claim whose wording presents the proposition as document-backed, using the seed fragment containing that unsupported assertion as evidence. Elsewhere in the same report, Agora correctly describes the same proposition as a postulate that is not empirically supported.

The report can therefore express both:

1. "the document proves X", and
2. "the document merely asserts X without evidence".

This isolates the missing contract: provenance captures **where text came from**, but not reliably **what epistemic status the source assigned to that text**.

A seed-corpus evidence item needs an assertion status such as `documented_fact`, `internal_claim`, `hypothesis`, `synthetic_statement`, `unverified_data`, `contradiction`, or `unknown`. A `seed_corpus + unverified_claim` item may support the meta-claim **"the source states X"**. It must not by itself validate the world-claim **X**.

## Critical finding 2: foreign-role takeover reaches validated evidence

The only `medium` claim is a simulated quote from `lisa_hartmann_610` saying the migration strengthens **her** personal brand as a self-employed software developer and IT consultant. The migration concerns Alexander Schneider's domain, not Lisa Hartmann's. The answer has taken over the subject's role.

The raw interview should remain in the trace, but a foreign-role answer should be ineligible as claim-supporting `agent_quote` evidence. Here it survives binding and becomes the strongest-confidence claim in the report, making it a useful regression fixture for identity/role guarding.

## Critical finding 3: evidence scope is rendered incorrectly

All 46 validated claim rows render as:

```text
scope = Simulationskonsens
basis = persona
```

Yet **38 are supported only by seed-document evidence**. This is not cosmetic. A source-bound claim and a simulation-consensus claim express different trust semantics and must not share the same scope label.

## Critical finding 4: the gate knows more than the final prose

The trust layer correctly rejects or weakens several unsupported numbers and the claim that Option B is uniquely viable. Strong formulations can nevertheless remain in visible section prose while later gate tables classify them as hypothesis, insufficient, contradicted, or merely related evidence.

The final report therefore needs a reconciliation stage after gating. Sentences ending in `INSUFFICIENT`, `CONTRADICTED`, or `related_evidence_only` should be removed or rewritten as explicitly qualified hypotheses.

## Critical finding 5: simulated authority can look like real authority

The evidence index contains a simulated persona with `persona_id="google_692"`. Its statements are stored as `Agentenzitat`, not as official web sources. Renderer language must preserve that distinction: simulated persona → "simulated search-engine perspective"; official documentation → `web_source` with provenance.

## Critical finding 6: non-stakeholder eligibility is improved, not solved

Older runs admitted obvious software/product entities as personas. This run is cleaner, but the evidence index still contains:

```text
Fachblog CREATE_POST on reddit in round 0
```

A technical blog is content/media, not an individual or collective stakeholder. The report artifact does not export `generation_source`, so this run does **not** prove whether the entity came through the normal or degraded persona path. It only proves that a non-stakeholder still reached the final simulation.

## Auditability issue: claim IDs are not globally unique in the flat export

The report contains **46 claim rows but only 22 unique `claim_*` IDs**. The IDs may be section-scoped internally, but the Markdown renderer does not expose that scope. Human references such as `claim_07` are therefore ambiguous. Report-level IDs should be globally unique or include the section scope in the rendered identifier.

## Simulation dynamics: weaker signal than reference run 4

| Metric | Reference run 4 | This run |
|---|---:|---:|
| rounds | 20 | 20 |
| validated claims | 39 | **46** |
| hypotheses | 141 | 141 |
| data gaps | 131 | 133 |
| social actions / interactions | **665** | 109 |
| clusters | **6** | 3 |
| echo chamber index | 0.5741 | 0.5963 |

The new run yields about **5.45 interactions per configured round**, versus about **33.25 actions per round** in reference run 4. This is a red flag, not a proven regression: agent count, provider/model routing, action configuration, and recommender behavior can materially change the dynamics.

This run is therefore the better **trust-pipeline reference**; reference run 4 remains the richer **simulation-dynamics reference**.

## What this run demonstrates

- Evidence binding works at useful scale.
- Seed-document provenance reaches the report.
- Numerical prose gating catches several unsupported targets.
- Many hypotheses and data gaps remain separated from validated claims.
- The remaining failures are concrete enough for deterministic regression tests.
- The domain-migration seed is a strong adversarial fixture for trust-layer development.

## What this run explicitly does not demonstrate

- **No predictive validity.**
- **No real recruiter, employer, Google, or user research.**
- **No proof that the recommended migration strategy is objectively best.**
- **No complete epistemic provenance yet.**
- **No guarantee that a validated claim is a true world-fact merely because its source span is real.**
- **No proof that the lower interaction count is a simulation regression.**

## Remediation priority

1. **P1 — preserve seed assertion status end to end.** Unsupported, hypothetical, or synthetic source spans must not validate direct world-facts.
2. **P1 — reject foreign-role interview answers from claim-supporting evidence.** Preserve the raw trace, block evidence eligibility.
3. **P2 — reconcile final prose with the final gate verdict.** `INSUFFICIENT`, `CONTRADICTED`, and related-only statements must be qualified or removed.
4. **P2 — render the correct confidence scope and basis.** Seed-bound claims must not appear as simulation consensus.
5. **P2 — harden persona eligibility against content objects such as `Fachblog`.**
6. **P3 — make exported claim identifiers globally unambiguous.**
7. **P3 — centralize risk objects so summary/detail likelihood and impact cannot drift.**

## Artifacts

- Machine-readable audit summary: [`artifacts/run-summary.json`](./artifacts/run-summary.json)
- Source report: `report_fb5dfaf69ffa` (full Markdown export retained with the run audit outside this repository snapshot)

## Conclusion

Reference run 4 proved that Agora could finally bind evidence. Reference run 5 shows the next boundary: **binding the correct source is not enough if the system forgets whether the source itself called the statement a fact, hypothesis, synthetic statement, contradiction, or unsupported assertion.**

That is why this is the current reference run. It is not the prettiest simulation and not the richest social trace. It is the clearest end-to-end test of the trust architecture Agora is trying to make stable for 1.0.
