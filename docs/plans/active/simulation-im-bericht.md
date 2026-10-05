# Plan: Die Simulation trägt zum Bericht bei

Stand 2026-10-04. Issue: #1778 (Etappe 1 und 3) und #1779 (Etappe 2). Grundlage: Auswertung des Laufs `sim_c8c6b30aa652` auf gns3 und die Abstimmung mit dem Maintainer am selben Tag.
Basis-Commit für alle Anker: `origin/main` = `db5a40e3`. Zeilennummern gelten für diesen Commit.

Dieser Plan ist für ausführende Modelle `glm-5.3` und `glm-5.3-flash` geschrieben. Jeder Schritt nennt das Modell, die Dateien, einen wörtlichen Anker, die Änderung, die Tests, den Prüfbefehl und was verboten ist.

---

## 0. Regeln für das ausführende Modell (vor jedem Schritt lesen)

1. **Ein Schritt = ein Commit.** Bearbeite genau den Schritt, der dir genannt wird. Fange keinen weiteren an.
2. **Anker zuerst prüfen, mit CRG und context-mode. Kein `grep`, kein `rg`, kein `cat`, kein `sed`.** Jeder Schritt hat eine Anker-Tabelle (Symbol, Datei, Zeile, wörtlicher Text). Ablauf je Zeile der Tabelle:
   1. **Symbol finden mit CRG:** `semantic_search_nodes_tool(query="<Symbol>")`. Die gemeldete Datei muss die Datei aus der Tabelle sein.
   2. **Wörtlichen Text bestätigen mit context-mode:** `ctx_execute_file(path="<Datei>", language="python", code=...)`. Der Code gibt nur die Zeilen aus, die den wörtlichen Text enthalten, mit Zeilennummer. Beispiel (der Name der Variable mit dem Dateiinhalt steht in der Werkzeugbeschreibung):
      ```python
      for nr, zeile in enumerate(FILE_CONTENT.splitlines(), 1):
          if "<wörtlicher Text>" in zeile:
              print(nr, zeile.strip())
      ```
   3. Ist der wörtliche Text nicht in der Datei, **höre auf und melde „Anker nicht gefunden: <Text>"**. Rate nicht, suche keine „ähnliche" Stelle. Eine Zeilennummer, die um bis zu 30 Zeilen abweicht, ist in Ordnung, solange der Text stimmt.
   4. Liefert CRG nichts, heißt das nicht, dass das Symbol fehlt: Der Graph kann veraltet sein. Dann entscheidet Punkt 2. Bei Widerspruch zwischen Graph und Quelltext gilt der Quelltext.
   - **Aufrufer suchen:** `query_graph_tool(pattern="callers_of", target="<Symbol>")`.
   - **Tests suchen:** `query_graph_tool(pattern="tests_for", target="<Symbol>")`.
   - **Was hängt daran:** `get_impact_radius_tool(file_path="<Datei>")`.
   - **`Read`** nur für die Datei, die du gleich mit `Edit` änderst, und nur den Bereich um die Stelle (`offset`, `limit`).
   - **Prüfbefehle** laufen über `ctx_execute(language="shell", code="<Befehl>")`. In deinen Bericht gehören nur Exit-Code und die letzten Zeilen.
3. **Nur die genannten Dateien ändern.** Brauchst du eine weitere Datei, höre auf und melde, welche und warum.
4. **Verträge zuerst.** Ändert ein Schritt ein Modell unter `backend/app/contracts/`, dann in dieser Reihenfolge: Vertrag, `dump_schemas` rendern, Zod-Spiegel im Frontend, erst dann der Code, der den Vertrag benutzt.
5. **Diese fünf Dinge fasst du nie an**, außer ein Schritt nennt sie ausdrücklich:
   - den Block `<evidence_gating priority="hard">` in `backend/app/services/report_prompts/sections.py`
   - `backend/tests/eval/snapshots/evidence-gating-hedge-words.txt`
   - das Enum `EvidenceSourceKind` in `backend/app/contracts/report_contract.py`
   - den Validator `cross_stakeholder_for_high`
   - den Validator `reject_inferred_in_high_confidence`
6. **Tests nie abschwächen.** Kein `skip`, kein `xfail`, keine gelöschte Assertion, kein `# pragma: no cover`. Wird ein bestehender Test rot und der Schritt sagt nicht ausdrücklich, dass er angepasst wird: aufhören und melden.
7. **Kein `print()`.** Logging über `logger`.
8. **Kein roher OpenAI-Client.** LLM-Aufrufe mit strukturiertem Ergebnis nur über `LLMClient.chat_json` mit Pydantic-Schema.
9. **Nicht pushen, keinen PR öffnen, kein Issue anlegen.** Du committest lokal. Der Lead prüft und pusht.
10. **Nur die Tests laufen lassen, die der Schritt nennt.** Keine Full-Suite.
11. **Sprache:** Kommentare, Docstrings, Commit-Message und Fehlermeldungen für Nutzer auf Deutsch mit echten Umlauten. Bezeichner im Code auf Englisch, wie im Bestand.
12. **Arbeitsverzeichnis:** Nutze das Verzeichnis, das `pwd` dir zeigt. Verwende absolute Pfade, die mit diesem Verzeichnis beginnen. Wechsle nie in `/Volumes/T7/Projekte/agora`.
13. **Bericht am Ende jedes Schritts**, genau in dieser Form:
    ```
    Schritt: <Nummer>
    Commit: <Hash>
    Geänderte Dateien: <Liste>
    Prüfbefehle und Ergebnis: <Befehl> -> <Exit-Code, letzte Zeile>
    Abweichungen vom Plan: <keine | Beschreibung>
    ```

### Standard-Prüfbefehle

Jeden dieser Befehle über `ctx_execute(language="shell", code="...")` ausführen, nicht direkt in `Bash`. `Bash` ist nur für `git` (status, add, commit).

```bash
# Backend, nach jedem Backend-Schritt
cd backend && uv run pytest <die im Schritt genannten Testdateien> -x -q
cd backend && uv run ruff check . && uv run mypy app

# Wenn ein Vertrag geändert wurde
cd backend && uv run python -m app.contracts.dump_schemas          # rendert schemas/
cd backend && uv run python -m app.contracts.dump_schemas --check  # muss Exit 0 liefern
cd backend && uv run pytest tests/contracts/ -x -q

# Frontend, nach jedem Frontend-Schritt
cd frontend && bun run test <die im Schritt genannten Spec-Dateien> && bun run check
```

### Begriffe (verbindlich, stehen auch in `CONTEXT.md`)

| Begriff | Bedeutung | Bezeichner im Code |
|---|---|---|
| Beleg | ein einzelner Evidence-Eintrag | Evidence-Item |
| Stimme | eine Persona, egal über wie viele Belege und Kanäle | `voice_key` |
| Quellenart | Seed, Graph, Simulation, Interview, Web | `source_kind` |
| Streitfrage | bejah- oder verneinbare Aussage des Laufs, höchstens eine | `contested_question` |
| Haltung | Position einer Stimme zur Streitfrage: dafür, dagegen, unentschieden | `stance_class`: `in_favour`, `opposed`, `undecided` |
| Positionswechsel | andere Haltungsklasse am Ende als am Anfang, belegt durch einen Simulationsbeitrag | `position_shift` |
| Haltungsabweichung | Anfang und Ende verschieden, aber kein Beitrag belegt es | `stance_deviation` |
| Lager | alle Stimmen mit derselben Haltungsklasse | `camp` |
| Koalition | mindestens zwei Stimmen aus verschiedenen Rollenfamilien, gleiche Haltung, zustimmender Bezug in der Simulation | `coalition` |
| Positionierungsquote | Anteil der Stimmen mit mindestens einem Simulationsbeitrag der Haltung dafür oder dagegen | `positioning_ratio` |
| Lagerverteilung | Verteilung der positionierten Stimmen auf die Lager | `camp_distribution` |

Abbildung der bestehenden Konfigurationswerte: `supportive` = dafür, `opposing` = dagegen, `neutral` und `observer` = unentschieden. Die bestehenden Literale werden **nicht** umbenannt.

---

## 1. Entscheidungen des Maintainers (2026-10-04)

1. Ein Bericht entsteht aus Simulation **und** Interviews. Dass fast kein Claim auf Simulationsaktionen beruht (B8), ist ein Defekt.
2. Der Report-Agent bekommt ein Werkzeug für Simulationsaktionen, und es gibt eine Verlaufsanalyse. Beides in einem Issue.
3. Unabhängigkeit hängt an der Stimme, nicht am Kanal. Post und Interview derselben Persona sind eine Stimme. Zwei Personas sind zwei Stimmen, der Ein-Quellen-Deckel fällt, höchstens `medium`. Seed plus eine Stimme sind zwei Quellenarten, der Deckel fällt. `high` bleibt unverändert an Anker 4 gebunden.
4. Positionswechsel und Koalitionen bleiben Pflichtaspekte, sofern der Lauf eine Streitfrage hat. Frühwarnindikatoren bleiben Pflicht für alle vier entscheidungsorientierten Berichtsarten. Stop- und Expand-Bedingungen sind nur Pflicht, wenn die Fragestellung einen Piloten oder eine stufenweise Einführung betrifft.
5. `speculative` wird fünfte Stufe im Enum `ConfidenceLabel`, mit Eintrag in `docs/decisions/0002-supersedes.md`. **Ausdrücklich freigegeben.**
6. Standard-Deckel der Simulation bleibt 20 Mio. Tokens und zählt nur ungecachte Eingabe-Tokens. Die Warnung zum Tageslimit des Anbieters kommt getrennt in #1772.
7. Positionierungsquote wird an den Simulationsbeiträgen gemessen, nicht an Interviews. Unter 50 % (konfigurierbarer Standardwert) ist es eine Degradation. Die Lagerverteilung ist nie eine Degradation.
8. Jeder Lauf hat höchstens eine Streitfrage. Der Konfigurations-Assistent schlägt sie vor, sie ist sichtbar und änderbar.
9. Ein großes Issue für alles hier. Die Farblosigkeit der Simulation bekommt ein eigenes Issue (freigegeben). Übrige Befunde gehen als Punkte in #1766 und #1772.
10. Drei Etappen mit je einem Abnahmelauf auf dem Seed `seed-3-geburtshilfe-hollerau.md`.

