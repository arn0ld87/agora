# CONTEXT.md — Was Agora kann und wie es arbeitet

Orientierung fuer Agenten die mit Agora-Code, -Artefakten oder -Laeufen arbeiten.

> **Verifiziert gegen:** `main@39b65297` am 2026-08-14, anhand von `report_3c594fcc7613` (Stakeholder-Analyse KI-Klinikrollout, 6 Sections, 20 Simulationsrunden).

---

## Was Agora tut

Agora nimmt ein Quelldokument (Strategiepapier, Entscheidungsvorlage, Produktkonzept) und simuliert, wie verschiedene DACH-Stakeholdergruppen darauf reagieren wuerden. Das Ergebnis ist ein evidenzgebundener Bericht mit zitierbaren Persona-Aussagen, Hypothesen und explizit benannten Datenluecken.

**Typisches Szenario:** Ein Aufsichtsrat muss ueber den Rollout eines KI-Systems entscheiden. Agora extrahiert die relevanten Akteure aus dem Dokument, generiert demographisch und fachlich differenzierte Personas (Aerzte, Betriebsrat, Pflegekraefte, IT-Leitung, Qualitaetsmanagement), laesst sie 20 Runden auf simulierten Social-Plattformen diskutieren, befragt ausgewaehlte Personas anschliessend in Tiefeninterviews und erzeugt einen Bericht, in dem jede Kernaussage an konkrete Simulationsevidenz gebunden ist.

**Was Agora nicht ist:**
- Keine Verhaltensprognose — Personas sind synthetische LLM-Konstrukte
- Kein Ersatz fuer reale Interviews oder Nutzertests
- Confidence bewertet Evidenzbindung im System, nicht Welt-Wahrheit

---

## Die Pipeline: vier Phasen

```
Quelldokument → [1 Graph] → [2 Prepare] → [3 Simulation] → [4 Report]
                    ↓             ↓              ↓               ↓
              Neo4j-Graph    Personas      Plattform-DBs    Evidence-Map
              + Vektoren     + Config      + Traces         + Bericht
```

### Phase 1 — Graph-Build

Das Dokument wird gechunkt. Pro Chunk: NER-Extraktion (`NerExtractionResult`), Embedding, Persistenz in Neo4j. Ergebnis: ein Wissensgraph mit Entitaeten, Relationen und Vektorindizes.

**Wichtig:** `entity_type` ist nicht ueber Laeufe stabil. Dasselbe Dokument kann je nach Modell unterschiedliche Typen liefern. Logik die `entity_type` als stabiles Label behandelt muss geprueft werden.

### Phase 2 — Prepare

Aus dem Graph werden Personas abgeleitet. Sechs Schutzstufen filtern ungeeignete Kandidaten:

1. **Typfilter** — blockiert nicht-personenfaehige Typen (Stadt, Software, Datum)
2. **Dedup** — normalisierter Schluessel `(name, entity_type)`
3. **Typbewusster Cap** — Round-Robin ueber Typen statt einfaches Abschneiden
4. **LLM-Eignungspruefung** — Modell kann `ineligible: true` zurueckgeben
5. **Persona-Art** — `individual` (mit Vita) vs. `collective` (ohne erfundene Biografie)
6. **Identitaetsangleichung** — Name wird auf Anzeigenamen ausgerichtet

Danach erzeugt `simulation_config_generator.py` die Agent-Konfiguration, Initial-Posts und Event-Config.

### Phase 3 — Simulation

OASIS/CAMEL laeuft als Subprozess. Twitter und Reddit parallel mit denselben Personas, aber unterschiedlichen Aktionsraeumen:

| Plattform | Charakter |
|-----------|-----------|
| Twitter | Posts, Likes, Reposts, Quotes. Keine Kommentare — `quote_post` ist die zitierende Reaktion. |
| Reddit | Volle Diskussionsstruktur: Posts, Kommentare, Up-/Downvotes, Suche. |

Typisch: 10–20 Runden. Jede Runde: jeder Agent waehlt eine Aktion basierend auf seinem Feed und Persona-Profil.

### Phase 4 — Report

Drei Stufen erzeugen den Bericht:

**Planning:** Ein LLM-Call erzeugt den Report-Plan mit 4–8 benannten Sections.

**Section-ReAct:** Pro Section ein iterativer Loop (3–5 Iterationen) mit vier Tools:
- `insight_forge` — Tiefenanalyse gegen Graph + Evidence
- `panorama_search` — Breitensuche ueber alle Quelltypen
- `quick_search` — gezielte Einzelabfrage
- `interview_agents` — Tiefeninterview mit ausgewaehlten Personas (zusaetzliche LLM-Befragung, keine Feed-Auswertung)

**Phase-Timing:** Claim-Extraktion, Evidence-Binding, Fliesstext-Verifikation, Gate-Checks.

---

## Evidence-Modell

Jede Aussage im Bericht wird gegen zwei getrennte Pruefstellen geprueft:

