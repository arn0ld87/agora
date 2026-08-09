# Referenzlauf: Domainmigration alexle135.de → alex-schneider.dev

> [!IMPORTANT]
> Dieser Referenzlauf demonstriert Agoras **End-to-End-Pipeline, Social-Simulation und Evidence-Gating-Verhalten** in einem konkreten Szenario. Er validiert **keine** Vorhersage realen menschlichen Verhaltens und ersetzt keine Interviews, Nutzertests oder empirische Stakeholderforschung.

| Feld | Wert |
|---|---|
| Datum | 9. August 2026 |
| Report | `report_41f7b1bcf1e4` |
| Simulation | `sim_1d96603073ae` |
| Szenario | Domainmigration `alexle135.de` → `alex-schneider.dev` |
| Social-Umgebungen | Reddit-/Twitter-artige Simulation |
| Evidence-Schema des historischen Exports | `2` |
| Öffentlicher Evidence-Auszug | [`artifacts/evidence-extract.json`](./artifacts/evidence-extract.json) |
| Artefakt-Provenienz | [`artifacts/README.md`](./artifacts/README.md) |

## Warum dieser Lauf öffentlich dokumentiert wird

Agora soll nicht dadurch überzeugen, dass ein LLM einen plausibel klingenden Bericht produziert. Interessanter ist, ob die gesamte Pipeline unter realistischen Bedingungen zusammenarbeitet und ob das System mit seinen eigenen Unsicherheiten umgehen kann:

```text
Dokument / Szenario
        ↓
Knowledge Graph
        ↓
Stakeholder-Personas
        ↓
Social Multi-Agent Simulation
        ↓
Graph- und Interaktionsmetriken
        ↓
Claim-/Evidence-Prüfung
        ↓
Report + Hypothesen + Data Gaps
```

Der Domainwechsel eignet sich als Referenzfall, weil er mehrere Arten von Konflikten gleichzeitig enthält: Markenwirkung, Recruiting, technische Migration, SEO, E-Mail, Identitätskonsistenz und Bestandsnutzer. Das Seed-Material enthielt außerdem bewusst widersprüchliche und teilweise unbelegte Aussagen. Der Lauf konnte deshalb nicht sinnvoll bestehen, indem Agora einfach alles zusammenfasste und anschließend selbstbewusst nickte.

## Was Agora als Input bekam

Das Evaluationsszenario kombinierte vier Ebenen:

1. **dokumentierten Ausgangsbestand**, etwa bestehende Domain-, GitHub- und Website-Informationen,
2. **Planungsannahmen**, beispielsweise erwartete Vorteile einer Klarnamen-Domain,
3. **synthetische Stakeholder-Aussagen** für unterschiedliche Perspektiven,
4. **absichtlich eingebaute Widersprüche und Evidenzlücken**.

Die Fragestellung verlangte ausdrücklich die Trennung von dokumentbelegten Aussagen, plausiblen Hypothesen, unbelegten Behauptungen und fehlenden Informationen. Zusätzlich sollte genau eine Migrationsstrategie empfohlen und mit Risiken, Mindestbedingungen und Abbruchkriterien begründet werden.

Synthetische Aussagen im Seed und alle später von Agenten erzeugten Aussagen sind **keine realen Nutzer- oder Recruiter-Interviews**.

## Simulation: Population und Snapshot

Für den Lauf wurde vom Betreiber eine **erzeugte Simulationspopulation von 33 Agenten** angegeben. Der exportierte Metrics-Snapshot weist dagegen `total_agents: 24` aus.

> [!WARNING]
> Die Differenz **33 vs. 24** wird hier absichtlich nicht erklärt. Aus den eingefrorenen Exporten lässt sich nicht belastbar ableiten, ob `24` nur aktive Agenten, ein bestimmtes Analysefenster oder eine Instrumentations-/Accounting-Lücke beschreibt. Für die öffentliche Dokumentation gilt daher: **33 = Betreiberangabe zum Laufkontext; 24 = artefaktbelegter Wert des Metrics-Snapshots.**

### Artefaktbelegte Snapshot-Metriken