### Messwerte, auf denen der Plan beruht (Lauf `sim_c8c6b30aa652`, Bericht `report_61cbeadf1b08`)

- 164 stützende Belege: 155 Interview, 6 Seed, 3 Simulationsaktionen. 68 von 86 Claims exakt bei 0,59.
- 426 Beiträge mit Text. Stichwortsuche: 10 ablehnend, 0 zustimmend, 313 abwägend.
- Startkonfiguration (54 Agenten): 11 `opposing`, 5 `supportive`, 13 `neutral`, 25 `observer`.
- Interviewhaltung am Ende (50 Personas): 34 dagegen, 4 dafür, 12 unentschieden.
- Die Haltung hat keinen festen Bezug: AfD `opposing` mit `sentiment_bias` +0,65 und Interview +0,9; Samtgemeinde Ohlendorf `supportive` mit -0,4 und Interview -0,7.
- 54 Agenten, 50 Profile.

---

## 2. Etappe 1: Messen (erster PR des großen Issues)

Branch: `feat/1778-simulation-im-bericht-1`. Reihenfolge der Schritte einhalten.

### Schritt 1.1 · `speculative` als fünfte Stufe in `ConfidenceLabel`

- **Modell:** `glm-5.3` (berührt den Drift-Guard zu ADR-0002).
- **Ziel:** Der Rechner liefert bereits `speculative` für Scores unter 0,45. Das Enum lehnt den Wert ab, deshalb werden solche Claims heute nachträglich auf `low` gesetzt und füllen das Degradationsprotokoll.
- **Anker** (prüfen nach Regel 2):
  | Symbol | Datei | Zeile | wörtlicher Text |
  |---|---|---|---|
  | `ConfidenceLabel` | `backend/app/contracts/report_contract.py` | 41 | `class ConfidenceLabel(str, Enum):` (darunter genau vier Werte: `low`, `medium`, `high`, `verified`) |
  | `test_confidence_label_enum_stufen` | `backend/tests/eval/test_evidence_gating_snapshot.py` | 121 | `assert stufen == {"low", "medium", "high", "verified"}` |
  | `_ConfidenceKey` | `backend/app/contracts/branch_comparison.py` | 39 | `_ConfidenceKey = Literal["low", "medium", "high", "verified"]` |
  | `_CONFIDENCE_KEYS` | `backend/app/services/compare_service.py` | 33 | `_CONFIDENCE_KEYS = ("low", "medium", "high", "verified")` |
- **Änderungen:**
  1. `backend/app/contracts/report_contract.py`: im Enum `ConfidenceLabel` als **erste** Zeile `speculative = "speculative"` einfügen. Sonst nichts an dem Enum ändern.
  2. `backend/tests/eval/test_evidence_gating_snapshot.py`, Test `test_confidence_label_enum_stufen`: die erwartete Menge auf `{"speculative", "low", "medium", "high", "verified"}` ändern. **Das ist die einzige erlaubte Änderung an dieser Datei.** Sie ist vom Maintainer freigegeben.
  3. `docs/decisions/0002-supersedes.md`: am Ende einen Abschnitt anhängen:
     - Überschrift `## 2026-10-04: Stufe speculative im Enum ConfidenceLabel`
     - Inhalt in drei Sätzen: Das Enum bekommt die Stufe `speculative` unterhalb von `low`. Grund: Rechner, ReportV3-Vertrag, Prompt-Block (`max_confidence="speculative"`) und Frontend kennen sie bereits, nur das Enum nicht; acht Claims je Bericht wurden deshalb fälschlich auf `low` gesetzt. Kein Validator für `high` oder `verified` ändert sich. Freigabe: Maintainer, 2026-10-04.
  4. `backend/app/contracts/branch_comparison.py` Zeile 39 (`_ConfidenceKey = Literal["low", "medium", "high", "verified"]`) und `backend/app/services/compare_service.py` Zeile 33 (`_CONFIDENCE_KEYS = ("low", "medium", "high", "verified")`): jeweils `"speculative"` vorne ergänzen.
  5. Schemas rendern: `cd backend && uv run python -m app.contracts.dump_schemas`. Erwartet geänderte Dateien: `schemas/report-contract.schema.json`, `schemas/evidence-map.schema.json`, `schemas/evidence-map-response.schema.json`, `schemas/branch-comparison.schema.json`. Ändert sich eine andere Schema-Datei: aufhören und melden.
  6. Prüfen, ob ein Validator in `report_contract.py` `speculative` falsch behandelt: Lass dir mit `ctx_execute_file` alle Zeilen der Datei ausgeben, die `ConfidenceLabel.low` enthalten. Erwartet u. a. Zeile 465 und 636: `if self.confidence_label != ConfidenceLabel.low and not self.evidence:`. Diese Bedingung muss `speculative` wie `low` behandeln. Ändere beide Stellen zu `if self.confidence_label not in (ConfidenceLabel.speculative, ConfidenceLabel.low) and not self.evidence:`.
- **Neue Tests** in `backend/tests/contracts/test_confidence_semantics.py` (anhängen):
  - `test_speculative_claim_passes_contract`: ein `ReportClaimModel` mit `confidence_label="speculative"`, `confidence_score=0.3` und einem stützenden Beleg validiert ohne Fehler.
  - `test_speculative_claim_without_evidence_passes`: dasselbe ohne Beleg validiert ohne Fehler.
- **Neuer Regressionstest** in `backend/tests/contracts/test_evidence_degradation.py` (anhängen): Ein Abschnitt mit einem Claim `confidence_label="speculative"`, Score 0,3, läuft durch `degrade_sections_for_violations` und behält `speculative`; das zurückgegebene Degradationsprotokoll enthält **keinen** Eintrag mit `violation` gleich `enum` für diesen Claim. Lies vorher einen vorhandenen Test in dieser Datei und übernimm dessen Aufbau.
- **Frontend:** nichts zu tun. `frontend/src/contracts/reportContract.ts:21` kennt `speculative` schon.
- **Prüfbefehl:**
  ```bash
  cd backend && uv run pytest tests/contracts/ tests/eval/test_evidence_gating_snapshot.py tests/services/test_compare_service.py tests/test_confidence_calculator.py -x -q
  cd backend && uv run python -m app.contracts.dump_schemas --check && uv run ruff check . && uv run mypy app
  ```
- **Nicht tun:** keinen der fünf Anker aus Regel 5 anfassen; `report_agent/schemas.py:103` (Kernaussagen, drei Werte) nicht ändern; `apply_claim_type_floor` nicht ändern.
- **Dokumentation im selben Commit:** `changelog.d/1778-speculative-stufe.md` (zwei Sätze) und ein Satz in `docs/STATUS.md` im Abschnitt zum Bericht.

### Schritt 1.2 · Stimme als Feld am Beleg (Vertrag)

- **Modell:** `glm-5.3` (Vertrag, Schema, Zod).
- **Ziel:** Jeder Beleg aus Interview oder Simulationsaktion trägt, von welcher Persona er stammt, in einem einheitlichen Feld `voice_key`.
- **Anker** (prüfen nach Regel 2):
  | Symbol | Datei | Zeile | wörtlicher Text |
  |---|---|---|---|
  | `EvidenceItemModel` | `backend/app/contracts/report_contract.py` | ~236 | `persona_stakeholder_group: Optional[str] = Field(` |
  | `EvidenceRecordModel` | `backend/app/contracts/report_contract.py` | ~317 | `persona_stakeholder_group: Optional[str] = Field(` (zweiter Treffer derselben Zeile) |
  | `AgentInterview` | `backend/app/services/graph/graph_dtos.py` | 334 | `class AgentInterview` |
  | `_record_tool_evidence` | `backend/app/services/report_agent/agent.py` | 703 | `"type": "agent_interview",` |
  | `_collect_simulation_evidence_items` | `backend/app/services/report_agent/agent.py` | ~487 | `type="agent_action",` |
- **Änderungen:**
  1. `backend/app/contracts/report_contract.py`: in `EvidenceItemModel` **und** `EvidenceRecordModel` direkt unter `persona_stakeholder_group` ein Feld ergänzen:
     ```python
     #: Stimme: eindeutiger Schlüssel der Persona, von der der Beleg stammt.
     #: Form ``agent:<agent_id>``. ``None`` bei Belegen ohne Persona (Seed, Graph, Web).
     voice_key: Optional[str] = Field(default=None, max_length=64, pattern=r"^agent:\d+$")
     ```
  2. `backend/app/services/graph/graph_dtos.py`, Klasse `AgentInterview`: Feld `agent_id: Optional[int] = None` ergänzen und in `to_dict` als `"agent_id": self.agent_id` ausgeben.
  3. `backend/app/services/graph_tools.py`: an der Stelle, an der `AgentInterview(` gebaut wird (CRG: `query_graph_tool(pattern="callers_of", target="AgentInterview")`; erwartet in `GraphToolsService.interview_agents`, Bereich Zeile 520-550, dort steht auch `topic_stance=topic_stance,`), `agent_id=agent_idx` setzen. `agent_idx` ist die Schleifenvariable an dieser Stelle (Anker: Zeile 459, Text `for i, agent_idx in enumerate(selected_indices):`; dieselbe Variable geht in Zeile 427 als `"agent_id": agent_idx,` an das Interview). **Geprüft am Lauf `sim_c8c6b30aa652`:** Der Listenindex der Profile ist für alle 50 Profile gleich `user_id`, gleich `agent_id` in `simulation_config.json` und gleich `agent_id` in `actions.jsonl`. Lies **nicht** `agent.get("user_id")` und nicht den Namen: Der Name im Profil weicht bei 7 von 50 Agenten vom Namen in der Konfiguration ab (siehe Abschnitt 5), nur die Zahl ist verlässlich.
  4. `backend/app/services/report_agent/agent.py`, Interview-Item (Zeile ~703-725): `"voice_key": f"agent:{interview.agent_id}" if getattr(interview, "agent_id", None) is not None else None,` ergänzen.
  5. `backend/app/services/report_agent/agent.py`, Aktions-Item (Zeile ~486-492): nach dem `items.append(...)` setzen:
     ```python
     if action.get("agent_id") is not None:
         items[-1]["voice_key"] = f"agent:{action.get('agent_id')}"
     ```
  6. Schemas rendern und Zod-Spiegel nachziehen: in `frontend/src/contracts/reportContract.ts` an beiden Stellen, an denen `persona_stakeholder_group` steht, `voice_key: z.string().regex(/^agent:\d+$/).nullable().optional(),` ergänzen.
