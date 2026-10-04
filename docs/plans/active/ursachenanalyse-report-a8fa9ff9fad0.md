# Agora: Ursachenanalyse und Abnahmeplan für `report_a8fa9ff9fad0`

Stand 2026-10-04. Nur lesende Analyse: kein Produktcode geändert, kein Deployment, keine neue Simulation, keine LLM-Aufrufe.

> **Historischer Stand.** Dieses Dokument beschreibt den Lauf `report_a8fa9ff9fad0` und den Code vom 04.10.2026. Ein Teil des Reparaturplans ist seitdem auf `main`; siehe Abschnitt „Stand der Umsetzung" direkt unter dieser Einleitung. Abschnitt 4 und Abschnitt 10 sind als damalige Planung zu lesen, nicht als offene Arbeit.

Dieses Dokument ist die Synthese einer Analyse, deren Detailbelege **nicht im Repository liegen**: vier Teilberichte (A Laufforensik, B Code-Ursachen, C Recherche, D Doku/Issues/Tooling), ein Manifest des eingefrorenen Laufs (91 Dateien) und Repro-Skripte. Sie entstanden in einer Arbeitssitzung außerhalb des Repos und wurden nicht eingecheckt. Verweise wie „Teil B", „Nr. in B" oder „Befehle stehen in Teil D" beziehen sich darauf und lassen sich aus dem Repository nicht nachvollziehen.

Aus dem Repository prüfbar sind die Fundstellen mit `Datei:Zeile` in Abschnitt 3 (gegen den Stand vom 04.10.2026) und die in „Stand der Umsetzung" genannten PRs mit ihren Regressionstests.

## Stand der Umsetzung (05.10.2026)

| AP | Stand | Beleg |
|---|---|---|
| 1 Segmentierung (U4) | umgesetzt | #1768: gemeinsamer Satzsplitter `backend/app/services/sentence_splitter.py::split_sentences`, genutzt von `claim_atomizer`, `evidence_entailment`, `evidence_binder` und `text_verification` |
| 2 Interviewtext (U1) | umgesetzt | #1768: eine Volltextprojektion `backend/app/services/evidence_text.py::evidence_text` für Binder, Entailment und Data-Gap |
| 3 Rate-Limit-Verlust (U2) | umgesetzt | #1767: Degradation für fehlgeschlagene Simulations-LLM-Aufrufe (`run_degradation.py::_simulation_llm_failure_degradations`); Limiter standardmäßig an, Meldung des Anbieters sichtbar (#1776) |
| 4 Confidence-Flächen (U5) | teilweise | #1770: Kernaussagen-Confidence gedeckelt, Konsens-Label erst ab zwei Stimmen |
| U9 Aktionen als Evidence | teilweise | #1780: Werkzeug `search_simulation_actions`, Treffer als zitierbare Belege |
| 5 bis 10 | nicht geprüft | Stand gegen `main` vor Arbeitsbeginn neu feststellen |

Offen ist der Wirknachweis: Der Bericht wurde seit diesen Reparaturen nicht aus der eingefrorenen Simulation neu erzeugt und gegen die Abnahmematrix (Abschnitt 5) gemessen.

**Wie belastbar sind die Aussagen hier?** Jede Ursache trägt einen Status:

- **bestätigt**: durch Repro mit eingefrorenen Artefakten oder durch Zählung am Artefakt belegt.
- **statisch**: im Quellcode nachgewiesen, im Lauf nicht direkt beobachtet.
- **plausibel**: Mechanismus passt, Beleg fehlt.

Die in Abschnitt 3 mit „(gegengeprüft)" markierten Fundstellen habe ich selbst am Quellcode nachgelesen. Der Rest stammt aus den Teilberichten und ist nicht ein zweites Mal geprüft.

---

## 1. Urteil

**Technischer Trust: nicht belastbar.** Der Bericht taugt nicht als Trust-Abnahme. Vier Gründe, jeder für sich ausreichend:

1. Der Binder sieht von jeder Interviewantwort nur die ersten rund 300 Zeichen. Aussagen dahinter sind strukturell nicht bindbar (bestätigt).
2. Kein Tabellenwert des Seeds erreicht den Graphen; 318, die Fahrzeiten und der März-Termin fehlen im Bericht vollständig (bestätigt für den Verlust, plausibel für die Ursache).
3. 68 % der LLM-Aufrufe der Simulation scheiterten an Rate Limits, ohne dass das als Degradation im Bericht steht (bestätigt).
4. Sieben `high`-Kernaussagen entstehen ohne Evidence-Referenz und laufen an den ADR-0002-Validatoren vorbei (statisch, im Artefakt beobachtet).

