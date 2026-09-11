# Repository-weites LOC- und Struktur-Audit

Stand: 2026-09-11  
Basis-Commit: `4496d7ad425593ec12084e508d3f148be9a4166e` (`main`)  
Status: Zwei verhaltensneutrale Refactoring-Slices umgesetzt; Abschlussverifikation durch die Protected Gates ausstehend

## Ziel und Regeln

Dieses Audit nutzt LOC nur als Screening-Signal. Refactoring-Prioritaet entsteht aus der Kombination aus Groesse, Verantwortungsmischung, Komplexitaet, Kopplung, Aenderungswahrscheinlichkeit und Risiko. Grosse, fachlich kohaerente Contracts duerfen bewusst gross bleiben; kleinere God-Module koennen dagegen hoeher priorisiert werden.

Vor der Analyse wurden `CLAUDE.md`, `AGENTS.md`, `docs/agents/tool-pipeline.md` und die spezialisierten Agent-Profile unter `.claude/agents/` gelesen. Die dort definierten Contract-, Evidence-, Schema-, Security-, Git- und Test-Gates bleiben bindend. Die geschuetzten Evidence-Gating-Anker werden nicht veraendert. Vendored OASIS-Source, generierte Artefakte und `design/**` sind nicht Teil des produktiven LOC-Refactorings.

## Messmethode

Der erste Screening-Durchlauf lief ueber den GitHub-Connector. Fuer den aktuellen Inventarstand wurde das Inventar anschliessend in GitHub Actions reproduzierbar ueber `git ls-files` erzeugt. Gezaehlt werden logische Textzeilen (`splitlines()`) fuer alle getrackten `.py`, `.ts`, `.tsx`, `.vue`, `.js` und `.sh`-Dateien. Tests werden separat klassifiziert; `design/`, Vendor-/Build-/Dist-Verzeichnisse und eindeutig generierte Dateien sind ausgeschlossen.

Die vollstaendigen Rohdaten stehen in `docs/refactor/loc-inventory.tsv`, die menschenlesbare Rangliste in `docs/refactor/loc-inventory.md`. Damit sind die frueheren Schwellenproben durch exakte Repo-Zahlen ersetzt.

Aktueller Inventarstand: **633 Produktionsdateien**, **755 Testdateien**, davon im Produktionscode **23 P0**, **49 P1**, **57 P2** und **75 P3**.

## Ausschluesse

Nicht in der normalen Rangliste:

- `.git/`, `.claude/worktrees/`
- `node_modules/`, `.venv/`, `venv/`
- `dist/`, `build/`, `coverage/`
- Lockfiles
- generierte Schemas/Clients/Artefakte
- Snapshots und reine Fixtures/Testdaten
- vendored/externe Quellen und OASIS-Source
- `design/**` (Repo selbst markiert diesen Bereich als vendored/statische Design-Mockups)

Tests werden separat betrachtet.

## Screening-Klassen

| Klasse | LOC |
| --- | ---: |
| P0 / kritisch | > 800 |
| P1 / hoch | 501-800 |
| P2 / pruefen | 351-500 |
| P3 / beobachten | 251-350 |

## Priorisierte produktive Kandidaten

