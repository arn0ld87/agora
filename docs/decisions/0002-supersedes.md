# ADR-0002-S — Der Entailment-Judge darf in der Grauzone belegen

**Status:** Accepted
**Datum:** 2026-08-17
**Löst ab:** die Judge-Klausel aus [ADR-0002](0002-evidence-gating.md), präzisiert in [ADR-0011](0011-evidence-entailment-and-provenance.md) §„Zwei Stufen"
**Bezug:** [#1357](https://github.com/arn0ld87/agora/issues/1357), [`backend/app/services/evidence_entailment.py`](../../backend/app/services/evidence_entailment.py), [`backend/app/services/llm_entailment_judge.py`](../../backend/app/services/llm_entailment_judge.py)
**Sign-off:** arn0ld87

---

## Was abgelöst wird

ADR-0011 formulierte es so:

> Ein optionaler LLM-Judge darf ein regelbasiertes `SUPPORTED` nur
> abschwächen, nie erzeugen.

Diese Klausel entfällt für den qualitativen Pfad (Regel 3). Für die
deterministischen Regeln 1 und 2 — Zahl, Bezugsgruppe, Mengenaussage — gilt
sie unverändert weiter: dort entscheidet die Regel, und der Judge wird gar
nicht erst gefragt.

## Warum

Die Klausel war korrekt, solange Regel 3 selbst großzügig `SUPPORTED` vergab.
Sie tat das über Containment: sobald der Evidence-Text Teilmenge des Claims
war, galt der Claim als belegt. Der Judge war damit die einzige Instanz, die
diese Großzügigkeit noch bremsen konnte — ein reiner Sicherheitsmechanismus.

Gemessen an einem vollständigen 7-Sektionen-Lauf war das Ergebnis:

```
Claim-Evidence-Paare              80
  SUPPORTED                       24   ausnahmslos aus dem lexikalischen Zweig
  containment (Median)          1.00   Evidence ⊆ Claim
  coverage    (Median)          0.21   der Claim behauptet das Fünffache
```

Konkret band die Aussage „Der ungestaffelte Vollstart birgt gravierende
Risiken für Patientensicherheit, Prozessstabilität und Mitarbeiterakzeptanz"
an das Snippet „Der Städtische Klinikverbund Falkenbrück plant unter dem
Projektnamen AURORA die Einführung des Systems Nexora Triage Assist."

Mit umgedrehter Deckungsrichtung ist der Deckel nicht mehr Sicherung, sondern
Sperre. Er hätte drei Folgen, alle unerwünscht:

1. **Die Grauzone wäre für immer `RELATED_ONLY`.** Zwischen den Schwellen
   liegt genau das, was ein lexikalisches Maß nicht entscheiden kann. Im
   Referenzlauf fallen dort 77 der 80 Paare hin.
2. **Interviews könnten nie binden.** Ihre lexikalische Deckung liegt im
   Median bei 0.02, im Maximum bei 0.29 — ein Interviewzitat sagt dasselbe in
   anderen Worten. Da `EvidenceType.agent_interview` auf
   `EvidenceSourceKind.agent_quote` abgebildet wird und
   `cross_stakeholder_for_high` genau diese Gattung verlangt, wäre
   `high`/`verified` **strukturell unerreichbar**. Der Referenzlauf zeigt das:
   alle 16 Claims `low`, 0 Interview-Bindungen, 0 `agent_quote` in den
   `evidence_refs`.
3. **Kein Weg zurück zur alten Großzügigkeit.** Die einzige Alternative wäre,
   die Schwelle abzusenken — und damit exakt den AURORA-Fall zu
   reproduzieren.

Die Klausel schützte also nicht mehr vor ungedeckten Claims. Sie verhinderte,
dass gedeckte Claims überhaupt als gedeckt erkennbar werden.

## Was an ihre Stelle tritt

Der Judge urteilt nur dort, wo keine Regel urteilt, und nur dort, wo das
lexikalische Maß nachweislich nicht trennt:

| Deckung `coverage_ratio(claim, evidence)` | Entscheidung |
|---|---|
| ≥ 0.60 | `SUPPORTED`, regelbasiert |
| < 0.10 ohne Retrieval-Signal | `RELATED_ONLY`, regelbasiert |
| dazwischen | Judge; ohne Judge `RELATED_ONLY` |

Vier Grenzen bleiben:

- **Regel 1 und 2 sind vorgelagert und bindend.** Ein regelbasiertes
  `CONTRADICTED` erreicht den Judge nie — es kehrt vorher zurück.
- **Kein Judge im Fließtext-Check.** `verify_prose` prüft ausschließlich
  numerische Sätze; die laufen über Regel 1.
- **Budget durch `top_k` gedeckelt.** Der Binder klassifiziert erst nach dem
  Kürzen auf die besten Retrieval-Treffer. Referenzlauf: höchstens 5 Calls je
  Claim, 77 insgesamt.
- **Ausfall fällt auf den Regelpfad.** Exception oder unbekanntes Verdikt →
  `judge_failed`, die Grauzone endet bei `RELATED_ONLY`. Der Report wird
  dadurch vorsichtiger, nicht falscher.

## Die fünf Hartanker bleiben unberührt

Prompt-Block in `report_prompts/sections.py`, Hedge-Snapshot,
`EvidenceSourceKind`, `cross_stakeholder_for_high`,
`reject_inferred_in_high_confidence` — keiner davon wird angefasst. Anker 4
wird durch diese Änderung erstmals überhaupt erfüllbar, nicht geschwächt.

## Risiko

Die Grauzone 0.10–0.60 ist an einem Lauf kalibriert, nicht an einer
Stichprobe. Ist der Judge zu großzügig, kehrt der AURORA-Fall zurück; ist er
zu streng, bricht die Claim-Zahl ein. Beides ist an den Checks
(`high_claim_coverage`, `judge`, `grey_zone_unjudged`) im
`gate_decision_log` ablesbar und ohne Vertragsänderung nachjustierbar.
