# AGORA Technical Audit

> **Historischer Stand, keine Steuerungsquelle.** Snapshot gegen `main` vom 25.09.2026 (`98ebd1ce`). Einzelne Befunde sind inzwischen behoben (z. B. Manifest/Replay in #1686). Maßgeblich sind `docs/STATUS.md`, `ROADMAP.md` und die offenen GitHub-Issues.

**Prüfstand:** `main` bei `98ebd1ceed239d2e01fe71e7042973d13d921928`, 25.09.2026. Codebelege sind `Pfad:Zeile` in genau diesem Commit. GitHub meldete zu diesem Zeitpunkt 30 offene Issues. Das Audit ist lesend: Quellcode, Verträge, Tests, Workflows, Dokumentation und Issue-Texte wurden geprüft; weder Produktcode noch Issues wurden geändert. Tests wurden nicht lokal ausgeführt, da der Arbeitsbaum auf `feat/f006-sim-fidelity` steht. Die [CI des Prüfcommits](https://github.com/arn0ld87/agora/actions/runs/36072201453) ist **rot**: 6 PostgreSQL-Backup-Integrationstests scheitern an `pg_dump` 16.15 gegen Server 17.11; 74 Integrationstests bestanden. Backend, Frontend, Security, Contract-Gates, E2E, Docker-Image, CodeQL, Scorecard und Version-Drift waren erfolgreich. Laufzeitmessungen, ein frischer Host, echte Modellantworten und ein Restore-Drill sind **NICHT VERIFIZIERT**.

## 1. Executive Assessment

- Agora hat belastbare Pydantic-Verträge für zentrale Domänen, Zod-Spiegel, echte Redis/Neo4j/PostgreSQL-Integrationstests, Auth-Guards, SSRF-Schutz und atomare Einzeldatei-Schreibvorgänge.
- Die fünf Evidence-Gating-Hartanker aus ADR-0002 sind im geprüften Code vorhanden (`backend/app/contracts/report_contract.py:66,510,549`; `backend/app/services/report_prompts/sections.py:31`).
- Eine vollständige Replay-Zusage trägt der Code nicht: Das Manifest enthält Platzhalter und leere Prompt-Snapshots; Replay übernimmt nicht die eingefrorenen Originalparameter.
- Prozessabbruch wird für Jobs erkennbar, doch Report hat keinen belastbaren Abschnitts-Checkpoint; ein Report ist weiterhin Arbeit im Webprozess.
- Entity-Aliase werden vor dem Persona-Cap nicht kanonisiert. Role Leakage und quantifizierte Claims bleiben offene Trust-Grenzen.
- Budget-Hard-Limits können bei Ledger-/Enforcer-Fehlern fail-open weiterlaufen.
- Backup-Werkzeug einschließlich PostgreSQL ist vorhanden; der in der Roadmap verlangte reale Fresh-Host-/Rollback-Nachweis fehlt.
- Der Produktmehrwert gegenüber einfacheren LLM-Baselines ist nicht durch die verlangte Referenzfall-Suite belegt.
- `0.10.0 RC` ist nach den eigenen Freigabekriterien nicht bereit; die aktuelle Gesamt-CI ist rot. `1.0.0` braucht zusätzlich stabile Prozess-Ownership, abgeschlossene Migrationen und sieben blockierungsfreie RC-Tage.

## 2. Release Readiness

| Bereich | 0.10 RC | 1.0 | Begründung |
| --- | --- | --- | --- |
| Contracts/API | TEILWEISE | TEILWEISE | Pydantic und Zod sind breit vorhanden; der Live-Task-Zweig des Report-Status hat keinen Backend-Contract (`backend/app/services/report_status.py:225`; `frontend/src/contracts/reportStatusContract.ts:8`). |
| Evidence | TEILWEISE | OFFEN | High-/Inferred-Validatoren existieren; aggregierte Quantortragfähigkeit und Szenario-vs.-Fakt-Herkunft sind offen (`backend/app/services/evidence_entailment.py:917,1320`; `backend/app/contracts/report_contract.py:82`). |
| Personas/Simulation | TEILWEISE | OFFEN | Typgebundener Namens-Dedup vor Cap, aber keine Aliasidentität (`backend/app/services/prepare_entities.py:96-119`); Role-Leakage-Gate fehlt gemäß #1323. Recommender-Mittelwert-Pooling ist bereits verdrahtet (`backend/scripts/_sim_common.py:847`; drei produktive Runner). |
| Job-Lifecycle | TEILWEISE | OFFEN | Lease, Reconciliation sowie Graph-/Prepare-Checkpoint vorhanden; Report läuft im Daemon-Thread ohne äquivalenten Checkpoint (`backend/app/jobs/__init__.py:162`; `backend/app/api/runs.py:1187`). |
| Budgets | TEILWEISE | OFFEN | Reservierungen erfassen In-Flight-Calls pro Prozess; Enforcer-/Ledger-Fehler lassen Provider-Calls zu (`backend/app/llm/client.py:686-718`). |
| Embeddings | TEILWEISE | TEILWEISE | Store und versionierter Index steuern den Runtime-Pfad; UI-Modellwechsel und `readyz`-Wahrheit zur aktiven Route sind noch nicht geschlossen (`backend/app/services/embedding_configurations/runtime.py:87-107`; `backend/app/readiness.py:153-176`). |
| Manifest/Replay | OFFEN | OFFEN | Platzhalter-Inputs, leere Prompt-Snapshots und Replay ohne Manifestparameter (`backend/app/api/simulation_run.py:638-664`; `backend/app/api/runs.py:1191-1285`). |
| Betrieb/Release-Artefakte | NICHT NACHWEISBAR | OFFEN | Werkzeuge und PostgreSQL-Roundtrip-Tests existieren, letztere sind im geprüften CI-Lauf rot; der geforderte echte Host-Drill, Upgrade/Rollback und Release-Artefakte dieses RC sind nicht belegt (#766; `docs/STATUS.md:277`). |
| Produktnachweis | OFFEN | OFFEN | Drei reproduzierbare Referenzfälle mit Baselines, Varianz, Kosten und negativen Ergebnissen fehlen (#765). |
| CI/Security | OFFEN | OFFEN | Gesamt-CI rot: 6 neue PostgreSQL-Backup-Tests scheitern am `pg_dump`-Major-Mismatch ([Run 36072201453](https://github.com/arn0ld87/agora/actions/runs/36072201453)). Auth, SSRF, Trivy und Dependency-Audits sind implementiert (`backend/app/utils/auth.py:199`; `backend/app/security/outbound_http.py:366`; `.github/workflows/docker-image.yml:218`). |

## 3. Blocker

### [BLOCKER-001] Manifest und Replay kontrollieren den realen Lauf nicht

**Kategorie:** A. Fehler / G. fehlender Nachweis. **Bereich:** Reproduzierbarkeit. **Dateien:** `backend/app/api/simulation_run.py:620-664`, `backend/app/services/manifest_capture.py:79-107,184-207`, `backend/app/api/runs.py:1191-1285,1316-1367`, `backend/scripts/_sim_common.py:38-87`. **Issue:** #1274. **Problem:** Draft und Legacy-Manifest schreiben `unknown`, leere `prompts.entries` und einen aus der Simulations-ID abgeleiteten Wert, der im API-Code ausdrücklich als Platzhalter bezeichnet wird. Der Subprozess seeding nutzt inzwischen `config.random_seed` oder dieselbe ID-Ableitung; diese neue Runtime-Semantik wird im Manifest nicht nachgewiesen. Replay prüft nur, ob `manifest.json` existiert, klont den aktuellen Simulationszustand und löst Routing erneut auf. **Beleg:** Die Replay-Funktion liest keinen Manifestinhalt und `random_seed`-Override wird abgewiesen (`runs.py:1316-1367`). **Auswirkung:** Ein Replay kann andere Dateien, Prompts, Provider/Connections, Graph-/Embedding-Versionen und Modellantworten verwenden, ohne die Abweichung als Variante auszuweisen. **Empfehlung:** Manifest nur mit tatsächlich erfassten Werten finalisieren; unbekannte Legacy-Werte als `null` modellieren; Replay aus einem validierten Snapshot mit explizitem Diff starten. LLM-Antworten bzw. ihre Nichtdeterminismusgrenze offen ausweisen. **Benötigter Regressionstest:** Original-Run mit geänderter Route/Datei/Prompt replayen und Abweichungs- oder Ablehnungsnachweis; Seed aus Worker-Start gegen Manifest abgleichen. **Aufwand:** XL.

### [BLOCKER-002] Report-Job ist nach Prozessverlust nicht fachlich fortsetzbar

**Kategorie:** C. Reliability-Risiko. **Bereich:** Lifecycle. **Dateien:** `backend/app/jobs/__init__.py:1-4,139-162`, `backend/app/api/runs.py:1164-1188`, `backend/app/services/sim/reconciliation.py:133`, `docs/STATUS.md:169-179`. **Issue:** #1551, #1552. **Problem:** Lange Jobs laufen in Daemon-Threads des Webprozesses. Lease/Reconciliation terminalisieren verwaiste Jobs, Graph-Build und Hauptphase von Prepare haben Checkpoints. Für Report fehlt ein entsprechender Commit-/Resume-Checkpoint; `resume` startet Reportarbeit erneut, während bereits erzeugte Abschnitte und LLM-Aufrufe existieren können. Prepare-Backfill liegt ebenfalls außerhalb seines Checkpoints. **Beleg:** `docs/STATUS.md:173-177` beschreibt diese Grenzen; `runs.py:1461-1474` bietet zwar die Route, aber keine vollständige Fortsetzungsgarantie. **Auswirkung:** Crash/Retry kann teure Arbeit wiederholen und Artefaktzustände mehrdeutig machen. **Empfehlung:** Fachlich idempotente Report-Phasen und persistierte Abschnitts-Commits vor einem Out-of-Process-Worker definieren; Resume pro Phase explizit zulassen oder ehrlich als Restart markieren. **Benötigter Regressionstest:** SIGKILL an jeder Phasengrenze und nach Section-Write; Neustart darf weder `COMPLETED` noch Doppelabrechnung ohne Commit-Nachweis erzeugen. **Aufwand:** XL.

### [BLOCKER-003] Persona-Aliasidentität fehlt vor dem Cap

**Kategorie:** A. Fehler. **Bereich:** Graph → Personasatz. **Dateien:** `backend/app/services/prepare_entities.py:96-119,208-250`. **Issue:** #1470. **Problem:** Der Dedupe-Schlüssel ist normalisierter Anzeigename plus Entity-Typ. `BMW`, `BMW AG` und `Bayerische Motoren Werke` bleiben getrennt; Typvarianten ebenfalls. Der Cap folgt direkt nach diesem Schritt. **Beleg:** `_entity_identity_key` normalisiert Artikel/Endungen, führt aber keine belegten Aliasbeziehungen oder semantische Klasse zusammen. **Auswirkung:** Derselbe Stakeholder verbraucht mehrere Persona-Slots; technische Konzepte gelangen unnötig in die teure Eignungsprüfung. **Empfehlung:** kanonische Identität und belegte Aliasrelationen vor Cap/Quota; mehrdeutige Namen konservativ getrennt lassen. **Benötigter Regressionstest:** BMW- und BMG-Alias-Sets, Namensvettern, Typkonflikte, Cap-Verteilung und negativer Fall ohne belegbare Gleichsetzung. **Aufwand:** L.

### [BLOCKER-004] Quantoren und Szenario-Herkunft sind nicht ausreichend abgesichert

**Kategorie:** A. Fehler / G. fehlender Nachweis. **Bereich:** Evidence und Evaluation. **Dateien:** `backend/app/services/evidence_entailment.py:296-310,917-923,1320-1350`, `backend/app/contracts/report_contract.py:66-87`, `backend/app/services/report_agent/evidence.py:103`. **Issue:** #1345, #1240. **Problem:** Der deterministische Quantorpfad erkennt Mehrheit/Minderheit, aber nicht die volle geforderte Menge (`alle`, `nahezu alle`, `sechs von acht`, `niemand`) aus aggregierten Interviewstimmen. `EvidenceSourceKind.seed_corpus` unterscheidet Seed-Herkunft, aber keine im Seed beschriebene Szenarioannahme von einem unabhängigen Domänenfakt. **Beleg:** `_quantifier_direction` gibt nur `majority`/`minority` oder `None` zurück; das Quellarten-Enum enthält keine Szenario-Kategorie. **Auswirkung:** Ein thematisch passendes Einzelzitat oder vorgegebener Szenariotext kann eine stärkere Gesamtaussage plausibel aussehen lassen; der Produktnutzen der Simulation wird überschätzt. **Empfehlung:** Claim-Quantor/Grundgesamtheit kontraktieren und gegen aggregierte, unterschiedliche Stimmen prüfen; Szenarioannahmen separat typisieren und als alleinige Stütze sperren. ADR-0002-Hartanker nur mit eigenem Supersedes-ADR und Maintainer-Freigabe ändern. **Benötigter Regressionstest:** Falkenbrück-Gegenbeispiel aus #1345, positive belegte Einzelfakten, bereinigtes Seed-Dokument aus #1240. **Aufwand:** L.

### [BLOCKER-005] Simulationstreue ist nicht belegt

**Kategorie:** G. fehlender Nachweis. **Bereich:** Simulation. **Dateien:** `backend/scripts/_sim_common.py:847-891`, `backend/scripts/run_parallel_simulation.py:177`, `docs/STATUS.md:384-390`. **Issue:** #1323, #1603. **Problem:** Der Recommender-Pooler-Fix ist im aktuellen `main`; er darf nicht erneut als offene Implementierung gezählt werden. Der dokumentierte Role-Leakage-Referenzbefund und die fehlende Acceptance-Messung texttragender Aktionen bleiben. **Beleg:** `docs/STATUS.md:386` nennt 23/234 auffällige Aktionen; ein persistenznahes Persona-Consistency-Gate ist in den produktiven Runnerpfaden nicht nachgewiesen. **Auswirkung:** Reports können Simulationstext als Stakeholderreaktion behandeln, obwohl Agenten ihre Rolle verlassen. **Empfehlung:** repräsentativen Textkorpus klassifizieren, Fehlerrate/Schweregrad messen, dann ein begrenztes Gate vor Persistenz einführen; keine Prognose- oder Repräsentativitätsbehauptung daraus ableiten. **Benötigter Regressionstest:** gelabelte positive/negative Aktionsbeispiele über Twitter und Reddit, inklusive Fehlalarmquote. **Aufwand:** L.

### [BLOCKER-006] Restore, Upgrade und Rollback auf frischem Host sind nicht nachgewiesen

**Kategorie:** G. fehlender Nachweis. **Bereich:** Operations. **Dateien:** `scripts/restore-drill.sh`, `backend/app/infrastructure/postgres/pg_cli.py`, `backend/scripts/restore_verify.py`, `backend/tests/integration/test_postgres_backup_restore.py`, `docs/backup-restore.md`. **Issue:** #766. **Problem:** #1583 hat `pg_dump`/`pg_restore`, konsistentes Manifest und Integrationstest ergänzt. Das ist ein Werkzeug mit Testfällen, deren CI-Lauf aktuell scheitert, und kein End-to-End-Nachweis auf einem frischen Host mit Neo4j, Dateiartefakten, entschlüsselbaren Secrets, Upgrade und absichtlich fehlgeschlagener Migration. **Beleg:** `docs/STATUS.md` nennt den realen Drill ausdrücklich ausstehend; #766 führt ihn weiter als Done-Kriterium. **Auswirkung:** Datenwiederherstellung und Release-Rollback sind operativ nicht freigabefähig. **Empfehlung:** isolierten Fresh-Host-Drill samt prüfbarem Protokoll und Restore-Abgleich durchführen; Release-Checksummen/SBOM an den konkreten RC binden. **Benötigter Regressionstest:** automatisierter Restore-Roundtrip bleibt, dazu dokumentierter manueller Host-Drill mit absichtlich roter Migration. **Aufwand:** L.

### [BLOCKER-007] Produktnutzen gegenüber einfachen Baselines ist unbelegt

**Kategorie:** G. fehlender Nachweis. **Bereich:** Evaluation. **Dateien:** `ROADMAP.md:133-144`, `backend/tests/eval/`, `docs/reference-runs/`. **Issue:** #765, #1603. **Problem:** Einzelne Regressionen und Referenzläufe ersetzen die geforderte Vergleichssuite mit mindestens drei Fällen, statischer Persona-Liste und gutem Single-Prompt-Ansatz nicht. Der Simulationsbeitrag eines Referenzberichts wird in #1603 erst neu gemessen. **Auswirkung:** Der zentrale Mehrwert der zusätzlichen Pipeline-Komplexität ist extern nicht prüfbar. **Empfehlung:** Fälle und Bewertungsmetriken vorab einfrieren, negative Ergebnisse und Kosten/Laufzeit mitveröffentlichen. **Benötigter Regressionstest:** reproduzierbare Heavy-Eval mit gespeicherten Inputs, Szenario-Herkunft und Baseline-Vergleich. **Aufwand:** XL.

### [BLOCKER-008] Aktuelle Gesamt-CI scheitert am PostgreSQL-Client-Major

**Kategorie:** A. Fehler. **Bereich:** CI/Backup. **Dateien:** `.github/workflows/ci.yml:606,655`, `backend/app/infrastructure/postgres/pg_cli.py:101-165`, `backend/tests/integration/test_postgres_backup_restore.py:45-55,110-121`. **Issue:** #1583 ist geschlossen; kein offenes Folge-Issue. **Problem:** Die Integration startet PostgreSQL 17, während der Runner `pg_dump` 16.15 verwendet. Alle sechs neuen Backup-Roundtrip-Tests brechen vor der eigentlichen Verifikation mit `server version mismatch` ab. **Beleg:** [CI-Run 36072201453](https://github.com/arn0ld87/agora/actions/runs/36072201453), Job „Integration tests“: 6 failed, 74 passed; Server 17.11, Client 16.15. **Auswirkung:** `main` ist rot und der neue Restore-Nachweis in CI nicht erbracht. **Empfehlung:** PostgreSQL-17-Client im Integrationsjob festlegen und vor den Tests `pg_dump --version` gegen den Service-Major prüfen; dann denselben Workflow erneut ausführen. **Benötigter Regressionstest:** alle sechs Backup-Integrationstests in der regulären CI mit passendem Client und unverändertem PostgreSQL-17-Service. **Aufwand:** S.

## 4. High Findings

### [HIGH-001] Harte Budgets laufen bei Enforcer-/Ledger-Fehlern fail-open

**Kategorie:** A. Fehler. **Bereich:** Budget/Provider. **Dateien:** `backend/app/llm/client.py:686-718,738-754`, `backend/scripts/sim_runtime/budget_guard.py:134-168`, `backend/app/services/run_budget.py:267-296,322-354`. **Issue:** keines. **Problem:** `BudgetExceededError` wird durchgereicht, aber Fehler beim Erzeugen oder Lesen des Enforcers werden geloggt und der physische Call läuft weiter. `remaining_hard_calls` liefert bei Ledger-Lesefehler `None`, also „kein hartes Limit“. **Auswirkung:** Ein beschädigtes Budget-Ledger kann ausgerechnet im Fehlerfall Kosten- oder Call-Limits aufheben. **Empfehlung:** bei `enforcement="hard"` fail-closed oder den Lauf sichtbar mit dedizierter Budget-Infrastruktur-Degradation stoppen; weiche Budgets dürfen separat fail-open bleiben. **Benötigter Regressionstest:** Ledger-Read/Parse/Write-Fehler unmittelbar vor jedem physischen Call einschließlich Repair, Vision, Tool und IPC. **Aufwand:** M.

### [HIGH-002] RunRegistry ist nur innerhalb eines Prozesses konsistent

**Kategorie:** B. Architekturproblem / C. Reliability-Risiko. **Bereich:** Run-Status. **Dateien:** `backend/app/services/run_registry.py:39-52,84-98,182-190,252`, `backend/app/services/run_budget.py:205-207,339-354`. **Issue:** #1551. **Problem:** Singleton-Cache und Locks sind `threading`-lokal. `update_run` liest aus dem Cache und schreibt anschließend den ganzen Record; ein zweiter Prozess besitzt einen anderen Cache und andere Reservierungen. **Auswirkung:** Bei Worker-Überlappung oder künftigen Out-of-Process-Jobs können Status-Updates verloren gehen und harte Call-Budgets überbucht werden. Ein Webworker im heutigen Default begrenzt das Risiko, beseitigt die Architekturgrenze aber nicht. **Empfehlung:** prozessübergreifende CAS/Versionierung oder transaktionale Repository-Sperre; Budgetreservierungen im selben gemeinsamen Store. **Benötigter Regressionstest:** zwei Prozesse aktualisieren denselben Run und reservieren das letzte Call-Kontingent gleichzeitig. **Aufwand:** L.

### [HIGH-003] Report-Status und ReportV3 sind kein atomarer Commit

**Kategorie:** C. Reliability-Risiko. **Bereich:** Report-Persistenz. **Dateien:** `backend/app/services/report_agent/manager.py:1105-1139`, `backend/app/services/report_agent/storage.py:143-153,251-279,404-426`, `backend/app/services/report_agent/workflow.py:1762-1783`. **Issue:** #1297. **Problem:** Die frühe `ReportV3`-Validierung ist positiv; einzelne Dateien werden atomar geschrieben. `save_report` persistiert aber Metadaten einschließlich `COMPLETED` vor Outline und `report-v3.json`. Ein Crash genau dazwischen lässt einen vollständigen Status ohne passendes Artefakt zurück; ein späterer `ValidationError` beim V3-Bau wird nur geloggt. **Auswirkung:** API/Export können eine beschädigte oder alte Artefaktkombination als fertigen Bericht sehen. **Empfehlung:** Artefaktgeneration in Staging-Verzeichnis schreiben und erst nach validiertem Cross-File-Commit den Status/Marker publizieren; beim Lesen Generation und Referenzen abgleichen. **Benötigter Regressionstest:** Kill-/Fault-Injection zwischen Metadaten-, Outline-, Evidence-Map- und V3-Write. **Aufwand:** L.

### [HIGH-004] Live-Report-Status umgeht den Backend-/Frontend-Vertrag

**Kategorie:** B. Architekturproblem. **Bereich:** API/Frontend. **Dateien:** `backend/app/services/report_status.py:206-229`, `frontend/src/contracts/reportStatusContract.ts:8-16`, `frontend/src/composables/useReportGeneration.ts:71-103,169-179`. **Issue:** keines. **Problem:** Vier Status-Zweige verwenden `ReportStatusResponse`; der Live-Task-Zweig gibt `Task.to_dict()` zurück. Das Frontend verdrahtet seinen Zod-Parser deshalb ausdrücklich nicht und akzeptiert `status?: string` sowie freie Response-Dicts. **Auswirkung:** Neue oder verlorene Status-/Degradationswerte erreichen die UI ohne Contract-Fehler; Backend- und Frontend-Semantik können auseinanderlaufen. **Empfehlung:** zuerst einen diskriminierten Pydantic-Statusvertrag für alle Zweige definieren, danach JSON Schema/Zod und Polling umstellen. **Benötigter Regressionstest:** jeder Status-Resolver-Zweig gegen denselben Envelope; `INCOMPLETE`, `stopped`, Transportfehler und unbekannte Werte in der UI. **Aufwand:** M.

## 5. Medium Findings

### [MEDIUM-001] `readyz` meldet die Legacy-Embedding-Konfiguration als Betriebswahrheit

**Kategorie:** B. Architekturproblem. **Bereich:** Readiness/Embedding. **Dateien:** `backend/app/readiness.py:153-176,318-319`, `backend/app/services/embedding_configurations/runtime.py:87-107`. **Issue:** #1417. **Problem:** Die Betriebsdimension stammt bei aktiver Indexversion aus dem Store; `_check_embedding_config` prüft und meldet weiterhin `current_app.config["EMBEDDING_MODEL"/"VECTOR_DIM"]`. **Auswirkung:** Ein grüner Detailcheck kann das falsche Modell nennen, oder eine inkonsistente Legacy-Env kann den Healthcheck rot färben, obwohl der aktive Store-Pfad korrekt ist. **Empfehlung:** Readiness über denselben Resolver wie der Runtime-Pfad prüfen und Legacy nur ohne aktive Version verwenden. **Benötigter Regressionstest:** aktiver versionierter Index mit von der Legacy-Env abweichendem Modell/Dimension. **Aufwand:** S.

### [MEDIUM-002] Run-ZIP exportiert rekursiv ohne Dateityp-Allowlist und puffert alles im RAM

**Kategorie:** C. Reliability-Risiko / Security-Härtung. **Bereich:** Export. **Dateien:** `backend/app/api/runs.py:1398-1446`. **Issue:** #1274. **Problem:** Nach `manifest.json` schreibt `os.walk(run_dir)` jede weitere Datei ins ZIP; `BytesIO` plus `getvalue()` hält das Archiv vollständig im Speicher. Ein aktueller Secret-Leak aus einem konkreten Run-Artefakt wurde **NICHT VERIFIZIERT**. **Auswirkung:** Künftige Debug-/Routing-Dateien könnten unbeabsichtigt exportiert werden; große Läufe können den Webworker durch Speicherverbrauch blockieren. **Empfehlung:** explizite Artefakt-Allowlist und Größenlimit, danach echtes Streaming/temporäre kontrollierte Ausgabe. **Benötigter Regressionstest:** unerwartete Secret-Datei bleibt draußen; großer Report überschreitet ein definiertes Limit kontrolliert. **Aufwand:** M.

### [MEDIUM-003] CSV-Export schützt nicht vor Tabellenformeln

**Kategorie:** A. Fehler / Security. **Bereich:** Report-Export. **Dateien:** `backend/app/services/report_agent/csv_export.py:19-21,42-63,80-94,113-135`, `backend/app/services/report_export.py:227-234,294`. **Issue:** keines. **Problem:** Dokument-/LLM-abgeleitete `name`, `beschreibung`, `claim_text` und `notes` gehen unverändert in `csv.writer`. RFC-4180-Quoting verhindert keine Ausführung von Zellen, die mit `=`, `+`, `-` oder `@` beginnen, in Tabellenprogrammen. **Auswirkung:** Öffnet ein Nutzer den Export, kann untrusted Text als Formel interpretiert werden. **Empfehlung:** Textzellen vor dem CSV-Writer für Spreadsheet-Nutzung neutralisieren und Rohdatenexport bei Bedarf getrennt anbieten. **Benötigter Regressionstest:** Formelpräfixe einschließlich führender Leer-/Steuerzeichen in allen drei CSV-Typen. **Aufwand:** S.

## 6. Low Findings

### [LOW-001] Alte Kommentare widersprechen inzwischen der Seed-Runtime

**Kategorie:** D. Technical Debt. **Bereich:** Reproduzierbarkeit. **Dateien:** `backend/app/api/simulation_run.py:627-631`, `backend/app/api/runs.py:1358-1364`, `backend/scripts/_sim_common.py:71-87`. **Issue:** #1274. **Problem:** API-Kommentare behaupten, es gebe kein tatsächliches Runtime-RNG-Konzept; der Worker seedet inzwischen `random`. **Auswirkung:** Maintainer können den Platzhalter für den tatsächlich verbrauchten Seed halten und einen falschen Replay-Fix bauen. **Empfehlung:** Kommentare und Manifest-Semantik gemeinsam aktualisieren. **Benötigter Regressionstest:** Seed-Capture aus Subprozess-Start. **Aufwand:** S.

## 7. Architecture Debt

| Problem | Aktueller Zustand | Zielzustand | Risiko | Aufwand |
| --- | --- | --- | --- | --- |
| Prozesslokale Job-Ownership | Daemon-Threads, In-Memory-Cache und Lease in Dateimanifesten (`jobs/__init__.py:162`; `run_registry.py:50`) | Idempotente Schritte + dauerhafte Queue/Worker + CAS | Lost updates, Restart-Dopplung | XL |
| Report-Metadaten vs. Inhalt | `ReportRepository` abstrahiert `meta.json`, Inhalte bleiben direkter Dateizugriff (`manager.py:1120-1135`) | eine generationstreue Commit-Grenze; kein unnötiger Blob-Port vor Bedarf | Complete-Status ohne kohärente Artefakte | L |
| Mehrere Statusformen | Report-Status aus Registry, Task, Persistenz, Simulation (`report_status.py:285-314`) | ein diskriminierter Contract | UI-Drift | M |
| Hybrid-Metadaten | Profile/Projekte/Simulationen besitzen PG-Adapter, Run/Report noch Datei-Adapter (`backend/app/infrastructure/postgres/repositories/`) | konsistente Cutover- und Rollback-Reihenfolge | Teilmigration/Backup-Inkonsistenz | XL |
| Budgetreservierung | In-Memory pro Prozess (`run_budget.py:205-207`) | gemeinsamer atomarer Zähler pro Run | Overspend bei Mehrprozessbetrieb | L |

## 8. Missing Work

| Aufgabe | Warum notwendig | Release | Priorität | Aufwand |
| --- | --- | --- | --- | --- |
| PostgreSQL-Backup-CI reparieren | aktueller `main`-Integrationsjob: `pg_dump` 16 gegen Server 17, sechs Tests rot | 0.10 RC | P0 | S |
| Report-Checkpoint und Crash-Matrix | eigene P0-Lifecycle-Grenze | 0.10 RC | P0 | XL |
| Embedding-UI-Cutover und Readiness-Wahrheit | Store muss vollständig produktive Konfiguration sein | 0.10 RC | P0 | M |
| Aliasidentität, Role-Leakage-Messung | Personasatz/Simulation als Evidence-Grundlage | 0.10 RC | P0/P1 | L |
| Quantor-Gate und Szenario-Fakt-Typ | Claim-Korrektheit | 0.10 RC | P0/P1 | L |
| Manifest/Replay vervollständigen | Nachvollziehbarkeit | 0.10 RC | P1 | XL |
| Fresh-Host-Drill, Upgrade/Rollback, Checksummen | Release-Wiederherstellung | 0.10 RC | P1 | L |
| Baseline- und Gegenprobe-Suite | Produktnutzen | 0.10 RC | P1 | XL |
| PG-Run-/Report-Adapter, Gesamtmigration | stabile einheitliche Persistenz | 1.0 | P1 | XL |
| Prozessübergreifende Registry-/Budget-Transaktion | sichere Worker-Auslagerung | 1.0 | P1 | L |
| finaler grüner CI-/Security-/E2E-Lauf und sieben Tage RC | 1.0-Gate aus Roadmap | 1.0 | P1 | M |

## 9. Things That Work But Should Be Improved

1. **Einzeldatei-Atomizität:** `storage.py:143-153,251-279` nutzt Temp-Datei, `fsync` und `os.replace`; der Nachteil ist die fehlende atomare Beziehung zwischen Metadaten, Evidence-Map und V3. Ein Generation-/Commit-Marker macht alle Leser auf dieselbe Version fest. Migrationsrisiko: Legacy-Reports brauchen einen klar markierten Lesefallback.
2. **Reconciliation:** `sim/reconciliation.py` korrigiert verwaiste Zustände sichtbar. Der Nachteil ist, dass Erkennung allein keine idempotente Fortsetzung liefert. Phasen-Checkpoints vor einer Queue reduzieren Doppelarbeit. Migrationsrisiko: alte Runs ohne Checkpoint müssen explizit Restart bleiben.
3. **Embedding-Versionen:** `EmbeddingConfigurationStore` und Migrationsservice haben den Cutover weitgehend umgesetzt. `readyz` sollte dieselbe aktive Route statt Env-Daten berichten. Nutzen: Operator sieht die tatsächliche Modell-/Dimensionskombination. Migrationsrisiko: Legacy-Installationen ohne aktive Version benötigen den bestehenden Fallback.
4. **Budget-Ledger:** physische Aufrufe werden an mehreren Stellen erfasst und Tests decken Tool/Vision/IPC ab. Die prozesslokale Reservierung sollte mit der geplanten Worker-Auslagerung in denselben transaktionalen Store ziehen. Migrationsrisiko: Doppelzählung beim Übergang erfordert eindeutige Attempt-IDs.

## 10. Test Gaps

| Fehlerklasse | vorhandener Test | fehlender Test | Priorität |
| --- | --- | --- | --- |
| Report-Crash zwischen Dateien | `backend/tests/services/report_agent/test_partial_report_status.py`; atomare Write-Tests | SIGKILL/Fault-Injection zwischen Meta, Outline, Evidence und V3 mit erneutem API-/Export-Read | P0 |
| Harte Budgets bei Ledger-Fehler | `backend/tests/services/test_run_budget_reservation.py`, Tool-/Vision-/IPC-Tests | beschädigtes Ledger vor physischem Call und zwei Prozesse auf letztem Slot | P0 |
| Manifest vs. Runtime | `backend/tests/services/test_manifest_capture.py`, `backend/tests/api/test_start_run_writes_manifest.py` | Worker-Seed/Prompt/Input-Hash/Route wirklich im finalen Manifest und Replay-Parameter-Diff | P0 |
| Quantifizierte Interview-Claims | `backend/tests/regression/test_numeric_scope_entailment.py`, qualitative Entailment-Tests | aggregierte Stimmen für `alle`, `nahezu alle`, `sechs von acht`, `niemand`; Falkenbrück-Gegenfall | P0 |
| Persona-Alias vor Cap | Prepare-Dedup-/Quota-Tests | Alias-/Koreferenz-Sets, Namensvetter und fachliche Typkonflikte | P0 |
| Export-Injection/Allowlist | `backend/tests/api/test_report_export_csv.py`, ZIP-Tests | Formelpräfixe, fremde Datei im Run-Verzeichnis, Archiv-Limit | P1 |
| Restore auf frischem Host | `backend/tests/integration/test_postgres_backup_restore.py`, `test_restore_verify.py` | echter Gesamt-Drill mit Neo4j, Secrets, Migration-Fehlschlag und Rollback | P1 |
| PostgreSQL-Client/Server-Version in CI | sechs neue Backup-Integrationstests scheitern vor der Verifikation ([Run 36072201453](https://github.com/arn0ld87/agora/actions/runs/36072201453)) | passender `pg_dump`/`pg_restore`-Major und frühe Versionsprüfung im Job | P0 |
| Simulationstreue/Produktnutzen | Recommender-Regression und einzelne Referenzläufe | gelabeltes Role Leakage, negative Interaktionen, drei eingefrorene Baseline-Fälle | P1 |

## 11. Security Findings

**Bedrohungsmodell:** kontrolliert hybrider Single-User-Betrieb; Vertrauensgrenzen sind untrusted Dokument/LLM-Ausgabe → Graph/Report → CSV/ZIP, Browser → Token-geschützte API/SSE, sowie konfigurierte Provider-URL → ausgehende Netzwerkverbindung. Auth-Guards liegen an den API-Blueprints (`backend/app/__init__.py:428-468`), Nicht-Debug-Start verlangt Token oder bewusstes Opt-out (`config.py:738-751`). Outbound-HTTP validiert DNS/IP und Redirects (`security/outbound_http.py:366,473-539`). Für diese Mechanismen wurde kein konkreter Bypass belegt.

1. **Medium – CSV Formula Injection:** [MEDIUM-003]. Beleg `backend/app/services/report_agent/csv_export.py:52,87,126`; untrusted Zellen werden nur CSV-gequotet. Ein Claim-Text `=1+1` bleibt eine Tabellenformel. Neutralisierung und Test vor Release.
2. **Medium – unbeschränkter Run-Export:** [MEDIUM-002]. Beleg `backend/app/api/runs.py:1422-1446`; rekursiver Export ohne Allowlist und vollständiger RAM-Puffer. Konkrete Secret-Datei im heutigen Run-Verzeichnis **NICHT VERIFIZIERT**; daher kein behaupteter aktueller Secret-Leak.
3. **Nicht verifiziert:** Eine aktuelle Live-CVE-Freiheit oder vollständige Secret-Rotation lässt sich aus Code und grünen Security-Teiljobs allein nicht ableiten. Trivy-, `pip-audit`-, `bun audit`-, CodeQL- und Dependency-Review-Gates existieren (`.github/workflows/docker-image.yml:218-296`; `.github/workflows/ci.yml:100-146`). Die Gesamt-CI ist wegen des PostgreSQL-Backup-Jobs rot, nicht wegen eines belegten Security-Befunds.

## 12. Issue Audit

Alle zum Prüfzeitpunkt **30 offenen** Issues wurden gelesen. `OPEN_CORRECT` bedeutet weiterhin sinnvoller Scope, nicht Release-Priorität. `PARTIALLY_DONE` und `OPEN_NEEDS_UPDATE` sind Empfehlungen; kein Issue wurde geändert.

| Issue | Status | Begründung am Prüfcommit | empfohlene Aktion |
| --- | --- | --- | --- |
| [#1603](https://github.com/arn0ld87/agora/issues/1603) | OPEN_CORRECT | Referenzlauf-Messungen und Simulationsbeitrag stehen aus; `simulation_contribution` existiert (`report_agent/simulation_contribution.py`). | M1–M3 messen, negative Ergebnisse dokumentieren. |
| [#1593](https://github.com/arn0ld87/agora/issues/1593) | OPEN_CORRECT | Optionaler Blob-Cutover folgt erst auf S14–S16. | Hinter Pflicht-RC-Arbeit halten. |
| [#1592](https://github.com/arn0ld87/agora/issues/1592) | OPEN_CORRECT | Default ist weiter Legacy (`docs/STATUS.md:289-341`). | Cutover erst nach S5/S7/S10–S12 und Drill. |
| [#1591](https://github.com/arn0ld87/agora/issues/1591) | OPEN_CORRECT | `agora.artifacts`-Modell fehlt unter `backend/app/infrastructure/postgres/models/`. | Optionalen Metadaten-Slice separat halten. |
| [#1590](https://github.com/arn0ld87/agora/issues/1590) | OPEN_CORRECT | `backend/scripts/verify_metadata_cutover.py` fehlt im Tree. | Nach Adaptern und Gesamtgate bauen. |
| [#1589](https://github.com/arn0ld87/agora/issues/1589) | OPEN_CORRECT | Einzelmigrationstests existieren, Gesamt-Migrations-/Rollback-Gate fehlt. | Integrationsmatrix über alle Backends ergänzen. |
| [#1588](https://github.com/arn0ld87/agora/issues/1588) | OPEN_CORRECT | `ReportRepository`/File-Adapter seit #1580 vorhanden, PG-Report-Adapter fehlt. | S7 implementieren, Export-Parität prüfen. |
| [#1587](https://github.com/arn0ld87/agora/issues/1587) | OPEN_CORRECT | `RunRepository` existiert, PG-Run-Adapter fehlt. | S5 und Resume-/CAS-Test. |
| [#1586](https://github.com/arn0ld87/agora/issues/1586) | OPEN_CORRECT | Optionaler Supabase-Blob-Adapter fehlt. | Nach S14/Bedarf neu priorisieren. |
| [#1584](https://github.com/arn0ld87/agora/issues/1584) | OPEN_CORRECT | `BlobArtifactStore`-Port fehlt; aktuelle Report-Inhalte sind Dateien (`report_agent/storage.py`). | Optionalen Port nur mit messbarem Cutover-Nutzen bauen. |
| [#1576](https://github.com/arn0ld87/agora/issues/1576) | PARTIALLY_DONE | PG-Profile/Projekt/Simulation und PG-Backup sind im Code; Run-/Report-PG und Cutover fehlen. Der neue Backup-Integrationstest ist aktuell CI-rot. | Fortschritt, CI-Folgefehler und Abhängigkeiten nach #1580/#1583 aktualisieren. |
| [#1552](https://github.com/arn0ld87/agora/issues/1552) | OPEN_NEEDS_UPDATE | `/resume` hat `simulation_run`-Route (`runs.py:1466`), setzt aber nur eine lebend pausierte Simulation fort; nach Crash erzeugt es einen neuen Run (`runs.py:989-1034`). Report hat keinen gleichwertigen Checkpoint. | Titel/AC präzisieren: „Crash-Resume vs. Neustart der Simulation“; Entscheidung (a/b/c) beibehalten. |
| [#1551](https://github.com/arn0ld87/agora/issues/1551) | OPEN_CORRECT | Daemon-Threads und prozesslokale Registry-/Budget-Locks (`jobs/__init__.py:162`; `run_registry.py:50`). | Worker nur mit CAS/Idempotenz auslagern. |
| [#1495](https://github.com/arn0ld87/agora/issues/1495) | PARTIALLY_DONE | Mypy-Schuld- und Coverage-Gates existieren; datierte Radon-Zielkurve bleibt offen. | Nur verbliebene Debt-Slices verfolgen. |
| [#1470](https://github.com/arn0ld87/agora/issues/1470) | OPEN_CORRECT | Typgebundener Namens-Dedup (`prepare_entities.py:96-119`) löst Aliase nicht. | Kanonische Identität vor Cap. |
| [#1417](https://github.com/arn0ld87/agora/issues/1417) | OPEN_NEEDS_UPDATE | Issue-Text vom 19.09. behauptet fehlenden Runtime-Cutover; aktive Indexnamen und Dimension werden inzwischen aufgelöst (`embedding_configuration_store.py:281-317`; `embedding_configurations/runtime.py:87-107`). UI/Readiness bleiben offen. | Erledigte Slices streichen, Rest-AC auf UI, Readiness und Legacy-Bestand fokussieren. |
| [#1400](https://github.com/arn0ld87/agora/issues/1400) | OPEN_CORRECT | Claim-Typ-Klassifikation/Confidence-Semantik noch Designfrage; `ReportClaimModel` hat Confidence-Gates, keine vollständige Typstrategie. | ADR-nahe Entscheidung vor Code. |
| [#1345](https://github.com/arn0ld87/agora/issues/1345) | OPEN_CORRECT | Quantorpfad deckt Mehrheit/Minderheit, keine aggregierte Stakeholder-Zählung (`evidence_entailment.py:917-923,1320-1350`). | Falkenbrück-Test + Gegenprobe #1317. |
| [#1323](https://github.com/arn0ld87/agora/issues/1323) | OPEN_CORRECT | Gemessene Rollenabweichung dokumentiert; Persistenz-Gate nicht nachgewiesen (`docs/STATUS.md:386`). | Erst Korpus/Fehlalarmquote, dann Gate. |
| [#1304](https://github.com/arn0ld87/agora/issues/1304) | PARTIALLY_DONE | Simulationsbeitrag technisch instrumentiert; M3-Messung nach #1603 verlagert, Netzwerk-/Position-Shift-Semantik offen. | AC auf verbleibende Dynamik/Evidence-Provenance verengen. |
| [#1297](https://github.com/arn0ld87/agora/issues/1297) | PARTIALLY_DONE | Evidence-Map/Validatoren vorhanden; Quantoren, Typstrategie und Cross-File-Commit offen. | Epic-Checkliste an #1345/#1400 und Report-Commit binden. |
| [#1292](https://github.com/arn0ld87/agora/issues/1292) | OPEN_NEEDS_UPDATE | Issue belegt alten Tabellen-Chunk, nennt Ursache selbst „ungeprüft“; aktueller Prompt-/Modell-Lauf wurde hier nicht wiederholt. | aktuellen Reproducer, Prompt-Snapshot und Modellversion ergänzen, bevor Fix-Scope feststeht. |
| [#1287](https://github.com/arn0ld87/agora/issues/1287) | OPEN_CORRECT | Kein Bedrock-Converse-Adapter unter `backend/app/llm/providers/`. | Nicht vor RC-Trust-Arbeit priorisieren. |
| [#1285](https://github.com/arn0ld87/agora/issues/1285) | OPEN_CORRECT | Kein Bedrock-Embedding-Adapter im Embedding-Runtime-Pfad. | Hinter #1417 priorisieren. |
| [#1274](https://github.com/arn0ld87/agora/issues/1274) | OPEN_CORRECT | Manifest-Platzhalter und unvollständiges Replay konkret belegt (`simulation_run.py:638-664`; `runs.py:1191-1285`). | Runtime-Parameter einfrieren und Varianten-Diff. |
| [#1240](https://github.com/arn0ld87/agora/issues/1240) | OPEN_CORRECT | `seed_corpus` trennt Dokument von Simulation, nicht Szenarioannahme von Domänenfakt (`report_contract.py:82-87`). | Quellsemantik und bereinigte Gegenprobe. |
| [#812](https://github.com/arn0ld87/agora/issues/812) | OPEN_CORRECT | Repo nutzt TypeScript `^6.0.3`, `vue-tsc ^3.3.11`, Parser `^8.70.0` (`frontend/package.json`); Issue ist ausdrücklich extern blockiert. | Erst bei verfügbaren Voraussetzungen neu triagieren. |
| [#767](https://github.com/arn0ld87/agora/issues/767) | OPEN_CORRECT | 1.0-Gate bleibt mit Migration, Betrieb und Produktnachweis offen (`ROADMAP.md:158-174`). | Parent-Gate offen halten. |
| [#766](https://github.com/arn0ld87/agora/issues/766) | PARTIALLY_DONE | PG-Backup-Werkzeug und Roundtrip-Test seit #1583; Test in CI wegen Client-Mismatch rot, echter Host-/Rollback-Drill offen. | Erst CI reparieren, dann Done-Text auf verbleibenden Host-Nachweis aktualisieren. |
| [#765](https://github.com/arn0ld87/agora/issues/765) | OPEN_CORRECT | Geforderte Baseline-Suite und drei Fälle nicht nachgewiesen (`ROADMAP.md:133-144`). | Vor RC reproduzierbar ausführen. |

Kein offenes Issue konnte am Prüfcommit belastbar als `DONE_BY_CODE`, `DUPLICATE`, `OBSOLETE` oder `WRONG_ASSUMPTION` klassifiziert werden. Die bereits geschlossenen #1580/#1583 sind im Code berücksichtigt; #1583 hat einen neuen CI-Folgefehler (BLOCKER-008), und der noch offene Text von #1417 ist teilweise überholt.

## 13. Documentation Drift

| Dokument | Aussage | tatsächlicher Codezustand | Änderung |
| --- | --- | --- | --- |
| `ROADMAP.md:100` | #1236/Recommender-Pooler offen | Mean-Pooling-Patch in `_sim_common.py:847`, Aufruf in Twitter/Reddit/Parallel-Runnern; #1236 geschlossen | Kriterium als erfüllt markieren; keine erneute Implementierung planen. |
| `docs/STATUS.md:402` | Prepare-Resume noch offen | `docs/STATUS.md:173` beschreibt bereits Hauptphasen-Checkpoint und `INTERRUPTED`; Backfill bleibt offen | Alte Sammelaussage auf Report und Prepare-Backfill eingrenzen. |
| `docs/STATUS.md:403` | `VECTOR_DIM`-SSoT und Frontend-`building`-Spiegel fehlen | `runtime.py:87-107` löst Betriebsdimension auf; `frontend/src/contracts/embeddingContract.ts:55-59` und Test akzeptieren `building` | Liste auf tatsächliche Restarbeit aktualisieren. |
| [#1417](https://github.com/arn0ld87/agora/issues/1417) | Aktiver Read-/Write-Index habe keinen Cutover | Store löst aktive Entity-/Fact-Indizes auf (`embedding_configuration_store.py:281-317`) | Issue-Text/AC neu schneiden. |
| [#1552](https://github.com/arn0ld87/agora/issues/1552) | `simulation_run` habe keinen Resume-Pfad | Route existiert; Crash-Fall startet neu (`runs.py:989-1034,1466-1467`) | „kein fachlich äquivalentes Crash-Resume“ schreiben. |
| `backend/app/api/simulation_run.py:627-631` | `random_seed` nur Platzhalter, kein RNG-Wiring | Worker nutzt `seed_simulation_rng` (`_sim_common.py:71-87`) | Capture und Kommentar in einem Slice korrigieren. |

## 14. Unnecessary Complexity

- **Entfernung:** veraltete Roadmap-/STATUS-Häkchen und API-Kommentare, die fertige Slices erneut als offen ausweisen. Messbarer Nutzen: weniger Doppelarbeit und falsche Release-Entscheidungen.
- **Zusammenführung:** fünf Report-Status-Resolver unter einem Pydantic-Union-Envelope statt Task-Dict-Sonderform. Messbarer Nutzen: ein Schema-Gate und ein Frontend-Parser.
- **Vereinfachung:** Replay aus einem einzigen validierten Manifest-Snapshot statt aktueller Branch-State plus separat erneut aufgelöster Route. Messbarer Nutzen: explizite Parameterabweichungen.
- **Ablösung:** prozesslokaler Registry-Cache/Reservierungszähler beim Worker-Cutover durch transaktionale Versionierung. Messbarer Nutzen: keine Cross-Process-Lost-Updates.
- **Nicht voreilig abstrahieren:** optionaler BlobArtifactStore/SupabaseBlob-Cutover (#1584/#1586/#1593) bringt vor den Pflicht-RC-Nachweisen keinen belegten Nutzen; der Dateipfad funktioniert und wird bereits gesichert.

## 15. Top 10 Next Actions

1. **PostgreSQL-17-Client im CI-Integrationsjob festlegen.** Warum jetzt: `main` ist rot und der neue Backup-Roundtrip läuft nicht. Abhängigkeit: PostgreSQL-17-Service. AC: `pg_dump`-Major passt zum Server, alle sechs Backup-Tests und der gesamte Integrationsjob sind grün. Test: regulärer CI-Run. Dateien: `.github/workflows/ci.yml`, `backend/tests/integration/test_postgres_backup_restore.py`. Aufwand: S.
2. **Report-Commit/Crash-Gate schließen.** Warum jetzt: falsches `COMPLETED` gefährdet Auslieferung. Abhängigkeit: ReportV3-/Evidence-Vertrag. AC: Status erst nach validiertem generationstreuem Commit; Kill an jeder Write-Grenze bleibt sichtbar `INCOMPLETE`/`failed`. Test: Fault-Injection. Dateien: `report_agent/manager.py`, `storage.py`, `workflow.py`, Report-API. Aufwand: L.
3. **Budget-Hard-Limit fail-closed machen.** Warum jetzt: Ausgabenbegrenzung ist im Fehlerfall nicht hart. Abhängigkeit: definierte Fehler-/Degradationssemantik. AC: kein physischer Provider-Call bei unlesbarem Hard-Budget. Test: Ledger-Fehler für Chat, Repair, Tool, Vision, IPC. Dateien: `llm/client.py`, `run_budget.py`, `sim_runtime/budget_guard.py`. Aufwand: M.
4. **Quantor- und Szenario-Provenance-Gate definieren.** Warum jetzt: Evidence-Korrektheit. Abhängigkeit: ADR-0002-Grenzen und #1400-Typentscheidung. AC: Falkenbrück-Claim nicht supported; belegte Einzelfakten bleiben. Test: #1345/#1240-Gegenproben. Dateien: `report_contract.py`, `evidence_entailment.py`, `llm_entailment_judge.py`. Aufwand: L.
5. **Persona-Aliasidentität vor Cap einführen.** Warum jetzt: falscher Personasatz färbt alle Folgeschritte. Abhängigkeit: kontrollierte semantische Klasse. AC: ein belegter BFW-/BMW-Akteur pro beabsichtigter Repräsentation. Test: Alias-/Namensvetter-Matrix. Dateien: `prepare_entities.py`, NER/Graph-Contract. Aufwand: L.
6. **Simulationstreue messen und Gate begrenzen.** Warum jetzt: Synthese darf nicht als echte Stakeholderposition ausgegeben werden. Abhängigkeit: gelabelter Referenzkorpus. AC: Role Leakage und negative Interaktionen mit Fehlalarmquote berichtet. Test: Twitter-/Reddit-Aktionen. Dateien: Runner-/Post-Event-Pfad, `backend/tests/eval/`. Aufwand: L.
7. **Manifest/Replay an Runtime koppeln.** Warum jetzt: Baseline und Audit setzen nachvollziehbare Inputs voraus. Abhängigkeit: Stage-Routen- und Prompt-Snapshot-Vertrag. AC: Originalparameter eingefroren, Legacy `null`, Varianten-Diff sichtbar. Test: geänderte Route/Seed/Datei. Dateien: `run_manifest_contract.py`, `manifest_capture.py`, `simulation_run.py`, `runs.py`. Aufwand: XL.
8. **Embedding-Restscope schließen.** Warum jetzt: Roadmap-P0 und Health-Wahrheit. Abhängigkeit: aktiver Indexversionspfad. AC: UI kann nur validierten Cutover aktivieren; `readyz` meldet aktive Route. Test: Legacy-vs.-Store-Divergenz. Dateien: `readiness.py`, `embedding_configurations/runtime.py`, `frontend/src/contracts/embeddingContract.ts`, UI. Aufwand: M.
9. **Fresh-Host-/Rollback-Drill ausführen.** Warum jetzt: 0.10-Release-Nachweis. Abhängigkeit: Referenzdaten und Backup-Snapshot. AC: Graph, Runs, Reports, PG, entschlüsselbare Secrets, Upgrade und absichtlich rote Migration verifiziert. Test: bestehender PG-Roundtrip plus protokollierter Host-Drill. Dateien: `scripts/restore-drill.sh`, `restore_verify.py`, Runbook. Aufwand: L.
10. **Drei Baseline-Referenzfälle veröffentlichbar machen.** Warum jetzt: größte Produktannahme. Abhängigkeit: Quantor-/Szenario-Gates, Persona- und Simulationstreue sowie eingefrorene Inputs. AC: Agora vs. Single Prompt/statische Personas, Treffer/Fehler/Varianz/Kosten/Laufzeit einschließlich negativer Fälle. Test: Heavy-Eval. Dateien: `backend/tests/eval/`, `docs/reference-runs/`. Aufwand: XL.

## Kritische Abschlussfragen

**Größtes technisches Risiko:** Eine nach Crash/Retry oder schwachem Evidence-Binding als vollständig ausgelieferte, fachlich zu starke Reportaussage. Die Grenze liegt zwischen Status-/Artefakt-Commit und Evidence-Semantik (`manager.py:1120-1137`; `report_contract.py:510-549`).

**Größte unbelegte Annahme:** Dass Graph → Personas → Simulation → Evidence gegenüber einem guten Single-Prompt- oder statischen Persona-Ansatz nachweisbar bessere Entscheidungen liefert. #765 verlangt diesen Vergleich; #1240 und #1603 zeigen, welche Herkunfts- und Beitragsmessungen noch fehlen.

**Gefährlichste versteckte Komplexität:** Der Report-Workflow: Planung, Tool-/Interview-IPC, Budget, Binding, mehrere Gates, getrennte Artefakte und Resume laufen über verschiedene Persistenz- und Statuspfade (`report_agent/workflow.py`, `manager.py`, `report_status.py`). Einzelne Gates sind stark; ihre gemeinsame Crash-Semantik ist nicht belegt.

**Was fehlt für 0.10 RC?** Zuerst die rote PostgreSQL-Backup-CI beheben; dann verlässliche Report-/Prepare-Fortsetzung nach Restart, Embedding-UI/Readiness, Alias-/Role-Leakage- und Quantor-/Szenario-Gates, vollständiges Manifest/Replay, Fresh-Host-Restore/Upgrade/Rollback mit Artefakten und drei Baseline-Fälle nachweisen. Siehe Blocker 001–008 und `ROADMAP.md:90-148`.

**Was fehlt danach für 1.0?** Versionierte einheitliche Status-/Persistenzverträge, Run-/Report-PG-Cutover mit Migration/Rollback, prozessübergreifende Worker-/Budget-Koordination, alle Release-Gates, öffentlicher Referenzlauf und mindestens sieben Tage finaler RC ohne neuen P0/P1-Blocker (`ROADMAP.md:158-174`).

**Was würde ein externer Gutachter zuerst angreifen?** Die Differenz zwischen detaillierten Reproduzierbarkeits-/Evidence-Zusagen und dem tatsächlich erfassten Manifest sowie dem noch fehlenden Baseline-/Restore-Nachweis; danach die ungesicherte Cross-File-Report-Commit-Grenze. Diese Reihenfolge folgt direkt aus `simulation_run.py:638-664`, `runs.py:1191-1285`, #765/#766 und `manager.py:1120-1137`.

**Was sollte nicht gebaut werden?** Vor RC kein Multi-User, Kubernetes, Federation, allgemeines Plugin-System, weiterer großer Frontend-Rewrite, optionaler Blob-Cutover oder Bedrock-Adapter ohne nachgewiesenen Bezug zu den obigen Gates. Die Roadmap schließt solche Feature-Ausweitung für die RC-Phase ausdrücklich aus (`ROADMAP.md:146-148,178-189`).
