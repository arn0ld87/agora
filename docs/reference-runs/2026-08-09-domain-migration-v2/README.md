# Referenzlauf v2: Domainmigration `alexle135.de` → `alex-schneider.dev`

> [!IMPORTANT]
> Dieser Lauf dokumentiert Agoras Verhalten in einer simulierten Multi-Agenten-Umgebung. Er ist **kein** Nachweis dafür, dass die simulierten Personas reale Menschen repräsentieren oder reales menschliches Verhalten vorhersagen.

## Warum dieser zweite Lauf dokumentiert wird

Dieser Lauf wurde nach der ersten Domainmigration-Evaluation erneut ausgeführt, nachdem Agora an Reportplanung, Evidence-Identität und Report-Gating überarbeitet worden war. Er ersetzt den [ersten Referenzlauf](../2026-08-09-domain-migration/README.md) nicht, sondern zeigt, welche Teile sich verbessert haben und welche neue Integrationslücke dadurch sichtbar wurde.

Der zweite Lauf ist besonders nützlich, weil er zwei Dinge gleichzeitig zeigt:

1. Die Simulation und Report-Generierung sind gegenüber dem ersten Lauf deutlich konsistenter und fokussierter.
2. Der strengere Evidence-Vertrag deckt einen neuen Provenance-Bruch auf: erfolgreiche Deep Interviews werden im Report verwendet, aber im exportierten Evidence Index nicht als kanonisch referenzierbare Interview-Evidence persistiert. Dadurch bleiben alle ReportV3-Claims leer.

## Run-Identität

| Feld | Wert |
|---|---|
| Report-ID | `report_06f654800817` |
| Simulation-ID | `sim_464a7a8e6310` |
| Evidence Schema | `3` |
| Report-Modus | `balanced` |
| Report-Intent | `risk` |
| geplante Sections | `6` |

## Simulation Snapshot

Der exportierte Metrics-Snapshot ist in diesem Lauf konsistent mit der geladenen Agentenpopulation:

| Metrik | Wert |
|---|---:|
| Agenten im Metrics-Snapshot | **30** |
| Graph-Interaktionen | **412** |
| Social Actions im Sampling-Universum | **540** |
| Cluster | **3** |
| Clustergrößen | **12 / 12 / 6** |
| Echo-Chamber-Index | **0.5461** |
| Bridge Agents | **28, 6, 22, 29, 0** |

Damit ist die Population-Accounting-Diskrepanz des ersten Laufs (`33` angegebene erzeugte Agenten vs. `24` im Snapshot) in diesem Run nicht mehr sichtbar: Die Logs laden 30 Agentenprofile und der Metrics-Snapshot weist ebenfalls `total_agents: 30` aus.

`540 Social Actions` und `412 Graph-Interaktionen` sind unterschiedliche exportierte Größen und werden nicht gleichgesetzt.

## Adaptive Reportplanung

Agora erkannte den Intent `risk` und reduzierte die Outline von elf auf sechs passende Abschnitte:

1. Kurzfazit
2. Betroffene Gruppen
3. Zentrale Risiken
4. Reibungspunkte und Eskalationspfade
5. Gegenmaßnahmen
6. Unsicherheiten und Datenlücken

Der Report wird damit nicht mehr als starres Universaltemplate behandelt.

## Abschnittsspezifische Deep Interviews

Für jede Section lädt Agora 30 verfügbare Agentenprofile und wählt acht thematisch passende Agenten für ein vertiefendes Interview aus. Die Auswahl wechselt je nach Abschnitt:

| Section | ausgewählte Agenten-IDs |
|---|---|
| 1 | `13, 27, 28, 25, 29, 21, 19, 1` |
| 2 | `13, 27, 29, 21, 25, 15, 5, 18` |
| 3 | `13, 0, 21, 19, 27, 25, 1, 29` |
| 4 | `27, 28, 13, 1, 21, 25, 29, 6` |
| 5 | `13, 0, 27, 25, 21, 22, 29, 1` |
| 6 | `13, 27, 25, 0, 1, 29, 19, 5` |