### 1. Claim-Binding (maschinell)

Claims werden extrahiert und gegen Evidence gebunden:
- **Claim** — mit `entailment: SUPPORTED` gebunden
- **Hypothese** — nicht ausreichend belegt
- **Data Gap** — die Information liegt in *keiner* verfuegbaren Quelle vor

Evidence-Typen: `agent_interview`, `seed_document`, `relationship_chain`, `agent_action`, `graph_metric`, `web_search_result`

Die Kandidatensuche laeuft zweigleisig: embedding-basiert fuer Fliesstext und
deterministisch fuer Zahlen (`numeric_evidence.py`). Eine Quelle, die dieselbe
Zahl in derselben Einheit nennt, ist immer Kandidat — auch unterhalb der
Cosine-Schwelle. Ob sie den Claim *belegt*, entscheidet unveraendert das
Entailment.

**Data Gap ist eine Aussage ueber die Quellenlage, nicht ueber den Matcher.**
Scheitert die Bindung, obwohl die Information in den Quellen steht, ist das ein
`binding_failure`: die Aussage wird als Hypothese gefuehrt, der Grund steht im
`gate_decision_log`, ein Data Gap entsteht nicht. Nur
`source_information_absent` wird als `DataGap` exportiert
(`report_agent/data_gap.py`).

**Coverage-Ledger.** Jeder quantitative Fakt aus einem Tool-Ergebnis traegt im
`evidence_coverage_ledger` der Evidenzkarte entweder eine kanonische
Evidence-ID oder einen Verwerfungsgrund (`duplicate`, `missing_producer_key`,
`validation_error:…`). Ein Fakt darf verworfen werden — nur nicht wortlos.

### 2. Fliesstext-Verifikation (`verify_prose`)

Engere Pruefung: erkennt numerische Faktenaussagen im Text und entfernt sie bei fehlender Deckung. Qualitative Saetze durchlaufen diesen Validator nicht — deshalb koennen Evidence-Map und ausgelieferte Prosa auseinanderdriften.

Ein abweichender Zahlenwert allein ist kein Widerspruch. Vor einem
`CONTRADICTED` prueft `facts_are_comparable`, ob beide Zahlen ueberhaupt
denselben Sachverhalt betreffen: gleiche Einheit, gleiche Faktenart
(Ist-Wert / Zielwert / Mindest- oder Hoechstgrenze) und gleiche
Teilpopulation. Ein Ist-Wert einer Teilgruppe widerlegt keine
Mindestanforderung an die Gesamtheit.

Wird ein Satz entfernt, bleibt die Aufzaehlung, in der er stand, lueckenlos —
fuer nummerierte Listen und fuer ausgeschriebene ("Erstens … Zweitens …").

### 3. Zuschreibung (`attribution_guard`)