- **Test (Pflicht):** Die Agenten-ID im Interview und in der Aktion ist dieselbe Zahl für dieselbe Persona (am Lauf geprüft, siehe Punkt 3). Schreibe einen Test `backend/tests/services/test_voice_key.py` mit zwei Fällen:
  - Interview-Item und Aktions-Item mit gleicher `agent_id=7` bekommen beide `voice_key == "agent:7"`.
  - Ein Graph-Fakt-Item bekommt `voice_key is None`.
  Nimm `backend/tests/services/test_report_tool_evidence.py` als Vorlage für den Aufbau.
- **Prüfbefehl:**
  ```bash
  cd backend && uv run pytest tests/contracts/ tests/services/test_voice_key.py tests/services/test_report_tool_evidence.py tests/services/test_interview_evidence_anchor.py -x -q
  cd backend && uv run python -m app.contracts.dump_schemas --check && uv run ruff check . && uv run mypy app
  cd frontend && bun run test src/contracts/__tests__/reportContract.spec.ts && bun run check
  ```
- **Nicht tun:** `persona_stakeholder_group` und `persona_role_family` nicht verändern; `build_producer_key` nicht ändern (sonst ändern sich Evidence-IDs).

### Schritt 1.3 · Ein-Quellen-Deckel zählt Stimmen und Quellenarten

- **Modell:** `glm-5.3`.
- **Ziel:** Entscheidung 3 umsetzen.
- **Anker** (prüfen nach Regel 2):
  | Symbol | Datei | Zeile | wörtlicher Text |
  |---|---|---|---|
  | `_compute_confidence_with_penalties` | `backend/app/services/confidence_calculator.py` | 265 | `unique_sources = len({(e.get("type"), e.get("source")) for e in evidence})` |
  | `_component_consistency` | `backend/app/services/confidence_calculator.py` | 148 | `sources = {(e.get("type"), e.get("source")) for e in evidence}` |
  | `_apply_single_source_cap` | `backend/app/services/confidence_calculator.py` | 158 | `def _apply_single_source_cap(` |
  
  Einziger Aufrufer von `compute_confidence` im Produktivcode: `backend/app/services/report_agent/agent.py:957`. Bestätige das mit `query_graph_tool(pattern="callers_of", target="compute_confidence")`.
- **Änderungen**, nur in `backend/app/services/confidence_calculator.py`:
  1. Neue Funktion oberhalb von `_component_consistency`:
     ```python
     def _independence_key(e: Dict[str, Any]) -> Tuple[str, str, str]:
         """Schlüssel für die Unabhängigkeit eines Belegs.

         Belege derselben Stimme sind nicht unabhängig, egal über welchen
         Kanal (Interview, Simulationsbeitrag). Belege ohne Stimme zählen
         nach Quellenart und Herkunft wie bisher.
         """
         voice = e.get("voice_key")
         if voice:
             return ("voice", str(voice), "")
         return ("source", str(e.get("type") or ""), str(e.get("source") or ""))


     def _count_independent_sources(evidence: List[Dict[str, Any]]) -> int:
         return len({_independence_key(e) for e in evidence})
     ```
  2. Zeile 148: `sources = {...}` ersetzen durch `count = _count_independent_sources(evidence)` und die drei `len(sources)`-Vergleiche darunter auf `count` umstellen.
  3. Zeile 265: ersetzen durch `unique_sources = _count_independent_sources(evidence)`.
- **Neue Tests** in `backend/tests/test_confidence_calculator.py` (anhängen). Jeder Beleg hat `supports_claim=True`, `match_score=0.7`, `entailment` so wie in den vorhandenen Tests dieser Datei:
  | Test | Belege | Erwartung |
  |---|---|---|
  | `test_same_voice_two_channels_stays_capped` | Interview `voice_key="agent:1"` + Aktion `voice_key="agent:1"` | Score `<= 0.59` |
  | `test_two_voices_lift_the_cap` | zwei Interviews, `agent:1` und `agent:2` | Score `> 0.59` |
  | `test_seed_plus_one_voice_lifts_the_cap` | ein Seed-Beleg ohne `voice_key` + ein Interview `agent:1` | Score `> 0.59` |
  | `test_items_without_voice_key_count_as_before` | zwei Interviews ohne `voice_key`, gleiches `type` und `source` | Score `<= 0.59` |
- **Bestehende Tests:** `test_repeated_high_scores_from_one_source_cap_at_low` (Zeile 52) und `backend/tests/services/test_confidence_kalibrierung.py` müssen unverändert grün bleiben.
- **Zusätzlicher Vertragstest** in `backend/tests/contracts/test_role_family_counting.py` (anhängen): Ein Claim mit Label `high`, gestützt auf zwei Interviews mit verschiedenen `voice_key`, aber **derselben** `persona_role_family`, wird vom Vertrag weiterhin abgelehnt (`ValidationError`). Das beweist, dass Anker 4 unberührt ist.
- **Prüfbefehl:**
  ```bash
  cd backend && uv run pytest tests/test_confidence_calculator.py tests/services/test_confidence_kalibrierung.py tests/contracts/test_role_family_counting.py tests/test_report_agent_contracts.py -x -q
  cd backend && uv run ruff check . && uv run mypy app
  ```
- **Nicht tun:** die Schwelle 0,59, die Gewichte (0.40/0.25/0.20/0.15) und die Verified-Schranke nicht ändern.

### Schritt 1.4 · Streitfrage: Vertrag und Vorschlag des Konfigurations-Assistenten

- **Modell:** `glm-5.3` (Cross-Layer, Prompt-Semantik).
- **Ziel:** Jede Simulationskonfiguration trägt eine Streitfrage oder die ausdrückliche Angabe, dass es keine gibt.
- **Ausgangslage:** `simulation_config.json` hat keinen Pydantic-Vertrag. Sie entsteht aus dem Dataclass `SimulationParameters` (`backend/app/services/simulation_config_models.py:121`). Dieser Schritt migriert die Datei **nicht** als Ganzes. Er führt einen Vertrag nur für die Streitfrage ein.
- **Anker** (prüfen nach Regel 2):
  | Symbol | Datei | Zeile | wörtlicher Text |
  |---|---|---|---|
  | `SimulationParameters` | `backend/app/services/simulation_config_models.py` | 121 | `class SimulationParameters:` |
  | Feld `generation_reasoning` | `backend/app/services/simulation_config_models.py` | 158 | `generation_reasoning: str = ""` |
  | `SimulationConfigGenerator.generate_config` | `backend/app/services/simulation_config_generator.py` | 230 | `def generate_config` |
  | `total_steps` | `backend/app/services/simulation_config_generator.py` | 277 | `total_steps = (` |
  | `_call_llm_with_retry` | `backend/app/services/simulation_config_llm.py` | ~37 | `def _call_llm_with_retry` |
- **Änderungen:**
  1. Neue Datei `backend/app/contracts/contested_question_contract.py`:
     ```python
     """Streitfrage eines Laufs (siehe CONTEXT.md, Abschnitt Streitfrage)."""
     from typing import Literal, Optional
     from pydantic import BaseModel, ConfigDict, Field, model_validator

     class ContestedQuestion(BaseModel):
         model_config = ConfigDict(extra="forbid")

         #: Bejah- oder verneinbare Aussage. ``None``, wenn der Lauf keine hat.
         statement: Optional[str] = Field(default=None, min_length=10, max_length=300)
         #: Wer die Streitfrage festgelegt hat.
         origin: Literal["assistant", "user", "none"] = "none"
         #: Begründung, wenn es keine Streitfrage gibt.
         absence_reason: Optional[str] = Field(default=None, max_length=300)

         @model_validator(mode="after")
         def _consistent(self) -> "ContestedQuestion":
             if self.origin == "none" and self.statement is not None:
                 raise ValueError("origin=none verlangt statement=None")
             if self.origin != "none" and self.statement is None:
                 raise ValueError("origin assistant/user verlangt ein statement")
             return self
     ```
     In `backend/app/contracts/__init__.py` exportieren und in `backend/app/contracts/dump_schemas.py` registrieren. Sieh dir an, wie dort ein kleines Modell wie `RunBudgetConfig` eingetragen ist, und trage `ContestedQuestion` genauso ein, Schema-Dateiname `contested-question.schema.json`.
  2. Zod-Spiegel `frontend/src/contracts/contestedQuestionContract.ts` mit denselben drei Feldern und einem Spec `frontend/src/contracts/__tests__/contestedQuestionContract.spec.ts` (gültig: Aussage mit `origin: "assistant"`; ungültig: `origin: "none"` mit Aussage).
  3. `backend/app/services/simulation_config_models.py`, `SimulationParameters`: Feld `contested_question: Dict[str, Any] = field(default_factory=lambda: {"statement": None, "origin": "none", "absence_reason": None})` direkt unter `generation_reasoning`. In `to_dict` die Zeile `"contested_question": self.contested_question,` ergänzen.
  4. `backend/app/services/simulation_config_schemas.py`: neues LLM-Antwortschema
     ```python
     class ContestedQuestionResponse(BaseModel):
         has_contested_question: bool
         statement: str | None = None
         absence_reason: str | None = None
     ```
  5. Neue Datei `backend/app/services/simulation_config_contested_question.py` mit einer Funktion `generate_contested_question(call_llm, simulation_requirement: str) -> ContestedQuestion`. Sie ruft `call_llm(prompt, system_prompt, ContestedQuestionResponse)` auf. Prompt wörtlich:
     ```
     System: You derive the single contested question of a stakeholder simulation. Answer in the language of the simulation requirement.
     User:
     Simulation requirement:
     {simulation_requirement}

     Task: State the ONE proposition that the stakeholders in this scenario are for or against.
     Rules:
     - It must be a full declarative sentence that can be affirmed or denied, e.g. "Die Geburtshilfe in Brenkhausen wird zum 30. Juni 2027 geschlossen."
     - Phrase it as the measure or decision itself, never as its negation. "In favour" must mean: the measure happens.
     - If the requirement contains several contested points, choose the one the requirement is mainly about.
     - If the requirement contains no decidable proposition (for example an open perception question), set has_contested_question=false and give absence_reason in one sentence.
     ```
     Ergebnis: bei `has_contested_question=True` und nichtleerem `statement` → `ContestedQuestion(statement=..., origin="assistant")`, sonst `ContestedQuestion(origin="none", absence_reason=...)`. Wirft `call_llm` eine `BudgetExceededError`: **nicht fangen**, durchreichen. Jede andere Ausnahme: `ContestedQuestion(origin="none", absence_reason="Streitfrage konnte nicht ermittelt werden.")` und `logger.warning`.
  6. `backend/app/services/simulation_config_generator.py`, `generate_config`:
     - Neuer optionaler Parameter `contested_question_override: Optional[str] = None`.
     - Direkt nach `context = self._build_context(` und **vor** Schritt 1 (Zeit): Streitfrage bestimmen. Ist `contested_question_override` ein nichtleerer String, dann `ContestedQuestion(statement=override.strip(), origin="user")` ohne LLM-Aufruf, sonst `generate_contested_question(self._call_llm_with_retry, simulation_requirement)`.
     - `total_steps` um 1 erhöhen und einen `report_progress`-Aufruf „Streitfrage wird bestimmt..." einfügen. Sieh dir an, wie die vorhandenen Schritte `report_progress` aufrufen.
     - Beim Bau von `SimulationParameters(` (Zeile ~396): `contested_question=cq.model_dump(),` übergeben.