Pro Interview-Batch wurden vier oder fünf section-spezifische Fragen erzeugt. Die API meldete jeweils acht erfolgreiche Ergebnisse.

Aussagen wie `8/8` beziehen sich deshalb auf die **acht für den jeweiligen Abschnitt interviewten Agenten**, nicht automatisch auf die gesamte 30-Agenten-Population.

## Tool-Nutzung pro Section

Der ReACT-ReportAgent kombinierte je nach Abschnitt unterschiedliche Reihenfolgen aus:

- `insight_forge`
- `panorama_search`
- `interview_agents`
- `quick_search`

Die Reihenfolge war nicht vollständig starr. Beim Kurzfazit lief beispielsweise zunächst `insight_forge`, während bei „Betroffene Gruppen“ zuerst `interview_agents` aufgerufen wurde.

## Was im Report besser funktioniert

### 1. Evidenzlücken werden explizit benannt

Der Report unterscheidet klarer zwischen dokumentierten Aussagen, simulationsgestützten Einschätzungen und Fragen, die ohne reale Daten nicht belastbar beantwortet werden können.

Beispiele für ausdrücklich nicht belastbar beantwortete Punkte:

- ob Recruiter die neue Domain tatsächlich bevorzugen,
- ob `.dev` die Bewerbungsquote erhöht,
- ob die Migration SEO-neutral bleibt,
- ob bestehende Leser die neue Domain problemlos wiedererkennen.

### 2. Nicht ausreichend repräsentierte Gruppen werden sichtbar gemacht

Datenschutz-/Security-orientierte Besucher und potenzielle Arbeitgeber werden nicht einfach durch angrenzende Personas ersetzt. Der Report markiert, wenn eine Perspektive in einem Abschnitt nicht direkt interviewt wurde.

### 3. Risikoanalyse ist strukturierter

Risiken erhalten Eintrittswahrscheinlichkeit, Auswirkung, Evidenzgrad, Frühindikatoren und Gegenmaßnahmen. Zusätzlich werden Konfliktachsen und Eskalationspfade getrennt analysiert.

### 4. Evidence-Gating greift in den generierten Fließtext ein

Die Logs zeigen, dass nach der Section-Generierung ungedeckte Faktenaussagen entfernt bzw. als Hypothesen weitergeführt wurden:

| Section | entfernte ungedeckte Aussagen |
|---|---:|
| Zentrale Risiken | 3 |
| Reibungspunkte und Eskalationspfade | 2 |
| Gegenmaßnahmen | 11 |
| Unsicherheiten und Datenlücken | 1 |
| **Summe** | **17** |

Diese Schutzfunktion soll bei der Remediation ausdrücklich erhalten bleiben.

## Kanonische Evidence-Identität funktioniert grundsätzlich

Im Gegensatz zum historischen Lauf enthält der Evidence Index echte kanonische IDs wie:

```text
ev_36886410740125f7bdc247245888ec99
ev_3b3da5a1e8c225f9a71a8c5497e9dcb8
```

sowie strukturierte `producer_key`-Werte.

Der Export enthält derzeit zwölf kanonische Evidence-Items:

- **8 × `agent_action`**
- **4 × `graph_metric`**

Damit ist der in PR #1147 adressierte Grundsatz korrekt sichtbar: Ein freier Quellenstring wie `report_tool` ist keine hinreichende Claim-Identität.

## Kritischer neuer Befund: Interview-Evidence wird nicht kanonisch gebunden

Dies ist der wichtigste offene Defekt dieses Laufs.

Die Logs belegen erfolgreiche Deep Interviews, und die finalen Reporttexte zitieren diese Antworten. Im exportierten `evidence_index` sind jedoch keine entsprechenden kanonischen `agent_interview`-/`interview_response`-Items vorhanden.

Die Interviewantworten tauchen stattdessen teilweise nur als Text in `suggested_evidence` auf.

Der beobachtete Datenpfad ist damit sinngemäß:

```text
interview_agents
    ↓
erfolgreiche Antwort
    ↓
ReACT-Section verwendet die Antwort
    ↓
Candidate Claim wird extrahiert
    ↓
keine kanonische evidence_id für das Interview
    ↓
Claim darf nicht persistiert werden
    ↓
Hypothese
```

