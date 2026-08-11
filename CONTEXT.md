# CONTEXT.md — Wie Agora tatsächlich arbeitet

Diese Datei erklärt die Laufzeit-Mechanik von Agora für Agenten und LLMs, die mit dem System oder seinen Artefakten arbeiten. Sie beschreibt, **was passiert**, nicht was wünschenswert wäre. Produktbeschreibung steht in [`README.md`](README.md), Arbeitsregeln in [`AGENTS.md`](AGENTS.md).

> Kurzfassung in einem Satz: Agora zerlegt Dokumente in einen Wissensgraphen, leitet daraus Stakeholder-Personas ab, lässt diese in einer OASIS-Simulation auf zwei Social-Plattformen interagieren, befragt sie anschließend in Tiefeninterviews, und erzeugt daraus einen Bericht, dessen Aussagen einzeln gegen Evidence geprüft werden.

---

## 1. Die fünf Phasen und ihre Artefakte

Jede Phase erzeugt Artefakte mit stabilen IDs. Wer einen Lauf auswertet, arbeitet immer mit diesen IDs.

| Phase | Erzeugt | ID-Präfix |
|---|---|---|
| 1 Graph-Build | Neo4j-Knoten, Vektoren | `graph` = UUID |
| 2 Prepare | Personas, Agent-Konfiguration | `sim_…` |
| 3 Simulation | Zwei SQLite-DBs mit Posts, Kommentaren, Aktionen | `sim_…` |
| 4 Report | Sections, Evidence-Map | `report_…` |
| — Klammer | Run-Registry über alle Phasen | `run_…` |

### Phase 1 — Graph-Build

Das Quelldokument wird gechunkt. Pro Chunk ein NER-Call gegen ein Pydantic-Schema (`NerExtractionResult`), der Entitäten und Relationen liefert, dann ein Batch-Embedding, dann ein Schreibvorgang nach Neo4j.

```
[graph_build] Chunk 12/48 (413 chars): "…"
[ingestion] NER done: 5 entities, 4 relations
[ingestion] Batch-embedding 9 texts...
[graph_build] All 48 chunks processed successfully
Graph <uuid> marked as completed
```

**Wichtig:** Die NER erfindet ihr Typvokabular pro Lauf neu. Dasselbe Dokument ergab mit drei Modellen drei disjunkte Vokabulare (`Lecturer`/`Employer` — `Organization`/`Student`/`Professor` — `FreelanceLecturer`/`PermanentLecturer`/`WorksCouncilMember`), und zwei Läufe mit demselben Modell ebenfalls unterschiedliche. Jede Logik, die auf `entity_type` matcht, ist damit lauf-abhängig.

### Phase 2 — Prepare

Entitäten werden gefiltert und auf Persona-Eignung geprüft (`backend/app/services/persona_eligibility.py`, zwei Stufen):

