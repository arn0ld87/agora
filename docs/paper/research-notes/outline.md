# P4 — Evidence-Mapped Outline

Topic-first, nicht task-order-first. Jede Section gemappt auf Findings + Quellen, mit Counter-Claim-Kandidaten und Recency-Checks.

## 0. Executive Summary
- Kernfrage-Antwort: **aktuell Nein** (0 validierte Claims im Referenzlauf R2) — aber Konzept ehrlich und partiell über Prompt-Level [R2, C26, C30, A4]
- Smoking Gun: R1 (25 medium-Claims auf 100% inferred) vs R2 (0 Claims, Gate zu streng für eigenen Throughput) [R1, R2, A3]
- 2 Gesamtscores: Engineering Score hoch / Evidence-Research Score niedrig [L1, L10, L11]
- Counter-Claim: „Agora ist ein unbewiesenes Experiment" — teilweise gerechtfertigt, aber Evidence-Pipeline ist echter Differenzierer [A3, C24, C25]

## 1. Evidence Chain Rekonstruktion (Diagramm)
- 14 Stufen: Seed-Doc → Ingestion → Chunks → KG → Retrieval → Persona → Simulation → Social Actions → Interviews → Report Tools → Evidence Normalization → Evidence Identity → Evidence Index → Claim Binding → Gating → Confidence → Hypothesen/Data Gaps → Renderer → Export [C1–C44]
- 7 Provenance-Verlust-Punkte: graph_build.py:439, neo4j_write.py:244/306-318/443-458, graph_reader.py:57-88, agent.py:315-327, sections.py:196-197 [C11, C15, C16, C17, C19, C21, C10]
- Quellen: Task-A Stufen 1–5, Task-C Stufen 1–10 [C1–C44]