- **Tests:** neue Datei `backend/tests/services/test_contested_question.py`:
  - LLM-Stub liefert Aussage → `origin == "assistant"`.
  - LLM-Stub liefert `has_contested_question=False` → `origin == "none"`, `statement is None`.
  - Override gesetzt → `origin == "user"`, der LLM-Stub wurde **nicht** aufgerufen.
  - LLM-Stub wirft `BudgetExceededError` → die Ausnahme kommt beim Aufrufer an.
  - LLM-Stub wirft `RuntimeError` → `origin == "none"`.
  Vorlage für den Stub: `backend/tests/services/test_simulation_config_generator_refactored.py`.
  Dazu `backend/tests/contracts/test_contested_question_contract.py` mit den zwei Validator-Fällen.
- **Prüfbefehl:**
  ```bash
  cd backend && uv run pytest tests/contracts/ tests/services/test_contested_question.py tests/services/test_simulation_config_generator_refactored.py tests/services/test_simulation_config_generator_parallel_batches.py -x -q
  cd backend && uv run python -m app.contracts.dump_schemas --check && uv run ruff check . && uv run mypy app
  cd frontend && bun run test src/contracts/__tests__/contestedQuestionContract.spec.ts && bun run check
  ```
- **Nicht tun:** `SimulationParameters` nicht nach Pydantic migrieren; keine anderen Felder der Konfiguration anfassen.

### Schritt 1.5 · Streitfrage in allen drei Prompts verwenden

- **Modell:** `glm-5.3` (Prompt-Semantik).
- **Ziel:** Startkonfiguration, Agenten-Prompt und Interview beziehen die Haltung auf dieselbe Aussage.
- **Anker** (prüfen nach Regel 2):
  | Symbol | Datei | Zeile | wörtlicher Text |
  |---|---|---|---|
  | `_generate_agent_configs_batch` | `backend/app/services/simulation_config_agents.py` | 118 | `"stance": "<supportive/opposing/neutral/observer>"` |
  | `_describe_stance` | `backend/scripts/agent_tools.py` | ~676-690 | `Du siehst das Vorhaben` |
  | `build_stance_section` | `backend/scripts/agent_tools.py` | 722 | `def build_stance_section` |
  | `STANCE_PROMPT_REQUIREMENT` | `backend/app/services/interview_stance.py` | ~40 | `position on the subject of these questions` |
- **Änderungen:**
  1. **Konfigurations-Prompt** (`simulation_config_agents.py`, Funktion `_generate_agent_configs_batch`): Die Funktion bekommt die Streitfrage als Parameter `contested_statement: Optional[str]`. Reiche sie von `generate_config` über `_generate_agent_configs_parallel` durch. Ist sie gesetzt, füge im Prompt direkt nach der Zeile `Simulation Requirements: {simulation_requirement}` ein:
     ```
     Contested question: {contested_statement}
     For every entity, `stance` and `sentiment_bias` refer ONLY to this contested question:
     - "supportive" and a positive sentiment_bias mean: the entity wants the contested question to come true.
     - "opposing" and a negative sentiment_bias mean: the entity wants to prevent it.
     - "neutral" means genuinely undecided. "observer" is reserved for media and pure reporting entities.
     - stance and the sign of sentiment_bias must agree. Never combine "opposing" with a positive sentiment_bias or "supportive" with a negative one.
     - Entities that are directly affected (employees, patients, residents, their associations, political groups) normally have a position. Do not default them to "neutral" or "observer".
     ```
     Ist sie `None`, bleibt der Prompt unverändert.
  2. **Nachbearbeitung** in derselben Datei, dort wo `AgentActivityConfig(` gebaut wird (Zeile 142): Nach dem Bau prüfen, ob `stance` und Vorzeichen von `sentiment_bias` zusammenpassen. Regel: `stance == "opposing"` und `sentiment_bias > 0` → `sentiment_bias = -abs(sentiment_bias)`. `stance == "supportive"` und `sentiment_bias < 0` → `sentiment_bias = abs(sentiment_bias)`. Die `stance` gewinnt, weil sie nach dem Graph-Abgleich (`resolve_stance`) feststeht. Jede Korrektur mit `logger.info` protokollieren. Lege das in eine eigene Funktion `_align_sentiment_sign(stance: str, sentiment_bias: float) -> float`.
  3. **Agenten-Prompt** (`backend/scripts/agent_tools.py`): `build_stance_section` und `_describe_stance` bekommen einen optionalen Parameter `contested_statement: Optional[str] = None`. Ist er gesetzt, lautet der Haltungssatz nicht mehr „Du siehst das Vorhaben ... kritisch", sondern:
     - `supportive`: `Zur Streitfrage „{contested_statement}" bist du {sehr }dafür.`
     - `opposing`: `Zur Streitfrage „{contested_statement}" bist du {sehr }dagegen.`
     - `neutral`: `Zur Streitfrage „{contested_statement}" bist du noch unentschieden.`
     - `observer`: `Die Streitfrage „{contested_statement}" beobachtest du, ohne selbst Partei zu sein.`
     „sehr " wie bisher bei `abs(bias) >= 0.5`. Ohne `contested_statement` bleibt der bisherige Text Wort für Wort erhalten.
     Alle Aufrufer von `build_stance_section` müssen den Wert aus `config.get("contested_question", {}).get("statement")` übergeben. Aufrufer finden mit CRG: `query_graph_tool(pattern="callers_of", target="build_stance_section")` und `query_graph_tool(pattern="callers_of", target="augment_profile_with_stance")`. Erwartet: `agent_tools.py` (~801, ~836, ~881, ~970), `run_parallel_simulation.py` (311, 1551, 1924, 1781, 2129), `sim_runtime/platform_runner.py` (~732).
  4. **Interview-Prompt** (`backend/app/services/interview_stance.py`): `STANCE_PROMPT_REQUIREMENT` bleibt als Konstante für den Fall ohne Streitfrage. Neue Funktion:
     ```python
     def stance_prompt_requirement(contested_statement: Optional[str]) -> str:
         if not contested_statement:
             return STANCE_PROMPT_REQUIREMENT
         return (
             "7. After your last answer, add one final line in exactly this form:\n"
             "   STANCE: <number>\n"
             "   where the number is between -1.0 and 1.0 and expresses your position on this "
             f"statement: \"{contested_statement}\" "
             "-1.0 means you clearly want to prevent it, 0.0 undecided or torn, "
             "1.0 means you clearly want it to happen. Give the number that matches "
             "what you actually said. Write this line only once, at the very end.\n"
         )
     ```
     `backend/app/services/graph_tools.py`, `interview_agents` (Signatur Zeile 285-291): neuer Parameter `contested_statement: Optional[str] = None`, und an der Stelle `+ STANCE_PROMPT_REQUIREMENT` (Zeile ~409) stattdessen `+ stance_prompt_requirement(contested_statement)`.
     `backend/app/services/tool_execution.py`, `_run_interview_agents` (Zeile 40): den Wert durchreichen. Quelle: `store.read_json(simulation_id, "simulation_config", default=None)`; sieh dir an, wie `backend/app/services/sim/interview_direct.py:133-141` (`_simulation_context`) die Datei liest, und verwende dieselbe Lesefunktion.
- **Tests:**
  - `backend/tests/services/test_contested_question.py` erweitern: `_align_sentiment_sign("opposing", 0.65) == -0.65`; `("supportive", -0.4) == 0.4`; `("neutral", 0.3) == 0.3`.
  - `backend/tests/services/test_simulation_stance_graph.py` (nutzt `build_stance_section`): neuer Test, dass mit `contested_statement="X wird geschlossen."` und `stance="opposing"` der Text `Zur Streitfrage „X wird geschlossen." bist du` und `dagegen` enthält; und dass ohne `contested_statement` der alte Text unverändert ist.
  - `backend/tests/regression/test_interview_stance.py`: neuer Test, dass `stance_prompt_requirement("X.")` den String `"X."` enthält und `stance_prompt_requirement(None) == STANCE_PROMPT_REQUIREMENT`. Der vorhandene Test `test_the_prompt_requirement_is_wired_into_the_interview_prompt` muss grün bleiben.
- **Prüfbefehl:**
  ```bash
  cd backend && uv run pytest tests/services/test_contested_question.py tests/services/test_simulation_stance_graph.py tests/regression/test_interview_stance.py tests/services/test_skeptic_quota.py tests/scripts/test_agent_tools_untrusted_observation.py tests/test_tool_execution.py -x -q
  cd backend && uv run ruff check . && uv run mypy app
  ```
