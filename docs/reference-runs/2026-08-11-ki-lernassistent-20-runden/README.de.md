# Referenzlauf 4: KI-Lernassistent, 20 Runden, Gemini 3.6 Flash

*Deutsch · [English](./README.md)*

> [!IMPORTANT]
> Dieser Lauf dokumentiert Agoras Verhalten in einer simulierten Multi-Agenten-Umgebung. Er ist **kein** Nachweis dafür, dass die simulierten Personas reale Menschen repräsentieren oder reales menschliches Verhalten vorhersagen.

## Warum dieser Lauf der aktuelle Referenzlauf ist

Er ist der erste, in dem die Evidence-Bindung tatsächlich arbeitet. Fünf vorangegangene Reports über vier Modellkonfigurationen banden **null oder einen** Claim; dieser bindet **39**. Damit wird zum ersten Mal messbar, wo die Grenze wirklich liegt — und sie liegt woanders, als die Vorgängerläufe nahelegten.

Gleichzeitig ist er der Lauf mit der besten Textqualität und der schlechtesten Belegqualität. Beides gehört zusammen: Ein stärkeres Schreibmodell formuliert überzeugender **und** erfindet überzeugendere Herkunftsangaben, solange nichts sie prüft.

Er ersetzt die früheren Referenzläufe nicht. Der [dritte Lauf](../2026-08-11-ki-lernassistent/README.md) beschreibt Mechanismen, die hier vorausgesetzt werden.

## Run-Identität

| Feld | Wert |
|---|---|
| Report-ID | `report_4786a1a3d4ea` |
| Simulation-ID | `sim_eb9037a01fb4` |
| Graph-ID | `951b6064-ad30-4b9d-a8e9-0b4790369817` |
| Report-Modell | `models/gemini-3.6-flash` |
| NER-/Ontologie-Modell | `models/gemini-3.6-flash` |
| Persona-Modell | `deepseek-v4-flash:0731` |
| Embedding | `gemini-embedding-2`, 3072 dim, OpenAI-kompatibler Pfad |
| Report-Intent | `opinion`, 6 Sections |
| Runden | **20 / 20** (`max_rounds=20`) |

## Simulation Snapshot

| Metrik | Wert |
|---|---:|
| konfigurierte Persona-Profile | **50** |
| Agenten im Metrics-Snapshot | **42** |
| Entitäten gematcht | 47 |
| Aktionen Twitter / Reddit | 291 / 374 |
| Kommentare (Reddit) | 84 |
| Cluster | 6 |
| Clustergrößen | 10 / 10 / 8 / 5 / 5 / 4 |
| Echo-Chamber-Index | 0.5741 |
| Bridge Agents | 20, 12, 27, 7, 37 |

> [!WARNING]
> Die Population-Accounting-Diskrepanz besteht fort: 50 konfigurierte Profile gegen 42 Agenten im Snapshot. Im dritten Referenzlauf waren es 50 gegen 38.

## Was in diesem Lauf funktioniert

### Die Poster-Zuordnung trifft vollständig

Erstmals landen alle Initial-Posts bei der fachlich richtigen Persona — 8 von 8, null `No matching agent`-Warnungen:

```
ExecutiveManager    → Geschäftsführung
WorksCouncilMember  → Betriebsrat
PermanentLecturer   → Dozenten
FreelanceLecturer   → Honorarkräfte
RetrainingStudent   → Umschüler
ExamBoardMember     → IHK
FundingAgency       → Agentur für Arbeit
HiringCompany       → Regionale Betriebe
```

Der Grund ist strukturell: Bei domänenspezifischer Typisierung gilt **Typ ≈ Rolle**, jeder Typ hat wenige Entitäten, der Direct-Match trifft zwangsläufig. Zum Vergleich der Lauf `sim_76ef482a13e4` mit generischem Vokabular (`Organization`, `Student`, `Professor`): Dort landete einer von neun Seed-Posts bei `Agora` selbst, weil `Organization` ein Topf mit 22 Einträgen war und der Match Index 0 nimmt.

### Die Evidence-Bindung arbeitet

