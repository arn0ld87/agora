# Referenzlauf 3: KI-Lernassistent bei einem AZAV-Umschulungsträger

> [!IMPORTANT]
> Dieser Lauf dokumentiert Agoras Verhalten in einer simulierten Multi-Agenten-Umgebung. Er ist **kein** Nachweis dafür, dass die simulierten Personas reale Menschen repräsentieren oder reales menschliches Verhalten vorhersagen.

## Warum dieser dritte Lauf dokumentiert wird

Die ersten beiden Referenzläufe untersuchten dieselbe Domainmigration und maßen vor allem die Evidence-Identität. Dieser Lauf wechselt bewusst die Domäne — Einführung eines selbstgehosteten KI-Lernassistenten bei einem AZAV-zertifizierten Umschulungsträger in Sachsen-Anhalt — und dokumentiert drei Dinge, die in den Vorgängern nicht sichtbar waren:

1. **Der Testfall enthält seine eigenen Antworten.** Das Seed-Dokument mischt Szenario, Konstruktionsnotizen und erwartete Ergebnisse. Der Report ruft diese Sätze als Evidence ab und präsentiert sie als Simulationsergebnis. Das ist der schwerwiegendste Befund dieses Laufs und betrifft die Validität der Auswertung insgesamt.
2. **Genau ein Claim bindet — und nur durch Selbstzitat.** Nach fünf Reports mit null validierten Claims bindet dieser einen. Die Untersuchung, warum ausgerechnet dieser, legt den Mechanismus hinter dem Bindungsproblem offen.
3. **Das Evidence-Gate beschädigt beim Entfernen die Textstruktur.** In zwei von sechs Sections bleibt eine Aufzählung ohne ihren Punkt oder ein Rückverweis ohne Bezug zurück.

Zusätzlich ist dies der erste dokumentierte Lauf mit **Gemini-Embedding** statt lokalem Ollama.

## Run-Identität

| Feld | Wert |
|---|---|
| Report-ID | `report_40236c4a59f0` |
| Simulation-ID | `sim_8495a5fe314b` |
| Graph-ID | `b677b8f9-0530-4fb8-a310-3295fbc5e50a` |
| Projekt-ID | `proj_e8adf5f5984b` |
| Report-Modell | `deepseek-v4-flash:0731` (ollama_cloud) |
| NER-/Persona-Modell | `deepseek-v4-flash:0731` |
| Embedding | `gemini-embedding-2`, 3072 dim, OpenAI-kompatibler Endpunkt |
| Report-Intent | `opinion` |
| Sections | 6 (von 11 reduziert) |
| Status | `completed`, `missing_sections: []` |
| Laufzeit Report | 05:10:53 – 05:32:20 |

## Simulation Snapshot

| Metrik | Wert |
|---|---:|
| konfigurierte Persona-Profile | **50** |
| Agenten im Metrics-Snapshot | **38** |
| Entitäten im Graphen (gematcht) | 47 |
| Runden | 10 / 10 |
| Aktionen gesamt | **451** |
| Graph-Interaktionen | 286 |
| Cluster | 4 |
| Clustergrößen | 12 / 10 / 9 / 7 |
| Echo-Chamber-Index | 0.4685 |
| Bridge Agents | 14, 16, 11, 42, 21 |

> [!WARNING]
> **Die Population-Accounting-Diskrepanz ist zurück.** Der v2-Referenzlauf vermerkte sie als behoben (30 konfiguriert, 30 im Snapshot). Hier stehen **50 konfigurierten Profilen 38 Agenten im Snapshot** gegenüber. Vermutlich zählt der Snapshot nur Agenten mit Interaktionen; die Kennzahl ist dann aber falsch benannt und im Report nicht als solche kenntlich.

Trace-Verteilung über beide Plattformen:

```
Twitter: like_post 43, create_post 33, refresh 27, quote_post 26, sign_up 50, follow 7, repost 2
Reddit : like_post 87, create_comment 77, refresh 50, sign_up 50, create_post 11, like_comment 2
```