| Metrik | Wert |
|---|---:|
| `total_agents` | 24 |
| `total_interactions` | 267 |
| `cluster_count` | 3 |
| `echo_chamber_index` | 0.4794 |
| Bridge Agents | `24, 15, 11, 18, 0` |
| Clustergrößen | `13 / 6 / 5` |

Der Evidence-Export enthält außerdem gesampelte `agent_action`-Ereignisse, deren Sampling-Metadaten `sampled_from_total: 473` ausweisen. **473 Actions und 267 Interactions sind unterschiedliche exportierte Größen und werden hier nicht gleichgesetzt.**

## Was in der Social-Simulation tatsächlich passiert ist

Der Lauf war keine Folge isolierter Persona-Fragebögen. Agenten erzeugten Social-Actions in Reddit-/Twitter-artigen Umgebungen, unter anderem:

- `CREATE_POST`,
- `CREATE_COMMENT`,
- `LIKE_POST`,
- `LIKE_COMMENT`,
- `FOLLOW`.

Der öffentliche Evidence-Auszug enthält konkrete Beispiele aus mehreren Runden. So erstellt ein `HRRecruiter` in Runde 0 einen Reddit-Post zur neuen Domain. In späteren Runden liken andere Agenten Beiträge auf Reddit und Twitter, reagieren auf Aussagen anderer Rollen und tragen Narrative weiter.

Besonders aufschlussreich ist ein anderes Ereignis: Ein simulierter Agent mit dem Namen `arn0ld87` behauptet in einem Reddit-Kommentar plötzlich, 301-Redirects seien bereits sauber umgesetzt, TLS laufe über Let's Encrypt und SPF/DKIM/DMARC seien getestet worden. Diese konkrete Betriebsbehauptung ist **Simulationsoutput**, nicht automatisch eine dokumentierte Realwelt-Tatsache.

Genau solche Ereignisse sind für diesen Referenzlauf wichtiger als ein hübsches Persona-Zitat: Eine Social-Simulation darf neue Behauptungen erzeugen. Der nachgelagerte Report darf sie aber nicht ungeprüft in Fakten verwandeln.

## Ergebnis des generierten Reports

Der Report tendierte zu **Option B: kontrollierte 90-Tage-Migration**. Als zentrale Themen wurden unter anderem genannt:

- Identitätsinkonsistenz zwischen Website, GitHub, Repository-Namen und E-Mail,
- Redirect- und Erreichbarkeitsrisiken,
- mögliche SEO-Verluste beziehungsweise Unsicherheit während der Migration,
- E-Mail-/Auth-/CSP-/CORS-Risiken,
- mögliche Fehlwahrnehmung von `.dev` als reines Softwareentwicklungsprofil,
- Spannungen zwischen Recruiting-Positionierung und technischer Tiefe.

Dieses Ergebnis ist eine **simulationsbasierte Entscheidungshilfe**, keine empirisch validierte Prognose.

Der Report selbst benennt wichtige Grenzen: Ob Recruiter die neue Domain tatsächlich bevorzugen, ob Rankings real sinken und ob `.dev` in echten Auswahlprozessen falsch interpretiert wird, kann aus der Simulation nicht belastbar beantwortet werden. Dafür wären reale Traffic-/Backlink-Daten, Recruiter-Befragungen, Nutzerfeedback und technische Tests nötig.

## Evidence Gating: der wichtigere Teil des Referenzlaufs

Die für Agora entscheidende Frage lautet nicht: „Klingt der Report plausibel?“ Sondern: **Was passiert, wenn eine plausible Aussage nicht ausreichend belegt ist?**

Der historische Evidence-Export zeigt mehrere Schutzmechanismen.

### `RELATED_ONLY` ist kein Beleg

Ein Beispiel aus dem Export:

- Claim: Die neue Domain solle professioneller auf Recruiter wirken und den Klarnamen stärker hervorheben.
- gefundene Evidence: Die neue Domain werde Primärdomain und die alte Domain erhalte Redirects.
- Ergebnis: `RELATED_ONLY`
- Begründung: `thematisch verwandt, aber kein Beleg`
- `supports_claim: false`