| Prioritaet | Datei | LOC | Verantwortlichkeiten | Problem | Refactoring-Vorschlag | Risiko |
| --- | --- | ---: | --- | --- | --- | --- |
| P0 | `backend/app/api/runs.py` | **1419 exakt** | Run-Read-Model, List/Detail/Usage, Stop/Cancel, Graph-Rebuild, Prepare-Restart, Simulation-Resume, Report-Resume, Replay, Manifest, Export | klarer God-Controller; Read-, Lifecycle-, Routing-, Budget- und Worker-Orchestrierung in einem API-Modul; `_build_run_summary` und `_build_run_detail` stehen bereits in der Radon-Allowlist | zuerst reinen Read-Path in fachliches Modul extrahieren; danach Restart/Resume-Strategien pro Run-Typ trennen | mittel bis hoch; Resume/Routing/Budget spaeter separat behandeln |
| P0 | `backend/app/api/simulation_run.py` | **>800 verifiziert** | Start/Stop/Status, Persona-Review-Gate, Budget-Artefakte, Routing/Provider-Aufloesung, Manifest/Lifecycle | API-Transport und Start-Orchestrierung mit Budget-/Provider-Semantik gekoppelt | Request-/Response-Boundary von Start-Phasen und Runtime-Aufbau trennen; keine Provider-Semantik im ersten Slice aendern | hoch |
| P0 | `backend/app/api/simulation_prepare.py` | **>800 verifiziert** | Start-Locks, Request-Parsing, Quota-/Agent-Validierung, Provider/Routing, Prepare-Jobs, Fortschritt | API-Boundary, Concurrency und Orchestrierung vermischt | Lock-/Request-Helfer und Job-Orchestrierung fachlich trennen; Routing unveraendert lassen | mittel bis hoch |
| P0 | `backend/app/services/prepare_service.py` | **>800 verifiziert** | Provider-Aufloesung, Entity-Normalisierung, Quoten, Profile, Config-Generierung, FSM-Orchestrierung | viele fachliche Phasen plus providerkritische Aufloesung in einem Modul | Phasen-/Quota-Helfer fachlich extrahieren; `_resolve_llm_connection` wegen Provider-Semantik separat absichern | hoch |
| P0 | `backend/app/llm/client.py` | **>800 verifiziert** | LLM-Facade, Active-Config/Secrets, Request-Aufbau, JSON-/Tool-/Provider-Kompatibilitaet | trotz bereits erfolgter Splits noch sehr breite Facade; provider-/secret-kritisch | nur klar isolierbare Facade-Helfer extrahieren; keine Routing-/Secret-/Prompt-Semantik als LOC-Massnahme | hoch |
| P0 | `backend/app/services/sim/monitor.py` | **>800 verifiziert** | Monitor-Thread, Terminal-/Manifest-Finalisierung, Cancel/Process-Ueberwachung, Timeline/Stats Read-Aggregation | Thread-/Lifecycle-Seiteneffekte und reine Read-Aggregatoren in derselben Datei | Read-only Timeline/Stats in eigenes Modul; Supervision/Finalisierung kohaerent zusammenlassen | mittel |
| P0 | `backend/app/services/sim/process_manager.py` | **>800 verifiziert** | Prozessstart/-cleanup, Cancel-Abort, Updater-/Prozessverwaltung | Prozess-Lifecycle und Hilfs-/Persistenzlogik sehr breit | Prozess-Lifecycle, Cleanup und Cancel-Artefaktzugriff entlang vorhandener Grenzen trennen | mittel |
| P0 | `backend/app/services/graph_tools.py` | **>800 verifiziert** | Graph-Retrieval, Insight/Panorama/QuickSearch, Interviews, Panel-/Fehlerlogik | eine Serviceklasse traegt mehrere Tool-Familien; hohe Evidence-/Report-Kopplung | Retrieval-Tools und Interview-Tooling hinter bestehenden DTO-/Servicegrenzen trennen | hoch |
| P0 | `backend/app/services/oasis_profile_generator.py` | **>800 verifiziert** | Persona-/OASIS-Profilgenerierung, Provider-Aufrufe, Mapping/Fallbacks | Generierung, Normalisierung und Provider-Interaktion stark gekoppelt | reine Mapping-/Normalisierungslogik zuerst extrahieren; LLM-/Fallback-Semantik unangetastet | hoch |
| P0 | `backend/app/services/simulation_config_generator.py` | **>800 verifiziert** | Config-Generierung, LLM-Ausgabe-Normalisierung, Wert-/Schedule-Parsing | Generator und umfangreiche Normalisierung/Parsing in einer Datei | deterministische Parser/Normalizer in fachliches Config-Normalization-Modul extrahieren | mittel |
| P0 | `backend/app/services/report_agent/agent.py` | **>800 verifiziert** | Report-Agent-Facade, Evidence-Binding, Claim-Verarbeitung, Section-Pipeline, Tool-/Prompt-Anbindung | zentrale Report-/Evidence-Drehscheibe mit sehr breiten Abhaengigkeiten | nur nach Evidence-/Contract-Tests weiter zerlegen; Facade auf bereits vorhandene Submodule reduzieren | sehr hoch |
| P0 | `backend/app/services/report_agent/workflow.py` | **>800 verifiziert** | ReAct/Chat/Tool-Call-Workflow, Final-Answer- und Fallback-Steuerung | Prompt-/Tool-/Evidence-Gate-Semantik; bestehender Complexity-Hotspot | spaeter in klar definierte Workflow-Phasen schneiden, nur mit Characterization-Tests | sehr hoch |
| P0 | `backend/app/services/report_agent/evidence.py` | **>800 verifiziert** | Evidence-Map, Normalisierung, Provenance, Degradation/Violation-Handling | Evidence-Semantik und Contract-Normalisierung stark verdichtet | fachliche Teilmodule nur bei unveraenderten Evidence-Gates/Contracts | sehr hoch |
| P0 | `backend/app/services/evidence_entailment.py` | **>800 verifiziert** | Entailment-Regeln, Text-/Claim-Auswertung, Evidence-Urteile | semantisch hochsensibel; Aufteilung kann Urteilsschwellen veraendern | vorerst nicht mechanisch teilen; zuerst Tests/Regelgruppen kartieren | sehr hoch |
| P0 | `backend/app/services/report_agent/manager.py` | **>800 verifiziert** | Report-Persistenz, Fortschritt, Build-/Manager-Aufgaben | Manager traegt mehrere Lifecycle-/Persistenzaufgaben | Persistenz und Build-Orchestrierung nach Use-Site-Audit trennen | hoch |
| P0 | `backend/app/contracts/report_contract.py` | **>800 verifiziert** | Pydantic-SSoT fuer Report/Evidence, Enums, Validatoren, Schema-Dump-Basis | gross, aber ueberwiegend deklarativ/vertraglich; Split kann Schema-Drift erzeugen | **bewusste Ausnahme vorerst**; nur bei klarer Contract-Domaingrenze und Schema-Gates splitten | sehr hoch |
| P0 | `frontend/src/components/shell/Dossier.vue` | **>800 verifiziert** | Dossier-Darstellung, UI-Logik und umfangreicher Component-Style | SFC sehr gross; Zeile 800 liegt bereits im Style-Block, daher LOC teilweise Styling statt Logik | Script/Template zuerst strukturell bewerten; wiederverwendbare Panels/Styles nur nach A11y-/Component-Tests extrahieren | mittel |
| P0 | `frontend/src/components/v4/steps/Step4Report.vue` | **>800 verifiziert** | Report-Step UI, Interaktionen/Confirm-Flows, Template und Styling | zentrale Report-Komponente mit grosser UI-Oberflaeche | fachliche Report-Panels/Dialogs in Komponenten extrahieren, Contract/Zod-Grenzen nicht veraendern | mittel bis hoch |
| P1 | `backend/app/utils/file_parser.py` | **501-800 verifiziert** | Datei-/Text-Parsing und Chunk-/Boundary-Helfer | mehrere Parsing-Verantwortlichkeiten; guter isolierbarer Kandidat | Parser je Format/Boundary-Verantwortung trennen, API-Facade erhalten | niedrig bis mittel |
| P1 | `backend/app/services/graph_build.py` | **501-800 verifiziert** | Graph-Build-Lifecycle, Progress, Persistenz, Cancel, Fehler-/Degradation-Pfade | zentrale Orchestrierung mit vielen Seiteneffekten | Phasen-/Finalisierungshelfer extrahieren, Lifecycle-Endzustaende unveraendert pinnen | hoch |
| P1 | `backend/app/services/simulation_runner.py` | **501-800 verifiziert** | Runner-Facade und Delegationen zu `sim/*` | bereits teilweise modularisiert; Restgroesse nicht automatisch Fehlarchitektur | nur verbleibende echte Mehrfachverantwortung extrahieren; Thin-Facade darf bewusst bestehen | niedrig bis mittel |
| P1 | `frontend/src/contracts/reportContract.ts` | **501-800 verifiziert** | Frontend-Zod/TypeScript-Spiegel des Backend-Report-Contracts | gross, aber Contract-SSoT/Mirror; Split kann Drift-Gate komplizieren | **bewusste Ausnahme vorerst**, solange Schema-Mirror und Imports kohaerent bleiben | hoch |
| P1 | `backend/app/contracts/report_v3.py` | **794 exakt** | Report-v3-Contract/Normalisierung | deklarativ/vertraglich; keine LOC-Kosmetik | beobachten; nur bei fachlich sauberer Contract-Grenze | hoch |
| P1 | `backend/app/services/report_agent/text_verification.py` | **788 exakt** | deterministische Text-/Prose-Verifikation | Evidence-nah; trotz P1 keine mechanische Aufteilung nur wegen LOC | spaeter nur entlang fachlicher Verifikationsgrenzen | hoch |