Dieser Defekt darf **nicht** dadurch repariert werden, dass der Claim-Validator gelockert wird. Der Fix muss upstream die Interviewantwort als konkrete, auflösbare Evidence persistieren.

## Folge: ReportV3 enthält null validierte Claims

Alle sechs exportierten Sections enthalten:

```json
"claims": []
```

Gleichzeitig enthält jede Section fünf primäre Hypothesen. Insgesamt ergeben sich im Evidence-Export damit:

- **0 validierte Claims**
- **30 primäre Hypothesen**
- **12 kanonische Evidence-Items**

Das ist für einen `balanced`-Report ein deutliches Signal für eine Binding-Lücke. Wichtig: `0 Claims` ist nicht deshalb falsch, weil ein Report zwingend Claims enthalten müsste. Es ist hier auffällig, weil die verwendeten Interviews und Seed-/Retrieval-Inhalte tatsächlich vorhanden sind, aber nicht kanonisch gebunden werden können.

## Zweiter Konsistenzfehler: High Confidence ohne validierten Claim

`structured_metadata.key_takeaways` enthält an mehreren Stellen Aussagen mit `confidence: high`, obwohl dieselbe Section `claims: []` enthält und entsprechende Aussagen als Hypothesen geführt werden.

Damit werden mindestens zwei unterschiedliche Konzepte vermischt:

- interne bzw. simulierte Konvergenz,
- Evidence-Konfidenz eines validierten Claims.

Eine spätere Remediation sollte Confidence deshalb mindestens nach Scope unterscheiden, zum Beispiel `simulation_consensus`, `evidence_confidence` und `empirical_confidence`.

## Dritter Konsistenzfehler: Structured Metadata sieht offenbar unvollständige Sections

Die Structured Metadata meldet bei mehreren Abschnitten sinngemäß, der Text breche ab oder angekündigte Risiken würden nicht vollständig ausgeführt. Im vollständigen finalen Report sind diese Inhalte jedoch vorhanden.

Das spricht dafür, dass `generate_section_metadata()` wahrscheinlich nicht den vollständigen postprocessed Section-Text erhält, sondern einen gekürzten oder anderweitig truncatierten Textpfad. Die genaue Root Cause muss im Code reproduziert werden.

## `degradation_log` und Auditierbarkeit

Der Evidence-Export endet mit:

```json
"degradation_log": []
```

Gleichzeitig zeigen die Logs 17 entfernte ungedeckte Aussagen. Zu klären ist, ob diese Operationen absichtlich nicht als Degradation gelten oder ob ein separates strukturiertes `claim_decision_log`/`evidence_gate_log` fehlt.

Die Auditspur sollte die Entscheidung speichern, nicht interne Chain-of-Thought:

```text
Section
Candidate Claim
from_status
to_status
reason
candidate_evidence_refs
```

## Social Simulation: bessere Datenbasis, noch zu wenig Report-Nutzung

Der Run enthält 30 Agenten, 412 Graph-Interaktionen, 540 Social Actions, drei Cluster und fünf Bridge Agents. Der finale Report argumentiert trotzdem überwiegend über die section-spezifischen Deep Interviews.

Für spätere Reportversionen wäre zusätzlich interessant:

- Narrativausbreitung zwischen Clustern,
- Gegenpositionen,
- Bridge-Agent-Effekte,
- Interaktionsketten,
- Social Support Ratios.

Diese Größen bleiben Simulationsevidence und dürfen nicht als empirische Mehrheitsmeinung realer Menschen interpretiert werden.

## Was dieser Lauf demonstriert

Dieser Lauf zeigt, dass Agora aktuell:

- eine konsistente 30-Agenten-Simulation mit Social Actions und Graphmetriken ausführen kann,
- intentabhängig eine Reportstruktur planen kann,
- pro Section relevante Agenten für Deep Interviews auswählen kann,
- mehrere Analyse-/Retrieval-Tools ReACT-gesteuert kombinieren kann,
- ungedeckte Aussagen nach der Textgenerierung erkennen und aus dem Fließtext entfernen kann,
- kanonische Evidence-IDs für bereits angebundene Evidence-Typen erzeugt,
- eigene Datenlücken und nicht ausreichend vertretene Perspektiven sichtbar machen kann.

