# CONTEXT.md — Was Agora kann und wie es arbeitet

Orientierung für Agenten und Maintainer, die mit Agora-Code, Laufartefakten oder Reports arbeiten.

> **Stand:** 20.09.2026. **Verifiziert gegen:** `main@b62aea62`, Produktversion `0.9.6`.  
> Für den verifizierten Projekt-Iststand ist [`docs/STATUS.md`](docs/STATUS.md) führend. Diese Datei erklärt Begriffe, Datenflüsse und die wichtigsten Invarianten.

---

## 1. Was Agora tut

Agora verarbeitet Dokumente, Webseiten und Fragestellungen zu einem Wissensgraphen, leitet daraus synthetische Stakeholder-Personas ab, lässt sie in einer kontrollierten Multi-Agenten-Simulation interagieren und erzeugt anschließend einen evidenzorientierten Bericht.

Typische Fragestellung: *Welche Konfliktlinien, Einwände, Risiken und ungeklärten Annahmen könnten bei einer geplanten Entscheidung oder einem Rollout relevant werden?*

Agora ist dabei **kein Vorhersagesystem für menschliches Verhalten**:

- Personas sind synthetische Modellkonstrukte.
- Simulationen sind Szenarien, keine Stichprobe realer Menschen.
- Confidence bewertet die systeminterne Evidenzbindung, nicht „Wahrheit“.
- Reale Interviews, Fachreviews, Nutzertests und empirische Daten bleiben die externe Referenz.

---

## 2. Verbindliches Vokabular

### Lauf

Ein vollständiges Vorhaben von der Quelle bis zum Bericht. Ein Lauf umfasst je nach Konfiguration Graph, Personas, Simulation, Bericht, Exporte und Interviews.

### Job

Ein einzelner ausführbarer Schritt innerhalb eines Laufs, verwaltet über die `RunRegistry`, z. B. Graph-Build, Ontologie, Prepare, Simulation oder Report. Im Code heißen die technischen IDs weiterhin `run_id`/`run_type`.

### Bericht

Das lesbare Ergebnis eines Laufs. Ein Bericht besitzt einen eigenen Status und kann auch **auslieferbar, aber `INCOMPLETE`** sein. `INCOMPLETE` ist eine fachlich sichtbare Degradation und kein kosmetischer Alias für `COMPLETED`.

### Personasatz

Eine Sammlung synthetischer Personas. Personas können vor einer Simulation geprüft, verändert oder verworfen werden.

### Graph

Das aus Quellen extrahierte Wissensumfeld: Entitäten, Relationen, Quellenfragmente und Vektoren in Neo4j.

### Projekt

Vor allem Implementierungsbegriff. `project_id` ist eine technische Persistenz-/Graph-ID und nicht automatisch das Produktwort für einen gesamten Lauf.

### Stop / Abbruch

Mehrere Zustandsmodelle existieren nebeneinander:

