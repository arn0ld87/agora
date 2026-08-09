# Task B3 — Interview-to-agent-Quote-Evidence Binding

Untersucht am Branch `feat/1152-document-chunk-provenance` (HEAD `7e42ae34`).
Referenzlauf: `docs/reference-runs/2026-08-09-domain-migration-v2/` (R2, `report_06f654800817` / `sim_464a7a8e6310`).

## Sources

| file:line | Source-Type | Inhalt |
|---|---|---|
| `backend/app/services/report_agent/agent.py:301-452` | official | `_record_tool_evidence` — Tool-Evidence-Registrierung, Interview-Zweig ab L. 365 |
| `backend/app/services/report_agent/agent.py:70` | official | Import `InterviewResult` |
| `backend/app/services/report_agent/agent.py:313-314` | official | Kommentar nennt explizit `report_06f654800817: 0 von ~40 Interview-/Fakten-Items im evidence_index` |
| `backend/app/services/report_agent/evidence.py:44-61` | official | `_TYPE_TO_SOURCE_KIND` Mapping (`agent_interview → agent_quote`) |
| `backend/app/services/report_agent/evidence.py:112-140` | official | `register_evidence_record` — silent Drop bei leerem `producer_key` (L. 120-122) |
| `backend/app/services/report_agent/evidence.py:160-198` | official | `_count_supporting_stakeholder_groups`, `has_agent_grounded_evidence` |
| `backend/app/services/evidence_identity.py:18-57` | official | `build_evidence_id`, `build_producer_key` |
| `backend/app/contracts/report_contract.py` | official | `EvidenceSourceKind`-Enum, `EvidenceRecordModel`, `agent_quote_needs_stakeholder_group`, `cross_stakeholder_for_high` |
| `backend/app/contracts/interview_envelope_contract.py:33-49` | official | `InterviewEnvelope` — API-Antwort-Envelope, kein Evidence-Persistenz-Vertrag |
| `backend/app/services/graph/graph_dtos.py:257-319` | official | `AgentInterview`-/`InterviewResult`-Dataclasses — kein `producer_key`-Feld |
| `backend/app/services/graph_tools.py` (`interview_agents`) | official | populates `result.interviews` nur bei `api_result["success"]` |
| `backend/app/services/tool_execution.py:115-124, ~207` | official | Dispatch `interview_agents` → `record_evidence(structured_result=InterviewResult, …)` |
| `backend/app/services/report_agent/tools.py:90` | official | `record_evidence=agent._record_tool_evidence` |
| `backend/tests/services/test_report_tool_evidence.py:110-204` | official | `test_interview_response_gets_canonical_evidence_id`, `test_empty_interview_response_is_skipped` |
| `backend/tests/services/test_graph_tools_interview_soft_fail.py` | official | Soft-Fail-Pfad (tote Sim + kein Direktpfad → leere `interviews`) |
| `backend/tests/services/test_graph_tools_interview_uses_direct_path.py` | official | Direktpfad-Test (persistierte Personas) |
| `docs/reference-runs/2026-08-09-domain-migration-v2/artifacts/evidence-extract.json:120-154` | official | `evidence_index_summary: {agent_action: 8, graph_metric: 4}`, `interview_evidence_items_detected_in_index: 0` |
| `docs/reference-runs/2026-08-09-domain-migration-v2/artifacts/README.md:29-39` | official | „keine im Evidence Index erkannte kanonische Interview-Evidence … Root Cause muss im Produktcode reproduziert werden" |
| `git log d7d9f0a4` (2026-08-09 07:24) | official | PR #1151 „Evidence-Provenance-Pipeline — Interviews/Fakten kanonisch persistieren" — enthält den Fix im Interview-Zweig |

## Findings

1. **Kanonische `evidence_id` entsteht in `register_evidence_record`** ([evidence.py:130](backend/app/services/report_agent/evidence.py:130)) via `build_evidence_id(scope_id, source_kind, producer_key)`. Ohne `producer_key` kehrt die Funktion **vor** der ID-Konstruktion mit `None` zurück ([evidence.py:120-122](backend/app/services/report_agent/evidence.py:120)) — das Item wird **still verworfen**, weder in `evidence_index` noch in `global_evidence_refs` noch in `_active_section_evidence`.

