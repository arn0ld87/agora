# CONTEXT.md — Wie Agora tatsächlich arbeitet

Diese Datei erklärt die Laufzeit-Mechanik von Agora für Agenten und LLMs, die mit dem System oder seinen Artefakten arbeiten. Sie beschreibt **den verifizierten Istzustand**, nicht die Zielarchitektur. Produktbeschreibung steht in [`README.md`](README.md), Arbeitsregeln in [`AGENTS.md`](AGENTS.md), Release-Status in [`docs/STATUS.md`](docs/STATUS.md).

> **Runtime-Verifikation:** gegen `main@a3cebd38f38fc2c0043dc245766869eb05b41e0f` am 2026-08-11 geprüft. Ändert ein PR die hier beschriebene Laufzeit-Mechanik, wird `CONTEXT.md` im selben PR nachgezogen und diese Referenz aktualisiert.

> Kurzfassung: Agora zerlegt Dokumente in einen Wissensgraphen, leitet daraus geeignete Einzel- oder Kollektiv-Personas ab, lässt diese in einer OASIS-Simulation auf zwei Social-Plattformen interagieren, befragt ausgewählte Personas anschließend in separaten Tiefeninterviews und erzeugt daraus einen Bericht. **Extrahierte Claims** werden gegen Evidence gebunden; der Fließtext hat zusätzlich eine eigene, deutlich engere Prüfstrecke.

---

## 1. Vier Laufzeitphasen plus Run-Registry

Agora hat vier eigentliche Laufzeitphasen. Die Run-Registry ist die phasenübergreifende Klammer, keine fünfte Verarbeitungsphase.

| Phase | Erzeugt | ID-Präfix |
|---|---|---|
| 1 Graph-Build | Neo4j-Knoten, Relationen, Vektoren | `graph` = UUID |
| 2 Prepare | gefilterte Entitäten, Personas, Agent- und Event-Konfiguration | `sim_…` |
| 3 Simulation | Plattform-DBs, Aktionen, Posts, Kommentare, Laufzustand | `sim_…` |
| 4 Report | Sections, Evidence-Map, Agent-Trace, Exporte | `report_…` |
| Klammer | Run-Registry über alle Phasen | `run_…` |

### Phase 1 — Graph-Build

Das Quelldokument wird gechunkt. Pro Chunk läuft ein strukturierter NER-Call gegen `NerExtractionResult`; danach folgen Embeddings und die Persistenz in Neo4j.

```text
[graph_build] Chunk 12/48 (413 chars): "…"
[ingestion] NER done: 5 entities, 4 relations
[ingestion] Batch-embedding 9 texts...
[graph_build] All 48 chunks processed successfully
Graph <uuid> marked as completed
```

**Wichtig:** Das NER-Typvokabular ist nicht über Läufe stabil. Dasselbe Dokument kann mit verschiedenen Modellen oder sogar mit demselben Modell unterschiedliche Typen liefern, etwa `Lecturer`, `FreelanceInstructor`, `Organization` oder `WorksCouncilMember`. Logik, die `entity_type` als semantisch stabiles Rollenlabel behandelt, muss deshalb besonders geprüft werden. Die vollständige Bindung extrahierter Typen an die lauf-spezifische Ontologie ist auf dem oben genannten Runtime-Stand noch nicht abgeschlossen; siehe #1247.

### Phase 2 — Prepare

Prepare besteht aus mehreren Schutzstufen. Entscheidend ist, **welche Stufe welche Fehlerklasse abfängt**.