1. **Harte Blockliste** über `entity_type` (`INELIGIBLE_ENTITY_TYPES`) — `city`, `software`, `date`, `concept`, `document`, `technology` u. a. „hat keinen menschlichen Träger".
2. **Unbekannte Typen** werden konservativ **zugelassen** (Issue #1034) und geloggt.

Danach eine Persona pro Entität, generiert in parallelen Einzel-Calls gegen `PersonaProfileSchema`. Jeder Call sieht nur seine eigene Entität.

```
Persona-Eligibility: 36 von 48 Entitaeten tragen einen entity_type
  ausserhalb der bekannten Liste und werden konservativ zugelassen
Starting parallel generation of 50 agent personas (parallel count: 10)
```

Anschließend baut `simulation_config_generator.py` die `initial_posts` und weist ihnen Poster-Agenten zu — Direct-Match über `entity_type`, dann eine Alias-Tabelle, dann Fallback auf den Agenten mit höchstem `influence_weight`.

### Phase 3 — Simulation

Ein **eigener Subprozess** (OASIS/CAMEL) läuft zwei Plattformen parallel:

| Plattform | Recsys | Aktionen |
|---|---|---|
| Twitter | `twhin-bert` | `create_post`, `quote_post`, `repost`, `like_post`, `follow`, `refresh` |
| Reddit | `reddit` | `create_post`, `create_comment`, `like_post`, `like_comment`, `refresh` |

Twitter kennt **keine Kommentare** — `quote_post` übernimmt diese Rolle. Das ist kein Defekt.

`max_rounds` schneidet die geplanten Runden ab (`Rounds truncated: 24 -> 10`).

### Phase 4 — Report

Pro Section ein ReAct-Loop mit vier Tools, danach eine mehrstufige Nachbearbeitung.

| Tool | Zweck |
|---|---|
| `insight_forge` | Tiefenanalyse gegen den Graphen, liefert Fakten-Listen |
| `panorama_search` | Breitensuche |
| `quick_search` | gezielte Einzelabfrage |
| `interview_agents` | **Tiefeninterview mit ausgewählten Agenten** |

---

## 2. Die Interviews — das am häufigsten missverstandene Stück

`interview_agents` ist **keine** Auswertung der Simulationsposts. Es ist eine **zweite, nachgelagerte LLM-Befragung** derselben Personas, nach Abschluss der Simulation.

Ablauf pro Section:

```
InterviewAgents deep interview (real API): <topic>
Loaded 30 profiles from reddit_profiles.json
Selected 8 Agents for interview: [15, 29, 4, 7, 21, 9, 11, 14]
Generated 4 interview questions
Calling batch interview API (dual platform): 8 Agents
Interview API returned: 8 results, success=True
```

- Der Report-Agent formuliert ein **`interview_topic`** und wählt bis zu `max_agents` Personas aus, mit einer Begründung im Ergebnis (`Selection Rationale`).
- Daraus werden **4–5 Fragen** generiert. Diese Fragen sind neutral formuliert („Welcher Moment lässt Sie am stärksten an der KI zweifeln?"), das **Thema** ist es nicht — es nennt regelmäßig konkrete Stakeholder-Gruppen.
- Jede Persona antwortet **pro Plattform getrennt**. Twitter liefert häufig `(No response from this platform)`; die Reddit-Antwort trägt den Inhalt.
- Die Antworten werden zu `agent_interview`-Evidence und sind in vielen Läufen der **größte Evidence-Typ**.

**Drei Eigenheiten, die man kennen muss:**

1. **Frage-Echo.** Personas beginnen ihre Antwort oft mit der Formulierung der Frage („Die Akzeptanz bricht zuerst bei den Honorarkräften, konkret in dem Moment, wo …"). Wenn mehrere Personas dieselbe Frage bekommen, wirken ihre Antworten dadurch wie unabhängige Bestätigung, sind es aber nicht.
2. **Rollenübernahme.** Personas präfixieren Antworten mit einer Rolle, die nicht ihre ist — eine Rechenzentrums-Technikerin antwortet „Als Betriebsrat hätte ich vorab klären müssen …". Der Report übernimmt diese Zuschreibung.
3. **Zitat ≠ Simulationsäußerung.** Ein Zitat im Report stammt meist aus dem Interview, nicht aus einem Post der Simulation. Wer im Feed danach sucht, findet es nicht.

---

## 3. Das Evidence-Modell

Jede Aussage des Berichts durchläuft eine Prüfung und landet in genau einer Kategorie.

| Kategorie | Bedeutung |
|---|---|
| **Claim** | mit Evidence gebunden, `entailment: SUPPORTED` |
| **Hypothese** | keine deckende Evidence gefunden → aus dem validierten Bestand entfernt |
| **Data Gap** | benannte Lücke |

Evidence-Typen im `evidence_index`:

```
agent_interview     Antworten aus Phase 4
seed_document       Sätze aus dem Quelldokument
relationship_chain  Pfade im Graphen
agent_action        "IHK CREATE_POST on reddit in round 0"
graph_metric        echo_chamber_index, cluster_count, …
```

### Zwei getrennte Prüfstellen — häufige Verwechslung

| | `claim_extraction_and_evidence_binding` | `verify_prose` |
|---|---|---|
| prüft | extrahierte Claims | Sätze im Fließtext |
| Umfang | alle Claims | **nur Sätze mit einer Zahl** |
| Ergebnis | Claim oder Hypothese | Satz bleibt oder wird entfernt |

`backend/app/services/report_agent/text_verification.py`:

```python
def _has_factual_claim(sentence: str) -> bool:
    """Nur Sätze mit einer Zahl samt Bezugsgruppe sind prüfbare Faktenaussagen."""
    return bool(extract_numeric_facts(sentence))
```

**Folge:** Der Bericht kann 130 Hypothesen in der Maschinenschicht führen und im Text nur einen Satz pro Section verlieren. Text und Belegschicht driften auseinander. Ein Satz wie „Die Simulation zeigt ein klares Ergebnis" wird nie geprüft.

### Zitat-Anker

Zitate tragen `persona_id` und `seed_anchor`. Die Validierung in `backend/app/services/report_agent/evidence.py` prüft Anker gegen `known_anchors` — **außer** wenn sie mit `seed_doc:` beginnen:

```python
# seed_doc:-Prefix ist immer akzeptiert (opaque Referenz)
if not seed_anchor.startswith(_SEED_DOC_PREFIX):
    if seed_anchor not in known_anchors:
        unbound_refs.append(seed_anchor)
```

Beobachtet: Modelle setzen `seed_doc:`-Anker, die auf nichts verweisen — mal einen konstanten Wert für alle Zitate, mal pro Persona konstruierte wie `seed_doc:interview_<name>`. Beides passiert die Prüfung.

Zusätzlich: Sections **ohne** `<simulated_quote>`-Tags gelten als valide. Ein Modell, das Personas wörtlich zitiert, ohne die Tag-Syntax zu verwenden, erzeugt keinen Verstoß.

---

## 4. Wo die Artefakte liegen

Im Container `agora`:

```
/app/backend/uploads/simulations/<sim_id>/
    simulation_config.json     agent_configs[], event_config.initial_posts[]
    run_state.json             runner_status, current_round, total_actions_count
    reddit_profiles.json       die finalen 30–50 Personas
    twitter_simulation.db      SQLite
    reddit_simulation.db       SQLite
    simulation.log             Subprozess-Log — NICHT auf Container-stdout

/app/backend/uploads/reports/<report_id>/
    outline.json               geplante Sections
    section_01.md … NN.md      ausgelieferter Text
    evidence_map.json          claims, hypotheses, data_gaps, evidence_index, gate_decision_log
    agent_log.jsonl            jeder Tool-Call und jedes Tool-Result
    console_log.txt            Phasenprotokoll mit Heartbeats
    meta.json                  status, markdown_content, simulation_snapshot
```

`docker logs agora` zeigt Backend, Prepare und Report — **nicht** die Simulationsrunden. Die stehen in `simulation.log` im Container.

### Sim-DB-Schema

Beide Plattformen identisch:

```sql
post(post_id, user_id, original_post_id, content, quote_content, created_at,
     num_likes, num_dislikes, num_shares, num_reports)
trace(user_id, created_at, action, info)
comment, like, dislike, comment_like, comment_dislike, follow, mute, rec, user
```

**Auswertungsfalle:** Reposts und Quotes sind eigene `post`-Zeilen mit gesetztem `original_post_id`; reine Reposts tragen **leeres `content`**. Ohne den Filter `original_post_id IS NULL` sieht jede Auswertung nach Mode-Collapse und leeren Posts aus, obwohl die Semantik korrekt ist.

---

## 5. Modell- und Provider-Routing

Ein Lauf nutzt typischerweise **mehrere Modelle gleichzeitig**:

| Aufgabe | Schema | Beispiel |
|---|---|---|
| Ontologie | `OntologyDefinition` | 1 Call |
| NER | `NerExtractionResult` | 1 Call pro Chunk |
| Personas | `PersonaProfileSchema` | 1 Call pro Entität |
| Report | ReAct + Sections | viele |

Das Log meldet die Bindung explizit:

```
Report LLM route locked provider_id=google model=models/gemini-3.6-flash
  [simulation_id=…, report_id=…, project_id=…, run_id=…]
```

**Strukturierte JSON-Calls laufen ausschließlich über `LLMClient.chat_json` mit Pydantic-Schema.** Der rohe OpenAI-Client umgeht Provider-Detection, strict-json_schema und die JSON-Repair-Logik — siehe [`CLAUDE.md`](CLAUDE.md).

### Embedding hat einen eigenen, getrennten Pfad

| Pfad | Konfigurationsquelle |
|---|---|
| Graph-Ingestion | Env `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` |
| Re-Embedding / Migration | `EmbeddingConfigurationStore`, JSON unter `AGORA_DATA_DIR` |

Was in der Embedding-UI konfiguriert wird, erreicht den Graph-Build **nicht**. `VECTOR_DIM` wird aus `KNOWN_EMBEDDING_DIMS` abgeleitet; ein abweichender expliziter Wert löst einen Guard aus. Die Neo4j-Vektorindizes `entity_embedding` und `fact_embedding` müssen zur Dimension passen.

---

## 6. Bekannte Fehlerbilder — nicht als neue Befunde melden

Diese Beobachtungen sind dokumentiert und erklärt. Wer sie als Neufund meldet, verbrennt Zeit.

| Beobachtung | Erklärung |
|---|---|
| `Failed to write data to connection … neo4j:7687`, gehäuft beim Simulationsstart | Docker-Bridge killt Bolt-Sockets in der Fork-Idle-Phase; `liveness_check_timeout` fängt es ab, der Treiber baut neu auf. Dokumentiert in `backend/app/storage/neo4j_storage.py`. Kein Defekt. |
| Twitter hat 0 Kommentare | Twitter kennt keine; `quote_post` übernimmt die Rolle. |
| Viele identische Posts, manche mit leerem `content` | Reposts und Quotes, siehe Auswertungsfalle oben. |
| `pooler.dense.weight MISSING` beim Laden von `twhin-bert-base` | Bekannt, Issue #1236 — der Twitter-Recommender rankt über zufällig initialisierte Gewichte. |
| Rohes Persona-Log zeigt Namens- und Gender-Kollaps | Der Dedup-Schritt repariert das. Maßgeblich ist `reddit_profiles.json`, nicht das Log. |
| `Published 1 initial posts` bei mehr konfigurierten Posts | Der Zähler zählt **distinkte Poster-Agenten**, nicht Posts. |

---

## 7. Einen Lauf auswerten — Standardgriffe

```bash
# Phasen und IDs
docker logs agora 2>&1 | grep -E "marked as completed|Create simulation|Simulation started|Report LLM route"

# Simulationsstand
docker exec agora cat /app/backend/uploads/simulations/<sim_id>/run_state.json

# Aktionsverteilung und Dislikes
docker exec agora python -c "
import sqlite3,collections
c=sqlite3.connect('file:/app/backend/uploads/simulations/<sim_id>/reddit_simulation.db?mode=ro',uri=True)
print(collections.Counter(r[0] for r in c.execute('select action from trace')))"

# Evidence-Bilanz
docker exec agora python -c "
import json
m=json.load(open('/app/backend/uploads/reports/<report_id>/evidence_map.json'))
for s in m['sections']:
    print(s['section_index'], len(s.get('claims') or []), len(s.get('hypotheses') or []))"

# Woher stammt eine Aussage im Report?
docker exec agora grep -o '.\{200\}SUCHTEXT.\{100\}' \
  /app/backend/uploads/reports/<report_id>/agent_log.jsonl
```

Der letzte Griff ist der wichtigste: **`agent_log.jsonl` enthält jeden Tool-Call und jedes Tool-Result.** Damit lässt sich jede Formulierung im Bericht bis zu ihrer Quelle zurückverfolgen — und feststellen, ob sie aus einem Interview, aus dem Graphen oder aus dem Quelldokument stammt.

---

## 8. Was Agora nicht ist

- **Keine Verhaltensprognose.** Die Personas sind LLM-Konstrukte aus einem Dokument, keine Stichprobe. Der Bericht liefert mögliche Einwände und Konfliktlinien, keine Vorhersage.
- **Kein Ersatz für Interviews oder Nutzertests.**
- **Keine Garantie, dass ein Zitat belegt ist.** Zitate tragen Anker, deren Prüfung Lücken hat (Abschnitt 3).
- **Keine Aussage darüber, was die Simulation beigetragen hat**, wenn das Quelldokument bereits Antworten enthält — siehe Issue #1240.

Aktuelle Belege für alle vier Punkte stehen in den [Referenzläufen](docs/reference-runs/), die bewusst Fehlerklassen mitdokumentieren.
