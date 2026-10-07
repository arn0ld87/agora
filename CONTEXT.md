# CONTEXT.md — Was Agora kann und wie es arbeitet

Orientierung für Agenten und Maintainer, die mit Agora-Code, Laufartefakten oder Reports arbeiten.

> **Stand:** 02.10.2026. **Abgeglichen gegen:** `main@4cbf0eb8`, Produktversion `0.9.6`.
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

Ein benannter Satz synthetischer Personas in der Bibliothek. Ein Lauf bekommt eine Kopie (Schnappschuss); nach dem ersten Lauf aus diesem Satz ist der Satz gesperrt, der Ausweg ist Duplizieren. Jeder Eintrag trägt seine Herkunft: `graph`, `manual`, `ai_draft` oder `fallback`.

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
- Regelbasierte Alias-Auflösung, semantische Entitätsklassen und NER-Chunk-Kontext vor dem Persona-Cap sind umgesetzt (#1470 geschlossen). Mehrdeutige Identitäten bleiben getrennt; LLM-Koreferenz liegt außerhalb des Scopes.

### Phase 2 — Prepare und Personas

Aus Graph-Entitäten werden Persona-Kandidaten gebildet. Der aktuelle Pfad kombiniert unter anderem:

1. Typ-/Kopfnomenfilter für offensichtlich nicht-personenfähige Entitäten,
2. normalisierte Deduplication,
3. typbewusste Auswahl/Caps,
4. LLM-Eignungsprüfung,
5. Unterscheidung zwischen Individual- und Kollektiv-Personas,
6. Identitäts-/Namensangleichung,
7. Reserve-/Backfill-Logik,
8. Person-Organisation-Zusammenlegung: vertritt eine Person laut belegter Graph-Relation (`REPRESENTS`; `WORKS_FOR`/`AFFILIATED_WITH` gelten bewusst nicht als Vertretung) eine Organisation, bleibt sie der einzige Agent und trägt die Organisation als `affiliation`; vertreten mehrere Personen dieselbe Organisation oder keine, bleibt die Organisation ein eigener Agent (#1713/#1470).

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

Mit dem Werkzeug `search_simulation_actions` sucht der Report-Agent seit #1778 gezielt in den Simulationsbeiträgen (Stichwort, Agentenname, Rundenbereich); jeder Treffer wird ein Beleg vom Typ `agent_action`. Die Suche läuft außerdem zu Beginn jedes Abschnitts durch das System (höchstens zweimal) und zählt gegen das Limit von fünf Werkzeugaufrufen; ihre Treffer sind in allen Abschnitten Kandidat für das Evidence-Binding. Beim Binding wird ein Beitrag über seinen reinen Wortlaut gesucht und bekommt bis zu zwei eigene Plätze neben den fünf besten Kandidaten. Das ändert nur, welche Beiträge geprüft werden: ob ein Beitrag einen Claim stützt, entscheidet unverändert die Entailment-Stufe.

Drei Nummern meinen denselben Agenten: `agent_configs[].agent_id` in der Simulationskonfiguration, `user_id` im Profil und die Nummer in OASIS. OASIS vergibt seine Nummer nach der Position des Profils in der Profildatei. Fehlt ein Profil, weichen die Nummern ab; Runner und Bericht lesen die Konfiguration deshalb über `align_config_to_profiles` (`services/simulation_agent_identity.py`). `agent_id` im Aktionsprotokoll und `voice_key` am Beleg sind immer die OASIS-Nummer. In `twitter_profiles.csv` ist `user_id` die Zeilenposition; die Nummer aus der Konfiguration steht dort in `source_user_id`.

Ein Fallback-Outline oder ein Cancel mit fehlenden Sections wird nicht mehr still als vollständig abgeschlossen behandelt. Ein Resume bewahrt relevante Degradationsmarker und kann einen temporären Fallback-Outline neu planen (#1479).

---

## 4. Evidence-Modell

### Claim, Hypothese und Data Gap

- **Claim:** eine berichtete Aussage mit Evidence-Bezug und Vertragsmetadaten.
- **Hypothese:** plausible Aussage, für die die verfügbare Evidence nicht ausreicht.
- **Data Gap:** benötigte Information, die in den verfügbaren Quellen nicht vorhanden ist.

Ein fehlgeschlagenes Binding ist nicht automatisch ein Data Gap. Wenn die Information vorhanden ist, aber das Matching scheitert, muss das als Binding-/Gate-Problem sichtbar bleiben.

### Beleg, Stimme und Quellenart

- **Beleg:** ein einzelner Evidence-Eintrag, etwa ein Simulationspost, eine Interviewantwort oder eine Seed-Stelle.
- **Stimme:** eine Persona, unabhängig davon, über wie viele Belege und Kanäle sie auftritt. Ein Post und eine Interviewantwort derselben Persona sind zwei Belege, aber eine Stimme.
- **Quellenart:** die Herkunftsklasse eines Belegs. Die Quellenarten stehen im nächsten Abschnitt.

Zwei Belege gelten als voneinander unabhängig, wenn sie von verschiedenen Stimmen oder aus verschiedenen Quellenarten stammen. Mehrere Belege derselben Stimme sind nicht unabhängig. Übereinstimmung mehrerer Stimmen bleibt Simulationskonsens: Alle Personas sind synthetisch.

### Streitfrage

Eine Aussage, die man bejahen oder verneinen kann, abgeleitet aus der Fragestellung des Laufs. Ein Lauf hat höchstens eine Streitfrage. Sie wird vor der Simulation festgelegt und ist prüf- und änderbar.

Enthält die Fragestellung keine entscheidbare Aussage, hat der Lauf keine Streitfrage. Haltung, Positionswechsel, Koalition und Positionierungsquote sind dann nicht anwendbar; das ist keine Degradation.

### Haltung, Positionswechsel und Haltungsabweichung

- **Haltung:** die Position einer Stimme zur Streitfrage, in einer von drei Klassen: dafür, dagegen, unentschieden. Was eine Stimme sonst vertritt, ist Inhalt ihrer Beiträge, nicht ihre Haltung.
- **Positionswechsel:** Eine Stimme hat am Ende des Laufs eine andere Haltungsklasse als zu Beginn, und mindestens ein Simulationsbeitrag dieser Stimme belegt die neue Haltung. Der Übergang von unentschieden zu dafür oder dagegen zählt.
- **Haltungsabweichung:** Anfangs- und Endhaltung einer Stimme unterscheiden sich, ohne dass ein Simulationsbeitrag die neue Haltung belegt. Eine Haltungsabweichung ist eine Auffälligkeit, kein Positionswechsel.

„Kein Positionswechsel beobachtet" ist ein gültiges Ergebnis.

### Lager und Koalition

- **Lager:** alle Stimmen mit derselben Haltungsklasse, unabhängig davon, ob sie in der Simulation aufeinander reagiert haben.
- **Koalition:** mindestens zwei Stimmen aus verschiedenen Rollenfamilien mit derselben Haltungsklasse, die in der Simulation zustimmend aufeinander Bezug genommen haben.

- **Aktivitätsmodell:** Regel, nach der Agenten in einer Runde aktiv werden. Seit #1779 eine Tagesrate für Textbeiträge je **Akteursklasse** (Einzelperson, Politiker, Behörde, Organisation, Medium) mit Stundenprofil, in den Modi `realistic` und `active`; je Aktivierung höchstens ein Textbeitrag und zwei Reaktionen. Die Werte begrenzen, wie viel simulierte Akteure schreiben; sie sagen nicht vorher, wie sich ein realer Akteur verhält.
- **Belegdichte:** Zahl der stützenden Belege je Claim eines Berichts, festgehalten in `evidence_density.json`. Ein Beleg zählt nur mit `supports_claim: true`; mehrere Belege derselben Stimme sind keine unabhängigen Quellen. Die Datei misst, sie bewertet nicht.
- **Positionierungsquote:** Anteil der Stimmen, die in mindestens einem Simulationsbeitrag eine Haltung dafür oder dagegen zeigen. Interviews zählen dafür nicht. Eine niedrige Positionierungsquote ist eine Degradation.
- **Lagerverteilung:** wie sich die positionierten Stimmen auf die Lager verteilen. Eine einseitige Lagerverteilung ist ein Befund, keine Degradation.

Stimmen derselben Rollenfamilie bilden keine Koalition. Häufige Interaktion bei gegensätzlicher Haltung ist eine Konfliktlinie, keine Koalition.

### Quellenarten

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

Seit #1478 werden auch Interview-Providercalls dem Report-Budget zugeordnet und Budgetabbrüche strukturiert zurückpropagiert. Der separate `ParallelIPCHandler` des Default-Parallelrunners wurde durch #1527 ebenfalls in die Budgetattribution einbezogen.

### Evidence-API

`GET /api/report/<id>/evidence` besitzt einen Pydantic-/JSON-Schema-/Zod-Vertrag. Bei vertragswidrigem Altbestand kann der Endpoint einen `evidence_omitted`-Zustand liefern, statt ungültige Evidence als geprüft auszugeben (#1477/#1482).

### Bekannte Trust-Grenzen

- Quantor-gestützte Evidence-Prüfung ist umgesetzt (#1345 geschlossen); sie ersetzt keine empirische Kalibrierung.
- Evaluation-Seeds können erwartete Antworten enthalten und dadurch einen vermeintlichen Erkenntnisgewinn vortäuschen (#1240).
- Role Leakage wird lesend markiert; markierte Aktionen fallen aus der Report-Stichprobe (#1323 geschlossen). `actions.jsonl` bleibt unverändert, ein Repair-/Verwerf-Gate im Subprozess ist bewusst nicht vorgesehen.
- Confidence-/Claim-Typen sind konsolidiert (#1301/#1400 geschlossen); eine externe Kalibrierungszusage ergibt sich daraus nicht.

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

Embedding-Konfiguration ist bewusst vom Chat-Routing getrennt. Lese- und Schreibpfad lösen Index- und Property-Namen kanonisch über den Store auf; der Cutover aktiviert eine neue Index-Version erst nach geprüftem Re-Embedding und Index-Check. [#1417](https://github.com/arn0ld87/agora/issues/1417) ist geschlossen: Betriebsdimensionen, Legacy-Bootstrap-Sicht, Frontend-`building`-Spiegel, Env-/Store-Divergenzwarnung und Dimensionsprüfung vor dem Schreiben sind umgesetzt. Ein echter Modellwechsel gegen das produktive Neo4j-/Embedding-Backend bleibt ein operativer Nachweis in [#1592](https://github.com/arn0ld87/agora/issues/1592).

---

## 7. Run-Budgets

Run-Budgets können Zeit, Tokens, Kosten und LLM-Aufrufe begrenzen. Die Durchsetzung arbeitet mit Reservierungen, damit parallele Calls dasselbe Restbudget nicht mehrfach verbrauchen.

Seit #1478 werden Text-, Tool-, Vision- und Interview-Pfade pro physischem Provider-Versuch geprüft und im Ledger erfasst. `BudgetExceededError` ist ein harter Laufzustand und darf nicht zu einer freundlichen Fallback-Antwort weichgespült werden.

Seit #1772 gilt für eine Simulation ohne Nutzerbudget ein harter Standard-Tokendeckel (`AGORA_SIM_DEFAULT_MAX_TOKENS`, Standard 20 Mio., `0` = aus). Die Schätzung vor dem Start rechnet für die Simulation mit wachsendem Kontext je Runde und nennt als Annahme, dass der Budget-Zähler nur erfolgreiche Aufrufe zählt.

---

## 8. Reproduzierbarkeit

[#1274](https://github.com/arn0ld87/agora/issues/1274) ist geschlossen. Manifeste erfassen Prompt-Templates, verfügbare Input-Hashes und strikte Route-Snapshots; Replay übernimmt die ursprünglichen Simulationsparameter, erlaubt ein Modellrouten-Override und dokumentiert Abweichungen. Nicht rekonstruierbare Altwerte bleiben `null`; unvollständige Alt-Manifeste können abgewiesen werden. Nach der Maintainer-Entscheidung vom 26.09.2026 bleibt `random_seed` bewusst `null`; durchgängiges RNG-Wiring wurde verworfen und ist keine unerledigte Release-Zusage. **Replay garantiert weder identische Modellantworten noch dasselbe Experimentergebnis.** Nachvollziehbar sind Eingaben und Konfiguration, keine deterministische Simulation.

Manifest-/Replay-Verträge und die detaillierten Capture-/Legacy-Grenzen stehen in [STATUS](docs/STATUS.md). Feature Flags, externe Modellversionen und Graphzustand sind bei Referenzläufen weiterhin zu dokumentieren.

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
| Out-of-Process-Worker / Report-Parallelität | #1551 (Recovery #1472 geschlossen) |
| Echter Embedding-Modellwechsel und Cutover-Nachweise | #1592 (Embedding-Code #1417 geschlossen) |
| LLM-Koreferenz außerhalb des abgenommenen Alias-Scopes | #1470 geschlossen |
| Role Leakage: Markierung statt Verwerfen, keine vollständige Erkennung zugesagt | #1323 geschlossen |
| Evaluation-Leakage/Gegenlauf | #1240 |
| Replay ohne Determinismusgarantie, `random_seed=null` | #763 / #1274 geschlossen |
| Kompatibilität ab 1.0: Die Policy steht in ADR-0021 und gilt erst ab `v1.0.0`. Offene Einzelfälle sind bis `1.0.0-rc.1` zu entscheiden, ein automatischer Breaking-Change-Check fehlt | ADR-0021 (#1664) |
| Test-Isolation vom echten Datenbestand: Schreibsperre gilt nur im Testprozess, nicht für Kindprozesse | #1632 geschlossen |
| Fresh-Host-Install/Restore/Upgrade-Nachweis | #766 |
| AURORA-Produktvergleich / volle Kalibrierung nach 1.0 | #1662 / #765 |
| Prompt Injection: Single-Platform-Tool-Loop gekapselt, native CAMEL-Pfade und Fallback-Runden nicht pauschal abgedeckt | #1224 geschlossen |

Historische Referenzläufe und Audits sind Belege ihres damaligen Zustands. Sie dürfen nicht als automatische Aussage über den aktuellen `main` gelesen werden.
