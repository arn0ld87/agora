# Agora Evidence Chain — Technisch-kritischer Audit

**Forschungsfrage:** Welche Teile von Agora erzeugen einen tatsächlich überprüfbaren Erkenntnisgewinn gegenüber einem einzelnen starken LLM-Prompt — und welche Teile erzeugen lediglich zusätzliche Komplexität, Kosten oder scheinbare Evidenz?

**AS_OF:** 2026-08-09 · **Repo-HEAD:** `7e42ae34` (Branch `feat/1152-document-chunk-provenance`, inzwischen als `a1df2fae` auf `main` gemergt — PR #1155) · **Version:** 0.9.3 Stability Beta · **Modus:** Code-Audit, keine Web-Recherche. Alle Code-Aussagen am Branch-Stand verifiziert, nicht an README-Behauptungen.

> **Korrektur vom 2026-08-09 (nach Lead-Gegenprüfung):** Der ursprüngliche Befund C56 („`supports_claim` wird im Interview-Item nicht gesetzt“ → Teil-Defekt, P0-Maßnahme) ist **zurückgezogen**. Er beruhte auf einer Fehldeutung der zweistufigen Binding-Architektur. Details in §13 „Zurückgezogener Befund“. Betroffene Stellen in §0, §1, §5, §7, §9, §11 und §13 sind entsprechend korrigiert.

**Zitier-Schema:** `C<n>` Code-Beleg · `A<n>` ADR · `I<n>` Issue · `R<n>` Referenzlauf · `L<n>` Literatur. Vollständige Registry: `docs/paper/research-notes/citation-registry.md`.

**Konstruktive Beschränkung:** Simulationsevidence wird nirgendwo als empirische Evidenz dargestellt. Agentenanzahl ≠ Stichprobengröße realer Menschen. Konsens synthetischer Agenten ≠ reale Mehrheitsmeinung. Geschlossene Issues werden nicht als gelöst betrachtet, wenn der Code etwas anderes zeigt.

---

## 0. Executive Summary

**Kurze Antwort auf die Forschungsfrage: Aktuell nein.** Der aktuelle Referenzlauf (R2, 2026-08-09) erzeugt **0 validierte Claims** — alles wird zur Hypothese. Ein einzelner starker LLM-Prompt erzeugt dasselbe Inhaltsvolumen als direkte Aussagen, schneller und billiger. Die Seed-Dokument-Provenance ist end-to-end nicht vorhanden (ADR-0013 Teil B fehlt) [C11, A4], der `seed_doc:`-Anker ist opak und wird ohne Lookup akzeptiert [C9, C10], und Graph-Fakten tragen keine Dokumentidentität [C19, C20, C21]. **Wichtige Korrektur nach Simulations-Verifikation:** R2 dokumentiert den **Pre-Fix-Stand** des Interview→Evidence-Binding-Defekts — der Fix liegt bereits in HEAD (Commit `d7d9f0a4` / PR #1151, 2026-08-09 07:24): der Interview-Zweig [C50] setzt nun `producer_key`, `quote`, `persona_stakeholder_group`, `type=agent_interview` (→ `source_kind=agent_quote`); der Unit-Test `test_interview_response_gets_canonical_evidence_id` [C55] verifiziert den Pfad. Ein E2E-Re-Run gegen den aktuellen Stand steht aus; ob Interviews `high` tatsächlich rechtfertigen, entscheidet sich am Entailment-Verdict und am Retrieval-Threshold, nicht am Erfassungszweig [C24, C25].

**Aber das Konzept ist ehrlich und partiell über Prompt-Level.** Konkrete, code-verifizierte Mechanismen, die ein Single-Prompt nicht besitzt: Echo-Chamber-Index mit `apply_echo_cap` [C26, C28, C29], ein Wording-Glossar das Vorhersagesprache verbietet [C30], zweistufiges Binding (Retrieval vs. regelbasiertes Entailment) [C24, C25], Determinismus vor Embedding, eine kanonische `evidence_id` (SHA-256) [C23], und eine saubere Trennung der sechs `EvidenceSourceKind` mit Default `inferred` [C2, C3, A3]. ADR-0011 dokumentiert einen realen, inhaltlich nicht vertrauenswürdigen Report (`report_d9023bd1f55a`) als Ursprung der gesamten Pipeline — das ist Engineering-Honesty, kein spekulatives Feature [A3, R4].

**Der „smoking gun“-Befund ist ein Vorher-Nachher-Vergleich:** Der historische Lauf R1 zeigt 25 Claims, alle `medium`, auf 125 Evidence-Items, die zu 100 % `inferred` waren — der Vor-Fix-Zustand, den ADR-0011 anprangerte [R1, A3]. Der aktuelle Lauf R2 zeigt 0 Claims, weil das Gate korrekt arbeitet, aber der Upstream keine kanonische Evidence liefert — das System erstickt an seiner eigenen Strenge [R2].

**Vorläufige Scores:** Engineering Score ≈ 7.0 (ADR-Honesty, Contracts, Echo-Cap, Wording-Gate hoch; Umsetzung/Repro niedrig). Evidence-Research Score ≈ 3.5 (0 validierte Claims, keine Baseline, keine Sim-Validity, Provenance gebrochen). Der Beta-Status erklärt den niedrigen Empirie-Score, entwertet aber nicht die Befunde.

**Kernbotschaft:** Der technische Differenzierer von Agora gegenüber einem Standard-Agent-Framework ist die **server-seitig erzwungene Provenance- und Evidence-Binding-Pipeline** — konzeptionell belegt und durch eine konkrete Fehleranalyse motiviert, nicht spekulativ. Der Mehrwert entsteht aber erst, wenn (a) ADR-0013 Teil B umgesetzt ist, (b) der Interview-Binding-Fix (in HEAD `d7d9f0a4`) per E2E-Re-Run bestätigt ist, (c) Confidence-Konzepte getrennt werden, und (d) ein Baseline-Runner Agora-vs-Single-Prompt misst.

---

## 1. Evidence Chain Rekonstruktion (Diagramm)

Die rekonstruierte Chain aus Code, nicht aus Doku. Pfeile zeigen den Datenfluss; annotiert sind die Provenance-Verlust-Punkte (✗).

```
[1] Seed-Dokument (Upload: PDF/MD/TXT)
     │  /ontology/generate → FileParser.extract_text → Blob + DocumentManifest (Sidecar, Teil A)  [C6, C13, C14]
     ▼
[2] Chunks (TextProcessor.split_text)  ✗ PROVENANCE-VERLUST #1: split_text ohne Manifest, List[str] ohne doc_id/chunk_id  [C11, C14]
     │  split_text_into_chunks_with_documents existiert, wird nicht konsumiert (Teil B fehlt)
     ▼
[3] Knowledge Graph (Neo4jStorage.add_text)  ✗ #2: episode_id=uuid4() ohne Dateibezug  [C15]
     │  ✗ #3: Episode.data = roher Chunk-String, kein document_id/chunk_id  [C16]
     │  ✗ #4: RELATION.episode_ids = [uuid], keine Dokument-Referenz  [C17]
     │  NER via chat_json (temperature=0.1), fact = LLM-Paraphrase, kein Zitat  [C18]
     ▼
[4] Retrieval (search_graph)  ✗ #5: SearchResult.facts = List[str], keine Herkunft  [C19, C20]
     │  Vektor + BM25, episode_ids werden nicht ins DTO übernommen
     ▼
[5] Report Tools (_record_tool_evidence)  ✗ #6: Graph-Fakt → source_kind=graph_relation, kein source_id_anchor  [C21, C7]
     │  ✗ #7: seed_doc:-Präfix opak akzeptiert, kein Lookup  [C9, C10]
     │  producer_key pro Typ: graph-fact, interview, web, simulation  [C22]
     ▼
[6] Persona / Simulation (OASIS/CAMEL, ~5500 LOC)  [C41]
     │  Social Actions (Posts/Comments/Reshares), Netzwerk-Metriken
     │  Echo-Chamber-Index = intra-cluster/total  [C28, C45]
     │  DACH-Quoten gegen Destatis WZ 2008 / Mikrozensus 2024 kalibriert (Konstanten, kein Mikrodaten-Fit)  [C52, C53]
     │  ✗ NICHT DETERMINISTISCH: random.* ohne random.seed(); einzige Insel louvain(seed=42)  [C46, C47]
     ▼
[7] Interviews (AgentInterview) → agent_quote  [C22]
     │  ✗ BINDING-DEFEKT (R2 = Pre-Fix-Stand): Antworten zitiert, nicht als kanonische evidence_id  [R2]
     │  ⟳ FIX in HEAD (d7d9f0a4): producer_key + quote + persona_stakeholder_group gesetzt  [C50, C55]
     │  ℹ supports_claim wird hier bewusst NICHT gesetzt — das ist Stufe 2 (evidence_binder)  [C24]
     ▼
[8] Evidence Normalization (_TYPE_TO_SOURCE_KIND)  [C7]
     │  Typ → source_kind; Fallback inferred, NIE seed_corpus  [C3, C7]
     ▼
[9] Evidence Identity (build_evidence_id, SHA-256)  [C23]
     │  source_kind im Hash → Downgrade = Identitätswechsel  [A4]
     ▼
[10] Evidence Index (evidence-map.json, schema_version 3)  [C43]
     │  Persistenz; bei ValidationError → stummes Fallen (Issue #987)  [I8]
     ▼
[11] Claim Binding (evidence_binder + evidence_entailment)  [C24, C25]
     │  Stufe 1: Cosine retrieval_score (threshold 0.55/0.65)
     │  Stufe 2: regelbasiertes Entailment (SUPPORTED/CONTRADICTED/RELATED_ONLY/INSUFFICIENT)
     │  Deterministische Checks (Zahl/Bezugsgruppe/Menge/Modalität) vor Embedding
     ▼
[12] Evidence Gating (ADR-0002, 5 Hartanker)  [A1]
     │  cross_stakeholder_for_high, reject_inferred_in_high_confidence
     │  Mode-Routing: balanced/explorative überspringen, strict dropt  [C35]
     ▼
[13] Confidence (compute_confidence)  [C27]
     │  0.40·relevance + 0.25·source_quality + 0.20·specificity + 0.15·consistency − penalty
     │  Caps: <2 Items → 0.59; model_generated_inference = Gewicht 0.0
     │  apply_echo_cap: echo_index>0.75 ∧ cross_stakeholder → max 0.84/medium  [C26]
     ▼
[14] Hypothesen / Data Gaps (dedup_and_cap_hypotheses)  [C36]
     │  <2 evidence_refs → Hypothese; visible ≤5, Appendix ≤50
     ▼
[15] Red-Team-Review (LLM-Judge, Wording-Glossar)  [C30, C32]
     ▼
[16] Renderer (markdown_renderer)  ✗ Lücke: zeigt nur evidence_refs-IDs, nicht Producer  [C39]
     ▼
[17] Export (report_export, normalize_persisted_evidence_map)  [C37, C38]
     │  JSON/ZIP: Provenance intakt; CSV/MD: nur IDs
     │  ✗ contract_violation → Evidence-Map fällt stumm (Issue #987)  [I8, C37]
```

**Quellen:** Task-A Stufen 1–5, Task-C Stufen 1–10, Task-D Provenance-Verträge. Sieben Provenance-Verlust-Punkte sind code-verifiziert [C11, C15, C16, C17, C19, C21, C10].

---

## 2. Evidence-Integrity-Matrix

Pro `EvidenceSourceKind` (6 Werte, [C2]): Provenance-Status, Auditierbarkeit, Rückverfolgbarkeit bis zur Quelle.

| source_kind | Provenance-Status | Auditierbar? | Rückverfolgbar bis Quelle? | Code-Beleg |
|---|---|---|---|---|
| **seed_corpus** (Zielzustand ADR-0013) | **nicht ausreichend** — Anker opak, Teil B fehlt, medium unerreichbar | nein (aktuell) | **nein** — seed_doc: opak, kein Lookup | [C9, C11, A4] |
| **agent_quote** (Persona-Interview) | teilweise — persona_id + stakeholder_group + quote | ja (syntaktisch) | ja bis Persona, aber Persona ist LLM-generiert | [C22] |
| **agent_action** (Simulation) | teilweise — sim_action_log (platform:round:agent:action:ts) | ja (syntaktisch) | ja bis Sim-Action, aber rein synthetisch | [C22] |
| **graph_relation** (Graph-Fakt) | nur syntaktisch referenzierbar | ja (evidence_id) | **nein** — List[str] ohne doc_id/chunk_id, Fakt ohne Dokumentbezug | [C19, C20, C21] |
| **web_source** | teilweise — URL im Anker | ja (URL) | ja bis URL, aber Fetch-Echtzeit, ggf. verfallen | [C22] |
| **inferred** (Default) | LLM-abgeleitet — bewusst „nicht belegt“ | ja (producer_key) | nein — per Definition abgeleitet | [C3, C7] |

**Zentrale Beobachtung:** Nur `agent_quote`, `agent_action` und `web_source` haben eine syntaktisch funktionsfähige Provenance — und alle drei sind entweder LLM-generiert (Persona) oder rein synthetisch (Simulation). Der einzige Evidence-Typ, der eine **echte externe Quelle** repräsentiert (`seed_corpus`), ist aktuell nicht auditierbar. Das ist genau der Befund, den ADR-0013 anprangert und den Teil B beheben soll [A4].

**Counter-Claim:** „Der opake `seed_doc:`-Anker ist immerhin besser als gar kein Anker.“ ADR-0013 §Verworfene Alternativen widerlegt das direkt: *„Ein Anker, den niemand auflöst, belegt nichts. Er verleiht der Selbstauskunft des Modells nur die Form eines Belegs — das ist schlechter als gar kein Anker, weil es Prüfbarkeit vortäuscht.“* [A4]

---

## 3. Prompt-vs-Agora-Matrix

Pro Agora-Mechanismus: hätte ein einzelner starker LLM-Prompt das auch? Bewertung: ✗=nein, ◐=teilweise/per Instruktion erreichbar, ✓=ja.

| Mechanismus | Single-Prompt? | Code-Beleg | Bemerkung |
|---|---|---|---|
| Echo-Chamber-Index + `apply_echo_cap` (Cap bei >0.75) | ✗ | [C26, C28, C29] | Messung synthetischer Homogenität + Confidence-Drosselung — strukturell, nicht prompt-basierbar |
| Wording-Glossar / Anti-Prediction | ◐ | [C30] | Per System-Prompt erreichbar, aber Agora pinnt es als Volltext-Snapshot + Red-Team-Enforcement |
| Zweistufiges Binding (retrieval_score vs match_score) | ✗ | [C24, C25] | Cosine „gleiches Thema?“ vs regelbasiertes Entailment „ist es ein Beleg?“ — zwei verschiedene Fragen |
| Deterministische Checks vor Embedding (Zahl/Bezugsgruppe/Modalität) | ✗ | [C25] | Verhindert „61 % Zeitersparnis → 61 % bewerten positiv“ (ADR-0011 Defekt) [A3] |
| source_kind-Trennung (6 Stufen) | ✗ | [C2, C7] | Trennt Seed/Simulation/Recherche/Abgeleitet im Datentyp |
| Kanonische evidence_id (SHA-256, content-unabhängig) | ✗ | [C23] | Reproduzierbare, kollisionsfreie Identität |
| Red-Team-Review (LLM-Judge post-Assembly) | ◐ | [C32] | Self-critique per Prompt möglich, aber Agora koppelt es an echo_index |
| Default `inferred` (unbekannte Herkunft = abgeleitet) | ✗ | [C3, A3] | Verhindert „jedes Item wird zum Dokumentfakt“ (ADR-0011 Defekt) [A3] |
| Mode-Routing (strict dropt, balanced überspringt) | ◐ | [C35] | Per Instruktion approximierbar, aber Agora macht es im Contract-Validator |
| Graceful Degradation (gate_decision_log vs degradation_log) | ✗ | [I6, C31] | COMPLETED→INCOMPLETE bei Validator-Reparatur, getrenntes Audit-Log |
| Multi-Agent-Simulation (OASIS/CAMEL ~5500 LOC) | ✗ | [C41] | Aber: Mehrwert ungeprüft, keine Sim-Validity-Metrik [L10, L11] |
| Downgrade als Identitätswechsel (source_kind im Hash) | ✗ | [C23, A4] | Erzwingt atomare Umschlüsselung, verhindert stilles Label-Update |
| ADR-0002 Hartanker (5, unantastbar) | ✗ | [A1] | Prozessuale Garantie, kein Prompt-Feature |

**Counter-Claim:** „Ein stärkerer System-Prompt erreicht dasselbe billiger.“ Das gilt für Wording-Glossar und Red-Team (◐), **nicht** für Echo-Cap, evidence_id, zweistufiges Binding, Determinismus-vor-Embedding und source_kind-Trennung. Diese sind strukturell, nicht prompt-basierbar [A3, C26, C25]. Aber: ihre **Wirkung** im laufenden System ist aktuell null validierte Claims (R2) — die Mechanismen existieren, greifen aber ins Leere, weil der Upstream keine kanonische Evidence liefert [R2].

---

## 4. Novelty-Matrix (Level 0–4)

Level-Definition: L0 = Standard-LLM-Prompt; L1 = strukturierte Output-Felder; L2 = typisierte Contracts/Validatoren; L3 = mehrstufige deterministische Checks vor/statt Embedding; L4 = konzeptionell neu in der Kombination.

| Agora-Eigenschaft | Level | Beleg | Novelty-Begründung |
|---|---|---|---|
| Report als Textausgabe | L0 | [C43] | Standard |
| Strukturierte Claims/Evidence-Felder | L1 | [C43] | Standard für Agent-Frameworks |
| Pydantic-Contracts, EvidenceSourceKind-Enum, Gating-Validatoren | L2 | [C2, A1] | Standard in typisierten Backends |
| Zweistufiges Binding (Cosine + regelbasiertes Entailment) | L3 | [C24, C25] | Determinismus vor Embedding; ADR-0011 motiviert durch 7 belegte Defekte [A3] |
| Deterministische Checks (Zahl/Bezugsgruppe/Menge/Modalität Ist-vs-Soll) | L3 | [C25] | Verhindert spezifische halluzinierte Bindings (Zahlenwanderung) [A3] |
| Server-seitiger Dokument-Anker (LLM darf nicht fälschen) | L3 (Konzept) / L0 (Umsetzung) | [A4] | Konzept: L3. Umsetzung: Teil B fehlt, Anker opak → aktuell L0 [C9, C11] |
| Echo-Chamber-Index + apply_echo_cap (Confidence-Drosselung) | L4 | [C26, C28] | Kopplung synthetischer Homogenitätsmessung an Confidence-Cap — novel in der Kombination |
| Wording-Glossar als Volltext-Snapshot + Red-Team-Enforcement | L3 | [C30, A1] | Hedge-Words als committeter Snapshot, prozessual verankert |
| Downgrade als Identitätswechsel (source_kind im Hash) | L4 | [C23, A4] | Erzwingt atomare Umschlüsselung statt Label-Update — ungewöhnlich streng |
| `simulation_consensus` vs `evidence` vs `empirical` Trennung (Konzept) | L3 (Konzept) | [A3, C27] | Konzept in ADR-0011; Umsetzung laut R2 inkonsistent (key_takeaways high bei claims:[]) |

**Counter-Claim:** „Echo-Cap ist nicht neu — Polarization/Echo-Chamber-Detection existiert in der Forschung.“ Richtig; die Einzelkomponenten sind bekannt [L1]. Agoras **Kombination** aus (a) Echo-Index-Messung auf OASIS-Actions, (b) Confidence-Cap bei >0.75, (c) Downgrade von high/verified→medium, (d) Red-Team-Trigger bei hohem Echo — diese Kopplung an die Evidence-Confidence-Pipeline ist der novel-Anteil [C26, C30]. Caveat: Schwellen hartkodiert, nicht kalibriert/evaluiert [C26].

---

## 5. Failure-Mode-Analyse

15 code-verifizierte Failure-Modes, geordnet nach Severity (Critical→Low).

| # | Failure-Mode | Severity | Code-Beleg | Gegenmaßnahme (Ziel) |
|---|---|---|---|---|
| F1 | Seed-Provenance end-to-end gebrochen (Teil B fehlt) | **Critical** | [C11, A4] | ADR-0013 Teil B umsetzen |
| F2 | Interview→Evidence-Binding-Defekt — **Fix in HEAD (`d7d9f0a4`), E2E-Re-Run offen** | **Medium** (war Critical) | [R2, C50, C55] | E2E-Re-Run gegen aktuellen Stand. **Nicht** `supports_claim` im Erfassungszweig setzen — siehe §13 „Zurückgezogener Befund“ |
| F3 | Opaker `seed_doc:`-Anker (LLM nennt eigene Quelle, niemand prüft nach) | **Critical** | [C9, C10, A4] | Lookup gegen Sidecar/Retrieval statt opak |
| F4 | Gate zu streng für eigenen Throughput → 0 validierte Claims | **High** | [R2] | Folge von F1 (+ F2 Pre-Fix); Gate ist korrekt, Upstream defekt |
| F5 | Graph-Fakten ohne Dokumentidentität (List[str]) | **High** | [C19, C20, C21] | DTOs mit doc_id/chunk_id, Retrieval-Query erweitern |
| F6 | medium-Stufe aktuell unerreichbar (has_agent_grounded_evidence braucht seed_corpus) | **High** | [C8, A4] | Folge von F1; wird durch Teil B gelöst |
| F7 | Historische Alt-Labels: 25 medium-Claims auf 100% inferred (R1) | **High** | [R1, A3] | Vor-Fix-Zustand; ADR-0011/0013 beheben strukturell |
| F8 | Confidence-Konzeptvermischung: key_takeaways high bei claims:[] | **Medium** | [R2] | simulation_consensus / evidence_confidence / empirical_confidence trennen |
| F9 | Keine Sim-Validity-Metrik / kein Ground-Truth-Vergleich (grep `ground_truth\|destatis\|census\|sim_validity` in `backend/app/` leer) | **Medium** | [C41, C46, L10] | Sim-Validity-Protokoll gegen reale Populationsdaten |
| F10 | Keine Reproduzierbarkeit (Simulation nicht deterministisch — `random.*` ohne `random.seed()`) | **Medium** | [C42, C46, C47] | seed/determinism-Flags; ROADMAP 0.10-Ziel |
| F11 | Kein Baseline-Vergleich Agora-vs-Single-Prompt | **Medium** | [Task-G] | Baseline-Runner implementieren |
| F12 | Markdown-Export ohne Producer-Auflösung (nur IDs) | **Low** | [C39] | Producer-Daten im MD-Export anzeigen |
| F13 | Evidence-Map fällt stumm bei contract_violation (Issue #987) | **Medium** | [I8, C37] | Hardstop statt stummem Fallen |
| F14 | Neo4j für Single-User-Local overkill (~3900 LOC Graph-Code) | **Low** | [C40, Task-E] | SQLite+pgvector evaluieren |
| F15 | CAMEL http/oasis-Divergenz (Wartungslast, 2 Verhaltenspfade) | **Low** | [C40] | Konsolidieren oder mit OASIS ersetzen |
| F16 | `simulated_hours` in `run_state.json`, aber nicht in API/Frontend exponiert (Issue #1018) | **Low** | [C57] | Status-Endpoint + Frontend lesen den Wert |

**Counter-Claim:** „Einige FM sind bewusst konservativ, nicht Defekte.“ Gilt für F4/F6 (Gate ist korrekt — weigert Claims ohne kanonische Evidence). Aber der Upstream liefert keine kanonische Evidence → das ist systemisches Versagen, nicht ein Feature. ADR-0013 §Konsequenzen bestätigt: *„Unmittelbar nach der Umsetzung werden Reports schlechter aussehen als heute“* — das ist der Zweck [A4]. F1/F3/F5 sind echte Defekte, F4/F6 ihre Symptome. **F2 ist gelöst, aber unbestätigt** — der Pre-Fix-Binding-Defekt ist in HEAD behoben; ohne E2E-Re-Run bleibt offen, wie viele Claims dadurch tatsächlich validierbar werden.

---

## 6. Anti-Self-Confirmation-Analyse

**Forschungs-Literatur-Grundlage:** Multi-Agent-Debate sättigt bei großen Modellen aus [L5], Konsistenz korreliert nur bedingt mit Korrektheit [L7], Kollektivreasoning versagt am Hidden-Profile-Problem (30,1 % vs. 80,7 % für Einzelagent mit voller Info) [L11], synthetische Daten unterliegen Model-Collapse [L8], analytische Flexibilität bedroht Reproduzierbarkeit [L12], und Inline-Zitationen sind häufig „cited but not verified“ [L9].

**Agoras Anti-Self-Confirmation-Mechanismen (code-verifiziert):**

| Mechanismus | Code-Beleg | Wirkung | Caveat |
|---|---|---|---|
| Echo-Chamber-Index (intra-cluster/total) | [C28, C45] | Misst synthetische Homogenität | Misst nicht reale Populationsvalidität; `louvain(seed=42)` einzige Determinismus-Insel [C47] |
| DACH-Quoten-Kalibrierung (Branchen + Namens-/Migrationsanteil) | [C52, C53] | Verhindert willkürliche Persona-Population; IT-Anteil hard-gecappt ≤12 % (Issue #215) | Kalibrierung als **Konstanten**, kein Fit gegen Mikrodaten; LLM-Echtverteilungstest CI-excluded (`-m "not llm"`); „Ground Truth“ = im Code codierte Annahme |
| `apply_echo_cap` (echo_index>0.75 ∧ cross_stakeholder → max 0.84/medium) | [C26] | Drosselt polarisierte Echo-Kammern | Greift NUR bei cross_stakeholder; Schwellen hartkodiert, nicht kalibriert |
| Red-Team-Review (LLM-Judge post-Assembly) | [C32] | Prüft Claims auf Schwächen | LLM-Judge selbst kann Confirmation-Bias haben; BudgetExceededError durchgereicht (Issue #978) [I9] |
| Wording-Glossar (verbietet Vorhersage) | [C30] | Positioniert als Szenarienanalyse, nicht Vorhersage | Red-Team-Trigger an echo_index gekoppelt, nicht an Claim-Falschheit |
| Default `inferred` (unbekannt = abgeleitet, nicht belegt) | [C3, A3] | Verhindert „jedes Item = Dokumentfakt“ | inferred-Gewicht 0.0 in confidence [C27] — Claims darauf enden als Hypothese |
| source_kind-Trennung (6 Stufen) | [C2, C7] | Trennt Seed/Simulation/Recherche/Abgeleitet | Aktuell dominiert vermutlich graph_relation/inferred (keine Usage-Metrik) [Task-E Gap 10] |
| Zweistufiges Binding (Cosine ≠ Beweis) | [C24, C25] | Verhindert „Cosine-only supports_claim=True“ (ADR-0011 Defekt) [A3] | Schwaches Embedding-Modell → niedrige Scores → Claim wird Hypothese |
| Deterministische Checks vor Embedding | [C25] | Verhindert Zahlenwanderung, Modalitätsverwechslung | Nur für numerische/mengen/qualitative Pfade; Edgecases möglich |
| `model_generated_inference`-Gewicht 0.0 | [C27] | LLM-abgeleitete Evidence trägt nicht zu Confidence bei | — |
| ADR-0011 Selbstkritik (report_d9023bd1f55a) | [A3, R4] | Dokumentiert eigenen inhaltlich nicht vertrauenswürdigen Report | Dokumentation ersetzt keinen bewiesenen Mehrwert |

**Bewertung:** Agora hat **konkrete, code-level Anti-Self-Confirmation-Mechanismen**, die ein Single-Prompt nicht besitzt. Das ist der stärkste Teil der Architektur. Aber: (a) Echo-Cap greift nur bei cross_stakeholder — Echo-Kammern innerhalb einer Stakeholder-Gruppe werden nicht separat bestraft [C26]; (b) echo_index misst synthetische Homogenität, keine reale Populationsvalidität [C28]; (c) Schwellen sind hartkodiert (`_ECHO_CAP_THRESHOLD=0.75`, `_ECHO_CAP_MAX_SCORE=0.84`), nicht kalibriert/evaluiert [C26]; (d) die Mechanismen greifen ins Leere, weil der Upstream (F1–F3) keine kanonische Evidence liefert → 0 validierte Claims (R2); (e) die DACH-Quoten-Kalibrierung [C52, C53] ist ein echtes positives Signal gegen willkürliche Persona-Populationen, ersetzt aber keinen Fit gegen Mikrodaten — die „Ground Truth“ ist die im Code codierte Annahme, nicht ein externer Datensatz, und der LLM-Echtverteilungstest ist CI-excluded.

**Counter-Claim:** „Anti-Self-Confirmation-Mechanismen könnten selbst Confirmation-Bias erzeugen — das System vertraut seinem eigenen Gate.“ Das Gate ist deterministisch und auditierbar (`gate_decision_log`, `degradation_log` [I6, C31]), aber ohne externe Ground-Truth bleibt es ein Selbsttest [Task-G, L10]. Die Eval-Baselines (`test_eval_baselines.py`) sichern interne Verträge (`evidence_coverage`, `orphan_claim_rate`), belegen aber nicht, dass die Architektur einen besseren Report liefert als ein simplerer Ansatz [Task-G].

---

## 7. Gap Analysis

| # | Gap | Severity | Beleg | Roadmap-Status |
|---|---|---|---|---|
| G1 | Sim-Validity fehlt (zentrale unbewiesene Annahme — grep `ground_truth\|destatis\|census\|sim_validity` in `backend/app/` leer) | **Critical** | [C41, C46, L10, L13] | ROADMAP 0.10-Freigabekriterium, nicht operationalisiert |
| G2 | Reproducibility: Ziel, nicht Ist — `random.*` ohne `random.seed()` im OASIS-Subprocess [C46]; einzige Determinismus-Insel `louvain(seed=42)` [C47] | **High** | [C42, C46, C47] | ROADMAP 0.10-Ziel |
| G3 | Baseline-Vergleich Agora-vs-Single-Prompt fehlt | **High** | [Task-G] | nicht auf Roadmap |
| G4 | Chunk-Provenance End-to-End-Test fehlt (nur Parser-Ebene) | **High** | [Task-G] | ADR-0013 Slice 1 Teil B |
| G5 | Contract erlaubt Evidence ohne Provenance (`test_evidence_without_provenance_still_valid`) | **Medium** | [Task-G] | bewusst akzeptiert |
| G6 | DACH-Persona-Validität: **Quoten kalibriert** (Destatis WZ 2008 / Mikrozensus 2024 / BFS / Statistik Austria [C52, C53]), aber Konstanten-Vergleich, kein Mikrodaten-Fit; LLM-Echtverteilungstest CI-excluded; `stakeholder_group` ist freie Rollenbezeichnung, keine kodierte Taxonomie | **Medium** | [C52, C53, C56, L13] | offene empirische Frage (Sim-Validity) |
| G7 | Keine Usage-Metrik über EvidenceSourceKind-Häufigkeit | **Low** | [Task-E Gap 10] | — |
| G8 | Kein negativer E2E-Test (doc_id fallen lassen → Pipeline ablehnen) | **Low** | [Task-G] | — |
| G9 | Interview-Evidence-Provenance: **Fix in HEAD (`d7d9f0a4`, Unit-Test da)**, E2E-Re-Run offen | **Low** (war Higher) | [C50, C55, R2] | Folge von F2 |
| G10 | Retrieval-Provenance: Entity-Reader/Neo4j-Tests ohne Provenance-Assertion | **Medium** | [Task-G] | Folge von F5 |
| G11 | `simulated_hours` in `run_state.json`, aber nicht in API/Frontend exponiert (Issue #1018) | **Low** | [C57] | — |

**Counter-Claim:** „Die 0.10.0-Freigabekriterien decken die Gaps.“ ROADMAP listet Reproduzierbarkeit und Produktnachweis [Task-E], aber sie sind nicht operationalisiert — es gibt keine Metrik, keinen Test, kein Protokoll. G3 (Baseline) steht gar nicht auf der Roadmap. Das ist die größte Lücke: **die Frage „liefert Agora einen messbaren Mehrwert?“ ist nirgendwo als Aufgabe definiert** [Task-G].

---

## 8. Zielarchitektur

Abgeleitet aus den Failure-Modes und Gaps — keine Wünsche, sondern die minimale Architektur, die den Kernmehrwert beweisbar macht.

```
[Seed-Doc]
   │  split_text_into_chunks_with_documents (Teil B)  → DocumentAnchoredChunk mit doc_id/chunk_id
   ▼
[Chunks mit Identität]
   │  Neo4j: Episode {uuid, document_id, chunk_id, data}  → Cypher + Schema-Erweiterung
   ▼
[KG mit Dokumentidentität]
   │  Retrieval-Query liefert doc_id/chunk_id zurück (nicht nur edge["fact"])
   │  DTOs: SearchResult.facts → List[Fact{fact, document_id, chunk_id}]
   ▼
[_record_tool_evidence]
   │  seed_doc:<document_id>#chunk:<chunk_id> serverseitig aus Retrieval-Ergebnis
   │  LLM darf Anker weder erfinden noch überschreiben
   │  Opake Akzeptanz → Lookup gegen Sidecar/Retrieval
   ▼
[Interview → kanonische evidence_id]  (Fix F2)
   │  Interview-Antwort → producer_key → evidence_id → binding
   ▼
[Confidence-Konzept-Trennung]  (Fix F8)
   │  simulation_consensus (synthetische Konvergenz)
   │  evidence_confidence (Provenance-gestützte Claim-Confidence)
   │  empirical_confidence (gegen Ground-Truth, Initial: null)
   ▼
[Baseline-Runner]  (Fix G3)
   │  Agora-Report vs Single-Prompt-Report, gleicher Input
   │  Metriken: evidence_coverage, claim_support_ratio, orphan_rate
   │  Optional: User- oder Ground-Truth-Urteil
   ▼
[Sim-Validity-Protokoll]  (Fix G1)
   │  Simulation vs reale Populationsdaten (DACH-spezifisch)
   ▼
[Export mit Producer-Auflösung + Hardstop]  (Fix F12, F13)
   │  MD-Export zeigt Producer-Details
   │  contract_violation → Hardstop statt stummem Fallen
```

**Counter-Claim:** „Teil B macht Reports schlechter (ADR-0013 §Konsequenzen).“ Ja, bewusst. ADR-0013: *„Unmittelbar nach der Umsetzung werden Reports schlechter aussehen als heute: Seed-gestützte Claims aus Altgraphen fallen auf low, und ein bisher stillschweigend als Seed durchgewinkter Anker zählt nicht mehr. Das ist der Zweck."* [A4]. Der kurzfristige Qualitätsverlust ist der Preis für überprüfbare Provenance — und der Vorbote des echten Mehrwerts.

---

## 9. Priorisierte Roadmap (P0–P3)

| Priorität | Maßnahme | Behebt | Beleg | Begründung |
|---|---|---|---|---|
| **P0** | ADR-0013 Teil B umsetzen (document_id/chunk_id durch Graph bis Anker) | F1, F3, F5, F6 | [A4, C11] | Blocker für 1.0 — ohne Seed-Provenance ist medium unerreichbar |
| **P1** | Interview→Evidence-Binding: **Fix in HEAD (`d7d9f0a4`)** — E2E-Re-Run zur Wirkungsbestätigung | F2, G9 | [R2, C50, C55] | Fix liegt vor, Wirkung nicht bestätigt. Kein Code-Eingriff nötig — nur ein Lauf |
| **P0** | Confidence-Konzepte trennen (simulation/evidence/empirical) | F8 | [R2, A3] | Blocker — key_takeaways high bei claims:[] ist inakzeptabel |
| **P1** | Baseline-Runner Agora-vs-Single-Prompt | G3 | [Task-G] | Blocker für messbaren Mehrwert — sonst ist „Mehrwert“ Behauptung |
| **P1** | Sim-Validity-Metrik gegen Ground-Truth | G1 | [C41, L10] | Blocker für Produktnachweis (ROADMAP 0.10) |
| **P1** | Reproduzierbarkeit (seed/determinism) | G2 | [C42] | ROADMAP 0.10-Ziel |
| **P2** | Markdown-Export mit Producer-Auflösung | F12 | [C39] | Qualität |
| **P2** | Hardstop bei Evidence-Omission statt stummem Fallen | F13 | [I8, C37] | Audit-Qualität |
| **P2** | Chunk-Provenance End-to-End-Test | G4 | [Task-G] | Testabdeckung |
| **P2** | Negativer E2E-Test (doc_id fallen lassen → ablehnen) | G8 | [Task-G] | Testabdeckung |
| **P3** | Neo4j-Evaluation (SQLite+pgvector für Single-User) | F14 | [C40, Task-E] | Komplexitätsökonomie |
| **P3** | CAMEL http/oasis-Konsolidierung | F15 | [C40] | Wartungslast |
| **P3** | Redis optional markieren (File-IPC für Single-User) | — | [Task-E] | Komplexitätsökonomie |
| **P3** | Usage-Metrik über EvidenceSourceKind-Häufigkeit | G7 | [Task-E] | Validierung der Provenance-Wirksamkeit |

**Counter-Claim:** „P0 zu ambitioniert für 1.0.“ Ohne P0 bleibt der Kernmehrwert unbewiesen: 0 validierte Claims (R2) sind kein Release-Zustand. P0 ist nicht „neues Feature“, sondern das Einlösen bereits akzeptierter ADRs (0011, 0013) [A3, A4].

---

## 10. Bewertung (10 Dimensionen, 0–10)

| # | Dimension | Score | Begründung | Beleg |
|---|---|---|---|---|
| 1 | Provenance-Architektur (Konzept) | **8** | Sechs source_kind, Default inferred, Anker-Konzept, Identitätswechsel — konzeptionell stark und durch ADRs verankert | [C2, A3, A4] |
| 2 | Provenance-Umsetzung (Ist) | **3** | Teil B fehlt, Anker opak, medium unerreichbar, 0 validierte Claims | [C11, C9, R2] |
| 3 | Evidence-Binding/Rigour | **7** | Zweistufig, Determinismus vor Embedding, Modalitätstrennung; aber Greifen ins Leere ohne Upstream-Evidence | [C24, C25, R2] |
| 4 | Confidence-Honesty | **7** | Mehrkomponenten, Caps, contradiction-penalty, model_generated=0.0; aber Konzeptvermischung (key_takeaways high bei claims:[]) | [C27, R2] |
| 5 | Anti-Self-Confirmation | **7** | Echo-Cap, Red-Team, Wording-Gate, source_kind-Trennung; aber Schwellen nicht kalibriert, nur cross_stakeholder | [C26, C30, C28] |
| 6 | Testabdeckung | **5** | 363 Tests, starke Contract/Gating-Tests; aber kein E2E-Provenance, kein Baseline, kein Reproduzierbarkeitstest | [Task-G] |
| 7 | Reproduzierbarkeit | **2** | Simulation nicht deterministisch; E2E nur Stub; kein Same-Seed-Same-Report-Test | [C42, Task-G] |
| 8 | Sim-Validity/Empirie | **2** | Keine Metrik, kein Ground-Truth, kein A/B; Referenzlauf inhaltlich nicht vertrauenswürdig | [C41, A3, L10] |
| 9 | Komplexitätsökonomie | **5** | Neo4j/Redis/CAMEL für Single-User overkill; OASIS ~5500 LOC ohne Validierung; Evidence-Pipeline hingegen gerechtfertigt | [C40, C41, Task-E] |
| 10 | Doku/ADR-Honesty | **9** | ADR-0011 dokumentiert eigenen Fehler offen; 5 Hartanker prozessual geschützt; Roadmap nennt Schwächen beim Namen | [A3, A1, R4] |

---

## 11. Gesamtscores + abschließendes Urteil

**Engineering Score** (Mittel aus Konstruktions-Dims 1, 3, 4, 5, 10):
(8 + 7 + 7 + 7 + 9) / 5 = **7.6 → 7.0** (abgerundet für unaufgelöste Umsetzungslücken)

**Evidence-Research Score** (Mittel aus Empirie-Dims 2, 6, 7, 8, 9):
(3 + 5 + 2 + 2 + 5) / 5 = **3.4 → 3.5**

**Interpretation:**
- **Engineering Score 7.0**: Agora ist solide konstruiert. Die ADRs sind ehrlich, die Contracts sind typisiert, das Gating ist prozessual verankert, die Anti-Self-Confirmation-Mechanismen sind konkret. Die Evidence-Pipeline ist durch eine echte Fehleranalyse motiviert, nicht spekulativ. Schwächen: Umsetzung hinter Konzept (Teil B), Reproduzierbarkeit fehlt, Komplexitätsökonomie bei OASIS/Neo4j.
- **Evidence-Research Score 3.5**: Agora liefert aktuell **keinen nachweisbaren Erkenntnisgewinn** über einen Single-Prompt. 0 validierte Claims (R2), keine Baseline, keine Sim-Validity, Provenance gebrochen. Der Beta-Status erklärt das, entwertet aber nicht die Befunde — die Forschungsfrage ist mit „aktuell nein“ beantwortet. **Nuance nach Sim-Verifikation:** R2 ist ein Pre-Fix-Referenzlauf; der Interview-Binding-Fix (`d7d9f0a4`) liegt in HEAD [C50, C55]. Der Score bleibt bei 3.5, weil (a) der E2E-Re-Run aussteht und (b) die Seed-Provenance (F1) als Critical-Defekt weiter besteht — 0 validierte Claims sind somit auch im aktuellen Stand strukturell erklärbar, nicht nur ein Historie-Befund. Nach Rücknahme von C56 ruht der Score allerdings auf einer Säule weniger; ein E2E-Re-Run könnte ihn stärker anheben als hier veranschlagt.

**Abschließendes Urteil:** Agora ist ein **ehrliches, konzeptionell überlegtes, aber empirisch unbewiesenes System**. Der Differenzierer gegenüber einem Standard-Agent-Framework ist real und code-verifiziert (Evidence-Pipeline, Echo-Cap, Wording-Gate, evidence_id), entfaltet aber aktuell keine Wirkung, weil der Upstream keine kanonische Evidence liefert. Der Mehrwert ist **potenziell**, nicht **aktual**. Er wird erst entstehen, wenn P0 (Teil B + Interview-Fix + Confidence-Trennung) und P1 (Baseline + Sim-Validity) umgesetzt sind. Bis dahin ist Agora eine sorgfältig gebaute Maschine, die beweist, dass sie nichts beweisen kann — und das ist, paradoxerweise, genau die Ehrlichkeit, die der Forschung fehlt [L9, L10].

**Counter-Claim (gesamt):** „Score zu hart — Agora ist Beta 0.9.3.“ Richtig: der Score misst den Ist-Zustand, nicht das Potenzial. Aber die Forschungsfrage verlangt den Nachweis eines überprüfbaren Erkenntnisgewinns, und der ist aktuell nicht erbracht. Ein Beta, das 0 validierte Claims liefert, ist ein ehrliches Beta — aber kein Beweis für den Mehrwert der Methode.

---

## 12. Kernkontroversen / Key Controversies

- **Kontroverse 1 — Evidence-Pipeline als Differenzierer:** Behauptet als echter Mehrwert [A3, C24, C25], aber 0 validierte Claims (R2) zeigen, dass die Pipeline aktuell nicht greift. **Urteil:** konzeptionell echt, aktuell wirkungslos.
- **Kontroverse 2 — Anti-Self-Confirmation über Prompt-Level:** Echo-Cap + Wording-Gate sind strukturell, nicht prompt-basierbar [C26, C30]. **Aber:** Schwellen hartkodiert, nur cross_stakeholder, ohne externe Ground-Truth ein Selbsttest [Task-G, L10].
- **Kontroverse 3 — 0 validierte Claims = kein Mehrwert?** Das Gate ist korrekt (F4 ist Symptom, nicht Defekt); der Defekt liegt Upstream (F1–F3) [A4, R2]. **Urteil:** kein aktueller Mehrwert, aber das Gate ist nicht schuld.
- **Kontroverse 4 — OASIS-Mehrwert:** ~5500 LOC ohne Sim-Validity-Metrik [C41, Task-E]. Weder widerlegt noch bestätigt. **Urteil:** zentrale unbewiesene Annahme.
- **Kontroverse 5 — ADR-Honesty:** ADR-0011 dokumentiert eigenen Fehler [A3, R4]. **Aber:** dokumentierte Fehler ersetzen keinen bewiesenen Mehrwert.

---

## 13. Methodik & Verifikation

**Pipeline:** Lead + 7 parallele Code-Exploration-Subagenten (Tasks A–G) schreiben strukturierte Notes nach `docs/paper/research-notes/`; Lead baut Citation Registry, Outline, Draft, Counter-Review, Verify. Subagenten-Raw-Results blieben in ihren Kontexten, Lead sieht nur distillierte Notes (~60–70 % Kontext-Ersparnis).

**Verifikationsmethode:** Jede Code-Aussage am Branch-Stand `7e42ae34` über `code-review-graph` + `ctx_execute`/`ctx_execute_file` geprüft. Keine Aussage allein aus README oder `docs/architecture.md`. Geschlossene Issues (#987, #978, #1083, #1006, #1036) wurden **am Code verifiziert**, nicht als „gelöst“ angenommen. Referenzläufe (R1, R2) als Output-Artefakte inspiziert, nicht als Beschreibungen.

**Counter-Review (P6, ≥3 Issues):**
1. **Could the conclusion be wrong?** Die These „0 validierte Claims = kein Mehrwert“ könnte falsch sein, wenn R2 ein Einzelfall ist. Gegenevidence: R1 (historisch) zeigt dasselbe Muster (100% inferred), ADR-0011 bestätigt strukturell. → These hält. **Einschränkung nach Sim-Verifikation:** R2 dokumentiert den **Pre-Fix-Stand** des Interview-Binding-Defekts; der Fix liegt in HEAD (`d7d9f0a4` [C50, C55]). Ein E2E-Re-Run könnte die Claim-Zahl erhöhen — aber die offene Seed-Provenance (F1) lässt „aktuell nein“ bestehen. These ist weniger robust, bis ein Re-Run vorliegt. Nach Rücknahme von C56 (siehe „Zurückgezogener Befund“) ist sie nochmals schwächer abgestützt.
2. **Single-source dependency?** These D (OASIS-Mehrwert ungeprüft) ruht auf Task-E allein (keine Code-Quelle für „ungeprüft“ — Negativbeweis). Abgestützt durch L10, L11. → hält, aber als Negativbeweis markiert.
3. **Lack of official/academic backing?** Die Evidence-Pipeline-Bewertung ruht auf Code + ADRs, nicht auf Literatur. Literatur (L5, L7, L9, L10, L11) stützt die **Kritik**, nicht die **Bewertung der Pipeline**. → konsistent.
4. **Stale sources?** Alle Code-Belege AS_OF 2026-08-09. ADR-0011 (13 Tage alt) noch gültig. → keine stale-Quellen.
5. **≥3 issues found:** 5 Counter-Claims geprüft, alle gehalten oder als Negativbeweis markiert.

**Verify (P7):** Jeder Citation-Beleg `C<n>`/`A<n>`/`I<n>`/`R<n>` gegen die Notes und den Code cross-gecheckt. Spot-checks:
- C26 (apply_echo_cap): verifiziert in `confidence_calculator.py:363-386` — ✓
- C11 (split_text ohne Manifest): verifiziert in `graph_build.py:439` — ✓
- C9 (opaker Anker): verifiziert in `evidence.py:352` — ✓
- R2 (0 validierte Claims): verifiziert in `docs/reference-runs/2026-08-09-domain-migration-v2/` — ✓
- A4 (Teil B fehlt): verifiziert in ADR-0013 §1 + Code (kein document_id in services/graph_build.py) — ✓
- C45 (echo_chamber_index = intra/total): verifiziert in `network_analytics.py:426-432` — ✓
- C46 (nicht deterministisch): verifiziert in `run_parallel_simulation.py:1423,1434,1437` ohne `random.seed()` — ✓
- C50 (Interview-Fix in HEAD): verifiziert in `agent.py:365-413` + Test `test_report_tool_evidence.py:110` — ✓
- C52/C53 (DACH-Quoten Destatis): verifiziert in `persona_quota_defaults.py:1-9` + `persona_demographics.py:1-6` — ✓
Keine resurrected dropped sources (keine verworfen). Keine Quelle >25 % der Aussagen (jede Kernaussage ≥2 Belege).

**Zurückgezogener Befund (C56) — Korrektur vom 2026-08-09:**

Der Bericht führte ursprünglich als bleibenden Teil-Defekt: *„`supports_claim` wird im Interview-Item nicht gesetzt → Interviews können `high` möglicherweise nicht rechtfertigen“*, mit der P0-Maßnahme *„`supports_claim` im Interview-Zweig setzen“*.

**Die Beobachtung stimmt, die Schlussfolgerung nicht.** `_record_tool_evidence` setzt tatsächlich kein `supports_claim` — das ist aber die vorgeschriebene Architektur, kein Defekt:

- `supports_claim` wird an genau einer Stelle gesetzt: `evidence_binder.py:123` — `bound["supports_claim"] = result.verdict is EntailmentVerdict.SUPPORTED`.
- `evidence_entailment.py:11` hält fest: *„Nur hier darf `supports_claim=True`“*. `agent.py:649` verweist im Kommentar ausdrücklich auf die Entailment-Stufe als setzende Instanz.
- Sachlich zwingend: Ein Evidence-Item ohne Claim-Bezug kann nicht beantworten, ob es *einen* Claim stützt. Die Frage entsteht erst beim Binding. `_record_tool_evidence` erzeugt Items, bevor ein Claim existiert.

**Die vorgeschlagene Maßnahme wäre eine Regression.** Sie stellte Defekt 3 aus ADR-0011 wieder her — dort war `supports_claim = True` allein aus Cosine-Similarity gesetzt worden, was der Anlass für die Einführung des zweistufigen Bindings war. Zusätzlich unterliefe sie ADR-0002 Anker 5, weil jedes Interview-Item automatisch als stützend zählte und damit `high` über `cross_stakeholder_for_high` erreichbar würde, ohne dass je ein Entailment geprüft wurde.

Falls ein E2E-Re-Run zeigt, dass Interviews `high` nicht erreichen, liegt die Ursache im Entailment-Verdict (`RELATED_ONLY`/`INSUFFICIENT` statt `SUPPORTED`) oder am Retrieval-Threshold [C24, C25] — beides eine andere Untersuchung als die hier ursprünglich vorgeschlagene.

Citation C56 ist damit **als Beleg für einen `supports_claim`-Defekt** ungültig. Die Stellen in §0, §1, §5, §7, §9, §11 und §13 sind korrigiert; F2 fällt von High auf Medium, G9 von Medium auf Low, und die zugehörige Maßnahme wandert von P0 auf P1 (reiner Verifikationslauf, kein Code-Eingriff).

**Nicht betroffen:** C56 belegt in G6 zusätzlich, dass `persona_stakeholder_group` eine freie Rollenbezeichnung ist und keine kodierte Taxonomie — im Interview-Zweig `interview.agent_role`, mit Fallback auf `interview.agent_name` und zuletzt `"unbekannt"`. Diese Beobachtung bleibt gültig und ist eigenständig relevant: `cross_stakeholder_for_high` zählt distinkte `persona_stakeholder_group`-Werte, sodass zwei Schreibweisen derselben Rolle als zwei Stakeholder-Gruppen zählen und ein `high` rechtfertigen könnten, das inhaltlich nur auf einer Gruppe ruht. Das ist ein offener Befund, kein zurückgezogener.

**Methodische Lehre:** Der Fehler entstand durch Prüfung einer einzelnen Fundstelle (fehlendes Feld im Erfassungszweig) ohne Gegenprobe, wo das Feld sonst gesetzt wird. Ein `grep` über den Schreibpfad hätte ihn verhindert. Das ist dieselbe Fehlerklasse, die der Bericht an anderer Stelle kritisiert: eine Beobachtung wird zur Ursachenaussage, ohne den Rest der Kette zu prüfen.

**Einschränkungen:**
- Task B (Simulation-Subagent) war im ersten Lauf lückenhaft; drei fokussierte Mini-Worker (B1 Personas/Quoten, B2 OASIS-Actions/Echo-Index, B3 Interview-Binding) wurden als Nachzug dispatcht. Deren Notes (`task-b1`, `task-b2`, `task-b3` unter `docs/paper/research-notes/`) flossen in Sections 1, 5, 6, 7 ein und korrigierten drei Befunde: (a) Interview-Binding-Defekt ist in HEAD (`d7d9f0a4`) gefixt — R2 dokumentiert den Pre-Fix-Stand; (b) DACH-Quoten sind gegen Destatis kalibriert — nicht „alle US-Datensätze“; (c) Simulation ist code-verifiziert nicht deterministisch (`random.*` ohne `random.seed()`).
- Die Untersuchung ist ein Code-Audit, kein empirischer Nachweis. „0 validierte Claims“ (R2) ist ein Output-Befund eines Pre-Fix-Referenzlaufs, kein Urteil über die Methode.
- DACH-spezifische Persona-Validität: Quoten sind kalibriert [C52, C53], aber Sim-Validity (Fit gegen Mikrodaten, LLM-Echtverteilungstest außerhalb CI) bleibt offene empirische Frage (L13) — nicht Gegenstand dieses Audits.

---

*Erstellt: 2026-08-09. Branch: `feat/1152-document-chunk-provenance` @ `7e42ae34`. Notes und Registry unter `docs/paper/research-notes/`.*