## 2. Evidence-Integrity-Matrix
Pro Evidence-Typ (source_kind): Provenance-Status, Auditierbarkeit, ob nachprüfbar bis Quelle [Task-D Provenance-Klassifizierung]
- seed_corpus: nicht ausreichend auditierbar (Anker opak, Teil B fehlt) [C9, C11, A4]
- agent_quote: teilweise provenance-gesichert (persona_id + quote, aber LLM-generiert) [C22]
- agent_action: teilweise (sim_action_log, rein synthetisch) [C22]
- graph_relation: nur syntaktisch referenzierbar (List[str] ohne doc_id) [C19, C20, C21]
- web_source: teilweise (URL im Anker, Fetch-Echtzeit) [C22]
- inferred: LLM-abgeleitet (bewusst „nicht belegt") [C3, C7]
- Counter-Claim: „Opaker Anker ist immerhin besser als gar kein Anker" — ADR-0013 §Verworfene Alternativen widerlegt: „schlechter als gar kein Anker, weil es Prüfbarkeit vortäuscht" [A4]

## 3. Prompt-vs-Agora-Matrix
Pro Agora-Mechanismus: hat Single-Prompt das auch? [Task-E Komponenten-Matrix]
- Echo-Chamber-Index + apply_echo_cap: Single-Prompt NEIN [C26, C28, C29]
- Wording-Glossar / Anti-Prediction: Single-Prompt NEIN (aber per Instruktion im Prompt erreichbar) [C30]
- Zweistufiges Binding (retrieval vs entailment): Single-Prompt NEIN [C24, C25]
- source_kind-Trennung: Single-Prompt NEIN [C2, C7]
- Red-Team-Review: Single-Prompt teilweise (self-critique) [C32]
- Kanonische evidence_id (SHA-256): Single-Prompt NEIN [C23]
- Multi-Agent-Simulation: Single-Prompt NEIN — aber Mehrwert ungeprüft [C41, L10, L11]
- Counter-Claim: „Ein stärkerer System-Prompt erreicht dasselbe billiger" — gilt für Wording-Glossar/Red-Team, NICHT für echo-cap, evidence_id, zweistufiges Binding [A3, C26]

## 4. Novelty-Matrix (Level 0–4)
Level 0 = Standard-LLM-Prompt; Level 4 = konzeptionell neu in der Forschung [Task-E Differenzierungs-Analyse]
- L0: Report-Erzeugung als Textausgabe
- L1: Strukturierte Claims/Evidence-Felder im Output [C43]
- L2: Pydantic-Contracts, EvidenceSourceKind-Enum, Gating-Validatoren [C2, A1]
- L3: Zweistufiges Binding (Cosine + regelbasiertes Entailment), Determinismus vor Embedding, server-seitiger Anker [C24, C25, A4]
- L4: Echo-Chamber-Index mit apply_echo_cap, Downgrade als Identitätswechsel, Wording-Glossar-Volltext-Snapshot [C26, C23, A1]
- Counter-Claim: „Echo-Cap ist nicht neu — Polarization-Detection existiert" — Agoras Kopplung an Confidence-Cap + Wording-Gate ist die Kombination, die novel ist [C26, C30, L1]

## 5. Failure-Mode-Analyse (≥10)
1. Seed-Provenance end-to-end gebrochen (Teil B fehlt) [C11, A4]
2. Interview→Evidence-Binding-Defekt (R2) [R2]
3. Graph-Fakten ohne Dokumentidentität [C19, C20, C21]
4. Opaker seed_doc:-Anker (LLM nennt eigene Quelle) [C9, C10, A4]
5. medium-Stufe aktuell unerreichbar (has_agent_grounded_evidence braucht seed_corpus) [C8, A4]
6. Gate zu streng für eigenen Throughput → 0 validierte Claims (R2) [R2]
7. Historische Alt-Labels: 25 medium-Claims auf 100% inferred (R1) [R1, A3]
8. Confidence-Konzeptvermischung: key_takeaways high bei claims:[] (R2) [R2]
9. Markdown-Export ohne Producer-Auflösung [C39, C37]
10. Evidence-Map fällt stumm bei contract_violation (Issue #987) [I8, C37]
11. Keine Sim-Validity-Metrik / kein Ground-Truth-Vergleich [C41, L10]
12. Keine Reproduzierbarkeit (Simulation nicht deterministisch) [C42]
13. Kein Baseline-Vergleich Agora vs Single-Prompt [Task-G]
14. Neo4j für Single-User-Local overkill [C40, Task-E]
15. CAMEL http/oasis-Divergenz Wartungslast [C40]
- Counter-Claim: „Einige FM sind bewusst konservativ, nicht Defekte" — gilt für #5/#6 (Gate ist korrekt), aber Upstream liefert keine Evidence → systemisches Versagen, nicht Feature [A4]

## 6. Anti-Self-Confirmation-Analyse
- Agora hat konkrete Mechanismen: echo-chamber-index, apply_echo_cap, Red-Team, Wording-Glossar, source_kind-Trennung, Default inferred, zweistufiges Binding [C26, C30, C25, A3]
- ADR-0011 dokumentiert eigenen Fehler offen (report_d9023bd1f55a) — Engineering-Honesty [A3, R4]
- Caveats: Echo-Cap greift nur bei cross_stakeholder; echo_index misst synthetische Homogenität, keine reale Populationsvalidität; Schwellen hartkodiert, nicht kalibriert [C26, C28, L12]
- Literatur: Konsistenz ≠ Wahrheit (L7), MAD sättigt aus (L5), Kollektivreasoning versagt am Hidden-Profile-Problem (L11) [L5, L7, L11]
- Counter-Claim: „Anti-Self-Confirmation-Mechanismen könnten selbst Confirmation-Bias erzeugen (System vertraut seinem eigenen Gate)" — Gate ist deterministisch und auditierbar, aber ohne externe Ground-Truth bleibt das Gate ein Selbsttest [Task-G, L10]

## 7. Gap Analysis
- Sim-Validity fehlt (zentrale unbewiesene Annahme) [Task-E Gap 1, L10, L13]
- Reproducibility Ziel, nicht Ist [C42, Task-E]
- Baseline-Vergleich Agora-vs-Single-Prompt fehlt [Task-G]
- Chunk-Provenance End-to-End-Test fehlt (nur Parser-Ebene) [Task-G]
- Contract erlaubt Evidence ohne Provenance (test_evidence_without_provenance_still_valid) [Task-G]
- DACH-spezifische Persona-Validität offen (alle Studien US-Datensätze) [L13, Task-F Gap]
- Counter-Claim: „0.10.0-Freigabekriterien decken die Gaps" — ROADMAP listet sie, aber nicht operationalisiert [Task-E]

## 8. Zielarchitektur
- Teil B umsetzen (echte Seed-Provenance: document_id/chunk_id durch Graph bis Anker) [A4]
- Interview-Binding-Defekt fixen (Interviews → kanonische evidence_id) [R2]
- Confidence-Konzepte trennen: simulation_consensus / evidence_confidence / empirical_confidence [A3, C27]
- Baseline-Runner: Agora-vs-Single-Prompt A/B [Task-G]
- Sim-Validity-Metrik gegen Ground-Truth [Task-E, L10]
- Markdown-Export mit Producer-Auflösung [C39]
- Hardstop bei Evidence-Omission statt stummem Fallen [I8, C37]
- Counter-Claim: „Teil B macht Reports schlechter (ADR-0013 §Konsequenzen)" — ja, bewusst; das ist der Zweck [A4]

## 9. Priorisierte Roadmap (P0–P3)
- P0 (Blocker für 1.0): Teil B Seed-Provenance, Interview-Binding-Defekt, Confidence-Konzept-Trennung [A4, R2]
- P1 (Blocker für messbaren Mehrwert): Baseline-Runner, Sim-Validity-Metrik, Reproduzierbarkeit [Task-G, Task-E]
- P2 (Qualität): Markdown-Producer-Auflösung, Hardstop bei Omission, Sim-Validity-Protokoll [C39, I8]
- P3 (Optimierung): Neo4j-Evaluation, CAMEL-Konsolidierung, Redis-optional, large-file-Zerlegung [Task-E]
- Counter-Claim: „P0 zu ambitioniert für 1.0" — ohne P0 bleibt der Kernmehrwert unbewiesen [R2]

## 10. Bewertung (10 Dimensionen, 0–10)
1. Provenance-Architektur (Konzept)
2. Provenance-Umsetzung (Ist)
3. Evidence-Binding/Rigour
4. Confidence-Honesty
5. Anti-Self-Confirmation
6. Testabdeckung
7. Reproduzierbarkeit
8. Sim-Validity/Empirie
9. Komplexitätsökonomie
10. Doku/ADR-Honesty
- Engineering Score = Mittel aus Konstruktions-Dims (1,3,4,5,10)
- Evidence-Research Score = Mittel aus Empirie-Dims (2,6,7,8,9)

## 11. Gesamtscores + abschließendes Urteil
- Engineering Score: ~7.0 (ADR-Honesty, Contracts, Echo-Cap, Wording-Gate hoch; Umsetzung/Repro niedrig)
- Evidence-Research Score: ~3.5 (0 validierte Claims, keine Baseline, keine Sim-Validity, Provenance gebrochen)
- Counter-Claim: „Score zu hart — Agora ist Beta 0.9.3" — genau: Score misst Ist, nicht Potenzial; Beta-Status erklärt niedrigen Empirie-Score, entwertet aber nicht die Befunde [R2, ROADMAP]

## Recency-Checks
- Alle Code-Belege AS_OF 2026-08-09 (Branch 7e42ae34) — nicht stale [C1–C44]
- ADR-0013 vom 2026-08-09 — aktuell [A4]
- ADR-0011 vom 2026-07-27 — 13 Tage alt, noch gültig [A3]
- Referenzlauf R2 vom 2026-08-09 — heute [R2]
- Literatur L1 (2023) bis L13 (2025) — arXiv-Papers, nicht zeitkritisch im Code-Audit-Kontext [L1–L14]

## Counter-Review-Markierungen (für P6)
- These A: „Evidence-Pipeline ist echter Differenzierer" → Counter: nur konzeptionell, 0 validierte Claims (R2) schwächt
- These B: „Anti-Self-Confirmation über Prompt-Level" → Counter: Echo-Cap greift nur cross_stakeholder, Schwellen nicht kalibriert
- These C: „0 validierte Claims = kein Mehrwert" → Counter: Gate ist korrekt, Defekt liegt Upstream (Binding-Defekt + Teil B)
- These D: „OASIS-Mehrwert ungeprüft" → Counter: Task-E zeigt ~5500 LOC ohne Sim-Validity-Metrik — nicht widerlegt, aber auch nicht belegt
- These E: „ADR-Honesty ist starkes Signal" → Counter: dokumentierte Fehler ersetzen keinen bewiesenen Mehrwert