## Was dieser Lauf ausdrücklich nicht demonstriert

Er zeigt **nicht**:

- prädiktive Validität für reales menschliches Verhalten,
- Repräsentativität der 30 Agenten für reale Stakeholder,
- empirische Recruiter-Präferenzen,
- reale SEO-Auswirkungen der Domainmigration,
- dass `8/8` Interviewzustimmung einer realen Mehrheitsmeinung entspricht,
- dass die Evidence-Pipeline bereits vollständig geschlossen ist,
- dass ein `high`-Confidence-Key-Takeaway automatisch ein validierter Claim ist.

## Vergleich mit dem ersten Referenzlauf

| Bereich | Erster Lauf | Zweiter Lauf |
|---|---|---|
| Metrics-Agenten | 24 | **30** |
| Betreiberangabe Population | 33, Diskrepanz offen | **30 und Snapshot konsistent** |
| Graph-Interaktionen | 267 | **412** |
| Social-Action-Population | 473 | **540** |
| Cluster | 3 | 3 |
| Echo-Chamber-Index | 0.4794 | 0.5461 |
| Reportplanung | weniger fokussiert | **Intent `risk` → 6 Sections** |
| Deep Interviews | vorhanden | **section-spezifisch 8 aus 30** |
| Evidence-ID | historischer Legacy-Mangel | **kanonische `ev_...` IDs vorhanden** |
| Interview → Evidence Binding | schwach | **weiterhin offen / jetzt klar sichtbar** |
| validierte Claims | vorhanden, aber historisch problematisch gebunden | **0, weil Binding fehlt** |

Der zweite Run ist damit **kein Beweis, dass alle Evidence-Probleme behoben sind**. Er ist ein besser instrumentierter Lauf, der den nächsten klaren Fehler sichtbar macht.

## Remediation-Priorität

Die wichtigste Folgearbeit ist der Datenpfad:

```text
interview_agents
→ Tool Result
→ Evidence Normalization
→ Evidence Index
→ evidence_id
→ Claim.evidence_refs
→ ReportV3 Validator
→ Renderer / Export
```

Die zentrale Frage lautet:

> An welcher Stelle geht die Identität einer erfolgreichen Interviewantwort zwischen Tool Result und Evidence Index verloren?

Danach folgen:

1. Seed-/Retrieval-Evidence kanonisch binden,
2. Aggregationsclaims wie `8/8` maschinenlesbar mit `eligible/supporting/contradicting` modellieren,
3. Confidence-Scope trennen,
4. Structured-Metadata-Truncation beheben,
5. Renderer an Claim-/Hypothesenstatus koppeln,
6. Social-Graph-Dynamik stärker in die Analyse einbeziehen.

## Artefakte

Ein kompakter Evidence-Auszug und die SHA-256-Provenienz der vollständigen bereitgestellten Artefakte liegen unter [`artifacts/`](./artifacts/README.md).

Die vollständigen generierten Exporte werden auch bei diesem Run nicht als zweite Dokumentations-SSoT in den Git-Tree kopiert. Der Extract bindet die öffentlich dokumentierten Zahlen und Findings an die bereitgestellten Originalartefakte.

## Fazit

Der zweite Run ist als technischer Referenzlauf wertvoll, **gerade weil er nicht makellos ist**. Simulation, Population Accounting, adaptive Reportplanung und Text-Gating sind sichtbar besser als beim ersten Lauf. Gleichzeitig verhindert der strengere Evidence-Vertrag zu Recht die Persistenz nicht referenzierbarer Claims und legt dadurch offen, dass Interviewantworten noch nicht als kanonische Evidence durch die gesamte Pipeline getragen werden.

Das ist kein Grund, den Run zu verstecken. Es ist ein reproduzierbarer Produktbefund und damit genau die Art von Referenz, die weitere Remediation sinnvoll macht.