### Weitere gescreente Bereiche

Das exakte Inventar in `docs/refactor/loc-inventory.md` ersetzt das fruehere Byte-Vorscreening. Die zuvor nur grob eingeordneten Dateien sind damit abschliessend klassifiziert; es steht keine LOC-Klassifizierung mehr aus. Insbesondere sind `backend/app/config.py` mit **429 LOC (P2)**, `backend/app/__init__.py` mit **465 LOC (P2)** und `backend/app/api/report.py` mit **697 LOC (P1)** erfasst.

Auch Shell-Dateien werden vom gleichen Inventar abgedeckt. Fuer Prioritaet und LOC ist durchgehend `docs/refactor/loc-inventory.md` massgeblich; `scripts/pre-push-gate.sh` bleibt als Gate ausserhalb eines beiläufigen Refactorings.

## Tests separat

Im Frontend wurden mehrere grosse Spec-Dateien gefunden, insbesondere:

- `frontend/src/components/__tests__/Step4Report.spec.ts`
- `frontend/src/components/__tests__/Step3Simulation.spec.ts`
- `frontend/src/components/v4/dashboard/__tests__/HeroNewRun.spec.ts`

Grosse Tests sind nicht automatisch Refactoring-Kandidaten. Sie werden nur gesplittet, wenn Setup/Fixtures/Szenarien selbst unwartbar oder redundant sind.