## Was in diesem Lauf funktioniert

### Embedding-Umstellung auf Gemini

Der Graph-Build lief mit **null Embedding-Fehlern** durch. Der vorherige Pfad über Host-Ollama (`embeddinggemma:300m`, 768 dim, `host.docker.internal:11434`) lief wiederholt in Read-Timeouts; der Graph blieb dann ohne Vektoren und die semantische Suche fand nichts — ein stiller Qualitätsverlust, der den Lauf nicht abbrach.

Genutzt wird der **OpenAI-kompatible** Gemini-Endpunkt (`…/v1beta/openai` + `/embeddings`), nicht der native `:embedContent`-Pfad. Der native Weg funktioniert hier nicht: `embedding_migrations.py` lehnt `provider_kind: "google"` beim Re-Embedding ausdrücklich ab.

### Persona-Diversität hält auch bei 50 Agenten

| Kennzahl | Wert |
|---|---:|
| Namen unique | **50 / 50** |
| häufigster Nachname | 1× |
| häufigster MBTI-Typ | 12 % |
| häufigster Alterswert | 4 % |
| Name-/Gender-Inkonsistenzen | 0 |

Die Rohausgabe des Generierungslogs zeigt noch den bekannten Modus-Kollaps (6× „Sabine“, 4× „Lena“, ~12× „Weber“, eine Persona mit weiblichem Namen und `gender=male`). Der Dedup-Schritt repariert das vollständig. Für die Bewertung zählt die finale `reddit_profiles.json`, nicht das Log.

### Adaptive Reportplanung und Tool-Nutzung

Intent `opinion` erkannt, Outline von 11 auf 6 Abschnitte reduziert. Tool-Nutzung pro Section:

| Section | Calls | Tools |
|---|---:|---|
| Kurzfazit | 3 | `insight_forge`, `interview_agents`, `panorama_search` |
| Stakeholder- und Meinungsgruppen | 4 | + `quick_search` |
| Zentrale Zustimmungspunkte | 4 | + `quick_search` |
| Zentrale Kritikpunkte | 4 | + `quick_search` |
| Konfliktlinien | 4 | + `quick_search` |
| Unsicherheiten und Datenlücken | 3 | ohne `quick_search` |

Keine Section lief ins Iterationslimit.

### Inhaltliche Qualität

Der Bericht befolgt die Vorgaben aus dem Requirement nachweisbar: Er behandelt die Geschäftsführungsaussagen durchgehend als unbelegte Behauptung, benennt ausbleibende erwartete Effekte statt sie zu relativieren, und liefert kein ausgewogenes Bild, sondern eine Zuspitzung.

Der Abschnitt „Unsicherheiten und Datenlücken“ ist inhaltlich der stärkste: Er benennt vier konkrete Lücken des Vorhabens und arbeitet heraus, dass alle befragten Gruppen unabhängig voneinander dieselbe Schließung fordern — eine Pilotphase, die nicht eingeplant ist.

## Kritischer Befund 1: Der Testfall enthält seine eigenen Antworten

Das Seed-Dokument enthält neben dem Szenario auch **Konstruktionsnotizen und erwartete Ergebnisse**. Die NER zieht sie als Fakten in den Graphen, `insight_forge` und `panorama_search` liefern sie als Evidence, und der Report präsentiert sie als Simulationsergebnis.

Belegte Beispiele, jeweils im Report als Befund vorgetragen:

| Im Report als Ergebnis präsentiert | Tatsächliche Herkunft |
|---|---|
| „Der Fall ist so gebaut, dass Honorarkräfte und Geschäftsführung nicht auf einen Nenner kommen können.“ | Graph-Fakt aus dem Seed-Dokument |
| „Die IHK sieht generierte Übungsaufgaben unkritisch.“ | Graph-Fakt aus dem Seed-Dokument |
| „Der Kostenträger ist gleichgültig, solange der Unterrichtsumfang formal unverändert bleibt.“ | Graph-Fakt aus dem Seed-Dokument |
| „Der Betriebsrat blockiert nicht die Einführung, sondern die Auswertungsfunktion.“ | Graph-Fakt aus dem Seed-Dokument |
| „Honorarkräfte lehnen stärker ab als Festangestellte, weil sie keinen Anteil an der Entlastung haben.“ | Graph-Fakt aus dem Seed-Dokument |