1. **Typbasierter Vorfilter.** `persona_eligibility.py` blockiert bekannte nicht-personenfähige Typen wie Stadt, Software, Datum, Konzept, Dokument oder Technologie. Unbekannte Typen werden weiterhin konservativ zugelassen; ein unbekanntes Label ist für sich allein kein Ausschlussgrund.
2. **Dedup vor dem Cap.** Kandidaten werden über den normalisierten Schlüssel `(name, entity_type)` dedupliziert. Der erste Treffer gewinnt.
3. **Typbewusster `max_agents`-Cap.** Wenn ein Cap greift, wird nicht einfach `entities[:max_agents]` verwendet. Die Auswahl läuft Round-Robin über die vorhandenen Typen, damit kleine Typgruppen nicht allein durch die Query-Reihenfolge verschwinden. Nicht ausgewählte Kandidaten bleiben als Reserve erhalten.
4. **LLM-seitige Eignungsprüfung am Namen und Kontext.** Im ohnehin stattfindenden Persona-Generierungsaufruf darf das Modell `ineligible: true` zurückgeben. Eine solche Ablehnung ist von einem Generierungsfehler getrennt (`PersonaIneligible`) und kann aus dem Reservepool nachbesetzt werden. Das schließt den beobachteten Fall, dass etwa Software, Orte oder Dokumentverweise trotz des Typs `Organization` zu Personas wurden (#1247).
5. **Persona-Art.** Individuen und Gruppen benutzen getrennte Verträge. Gruppen-/Organisationsentitäten werden als `persona_kind: collective` geführt und erhalten keine erfundene persönliche Vita mit Alter, Geschlecht, MBTI oder Beruf. Individuen bleiben `persona_kind: individual` (#1246).
6. **Identitätsangleichung bei Individuen.** Wenn der Persona-Freitext mit einem erkennbaren Personennamen beginnt, wird dieser deterministisch auf den finalen Anzeigenamen ausgerichtet. Damit bekommt der nachgelagerte Interview-Prompt nicht mehr absichtlich zwei verschiedene Identitäten für dieselbe Persona.

**Grenze der Eignungsprüfung:** Der regelbasierte/degradierte Persona-Pfad führt keine semantische LLM-Ablehnung durch. Ein LLM-Ausfall ist absichtlich nicht dasselbe wie `ineligible`; sonst würde ein Providerfehler still als fachlicher Ausschluss interpretiert. Bei Runs mit Degradierung muss deshalb `generation_source` in den finalen Profilen mitbewertet werden.

Danach erzeugt `simulation_config_generator.py` unter anderem die `initial_posts` und ordnet Poster zu. Die Reihenfolge auf dem verifizierten Runtime-Stand ist:

1. exakter Match auf `entity_name`,
2. Match auf `entity_type`,
3. bekannte Alias-Zuordnung,
4. deterministischer Round-Robin-Fallback über die Fallback-Agenten.

Der Fallback-Pool ist nach `influence_weight` absteigend und bei Gleichstand nach `agent_id` aufsteigend geordnet. Mehrere Posts dürfen legitim demselben Agenten zugeordnet sein.

### Phase 3 — Simulation

Die eigentliche OASIS/CAMEL-Simulation läuft in einem **separaten Subprozess**. Twitter und Reddit werden parallel mit derselben Simulationskonfiguration betrieben, haben aber unterschiedliche Aktionsräume.

| Plattform | Recsys | produktiv zugelassene Aktionen |
|---|---|---|
| Twitter | `twhin-bert` | `create_post`, `like_post`, `repost`, `follow`, `do_nothing`, `quote_post` |
| Reddit | `reddit` | `like_post`, `dislike_post`, `create_post`, `create_comment`, `like_comment`, `dislike_comment`, `search_posts`, `search_user`, `trend`, `refresh`, `do_nothing`, `follow`, `mute` |

Twitter kennt **keine Kommentare**. `quote_post` ist die dortige zitierende Reaktionsform; `0 comments` auf Twitter ist deshalb erwartetes Verhalten.

`max_rounds` kann die geplante Rundenzahl abschneiden:

```text
Rounds truncated: 24 -> 10
```

#### Initial-Posts werden plattformgleich gebaut

Twitter und Reddit benutzen inzwischen denselben `build_initial_post_actions(...)`-Pfad (#1245). Mehrere Seed-Posts desselben Agenten werden als mehrere Aktionen erhalten und überschreiben sich nicht mehr gegenseitig.

Der Log-Eintrag unterscheidet deshalb bewusst **Post-Anzahl** und **Zahl distinkter Poster-Agenten**:

```text
Published 9 initial posts from 1 distinct agent
```

Ein alter Lauf mit `Published 1 initial posts` kann noch aus dem früheren, fehlerhaften Zähler-/Publish-Pfad stammen und muss gegen den verwendeten Commit eingeordnet werden.

#### Twitter-Recommender ist derzeit ein bekannter Validitäts-/Reproduzierbarkeitsfehler

Auf `main@a3cebd3` ist #1236 offen: `Twitter/twhin-bert-base` ist ein MLM-Checkpoint ohne trainierten Pooler, OASIS liest aber `pooler_output`. Die fehlenden Pooler-Gewichte werden zufällig initialisiert. Das betrifft nur den Twitter-Recommender, nicht Reddit.

Bis #1236 geschlossen und mit einem Reproduzierbarkeitstest belegt ist, sind Vergleiche zwischen Twitter-Läufen mit besonderer Vorsicht zu interpretieren.

### Phase 4 — Report

Pro Section läuft ein ReAct-Loop mit vier zentralen Tools, danach folgt die Evidence-/Validierungs-Nachbearbeitung.

| Tool | Zweck |
|---|---|
| `insight_forge` | Tiefenanalyse gegen Graph/Evidence, liefert Faktenlisten |
| `panorama_search` | Breitensuche |
| `quick_search` | gezielte Einzelabfrage |
| `interview_agents` | nachgelagertes Tiefeninterview mit ausgewählten Personas |

Die Nachbearbeitung kann wesentlich länger dauern als das eigentliche Schreiben der Section. Das bekannte Performanceproblem ist in #1190 dokumentiert; eine Optimierung darf die Evidence-Gates nicht verändern.

---

## 2. Interviews sind eine zweite LLM-Befragung, keine Feed-Auswertung

`interview_agents` liest nicht einfach die Posts der Simulation zusammen. Es startet **nach der Simulation eine zweite LLM-Befragung derselben Persona-Profile**.

Typischer Ablauf:

```text
InterviewAgents deep interview (real API): <topic>
Loaded 30 profiles from reddit_profiles.json
Selected 8 Agents for interview: [15, 29, 4, 7, 21, 9, 11, 14]
Generated 4 interview questions
Calling batch interview API (dual platform): 8 Agents
Interview API returned: 8 results, success=True
```

- Der Report-Agent formuliert ein `interview_topic` und wählt Personas aus.
- Daraus werden typischerweise 4–5 Fragen erzeugt.
- Jede ausgewählte Persona wird pro Plattform befragt.
- Die Antworten werden als `agent_interview`-Evidence verarbeitet.
- Ein Zitat aus dem Bericht stammt deshalb häufig aus diesem Interview und **nicht** aus einem Simulationspost.

### Bekannte Interview-Effekte

**Frage-Echo:** Mehrere Personas können Teile derselben Frage übernehmen. Gleiche Formulierungen sind dann keine unabhängigen Beobachtungen.

**Rollenübernahme:** Der strukturelle Identitätsbruch aus #1246 ist code-seitig behoben, aber damit ist nicht bewiesen, dass jede Rollenübernahme verschwunden ist. Das `interview_topic` kann Rollen explizit nennen, und eine Persona kann weiterhin eine fremde Rolle formulieren. Die explizite Fremdrollen-Detektion für `agent_quote`-Evidence ist die noch offene Restarbeit aus #1248.

**Zitat ≠ Simulationsäußerung:** Wer ein Report-Zitat im Feed sucht und dort nicht findet, hat damit noch keinen Provenance-Fehler bewiesen. Zuerst `agent_log.jsonl` und den Evidence-Typ prüfen.

---

## 3. Evidence: Claim-Binding und Fließtextprüfung sind zwei verschiedene Dinge

Die Aussage „jede Aussage im Bericht wird geprüft" ist zu grob und soll nicht verwendet werden.

### Maschinenschicht: Claims

Aus dem Section-Text werden Claims extrahiert und gegen Evidence gebunden.

| Kategorie | Bedeutung |
|---|---|
| **Claim** | mit passender Evidence gebunden; stützende Bindung hat `entailment: SUPPORTED` |
| **Hypothese** | nicht ausreichend belegt; gehört nicht in den validierten Claim-Bestand |
| **Data Gap** | explizit benannte Informationslücke |

Typische Evidence-Typen im `evidence_index`:

```text
agent_interview     Antworten aus Phase 4
seed_document       belegbare Stellen aus dem Quelldokument
relationship_chain  Pfade im Graphen
agent_action        Simulationsaktionen
agent_post/quote    Persona-Äußerungen
graph_metric        z. B. Cluster-/Echo-Kennzahlen
web_*               optionale externe Recherche
```

Die Provenance-Schicht unterscheidet unter anderem `seed_corpus`, `agent_quote`, `agent_action`, `graph_relation`, `web_source` und `inferred`. Unbekannte Herkunft wird **nicht** automatisch zum Dokumentfakt.

### Fließtext: `verify_prose`

Die zweite Prüfstrecke ist enger:

| | Claim-Binding | `verify_prose` |
|---|---|---|
| prüft | extrahierte Claims | Sätze im Fließtext |
| Umfang | Claim-Kandidaten | derzeit nur erkannte numerische Faktenaussagen |
| Ergebnis | Claim/Hypothese/Data Gap | Satz bleibt oder wird entfernt |

`backend/app/services/report_agent/text_verification.py` entscheidet über `_has_factual_claim(...)` anhand extrahierbarer Zahlenfakten.

**Konsequenz:** Evidence-Map und ausgelieferte Prosa können auseinanderdriften. Ein qualitativer Satz wie „Die Simulation zeigt ein klares Ergebnis" wird nicht allein deshalb von `verify_prose` geprüft, weil er wie eine Tatsachenbehauptung klingt. Bei Audits deshalb immer Report **und** Evidence-Map lesen.

### Cross-Stakeholder-Confidence

Für hohe Confidence zählt nicht mehr nur der frei formulierte Jobtitel. `agent_quote`-Evidence kann `persona_role_family` tragen; dieses Label wird aus dem `source_entity_type` der Persona durchgereicht und für die Stakeholder-Diversität verwendet. Fehlt das Label, fällt der Code auf den Jobtitel zurück.

Breite Auffangtypen wie `Person`, `Organization`, `Entity`, `Node`, `Unknown` und `Other` zählen **nicht** als Rollenfamilie. Für sie wird ebenfalls der normalisierte Jobtitel verwendet (#1248). Damit werden zwei fachlich verschiedene Organisationen nicht allein wegen des gemeinsamen Fallback-Typs zu einer Stimme zusammengezogen.

**Verbleibende Grenze aus #1248:** Eine Interview-Antwort mit expliziter Fremdrollen-Zuschreibung verliert noch nicht automatisch ihre Eignung als `agent_quote`. Das Rollenfamilien-Label ist deshalb ein Diversitätsanker, aber kein vollständiger Rollenwahrheits-Validator.

### Zitat-Anker

`<simulated_quote>`-Tags tragen `persona_id` und `seed_anchor`.

Für echte Dokumentherkunft erzeugt Agora kanonische Anker der Form:

```text
seed_doc:<document_id>#chunk:<chunk_id>
```

Seit #1249 gilt `seed_doc:` **nicht mehr als Freikarte**. `validate_quote_anchors(...)` vergleicht jeden vorhandenen Anker mit `known_anchors`, unabhängig vom Präfix.

- fehlender `seed_anchor` → `invalid_quote`,
- unbekannte `persona_id` bei konfigurierter Persona-Liste → `invalid_quote`,
- vorhandener, aber nicht auflösbarer Anker → Eintrag in `unbound_evidence_refs`, das Zitat wird nicht allein deshalb verworfen,
- auflösbarer Anker → gebunden.

Das ist bewusst keine Garantie, dass jedes ausgelieferte Zitat vollständig gebunden ist. Ungebundene Referenzen bleiben sichtbar statt still akzeptiert zu werden.

**Weitere Grenze:** Sections ohne `<simulated_quote>`-Tags bestehen die Quote-Tag-Prüfung. Ein Modell kann wörtliche Persona-Formulierungen in normaler Prosa verwenden, ohne dass dieser spezielle Validator anspringt. Das ist bei Audits separat zu prüfen.

---

## 4. Wo die Artefakte liegen

Im Standard-Container `agora`:

```text
/app/backend/uploads/simulations/<sim_id>/
    simulation_config.json     agent_configs[], event_config.initial_posts[]
    run_state.json             runner_status, current_round, total_actions_count
    reddit_profiles.json       finale Persona-Profile
    twitter_simulation.db      SQLite
    reddit_simulation.db       SQLite
    simulation.log             Subprozess-Log; nicht Container-stdout

/app/backend/uploads/reports/<report_id>/
    outline.json               geplante Sections
    section_01.md … NN.md      ausgelieferter Section-Text
    evidence_map.json          Claims, Hypothesen, Data Gaps, Evidence-Index, Gates
    agent_log.jsonl            Tool-Calls und Tool-Results
    console_log.txt            Report-/Phasenprotokoll mit Heartbeats
    meta.json                  Status, Markdown, Simulation-Snapshot
```

`docker logs agora` zeigt Backend, Prepare und Report, aber nicht zuverlässig die eigentlichen Simulationsrunden. Für Phase 3 ist `simulation.log` im Simulationsverzeichnis die zentrale Quelle.

### Simulations-DB

Die Plattform-DBs enthalten unter anderem:

```sql
post(post_id, user_id, original_post_id, content, quote_content, created_at,
     num_likes, num_dislikes, num_shares, num_reports)
trace(user_id, created_at, action, info)
comment, like, dislike, comment_like, comment_dislike, follow, mute, rec, user
```

**Auswertungsfalle:** Reposts und Quotes sind eigene `post`-Zeilen mit `original_post_id`. Reine Reposts können leeres `content` tragen. Wer jede `post`-Zeile wie einen originären Text behandelt, erzeugt künstlich „leere Posts" und scheinbaren Mode-Collapse.

---

## 5. Modell-, Provider- und Embedding-Routing

Ein Run kann mehrere Modelle gleichzeitig verwenden.

| Aufgabe | strukturierter Vertrag / Pfad | typische Granularität |
|---|---|---|
| Ontologie | `OntologyDefinition` | wenige Calls |
| NER | `NerExtractionResult` | pro Chunk |
| Individual-Persona | `PersonaProfileSchema` | pro Kandidat |
| Kollektiv-Persona | `CollectivePersonaSchema` | pro Kandidat |
| Report | ReAct + Section-Pipeline | viele Calls |

Das Runtime-Log bindet Report-Routen an Provider/Modell und Run-Kontext, zum Beispiel:

```text
Report LLM route locked provider_id=google model=models/gemini-3.6-flash
  [simulation_id=…, report_id=…, project_id=…, run_id=…]
```

Strukturierte JSON-Calls laufen über `LLMClient.chat_json` mit Pydantic-Schema. Provider-Routing, JSON-Schema und Repair-Logik dürfen nicht durch lokale Parallel-Heuristiken umgangen werden; siehe [`CLAUDE.md`](CLAUDE.md) und [`AGENTS.md`](AGENTS.md).

### Embeddings haben einen getrennten Konfigurationspfad

| Pfad | Konfigurationsquelle |
|---|---|
| Graph-Ingestion | Env `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY` |
| Re-Embedding / Migration | `EmbeddingConfigurationStore` unter `AGORA_DATA_DIR` |

Die Embedding-UI ist damit nicht automatisch die Konfigurationsquelle des Graph-Builds. `VECTOR_DIM` und die Neo4j-Vektorindizes müssen zur tatsächlich verwendeten Embedding-Dimension passen.

---

## 6. Bekannte Signaturen: Status unterscheiden, nicht pauschal ignorieren

„Bekannt" bedeutet **nicht** „korrekt". Wenn eine Beobachtung bereits dokumentiert ist, zuerst Status und bestehendes Issue prüfen. Ein neuer Manifestationstyp, andere Ursache oder verletztes Akzeptanzkriterium bleibt ein legitimer neuer Befund.

| Status | Beobachtung | Einordnung |
|---|---|---|
| `handled` | `Failed to write data to connection … neo4j:7687` gehäuft um den Simulationsstart | Bekannter Fork-/Idle-Socket-Effekt; `liveness_check_timeout` und Treiber-Reconnect behandeln den erwarteten Transienten. Nur eskalieren, wenn der Run dadurch fehlschlägt oder Daten verliert. |
| `expected` | Twitter hat 0 Kommentare | Plattformmodell; Twitter nutzt `quote_post`, nicht `create_comment`. |
| `expected` | Reposts/Quotes erzeugen zusätzliche Post-Zeilen, reine Reposts teils mit leerem `content` | DB-Semantik, kein originärer Leerpost. |
| `fixed-code` | mehrere `initial_posts` mit demselben Poster | Seit #1245 werden sie für Twitter und Reddit gemeinsam aufgebaut und nicht mehr überschrieben. Aktuelles Log: `Published N initial posts from M distinct agents`. |
| `fixed-code / rerun sinnvoll` | Persona-Anzeigename und Persona-Text beschrieben verschiedene Menschen; Organisationen bekamen erfundene persönliche Viten | Strukturell in #1246 geändert: Identitätsangleichung + `individual`/`collective`. Ein produktnaher Nachlauf bleibt der relevante Wirksamkeitsnachweis. |
| `known-bug` | `pooler.dense.weight MISSING` bei `twhin-bert-base` | #1236; Twitter-Recommender nutzt auf diesem Runtime-Stand zufällig initialisierte Pooler-Gewichte. |
| `known-bug` | Evaluationsdokument enthält erwartete Antworten/Meta-Text, die später als Befund wieder auftauchen | #1240; Testfall-Hygiene und Evidence-Typisierung. Solche Runs beweisen keinen isolierten Simulationsmehrwert. |
| `known-gap` | Extrahierte `entity_type`-Werte sind nicht vollständig an die Lauf-Ontologie gebunden | Restarbeit aus #1247. Die typunabhängige Eignungsprüfung ist derzeit die tragende Schutzschicht. |
| `known-gap` | Persona antwortet im Interview ausdrücklich aus einer fremden Rolle | Restarbeit aus #1248. Der Inhalt kann erhalten bleiben, darf aber bis zur Detektion nicht unkritisch als unabhängige Rollen-Evidence interpretiert werden. |
| `fixed-code` | frei erfundene `seed_doc:`-Anker liefen ungeprüft durch | Seit #1249 werden auch `seed_doc:`-Anker gegen `known_anchors` geprüft und bei fehlender Bindung als `unbound_evidence_refs` sichtbar. |

---

## 7. Einen Run auswerten: Standardgriffe

```bash
# Phasen und IDs
docker logs agora 2>&1 | grep -E "marked as completed|Create simulation|Simulation started|Report LLM route"

# Simulationsstand
docker exec agora cat /app/backend/uploads/simulations/<sim_id>/run_state.json

# Initial-Post-Publish prüfen
docker exec agora grep -E "Published [0-9]+ initial posts" \
  /app/backend/uploads/simulations/<sim_id>/simulation.log

# Aktionsverteilung und Dislikes, Beispiel Reddit
docker exec agora python -c "
import sqlite3,collections
c=sqlite3.connect('file:/app/backend/uploads/simulations/<sim_id>/reddit_simulation.db?mode=ro',uri=True)
print(collections.Counter(r[0] for r in c.execute('select action from trace')))"

# Persona-Arten und Degradierungen prüfen
docker exec agora python -c "
import json,collections
p=json.load(open('/app/backend/uploads/simulations/<sim_id>/reddit_profiles.json'))
print('kind', collections.Counter(x.get('persona_kind','legacy') for x in p))
print('source', collections.Counter(x.get('generation_source','llm') for x in p))"

# Evidence-Bilanz
docker exec agora python -c "
import json
m=json.load(open('/app/backend/uploads/reports/<report_id>/evidence_map.json'))
for s in m['sections']:
    print(s['section_index'], len(s.get('claims') or []), len(s.get('hypotheses') or []))"

# Woher stammt eine konkrete Formulierung?
docker exec agora grep -o '.\{200\}SUCHTEXT.\{100\}' \
  /app/backend/uploads/reports/<report_id>/agent_log.jsonl
```

Der letzte Griff ist für Forensik der wichtigste: **`agent_log.jsonl` enthält Tool-Calls und Tool-Results.** Damit lässt sich feststellen, ob eine Formulierung aus einem Interview, aus Graph-/Seed-Evidence, aus Web-Recherche oder aus einer anderen Report-Stufe stammt.

Für eine belastbare Bewertung eines Runs nicht nur auf `runner_status: completed` schauen. Mindestens zusätzlich prüfen:

- finale Persona-Profile und `generation_source`,
- Zahl und Verteilung der publizierten Initial-Posts,
- Aktionsverteilung beider Plattformen,
- Claims/Hypothesen/Data Gaps,
- `unbound_evidence_refs` und Quote-Tags,
- ob Kernaussagen bereits im Seed-Dokument standen,
- bei Vergleichsläufen die Reproduzierbarkeitsgrenzen aus #1236 und #763.

---

## 8. Was Agora nicht ist

- **Keine Verhaltensprognose.** Die Personas sind synthetische, dokumentbasierte LLM-Konstrukte und keine repräsentative Stichprobe.
- **Kein Ersatz für reale Interviews, Nutzertests oder historische Vergleichsdaten.** Agora kann Hypothesen, Konfliktlinien und Datenlücken erzeugen, nicht reale Reaktionen garantieren.
- **Keine Garantie, dass jedes Zitat hart gebunden ist.** Unauflösbare vorhandene Anker werden sichtbar als `unbound_evidence_refs` geführt; ungetaggte wörtliche Prosa fällt nicht automatisch in den Quote-Validator.
- **Kein Nachweis des Simulationsbeitrags, wenn der Seed die Antworten bereits enthält.** Das ist der Kern von #1240.
- **Noch kein vollständig reproduzierbares Experiment-System.** Run-Manifest/Replay (#763) und der Twitter-Recommender (#1236) sind dafür relevante offene Punkte.
- **Noch keine systematisch kalibrierte Überlegenheit gegenüber einfacheren LLM-Baselines.** Diese Messung gehört zu #765 und muss auch negative Ergebnisse enthalten.

Die Referenzläufe unter [`docs/reference-runs/`](docs/reference-runs/) dokumentieren bewusst nicht nur erfolgreiche Ergebnisse, sondern auch Fehlerklassen und Grenzen. Genau dafür sind sie wertvoll.