| | dieser Lauf | fünf Vorgänger |
|---|---:|---:|
| validierte Claims | **39** | 0 – 1 |
| Hypothesen | 141 | 129 – 157 |
| data_gaps | 131 | 41 – 111 |
| `evidence_index` | 76 | 38 – 85 |

Evidence-Zusammensetzung: 33 `agent_interview`, 17 `seed_document`, 14 `relationship_chain`, 8 `agent_action`, 4 `graph_metric`.

Gate-Entscheidungen: `no_supporting_evidence` 131, `prose_fact_unsupported` 13.

### Der Prosa-Gate skaliert korrekt

Entfernte Faktenaussagen pro Section: **1, 7, 2, 3, 1** (Section 3 ohne Meldung). Im dritten Referenzlauf war es sechsmal in Folge exakt eine — das war eine Eigenschaft des Schreibmodells, nicht des Gates. `gemini-3.6-flash` schreibt zahlendichter, also findet der Filter mehr Kandidaten.

### Der Bericht formuliert beobachtbar statt thematisch

Der Kipppunkt ist erstmals als konkretes Ereignis benannt statt als Thema:

> Die Akzeptanz kippt nicht an einer technischen Hürde, sondern genau in dem Moment, in dem eine Honorarkraft eine vom KI-System erzeugte Übungsaufgabe vor der Klasse als fachlich falsch abtut. Wenn der Dozent den Teilnehmenden explizit rät: „Vergesst, was der Assistent euch ausgibt, lernt lieber nach meinen Folien“, verlieren die Umschüler augenblicklich das Vertrauen.

Dazu eine Kausalkette, die kein früherer Lauf gefunden hat: Das System fängt Einstiegs- und Routinefragen ab → im Präsenzunterricht verbleiben nur verdichtete Problemfälle → unkompensierte Arbeitsverdichtung.

## Kritischer Befund 1: Die Provenance-Anker sind erfunden

Erstmals trägt jedes Zitat einen **eigenen** Anker statt eines gemeinsamen:

```
seed_doc:interview_ana_hodzic
seed_doc:interview_ali_demir
seed_doc:interview_katharina_weber
seed_doc:interview_clara_meyer
seed_doc:interview_luca_greco
```

**Keiner davon kommt in irgendeinem `tool_result` vor.** Im Graphen existiert genau eine Entität mit „interview“ im Namen: `Stakeholder-Interviews`. Das Modell konstruiert die Anker nach dem Schema `interview_<personenname>`, und nichts prüft sie, weil der `seed_doc:`-Präfix die Bindungsprüfung in `backend/app/services/report_agent/evidence.py` vollständig umgeht.

Das ist eine **Verschärfung** gegenüber den Vorgängern, keine Verbesserung. Dort trugen alle Zitate denselben Wert — offensichtlich falsch und sofort erkennbar. Hier sieht jedes Zitat einzeln belegt aus und verweist auf Dokumente, die es nicht gibt. Für einen Leser ist die zweite Variante gefährlicher.

## Kritischer Befund 2: Der Entailment-Judge urteilt inkonsistent

Derselbe Sachverhalt wird im selben Report gegenläufig beurteilt.

**In Section 1** bindet `claim_10` eine Paraphrase korrekt:

```
CLAIM   : … die 31 auf der Personalliste geführten Honorarkräfte
EVIDENCE: 31 Honorarkräfte stehen auf der Personalliste des Trägers.
URTEIL  : SUPPORTED  ("qualitative Aussage deckt sich weitgehend mit der Evidence")
```

**In Section 2** entfernt der Prosa-Gate denselben Fakt als ungedeckt:

```
"31 Honorarkr…"      vorher 1 → nachher 0   ENTFERNT
"2023"               vorher 1 → nachher 0   ENTFERNT
"22 festangestellte" vorher 1 → nachher 1   behalten
```

Beide entfernten Aussagen sind im Evidence-Pool desselben Reports wörtlich vorhanden. Der strukturgleiche Satz mit „22 festangestellte Dozenten“ überlebt.