- Ein expliziter Nutzer-Stop eines Simulationsjobs wird als `status="stopped"` mit `termination_reason="user_stop"` geführt (#1474).
- Budgetabbrüche besitzen eigene strukturierte Termination-Reasons.
- Ein Report, bei dem Sections fehlen oder dessen Planung degradiert ist, endet als `INCOMPLETE` (#1479).
- Ein verwaister Simulationsprozess nach Restart wird durch Startup-Reconciliation als `failed/process_restart` klassifiziert, wenn der Zustand eindeutig ist (#1476).

Nicht aus einem einzelnen Statusfeld auf die gesamte Pipeline schließen. Run-, Simulation- und Reportstatus beschreiben unterschiedliche Ebenen.

---

## 3. Pipeline

```text
Quelle
  ↓
[Graph / Ontologie]
  ↓
[Prepare / Personas / Simulationskonfiguration]
  ↓
[OASIS/CAMEL-Simulation]
  ↓
[Reportplanung / Tools / Interviews]
  ↓
[Claims / Evidence / Gates / Export]
```

### Phase 1 — Graph und Ingestion

Quellen werden extrahiert und gechunkt. NER/Relationsextraktion und Embeddings erzeugen einen Neo4j-Graphen.

Wichtige Invarianten:

- Upload-Provenance wird über Dokument- und Chunk-IDs weitergetragen (ADR-0013).
- Episode- und Relation-Writes sind gegen Retry-after-commit idempotent (#1460).
- `entity_type` ist kein garantiert stabiles Label zwischen unterschiedlichen Modellläufen.
- Alias-/Koreferenzauflösung und semantische Entitätsklassen vor dem Persona-Cap sind noch nicht vollständig gelöst (#1470).

### Phase 2 — Prepare und Personas

Aus Graph-Entitäten werden Persona-Kandidaten gebildet. Der aktuelle Pfad kombiniert unter anderem:

1. Typ-/Kopfnomenfilter für offensichtlich nicht-personenfähige Entitäten,
2. normalisierte Deduplication,
3. typbewusste Auswahl/Caps,
4. LLM-Eignungsprüfung,
5. Unterscheidung zwischen Individual- und Kollektiv-Personas,
6. Identitäts-/Namensangleichung,
7. Reserve-/Backfill-Logik.

Der geroutete Provider ist für die Persona-Generierung kanonisch. Eine aufgelöste `cli`-Route darf nicht mit `.env`-HTTP-Endpoint oder fremdem API-Key vermischt werden (#1418/#1422).

Vollständige regelbasierte Fallback-Personas gelten als Degradation und dürfen nicht als normaler Erfolg verschleiert werden.

Die Branchenquote lenkt nur bewusst synthetische Personas; trägt die Quelle einer Entität bereits erkennbares Fachvokabular, bleibt ihr Fach erhalten. Erkannte Domänendrift wird über den regulären LLM-Pfad korrigiert (Beruf, Bio, Freitext); eine fehlgeschlagene Korrektur ist als `generation_error` sichtbar (#1471).

### Phase 3 — Simulation

OASIS/CAMEL läuft in einem **separaten Subprozess**. Twitter- und Reddit-Simulationen besitzen unterschiedliche Aktionsräume. Redis und dateibasierte Artefakte verbinden Laufzeit, Webprozess und UI.

Produktions-Gunicorn verwendet bewusst **einen Web-Worker**. Der OASIS-Prozess ist davon getrennt.

Aktuelle Lifecycle-Härtungen:

- Nutzer-Stop → `stopped/user_stop` (#1474).
- Generation-Tokens verhindern, dass ein alter Monitor einen neu gestarteten Prozess überschreibt (#1474).
- Startup-Reconciliation prüft stale `pending`/`processing`/`paused` Runs gegen den persistierten Prozesszustand (#1476).
- `post_fork` führt die Reconciliation auch nach einem Gunicorn-Worker-Replacement aus (#1476).

Bekannte Grenze: Prepare-, Report- und Graph-Build-Jobs laufen noch in daemonisierten Threads des Webprozesses. Bei einem regulären Shutdown (SIGTERM, nicht SIGKILL) markiert ein `atexit`-Hook (`app/services/sim/process_shutdown.py`, registriert in `post_worker_init`) die zu diesem Worker-Prozess gehörenden In-Process-Jobs (`simulation_prepare`, `report_generate`, `graph_build`, `ontology_generate`) noch im selben Lauf ehrlich als `failed/process_restart` — anhand von Worker-Token und PID, damit nur eigene Jobs markiert werden, nicht die anderer Worker. Das läuft bewusst außerhalb des Signalkontexts (der SIGTERM-Handler setzt nur ein Flag), weil `gevent.signal.signal()` den echten CPython-Signalkontext liefert, in dem ein `threading.Lock` nach `patch_all()` als kooperatives Semaphore blockieren könnte. Ein `SIGKILL` nach Ablauf des `graceful_timeout` überspringt den Hook; dafür bleibt die Startup-Reconciliation (#1476) der Mechanismus. Ein persistierter, automatisch fortsetzbarer Zwischenstand entsteht in keinem der beiden Pfade — vollständige Crash-/Restart-Recovery bleibt an einer Job-Queue mit eigenen Workern (#1472).

### Phase 4 — Report

Der Report besteht grob aus:

1. **Outline/Planning**
2. **Section-ReAct** mit Graph-/Evidence-Tools und optionalen Persona-Interviews
3. **Claim-Extraktion und Evidence-Binding**
4. **Prose-/Attribution-/Requirement-Gates**
5. **Persistenz, Export und Degradationsmodell**

Ein Fallback-Outline oder ein Cancel mit fehlenden Sections wird nicht mehr still als vollständig abgeschlossen behandelt. Ein Resume bewahrt relevante Degradationsmarker und kann einen temporären Fallback-Outline neu planen (#1479).

---

## 4. Evidence-Modell

### Claim, Hypothese und Data Gap

- **Claim:** eine berichtete Aussage mit Evidence-Bezug und Vertragsmetadaten.
- **Hypothese:** plausible Aussage, für die die verfügbare Evidence nicht ausreicht.
- **Data Gap:** benötigte Information, die in den verfügbaren Quellen nicht vorhanden ist.

Ein fehlgeschlagenes Binding ist nicht automatisch ein Data Gap. Wenn die Information vorhanden ist, aber das Matching scheitert, muss das als Binding-/Gate-Problem sichtbar bleiben.

### Evidence-Arten

Je nach Pfad unter anderem:

- Seed-/Dokumentevidence,
- Graphrelationen,
- Simulationsaktionen,
- Persona-/Agenteninterviews,
- Web-/Rechercheergebnisse.

### Interview-Evidence

`interview_agents` ist eine **zusätzliche Befragung** anhand der Persona-Profile. Es ist keine bloße Zusammenfassung des Social-Feeds. Ein Report-Zitat kann deshalb aus einem Phase-4-Interview stammen, obwohl dieselbe Formulierung nie als Simulationspost existierte.

Transportpfade:

- lebender Worker: IPC zum OASIS-Prozess,
- terminaler Lauf: Direct-Client im Backend.

Seit #1478 werden auch Interview-Providercalls dem Report-Budget zugeordnet und Budgetabbrüche strukturiert zurückpropagiert. Der separate `ParallelIPCHandler` des Default-Parallelrunners besitzt noch eine bekannte Attribution-Lücke.

### Evidence-API

`GET /api/report/<id>/evidence` besitzt einen Pydantic-/JSON-Schema-/Zod-Vertrag. Bei vertragswidrigem Altbestand kann der Endpoint einen `evidence_omitted`-Zustand liefern, statt ungültige Evidence als geprüft auszugeben (#1477/#1482).

### Bekannte Trust-Grenzen

- Quantifizierte Aussagen können noch stärker formuliert sein als die aggregierte Evidence trägt (#1345).
- Evaluation-Seeds können erwartete Antworten enthalten und dadurch einen vermeintlichen Erkenntnisgewinn vortäuschen (#1240).
- Rollenwechsel/Role Leakage in Simulationsaktionen wird noch nicht hart gegatet (#1323).
- Confidence-/Claim-Typisierung ist noch nicht vollständig kalibriert (#1301/#1400).

---

## 5. Persistenz und Artefakte

Die konkreten Dateinamen können sich über Versionen ändern; die führenden Services/Contracts sind immer der Code. Die wichtigsten Roots sind aktuell:

```text
backend/uploads/
  simulations/<sim_id>/     Simulationskonfiguration, State, Plattform-DBs, Logs
  reports/<report_id>/      Report-Metadaten, Outline, Sections, Evidence, Logs

backend/data/
  llm_provider_secrets.json verschlüsselte Provider-Credentials
  api_keys.json             verschlüsselter Workspace-API-Key-Store
  ...                       Routing-/Konfigurationsdaten
```

Report-Persistenz folgt seit #1475 einer Commit-Marker-Invariante:

1. Sektions-Evidence wird zuerst persistiert.
2. Markdown wird atomar geschrieben und markiert die fertige Sektion.
3. Ein Markdown-Orphan ohne passende Evidence wird beim Resume nicht als fertig restauriert.

Wo möglich werden Datei-/Verzeichnis-Writes atomar und mit `fsync` behandelt; echte Storage-/Permissionfehler dürfen nicht still als „nicht unterstützt“ geschluckt werden.

### PostgreSQL-Schicht (parallel, nicht Default)

Neben den Datei-/JSON-/SQLite-Stores existiert eine SQLAlchemy-/Alembic-gestützte PostgreSQL-Schicht: ein self-hosted Supabase-Compose-Overlay (#1504), die SQLAlchemy-/Alembic-Grundlage (#1505), sowie je ein Repository-Port mit Datei-/SQLite- **und** PostgreSQL-Adapter für LLM-Profile (`LlmProfileRepository` #1515, `LlmProfileSecretsStore` #1516, `PostgresLlmProfileRepository` auf `agora.llm_profiles` #1507/#1517) und Projektmetadaten (`ProjectRepository`/`FileProjectRepository`, `PostgresProjectRepository`; changelog.d/projekt-vertrag-und-repository-port.md, changelog.d/projekt-postgres-adapter.md — ohne Issue-Nummer).

Drei unabhängige Umschalter steuern das, jeder mit dem bisherigen Pfad als Default: `AGORA_METADATA_BACKEND` (`legacy`), `AGORA_PROJECT_BACKEND` (`file`), `AGORA_LLM_PROFILE_BACKEND` (`sqlite`). Ohne explizites Umschalten bleibt Agora vollständig auf Datei-/SQLite-Stores; **„Agora läuft auf PostgreSQL“ ist keine zutreffende Aussage über den Default**.

---

## 6. Provider, Routing und Secrets

Ein Lauf kann verschiedene Modelle pro Pipeline-Stage verwenden.

Kanonische Bausteine:

- Provider-Matrix: `backend/app/services/llm_provider_registry.py`
- Detection/Adapter: `backend/app/llm/providers/registry.py`
- Connection: `ProviderConnection`
- Modell/Route: `AiModelRef`, `AiRoute`, `LlmRoute`
- strukturierte Calls: `LLMClient.chat_json`
- Secrets: Provider-Secret-Store

Transportarten:

- `http` (u. a. OpenAI, Gemini, MiniMax, Amazon Bedrock über den OpenAI-kompatiblen Mantle-Pfad, Default-Region `eu-central-1`, #1282); Anthropic nur für Modell-Discovery, nativer Anthropic-Chat wird laut abgelehnt — Claude läuft über Bedrock (#1284)
- `local` (lokaler HTTP-Dienst, z. B. Ollama)
- `cli`: zwei Provider sprechen eine lokale CLI per Subprozess statt Pay-per-Token-API an — `codex_cli` (ChatGPT-Abo, `auth_mode="session"`, lokale CLI-Login-Session) und `claude_cli` (Claude-Abo, #1531, Langzeit-Token `CLAUDE_CODE_OAUTH_TOKEN` im Fernet-Secret-Store, isoliertes `HOME` pro Aufruf). Eine aufgelöste `cli`-Route darf nicht mit `.env`-HTTP-Endpunkt oder fremdem API-Key vermischt werden (#1418/#1422).

`codex_cli` fragt seinen Modellkatalog seit #1416 laufzeitseitig über `codex debug models` ab (`discover_codex_cli_models()`) statt einen einzelnen Platzhalter (`codex-cli-default`) zu zeigen; der Katalog ist account-/planabhängig, der Sentinel bleibt als Fallback bei jedem Discovery-Fehlschlag erhalten.

Embedding-Konfiguration ist davon getrennt. Lese- und Schreibpfad lösen Index- und Property-Namen inzwischen kanonisch über den Store auf (`resolve_active_entity_index()`/`resolve_active_fact_index()`, Slice 2.1), und `EmbeddingMigrationService` schaltet eine neue Index-Version erst nach geprüftem Re-Embedding und Index-Check gegen Neo4j atomar frei (Slice 2.2). **#1417 ist damit noch nicht vollständig geschlossen:** offen bleiben eine `VECTOR_DIM`-SSoT (Slice 2.3), eine Legacy-View für Bestandsgraphen (Slice 2.4) und der Frontend-Zod-Spiegel für den neuen `building`-Status.

---

## 7. Run-Budgets

Run-Budgets können Zeit, Tokens, Kosten und LLM-Aufrufe begrenzen. Die Durchsetzung arbeitet mit Reservierungen, damit parallele Calls dasselbe Restbudget nicht mehrfach verbrauchen.

Seit #1478 werden Text-, Tool-, Vision- und Interview-Pfade pro physischem Provider-Versuch geprüft und im Ledger erfasst. `BudgetExceededError` ist ein harter Laufzustand und darf nicht zu einer freundlichen Fallback-Antwort weichgespült werden.

---

## 8. Reproduzierbarkeit

Ein gespeichertes `random_seed`-Feld bedeutet **nicht**, dass ein Agora-Lauf bereits reproduzierbar ist. Ein strukturelles `RunManifest` und ein Replay-Dialog existieren (#763/#1273); das Manifest wird atomar geschrieben, referenziert den kanonischen `AiModelRef` bei Modell-Overrides und übernimmt `runtime.usage_summary` beim Finalisieren. Es ist damit noch kein vollständiger Reproduktionsanker.

Für einen belastbaren Replay müssen mindestens kontrolliert oder aufgezeichnet werden:

- rohe Inputs inklusive Hash/Dateiname,
- Prompt-Snapshots,
- tatsächlich verwendete RNG-Seeds und deren Wiring,
- Provider-/Connection-/Modell-/Routing-Snapshots,
- relevante Feature Flags und Limits,
- Graph-/Embedding-Versionen,
- gegebenenfalls Modellantworten für einen deterministischen Replay.

Diese Arbeit ist in #763/#1274 offen. Deshalb nicht dokumentieren oder kommunizieren: „same seed = same run“.

---

## 9. Auth und Secret-Grenzen

- `AGORA_AUTH_TOKEN`: Master-Token mit administrativer Wirkung.
- Workspace-API-Keys (`ago_...`): persistiert und scope-basiert.
- `AGORA_SECRET_KEY`: Fernet-Master für Provider-Secrets.
- `AGORA_FERNET_KEY`: Fernet-Master für `backend/data/api_keys.json`.
- `SECRET_KEY`: Flask-/Ticket-Signing.

Details: [`docs/auth.md`](docs/auth.md) und [`docs/secret-key-lifecycle.md`](docs/secret-key-lifecycle.md).

---

## 10. Aktuelle bekannte Grenzen

Die verbindliche Priorisierung steht in [`docs/STATUS.md`](docs/STATUS.md) und [`ROADMAP.md`](ROADMAP.md). Besonders relevant:

| Thema | Referenz |
|---|---|
| Webprozess-Jobs nach Restart | #1472 |
| Embedding Runtime SSoT | #1417 |
| Entitätsauflösung | #1470 |
| Role Leakage | #1323 |
| Twitter-Recommender / Reproduzierbarkeit | #1236 |
| Quantoren vs. Evidence | #1345 |
| Evaluation-Leakage | #1240 |
| vollständiges Manifest / Replay | #763 / #1274 |
| Backup/Restore/Upgrade-Nachweis | #766 |
| Baseline-/Produktvalidierung | #765 |
| Prompt Injection aus untrusted Observation — teilweise adressiert: Single-Platform-Tool-Loop kapselt und neutralisiert seit #1224, paralleler Simulationspfad und Fallback-Runden (natives CAMEL-`LLMAction()`) nicht | #1224 |

Historische Referenzläufe und Audits sind Belege ihres damaligen Zustands. Sie dürfen nicht als automatische Aussage über den aktuellen `main` gelesen werden.