- **Nicht tun:** Die Skeptiker-Quote (`_ensure_skeptic_quota`) und `resolve_stance` nicht ändern. Die Verteilung der Haltungen nicht „korrigieren"; das ist Etappe 2.

### Schritt 1.6 · Streitfrage in der Oberfläche: eingeben und anzeigen

- **Modell:** `glm-5.3-flash` für das Frontend, `glm-5.3` für den Backend-Teil. Zwei Commits.
- **Ziel:** Vor der Vorbereitung kann man eine Streitfrage vorgeben. Nach der Vorbereitung steht die geltende Streitfrage sichtbar da. Ändern heißt: Vorbereitung mit eigener Streitfrage neu starten. Es gibt bewusst keinen Endpunkt, der die Streitfrage nachträglich ändert, weil die Haltungen aller Agenten an ihr hängen.
- **Backend-Commit:**
  - Anker (prüfen nach Regel 2): Symbol `PrepareRequest`, Datei `backend/app/api/simulation_prepare_contracts.py`, Zeile 105, Text `class PrepareRequest`. Symbol `PrepareInputs`, dieselbe Datei, Zeile ~131, Text `class PrepareInputs`.
  - `PrepareRequest`: Feld `contested_question: Optional[str] = Field(default=None, min_length=10, max_length=300)`.
  - `PrepareInputs`: dasselbe Feld durchreichen. Folge dem Weg eines vorhandenen optionalen Feldes (z. B. `budget_config`) von `PrepareRequest` bis zum Aufruf `generate_config(` in `backend/app/services/prepare_service.py:593` und übergib dort `contested_question_override=`.
  - Test in der vorhandenen Testdatei für die Prepare-Route (finden mit CRG: `query_graph_tool(pattern="tests_for", target="PrepareRequest")`): Request mit `contested_question` → `generate_config` wird mit `contested_question_override` aufgerufen.
- **Frontend-Commit:**
  - `frontend/src/api/simulation.ts`, Interface `PrepareSimulationData` (Zeile 35-46): `contested_question?: string`.
  - Neue Komponente `frontend/src/components/step2/ContestedQuestionField.vue`. Vorlage für Aufbau, Props und Stil: `frontend/src/components/step2/AgentCapControl.vue`. Inhalt: ein `<textarea>` mit Label „Streitfrage (optional)", Hilfetext „Eine Aussage, die man bejahen oder verneinen kann. Leer lassen, dann schlägt der Assistent eine vor.", `maxlength="300"`, `v-model`.
  - Einbinden in `frontend/src/components/v4/steps/Step2EnvSetup.vue` vor dem Start der Vorbereitung; Wert in den Payload von `prepareSimulation` geben (Anker nach Regel 2: Datei `frontend/src/composables/useSimulationPrepare.ts`, Zeile ~159, Text `prepareSimulation(payload)`).
  - Anzeige nach der Vorbereitung: in `Step2EnvSetup.vue` aus `simulationConfig.contested_question` mit `ContestedQuestionSchema.safeParse` lesen. Bei `origin` `assistant` oder `user`: Zeile „Streitfrage: <statement>" mit Zusatz „(Vorschlag des Assistenten)" bzw. „(von dir vorgegeben)". Bei `origin: "none"`: „Keine Streitfrage: <absence_reason>". Schlägt `safeParse` fehl: nichts anzeigen, kein Fehler.
  - Texte in `frontend/src/i18n/locales/de.json` und `en.json` unter einem neuen Schlüssel `contestedQuestion`.
  - Spec `frontend/src/components/step2/__tests__/ContestedQuestionField.spec.ts` nach dem Muster von `AgentCapControl.spec.ts`: rendert Label, gibt Eingabe per `update:modelValue` weiter.
- **Prüfbefehl:** Backend wie Schritt 1.4; Frontend `cd frontend && bun run test src/components/step2/__tests__/ContestedQuestionField.spec.ts && bun run check`.

### Schritt 1.7 · Werkzeug `search_simulation_actions` für den Report-Agenten

- **Modell:** `glm-5.3`.
- **Ziel:** Der Report-Agent kann Simulationsbeiträge gezielt suchen. Jeder Treffer wird ein Beleg vom Typ `agent_action`.
- **Anker** (prüfen nach Regel 2; alle müssen stimmen):
  | Symbol | Datei | Zeile | wörtlicher Text |
  |---|---|---|---|
  | `define_tools` | `backend/app/services/report_agent/tools.py` | 48 | `"interview_agents": {` |
  | `execute_tool` | `backend/app/services/tool_execution.py` | 195 | `elif tool_name == "interview_agents":` |
  | `VALID_TOOL_NAMES` | `backend/app/services/tool_validation.py` | 19 | `VALID_TOOL_NAMES: FrozenSet[str] = frozenset({` |
  | `all_tools` | `backend/app/services/report_agent/workflow.py` | 976 | `all_tools = {"insight_forge", "panorama_search", "quick_search", "interview_agents"}` |
  | `_record_tool_evidence` | `backend/app/services/report_agent/agent.py` | 662 | `elif isinstance(structured_result, InterviewResult):` |
  | `SimulationRunner.get_all_actions` | `backend/app/services/simulation_runner.py` | 548 | `def get_all_actions` |
  | `action_content` | `backend/app/services/report_agent/sections.py` | 91 | `def action_content` |
  | `_HARD_ROLE_CONFLICTS` | `backend/app/services/report_agent/agent.py` | 201 | `_HARD_ROLE_CONFLICTS = frozenset({"foreign_role", "foreign_name_signature"})` |
- **Änderungen:**
  1. Neue Datei `backend/app/services/report_agent/action_search.py`:
     - Dataclass `ActionSearchResult` mit `query: str`, `hits: List[Dict[str, Any]]`, `total_matching: int`, `total_actions: int`.
     - Funktion `search_simulation_actions(simulation_id: str, query: str = "", agent_name: str = "", round_from: int | None = None, round_to: int | None = None, limit: int = 12) -> ActionSearchResult`.
     - Ablauf: `SimulationRunner.get_all_actions(simulation_id)` → `to_dict()` je Aktion → Aktionen mit hartem Rollenkonflikt verwerfen (Konstante `_HARD_ROLE_CONFLICTS` aus `report_agent/agent.py:201` importieren, nicht kopieren) → nur Aktionen behalten, für die `action_content(action)` (aus `report_agent/sections.py:91`) einen nichtleeren Text liefert → Filter:
       - `agent_name`: Teilstring-Vergleich ohne Groß-/Kleinschreibung gegen `action["agent_name"]`.
       - `round_from`/`round_to`: gegen `action["round_num"]`, beide Grenzen einschließlich.
       - `query`: in Wörter mit mindestens vier Zeichen zerlegen, kleinschreiben; Punktzahl = Anzahl der Wörter, die im kleingeschriebenen Text vorkommen; Aktionen mit Punktzahl 0 verwerfen. Leere `query`: kein Textfilter, Punktzahl 0 für alle.
     - Sortierung: Punktzahl absteigend, dann `round_num` aufsteigend. `limit` auf 1 bis 20 begrenzen.
     - Kein LLM-Aufruf, keine Embeddings.
  2. `backend/app/services/tool_schema.py`: neue Konstante `TOOL_DESC_SEARCH_SIMULATION_ACTIONS` nach dem Muster von `TOOL_DESC_INTERVIEW_AGENTS` (Zeile 63), in `__all__` eintragen. Text:
     ```
     Search what the simulated agents actually posted and commented during the simulation (posts, comments, quote posts). Use this to find out what was said publicly, by whom and in which round. Use it for claims about the course of the debate. It returns original post texts with agent name, platform and round. It does NOT interview anyone; for first-person answers use interview_agents.
     Parameters: query (keywords), agent_name (optional), round_from / round_to (optional), limit (default 12, max 20).
     ```
  3. `backend/app/services/report_agent/tools.py`, `define_tools`: Eintrag `"search_simulation_actions"` nach `"interview_agents"`, gleiche Dict-Form, Parameter `query`, `agent_name`, `round_from`, `round_to`, `limit`. Prüfe die Typ-Heuristik in `get_openai_tools_schema` (Zeile ~158): Sie macht nur `limit` und `max_*` zu `integer`. Erweitere die Bedingung so, dass auch Parameternamen mit Präfix `round_` zu `integer` werden.
  4. `backend/app/services/tool_execution.py`: neuer Zweig `elif tool_name == "search_simulation_actions":` vor dem `else` mit dem Fehlertext für unbekannte Werkzeuge. Parameter aus dem Aufruf lesen wie beim Zweig `quick_search`, `search_simulation_actions(...)` aufrufen, Ergebnis über denselben Weg registrieren wie die anderen Zweige (`_record_and_annotate`, Zeile ~83). Den Fehlertext bei Zeile 277 um den neuen Namen ergänzen.
  5. `backend/app/services/report_agent/agent.py`, `_record_tool_evidence`: neuer Zweig `elif isinstance(structured_result, ActionSearchResult):` vor dem Fallback bei Zeile 765. Je Treffer ein Item, **gleiche Form wie in `_collect_simulation_evidence_items` (Zeile ~472-503)**: `type="agent_action"`, `source="simulation_actions"`, `value=action_type`, Snippet `"{agent} {action_type} on {platform} in round {round_num}: {Text, höchstens 600 Zeichen}"`, `raw=action`, `producer_key` nach derselben Regel `"simulation-action:" + ":".join(...)`, `voice_key` wie in Schritt 1.2. Damit Sammeln und Suchen dieselbe Evidence-ID für dieselbe Aktion erzeugen, ziehe den Bau des Items in eine gemeinsame Funktion `build_action_evidence_item(action: Dict[str, Any]) -> Dict[str, Any]` in `action_search.py` und rufe sie an beiden Stellen auf.
  6. `backend/app/services/tool_validation.py:19`: `"search_simulation_actions"` in `VALID_TOOL_NAMES` ergänzen. `backend/tests/test_tool_validation.py:21` (`TestValidToolNames`) prüft die Menge wörtlich: dort den neuen Namen ergänzen. Das ist eine erlaubte Testanpassung.
  7. `backend/app/services/report_agent/workflow.py:976`: `"search_simulation_actions"` in `all_tools` ergänzen.
  8. `backend/app/services/report_agent/search_dedup.py:41` (`SEARCH_TOOLS`): `"search_simulation_actions"` ergänzen.
  9. `backend/app/services/report_prompts/sections.py`, Werkzeugliste bei Zeile 295-300: eine Zeile ergänzen, **außerhalb** des Blocks `<evidence_gating priority="hard">`:
     ```
     - search_simulation_actions: Search the posts and comments the agents actually wrote during the simulation. Use it for what was said publicly and how the debate developed.
     ```
     Lass dir vorher mit `ctx_execute_file` alle Zeilen von `backend/app/services/report_prompts/sections.py` ausgeben, die `evidence_gating` enthalten. So siehst du, wo der harte Block beginnt und endet. Bleibe außerhalb.
  10. `backend/app/utils/llm_e2e_stub.py` (`_STUB_TOOL_RETURNS`, Zeile ~308): Eintrag für das neue Werkzeug mit leerem Ergebnis, nach dem Muster von `quick_search`.