Der Text darf die Simulation nur als Zeugen anrufen, wenn Simulations-Evidence
vorliegt, und Interviews nur, wenn welche stattfanden. Fehlt die Grundlage,
wird die Zeugenformel ersetzt ("Die Simulation zeigt" → "Die Quellenlage
zeigt") — die Aussage selbst bleibt unangetastet. Konsenssprache
("durchweg", "einhellig") wird gemeldet, aber nicht umgeschrieben.

### Zitat-Anker

`<simulated_quote persona_id="..." seed_anchor="<anker>">` — jeder Anker wird gegen `known_anchors` geprueft, unabhaengig von seinem Praefix (#1249). `seed_anchor` ist ein Prompt-Attribut, kein Contract-Feld; das Vertragsfeld heisst `source_id_anchor`.

Welche Form der Anker traegt, haengt an der Herkunft des Belegs:

| Herkunft | `source_kind` | Ankerform |
|---|---|---|
| Interview-Aussage (Phase 4) | `agent_quote` | `ev_<id>` — die Evidence-ID, die der `interview_agents`-Ergebnistext unter jeder Antwort ausweist |
| Dokumentstelle aus der Aufnahme | `seed_corpus` | `seed_doc:<doc_id>#chunk:<chunk_id>` (ADR-0013) |

Andere Quellengattungen (`agent_action`, `graph_relation`, `web_source`) tragen die Kennung, die ihr Produzent vergibt; geprueft wird nur, ob sie in `known_anchors` steht.

Seit #1300 verbieten die Validatoren `agent_quote_rejects_seed_doc_anchor` einen `seed_doc:`-Anker auf `agent_quote`-Evidence: eine Interview-Aussage steht in keinem Seed-Dokument, ein solcher Anker waere erfunden. Zitatquellen sind haeufig Interviews (Phase 4), nicht Simulationsposts (Phase 3) — die `ev_`-Form ist deshalb der Regelfall, nicht die Ausnahme.

Zitiert ein Abschnitt einen Anker, der in keiner Bindung auftaucht, steht er seit #1324 als `unbound_evidence_refs` an der Section im persistierten Artefakt — vorher nur im Log.

### Cross-Stakeholder-Confidence

Hohe Confidence erfordert Diversitaet: verschiedene `persona_role_family`-Werte (aus `source_entity_type`). Generische Auffangtypen (`Person`, `Organization`, `Unknown`) zaehlen nicht als eigenstaendige Stimme.

---

## Was ein Run produziert

```
uploads/simulations/<sim_id>/
    simulation_config.json    Personas, Events, Plattform-Config, LLM-Modell
    reddit_profiles.json      Finale Persona-Profile mit persona_kind + generation_source
    run_state.json            runner_status, current_round
    reddit_simulation.db      SQLite: posts, comments, traces, likes
    twitter_simulation.db     SQLite: posts, traces, likes, reposts
    simulation.log            Subprozess-Log (primaere Quelle fuer Phase 3)

uploads/reports/<report_id>/
    meta.json                 Status, Simulation-Snapshot, Timestamps
    outline.json              Geplante Sections mit Titeln
    evidence_map.json         Claims, Hypothesen, Data Gaps, Gate-Entscheidungen
                              (schema_version: 3, evidence_index, sections[], degradation_log)
    progress.json             Aktueller Fortschritt waehrend Generierung
    agent_log.jsonl           Tool-Calls und -Results (Forensik-Primaerquelle)
```

**DB-Semantik:** Reposts/Quotes sind eigene `post`-Zeilen mit `original_post_id`. Reine Reposts koennen leeres `content` haben — nicht jede Zeile ist originaerer Text.

---

## Interviews: eine zweite Befragung

`interview_agents` im Report-ReAct liest nicht den Feed zusammen. Es startet eine **zusaetzliche LLM-Befragung** anhand der Persona-Profile. Zwei Transportpfade:

- **IPC** (lebender Worker): ueber `SimulationIPCClient`
- **Direct** (terminaler Run): im Flask-Prozess ueber `LLMClient`

Das bedeutet: ein Zitat im Bericht stammt haeufig aus diesem Interview, nicht aus einem Simulationspost. Wer eine Formulierung im Feed sucht und nicht findet, hat keinen Provenance-Fehler bewiesen — erst `agent_log.jsonl` und den Evidence-Typ pruefen.

---

## Simulation-Lifecycle (FSM)

```
CREATED → PREPARING → READY → RUNNING → COMPLETED
                ↓         ↓        ↓
              FAILED    FAILED   PAUSED → RUNNING
                ↑                   ↓
                └── (retry) ───────┘    STOPPED → RUNNING
                                        CANCELLED_PARTIAL → COMPLETED
```

Terminal: `COMPLETED`, `FAILED`. Doppelter Prepare bei aktivem Task = HTTP 409.

---

## Modell- und Provider-Routing

Ein Run kann mehrere Modelle gleichzeitig verwenden (NER, Personas, Report jeweils eigene Route). Strukturierte JSON-Calls laufen ueber `LLMClient.chat_json` mit Pydantic-Schema. Provider-Detection: `registry.py::detect_provider`.

Embeddings haben einen getrennten Konfigurationspfad (Env-Vars fuer Graph-Build, `EmbeddingConfigurationStore` fuer Migration).

---

## Bekannte Signaturen

„Bekannt" ≠ „korrekt". Ein neuer Manifestationstyp bleibt ein neuer Befund.

| Status | Beobachtung |
|--------|-------------|
| `expected` | Twitter: 0 Kommentare (nutzt `quote_post`) |
| `expected` | Reposts erzeugen Post-Zeilen mit leerem content |
| `handled` | Neo4j-Socket-Fehler beim Simulationsstart (Reconnect) |
| `fixed-code` | Identitaetsbruch bei Personas (#1246), parallele Prepares (#1271), seed_doc-Anker ungeprüft (#1249) |
| `known-bug` | Twitter-Recommender: zufaellige Pooler-Gewichte (#1236) |
| `known-gap` | entity_type nicht an Ontologie gebunden (#1247), Fremdrollen-Interview nicht detektiert (#1248) |

---

## Grenzen

- Kein Nachweis des Simulationsbeitrags wenn der Seed die Antworten bereits enthaelt (#1240)
- Noch kein reproduzierbares Experiment-System (Run-Manifest #763, Twitter-Recommender #1236)
- Nicht jedes Zitat ist hart gebunden — unaufloesbare Anker werden als `unbound_evidence_refs` sichtbar gefuehrt
- Claim-Dedup erkennt Umstellungen, keine Synonyme: "erreichte 54 %" und "liegt bei 54 %" bleiben zwei Claims. Eine Aussage faelschlich zu verschmelzen waere teurer als eine Dublette
- Domaenen-Kohaerenz prueft gegen ein kleines Fachlexikon (Klinik, Fertigung, Bildung, Logistik, Finanzen); Branchen ausserhalb davon werden nicht erkannt
- Single-User, kein Multi-Tenant vor 1.0.0