Fuer `backend/app/api/runs.py` existiert bereits `backend/tests/test_runs_api.py` mit HTTP-Level-Regressionen fuer List/Detail-Summary, Filter, Fehlerfaelle und fehlende Project-/Simulation-Daten. Das macht den Read-Path zum risikoaermsten ersten Slice.

## A. Sofort refactoren

1. **`backend/app/api/runs.py`: Read-Model-Enrichment extrahieren.**
   - Kandidaten: `_resolve_simulation_summary`, `_resolve_project`, `_build_run_summary`, `_attach_summary`, `_build_run_detail`.
   - Zielmodul: fachlich benannt, z. B. `services/run_read_model.py`.
   - Bestehende HTTP-Contracts und `RunDetail` bleiben unveraendert.
   - Vorhandene `test_runs_api.py` dient als Regression-Gate; direkte Characterization-Tests fuer das neue Modul sind sinnvoll.

2. **`backend/app/services/sim/monitor.py`: reine Read-Aggregation von Thread-/Finalisierungslogik trennen.**
   - Erst nach vollstaendigem Use-Site- und Test-Audit.

3. **`backend/app/api/simulation_prepare.py`: Request-/Lock-Helfer gegen Job-Orchestrierung trennen.**
   - Provider-/Routing-Semantik bleibt ausserhalb des ersten Slices.

4. **Frontend P0s (`Dossier.vue`, `Step4Report.vue`) nach Script/Template/Style-Anteil zerlegen.**
   - Nur fachliche Komponenten, keine kosmetische Dateizersplitterung.

## B. Spaeter refactoren

