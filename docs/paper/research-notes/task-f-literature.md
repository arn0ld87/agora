# Task F — Wissenschaftliche Literatur

AS_OF: 2026-08-09
Recherche über firecrawl research_search_papers (arXiv-/PMC-Index) sowie WebSearch. Fokus: peer-reviewed Publikationen, arXiv-Papers etablierter Gruppen, offizielle Tech-Docs. Belegstatus-Legende: **belegt** = formal/mathematisch oder experimentell mehrfach bestätigt; **beobachtet** = empirisch in einer Studie beobachtet, Replikation offen; **plausibel** = theoretisch oder mechanistisch begründet, noch nicht breit repliziert; **spekulativ** = Hypothese/Meinung ohne starke Evidenz.

## Sources (kanonische IDs, Titel, Autoren, Jahr, Source-Type, Authority 1-10)

| # | ID | Titel | Erstautor | Jahr | Source-Type | Authority |
|---|---|---|---|---|---|---|
| S01 | arxiv:2304.03442 | Generative Agents: Interactive Simulacra of Human Behavior | Park, J.S. et al. | 2023 | academic (arXiv, UIST'23) | 9/10 |
| S02 | arxiv:2209.06899 | Out of One, Many: Using Language Models to Simulate Human Samples | Argyle, L. et al. | 2022 | academic (arXiv, Political Analysis) | 9/10 |
| S03 | arxiv:2301.07543 | Large Language Models as Simulated Economic Agents (Homo Silicus) | Horton, J.J. | 2023 | academic (arXiv, NBER) | 8/10 |
| S04 | pmcid:PMC11127003 | Can Generative AI improve social science? | Bail, C.A. | 2024 | academic (PNAS) | 9/10 |
| S05 | arxiv:2404.16130 | From Local to Global: A Graph RAG Approach to Query-Focused Summarization | Edge, D. et al. (Microsoft) | 2024 | academic/official (arXiv, Microsoft) | 9/10 |
| S06 | arxiv:2408.08921 | Graph Retrieval-Augmented Generation: A Survey | — et al. | 2024 | academic (arXiv survey) | 7/10 |
| S07 | arxiv:2305.14325 | Improving Factuality and Reasoning in Language Models through Multiagent Debate | Du, Y. et al. | 2023 | academic (arXiv, ICLR'24) | 8/10 |
| S08 | arxiv:2203.11171 | Self-Consistency Improves Chain of Thought Reasoning in Language Models | Wang, X. et al. | 2022 | academic (arXiv, ICLR'23) | 9/10 |
| S09 | arxiv:2410.12853 | Diversity of Thought Elicits Stronger Reasoning in Multi-Agent Debate | — et al. | 2024 | academic (arXiv) | 6/10 |
| S10 | arxiv:2407.05778 | When is the consistent prediction likely to be a correct prediction? | — et al. | 2024 | academic (arXiv) | 6/10 |
| S11 | arxiv:2503.13657 | Why Do Multi-Agent LLM Systems Fail? (MAST-Data) | — et al. | 2025 | academic (arXiv) | 7/10 |
| S12 | arxiv:2505.11556 | Systematic Failures in Collective Reasoning under Distributed Information (HiddenBench) | — et al. | 2025 | academic (arXiv) | 6/10 |
| S13 | arxiv:2607.05775 | Beyond the Leaderboard: Synthesis of Tool-Use, Planning, Reasoning Failures in LLM Agents | — et al. | 2026 | academic (arXiv synthesis) | 6/10 |
| S14 | arxiv:2404.05090 | How Bad is Training on Synthetic Data? Statistical Analysis of Language Model Collapse | — et al. | 2024 | academic (arXiv, ICML'24) | 8/10 |
| S15 | arxiv:2509.13397 | The threat of analytic flexibility in using LLMs to simulate human data | — et al. | 2025 | academic (arXiv) | 7/10 |
| S16 | arxiv:2504.08260 | Evaluating the Bias in LLMs for Surveying Opinion and Decision Making in Healthcare (UAS digital twins) | — et al. | 2025 | academic (arXiv) | 6/10 |
| S17 | arxiv:2504.18346 | Comparing Uncertainty Measurement and Mitigation Methods for LLMs (Systematic Review) | — et al. | 2025 | academic (arXiv review) | 7/10 |
| S18 | arxiv:2605.06635 | Cited but Not Verified: Parsing and Evaluating Source Attribution in LLM Deep Research Agents | — et al. | 2026 | academic (arXiv) | 7/10 |
| S19 | arxiv:2507.22915 | Theoretical Foundations and Mitigation of Hallucination in LLMs | — et al. | 2025 | academic (arXiv) | 7/10 |
| S20 | arxiv:2502.08691 | AgentSociety: Large-Scale Simulation of LLM-Driven Generative Agents | — et al. | 2025 | academic (arXiv) | 6/10 |
| S21 | arxiv:2311.17311 | Framework-Based Qualitative Analysis of Free Responses of LLMs: Algorithmic Fidelity | — et al. | 2023 | academic (arXiv) | 6/10 |
| S22 | arxiv:2601.04742 | Tool-MAD: Multi-Agent Debate Framework for Fact Verification with Diverse Tool Augmentation | — et al. | 2026 | academic (arXiv) | 5/10 |

## Findings (max 15 Sätze, je mit [Quelle-ID] und Belegstatus)

1. [S01] **beobachtet**: Park et al. zeigen in einer 25-Agenten-Sandbox, dass Memory+Reflection+Planning-Architektur glaubwürdiges menschenähnliches Verhalten über mehrere Tage erzeugt; Validierung erfolgte nur qualitativ/interview-basiert, nicht populationsrepräsentativ.
2. [S02] **beobachtet**: Argyle et al. demonstrieren, dass GPT-3 mit demografischem Conditioning Antwortverteilungen realer US-Subpopulationen reproduziert ("silicon samples"); Effekte sind feinkörnig und demografisch korreliert, aber abhängig von Prompt-Format.
3. [S15] **beobachtet**: Über 252 Silicon-Sample-Konfigurationen hinweg variiert die Übereinstimmung mit Humandaten drastisch mit Modell, Prompt-Format und Sampling-Parametern — analytische Flexibilität bedroht Reproduzierbarkeit ("P-hacking-Äquivalent").
4. [S16] **beobachtet**: Digitale Zwillinge auf Basis der UAS-Gesundheitsstudie reproduzieren demografische Muster nur unvollständig; LLM-Antworten weisen systematische Bias auf, die nicht durch besseres Demographic-Conditioning verschwinden.
5. [S03] **beobachtet**: Horton zeigt, dass LLMs klassische experimentelle Wirtschaftsergebnisse (Charness-Rabin, Kahneman etc.) qualitativ replizieren; Abweichungen sind meist "wrong in plausible ways" — Homo Silicus ist nützliche Approximation, kein validated simulator.
6. [S04] **plausibel**: Bail argumentiert, dass GenAI survey research, Online-Experimente, automatisierte Inhaltsanalyse und agent-based models im Sozialwissenschaften verbessern kann, warnt aber ausdrücklich vor Homogenität, Halluzination und fehlender Validierung als zentrale Risiken.
7. [S11] **beobachtet**: Über 1600 annotierte Traces in 7 MAS-Frameworks zeigt MAST-Data, dass MAS-Fehler in 3+ Klassen zerfallen (Specification-Unterbestimmung, Inter-Agent-Misalignment, Task-Coverage); Performance-Gewinne auf Benchmarks sind oft minimal.
8. [S12] **beobachtet**: HiddenBench zeigt, dass Multi-Agent-LLMs unter verteilter Information nur 30,1 % Accuracy erreichen vs. 80,7 % für Einzelagenten mit voller Info — Kollektivreasoning versagt systematisch am Hidden-Profile-Problem.
9. [S07] **beobachtet**: Du et al. berichten, dass Multi-Agent-Debate über mehrere Runden Factuality und Reasoning auf Biografie-/Math-Aufgaben verbessert; Effekt ist bei kleinen Modellen stärker und sättigt bei großen Modellen aus.
10. [S09] **beobachtet**: Diversity-of-Thought-Anreicherung (verschiedene Persona-Prompts) steigert MAD-Gewinne auf Math-Reasoning; ohne Diversität konvergieren Agenten zu einheitlichen Fehlern.
11. [S10] **beobachtet**: Selbstkonsistenz korreliert nur bedingt mit Korrektheit — längere Reasoning-Texte erzeugen eher konsistente Antworten, was "consistency ≠ truth" empirisch untermauert und Wang et al.'s ursprüngliche Annahme nuanciert.
12. [S08] **belegt**: Self-Consistency (Wang et al.) verbessert Chain-of-Thought-Antworten durch Marginalisieren über mehrere sampled Reasoning Paths signifikant; Effekt auf Arithmetic/Commonsense/Multi-Step-Reasoning mehrfach repliziert.
13. [S05] **belegt**: Edge et al. (Microsoft) zeigen, dass GraphRAG mit hierarchischer Leiden-Community-Summary globale QFS-Fragen ("Hauptthemen im Korpus") besser beantwortet als vector-RAG; lokale Fragen bleiben vergleichbar.
14. [S14] **belegt**: Statistische Analyse des Model Collapse zeigt, dass rekursives Training auf model-generierten Daten die Verteilungsschwerpunkte verengt und Randbereiche vergisst — Effekt ist mathematisch charakterisierbar und empirisch bestätigt.
15. [S18] **beobachtet**: Ein AST-basiertes Evaluationsframework für LLM-Deep-Research-Agents findet, dass Inline-Zitationen häufig "cited but not verified" sind — Quellen werden angegeben, sind aber oft nicht zugänglich, irrelevant oder faktisch inkonsistent, ein direkter Befund für Provenance-Anforderungen wie Agoras Evidence-Gating.

## Themen-Cluster (pro Thema 2-4 Quellen + Kernaussage)

### LLM Multi-Agent Systems (Evaluierung, Failure Modes)
- [S11] MAST-Data: 1600+ Traces, 7 Frameworks — MAS-Fehler sind klassifizierbar, Benchmark-Gewinne oft minimal.
- [S12] HiddenBench: Kollektivreasoning versagt unter verteilter Information (30,1 % vs. 80,7 %).
- [S13] Beyond-the-Leaderboard-Synthese: 27 Benchmarks/Taxonomien, 19 Benchmarks — Tool-Use, Planning, Long-Horizon, Multi-Agent-Coordination zeigen wiederkehrende Fehlermuster.
- Kernaussage: Multi-Agent-Systeme sind anfällig für Spezifikationslücken, Inter-Agent-Misalignment und kollektiven Reasoning-Zusammenbruch; Benchmarks überzeichnen Nutzen.

### Synthetic Personas & Generative Agents
- [S01] Park et al.: Architecture Memory+Reflection+Planning erzeugt glaubhafte Simulacra in 25-Agenten-Sandbox.
- [S02] Argyle et al.: GPT-3 als "silicon sample" reproduziert demografische Antwortverteilungen bei passendem Conditioning.
- [S20] AgentSociety: Framework für große LLM-getriebene agent-basierte Gesellschaftssimulation.
- Kernaussage: Synthetische Personas sind praktisch nützlich, aber ihre Validität hängt stark von Prompt-Design und demografischem Conditioning ab; genuine Populationsrepräsentation ist nicht gezeigt.

### Agent-based Social Simulation mit LLMs
- [S03] Horton — Homo Silicus: LLMs als wirtschaftliche Agenten; repliziert klassische Ergebnisse qualitativ.
- [S20] AgentSociety: skalierbare Bottom-up-Simulation sozialer Dynamiken.
- [S22] Tool-MAD: fact-verification-orientierte Multi-Agent-Debate mit Werkzeug- und Retrieval-Erweiterung.
- Kernaussage: LLM-basierte soziale Simulation liefert qualitativ plausible Muster, ersetzt aber keine kontrollierte empirische Validierung gegen reale Populationsdaten.

### LLM-based Social Science
- [S04] Bail (PNAS): GenAI-Potenzial für survey research, Experimente, Content-Analyse, ABM; Warnung vor Homogenität/Halluzination.
- [S15] Analytic Flexibility: 252 Konfigurationen — Ergebnis hängt stark an Prompt/Sampling/Modell.
- [S16] UAS-Digital-Twins: unvollständige Replikation, persistenter Bias.
- Kernaussage: LLMs als Sozialforschungswerkzeug sind vielversprechend, aber p-hacking-anfällig und validierungsbedürftig; analytische Flexibilität ist eine zentrale methodische Bedrohung.

### GraphRAG
- [S05] Edge et al. (Microsoft): hierarchische Community-Summaries lösen globale QFS-Aufgaben, die vector-RAG verfehlt.
- [S06] GraphRAG-Survey: strukturbezogene RAG-Variante reduziert Halluzinationen und verbessert Multi-Hop-Reasoning.
- Kernaussage: GraphRAG übertrifft Standard-RAG bei globalen, korpusweiten Fragen; bei lokalen Faktenfragen ist der Mehrwert geringer.

### Provenance Tracking & Retrieval Grounding & Evidence Attribution
- [S18] Cited but Not Verified: AST-basierte Evaluation zeigt systematisch fehlerhafte/irrelevante Quellen-Zitationen.
- [S06] GraphRAG-Survey: strukturierter RAG reduziert Halluzinationen durch explizite Entity-Beziehungen.
- Kernaussage: Quellenangabe allein ist kein Validitätsbeweis; Provenance muss aktiv verifiziert werden (Passung zu Agoras Evidence-Gating).

### Hallucination Detection & Calibration & Uncertainty Estimation
- [S17] Systematic Review UQ: Halluzination bleibt Top-Herausforderung; Kalibrierung schlägt Fehlanpassung zwischen Unsicherheit und Genauigkeit vor.
- [S19] Theoretical Foundations: formale Hallucinations-Definition, PAC-Bayes/Rademacher-Bounds, Detektionsstrategien (token-level UE, Kalibrierung).
- Kernaussage: Uncertainty-Estimation ist unzuverlässig in niedrigen Informationsregimen; Kalibrierung ist notwendig, aber nicht hinreichend.

### Ensemble Methods, Multi-Agent Debate, Self-Consistency
- [S07] Du et al.: MAD verbessert Factuality über mehrere Runden.
- [S08] Wang et al.: Self-Consistency marginalisiert über Reasoning-Paths (belegt, ICLR'23).
- [S09] Diversity of Thought: Diversifikation verstärkt MAD-Gewinne.
- [S10] Consistency ≠ Truth: Konsistenz korreliert nur bedingt mit Korrektheit.
- Kernaussage: Ensemble-Methoden bringen echten, aber begrenzten Mehrwert; ohne Diversität und ohne externe Verifikation erzeugen sie Schein-Evidenz (Konsens statt Korrektheit).

### Synthetic Data Risks (Self-Reinforcement, Model Collapse)
- [S14] Statistical Model Collapse: rekursives Training auf model-generierten Daten verengt Verteilung, vergisst Ränder (belegt, ICML'24).
- [S15] Analytic Flexibility: 252 Konfigurationen zeigen Ergebnis-Drift.
- Kernaussage: Synthetische Daten unterliegen Selbstverstärkung; ohne echte humanoide Daten oder Mischungsstrategien droht Performance-Degradation und Bias-Verstärkung.

### Evaluation of Agent Simulations / Validation of LLM-as-Social-Simulator
- [S16] UAS-Digital-Twins: unvollständige Replikation realer Survey-Daten.
- [S13] Beyond-the-Leaderboard: Synthese von Agent-Fehlern über 27 Studien.
- [S11] MAST-Data: MAS-Fehler-Klassifikation.
- Kernaussage: Es fehlt an standardisierten Validierungsprotokollen; Populate-Reproduktion vs. Realdaten ist die Ausnahme, nicht die Regel.

## Synthese: Persona-Validität (was Literatur zu synthetischen Personas sagt)

Die Literatur ist vorsichtig-optimistisch, aber in der Validitätsfrage kritisch. Argyle et al. (S02) zeigen, dass LLMs mit demografischem Conditioning Antwortverteilungen reproduzieren können; Horton (S03) liefert qualitative Replikationen klassischer Experimente. Gleichzeitig relativieren neuere Studien dies: UAS-Digital-Twins (S16) und analytic flexibility (S15) zeigen, dass die Übereinstimmung stark von Prompt-Format, Modell, Sampling-Parametern und demografischem Detailgrad abhängt — reproduzierbare Resultate erfordern fixierte Pipelines. Bail (S04) warnt vor Homogenität und Halluzination als strukturellen Limitationen. Park et al. (S01) liefern keine populationsrepräsentative Validierung, sondern ein qualitatives Simulacrum-Konzept. Zusammen: **Synthetische LLM-Personas sind nützliche Heuristiken und Sandboxes, aber valide Repräsentationen realer Populationen sind nicht belegt — Bias, Homogenität und analytische Flexibilität sind die Hauptbedenken.**

## Synthese: Multi-Agent-Debate / Self-Consistency — echter Mehrwert?

Du et al. (S07) und Wang et al. (S08) liefern robuste, replizierte Belege für begrenzte Faktualitäts- und Reasoning-Gewinne. Diversity of Thought (S09) zeigt, dass der Gewinn ohne Diversifikation schrumpft. [S10] nuanciert: Konsistenz korreliert nur teilweise mit Korrektheit — längere Reasoning-Texte erzeugen Konsistenz ohne Wahrheitsgewinn. MAST-Data (S11) und HiddenBench (S12) zeigen, dass MAS auf verteilten/kollektiven Aufgaben systematisch versagen. **Fazit: Multi-Agent-Debate und Self-Consistency liefern einen echten, aber begrenzten Zuverlässigkeitsgewinn auf isolierten Reasoning-Aufgaben; ohne externe Evidenzverifikation erzeugen sie eher Konsens-Evidenz als Wahrheits-Evidenz. Für Agora bedeutet das: Debate/Ensemble ersetzt nicht das Evidence-Gating, sondern ergänzt es.**

## Synthese: GraphRAG vs Standard-RAG (Belege)

Edge et al. (S05, Microsoft) belegen, dass GraphRAG mit hierarchischer Leiden-Community-Summary globale korpusweite Fragen ("Hauptthemen") beantwortet, an denen vector-RAG scheitert, weil letzteres ein QFS- und kein Retrieval-Problem ist. Die GraphRAG-Survey (S06) bestätigt, dass strukturierter RAG Halluzinationen reduziert und Multi-Hop-Reasoning verbessert. Gleichzeitig zeigen Folgearbeiten (E²GraphRAG, Core-based Hierarchies), dass GraphRAG-Kosten (LLM-Extraktion) signifikant sind und Skalierung Herausforderungen bleibt. **Fazit: GraphRAG ist für globale/themenübergreifende Fragen evidenzbasisiert überlegen; für lokale Faktenfragen ist der Mehrwert gering. Für Agoras Dokumenten-Provenance-Ansatz (ADR-0013) stützt das die Wahl graph-basierter Strukturierung für thematische Aggregation, ohne vector-RAG für Einzelfakten abzuwerten.**

## Gaps (welche Themen wenig abgedeckt)

- **Standardisierte Persona-Validierungsprotokolle**: Es fehlt ein Kanon, wie LLM-Personas gegen reale Populationsstatistiken systematisch validiert werden (nur punktuelle Fallstudien wie S16).
- **Provenance-Verifikation vs. Provenance-Attribution**: Cited-but-not-Verified (S18) ist eines der wenigen systematischen Frameworks; Verifikation von Zitations-Pfaden ist untererforscht.
- **Langfristige Multi-Agent-Simulationsstabilität**: Park et al. (S01) testen Tage, AgentSociety (S20) skaliert, aber Drift/Homogenisierung über Wochen wird kaum systematisch gemessen.
- **GraphRAG-Kosten/Nutzen-Trade-off**: wenig vergleichende Eval gegen vector-RAG bei festem Budget; Effizienz-Variants (E²GraphRAG, Practical GraphRAG) sind erst 2025/2026 entstanden.
- **Debate + Provenance-Integration**: kaum Studien kombinieren Multi-Agent-Debate mit aktiver Quellenverifikation (PROClaim 2603.28488 ist eine Ausnahme); für Agora relevant, da Evidence-Gating + Debate kombiniert werden sollen.
- **DACH-spezifische Persona-Bias**: alle identifizierten Studien nutzen US-Datensätze (UAS, GPT-3 US-Conditioning); Übertragbarkeit auf DACH-Populationen ist eine offene empirische Frage.