- **Tests:** neue Datei `backend/tests/services/report_agent/test_action_search.py`:
  - Textfilter findet den passenden Beitrag und sortiert ihn nach vorn.
  - `agent_name`-Filter und Rundenfilter wirken.
  - Aktionen mit `role_conflict="foreign_role"` kommen nicht vor.
  - Aktionen ohne Text (`LIKE_POST`) kommen nicht vor.
  - `limit=50` wird auf 20 begrenzt.
  - `build_action_evidence_item` liefert für dieselbe Aktion denselben `producer_key` wie zuvor `_collect_simulation_evidence_items`. Dafür den erwarteten Wert aus dem vorhandenen Test `backend/tests/services/report_agent/test_action_sampling_content_aware.py` übernehmen.
  `SimulationRunner.get_all_actions` per `monkeypatch` ersetzen; Vorlage: `backend/tests/services/sim/test_role_leakage_marking.py:281`.
  Dazu in `backend/tests/test_tool_execution.py` ein Dispatch-Test für den neuen Zweig.
- **Prüfbefehl:**
  ```bash
  cd backend && uv run pytest tests/services/report_agent/test_action_search.py tests/services/report_agent/test_action_sampling_content_aware.py tests/services/sim/test_role_leakage_marking.py tests/test_tool_execution.py tests/test_tool_validation.py tests/services/test_search_dedup.py tests/services/report_agent/test_native_toolcalls.py tests/test_llm_e2e_stub.py tests/eval/test_evidence_gating_snapshot.py -x -q
  cd backend && uv run ruff check . && uv run mypy app
  ```
- **Nicht tun:** `MAX_TOOL_CALLS_PER_SECTION` nicht ändern; die Acht-Aktionen-Stichprobe nicht entfernen; `EvidenceType` und `EvidenceSourceKind` nicht erweitern (`agent_action` existiert bereits).

### Schritt 1.8 · Haltung je Beitrag und Positionierungsquote

- **Modell:** `glm-5.3`.
- **Ziel:** Vor dem Schreiben der Abschnitte wird jeder Simulationsbeitrag einmal nach seiner Haltung zur Streitfrage klassifiziert. Daraus entstehen Positionierungsquote und Lagerverteilung. Liegt die Quote unter der Schwelle, entsteht eine Degradation.
- **Anker** (prüfen nach Regel 2):
  | Symbol | Datei | Zeile | wörtlicher Text |
  |---|---|---|---|
  | Aufruf im Normalfall | `backend/app/services/report_agent/workflow.py` | ~2226 | `report.run_degradations = collect_run_degradations(` |
  | `collect_run_degradations` | `backend/app/services/report_agent/run_degradation.py` | 247 | `def collect_run_degradations` |
  | `_entry` | `backend/app/services/report_agent/run_degradation.py` | 33 | `def _entry` |
  | `RunDegradationModel.component` | `backend/app/contracts/report_contract.py` | 895 | `"interview_agents",` (Literal der Komponenten, Zeile 888-912) |
- **Änderungen:**
  1. Vertrag: neue Datei `backend/app/contracts/stance_analysis_contract.py` mit
     - `StanceClass = Literal["in_favour", "opposed", "undecided"]`
     - `ClassifiedContribution`: `agent_id: int`, `agent_name: str`, `platform: str`, `round_num: int`, `action_type: str`, `producer_key: str`, `stance_class: StanceClass`
     - `VoiceStance`: `voice_key: str`, `agent_name: str`, `role_family: Optional[str]`, `start_class: StanceClass`, `contribution_classes: list[StanceClass]`, `interview_class: Optional[StanceClass]`
     - `StanceAnalysis`: `contested_statement: Optional[str]`, `applicable: bool`, `voices_total: int`, `voices_positioned: int`, `positioning_ratio: Optional[float]` (0 bis 1), `camp_distribution: dict[StanceClass, int]`, `voices: list[VoiceStance]`, `contributions: list[ClassifiedContribution]`, `classified_total: int`, `classification_failed: int`
     Alle Modelle mit `extra="forbid"`. In `dump_schemas.py` registrieren (`stance-analysis.schema.json`). Zod-Spiegel `frontend/src/contracts/stanceAnalysisContract.ts` mit Spec.
  2. `backend/app/contracts/report_contract.py`, Literal der Komponenten in `RunDegradationModel.component` (Zeile 888-912): `"simulation_positioning"` ergänzen. Schemas rendern, `frontend/src/contracts/reportContract.ts` an der entsprechenden Stelle (`RunDegradationSchema`, Zeile ~341) ebenfalls ergänzen.
  3. Neue Datei `backend/app/services/report_agent/stance_analysis.py`:
     - `classify_contributions(llm_client, contested_statement, contributions, batch_size=25) -> list[StanceClass | None]`. Je Batch ein Aufruf von `llm_client.chat_json` mit Schema `StanceBatchResponse` (`items: list[{index: int, stance: StanceClass}]`). Prompt wörtlich:
       ```
       System: You classify short social media posts. Answer only with the requested JSON.
       User:
       Statement: "{contested_statement}"
       For each numbered post decide the author's position on the statement:
       - in_favour: the post clearly wants the statement to come true or defends it.
       - opposed: the post clearly wants to prevent it or rejects it.
       - undecided: the post weighs up, asks for more data, reports neutrally, or does not address the statement.
       Judge only what the post says. When in doubt choose undecided.
       Posts:
       {index}. {text, höchstens 500 Zeichen}
       ...
       ```
       Fehlt ein Index in der Antwort oder schlägt der Batch fehl: `None` für diese Beiträge, `logger.warning`. `BudgetExceededError` nie fangen.
     - `build_stance_analysis(simulation_id, simulation_config, actions, interview_stances, llm_client) -> StanceAnalysis`:
       - Hat die Konfiguration keine Streitfrage (`statement is None`): `StanceAnalysis(applicable=False, ...)` mit leeren Listen, **kein** LLM-Aufruf.
       - Beiträge = Aktionen mit Text, ohne harte Rollenkonflikte (dieselbe Filterung wie in Schritt 1.7; nutze eine gemeinsame Hilfsfunktion in `action_search.py`).
       - `start_class` je Agent aus `agent_configs[].stance`: `supportive` → `in_favour`, `opposing` → `opposed`, sonst `undecided`.
       - Eine Stimme ist „positioniert", wenn mindestens einer ihrer Beiträge `in_favour` oder `opposed` ist.
       - `voices_total` = Zahl der Agenten in `agent_configs`. `positioning_ratio = voices_positioned / voices_total`, bei `voices_total == 0` `None`.
       - `camp_distribution`: je positionierter Stimme die Klasse, die unter ihren Beiträgen häufiger vorkommt (`in_favour` gegen `opposed`); bei Gleichstand `undecided`. Nicht positionierte Stimmen zählen als `undecided`.
       - `interview_class` bleibt in diesem Schritt `None`; Etappe 3 füllt es.
     - Ergebnis als `stance_analysis.json` im Berichtsverzeichnis speichern. Sieh dir an, wie `evidence_map.json` in `backend/app/services/report_agent/storage.py` atomar geschrieben wird, und verwende dieselbe Schreibfunktion.
  4. `backend/app/config.py`: `REPORT_POSITIONING_RATIO_MIN = float(os.environ.get("AGORA_REPORT_POSITIONING_RATIO_MIN", "0.5"))`. Eintrag in `backend/app/services/settings_schema.py` nach dem Muster von `AGORA_SIM_DEFAULT_MAX_TOKENS` (Zeile 195) und in `.env.example` als auskommentierte Zeile. Weil ein Env-Standard dazukommt: einen Absatz in `docs/runbooks/upgrade.md` ergänzen.
  5. `backend/app/services/report_agent/run_degradation.py`: neue Funktion `_positioning_degradations(analysis: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]`. Regeln:
     - `analysis is None` oder `applicable is False` → `[]`.
     - `positioning_ratio is not None and positioning_ratio < Config.REPORT_POSITIONING_RATIO_MIN` → ein Eintrag über `_entry("simulation_positioning", f"positioning_ratio_{voices_positioned}_of_{voices_total}", "<Detail>", severity="warning")`. Detailtext: `"Nur {voices_positioned} von {voices_total} Stimmen ({prozent} %) beziehen in der Simulation Stellung zur Streitfrage. Der Simulationsverlauf trägt deshalb wenig zum Bericht bei."`
     - `collect_run_degradations` bekommt einen Parameter `stance_analysis: Optional[Dict[str, Any]] = None` und hängt das Ergebnis an.
     Schweregrad ist bewusst `warning`: Der Bericht bleibt lesbar, die Degradation ist sichtbar. `blocking` würde jeden heutigen Lauf auf `incomplete` setzen.
  6. `backend/app/services/report_agent/workflow.py`: Die Analyse **einmal vor dem ersten Abschnitt** berechnen, das Ergebnis am Agenten ablegen (`agent.stance_analysis`) und an beiden Aufrufstellen von `collect_run_degradations` (Zeile ~1687 und ~2226) übergeben. Finde die Stelle, an der `_init_evidence_map` aufgerufen wird (CRG: `query_graph_tool(pattern="callers_of", target="_init_evidence_map")`), und rufe `build_stance_analysis` direkt danach auf. Der LLM-Client muss derselbe sein, den der Report-Agent verwendet, damit die Aufrufe im Budget-Ledger des Berichts landen.