Das ist wichtig, weil semantische Ähnlichkeit allein andernfalls sehr leicht als „Evidence“ missverstanden wird.

### Numerische Aussagen werden nicht automatisch durchgewunken

Mehrere Aussagen zum vermeintlichen 90-Tage-Konsens wurden im Evidence-Export mit `INSUFFICIENT` bewertet und aus dem Fließtext entfernt, weil die konkrete Zahl beziehungsweise Bezugsgruppe nicht ausreichend belegt war.

Dazu gehört beispielsweise die Behauptung, *alle acht* befragten Agenten hätten ausnahmslos mindestens 90 Tage gefordert. Dass eine Aussage plausibel zum Gesamtnarrativ passt, reicht für die numerische Behauptung nicht aus.

### Reviewer-Floor

Mehrere Aussagen wurden als Hypothesen geführt, weil nur eine der zwei geforderten stützenden Evidence-Quellen vorlag. Das betrifft unter anderem Aussagen zur Professionalitätswirkung der neuen Domain.

### Confidence-Degradation

Der Export enthält sechs Einträge im `degradation_log`, bei denen ein ursprünglich zu hoch angesetztes `medium`-Label auf `low` heruntergestuft wurde. Der Validator begründet das damit, dass die für `agent_grounded` benötigte Kombination aus Agent-Zitat und Seed-Corpus-Evidence nicht vorhanden war.

Diese Fälle sind im [`evidence-extract.json`](./artifacts/evidence-extract.json) reproduzierbar dokumentiert.

## Was in diesem Lauf funktioniert hat

Auf Basis der vorhandenen Artefakte lässt sich für diesen konkreten Run belegen:

- die Pipeline lief von Szenario/Knowledge-Graph-Kontext bis zum strukturierten Report,
- Agenten führten Social-Actions in Reddit-/Twitter-artigen Umgebungen aus,
- Interaktions- und Graphmetriken wurden erzeugt,
- mehrere Cluster und Bridge Agents wurden berechnet,
- der Report strukturierte Stakeholder-Konflikte, Risiken, Hypothesen und Data Gaps,
- thematisch verwandte, aber nicht tragende Evidence konnte als `RELATED_ONLY` abgelehnt werden,
- unzureichend belegte numerische Aussagen konnten als `INSUFFICIENT` aus dem Fließtext entfernt werden,
- Reviewer-Floor-Regeln verschoben schwach belegte Aussagen in Hypothesen,
- Confidence konnte validatorseitig heruntergestuft werden,
- Markdown-, HTML-, PDF- und Evidence-JSON-Exporte wurden für denselben Report erzeugt.

Das ist der eigentliche Nachweis dieses Referenzlaufs: **Agora hat eine nicht-triviale Analyse-Pipeline end-to-end ausgeführt und dabei seine Evidenzgrenzen zumindest teilweise maschinenlesbar sichtbar gemacht.**

## Was nicht funktioniert hat oder unklar blieb

Ein Referenzlauf, der nur Erfolge dokumentiert, wäre Werbung. Deshalb gehören die Schwächen in denselben Bericht.

### 1. Population Accounting ist nicht eindeutig

Die vom Betreiber angegebene Population von 33 erzeugten Agenten und `total_agents: 24` im Metrics-Snapshot sind nicht sauber miteinander erklärbar. Das sollte künftig im RunManifest beziehungsweise in Simulationsmetriken eindeutig getrennt werden, etwa in `generated`, `activated`, `participating` und `observed_in_snapshot`.

### 2. Der finale Report zeigt die Social-Simulation nur teilweise

Im Evidence-Export sind Social-Actions, Cluster, Bridge Agents und ein Echo-Chamber-Index vorhanden. Der finale Markdown-/PDF-Report wirkt dagegen stellenweise wie eine Folge vertiefender Persona-Interviews. Dadurch wird ausgerechnet der soziale Teil der Multi-Agenten-Simulation schwächer sichtbar als er in den Rohdaten vorhanden ist.

### 3. „Konsens“ wird stellenweise zu stark formuliert

