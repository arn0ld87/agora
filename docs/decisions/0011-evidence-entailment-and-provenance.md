# ADR-0011: Evidence-Entailment, Provenance-Trennung und Final-Content-Contract

- Status: akzeptiert
- Datum: 2026-07-27
- Bezug: ergänzt [ADR-0002](0002-evidence-gating.md) — ersetzt es nicht

## Kontext

Der Referenzlauf `report_d9023bd1f55a` (Simulation `sim_7058c126da03`, 30 Agents,
315 Interaktionen, 5 Cluster, Echo-Chamber-Index 0.4317, Modus `balanced`)
lieferte einen Report, der formal valide, inhaltlich aber nicht vertrauenswürdig
war. Sieben Ursachen ließen sich im Code belegen:

1. Der Section-Prompt forderte ausdrücklich `Output your thinking` und
   `First think (Thought)`; `workflow.py` übernahm den Modelloutput per
   `final_answer = response.strip()` ungeprüft. Interne Arbeitsschritte
   erschienen als Berichtsinhalt und wurden zu Claims weiterverarbeitet.
2. Seed-Zahlen wanderten zu falschen Bezugsgruppen (61 % Zeitersparnis der
   Lehrkräfte wurde zu "61 % bewerten die Lernhilfe positiv"); eine Zielvorgabe
   ("70 % sollen geschult sein") wurde als Zustimmungsquote gelesen.
3. `evidence_binder.bind_evidence_to_claim` setzte `supports_claim = True`
   allein aufgrund von Cosine-Similarity über einem Schwellwert.
4. `EvidenceItemModel.source_kind` hatte den Default `seed_corpus`. Damit galt
   jedes Item ohne explizite Angabe als Dokumentfakt — auch Agentenaktionen und
   Web-Treffer.
5. Interpretationen ohne Beleg liefen als Claims durch, weil der Claim-Floor
   jedes thematisch ähnliche Evidence-Item mitzählte.
6. `generate_section_metadata` extrahierte Personas, Segmente und
   Reibungspunkte, gab sie aber nur an den Report-Logger weiter. `ReportV3`
   blieb leer, während der Prosa-Report dieselben Inhalte zeigte.
7. `report.status = ReportStatus.COMPLETED` wurde unabhängig davon gesetzt, ob
   einzelne Abschnitte fehlgeschlagen waren.

## Entscheidung

### 1. Evidence-Binding ist zweistufig

Retrieval und Beweis werden getrennt:

- Stufe 1 schreibt `retrieval_score` (Cosine-Similarity). Sie beantwortet nur
  "gleiches Thema?".
- Stufe 2 (`evidence_entailment.classify_evidence`) schreibt `entailment` mit
  einem von vier Urteilen: `SUPPORTED`, `CONTRADICTED`, `RELATED_ONLY`,
  `INSUFFICIENT`.

`supports_claim = True` wird ausschließlich bei `SUPPORTED` gesetzt.
`RELATED_ONLY` und `INSUFFICIENT` erhöhen die Confidence nie;
`CONTRADICTED` senkt sie und setzt `contradicts_claim`.

Deterministische Checks haben Vorrang. Sobald ein Claim eine Zahl, eine
Bezugsgruppe oder eine Mengenaussage trägt, entscheidet die Regel — nicht das
Embedding. Ein optionaler LLM-Judge darf ein regelbasiertes `SUPPORTED` nur
abschwächen, nie erzeugen.

Ein numerischer Seed-Fakt gilt nur dann als übernommen, wenn Zahl,
Bezugsgruppe, Aussage **und** Modalität zusammenpassen. Die Modalität trennt
berichtete Ist-Werte von normativen Zielvorgaben ("sollen", "geplant").

### 2. Provenance unterscheidet Seed, Simulation und Recherche

`EvidenceSourceKind` wird additiv um `agent_action` und `web_source` erweitert.
Der Default wechselt von `seed_corpus` zu `inferred`: unbekannte Herkunft ist
abgeleitet, nicht belegt.

Für die ADR-0002-Anker ändert sich nichts — `cross_stakeholder_for_high` wertet
weiterhin ausschließlich `agent_quote` als Stakeholder-Stimme, und
`reject_inferred_in_high_confidence` bleibt unverändert. Eine Agentenaktion ist
Simulationsverhalten, keine Stakeholder-Aussage, und rechtfertigt kein `high`.

### 3. Final-Content-Contract

Der Section-Prompt fordert kein "Thought" mehr: eine Antwort enthält entweder
nur den `<tool_call>`-Block oder nur `Final Answer:` plus Berichtstext. Die
Durchsetzung liegt in `report_agent/output_contract.sanitize_final_content` —
gestaffelt (strukturell vor zeilenweise vor Gate), nicht als Regex-Halde.
Bleibt nach dem Entfernen aller Arbeitsspuren kein tragfähiger Inhalt übrig,
wird der Output abgelehnt statt notdürftig weitergereicht.

### 4. Fehlgeschlagene Abschnitte sind sichtbar

Abschnitte mit Fallback-Text erzeugen weder Claims noch Evidence noch
Metadaten. Eine fehlgeschlagene Pflichtsection setzt den Report auf
`INCOMPLETE`; der Rest bleibt nutzbar.

### 5. ReportV3 ist die kanonische Struktur-Quelle

Validierte Section-Metadaten fließen über `report_agent/metadata_merge` in
`ReportV3`. Markdown, HTML, JSON und Frontend rendern dieselbe Quelle, statt
Inhalte unabhängig zu rekonstruieren.

### 6. Confidence trennt Quellentreue von Simulationskonsens

`compute_confidence` rechnet nur noch mit stützender Evidence.
`compute_confidence_breakdown` liefert zusätzlich `source_fidelity` (wie
quellentreu gibt der Claim wieder, was in den Quellen steht) und
`simulation_consensus` (wie breit tragen unabhängige simulierte
Stakeholder-Gruppen die Aussage). Ein korrekt wiedergegebener Seed-Fakt ist
damit ausdrücklich keine Aussage über die reale Bevölkerung.

## Konsequenzen

- Reports enthalten weniger Claims und mehr explizit markierte Hypothesen. Das
  ist beabsichtigt.
- Bestehende Evidence-Daten ohne `entailment`-Feld gelten weiterhin als
  stützend, damit Alt-Reports beim Neuberechnen nicht ihre Confidence verlieren.
- Alte Fixtures ohne `source_kind` laden weiter, verlieren aber ihren
  unverdienten Seed-Status.
- Die Drift-Guards für ADR-0002 Anker 3 wurden auf sechs Werte gepinnt. Anker 1,
  2, 4 und 5 sind unverändert.

## Verworfene Alternativen

**Nur eine Sanitizer-Regex gegen `Thought:`.** Behandelt das Symptom. Solange
der Prompt Denkprotokolle anfordert, produziert das Modell sie weiter — in
Varianten, die keine Regex-Liste vollständig erfasst.

**Similarity-Schwelle anheben statt Entailment.** Ein höherer Schwellwert
verschiebt nur, wo die Verwechslung von Ähnlichkeit und Beweis auftritt. Sie
bleibt bestehen.

**`EvidenceSourceKind` ersetzen statt erweitern.** Hätte ADR-0002 Anker 3
gebrochen und alle bestehenden Reports invalidiert. Die additive Erweiterung
verschärft die Trennung, ohne das Gating zu schwächen.