Hoher Nutzen, aber durch Provider-, Lifecycle-, Evidence-, Prompt- oder Contract-Semantik riskanter:

- `backend/app/api/simulation_run.py`
- `backend/app/services/prepare_service.py`
- `backend/app/llm/client.py`
- `backend/app/services/graph_tools.py`
- `backend/app/services/oasis_profile_generator.py`
- `backend/app/services/graph_build.py`
- `backend/app/services/report_agent/agent.py`
- `backend/app/services/report_agent/workflow.py`
- `backend/app/services/report_agent/evidence.py`
- `backend/app/services/evidence_entailment.py`
- `backend/app/services/report_agent/manager.py`

Diese Dateien duerfen nicht in einem Mega-Diff zusammengefasst werden.

## C. Bewusste Ausnahmen

### `backend/app/contracts/report_contract.py`

Gross, aber als Pydantic-Contract-SSoT fachlich kohaerenter als ein typischer Service. Ein Split nur zur LOC-Reduktion wuerde mehr Import-/Schema-Grenzen schaffen und die Drift-Gefahr erhoehen. Vorlaeufig akzeptiert; jede spaetere Aufteilung benoetigt Contract- und Schema-Gates.

### `frontend/src/contracts/reportContract.ts`

Frontend-Spiegel des Report-Contracts. Ebenfalls kein Kandidat fuer mechanisches Zerschneiden. Die bestehende Backend/Frontend-Schema-Synchronitaet hat Vorrang vor einer kleineren Datei.

### `backend/app/services/simulation_runner.py`

Bereits als Facade ueber ausgegliederte `sim/*`-Module strukturiert. Seine Restgroesse wird nicht automatisch als Architekturfehler behandelt. Nur echte verbleibende Mehrfachverantwortung wird spaeter extrahiert.

## Erster Refactoring-Slice: Vertrag vor der Aenderung

Ziel: Read-Model-Enrichment aus `backend/app/api/runs.py` extrahieren.

### Oeffentliche API

Unveraendert:

- `GET /api/runs`
- `GET /api/runs/<run_id>`
- JSON-Huelle und `RunDetail`/`RunsListResponse`
- Summary-Felder `model`, `document_name`, `persona_count`, `graph_id`, `graph_name`, `branch_name`
- Detail-Felder `eta_seconds`, `log_tail`, `metrics`, `budget`, `usage`

### Inputs/Outputs

Input bleibt das vorhandene Run-Manifest plus Project-/Simulation-/Artifact-Store-Read-Model. Output bleibt ein angereichertes `dict`, das anschliessend durch die bestehenden Pydantic-Contracts validiert wird.

### Exceptions und Seiteneffekte

- Project-/Simulation-/Artifact-Enrichment bleibt defensiv und darf den Read-Pfad nicht brechen.
- Budget-/Usage-Anreicherung bleibt best-effort wie bisher.
- Keine neuen Writes; Summary ist Read-only.
- Keine Schema-, Auth-, Security-, Secret-, Provider-, Prompt- oder Routing-Aenderung.

### Externe Abhaengigkeiten

- `ProjectManager`
- `SimulationManager`
- Flask `current_app.extensions['artifact_store']`
- Run-Budget/Usage-Ledger fuer Detail-Enrichment
- bestehende `RunDetail`-/Runs-Contracts

## Geplante Verifikation pro Backend-Slice

```bash
cd backend
uv run pytest tests/contracts/ -x -q
uv run python -m app.contracts.dump_schemas --check
uv run ruff check app/ tests/
uv run mypy app
cd ..
bash scripts/pre-push-gate.sh backend
```

Zusaetzlich fuer den ersten Slice:

```bash
cd backend
uv run pytest tests/test_runs_api.py -q
```

In der aktuellen Connector-Umgebung koennen diese Befehle nicht lokal ausgefuehrt werden. Ein Code-Slice gilt daher erst dann als verifiziert, wenn die entsprechenden PR-Gates/CI-Jobs auf dem Branch gruen sind. Bis dahin wird er im Abschlussaudit nicht als abgeschlossen markiert.