Positiv: Das System stuft den Bericht selbst als `incomplete` ein, mit sechs fehlenden Pflichtaspekten. Diese Degradation ist sichtbar und korrekt. Die fünf ADR-0002-Hartanker sind unverändert.

**Fachlicher Nutzen: teilweise.** Die Interviews liefern differenzierte synthetische Perspektiven, und der Einwand „Beschluss vor Landesentscheidung" ist in den Rohantworten nachvollziehbar. Für eine Entscheidungsvorlage fehlt die quantitative Grundlage. Außerdem ist das Perspektivenbild schief: 51 von 57 Interviewantworten sind ablehnend, die im Seed zustimmenden Akteure kommen je einmal vor. Das sind Aussagen über Modellantworten, keine Bestätigung realer Tatsachen.

**Modellfrage:** Ein Modellwechsel ist nicht angezeigt. Es gibt 0 Refusals, und die Hauptursachen sind deterministische Pipelinefehler (Abschnitt 7).

---

## 2. Laufsteckbrief

**Der Lauf liegt auf `armserver`, nicht auf `gns3`.** Auf gns3 existiert die ID weder auf der Platte noch in den Logs. Der Snapshot stammt deshalb von armserver. Beide Hosts fahren dasselbe Image.

| Ebene | ID / Wert |
|---|---|
| Bericht | `report_a8fa9ff9fad0`, Status `incomplete`, Modus `balanced` |
| Bericht-Job | `run_10989a2d3be6` (00:44:25 bis 00:54:50 CEST), Run-Status `completed` |
| Simulation | `sim_cc6067a70603`, 24/24 Runden, 736 Aktionen |
| Prepare-Job | `run_53a5ea76ef21`, 52 Entitäten → 48 Profile |
| Projekt / Graph | `proj_47db38facf64` / `e0ddeae9-75de-47ef-a5b2-485b84158393` (20 Episoden, 79 Entitäten, 74 Relationen) |
| Image | `ghcr.io/arn0ld87/agora:sha-3e94173`, alle Stufen ohne Neustart unter diesem Image |
| Seed | SHA-256 `54c9313a…`, identisch mit der lokalen Seed-Datei |

Es gibt keinen neueren Lauf. Jüngster gestarteter, abgeschlossener und exportierter Lauf sind derselbe.

**Modellroute** (aus den Route-Snapshots der Jobs):

| Stufe | Modell | Aufrufe ok / Fehler |
|---|---|---|
| Ontologie, Graph, Personas | openai / `gpt-6-luna` | 85 / 0 |
| Simulation | openai / `gpt-6-luna` | 1.059 / 2.225 `RateLimitError` |
| Interviews | openai / `gpt-6-luna` | 57 / 0 |
| Bericht | openai / `gpt-6-sol` | 105 / 0 |
| Bericht, erster Versuch | claude_cli / `claude-opus-5-5` | 0 / 1 (CLI 2.1.278 zu alt, 2.1.280 nötig) |

Parameter überall: `temperature` und `max_tokens` nicht gesetzt, `reasoning_effort: none`.

**Abweichungen zwischen Snapshot, Repo und Deployment:**