- **Tests:** neue Datei `backend/tests/services/report_agent/test_stance_analysis.py`:
  - keine Streitfrage → `applicable is False`, LLM-Stub nicht aufgerufen.
  - 4 Agenten, 2 davon mit je einem `opposed`-Beitrag → `voices_positioned == 2`, `positioning_ratio == 0.5`, `camp_distribution["opposed"] == 2`.
  - Batch-Antwort lässt einen Index aus → dieser Beitrag zählt nicht als positioniert, `classification_failed == 1`.
  - `BudgetExceededError` aus dem Stub kommt beim Aufrufer an.
  In `backend/tests/regression/test_run_degradation.py`: Quote 0,3 → genau ein Eintrag `simulation_positioning` mit `severity == "warning"`; Quote 0,6 → keiner; `applicable=False` → keiner.
- **Prüfbefehl:**
  ```bash
  cd backend && uv run pytest tests/contracts/ tests/services/report_agent/test_stance_analysis.py tests/regression/test_run_degradation.py tests/services/test_partial_report.py -x -q
  cd backend && uv run python -m app.contracts.dump_schemas --check && uv run ruff check . && uv run mypy app
  cd frontend && bun run test src/contracts && bun run check
  ```

### Schritt 1.9 · Dokumentation für Etappe 1