## Historische Baseline vor dem Refactoring

Vor dem ersten Slice war noch kein Produktionscode dieses Auftrags veraendert. Diese Aussage bezieht sich ausschliesslich auf den Basis-Commit `4496d7ad425593ec12084e508d3f148be9a4166e` und ist als historische Baseline zu lesen.

## Nachher-Zustand

Zwei verhaltensneutrale Slices sind im PR implementiert. Ihre **Abschlussverifikation ist weiterhin ausstehend**, solange die erforderlichen Protected Gates fuer den aktuellen PR-Head nicht erfolgreich durchgelaufen sind. Der Commit `80af7ad0ed2835b721225541d5cfdc1ba57f8204` wird daher nicht als abgeschlossen gewertet; seine geschuetzten Workflow-Laeufe endeten mit `action_required` statt mit ausgefuehrten erfolgreichen Jobs. Erfolgreiche Job-/Commit-Nachweise werden erst nach gruener Abschlussverifikation dokumentiert.

## Abschlussentscheidung fuer aktuelle P0-Hotspots

LOC bleibt ein Screening-Signal, kein Selbstzweck. Ein P0 wird in diesem PR nur dann geteilt, wenn die Verantwortung sauber abgrenzbar ist und bestehende Contract-/Semantik-Gates die Verschiebung ohne Parallelumbau absichern.

| Datei | LOC nach Slices | Entscheidung in diesem PR | Begruendung / naechste saubere Grenze |
|---|---:|---|---|
| `backend/app/services/oasis_profile_generator.py` | 2792 | spaeter | Provider-, Fallback- und Persona-Semantik stark gekoppelt; zuerst reine Mapping-/Normalisierungshelfer separat charakterisieren. |
| `backend/scripts/run_parallel_simulation.py` | 2564 | spaeter | eigenstaendiger Runtime-Orchestrator mit Prozess-/IPC-Semantik; eigener Refactor-PR statt Beifang. |
| `backend/app/services/report_agent/workflow.py` | 2272 | bewusste Stop-Bedingung | Prompt-, Tool- und Evidence-Gate-Semantik; nur mit Characterization-Tests pro Workflow-Phase. |
| `backend/app/services/report_agent/agent.py` | 1631 | bewusste Stop-Bedingung | zentrale Evidence-/Claim-/Tool-Facade; geschuetzte Evidence-Gates haben Vorrang vor LOC. |
| `backend/app/llm/client.py` | 1620 | spaeter | Provider-/Secret-/Transport-Semantik; kein mechanischer Split ohne eigene Provider-Regressionen. |
| `backend/app/services/evidence_entailment.py` | 1496 | bewusste Ausnahme | hochsensible Evidence-Urteile; keine LOC-Kosmetik an semantischen Schwellen. |
| `backend/app/services/simulation_config_generator.py` | 1390 | naechster geeigneter Slice | deterministische Parser/Normalizer sind abtrennbar, aber nicht mit diesem PR vermischen. |
| `backend/app/contracts/report_contract.py` | 1318 | bewusste Ausnahme | deklarative Pydantic-SSoT; Split kann Schema-/Zod-Drift statt Wartbarkeit erzeugen. |
| `backend/app/api/runs.py` | 1316 | **teilweise refactored** | Read-Model extrahiert (-103 LOC). Resume/Restart bleibt vorerst, weil Regressionstests Budget-/Cancel-Semantik sogar per `inspect.getsource` an die Funktion pinnen; eigener Folge-Slice erforderlich. |
| `backend/scripts/agent_tools.py` | 1307 | spaeter | Simulations-/Agenten-Tooling als Script-Oberflaeche; Use-Sites und CLI-Kompatibilitaet zuerst separat kartieren. |
| `backend/app/api/simulation_prepare.py` | 1293 | naechster geeigneter Slice | Lock-/Request-/Quota-Helfer sind trennbar; Routing-/Provider-Aufloesung bleibt dabei unveraendert. |
| `backend/app/services/report_agent/manager.py` | 1269 | spaeter | Report-Persistenz und Lifecycle; Endzustands-/Persistenztests vor Split erforderlich. |
| `backend/app/api/simulation_run.py` | 1133 | spaeter | Start, Budget, Routing und Manifest-Lifecycle eng gekoppelt; eigener Contract-Slice. |
| `backend/app/services/prepare_service.py` | 1088 | spaeter | Provider-Aufloesung, Quoten und FSM teilen Semantik; Phasen nur einzeln mit Regressionstests extrahieren. |
| `frontend/src/components/shell/Dossier.vue` | 1078 | bewusste UI-Ausnahme fuer diesen PR | erheblicher Template-/Style-Anteil; zuerst fachliche Panel-Grenzen statt CSS-Dateiverschiebung. |
| `backend/scripts/_sim_common.py` | 1022 | spaeter | breit geteilter Runtime-Helfer; Import-/Script-Kompatibilitaet zuerst sichern. |
| `backend/app/services/sim/process_manager.py` | 1014 | spaeter | Prozess-, Cleanup- und Cancel-Lifecycle; eigener Prozess-Slice. |
| `backend/app/services/report_agent/evidence.py` | 984 | bewusste Stop-Bedingung | Evidence-Provenance/Degradation geschuetzt; keine semantische Aenderung in einem LOC-PR. |
| `frontend/src/components/v4/dashboard/HeroNewRun.vue` | 959 | spaeter | UI-State/Flows; Component-/A11y-Schnitt separat. |
| `backend/app/services/graph_tools.py` | 924 | spaeter | Retrieval und Interviews sind Report-/Evidence-nah; getrennte Tool-Familien erst mit Regressionen. |
| `frontend/src/components/v4/steps/Step4Report.vue` | 924 | spaeter | Report-UI und Confirm-/Budget-Flows; fachliche Child-Komponenten als eigener Frontend-Slice. |
| `frontend/src/components/shell/Shelf.vue` | 892 | spaeter | Shell-SFC; erst Script/Template/Style-Verantwortungen separat bewerten. |
| `frontend/src/components/compare/BranchComparePanel.vue` | 882 | spaeter | Compare-Contract/UI gekoppelt; eigener komponentenbezogener Refactor. |