- Repo-HEAD `c97616de` liegt zwei Commits vor dem Deployment `3e941738`. Beide betreffen CI und Dependency-Cooldown; `git diff` über `backend/app` und `frontend/src` ist leer. Der lokale Quelltext entspricht dem Laufzeitcode.
- Alle einschlägigen Fixes (#1345, #1217, #1300, #1357, #1301, #1400, #1346, #1470/#1471, #1479, #1477/#1482, #1759) waren im Lauf aktiv. Keiner der Befunde ist ein „Fix noch nicht deployt"-Fall.
- `AGORA_AUDIT.md` existiert nirgends. Nächster Verwandter ist `docs/audits/2026-09-25-technical-audit.md`; ob das derselbe Snapshot ist, ist nicht belegt.

**Nicht nachweisbar:**

- Trunkierung, Parsingfehler und Retries der Berichtsstufen: `llm_call_events.jsonl` enthält weder `finish_reason` noch Antwortlänge noch Parsing-Status.
- Embedding-Aufrufe: fehlen im Log ganz.
- Rohantworten der Persona-Generierung und der Simulationsagenten: nicht gespeichert.
- Cosinewerte und Kandidatenlisten des Bindings: nicht persistiert.
- Ursache der Rate Limits: `http_status` und `remote_request_id` sind in allen Events `null`.

---

## 3. Ursachen nach Schwere

Zeilenangaben gelten für `3e941738` und `c97616de` gleichermaßen. Pfade relativ zu `backend/app/services/`.

### U1 (kritisch, bestätigt): Interviewtext wird vor der Bindung gekürzt

- `report_agent/agent.py:702` kürzt den Interview-Snippet, `:704` das Zitat auf 500 Zeichen (gegengeprüft).
- `evidence_binder.py:43` `candidate_text` liest `snippet`, `value` und aus `raw` nur `content`, `snippet`, `summary`, `name`. `raw.response` wird nie gelesen (gegengeprüft).
- Im Lauf ist der Vergleichstext bei allen 57 Interviews 303 Zeichen lang. Der Nachtbus-Satz steht bei Zeichen 657 von 2.380 in `ev_41539b715b4058a44d33bf8234f5bfa8`. Laut Gate-Log hatte der Claim keinen einzigen Kandidaten.
- Der Binder sieht 13 % des Interviewtexts, das Entailment 33 %. Es gibt drei abweichende Evidence-Text-Projektionen: `candidate_text`, `evidence_entailment._evidence_text` (`:997`) und `data_gap._pool_texts`.
- **Einschränkung:** Auch mit vollem Text erreicht der Nachtbus-Satz im Repro nur eine Deckung von 0,38, also `RELATED_ONLY`. Die Kürzung zu beheben ist notwendig, aber nicht hinreichend; danach entscheidet der Judge.
- Prüffall: `repro/repro_binding_numbers.py` (nicht im Repository, siehe Einleitung).

### U2 (hoch, bestätigt): Simulation zu zwei Dritteln ausgefallen, unsichtbar

- 2.225 von 3.284 Simulationsaufrufen scheiterten an Rate Limits; `simulation.log` nennt 640 Agentenschritte ohne Antwort.
- `payload.run_degradations` hat acht Einträge, keiner betrifft die Rate Limits. Sichtbar ist nur `tokens_status: partial`.
- Das verletzt die Projektregel, dass Degradationen sichtbar bleiben. Die 736 Aktionen sind das Ergebnis einer stark ausgedünnten Simulation.
- Ursache auf Anbieterseite (Tier-Limit) ist plausibel, nicht belegt.

### U3 (hoch, bestätigt für den Verlust): Tabellenwerte erreichen den Graphen nicht

- Stufenzählung aus A: 318 steht im Seed (Zeile 22) und im Chunk, aber in keiner der 74 Graph-Relationen. Dasselbe gilt für Fahrzeiten und März-Termin. Kein einziger Tabellenwert des Seeds wird zur Relation; nur Prosa-Sätze.
- Der Chunker ist nicht die Ursache (Repro: Tabellen liegen mit Kopfzeile in einem Chunk).
- Plausible Ursache: der relationszentrierte NER-Prompt (`ner_extractor.py:104`). Nicht bestätigt, weil die Rohantworten des Graph-Builds fehlen.
- Zweite Verluststelle, bestätigt: `extract_numeric_facts` liefert für eine Tabellenzeile, für „60 bis 80" und für „30. Juni 2027" nichts. `NumericFact.unit` kennt nur `percent` und `absolute` (`numeric_evidence.py:38`); alle 128 Ledger-Einträge tragen `absolute`. Typ, Einheit, Zeitbezug und Modalität gehen hier verloren.
- Folge im Bericht: 341 nur als ungebundene Hypothese; 60–80 Transporte erreichen den Evidence-Index nicht, und vier Interviews hängen der Zahl eine Verlegungs-Deutung an, die im Seed nicht steht.

### U4 (hoch, bestätigt): Satzsegmentierung zerreißt Datumsangaben

- `claim_atomizer.py:34` und `evidence_entailment.py:653` splitten an `(?<=[.!?])\s+` ohne Schutz für Ordinalzahlen (gegengeprüft).
- Aus „zum 30. Juni 2027 aufgibt." werden „…zum 30." und „Juni 2027 aufgibt.". Fragmente unter `MIN_ATOM_TOKENS` (`:43`) fallen still weg; `evidence_ledger.py:86` schreibt Fragmente als Fakt.
- Im Lauf: sechs Hypothesen und mehrere Ledger-Einträge mit diesen Fragmenten.
- `text_verification.py:306` löst das Problem bereits, wird hier aber nicht verwendet.
- Prüffall: `repro/repro_segmentation.py` (nicht im Repository, siehe Einleitung).

### U5 (hoch, statisch und beobachtet): Zwei unverbundene Confidence-Urteile

- Die fünf Claims werden `low`, weil `report_agent/manager.py:248` jeden Claim mit genau einer Evidence-Referenz deckelt (gegengeprüft).
- Die 29 `key_takeaways` (7 davon `high`) kommen aus dem `SectionMetadata`-Aufruf vor der Bindung (`report_agent/schemas.py:91-114`). `confidence` ist dort ein freier String ohne Evidence-Felder.
- `key_takeaways` hat außerhalb von `schemas.py` keinen Konsumenten in `backend/app` oder `frontend/src` (gegengeprüft per Suche). Die Werte stehen nur in `evidence_map.json` und damit im Evidence-Export, nicht in `report-v3.json`, Markdown oder UI-Komponenten. Das UI-Verhalten zur Laufzeit ist nicht geprüft.
- `cross_stakeholder_for_high` und `reject_inferred_in_high_confidence` greifen nur auf `ReportClaimModel` (`contracts/report_contract.py:537,576`). Die Hartanker sind intakt, decken diese Fläche aber nicht ab.
- „Simulationskonsens / persona" bei einer einzigen Stimme: `claim_provenance.py:100` gibt `simulation_consensus` als Rückfallwert zurück (gegengeprüft); in `:117` ist eine von einer Stimme eine strikte Mehrheit.

### U6 (mittel, statisch und beobachtet): Persona-Metadaten

- `graph_tools.py:461` setzt `agent.get("profession", "Unknown")` (gegengeprüft). „Unknown" ist ein nicht-leerer String und blockiert den Fallback auf die Rollenfamilie in `agent.py:683`.
- Im Lauf: 37 von 57 Interviews mit Gruppe `Unknown`, verteilt auf 31 Agenten, überwiegend Organisations- und Ortsentitäten.
- `Person` ist der Pflicht-Fallbacktyp der Ontologie (`ontology_generator.py:441`).
- Zehn Profilnamen weichen vom Entitätsnamen ab; vier handelnde Agenten haben kein Profil. Die 12 Rollenkonflikte existieren nur als Zähler.
- Eine Fallback-Persona: Dr. Frank Oltmann wurde wegen der Altersregel aus #1759 zum Platzhalter und nie befragt. In den Profilen ist der Platzhalter nicht markiert.

### U7 (mittel, bestätigt): Data Gaps aus Fragmenten

- `G3_01` und `G5_01` entstehen aus Satzfragmenten (U4) und einem Wortüberdeckungsmaß; bester Wert im Repro 0,077.
- Es gibt keinen Typ „Aussagegrenze". Eine im Seed vorhandene Information landet als Gap, weil die Paraphrase die Wortüberdeckung verfehlt. Das ist ein Binding-Problem, kein Data Gap.
- Prüffall: `repro/repro_data_gap.py` (nicht im Repository, siehe Einleitung).

### U8 (mittel, statisch): Provenienz und Zitattreue

- `source_model` hat keinen Producer; außerhalb der Verträge existiert nur ein Whitelist-Eintrag in `evidence_migrations.py:555` (gegengeprüft). Alle 99 Evidence-Einträge sind leer.
- `document_role` bleibt für `domain_fact` absichtlich `None` (`document_roles.py:45`).
- `report-v3.json:model_attribution` nennt nur die Stufe `red_team` mit `provider: unknown`; 104 weitere Berichtsaufrufe fehlen.
- Hebammenzitat: Die Kürzung stammt vom LLM. `validate_quote_anchors` (`evidence.py:580`) prüft den Anker, nie den Zitattext. 6 von 37 Persona-Zitaten sind nicht exakt in der Antwort enthalten.

### U9 (mittel, beobachtet): Aktionen als Evidence

- `agent.py:469` zieht fest `k=8` Aktionen (gegengeprüft). Von 736 Aktionen stehen 8 im Evidence-Index.
- Nur ein Claim hatte überhaupt eine Aktion als Kandidaten (`INSUFFICIENT`, Cosine 0,599). Eine Belegpflicht für Aktionen ist nirgends definiert.
- Die Auswahlregel der acht Aktionen ist nicht untersucht.

### U10 (mittel, Design): Kurzfazit, Risiken, Empfehlung ohne Claims

- Jeder Satz braucht ein Item mit `supports_claim=True` (`agent.py:1227`). Es gibt keinen Aggregat-Claim über mehrere Teil-Claims, deshalb bleiben zusammenfassende Abschnitte ohne validierte Claims.
- Das ist eine Designfrage. Ein Reparaturansatz braucht eine Entscheidung des Maintainers.

### U11 (niedrig, beobachtet): Statusinkonsistenzen

- Run `completed` bei Bericht `incomplete`; auch der gescheiterte erste Versuch steht auf `completed`.
- `agora.simulations.status` bleibt in Postgres `running`, obwohl `run_state.json` `completed` zeigt.
- `total_actions_count` 793 zählt die 57 Interviews mit; tatsächlich sind es 736 Aktionen.
- `degradation_log` in `evidence_map.json` ist leer; die Degradationen stehen nur im Postgres-Payload und in `progress.json`.

### Unbekannt

- Ob die NER-Stufe die Tabellenzeilen verwarf oder nie sah.
- Cosinewert und Kandidatenrang von `ev_4153…` sowie echte Judge-Urteile.
- Ob die UI `key_takeaways` zur Laufzeit anzeigt.
- Ursache der Rate Limits.

---

## 4. Reparaturplan

Reihenfolge nach Abhängigkeit. Aufwand grob: S bis ein Tag, M wenige Tage, L eine Woche und mehr. Alle Pakete lassen die ADR-0002-Hartanker unverändert. Die Regressionstests stehen mit Eingabe und Erwartung in Teil B, Abschnitt „Vorgeschlagene Regressionstests".

| AP | Problem | Vertragsänderung | Producer / Consumer | Regressionstest (Nr. in B) | Aufwand | Rollback |
|---|---|---|---|---|---|---|
| 1 | U4 Segmentierung | keine | ein gemeinsamer Satzsplitter für `claim_atomizer`, `evidence_entailment`, `evidence_ledger`; Basis `text_verification.py:306` | 1, 2 | S | Revert, reine Funktion |
| 2 | U1 Interviewtext | Evidence-Item bekommt ein kanonisches Volltextfeld; Snippet bleibt Anzeige | `agent.py` schreibt, Binder, Entailment und Data-Gap lesen dieselbe Projektion | 4 | M | Revert; Feld ist additiv |
| 3 | U2 Rate-Limit-Verlust | neuer Degradationseintrag mit Fehlerquote | Simulations-Runner schreibt, Bericht und UI zeigen | neuer Test: Fehlerquote über Schwelle erzeugt Degradation | S–M | Revert |
| 4 | U5 Confidence-Flächen | `SectionKeyTakeaway.confidence` als Enum; Kernaussage referenziert Claim-IDs oder wird gedeckelt | `schemas.py`, Evidence-Export, Frontend-Spiegel | 6, 5 | M | Revert; Schema regenerieren |
| 5 | U6 Persona-Gruppe | keine | `graph_tools.py:461`, `interview_helpers.py`, Fallback in `agent.py:683` | 9 | S | Revert |
| 6 | U3 Zahlen | `NumericFact` um Einheit, Zeitbezug, Modalität, Quellspan | `numeric_evidence`, Ledger, operative Tabelle, Frontend-Spiegel | 3 | L | Feature hinter additiven Feldern |
| 7 | U7 Data Gaps | Gap-Typ „Aussagegrenze" oder Ausschluss | `report_agent/data_gap.py` | 7 | S, nach AP 1 und 2 | Revert |
| 8 | U8 Provenienz | `source_model` bekommt einen Producer; `model_attribution` vollständig; Aufruf-Log mit `finish_reason` und Parsing-Status | LLM-Client, Evidence-Erzeugung, Export | neuer Vertragstest | M | Revert |
| 9 | U8 Zitattreue | keine | `evidence.py:580` prüft Zitattext gegen Quelle | 8 | S | Revert |
| 10 | U11 Status | keine | Run-Registry, Postgres-Sync, Aktionszähler | neuer Test je Inkonsistenz | S | Revert |

Vor AP 6 steht eine Diagnose statt einer Annahme: einen einzelnen Graph-Build auf dem eingefrorenen Seed mit gespeicherten Rohantworten fahren und prüfen, ob die Tabellenzeilen den NER-Prompt erreichen. Das ist ein LLM-Aufruf im Umfang von 20 Chunks und fällt nicht unter diesen Auftrag.

**Nicht geplant, weil Entscheidung offen:** U9 (Aktions-Stichprobe, Belegpflicht für Aktionen) und U10 (Aggregat-Claims für zusammenfassende Abschnitte).

**Zuordnung zu bestehender Arbeit:**

- #1304 (offen) und #1662 (offen) messen die Evidence-Nutzung, enthalten aber keine Ursachenarbeit. AP 2 gehört thematisch dorthin.
- #1400 und #1240 (offen, Teile gemerged) decken `document_role` teilweise; AP 8 ergänzt `source_model`.
- #1292 (offen) betrifft Seed-Zahlen; AP 6 passt dazu.
- Ohne Issue: U1, U2, U4, U5 (Kernaussagen), U6, `source_model`. Nach der Projektregel „keine Folge-Issues" lege ich keine an; das ist eine der offenen Fragen.
- Erledigt und nicht neu zu planen: Einzelzahl-Prüfung (#1217, #1345), ehrliches `INCOMPLETE` (#1479), Evidence-Vertrag (#1477/#1482).

---

## 5. Abnahmematrix

Harte Kriterien sind deterministisch am Artefakt prüfbar. Für Coverage und Mehrwert gibt es bewusst keine Prozentziele, solange keine Referenzannotation existiert.

| Kriterium | Baseline in diesem Lauf | Ziel | Messmethode |
|---|---|---|---|
| Evidence-Referenzen auflösbar | 15 von 15 Zitatanker auflösbar | 100 % | Skript über `evidence_map.json` |
| Vergleichstext gleich Volltext | 57 von 57 Interviews auf 303 Zeichen gekürzt | 0 gekürzte | Invariante aus Test 4 |
| Keine widersprüchlichen Confidence-Ausgaben | 7 `high`-Kernaussagen bei 5 `low`-Claims | keine Ausgabefläche über dem Claim-Label | Test 6, Skript über Export |
| Konsens-Label nur ab zwei Stimmen | 4 Claims „Konsens" mit je einer Stimme | 0 | Test 5 |
| Datumsangaben unzerteilt | 6 Hypothesen mit Fragment | 0 | Regex über Hypothesen und Ledger |
| Zahlenherkunft erhalten | 0 von 7 geprüften Seed-Ankern als Claim gebunden; 318 fehlt | jede Gold-Zahl mit Wert, Einheit, Zeitbezug, Modalität und Seed-Span auffindbar | Stufenzählung wie A, Abschnitt 4.0 |
| Degradationen sichtbar | Rate-Limit-Verlust 68 % nicht ausgewiesen | jede Degradation in Bericht und Export | Skript: Fehlerquote gegen `run_degradations` |
| Provenienz gefüllt | `source_model` in 0 von 99 Einträgen | 100 % der modellerzeugten Einträge | Skript |
| Zitattreue | 6 von 37 Zitaten nicht exakt | 0 unmarkierte Abweichungen | Teilstring-Prüfung plus Test 8 |
| Stakeholder-Gruppe gesetzt | 37 von 57 `Unknown` | 0 `Unknown` | Skript |
| Belegte Claim-Coverage | 5 Claims, 94 Hypothesen | Schwelle erst nach Referenzannotation festlegen | Abgleich gegen Gold-Aussagen |
| Fachlicher Mehrwert der Simulation | nicht gemessen | Vergleich gegen zwei Baselines, Abschnitt 6 | menschliche Bewertung |

---

## 6. Referenzfälle und Baselines

Es fehlen annotierte Seed-Referenzfälle, Recall-Metriken auf Laufartefakten und Baselines. Der bestehende Evidence-Quality-Gate misst nur die Claim-Seite auf drei synthetischen Fixtures. #765 (Baseline-Vergleich) ist laut `ROADMAP.md:136` auf nach 1.0 verschoben; #1662 ist die offene 1.0-Pflicht mit einem Lauf je Variante.

Drei Referenzfälle, jeweils mit Gold-Annotation von Hand (Zahlen mit Einheit und Modalität, Kernaussagen je Stakeholder, bekannte Lücken):

1. **Hollerau (vorhanden):** zahlenlastig mit Tabellen und zwei Zählweisen. Prüft Zahlenherkunft und Datumsangaben. Eingefrorener Seed und Snapshot existieren.
2. **Widerspruchsfall:** Seed mit zwei Quellen, die sich in einer Zahl und einer Bewertung widersprechen. Erwartung: Widerspruch wird ausgewiesen, kein `high`.
3. **Lückenfall mit Budgetabbruch:** Seed, dem eine entscheidende Information fehlt, plus ein Lauf mit knappem Budget. Erwartung: echter Data Gap, sichtbarer Budgetabbruch, kein Fallback-Erfolg.

Dazu je ein Gegenbeispiel: eine Aussage, die im Interview steht und gebunden werden muss (Nachtbus), und eine, die nicht im Material steht und nicht gebunden werden darf.

**Baselines je Referenzfall:**

- A: einfache seedbasierte LLM-Analyse, ein Prompt, kein Graph, keine Personas.
- B: interviewgestützte Analyse ohne Simulation.
- C: vollständige Pipeline.

Gemessen wird dasselbe wie in der Abnahmematrix. Die Simulation hat einen belegten Mehrwert nur, wenn C gegenüber B zusätzliche gebundene Aussagen liefert, die auf Aktionen zurückgehen. In diesem Lauf stützt keine Aktion einen Claim; der gemessene Beitrag der Simulation zum Bericht ist null. Das kann an U9 liegen und ist kein Beweis, dass die Simulation nutzlos ist.

Wiederholungen: mindestens drei Läufe je Variante, Streuung ausweisen. Ein gespeicherter Seed macht einen Lauf nicht reproduzierbar. Drei Ebenen getrennt halten: deterministische Artefaktprüfung, erneute Berichtserzeugung aus eingefrorener Simulation, neue stochastische Simulation.

---

## 7. Modellentscheidung

**Befund:** 0 harte Refusals, 0 KI-Disclaimer, 0 moralische Ausweichantworten in 57 Interviews, 369 Textaktionen, Log und 48 Profilen. 25 Antworten enthalten epistemische Zurückhaltung („kann ich nicht beurteilen"); das ist per Regex gezählt und nur stichprobenhaft gelesen. Die fehlenden Perspektiven gehen auf Konfiguration zurück (Altersregel, Entitäten ohne Rolle), nicht auf Verweigerung.

**Entscheidung:** Beim aktuellen Modell bleiben und die Pipeline reparieren. U1, U3 (zweite Stufe), U4, U5, U6 und U8 sind deterministisch und modellunabhängig. Ein unzensiertes Modell löst ein Problem, das in diesem Lauf nicht auftritt, und laut Recherche (Teil C, Punkt 10) ist ein abliteriertes Modell nicht einfach das Basismodell ohne Refusals.

**Die echte Modellrouten-Frage ist der Durchsatz:** 68 % Rate-Limit-Fehler in der Simulation. Hier liegt der kurzfristige Hebel, entweder über gedrosselte Parallelität oder eine Route mit höherem Limit.

**Vergleichsdesign, falls gewünscht (nichts davon gestartet):**

- Eingefrorene Eingaben je Stufe aus dem Snapshot: 57 Interviewfragen mit Profilen, 20 Chunks für die Extraktion, die Abschnittsprompts.
- Drei Arme: `gpt-6-luna` (aktuell), ein stärkeres reguläres Modell, ein lokales unzensiertes Modell. Auf gns3 läuft RavenX-35B-v5.1; auf der Platte liegen außerdem OrcaSAQ-2-27B-Uncensored und Qwen3.8-27B-OBLITERATED.
- Vierter Arm zur Isolation des Unzensierungs-Effekts: das Basismodell `Qwen/Qwen3.8-27B`. Es ist laut Inventar nicht auf der Platte und müsste geladen werden.
- Messgrößen: Zahlentreue gegen Gold, gebundene Claims, falsche Bindungen, Schemakonformität, Role Leakage, Perspektivenvielfalt, Refusals, Laufzeit, Kosten.
- Deterministische Prüfungen und Handannotation zuerst; ein LLM-Judge nur ergänzend.
- Modell- und Pipelinewechsel getrennt: erst nach AP 1 und 2 vergleichen, sonst misst der Vergleich die Kürzung mit.

Kosten als Anhaltspunkt: Interviews und Bericht dieses Laufs brauchten zusammen rund 637.000 Eingabe- und 49.000 Ausgabe-Tokens. Die Simulation mit 35,7 Millionen Eingabe-Tokens ist der teure Teil und für den Stufenvergleich nicht nötig.

---

## 8. Recherche: was übertragbar ist

Volltext, Grenzen und Experimente je Empfehlung stehen in Teil C. Die Lesetiefe ist dort begrenzt: 39 Registereinträge, rund 33 ausgewertet, die meisten nur in gezielten Passagen. Fast alle Quellen sind englischsprachig; die Tauglichkeit für Deutsch ist nirgends belegt.

| Verfahren | Quelle | Passt zu |
|---|---|---|
| Claim-Selektion und Disambiguierung mit Abstention | Claimify, arXiv 2502.10855 | U7, U10 |
| Claim als Ereignis mit allen Modifikatoren, Kontextfenster | VeriScore, arXiv 2406.19276 | U4 |
| Zahlen- und Datumsprüfung vor der Verifikation | QuanTemp, arXiv 2403.17169 | U3 |
| Zweistufiges Binding: Zitat-Check, dann Mehrsatz-Verifikation | MiniCheck 2404.10774, AlignScore 2305.16739, SummaC 2111.09525 | U1 |
| Citation-Recall und -Precision als Pflichtmetrik | ALCE 2305.14627, AIS 2112.12870 | Abnahmematrix |
| Confidence aus verifizierter Evidence statt verbalisiert | Xiong 2306.13063, Tian 2305.14975 | U5 |
| Konsens nur ab zwei verschiedenen Personas, Diversität messen | OpinionQA 2303.17548, arXiv 2402.01908 | U5, U6 |
| Grammatik sichert Form, Validatoren sichern Semantik | Anbieterdokumentation | U8 |

**Transport:** Der selbstgehostete Firecrawl kann Scrape und Search, auch PDF. Der Paper-Index liefert 404, `formats:["query"]` scheitert meist. Cloud wurde nicht genutzt. Abweichung von der Vorgabe: Die Volltexte wurden überwiegend per `ctx_fetch_and_index` lokal abgerufen statt über Firecrawl. SearXNG brach nach etwa elf Anfragen mit „Network Error" ab.

**Abdeckungslücken:** keine Primärquelle zu Modalität (Erwartung gegen Ist-Wert) und zu Role Leakage; OASIS-Interview-Aktion und Agentenprofil nicht gelesen; Verhalten deutscher Segmentierer bei „zum 30. Juni 2027" nicht belegt.

**Rerun Inputs:** workflow `firecrawl-deep-research`, topic `Agora Lauf-Trust und Evidence-Verlust`, depth `exhaustive`, output `markdown`, Skill-Version 0.1.0 (Frontmatter), Transport selbstgehosteter Firecrawl plus SearXNG, Lauf `report_a8fa9ff9fad0`, Deployment `sha-3e94173` auf armserver. Diese Angaben dokumentieren die Konfiguration und garantieren keine identischen Ergebnisse.

---

## 9. Tooling

Nichts davon wurde ausgeführt oder installiert; Befehle stehen in Teil D.

- Vorhanden und in CI: Ruff, mypy, Schema-Drift-Check, CodeQL, Coverage-Ratchet, gitleaks.
- CodeQL: 0 offene Alerts, keiner betrifft Evidence- oder Report-Code. Das sind Security-Befunde und sagen nichts über Evidence-Korrektheit.
- Inkonsistenz: `pyproject.toml` hat `branch = false`, CI misst mit `--cov-branch`.
- Nicht vorhanden: import-linter, mutmut, hypothesis. Pyright steht in den Dev-Abhängigkeiten ohne Konfiguration und Aufruf.
- Mutationskandidaten und ein import-linter-Entwurf stehen in Teil B. Sinnvoll erst nach AP 1 und 2, wenn die Tests 1 bis 6 existieren.

Ein grünes Tool belegt keinen belastbaren Bericht. Die semantischen Verluste hier wären von keinem dieser Werkzeuge gefunden worden.

---

## 10. Drei nächste Schritte

**Aktueller Stand (05.10.2026):** AP 1, AP 2 und AP 3 sind auf `main` (siehe „Stand der Umsetzung"). Der nächste Schritt ist deshalb nicht ihre Umsetzung, sondern ihr Wirknachweis: den Bericht aus der eingefrorenen Simulation `sim_cc6067a70603` neu erzeugen und gegen die Abnahmematrix messen. Schritt 3 unten (Hollerau annotieren) ist unverändert offen.

Die folgende Liste ist die Planung vom 04.10.2026:

1. **AP 1 und AP 2 umsetzen**, jeweils mit den Regressionstests 1, 2 und 4. Danach den Bericht aus der eingefrorenen Simulation `sim_cc6067a70603` neu erzeugen und gegen die Abnahmematrix messen.
2. **AP 3 umsetzen**: den Rate-Limit-Verlust als Degradation ausweisen und die Parallelität der Simulation drosseln. Ohne das ist jeder weitere Lauf auf dieser Route zu zwei Dritteln leer.
3. **Hollerau von Hand annotieren**: Gold-Zahlen mit Einheit, Zeitbezug und Modalität, dazu die Kernaussagen je Stakeholder. Das ist die Voraussetzung für AP 6 und für jede Coverage-Schwelle.

## 11. Offene Fragen

- Unter welchem Issue laufen U1, U2, U4, U5, U6 und `source_model`? Die Projektregel verbietet Folge-Issues ohne Freigabe.
- Sollen zusammenfassende Abschnitte Aggregat-Claims bekommen (U10), und welche Belegpflicht gilt für Empfehlungen?
- Sollen Simulationsaktionen eine Belegpflicht bekommen, und wie groß darf die Stichprobe sein (U9)?
- Soll `key_takeaways` entfernt, gedeckelt oder an Claims gebunden werden?
- War der Lauf auf armserver beabsichtigt? Der Auftrag nannte gns3.
- Woher kommen die Rate Limits: Tier-Limit des Anbieters oder Parallelität der Simulation?