Der Report leitet daraus seine Höhepunkte ab. Die IHK wird „die **überraschendste** Gruppe“ genannt, der Kostenträger „ein **erwarteter Effekt, der nicht eintritt**“ — beide auf Basis von Sätzen, die wörtlich im Eingabedokument stehen.

Das erklärt auch, warum die Reports über verschiedene Modelle hinweg dieselben Kernaussagen liefern: Sie lesen denselben Lösungsschlüssel.

**Für die Kernaussagen dieses Berichts wird die Simulation nicht gebraucht.**

Zwei Ursachen greifen ineinander:

1. **Testfall-Hygiene.** Ein Evaluationsdokument darf keine Meta-Kommentare über seine eigene Konstruktion und keine erwarteten Ergebnisse enthalten, wenn dasselbe Dokument als Wissensquelle ingested wird.
2. **Evidence-Typisierung.** Die Evidence-Schicht unterscheidet nicht zwischen einer Aussage *über die Domäne* und einer Aussage *über das Szenario*. Beide landen als `seed_document` im Index.

## Kritischer Befund 2: Genau ein Claim bindet — durch Selbstzitat

| | |
|---|---:|
| validierte Claims | **1** |
| Hypothesen | 129 |
| data_gaps | 111 |
| `evidence_index` | 85 |
| `degradation_log` | 0 |

Evidence-Zusammensetzung: 40 `agent_interview`, 22 `seed_document`, 11 `relationship_chain`, 8 `agent_action`, 4 `graph_metric`.

Gate-Entscheidungen: `no_supporting_evidence` 111, `reviewer_floor_insufficient_evidence` 12, `prose_fact_unsupported` 6, `medium_without_agent_grounded_evidence` 1.