2. **`persona_stakeholder_group` wird im Interview-Zweig gesetzt** ([agent.py:388-404](backend/app/services/report_agent/agent.py:388)): Fallback-Kette `agent_role → agent_name → "unbekannt"`, auf 200 Zeichen gekappt. Der Contract-Validator `agent_quote_needs_stakeholder_group` ([report_contract.py](backend/app/contracts/report_contract.py)) fordert für `source_kind=agent_quote` nicht-leeres `persona_stakeholder_group` — wäre das Feld leer, würde `EvidenceRecordModel.model_validate` werfen und das Item landet im `unresolved_evidence`-Audit-Trail ([agent.py:451-459](backend/app/services/report_agent/agent.py:451)).

3. **Report-Text ohne evidence_index-Eintrag war der Pre-Fix-Zustand.** Der Referenzlauf `report_06f654800817` zeigt `interview_evidence_items_detected_in_index: 0` ([evidence-extract.json:150](docs/reference-runs/2026-08-09-domain-migration-v2/artifacts/evidence-extract.json:150)). Der Code-Kommentar [agent.py:313-314](backend/app/services/report_agent/agent.py:313) bestätigt exakt diesen Befund für diesen Report. Root Cause: der alte Interview-Zweig erzeugte Items **ohne `producer_key`** → `register_evidence_record` dropte sie still. DieInterview-Antworten flossen nur über `structured_result.to_text()` / den `summary`-Render in den Reporttext, nicht als kanonische Items.

4. **`cross_stakeholder_for_high` (ADR-0002 Anker 4)** fordert `agent_quote`-Evidence mit `supports_claim=True` aus ≥ 2 unterschiedlichen `persona_stakeholder_group`-Werten. Interviews erreichen `high` aktuell aus zwei Gründen nicht: (a) im Pre-Fix-Stand gar nicht im `evidence_index`; (b) der Interview-Zweig setzt **nicht** `supports_claim=True` ([agent.py:397-413](backend/app/services/report_agent/agent.py:397)) — das Feld fällt unter `_CLAIM_RELATIVE_FIELDS` ([evidence.py:102-109](backend/app/services/report_agent/evidence.py:102)) und wird erst später im Claim-Binding (`bind_evidence_to_claim`) gesetzt. Erst dort entscheidet sich, ob ein Interview-Item einen Claim stützt.

