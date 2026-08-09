# ADR-0013: Verifizierter Dokument-Anker für seed_corpus-Evidence

- Status: akzeptiert
- Datum: 2026-08-09
- Bezug: ergänzt [ADR-0011](0011-evidence-entailment-and-provenance.md) und
  [ADR-0002](0002-evidence-gating.md) — ersetzt beide nicht
- Entscheidungsvorlage: [#1086](https://github.com/arn0ld87/agora/issues/1086),
  Vorarbeit [#1008](https://github.com/arn0ld87/agora/issues/1008)

## Kontext

ADR-0002 verlangt für das Confidence-Label `medium` mindestens eine
`agent_quote`- **und** eine `seed_corpus`-Evidence (`has_agent_grounded_evidence`
in `backend/app/services/report_agent/evidence.py`, gespiegelt vom Validator
`ReportClaimModel.agent_grounded_for_medium`). Diese Stufe ist im laufenden
System nicht erreichbar, und der Anker, auf den sie sich stützt, ist nicht
überprüfbar. Beides ist im Code belegt:

1. **Seed-Aussagen erreichen den `evidence_index` nur als `graph_fact`.** Die
   Graph-Tool-DTOs `SearchResult.facts`, `InsightForgeResult.semantic_facts` und
   `PanoramaResult.active_facts` (`backend/app/services/graph/graph_dtos.py`)
   sind `List[str]`. Ein Fakt trägt keine Herkunft, also mappt
   `_record_tool_evidence` ihn auf `source_kind=graph_relation`. Ein echtes
   `seed_corpus`-Item aus dem Retrieval kann so nicht entstehen.

2. **Dokumentidentität existiert in der Pipeline nicht.** `document_id` und
   `chunk_id` kommen in `backend/app` nirgends vor. `graph_build` konkateniert
   den Korpus zu einem einzigen `text` und chunkt ihn danach
   (`TextProcessor.split_text` → `List[str]`); die Dokumentgrenze ist vor dem
   Chunking bereits verloren. `Neo4jGraphStorage.add_text` erzeugt ein
   `episode_id = uuid4()` ohne jeden Bezug zur Quelldatei, und
   `graph_reader.search` liefert nur `edge["fact"]` und Node-Summaries zurück.

3. **Der einzige heute existierende Seed-Anker ist unverifiziert.** Das
   `seed_doc:`-Präfix wird als opake Referenz ohne Lookup akzeptiert
   (`report_prompts/sections.py`, `report_agent/evidence.py`). Es ist eine
   Selbstauskunft des Modells: Das LLM benennt seine eigene Quelle, und niemand
   prüft nach.

Damit hängt die Trennung „belegter Dokumentfakt" gegen „abgeleitete Aussage"
— der Kern von ADR-0002 — an Modellgehorsam. Genau diese Abhängigkeit hat
ADR-0011 an anderer Stelle bereits als untragbar verworfen.

## Entscheidung

### 1. `source_id_anchor` wird für `seed_corpus` verpflichtend

Ein Evidence-Item darf `source_kind=seed_corpus` nur führen, wenn es einen
serverseitig erzeugten Anker trägt. Der Producer bildet den Anker aus dem
tatsächlichen Retrieval-Ergebnis; das LLM darf ihn weder erfinden noch
überschreiben. Ohne Anker gilt die bestehende Regel aus ADR-0011 unverändert
weiter: unbekannte Herkunft ist `inferred`, ein Graph-Fakt ohne Dokumentbezug
bleibt `graph_relation`. Geraten wird nicht.

### 2. Ankerformat ist `seed_doc:<document_id>#chunk:<chunk_id>`

Dokument **und** Chunk. Die Chunk-Ebene kostet fast nichts zusätzlich, sobald
die Dokumentidentität überhaupt durch den Chunker gereicht wird — die
Reihenfolge der Chunks liegt dort ohnehin vor. Sie ist aber der Unterschied
zwischen „steht irgendwo in einem 80-seitigen Dokument" und einer nachprüfbaren
Stelle.

`document_id` ist eine kanonische, pro Upload eindeutige Kennung. Autorengegebene
Quellen-Labels im Chunk (etwa `A1`–`J1` im Referenz-Testfall) sind **keine**
`document_id`: Sie sind über mehrere hochgeladene Dokumente hinweg nicht
garantiert eindeutig, und zwei Dateien mit gleichem Label und gleicher lokaler
Chunk-Nummer erzeugten denselben Anker. Ein Anker, der auf zwei Stellen zeigen
kann, ist serverseitig nicht verifizierbar — und Verifizierbarkeit ist der
einzige Zweck dieser Entscheidung. Das Autoren-Label wird als Metadatum am
Evidence-Item geführt und darf angezeigt werden; die Auflösung läuft
ausschließlich über die kanonische ID.

### 3. Bestandsgraphen werden nicht nachgerüstet

Bereits gebaute Neo4j-Graphen tragen Episoden mit `uuid4()` ohne Dateibezug. Der
Anker ließe sich daraus nicht rekonstruieren, sondern nur erfinden. Es gibt
deshalb weder Backfill noch Reingest-Zwang: Altgraphen liefern dauerhaft keine
`seed_corpus`-Evidence. Wer sie will, baut den Graphen neu. Kompatibilitätscode
dafür entsteht nicht.

Betroffen ist damit ausschließlich die Stufe `medium`, die über
`agent_grounded_for_medium` zwingend eine `seed_corpus`-Evidence verlangt. Ein
Claim aus einem Altgraphen, dessen Confidence auf Seed-Evidence angewiesen ist,
bleibt auf `low`.

**Kein pauschaler Deckel.** `cross_stakeholder_for_high` wertet ausschließlich
`agent_quote` aus zwei unterschiedlichen Stakeholder-Gruppen; `seed_corpus`
kommt darin nicht vor. Ein hinreichend breit gestützter Interview-Claim erreicht
also auch aus einem Altgraphen weiterhin `high` oder `verified`. Weder
Implementierung noch Tests dürfen daraus einen generellen `low`-Cap für
Altgraphen ableiten. Dass `medium` hier strenger ist als `high`, ist eine
bestehende Eigenheit von ADR-0002 und wird von dieser ADR nicht angefasst.

### 4. Persistierte Items ohne Anker werden beim Laden abgestuft

Für bestehende `evidence-map.json`-Dateien läuft der Downgrade beim **Lesen**
über `normalize_persisted_evidence_map` in
`backend/app/services/evidence_migrations.py` — die Datei auf der Platte wird
nicht mutiert, der Schritt ist idempotent. Ein `seed_corpus`-Item ohne
verifizierten Anker verliert dort seinen Seed-Status; ein Claim, der dadurch
seine agent-grounded Basis verliert, fällt von `medium` auf `low`.

**Der Downgrade ist ein Identitätswechsel, kein Label-Update.**
`build_evidence_id(scope_id, source_kind, producer_key)` in
`services/evidence_identity.py` nimmt `source_kind` in den Hash auf. Wer
`seed_corpus` durch eine andere Gattung ersetzt, ändert damit die kanonische
Identität des Records. `EvidenceMapModel` prüft beides: dass jeder
`evidence_index`-Key mit der `evidence_id` seines Records übereinstimmt, und
dass jede Claim-Bindung auf einen existierenden Key zeigt. Ein Downgrade, der
nur `source_kind` umschreibt, oder einer, der die Record-ID neu berechnet, ohne
Index-Key und Bindungen mitzuziehen, produziert deshalb exakt den HTTP 422,
den er verhindern soll.

Der Schritt ist folglich atomar zu implementieren: neue `evidence_id` berechnen,
`evidence_index` umschlüsseln, alle Claim-Bindungen und globalen Referenzen in
derselben Operation nachziehen. Kollidiert die neue ID mit einem bereits
vorhandenen Record derselben Gattung, werden die Einträge zusammengeführt statt
überschrieben.

Damit unterscheidet sich dieser Fall ausdrücklich von Issue #963: Dort wurde
`confidence_label` am Claim geändert, was kein Identitätsbestandteil ist. Das
Lese-Zeitpunkt-Muster wird von dort übernommen, die Mutationsmechanik nicht.

Eine Legacy-Ausnahme mit Stichtag wird ausdrücklich **nicht** eingeführt.

### 5. Die ADR-0002-Hartanker bleiben unberührt

Diese Entscheidung verschärft die Provenance-Prüfung und schwächt keinen der
fünf Anker. `cross_stakeholder_for_high` und
`reject_inferred_in_high_confidence` bleiben unverändert; der Hedge-Snapshot,
der Prompt-Block und `EvidenceSourceKind` werden nicht angefasst. `EvidenceType`
wird additiv um `seed_document` ergänzt — das Mapping nach `seed_corpus` liegt
in `_TYPE_TO_SOURCE_KIND` bereits vor.

## Konsequenzen

- Der Weg zum Anker führt über fünf Ebenen: Text-Aggregation → Chunker →
  Episode-Persistenz (Cypher und Schema) → Retrieval-Query → DTO →
  `_record_tool_evidence`. Das ist keine additive DTO-Erweiterung, sondern ein
  Cross-Layer-Slice mit Schema-Anteil.
- Unmittelbar nach der Umsetzung werden Reports *schlechter* aussehen als heute:
  Seed-gestützte Claims aus Altgraphen fallen auf `low`, und ein bisher
  stillschweigend als Seed durchgewinkter Anker zählt nicht mehr. Das ist der
  Zweck.
- Der Downgrade-Pfad fasst die kanonische Evidence-Identität an und braucht
  deshalb Regressionstests gegen die Cross-Reference-Validierung von
  `EvidenceMapModel`, nicht nur gegen das Confidence-Label.
- Ein herabgestufter Claim behält vorerst seinen ungehedgten Wortlaut. Der
  Defekt ist bekannt und getrennt getrackt
  ([#1012](https://github.com/arn0ld87/agora/issues/1012)); er trifft auch
  diesen Downgrade-Pfad.
- Die Stufe `medium` wird erstmals real erreichbar, statt nur im Contract zu
  stehen.

## Verworfene Alternativen

**Den `seed_doc:`-Anker weiter als opake Referenz akzeptieren.** Billig, aber
sinnlos: Ein Anker, den niemand auflöst, belegt nichts. Er verleiht der
Selbstauskunft des Modells nur die Form eines Belegs — das ist schlechter als
gar kein Anker, weil es Prüfbarkeit vortäuscht.

**Nur `document_id` ohne Chunk.** Spart praktisch keinen Aufwand, weil die
teure Arbeit das Durchreichen der Dokumentidentität ist, nicht der Chunk-Index.
Der Anker wäre bei großen Dokumenten aber nicht mehr nachschlagbar.

**Legacy-Ausnahme statt Downgrade.** Hieße, einen dauerhaften Zweig im
Validator zu pflegen, der `seed_corpus` ohne Anker durchlässt — eine
Aufweichung mitten in ADR-0002 Anker 5, die eine ablösende ADR und Sign-off
erfordern würde. Der Preis stünde in keinem Verhältnis: Die betroffenen
Bestandsdaten stammen aus Testläufen, nicht aus produktiver Nutzung.

**Anker rückwirkend aus Altgraphen rekonstruieren.** Nicht möglich. Die
Episoden tragen keine Dateiherkunft; jede Zuordnung wäre geraten und verstieße
gegen die Grundregel, keine Provenance zu erfinden.