Damit ist das erste Akzeptanzkriterium aus [#1209](https://github.com/arn0ld87/agora/issues/1209) — „mindestens ein Claim mit gebundener Evidence“ — knapp erfüllt. Interessanter ist, **warum ausgerechnet dieser** bindet.

`claim_20`, Section „Konfliktlinien“, `confidence_label: low`, `confidence_score: 0.71`, drei Evidence-Items mit `entailment: SUPPORTED`. Die Begründung lautet bei allen dreien identisch:

```
"entailment_reason": "qualitative Aussage deckt sich weitgehend mit der Evidence"
```

Der Claim-Text enthält seine Evidence als wörtliches Zitat:

> **Ein erwarteter Konflikt tritt in der Simulation nicht auf.** Trotz der institutionellen Spannung zwischen Betriebsrat und Geschäftsführung hält die Simulation fest: „Der Betriebsrat wird zustimmen, weil keine Dozentendaten erhoben werden.“ Diese Aussage steht in direktem Widerspruch zur Blockade der Auswertungsfunktion — ein Widerspruch, den die Simulation nicht auflöst, sondern nebeneinander stehen lässt.

Die Entailment-Prüfung vergleicht damit einen Satz mit sich selbst. **Der einzige Claim, der bindet, ist der, der seine eigene Evidence zitiert.**

Daraus folgt eine prüfbare Hypothese zur Ursache des Bindungsproblems: Der Judge vergibt SUPPORTED nur bei Nahezu-Wortgleichheit gegen ein **einzelnes** Evidence-Item. Jede Aussage, die über **mehrere** Items synthetisiert — also genau das, was ein Analysebericht leisten soll — kann per Konstruktion an keinem Einzelitem hängen.

Das Retrieval funktioniert dabei nachweislich (`match_score` 0.71–0.77). Der Engpass liegt in der Entailment-Stufe, nicht im Abruf.

> [!NOTE]
> Dieser Lauf schließt zwei bisher plausible Miterklärungen aus: Er lief mit **fehlerfreiem Embedding** und vollständig bestücktem 3072-dim-Vektorindex, und mit **50 statt 30 Agenten**. Beides ändert nichts.

## Kritischer Befund 3: Das Gate prüft nur Sätze mit Zahlen

In allen sechs Sections wurde **exakt eine** Faktenaussage aus dem Fließtext entfernt. Nie null, nie zwei. Die Ursache steht in `backend/app/services/report_agent/text_verification.py`:

```python
def _has_factual_claim(sentence: str) -> bool:
    """Nur Sätze mit einer Zahl samt Bezugsgruppe sind prüfbare Faktenaussagen."""
    return bool(extract_numeric_facts(sentence))
```

Der Fließtext-Gate prüft ausschließlich Sätze mit einer Zahl. Alles Qualitative läuft ungeprüft durch. Pro Section enthält der Text typischerweise genau einen quantitativen Satz — daher sechsmal in Folge exakt eine Entfernung.

Damit ist die Divergenz zwischen Text und Belegschicht mechanisch erklärt: **129 Aussagen sind in der Maschinenschicht zu Hypothesen degradiert, sichtbar entfernt wurden sechs Sätze.** Sätze wie „Die Simulation zeigt ein klares Ergebnis“ oder „Der Kipppunkt liegt bei den festangestellten Dozenten“ enthalten keine Zahl, werden nicht geprüft und nicht gekennzeichnet.

Das ist die mechanische Ursache für das dritte, weiterhin unerfüllte Akzeptanzkriterium von #1209 Befund 6.

## Kritischer Befund 4: Die Exzision beschädigt die Textstruktur

Das Gate entfernt den beanstandeten Satz, führt aber die umgebende Struktur nicht mit. In zwei von sechs Sections ist der Schaden im ausgelieferten Text sichtbar.

**Section 1 „Kurzfazit“** — `section_content` im Log 4486 Bytes, `section_01.md` auf Platte 4379 Bytes:

> „**Zwei Dinge** müssen vor dem Kursstart entschieden sein … **Erstens** eine verbindliche Betriebsvereinbarung … Ohne **diese beiden** Vorentscheidungen kippt die Akzeptanz.“

Der zweite Punkt wurde entfernt. Die Ankündigung und der Rückverweis bleiben stehen.

**Section 6 „Unsicherheiten und Datenlücken“** — 218 Bytes entfernt, darunter diese Zwischenüberschrift:

> **Die zweite Datenlücke: Die 6–9 Stunden unbezahlter Nacharbeit sind eine interne Schätzung, keine Messung.**

Die Aufzählung im ausgelieferten Text lautet danach: `Die zentrale Datenlücke` → `Die dritte Datenlücke` → `Die vierte Datenlücke`. Zusätzlich verweist ein späterer Satz auf „**diese Zahl**“, deren Bezug in der entfernten Überschrift stand.

Das Muster ist systematisch: Der Gate entfernt den einzigen Satz mit einer Zahl, und Zahlen stehen bevorzugt in Überschriften und Aufzählungsköpfen — also genau dort, wo der umgebende Text sich darauf bezieht.

## Weitere Befunde

### Personas sprechen in fremden Rollen

Die Interviewfragen sind neutral formuliert („Welcher Moment lässt Sie am stärksten an der KI zweifeln?“). Die Personas präfixieren ihre Antworten dennoch mit einer Rolle, die nicht ihre ist, und der Report übernimmt die Zuschreibung:

| Persona | tatsächliche Identität | antwortet als | im Report geführt als |
|---|---|---|---|
| `kim_novak_rzmd_903` | Technikerin, Rechenzentrum Magdeburg | „Als Betriebsrat…“ | Position des Betriebsrats |
| `lisa_hofmann_989` | Geschäftsführerin | „Als Dozent…“ | Geschäftsführung über Dozenten |
| `sabine_krueger_ba_157` | Agentur für Arbeit | „Als Kostenträger…“ | „AZAV-Zulassungsteamleiterin“ |

Im Live-Feed zeigt sich dasselbe: `u/Jüngere Teilnehmende Anfang 20` schreibt „Ich habe Migrationshintergrund“, `u/Festangestellte Fachdozenten` schreibt „Ich bin kurz vor der Rente“.

### Nicht-Stakeholder als Personas und als Kronzeugen

Von den generierten Personas entfallen rund 13 auf Entitäten, die keine Stakeholder sind: `Moodle`, `GPU-Server`, `AZAV`, `Kursstart Februar 2027`, `Mitbestimmungsverfahren`, `Bildungsgutschein`, `Rechenzentrum`, `IT-Umschulungen`, `Agora`, `KI-Lernassistent`. Ein Datum, ein Verwaltungsverfahren, ein Zertifizierungsstandard und ein Stück Hardware nehmen als Personen an der Diskussion teil.

Im Feed ist das sichtbar: `u/Kursstart Februar 2027` schreibt „Ich erlebe es seit Jahrzehnten“. Im Report tritt `AZAV` als „AZAV-Zulassungsteamleiterin Sabine Krüger“ als bestätigende Quelle auf.

Gleichzeitig sind die verbleibenden Personas stark redundant: neunmal `Retrainee` in unterschiedlicher Benennung. Der Report verdichtet 50 Personas zu acht Meinungsgruppen und macht die Redundanz damit rückwirkend sichtbar.

### Kein negatives Feedback

Über 451 Aktionen und beide Plattformen: **0 Dislikes, 0 Comment-Dislikes**. In 77 Reddit-Kommentaren finden sich **0 Dissens-Marker** bei 15 Zustimmungsfloskeln. Das reproduziert #1209 Befund 4 zum dritten Mal, obwohl die dort adressierten Fixes im Image enthalten sind.

### Zitat-Kennzeichnung uneinheitlich

Die SIM-Kennzeichnung mit `persona_id` und `seed_anchor` ist in diesem Lauf vorhanden — im unmittelbar vorangegangenen Lauf mit demselben Modell fehlte sie vollständig. Innerhalb dieses Reports schwankt sie ebenfalls: In Section 6 tragen von rund zehn wörtlichen Zitaten nur zwei die Kennzeichnung.

Alle Anker lauten `seed_doc:simulation_requirement`. Der `seed_doc:`-Präfix umgeht die Bindungsprüfung in `evidence.py` vollständig — jeder Wert mit diesem Präfix gilt als gültig, ohne gegen vorhandene Dokumente aufgelöst zu werden.

## Vergleich mit den ersten beiden Referenzläufen

| | Lauf 1 | Lauf 2 | **Lauf 3** |
|---|---|---|---|
| Domäne | Domainmigration | Domainmigration | Umschulungsträger |
| Report-Modell | Gemini 3.6 Flash | — | deepseek-v4-flash |
| Embedding | Ollama 768 | Ollama 768 | **Gemini 3072** |
| Agenten konfiguriert / im Snapshot | 33 / 24 | 30 / 30 | **50 / 38** |
| validierte Claims | 17 unique | 0 | **1** |
| Hypothesen | 157 | — | 129 |
| data_gaps | 41 unique | — | 111 |

Die Population-Diskrepanz aus Lauf 1 ist in Lauf 3 zurück. Die Claim-Bindung ist gegenüber Lauf 2 minimal besser, aber die Untersuchung des einen Claims zeigt, dass es sich um einen Grenzfall handelt, nicht um funktionierende Bindung.

## Was dieser Lauf demonstriert

- Die Umstellung des Embeddings auf einen Cloud-Anbieter über den OpenAI-kompatiblen Pfad funktioniert und beseitigt eine reale Ausfallquelle.
- Die Persona-Diversität ist auf Attributebene gelöst und skaliert auf 50 Agenten.
- Die adaptive Reportplanung und die abschnittsspezifische Tool-Auswahl arbeiten stabil.
- Der Bericht befolgt inhaltliche Vorgaben aus dem Requirement nachweisbar, auch unbequeme.
- Das Evidence-Gate greift und degradiert 129 Aussagen — die Maschinerie ist nicht dekorativ.

## Was dieser Lauf ausdrücklich nicht demonstriert

- **Keine Validität der Auswertung.** Solange der Testfall seine Antworten mitliefert, ist nicht unterscheidbar, was die Simulation beigetragen hat.
- **Keine funktionierende Evidence-Bindung.** Ein Claim von 130 bindet, und nur durch Selbstzitat.
- **Keine Vorhersage realen Verhaltens.** Die Personas sprechen in fremden Rollen, Nicht-Stakeholder nehmen teil, und es fällt über 451 Aktionen kein einziges ablehnendes Signal.
- **Keine Vergleichbarkeit der Twitter-Seite zwischen Läufen.** Der Twitter-Recommender rankt über zufällig initialisierte Pooler-Gewichte ohne Seed (siehe [#1236](https://github.com/arn0ld87/agora/issues/1236)).

## Remediation-Priorität

1. **Testfall-Hygiene und Evidence-Typisierung.** Meta-Aussagen und erwartete Ergebnisse gehören nicht in ein Dokument, das als Wissensquelle dient — und die Evidence-Schicht sollte Aussagen über das Szenario von Aussagen über die Domäne trennen können.
2. **Entailment-Stufe.** Prüfen, ob der Judge Claims gegen einzelne Evidence-Items statt gegen Kombinationen bewertet. Regressionstest: ein Claim, der zwei Items korrekt zusammenfasst, ohne eines wörtlich zu enthalten.
3. **Prosa-Gate über Zahlen hinaus.** Qualitative Aussagen werden derzeit nicht geprüft und nicht gekennzeichnet.
4. **Strukturerhaltende Exzision.** Beim Entfernen eines Satzes müssen Aufzählungen und Rückverweise mitgeführt oder die Section neu gerendert werden.
5. **Persona-Eligibility.** Nicht-Stakeholder-Entitäten (Daten, Verfahren, Standards, Hardware) dürfen keine Personas werden; Rollendubletten sollten zusammengeführt werden.
6. **Population-Accounting.** `total_agents` im Metrics-Snapshot muss entweder die konfigurierten Agenten zählen oder korrekt benannt werden.

## Artefakte

- Simulation: `backend/uploads/simulations/sim_8495a5fe314b/` — `simulation_config.json`, `run_state.json`, `reddit_profiles.json`, `{twitter,reddit}_simulation.db`, `simulation.log`
- Report: `backend/uploads/reports/report_40236c4a59f0/` — `evidence_map.json`, `outline.json`, `section_01.md` … `section_06.md`, `agent_log.jsonl`, `console_log.txt`

## Fazit

Dieser Lauf ist der erste, in dem die Auswertungskette technisch weitgehend sauber durchläuft: fehlerfreies Embedding, stabile Persona-Diversität bei 50 Agenten, vollständige Sections, greifendes Gate. Genau deshalb wird sichtbar, was darunter liegt.

Der Bericht liest sich überzeugend und ist inhaltlich anschlussfähig. Seine Kernaussagen stammen aber überwiegend aus dem Eingabedokument, seine Belegschicht bindet eine von 130 Aussagen, und die Kennzeichnung dessen, was Hypothese ist, erreicht den gelesenen Text nur bei Sätzen mit Zahlen.

Für den Zweck der Plattform — belegte Aussagen von Vermutungen trennbar zu machen — ist das der entscheidende offene Punkt, und er liegt nicht in der Simulation, sondern zwischen Evidence-Erzeugung und Textproduktion.