5. **`producer_key` für Interviews WIRD konstruiert** ([agent.py:406-412](backend/app/services/report_agent/agent.py:406)) — `build_producer_key(f"interview:s{section_index}", topic, agent_name, question, response)`. Der Hash basiert auf Section + Topic + Agent + Frage + Antwort; gleicher Text verschiedener Agenten kollabiert nicht, zwei Fragen an denselben Agenten bleiben unterscheidbar. Dieser Code ist Teil des Fixes `d7d9f0a4` (PR #1151, 2026-08-09 07:24) und liegt in HEAD `7e42ae34`.

6. **Der Fix `d7d9f0a4` adressiert genau den Defekt.** Git-Blame ([agent.py:365-413](backend/app/services/report_agent/agent.py:365)) zeigt: der alte Zweig iterierte nur `for interview in structured_result.interviews[:6]` ohne Identität/Provenance. Die aktuelle Fassung setzt `type=agent_interview`, `quote`, `persona_stakeholder_group`, `producer_key`. Test `test_interview_response_gets_canonical_evidence_id` ([test_report_tool_evidence.py:110-136](backend/tests/services/test_report_tool_evidence.py:110)) belegt: 2 Interviews → 2 `agent_interview`-Records, alle mit `source_kind=agent_quote`, gültigem `evidence_id`, nicht-leerem `quote` und `persona_stakeholder_group`.

7. **`source_kind`-Mapping für Interviews ist kanonisch.** `agent_interview` → `agent_quote` ist in `_TYPE_TO_SOURCE_KIND` ([evidence.py:49](backend/app/services/report_agent/evidence.py:49)) fest verdrahtet. `normalize_source_kind` ([evidence.py:74-88](backend/app/services/report_agent/evidence.py:74)) zieht ein explizites `source_kind` vor, fällt sonst auf den Typ zurück. `agent_quote` ist Teil von `_VALID_SOURCE_KINDS` ([evidence.py:69-71](backend/app/services/report_agent/evidence.py:69)).

8. **Soft-Fail-Pfad erzeugt keine Evidence (by Design).** `GraphToolsService.interview_agents` ([graph_tools.py](backend/app/services/graph_tools.py)) liefert bei toter IPC-UMgebung + fehlendem Direktpfad ein `InterviewResult` mit leerer `interviews`-Liste und terminaler `summary` („Do NOT call interview_agents again"). Der leere `interviews`-Iterator erzeugt keine Items → `evidence_index` bleibt leer. Test-Coverage: `test_graph_tools_interview_soft_fail.py` (Soft-Fail), `test_graph_tools_interview_uses_direct_path.py` (Direktpfad mit persistierten Personas).

9. **API-Endpunkte persistieren keine Evidence.** `/interview`, `/interview/batch`, `/interview/all` ([simulation_interviews.py](backend/app/api/simulation_interviews.py)) antworten via `InterviewEnvelope` ([interview_envelope_contract.py:33-49](backend/app/contracts/interview_envelope_contract.py:33)) — HTTP 200 + `data: dict[str, Any]` mit dem rohen Runner-Result. Kanonische Evidence entsteht **ausschließlich** im ReportAgent-Tool-Pfad (`tool_execution.py` → `_record_tool_evidence`), nicht in der Interview-API.

10. **`question`-Feld im Producer-Key ist der kombinierte Prompt, nicht die Einzelfrage.** `AgentInterview` wird in `interview_agents` mit `question=combined_prompt` (alle Fragen zusammengeführt) konstruiert, nicht mit der spezifischen Frage pro Agent. Der Producer-Key ist trotzdem deterministisch (Antwort + Agent + Topic differenzieren); die Semantik des `question`-Feldes in der Identitätsbasis ist aber gröber als im ADR-0013-Draft angedacht.

## Binding-Defekt-Lokalisation

Konkreter Code-Pfad, an dem das Binding (im Pre-Fix-Stand, dokumentiert durch R2) brach:

```
GraphToolsService.interview_agents()  →  InterviewResult(interviews=[AgentInterview(...)])
        │
        ▼  (tool_execution.py:124, übergeben als structured_result)
execute_tool()  →  record_evidence = agent._record_tool_evidence  (tools.py:90)
        │
        ▼  (tool_execution.py:~207)
ReportAgent._record_tool_evidence(tool_name, parameters, structured_result, rendered, section_index)
        │
        ▼  isinstance(structured_result, InterviewResult)  →  True  (agent.py:365)
        │
        ▼  [Pre-Fix]  for interview in structured_result.interviews[:6]:
        │               item = { type, tool_name, query, snippet, raw, agent_log_ref }
        │               ❌ KEIN producer_key
        ▼
register_evidence_record(evidence_map, item, scope_id=simulation_id)
        │
        ▼  producer_key = ""  →  return None   (evidence.py:120-122)  ← HIER BRICHT DAS BINDING
        │
        ▼  Item verworfen, evidence_index bleibt leer
        │
Report-Render: Interview-Antworten erscheinen nur via structured_result.to_text()/summary
              als freier Text im Reportbody, nicht als kanonische evidence_id-referenzierte Items.
```

**Bruchstelle:** `register_evidence_record` ([evidence.py:120-122](backend/app/services/report_agent/evidence.py:120)) — `if not producer_key: return None`. Das ist der universelle Silent-Drop für alle Items ohne Identitätskey; im Pre-Fix-Stand betraf es **alle** Interview-Items (undGraph-Fakt-Items), im R2 belegt durch `interview_evidence_items_detected_in_index: 0`.

## Fix-Pfad

Der Fix ist **bereits in HEAD** (`d7d9f0a4`, PR #1151). Minimal-Änderung, die den Defekt behebt (Status: implementiert):

1. **`producer_key` im Interview-Zweig setzen** — [agent.py:406-412](backend/app/services/report_agent/agent.py:406):
   ```python
   "producer_key": build_producer_key(
       f"interview:s{section_index}",
       topic or "no-topic",
       agent_name,
       question,
       response,
   ),
   ```
2. **`persona_stakeholder_group` setzen** (damit `agent_quote_needs_stakeholder_group` nicht wirft) — [agent.py:404](backend/app/services/report_agent/agent.py:404).
3. **`quote` setzen** (damit `has_agent_grounded_evidence` zählt) — [agent.py:403](backend/app/services/report_agent/agent.py:403).
4. **Substanz-Filter** gegen Platzhalter-Antworten stummer Plattformen — [agent.py:380-383](backend/app/services/report_agent/agent.py:380), damit keine Schein-Interviews als `agent_quote` persistieren.
5. **`type=agent_interview`** → wird via `_TYPE_TO_SOURCE_KIND` kanonisch zu `source_kind=agent_quote` gemappt — [evidence.py:49](backend/app/services/report_agent/evidence.py:49).

Bleibende Aufgabe (nicht Teil des Fixes): Re-Run des R2-Szenarios gegen den aktuellen Stand, um `interview_evidence_items_detected_in_index > 0` end-to-end zu verifizieren. Der Referenzlauf dokumentiert den Pre-Fix-Stand; ein aktualisierter Extract steht noch aus.

## Gaps

- **Kein Re-Run nach `d7d9f0a4`.** R2 (`report_06f654800817`) wurde vor oder unabhängig vom Fix eingefroren (SHA-256 in README fixiert). Der Extract belegt den Defekt, nicht die Heilung. Eine Bestätigung, dass der Fix im echten Lauf greift, fehlt — nur die Unit-Tests (`test_report_tool_evidence.py`) decken den Pfad ab.
- **`supports_claim` fehlt im Interview-Item.** Der Interview-Zweig setzt `supports_claim` nicht. `cross_stakeholder_for_high` verlangt `supports_claim=True`. Ob ein Interview-Item einen Claim stützt, entscheidet erst `bind_evidence_to_claim` im Claim-Binding. Falls das Binding `supports_claim` nicht oder false setzt, können Interviews `high` nie rechtfertigen — selbst wenn sie kanonisch persistieren.
- **Soft-Fail- vs. Echt-Interview-Diskriminierung im Audit.** Der R2-Extract zeigt `interview_selection_by_section` (aus Logs geparst) aber nicht, ob `result.interviews` tatsächlich gefüllt war. Wenn die Interview-API im R2 soft-failte (tote Sim, Direktpfad evtl. nicht verfügbar), wäre `interviews=[]` und die 0 Items sind by Design, kein Binding-Defekt. Diese Unterscheidung ist aus dem Extract allein nicht möglich.
- **`question`-Feld im Producer-Key ist `combined_prompt`**, nicht die spezifische Frage. Semantisch unpräzise gegenüber der Spec `hash(topic, agent, question, response)`, funktional nicht breakend (Antwort + Agent differenzieren ausreichend).
- **`interview_envelope_contract.py` trägt keine Provenance.** Der `InterviewEnvelope`-Vertrag modellt bewusst nur die HTTP-200-Legacy-Form, nicht die kanonische Evidence-Persistenz. Eine Contract-Lücke besteht nicht, aber der Name legt eine Nähe zur Evidence-Persistenz nahe, die faktisch nicht besteht.
- **`AgentInterview`/`InterviewResult`-Dataclasses ([graph_dtos.py:257-319](backend/app/services/graph/graph_dtos.py:257)) haben kein `producer_key`-Feld.** Die Identität wird im ReportAgent konstruiert, nicht im DTO. Konsistent mit `build_producer_key` als run-lokaler Identität, aber das DTO ist damit nicht eigenständig referenzierbar — erst der ReportAgent macht es kanonisch.