### In diesem PR umgesetzt; Abschlussverifikation ausstehend

1. **Ausstehend:** `backend/app/api/runs.py`: Read-only Summary-Enrichment nach `services/run_read_model.py` extrahiert; die zuvor verschobene CC=27-Funktion wurde real zerlegt statt neu allowzulisten. Der Slice gilt erst nach gruener Protected-Gate-Verifikation als abgeschlossen.
2. **Ausstehend:** `backend/app/services/sim/monitor.py`: reine Timeline-/Agent-Statistik nach `sim/run_metrics.py` extrahiert; bestehender `_get_actions`-Monkeypatch-Hook bleibt ueber duenne Wrapper kompatibel. Dadurch faellt `monitor.py` von **893 auf 798 LOC** und damit von P0 auf P1. Der Slice gilt erst nach gruener Protected-Gate-Verifikation als abgeschlossen.
3. Exaktes Repo-Inventar fuer alle geforderten Quelltypen inklusive separater Testliste erzeugt.
4. Veralteten Radon-Allowlist-Eintrag fuer `_build_run_summary` entfernt und Frontend-SSoT-Kommentar auf das neue Modul aktualisiert.

Es wird bewusst noch kein erfolgreicher Job-/Commit-Nachweis fuer den Abschluss dokumentiert; dieser folgt erst, wenn die erforderlichen Protected Gates fuer den aktuellen PR-Head erfolgreich ausgefuehrt wurden.

### Nicht als Erfolg verkauft

`runs.py` bleibt mit **1316 LOC** P0. Der erste Slice reduziert Verantwortungsmischung, loest den God-Controller aber nicht vollstaendig. Die verbleibenden Resume-/Restart-Pfade sind fachlich deutlich riskanter und werden deshalb nicht nur fuer eine schoenere LOC-Zahl verschoben.