Der Judge kann Paraphrase also — er tut es nur nicht zuverlässig. Das ist eine andere Diagnose als „er hängt an Oberflächenähnlichkeit“ und verschiebt die Suche auf Konsistenz und Schwellenwerte.

## Kritischer Befund 3: Alle 39 Claims stehen auf `low`

```
confidence-Labels : {'low': 39}
confidence-Scores : [0.59]
```

Kein einziger Claim erreicht `medium` oder `high`, und alle 39 tragen denselben Score. Ein Konfidenzmaß, das über 39 Fälle exakt einen Wert annimmt, misst nichts.

Zudem sind **22 der 39 reine `<simulated_quote>`-Tags** — Bindungen eines Zitats an das Interview, aus dem es stammt, also Selbstbezug. Bleiben **17 echte Prosa-Claims** bei 141 Hypothesen: rund 11 %.

## Kritischer Befund 4: Der Datenlücken-Abschnitt kennt die eigenen Lücken nicht

Section 6 behandelt ausführlich die Datenlücken **des Bildungsträgers** — fehlende Pilotdaten, unbelegte Nutzenbehauptungen, unklare Validität der Lernstandserfassung. Sie erwähnt „Hypothesen“ zweimal, beide Male im Sinne von „optimistische Hypothesen der Führungsebene“.

Über die **141 Hypothesen und 131 Datenlücken des Berichts selbst** steht kein Wort. Das ist derselbe blinde Fleck wie im dritten Referenzlauf, hier bei achtmal so vielen gebundenen Claims.

## Weitere Befunde

### `status: incomplete` bei `missing_sections: []`

Die `meta.json` meldet `status: incomplete`, obwohl alle sechs Sections erzeugt und gespeichert wurden und `missing_sections` leer ist. Der Zustand ist in sich widersprüchlich.

### Eine Worthalluzination in belegtem Kontext

Der Bericht schreibt „nach den Erfahrungen der **Zeiterforderung** aus dem Jahr 2023“. Das Wort existiert nicht. Die Evidence sagt korrekt „digitale **Zeiterfassung** im Jahr 2023“ — Jahreszahl und Sachverhalt sind richtig übernommen, das Substantiv ist verballhornt.

### Kein negatives Feedback, auch über 20 Runden

```
Twitter:  291 Aktionen   0 dislike   0 comment_dislike
Reddit:   374 Aktionen   0 dislike   0 comment_dislike
          74 like, 6 comment_like, 84 Kommentare, 0 Dissens-Marker
```

Dieser Lauf räumt die drei naheliegenden Gegenerklärungen ab: **20 statt 10 Runden**, **50 Agenten**, und `FreelanceLecturer` gegen `PermanentLecturer` erstmals als **getrennte, korrekt zugeordnete Sprecher** — also genau die beiden Gruppen, deren Gegensatz jeder Report als Kernkonflikt benennt. Es entsteht keine einzige ablehnende Handlung.

### Nicht-Stakeholder und Rollendubletten bestehen fort

44 distinkte Entity-Namen fallen auf 12 Typen. Die Verteilung zeigt beide Probleme:

```
RetrainingStudent (10):  Absolventen · Jüngere Teilnehmende · Teilnehmende mit Migrationsgeschichte · …
Organization (8):        Auswertungsfunktion · ChatGPT · IHK · KI-Lernassistent · Moodle · …
FundingAgency (6):       Agentur für Arbeit · Jobcenter · Kostenträger · kommunale Jobcenter
PermanentLecturer (5):   Dozenten · Festangestellte · Festangestellte Fachdozenten · Ältere Dozenten
```

Die Blockliste in `backend/app/services/persona_eligibility.py` hat in diesem Lauf einmal gegriffen (`Der Assistent`, Typ `Technology`). Sie kann `Organization` nicht aufnehmen, weil das ein legitimer Stakeholder-Typ ist — deshalb sitzen `ChatGPT`, `Moodle` und `Auswertungsfunktion` weiterhin als Personas im Lauf.

Bemerkenswert ist der Zielkonflikt: `gemini-3.6-flash` liefert mit `FreelanceLecturer`/`PermanentLecturer` die fachlich beste Typisierung aller Läufe und hat **gerade deshalb** den höchsten Fallback-Anteil (36 von 48, 75 %), weil keiner dieser Typen in der bekannten Liste steht. Gute Domänenmodellierung wird derzeit bestraft.

