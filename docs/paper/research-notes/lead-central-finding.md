# LEAD CENTRAL FINDING — output-verifiziert (der Kern der Untersuchung)

## C1 — Historischer Referenzlauf report_e2e_trust01 (= ADR-0011 sim_7058c126da03)
Datei: `backend/uploads/reports/report_e2e_trust01/evidence_map.json` (schema_version 2)
- 25 Claims, **alle** `confidence_label: medium` (score teils 0.89)
- 125 Evidence-Items insgesamt, **100 % `source_kind: inferred`**
- 0 Items mit `source_id_anchor`; (teilweise `quote`-Feld gesetzt, aber kein Anker)
- global_evidence: 12 Items, alle `inferred`; erstes Item = graph_metric echo_chamber_index=0.4317 (identisch mit ADR-0011-Referenz)
- report-v3.json: 25 Claims, claim0 `evidence_ids: []`, `confidence: None` (ReportV3-Feld leer)

**Interpretation:** Das ist der **Vor-Fix-Zustand**, den ADR-0011 (2026-07-27) anprangerte. Dass alle Items heute als `inferred` geladen werden, stammt aus ADR-0011 §2 (Default `seed_corpus` → `inferred`) + `normalize_persisted_evidence_map`-Downgrade beim Lesen. Die `medium`-Labels sind **historische Alt-Labels**, die beim Downgrade der source_kind nicht neu berechnet wurden — denn ein Downgrade ist ein Identitätswechsel (ADR-0013 §4), und die Label-Neuberechnung ist genau der Defekt #1012 (ungehedgter Wortlaut nach Downgrade). Das bestätkt ADR-0013 §Konsequenzen: „Ein herabgestufter Claim behält vorerst seinen ungehedgten Wortlaut.“

**Bedeutung:** Zeigt die Gefahr, die ADR-0011 beseitigen wollte: Confidence-Labels (`medium`) auf reiner `inferred`-Evidence = „Schein-Evidenz“. Heute durch ADR-0011/0013 strukturell erschwert, aber der Alt-Stand belegt, dass das System früher genau hier versagte.

## C2 — Aktueller Referenzlauf Domain-Migration v2 (2026-08-09, commit a611b50a)
Datei: `docs/reference-runs/2026-08-09-domain-migration-v2/README.md`
- Report `report_06f654800817`, Sim `sim_464a7a8e6310`, Evidence-Schema 3, Modus `balanced`, Intent `risk`
- 30 Agenten, 412 Graph-Interaktionen, 540 Social Actions, 3 Cluster, Echo-Chamber-Index 0.5461
- **`claims: []` in allen 6 Sections → 0 validierte ReportV3-Claims**
- 30 primäre Hypothesen, 12 kanonische Evidence-Items (8 × agent_action, 4 × graph_metric)
- **Interview→Evidence-Binding-Defekt (offen dokumentiert):** erfolgreiche Deep Interviews werden in finalen Reporttexten zitiert, aber im `evidence_index` nicht als kanonische `agent_interview`-/`interview_response`-Items persistiert. Datenpfad: interview_agents → Antwort → ReACT verwendet Antwort → Candidate Claim → keine kanonische evidence_id → Claim darf nicht persistiert werden → Hypothese.
- **Konsistenzfehler 1:** `structured_metadata.key_takeaways` trägt an mehreren Stellen `confidence: high`, während dieselbe Section `claims: []` enthält. Konzeptvermischung: interne/simulierte Konvergenz vs. Evidence-Konfidenz eines validierten Claims.
- **Konsistenzfehler 2:** Structured Metadata meldet unvollständige Sections (Abbruch), während der finale Report vollständig ist. `generate_section_metadata()` erhält vermutlich truncierten Textpfad.
- **Explizite Grenzaussage (README):** „Dieser Lauf dokumentiert Agoras Verhalten in einer simulierten Multi-Agenten-Umgebung. Er ist **kein** Nachweis dafür, dass die simulierten Personas reale Menschen repräsentieren oder reales menschliches Verhalten vorhersagen."
- **`8/8`-Klärung:** bezieht sich auf die **acht pro Section ausgewählten** Interview-Agenten, nicht auf die 30-Agenten-Population.

## C3 — Synthese: Kernfrage-Antwort (aktuell)
> Erzeugt Agora Erkenntnisse, die ein einzelnes starkes LLM mit gutem Prompt nicht erzeugen würde, und sind diese über eine vollständige Evidence Chain nachvollziehbar und reproduzierbar?

**Aktuell: Nein.**
1. **Keine validierten Claims:** Der aktuelle Referenzlauf erzeugt 0 validierte Claims. Alles ist Hypothese. Ein Single-Prompt erzeugt dasselbe Inhaltsvolumen als direkte Aussagen — schneller, billiger, ohne Binding-Defekt.
2. **Provenance gebrochen:** Seed-Dokument-Provenance ist end-to-end nicht vorhanden (Teil B fehlt, seed_doc: opak). Interview-Provenance bricht am Binding-Defekt. Graph-Fakten tragen keine Dokumentidentität.
3. **Evidence-Gate zu streng für eigenen Throughput:** Das Gate ist korrekt (weigertClaims ohne kanonische Evidence), aber der Upstream liefert keine kanonische Evidence → 0 Claims. Das System „erstickt“ an seiner eigenen Strenge.
4. **Aber: Konzept ist ehrlich und teilweise über Prompt-Level:**
   - Echo-Chamber-Index + `apply_echo_cap` (Cap bei >0.75) — ein Single-Prompt hat das nicht.
   - Wording-Glossar verbietet Vorhersagesprache.
   - Zweistufiges Binding (retrieval_score vs entailment), deterministische Checks vor Embedding.
   - source_kind-Trennung (Seed/Simulation/Recherche) mit Default `inferred`.
   - Red-Team-Review bei hohem Echo-Index.
   - Kanonische evidence_id (SHA-256 aus scope+source_kind+producer_key).
   - ADR-0013 wird die Seed-Provenance eventually liefern (Teil A da, Teil B offen).
5. **Mehrwert entsteht erst, wenn:** (a) Teil B umgesetzt ist (echte Seed-Provenance), (b) Interview-Binding-Defekt gefixt ist (Interviews werden kanonische Evidence), (c) Confidence-Konzepte getrennt werden (simulation_consensus / evidence_confidence / empirical_confidence), (d) Baseline-Runner Agora-vs-Single-Prompt misst.

**Vorläufige Score-Tendenz:** Engineering Score hoch (ehrliche ADRs, Contracts, Tests, Echo-Cap, Wording-Gate); Evidence/Research Score niedrig (0 validierte Claims, Provenance gebrochen, keine Baseline, keine Reproduzierbarkeits-Tests, Simulation nicht empirisch validiert).

## Quellen (Source-Type: official, As Of: 2026-08-09)
- `backend/uploads/reports/report_e2e_trust01/evidence_map.json` + `report-v3.json` (output-Artefakt, official)
- `docs/reference-runs/2026-08-09-domain-migration-v2/README.md` (official, heute)
- `docs/reference-runs/2026-08-09-domain-migration/README.md` (official)
- `docs/decisions/0011-evidence-entailment-and-provenance.md` (official)
- `docs/decisions/0013-seed-corpus-document-anchor.md` (official)