Der Report verwendet Formulierungen wie „Konsens“ oder „alle acht“, während das Evidence-Gating einzelne dazugehörige numerische Aussagen später als `INSUFFICIENT` einstuft. Das ist kein Grund, den Validator zu lockern. Die Synthese sollte vorsichtiger formulieren, zum Beispiel `starke Konvergenz` oder `häufiges Muster`, solange die konkrete Bezugsgruppe nicht belegt ist.

### 4. Graphmetriken werden noch zu wenig in die Interpretation eingebaut

Drei Cluster, Bridge Agents und ein Echo-Chamber-Index von `0.4794` sind vorhanden. Der Report erklärt aber nicht ausreichend, **welche Narrative in welchem Cluster entstanden**, welche Agenten Argumente zwischen Gruppen transportierten oder wie robust eine Konvergenz über Clustergrenzen hinweg war.

Gerade hier liegt Potenzial, Agora klar von einem gewöhnlichen LLM-Stakeholderbericht zu unterscheiden.

### 5. Historische Evidence-Identität war nicht kanonisch genug

Der parallel geführte Audit-/Remediation-Prozess bestätigte für den damaligen Stand ein strukturelles Problem: Evidence-Referenzen konnten auf freie Quellenstrings wie `report_tool` zurückfallen und dadurch keine eindeutig auflösbare Evidence-Identität darstellen.

Das ist relevant für diesen historischen Lauf, weil der Evidence-Export genau aus dieser Generation stammt.

### 6. Niedrige belastbare Claim-Ausbeute ist sichtbar

Viele inhaltlich sinnvolle Aussagen landen als Hypothesen oder Data Gaps, weil `no_evidence_bound`, `RELATED_ONLY` oder Reviewer-Floor-Regeln greifen. Das ist sicherer als falsche Sicherheit, zeigt aber zugleich, dass Retrieval, Provenance-Bindung und Claim-Funnel weiter kalibriert werden müssen.

### 7. Der historische Lauf ist noch kein reproduzierbarer Benchmark

Es existieren IDs und Exportartefakte, aber für diesen historischen Run noch kein vollständiger, versionierter RunManifest-/Replay-Vertrag mit allen Input-Hashes, Modell-/Provider-Routen, Prompt-/Schema-Versionen, Seeds und Feature-Flags.

Der Lauf wird deshalb als **frozen historical reference run** dokumentiert und nicht nachträglich zum reproduzierbaren Benchmark umetikettiert.

## Laufbeobachtung, Audit-Finding und Remediation sauber getrennt