## Vergleich der vier Referenzläufe

| | Lauf 1 | Lauf 2 | Lauf 3 | **Lauf 4** |
|---|---|---|---|---|
| Domäne | Domainmigration | Domainmigration | Umschulung | Umschulung |
| Report-Modell | Gemini 3.6 Flash | — | deepseek-v4-flash | **gemini-3.6-flash** |
| Runden | — | — | 10 | **20** |
| Agenten konfig./Snapshot | 33 / 24 | 30 / 30 | 50 / 38 | **50 / 42** |
| validierte Claims | 17 unique | 0 | 1 | **39** (17 Prosa) |
| Hypothesen | 157 | — | 129 | 141 |
| Poster-Zuordnung | — | — | 10/10 (zufällig) | **8/8 (strukturell)** |
| Provenance-Anker | — | — | ein konstanter Wert | **pro Zitat erfunden** |

## Was dieser Lauf demonstriert

- Die Evidence-Bindung funktioniert grundsätzlich — die Vorgängerläufe maßen nicht eine kaputte Bindung, sondern ein zu schwaches Report-Modell.
- Domänenspezifische Typisierung macht die Poster-Zuordnung strukturell korrekt statt zufällig.
- Der Prosa-Gate skaliert mit dem Anteil quantitativer Aussagen.
- Zwanzig Runden mit korrekt zugeordneten Konfliktparteien erzeugen dennoch kein negatives Feedback.

## Was dieser Lauf ausdrücklich nicht demonstriert

- **Keine belastbare Provenance.** Die Anker sind pro Zitat erfunden und werden nicht geprüft.
- **Kein funktionierendes Konfidenzmaß.** 39 Claims, ein einziger Score.
- **Keine Selbstauskunft über die eigene Belegbasis.** 141 Hypothesen erscheinen im Text nirgends.
- **Keine Validität der Auswertung**, solange der Testfall seine Antworten mitliefert (#1240).

## Remediation-Priorität

1. **`seed_doc:`-Bypass schließen** (#1226). Der Lauf zeigt, dass ein stärkeres Modell die Lücke systematischer ausnutzt als ein schwächeres.
2. **Entailment-Konsistenz** (#1209). Derselbe Fakt darf nicht in Section 1 binden und in Section 2 entfernt werden.
3. **Konfidenz differenzieren.** Ein Score über alle Claims ist kein Maß.
4. **Prosa-Gate über Zahlen hinaus** (#1209). Qualitative Behauptungen bleiben ungeprüft.
5. **Persona-Eignung typunabhängig prüfen** (#1226). Die Blockliste ist korrekt, wird aber über `Organization` umgangen.
6. **Bekannte Typ-Liste um Domänentypen erweitern**, statt die NER zu generischen zu drängen.
7. **Population-Accounting** und `status: incomplete` bei leerem `missing_sections` bereinigen.

## Artefakte

- Simulation: `backend/uploads/simulations/sim_eb9037a01fb4/`
- Report: `backend/uploads/reports/report_4786a1a3d4ea/`
- Maschinenlesbare Zusammenfassung: [`artifacts/run-summary.json`](./artifacts/run-summary.json)

## Fazit

Dieser Lauf trennt zwei Qualitäten, die in allen Vorgängern zusammenfielen. Die **Textqualität** steigt mit dem Modell sichtbar: schärfere Kipppunkte, echte Kausalketten, saubere Beantwortung der gestellten Fragen. Die **Belegqualität** sinkt im selben Zug: erfundene Anker pro Zitat, ein Konfidenzwert für alles, ein Judge, der denselben Fakt zweimal gegenläufig beurteilt.

Für eine Plattform, die belegte Aussagen von Vermutungen trennbar machen soll, ist das die unbequemere Erkenntnis: Ein besseres Sprachmodell verbessert den Bericht und verschlechtert seine Überprüfbarkeit, solange die Prüfschicht Lücken lässt, die es ausfüllen kann.