- **Modell:** `glm-5.3-flash`.
- Dateien: `docs/STATUS.md` (Istzustand: Werkzeug, Stimme, Streitfrage, Positionierungsquote), `docs/api.md` und `docs/api-contracts.md` (neues Feld `contested_question` im Prepare-Request, `voice_key` am Beleg, neue Degradationskomponente), `CONTEXT.md` (Abschnitt „Phase 4 — Report": ein Satz zum neuen Werkzeug), `changelog.d/1778-simulation-im-bericht-1.md`.
- Regel: Nur beschreiben, was der Code nach den Schritten 1.1 bis 1.8 tut. Nichts aus Etappe 3 erwähnen.

### Abnahme Etappe 1 (führt der Lead aus, nicht das ausführende Modell)

Ein Lauf mit `seed-3-geburtshilfe-hollerau.md`, Standardwerte, `gpt-6-luna`. Bestanden, wenn:

| Kriterium | Messung |
|---|---|
| Streitfrage steht in `simulation_config.json` mit `origin: "assistant"` | Datei lesen |
| Kein Agent mit `opposing` und positivem `sentiment_bias` oder umgekehrt | `agent_configs` auswerten |
| `stance_analysis.json` existiert, `positioning_ratio` ist gesetzt | Datei lesen |
| Mindestens 25 % der Claims haben einen stützenden Beleg `agent_action` | `evidence_map.json` |
| Weniger als 50 % der Claims liegen exakt bei 0,59 | `evidence_map.json` |
| Kein Eintrag `violation: enum` im Degradationsprotokoll | `meta.json` |

Die Schwellen 25 % und 50 % sind gesetzt, nicht gemessen. Verfehlt der Lauf sie, entscheidet der Maintainer, ob die Schwelle oder der Code falsch ist.

---

## 3. Etappe 2: Belegdichte je Aussage (Issue #1779, eigener PR)

**Neuer Zuschnitt vom 05.10.2026.** Der alte Zuschnitt („Farblosigkeit der Simulation", Abnahmeziel Positionierungsquote über 50 %) ist überholt: Die Quote lag in beiden Abnahmeläufen von Etappe 1 über 93 % (49 von 52 und 58 von 62 Stimmen), ohne dass Etappe 2 begonnen war. Der Maintainer hat den Start von Etappe 2 am 05.10.2026 freigegeben, obwohl die Abnahme Etappe 1 an Kriterium 5 verfehlt ist. Die Schritte unten sind der Vorschlag des Leads; der Maintainer kann sie ändern.

**Befund** (Lauf `sim_1a88f50d89cd`, Bericht `report_7caeb1e0827b`, `evidence_map.json`):

| Messwert | Zähler / Nenner |
|---|---|
| Claims mit genau einem stützenden Beleg | 45 von 71 |
| Claims mit zwei oder mehr stützenden Belegen | 26 von 71 |
| Claims exakt bei 0,59 (Ein-Quellen-Deckel) | 38 von 71 |
| davon gestützt durch ein einzelnes Interview / einen Simulationsbeitrag / ein Seed-Dokument | 26 / 10 / 2 |
| Vorlagen je Ein-Beleg-Claim (Median) | 5, von 4 verschiedenen Stimmen |
| Urteile der übrigen Vorlagen bei Ein-Beleg-Claims | 122 `RELATED_ONLY`, 24 `INSUFFICIENT`, 13 `CONTRADICTED` |
| Textbeiträge, die eine andere Stimme bestätigt (Like, Repost, Zitat) | 101 von 540 |
| Ein-Beleg-Claims, deren Beleg ein von anderer Stimme bestätigter Beitrag ist | 3 von 45 |

Lesart: Den meisten Claims liegen Belege mehrerer Stimmen vor, aber nur einer wird als stützend gewertet. Der Engpass liegt damit zwischen Vorlage und Urteil, nicht beim Finden. Öffentliche Zustimmung (Likes, Reposts) ist im Bericht bisher unsichtbar, trägt für sich aber wenig (3 Claims).

**Nicht geklärt:** warum bei inhaltlich ähnlichen Interviewantworten eine als `SUPPORTED` und andere als `RELATED_ONLY` oder `CONTRADICTED` gewertet werden. Dafür ist eine Messung mit Modellaufrufen nötig (Schritt 2.3).

**Die alten Befunde aus #1779** (regelbasierte Default-Haltung `neutral`, bremsender Haltungssatz, Skeptiker ohne Profil, Namensabweichungen zwischen Profil und Konfiguration) sind nicht Teil dieses Zuschnitts. Die Zuordnung Konfiguration → OASIS-Agent ist seit PR #1785 korrigiert. Offen bleibt, warum einzelne Profile fehlen (Agenten 9 und 35 im Lauf `sim_1a88f50d89cd`).

### Schritt 2.1 · Belegdichte als Messwert im Bericht

- **Ziel:** Die Abnahme wird aus einem Artefakt gelesen statt mit einem Handskript gezählt.
- **Vertrag:** `backend/app/contracts/evidence_density_contract.py`, Modell `EvidenceDensity` (Pydantic v2, `extra="forbid"`): `schema_version`, `claims_total`, `claims_without_support`, `claims_single_support`, `claims_multi_support`, `claims_multi_independent` (zwei oder mehr unabhängige Quellen nach `_count_independent_sources`), `claims_at_single_source_cap` (Score exakt 0,59), `claims_with_action_support`, `supporting_links_by_type` (Belegart → Zahl), `single_support_ratio`, `action_support_ratio`. Im Schema-Register von `dump_schemas` eintragen.
- **Berechnung:** reine Funktion `compute_evidence_density(evidence_map)` in `backend/app/services/report_agent/evidence_density.py`, ohne Modellaufruf.
- **Persistenz:** `evidence_density.json` im Berichtsordner, atomar geschrieben, beim Abschluss des Berichts (auch bei `INCOMPLETE`).
- **Tests:** Zählung an einer kleinen, handgebauten `evidence_map`; Vertragstest; Test, dass die Datei auch bei `INCOMPLETE` entsteht.
- **Nicht tun:** keine neue Degradation, keine Änderung an Schwellen oder am Confidence-Rechner.

### Schritt 2.2 · Öffentliche Zustimmung als Stimme am Beleg

- **Ziel:** Bestätigt eine andere Stimme einen Beitrag öffentlich (`LIKE_POST`, `LIKE_COMMENT`, `REPOST`, `QUOTE_POST`), steht das am Beleg.
- **Vertrag zuerst:** optionales Feld `endorsing_voice_keys` am Beleg `agent_action`, analog zu `voice_key` (Schritt 1.2). Die Stimme des Autors zählt nicht mit. Aktionen mit hartem Rollenkonflikt zählen nicht.
- **Offene Entscheidung des Maintainers, vor der Umsetzung des zweiten Teils:** ob eine bestätigende Stimme beim Ein-Quellen-Deckel als unabhängige Quelle zählt. Dagegen spricht, dass ein Like billig ist; dafür, dass der bestätigte Beitrag selbst die Entailment-Prüfung bestanden hat. Bis zur Entscheidung wird das Feld nur geschrieben und angezeigt, der Confidence-Rechner bleibt unverändert.

### Schritt 2.3 · Diagnose: Vorlage und Urteil bei Interviews

- **Ziel:** klären, warum von mehreren Vorlagen meist nur eine stützt. Kandidaten: zusammengesetzte Claims (Median drei Teilaussagen), die keine einzelne Antwort ganz deckt; schwankende Urteile bei langen Interviewantworten (rund 3.000 Zeichen, mehrere Fragen).
- **Vorgehen:** Nur-Lese-Messung am Bericht `report_7caeb1e0827b` mit demselben Judge. Sie braucht Modellaufrufe und läuft erst nach Freigabe des Maintainers.
- **Ergebnis:** Befund mit Zählern; daraus folgen die Schritte 2.4 ff. Ohne diesen Befund wird an der Entailment-Stufe nichts geändert.

### Schritt 2.4 ff.

Werden nach Schritt 2.3 ausgearbeitet.

### Abnahme Etappe 2 (führt der Lead aus, nach Freigabe des Laufs durch den Maintainer)

Ein Lauf mit `seed-3-geburtshilfe-hollerau.md`, Standardwerte, `gpt-6-luna`. Bestanden, wenn in `evidence_density.json`:

| Kriterium | Feld |
|---|---|
| Weniger als 50 % der Claims liegen exakt bei 0,59 | `claims_at_single_source_cap` / `claims_total` |
| Mindestens 50 % der Claims haben zwei oder mehr unabhängige stützende Quellen | `claims_multi_independent` / `claims_total` |
| Mindestens 25 % der Claims haben einen stützenden Beleg `agent_action` | `action_support_ratio` |

Die Schwellen sind gesetzt, nicht gemessen. Die Lagerverteilung wird nicht künstlich ausgeglichen, und die Entailment-Prüfung wird nicht gelockert: Ein Beleg zählt nur, wenn er den Claim inhaltlich stützt.

---

## 4. Etappe 3: Verlauf (zweiter PR des großen Issues)

Erst starten, wenn Etappe 2 abgenommen ist. Vor dem Start alle Anker neu prüfen, weil Etappe 1 und 2 Zeilennummern verschieben.

### Schritt 3.1 · Interviewhaltung in die Analyse aufnehmen

- **Modell:** `glm-5.3-flash`.
- `build_stance_analysis` füllt `interview_class` je Stimme aus den Interview-Belegen des Berichts (`topic_stance` am Beleg, `voice_key` aus Schritt 1.2). Abbildung: `topic_stance >= 0.25` → `in_favour`, `<= -0.25` → `opposed`, sonst `undecided`. Mehrere Interviews derselben Stimme: Mittelwert.
- Da Interviews erst während der Abschnitte entstehen, läuft dieser Teil **nach** dem letzten Abschnitt und aktualisiert `stance_analysis.json`.
- Test: drei Interview-Belege, zwei Stimmen, erwartete Klassen.

### Schritt 3.2 · Positionswechsel und Haltungsabweichung berechnen

- **Modell:** `glm-5.3`.
- Vertrag `stance_analysis_contract.py` erweitern: `PositionShift` (`voice_key`, `agent_name`, `from_class`, `to_class`, `first_round`, `evidence_producer_key`) und `StanceDeviation` (`voice_key`, `agent_name`, `start_class`, `interview_class`). Listen `position_shifts` und `stance_deviations` an `StanceAnalysis`.
- Regeln, genau so:
  - Endklasse einer Stimme = Klasse ihrer Beiträge im letzten Drittel der Runden (Mehrheit unter `in_favour`/`opposed`; ohne solchen Beitrag: `undecided`).
  - **Positionswechsel:** `start_class != Endklasse` **und** Endklasse ist `in_favour` oder `opposed` **und** es gibt mindestens einen Beitrag der Stimme mit der Endklasse. `first_round` = Runde des ersten solchen Beitrags, `evidence_producer_key` = dessen `producer_key`.
  - **Haltungsabweichung:** `interview_class` ist gesetzt, `interview_class != start_class`, und es gibt **keinen** Beitrag der Stimme mit `interview_class`.
  - Eine Stimme kann nicht beides sein; Positionswechsel hat Vorrang.
- Tests für die drei Szenarien aus der Grilling-Sitzung (Bürgerinitiative, Kreistagsfraktion, Betriebsrat) plus „kein Wechsel".

### Schritt 3.3 · Lager und Koalitionen berechnen

- **Modell:** `glm-5.3`.
- Vertrag: `Coalition` (`stance_class`, `members: list[voice_key]`, `role_families: list[str]`, `supporting_interactions: int`, `example_producer_keys: list[str]`). Liste `coalitions` an `StanceAnalysis`.
- Zustimmender Bezug, erster Schnitt: nur `LIKE_POST`, `LIKE_COMMENT`, `REPOST`, `QUOTE_POST`. `CREATE_COMMENT` zählt nicht. Die Auflösung „wer reagiert auf wen" übernimmt die vorhandene Logik in `backend/app/services/network_analytics.py` (`_iter_interactions`, Zeile 359, `_extract_target_agent`, Zeile 197). Diese Funktionen wiederverwenden, nicht nachbauen.
- Regel: Gruppe aus Stimmen derselben Endklasse (`in_favour` oder `opposed`), verbunden über zustimmende Bezüge, mit Mitgliedern aus mindestens zwei verschiedenen Rollenfamilien. Rollenfamilie je Stimme aus `entity_type` in `agent_configs`. Zusammenhangskomponenten über die zustimmenden Bezüge bilden; Komponenten mit nur einer Rollenfamilie verwerfen.
- Tests für die vier Szenarien (Koalition; gleiche Rollenfamilie; Konfliktlinie; gleiches Lager ohne Bezug).

### Schritt 3.4 · Verlaufs-Befunde als Belege und im Abschnitts-Prompt

- **Modell:** `glm-5.3`.
- Jeder Positionswechsel und jede Koalition wird ein Beleg in der globalen Evidence (wie die Netzwerk-Metriken in `_collect_simulation_evidence_items`), Typ `agent_action`, mit dem `producer_key` des belegenden Beitrags als Anker, damit der Beleg auf einen echten Simulationsbeitrag zeigt.
- Der Abschnitt „Handlungsempfehlung" bekommt die Zusammenfassung der Analyse als Kontext (Positionierungsquote, Lagerverteilung, Liste der Positionswechsel, Liste der Koalitionen, oder ausdrücklich „keine beobachtet"). Einfügen **außerhalb** des Blocks `<evidence_gating priority="hard">`.
- Wortlaut für den leeren Fall, den der Bericht übernehmen darf: „In der Simulation wurde kein Positionswechsel beobachtet." und „In der Simulation hat sich keine Koalition gebildet."

### Schritt 3.5 · Pflichtaspekte an Streitfrage und Fragestellung koppeln

- **Modell:** `glm-5.3`.
- `backend/app/services/report_agent/requirement_checker.py`, `checklist_for_intent` (Zeile 238) bekommt zwei weitere Parameter: `has_contested_question: bool` und `simulation_requirement: str`.
  - Explorativ: weiterhin `()`.
  - `positionswechsel` und `koalitionen`: nur in der Liste, wenn `has_contested_question` wahr ist.
  - `stop_bedingungen` und `expand_bedingungen`: nur in der Liste, wenn `simulation_requirement` (kleingeschrieben) eines dieser Muster enthält: `pilot`, `stufenweise`, `schrittweise`, `einführung`, `einfuehrung`, `rollout`, `ausweit`, `skalier`, `testphase`, `phased`, `roll-out`, `scale up`.
  - `stakeholder_widersprueche` und `fruehwarnindikatoren`: immer.
- Die Muster für `positionswechsel` und `koalitionen` um die Wortlaute aus Schritt 3.4 ergänzen, damit „kein Positionswechsel beobachtet" den Aspekt erfüllt.
- Aufrufer `workflow.py:1810` anpassen; `has_contested_question` aus `agent.stance_analysis`.
- Tests in `backend/tests/services/test_requirement_checker.py`: Hollerau-Fragestellung ohne Pilot → Stop und Expand nicht verlangt; Fragestellung mit „Pilotprojekt" → verlangt; ohne Streitfrage → Positionswechsel und Koalitionen nicht verlangt. Der vorhandene Test bei Zeile 132 (alle vier Intents teilen die Liste) wird dadurch falsch und **darf** an die neue Signatur angepasst werden; die Erwartung „explorativ ist leer" (Zeile 138) bleibt.

### Schritt 3.6 · Degradationen der Simulation im Berichtstext und in der Oberfläche

- **Modell:** `glm-5.3` (Prompt) und `glm-5.3-flash` (Frontend).
- Der Abschnitt „Unsicherheiten und Datenlücken" (bzw. der letzte Abschnitt, wenn es ihn nicht gibt) bekommt die Einträge aus `run_degradations` mit Komponente `simulation` und `simulation_positioning` als Kontext, mit der Anweisung, sie in einem Satz je Eintrag zu nennen. Nicht als Data Gap ausgeben.
- Frontend: `run_degradations` im Bericht anzeigen. Vorlage `frontend/src/components/DegradationNotice.vue` (heute nur in `Step2EnvSetup.vue:317` und `StepGraphBuildView.vue:24` eingebunden); in der Berichtsansicht einbinden.

### Abnahme Etappe 3

| Kriterium | Messung |
|---|---|
| Bericht nennt Positionswechsel und Koalitionen oder ausdrücklich „keine beobachtet" | Berichtstext |
| Status nicht `incomplete` wegen `positionswechsel`, `koalitionen`, `stop_bedingungen`, `expand_bedingungen` | `meta.json` |
| Ausfallquote der Simulation steht im Berichtstext, falls es eine Degradation gibt | Berichtstext |
| Jeder genannte Positionswechsel hat einen Beleg, der auf einen Simulationsbeitrag zeigt | `evidence_map.json` |

---

## 5. Was nicht in dieses Issue gehört

| Befund | Ziel |
|---|---|
| B2, B3, B4, B5, B10, B11, B16, B17, B18 | zusätzliche Punkte in #1766 |
| S4 (Tageslimit des Anbieters als Preflight-Warnung), S5 (Deckel zählt nur ungecachte Tokens, bleibt 20 Mio.), A1 bis A5 | zusätzliche Punkte in #1772 |
| Gr1 bis Gr4 (Dubletten, Entitäten ohne Relation, Sprachmix, fehlende Zahlen im Graphen) | offen: #1470 und #1471 sind geschlossen; Ziel entscheidet der Maintainer |
| 54 Agenten, aber 50 Profile: die vier synthetischen Skeptiker haben kein Profil und schreiben nie | Punkt in #1779 |
| Name im Profil weicht bei 7 von 50 Agenten vom Namen in der Konfiguration ab (4 Organisationen, die über eine Person laufen oder ein „Dr." im Namen; 3 Personen mit ganz anderem Namen: Agenten 23, 27, 28). Aktionen tragen den Konfigurationsnamen, Interviews den Profilnamen. Derselbe Agent erscheint im Bericht unter zwei Namen. | Punkt in #1779 |
| Ursache der Farblosigkeit | eigenes Issue, Etappe 2 |

## 6. Kosten und Randbedingungen der Abnahmeläufe

- Je Lauf rund 0,70 $ (`gpt-6-luna`), dazu etwa 1 Cent für die Klassifikation der Beiträge.
- Das Tageslimit des Anbieters (20 Mio. Tokens, gecachte zählen mit) erlaubt einen Lauf pro Tag.
- Deployment auf gns3 und jeder Lauf nur auf ausdrückliche Ansage des Maintainers. Das gilt auch für Nur-Lese-Messungen mit vielen Modellaufrufen.