| Ebene | Befund | Status |
|---|---|---|
| Laufbeobachtung | Social-Actions, 267 Interaktionen, 3 Cluster, Evidence-Gating und Report wurden erzeugt | artefaktbelegt |
| Laufbeobachtung | 33 erzeugte Agenten laut Betreiberangabe vs. `total_agents: 24` im Metrics-Snapshot | ungeklärt |
| Laufbeobachtung | Report nutzt teils stärkere Konsenssprache als einzelne Evidence-Urteile tragen | sichtbar im historischen Export |
| Audit/Analyse | freie/duplizierbare Evidence-Referenzen konnten auf `report_tool` zurückfallen | bestätigt |
| Remediation | kanonische deterministische `evidence_id`, Evidence-Index und Cross-Reference-Validierung | in [PR #1147](https://github.com/arn0ld87/agora/pull/1147) gemergt |
| Folgearbeit | serverseitig verifizierte Seed-Chunk-Provenance | weiterhin separate Arbeit, u. a. #1086 |
| Folgearbeit | Claim-Funnel/Kalibrierung | separate Arbeit, u. a. #765 |
| Folgearbeit | RunManifest/Replay/Reproduzierbarkeit | Release-Arbeit Richtung `0.10.0`, u. a. #763 |

PR #1147 behebt **nicht** rückwirkend alle Schwächen dieses historischen Reports. Genau deshalb bleibt der alte Lauf als historisches Artefakt interessant: Er zeigt sowohl vorhandene Schutzmechanismen als auch die damaligen Grenzen.

## Was dieser Lauf demonstriert

Dieser konkrete Lauf unterstützt folgende Aussagen:

1. Agora kann einen Dokument-/Entscheidungsfall durch seine Kernpipeline verarbeiten.
2. Agenten können in einer Social-Simulationsumgebung miteinander interagieren.
3. Agora kann aus dem Interaktionsgraphen Metriken wie Cluster, Bridge Agents und Echo-Chamber-Index erzeugen.
4. Report-Synthese kann Risiken, Konfliktlinien, Hypothesen und fehlende Informationen strukturieren.
5. Evidence-Gating kann semantisch verwandte, aber nicht tragende Quellen erkennen.
6. Unzureichend belegte numerische Aussagen können aus dem validierten Fließtext herausfallen.
7. Confidence-Verstöße können maschinenlesbar degradiert werden.
8. Ein realer End-to-End-Lauf kann Produktmängel aufdecken, die anschließend in konkrete Remediation münden.

## Was dieser Lauf ausdrücklich nicht demonstriert

Aus diesem Referenzlauf darf **nicht** abgeleitet werden:

- dass Agora reale Menschen zuverlässig vorhersagt,
- dass die Agentenpopulation repräsentativ für Recruiter, Entwickler oder Websitebesucher ist,
- dass `alex-schneider.dev` real bessere Jobchancen erzeugt,
- dass Recruiter `.dev` tatsächlich bevorzugen,
- dass die Domainmigration reale SEO-Verluste von bestimmter Höhe verursacht,
- dass der Echo-Chamber-Index extern validiert oder allgemein interpretierbar ist,
- dass jeder Agora-Lauf dieselbe Qualität erreicht,
- dass dieser historische Lauf vollständig reproduzierbar ist,
- dass mehrere übereinstimmende Agenten eine empirische Mehrheitsmeinung darstellen.

## Reproduzierbarkeitsstatus

**Status: historischer Referenzlauf, nicht vollständiger Replay-Benchmark.**

Vorhanden sind:

- Report-ID und Simulation-ID,
- Report in mehreren Exportformaten,
- Evidence-Export,
- Graph-/Interaktionsmetriken,
- Social-Action-Samples,
- maschinenlesbare Hypothesen, Data Gaps und Degradation-Einträge,
- SHA-256-Prüfsummen der für diese Auswertung verwendeten Originalexporte.

Für einen echten Replay-Benchmark fehlen beim historischen Lauf noch Teile des geplanten RunManifest-Vertrags. Ein späterer vollständig manifestierter Replay-Run sollte als **neuer** Referenzlauf dokumentiert werden, statt die Historie dieses Laufs zu überschreiben.

## Artefakte

- [`artifacts/evidence-extract.json`](./artifacts/evidence-extract.json) — deterministischer öffentlicher Extract der in dieser Case Study ausgewerteten Evidence-Felder.
- [`artifacts/README.md`](./artifacts/README.md) — Provenienz, Originalgrößen und SHA-256-Prüfsummen der vollständigen Markdown-, JSON-, HTML- und PDF-Exporte.

Der vollständige historische Evidence-Export umfasste 419.716 Byte und 5.809 Zeilen. Er wird hier nicht als zweite Dokumentations-SSoT eingecheckt; der öffentliche Extract macht stattdessen die für diese Case Study herangezogenen Felder reviewbar und bindet sie per SHA-256 an den ursprünglichen Export.

## Schlussfolgerung

Dieser Run ist kein Beweis, dass eine Gruppe künstlicher Agenten die Realität korrekt nachspielt. Er ist ein **technischer Referenznachweis dafür, dass Agora bereits mehr tut als einen Prompt in einen langen Bericht zu verwandeln**:

- soziale Agenteninteraktionen werden erzeugt,
- daraus entstehen messbare Graphstrukturen,
- die Report-Synthese versucht daraus eine Entscheidungsvorlage abzuleiten,
- ein separater Evidence-Layer kann Teile dieser Synthese zurückweisen oder herabstufen,
- und die dabei sichtbaren Schwächen lassen sich in konkrete technische Remediation überführen.

Die verbleibenden Lücken sind Teil dieses Referenzlaufs, nicht Fußnoten, die für eine hübschere Demo verschwinden sollen.
