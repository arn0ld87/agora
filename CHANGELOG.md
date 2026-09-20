# Changelog

Alle nennenswerten Änderungen an Agora werden hier dokumentiert.
Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

## [0.9.6] - 2026-09-20

Ein Zwischenrelease zwischen `0.9.5` (11.08.2026) und dem Ziel `0.10.0`: mehr als 330 Commits, 184 eingesammelte Changelog-Fragmente, sechs Wochen Arbeit. Es ist ausdrücklich **kein `0.10.0`** — die neun Release-Prioritäten aus [`ROADMAP.md`](ROADMAP.md) sind nicht erfüllt, und dieses Release beansprucht keines ihrer Gates.

Vier Wege zu einem Modell statt einem: neben HTTP sprechen `codex_cli` und `claude_cli` eine lokal installierte CLI über deren Login-Session — ohne API-Key, ohne Endpunkt — und Amazon Bedrock kommt als OpenAI-kompatibler Provider dazu. Das Request-Shaping liegt dafür nicht mehr verteilt in `chat`, `describe_image` und `tool_calls`, sondern hinter `build_request` und `execute` in `app/llm/request_plan.py`.

Eine PostgreSQL-Schicht existiert, **und niemand benutzt sie**: LLM-Profile, Provider-Secrets und Projektmetadaten haben je einen Repository-Port mit Datei- und Postgres-Adapter, dazu eine Alembic-Baseline und einen prüfbaren Restore-Drill. `AGORA_METADATA_BACKEND`, `AGORA_PROJECT_BACKEND` und `AGORA_LLM_PROFILE_BACKEND` stehen alle drei auf dem Dateipfad. Die Schicht ist gebaut, nicht in Betrieb.

Die Oberfläche ist über zehn PRs neu geschnitten — Ablage und Dossier sind der Einstieg, das Legacy-Frontend ist abgebaut. Der grösste Block sind Evidence- und Report-Härtungen: Claim-Atomisierung, semantisches Entailment statt Wortüberlappung, Interview-Panel-Rotation, ein Requirement-Checker vor Report-Abschluss, global eindeutige Claim- und Gap-IDs.

Was dieses Release **nicht** liefert: Reproduzierbarkeit. `RunManifest` und Replay-Dialog existieren strukturell, das Manifest ist aber kein vollständiger Reproduktionsanker — derselbe gespeicherte Seed erzeugt weiterhin nicht denselben Lauf (#763/#1274). Die Embedding-SSoT-Ausnahme (#1417) ist enger geworden, nicht geschlossen: Slice 2.1 und 2.2 sind gelandet, 2.3 und 2.4 offen. Langläufer ausserhalb der OASIS-Simulation überleben einen Neustart weiterhin nicht (#1472) — der neue `atexit`-Hook markiert sie ehrlich als `failed/process_restart`, statt sie stumm verschwinden zu lassen.

### Release-Metadaten — Zenodo-Versionsstring

`.zenodo.json` setzt seit dem 0.9.6-Schnitt ein eigenes `version`-Feld. Zuvor
gab es keines, und der Zenodo-Webhook übernahm den Tag-Namen — die sechs
bisherigen Archiv-Einträge stehen deshalb als `v0.9.5`, `v0.9.4` und so
weiter. Der Wert lautet jetzt `v0.9.6` statt `0.9.6`, damit die Versionsliste
im Archiv einheitlich bleibt; nachträglich lässt sich das dort nicht mehr
korrigieren. `VERSION` und `CITATION.cff` führen weiterhin die reine
SemVer-Zahl — CFF-Konvention und Quelle für `check_version_drift.py`.

### Slice 1.3 — Graph-Build-Resume

Ein unterbrochener Graph-Build kann jetzt an der Stelle fortgesetzt werden, an
der er abgebrochen wurde, statt komplett neu zu starten. `GraphBuilderService.
add_text_batches` verarbeitet Chunks parallel über einen `ThreadPoolExecutor`
und schließt sie deshalb außerhalb ihrer Ursprungsreihenfolge ab — ein
einzelner Höchstwert-Cursor wie bei `EmbeddingMigrationProgress.
last_processed_id` reicht als Checkpoint-Einheit nicht. Der neue
`GraphBuildCheckpoint`-Vertrag (`backend/app/contracts/
graph_build_checkpoint_contract.py`) führt deshalb die tatsächliche MENGE
bereits committeter Chunk-Indizes, nicht nur einen Höchstwert, und wird je
Projekt (nicht je Run-ID) atomar mit `fsync` persistiert — ein Resume-Versuch
legt einen eigenen, neuen Run an, der Fortschritt selbst gehört aber zum
Graph-Build-Vorhaben des Projekts als Ganzes und muss über mehrere Versuche
hinweg erhalten bleiben.

Der Plan-Wortlaut "Stage-Checkpoint pro abgeschlossenem Build-Abschnitt" trägt
nicht wörtlich: der Build zerfällt nicht in abgrenzbare Abschnitte wie
Ingest/Chunking/Extraktion/Embedding/Write, sondern ist eine durchgehende
Chunk-Schleife, in der jeder Chunk NER-Extraktion, Embedding und Neo4j-Write
in einem Aufruf bündelt. Die richtige Einheit ist ein Chunk-Index.

Der Checkpoint bindet sich zusätzlich an `graph_id`, `chunk_size`,
`chunk_overlap` und eine `manifest_anchored`-Flagge (dokument-verankerte vs.
Legacy-Chunk-Zerlegung). Das ist kein Zusatzschutz, sondern zwingend: Neo4j
dedupliziert Entities über einen inhaltlichen MERGE-Schlüssel
(`graph_id + name_lower + entity_type`), aber Episode- und Relation-Knoten
über eine je Aufruf frisch generierte UUID — ein erneut prozessierter, bereits
committeter Chunk würde also Dubletten-Episoden und -Relationen erzeugen statt
sie zu deduplizieren. Ändern sich Chunk-Größe, Overlap oder die
Chunking-Methode gegenüber dem Original-Lauf, bedeutet ein Chunk-Index nicht
mehr dasselbe Textstück — der Checkpoint gilt dann als ungültig und die Route
fällt sauber auf einen kompletten Restart zurück, statt falsch übersprungene
Chunks zu produzieren.

`POST /api/runs/<id>/resume` bietet für `graph_build`-Runs jetzt zwei Pfade
hinter derselben Route (analog dem bestehenden Resume/Restart-Dispatch für
`simulation_run`): `_resume_or_restart_graph_build` prüft den Checkpoint gegen
die aktuelle Chunk-Zerlegung und wählt `GraphBuildService.resume_graph_build`
(setzt am Checkpoint fort, kein erneutes `create_graph`, verarbeitet nur die
noch nicht abgeschlossenen Chunks) oder fällt auf den bestehenden
`_restart_graph_build` zurück. `resume_capability` beschreibt jetzt den
tatsächlichen Zustand: `resume` wird nur angeboten, wenn ein zum aktuellen
Graphen passender Checkpoint mit mindestens einem abgeschlossenen Chunk
existiert — ein angebotenes Resume, das doch bei null beginnt, wäre schlimmer
als keins.

Das schließt auch den Prozess-Neustart-Fall aus Slice 1.1 aus #1472: dessen
Changelog hielt ausdrücklich fest, dass dort "kein vollständig persistierter
interrupted-/Resume-Zustand" entsteht. Sowohl der Shutdown-Hook
(`services/sim/process_shutdown.py`) als auch die Startup-Reconciliation
(`services/sim/reconciliation.py`) markierten `graph_build`-Runs bisher ohne
Checkpoint-Prüfung failed/`process_restart` und ließen dabei den sticky
`restart`-Default aus der Run-Anlage stehen. Beide setzen jetzt für
`graph_build`-Runs `resume_capability` anhand des vorhandenen Checkpoints
(leichtgewichtige Prüfung: Graph-Identität + mindestens ein fertiger Chunk;
die volle Parametervalidierung inklusive Chunk-Größe/Overlap übernimmt erst
der eigentliche Resume-Versuch und fällt bei Nichtübereinstimmung sauber auf
Restart zurück). Ohne diese Ergänzung würde der genau für diesen Fall gebaute
Checkpoint-Mechanismus dem Nutzer nie angeboten — der Prozess-Neustart ist der
Hauptfall, für den Slice 1.3 überhaupt existiert.

Ein Checkpoint-Schreibfehler (Festplatte, Berechtigungen) propagiert
unverändert aus `add_text_batches` heraus und beendet den betroffenen Run
sichtbar als `failed`, statt den Build unbemerkt ohne aktuellen Checkpoint
weiterlaufen zu lassen.

Weiterhin offen: Prepare-Resume (Slice 1.4, #1472c) und Heartbeat/Lease
(Slice 1.5, #1472d). #1472 als Ganzes ist damit nicht geschlossen.

Review-Nachbesserung (PR #1535): drei Fälle behoben. Erstens scheiterte ein
Build nach dem ersten gesetzten Checkpoint bislang mit `delete_graph`, obwohl
`resume_capability` weiter `resume` anbot — der Resume-Pfad arbeitet aber
ausschließlich mit `MATCH` und hätte ins Leere gegriffen. Der Checkpoint wird
jetzt zusammen mit dem gelöschten Graphen verworfen, danach bleibt nur noch
`restart` eine ehrliche Option. Zweitens verlor `add_text_batches` bei einem
scheiternden Chunk in der `as_completed`-Schleife den Checkpoint für Chunks,
die zu diesem Zeitpunkt bereits erfolgreich committet, aber noch nicht
gecheckpointet waren — ein anschließender Resume hätte sie erneut verarbeitet
und Dubletten-Episoden erzeugt. Drittens durchlief ein resumeter Build das
Qualitätsgate (`assess_graph_quality_from_counts`) nicht und trug deshalb nie
eine `degradations`-Meldung, selbst wenn der fertige Graph unter der
Mindestzahl an Relationen blieb — der resumete Pfad meldet diese Degradation
jetzt genauso wie der Original-Build.

### Added (die LLM-Profile können jetzt in PostgreSQL liegen — 2026-09-18)

- **`PostgresLlmProfileRepository` ist der zweite Adapter des Ports**, PR 4 aus [`docs/plans/supabase.md`](docs/plans/supabase.md) §10 und die erste echte Datenmigration des Plans. `AGORA_LLM_PROFILE_BACKEND=postgres` ist damit ein Wert, der etwas tut — der Default bleibt `sqlite`.
- **Die ID-Darstellung bleibt die der SQLite.** Der bisherige Store erzeugt IDs als `uuid4().hex` (32 Zeichen), die Spalte in PostgreSQL ist ein `UUID` (36 Zeichen mit Bindestrichen) — dieselbe Zahl, andere Schreibweise. Der Adapter reicht nach außen immer `.hex`. Ohne das bekäme dieselbe Zeile nach der Migration eine andere ID, und jede gespeicherte Referenz der Form `llm_model: "profile:<id>"` in einer Simulationskonfiguration zeigte ins Leere.
- **Der Schlüssel liegt nicht in der Tabelle.** `agora.llm_profiles` hat keine `api_key`-Spalte; der Adapter holt ihn aus dem Fernet-Store, den PR #1516 eingeführt hat, unter derselben Profil-ID. Zwei Profile desselben Providers behalten damit verschiedene Schlüssel — verifiziert gegen eine echte Datenbank, nicht nur behauptet.
- **`scripts/migrate_llm_profiles_to_postgres.py` überträgt den Bestand** und lässt die SQLite unberührt (`mode=ro`, §10 Schritt 9). `--dry-run` zählt, `--verify` vergleicht feldweise: Anzahl, IDs, alle Felder, beide Zeitstempel und die Schlüssel über den **entschlüsselten Klartext** — eine Existenzprüfung würde einen Eintrag durchgehen lassen, der unter der falschen ID liegt. Verwaiste Zeilen in PostgreSQL werden benannt. Der Lauf ist wiederholbar: ein zweiter Durchgang aktualisiert, statt an der Primärschlüssel-Kollision zu scheitern.
- **`list()` legt in PostgreSQL kein Bootstrap-Profil an**, anders als der SQLite-Adapter. Das Bootstrap ist Erstinbetriebnahme einer leeren Installation; wer auf PostgreSQL umschaltet, hat seinen Bestand migriert und bekäme sonst ein zusätzliches Profil, das niemand angelegt hat.
- **Ablauf, Rückweg und Grenzen stehen in [`docs/runbooks/llm-profile-postgres-umstellung.md`](docs/runbooks/llm-profile-postgres-umstellung.md).** Dort auch der Satz, der am leichtesten übersehen wird: der Rückweg auf `sqlite` ist sofort wirksam, verliert aber jedes Profil, das nach der Umstellung angelegt wurde — er gilt für den Tag der Umstellung, nicht für den Monat danach.

### Changed

- `LLM_PROFILE_BACKENDS_NOT_YET_AVAILABLE` ist leer. Die Mechanik bleibt stehen, weil der nächste Store denselben Zwischenzustand durchläuft: Wert schon gültig, Adapter noch nicht da.

### Added (die Profil-Schlüssel haben jetzt eine verschlüsselte Ablage — 2026-09-18)

- **`LlmProfileSecretsStore` legt API-Keys pro Profil verschlüsselt ab**, Fernet unter `AGORA_SECRET_KEY`, Datei `llm_profile_secrets.json` im `AGORA_DATA_DIR`. Vorarbeit für PR 4 aus [`docs/plans/supabase.md`](docs/plans/supabase.md) §10: das Ziel-Datenmodell `agora.llm_profiles` hat bewusst keine `api_key`-Spalte, also braucht der PostgreSQL-Adapter die Schlüssel woanders.
- **Warum nicht der bestehende Provider-Store.** Der legt **pro Provider** ab (`get_plaintext("openai")`). Profile sind feiner geschnitten: es gibt keinen Unique-Constraint auf `provider`, zwei Profile desselben Providers dürfen verschiedene Schlüssel tragen, und der Laufzeit-Resolver zieht den Schlüssel pro Profil. Hätte der PostgreSQL-Adapter auf den Provider-Store zurückgegriffen, teilten sich diese Profile stillschweigend einen Schlüssel — ein Verhaltenswechsel, der erst aufgefallen wäre, wenn das Feature-Flag längst umgelegt ist.
- **Ein nicht entschlüsselbarer Eintrag ist kein fehlender Eintrag.** `get_plaintext` gibt `None` zurück, wenn kein Schlüssel hinterlegt ist, wirft aber `ProfileSecretDecryptionError`, wenn einer existiert und der Master-Key nicht passt. Ohne diese Trennung liefe ein Profil nach einer Key-Rotation stillschweigend ohne Authentifizierung weiter.
- **Ein leerer Wert löscht den Eintrag**, statt einen verschlüsselten Leerstring abzulegen — dieselbe Bedeutung, die ein leeres `api_key`-Feld in der SQLite hat. Ein solcher Eintrag würde vorgeben, einen Schlüssel zu haben.
- **`scripts/migrate_profile_secrets.py` füllt den Store aus der bestehenden SQLite** und **fasst sie dabei nicht an**: die Verbindung ist auf `mode=ro` gesetzt, kein Schlüssel wird dort gelöscht. Solange `AGORA_LLM_PROFILE_BACKEND=sqlite` gilt, bleibt die Datenbank die Wahrheit und der Store nur eine zweite Kopie. `--dry-run` zählt, ohne zu schreiben; `--verify` vergleicht beide Seiten **feldweise über den entschlüsselten Klartext** — eine reine Existenzprüfung würde einen Eintrag durchgehen lassen, der unter der falschen Profil-ID liegt oder aus einem früheren Lauf mit anderem Wert stammt — und benennt auch verwaiste Einträge, deren Profil verschwunden ist.

### Added (die LLM-Profile liegen jetzt hinter einem Port — 2026-09-18)

- **`LlmProfileRepository` ist der Port für LLM-Profil-Metadaten**, PR 3 aus [`docs/plans/supabase.md`](docs/plans/supabase.md) §38 und die erste Hälfte der Repository-Schicht aus §12. Der Port schreibt die Semantik des heutigen SQLite-Stores fest, damit der PostgreSQL-Adapter aus PR 4 sie nicht anders auslegt: `get()` gibt `None` zurück statt zu werfen (ein fehlendes Profil ist beim Auflösen einer Route ein erwarteter Fall), `api_key` verlässt das Repository nur mit `include_api_key=True`, und `list()` legt bei leerer Ablage das Bootstrap-Profil aus den `LLM_*`-Env-Variablen an — ohne das stünde eine frische Installation ohne jede Route da.
- **Der schwierigste Teil des Vertrags steht in `update()`.** Für `api_key` gilt eine Dreiteilung: `None` heißt „nicht mitgeschickt" und lässt den gespeicherten Schlüssel stehen, `""` heißt „ausdrücklich leeren", jeder andere Wert ersetzt ihn. Ohne diese Unterscheidung löschte jedes Speichern aus der Oberfläche den Schlüssel, denn die API gibt ihn nie aus und ein Formular schickt ihn leer zurück. Ein zweiter Adapter, der das übersieht, macht genau diesen Fehler wieder.
- **`AGORA_LLM_PROFILE_BACKEND` schaltet die Ablage, Default `sqlite`.** Bewusst getrennt von `AGORA_METADATA_BACKEND`: die Stores werden einzeln umgestellt, und ein Schalter für alles wäre genau die Migration in einem Schritt, die der Plan vermeidet.
- **`postgres` ist ein gültiger Wert ohne Adapter, und das sagt die Anwendung auch so.** `Config.validate()` lehnt ihn beim Start ab mit dem Hinweis, dass der Adapter mit PR 4 kommt und bestehende Profile bleiben, wo sie sind — nicht mit einem Importfehler beim ersten Profilzugriff. Die Factory wirft dieselbe Aussage als `LlmProfileBackendUnavailable`, falls jemand sie ohne Validierung erreicht; kein `ValueError`, weil der Wert nicht falsch ist, sondern noch nicht bedient. Die Verzweigung hängt an einer Konstanten, die mit PR 4 leer wird und die Verzweigung mitnimmt.

### Changed

- **`LlmProfilesStore` heißt jetzt `SqliteLlmProfileRepository`** und sagt damit, was es ist: der SQLite-Adapter des Ports. Der alte Name bleibt als Alias — er steht in vier Consumern und sechs Testdateien, und ein Rename dort verbessert nichts, was der Port nicht schon leistet. **Das Datenformat ändert sich nicht**: eine bestehende `instance/llm_profiles.db` wird unverändert weiterbenutzt, es gibt keine Migration und nichts zu sichern.

### Added (ein Maßstab dafür, dass eine Migration nichts verloren hat — 2026-09-18)

- **`backend/scripts/migration_baseline.py` erzeugt ein Baseline-Manifest**, Phase 0 aus [`docs/plans/supabase.md`](docs/plans/supabase.md) §6. Es wird zweimal gefahren — vor und nach einer Migrationsphase — und `--compare` hält beide gegeneinander: Anzahl, IDs, Zeitstempel, Statuswerte, Referenzen und eine sha256 je Artefaktdatei. „Die Migration lief sauber durch" ist keine Aussage, gegen die sich etwas prüfen lässt; „620 Runs vorher, 620 nachher, alle IDs identisch" ist es.
- **Drei Fragen, drei Werkzeuge.** `restore-drill.sh` sichert, `restore_verify.py` prüft ob eine Wiederherstellung funktioniert, `migration_baseline.py` prüft ob eine Migration etwas verloren hat. Keines ersetzt ein anderes, und das neue Runbook [`docs/runbooks/migration-baseline.md`](docs/runbooks/migration-baseline.md) sagt das als Erstes.
- **Ungeprüft ist kein Erfolg.** Eine nicht erreichbare Quelle — fehlendes Verzeichnis, nicht lesbare `llm_profiles.db`, abwesendes Neo4j — wird als `unchecked` geführt, nie als `count = 0`. Der Vergleich endet dann mit Exit 2 statt grün. Dieselbe Regel, die `restore_verify.py` schon für übersprungene Prüfpunkte führt: ein blinder Fleck ist kein Nachweis.
- **Das Manifest ist zum Weitergeben gedacht.** Keine Dateiinhalte, keine Geheimnisse. Die Spalte `api_key` aus `instance/llm_profiles.db` wird nicht gelesen — sie steht dort im Klartext —, `base_url` ebenso wenig, weil eine Basis-URL ein Token tragen kann.

### Fixed (der Restore-Drill konnte den Rechner überschreiben, auf dem er lief — 2026-09-18)

- **`--phase restore` verweigert jetzt Ziele im eigenen Checkout.** Die Vorgaben für `--data-dir`, `--store-dir` und `--instance-dir` zeigen auf `backend/uploads`, `backend/data` und `backend/instance`. Fürs Backup ist das richtig — gesichert wird die laufende Installation. Für den Restore war es die teuerste Zeile im Skript: ein Aufruf ohne explizite Pfade überschrieb genau diese drei Verzeichnisse, inklusive Fernet-Stores und LLM-Profilen. Das Runbook sagte „auf einem frischen Host"; ein Satz in einer Markdown-Datei hält niemanden auf. `--allow-repo-target` hebt die Sperre dort auf, wo der Checkout tatsächlich das Ziel ist.
- **`llm_profiles.db` wird vor dem Archivieren gecheckpointet.** Die Datenbank läuft mit `journal_mode=WAL` und besteht zur Laufzeit aus `.db`, `.db-wal` und `.db-shm`; ein reines `tar` fror den Zwischenstand ein, in dem die letzten Schreibvorgänge noch im WAL standen. Fehlt `sqlite3` auf dem Host, steht eine Warnung im Protokoll statt stiller Inkonsistenz.
- **Backup-Verzeichnis und Archive entstehen mit `0700` beziehungsweise `0600`.** Vorher erbten sie den Prozess-Umask, auf den meisten Hosts 022 — world-readable, obwohl die Archive `backend/data` mit den Fernet-Stores und `llm_profiles.db` mit der `api_key`-Spalte im Klartext tragen.
- **Jeder Lauf schreibt ein frisches `MANIFEST.sha256`**, und der Restore prüft jedes Archiv dagegen, bevor er entpackt. Ein durch volle Platte abgebrochenes `tar` lief vorher beim Backup grün durch und fiel erst beim Restore auf — oder nie. Ein Archiv ohne Manifesteintrag wird entpackt, aber als ungeprüft protokolliert.
- **Protokollzeilen und Befehlsausgaben laufen durch einen Redaktionsfilter** für `Authorization`-Header und `token`/`secret`/`password`/`api_key`. Heute nimmt kein verdrahteter Befehl ein Geheimnis entgegen; der vom Runbook selbst nahegelegte Health-Check mit Bearer-Token wäre per Copy-Paste sofort einer.
- **Die Tests setzten selbst nur `--data-dir`** und liefen für die beiden anderen Pfade in den Checkout — genau der Halbfehler, den der neue Schutz abfängt. Acht Regressionstests decken Zielschutz, Manifest, Dateirechte, beschädigte Archive und Redaktion ab.

### Added (die erste Fachtabelle existiert, und niemand liest sie — 2026-09-18)

- **`agora.llm_profiles` ist das erste fachliche PostgreSQL-Modell**, Phase 3 aus [`docs/plans/supabase.md`](docs/plans/supabase.md) §9 — und zwar nur die Definition. Ein SQLAlchemy-Modell (`LlmProfileModel`) und eine Alembic-Revision legen die Tabelle an; kein Store, kein Repository und kein Endpunkt zeigt darauf. Solange `AGORA_METADATA_BACKEND=legacy` gilt, entsteht keine Verbindung und die Tabelle bleibt leer. Der Umstieg ist Phase 4 und ein eigener Schritt.
- **Die Tabelle trägt Metadaten, keine Geheimnisse.** Name, Provider, Basis-URL, Modellname, ein Default-Flag, zwei Zeitstempel. API-Keys und Provider-Secrets bleiben im Fernet-Store (§10): eine Kopie in Postgres wäre eine zweite Stelle, an der ein Schlüssel im Klartext liegen kann, und der Betreiber müsste zwei Ablagen rotieren statt einer.
- **Workspace- und Auth-Spalten sind nicht vorgezogen.** Agora ist Single-User, und eine `workspace_id`, die niemand füllt, ist entweder nullable und damit wertlos oder sie zwingt beim Multi-User-Schritt zu einer Backfill-Migration auf Platzhalterdaten. Sie kommt, wenn Phase 6 sie braucht.
- **Höchstens ein Default-Profil, und das erzwingt die Datenbank.** `uq_llm_profiles_single_default` ist ein partieller Unique-Index über `is_default WHERE is_default` — Anwendungscode, der zwei Profile als Default markieren will, scheitert am Constraint statt an einer Prüfung, die ein zweiter Aufrufer umgehen kann. Dazu vier `CHECK`-Constraints gegen leere Zeichenketten und einen Namen über 80 Zeichen.
- **`target_metadata` in `migrations/env.py` zeigt jetzt auf die gemeinsame Declarative Base.** Alembic und Anwendungscode arbeiten damit gegen dieselbe Modelldefinition, statt dass ein handgeschriebenes DDL und ein ORM-Modell auseinanderlaufen. Die Regel bleibt unverändert: Tabellen werden ausschließlich über versionierte Migrationen geändert, `--autogenerate` schreibt einen Vorschlag, keinen Commit.
- **`include_name` beschränkt die Reflexion auf `agora`.** Ohne diesen Filter sieht Autogenerate auch `public`, `auth` und `storage` — die Schemata, die Supabase selbst mitbringt — und schlägt vor, sie zu löschen, weil kein Modell sie beschreibt. Ein einziges unbesehen übernommenes Autogenerate-Ergebnis hätte gereicht.
- **Getestet wird gegen echtes PostgreSQL, nicht gegen SQLite.** Partielle Indizes, `CHECK`-Constraints und schema-qualifizierte Tabellen sind genau die Dinge, bei denen ein SQLite-Ersatz grün meldet und Postgres danach etwas anderes tut. Die Integrationstests fahren `upgrade` und `downgrade` gegen eine laufende Instanz und überspringen sich, wenn keine erreichbar ist.

### Added (Agora kann PostgreSQL sprechen, tut es aber nicht — 2026-09-17)

- **`sqlalchemy`, `psycopg[binary]` und `alembic` sind jetzt Abhängigkeiten, und der Laufzeitpfad merkt davon nichts.** Das ist Phase 2 aus [`docs/plans/supabase.md`](docs/plans/supabase.md) §8: die Grundlage steht, bevor irgendein Store sie benutzt. `AGORA_METADATA_BACKEND=legacy` ist der Default, und solange er gilt, entsteht keine einzige Datenbankverbindung. Dateisystem und Neo4j bleiben die Wahrheit.
- **Die Deps stehen fest in `dependencies`, nicht in einem Extra.** Ein optionaler Block bedeutet, dass der Import-Pfad in einer Installation fehlen kann — und daran scheitern Migrationen dann erst auf dem Zielsystem. `psycopg[binary]` statt `psycopg2`: psycopg 3 ist der gepflegte Treiber, SQLAlchemy spricht ihn über das Dialekt-Präfix `postgresql+psycopg`, und der `binary`-Extra bringt libpq als Wheel mit, statt auf jedem Build-Host `pg_config` zu verlangen.
- **`app/infrastructure/postgres/` ist der einzige Weg zu einer Verbindung.** `Database.session()` ist ein Kontextmanager mit Transaktionsgrenze: Commit bei sauberem Austritt, Rollback bei jeder Exception, und die Exception wird weitergereicht — ein fehlgeschlagener Schreibvorgang ist ein Fehler, keine leere Antwort. Engine und Session-Factory entstehen beim ersten Zugriff, nicht im Konstruktor, damit ein ungenutzter Adapter nichts hält. Freie `psycopg.connect()`-Aufrufe quer durch Services sind ausdrücklich nicht vorgesehen; sie umgehen Pool, Konfiguration und Transaktionsgrenze.
- **`pool_pre_ping` ist gesetzt, aus derselben Erfahrung, die `NEO4J_LIVENESS_TIMEOUT` erzwungen hat:** im Docker-Bridge-Netz verschwinden Sockets, die im Pool liegen, ohne dass eine Seite es merkt. Ohne Pre-Ping bekommt der erste Zugriff nach einer Idle-Phase einen toten Socket statt einer Verbindung. `pool_recycle` liegt unter den Timeouts, die Supavisor auf einer Verbindung durchsetzt.
- **`DATABASE_URL` hat bewusst keinen Default.** Ein geratener `localhost`-Wert wäre genau der Legacy-Fallback, den die Architekturregel verbietet: er gäbe eine fehlende Konfiguration als funktionierende aus und zeigte im Containerpfad auf den Container selbst. `Config.validate()` lehnt stattdessen drei Fälle beim Start ab statt beim ersten Zugriff — `AGORA_METADATA_BACKEND=postgres` ohne URL, ein unbekannter Backend-Wert (ein Tippfehler darf nicht still auf `legacy` zurückfallen, das sähe im Log aus wie eine Entscheidung), und ein blankes `postgresql://`, das in SQLAlchemy psycopg2 wählt und damit ein nicht installiertes Paket.
- **Ab jetzt gilt: das Datenbankschema wird ausschließlich über versionierte Migrationen geändert.** Alembic liegt unter `backend/migrations/`, liest die Verbindung aus `DATABASE_URL` statt aus `alembic.ini` — eine Zeichenkette mit Passwort gehört nicht in eine versionierte Datei — und trägt eine erste Migration, die das Fachschema `agora` anlegt. Ohne `IF NOT EXISTS`, mit Absicht: existiert das Schema schon, hat es jemand von Hand angelegt, und dann soll die Migration scheitern statt so zu tun, als hätte sie es getan. `alembic_version` bleibt in `public`, weil es sonst in dem Schema liegen müsste, das die erste Migration erst erzeugt.
- **`public` bleibt leer.** Es ist das Schema, das PostgREST über die Supabase-API nach außen reicht; Fachtabellen gehören nicht versehentlich dorthin (§9).
- **Eine offene Frage ist benannt, nicht gelöst:** psycopg 3 ist im Synchronmodus nicht gevent-kooperativ, und der Webprozess läuft unter einem gunicorn-Worker mit gevent-Worker-Klasse — eine laufende Query blockiert den Hub und damit jeden anderen Greenlet. Für kurze Metadaten-Abfragen ist das tragbar, für lange Scans nicht. Solange der Default `legacy` gilt, entsteht keine Verbindung; bevor in Phase 4 der erste Store umgestellt wird, gehört die Frage beantwortet. Der Hinweis steht im Modul, nicht nur hier.
- **Die prod-Stage im `Dockerfile` kopiert jetzt `backend/migrations` mit.** Sie kopiert selektiv (`backend/app`, `backend/scripts`, …) statt `COPY . .` wie die dev-Stage — das Verzeichnis fehlte, und `alembic upgrade head` wäre im Produktionscontainer schlicht nicht ausführbar gewesen. Aufgefallen wäre das erst, wenn ein Zielsystem die erste Migration braucht. Ein Test hält die COPY-Zeile jetzt fest, statt einen Docker-Build dafür zu bezahlen.
- **Das Komplexitäts-Gate hat mitgeredet.** Die neue Validierung hätte `Config.validate()` über seine Allowlist-Grenze gehoben (rank D, cc 26 gegen erlaubte 21). Statt die Grenze anzuheben liegt die Prüfung als Modulfunktion `validate_database_settings()` daneben; `validate()` bleibt bei 21, und die Allowlist bleibt unverändert.

### Added (Self-hosted Supabase steht als eigenes Compose-Projekt bereit, ohne dass Agora es benutzt — 2026-09-17)

- **`supabase/` ist ein zweites Compose-Projekt, kein Anbau an den Agora-Stack.** Enthalten sind PostgreSQL 17, Supavisor, GoTrue, PostgREST, Storage, postgres-meta, Studio und ein Envoy-Gateway. Realtime, Edge Runtime, imgproxy und Analytics/Logflare laufen bewusst nicht mit — je weniger Container am Anfang, desto weniger bewegliche Teile. Sichtbare Folgen: `/realtime/v1` und `/functions/v1` antworten am Gateway mit 503, Storage läuft ohne Bildtransformation, die Log-Ansichten in Studio bleiben leer. Das ist Phase 1 aus [`docs/plans/supabase.md`](docs/plans/supabase.md) §7, der mit diesem Commit ebenfalls ins Repository kommt.
- **Im Backend ändert sich nichts.** Kein PostgreSQL-Code, keine neue Abhängigkeit, kein Feature-Flag, keine Auth-Änderung. `AGORA_AUTH_TOKEN` und das API-Key-Scope-Modell bleiben die Auth-Wahrheit; GoTrue läuft mit `DISABLE_SIGNUP=true` mit und wird von nichts aufgerufen. Die SQLAlchemy-/Alembic-Grundlage ist Phase 2 (§8), das Datenmodell Phase 3 (§9).
- **Die Netzkopplung ist ein Overlay, nicht die Basis-Compose.** `deploy/compose/docker-compose.supabase.yml` hängt den Agora-Container zusätzlich an das externe Netz `agora-backend`. Der Grund ist unspektakulär und entscheidend: ein `external: true`-Netz muss vor `docker compose up` existieren, und in `docker-compose.yml` eingetragen hätte es jeden bestehenden Stack gebrochen, bei dem `docker network create agora-backend` nicht gelaufen ist — genau gegen das Abnahmekriterium von Phase 1, „Agora funktioniert weiterhin komplett ohne neue Supabase-Funktion". Das Overlay nennt `default` und `agora-backend` beide explizit, weil eine explizite `networks`-Liste die implizite Default-Zuordnung ersetzt und Agora sonst Redis und Neo4j verlöre. Redis und Neo4j bleiben außerhalb von `agora-backend`: Supabase kommt an Graph und Event-Bus nicht heran.
- **Die Supabase-Konfigurationsdateien liegen nicht im Repository.** DB-Init-SQL, Envoy-Routing und `pooler.exs` sind zusammen rund 1500 Zeilen fremder Konfiguration aus supabase/supabase (Apache-2.0); vendored müssten sie bei jedem Supabase-Update nachgezogen und reviewt werden. Stattdessen holt `supabase/bootstrap.sh` sie per sparse-checkout von einem gepinnten Commit nach `supabase/volumes/` (gitignored), prüft jede erwartete Datei und bricht sonst mit Verweis auf `SUPABASE_REF` ab. Der Preis steht als Schritt 1 im README: ohne Bootstrap-Lauf startet der Stack nicht. `SUPABASE_REF` und die Image-Tags in `.env.example` werden gemeinsam angehoben.
- **Der Bootstrap muss vor dem ersten `docker compose up` laufen, und das Skript weiß das.** Andersherum legt Docker für jeden fehlenden Bind-Mount ein leeres *Verzeichnis* an Stelle der Datei an (`volumes/db/roles.sql/` statt `roles.sql`); Postgres initialisiert dann ohne Rollen, sichtbar erst später daran, dass `auth`, `rest` und `storage` sich nicht anmelden können. `bootstrap.sh` erkennt an einem fehlenden `volumes/.supabase-ref`, dass das Verzeichnis nicht von ihm stammt, ersetzt es und weist auf das nötige `docker compose down -v` hin — eine reine Existenzprüfung hätte die Reparatur genau dann verweigert, wenn sie gebraucht wird.
- **Nicht öffentlich exponiert.** Alle Host-Ports binden auf `127.0.0.1`; das offizielle Supabase-Compose exponiert die Supavisor-Ports ohne Bind-Adresse, hier tun sie es nicht. Nach außen geht ausschließlich das Gateway über den Reverse Proxy, Studio nur intern bzw. über VPN und dahinter mit Basic Auth. `supabase/.env.example` trägt kein einziges Secret: alle Secret-Felder sind leer, die Werte kommen aus Vaultwarden.
- **Nebenbefund für den Plan:** das Supabase-Gateway ist inzwischen Envoy, nicht mehr Kong. Die Zielarchitektur-Skizze im Plan nennt noch „Kong :8000". Das Compose exponiert die Netzwerk-Aliase `envoy` und `kong`, alte Hostnamen lösen also weiter auf.

### Fixed (Prepare-Wire-Validierung: Nicht-String-Felder enden nicht mehr als HTTP 500 — CodeRabbit-Finding PR #1497)

- **`PrepareRequest` ist jetzt ein vollständiger Pydantic-Contract** statt einer frozen Dataclass. Die Wire-Validierung bleibt feldweise in den Parse-Phasen (bewusste Architektur-Entscheidung des Modul-Splits), aber der Container erzwingt jetzt selbst Typen und White-Striping (`str_strip_whitespace`), statt sich auf die Disziplin der Caller zu verlassen.
- **Nicht-String-Wire-Felder crashten mit `AttributeError` → HTTP 500.** `(data.get('language') or '').strip()` in `_collect_prepare_inputs` und dieselbe Konstruktion für `llm_model`/`llm_profile_id`/`llm_project_profile` in `_read_client_choice` warfen bei `{"language": 5}` oder `{"llm_model": 123}` einen 500er, während ein ungültiges `max_agents` sauber zu `None` fällt. Die neue Hilfsfunktion `_coerce_optional_str` in `simulation_prepare_contracts.py` erzwingt an allen vier Stellen dieselbe None-Semantik: Client-Fehler im Wire-Format zählen als nicht gesetzt, statt den Handler zu sprengen.
- **`AiModelRef`/`RunBudgetConfig` sind Laufzeit-Importe** statt TYPE_CHECKING-only — Pydantic braucht die Forward-Referenzen zur Modelldefinition; die funktionslokalen Lazy-Importe in `_parse_prepare_identity`/`_parse_prepare_budget` entfallen damit.
- **Regressionstests** in `tests/api/test_simulation_prepare_phases.py`: `test_collect_prepare_inputs_tolerates_non_string_language` und `test_read_client_choice_tolerates_non_string_fields` pinnen die None-Semantik für Nicht-String-Input fest.
- **Docstring-Lücken geschlossen** (`_prepare_start_lock`, `_track_active_prepare_job`, `_discard_active_prepare_job`), die der Coverage-Check des PR bemängelt hatte.

### Changed (Simulations-Read-Metriken aus Monitor-Orchestrierung extrahiert — 2026-09-11)

- `get_timeline` und `get_agent_stats` aggregieren persistierte Agentenaktionen jetzt in `backend/app/services/sim/run_metrics.py`.
- `backend/app/services/sim/monitor.py` behaelt duenne kompatible Wrapper und den bestehenden `_get_actions`-Monkeypatch-Hook; Prozessueberwachung, Cancellation und Manifest-Finalisierung bleiben unveraendert im Monitor-Modul.
- Der veraltete Radon-Allowlist-Eintrag fuer die bereits extrahierte Run-Summary wurde entfernt; der Frontend-Kommentar zur Run-Summary-SSoT zeigt auf `services/run_read_model.py`.

### Changed (Run-Read-Model aus API-God-Controller extrahiert — 2026-09-11)

- Die rein lesende Summary-Anreicherung fuer Run-Listen und Run-Details liegt jetzt in `backend/app/services/run_read_model.py` statt in `backend/app/api/runs.py`.
- HTTP-Contracts, Feldnamen, Caching-Verhalten und Best-Effort-Fehlerbehandlung bleiben unveraendert; Resume-, Routing-, Budget- und Lifecycle-Pfade wurden nicht angefasst.
- Hintergrund ist das repository-weite LOC-/Struktur-Audit unter `docs/refactor/loc-audit.md`; `runs.py` war mit 1419 Zeilen der deutlichste God-Controller-Kandidat.

### Fixed (Ein Setting, ein Default — `LLM_MODEL_NAME` war auf drei Flächen zweierlei — Phase 7 des Remediation Plans)

- **`LLM_MODEL_NAME` hatte zwei verschiedene Code-Defaults.** `app/config.py` und `SETTINGS_FIELDS` führten bewusst den leeren String, `AgoraSettings` dagegen `"qwen2.5:32b"` — obwohl deren eigene Docstring behauptet, `config.py` „1:1" zu spiegeln. Der leere Default ist der gewollte: ein vorbelegtes lokales Ollama-Tag führte in Cloud-Setups (Ollama Cloud / OpenAI / Gemini) zu 404, weil das Auto-Bootstrap-Profil auf ein Modell zeigte, das im aktiven Backend nicht existiert. Genau diese Begründung steht seit dem damaligen Fix in `config.py`; `AgoraSettings` wurde nicht mitgezogen.
- **`backend/tests/test_settings.py` hat den falschen Wert festgeschrieben** (`assert s.llm_model_name == "qwen2.5:32b"`) und damit den Drift gegen Korrektur verteidigt, statt ihn zu melden. Korrigiert samt Begründung im Docstring.
- **Neues Drift-Gate `backend/tests/test_settings_default_drift.py`.** Es vergleicht die **deklarierten** Defaults von `AgoraSettings` und `SETTINGS_FIELDS` feldweise über den Env-Alias — nie aufgelöste Werte, weil `Config` seine Klassenattribute beim Import aus `os.environ` (inklusive `.env`) belegt und damit kein Default-Anker ist. `Config` hängt transitiv über die Literalliste in `test_settings_layer.py` mit drin. Der bestehende Pin-Test deckte nur `SETTINGS_FIELDS` ab — deshalb konnte der Drift überhaupt entstehen.
- **Secrets werden im Gate explizit behandelt, nicht stillschweigend übersprungen.** `LLM_API_KEY` und `AGORA_AUTH_TOKEN` modellieren „nicht gesetzt" unterschiedlich (`''` im Settings-Layer, `None` als `SecretStr | None`). Das ist eine Typ-, keine Wertaussage; das Gate fordert für Secret-Felder stattdessen, dass *keine* Fläche einen vorbelegten Wert trägt.
- **Ein Test, der nichts mehr vergleicht, fällt jetzt auf.** `test_surfaces_actually_overlap` sichert ab, dass die Parametrisierung überhaupt Paare findet — ein Alias-Refactor würde den Drift-Test sonst still grün und wertlos machen.
- **`.env.example` setzte `LLM_MODEL_NAME=qwen2.5:32b` aktiv** und stellte damit bei `cp .env.example .env` genau den Zustand wieder her, den der leere Code-Default vermeidet — im Widerspruch zur eigenen Dateikonvention („Aktive Defaults sind bewusst auskommentiert"). Die Zeile ist jetzt ein kommentiertes Beispiel; `Vertrag D` in `backend/tests/config/test_env_examples_consistency.py` hält das fest.
- **Kein vierter Runtime-Default:** Das `qwen2.5:32b` in `app/api/settings.py` steht nur im Docstring-Beispiel der GET-Antwort — der reale Wert kommt aus dem Settings-Layer. Das Beispiel war trotzdem irreführend und zeigt jetzt `"default": ""`.

### Fixed (E2E-Stack bringt seinen Modellnamen selbst mit)

- **Sechs der sieben Playwright-Smokes fielen, nachdem `.env.example` den aktiven `LLM_MODEL_NAME` verloren hatte.** `scripts/e2e-up.sh` seedet die `.env` des CI-Stacks aus `.env.example`; ohne Modellnamen gibt `_bootstrap_profile()` in `llm_profiles_store.py` `None` zurück, es entsteht kein Auto-LLM-Profil, und jeder Smoke, der einen Run startet oder ein Modell auswählt, scheitert. Der Health-Smoke blieb als einziger grün — er prüft nur Endpunkte und braucht kein Modell. Genau dieses Muster (ein grüner, sechs rote Jobs) war der Hinweis auf die Ursache.
- **Der Modellname gehört in den E2E-Seed, nicht in die Vorlage.** `.env.example` setzt bewusst keinen mehr: der Code-Default ist leer, damit ein Operator ein Modell wählt, das in seinem Backend wirklich existiert. `scripts/e2e-up.sh` pinnt ihn jetzt über denselben `_env_upsert`-Mechanismus, mit dem der Stack auch `AGORA_PROXY_PORT` und `AGORA_E2E_LLM_MODE` deterministisch festlegt. Im Stub-Modus wird der Wert nie wirklich aufgerufen.
- **Regression:** `backend/tests/config/test_env_examples_consistency.py` bekommt Vertrag E. `test_contracts_d_and_e_stay_coupled` hätte den Fehler gefangen: es fordert, dass **genau eine** der beiden Quellen den Modellnamen liefert — nie keine. Beide Tests sind ohne den Fix rot (verifiziert).

### Fixed (AiModelPicker-Smoke hängt nicht mehr an einer DNS-Auflösung)

- **Der AiModelPicker-Smoke fiel, nachdem der `dns:`-Default aus dem ausgelieferten Compose-Stack entfernt wurde** — als einziger der sieben Playwright-Jobs. Die Playwright-Trace zu Lauf `34600171007` zeigt warum: `openai_compatible` meldet `status: "connected"` und der Modell-Endpunkt liefert beide Modelle mit HTTP 200. Das Backend war gesund. Hängen blieben stattdessen sechs Requests auf `/api/llm/provider-connections/**openai**/models` mit HAR-Status `-1` — der *absichtlich unerreichbaren* Verbindung.
- **Entscheidend ist nicht, dass der Name scheitert, sondern wie schnell.** Der Smoke seedet `mock-models-unreachable:8080`, um den Offline-Fall zu prüfen. Mit festem Resolver kommt NXDOMAIN sofort, die Verbindung geht auf `disconnected`, und die Combobox rendert. Ohne festen Resolver läuft die Abfrage unter der Egress-Sperre des CI-Runners in einen Timeout; die Modell-Requests bleiben offen und der Picker rendert nie seine Optionen.
- **Compose-Servicenamen waren nie betroffen.** `neo4j`, `redis` und `mock-models` beantwortet Dockers eingebettetes DNS lokal — deshalb liefen die anderen sechs Smokes durch, und deshalb war die naheliegende Vermutung „Compose-DNS kaputt" falsch. Nur externe Namen brauchen den Upstream.
- **Der Resolver ist jetzt im E2E-Override gepinnt, nicht im ausgelieferten Stack.** Der Default erbt weiterhin den Host-Resolver, damit Split-DNS (Tailscale MagicDNS, Homelab-Zonen) funktioniert und keine Namensauflösung ungefragt an Dritte geht. Der E2E-Stack legt seine Konfiguration wie gehabt selbst fest — dasselbe Muster wie bei `AGORA_PROXY_PORT`, `AGORA_E2E_LLM_MODE` und `LLM_MODEL_NAME`.
- **Regression:** `test_e2e_override_pins_a_resolver` und `test_shipped_stack_and_e2e_override_stay_coupled` in `backend/tests/test_compose_defaults.py`; beide ohne den Pin rot (verifiziert).

### Changed (Der Container erbt wieder den DNS des Hosts — Phase 12 des Remediation Plans)

- **`docker-compose.yml` hat dem `agora`-Service hart `8.8.8.8`/`8.8.4.4` als Resolver gesetzt.** Für ein local-first-System ist das der falsche Default gleich zweifach: jede Namensauflösung des Containers ging ungefragt an einen Dritten, und Split-DNS-Setups waren schlicht kaputt — Tailscale-MagicDNS-Namen, Homelab-Zonen und interne Firmen-Domains sind über einen öffentlichen Resolver nicht auflösbar. Ein lokaler LLM-Endpunkt hinter einem solchen Namen war damit aus dem Container nicht erreichbar.
- **Der `dns:`-Block ist entfernt.** Der Container erbt jetzt den Resolver der Docker-Engine und damit den des Hosts, was für Homelab-, Tailnet- und Firmennetze der einzige Default ist, der ohne Vorwissen funktioniert.
- **Wer externe Resolver braucht, hängt `deploy/compose/docker-compose.external-dns.yml` an.** Dort sind `AGORA_DNS_PRIMARY` und `AGORA_DNS_SECONDARY` bewusst als Pflichtvariablen deklariert (`${VAR:?…}`, nicht `${VAR:-default}`): ein stiller Fallback würde exakt den Zustand wiederherstellen, den dieser Fix entfernt.
- **Regression:** `backend/tests/test_compose_defaults.py` parst die Compose-Dateien direkt statt über `docker compose config` — die Invariante gilt damit auch auf Testhosts ohne Docker-Engine. Gegen den Vor-Fix-Stand sind zwei der fünf Tests rot (verifiziert).
- **Doku nachgezogen:** `.env.example`, `docs/security-hardening.md` und `docs/deployment.md` beschrieben die Variablen bisher als wirksame Defaults; sie sind jetzt als „nur mit Override wirksam" gekennzeichnet.

### Security (Der Standard-Stack mountet keine persönlichen ChatGPT-Credentials mehr — Phase 5 des Remediation Plans)

- **`docker-compose.yml` hat `${CODEX_HOME:-${HOME}/.codex}` read/write in den Agora-Container gemountet — bedingungslos.** Damit hatte der Backend-Prozess Lese- *und* Schreibzugriff auf die persönliche ChatGPT-Session inklusive Refresh-Token, unabhängig davon, ob der `codex_cli`-Provider überhaupt benutzt wird. Ein optionaler Provider hat eine nicht-optionale Credential-Exposition erzeugt; bei einem kompromittierten Backend-Prozess wäre das Abo-Token direkt abgreifbar und überschreibbar gewesen.
- **Der Mount ist aus dem Default-Stack entfernt und liegt jetzt in `deploy/compose/docker-compose.codex-cli.yml`.** Dort ist `AGORA_CODEX_HOME` eine Pflichtvariable ohne Default: ein Fallback auf `~/.codex` würde genau die Vermischung wiederherstellen, die das Override auflöst. Eingerichtet wird mit `CODEX_HOME="$AGORA_CODEX_HOME" codex login` gegen ein Agora-eigenes Verzeichnis.
- **Die Provider-Probe unterscheidet jetzt Binary, Credential-Verzeichnis und Login.** Vorher galt „Binary im PATH" als `available`, und ein fehlender Login fiel erst im ersten echten Run als kryptischer Subprozessfehler auf. `codex_cli_readiness()` liefert stattdessen `missing` (kein Mount), `unreadable` (von Docker als root angelegt — der häufigste Praxisfall), `empty` (kein Login) oder `ok`; die ersten drei melden `invalid_credentials` mit konkreter Handlungsanweisung statt eines Erfolgsstatus.
- **Bewusst kein Test auf einen konkreten Dateinamen der CLI.** Deren internes Anmeldeformat ist nicht Teil unseres Vertrags und hat sich in der Vergangenheit geändert; ein hartkodierter Dateiname wäre beim nächsten CLI-Update still zu einem Falsch-Negativ geworden. Ein lesbares, nicht-leeres Verzeichnis gilt als angemeldet — die endgültige Wahrheit liefert der Aufruf selbst.
- **`docs/troubleshooting.md` behauptete, die Session sei „read-only eingebunden".** Das war schon vor dieser Änderung falsch — der Compose-Kommentar begründet ausdrücklich das Gegenteil, weil `codex exec` Session-State schreibt und ohne Schreibrecht mit `Read-only file system (os error 30)` abbricht. Korrigiert, zusammen mit einer Tabelle der drei neuen Fehlzustände.
- **Regression:** `backend/tests/test_compose_defaults.py` prüft gegen die geparsten Volume-Definitionen, dass weder Dev- noch Prod-Stack ein `.codex`-Verzeichnis oder irgendetwas aus `$HOME` einhängt, und dass das Override ohne stillen Default arbeitet. Gegen den Vor-Fix-Stand ist der Test rot (verifiziert). `backend/tests/llm/test_codex_cli_provider.py` deckt die vier Credential-Zustände ab, `tests/services/provider_connections/test_adapters.py` die Probe-Semantik.

### Fixed (Ausgeschriebene Zahlwörter werden prüfbar, Spannen nicht mehr als Punktwert gelesen — Rest von [#1492](https://github.com/arn0ld87/agora/issues/1492))

- **„sechs Qualifizierungsangebote" erzeugte keinen prüfbaren Fakt.** Beide Extraktionsmuster verlangten eine Ziffer, obwohl die deutsche Schreibkonvention Zahlen bis zwölf als Wort setzt. Die Angabe war für den Trust-Layer unsichtbar — weder belegbar noch widerlegbar. Der Wertausdruck akzeptiert jetzt `zwei` bis `zwölf` in beiden Mustern, groß wie klein geschrieben.
- **`ein`/`eine` bleibt bewusst ausgenommen.** Im Deutschen ist es weit öfter unbestimmter Artikel als Zahlwort. Mitgezählt entstünde aus „eine Lehrkraft berichtet von Zeitgewinn" der Fakt „1 Lehrkraft" — eine Mengenbehauptung, die der Satz gar nicht aufstellt, und damit eine vom Trust-Layer selbst erfundene Zahl. `null` fehlt aus dem Gegengrund: als Mengenangabe praktisch nie ausgeschrieben, als Wort dagegen häufig.
- **Dabei fiel ein zweiter, älterer Fehler auf: Zahlenspannen wurden als exakte Punktwerte gelesen.** Aus „sechs bis neun Stunden" entstand der Fakt `6 Stunden` mit `BoundKind.EXACT` — eine Genauigkeit, die der Satz nicht behauptet. Gegen eine Quelle mit derselben Spanne ergab das ein Fehlurteil; der bestehende Test `test_late_evidence_reaches_the_binder` (#1217) wurde davon rot. Der Fehler betraf auch die Ziffernform („6 bis 9 Stunden") und bestand damit schon vor dieser Änderung — sichtbar wurde er erst, als die Zahlwörter dazukamen.
- **Spannen erzeugen jetzt gar keinen Fakt.** Die Vergleichslogik kennt nur Punktwerte und Schranken (`EXACT`/`AT_LEAST`/`AT_MOST`); eine Spanne lässt sich darin nicht ehrlich abbilden. Kein Fakt ist die richtige Antwort — der Satz läuft dann über den Textpfad, statt eine erfundene Präzision zu prüfen. Erkannt werden `X bis Y`, `X to Y`, Gedankenstrich-Formen und `zwischen X und Y`.
- **Zwei Abgrenzungen, die den Fix sonst zerstört hätten:** `bis zu neun Stunden` ist eine Obergrenze (`AT_MOST`) und bleibt ein vollwertiger Fakt, kein Spannenende. Und ein bloßes `und` zwischen zwei Zahlen zählt auf — „120 Teilnehmende und 18 Lehrkräfte" sind zwei Fakten. Nur mit dem Marker `zwischen` gilt `und` als Spanne. Ohne diese Abgrenzung hätte die Spannenerkennung den Kernfall von #1492 selbst kaputtgemacht.
- **Das Prädikat einer Aufzählung steht im Satzkopf.** Seit die Faktengrenze den Ausschnitt beim Vorgänger abschneidet, blieben für die hinteren Glieder von „Der Pilot umfasst A, B und C" nur Bindewörter übrig, und die Prüfung meldete „Aussage zu kurz" statt eines Urteils. `_full_predicate` greift jetzt auf den Satzteil vor der **ersten** Zahl zurück — der trägt die Aussage für alle Glieder.
- **Regression:** 29 Tests in `backend/tests/regression/test_evidence_fact_boundaries.py`, davon neun neue für Zahlwörter, Artikelabgrenzung, Wortinneres („Entzweiung" enthält „zwei"), Spannen und die beiden Abgrenzungen. Volle Backend-Suite 6560 passed.

### Fixed (Belegte Seed-Aussagen tragen kein `[Beleg fehlt]` mehr — [#1492](https://github.com/arn0ld87/agora/issues/1492))

- **Sätze wurden entwertet, deren Zahlen wörtlich im Seed stehen.** In `report_6daa7796257e` trug „120 Teilnehmende, 18 Lehrkräfte und sechs Qualifizierungsangebote …" die Markierung `[Beleg fehlt]`. Für einen Bericht, dessen Kernversprechen Evidenzbindung ist, ist das ein Vertrauensschaden: Leser können belegte und unbelegte Aussagen nicht mehr unterscheiden.
- **Ursache war die Faktengrenze, nicht die Satzprüfung.** Die Prüfung läuft seit #1356 bereits pro numerischem Fakt — der Ausschnitt *je Fakt* endete aber weiterhin erst am Satzende. Für die 120 entstand damit das Prädikat „18 Lehrkräfte und sechs Qualifizierungsangebote"; keine einzelne Quelle konnte das decken. `_split_subject_predicate` zog diese Grenze für das *Subjekt* seit #1356; für den restlichen Ausschnitt fehlte sie. Jetzt gilt sie durchgängig: der Ausschnitt eines Fakts endet, wo der nächste beginnt, und beginnt, wo der vorige endet.
- **Der schwerere, bisher unbemerkte Teilbefund: Sätze wurden gelöscht, nicht nur markiert.** Die Evidenz „18 % … 44 % …" trug in ihrem 18-%-Fakt das Prädikat der 44 % mit. Gegen den 44-%-Fakt des Berichts ergab das „gleiche Aussage über dieselbe Gruppe, abweichender Zahlenwert" — `CONTRADICTED`. Ein Satz, der mit seiner Quelle **identisch** war, verschwand damit aus dem Bericht. Reproduziert und mit `test_identischer_prozentsatz_wird_nicht_als_widerspruch_geloescht` festgenagelt.
- **Gemischte Sätze verloren ihre Absolutzahlen vollständig.** Die Absolutzahl-Extraktion lief nur, wenn der Satz *keine* Prozentangabe enthielt (`if not any(f.raw == sentence.strip() …)`). „Von 120 Teilnehmenden lehnen 18 % der Lehrkräfte ab" erzeugte keinen Fakt für die 120 — sie war für den Trust-Layer schlicht nicht vorhanden und konnte weder belegt noch widerlegt werden. Beide Muster laufen jetzt über denselben Satz; überlappende Treffer gewinnt das Prozentmuster, damit aus „18 % der Lehrkräfte" nicht zusätzlich ein Absolutfakt „18 Lehrkräfte" entsteht.
- **Die Beanstandung benennt jetzt die konkrete Zahl.** `unverified_statements[].reason` lautet z. B. `»71 Schulleitungen«: numerischer Claim ohne passenden Zahlenbeleg — 1 der 2 Zahlenangaben des Satzes ist belegt`. Damit sind „teilweise belegt" und „gar kein Beleg" unterscheidbar, ohne dass Frontend oder Audit am Markerstring parsen müssen — so, wie der Contract es seit #1356 vorsieht. Der sichtbare Marker `[Beleg fehlt]` bleibt unverändert.
- **Gegenproben mitgeliefert, damit der Fix kein abgeschaltetes Gate ist:** erfundene Zahlen werden weiterhin markiert, und ein abweichender Wert derselben Kennzahl über dieselbe Gruppe bleibt ein `CONTRADICTED` mit Löschung.
- **Regression:** `backend/tests/regression/test_evidence_fact_boundaries.py`. Gegen den Vor-Fix-Stand sind fünf der Tests rot (verifiziert).
- **Bewusst offen geblieben** bleibt die **Gewinnung** der Evidence: zerlegt die Graph-Ingestion einen gebündelten Seed-Satz LLM-seitig zu einem Teilfakt, fehlen die übrigen Angaben im Pool. Dieser Fix repariert die Prüfseite deterministisch; Lösungsrichtung 1 des Issues (Rohsatz zusätzlich als Evidenz führen) bleibt eigene Arbeit.

### Security (Agent-`web_fetch` kann nicht mehr ins interne Netz zeigen — #1485)

- **`backend/scripts/agent_tools.py::web_fetch()` hat die vom Modell gelieferte URL ungeprüft an `requests.get(..., allow_redirects=True)` gereicht.** Kein Scheme-Check über `http`/`https` hinaus, keine Adressklassenprüfung, keine Redirect-Validierung, kein Größenlimit. Bei `ENABLE_AGENT_TOOLS=true` war der OASIS-Subprozess damit ein Confused Deputy für alles, was aus dem Container erreichbar ist — Loopback-APIs, RFC1918-Hosts, Tailnet-Peers und der Cloud-Metadata-Endpunkt inklusive. Der Default `false` hat die Lücke entschärft, aber nicht geschlossen.
- **Der gesamte Netzwerkteil liegt jetzt in `backend/app/security/outbound_http.py`.** `agent_tools.py` enthält keinen `requests`-Aufruf mehr; `app/services/web_tools.py::_is_public_url` delegiert an dasselbe Modul, statt eine zweite Kopie derselben Allow/Deny-Logik zu führen. Zwei Kopien laufen auseinander, und eine davon ist dann wieder die Lücke.
- **Vier Prüfschichten statt einer:** (1) URL-Form — nur `http`/`https`, keine Credentials in der URL, keine Docker-/Kubernetes-/`.internal`-Sondernamen; (2) Adressklassen — Loopback, RFC1918, CGNAT, Link-Local, Multicast, Reserved, Unspecified und Cloud-Metadata werden abgelehnt, inklusive IPv4-mapped IPv6 (`::ffff:127.0.0.1`) und 6to4, mit `is_global` als Catch-all; (3) Verbindungs-Pinning; (4) Redirect-Revalidierung.
- **Gegen DNS-Rebinding hilft nur Pinning, nicht ein zweiter Lookup.** Zwischen „Hostname prüfen“ und `requests.get(hostname)` liegt ein Fenster, in dem die Auflösung wechseln kann. Die Verbindung geht deshalb an die *geprüfte* IP; Host-Header, TLS-SNI und Zertifikatsprüfung bleiben am echten Hostnamen (`urllib3`-Pool mit `host=<ip>`, `assert_hostname` und `server_hostname`). TLS wird dadurch nicht abgeschwächt.
- **Löst ein Hostname auf mehrere Adressen auf und ist eine davon nicht öffentlich, fällt die gesamte URL durch.** Sonst ist eine Round-Robin-Antwort mit einem öffentlichen und einem privaten Eintrag ein Umgehungsweg.
- **Redirects werden manuell verfolgt.** Jeder Hop durchläuft die Schichten 1–3 erneut, relative `Location`-Header werden gegen den tatsächlich gemachten Hop aufgelöst. `allow_redirects=True` hätte eine öffentliche URL weiterhin direkt in die Metadata-Adresse springen lassen. Default-Limit: 3 Hops.
- **Fehlerstatus der Gegenstelle werden als solche gemeldet.** Ein 4xx/5xx bricht den Abruf ab, statt die HTML-Fehlerseite als Seiteninhalt zurückzugeben; `agent_tools.web_fetch` meldet dann `HTTP 404` statt `Blocked by outbound policy`. Beides in einen Topf zu werfen würde dem Modell ein Rechteproblem melden, wo „Seite existiert nicht" die Wahrheit ist.
- **Response-Bodies werden gestreamt und bei 1 MB gekappt** statt über ein vollständiges `resp.text` geladen; Content-Type-Allowlist (`text/html`, `text/plain`) greift vor dem Lesen des Bodies. Connect- und Read-Timeout sind getrennt (5 s / 10 s).
- **Ablehnungsgründe werden ohne URL-Userinfo geloggt.** Der Grund nennt die blockierende Adressklasse, nicht die vollständige URL mit möglichen Query-Secrets.
- **Bewusste Grenze:** Der gepinnte Pfad honoriert `HTTP(S)_PROXY` nicht — Pinning und ein selbst auflösender Proxy schließen sich aus. Wer zwingend über einen Egress-Proxy will, setzt diese Grenze auf Netzwerkebene. Das Repo konfiguriert an keiner Stelle einen Proxy für den Subprozess, der Wegfall betrifft also keine bestehende Konfiguration.
- **Der Pinning-Pfad wird ohne Mock getestet.** `TestPinnedPoolConstruction` baut Pool und Connection wirklich (netzfrei — `_new_conn()` erzeugt nur das Objekt) und prüft, dass die Verbindung an der geprüften IP hängt, während SNI und Zertifikatsprüfung am Hostnamen bleiben. Ohne diesen Test blieb ausgerechnet das sicherheitskritischste Stück in jedem Lauf unausgeführt.
- **Regression:** `backend/tests/scripts/test_agent_tools_web_fetch.py` schlägt gegen den Vor-Fix-Stand in 9 von 10 Fällen fehl (verifiziert) und lässt jeden direkten `requests`-Aufruf aus `web_fetch` hart auflaufen. `backend/tests/security/test_outbound_http.py` deckt die vier Schichten mit 45 Fällen ab, inklusive „öffentliche URL → Redirect auf Metadata-IP“ und „gemischte DNS-Antwort“. Der bestehende `backend/tests/test_ssrf_blocker.py` läuft unverändert gegen die zentrale Implementierung weiter.

### Dokumentation

- Synchronisiert die lebende Projekt-, Architektur-, Betriebs-, Auth-, Secret- und Release-Dokumentation mit dem aktuellen `0.9.5`-Stand.
- Entfernt veraltete 0.9.4-/Testzähler-Angaben und zu starke Reproduzierbarkeitsbehauptungen aus den READMEs; aktuelle Nachweise bleiben zentral in `docs/STATUS.md`.
- Trennt aktuelle Referenzen klar von historischen Audits, Worklogs und eingefrorenen Referenzläufen.

### Fixed

- **`install.sh` erzeugte im Host-Modus keine Pflicht-Secrets — trotz Aufruf
  von `ensure_secret` wäre der Fix wirkungslos geblieben.** `.env.example` Der Docker-Modus sichert dieselben beiden Master-Keys ab — er kannte sie zuvor gar nicht, weil `.env.docker.example` sie nie gefuehrt hat.
  enthält nicht-leere Platzhalter (`SECRET_KEY=change-me-use-token_urlsafe-32`,
  `NEO4J_PASSWORD=change-me`); der alte `ensure_secret`-Fruehausstieg
  (`grep -qE "^KEY=[^[:space:]]+"`) hielt einen Platzhalter für „gesetzt“ und
  griff nur im Docker-Modus, wo die Docker-Vorlage leere Werte nutzt.
  `ensure_secret` behandelt bekannte Platzhalter jetzt wie ungesetzt (Bash-Kopie
  der `SECRET_KEY_PLACEHOLDERS`/`NEO4J_PASSWORD_PLACEHOLDERS`-Frozensets aus
  `backend/app/config.py`, gegen Drift per Test abgesichert) und generiert im
  Host-Modus zusätzlich `AGORA_SECRET_KEY` und `AGORA_FERNET_KEY`.
- **`AGORA_SECRET_KEY`/`AGORA_FERNET_KEY` wären mit ungültigen Werten belegt
  worden.** Beide müssen gültige Fernet-Keys sein
  (`llm_provider_secrets_store.py`, `api_keys_persistence.py`); der bisherige
  Generator (`secrets.token_urlsafe(32)`) erzeugt kein gültiges Fernet-Format
  und hätte die Anwendung beim ersten Zugriff mit `RuntimeError` abbrechen
  lassen. `ensure_secret` erzeugt für diese beiden Keys jetzt
  `base64.urlsafe_b64encode(os.urandom(32))` — bit-identisch zu
  `Fernet.generate_key()`, aber ohne dass `cryptography` zum
  Installationszeitpunkt bereits installiert sein muss.
- Beide `AGORA_*`-Keys fehlten in `.env.example` und `.env.docker.example`
  vollständig und sind dort jetzt auskommentiert mit Zweck und
  Erzeugungsbefehl dokumentiert.
- `docs/backup-restore.md` verwies an fünf Stellen auf das nie existierende
  `./backend/reports/` — der reale Pfad ist `backend/uploads/reports/`
  (`Config.UPLOAD_FOLDER/reports`).
- README-Quickstart: redundantes `cp .env.example .env` entfernt (macht
  `install.sh` bereits selbst) und Requirements-Block um die tatsächlich von
  `install.sh` geprüften Voraussetzungen (`bun` >= 1.3, Node >= 20, `uv`)
  ergänzt.
- `backend/gunicorn.conf.py`: Kommentar ergänzt, warum `workers = 1` auch für
  `RunRegistry` und die Monitor-Threads in `app.services.sim.monitor`
  Pflicht ist (Prozess-lokaler State, Monitor-Generation-Zähler). Keine
  Wertänderung.

### Fixed (Installation - 2026-09-08, Codex-Review Runde 2)

- **Der Host-Modus erzeugt jetzt auch `AGORA_AUTH_TOKEN`.** `.env.example` führt den Key nur auskommentiert und setzt `FLASK_DEBUG=false`; ohne Token bricht `backend/run.py` beim Start mit `AGORA_AUTH_TOKEN missing in non-debug mode` aus `Config.validate()` ab. Eine frische Host-Installation war damit auch nach korrekt hinterlegten Neo4j-Zugangsdaten nicht startfähig.
- **Die Secret-Erzeugung setzt kein System-`python3` mehr voraus.** `install.sh` läuft vor `uv sync`; auf einem sauberen macOS mit den dokumentierten Voraussetzungen (bun, node, uv) bringt `uv` seinen eigenen Interpreter mit und `/usr/bin/python3` existiert nicht — die Generierung starb vor der ersten Abhängigkeitsinstallation. Neuer Helfer `random_urlsafe_32` mit Fallback-Kette `python3` → `openssl rand 32` → `head -c 32 /dev/urandom`, jeweils als URL-sicheres Base64 aus derselben Entropiequelle. Die Längenprüfung (44 Zeichen mit Padding für Fernet-Keys, 43 ohne für `token_urlsafe`-Äquivalente) bricht ab, bevor ein zu kurzer Wert in die `.env` geschrieben wird.
- **`README.md` nennt `NEO4J_PASSWORD` wieder im Quickstart.** `.env.example` liefert `NEO4J_PASSWORD=change-me`, und `Config.validate()` lehnt diesen Platzhalter außerhalb des Debug-Modus ab — die Kurzanleitung führte mit „nur LLM-Endpunkte konfigurieren, dann `bun run dev`" in einen Backend, der nicht startet.
- **Der Testblock in `install.sh` ist jetzt durch `# >>> ensure-secret-block` / `# <<< ensure-secret-block` markiert.** `test_install_ensure_secret.py` extrahierte ihn vorher per `sed`-Range bis zur ersten `^}` — jede zusätzliche Funktion vor `ensure_secret` hätte den Range still abgeschnitten.
- **Die Platzhalterliste im Test kommt jetzt aus `app.config` statt aus einer dritten Literalkopie.** `test_replaces_known_placeholder` führte `["change-me", …, "password", "neo4j"]` handgepflegt — neben der Bash-Kopie in `install.sh` die zweite Driftquelle, und GitGuardian las das Literal `password` darin als hartkodiertes Secret (Incident 32406958). Die Parametrisierung speist sich aus `SECRET_KEY_PLACEHOLDERS | NEO4J_PASSWORD_PLACEHOLDERS`; neue Platzhalter in der Config werden damit automatisch mitgetestet.

### Fixed (Frontend-Contracts - 2026-09-08, Review-Slice B7-Nachzug)

- **`_stakeholderGroupKey` (`frontend/src/contracts/reportContract.ts`) nähert sich Pythons `str.casefold()` an, statt nur `toLowerCase()` zu rufen.** Der Zod-Spiegel zu `_stakeholder_group_key` (`backend/app/contracts/report_contract.py`, ADR-0002 Anker 4) zählte bei `Großhaendler`/`Grosshaendler` und bei `ſupervisor`/`supervisor` zwei Stakeholder-Gruppen, wo das Backend eine sieht — der Validator `cross_stakeholder_for_high` war im Spiegel damit LOCKERER als am Vertrag. Ergänzt sind die Faltungen aus CaseFolding.txt, die `toLowerCase()` unverändert lässt: `ß` → `ss`, `ſ` (U+017F) → `s`, `ς` → `σ` sowie die lateinischen Ligaturen `ﬀ ﬁ ﬂ ﬃ ﬄ ﬅ ﬆ`.
- **Kein `normalize("NFKC")` im Spiegel (Codex-Review PR #1482).** Die Kompatibilitätszerlegung faltet mehr als `casefold()`: Fullwidth-Formen (`Ａｕｆｓｉｃｈｔ` → `Aufsicht`) und eingekreiste Ziffern (`①` → `1`) kollabieren unter NFKC, unter `casefold()` nicht. Ein solcher Kollaps macht den Spiegel STRENGER als das Backend — er zählt eine Gruppe, wo Python zwei zählt, und verwirft eine backend-gültige `high`-Antwort als `schema_mismatch`, sodass `getReportEvidence` die Evidence gar nicht mehr anzeigt. Die verbleibende Divergenz (armenische Ligaturen, Cherokee-/Deseret-Sonderfälle) läuft nun ausschließlich in die unschädliche Richtung: der Spiegel zählt höchstens mehr Gruppen als Python, nie weniger.
- **Regressionstest für den Evidence-Omission-Hinweis** (`frontend/src/api/__tests__/report.spec.ts`): eine Antwort mit `success: true`, aber ohne `evidence_map`, liefert den Omission-Grund durch, statt still als leere Evidence zu erscheinen.

### Added

- Echte Integrationstest-Schicht gegen laufendes Neo4j/Redis (Slice 9, Tech-Review 2026-09-07): neuer `integration`-Marker (`backend/pyproject.toml`), standardmäßig ausgeschlossen wie `llm`; `backend/tests/integration/conftest.py` mit `redis_client`- und `neo4j_session`-Fixtures, die bei fehlenden `AGORA_TEST_*`-Env-Variablen kontrolliert überspringen; `neo4j_session` erzeugt eine pro Lauf eindeutige Kennung und räumt im Teardown ausschließlich die davon markierten Knoten ab. Zwei Tests: Redis-Event-Bus Publish/Subscribe über einen echten Server, sowie Idempotenz des Episode/RELATION-Schreibpfads gegen echtes Neo4j. Neuer CI-Job `integration` (`redis:7` + `neo4j:5` als Services), läuft nur auf `push:main` und `workflow_dispatch`. `AGORA_TEST_REQUIRE_SERVICES=1` (im CI-Job gesetzt) macht aus dem Env-Skip ein hartes Fail — sonst meldete sich der Integrationsjob gruen, wenn ein Service-Container gar nicht hochkommt. Der Redis-Integrationstest wartet auf die Server-Bestaetigung (`PUBSUB NUMSUB`) statt auf ein festes `sleep` und publiziert einen Marker-Typ, den der Retained-Snapshot-Pfad nicht erzeugen kann — sonst koennte er gruen werden, ohne dass je eine Pub/Sub-Nachricht floss (Codex-Review PR #1481).

### Fixed

- Kein Fix in diesem Slice — B9 (`_entity_identity_key`) und B11 (`update_run`/`updated_at`) waren bei Prüfung gegen `main` bereits behoben; dieser Slice ergänzt für B11 den fehlenden Regressionstest (Passthrough-Feld-only Update bumpt `updated_at`). B9 hatte bereits einen Regressionstest (`backend/tests/services/test_persona_cap_dedup.py::test_gleicher_name_unter_verschiedenen_typen_bleibt_getrennt`).

### Fixed

- **Partial-Reports nach Nutzer-Abbruch (Cancel) endeten unbedingt als `COMPLETED`, auch wenn Sections fehlten.** `_build_partial_report` (`backend/app/services/report_agent/workflow.py`) setzte den Status bislang bedingungslos auf `completed` ("success-with-caveat"), unabhängig davon, ob die Section-Schleife durch den Abbruch vorzeitig endete. Der Bericht enthielt dadurch weniger Inhalte, als seine eigene Outline versprach, ohne das im Status auszuweisen. Zwei neue Degradationen schließen die Lücke: `run_cancellation` (blockierend, sobald `len(outline.sections) - len(completed_section_titles) > 0`) und `outline_planning` (Warnung, wenn die LLM-Outline-Planung scheiterte und das feste Ersatzschema griff). Der Teil-Report bekommt außerdem `failed_section_indices` und durchläuft dieselbe Vollständigkeitsprüfung (`_apply_requirement_check`) wie ein regulär abgeschlossener Report.
- **`POST /api/runs/<id>/resume` meldete einen `INCOMPLETE`-Report als technischen Fehlschlag.** `_resume_report_generate` verglich `report.status` exakt gegen `ReportStatus.COMPLETED` und schickte jeden anderen deliverable Status in den `failed`-Zweig. Der Vergleich läuft jetzt über `is_deliverable_report_status`; `finish_completed_run` trägt den tatsächlichen Report-Status als `metadata.report_status` am Run nach.
- **Codex-Review Runde 2: ein auf `INCOMPLETE` abgestufter Teil-Report meldete Polling- und Streaming-Consumern trotzdem `completed`.** `_build_partial_report` rief `ReportManager.update_progress(...)` und `progress_callback(...)` unbedingt mit `"completed"` auf — unabhängig vom zuvor ermittelten, ehrlichen `report.status`. Beide Terminal-Events verzweigen jetzt auf `report.status`: bei `INCOMPLETE` melden sie `"incomplete"` samt entsprechender Meldung, Progress bleibt bei 100 (Sections wurden tatsächlich generiert), analog zum Terminal-Handling am regulären Laufende.
- **Codex-Review Runde 2: die `outline_planning`-Degradation (Fallback-Outline) erreichte im gewöhnlichen Planungsfehler-Fall nie die Persistenz.** Fällt `plan_outline` in das feste Drei-Sections-Ersatzschema, erfüllt keine der Sections ein Intent-Preset oder die Pflichtabschnitte — `generate_report` kehrt dann im `missing`-Zweig zurück, lange bevor die einzige Degradations-Aggregation erreicht wird. Der `missing`-Zweig sammelt `fallback_outline_used` jetzt selbst ein und persistiert es mit `save_report`, sodass der Bericht ausweist, dass seine Struktur nicht vom Modell stammt.
- **Codex-Review Runde 3: zwei Degradations-Marker überlebten einen Resume nicht, und die Runde-2-Zuweisung im `missing`-Zweig überschrieb dabei eine bereits persistierte Degradationsliste.** Der Degradations-Zustand eines Laufs lebt im (flüchtigen) Agent-Objekt; ein Resume baut einen neuen Agenten, dessen Marker wieder auf Default stehen. (1) `failed_section_indices` wurde pro Aufruf neu aufgebaut — ein Resume übersprang eine zuvor fehlgeschlagene, jetzt nur noch aus der persistierten Evidence restaurierte Section, ohne sie erneut als fehlgeschlagen zu zählen; ein sonst vollständiger Rest-Lauf konnte den Report fälschlich auf `COMPLETED` heben. `process_section`/`_restore_persisted_section` lesen jetzt `generation_failed` aus der persistierten Evidence und geben es an den Aufrufer zurück. (2) `fallback_outline_used` stand nach einem Resume wieder auf `False`, weil die bereits vorhandene Fallback-Outline die erneute LLM-Planung (und damit die Markierung) umgeht — der Marker wird jetzt im selben Run-Events-Artefakt wie die Sanitization-Marker persistiert und vor der ersten Cancel-Grenze wiederhergestellt. Zusätzlich ersetzte die in Runde 2 in den `missing`-Zweig eingebaute Zuweisung eine bereits persistierte Degradationsliste (z. B. `run_cancellation` aus einem Cancel an der Post-Outline-Grenze im vorigen Aufruf) durch eine frisch berechnete — auf dem Resume-Pfad also durch eine potenziell unvollständige. Ein neuer Merge-Helper führt die persistierte Liste jetzt mit der frischen zusammen, statt sie zu ersetzen.
- **Codex-Review Runde 4: der Merge aus Runde 3 bekam trotzdem eine leere Liste, weil `generate_report` sie erst nach dem eigenen Überschreiben las.** `existing_outline = ReportManager.get_report(report_id)` stand hinter dem ersten `ReportManager.save_report(report)` — dieser erste Save persistiert bereits die leere `run_degradations`-Liste des frischen `Report`-Objekts, bevor der nachfolgende Read sie zurückliest. Ein `run_cancellation`-Eintrag aus einem Cancel nach Planung ging dadurch bei jedem Resume unwiederbringlich verloren, sobald der Lauf erneut im `missing`-Zweig landete. Der Read steht jetzt vor dem ersten Save. Der zugehörige Runde-3-Regressionstest hatte den Fehler verdeckt, weil er `ReportManager.get_report()` statisch auf das in Phase A gespeicherte Objekt mockte, statt die reale Save-vor-Read-Reihenfolge zu durchlaufen — er läuft jetzt gegen einen echten `ReportManager` auf einem `tmp_path`-Datenverzeichnis.

### Fixed (Report-Laufzeit - 2026-09-08, Codex-Review Runde 5)

- **Ein als Fallback markierter Outline wird beim Resume verworfen und neu geplant, statt wiederverwendet zu werden.** Folgefehler der Runde-4-Korrektur: erst dadurch, dass der `get_report`-Read vor dem ersten `save_report` liegt, sah `generate_report` beim Resume überhaupt einen persistierten Outline — und machte damit den Drei-Sektionen-Fallback aus `plan_outline` erstmals wiederverwendbar. Der besteht die Required-Section-Prüfung nie, ein Resume lief also sofort wieder in `INCOMPLETE`, ohne je einen zweiten Planungsversuch zu unternehmen; die angebotene Wiederaufnahme konnte eine nur vorübergehende Planungsstörung nicht mehr heilen. Neuer Helfer `_reusable_persisted_outline` liest dafür den in Runde 3 eingeführten `fallback_outline_used`-Marker. `_persist_fallback_outline_marker` schreibt jetzt auch das `False`, damit ein geheilter Lauf seinen Outline beim nächsten Resume wieder verwenden darf.
- **Der geerbte Fallback-Marker wird vor einem neuen Planungsversuch gelöscht** (Codex-Review Runde 6, Folgefehler von Runde 5). `_restore_work_trace_markers` setzt `fallback_outline_used` beim Resume aus dem persistierten Zustand des Vorlaufs. Gelingt der neue `plan_outline`-Versuch, stammt der ausgelieferte Outline nicht mehr aus dem Fallback — ohne Zurücksetzen schrieb `_persist_fallback_outline_marker` den geerbten Wert unverändert zurück: der Report trug eine falsche `outline_planning/fallback_outline_used`-Warnung, und der nächste Cancel/Resume hätte den gültigen Outline erneut verworfen. Neuer Helfer `clear_fallback_outline_used` in `run_degradation.py`; nur der Fallback-Pfad des jeweiligen Versuchs setzt den Marker.

### Slice 3.1 — BudgetExceededError im ParallelIPCHandler

#### Problem

Der `ParallelIPCHandler` (Default-Parallelrunner für Twitter+Reddit) fing
`BudgetExceededError` im generischen `except Exception` statt strukturiert.
Dadurch konnte ein hartes Report-Budget, das während eines Interviews in einer
Plattform erreicht wurde, durch die `success_count`-Aggregation der zweiten
Plattform verschluckt werden — der Run endete `completed` statt
`stopped`/`termination_reason=budget_*`.

Zusätzlich fehlte das `budget_exceeded`-Feld in der IPC-Response, sodass der
Client (`interview_client._reraise_if_budget_exceeded`) den Abbruch nicht als
`BudgetExceededError` re-raisen konnte.

#### Lösung

1. **`send_response`** um optionales `budget_exceeded: Dict[dimension, observed, threshold]` ergänzt (kompatibel zu `sim_runtime.ipc.IPCHandler`).

2. **`_interview_single_platform`** fängt `BudgetExceededError` **explizit** vor dem generischen `except` und gibt strukturierten Fehler mit `budget_exceeded`-Dict zurück.

3. **`handle_interview` (beide Plattformen):** Budget-Abbruch wird **vor** der `success_count`-Aggregation erkannt — erster `budget_exceeded` gewinnt, Response trägt strukturiertes Feld, Rückgabe `False`.

4. **`handle_batch_interview`** analog: `BudgetExceededError` explizit gefangen, `budget_exceeded` in Response, `False`.

5. **Client-seitig** (`interview_client._reraise_if_budget_exceeded`) unverändert: liest `response.budget_exceeded` und wirft wieder `BudgetExceededError` — Run endet korrekt `stopped`/`budget_*` (via `mark_budget_abort`).

#### Tests

Neue Regressionstests in `tests/scripts/test_run_parallel_ipc_attribution.py`:

- (a) Einzelplattform BudgetExceeded → Response-Feld + `ok=False`
- (b) Gemischter Beide-Plattformen-Fall: Budget hat Vorrang vor `success_count`
- (c) Batch-Interview BudgetExceeded → strukturierte Response
- (d) Batch beide Plattformen: erste Dimension gewinnt
- (e) Client-Re-Raise über den echten Weg: geschriebenes Response-JSON →
  `IPCResponse.from_dict` → `_reraise_if_budget_exceeded` → `BudgetExceededError`.
  Der Test bricht damit auch bei reiner Feldnamen-Drift zwischen Runner und
  Client-Deserialisierung.

#### Referenzen

- Vorbild: `scripts/sim_runtime/ipc.py:151-170,241-251`
- Repo-Regel: `BudgetExceededError` wird nie in eine Fallback-Antwort umgewandelt
- Follow-up zu #1478

### Fixed (Budget-Guard und Ledger decken Tool-Calls, Vision und Interview-Client ab — 2026-09-08)

- **Tool-Calls konnten das Budget beliebig überschreiten:** `LLMClient.chat_with_tools` (`app.llm.tool_calls._chat_with_tools`) rief `_budget_check()` nirgends auf — anders als der Textpfad (`chat`/`chat_json`), der jeden physischen Providerrequest über `_provider_attempt`/`_budget_check` absichert. Ein erschöpftes Hard-Limit (`max_llm_calls`) wurde auf diesem Pfad ignoriert, der Provider trotzdem angefragt. Der Guard läuft jetzt vor dem Providercall und wirft dieselbe `BudgetExceededError` wie der Textpfad.
- **Vision-Calls (`describe_image`) waren komplett unsichtbar für Budget-Guard und Ledger:** weder `_budget_check()` noch `_log_invocation_event`/`_budget_record()` liefen für diesen Pfad — Vision-Aufrufe erschienen weder in `llm_invocation_logger` noch in den weichen/harten Run-Budget-Limits. Beides ist jetzt nachgezogen (Erfolg und Fehlschlag werden gebucht, analog zu `_provider_attempt`).
- **Der Interview-Direktpfad (Post-Simulation, kein IPC) baute seinen `LLMClient` ohne `run_id`:** `interview_direct._default_client_factory` konstruierte den Client an allen drei Fallback-Zweigen ohne `run_id`, wodurch `_budget_enforcer`/`_log_invocation_event` mangels Run-Kontext No-Ops blieben. `run_id` wird jetzt additiv durch die gesamte Kette gereicht (`graph_tools.interview_agents` → `SimulationRunner.interview_agents_batch`/`interview_agent` → `interview_client.interview_agents_batch`/`interview_agent` → `interview_agents_batch_direct`/`interview_agent_direct` → `_default_client_factory`), bestehende Aufrufer ohne `run_id` bleiben unverändert (Default `None`).
- **Tool-Call-Reservierungen wurden nie freigegeben:** `chat_with_tools` rief `_budget_check()` vor dem Providercall auf, aber weder der Erfolgs- noch der Exception-Pfad das passende `_budget_record()` — die In-Flight-Reservierung blieb bis zum Ablauf der 900s-TTL bestehen und der Call zählte doppelt (Reservierung + Ledger-Eintrag). `_budget_record()` läuft jetzt auf beiden Ausgängen, analog zu `_provider_attempt` im Textpfad.
- **Ein erschöpftes Hard-Budget während eines Interviews wurde zum weichen Fehler statt zum Run-Abbruch:** `interview_direct._run` und `GraphToolsService.interview_agents` fingen `BudgetExceededError` mit ihren breiten `except Exception`-Blöcken ab und verwandelten sie in ein Item-Fehler-Feld bzw. eine `result.summary` — `report_generation.py` sah die Exception nie und der Run lief als `completed` statt `stopped`/`termination_reason=budget_*` weiter. Beide Stellen reichen ein hartes Budget jetzt durch (`reraise_if_budget_exceeded`), analog zum bereits gehärteten Selection-Pfad.
- **Der Vision-Budget-Guard saß auf der falschen Ebene:** `describe_image` prüfte das Budget einmal um die gesamte `execute()`-Operation statt pro physischem Providerrequest — ein transienter Retry oder ein `TOKEN_KEY_QUIRK`-Korrekturversuch erzeugte dadurch nur einen Check/Event/Record, obwohl mehrere Requests abgesetzt wurden (`max_llm_calls=1` erlaubte so mehrere abgerechnete Requests, das Ledger zählte zu niedrig). Der Guard-Lebenszyklus läuft jetzt pro Attempt über `_provider_attempt`, analog zum Textpfad.
- **Derselbe Fehler im Tool-Call-Pfad:** `chat_with_tools` (`app.llm.tool_calls._chat_with_tools`) hatte denselben Guard-auf-falscher-Ebene-Fehler wie zuvor `describe_image` — ein einzelner `_budget_check()` deckte die gesamte logische Operation ab statt jeden physischen Providerrequest, sodass ein transienter Retry oder eine Quirk-Korrektur (`TOKEN_KEY_QUIRK`/`TEMPERATURE_QUIRK`) nur einen Budget-Check/Event/Record erzeugte, obwohl mehrere physische Requests abgesetzt wurden. Der native Tool-Call-Pfad läuft jetzt ebenfalls über `_provider_attempt`.
- **Native Tool-Calls trugen keine Tokens ins Usage-Ledger:** `_log_invocation_event` bekam bei jedem erfolgreichen `chat_with_tools`-Aufruf nie `prompt_tokens`/`completion_tokens` — das Ledger markierte diese Calls als "token-unknown" und ließ ihre Tokens/Kosten aus den beobachteten Summen heraus, harte Token-/Kostenbudgets konnten den Tool-Pfad also unbegrenzt überschreiten. Usage wird jetzt sowohl aus der regulären Response als auch aus dem letzten Streaming-Chunk extrahiert und vor der Budget-Auswertung ins Event aufgenommen.
- **Vision-Usage wurde bei Modell-Override dem falschen Modell zugerechnet:** wählte `describe_image()` per `model=`-Parameter oder `VISION_MODEL_NAME` ein anderes Modell als `self.model`, schrieb `_log_invocation_event` trotzdem `self.model` ins Invocation-Event — die Usage landete im Ledger unter dem Text-Modell des Clients statt unter dem tatsächlich angefragten Vision-Modell. War das Text-Modell günstiger oder unbepreist, erschien die beobachtete Kostensumme zu niedrig und ein hartes `max_cost_micros`-Budget erlaubte zusätzliche Calls. `_provider_attempt`/`_record_provider_success`/`_log_invocation_event` nehmen jetzt einen optionalen `model`-Parameter (Default `self.model`), den `describe_image` mit dem tatsächlich angefragten Modell befüllt.
- **Runde 5 — der Vision-Provider wurde weiterhin vom falschen Modell abgeleitet:** der Runde-4-Fix reichte das effektive Modell nur ans `model`-Feld des Invocation-Events durch, `provider_id` blieb bei `self._detect_provider()` ohne Modell-Override hängen. `describe_image(model="...:cloud")` gegen einen lokalen Ollama-Endpoint schrieb damit `provider_id="ollama"` statt `"cloud"` ins Ledger — `PricingRegistry` hielt den Call für kostenlos, ein hartes Kostenbudget konnte überschritten werden. `_detect_provider` nimmt jetzt denselben optionalen `model`-Parameter wie `_log_invocation_event` an und leitet ihn über den zentralen `registry.py::detect_provider` ab; ohne Override bleibt das Verhalten unverändert.
- **Runde 5 — der IPC-Interview-Pfad umging das Report-Budget vollständig:** lebt der OASIS-Worker nach der Simulation noch (normaler Wartemodus), nimmt `interview_client.interview_agent`/`interview_agents_batch` den IPC-Zweig — `run_id` erreichte diesen Zweig nie, anders als den bereits gehärteten Direktpfad. Der Worker läuft mit der `AGORA_RUN_ID` der *Simulation*, und `scripts/sim_runtime/budget_guard.py` prüft harte Limits nur an Rundengrenzen, nicht um einzelne Interview-Kommandos im Wartemodus. IPC-Interviews eines Report-Laufs waren damit gegen dessen hartes Call-/Token-/Kostenbudget ungeschützt. Beide Funktionen prüfen das harte Report-Budget jetzt vor dem IPC-Versuch über denselben zentralen Mechanismus (`RunBudgetEnforcer.check_before_call`/`record_after_call`, wie im Direktpfad über `LLMClient`) — ohne `run_id` bleibt der Guard ein No-op.
- **Runde 6 — das Vorab-Gate aus Runde 5 reichte nicht: der physische Modellaufruf im Worker landete weiterhin im falschen Ledger.** `_report_budget_guard` prüfte nur ein einziges Mal vor dem IPC-Versuch und gab im `finally` seine Reservierung wieder frei — der tatsächliche LLM-Call lief im OASIS-Worker-Subprozess und wurde dort ausschließlich gegen dessen simulationszeitliche `AGORA_RUN_ID`/Stage `simulation_rounds` verbucht (`scripts/sim_runtime/budget_guard.py`). Ein erfolgreicher IPC-Batch hinterließ damit im Report-Ledger keine Spur, und ein Folge-Batch durfte erneut starten, obwohl das harte Limit längst erreicht war. `SimulationIPCClient.send_interview`/`send_batch_interview` reichen jetzt optional `report_run_id` im Kommando-Payload durch; `sim_runtime.ipc.IPCHandler` bekommt optional den `SubprocessBudgetGuard` injiziert und ordnet den physischen Modellaufruf für die Dauer von `env.step()` per `SubprocessBudgetGuard.attribute_to(report_run_id, "report_interview")` dem Report-Run zu. Jeder physische Aufruf innerhalb dieses Blocks prüft `RunBudgetEnforcer.check_before_call()` VOR dem Call und verbucht das Ergebnis danach im Report-Ledger (`record_after_call`) — dasselbe Check/Record-Paar wie `LLMClient._provider_attempt`, kein zweiter Budget-Mechanismus. Ohne `report_run_id` (Alt-Worker, Simulation ohne Report-Kontext) bleibt das Kommando unverändert; ohne injizierten Guard (ältere Runner-Version) wird `report_run_id` stillschweigend ignoriert. Bekannte Grenze: `scripts/run_parallel_simulation.py` (Dual-Platform-Runner) hat eine eigene, separate `ParallelIPCHandler`-Implementierung ohne jede `SubprocessBudgetGuard`-Anbindung — dieser Pfad bleibt von diesem Fix unberührt und braucht ein eigenes Issue.
- **Runde 7 (Codex-Review, Finding 3) — die vier in Runde 6 neu eingeführten Fehlerpfade in `scripts/sim_runtime/budget_guard.py` (`_enforce_before_physical_call`: Enforcer-Konstruktion und Budget-Check; `_release_report_reservation`: Enforcer-Konstruktion und `record_after_call`) nutzten `print()` statt strukturiertem Logging — ein von AGENTS.md verbotenes Muster.** Verifiziert: `app.utils.logger.get_logger` ist im OASIS-Subprozess importierbar (derselbe Import-Kontext, in dem `app.services.run_budget` bereits erfolgreich läuft) und sein Konsolen-Handler schreibt auf `sys.stdout`, das der Subprozess-Start (`process_manager.py::start_simulation`) 1:1 auf `simulation.log` im Simulationsverzeichnis umleitet — dieselbe Stelle, die `print()` zuvor traf, plus redundant `backend/logs/<datum>.log`. Die vier neuen Aufrufe protokollieren jetzt über `logger.warning(...)`; die zwei präexistenten `print()`-Aufrufe (Usage-Recording-Fehler, Abort-Marker-Schreibfehler aus Issue #764) bleiben unverändert — das wäre ein ungefragter Refactor gewesen.
- **Runde 7 (Codex-Review, Finding 2) — ein Budget-Abbruch während eines IPC-Interviews wurde im Flask-Prozess als generischer Tool-Fehler statt als Run-Ende behandelt.** Erreichte der Worker während `env.step()` ein hartes Report-Budget, warf der `SubprocessBudgetGuard` (Runde 6) zwar `BudgetExceededError`, aber `sim_runtime.ipc.IPCHandler.handle_interview`/`handle_batch_interview` fingen das nur mit ihrem generischen `except Exception`-Block ab und antworteten mit `status="failed"` und einem reinen Fehlertext. `interview_client.interview_agent`/`interview_agents_batch` lasen das als `{"success": False, "error": <Text>}`, `GraphToolsService` behandelte das Interview-Tool damit als dauerhaft nicht verfügbar statt den Lauf zu beenden — der Report kam nie als `stopped`/`termination_reason=budget_*` an. Beide Handler unterscheiden jetzt `BudgetExceededError` von generischen Fehlern und tragen `dimension`/`observed`/`threshold` strukturiert als eigenes `budget_exceeded`-Feld durch das IPC-Protokoll (Datei- und Redis-Transport: `sim_runtime.ipc.IPCHandler.send_response` → `event_bus.py`/`event_bus_redis.py` (Legacy-Response-Decode) → `simulation_ipc.IPCResponse`) — kein Parsen von Fehlertexten. `interview_client.py` wirft bei gesetztem Feld wieder dieselbe `BudgetExceededError`, statt `success=False` zurückzugeben; ein generischer Interview-Fehler bleibt unverändert ein weiches `{"success": False}`.
- **Runde 7 (Codex-Review, Finding 4) — eine kaputte, aber HTTP-erfolgreiche Vision-Antwort wurde als erfolgreicher Aufruf verbucht.** `describe_image()` rief `_record_provider_success` (Success-Event + Freigabe der Budget-Reservierung) auf, BEVOR die Antwort geparst wurde (`response.choices[0].message.content`) — ein Provider mit `choices=[]` oder einer Choice ohne `message.content` ließ Ledger und Telemetrie einen Erfolg melden, obwohl `describe_image` anschließend mit einer Exception endete, anders als die bereits abgesicherten Text-/Tool-Call-Pfade in derselben Datei. Die Antwort wird jetzt vor dem Success-Record geparst; schlägt der Parse fehl, läuft genau ein Failure-Event + `_budget_record()`, dann wird die Exception durchgereicht — derselbe Aufbau wie im Textpfad (`chat()`).
- **Der Timeout-Fallback auf den Direktpfad läuft außerhalb des Budget-Guards** (Codex-Review Runde 8). Galt der Worker als lebendig, antwortete aber nicht, lief `_direct()` noch innerhalb von `_report_budget_guard` — der Guard hielt seine prozesslokale Reservierung, und der eigene `_budget_check()` des Direktpfads zählte sie mit. Bei genau einem verbleibenden Call warf der Fallback deshalb `BudgetExceededError` und stoppte den Report, obwohl der Ledger noch gar nichts verbraucht hatte. Beide Timeout-Pfade (Einzel- und Batch-Interview) verlassen den `with`-Block jetzt, bevor sie den Direktpfad rufen.

### Fixed (Evidence-Map-Normalisierung - 2026-09-08)

- **`EvidenceMapModel.validate_evidence_cross_references` zählte Stakeholder-Gruppen für persistierte Reports anders als die ADR-0002-Hartanker:** der Persistenz-Validator zählte den rohen `persona_stakeholder_group`-Wert, während der Schreibpfad (`auto_downgrade_unsupported_high_claims`) und der Hartanker `cross_stakeholder_for_high` bereits über `_role_family_key` normalisieren. Folge: „Bürger“ und „bürger “ zählten beim Laden/Exportieren von Altbestand als zwei Gruppen, im Schreibpfad als eine — ein `high`-Label ließ sich aus einer einzigen Stakeholder-Stimme mit zwei Schreibweisen erzeugen. Frisch generierte Reports waren unauffällig, weil sie vorher durch `auto_downgrade` laufen. Der Validator zählt jetzt ebenfalls über `_role_family_key`. Reine Verschärfung: die Zahl unterscheidbarer Gruppen kann dadurch nur sinken.
- **`GET /api/report/<id>/evidence` degradiert bei einer vertragswidrigen Evidence-Map jetzt wie der JSON-Export** (200 mit `evidence_omitted`) statt mit 422 abzuweisen. Die Rollenfamilien-Verschärfung oben kann Altartefakte treffen, die vor der Verschärfung noch valide waren und die keine Migration nachträglich reparieren kann — der Report-Rumpf bleibt dabei unversehrt, nur die Evidence-Map entfällt.
- **Frontend zieht diesen Degradierungspfad nach (PR #1477):** `getReportEvidence` unterscheidet die degradierte 200-Antwort (`evidence_omitted`, kein `data`) strukturell von einer echten Evidence-Map. `Step4Report.vue` zeigt dafür denselben Auslassungshinweis wie beim JSON-Export, statt den fehlenden `data`-Wert stillschweigend als leeren Erfolg zu behandeln oder ihn fälschlich als generischen Schema-Mismatch zu melden.
- **Review-Nachbesserung (Runde 3):** `getReportEvidence` parste die Erfolgsantwort bislang nur per TypeScript-Assertion, ohne `EvidenceMapResponseSchema` tatsächlich aufzurufen — eine driftende Antwort (z. B. eine Omission ohne `validation_errors`) erreichte ungeprüft `Step4Report.vue` und riss dort beim `.length`-Zugriff. `getReportEvidence` parst die Erfolgsantwort jetzt mit `EvidenceMapResponseSchema.safeParse`, wirft bei Drift einen definierten Fehler und lässt den Fehler-Envelope (`success: false`) unangetastet durch. Der Zod-Spiegel des Cross-Stakeholder-Zählers (`EvidenceMapSchema`) zog außerdem exakt dieselbe `_role_family_key`-Normalisierung nach wie der Backend-Hartanker `cross_stakeholder_for_high` — vorher zählte er noch den rohen `persona_stakeholder_group`-Wert und lag damit strenger als das Backend.
- **Review-Nachbesserung (Runde 4):** ein Schema-Mismatch aus `getReportEvidence` warf bislang einen einfachen `Error`, den `Step4Report.loadEvidence()` nicht von einem Transport-/HTTP-Fehler unterscheiden konnte — er landete deshalb ungewollt im Retry-Zweig statt bei `recordSchemaError`. `getReportEvidence` wirft jetzt eine `ApiError` mit `code: 'schema_mismatch'`; `loadEvidence()` klassifiziert diesen Fall vor dem Retry-Zweig. Außerdem verlor `useObjectDetail` die `evidence_omitted`-Markierung für einen outline-losen Report (von `ReportSchema` ausdrücklich erlaubt) still, weil das Detail-Objekt nur bei vorhandener Outline entstand — es entsteht jetzt sobald der Report selbst geladen ist. Schließlich modelliert `EvidenceMapResponseModel` die Erfolgs-/Degradations-Union jetzt strukturell als `RootModel`-Union zweier `.strict()`-Varianten statt über zwei optionale Felder plus Laufzeit-Validator — das generierte JSON-Schema trägt die Exklusivität jetzt selbst (`oneOf` statt zweier optionaler Felder ohne `required`), der Zod-Spiegel zieht mit `z.union` nach.
- **Review-Nachbesserung (Runde 5):** `success` trug in beiden Envelope-Varianten (`EvidenceMapResponseSuccessVariant`/`EvidenceMapResponseOmittedVariant`) noch einen Default (`Literal[True] = True`) — ein Default nimmt ein Feld im generierten JSON-Schema aus der `required`-Liste heraus, `{"data": <valide Map>}` ohne `success` bestand also sowohl Pydantic als auch das eingecheckte `schemas/evidence-map-response.schema.json`, während die Zod-Grenze im Frontend (`reportContract.ts`) `success: true` verlangte und dieselbe Payload ablehnte. `success` ist jetzt in beiden Varianten Pflichtfeld ohne Default; die Factories `for_data`/`for_omission` übergeben `success=True` jetzt explizit. Außerdem war das eingecheckte Schema-Artefakt bereits vor dieser Änderung veraltet: sein `description`-Feld trug noch den alten Klassen-Docstring-Satz aus Runde 3 (\"``RootModel`` reicht ueberzaehlige Keyword-Argumente … durch\"), während der Docstring in `report_contract.py` seit Runde 4 auf die Factories verweist — `dump_schemas --check` war dadurch unabhängig vom `success`-Fix bereits rot. Beide Ursachen sind jetzt in einer Regenerierung behoben.
- **Review-Nachbesserung (Runde 5, Frontend):** `_stakeholderGroupKey` im Zod-Spiegel (`reportContract.ts`) normalisierte mit `toLowerCase()` + expliziter `ß`→`ss`-Ersetzung — schwächer als der Backend-Hartanker `_stakeholder_group_key`, der Pythons `str.casefold()` nutzt. Belegtes Gegenbeispiel: `"ſupervisor"` (U+017F LATIN SMALL LETTER LONG S) faltete im Frontend nicht auf `"supervisor"`, im Backend schon — der Spiegel hätte eine `high`-Evidence-Map akzeptiert, die das Backend abgelehnt hätte. Die Normalisierung läuft jetzt über `normalize("NFKC")` vor `toLowerCase()` vor den expliziten Sonderfällen (`ß`→`ss`, `ς`→`σ`); eine vollständige `casefold()`-Äquivalenz ist das weiterhin nicht (siehe Kommentar an `_stakeholderGroupKey`), der Spiegel bleibt aber ausschließlich strenger, nie laxer als das Backend. Ergänzend ein Regressionstest für den Evidence-Omission-Hinweis in `Dossier.vue`, der bislang ungetestet war.

### Added (Simulations-Laufzeit - 2026-09-07, Review-Fixes 2026-09-08)

- **Startup-Reconciliation für verwaiste `simulation_run`-Runs:** `reconcile_stale_runs` (`backend/app/services/sim/reconciliation.py`) iteriert alle RunRegistry-Einträge mit Status `pending`/`processing` und Typ `simulation_run`, lädt den zugehörigen `run_state.json` und prüft die dort persistierte `process_pid` per `os.kill(pid, 0)`-Liveness (`is_process_alive`). Fehlt der Prozess UND ist `run_state.json` in einem unklaren Zustand (`RUNNING`/`STARTING` oder gar nicht vorhanden), wird der Run als `failed`/`process_restart` markiert. Ist `run_state.json` dagegen bereits terminal (`COMPLETED`/`STOPPED`/`FAILED` — der Run also regulär beendet, nur die anschließende RunRegistry-Sync kam nie an), wird der Run NICHT mit `process_restart` überschrieben, aber der Endzustand auch nicht propagiert (siehe Review-Runde 3, F2 unten) — nur geloggt, Run bleibt unangetastet. Lebt der Prozess noch, bleibt der Run unangetastet, aber ein `logger.warning` macht sichtbar, dass er von diesem (neuen) Worker nicht mehr verwaltet wird (Finding C, siehe „Bekannt offen").
- **Kanonischer Einhängepunkt jetzt `gunicorn.conf.py::post_fork`** statt ausschließlich `create_app` (Codex-Review Finding A, PR #1476): mit `preload_app=True` + `workers=1` läuft `create_app` nur einmal im Master vor dem ersten Fork — ersetzt gunicorn den einzigen Worker danach (Timeout, Crash, Replacement) ohne Master-Neustart, läuft `create_app` nie wieder, während `post_fork` bei jedem Worker-Start feuert. `run_startup_reconciliation` (neu, `reconciliation.py`) bündelt Config-Flag-Check (`AGORA_STARTUP_RECONCILIATION`) und Best-effort-Fehlerbehandlung für beide Aufrufer. `create_app` bleibt zusätzlich Aufrufer für Entwicklungs-/Testbetrieb ohne gunicorn (`flask run`, Test-Fixtures) — der doppelte Lauf beim allerersten gunicorn-Boot ist ein harmloses No-op, da der zweite Durchlauf keine weiteren `pending`/`processing`-Runs mehr findet.
- **`TerminationReason` um `"process_restart"` erweitert** (additiv, kein neuer `RunStatus`) — `backend/app/contracts/run_budget_contract.py` und Zod-Spiegel `frontend/src/contracts/runBudgetContract.ts`; Schemas neu gerendert.

### Fixed (Simulations-Laufzeit - 2026-09-07)

- **`process_manager.start_simulation` blockt einen Neustart nicht mehr allein wegen eines persistierten `RUNNING`/`STARTING`-Status.** Vor dem Ablehnen wird die `process_pid` aus dem letzten `run_state.json` per Liveness geprüft (`is_process_alive`); ist der Prozess tot, wird der alte State auf `FAILED`/„Prozess-Neustart während des Runs" korrigiert und der Start zugelassen, statt eine Simulation für immer als „läuft schon" zu blockieren.
- **F1 (Codex-Review Runde 3):** `_resume_or_restart_simulation_run` reicht die per `/api/runs/<run_id>/resume` angefragte Run-ID jetzt bis in `_correct_stale_run_state` durch, statt bei mehreren historischen `processing`-Manifesten blind das erste (`candidates[0]`, faktisch das neueste) zu korrigieren — sonst traf der Fix den falschen, neueren Run und der angefragte blieb für immer `processing`.
- **F2 (Codex-Review Runde 3):** die Terminal-Propagation aus Finding B überträgt einen `COMPLETED`/`STOPPED`/`FAILED`-Zustand aus `run_state.json` nicht mehr auf ein `processing`-Manifest, weil `run_state.json` keine RunRegistry-`run_id` führt und die Zuordnung bei mehreren Manifesten pro `simulation_id` (z. B. Alt-Run + Ersatzlauf nach Resume) nicht verifizierbar ist — sonst wäre ein fremder Endzustand als stille Datenkorruption in die Historie eines verwaisten/gescheiterten Runs geschrieben worden.
- **Docker `stop_grace_period: 45s` + `init: true` am `agora`-Service in allen fünf Compose-Files** (`docker-compose.yml`, `docker-compose.override.yml`, `docker-compose.prod.yml`, `deploy/compose/docker-compose.prod-with-proxy.yml`, `deploy/compose/docker-compose.e2e.override.yml`). `gunicorn.conf.py` setzt `graceful_timeout=30`; Dockers Default von 10s hätte den Worker per SIGKILL abgeschossen, bevor er sauber beenden kann — genau die Ursache für die oben behobenen Orphan-Runs. `init: true` reapt Zombie-Kindprozesse (OASIS-Subprozesse).

### Fixed (Startup-Reconciliation - 2026-09-08, Review-Runde 4)

- **F1:** `reconcile_stale_runs` behandelt `paused`-Registry-Einträge jetzt genauso wie `pending`/`processing` — ein soft-pausierter Run, dessen OASIS-Subprozess durch einen Container-/Worker-Neustart stirbt, wird beim nächsten Start als `failed`/`process_restart` markiert, bevor der direkte Resume-Endpunkt darauf zugreifen kann.
- **F2:** teilen sich mehrere `pending`/`processing`/`paused`-Manifeste eine `simulation_id` mit totem Prozess, wird die Liveness-Entscheidung jetzt pro Simulation genau einmal getroffen und auf alle betroffenen Manifeste angewendet — vorher wurde nur das erste Manifest gescheitert, weil dessen Bearbeitung das geteilte `run_state.json` bereits auf `FAILED` schrieb, bevor das nächste Manifest denselben Zustand las.

### Fixed (Startup-Reconciliation - 2026-09-08, Review-Runde 5)

- **F1 (Major):** eine halb geschriebene Korrektur konnte permanenten Teilfortschritt hinterlassen: `reconcile_stale_runs` setzte die `RunRegistry` zuerst auf `failed` und persistierte `run_state.json` erst danach — schlug der zweite Schritt fehl, blieb das Manifest für immer auf `failed` hängen (nicht mehr in `_STALE_STATUSES`), während `run_state.json` weiterhin `RUNNING`/`STARTING` zeigte. Die Reihenfolge ist jetzt umgedreht (`save_run_state` zuerst); schlägt dieser Schritt fehl, bleibt die Registry unangetastet und der Run stale für den nächsten Start. Damit auch der umgekehrte Fehlerfall (State geschrieben, Registry-Update gescheitert) wieder aufgegriffen wird, ist `RunnerStatus.FAILED` kein Terminal-Status mehr, der übersprungen wird: steht `run_state.json` bereits auf `FAILED`, ist die PID tot und das Manifest weiterhin stale, wird es wie ein verwaister Run auf `failed`/`process_restart` gesetzt — anders als bei `COMPLETED`/`STOPPED`, wo eine Propagation weiterhin eine echte Falschaussage wäre (fremder Erfolgs-/Stop-Zustand auf einem verwaisten Alt-Manifest) und deshalb unterbleibt.

### Bekannt offen (nicht Teil dieses Slices)

- **Codex-Review Finding C (PR #1476, bewusst nicht behoben):** eine lebende PID heißt nur, dass der OASIS-Subprozess `start_new_session=True` den Tod seines Gunicorn-Worker-Elternprozesses überlebt hat — nicht, dass der (neue) Ersatz-Worker ihn noch verwaltet. Weder `Popen`-Objekt noch Monitor-Thread existieren dort; der Run bleibt dauerhaft `processing` und ist über die API nicht mehr steuerbar. Der naheliegende Fix (überlebenden Prozess beim Worker-Start terminieren) ist zu riskant: startete nur der Master neu, während der Worker gesund weiterlief, würde eine laufende Simulation abgeschossen. Reconciliation loggt diesen Fall stattdessen laut (`logger.warning` mit Run-ID, Simulation-ID, PID).
- Prepare-/Report-Daemon-Threads überleben einen Container-Restart ebenfalls nicht sauber (Issue [#1472](https://github.com/arn0ld87/agora/issues/1472)).
- Cancel-Flags (`cancel_flag.py`) liegen nur als `threading.Event` im Prozessspeicher, nicht Redis-persistent.
- Kein `worker_exit`-Hook in `gunicorn.conf.py`, der laufende Subprozesse beim Worker-Reload proaktiv abräumt.

### Fixed

- **Report Agent**: Sektions-Persistenz ist jetzt atomar und prüft beide Artefakte. Zuvor wurde `write_section_markdown` nicht-atomar ausgeführt, was bei Crashes zwischen Evidence und Markdown zu Orphan-Dateien führte (nur Markdown ohne Evidence). `_restore_persisted_section` überprüft jetzt, dass BEIDE Artefakte vorhanden sind, bevor ein Abschnitt als persistiert restauriert wird — fehlt die Evidence, wird die Sektion neu generiert. `write_section_markdown` nutzt jetzt das gleiche atomare Muster wie `write_json_atomic` (tmp-Datei + `os.replace`).
- **Report Agent** (Codex-Review PR #1475, Finding 1): eine verwaiste Markdown-Datei (auf Platte, aber ohne zugehörigen Evidence-Eintrag) wird jetzt entfernt, BEVOR die neu generierte Sektion ihre Evidence schreibt. Vorher konnte ein Absturz zwischen dem Schreiben der neuen Evidence und dem Ersetzen des Markdowns beide Artefakte inkonsistent zueinander hinterlassen — ein nachfolgender Resume hätte das alte Markdown gegen die neue Evidence restauriert.
- **Report Agent** (Codex-Review PR #1475, Finding 2): beim Resume eines Reports werden Abschnitte ohne Evidence-Eintrag jetzt aus dem Prompt-Kontext (`previous_sections`) und der Fortschrittsliste (`completed_section_titles`) herausgefiltert. Vorher floss ihr veralteter Inhalt in die Generierung nachfolgender Abschnitte ein und wurde nach der Regeneration ein zweites Mal angehängt.
- **Report Agent** (Codex-Review PR #1475, Runde 2, Finding 1): schlägt das Entfernen der verwaisten Markdown-Datei mit `OSError` fehl, propagiert der Fehler jetzt, statt ihn zu loggen und fortzufahren. Vorher hätte `_save_evidence_section` trotz gescheitertem Löschversuch neue Evidence geschrieben, während die veraltete Markdown-Datei liegen blieb — die Sektion scheitert jetzt sauber, bevor diese Inkonsistenz entstehen kann.
- **Report Agent** (CodeRabbit-Review PR #1475, Runde 2, Finding 3): `write_json_atomic` und `write_section_markdown` synchronisieren nach `os.replace` jetzt zusätzlich das Elternverzeichnis (`fsync`), damit der Rename einen Stromausfall übersteht — vorher wurde nur die temporäre Datei selbst gefsynct. Auf Plattformen/Dateisystemen ohne Verzeichnis-`fsync` degradiert der Aufruf still, statt den bereits erfolgreichen Schreibvorgang nachträglich als Fehler zu melden.
- **Report Agent** (Codex-Review PR #1475, Runde 3, Finding 1): das Verzeichnis-`fsync` degradiert jetzt nur noch für die typischen "nicht unterstützt"-errno-Werte (`EINVAL`, `EACCES`, `EPERM`, `ENOTSUP`/`EOPNOTSUPP`) still — echte Storage-Fehler (z. B. `ENOSPC`, `EIO`) propagieren jetzt, statt einen Write, dessen Rename einen Absturz nicht übersteht, fälschlich als erfolgreich zu melden.
- **Report Agent** (CodeRabbit-Review PR #1475, Runde 3, Finding 2): entfernt eine `FileNotFoundError` beim Löschen der verwaisten Markdown-Datei (z. B. weil der DELETE-Endpunkt den Report-Ordner zwischen Existenzprüfung und Löschversuch bereits per `shutil.rmtree` entfernt hat), wird das jetzt als Erfolg gewertet — der gewünschte Endzustand liegt bereits vor. `PermissionError` und jeder andere `OSError` propagieren weiterhin unverändert.

### Slice 1.1 — Worker-Exit-Hook für In-Process-Jobs

Beendet sich der Webprozess, bekommen alle laufenden In-Process-Jobs —
`simulation_prepare`, `report_generate`, `graph_build`, `ontology_generate` —
noch in diesem Lauf einen ehrlichen terminalen Zustand `failed/process_restart`,
statt auf die Startup-Reconciliation beim nächsten Start zu warten. Der neue
Hook in `backend/app/services/sim/process_shutdown.py` markiert dabei nur Runs,
die anhand von Worker-Token und PID diesem Prozess gehören, und setzt sie in
derselben Schreibreihenfolge wie `reconcile_stale_jobs`: erst das Cancel-Flag
für kooperativen Abbruch, dann — nur für `simulation_prepare` — der
SimulationState (F1-Invariante: State vor Manifest), zuletzt das
RunRegistry-Manifest.

Die Arbeit läuft nicht im Signal-Handler, sondern über `atexit`. Der
SIGTERM-Handler setzt nur ein Flag und ruft die Handler-Kette weiter; alles
Lock-Nehmende passiert außerhalb des Signalkontexts. Der Grund steht im
Moduldocstring: `gevent.signal.signal()` delegiert für jedes Signal außer
SIGCHLD an die ungepatchte stdlib, der Handler läuft also im echten
CPython-Signalkontext, während `threading.Lock` nach `patch_all()` ein
kooperatives Semaphore ist. Unterbricht das Signal ausgerechnet das Greenlet,
das `RunRegistry._lock` hält, kommt genau dieses Greenlet nie wieder zum Zug.

Daraus folgt eine Grenze, die der Hook nicht überschreitet: `atexit` läuft nur
bei einem regulären Interpreter-Shutdown. Wird der Worker nach Ablauf von
`graceful_timeout` per SIGKILL beendet, bleibt die Startup-Reconciliation beim
nächsten Start der Mechanismus, der die Jobs terminalisiert.

Registriert wird der Hook in `gunicorn.conf.py::post_worker_init`, nicht in
`create_app()` und nicht in `post_fork`. Unter `preload_app = True` läuft
`create_app()` im Master vor dem Fork, und gunicorns `Worker.init_process()`
setzt in `init_signals()` zuerst jedes Signal auf `SIG_DFL` zurück, bevor es
die eigenen Handler installiert — alles davor Registrierte ist danach weg.
`post_worker_init` ist der erste Hook nach diesem Reset und läuft im
Worker-Prozess. Der bestehende Handler wird dabei gekettet, damit gunicorns
`handle_exit` den Worker weiterhin beenden kann. Die Idempotenz-Sperren in
`process_shutdown` und `process_manager` hängen jetzt an der PID statt an
einem Bool, weil der geforkte Worker sonst das `True` des Masters erbt und
die Registrierung still überspringt.

Es entsteht kein neuer `TerminationReason`-Wert — `process_restart` wird
wiederverwendet, derselbe Wert, den die Reconciliation beim Neustart auch für
Runs setzt, die einen Prozessabsturz ohne SIGTERM nicht überlebt haben. Für
Debug-Modus mit Werkzeug-Reloader registriert sich der Handler nur im
Child-Prozess, um doppelte Registrierung zu vermeiden.

Wichtig, um keine Erwartung zu wecken, die der Code nicht einlöst: ein
vollständig persistierter `interrupted`-/Resume-Zustand entsteht dadurch
nicht. Der Job endet sichtbar und ehrlich als `failed`, nicht als
automatisch fortsetzbarer Zwischenstand. #1472 (Job-Queue mit eigenen Workern
für Out-of-Process-Ausführung) bleibt offen.

### Geändert

- **Frontend-Testrunner auf vitest 5.0.0** (von 4.1.11). Drei Kompatibilitätsanpassungen waren nötig, alle in Testcode, keine in Produktionscode:
  - jsdom exponiert `localStorage` jetzt als reinen Getter auf `Window` (wie echte Browser). Die Direktzuweisung in `useGraphRender.pinLayout.spec.ts` warf `TypeError: Cannot set property localStorage of [object Window] which has only a getter`; sie ist durch `Object.defineProperty` ersetzt.
  - `clearMocks` ist jetzt standardmäßig `true`. Der Side-Effect-Aufruf aus `main.ts` passiert in `beforeAll` und wurde vor dem ersten `it()` geleert, sodass die Aufrufzählung ins Leere lief. `main.spec.ts` hält die Zahl jetzt in `beforeAll` fest. Der neue Default bleibt bewusst aktiv — er verhindert Mock-Leakage zwischen Tests und wird nicht global ausgehebelt.
  - Der Routen-Integritätstest in `router/__tests__/index.spec.ts` bekommt ein eigenes `{ timeout: 30_000 }`. Das ist **keine** vitest-5-Regression: ein Differential-Lauf gegen vitest 4.1.11 auf `main` erzeugt denselben `Test timed out in 5000ms`, und dasselbe Timeout heilt ihn auch dort. Der Test löst Routen-Komponenten echt auf; die einzige nicht per `vi.mock` gestubbte View (`SimulationLiveView.vue`) braucht dafür gemessene ~2 s und lag damit schon vorher knapp unter dem 5-s-Default. Die Auflösung zu stubben wäre der falsche Fix — genau sie ist der Zweck des Tests.

### Behoben

- **`engines.node` und der Node-Gate in `install.sh` widersprachen dem Dependency-Tree.** vitest 5 verlangt `^22.12.0 || ^24.0.0 || >=26.0.0`; beide `package.json` deklarierten weiter `>=20.0.0`, `install.sh` ließ jeden Node ab Major 20 durch und das README versprach „Node.js >= 20". Eine saubere Installation nach README landete damit auf einer Laufzeit, die die Manifeste selbst ablehnen. Aufgefallen ist das nur im Review, nicht in der CI: die Workflows starten vitest ausschließlich über bun und richten nie Node ein, `engines` wird dort also nie erzwungen. Manifeste, Installer und README führen jetzt denselben Bereich; die ungeraden Majors 23 und 25 sind ausgeschlossen, weil sie keine LTS-Linien sind. Neuer Regressionstest `backend/tests/test_install_node_engine.py` prüft nicht die Zahl, sondern die Übereinstimmung zwischen `engines.node` und dem Bash-Gate — ein späterer Bump, der nur die Manifeste anfasst, wird damit rot. (Codex-P1 auf PR #1469)

  Wichtig für spätere Änderungen: `bun` wertet `engines` **nicht** aus — empirisch geprüft, ein `"node": ">=99.0.0"` installiert anstandslos durch. Der Bereich ist deshalb Dokumentation plus `install.sh`-Gate, keine vom Paketmanager erzwungene Schranke. Wer sich auf `bun install` als Schutz verlässt, hat keinen.

### Behoben

- Die Backend-Testsuite läuft in einem frischen Checkout ohne `.env` durch. `LLM_API_KEY` wird in `tests/conftest.py` per `setdefault` vorbelegt; zuvor hing die Suite an einer lokalen `.env` beziehungsweise am Job-Env der CI. Ein exportierter Key gewinnt weiterhin, damit Läufe gegen ein echtes Provider-Backend möglich bleiben.

### Behoben

- Ein hartes `max_llm_calls`-Budget wird bei paralleler Arbeit jetzt tatsächlich eingehalten, nicht nur angenähert. Ein bestandener `check_before_call()` reserviert einen Slot, und die Reservierung zählt wie ein verbrauchter Call, bis der Call verbucht ist — zuvor lasen alle gleichzeitigen Aufrufer denselben Vor-Aufruf-Stand und kamen durch. Zusätzlich deckelt die Persona-Generierung die Anzahl gleichzeitig gestarteter Worker auf das verbleibende Kontingent.
- Ein erschöpftes hartes Budget bricht die Persona-Stufe ab, statt drei Versuche lang zu warten und regelbasierte Ersatzprofile zu liefern. `BudgetExceededError` wird von den breiten Fehlerbehandlungen auf dem Persona-Pfad nicht mehr verschluckt.

### Changed (Radius-Skala durchgesetzt, Ablage-Titel nicht mehr hart gekuerzt — 2026-09-06)

- **56 hartkodierte `border-radius`-Werte im Frontend wurden auf die `--r-2`/`--r-3`/`--r-5`/`--r-pill`-Skala aus `tokens-v3.css` umgestellt**, je nach Semantik des gerundeten Elements (Chip/Tag/Badge/Kbd → `--r-2`, Button/Eingabe/Zeile → `--r-3`, Karte/Panel/Dialog/Drawer → `--r-5`, `999px`/`9999px` → `--r-pill`), nicht nach Pixelnaehe zum alten Wert. `50%`-Kreise und bewusste `0`-Werte blieben unangetastet. Drei Werte in `useReportExports.ts` (Standalone-HTML-Export ohne Zugriff auf `tokens-v3.css`) bleiben mit Begruendung hartkodiert.
- **Der Ablage-Titel in `useShelf.ts` wird nicht mehr bei 80 Zeichen mitten im Wort abgeschnitten.** Der volle `simulation_requirement`-Text landet im Datenmodell; Shelf-Zeile und Dossier-Ueberschrift kuerzen jetzt visuell per CSS (`text-overflow: ellipsis`) und tragen den vollen Text als `title`-Attribut fuer den Hover-Tooltip.

### Fixed (Visual-Audit-Restpunkte — Backend — 2026-09-06)

- **Task-Statusmeldungen liefern jetzt einen i18n-Schlüssel statt hartkodiertem Englisch:** `TaskManager.complete_task`/`fail_task` setzten `message="Task completed"`/`"Task failed"` — in einer deutschen Oberfläche unübersetzt sichtbar. `Task` trägt jetzt zusätzlich `message_key` (`"task.completed"`/`"task.failed"`); `message` bleibt als menschenlesbarer Fallback unverändert, ältere Consumer laufen nicht leer. Die Übersetzung selbst gehört ins Frontend (#1458).
- **`/api/status` liefert keinen rohen Exception-Text mehr:** Die drei Stellen (`_get_neo4j_status`, `_get_ollama_status`, `_get_disk_status`), die bislang `str(exc)` direkt in die HTTP-Antwort schrieben, geben jetzt einen strukturierten `StatusCheckError` mit geschlossenem Code (`unreachable` | `timeout` | `auth` | `unexpected`) zurück. Der rohe Text (Dateipfade, Hostnamen, Treiberdetails) landet nur noch im strukturierten Log — vorher ein Informationsleck und für ein Frontend unrenderbarer Traceback-Text. `SystemStatusOllama.error` und der Zod-Spiegel `frontend/src/contracts/systemStatusContract.ts` sind entsprechend nachgezogen. (#1458)

### Fixed

- Die Init-Zeile des `LLMClient` benennt jetzt zusaetzlich `provider_type`. Bisher
  loggten Aufrufer, die API-Key und Basis-URL selbst aufloesen und direkt
  durchreichen (etwa die Simulations-Konfigurationsgenerierung), ein
  `provider_id=unknown base_url=None` — bei `codex_cli` beides sachlich richtig,
  im Log aber nicht von einem fehlkonfigurierten Client zu unterscheiden. Die
  Provider-Erkennung selbst bleibt unveraendert; `provider_type` stammt aus
  derselben Aufloesung, aus der sich auch der Transport ergibt.
  Der Typ wird auch dann aufgeloest, wenn der Aufrufer den Schluessel
  selbst mitbringt und die aktive Konfiguration nur Modell oder Basis-URL
  beisteuert (Review-Nachbesserung).

Der Registry-Lookup und die Key-Aufloesung der Active-Config liegen dafuer jetzt
als Modul-Helfer neben `LLMClient` statt inline im Konstruktor — sonst haette der
zweite Lookup `__init__` ueber die Radon-Obergrenze aus `radon-allowlist.txt`
getrieben (gemessen 38, erlaubt 34; jetzt 31).

### Fixed

Ein noch nicht vorhandener Evidence-Endpunkt (HTTP 404, solange die Evidenzkarte serverseitig noch nicht geschrieben ist) wurde im Bericht faelschlich als "Schema-Mismatch" gemeldet, obwohl kein Zod-Fehler vorlag. `loadEvidence()` in `Step4Report.vue` unterscheidet jetzt anhand des Fehlertyps: eine geworfene `ApiError` (HTTP-/Transport-Ebene) fuehrt weiterhin in den bestehenden Retry mit Backoff und Budget, ein echter Zod-Parse-Fehler bleibt ein Schema-Mismatch.

Nachbesserung (Codex-Review PR #1456): Innerhalb der `ApiError`-Faelle ist HTTP 422 mit Code `contract_violation` (die persistierte Evidence-Map ist auch nach Migration nicht vertragskonform, siehe `backend/app/api/report.py`) kein transienter Zustand wie 404. Ein Retry wuerde denselben Vertragsverstoss zehn Minuten lang verschweigen — 422 wird deshalb wie ein Zod-Fehler behandelt: sichtbar als Schema-Mismatch, ohne Retry.

### Fixed

Die Persona-Generierung protokollierte abgelehnte Kandidaten widersprüchlich: Auf die Zeile „Entitaet abgelehnt name=… reason=…" folgte in der nächsten Zeile trotzdem „Successfully generated persona“ für dieselbe Entität, weil die Fortschrittsmeldung nur zwischen Notprofil (Fehlerfall) und Erfolg unterschied, nicht aber danach, ob überhaupt ein Profil entstanden war. Die Meldung nennt für abgelehnte Kandidaten jetzt wahrheitsgemäß Name und Ablehnungsgrund statt eines falschen Erfolgs, und am Ende der Generierung steht zusätzlich eine Summenzeile mit der Bilanz aus angetretenen Kandidaten, Ablehnungen und tatsächlich erzeugten Personas, damit eine Lücke wie „15/20 Personas“ nicht mehr aus dem Nichts kommt.

### Fixed (Persona-Mindestanzahl-Gate nennt jetzt Kandidaten- und Defizitzahl — 2026-09-06)

- **Die Fehlermeldung „Persona-Mindestanzahl nicht erreicht: 15/20 Personas vorhanden.“ ließ den Nutzer im Dunkeln, wenn der Unterlauf gar kein Fehlschlag war.** Ein Produktionslauf zeigte: 23 Persona-Kandidaten nach Dedup, 8 davon durch das Eignungs-Gate korrekt als technische Artefakte abgelehnt (z. B. „digitaler Zwilling“), 15 zugelassene Personas — unter dem Floor von 20. Die Meldung ließ diesen Zusammenhang nicht erkennen.
- **Review-Nachbesserung:** Die Differenz aus Kandidaten- und Personazahl wurde zunächst als Ablehnungszahl des Eignungs-Gates formuliert. Das ist nicht in jedem Fall zutreffend — `state.entities_count` wird bei einem Branch unverändert von der Quelle kopiert (`branching_service.py::create_branch`), während sowohl `persona_removals` (`_apply_persona_overrides`) als auch die manuelle Persona-Löschroute nur `reddit_profiles` mutieren, nicht diesen Zähler. Ein Branch mit 20 kopierten Kandidaten und einer absichtlich entfernten Persona hätte damit als „1 vom Eignungs-Gate abgelehnt“ gegolten, obwohl keine Ablehnung stattfand; auch Reserve-Backfills können die Differenz von der tatsächlichen Ablehnungszahl des Generators abweichen lassen.
- **Die Meldung benennt die Differenz deshalb als Defizit mit mehreren möglichen Ursachen** (Eignungs-Gate oder nachträgliche Entfernung), statt eine unbelegte Ursache zu behaupten. Der ursprüngliche Zweck — dem Nutzer zeigen, dass die 15 nicht aus dem Nichts kommen — bleibt erhalten. Die tatsächliche Ablehnungszahl des Generators wird an dieser Stelle weiterhin nicht persistiert (Folgearbeit).
- **Die Bezugsgröße des Gates bleibt unverändert:** Es vergleicht weiterhin die tatsächlich zugelassenen Personas gegen den Floor (`MIN_PERSONA_TABLE_ROWS`, Default 20) — die Schwelle selbst wurde nicht angetastet.

### Fixed

Die Persona-Dublettenerkennung vor dem Agenten-Cap erkannte deutsche Oberflächenvarianten desselben Stakeholders nicht: „digitaler Zwilling", „der digitale Zwilling" und „digitale Zwilling" zählten ebenso als drei getrennte Gruppen wie „Lernplattform" und „die Lernplattform" — ein Produktionslauf verlor dadurch nur eine von acht tatsächlichen Dubletten und der Graph zersplitterte in mehrere Knoten für dasselbe Konzept. `_entity_identity_key` in `backend/app/services/prepare_service.py` entfernt jetzt einen führenden bestimmten oder unbestimmten Artikel und gleicht einfache Adjektivendungen (`-er`/`-es`/`-em`/`-en`/`-e`) an, sofern der verbleibende Wortstamm mindestens vier Zeichen lang ist — bewusst konservativ, damit ähnliche, aber fachlich unterschiedliche Stakeholder wie „Lehrkraft" und „Lehrkräftevertretung" oder „Lernplattform" und „Lernender" getrennt bleiben; das letzte Wort einer Bezeichnung (das Kopf-Nomen) wird nie gestemmt. Nachbesserung (Review-Finding auf PR #1453): nur noch das Token unmittelbar vor dem Kopf-Nomen kommt für die Stemmung infrage, nicht mehr jedes nicht-letzte Token. Sonst kollabierten Nomen-Paare wie „Unternehmen der Region" und „Unternehmer der Region" fälschlich auf denselben Stamm, weil beide zufällig auf eine Adjektivendung enden, obwohl sie durch ein trennendes Wort („der") nicht unmittelbar vor dem Kopf-Nomen stehen und damit strukturell keine Adjektive sein können.

### Changed

- **Die Agent-Config-Batches der Simulationskonfiguration laufen jetzt parallel statt sequentiell.** Produktionsmessung (armserver): drei Batches über 23 Entities kosteten sequentiell ~81s (28s + 27s + 26s), weil sie disjunkte Entity-Bereiche generieren, aber nacheinander auf den Abschluss des jeweils vorherigen warteten, obwohl sie voneinander unabhängig sind. Die Zeit- und Event-Konfiguration sowie die Plattform-Konfiguration bleiben sequentiell — sie wurden geprüft und haben entweder eine echte Abhängigkeit (Skeptiker-Quote und Initial-Post-Zuordnung konsumieren die fertigen Agent-Configs) oder liefern keinen relevanten Parallelitätsgewinn (Plattform-Config macht keinen LLM-Call). Der Produktionsserver läuft unter `gunicorn -k gevent` mit monkey-gepatchten Sockets; ein naiver `ThreadPoolExecutor` reißt dort Verbindungen ab, weil OS-Threads nicht den gevent-Hub des aufrufenden Greenlets teilen. `SimulationConfigGenerator` erkennt daher aktive Gevent-Patches über `gevent.monkey.is_module_patched("socket")` und nutzt in diesem Fall den kooperativen `gevent.pool.Pool`, andernfalls einen `ThreadPoolExecutor` — analog zum bereits etablierten Muster in `oasis_profile_generator.generate_profiles_from_entities`. Ergebnisreihenfolge und Entity-Zuordnung bleiben deterministisch identisch zur sequentiellen Variante, ein Fehler in einem Batch propagiert weiterhin nach außen statt still verschluckt zu werden.

### Removed (UI-Redesign 2026-09, PR 10 Legacy-Abbau — 2026-09-06)

- **Zweite Hülle entfernt:** das Shell-Flag `useShellVariant` ist entfallen. Es hielt neben der Ablage eine zweite Navigationswelt („classic") am Leben — genau die zwei Navigationsmodelle nebeneinander sind der erste Befund des Audits. Der Default stand seit Block B3 ohnehin auf „dossier"; `/` leitet jetzt statisch auf `/ablage`. `/dashboard` bleibt als eigene Route erreichbar, nur nicht mehr als alternativer Einstieg. (#1449)
- **Unerreichbare Views gelöscht:** `RunsAppShellView.vue`, `RunsView.vue`, `RunsDashboard.vue` und `HistoryView.vue` samt ihrer Specs. Seit PR 8 leiten `/runs` und `/v4/history` auf die Ablage um; die Views waren danach von keiner Route mehr erreichbar. Mit ihnen entfallen die dadurch verwaisten `HistoryDatabase.vue`, `AppFooter.vue` (der im Audit gerügte Website-Footer in der Shell) und `AgoraGlyph.vue`. Die Redirects selbst bleiben als Deep-Link-Kompatibilität. (#1449)

### Offen aus PR 10 (bewusst nicht in diesem PR)

- `/runs/:id` zeigt weiterhin auf `RunDetailAppShellView`/`RunDetailView`, weil `usage-totals` (Verbrauchsanalyse) und `budget-exceeded-banner` nur dort existieren. Der Umstieg ist eine Feature-Migration, keine Löschung: erst muss der Kennzahlstreifen des Dossiers beide Blöcke tragen. Zusätzlich ist dabei die Schlüsselauflösung zu lösen — `groupJobsByEndeavor` schlüsselt Läufe über `simulation_id`/`project_id`, nicht über die Registry-ID, ein Deep-Link mit `run_…` fände sein Objekt sonst nicht.
- `StepSimulationFeedView.vue` bleibt, weil der Feed ein **Tab** innerhalb von `StepSimulationView` ist. Ihn auf die Vollbild-Live-Ansicht aus PR 7 umzubiegen hiesse, den Tab-Rahmen zu verlassen — auch das eine Verhaltensänderung, die eine eigene Entscheidung braucht statt in einen Lösch-PR mitgenommen zu werden.

### Fixed (UI-Redesign 2026-09, Nachtrag zu PR 8 — 2026-09-06)

- **Fortschritt abgeschlossener Läufe:** die Fortschrittsspalte der Läufe-Tabelle las ihren Wert aus `ShelfObject.active`, das bei abgeschlossenen, gescheiterten und gestoppten Läufen `null` ist — die Spalte blieb also für genau die Zeilen leer, die in einer Läufe-Tabelle die Mehrheit stellen. `ShelfObject` trägt den Fortschritt jetzt unabhängig vom Aktiv-Zustand, gespeist aus `RunDetail.progress` des jüngsten Jobs. (#1448)
- **Tabellenzeilen per Tastatur bedienbar:** `DataTable.rowClick` hing bisher nur an `@click`, und eine `<tr>` ist nicht fokussierbar — die Zeilenauswahl war für Tastaturnutzer schlicht nicht erreichbar. Mit gesetztem `rowClick` bekommt die Zeile jetzt `tabindex="0"`, reagiert auf Enter und Leertaste und trägt einen sichtbaren Fokusring. Das behebt den Mangel in allen drei Verbrauchern zugleich (Ablage-Tabelle, `ActiveRunsCard`, `RecentReportsCard`). Tastendrücke aus Bedienelementen innerhalb einer Zeile lösen die Zeilenauswahl bewusst nicht aus — sonst führte Enter auf „Vergleichen" oder dem Stopp-Knopf beides zugleich aus, weil `@click.stop` nur den späteren Klick aufhält, nicht den `keydown`. Bewusst ohne `role="button"`: das nähme der Zeile ihre Tabellensemantik. (#1448)
- **Wertloser Test korrigiert:** die Zusicherung für einen ungültigen `?filter=` steckte in `expect(async () => …).not.toThrow()`. `toThrow` ist synchron, sieht ein Promise statt eines Wurfs und ist zufrieden — der Rumpf wurde nie ausgewertet, ein Fehlschlag wäre eine unbehandelte Rejection geblieben. Jetzt direkt awaited. (#1448)

### Changed (UI-Redesign 2026-09, PR 8 Läufe-Tabelle — 2026-09-06)

- **Läufe leben in der Ablage:** `/runs` leitet auf `/ablage?filter=lauf` um, `/v4/history` auf `/ablage?filter=jobs`. `/runs/:id` bleibt bewusst die Detailansicht: `usage-totals` (Verbrauchsanalyse) und `budget-exceeded-banner` gibt es nur in `RunDetailView.vue`, das Dossier trägt beides nicht — ein Redirect hätte Verbrauch und Budgetabbruch eines Laufs ersatzlos unzugänglich gemacht. Der Umstieg gehört in PR 10 und setzt voraus, dass der Kennzahlstreifen des Dossiers die beiden Blöcke vorher übernimmt. Die Ablage wertet `?filter=` jetzt aus und schreibt den gewählten Filter per `router.replace` zurück in die Query, damit der Zustand teilbar ist. Die Legacy-Views `RunsAppShellView.vue` und `HistoryView.vue` bleiben vorerst liegen — ihre Löschung gehört in PR 10. (#1447)
- **Tabellenmodus in der Ablage:** für die Filter „Läufe" und „Alle Jobs" lässt sich zwischen Zeilenliste und dichter Tabelle umschalten; die Wahl merkt sich `localStorage` pro Browser. Die Tabelle ist die `DataTable` aus PR 5 (36px-Zeilen, Label-Spaltenköpfe ohne Versalien, rechtsbündige Zahlen in Mono, Auswahl als Kupferkante). Spalten für Läufe: Vorhaben, Zustand, Fortschritt, Personas, Angefasst, Nächster Schritt; für Jobs: Typ, Zustand, Meldung, Fortschritt, Angefasst. Zeilenklick wählt das Objekt aus wie in der Liste. (#1447)
- **Zwei bewusste Abweichungen von der Audit-Vorgabe (Zeile 137/146), beide im Code begründet:** Die Spalten „Aussagen", „Belege" und „Lücken" fehlen, weil ihre Werte aus `getReportEvidence(reportId)` stammen — ein Abruf pro Zeile, also ein N+1 im Listenpfad; sie bleiben im Kennzahlstreifen des Dossiers (PR 4). Statt der vorgesehenen Zwei-Läufe-Auswahl trägt jede Läufe-Zeile eine Aktion „Vergleichen", die zu `CompareV4` führt: `CompareView.vue` vergleicht Branches *einer* Simulation (`listSimulationBranches`), ein Vergleich zweier beliebiger Läufe hat keinen Endpunkt, der ihn einlösen würde. (#1447)
- **Barrierefreiheit:** der horizontal scrollende Jobs-Kasten der Ablage ist jetzt per Tastatur erreichbar (`role="region"`, `tabindex="0"`, Name, sichtbarer Fokusring). Der Befund (`scrollable-region-focusable`, serious) lag dort schon vorher, wurde aber von keinem Gate berührt, solange keine geprüfte Route auf den Jobs-Filter zeigte — der `/v4/history`-Redirect tut das jetzt. (#1447)

### Changed (UI-Redesign 2026-09, PR 6 Leseumgebung "Bericht lesen" — 2026-09-06)

- **Dreispalten-Leseumgebung für den abgeschlossenen Bericht:** `Step4Report.vue` rendert einen fertigen Report (`phase === 2 && reportHtml`) jetzt über die neue `ReportReader.vue` statt der bisherigen `ReportFinalView.vue` — Outline links (`ReportOutline.vue`, `role="tablist"`/`role="tab"`, Tastaturnavigation via Pfeiltasten/Home/End), Serif-Lesespalte in der Mitte (Newsreader, 62ch, `--fs-prose`/`--lh-prose`) und Belegrand rechts (`ReportEvidenceRail.vue`, 320–336px). Behebt Audit-Problem #4 ("Bericht als Formular-Stack … keine Leseumgebung"). `ReportFinalView.vue` und `ReportEvidencePanel.vue` sind zusammen mit ihren dedizierten Specs entfernt — ihre Funktion (Markdown-Rendering, Claims/Belege/Hypothesen-Anzeige, Export- und Branch-Aktionen) übernimmt vollständig `ReportReader.vue`/`ReportEvidenceRail.vue`, die vorhandenen `ReportBranchControls.vue` und `ReportRedTeamSection.vue` wurden wiederverwendet statt neu gebaut. (#1446)
- **Confidence als Wort statt nackter Prozentzahl:** der Belegrand zeigt für jeden Claim ein Confidence-Wort (`spekulativ`/`niedrig`/`mittel`/`hoch`/`verifiziert`) aus `step4.reader.confidence.*`, dazu die daran gebundenen Belege (Typ, Quelle, Zitat, Anker-Link), Datenlücken und — separat abgegrenzt — Hypothesen des Abschnitts. Behebt die Audit-Rüge zu "Confidence als '0% · spekulativ'-Chip ohne Erklärung". (#1446)
- **Overlay "Neu generieren" statt dauerhaftem Formular:** sobald ein Bericht angezeigt wird, wandern `ReportModelControls.vue`/`ReportModeControls.vue` aus dem Lesefluss in ein Overlay (`role="dialog"`, Escape schließt, Fokus wandert beim Öffnen/Schließen), das über einen Button im Reader-Header geöffnet wird. Vor dem ersten Report (Bestätigungs-/Generierungsphase) bleibt die bisherige inline Modell-/Modus-Auswahl unverändert. (#1446)
- Neue Testid-Konstanten `ReportReaderTestId` (`contracts/testIds.ts`) und i18n-Keys unter `step4.reader.*` (`de.json`/`en.json`).

**Bekannte Lücke:** die vormalige `ConfidenceBadge`-Anzeige (Prozent + Wort) in `ReportOutlinePanel.vue` bleibt für die laufende Generierung (Phase 0/1) unverändert bestehen — nur die abgeschlossene Leseansicht wurde migriert, siehe `Step4Report.spec.ts`.
- **Belegrand vollständig:** Belege ohne optionales `quote` zeigen jetzt ihren Pflicht-`snippet` statt nur den Quellennamen, und der Hypothesen-Block liest zusätzlich `hypotheses_appendix` — die serverseitig auf fünf gedeckelte Liste hatte den Überhang (bis 50 Einträge) bisher verschluckt, auch im Anhangszähler der Outline. (#1446)
- **Leseumgebung ohne Leerabschnitte:** Outline und Abschnitts-HTML werden in `composables/useReportReaderView.ts` gemeinsam bestimmt. Ein aus der Persistenz geladener Bericht (`_status_from_persisted_report`) liefert `markdown_content` als Ganzes, aber keine `generated_sections`; die getrennt gewählten Fallbacks ergaben dort eine Outline mit allen Abschnitten neben einem einzigen HTML-Block, sodass jeder Abschnitt außer dem ersten leer aufging. Jetzt trägt in diesem Fall genau ein Sammelabschnitt den vollständigen Bericht. (#1446)

### Added (UI-Redesign 2026-09, PR 7 Simulation live — 2026-09-06)

- **Simulation-live-Instrument:** neue Route `/v4/simulation/:simulationId/live` (`SimulationLiveView`) ersetzt den bisher shell-losen, im Audit mit 2/10 bewerteten Zustand von Step 3 (Text + Button, leerer Feed) durch ein Vollbild-Instrument — Kopfzeile mit Runde x/y, vergangener Zeit, s/Runde sowie echten Fortsetzen-/Pausieren- und Abbrechen-Aktionen; eine Rundenachse markiert erledigte, laufende und geplante Runden; vier Bahnen (Akteure, Reddit, Twitter, System und Ereignisse) zeigen den Lauf live. Datenquellen sind ausschließlich bestehende Endpunkte: `getRunStatusDetail` (Runde, Pause-Status, `started_at`/`completed_at` für die vergangene Zeit und s/Runde — beide in echten Sekunden, damit ein pausierter oder frisch neu geladener Lauf nicht 00:00 anzeigt), `useSimFeed`/`useEventStream` (Zod-validierter Post-Strom für Akteure/Reddit/Twitter, wiederverwendet aus `StepSimulationFeedView`, chronologisch zusammengeführt), `getRunEvents` (`/api/runs/<id>/events`) und `getRunUsage` (`/api/runs/<id>/usage`) für die System-Bahn. Die dafür nötige Registry-Lauf-ID wird über `GET /api/runs?simulation_id=<id>` aufgelöst — der Status-Detail-Payload (`SimulationRunState.to_dict()`) führt kein `run_id`. Bewusst weggelassen, weil aus den erlaubten Quellen nicht ableitbar: eine Aktivitätshöhe pro Runde auf der Rundenachse (`PostCreatedEvent` trägt kein `round_num`), „Aufkommende Themen" (kein Themen-Extraktions-Endpunkt) und Eingriffsaktionen wie „Ereignis einspeisen"/„Budget anheben" (kein Endpunkt gelistet). Neue reine Ableitungsfunktionen in `composables/useSimulationLiveMetrics.ts` (Rundenachse, s/Runde, Akteurs-Statistik) sind unabhängig von Mount/Router testbar. (#1445)

### Changed (UI-Redesign 2026-09, PR 5 Control-Primitives — 2026-09-06)

- **Buttons auf vier Varianten reduziert:** `.btn` nutzt jetzt `--r-3` (6px) statt Pill-Radius; `primary`/`secondary`/`ghost`/`danger` bleiben, `tinted`/`accent`/`info`/`plasma`/`glass` sind gestrichen — `info`/`plasma` trugen das repo-fremde `--status-purple` in die UI, `glass` einen `backdrop-filter`. `ghost` ist kein Akzent mehr (Text statt Kupfer), `danger` bekommt einen Coral-Rahmen statt getönter Fläche, Controls tragen keinen Schatten mehr. Der `ButtonVariant`-Typ in `v4/forms/Button.vue` erzwingt die vier Varianten jetzt auch statisch. Die zwei Aufrufer von `variant="accent"` in `SettingsSectionPanel.vue` stehen jetzt auf `primary`. (#1444)
- **Select-Primitive vereinheitlicht:** `v4/forms/Select.vue` ist jetzt das kanonische Select — Radius `--r-3`, Inset-Surface-Hintergrund, optionale `label`/`required`-Props im `label`-Typo-Stil (Satzschrift, kein Uppercase) und ein `aria-label`-Fallback für den axe-core-Fix aus Issue #838. Das sichtbare Label ist per `for`/`id` (`useId()`) mit dem Steuerelement verknüpft, sodass ein Klick darauf fokussiert; `required` setzt jetzt die native Validierungs-Constraint, statt nur einen Sternchen-Marker zu zeichnen. `components/ui/Select.vue` ist gelöscht, seine zwei Verwender (`EnvSetupModelPanel.vue`, `ReportModeControls.vue`) migriert. Rohe native `<select>`-Elemente bleiben unangetastet (folgen in PR 6–8), bekommen aber über eine neue globale `select`-Basisregel in `global.css` Radius, Hairline, Inset-Surface und einen eigenen Chevron ohne Markup-Änderung. (#1444)
- **Tabellen-Primitive:** `.dt-th` verliert Uppercase/0.04em-Tracking zugunsten des `label`-Typo-Stils (Satzschrift, 0.02em, Gewicht 500). Body-Zeilen sind jetzt 36px hoch (compact 28px) mit Hairline unten, Hover auf dem Surface-Hover-Token; das vertikale Zellpadding entfällt, damit die Zeilenhöhe die Dichte-Spec trifft statt sich mit dem Padding zu addieren. Neues Prop `rowSelected` markiert eine Zeile mit Accent-Tint, 2px-Kupfer-Kante links und `aria-current` — nicht `aria-selected`, das auf `<tr>` nur in einem `role="grid"` zulässig wäre. Rechtsbündige Zellen (`dt-cell--right`) bekommen `tabular-nums`; die Mono-Familie bleibt an `col.mono` gebunden, weil rechtsbündig nicht zwangsläufig numerisch bedeutet. (#1444)

### Changed (UI-Redesign 2026-09, PR 4 Lauf + Bericht anreichern — 2026-09-06)

- **Kennzahlstreifen erweitert:** `Dossier.vue`s KPI-Reihe (jetzt semantisch als `dl`) zeigt bei einem Lauf zusätzlich Personas (`RunSummaryContract.persona_count`) und Jobs (Anzahl gruppierter Jobs), bei einem Bericht Abschnitte, Belege (`Report.evidence_sections`) und Aussagen (Claims aus der Evidence-Map) — jede Kachel nur, wenn das Feld tatsächlich bekannt ist. (#1442)
- **Bestandteile mit Zahl + Link:** ein Lauf zeigt jetzt "Akteure" (Personenzahl, Link zu den Personas) und "Ausgabe" (Belegzahl des verknüpften Berichts, Link zum Bericht) — beide aus bereits geladenen Daten (`obj.jobs`, `obj.personaCount`) plus einem bestehenden `getReport`-Aufruf für die Ausgabe, kein neuer Endpunkt. (#1442)
- **Jobs-Zeitleiste:** neue Sektion im Lauf-Dossier — alle Jobs des Vorhabens als `<ol>`, neuestes zuerst, direkt aus `useShelf.buildShelfObjects` (kein Nachladen). (#1442)
- **Bericht-Anreicherung:** Confidence-Verteilung (Claims je Vertrauenslabel) und Red-Team-Befunde als eigene Abschnitte, gespeist aus dem bestehenden `GET /api/report/<id>/evidence`-Endpunkt (Evidence-Map) bzw. direkt aus dem bereits geladenen Report-Contract. (#1442)
- **Bewusst weggelassen (kein Contract-Feld ohne Fabrikation):** "Runden" im Lauf-Kennzahlstreifen (kein zuverlässiges typisiertes Feld auf einem abgeschlossenen Run ohne einen zusätzlichen Live-Status-Endpunkt) und "Budget" (RunBudgetStatus ist ein mehrdimensionales Verbrauchsobjekt — Tokens/Kosten/Zeit/Calls —, keine einzelne Kennzahl im Contract; eine korrekte Darstellung gehört in einen eigenen Slice statt einer zusammengefassten Schätzzahl). "Quellenumfeld" als Lauf-Bestandteil fehlt ebenfalls: `linked_ids` trägt nur `project_id`, keine `graph_id` — ein Entitäten-/Relationszähler bräuchte einen zusätzlichen Projekt→Graph-Nachschlag. (#1442)

### Changed (UI-Redesign 2026-09, PR 3 Ablage-Übersicht + Zeilen — 2026-09-06)

- **Dossier-Übersichtszustand:** `Dossier.vue` zeigt ohne Auswahl nicht mehr nur einen Satz, sondern eine Übersicht aus vier Abschnitten — "Braucht dich" (Objekte mit `nextAction.kind === 'warn'`), "Läuft gerade" (aktive Läufe mit Fortschrittsbalken, Pause/Abbrechen), "Zuletzt fertig" (jüngste abgeschlossene Objekte) und ein kompakter Systemstatus (Neo4j/Ollama über das bestehende `useSystemStatus`/`/api/status`). Primäraktion "Quelle ablegen" führt wie die Ablage-Zeile zum Dashboard. Alle Daten kommen aus dem bereits geladenen `useShelf()`-Zustand, kein zweiter Request. (#1441)
- **Weiter-Aktion pro Kind:** Personasatz-Zeilen hatten bisher keine Weiter-Aktion (nur der Dossier-Kopf konnte einen Lauf starten). Die neue Composable `useStartFromPersona.ts` teilt diese Logik zwischen `Shelf.vue`-Zeile und `Dossier.vue`-Kopf; ein Fehlschlag zeigt jetzt eine sichtbare Fehlermeldung an der Zeile statt still zu bleiben. (#1441)
- **Datum bei älteren Objekten:** `formatShelfDate` (`useShelf.ts`) unterscheidet jetzt heute (Uhrzeit), gestern ("Gestern"/"Yesterday") und älter (tt.mm.) — vorher fiel jedes Nicht-Heute-Datum auf tt.mm. ohne "Gestern"-Zwischenstufe. (#1441)
- **Filter als Text-Tabs:** die Filterleiste in `Shelf.vue` ist jetzt `role="tablist"`/`role="tab"` mit `aria-selected` statt `role="group"`/`aria-pressed`; die Labels stehen in Satzschrift statt Mono-Versalien, die Zähler bleiben in Geist Mono. (#1441)

### Fixed (LLM-Routing-Einstieg vollständig lokalisiert — 2026-09-06)

- Die LLM-Routing-Einstellungsansicht löst Seitentexte, Run-Auswahl, Feldlabels, Aktualisieren-Aktion, Leerzustand und Fallback-Ladefehler jetzt über `vue-i18n` auf. Deutsche und englische Texte liegen unter `settings.v4.llmRouting.*`; ein englischer Render-Regressionstest verhindert, dass die englische Oberfläche erneut deutsche Literale zeigt. (#1440)

### Changed (UI-Redesign 2026-09, PR 9 Einstellungen-Overlay — 2026-09-06)

- **Sektionsliste statt Pro-Seite-Breadcrumbs:** neue Komponente `SettingsOverlay.vue` fasst alle acht `/settings/*`-Routen unter einem gemeinsamen Kopf ("Einstellungen" + "Zurück") mit linker Sektionsliste zusammen (Allgemein, Integrationen, Profil, API-Schlüssel, LLM-Anbieter, Embedding-Konfiguration, LLM-Routing, Audit-Logs). Ersetzt die bisherigen `:breadcrumbs="BREADCRUMBS"`-Props (Audit-Punkt 12, "Breadcrumb 'Settings / General' über Titel 'Allgemein'"). Bewusst nicht umgesetzt: ein echtes, App.vue-weites Overlay über der eingefrorenen Arbeitsfläche (Vorlage `08-einstellungen.html`) — der Router tauscht `router-view` heute komplett aus, das bräuchte Eingriffe ausserhalb von Settings-Views/-Komponenten. (#1439)
- **LLM-Provider als Liste statt Card-Grid:** `LlmProvidersView.vue` zeigt Provider jetzt als kompakte, semantische Liste (`<ul role="list">`/`<li>`/`<button aria-current>`, kein `role="listbox"`/`"option"`); genau ein Provider steht im Detail-Formular (Audit-Punkt 9, "3×3 Cards mit acht Primärbuttons"). Aktionen (Speichern/Testen/Modelle laden/Trennen) nutzen jetzt die gemeinsame `Button`-Komponente (primary/secondary/danger) statt ad-hoc `.llm-btn`-Klassen; der Ladeindikator hängt nur noch am tatsächlich laufenden Aktions-Button, nicht an allen vieren gleichzeitig. (#1439)
- Neue Testids `SettingsOverlayTestId`, `LlmProviderListTestId` in `contracts/testIds.ts`; neue i18n-Schlüssel unter `settings.v4.overlay.*` und `settings.v4.llmProviders.list.*` (de/en). (#1439)

### Fixed (Review-Befunde PR #1439 — 2026-09-06)

- Golden-Gate-Accessibility-Smoke schlug auf `/settings/llm-providers` fehl: `aria-required-children`/`aria-required-parent` (Listbox-Muster ohne direkte `role="option"`-Kinder), `listitem` (semantisch ungültige `<li>` unter `role="listbox"`) und `color-contrast` (`--text-tertiary` auf dem Kupfer-Tint der Auswahl). Behoben durch die Umstellung auf `role="list"` + `aria-current` und `--text-secondary` für den Provider-Typ der ausgewählten Zeile. (#1439)

### Fixed

- Persona-Vorbereitung akzeptiert CLI-Provider mit lokaler Anmeldung ohne HTTP-API-Key. Die Transportart kommt aus der Provider-Registry; HTTP- und unbekannte Provider werden weiterhin auf fehlende Schlüssel geprüft. Modellwahl und Stage-Routing bleiben unverändert. (#1438)

### Fixed

- Dashboard: Eine fehlgeschlagene globale Ollama-Probe sperrt neue Runs nicht mehr. Profile, zentrale Modellrouten und explizite Provider-Connections werden weiterhin beim Ausführen im Backend aufgelöst. Neo4j- und Profil-Ladebedingungen bleiben erhalten; der deaktivierte Startknopf benennt den zutreffenden Grund. (#1437)

### Changed (UI-Redesign 2026-09, PR 2 Chrome bereinigen — 2026-09-05)

- **LOGS-FAB entfernt:** globale, feste FAB in `App.vue` ersetzt durch ein 20px-Icon "Protokoll" in beiden Kopfzeilen (`Topbar.vue`, `ShellRoot.vue`); Zustand + Ctrl/Cmd+Shift+L-Shortcut leben jetzt in `useLogDrawer.ts` (Single Source of Truth, analog `useCommandPalette.ts`). (#1436)
- **⌘K-Chip vereinheitlicht:** beide Kopfzeilen zeigen jetzt "Suchen ⌘K" mit identischem Markup/Styling (`.kbd`-Klasse, Tokens statt hartkodierter Werte); vorher Icon-only in `Topbar.vue`, Mono-Chip in `ShellRoot.vue`. (#1436)
- **Brand-Ring statt Glyph:** `AgoraBrand.vue` bekommt `mode="ring"` (reine CSS-Form, kein Asset) — `Sidebar.vue` zeigt jetzt den Kupfer-Ring statt des blau-violetten SVG-Glyphen. (#1436)
- **"?"-Fallback entfernt:** `UserMenu.vue` zeigte ohne Profil ein Fragezeichen als Avatar-Initiale — fällt jetzt zuerst auf den Benutzernamen, sonst auf ein neutrales Personen-Symbol zurück. Zusätzlich ein "Hilfe"-Eintrag im Menü (README-Anker, neuer Tab, opener-los). (#1436)
- **`/feed` im Shell:** `StepSimulationFeedView.vue` war shell-los ohne Rückweg — jetzt in `AppShell` + `PageHeader` gewrappt, analog `StepReportView.vue`, mit Rückweg-Breadcrumb zur Simulations-Pipeline. (#1436)

### Added (Screenshot-Vergleich PR 1 (Tokens) bei 1440/1024 — 2026-09-05)

- **Nachgereichter Vorher/Nachher-Vergleich für #1427:** `docs/ui/premium-redesign-2026-09/02-screenshot-vergleich-pr1.md` misst Body-Typografie, Karten-/Button-Radius, Feldlabel-Stil und Logo-Akzentfarbe je Route (`getComputedStyle`) und zeigt zehn Composite-Screenshots (`shots/vergleich-pr1/`, vorher/nachher nebeneinander) bei 1440×900 und 1024×768 — beide Zustände liefen gegen denselben Backend-Container und denselben Stub-Lauf, nur das ausgelieferte Frontend-Bundle wurde getauscht. (#1427)

### Changed

- Dependabot pflegt Frontend-Abhängigkeiten jetzt über das `bun`-Ökosystem statt
  `npm`. Das npm-Ökosystem aktualisierte nur `package.json` und ließ `bun.lock`
  stehen; der Frontend-Smoke-Gate brach mit „lockfile had changes, but lockfile
  is frozen" ab und jedes Frontend-Update musste manuell nachgezogen werden.
  Ein Wächtertest (`tests/config/test_dependabot_config.py`) verhindert den
  Rückfall. (#1428)
- Der bewusst unquotierte `$PIP_AUDIT_FLAGS`-Aufruf in `ci.yml` trägt eine
  begründete `shellcheck disable=SC2086`-Direktive. reviewdog/actionlint hängte
  den Befund bisher an jeden PR, der `ci.yml` berührte, und blockierte den
  Merge über die Konversationsauflösung. (#1428)

### Changed (UI-Redesign 2026-09, Audit + PR 1 Tokens — 2026-09-05)

- **Visuelles Audit der gerenderten App** mit Scores, Top-15-Problemen, Designrichtung, Design-System und 10-PR-Plan unter `docs/ui/premium-redesign-2026-09/` (Ist-Screenshots, Vorlagen, drei Zielversionen für Ablage/Simulation/Bericht als HTML). (#1427)
- **`tokens-v3.css` entkernt:** acht Typo-Rollen (`--fs-display` fluid … `--fs-mono-lg`), Radius-Skala 4/6/10/pill, semantische Namen (`--bg-*`, `--border-*`, `--text-muted`, `--accent-live`, `--status-warning`), Motion-Tokens. Body-Text 15 → 14 px. (#1427)
- **`tokens-compat.css` abgespalten:** nur noch referenzierte v1/v2-Aliase, 75 tote Tokens (Mesh, Grid, Glow, Paper, Ink-Skala) entfernt. (#1427)
- **Label-Stil:** Tabellenköpfe, KPI-Labels, Abschnitts-Kicker, Menü-Labels, `.meta` in Satzschrift ohne Versalien; Mono nur noch für IDs und Zahlen. (#1427)
- **Logo-Glyph** auf Kupfer statt Blau. (#1427)

### Fixed

- Simulationsrunden über die Codex-CLI reichen den Prompt jetzt über stdin
  statt als Kommandozeilenargument. Ein Runden-Prompt trägt Persona, Historie
  und Werkzeugschemata und riss als einzelnes argv-Element Linux'
  `MAX_ARG_STRLEN` von 128 KiB; auf armserver starben dadurch 12 Agenten-Turns
  einer Runde mit `OSError: [Errno 7] Argument list too long`. (#1425)

### Added (Simulationsrunden laufen jetzt auch über die Codex-CLI — 2026-09-05)

- **Mit `codex_cli` als Provider scheiterte jeder Simulationslauf, obwohl Ontologie, Graph, Personas und Simulations-Config seit [#1418](https://github.com/arn0ld87/agora/issues/1418) sauber durchliefen.** Im Log stand `OASIS-Preflight: Provider-Fehler (HTTP 400) … Simulation vor dem Fan-out abgelehnt`, verursacht durch `invalid params, unknown model 'gpt-5.6-luna' (2013)` — MiniMax' Fehlerformat. Issue [#1423](https://github.com/arn0ld87/agora/issues/1423).
- **Ursache war eine Lücke an der Subprozess-Grenze, nicht im Backend.** `build_route_subprocess_env` löst die Base-URL dreistufig auf (Route → Store → Registry-Default). Für einen Provider mit `transport="cli"` liefern alle drei `None`, also blieb `LLM_BASE_URL` ungesetzt — und weil der Schlüssel in `SAFE_ENV_KEYS` steht, **erbte** der Subprozess die `.env`-URL des Backend-Prozesses. Zusammen mit dem korrekt gerouteten `LLM_MODEL_NAME` ergab das: Codex-Modell an MiniMax-Endpunkt.
- **Der OASIS-Subprozess kannte `codex_cli` überhaupt nicht.** `detect_oasis_platform` mappt auf genau drei CAMEL-Plattformen (GEMINI, OLLAMA, OPENAI), alle HTTP; einen CLI-Transport gab es in `backend/scripts/` nicht. Das `codex`-Binary lief bis hierher ausschließlich in-process im Flask-Backend.
- **Neu: `scripts/sim_runtime/codex_cli_model.py` mit `CodexCliModel(BaseModelBackend)`.** Das Backend spricht `codex exec` statt HTTP und nutzt dafür dieselbe Brücke wie der In-Process-Pfad (`app/llm/providers/codex_cli.py`) — der Subprozess hat `app` im `PYTHONPATH`, deshalb wird importiert statt kopiert.
- **Tool-Call-Emulation, weil `codex exec` kein natives Function-Calling kennt.** OASIS-Agenten wählen ihre Aktionen ausschließlich über Werkzeugaufrufe; ohne Übersetzung wären sie handlungsunfähig. Die Schemas gehen als Prompt-Abschnitt mit, die Antwort wird über das Format `<tool_call>{"name":…,"parameters":{…}}</tool_call>` zurückgelesen — dasselbe Protokoll, das `scripts/agent_tools.py` bereits verwendet, statt eines zweiten. Davon profitiert auch der In-Process-Shim: `tools` wurde dort bisher stillschweigend verworfen.
- **`_arun` läuft über `asyncio.to_thread`.** Das ist nicht kosmetisch: OASIS treibt alle Agenten einer Runde nebenläufig, und ein blockierender Aufruf im Event-Loop hätte die Simulation von paralleler auf serielle Ausführung fallen lassen — bei 8–40 s pro CLI-Aufruf der Unterschied zwischen Minuten und Stunden.
- **Der Transport wird explizit signalisiert statt geraten.** `build_route_subprocess_env` setzt `AGORA_LLM_TRANSPORT=cli` anhand von `ProviderConnectionDefinition.transport`; `process_manager` entfernt daraufhin das geerbte `LLM_BASE_URL`. Die URL-Heuristik in `registry.py::detect_provider` bleibt unangetastet — für einen Provider ohne URL hätte sie ohnehin nichts zu mustern, und AGENTS.md verbietet Detection-Heuristiken daneben.
- **Zwei Guards nehmen CLI-Transport aus.** `simulation_run.py` und `simulation_history.py` lehnten einen Start bisher mit 422 ab, wenn kein `api_key` vorlag und der Endpunkt nicht lokal war — `is_local_endpoint(None)` ist `False`, also traf das jeden CLI-Provider, der per Definition keinen Key hat.
- **Nachtrag zu #1418:** `api/simulation_history.py` reichte `provider_type` nicht an `OasisProfileGenerator` durch. Dieser zweite Aufrufer wurde beim damaligen Fix übersehen und füllte weiterhin die `.env`-URL auf.
- **Laufzeit:** `codex exec` kostet im Container 8,7 s für einen Trivialprompt und rund 40 s für einen echten Persona-Prompt. Für eine 72-Runden-Simulation mit 20 Agenten sind grob 45–60 Minuten pro Lauf zu erwarten; Ratelimits des ChatGPT-Abos sind dabei eine offene Größe. Token-Zahlen meldet die CLI nicht, `usage` bleibt deshalb bei null statt einer erfundenen Schätzung.

### Behoben

- Ein Lauf, bei dem **alle** Personas nach gescheiterten LLM-Versuchen als
  regelbasierte Platzhalter in die Simulation gingen, meldete sich nach außen
  als erfolgreich. Die Degradierung war erfasst, blieb aber folgenlos: sie
  stand als `warning` im Task-Ergebnis, und der Report, der am Ende
  weitergegeben wird, wusste nichts davon. Ein Nutzer ohne Blick ins
  Backend-Log hielt das Ergebnis für belastbar. Zwei Stellen ziehen die
  Konsequenz jetzt nach:
  - `persona_rule_based_fallback` wird `blocking`, wenn keine einzige Persona
    vom Modell kam. `prepare_simulation` setzt dann `failed` statt `ready`
    und trägt die Ursache in `state.error` — der Vertrag verlangt seit jeher,
    dass ein blockierender Ausfall „bereit" nicht erreicht, durchgesetzt hat
    das bis hierher niemand. Bei einer Teilquote bleibt es `warning`: echte
    Stimmen sind dabei, die Platzhalter sind einzeln gekennzeichnet, der Lauf
    ist verwertbar und bleibt startbar.
  - `RunDegradationModel.component` kennt `persona_generation`. Ein Report,
    dessen Personas Platzhalter waren, wird über die bestehende
    `apply_run_degradation_downgrade`-Mechanik auf `INCOMPLETE` abgestuft
    statt als `completed` hinauszugehen. Das gilt auch für den nach einem
    Abbruch finalisierten Teil-Report, der bislang an der einzigen
    Degradations-Aggregation am Laufende vorbeilief.

  Die bewusste Wahl `use_llm_for_profiles=False` bleibt degradierungsfrei —
  gezählt wird `generation_error`, nicht `generation_source`. (#1419)

### Fixed (Die Persona-Generierung schickt das geroutete Modell nicht mehr an den `.env`-Endpunkt — 2026-09-04)

- **Mit `codex_cli` als Workspace-Default schlug jede Persona-Generierung fehl, während Ontologie, Graph und Report mit demselben Provider einwandfrei liefen.** Im Log stand pro Persona dreimal `Error code: 400 — invalid params, unknown model 'gpt-5.6-luna' (2013)`, danach `using rule-based generation`. Der Fehlercode `(2013)` ist MiniMax' Format: das aus der Route stammende Modell ging an `LLM_BASE_URL` aus der `.env`. Issue [#1418](https://github.com/arn0ld87/agora/issues/1418).
- **Ursache war ein Informationsverlust in der Bridge zurück in den Legacy-Vertrag.** `build_runtime_llm_config` bildet eine `ResolvedRoute` auf `RuntimeLlmConfig` ab; `_ROUTE_TO_RUNTIME_PROVIDER` kannte `codex_cli` nicht und ließ es in den generischen `custom_openai`-Eimer fallen. Für HTTP-Provider ist das folgenlos — die `base_url` trägt als String genug Information, damit `detect_provider` später wieder greift. `codex_cli` (transport=`cli`, [#1405](https://github.com/arn0ld87/agora/issues/1405)) hat aber gar keine `base_url`, also gab es nichts mehr zu erkennen.
- **Der `#1104`-Schutz in `_resolve_llm_connection` griff deshalb nie.** Er sitzt im `ResolvedRoute`-Zweig, die gebridgte Konfiguration nahm den Legacy-Zweig daneben und lieferte `(key, None)` zurück. `OasisProfileGenerator.__init__` las das fehlende `base_url` als „nicht aufgelöst" und füllte `Config.LLM_BASE_URL` auf — Modell aus der Route, Endpunkt aus der `.env`.
- **`_resolve_llm_connection` gibt jetzt zusätzlich den Provider-Typ zurück** und kennt CLI-Transporte: für `transport="cli"` ist eine fehlende `base_url` der Normalfall und kein Abbruchgrund. Die Gegenprobe bleibt scharf — ein HTTP-Provider ohne `base_url` wirft weiterhin.
- **`OasisProfileGenerator` und `SimulationConfigGenerator` reichen den Provider-Typ an `LLMClient` durch.** Damit greift dort `_codex_cli_active` und der Subprozess-Transport statt eines HTTP-Calls, wie in `LLMClient.from_route()` seit [#1406](https://github.com/arn0ld87/agora/issues/1406) bereits vorgesehen. Der Persona-Pfad war der einzige, der seinen Client selbst zusammenbaute — und der einzige, der scheiterte.
- **Bewusst nicht angefasst:** `SimulationConfigGenerator.self.base_url` behält den `.env`-Fallback, weil `SimulationParameters.llm_base_url` daran hängt und damit die Simulationsrunden — ein Pfad, den dieses Issue nicht untersucht hat. Nur der eigene `LLMClient` des Generators wird jetzt ohne diesen Fallback gebaut.
- **Zweiter Befund aus demselben Screenshot: das System-Panel meldete dauerhaft den `.env`-Provider.** „Ollama — Prüfung übersprungen — aktiver Provider ist MiniMax" stand da unabhängig davon, welche Verbindung unter Einstellungen → LLM-Anbieter aktiviert war. `_get_ollama_status` leitete sowohl die Probe-Entscheidung als auch den angezeigten Provider ausschließlich aus `Config.LLM_BASE_URL`/`Config.LLM_MODEL_NAME` ab, also aus der `.env` des Containers. Die aktive Konfiguration hat jetzt Vorrang; die `.env` bleibt Fallback für Installationen, die nie eine Verbindung aktiviert haben.
- **Der angezeigte Provider kommt jetzt bevorzugt aus der `provider_id` der aktiven Verbindung statt aus der URL-Heuristik.** `detect_provider` kann nur aus der Base-URL raten — für `codex_cli` gibt es nichts zu raten. `SkippedProviderKind` ist per Vertrag ein freier String, und `providerLabel` im Frontend fällt auf den Rohwert zurück; die bekannten Connection-IDs haben zusätzlich einen Anzeigenamen bekommen.
- **Nebenwirkung für Tests:** `backend/instance/active_llm_config.json` liegt im Repo-Verzeichnis und existiert auf Entwicklerrechnern, in CI nicht. `tests/test_status.py` isoliert den Reader deshalb per Autouse-Fixture, sonst hinge das Provider-Gating daran, welche Verbindung der Entwickler zuletzt aktiviert hat.

### Slice 2.1 — Kanonische Index-Auflösung

Lese- und Schreibpfad des Vector-Index lösen Index- und Property-Namen jetzt
über zwei neue Methoden am `EmbeddingConfigurationStore` auf,
`resolve_active_entity_index()` und `resolve_active_fact_index()`, statt sie
als Literale in `backend/app/storage/search_service.py` und
`backend/app/storage/neo4j_write.py` zu verdrahten. Die Entity-Methode liest
Index- und Property-Namen direkt aus dem gespeicherten
`EmbeddingIndexVersion`-Datensatz, den `EmbeddingMigrationService.start()`
anlegt (`entity_embedding_vN` / `embedding_vN`). Die Fact-Methode leitet
beide Namen konventionell aus der Versionsnummer ab (`fact_embedding_vN` für
Index und Property), weil Fact-Indizes keinen eigenen
`EmbeddingIndexVersion`-Datensatz haben — eine bereits vor diesem Slice
dokumentierte Asymmetrie in `embedding_migration.py`. Diese Konvention wurde
gegen die tatsächlich in `embedding_migration.py` (Zeilen 254-255) und
`embedding_reembedder.py` verwendeten Namen geprüft und deckt sich exakt
damit; sie ist keine zweite, unabhängige Quelle für Namensbildung, sondern
spiegelt die einzige, die es im Migrationslauf bereits gibt.

Im Lesepfad (`SearchService`) wird der Index-Name als Query-Parameter an
`db.index.vector.queryNodes`/`queryRelationships` gebunden — das sind
reguläre Prozedur-Argumente, keine DDL-Identifier, deshalb ist Parameter-
Bindung hier möglich und sicherer als String-Interpolation. Im Schreibpfad
(`Neo4jWriteMixin._persist_episode`) lässt sich der Property-Name in einer
`SET`-Klausel nicht als Parameter binden; er wird einmal pro Aufruf (nicht
pro Entity-/Relation-Schleifendurchlauf) aus dem Store gelesen und an der
Interpolationsstelle mit einem Kommentar versehen, der festhält, dass der
Wert ausschließlich aus dem Store stammt und nie aus Benutzereingaben.

Ohne aktive Index-Version bleibt das Verhalten unverändert: beide
Store-Methoden fallen dann auf exakt die bisherigen Legacy-Namen zurück
(`entity_embedding`/`embedding`, `fact_embedding`/`fact_embedding`). Das ist
die Rückwärtskompatibilitäts-Zusage dieses Slices und mit eigenen Tests
abgesichert.

Was dieser Slice ausdrücklich nicht tut: Er schaltet keine Konfiguration
scharf und ändert nicht, welcher Index aktiv ist — das bleibt Slice 2.2
(Cutover). Die `VECTOR_DIM`-SSoT bleibt offen (Slice 2.3), ebenso eine
Legacy-View für Bestandsgraphen (Slice 2.4). Die in
`docs/agents/architecture-ssot.md` dokumentierte SSoT-Ausnahme für Embedding
ist mit diesem Slice noch nicht geschlossen — er liefert nur die
Auflösungslogik, die die folgenden Slices verwenden.

### Slice 2.2 — Echter Cutover

`EmbeddingMigrationService.start()` markierte die neue Index-Version bisher sofort
als `active` und supersedierte die alte — noch bevor der Re-Embedder überhaupt lief.
Sobald Slice 2.1 (kanonische Index-Auflösung) aktiv war, hätte das Reads auf einen
leeren oder nicht existierenden Index geschickt und Writes des noch laufenden alten
Modells in die neue Property geschrieben: genau die Korruption, vor der #1417 warnt.
Dieser Slice schließt die Lücke.

`start()` legt die Ziel-Index-Version jetzt mit dem neuen, additiven Status
`building` an (Erweiterung von `EmbeddingIndexStatus`, keine Änderung bestehender
Werte oder Defaults) und supersediert die alte Version nicht mehr sofort. Solange
eine Migration läuft, bleibt die alte Version `active`, und `get_active_index_
version()` sowie die kanonische Auflösung aus Slice 2.1
(`resolve_active_entity_index()` / `resolve_active_fact_index()`) liefern
weiterhin ihre Namen — das ist der Regressionsschutz, mit dem dieser Slice
abgesichert ist.

Erst nach erfolgreichem Re-Embedding, bestandener Fortschritts-Validierung und
einer neuen Index-Prüfung (`Neo4jReEmbedder.index_is_online()`, `SHOW INDEXES`
gegen die Spalte `state`, analog zum bestehenden Dimensionswächter aus #263)
schaltet der Service atomar um: die Ziel-Version wird zuerst `active`, danach erst
wird die Quell-Version `superseded` — in dieser Reihenfolge, damit zwischen beiden
Schreibvorgängen nie ein Moment ohne aktive Version existiert. Jeder Fehlschlag-
oder Abbruchpfad (Exception, `failed`-Ergebnis des Re-Embedders, fehlgeschlagene
Fortschritts- oder Index-Validierung, expliziter `cancel()`) setzt die Ziel-Version
stattdessen auf `rolled_back` zurück; die Quell-Version bleibt dabei unangetastet
`active`. Ein fehlgeschlagener oder abgebrochener Re-Embedding-Lauf schaltet den
Betrieb also nie um.

ADR-0007 gilt unverändert: Der alte Index wird `superseded`, aber nie gedroppt —
dieser Slice fügt keine `DROP INDEX`-Ausführung hinzu.

Was dieser Slice nicht rückwirkend repariert: Ein Bestandssystem, bei dem eine
Migration bereits vor diesem Slice mit dem alten Verhalten gestartet wurde, trägt
diesen Zwischenzustand (Ziel-Version sofort `active`, Quell-Version sofort
`superseded`) weiterhin unverändert. Die `VECTOR_DIM`-SSoT (Slice 2.3) und eine
Legacy-View für Bestandsgraphen (Slice 2.4) bleiben ebenfalls offen.

### Changed (Der codex_cli-Provider bietet den echten Modellkatalog statt eines einzelnen Platzhalters — 2026-09-04)

- **`codex_cli` zeigte genau ein Modell, `codex-cli-default`** — obwohl dasselbe Abo in der CLI unter `/model` sechs auswählbare Modelle führt. Der Sentinel stammt aus #1405 und war dort die richtige Entscheidung: Ohne Einträge in der Probe weist `_verify_selected_model` jede Modellauswahl zurück, und ein erfundener „echter" Modellname wäre veraltungsanfällig gewesen. Er war als Platzhalter gedacht, nicht als Endzustand.
- **Die CLI kann ihren Katalog selbst ausgeben:** `codex debug models` liefert ihn als JSON. `discover_codex_cli_models()` fragt ihn zur Laufzeit ab und filtert auf `visibility == "list"` — genau der Filter, den die CLI für ihr eigenes `/model`-Menü verwendet. `hide` markiert interne Einträge (`gpt-reserve`, `codex-auto-review`), die keine Nutzerauswahl sind.
- **Laufzeit-Abfrage statt gepflegter Liste, weil der Katalog account- und planabhängig ist.** Das Binary kennt intern mehr Slugs, als ein konkretes Abo freischaltet — verifiziert: `gpt-5.6` und `gpt-5.6-pro` stehen im Binary, fehlen aber im Katalog eines Plus-Accounts. Eine im Repo gepflegte Liste wäre damit nicht nur veraltungsanfällig, sondern für einen Teil der Nutzer schlicht falsch.
- **Der Sentinel bleibt hinter den echten Slugs stehen, statt von ihnen ersetzt zu werden.** Eine bereits gespeicherte Routing-Auswahl auf `codex-cli-default` würde sonst von `_verify_selected_model` verworfen, sobald die Discovery zum ersten Mal greift. Außerdem bleibt „nimm, was `/model` in der CLI eingestellt hat" eine bewusst wählbare Option — `_run_codex_cli` lässt `--model` für den Sentinel weiterhin weg.
- **Discovery ist Komfort und darf nie eine funktionierende Verbindung kippen.** Jeder Fehlschlag — Binary fehlt, Timeout, Exit ≠ 0, kaputtes JSON, unerwartete Katalogform — liefert ein leeres Tupel und wird geloggt; die Probe fällt dann auf den Sentinel zurück und bleibt `available`. Der Katalog-Aufruf läuft wie jeder codex-Aufruf in einem isolierten, leeren `cwd` und mit eigenem Timeout (30 s), nicht mit dem 180-s-Timeout der Chat-Aufrufe.

### Added (Die codex-CLI liegt im Container — das ChatGPT-Abo ist damit nutzbar — 2026-09-04)

- **Der `codex_cli`-Provider war vollständig implementiert und trotzdem in keinem containerisierten Setup benutzbar** (#1412). `is_codex_cli_available()` prüft per `shutil.which("codex")` den **Container**-PATH; weder `dev` noch `prod` installierten das Binary. Eine Installation auf dem Host half nicht — die Probe meldete dauerhaft „codex-CLI nicht im PATH gefunden" und der Provider blieb `unavailable`, obwohl Contract, Registry, Adapter, Frontend und Schemas aus #1405/#1406 korrekt standen.
- **Eigene `codex-cli`-Build-Stage, aus der `dev` und `prod` per `COPY` bedient werden.** Eine Stage statt zweier Installationen, weil `prod` nicht von `base` erbt: So wird der Download (86 MB komprimiert, 222 MB entpackt) im Build genau einmal ausgeführt und beide Ziel-Stages bekommen dasselbe verifizierte Binary. Seit dem Rust-Rewrite ist codex ein statisch gelinktes musl-Binary — kein Node, keine Laufzeitabhängigkeiten, läuft unverändert im slim-Image.
- **Version und beide Architektur-Hashes sind gepinnt** (`CODEX_VERSION`, `CODEX_SHA256_AMD64`, `CODEX_SHA256_ARM64`), die Architektur wird primär aus `uname -m` der bauenden Maschine abgeleitet; `TARGETARCH` überschreibt sie nur, wenn BuildKit sie tatsächlich setzt. Die umgekehrte Reihenfolge mit `ARG TARGETARCH=amd64` war nachweislich falsch: `docker compose build` setzt `TARGETARCH` nicht, der Default griff, und ein aarch64-Server lud kommentarlos das x86_64-Binary — Download und Hash-Prüfung liefen sauber durch, erst `codex --version` scheiterte mit Exit 126. Der Download wird vor der Installation gegen den Hash geprüft — dasselbe Muster, das die `FROM`-Digests bereits verwenden; ein ungeprüftes Binary aus dem Netz gehört nicht ins Laufzeit-Image.
- **Die Anmeldung bleibt ausdrücklich außerhalb des Images.** `codex login` legt sie auf dem Host unter `${CODEX_HOME:-~/.codex}` ab; `docker-compose.yml` reicht dieses Verzeichnis in den Container. Ein Abo-Token gehört weder in eine Image-Schicht noch ins Repo. Der Mount ist bewusst **nicht** read-only: `codex exec` startet einen In-Process-App-Server und legt Session-State sowie PATH-Aliase unter `CODEX_HOME` ab — auf einem `:ro`-Mount bricht jeder Aufruf mit `failed to initialize in-process app-server client: Read-only file system (os error 30)` ab, während die Verfügbarkeitsprobe (`shutil.which`) weiterhin `True` meldet. Der Container kann damit auch den Refresh-Token zurückschreiben, was nötig ist, sobald das Abo-Token abläuft; im Gegenzug teilt er sich den Zustand mit der interaktiven codex-Installation des Hosts. Existiert das Host-Verzeichnis nicht, legt Docker es als `root` an und der Container-User (uid 1000) kann es nicht lesen — deshalb muss `codex login` einmal auf dem Host gelaufen sein.

### Behoben

- **`build-only` lief seit dem 2026-08-28 auf `main` und damit auf jedem PR
  rot.** Der `Trivy container scan` blockierte den Merge jedes offenen PRs,
  auch solcher mit sonst durchweg gruenen Checks. Die Ursache war
  mehrschichtig; alle vier Ebenen sind jetzt geschlossen (#1410):

  1. **openssl (CVE-2026-14456, HIGH)** in `openssl`, `libssl3t64` und
     `openssl-provider-legacy`: installiert `3.5.6-1~deb13u2`, gefixt in
     `3.5.7-1~deb13u2`. Gescannt wird `target: prod`, also genau die Stage,
     die seit #1328 ein `apt-get update && apt-get upgrade -y` traegt. Der
     Upgrade lief trotzdem ins Leere: Der Build-Job zieht `cache-from:
     type=gha`, und solange FROM-Digest und Instruktion unveraendert bleiben,
     serviert BuildKit den alten apt-Layer — die Zeile wird nie neu
     ausgefuehrt. Die prod-Stage haengt jetzt am aktuellen
     `python:3.14-slim`-Digest (`sha256:cad9a2c8...`). Der Bump ersetzt den
     Upgrade nicht, er loest ihn aus.

  2. **unstructured (CVE-2026-71428, CRITICAL)**: `0.18.32` → `0.27.5`. Der
     Bump erzwang einen zweiten Override: unstructured ab 0.24.0 verlangt
     `psutil>=7.2.2`, waehrend `camel-ai` `psutil<6` pinnt — auch in der
     aktuellsten Version 0.2.90, es gibt also keine camel-ai, die beides
     erfuellt. Ohne `psutil>=7.2.2` im Override-Block ist die Resolution
     unloesbar und die CRITICAL bliebe offen. `camel` 0.2.78 importiert
     gegen psutil 7.2.2 sauber, das Backend-Gate ist gruen.

  3. **nltk faellt ganz weg** und nimmt CVE-2026-79675 (CRITICAL),
     CVE-2026-78680, CVE-2026-71513 sowie GHSA-8mgp-746c-j5xp (HIGH) mit.
     nltk stand bis hierher nur im Override-Block und kam transitiv ueber
     unstructured herein; mit 2. (spacy statt nltk) faellt es aus `uv.lock`.

     Der naheliegende Reflex — nltk explizit auf die gefixte 3.10.3 pinnen, um
     die Import-Guard-Tests am Leben zu halten — war nachweislich falsch und
     wurde wieder zurueckgenommen: `GHSA-8mgp-746c-j5xp` ("Model-artifact APIs
     bypass pathsec") trifft nltk `<= 3.10.3` und traegt im
     GitHub-Advisory-Datensatz `first_patched_version: null`, waehrend 3.10.3
     zugleich die neueste Release ist. Es gibt **keine** sichere
     nltk-Version; der Pin holte die Advisory nur zurueck und liess
     `Dependency Review` (`fail-on-severity: high`) rot laufen. nltk
     fernzuhalten ist die staerkere Loesung, nicht der Nebeneffekt.

     Die Guard-Infrastruktur wurde entsprechend zurueckgebaut, ohne
     Assertions aufzuweichen: Die vier nltk-abhaengigen Tests in
     `tests/test_nltk_import_guard.py` tragen jetzt ein `requires_nltk`-skipif
     (ohne nltk pruefen sie nichts mehr — `import nltk` scheitert am
     ImportError statt am Guard) und bleiben stehen, damit sie bei einem
     Wiedereinzug sofort wieder greifen. Der Dockerfile-Test laeuft
     unabhaengig weiter. `test_pyproject_and_uv_lock_nltk_pin_match` skippt
     bei Abwesenheit statt zu scheitern; an seine Stelle tritt der schaerfere
     `test_nltk_is_absent_from_uv_lock`, der den Abwesenheitszustand aktiv
     festhaelt. `NLTK_DISABLE_IMPORT_SECURITY=1` und der Override-Eintrag
     bleiben als Riegel fuer den Fall stehen, dass eine kuenftige Transitive
     nltk zurueckholt.

  4. **msgpack (GHSA-6v7p-g79w-8964) und setuptools (CVE-2025-47273)**, beide
     HIGH, waren ueber `uv.lock` gar nicht erreichbar: Die venv fuehrt
     setuptools 83.0.0 und kein msgpack. Beide stecken in
     `site-packages/pip/_vendor` — pip 26.2.1 bundelt laut `vendor.txt`
     `msgpack==1.1.2` und `setuptools==70.3.0`. Das prod-Image braucht pip zur
     Laufzeit nicht (die venv kommt fertig aus `backend-build` und enthaelt
     selbst kein pip, gunicorn startet aus `.venv/bin`, der HEALTHCHECK nutzt
     `urllib`), deshalb wird pip dort jetzt entfernt — statt die Funde per
     `.trivyignore` zu unterdruecken. Die `dev`-Stage behaelt pip.

  Nebenwirkung von 2.: `unstructured` 0.27.5 zieht das spaCy-Oekosystem nach
  (17 neue Lock-Eintraege, 5 entfallen). Die 214 Parsing- und Chunking-Tests
  sowie das vollstaendige Backend-Gate laufen unveraendert gruen.

### Added (neuer LLM-Provider „Codex CLI (ChatGPT-Abo)“ — 2026-08-30)

- **Agora kann jetzt gegen die lokal eingeloggte Codex-CLI routen, statt einen `OPENAI_API_KEY` zu verlangen.** Der neue Provider `codex_cli` spricht `codex exec` als Subprozess in einem isolierten `cwd` und mit `--sandbox read-only` an — kein HTTP-Endpunkt, kein Secret im Store. Nutzung setzt eine bestehende, per ChatGPT-Abo authentifizierte Codex-CLI-Session voraus.
- Der Aufruf läuft mit hartem Timeout (Default 180s, konfigurierbar über `AGORA_CODEX_CLI_TIMEOUT_SECONDS`). Token-Streaming unterstützt dieser Provider in diesem Slice noch nicht.
- Bewusst nur Codex/ChatGPT in diesem Slice — ein möglicher Claude-CLI-Provider ist ausdrücklich nicht Teil dieser Änderung (höheres ToS-Risiko, eigenes Folge-Issue).

### Changed (LLM-Modell-Presets sind jetzt ein Pydantic-Vertrag statt einer Dict-Liste — 2026-08-24)

- **`Config.LLM_MODEL_PRESETS` und die Response von `/api/simulation/available-models` liefen bisher außerhalb der Schema-Generierung.** Der Endpunkt reichte rohe Dicts unvalidiert durch, das Frontend spiegelte sie in einem handgeschriebenen TypeScript-Interface — ein CodeRabbit-P1-Finding auf [#1390](https://github.com/arn0ld87/agora/pull/1390), entgegen der Contracts-first-Regel aus AGENTS.md.
- **`ModelPreset`/`AvailableModelsResponse` sind jetzt Pydantic-Modelle** (`backend/app/contracts/model_preset_contract.py`). Der Endpunkt konstruiert die Response darüber und validiert sie beim `model_dump`, statt Dicts durchzureichen.
- **`label` bleibt bewusst ein optionales Legacy-Feld** (Bestandsschutz aus [#1290](https://github.com/arn0ld87/agora/issues/1290)): Ollama-Tag-Einträge setzen es weiterhin auf den rohen Modellnamen, ältere Backends im Mischbetrieb können es für kuratierte Presets noch liefern. Ein `field_serializer` lässt ungesetzte Preset-Felder aus der Serialisierung weg statt sie als `null` zu senden — kuratierte Presets ohne `label` bekommen kein `"label": null` untergeschoben, sonst würde `test_no_preset_carries_hardcoded_label_text` durch die neue Validierung wieder scharf.
- **Frontend-Spiegel `frontend/src/contracts/modelPresetContract.ts`** nach dem bestehenden Zod-Mechanismus (strikt, gegen `schemas/model-preset.schema.json` und `schemas/available-models-response.schema.json` getestet). `frontend/src/api/simulation.ts` re-exportiert die generierten Typen statt eigene Interfaces zu pflegen; `useEnvForm.ts` bezog `ModelPreset` bereits darüber (Rework aus [#1390](https://github.com/arn0ld87/agora/pull/1390)).
- **`default_provider` ist im Vertrag bewusst `str`, nicht `Literal`** — analog zu `SystemStatusOllama.skipped_provider`: ein neuer Provider in `registry.py::detect_provider` (aktuell `ollama|cloud|minimax|openai|google|bedrock|unknown`) darf den Vertrag nicht brechen. Das vorherige TypeScript-Interface kannte nur vier der sieben Werte — `useEnvForm.ts`s `defaultProvider`-Ref ist entsprechend von der engen Union auf `string` geweitet.
- **`frontend/src/i18n/modelPresetLabel.ts::ModelPresetLike` bleibt unverändert** — der eigene Minimal-Strukturtyp entkoppelt die i18n-Schicht bewusst vom API-Layer und ist kein Duplikat.

- Tests: zwei Regressions-Waechter dokumentieren das offene CodeRabbit-Finding
  zur Nullability optionaler Felder und zur Integer-Validierung in Zod.
  Die Fixes erfordern eine Folge-Issue (Backend-Schema-Generator vs.
  ``field_validator``; Frontend Schema-Spiegel-Mechanik).

### Fixed (Drei Panel-Rotation-Regressionen aus #1380 behoben — 2026-08-23)

- **`InterviewResult.selected_agents` bekommt jetzt einen Produzenten.** Das Feld existierte seit jeher im DTO, wurde nach der Panel-Rotation in `GraphToolsService.interview_agents` aber nie zugewiesen — serialisierte Ergebnisse lieferten `selected_agents: []`, obwohl Interviews stattfanden. `graph_tools.py` schreibt die Auswahl jetzt neben ihre Begründung (`result.selected_agents = selected_agents`).
- **Nicht-antwortende Personas belasten das Diversitätskonto nicht mehr.** `_record_interviewed_panel` verbuchte bisher die volle `selected_indices`-Liste, unabhängig davon, ob eine Persona tatsächlich eine Plattformantwort lieferte oder nur den Platzhalter `"(No response from this platform)"` bekam. Eine neue `responded_indices`-Liste wird additiv neben der bestehenden `selected_indices`-Iteration aufgebaut (Positionskopplung `selected_agents[i]` bleibt unangetastet) und ist jetzt Grundlage der Buchung — eine stumme Persona wird dadurch nicht mehr fälschlich aus späteren Panels gedrängt.
- **Der Ausschöpfungs-Fallback unterscheidet jetzt zwischen anderem und gleichem Aspekt.** `InterviewPanelTracker.class_rank` gab bisher für beide Fälle denselben Rang 2 zurück, obwohl der Modul-Docstring eine Bevorzugung des anderen Kontexts dokumentierte. Die Klasse ist jetzt vierstufig (0 frisch, 1 wiederverwendbar unter Limit, 2 Ausschöpfung mit anderem Aspekt, 3 Ausschöpfung mit gleichem Aspekt); die Notiz-Schwelle in `apply_selection` wurde von `== 2` auf `>= 2` angepasst, damit Klasse 3 weiterhin als Ausschöpfungs-Notiz sichtbar bleibt.
- Drei gezielte Regressionstests in `test_interview_panel_rotation.py` decken jeweils genau den vorher stillschweigend falschen Fall ab, inklusive des bis dahin ungetesteten Teilerfolgs-Batches (nur ein Teil der Auswahl antwortet).

### Added (Kooperatives Abbrechen für `simulation_prepare` und `graph_build` — 2026-08-18)

- **`POST /api/runs/<id>/cancel` funktioniert jetzt auch für laufende Simulationsvorbereitungen und Graph-Builds** — vorher liefen beide Jobtypen unbeirrt bis zum Ende durch, auch nachdem der Nutzer abgebrochen hatte (nur `simulation_run` und `report_generate` kannten das Cancel-Flag). Beide Jobtypen prüfen jetzt an mehreren Stellen kooperativ nach, ob ein Abbruch angefordert wurde: `simulation_prepare` zwischen den drei Phasen (Entities lesen, Personas generieren, Config generieren) und zusätzlich in der `as_completed`-Schleife der Persona-Generierung; `graph_build` vor dem Chunk-Durchlauf und in dessen `as_completed`-Schleife.
- **Beide Pfade lassen bereits laufende Arbeit auslaufen, statt sie hart abzubrechen** — für `graph_build` heißt das: bereits committete Neo4j-Transaktionen (Episode, Entitäten, Relationen) bleiben stehen, es gibt kein Rollback und kein `delete_graph`; der Graph wird stattdessen als `incomplete` markiert (`Neo4jWriteMixin.mark_graph_incomplete`, `ProjectStatus.GRAPH_INCOMPLETE`). Für `simulation_prepare` bleibt die bereits geschriebene Profildatei (`realtime_output_path`) als Teilergebnis erhalten; der Simulations-FSM bekommt dafür einen neuen Übergang `PREPARING → CANCELLED_PARTIAL` (plus Retry-Pfad `CANCELLED_PARTIAL → PREPARING`, symmetrisch zum bestehenden `FAILED → PREPARING`).
- **Beide Endzustände folgen demselben Muster wie der bestehende Report-Abbruch:** `status="stopped"`, `termination_reason="user_cancel"`, `resume_capability` bietet einen Neustart an. `ontology_generate` bleibt bewusst außen vor (läuft synchron im Request-Handler, kein Job).

### Fixed (Review-Nachbesserungen am Cancel-Feature — 2026-08-18)

- **Der `graph_build`-Cancel-Pfad war über die API komplett unerreichbar:** `cancel_run` verlangte für JEDEN Run-Typ eine `linked_ids.simulation_id`, bevor das Flag überhaupt gesetzt wurde — `graph_build`-Runs verknüpfen aber nie eine simulation_id. Die Pflicht gilt jetzt nur noch für `simulation_run`, wo sie fachlich gebraucht wird.
- **Ein Abbruch während der Persona-Generierung mit gesetztem `quota_plan` endete als `failed` statt `stopped`:** die Quota-Validierung lief vor dem Cancel-Check und scheiterte an der durch den Abbruch gekürzten Profilliste. Der Cancel-Check läuft jetzt zuerst.
- **Ein Fehler im Cancel-Finalisierer selbst (Neo4j-Aussetzer, Registry-Schreibfehler) konnte den geretteten Teilgraphen wieder löschen**, weil er ins äußere Fehlerbehandlungs `except` durchschlug. Jeder Schritt läuft jetzt einzeln best-effort, der wichtigste (Run-Status auf `stopped`) unabhängig vom Erfolg der anderen.
- **Ein Restart nach einem Abbruch war selbst nicht mehr abbrechbar** — beide Restart-Pfade (`_restart_graph_build`, `_restart_simulation_prepare`) übergaben die neue `run_id` nicht an den Service. „Abbrechen → Neu starten → nochmal abbrechen“ quittierte 202, passierte aber nichts.
- **Die gemeldete Episodenzahl nach einem Abbruch konnte niedriger sein als tatsächlich im Graphen committet** — bereits laufende (nicht mehr stornierbare) Chunks committen ihre Transaktion trotzdem, ihr Ergebnis wurde aber nie eingesammelt. `add_text_batches` liest sie jetzt nach.
- **Ein zu spät angekommener Abbruch (nach dem letzten Checkpoint) hinterließ das Cancel-Flag dauerhaft im Prozessspeicher** — beide Job-Closures räumen es jetzt in einem `finally`-Block auf, unabhängig vom Ausgang.

### Behoben

- Der Coverage-Ledger persistiert keine rohen `producer_key`-Werte mehr —
  Web-Items tragen dort die volle Tool-URL samt Query.
- Ein Interview-Ausfall gilt nur bei explizit bekannter, nicht behebbarer
  Ursache als terminal. `503` und `connection refused` schalten das Tool nicht
  mehr für den ganzen Lauf ab; der Hinweistext folgt derselben Einschätzung.
- Der Coverage-Ledger ist referenzinteger: eine kanonisierte Zeile muss auf
  vorhandene Evidence zeigen, und Status und Feldbelegung schließen einander aus.
- Ein Schwellenwert in Tagen wird nicht mehr von einer Angabe in Minuten belegt.
- Zwei einander ausschließende Schranken ("mindestens 80" gegen "höchstens 70")
  gelten als Widerspruch.
- Ein an der Producer-Grenze gescheiterter Fakt zählt für die Data-Gap-Prüfung
  als vorhanden — sonst wird ein Registrierungsfehler zur fehlenden Information.
- Ein später Contract-Validierungsfehler landet in `run_degradations`.
- Ein Interview-Record deckt keine Simulationszuschreibung mehr ab.
- Die Red-Team-Invarianten prüfen komponentenscharf; ein unbezogener Mangel
  stellt keine fremde Prüfung mehr still.
- Ein zuerst als wiederholbar vermerkter Tool-Ausfall blockiert die spätere
  Abschaltung nicht mehr.
- Kein `KeyError` mehr im Sanitizer: Aufzählungswörter und Zählpositionen sind
  jetzt dieselbe Menge, durch eine Modul-Invariante gesichert.
- Threshold-Labels werden auf zehn statt sechs Zeichen gekürzt —
  "Fallbackdauer" und "Fallbackzeit" fielen sonst zusammen.
- Der Persona-Kohärenz-Log nennt keinen Entitätsnamen mehr (CodeQL).

### Behoben

- Ein Prozentwert gilt nicht mehr als durch dieselbe Absolutzahl belegt:
  "15 Prozent der Beschäftigten" wurde von "15 Beschäftigte" gestützt, weil
  die Einheit beim Gleichheitsvergleich fehlte.

### Behoben

- Ein satzeinleitendes Adverb ("Aktuell", "Insgesamt") galt als
  Teilpopulation und unterdrückte echte Widersprüche. Als Abgrenzung zählt
  jetzt nur, was hinter einer eingrenzenden Präposition steht.
- Die Faktenart wird am ganzen Satz erkannt, nicht nur am Prädikat rechts der
  Zahl: "Der Projektplan *fordert* mindestens 80 Prozent" wurde sonst als
  gemessener Wert gelesen.

### Neu

- Ein Pipeline-Regressionstest über den vollständigen Referenzlauf
  `report_cc2ef45da5e9`: dieselben Zahlen, derselbe Absatz, dieselbe
  gescheiterte Simulation. Er prüft das Zusammenspiel der Schutzmechanismen
  statt jeden einzeln — inklusive der Vertragstreue des entstehenden
  Artefakts.

### Behoben

- Abschnitte, die erst nach erzwungener Endgenerierung entstanden, und
  Abschnitte ohne strukturierte Metadaten erscheinen in der Qualitätsbilanz
  des Laufs. Beides stand bisher nur im Log — der Leser sah einen Abschnitt,
  dem er nicht ansehen konnte, dass dem Agenten die Schritte ausgegangen waren.

### Behoben

- Die Evidence-Bindung trug ein Feld, das der strikte Contract verbietet. Die
  Section-Validierung schlug dadurch fehl, und der Reparaturlauf verwarf jeden
  Claim mit gebundener Evidence.
- Interviews werden am Evidence-Typ erkannt, nicht an der Quellengattung:
  `agent_post` und `agent_interview` fallen beide auf `agent_quote`. Die
  Interview-Prüfungen waren dadurch genau dann still, wenn eine Simulation lief.
- Eine Quellenangabe links der Zahl ("Laut Betriebsrat") galt als
  Populationsunterschied und unterdrückte echte Widersprüche.
- Eine überschrittene Ober- oder Untergrenze gilt wieder als Widerspruch.
  Schrankenwörter bestimmen die Schranke, nicht mehr auch die Absicht.
- `run_degradations` wird beim Laden zurückgelesen; die API meldete sonst
  jeden Lauf als ungestört.
- Nur blockierende Mängel stufen `completed` ab — ein Bericht über eine noch
  laufende Simulation bleibt vollständig.
- Der Belegprüfungs-Anhang trägt wieder Abschnittsüberschriften.
- Ein Interview-Timeout schaltet das Tool nicht mehr für den ganzen Lauf ab.
- Modellableitungen und Web-Fundstellen können keinen Schwellenwert auf
  `verified` heben.
- "station" wird nicht mehr in "Ladestation" gelesen; ein solcher Fehlalarm
  löschte den Beruf einer korrekten Persona.

### Neu

- Deterministische Red-Team-Invarianten über den fertigen Lauf: angeforderte
  Interviews ohne Ergebnis, eine nicht regulär beendete Simulation und ein
  degradierter Lauf mit Status `completed` erscheinen als Befund im Bericht.
  Sie laufen unabhängig vom LLM-Red-Team — was sich abzählen lässt, gehört
  nicht in einen Prompt.

### Behoben

- Zuschreibungen im Fließtext folgen der Beleglage. "Die Simulation zeigt …"
  wird zu "Die Quellenlage zeigt …", wenn keine Simulations-Evidence vorliegt;
  Interview-Formulierungen ohne stattgefundene Interviews ebenso. Ersetzt wird
  nur die Zeugenformel, nie die Aussage.
- Semantisch identische Claims aus mehreren Abschnitten erscheinen einmal.
  Zusammengeführt wird nur bei gleichen Zahlen, gleicher Belegmenge und hoher
  Wortüberlappung; Entferntes steht im Protokoll.
- Ein zusammengesetzter Claim gilt nur als belegt, wenn die Quelle jede seiner
  Teilaussagen berührt.
- Die Belegprüfung steht gesammelt im Anhang statt hinter jedem Abschnitt.
  Gelöscht wird nichts — die Marken im Fließtext bleiben satzgenau erhalten.

### Behoben (Regression aus diesem Branch)

- Der Report-Export antwortete mit 400, weil `to_dict()` ein `degraded`-Feld
  ausgab, das der strikte Contract nicht kennt.

### Changed (Die Ablage ist der Standard, 2026-08-19)

- **`/` führt jetzt in die Ablage statt aufs Dashboard.** Der Shell-Standard ist von `classic` auf `dossier` gewechselt: Ablage und Dossier sind gebaut, Abbrechen und Pause hängen an der Zeile, Personasätze und Berichte sind Startpunkte. `agora.shell=classic` im localStorage bleibt als Rückweg erreichbar, bis die alten Ansichten gelöscht sind — dann fällt der Flag ganz.
- **`views/Home.vue` ist entfernt.** Sie war seit dem `/home`→`/dashboard`-Redirect (ADR-0010) an keiner Stelle mehr eingebunden. `RunsView`, `RunDetailView` und `RunsDashboard` bleiben: sie leben in den v4-Wrappern weiter und werden von den Weiter-Aktionen der Ablage angesteuert.

### Added (Läufe allein aus gespeicherten Personas, 2026-08-19)

- **`POST /api/simulation/create-from-personas`** legt Projekt und Simulation an und bereitet sie ausschließlich aus Personas vor — Verweise in die Bibliothek (`template_ids`) oder Inline-Personas. Kein Dokument, keine Ontologie, kein Graph. Bewusst ein eigener Endpunkt: in `/create` bleibt die `graph_id` Pflicht, der reguläre Weg über Dokument und Graph weicht nicht auf.
- **`prepare_from_personas`** fährt denselben FSM-Pfad wie `branching_service.create_branch` (`CREATED → PREPARING → READY`, kein Direktsprung) und schreibt `reddit_profiles.json`/`twitter_profiles.csv` sowie eine `simulation_config.json`. Beim Übersetzen der Bibliothekseinträge werden Felder ergänzt, die die Bibliothek gar nicht führt: `user_id`, `karma`, `created_at` (auf das Tagesformat normiert), `persona_kind` — und vor allem `age`/`gender`/`mbti`, die **immer** existieren müssen, weil die OASIS-Bibliothek sie ungeschützt indiziert. `PersonaLibrary._normalize` lässt leere Werte weg, ein Eintrag ohne Alter hat den Schlüssel also gar nicht.

### Changed

- **Die harte Untergrenze von 30 Personas ist entfallen** (`_validate_persona_quota` im `simulation_config_generator`, Issue #496). Sie stand genau dem im Weg, wofür der neue Weg gedacht ist: einem kleinen, gezielten Lauf — einem Gremium aus acht Leuten etwa. 30 bleibt der Vorschlagswert im Dashboard, ist aber keine Schranke mehr; unterhalb erscheint ein Hinweis auf die dünnere Aussagekraft statt einer Sperre. Mit der Grenze fällt auch der Schalter, der sie aufhob: `AGORA_ALLOW_SMALL_SIM` und das gespiegelte `allow_small_sim` in `/api/status` sind entfernt, ebenso die Abfrage im Dashboard, die den Regler beim Mount wieder hochklemmte.

### Fixed

- **Berichte sagen jetzt, was einem Persona-Lauf fehlt.** Die drei Prüfpunkte (`report_generation.py`, `report.py`, `runs.py`) antworteten mit „Missing graph ID“ — einem Satz, der jemandem nichts sagt, der nie einen Graphen bauen wollte. Sie nennen jetzt den Grund und halten fest, dass die Simulation selbst in Ordnung ist. Bewusst **kein** Platzhalter-Graph: ein formal gültiger Fake würde die Prüfungen passieren lassen, und der Bericht liefe ohne jede Graph-Evidenz durch — er sähe aus wie ein normaler. Ein klarer Abbruch ist ehrlicher.

### Behoben

- Gruppenentitäten werden nicht mehr zu erfundenen Einzelpersonen. Erkannt wird
  jetzt am Grundwort des Entitätstyps (`HospitalNetwork`, `EmployeeGroup`,
  `PatientAdvisoryCouncil`), nicht mehr an einer festen Liste, die jede neue
  Ontologie überholte.
- Ein Beruf, der einer Fachdomäne entstammt, die in keiner Quelle vorkommt,
  wird geleert statt erfunden. Ein Klinik-Rollout wird damit nicht mehr zu
  Fertigungsplanung oder Maschinenbau.

### Behoben

- Ein terminal ausgefallenes Tool wird abgeschaltet statt abgeraten. Der
  Hinweis "Do NOT call interview_agents again" stand nur im Tool-Ergebnis und
  blieb folgenlos; das Tool verschwindet jetzt aus dem angebotenen Schema und
  ein trotzdem angeforderter Aufruf wird nicht ausgeführt.
- Der Reportstatus bildet den Zustand des Laufs ab. Gescheiterte Simulation,
  unvollständige Runden, angeforderte Interviews ohne Ergebnis und
  fehlgeschlagene Abschnitte stufen `completed` auf `incomplete` ab.
- Parallele Reports schreiben nicht mehr in die Logdateien des jeweils anderen.

### Neu

- `run_degradations` am Report: strukturierte Qualitätsmängel des Laufs mit
  Komponente, Grund und Schweregrad. Additiv mit Default.
- Deterministische Red-Team-Invarianten über den fertigen Lauf
  (`assert_run_invariants`) — abzählbar statt erzählt.

### Fixed (API-Funktionen deklarieren, was sie wirklich liefern — #1373, 2026-08-19)

- **38 Funktionen in `frontend/src/api/*.ts` gaben den ausgepackten Nutzdatentyp vor, obwohl der Response-Interceptor grundsätzlich die Envelope zurückgibt** (`{success, data, …}`, siehe `api/index.ts`). Der deklarierte Typ beschrieb also nicht, was zur Laufzeit ankam — und weil er log, konnte der Compiler keinen Aufrufer mehr warnen. Jede Funktion wurde einzeln gegen ihren Endpunkt geprüft: die Zuordnung stammt aus Flasks eigener `url_map` (182 Routen), nicht aus einer Namensheuristik, und für jede Route wurde nachgesehen, ob sie `json_success` nutzt oder flach antwortet. `cancelRun` und `replayRun` antworten tatsächlich flach und bleiben unverändert; `closeSimulationEnv` baut seine Envelope von Hand (`jsonify({"success", "data"})`) und zählt deshalb dazu.
- **`AvailableModelsResponse` beschrieb ein Feld `models`, das der Endpunkt nie geliefert hat.** `get_available_models` gibt `ollama`, `presets`, `current_default` und weitere zurück. Nur die Index-Signatur `[key: string]: unknown` hat verhindert, dass das auffiel — der Aufrufer griff seit jeher auf Felder zu, die im Typ nicht standen.
- **Die `as unknown as …`-Casts in den Aufrufern sind entfallen.** Sie waren nie Absicht, sondern Notwehr gegen die falschen Signaturen, und haben die Diskrepanz versteckt statt behoben.

### Added

- **Guard `frontend/src/api/__tests__/envelopeContract.spec.ts`.** Er liest die Quelltexte und meldet jede exportierte Funktion, die ein `service.*`-Ergebnis direkt durchreicht, ohne einen Envelope-Typ zu deklarieren. Ausnahmen brauchen einen Eintrag samt Backend-Beleg (`datei.py::funktion`) — wer etwas einträgt, muss die Route nachgesehen haben. Funktionen, die die Envelope selbst auspacken und bewusst etwas anderes zurückgeben (etwa `getSimulationFeedSnapshot`), bleiben unbehelligt: ihr Typ beschreibt korrekt die eigene Rückgabe.

Hintergrund: In PR #1372 hat genau dieser Typfehler zwei echte Defekte verursacht — die Personasätze wären in der Ablage nie erschienen, und die Vergleichsansicht konnte noch nie Branches laden. Beide Male war der zugehörige Test grün, weil er dieselbe falsche Annahme mockte.

### Behoben

- Schwellenwerte werden semantisch dedupliziert. Maßgeblich ist der
  Sachverhalt (Kennzahl, Bezug, Wert, Einheit, Rolle), nicht die vom Modell
  vergebene ID — derselbe Wert aus zwei Abschnitten ist ein Schwellenwert.
- Ein Wert, der wörtlich in einer Quelle steht, wird an sie gebunden statt als
  unbelegte Heuristik zu enden.
- Bei widersprüchlicher, unbelegter Herkunftsangabe gilt die schwächere. Zwei
  unbelegte Behauptungen werden nicht dadurch wahrer, dass man die lautere nimmt.

### Added (Ablage und Dossier — eine Liste für alle Objekte, 2026-08-18)

- **Die neue Hülle `/ablage` zeigt Läufe, Berichte, Graphen und Personasätze in EINER Liste.** Bisher lag jede Sorte in einer eigenen Ansicht mit eigener Navigation, und ein Lauf war nur als Kette einzelner Jobs sichtbar — die erstellten Graphen ließen sich nirgends überblicken. Steht hinter dem Flag `agora.shell=dossier` (localStorage) bzw. `VITE_AGORA_SHELL`; ohne Flag ändert sich nichts. Ausgewertet wird das Flag ausschließlich im Router, nie in Komponenten.
- **Jede Zeile trägt eine Weiter-Aktion und, bei laufender Arbeit, Abbrechen und Pause.** Ein Abbruchknopf existierte zuvor nirgends in der Oberfläche. Abgebrochen wird ohne Rückfragedialog, dafür mit einem 5-Sekunden-Fenster zum Rückgängigmachen.
- **Ein Lauf ist eine Zeile, auch wenn er aus mehreren Jobs besteht.** Die Zusammenfassung läuft transitiv über `linked_ids`: `graph_build` trägt nur eine `project_id`, das folgende `simulation_prepare` trägt beide IDs. Wer je Job stur die `simulation_id` bevorzugt, zerlegt genau diesen Lauf in zwei Zeilen — einmal als Projekt-, einmal als Simulationszeile. Die Rohebene bleibt über den Filter „Alle Jobs“ erreichbar.
- **Das Dossier lädt die Bestandteile eines Objekts erst beim Auswählen.** Ein Bericht zeigt seine Zusammenfassung und die Abschnitte seiner Gliederung, ein Graph seine Entitäten- und Beziehungszahl. Sorten ohne Detail-Endpunkt zeigen bewusst nichts, statt ein leeres Gerüst zu behaupten; ein fehlgeschlagener Abruf lässt die Ablage unberührt.
- **Das Fake-Profil oben rechts ist weg.** Es gab zwei davon: ein `<div aria-hidden>AD</div>` in der klassischen Kopfzeile — nicht einmal fokussierbar — und ein nachgebautes `AS` in der neuen Hülle. Beide ersetzt durch ein echtes Menü mit Initialen aus dem Profil-Store (ohne Profil ein neutrales `?`) und den Einträgen Profil und Einstellungen. Die Glocke daneben war ein `<button>` ganz ohne Handler, dessen Badge-Wert nirgends je gesetzt wurde, und ist ersatzlos entfernt.

### Fixed

- **`listPersonaTemplates` deklarierte `Promise<PersonaTemplateRecord[]>`, obwohl der Axios-Interceptor grundsätzlich die Envelope zurückgibt.** Personasätze wären in der Ablage nie erschienen. Nach dem Ehrlichmachen des Typs deckte der Compiler prompt eine zweite Stelle auf, die im Erfolgszweig auf ein `error`-Feld zugriff, das dort nicht existiert.
- **Dynamisch gebildete Statusschlüssel (`shelf.status.report_*`, `project_*`) existierten in keiner Locale**, und das mitgegebene `{ fallback }` war wirkungslos: vue-i18n interpoliert benannte Werte nur *in* eine gefundene Message und gibt bei einem Fehltreffer den Schlüssel selbst zurück. In der Ablage hätte wörtlich `shelf.status.report_generating` gestanden. Alle zwölf Enum-Werte ergänzt, plus Rückfall auf den Rohstatus für künftige Backend-Werte.
- **Ein zweiter Abbruch innerhalb des Undo-Fensters verwarf den ersten stillschweigend** — der erste Lauf erreichte `cancelRun` nie, ohne dass es jemand bemerkt hätte. Er wird jetzt sofort ausgeführt, statt verschluckt zu werden.
- **Escape schloss das Aktivitäts-Panel, ohne den Fokus zurückzugeben**; er fiel auf den Dokumentkörper. Und der Stapel übernahm jeden Wert aus dem `sessionStorage` ungeprüft — ein beschädigter Eintrag erzeugte Pillen, deren Klick ins Leere navigierte.

### Changed

- **Control-Höhen wachsen unter `pointer: coarse` auf 36/44/48px.** Angehängt an die Eingabeart, nicht an eine Breite: ein 1280px-Tablet wird mit dem Finger bedient, ein schmales Desktop-Fenster mit der Maus. Die Icon-Knöpfe der Kopfzeile und die Grid-Zeile der AppShell hängen jetzt an diesen Tokens statt an festen Pixelwerten.

### Behoben

- Numerische Evidence wird deterministisch gefunden. Eine Quelle, die dieselbe
  Zahl in derselben Einheit nennt, ist Kandidat, auch wenn ihr Embedding-Score
  unter der Retrieval-Schwelle liegt. Ob sie den Claim belegt, entscheidet
  unverändert das Entailment.
- Absolutzahlen mit Adjektiv ("38 abweichende Dringlichkeitsfälle") werden
  überhaupt erst als Fakt erkannt.
- Eine gescheiterte Evidence-Bindung wird nicht mehr als Datenlücke exportiert.
  Als Data Gap gilt nur noch, wozu in keiner verfügbaren Quelle etwas steht.

### Neu

- `evidence_coverage_ledger` in der Evidence-Map: für jeden quantitativen
  Tool-Fakt entweder eine kanonische Evidence-ID oder ein Verwerfungsgrund.
  Additiv mit Default — bestehende persistierte Maps bleiben gültig.

### Behoben

- Ein abweichender Zahlenwert allein gilt nicht mehr als Widerspruch. Vor einem
  `CONTRADICTED` prüft der Trust-Layer jetzt Einheit, Faktenart (Ist-Wert gegen
  Zielvorgabe oder Schranke) und Teilpopulation. Ein gemessener Anteil einer
  Teilgruppe widerlegt damit keine Mindestanforderung an die Gesamtheit mehr.
- Zahlen, deren Bezugsgruppe links steht ("Die Verwaltung erreichte 91 Prozent"),
  werden überhaupt erst als Fakt erkannt. Vorher waren sie für Beleg *und*
  Widerspruch unsichtbar.
- Ausgeschriebene Aufzählungen ("Erstens … Zweitens …") werden nach dem
  Entfernen eines widerlegten Punkts lückenlos neu gezählt — bisher galt dieser
  Schutz nur für nummerierte Listen.

### Fixed (Ein ausgefallener Ubuntu-Mirror macht die Playwright-Gates nicht mehr rot — 2026-08-18)

- **Zwei PRs nacheinander scheiterten an einem Host, der nichts mit Agora zu tun hat.** `npx playwright install --with-deps` zieht Font-Pakete von den Ubuntu-Mirrors; war `azure.archive.ubuntu.com` nicht erreichbar, brach apt mit Exit 100 ab — nach gut einer Minute, bevor ein einziger Test lief. Der Install-Schritt läuft jetzt bis zu dreimal mit wachsender Pause und `apt-get update` dazwischen, damit ein rotierter Mirror auch benutzt wird statt derselbe unerreichbare Host erneut.
- **Ein größeres Step-Timeout wäre der falsche Hebel gewesen.** Das war der Fix für [#1070](https://github.com/arn0ld87/agora/issues/1070), wo der Schritt tatsächlich in die Zeitgrenze lief. Hier gibt apt von sich aus auf; mehr Zeit verlängert nur die Wartezeit auf denselben Fehler.
- **Der apt-Teil wird bewusst nicht bei warmem Cache übersprungen.** Gecacht ist `~/.cache/ms-playwright`, also die Browser-Binärdateien; die Systempakete liegen im Runner-Image und sind bei jedem Lauf frisch. Ein Cache-Treffer sagt nichts darüber, ob die Fonts da sind — ihn als Beleg zu nehmen hieße, still gegen ein anderes Font-Set zu rendern.

### Added (Interviewantworten tragen eine Richtung — 2026-08-18)

- **`sentiment_score` war ein Feld, das niemand schrieb.** Es steht in `EvidenceRecordModel`, wird von `confidence_calculator._extract_sentiment_scores` gelesen — und war im 7-Sektionen-Referenzlauf bei **0 von 99 Items** gesetzt. Damit war jede Mengenaussage über Stakeholder („die Mehrheit lehnt den ungestaffelten Vollstart ab“) strukturell unbelegbar: Regel 2 in `evidence_entailment` prüft solche Aussagen gegen einen Prozentwert, und ohne Richtung gibt es nichts auszuzählen. Die Persona nennt ihre Haltung jetzt selbst als letzte Zeile ihrer Antwort (`STANCE: <-1.0…1.0>`).
- **Warum die Persona sich selbst einschätzt.** Eine Markerliste wäre genau das lexikalische Raten, das [#1357](https://github.com/arn0ld87/agora/issues/1357) im Entailment gerade abgeschafft hat; ein eigener Judge-Call je Interview kostet im Referenzlauf 32 zusätzliche Calls. Gefragt ist hier die Haltung der Persona, nicht ein Urteil über sie — die Selbstauskunft ist die Sache selbst, nicht ihre Schätzung.
- **Fehlt die Zeile, bleibt der Wert leer.** Nicht `0.0`: eine Antwort ohne erkennbare Richtung ist keine Enthaltung, und sie als eine zu zählen füllte die Grundgesamtheit mit Stimmen, die niemand abgegeben hat. Werte außerhalb der Skala werden auf `[-1, 1]` gekappt statt das Item zu verwerfen; wiederholt das Modell die Zeile, zählt die letzte — dort, wo der Prompt sie verlangt hat, während frühere Vorkommen Echos der Anweisung sind.
- **Die Marke verlässt den Text nicht.** Die Zeile wird abgetrennt, bevor der Antworttext gerendert, gekürzt oder auf Zitate durchsucht wird — sonst stünde `STANCE: -0.6` im persistierten `quote`, im `snippet` und am Ende im Berichtstext.

### Changed

- **Die Haltung bekommt ein eigenes Feld, statt `sentiment_score` zu belegen.** `topic_stance` in `EvidenceRecordModel` und `EvidenceItemModel` trägt die Position der Person zum Thema; `sentiment_score` beschreibt weiterhin den Tenor eines Snippets. Der Unterschied ist nicht akademisch: `_has_contradiction` wertet die Sentiment-Spanne der Belege **eines Claims** aus und zieht bei `min < -0.3 UND max > +0.3` zwanzig Punkte ab. Zwei Personas können beide „Schulung ist nötig“ sagen — beide Snippets zustimmend — und dabei gegensätzlich zum Rollout stehen. Fiele die Themenhaltung in dasselbe Feld, würde genau der Claim abgewertet, über den sie einig sind. Die Widerspruchs-Penalty bleibt damit weiter ohne Eingabe; sie zu aktivieren wäre nur richtig, wenn die Sentiments claim-relativ wären, und das sind sie nicht.

### Fixed (Das Red Team bewertet den Bericht, nicht die ersten 4000 Zeichen — 2026-08-18)

- **Der Reviewer meldete einen Abbruch, den es nicht gab.** Im Referenzlauf lautete ein Befund, der Bericht breche bei „Das Management handelte zunächst unter dem Druck wirtschaf…“ ab. Das war der Schnitt des Excerpts, nicht des Berichts; der Satz und seine Sektion waren vollständig vorhanden. Gemessen an acht Artefakten griff die 4000-Zeichen-Grenze in fünf Fällen — jedes Mal mitten im Satz. Ein Reviewer, der ein Artefakt des Werkzeugs für einen Inhaltsfehler hält, verbraucht Aufmerksamkeit, statt sie zu schaffen.
- **Zwei weitere Kappungen lagen davor.** Der Entwurf bestand aus `claims[:20]` und `hypotheses[:10]`. Bei 339 Claims in einem gemessenen Artefakt sah der Reviewer sechs Prozent davon. Alle drei Grenzen sind weg; das verbleibende Zeichenbudget (60k, rund 20k Token) ist eine Kostenbremse gegen entartete Läufe, keine inhaltliche Auswahl — und es schneidet nur noch am Zeilenende, mit einer Marke, die die Kürzung als Kürzung ausweist und die Zahl der ausgelassenen Einträge nennt.
- **Die Schwellen fehlten vollständig, und genau dort lag der Widerspruch.** Der Bericht fordert in Sektion 1 vier Wochen Pilotbetrieb und in Sektion 7 mindestens acht. Beide Werte stehen als `Threshold` im Artefakt — im Entwurf für den Reviewer standen sie nie. Sie sind jetzt drin, mit Wert, Einheit, Herkunft und Beleglage, und der Prompt fragt ausdrücklich nach widersprüchlichen operativen Zahlen.
- **Jede Zeile trägt ihre Kennung.** `C7_03` nennt den Abschnitt, aus dem der Claim stammt. Der Prompt erklärt das und weist darauf hin, dass Widersprüche zwischen weit auseinanderliegenden Abschnitten die sind, die beim Lesen am wenigsten auffallen — derselbe Zuschnitt, der den 4-gegen-8-Wochen-Fall verdeckt hat.

### Fixed (Die Herkunft eines Claims wird abgeleitet, nicht behauptet — 2026-08-18)

- **Sechzehn von sechzehn Claims wiesen dieselbe Herkunft aus, und sie war bei fünfzehn falsch.** Jeder Claim trug `aggregation_basis="persona"` und `confidence_scope="simulation_consensus"`, während seine `evidence_refs` auf 22 `seed_corpus`- und 2 `agent_action`-Items auflösten. Der Leser erfuhr, ein Befund beruhe auf der Meinung simulierter Personas, obwohl er aus dem Seed-Dokument stammte. `aggregation_basis` war schlicht ein Literalwert im Konstruktoraufruf.
- **Die zweite Ursache saß eine Ebene tiefer.** Die Evidence-Dicts *am Claim* tragen nur die Bindungsdaten (`evidence_id`, `match_score`, `entailment` …); die Quellengattung steht ausschließlich im vollen Datensatz im `evidence_index`. Die Ableitung des Geltungsbereichs las `source_kind` direkt am Item, fand dort nie etwas und fiel still auf den Default zurück — ein Fehler, der sich als Vorsicht tarnte. Sie schlägt jetzt über die `evidence_id` im Index nach.
- **Eine einfache Mehrheit trägt keinen Claim.** Verlangt wird eine strikte: mehr als die Hälfte der stützenden Items. Zwei Seed-Belege und zwei Zitate ergeben `aggregat`, nicht `seed` — bei Gleichstand trägt keine Gattung die Aussage allein. `graph_relation` und `web_source` führen bewusst nicht auf `seed`, obwohl eine Graph-Kante aus dem Korpus stammt: Der Knoten verdichtet viele Erwähnungen zu einer Kante und ist damit selbst schon eine Aggregation. Items ohne auflösbare Gattung zählen in die Grundgesamtheit, können eine Mehrheit also verhindern, nie begründen.
- **Der Vertrag weist widersprüchliche Kombinationen jetzt ab.** `ReportV3Claim` lässt `seed` neben `confidence_scope="simulation_consensus"` nicht mehr zu — `seed_corpus` ist eine quellengebundene Gattung. `datenluecke` verträgt weder einen quellengebundenen Geltungsbereich noch ein `high`/`verified`-Label. Beide Felder stammen aus derselben Menge stützender Items; dass sie beliebig kombinierbar waren, ist der Grund, warum der Literalwert sechzehn Claims lang unbemerkt blieb.

### Fixed (qualitative Claims werden nicht mehr über Wortüberlappung belegt — 2026-08-17)

- **Die Deckungsrichtung war verkehrt herum.** Regel 3 maß Containment: sobald der Evidence-Text Teilmenge des Claims war, galt der Claim als belegt. Im Referenzlauf stammten deshalb **alle 24 `SUPPORTED` aus dem lexikalischen Zweig**, bei Containment-Median 1.00 und Deckungs-Median 0.21 — der Claim behauptete im Schnitt das Fünffache seiner Quelle. So band „Die simulationsgestützte Evaluation … ergibt gravierende Risiken für die Patientensicherheit“ an „Der Städtische Klinikverbund Falkenbrück plant unter dem Projektnamen AURORA die Einführung des Systems Nexora Triage Assist.“ Gemessen wird jetzt `coverage_ratio(claim, evidence)`: was der Claim behauptet, muss in der Quelle stehen.
- **Persona-Interviews konnten strukturell nie binden.** Ihre lexikalische Deckung liegt im Median bei 0.02, im Maximum bei 0.29 — ein Interviewzitat sagt dasselbe in anderen Worten. Das Retrieval fand sie mit 0.65 bis 0.79 korrekt, der lexikalische Vorfilter warf sie danach weg (22 von 25 Paaren). Da `agent_interview` auf `EvidenceSourceKind.agent_quote` abgebildet wird und `cross_stakeholder_for_high` genau diese Gattung verlangt, war `high`/`verified` damit **unerreichbar**: im Referenzlauf alle 16 Claims `low`, 0 `agent_quote` in den `evidence_refs`. Liegt ein Retrieval-Ergebnis über `RETRIEVAL_RELEVANCE_THRESHOLD` (0.60) vor, entfallen beide lexikalischen Filter — die Frage „geht es um dasselbe“ hat die Embedding-Stufe dann bereits besser beantwortet.

- **Eine Quelle, die den Claim ausdrücklich verneint, galt als Beleg.** `nicht` steht in `_STOPWORDS`, also reduzieren „die Betriebsvereinbarung ist abgeschlossen“ und „… ist *nicht* abgeschlossen“ auf dasselbe Token-Set und erreichen Deckung 1.00 — das regelbasierte `SUPPORTED` fiel vor dem Judge. Der qualitative Pfad prüft die Polarität jetzt zuerst (`qualitative_polarity_mismatch` → `CONTRADICTED`), wie der numerische seit [#1317](https://github.com/arn0ld87/agora/issues/1317).
- **Ein erschöpftes Run-Budget wurde als Judge-Fehler verschluckt.** Seit der Judge in der Bindungskette hängt, kann er `BudgetExceededError` auslösen — `classify_evidence` und der Binder-Block im `ReportAgent` fingen aber pauschal `Exception`. Der Lauf wäre als `completed` angekommen statt mit `termination_reason=budget_*`, und alle folgenden Kandidaten hätten weiter Calls versucht. Beide Schichten reichen die Ausnahme jetzt durch.

### Changed

- **Regel 3 ist dreiteilig.** Deckung ≥ 0.60 ergibt `SUPPORTED`, Deckung < 0.10 ohne Retrieval-Signal `RELATED_ONLY`; dazwischen entscheidet der Judge. Ohne Judge endet die Grauzone bei `RELATED_ONLY` — unentschieden heißt nicht belegt. Die deterministischen Regeln 1 und 2 (Zahl, Bezugsgruppe, Mengenaussage) bleiben unverändert vorgelagert und bindend; ein regelbasiertes `CONTRADICTED` erreicht den Judge nie.
- **Der Judge ist verdrahtet und darf in der Grauzone belegen.** `build_llm_judge` existierte, wurde aber von keinem Aufrufer gesetzt — der `judge`-Parameter war toter Code. `ReportAgent` baut ihn jetzt einmal pro Lauf und reicht ihn an `bind_evidence_to_claim`. Die alte ADR-0002-Klausel („darf `SUPPORTED` nur abschwächen, nie erzeugen“) ist für den qualitativen Pfad abgelöst, siehe [`docs/decisions/0002-supersedes.md`](docs/decisions/0002-supersedes.md) — sie war eine Bremse gegen die alte Großzügigkeit von Regel 3 und wäre nach deren Umkehrung eine Sperre gewesen, hinter der die Grauzone dauerhaft unbelegt bliebe.
- **Der Binder klassifiziert erst nach dem Kürzen auf `top_k`.** Vorher lief der Entailment-Check über jeden Kandidaten oberhalb der Retrieval-Schwelle. Mit einem Judge in der Kette wäre das ein Call je Kandidat gewesen, auch für die, die anschließend ohnehin herausfallen. Das Budget hängt damit an `top_k` (Referenzlauf: höchstens 5 je Claim). Der Preis: ein widersprechendes Item mit schwachem Retrieval-Score fällt heraus, statt `contradicts_claim` zu setzen.
- **Judge-Ausfall fällt auf den Regelpfad.** Exception oder unbekanntes Verdikt setzen `judge_failed`; die Grauzone endet bei `RELATED_ONLY`. Der Report wird dadurch vorsichtiger, nicht falscher.
- **Antwortet der Provider in Prosa statt JSON, wird das Urteil aus dem Text gelesen.** Gemessen an den fünf verfügbaren Ollama-Cloud-Modellen lieferte genau eines strukturiertes JSON; die übrigen antworteten mit einer sauberen, aber prosaischen Begründung (`**Urteil:** RELATED_ONLY — die Evidence thematisiert zwar …`). Mit `LLM_DISABLE_JSON_MODE` fällt der erzwungene Modus ohnehin weg. Ohne diesen zweiten Versuch wäre der Judge in vier von fünf Konfigurationen dauerhaft im `judge_failed`-Pfad, obwohl das Modell inhaltlich korrekt geurteilt hat; mit ihm sind es drei von fünf tauglich. Gelesen wird ausschließlich der Urteilsname und nur, wenn er eindeutig ist — bei null oder mehreren Treffern wird nichts geraten. Gesucht wird als eigenständiges Wort, nicht als Teilstring: „The claim is UNSUPPORTED“ enthält sonst genau einen Treffer, ausgerechnet das gegenteilige Urteil. Der zweite Versuch läuft mit `force_no_thinking`, weil Reasoning-Modelle ihr Budget sonst im Denkteil verbrauchen und leer antworten, und mit `context="report"`, damit Tokens und Kosten nicht dem interaktiven Chat zugeschrieben werden.

### Fixed (Fließtext-Faktenprüfung löscht keine belegten Aussagen mehr — 2026-08-17)

- **Ein vollständiger 7-Sektionen-Referenzlauf verlor 28 Faktenaussagen, die weit überwiegende Mehrheit davon belegt.** Aufgeschlüsselt nach Grund: 14 `predicate_overreach`, 8 `no_matching_number`, 4 `subject_mismatch`, 2 `predicate_not_measurable`. Gegen die neue Prüfung kehren alle 28 zurück — sie bleiben im Text stehen und tragen den Marker `[Beleg fehlt]`.
- **Dieselbe Zeile Code beschädigte Markdown-Struktur und Satzsyntax.** `_SENTENCE_SPLIT = (?<=[.!?])\s+` hielt Ordinalzahlen für Satzenden. Aus `… (3. bis 14. Juni mit 14 Ärzten …) wichen 38 Empfehlungen ab` wurden zwei Fragmente; das zweite trug die Zahlen und fiel, übrig blieb ein Satz, der mitten in der Datumsklammer abbrach. Bei Listen zerfiel `1. Erfolgreicher Wiederholungstest …` in `"1."` und den Rest — der Rest fiel, der nackte Marker blieb (`section_01.md` und `section_03.md` mit je zwei leeren Zeilen). Aufzählungspräfixe werden jetzt vor der Zerlegung abgetrennt, Ordinalzahlen und Abkürzungen (`z. B.`, `Nr. 3`, `15. Mai`) sind als Satzgrenze ausgeschlossen. Verliert eine Listenzeile ihren Inhalt, verschwindet sie ganz und die Liste zählt lückenlos weiter.
- **`INSUFFICIENT` wurde wie `CONTRADICTED` behandelt.** „Kein passendes Evidence-Item gefunden“ heißt nicht „falsch“. Entfernt wird nur noch, was einer Quelle aktiv widerspricht. `predicate_overreach` und `modality_mismatch` gelten dabei nicht mehr als Widerspruch: eine unbelegte Zusatzaussage ist keine falsche, und die Modalität wird ohne Parser aus Markerlisten geraten. `_modality_of` kennt jetzt zusätzlich substantivische Zielmarker (Ziel, Vorgabe, Anforderung, Schwellenwert, mindestens, maximal), damit „Schulungsziel von 80 Prozent“ nicht länger als Ist-Wert gelesen wird.
- **Ein einzelnes kollidierendes Evidence-Item entschied über einen ganzen Satz.** Ein beliebiges Item mit demselben Zahlenwert bei fremder Bezugsgruppe kippte einen Satz, dessen übrige Zahlen sauber belegt waren. Geprüft wird jetzt pro numerischem Fakt. Aggregiert wird über zwei bewusst verschiedene Ordnungen: pro Fakt zählt das *entschiedenste* Urteil des Pools (ein Beleg schlägt alles, danach kommt der Widerspruch), pro Satz das *schwerwiegendste* seiner Fakten. Dass dabei kein Zufallstreffer durchschlägt, sichert nicht die Rangfolge, sondern die Verdikte selbst — `subject_mismatch` ist kein Widerspruch mehr. Ergänzend endet eine Bezugsgruppe an der nächsten Zahlenangabe — vorher lief das Subjekt des ersten Fakts in einer Aufzählung über alle folgenden Zahlen hinweg.
- **Ein Claim, der den belegten Wert selbst nennt, widerspricht der Quelle nicht.** Steht die Bezugsgruppe vor der Zahl, läuft das Subjekt der ersten Zahl bis zur zweiten Gruppe durch. „83 Prozent im Ärztlichen Dienst und 91 Prozent in der Verwaltung“ verglich deshalb 83 mit den belegten 91 Prozent derselben Verwaltung und las einen Widerspruch, wo die Quelle den Satz stützt. `value_mismatch` verlangt jetzt zusätzlich, dass der Quellwert im Claim nirgends vorkommt; sonst gilt die Zuordnung als unscharf (`value_mismatch_ambiguous_subject`, `INSUFFICIENT`).

### Changed

- **Abschnitte führen `unverified_statements`** (`ReportSectionUnverifiedStatementModel`, Zod-Spiegel in `frontend/src/contracts/reportContract.ts`). Der Marker im Fließtext ist für den Leser da; dieses Feld trägt Aussagetext, Urteil und Begründung maschinenlesbar, damit UI und Audit nicht am Markerstring parsen müssen.
- **Die Fließtext-Prüfung vergleicht gegen den vollständigen `evidence_index`** statt nur gegen Abschnitts- und globale Evidence. Ein in Abschnitt 4 erhobener Fakt war für Abschnitt 1 vorher unsichtbar, obwohl der Beleg im selben Artefakt lag.
- **Das `gate_decision_log` unterscheidet `prose_fact_contradicted` von `prose_fact_unverified`.** `action` bleibt für beide `moved_to_hypotheses`, damit bestehende Konsumenten keinen neuen Wert sehen.

### Known limitation

- **Der Gründungsfall des Sanitizers bleibt bis [#1357] sichtbar im Text.** „61 % der Lehrkräfte bewerteten die Lernhilfe positiv und berichteten von einer Zeitersparnis“ ist eine echte Falschzuordnung — die Quelle belegt nur die Zeitersparnis. Sie ist von einer korrekten Paraphrase lexikalisch nicht zu trennen: die erfundene Aussage erreicht Deckung 0.56, die korrekte („forderten **bereits im Vorfeld** eine Verschiebung“) nur 0.50. Jede Schwelle, die die eine fängt, löscht die andere mit. `test_1e` prüft deshalb ab jetzt die Kennzeichnung statt die Entfernung; die semantische Trennung braucht ein Urteil jenseits der Wortzählung.
- **Steht die Bezugsgruppe vor der Zahl** („in der Ärzteschaft 83 Prozent“), sucht `_split_subject_predicate` nur rechts der Zahl und ordnet dem Fakt die nächstfolgende Gruppe zu. Auf das Gating schlägt das nicht mehr durch — eine fremde Bezugsgruppe ergibt `INSUFFICIENT`, und ein Wert, den der Claim selbst nennt, ebenfalls. Die Zuordnung bleibt trotzdem falsch und trägt die Begründung; als `xfail` gegen `extract_numeric_facts` festgehalten und in [#1357] aufgenommen.

[#1356]: https://github.com/arn0ld87/agora/issues/1356
[#1357]: https://github.com/arn0ld87/agora/issues/1357

### Fixed (`file_parser.py` — Zeilenalignment beim Chunk-Folgestart, 2026-08-23)

- **Mehrzeilige Aussagen zerfielen am Fensterrand in ein kontextloses Fragment:** Fiel die Chunk-Grenze (Projekt-Default 500 Zeichen) mitten in eine Pfeil-Listen-Aussage, begann der Folgechunk beim letzten Halbsatz — im AURORA-Referenzlauf trug der Evidence-Snippet nur noch „Danach Entscheidung ueber Falkenbrueck-Nord.“, während die tragende Bedingung „vier Wochen stabiler Betrieb“ allein im Vorchunk lag. Der Matcher verlor damit genau die Bedingung (#1347).
- **Neu: Der Folgechunk-Start wird vor dem Wort-Snap an den Anfang seiner Zeile ausgerichtet** (`_snap_to_line_start`), wenn eine Zeilengrenze im festen Rückblick von 100 Zeichen liegt; sonst greift unverändert der bisherige Wort-Snap. Beide Snaps sind verlustfrei — der Start wandert nur rückwärts, es wird kein Text übersprungen.
- **Bewusst fester, kleiner Rückblick statt Overlap-Scaling oder Absatz-Chunking:** Die Ausrichtung soll benachbarte Zeilen einer Aussage zusammenhalten; ein mit dem Overlap skalierender Rückblick erzeugte bei `GRAPH_CHUNK_SIZE=1500` messbar mehr (und kürzere) Chunks — also mehr Extraktionsaufrufe beim Graph-Build — ohne dort ein Problem zu lösen. Semantisches Chunking und Parent-Chunk-Anreicherung wurden geprüft und verworfen: neue Produktfläche bzw. wachsende Evidenzkarte (#1190).
- **Messbar (Synthetik-Dokument, Projekt-Default 500/50):** isolierte Entscheidungs-Fragmente 66 → 0 (großes Dokument: 266 → 0) bei identischer Chunk-Anzahl (133 bzw. 533) und +3 % Chunktext-Volumen durch den größeren Überlappungsanteil. Bei Graph-Default 1500/150 bleibt die Ausgabe byte-identisch. Die Nachbearbeitung (Claim-Binding, #1190) ist strukturell unberührt: Snippets sind LLM-Fakten mit unverändertem 300-Zeichen-Cap, Chunk-Anzahl und damit Extraktions- wie Evidence-Item-Menge bleiben gleich.

### Fixed (Sammelclaims werden pro Teilaussage bewertet statt komplett auf INSUFFICIENT abgestuft — 2026-08-24)

- **Ein Claim, der mehrere Voraussetzungen bündelt ("Rollout nur wenn: S-17 behoben, S-24 behoben, Schulungsquote erreicht"), war ein einziger Claim-Eintrag mit einem einzigen Evidence-Urteil.** Der bestehende Kompositions-Check (`claim_atomizer.split_compound_claim`, #1369) lief ausschließlich innerhalb der Entailment-Stufe (`evidence_entailment.py::_classify_qualitative_claim`) und konnte einen teilweise belegten Sammelclaim nur komplett auf `INSUFFICIENT` abstufen — das verhinderte das falsche `SUPPORTED`, lieferte aber nicht die im Issue verlangte Granularität ("jeden Teilclaim separat bewerten"). Ein Claim mit 2 von 5 belegten Teilen blieb ein einziger, komplett unbelegter Eintrag statt in 2 belegte und 3 unbelegte Einzelclaims zu zerfallen.
- **Die Zerlegung sitzt jetzt an der Extraktionsstufe:** `ReportAgent._build_claims_for_section` (`agent.py:725`) wendet `claim_atomizer.split_claim_chunks` nach den #1316-Struktur-/Diskursfiltern und vor der Evidence-Bindungsschleife an — jedes Sub-Atom durchläuft danach Roh-ID-Vergabe, Evidence-Binding und Confidence-Berechnung einzeln. Reihenfolge ist bewusst: vor den #1316-Filtern angesetzt hätte die Zerlegung Markup- oder Gliederungssatz-Fragmente erzeugt, die diese Filter (laufen nur einmal) nie zu sehen bekommen.
- **`split_compound_claim` erkennt jetzt zusätzlich Doppelpunkt-eingeleitete Bullet-Aufzählungen**, nicht nur Satzgrenzen/Semikolon/Konjunktionen (`sowie`, `und zugleich`, `und gleichzeitig`, `während`, `wohingegen`). Jede Bullet-Zeile wird mit der Einleitung vor dem Doppelpunkt zu einer eigenständigen Teilaussage kombiniert — ein blankes Listenelement wie "S-17 behoben" wäre sonst ohne Bezug und zu kurz für `MIN_ATOM_TOKENS`. Bewusst konservativ: ohne Doppelpunkt vor der Aufzählung greift die neue Erkennung nicht (Gegenprobe getestet), `oder` bleibt weiterhin kein Trennzeichen.
- **Die Export-ID-Vergabe (`ReportManager.build_report_v3`, #1341) ist unberührt** — sie zählt akzeptierte Claims der bereits fertigen Section-Liste und bekommt durch mehr Roh-Atome strukturell nur mehr Slots im selben `section_index`-Namensraum, keine Kollision. Die dedizierten Eindeutigkeitstests (`test_report_v3_contract.py`) laufen unverändert grün.
- **Nebenwirkung, bewusst hingenommen (im Issue benannt):** mehr Atome pro Section verschieben `claim_slot`-basierte Statistiken (Abwertungsquote, Data-Gap-Zahl) nachgelagerter Reports gegenüber älteren Läufen.

### Fixed (Datumswerte in Thresholds — Review PR #1379 — 2026-08-23)

- **Unmögliche ISO-Daten werden am Contract abgelehnt**: Bei explizitem `kind='date'` prüfte der After-Validator nur das Muster `YYYY-MM-DD` — `2026-02-30`, `2026-13-01` und Jahreswerte außerhalb der Grenzen passierten den Backend-Contract, und der Zod-Spiegel prüfte ebenfalls nur die Regex. Jetzt vergleicht der Validator den Wert gegen denselben Parser (`parse_date_value`) und übernimmt damit dessen komplette Kalender- und Jahresprüfung (1900–2100) statt einer zweiten, driftenden Datumslogik; der Zod-Spiegel liest Jahr/Monat/Tag, erzeugt über UTC und vergleicht alle drei Komponenten zurück.
- **Rückwärtskompatibilität numerischer Strings wiederhergestellt**: Vor #1343 war `value` ein reines `float`-Feld — Pydantic konvertierte `"90"` zu `90.0`. Mit `value: float | str` wählte Smart Union für exakte Strings den Textzweig, den die Shape-Prüfung anschließend verwarf; ältere bzw. providerseitig leicht abweichende Payloads wären plötzlich abgelehnt worden. Nach erfolgloser Datumserkennung wandelt der Before-Validator rein numerische Strings (`^-?\d+([.,]\d+)?$`, auch deutsches Kommaformat) wieder zu float um — echte Datumsstrings bleiben Strings.
- **Validierung ohne Seiteneffekte**: Der Before-Validator veränderte das übergebene Dict direkt (`data[...]`, `pop`). Er arbeitet jetzt auf einer flachen Kopie; das Eingabe-Dict bleibt unangetastet.
- **Regressionstests** am Contract-Pfad (nicht Parser) für alle drei Fälle plus Schalttag-Gegenprobe, numerische Coercion (positiv/negativ) und Seiteneffektfreiheit; Spiegel-Tests in `reportV3Contract.spec.ts`.

### Fixed (Datumswerte als numerische Thresholds — 2026-08-23)

- **Aus „15. Oktober 2026“ wurde `{value: 15.0, unit: "October"}`** (#1343, Part of #1297). Der AURORA-Referenzlauf extrahierte Datumsangaben über dieselbe generische Number+Unit-Lesart wie operative Schwellwerte: der Tag als Zahl, der Monatsname als Einheit. Beides ist in keinem Vergleich verwendbar — ein Datum ist keine Menge, es trägt keine Einheit und keinen Sinn als Schwellwert.
- **Contract-Erweiterung um eine `kind`-Diskriminante** (`Threshold.kind: Literal["quantity", "date"] | None = None`, `value: float | str`, `unit` optional): `quantity` ist die operative Zahl mit Einheit, `date` das Kalenderdatum als ISO-Wert (`YYYY-MM-DD`). Bewusst ein flaches Modell statt einer Pydantic-Discriminated-Union — das Schema erreicht über `model_json_schema()` auch Fallback-Provider im json_object-Modus (Ollama), wo anyOf-Unions mit zwei Objektformen unzuverlässig sind. `kind` ist optional mit Default `None`: Bestandsartefakte vor #1343 tragen das Feld nicht und laden unverändert; „nicht erfasst“ ist nicht dasselbe wie eine erfasste quantity (Muster: `Claim.confidence_scope`, #1160 A).
- **Der Datumsparser läuft VOR der Number-Coercion** (`mode="before"`-Validator): ein String, der „15. Oktober 2026“, „15 October 2026“, „2026-10-15“ oder „15.10.2026“ trifft, wird zu ISO normalisiert und auf `kind='date'` festgelegt — auch gegen einen fälschlichen `kind='quantity'`-Anspruch, dessen Einheit als Fehllesart verworfen wird. Nur vollständige Daten mit Jahr gelten; „15. Oktober“ ohne Jahr bleibt eine Lücke statt eines geratenen Werts.
- **Ein Monatsname ist strukturell keine Einheit**: der verstümmelte Eintrag `{value: 15.0, unit: "October"}` wird vom Vertrag verworfen, statt ins Artefakt zu rutschen. Ohne Jahr wäre er nur rekonstruierbar durch Raten — verworfen ist die ehrliche Richtung.
- **Consumer nachgezogen**: Deduplizierung führt Datum-Schlüssel getrennt von Mengen-Schlüsseln (gleiche Label verschmelzen kein Datum mit einer Zahl), die numerische Provenance-Bindung nimmt Datumsangaben aus, Markdown-Tabelle und Red-Team-Excerpt rendern den ISO-Wert ohne Einheit (`display_value`) — vorher wäre `:g` an einem ISO-String mitten im Review-Entwurf gesprengt worden. Die Feldbeschreibungen von `SectionMetadata.thresholds` weisen das Modell an, Datumsangaben ausschließlich als `kind='date'` mit ISO-Wert zu melden.
- **Schema-Dump und Zod-Spiegel synchron**: `schemas/report-v3.schema.json` regeneriert, `frontend/src/contracts/reportV3Contract.ts` spiegelt kind/value/unit samt Monatsnamen-Ablehnung; Drift-Guard für `Threshold` ergänzt. Regressionstests über alle vier Schreibweisen in `test_threshold_kind.py` (Vertrag) und `test_threshold_dates.py` (Pipeline).

### Changed (Referenzlauf 7 als aktuelle Referenz dokumentiert — 2026-08-17)

- **AURORA-Lauf vom 17.08.2026 ersetzt Referenzlauf 6 als aktuelle Referenz:** Englische und deutsche Referenzdokumentation unter `docs/reference-runs/2026-08-17-aurora-red-team/`, Referenzlauf-Index und der Referenzlauf-Abschnitt beider READMEs beschreiben `report_b259e254ee3f` aus der 24-Runden-Simulation `sim_c2108c7f543e`. Der Lauf ist die erste Referenz für das nachgeschaltete Red-Team-Review (9 Befunde, Echo-Index 0,703) und für das aktive Umleiten ungedeckter Faktenaussagen in den Hypothesen-Slot (10 Fälle in fünf von sieben Abschnitten). Er belegt zugleich den Export-Fix aus #1340 bis #1342 am Artefakt: Befunde und Modellzuordnung der Review-Stufe überleben den Neuaufbau, Claim-, Gap- und Hypothesen-IDs sind abschnittsqualifiziert und kollisionsfrei.
- **Kennzahlentabelle statt Screenshots:** Der Referenzlauf-Abschnitt beider READMEs führt Runden, Laufzeit, Evidenzarten, Claims, Hypothesen, Data Gaps und Red-Team-Befunde als Tabelle. Für diesen Lauf liegen keine UI-Screenshots vor; die Bilder von Referenzlauf 6 bleiben ausschließlich dort verlinkt.
- **Offene Trust-Grenzen bleiben als Regressionsziele benannt:** durchgängig `low` Confidence über alle 29 Claims, 92 von 116 ungebundenen Evidenzdatensätzen, 126 Data Gaps mit identischer Severity, fehlende `source_id_anchor`- und `source_model`-Werte sowie die gegenüber Lauf 6 gestiegene Laufzeit, die wegen der anderen Simulation kein direkter Reporter-Vergleich ist. Die erfüllte Erwartung aus Lauf 6 — auflösbare `ev_`-Anker in allen 24 Persona-O-Tönen — ist ausdrücklich vermerkt.

### Fixed (ReportV3: Red-Team-Befunde überleben den Export, Claim- und Gap-IDs sind global eindeutig — 2026-08-17)

- **Red-Team-Befunde verschwanden zwischen Log und Artefakt (#1340):** Der Lauf protokollierte `_run_red_team_review: 8 Befunde` und `generate_report: red_team_review abgeschlossen, findings=8`, im `report-v3.json` stand `"red_team_findings": []`. Ursache waren zwei Schreibpfade auf dieselbe Datei: der Red-Team-Schritt persistiert sein Ergebnis über `ReportManager.save_report_v3()` korrekt, danach läuft im selben `generate_report()` noch `ReportManager.save_report()` und baut das Artefakt über `build_report_v3()` komplett neu auf. Dieser Neuaufbau speist sich ausschließlich aus Report und Evidenzkarte — beide wissen nichts von der Red-Team-Stage, die ihr Ergebnis direkt auf dem ReportV3-Objekt ablegt. Das Feld fiel auf `default_factory=list` zurück und überschrieb die Befunde. `model_attribution` traf es über denselben Pfad: die Modell-Zuordnung der Review-Stage ging genauso verloren. `build_report_v3()` übernimmt beide Felder jetzt aus dem vorhandenen Artefakt (`ReportManager._preserved_review_state()`) — bewusst als Merge und nicht als Umbau der Aufrufreihenfolge, damit das Artefakt unabhängig davon korrekt bleibt, wie oft und an welcher Stelle gespeichert wird. Fehlt das Artefakt oder ist es unlesbar, wird nichts übernommen und der Grund geloggt.
- **Claim- und Gap-IDs kollidierten beim Merge der Abschnitte (#1341, #1342):** `build_report_v3()` übernahm die abschnittsinterne Rohform (`claim_01`, `gap_01`) unverändert als Export-ID. Da jeder Abschnitt bei 1 zu zählen beginnt, legten sich die Nummernräume übereinander: im Referenzlauf standen 10 Claims auf 8 IDs und 125 Datenlücken auf 22. Ein Consumer, der eine ID auflöst, bekam damit irgendeinen der Träger. Exportiert wird jetzt eine abschnittsqualifizierte ID nach demselben Muster, das die Hypothesen im selben Codeblock schon benutzen (`H<n>_<i>`): Claims als `C<abschnitt>_<i>`, Datenlücken als `G<abschnitt>_<i>`. Der Zähler läuft über die *akzeptierten* Einträge — er wird erst hochgezählt, wenn alle Filter (Evidence-Anker, Mindestlänge, `strict`-Modus) passiert sind, damit die ID die finale Liste beschreibt und nicht die Rohextraktion.
- **Der Übertrag gilt nur innerhalb eines Laufs (Codex-Review PR #1349):** Mit `force_regenerate` läuft die Generierung erneut auf derselben `report_id`. Ohne Schnitt hätte jeder Neuaufbau die Befunde des Vorlaufs importiert — und wenn `_red_team_required()` die Stage im neuen Lauf überspringt, wäre der fertige Report mit Befunden zu einem Claim-Set ausgeliefert worden, das es nicht mehr gibt. `generate_report()` verwirft den fremden Review-Stand jetzt zu Laufbeginn (`ReportManager.reset_review_state()`), bewusst nur die beiden Review-Felder und nicht das ganze Artefakt: bricht der neue Lauf ab, bleibt der übrige Bestand lesbar. Geerbte Werte werden außerdem validiert (CodeRabbit-Review) — kein `str()`-Zwang, der aus einem `None` im Artefakt den Befund „None“ macht, und keine Übernahme über `RED_TEAM_FINDINGS_LIMIT` hinaus, die genau den Rebuild sprengen würde, den das Erben retten soll.
- **Auch der zweite ReportV3-Producer vergibt jetzt eindeutige IDs (Codex-Review PR #1349):** `migrate_v2_to_v3()` sagt zu, ein ReportV3-valides Dict zu liefern, übernahm aber dieselbe abschnittslokale Rohform. Mit der Eindeutigkeit im Vertrag hätte jede mehrabschnittige Legacy-Migration ein Dokument erzeugt, das an der eigenen Zusage scheitert. Umgestellt sind dort bewusst nur `claims` und `data_gaps` — die aus derselben `claim_id` abgeleiteten `friction_points` und `trust_signals` tragen ihren eigenen gewachsenen Namensraum, werden vertraglich nicht geprüft und bleiben unverändert; ihr latentes Kollisionsrisiko ist separat zu bewerten.
- **Die Eindeutigkeit ist jetzt Vertragsbestandteil, nicht bloß Testaussage:** `ReportV3.validate_unique_export_ids` lehnt doppelte `Claim.id` und `DataGap.id` ab. Ein Artefakt mit kollidierenden IDs ist nicht unschön, es ist nicht interpretierbar. Der Validator deckte prompt ein Test-Fixture auf, das zwei Claims unbemerkt unter derselben ID führte (`tests/services/test_downgraded_claim_wording.py`). Bestandsartefakte aus der Zeit vor der Umstellung können an der Prüfung scheitern — dann liefert `ReportManager.build_report_v3_markdown()` wie bisher `None` und protokolliert den Grund, statt mehrdeutige IDs weiterzureichen. Das JSON-Schema ändert sich dadurch nicht; alle 70 Schemas matchen unverändert.

### Fixed (Ankerspezifikation aktualisiert, ungebundene Belege werden persistiert — 2026-08-17)

- **`CONTEXT.md` dokumentierte eine Ankerform, die für den Regelfall verboten ist:** Als einzige Form stand dort `seed_doc:<doc_id>#chunk:<chunk_id>`. Seit #1300 lehnen die Validatoren `agent_quote_rejects_seed_doc_anchor` genau diese Form auf Interview-Evidence ab — eine Persona-Aussage steht in keinem Seed-Dokument. Der Abschnitt nennt jetzt beide kanonischen Formen mit ihrer Quellengattung (`ev_<id>` für `agent_quote`, `seed_doc:…` für `seed_corpus`), hält fest, dass `seed_anchor` ein Prompt-Attribut und nicht das Vertragsfeld `source_id_anchor` ist, und dass ein Anker seit #1249 unabhängig von seinem Präfix gegen `known_anchors` geprüft wird (#1324).
- **`unbound_evidence_refs` wurde befüllt, aber nie geschrieben:** `QuoteValidationResult` trug das Feld, `section_pipeline` loggte es an zwei Stellen — im persistierten Artefakt war nicht sichtbar, welcher zitierte Beleg nie gebunden wurde, obwohl genau das den Statuswechsel auf `incomplete` erklärt. `_validate_quotes_with_repair` liefert die Refs des gescheiterten Repair-Versuchs jetzt zurück, `process_section` reicht sie über den bestehenden `_pending_*`-Weg an `_save_evidence_section` durch, und `ReportSectionModel` trägt sie als `unbound_evidence_refs` (`max_length=200`, Default leer — Bestandsartefakte ohne das Feld bleiben gültig). Der Frontend-Spiegel `reportContract.ts` zieht nach, weil sein Schema `.strict()` ist.

### Fixed (Vor #1322 geplante Outlines überstehen den Resume — 2026-08-17)

- **Ein Bestandsreport konnte beim Fortsetzen als `incomplete` enden, obwohl seine Outline korrekt war:** Die Handlungsempfehlung kam mit #1322 nachträglich in die Intent-Presets. `matches_known_preset` verlangt *alle* Titel genau eines Presets; eine davor geplante und persistierte Outline trägt die Empfehlung nicht, fiel damit durch die Preset-Prüfung und anschließend auf den Full-Report-Pflichtsatz zurück — `report.status = INCOMPLETE` mit einer langen `missing_sections`-Liste, obwohl zum Planungszeitpunkt nichts fehlte. Betroffen sind beide Prüfstellen: `workflow.py` und der Validator `require_default_sections` in `report_contract.py`. Gemeldet im Codex-Review zu PR #1331.
- **Die Lockerung gilt genau der Empfehlung, sonst nichts:** Ein Preset trifft jetzt auch dann zu, wenn die Outline ihm ohne `RECOMMENDATION_SECTION_TITLE` entspricht. Presets ohne Empfehlung (`EXPLORATIVE_SECTIONS`) werden dabei übersprungen, statt ein zweites Mal gegen denselben Titelsatz geprüft zu werden. Eine beliebige Kurz-Outline besteht die Prüfung weiterhin nicht — der Full-Report bleibt gegen versehentliche Verkürzung geschützt.

### Added (Berichte enden mit einem Beschlussvorschlag statt mit Datenlücken — 2026-08-17)

- **Kein einziges Section-Preset endete mit einer Empfehlung:** `FULL_SECTIONS` schloss mit „Datenlücken“, die vier Intent-Presets mit „Unsicherheiten und Datenlücken“. Am nächsten kamen „Top 10 Änderungen“ (Position 7 von 11) und „Gegenmaßnahmen“ (Position 5 von 6) — beide mitten im Bericht und beide nicht als Beschlussvorschlag formuliert. Der Leser bekam am Ende, was die Simulation *nicht* weiß, und musste sich die Entscheidung selbst zusammensuchen (#1322).
- **Neue Pflicht-Section „Handlungsempfehlung“** am Ende von `FULL_SECTIONS`, `OPINION_SECTIONS`, `RISK_SECTIONS` und `COMPARISON_SECTIONS`. Ihre Beschreibung gibt die sechs geforderten Elemente vor: empfohlene Variante, Vorbedingungen, Restrisiken, zustimmende und widerständige Akteure, mögliche Positionswechsel, Frühwarnindikatoren. Titel und Beschreibung liegen als `RECOMMENDATION_SECTION_TITLE`/`RECOMMENDATION_SECTION_DESCRIPTION` in `report_prompts.planning` — ein abweichender Wortlaut zwischen den Presets würde `matches_known_preset` auseinanderlaufen lassen.
- **`EXPLORATIVE_SECTIONS` bleibt bewusst ohne:** ein Explorationsbericht soll beschreiben, was auffällt, und offene Fragen offen lassen. Ein Beschlussvorschlag würde dort eine Entscheidungsreife behaupten, die die Fragestellung nicht verlangt hat.
- **Der Pflichtabschnitt-Satz wächst damit von 11 auf 12.** Bestehende gespeicherte Reports sind davon nicht betroffen: `ReportOutlineModel` wird ausschließlich beim Planen eines neuen Reports gebaut (`report_agent/planning.py`), das Laden geht über die Dataclass `ReportOutline` und validiert nicht gegen den Pflichtsatz. `ReportOutlineModel.sections` hat `max_length=15`, der Puffer reicht. Mitgezogen: Snapshot `output-contract-required-sections.txt`, der eingebettete Container-Fallback in `llm_e2e_stub` (dabei `_eleven_required_sections` zu `_required_sections` umbenannt — der Name stimmte nicht mehr) und die Zählungs-Assertions in vier Testdateien.

### Fixed (Token-Cap bei der Metadaten-Extraktion wird sichtbar — 2026-08-17)

- **Eine stumme Truncation degradierte den Report ohne Begründung im Log:** Lief `generate_section_metadata` in ein LLM-Token-Limit, warf der Provider `LLMOutputTruncatedError`, die Funktion fing sie über das generische `except Exception` ab und lieferte `{}` — der spätere `status = incomplete` (#1299) stand im `console_log.txt` ohne jede Erklärung (#1321).
- **`LLMOutputTruncatedError` bekommt jetzt einen eigenen degradation_log-Eintrag:** `generate_section_metadata` erkennt die Truncation gesondert und hängt einen contract-konformen Eintrag (Feldform nach `EvidenceDegradationModel`) an `agent.evidence_map["degradation_log"]` an, sofern die Evidence-Map an dieser Stelle bereits ein dict ist — sonst wird nur geloggt. `return {}` bleibt unverändert nicht blockierend; die Section-Schleife läuft weiter.
- **Die Extraktion setzt jetzt ein eigenes `max_tokens` statt `LLM_MAX_TOKENS_FLOOR` zu erben:** Der Boden ist für volle Fließtext-Sections gedacht; die Metadaten-Extraktion ist eine andere Aufgabe und soll nicht mitwandern, wenn jemand ihn für die Prosa nachjustiert. Neue Modulkonstante `METADATA_MAX_OUTPUT_TOKENS = 32768` mit `enforce_token_floor=False`.
- **Der Wert ist bewusst nicht kleiner:** Naheliegend wäre ein enger Deckel gewesen — die Extraktion liefert kompaktes JSON. Genau das wäre falsch. Im beobachteten Lauf lief sie in das Ausgabelimit von `gemini-2.0-flash` (8192), und dieses Modell ist Legacy: aktuelle Gemini-Modelle greifen über den `gemini-3`-Präfix und lösen auf 65536 auf. Ein Deckel von 8192 hätte ihnen das Legacy-Limit aufgezwungen — ausgerechnet den Wert, bei dem die Truncation auftrat. 32768 entspricht dem, was für Modelle mit ausreichendem Limit ohnehin galt; der Wert ist heute verhaltensneutral, entkoppelt die Extraktion aber vom Prosa-Boden. `resolve_max_tokens` deckelt weiterhin pro Modell, Legacy-Modelle behalten also ihre 8192 — nur bleibt ein Anschlag dort jetzt nicht mehr stumm.
- **Zur Einordnung: das behebt die Truncation selbst nicht.** Der Hebel dafür liegt auf der Eingangsseite (`METADATA_MAX_CONTENT_CHARS`, Schemagröße) und gehört in einen eigenen Slice. Geändert hat sich, dass ein Anschlag sichtbar wird und der Grenzwert eine Entscheidung ist statt eines Nebenprodukts.
- **Nicht umgesetzt:** die Arbeitsspur-Entfernungen aus `_finalize_content` (`workflow.py:345-351`) landen weiterhin nur im Log. Die Funktion hat an dieser Stelle keinen Zugriff auf `agent`, und eine Signaturänderung quer durch den Aufrufbaum gehört nicht in diesen Fix. Bleibt in #1321 offen.

### Fixed (Entfernte Arbeitsspur-Segmente werden im Bericht nachvollziehbar — 2026-08-23)

- **Eine still bereinigte Section war von einer unangetasteten nicht zu unterscheiden:** `_finalize_content` entfernte Arbeitsspur-Segmente (Thought-/Action-Zeilen, Tool-Call-Reste) aus dem Abschnittsinhalt und schrieb das nur ins Server-Log — der Bericht wies den Abschnitt aus wie jeden anderen (#1321).
- **`_finalize_content` nimmt jetzt einen optionalen `agent` entgegen** und trägt eine Bereinigung mit erhaltenem Inhalt in `RunEventLog.work_trace_removed_sections` ein. Am Laufende zieht `collect_run_degradations` die Summe als `N_sections_sanitized`-Eintrag in `report.run_degradations` (Schwere `warning` — der Inhalt selbst ist ja erhalten, ein Statusabstieg wäre unverhältnismäßig). Alle drei Aufrufer reichen den Agenten durch.
- **Der Marker überlebt jetzt auch Cancel und Resume:** Er lebte nur im flüchtigen RunEventLog des aktuellen Agenten — der Teil-Report nach kooperativem Abbruch erreichte die einzige Degradations-Aggregation nie, und beim Resume liefen bereits persistierte Sections nicht erneut durch `_finalize_content`; die Warnung blieb endgültig verloren. `_build_partial_report` zieht die Summe jetzt selbst, und der Zustand wird pro Section in `run_events.json` neben dem Report persistiert (`ReportManager.save_/load_work_trace_removed_sections`) und beim Resume vor der ersten Cancel-Grenze wiederhergestellt — dedupliziert, sodass die Warnung auch nach Fortsetzung genau einmal steht.
- **Der `FinalContentRejected`-Fall bleibt bewusst unmarkiert:** Wirft der Final-Content-Contract den ganzen Output weg, endet der Abschnitt im Fallback-Text und ist über `generation_failed` bzw. `failed_section_indices` bereits sichtbar — ein zweiter Marker würde denselben Abschnitt doppelt zählen.
- **`generation_failed` wird nicht an fehlgeschlagene Metadaten gekoppelt:** Der Flag heißt "der Abschnittsinhalt ist Fallback". Eine gescheiterte Extraktion bei vorhandenem Inhalt ist kein Generierungsfehler; sie ist über die bestehende `N_sections_without_metadata`-Warnung sichtbar. Eine Kopplung hätte erfolgreiche Sections fälschlich auf `incomplete` abgestuft.

### Fixed (Interview-Transkripte erfinden keine stumme Plattform mehr — 2026-08-17)

- **Jedes Interview trug einen leeren `[Twitter Platform Response]`-Block:** Im Referenzlauf standen 32 Interview-Traces in `reddit_simulation.db` und 0 in `twitter_simulation.db`, trotzdem rendered `GraphToolsService.interview_agents` für alle 42 Interviews beide Plattformen — die stumme mit dem Platzhalter `(No response from this platform)`. Das sah wie eine gescheiterte Befragung aus, war aber eine, die nie stattgefunden hat: der Direktpfad (`interview_agents_batch_direct`, der Normalfall für abgeschlossene Simulationen) ist bewusst single-platform, der Renderer wurde nie nachgezogen (#1320).
- **Gerendert werden nur noch Plattformen, die geantwortet haben:** Antworten beide, bleiben beide Blöcke mit ihrem Marker stehen. Antwortet keine, bleibt genau ein Platzhalter statt zweier — der Report-Agent erkennt daran weiterhin das gescheiterte Interview und verwirft es als Evidence (`_INTERVIEW_NO_RESPONSE`). Die Zitat-Extraktion arbeitet nur noch auf den tatsächlichen Antworten.
- **Zusatzdefekt, nicht in der ursprünglichen Kritik: der Einzelplattform-Runner schrieb einen Schlüsselraum, den niemand liest.** `sim_runtime/ipc.py::handle_batch_interview` legte die Ergebnisse unter der blanken `agent_id` ab; der Consumer sucht sie unter `<plattform>_<agent_id>`. Damit ging der Lookup für **beide** Plattformen ins Leere — nur `run_parallel_simulation.py` erzeugte die erwarteten Schlüssel. `IPCHandler` bekommt dafür ein `platform_key`, das `SinglePlatformRunner` aus seinem `PLATFORM_NAME` setzt; jeder Eintrag trägt zusätzlich sein `platform`-Feld wie im Parallel-Runner.

### Fixed (Datenlücken-Vorschlag wiederholt nicht mehr den Claim-Text — 2026-08-17)

- **`suggested_fix` einer Datenlücke war identisch mit dem Claim-Text:** Der Zweig `if not supporting_ids:` in `_finalize_section_claims` nahm für `suggested_fix` das erste Element von `suggestions` — bei fehlender direkter Evidence ist das der Synthesis-Audit-Eintrag mit `snippet = claim_text[:300]`. Im Referenzlauf betraf das 93 von 93 Datenlücken (#1319).
- **`suggested_fix` wird jetzt aus `gap_reason` abgeleitet:** `no_evidence_bound` liefert den Hinweis, gezielt einen Beleg zu recherchieren oder die Aussage zu streichen; `related_evidence_only` verweist darauf, eine Quelle mit direktem Aussagebezug zu suchen statt der nur thematisch verwandten. Die per LLM/Audit ermittelten `suggestions` bleiben unverändert als `suggested_evidence` an der zugehörigen Hypothese erhalten.
- **Die Doppelung Hypothese/Datenlücke ist als Beziehung ausgewiesen:** Beide entstehen im selben Zweig aus demselben `claim_text`. `data_gaps` trägt jetzt `hypothesis_id`, und `build_report_v3` übernimmt den Verweis als `DataGap.related_hypothesis_id` in den ReportV3-Vertrag — aus einer stummen Wiederholung wird eine auflösbare Beziehung. Der Verweis trägt die exportierte Hypothesen-ID (`H<n>_<i>` / `HA<n>_<i>`), nicht den abschnittsinternen Rohschlüssel, und entfällt, wenn Dedup oder Appendix-Cap die Hypothese entfernt haben — sonst zeigt er auf eine ID, die in der Hypothesentabelle des Artefakts nicht vorkommt. Die ReportV3-Datenlückentabelle bekommt dafür eine eigene Spalte, `reportV3Contract.ts` spiegelt das Feld. `claim_text` bleibt im Dict, weil `manager.py` es für die `beschreibung` braucht; die Datenlücke ohne ihn zu rendern würde den Leser zu einem Lookup zwingen. `ReportSectionDataGapModel` bekommt das neue optionale Feld, der Frontend-Spiegel `reportContract.ts` zieht nach — dessen Schema ist `.strict()` und hätte das neue Backend-Feld sonst zurückgewiesen.
- **`severity` einer `ReportV3DataGap` war hartkodiert `"medium"`:** `build_report_v3` leitet sie jetzt aus `gap_reason` ab — `no_evidence_bound` (keine Quelle gebunden) wird `"high"`, `related_evidence_only` (Quelle vorhanden, aber ohne Aussagebezug) bleibt `"medium"`.

### Fixed (Evidence-Duplikate verzerrten das Confidence-Mittel — 2026-08-17)

- **`EvidenceCandidatePool` deduplizierte nicht:** `agent.py` reicht `direct_items + global_items` in den Pool — beide Quellen werden nirgends disjunkt gehalten, dieselbe `evidence_id` konnte in beiden stehen. Ohne Dedup landete so ein Item doppelt im Pool, konnte zweimal an denselben Claim binden und zählte doppelt im Mittelwert von `confidence_calculator._component_relevance`. Der Konstruktor dedupliziert jetzt nach `evidence_id`, erstes Vorkommen gewinnt, die Reihenfolge bleibt stabil. Items ohne oder mit leerer `evidence_id` haben keine Identität zum Abgleichen und bleiben alle erhalten — ein leerer String als Schlüssel würde verschiedene Items zusammenfallen lassen und wäre ein stiller Datenverlust (#1318).
- **`contradicts_claim` in `detect_contradiction_penalty` ist redundant, nicht kaputt (#1327):** Die Boolean-Flag-Schleife prüft nur `supporting`-Items und sieht ein binder-erzeugtes `contradicts_claim=True` deshalb nie — das sieht nach totem Code aus. Der vollständige Pfad zeigt etwas anderes: `confidence_calculator.partition_by_entailment` zählt genau dieses Item bereits als `contradicting`, und `_compute_confidence_with_penalties` zieht dafür 0.2 ab. Da `report_agent/agent.py` das Ergebnis von `detect_contradiction_penalty` als `contradiction_penalty` in ebendiesen Rechner reicht, wäre eine Öffnung der Schleife ein doppelter Abzug für denselben Widerspruch. Die Schleife bleibt deshalb auf `supporting` beschränkt und deckt weiterhin den Fall ab, den der Entailment-Pfad nicht kennt: ein stützendes Item mit `is_contradiction`/`contradiction` aus fremder Quelle. Der Grund steht jetzt im Code und ist durch drei Tests festgehalten — kein Doppelabzug, der Entailment-Pfad bestraft nachweislich trotzdem, und das fremde Flag wirkt weiterhin.

### Fixed (nicht messbare Deckung wird nicht mehr als Widerspruch gewertet — 2026-08-17)

- **Eine "Deckung 0.00" bedeutete bisher "widerlegt", auch wenn gar nichts gemessen wurde:** `coverage_ratio` liefert 0.0 sowohl, wenn der Claim tatsächlich mehr behauptet als die Quelle deckt, als auch, wenn `_content_tokens` das Prädikat von Claim oder Evidence auf ein leeres Set kürzt — Stopwords und Tokens mit `len <= 3` fallen dort komplett weg. Ein kurzes Prädikat wie "sind da" ergab damit dieselbe Deckung 0.00 wie ein tatsächlich unbelegter Überschuss, und `classify_evidence` vergab in beiden Fällen `CONTRADICTED` (#1317).
- **`classify_evidence` unterscheidet jetzt beide Fälle:** Zahl und Bezugsgruppe passen, aber Claim- oder Evidence-Prädikat liefert nach dem Stopword-/Kurzwort-Filter kein Inhaltswort — das ergibt `INSUFFICIENT` mit dem Hinweis, dass die Aussage zu kurz ist, um gegen die Quelle geprüft zu werden (`predicate_not_measurable`). Die vier übrigen `CONTRADICTED`-Zweige (Normativ-vs-Faktisch, Prädikat-Überschuss bei tatsächlich gemessener Teildeckung, abweichendes Subjekt, abweichender Zahlenwert) bleiben unverändert.
- **Eine Verneinung bleibt ein Widerspruch:** `nicht` steht selbst in `_STOPWORDS`, deshalb reduzieren „sind da“ und „sind nicht da“ beide auf ein leeres Content-Token-Set. Vor der Nicht-messbar-Entscheidung wird jetzt die Polarität verglichen — gleiche Zahl, gleiche Bezugsgruppe, gegensätzliche Verneinung ergibt `CONTRADICTED` mit `polarity_mismatch`. Die Prüfung ist bewusst grob und macht keine Skopusanalyse; sie trennt nur zwei sonst nicht unterscheidbare Prädikate.
- **Was sich dadurch ändert und was nicht:** `verify_prose` behält einen numerischen Satz weiterhin nur bei `SUPPORTED` — ein nicht prüfbarer Satz wird also nach wie vor aus dem Fließtext entfernt und in die Hypothesen geroutet. Das ist Absicht: unbelegte Zahlen stehen zu lassen wäre eine Aufweichung des Evidence-Gatings und damit eine ADR-0002-Entscheidung, kein Bugfix. Geändert hat sich die *Begründung*, mit der er fällt — statt eines behaupteten Widerspruchs steht jetzt "nicht prüfbar" an der Hypothese. Auf dem Binder-Pfad entfällt zugleich das `contradicts_claim`-Flag, das `bind_evidence_to_claim` bei `CONTRADICTED` setzt.

### Fixed (Claim-Extraktion bindet kein Markup und keine Gliederungssätze mehr — 2026-08-17)

- **Die Claim-Extraktion bekam rohes Zitat-Markup:** `process_section` reichte denselben ungereinigten `content` an `save_section` und `_save_evidence_section` weiter. Nur `save_section` reinigte ihn intern — die Extraktion las die `<simulated_quote>`-Tags mit und zerlegte sie in Claim-Kandidaten, für die es naturgemäß keine Evidenz geben kann. Der Evidence-Pfad geht jetzt über `ReportManager.prepare_content_for_evidence`, das die Zitate zu Blockquotes rendert (#1316).
- **Bewusst nicht die volle Reinigung für den Evidence-Pfad:** `_clean_section_content` wandelt zusätzlich jede Markdown-Überschrift in Fettschrift um. Das ist eine Darstellungsfrage des Dateipfads und für die Extraktion schädlich — sie erkennt Überschriften am `#`, und der Bold-Filter in `is_claim_candidate` greift nur unterhalb von acht Wörtern. Eine lange Zwischenüberschrift wäre so als Aussage gebunden worden. `prepare_content_for_evidence` macht deshalb nur den einen Schritt, den die Extraktion braucht.
- **Zitatblöcke und Tag-Zeilen sind keine Claim-Kandidaten mehr:** Die Teilprüfung, mit der der Fließtext-Validator leere Zeilen, `>`/`|`-Zitatpräfixe und vollständig getaggte Zeilen aussortiert, ist als `is_markup_or_quote_line` aus `text_verification._is_structural` herausgezogen und wird jetzt auch von `is_claim_candidate` verwendet — eine Definition statt zweier. Ergänzend fällt Rest-Markup aus dem Section-Prompt heraus (`simulated_quote`, `tool_call`, `evidence_gating`, `self_check`), roh wie HTML-escapt.
- **Gliederungsansagen werden nicht mehr als Aussagen gebunden:** „Im Folgenden werden die Reaktionsmuster dargestellt.“ kündigt an, was der Abschnitt zeigt, und behauptet selbst nichts — als Claim gebunden ergibt sie zwangsläufig eine unbelegte Hypothese. `is_atomic_claim` verwirft solche Sätze. Der Filter ist bewusst eng: bestimmte Satzanfänge sowie die Kopplung aus Folgend-Verweis und passivem Darstellungsverb im selben Satz. „Die Personagruppe wird in den Interviews als skeptisch beschrieben.“ bleibt deshalb Claim.
- **Der Chunk-Fallback holt den verworfenen Metasatz nicht mehr zurück:** `_build_claims_for_section` fällt auf den ganzen Chunk zurück, wenn kein Atom den Filter passiert — damit eine legitime Single-Sentence-Section nicht verschwindet. Steht die Gliederungsansage als eigener Absatz, war `atoms` genau deshalb leer und `atoms or [chunk]` setzte den Satz unverändert wieder ein, womit der Filter wirkungslos blieb. Der Fallback ist jetzt für Gliederungsansagen ausgesetzt, für alles andere unverändert.

### Fixed (der Markdown-Export kehrt die Aussage des Berichts nicht mehr um — 2026-08-17)

- **Ein `incomplete`-Report lieferte beim `.md`-Download die annotierte Roh-Narrative statt des Contract-Artefakts:** `save_report` schrieb `report-v3.json` nur bei `COMPLETED`. Wurde ein Report per [#1299](https://github.com/arn0ld87/agora/issues/1299) auf `incomplete` abgestuft — etwa weil die Metadaten-Extraktion in den Token-Cap lief und `ReportV3.model_validate` deshalb scheiterte —, gab es kein v3-Artefakt, `build_report_v3_markdown()` lieferte `None`, und der Export-Endpunkt fiel auf `report.markdown_content` zurück. Im Referenzlauf `report_3c594fcc7613` war das exportierte Dokument dadurch 2,3-mal so lang wie die Rohprosa und bestand zu 57 % aus Annotation: 91× `Hypothese (unbelegt):` mitten im Fließtext, 45× sichtbares `&lt;simulated_quote&gt;`, 28× rohes `<span class="conf-badge">` (#1315). Das v3-Artefakt wird jetzt auch bei `INCOMPLETE` geschrieben, sofern es valide ist; der Statuswert selbst bleibt unberührt.
- **Bleibt der Fallback nötig, ist er als solcher gekennzeichnet:** Bestandsreports ohne Evidence-Map bekommen weiterhin `markdown_content`, jetzt aber mit vorangestelltem Hinweis, dass es sich nicht um das validierte Contract-Artefakt handelt.
- **Der Unbelegt-Marker steht einmal pro Hypothese statt an jeder Fundstelle:** `mark_hypotheses_in_content` nutzte `re.sub` ohne `count` und markierte damit jedes Vorkommen; zusätzlich markierte eine Hypothese, die Teilstring einer längeren war, dieselbe Passage ein zweites Mal — daher die drei Marker im selben Absatz. Die Zuordnung läuft jetzt über Span-Claiming gegen den Originaltext: erster Treffer je Hypothese, keine Überlappung. Appendix-Hypothesen bleiben markiert (sie sind genauso unbelegt, alles andere wäre ein Rückfall hinter [#1232](https://github.com/arn0ld87/agora/issues/1232)); neu ist, dass die Hypothesenliste ihre Restzahl ausweist, statt den Marker auf eine Aufzählung ohne diesen Satz zeigen zu lassen.
- **Confidence-Marker haben eine Markdown-Variante:** `render_claim_to_markdown(claim, raw_html=False)` liefert Fettung statt `<span class="conf-badge …">`. Der Default bleibt unverändert, damit der HTML-/Print-Pfad (CSS in `frontend/src/composables/useReportExports.ts` und `frontend/src/assets/styles/global.css`) weiter funktioniert.
- **Der Fallback liefert kein unrendertes HTML mehr:** Scheitert `build_report_v3` selbst an der Validierung — genau das Token-Cap-Szenario, das den Downgrade auf `incomplete` überhaupt auslöst ([#1321](https://github.com/arn0ld87/agora/issues/1321)) —, entsteht kein Artefakt und die Narrative bleibt der Fallback. Sie wird jetzt über `strip_raw_html_markers` gereinigt: die `<span class="conf-badge …">`-Badges werden zu Markdown-Fettung. Der gespeicherte `markdown_content` bleibt unverändert, damit das Frontend seine gefärbten Badges behält.

### Changed (Persona-Floor 50 → 20 — 2026-08-12)

- **`MIN_PERSONA_TABLE_ROWS` von 50 auf 20 gesenkt:** praktische Läufe mit kleineren DACH-Seed-Dokumenten erreichen nach typbasierter Vorfilterung, Dedup und LLM-seitiger Eignungsprüfung häufig nur ~40 elige Personas und scheiterten am harten 50er-Report-Gate (`Persona-Mindestanzahl nicht erreicht: 42/50`), obwohl der Report inhaltlich erstellbar war. 20 hält eine statistisch noch belastbare Untergrenze für die Persona-Tabelle, lässt dokumenttreue Runs aber durch.

### Fixed (nginx-Sidecar — 2026-08-13)

- **502 nach Backend-Container-Neubau behoben:** `deploy/nginx/agora.conf` nutzte literale `proxy_pass http://agora:5001;`-Direktiven, nginx cachte die IP prozesslebenslang. Jetzt: Docker-Resolver `127.0.0.11` (`valid=10s`) + Variablen-`proxy_pass` löst den Upstream pro Request auf. Regressionstest: `backend/tests/test_nginx_upstream_resolution.py`.

### Fixed (install.sh — 2026-08-13)

- **`ensure_secret` robuster:** Fehlende Keys werden angehängt statt still übersprungen; fail-fast wenn der Key danach nicht in `.env` steht. Regressionstest: `backend/tests/test_install_ensure_secret.py`.

### Fixed (AURORA reference screenshots — 2026-08-14)

- **Reference documentation:** Replaces the unreadable AI-rerendered AURORA screenshots with literal crops from the original UI captures, preserving readable Evidence Inspector, claim and `agent_interview` text in both English and German documentation. (#1307)

### Changed (AURORA-Referenzlauf dokumentiert — 2026-08-14)

- **AURORA als Referenzlauf 6 dokumentiert:** Englische und deutsche Referenzdokumentation, Referenzlauf-Index und anklickbare Evidence-Inspector-Screenshots beschreiben den Same-Simulation-Reportvergleich sowie bekannte Trust-Grenzen ausdrücklich als beobachtbare Regressionreferenz statt als vollständig reproduzierbaren Golden Run. (#1305)

### Added (Der Report weist aus, wie viel die Simulation zu ihm beiträgt — 2026-08-17)

- **Die Kritik „24 Runden Simulation, 0 % Beitrag“ war richtig und unbelegbar zugleich:** Es gab keine Zahl, gegen die man sie hätte prüfen können — und nach jedem Eingriff an Sampling oder Interviewkontext wäre unklar geblieben, ob er gewirkt hat. `compute_simulation_contribution` zählt jetzt über dieselbe Evidenzkarte, aus der `build_report_v3` seine Claims baut: kein zweiter Datenpfad, der driften kann (#1304, S3).
- **Drei Ebenen, absichtlich getrennt ausgewiesen:** `claims_with_simulation_evidence` (irgendein Simulationsbeleg, Interviews eingeschlossen), `claims_with_action_evidence` (mindestens eine beobachtete Aktion aus Phase 3) und `claims_requiring_action_evidence` (*alle* stützenden Belege sind Aktionen — ohne die Simulationsrunden gäbe es die Aussage nicht). Die mittlere Zahl allein überschätzt den Beitrag, die letzte allein unterschätzt ihn.
- **Gezählt wird nur, was auch validiert ist:** Ein Beleg ohne `supports_claim=True` trägt die Aussage nicht, egal wie ähnlich er ist; Hypothesen und Datenlücken sind per Definition unbelegt und würden die Quote beschönigen. Ohne validierte Aussage sind die Anteile `None`, nicht `0.0` — eine Null würde „kein Beitrag“ behaupten, wo nichts gemessen wurde.
- **Sichtbar im Artefakt und im Export:** `ReportV3.simulation_contribution` (additiv, Default `None` — Bestandsreports laden unverändert), gespiegelt in `reportV3Contract.ts`, und als eigener Block direkt unter dem Simulationsstand im ReportV3-Markdown. 24 Runden auszuweisen und zu verschweigen, dass keine Aussage darauf beruht, wäre die halbe Wahrheit.

### Fixed (Aktions-Sampling ist nicht mehr inhaltsblind — 2026-08-17)

- **Ein `like_post` an der Bin-Grenze schlug einen ausformulierten Beitrag:** `sample_actions_timeseries` zog aus jedem Zeit-Bin das erste Element, rein positional. Von 355 Aktionen erreichten so acht die Evidence-Schicht — und welche acht, entschied die Sortierung, nicht der Inhalt (#1304, S2).
- **Bevorzugt wird jetzt der längste Textbeitrag des Bins.** Trägt kein Eintrag eines Bins Text, bleibt es beim ersten: ein Bin ohne Textbeitrag soll seinen Platz behalten, damit die Zeitreihe keine Lücken bekommt. Die Bin-Struktur — der eigentliche Sinn der Funktion — bleibt unangetastet.
- **Der größere Befund lag daneben: die gezogene Evidence trug gar keinen Text.** Der Snippet war reine Metabeschreibung — `Anna create_post on reddit in round 3`. Gegen so einen Text kann kein Entailment eine Aussage stützen, egal wie gut gesampelt wurde. Damit war jede Agentenaktion strukturell unfähig, einen Claim zu tragen — die eigentliche Erklärung für die 0 % aus der Kritik, die auch besseres Sampling allein nicht behoben hätte. Der Beitragstext steht jetzt im Snippet (auf 600 Zeichen gekürzt).

### Fixed (Interviewte Personas kennen ihre eigenen Simulationsbeiträge — 2026-08-17)

- **Die Persona wusste im Interview nichts von ihren eigenen 10–20 Runden:** `build_persona_messages` baute den System-Prompt allein aus Profil und Simulationsfragestellung. Die Antworten klangen plausibel und bezogen sich auf nichts, was die Persona in der Simulation tatsächlich getan hatte — einer der Gründe, warum sich im Referenzlauf keine validierte Aussage auf eine Agentenaktion stützt (#1304, S1).
- **Der Prompt trägt jetzt die eigenen Beiträge:** `interview_agents_batch_direct` lädt sie über `action_log_reader.get_all_actions` für genau diese `agent_id` und Plattform. Gerendert werden die **letzten** acht Einträge in ihrer chronologischen Reihenfolge, jeder auf 240 Zeichen gekürzt: gefragt wird nach der aktuellen Haltung der Persona, nicht nach der aus Runde eins.
- **Fehlende Historie ist kein Fehler:** Ohne Aktionslog, ohne Einträge zu dieser `agent_id` oder bei einem Lesefehler bleibt der Prompt byte-identisch zum bisherigen. Ein Interview ohne Historie ist schlechter, aber immer noch eines.
- **Das falsche Versprechen im Interview-Prefix ist eingelöst:** `graph_tools.py` versicherte der Persona wörtlich, sie möge *"all past memories and actions"* einbeziehen. Auf dem Direktpfad — dem Normalfall für abgeschlossene Simulationen — existierten diese im Kontext gar nicht. Ein Versprechen, das der Kontext nicht einlöst, lädt das Modell zum Erfinden ein; der Prefix verweist jetzt auf das, was tatsächlich mitgeliefert wird.

### Added (`interview_panel.py` — Panel-Rotation für Abschnitts-Interviews, 2026-08-23)

- **Mehr Interviews bedeuteten bisher mehr vom Gleichen:** Im Referenzlauf interviewten Abschnitt 1, 3 und 5 praktisch dasselbe Fünferpanel — die LLM-Auswahl in `_select_agents_for_interview` hatte kein Run-Gedächtnis. Mehr Interview-Budget machte den bestehenden Konsens nur lauter, statt neue Perspektiven zu bringen (#1303).
- **Neu: `InterviewPanelTracker` (`backend/app/services/interview_panel.py`) ist dieses Run-Gedächtnis.** Eine `GraphToolsService`-Instanz lebt genau einen Report-Lauf, damit ist das Tracking automatisch lauf-scoped. Kandidaten werden in drei Prioritätsklassen geordnet: frisch (noch nie befragt) schlägt regelkonforme Wiederverwendung (unter dem Limit **und** signifikant anderer Aspekt), und erst wenn beide das Panel nicht füllen, greift der Ausschöpfungs-Fallback — Wiederverwendung trotz Limit, mit anderem Aspekt bevorzugt, gleicher Aspekt als letzter Ausweg, weil ein leeres Panel den Bericht seine Stakeholder-Stimmen kostet.
- **Interpretation von „signifikant anders“:** zwei Anforderungstexte gelten als unterschiedliche Aspekte, wenn ihre Inhaltswoerter (≥ 4 Zeichen, Stopwörter entfernt) eine Jaccard-Ähnlichkeit unter 0.5 haben. Bewusst lexikalisch und billig — ein Judge-LLM-Call je Section wäre ein zusätzlicher Call pro Abschnitt für wenig Zuwachs gewesen.
- **Die LLM-Auswahl bleibt Vorschlag, der Tracker die Garantie:** Nutzungszahlen wandern als `times_interviewed` in den Auswahl-Prompt (besseres Ranking innerhalb der Klassen), der harte Nachfilter im Tracker setzt sie aber auch dann durch, wenn das Modell darauf nicht hört. Eingriffe landen mit Begründung in `selection_reasoning` und bleiben damit im Berichts-Trace nachvollziehbar.
- **Konfigurierbar über `REPORT_INTERVIEW_MAX_PER_PERSONA`** (Default 2, wie im Issue gefordert); `0` schaltet die Rotation als Notbremse ab.
- **Metrik assertierbar:** `panel_overlap_ratio(panel_a, panel_b)` (Jaccard über Persona-Namen) macht sinkende Panel-Überlappung zwischen Abschnitten prüfbar; 19 neue Tests in `test_interview_panel_rotation.py`, darunter die beiden Testplan-Szenarien (5 Personas × 5 Abschnitte → jede Persona max. 2×; Ausschöpfung → Wiederverwendung mit anderem Kontext) und die Verdrahtung über `interview_agents`.

### Added (`requirement_checker.py` — maschinelle Vollständigkeitsprüfung vor dem Report-Abschluss, 2026-08-23)

- **`completed` hieß bisher nur „die Pipeline ist durchgelaufen", nicht „der Bericht behandelt alles Geforderte":** Der Reporter setzte den Status ab, ohne zu prüfen, ob Widersprüche zwischen Stakeholdern, Frühwarnindikatoren, Stop-/Expand-Bedingungen, Positionswechsel und Koalitionen im Text stehen. Genau diese Aspekte verspricht die Pflicht-Section „Handlungsempfehlung" (#1322), und die Aurora-Regressionserwartung Nr. 5 verlangt, dass Frühwarnindikatoren und Stop-/Expand-Kriterien im finalen Report sichtbar bleiben (#1302).
- **Neu: `RequirementChecker` (`backend/app/services/report_agent/requirement_checker.py`).** Deterministische Mustersuche über den fertigen Berichtstext — kein LLM-Urteil, es geht um das Vorhandensein benannter Aspekte. Pro fehlendem Requirement entsteht ein `requirement_checker`-Eintrag mit `severity=blocking`; die Statusabstufung übernimmt die bestehende `apply_run_degradation_downgrade`-Mechanik aus #1277 — keine zweite parallele Statuslogik neben #1006/#1299.
- **Die Naht liegt nach dem ReportV3-Build, vor dem ersten `save_report`:** Der Contract-Export entscheidet bis dahin mit COMPLETED (sonst würde der V3-Build übersprungen und das Artefakt fehlte); erst danach stuft der Checker ab und persistiert Status + Fehlerliste in einem einzigen Save.
- **„Alle vier Varianten" = die vier entscheidungsorientierten Presets:** FULL, OPINION, RISK und COMPARISON tragen laut #1322 dieselbe Handlungsempfehlung und damit dieselbe Default-Checkliste. Der explorative Report prüft bewusst nichts — er soll offene Fragen offen lassen und keinen Entscheidungsreifegrad behaupten; ein Gate auf Empfehlungsaspekte hätte jeden Explorativ-Report dauerhaft INCOMPLETE gesetzt.
- **Checkliste ist Daten, nicht Code-Pfad:** `Requirement(id, title, description, patterns)` als frozen Dataclass, `DEFAULT_REQUIREMENT_CHECKLIST` als Tupel, `checklist_for_intent()` als Intent-Mapping, eigene Checklisten per Parameter übergebbar. Notbremse: `REPORT_REQUIREMENT_CHECKER_ENABLED=false`.
- **Erkennungsmuster sind bewusst breit** (z. B. „Widerspruch/Konfliktlinie/Kontroverse", „Stop-Bedingung/-kriterium/Abbruchkriterium"): die Prüfung stellt Vollständigkeit fest, keine Formulierungstreue. Ein Aspekt gilt als behandelt, sobald er in irgendeinem Abschnitt steht.
- **Tests:** 29 neue Unit-/Integrationstests (`test_requirement_checker.py`, `test_report_requirement_gating.py`) inklusive der Testplan-Fälle — vollständiger Report → COMPLETED erlaubt, Report ohne Stop-Bedingungen → INCOMPLETE mit persistierter Fehlerliste in `run_degradations`. Drei Bestandsfixtures tragen jetzt checklistenerfüllenden Text, damit sie weiterhin ihr eigentliches Thema isolieren.
- **Die Checkliste folgt der Berichtssprache.** `REPORT_LANGUAGE` ist eine persistierte Nutzereinstellung und steuert bereits die Generierung; der Checker prüfte trotzdem immer gegen deutsche Muster. Ein englisch erzeugter Report hätte damit alle Aspekte gleichzeitig als fehlend gemeldet und wäre dauerhaft `incomplete` gewesen. `Requirement` trägt jetzt `patterns_en` neben `patterns`; die Auswahl **ersetzt** die Musterliste statt sie zu ergänzen, damit ein deutscher Report nicht durch englische Treffer als vollständig gilt. Unbekannte Sprachwerte fallen konservativ auf Deutsch zurück.
- **Stop-/Expand-Muster erkennen Plural- und Kombiformen.** Die früheren Muster akzeptierten nur den Singular direkt hinter dem Präfix. Dadurch fiel ausgerechnet `Stop-/Expand-Kriterien` durch — die Schreibweise, die der Modul-Docstring selbst als Regressionserwartung Nr. 5 des Aurora-Referenzlaufs zitiert. Ebenso `Stopkriterien`, `Stoppkriterien` und `Abbruchkriterien`. Ein Report hätte die beworbene Anforderung erfüllt und wäre trotzdem abgestuft worden.

### Fixed (E2E-Regression aus #1302 behoben, #1387, 2026-08-24)

- **Der E2E-Stub kannte den neuen Vertrag nicht:** Der Checker prüft `report.markdown_content` gegen sechs Pflichtaspekte (s. o.), aber `llm_e2e_stub.py::_STUB_FINAL_ANSWER_TEMPLATE` lieferte für alle zwölf Sections denselben generischen Platzhaltertext, der keines der sechs Muster trifft. Damit stufte der Checker jeden Stub-Report bedingungslos `COMPLETED → INCOMPLETE` ab, und die E2E-Smokes (`minimal-report.spec.ts`, `report-modes.spec.ts`) liefen 300 s in den Timeout. Genau dieselbe Lücke hätte auch das Persona-Floor-Gate treffen können — dort wird der Stub aber bereits explizit bedient (`seedPersonaFloor`); das wurde bei #1302 für den neuen Checker vergessen.
- **Fix Teil A — Stub-Vertrag erweitert:** `_STUB_FINAL_ANSWER_TEMPLATE` enthält jetzt je einen Satz zu Stakeholder-Widersprüchen, Frühwarnindikatoren, Stop-/Expand-Kriterien, Positionswechsel und Koalitionen, zusätzlich zum bisherigen Disclaimer-Text („Keine echten LLM-Daten in diesem Lauf"). Bleibt vollständig deterministisch — kein I/O, kein Random. Vor der Änderung per Graph-Abfrage geprüft, ob Tests am Wortlaut des Templates hängen: keiner tut es (`test_llm_e2e_stub.py` prüft nur Struktur/Schema-Validierung, nicht den Text), daher genügte eine Erweiterung des Basistexts statt section-spezifischer Varianten.
- **Fix Teil B — Poller erkennt terminale Nicht-Erfolgsstatus:** `pollReportReady` (`frontend/tests/e2e/helpers/report.ts`) akzeptierte ausschließlich `"completed"` und lief bei jedem anderen Endzustand in den vollen 300-s-Timeout. `"incomplete"` ist seit #1277-2 ein bewusster, vom gesamten System (Backend `report_status.py`, Zod-Contract, `useReportGeneration.ts`, `Step4Report.vue`) getragener dritter Endzustand — nur der Playwright-Helper kannte ihn nicht. Der Poller wirft jetzt sofort bei `"incomplete"` oder `"failed"` mit einer Meldung, die Status, `error` und (falls vorhanden) `run_degradations`/`missing_sections` nennt. Das macht den Test **strenger, nicht toleranter**: `"incomplete"` gilt weiterhin nicht als Erfolg, der Test schlägt nur schneller und mit Begründung fehl statt nach 5 Minuten mit einem bloßen Timeout.
- **Bewusst nicht gemacht:** `REPORT_REQUIREMENT_CHECKER_ENABLED=false` im E2E-Kontext — das wäre der schnellste Fix gewesen, hätte aber die einzige CI-Absicherung gegen eine #1302-Regression geopfert. Ebenso unangetastet: die Abstufungslogik in `run_degradation.py`/`requirement_checker.py` und `severity="blocking"` — beide sind korrekt, das Problem lag ausschließlich im Stub-Vertrag und im Test-Helper.

### Fixed (Single-Source-Deckel differenziert ab starkem Match — 2026-08-24)

- **Der 0.59-Deckel für Ein-Quellen-Claims war ein Attraktor, kein Grenzfall-Schutz:** `_compute_confidence_with_penalties` kappte jeden Claim mit nur einer `(type, source)`-Quelle bedingungslos auf `0.59`/`low`, unabhängig davon, wie gut der `match_score` war. Ein SUPPORTED-Fakt mit `match_score=0.946` erreichte einen Rohscore von 0.82–0.92, wurde aber trotzdem auf `0.59` gezogen. Im AURORA-Referenzlauf landeten dadurch 27 von 28 verbliebenen Claims exakt bei `0.59` — die gesamte Qualitätsdifferenzierung bei Ein-Quellen-Claims ging verloren. (#1301)
- **Der Deckel greift jetzt nur noch bei schwachem Match:** Ist `has_strong_match` (mind. ein `match_score >= 0.85` — dieselbe Schwelle, die die Verified-Schranke bereits verwendet) gesetzt, bleibt der 0.59-Deckel aus; der Rohscore zählt wieder. `backend/app/services/confidence_calculator.py:257` (`unique_sources < 2 and not has_strong_match`). Kein neuer Schwellwert — die 0.85-Grenze existierte bereits als `has_strong_match` und als oberste `specificity`-Stufe.
- **Die Verified-Schranke bleibt unangetastet:** `score >= 0.90` erfordert weiterhin `has_strong_match` UND `unique_sources >= 2` (`confidence_calculator.py:271-273`). Ein Ein-Quellen-Claim erreicht dadurch höchstens `0.89`/`high`, nie `verified` — auch nicht bei `match_score == 1.0`.
- **Regressionstest `test_repeated_high_scores_from_one_source_cap_at_low`** (5 Items, `match_score=0.78`, unter der 0.85-Schwelle) bleibt unverändert grün — der Deckel greift dort weiterhin exakt wie vorher.
- **Ein bestehender Test (`test_duplicate_bindings_do_not_raise_single_source_confidence`) prüfte den alten Deckelwert direkt am Rohscore** (`match_score=0.95` → vorher `<= 0.59`). Die eigentliche Dedup-Invariante — zwei Bindings derselben Evidence-ID ergeben keine zweite Quelle — bleibt bestehen, zeigt sich aber jetzt am finalisierten Label (`auto_downgrade_unsupported_high_claims` stuft `high` mangels Cross-Stakeholder-Beleg weiterhin auf `low` zurück), nicht mehr zufällig am Rohscore. Assertion auf `<= 0.89` und `label != "verified"` angepasst.

**Nicht Teil dieser Änderung (Slice 2, eigenes Issue):** Claim-Typ-Klassifikation (`empirical`/`analytical`/`recommendation`/`structural`). `evidence_entailment.py` (Issue #1317) wurde nicht angefasst.

### Fixed (Interviewzitate verankert — keine seed_doc-Referenzen mehr — 2026-08-14)

- Evidence mit `source_kind=agent_quote` (Interview-Aussagen) darf keinen `seed_doc:`-Anker tragen: neuer Contract-Validator `agent_quote_rejects_seed_doc_anchor` auf `EvidenceItemModel` und `EvidenceRecordModel` lehnt die Kombination ab — ein `seed_doc:`-Anker auf einer Persona-Aussage behauptet eine Dokumentstelle, die der Lauf nie produzierte (Referenzlauf: `seed_doc:seed_aurora#chunk:0`). Die Producer-Boundary `register_evidence_record` entfernt fabrizierte Anker, statt den ganzen Interview-Record zu verlieren; der Schreibpfad für echte Dokumentfakten (`seed_corpus`) bleibt unberührt. Der Section-Prompt beschränkt die `seed_doc:`-Form des `seed_anchor` ausdrücklich auf Zitate, die tatsächlich aus einer Seed-Dokument-Passage stammen, und weist Interview-Aussagen der `ev_`-Evidence-ID zu (contracts-first; das Positivbeispiel zeigt eine formgültige `ev_`-ID statt Persona × seed_doc).
- Der `interview_agents`-Tool-Ergebnistext zeigt jetzt die vergebene `ev_`-Evidence-ID direkt unter jeder Interviewantwort (`register_evidence_record` vergibt die ID vor dem finalen Rendern) — ohne sie hätte das Modell keine Möglichkeit gehabt, den vom Prompt verlangten `ev_`-Anker zu kopieren statt zu erfinden.
- Bereits als `schema_version=3` persistierte Reports mit der alten Kombination `source_kind=agent_quote` + `seed_doc:`-Anker werden beim Laden über `normalize_persisted_evidence_map` migriert (`strip_seed_doc_anchor_from_agent_quote_records`), statt `GET /api/report/<id>/evidence` mit HTTP 422 abzuweisen bzw. die Evidence-Map aus JSON/ZIP/CSV-Export stumm auszulassen.

### Fixed (Reportstatus an Contract-Validität gekoppelt — 2026-08-14)

- Ein Report mit ungültigem `ReportV3`-Contract oder fehlgeschlagener Zitat-Validierung (`quote_validation_failed=True`) erreicht nicht mehr fälschlich den Status `completed` — er wird mindestens auf `incomplete` abgestuft, nie aufgewertet. Erfasst jetzt auch: einen frisch fehlgeschlagenen `ReportV3`-Build ohne persistiertes Artefakt (vorher unsichtbar, da `save_report()` den Fehler intern abfängt) sowie eine bereits vor einem Cancel erfolglos gebliebene Zitatprüfung im Teil-Report-Pfad.

### Fixed (insight_forge Key Facts jenseits von Position 10 fielen still aus dem Evidence-Index — 2026-08-14)

- **`_record_tool_evidence` kappte `InsightForgeResult.semantic_facts` bei `[:10]`, bevor überhaupt geprüft wurde, ob ein Fakt eine Dokument-Provenienz trägt:** `insight_forge_tool.py::insight_forge()` dedupliziert Fakten aus mehreren Sub-Queries (`limit=15` je Sub-Query) plus der Hauptquery (`limit=20`) über ein `seen_facts`-Set — realistische Läufe liefern dabei deutlich mehr als 10 Key Facts (der auslösende Fall: 38). Das Slicing in `backend/app/services/report_agent/agent.py` griff vor `build_seed_document_anchor`/`register_evidence_record`, sodass jeder Fakt ab Position 10 unwiederbringlich verworfen wurde — auch solche mit gültigem `document_id`/`chunk_id`-Bezug, die als `EvidenceRecord` mit `source_kind=seed_corpus` hätten persistieren müssen.
- **Der Fix entfernt das Slicing im `InsightForgeResult`-Zweig; alle anderen Zweige (`InterviewResult`, `PanoramaResult`, `SearchResult`) bleiben unverändert**, insbesondere der bewusste Interview-Cap bei 10 (`test_interview_cap_registers_at_most_ten`). Determinismus und Idempotenz waren bereits über `build_evidence_id`/`register_evidence_record` gegeben und sind unverändert.

### Fixed

- **Report-Agent:** `min_tool_calls` von 3 auf 1 gesenkt — der ReAct-Loop akzeptiert nun ein korrektes Final Answer nach bereits einem Tool-Call, statt unnötige Über-Recherche zu erzwingen.
- **E2E-Stub:** Stub-Threshold an `min_tool_calls=1` angepasst, sodass Smoke-Tests das reale Verhalten abbilden.
- **CONTEXT.md:** Falsche Behauptung über parallele Tool-Calls korrigiert (nur `tool_calls[0]` wird pro Iteration ausgeführt).

### Fixed

- Frontend-Zod-Spiegel verwarf Backend-Payloads mit `persona_role_family` (`.strict()`-Rejection) und kannte `seed_document` nicht im `EvidenceTypeSchema`-Enum.

### Changed (Die Modell-Presets im Dropdown sind jetzt übersetzbar — 2026-08-24)

- **`Config.LLM_MODEL_PRESETS` trug den Anzeigetext als fertigen deutschen String** ("Qwen 2.5 14B (lokal, GPU-arm)", "GPT-OSS 120B (Bedrock)"). `/api/simulation/available-models` reichte ihn durch, `useEnvForm.ts` rendert ihn mit `p.label || p.name` unverändert — der Text lief damit komplett am `vue-i18n`-Katalog vorbei. Wer die Oberfläche auf `en` stellte, bekam im Modell-Dropdown weiter Deutsch; eine Textkorrektur brauchte einen Backend-Deploy.
- **Der Vertrag liefert statt `label` jetzt `label_key`** — einen stabilen, sprachneutralen Schlüssel nach dem Schema `llm.preset.<kind>.<slug>` (z. B. `llm.preset.bedrock.gpt_oss_120b`). Der Anzeigetext liegt in `frontend/src/i18n/locales/{de,en}.json` unter `llm.preset.*`. Die Entscheidung fiel bewusst für Backend-Schlüssel statt für eine Label-Ableitung im Frontend: der Preset-Katalog ist Backend-Wissen (Regionsbindung, Chat-Verifikation der Bedrock-IDs), nur der Text ist es nicht.
- **Alle elf Presets ziehen mit, nicht nur die sechs Bedrock-Einträge aus [#1288](https://github.com/arn0ld87/agora/pull/1288).** Ein halb umgestellter Katalog wäre schlechter als gar keiner — der Nutzer sähe im selben Dropdown übersetzte und nicht übersetzte Zeilen.
- **`i18n/modelPresetLabel.ts` löst die Kette `label_key` → `label` → `name` auf**, mit optionalem `te()`-Guard. Die Struktur ist absichtlich die von `components/graph/edgeLabelI18n.ts` — dieselbe Klasse Problem, dieselbe Lösung, kein zweites Muster im Repo. `label` bleibt als Fallback-Feld im TypeScript-Typ, damit ein Frontend gegen ein älteres Backend nicht auf rohe Modellnamen zurückfällt.
- **Der `(Ollama)`-Zusatz für lokal installierte Modelle ist ebenfalls raus aus dem Code** und kommt als `step2.model.ollamaOption` mit `{model}`-Parameter aus den Locales. Er saß als String-Literal in derselben `computed`.
- **`ModelPreset` in `api/simulation.ts` deklarierte `id` und `provider` als Pflichtfelder**, obwohl der Endpunkt beide nie geliefert hat — dieselbe Vertragslüge wie das bereits entfernte `models`-Feld, nur von der Index-Signatur verdeckt. Der Typ spiegelt jetzt, was tatsächlich über die Leitung geht.
- **Drift-Wächter in beide Richtungen:** `backend/tests/api/test_model_preset_label_keys.py` prüft Schema, `kind`-Konsistenz, Eindeutigkeit, die Abwesenheit von `label` — und löst jeden `label_key` gegen **beide** Locale-Dateien auf. Ein neues Preset ohne Locale-Eintrag fällt damit im Test auf statt im UI. `locale-coverage.spec.ts` und `modelPresetLabel.spec.ts` decken die Frontend-Seite ab.

### Fixed (Amazon Bedrock — Preset-Modelle chat-verifiziert, 2026-08-13)

- **Bedrock-Modell-Presets waren unbenutzbar:** die mit #1282 eingeführten sechs Preset-IDs waren nie gegen einen Live-Endpunkt geprüft worden. Fünf davon (`anthropic.claude-sonnet-5`, `anthropic.claude-opus-4-8`, `openai.gpt-5.6-sol/terra/luna`) existieren im mantle-Katalog der Default-Region `eu-central-1` gar nicht — jeder Chat-Call endete in `404 The model '<id>' does not exist`. Auth, Base-URL-Kanonisierung, Adapter-Routing und `/v1/models`-Discovery waren dabei die ganze Zeit korrekt. `LLM_MODEL_PRESETS` und die `fallback_models` des Connection-Eintrags führen jetzt sechs Modelle, die in `eu-central-1` mit einem echten `POST /v1/chat/completions` verifiziert sind: `openai.gpt-oss-120b`, `qwen.qwen3-235b-a22b-2507`, `minimax.minimax-m2.5`, `mistral.devstral-2-123b`, `nvidia.nemotron-super-3-120b`, `zai.glm-4.7-flash`. (#1282)
- **Claude und GPT-5.x sind über diesen Pfad grundsätzlich nicht erreichbar:** der mantle-Endpunkt führt die `anthropic.*`-Familie zwar im Katalog (in `us-east-1`, nicht in `eu-central-1`), bedient sie aber weder über `/v1/chat/completions` noch über `/v1/responses` — beide antworten `400 does not support the API`. Gleiches gilt für alle `openai.gpt-5.x`. In `us-east-1` sprechen 38 von 55 Katalog-Modellen Chat-Completions. Diese Modelle brauchen die native Converse/InvokeModel-API mit SigV4, die #1282 bewusst ausgeschlossen hat; Folge-Issue angelegt. Die Provider-Dokumentation im Code hält den Befund samt Messdatum fest. (#1282)
- **Regressionstest `tests/llm/test_bedrock_model_catalog.py`:** hält `LLM_MODEL_PRESETS` und `fallback_models` deckungsgleich (offline) und probt jedes Preset mit einem echten Chat-Call gegen die Default-Region (`@pytest.mark.llm`, Skip ohne `AWS_BEARER_TOKEN_BEDROCK`). Der Netz-Seam ist notwendig, weil `GET /v1/models` kein Capability-Feld liefert — ein reiner Katalog-Abgleich hätte die zweite Fehlerschicht durchgelassen. (#1282)

### Added (Amazon Bedrock als LLM-Provider — 2026-08-12)

- **Amazon Bedrock (OpenAI-kompatibler mantle-Pfad) als LLM-Provider:** `detect_provider` erkennt `bedrock-mantle.<region>.api.aws` / `bedrock-runtime.<region>.amazonaws.com` und resolved sie zu `OpenAIAdapter`; `openai_compat_base_url` erzwingt das nötige `/v1`. Connection-Discovery-Eintrag (`adapter_kind="bedrock"`, `api_key_ref=AWS_BEARER_TOKEN_BEDROCK`, Bearer-Auth) plus `/v1/models`-Discovery-Protokoll; Default-Region `eu-central-1` (im Connection-UI frei editierbar). `LLM_MODEL_PRESETS` um sechs Bedrock-Modelle ergänzt (Claude Sonnet 5, Claude Opus 4.8, OpenAI GPT-5.6 Sol/Terra/Luna, gpt-oss-120b). Frontend-Zod-Provider-Kind-Enums gespiegelt. Auth via Bedrock-API-Key (Bearer), kein boto3/SigV4. (#1282)

### Fixed (Output-Contract — toter Zweig nach PR #929 — 2026-08-12)

- **Toter `required`-Schnittmengen-Zweig in `resolve_report_status` entfernt:** Beide Arme nach dem `COMPLETED`-Early-Return lieferten `INCOMPLETE`; `required` und die Schnittmenge `failed & required` wurden bei jedem Aufruf berechnet und verworfen. Die Invariante (jeder Aufrufer übergibt `required_section_indices=list(range(1, total+1))` → jede failed Section wird `INCOMPLETE`) macht die Prüfung überflüssig. Eingedampft auf `COMPLETED if not failed else INCOMPLETE`; `required_section_indices` bleibt als Parameter, damit Aufrufer nicht geändert werden müssen. Verhaltensneutral — bestehende Trust-Tests decken beide Pfade ab. (#1277-5)

### Fixed (Report-Agent — Quote-Fallback und Binding-Merge — 2026-08-12)

- **Quote-Fallback behält keine Plattform-Strukturmarker mehr:** Bei leeren `key_quotes` fiel `quote_source` in `_record_tool_evidence` auf das rohe `response` zurück, sodass Marker wie `[Twitter Platform Response]` im persistierten `quote` landeten und in die Report-Prosa gerendert wurden. Der Fallback nutzt jetzt das bereits bereinigte `substance`. (#1277-4)
- **`_remap_claim_bindings` verwirft bei ID-Kollision nicht mehr die stärkere Bindung:** `merged.setdefault(target, binding)` war First-Wins — kam die schwächere `RELATED_ONLY`/`supports_claim=False`-Bindung zuerst, wurde die stärkere `SUPPORTED`-Bindung still verworfen; in `_finalize_section_claims` blieb `supporting_ids` leer und der Claim wanderte mit `no_supporting_evidence` in die Hypothesen. Die stärkere Bindung gewinnt jetzt nach Entailment-Rang (Tie-Break über `match_score`), unabhängig von der Reihenfolge. (#1277-6)
- **`demote_unanchored_seed_corpus_records` nutzt dieselbe strongest-binding-Policy:** Die Migrations-Pfad (`evidence_migrations.py`) enthielt eine zweite `setdefault`-Stelle mit derselben First-Wins-Bug-Klasse — beim Re-Key von Seed-Records konnte eine schwächere Bindung eine stärkere verdrängen. Die Policy wird dort jetzt konsistent angewendet; die Helper sind lokal gespiegelt (Konsolidierung in ein gemeinsames Modul steht aus). (#1277-6)

### Fixed (Confidence-Calculator — Audit-Trail und tote Zweige — 2026-08-12)

- **`compute_claim_confidence`-Audit-Trail beschreibt dieselbe Penalty-Menge wie der Score:** Bisher extrahierte die Funktion Sentiment-Scores über die gesamte Evidence-Menge (inkl. widersprechender und nur verwandter Items), während der Score in `compute_confidence` nur über die stützende Teilmenge lief — der Audit-Trail konnte Penalties aufführen, die der Score gar nicht abbildete, und umgekehrt fehlte die Entailment-Penalty im Audit. Beide Wrapper leiten jetzt aus der gemeinsamen Helper-Funktion `_compute_confidence_with_penalties` ab, sodass Score und Audit-Trail dieselbe Penalty-Menge tragen. (#1277-7(2), #1277-7(3))
- **Boolesche `sentiment_score`-Werte werden nicht mehr als numerische Sentiments interpretiert:** `bool` erbt von `int`, sodass `isinstance(True, (int, float))` True war und boolesche Sentinel-Werte als `1.0`/`0.0` durch die Extraktion rutschten — im schlimmsten Fall löste das einen Schein-Widerspruch und damit eine fälschliche Contradiction-Penalty aus. Boolesche Werte werden jetzt ausgeschlossen. (#1277-7(4))
- **Toter `base_score`-Parameter aus `compute_claim_confidence` entfernt:** Der Parameter wurde nie ausgewertet und führte Aufrufer in die Irre. (#1277-7(1))
- **Toter `elif`-Zweig in `apply_echo_cap` entfernt:** Der Zweig war unreachable: das vorherige `if` fängt alle `high`/`verified`-Labels ab, und für alle anderen Labels ist sein zweites Prädikat immer False. (#1277-3)

### Fixed (Report-Trust-Pfad — Laufzeit-Bugs — 2026-08-12)

- **Native Tool-Call-Modus retryt bei `content: None` statt dauerhaft zu scheitern:** Im nativen Pfad konnte `chat_with_tools` `{"content": None, "tool_calls": []}` liefern (erschöpftes `max_tokens`, Safety-Filter, leere Completion). Der Folgecode warf einen `TypeError`, den `_safe_generate_section_react` abfing — der vorgesehene None-Retry war auf diesem Pfad unerreichbar, die Section wurde dauerhaft `generation_failed` und der Report `INCOMPLETE`, obwohl ein einzelner Retry gereicht hätte. None wird jetzt frühzeitig im else-Zweig abgefangen, sodass der bestehende Retry-Pfad greift. (#1277-1)
- **`generate_report` meldet terminal `incomplete` statt `completed`, wenn der Report `INCOMPLETE` ist:** Der terminale Progress-Event am Happy Path sendete unterschiedslos `stage="completed"` bei 100 %, auch wenn `resolve_report_status`/`apply_degradation_downgrade` den Report auf `INCOMPLETE` gesetzt hatten. Consumern (WebSocket, Polling, Streaming-UI) wurde so Erfolg für einen unvollständigen Report vorgaukelt — genau die Fehldarstellung, die #1006 / P0-7 beseitigen sollte. Stage und Message verzweigen jetzt auf `report.status`. (#1277-2)
- **`/api/report/generate/status` propagiert den INCOMPLETE-Report-Status:** Der Progress-Event-Fix schrieb `stage="incomplete"` in `progress.json`, aber der Polling-Pfad (`ReportStatusService.get_status`) las den Status aus der Run-Registry — und `run_generate` schreibt den Registry-Status auch bei INCOMPLETE auf `"completed"` (Teilergebnis, kein Fehlschlag, #1006). `get_status` spiegelt jetzt den Report-Status in das `status`-Feld des Public-Contract, wenn der Run terminal ist; `useReportGeneration` nimmt damit den `incomplete`-Branch statt den completed-Branch für einen unvollständigen Report. (#1277-2)

### Fixed

- Replay-Overrides verwenden den kanonischen `AiModelRef` statt eines offenen
  Dictionaries. Die `provider_connection_id` wird jetzt an das Stage-Routing
  durchgereicht — dieselbe Modell-ID auf zwei Provider-Connections landete
  vorher auf der falschen Connection.
- Validierungsfehler beim Replay liefern einen strukturierten Fehler-Envelope
  mit `code` und sanitisierten Details, statt das rohe
  `ValidationError.errors()`-Payload als Fehlertext zu setzen.
- Run-Manifeste werden atomar geschrieben (tmp-Datei + `os.replace`). Ein
  fehlgeschlagener Schreibvorgang lässt das vorhandene Manifest unverändert;
  parallele Leser sehen kein halbfertiges JSON.
- `runtime.usage_summary` wird beim Finalisieren aus `usage_summary.json`
  übernommen und blieb bisher in jedem Simulations-Manifest leer.
- `RunManifest` mit `status="final"` verlangt jetzt Laufzeitdaten. `draft` und
  `legacy` bleiben ohne `runtime` gültig.
- Der Replay-Dialog bietet keine Eingabefelder mehr für Seed-Dokument und
  Zufalls-Seed an — beide werden serverseitig mit HTTP 400 abgelehnt. Ein halb
  ausgefülltes Modell-Override sperrt den Submit, statt still auf das
  Originalmodell zurückzufallen.
- Der Fehlerpfad des Replay-Dialogs verwendet einen i18n-Key statt eines
  hartkodierten deutschen Texts.

### Fixed (Simulationsvorbereitung und Gemini-Tool-Turns - 2026-08-12)

- **Prepare läuft pro Simulation exklusiv:** Ein zweiter Start bei aktivem Prepare-Task wird vor Run-, Task- und Artefakterzeugung mit HTTP 409 abgelehnt; verwaiste `preparing`-Zustände bleiben recoverbar.
- **Gemini-3-Tool-Historie behält Thought-Signaturen:** Der CAMEL-Adapter übernimmt die Provider-Signatur pro Tool-Call in nachfolgende Assistant-Nachrichten und nutzt den dokumentierten Validator-Ersatz nur für synthetisch rekonstruierte Calls.

### Fixed (406+ deutsche Zitate schlossen mit ASCII-Quote statt „…“ — 2026-08-24)

- **Repo-weite Korrektur des Zitat-Schlusszeichens:** 515 Stellen in `backend/app/`, `backend/tests/`, `backend/scripts/`, `frontend/src/`, `docs/` und `changelog.d/` öffneten ein deutsches Zitat mit `„` und schlossen es mit dem ASCII-`"` statt mit `“`. Getrennte Commits pro Bereich, reiner Zeichenersatz ohne inhaltliche Änderung. Zwei Treffer in `report_agent/text_verification.py` sind bewusst ausgenommen — dort ist der ASCII-Quote das Delimiter-Zeichen einer `str.strip()`-Zeichenklasse, kein Zitat. Schema-Drift aus den betroffenen Contract-Docstrings (Pydantic `Field`-Description) wurde mitgerendert. (#1269)

### Fixed (Section-Prompt beschreibt die Anker-Prüfung wieder korrekt — 2026-08-11)

- **Der Section-Prompt sagte dem Modell eine Freikarte zu, die es seit #1249 nicht mehr gibt:** Die Zeile `The "seed_doc:" prefix is accepted as an opaque reference without further lookup` beschrieb ein Verhalten, das `validate_quote_anchors` nach der #1249-Umsetzung nicht mehr zeigt — dort wird jeder Anker präfixunabhängig gegen `known_anchors` geprüft. Die Folge war nicht kosmetisch: ein nicht auflösbarer Anker setzt `QuoteValidationResult.valid` auf `False`, und `section_pipeline._validate_quotes_with_repair` löst daraufhin einen vollständigen zweiten ReAct-Durchlauf für die Section aus. Der lief mit demselben irreführenden Prompt und konnte strukturell nicht erfolgreich sein — ein verschwendeter Section-Call pro betroffenem Abschnitt, am Ende `quote_validation_failed=True`. Betroffen war jeder Abschnitt, dessen Titel `_section_expects_quotes` erfüllt (Persona, Segment, Reibung, Vertrauen, Interview, Reaktion), außerhalb des `explorative`-Modus.
- **Das vorgegebene Ankerformat war zusätzlich strukturell unauflösbar.** Der Prompt verlangte `seed_doc:<document_id>`, der Lesepfad (`_SEED_DOC_ANCHOR_RE`, ADR-0013) akzeptiert aber ausschließlich `seed_doc:<document_id>#chunk:<chunk_id>` — und nur solche Anker erzeugt `build_seed_document_anchor`, nur sie landen als `source_id_anchor` in `known_anchors`. Ein Modell, das dem Prompt exakt folgte, produzierte damit garantiert einen ungebundenen Anker. Ohne diese zweite Korrektur wäre die Aufforderung, einen auflösbaren Anker zu setzen, eine Anweisung gewesen, die das Modell nicht befolgen kann.
- **Das Beispiel `ev_kg_042` verletzte `EVIDENCE_ID_PATTERN`** (`^ev_[0-9a-f]{32}$`) — dieselbe Fehlerklasse wie der kopierbare Beispielwert aus #1244, nur im anderen Namensraum. Die Beispiele nutzen jetzt durchgängig die Platzhalterform, kein nachahmbares Literal.
- **Der Prompt benennt jetzt die tatsächliche Konsequenz:** jeder Anker wird geprüft, ein nicht auflösbarer wird als ungebundene Referenz ausgewiesen und kostet die Section einen Reparaturlauf. Erfundene Anker erzeugen keine Evidence.
- **Platzhalter in spitzen Klammern zerlegten den eigenen Section-Parser.** `_QUOTE_TAG_RE` liest die Attributliste mit `[^>]+` und endet damit am ersten `>`. Ein Beispiel-Tag wie `<simulated_quote persona_id="<persona_id>" seed_anchor="<evidence_id_or_seed_doc>">` schneidet sich selbst ab: `seed_anchor` bleibt unterminiert, fällt aus `_ATTR_RE` heraus und das Zitat gilt als ankerlos — der Attributrest landet zusätzlich im Zitattext. Der Prompt ist das Vorbild, dem das Modell folgt, also war das ein Defekt im Prompt, nicht im Parser. Alle Beispiel-Tags verwenden jetzt klammerfreie Großschreibungs-Platzhalter (`PERSONA_ID`, `DOCUMENT_ID`, `CHUNK_INDEX`), und der Prompt benennt die Regel ausdrücklich. Zwei der vier betroffenen Stellen bestanden schon vorher (Format-Vorgabe und Quote-Reminder), zwei wären mit dem #1267-Fix neu hinzugekommen — der Regressionstest deckt beide Fälle über denselben Produktions-Parser ab.
- Validator und Gating bleiben unverändert — der Validator war richtig, der Prompt war falsch. Der `<evidence_gating priority="hard">`-Block (ADR-0002 Hartanker 1) und der Hedge-Snapshot (Hartanker 2) sind nicht berührt; der Diff beginnt hinter dem Block.

### Slice 1.2 — Report-Generierung serialisiert statt parallel

Eine zweite parallele Report-Generierung für dieselbe Simulation wird
deterministisch mit HTTP `409 report_generate_in_progress` abgewiesen, statt
kooperativ gebremst zu werden. Der neue Guard
`ReportGenerationService._reject_if_report_generate_active` fragt vor jedem
Start die RunRegistry nach einem Run mit `run_type=report_generate` und
Status `pending` oder `processing` für dieselbe `simulation_id` ab — bewusst
kein In-Memory-Dict, weil das einen Worker-Neustart nicht überleben würde und
den zweiten Start dann wieder durchließe.

Das ist eine bewusste Verhaltensänderung und für Nutzer, die bisher parallel
generiert haben, eine Laufzeit-Regression: der zweite Aufruf schlägt jetzt
fehl statt (unkontrolliert) mitzulaufen. Begründung ist der in #1265
belegte Faktor ~6 an Ressourcenverbrauch — Tokens, LLM-Calls, Laufzeit —, den
zwei parallele Generierungen für dieselbe Simulation ohne Mehrwert
verursachen.

Out-of-Process-Jobausführung bleibt 1.0-Vorarbeit und ist mit diesem Slice
nicht erledigt; der Guard serialisiert nur den Start, er ändert nichts an der
grundsätzlichen In-Process-Ausführung der Jobs selbst.

### Changed (Runtime-Context verifiziert — 2026-08-11)

- **`CONTEXT.md` beschreibt wieder den tatsächlichen Runtime-Stand:** Prepare-/Persona-Pipeline, Initial-Post-Publishing, Interview-Mechanik, Evidence-Binding und bekannte Signaturen sind gegen `main@a3cebd38f38fc2c0043dc245766869eb05b41e0f` abgeglichen; bekannte Beobachtungen tragen jetzt explizite Status statt pauschal als „nicht neu melden“ zu gelten. (#1261)

### Fixed (`seed_doc:`-Anker werden gebunden statt geglaubt — 2026-08-11)

- **Ein Provenance-Anker mit `seed_doc:`-Präfix umging die Bindungsprüfung vollständig:** Die Validierung prüfte einen Anker nur dann gegen die bekannten Anker, wenn er dieses Präfix *nicht* trug — es galt als opake Referenz. Ein `ev_`-Anker ohne Bindung wurde als `unbound_evidence_refs` sichtbar, `seed_doc:beliebig` niemals. Das Modell wählte in den beobachteten Läufen exakt diesen einen ungeprüften Pfad, und zwar mit dem Wert, den der Prompt ihm vorgab: Alle acht Zitate einer Section, von sieben verschiedenen Personas, trugen `seed_doc:interview_transcript_07`; ein Dokument dieses Namens existierte im Lauf nicht. Über mehrere Läufe zeigte sich eine Verschärfung nach oben — ein stärkeres Modell konstruierte statt eines konstanten Ankers pro Persona einen individuell klingenden (`seed_doc:interview_<name>`), der ebenfalls auf nichts verweist. Der konstante Anker ist als wertlos sofort erkennbar, der individuelle nicht: Dann sieht jedes Zitat einzeln belegt aus.
- **Eine eigene Auflösungsquelle war dafür nicht nötig:** Echte Seed-Anker haben nach ADR-0013 die Form `seed_doc:<document_id>#chunk:<chunk_id>` und stehen als `source_id_anchor` bereits im Ankerindex. Es fehlte nur die Prüfung; der Kern der Änderung ist eine gelöschte Bedingung.
- **Gewählte Politik (Sign-off 2026-08-11):** Ein nicht auflösbarer `seed_doc:`-Anker wird geführt wie ein ungebundener `ev_`-Anker — sichtbar als `unbound_evidence_refs`, ohne das Zitat hart zu verwerfen. Ein real existierendes, aber aus technischen Gründen nicht indiziertes Dokument kostet damit Sichtbarkeit, keinen Inhalt. Die Behandlung von `ev_`-Ankern ist unverändert, ein *fehlender* Anker bleibt weiterhin ein hartes `invalid_quote`, und der `<evidence_gating priority="hard">`-Block sowie der Hedge-Snapshot sind unberührt.

### Changed (Der Cross-Stakeholder-Anker zählt Rollenfamilien statt Berufstitel — 2026-08-11)

- **Zwei Formulierungen desselben Berufs galten als zwei Stakeholder-Gruppen:** `persona_stakeholder_group` wird aus dem Berufstitel der Persona gefüllt und ist damit ein frei formulierter Satz. Der Validator zählte distinkte Werte nach einer Normalisierung, die nur Groß-/Kleinschreibung und Whitespace einebnet. In den Evidence-Karten zweier Referenzläufe standen deshalb `Umschüler im IT-Bereich (Teilnehmer)` und `Teilnehmer einer IT-Umschulung (Retrainee)` als verschiedene Gruppen nebeneinander, ebenso `Umschüler & Sprecher der Teilnehmenden`, `Umschüler zur Fachkraft für Lagerlogistik`, `Umschüler:in (Logistik & Lagerwesen)` und `Umschülerin zur Kauffrau für E-Commerce` — vier Gruppen, eine Rolle. In einem weiteren Lauf genügte ein Genusunterschied: `Festangestellte Dozentin für IT-Umschulungen und Betriebsratsmitglied` gegen `Festangestellter Fachdozent für IT-Umschulungen und Betriebsratsmitglied`. Der Anker verlangt zwei distinkte Gruppen für `high`; es genügte also eine andere Formulierung desselben Berufs, um eine Aussage als breit gestützt einzustufen, obwohl nur eine Perspektive gesprochen hat.
- **Gezählt wird jetzt ein kontrolliertes Rollenfamilien-Label:** Das neue Feld `persona_role_family` trägt den Entitätstyp der Quellentität — pro Lauf stabil, im Gegensatz zum Freitext. Der Berufstitel bleibt als Anzeigetext vollständig erhalten; er trägt Information, die der Report nutzt. Der Konsenswert in der Confidence-Berechnung folgt derselben Zählgröße, damit er keine andere Vorstellung von „Gruppe“ hat als der Validator, der über dasselbe Label entscheidet.
- **Kollektiv und Individuum derselben Organisation sind eine Familie:** Beide tragen den Entitätstyp ihrer Quellentität, die Zusammenführung fällt damit ohne eine zweite Identitätsquelle an. Ein Kollektiv-Zitat zählt nicht mehr als zusätzliche Stimme neben einem Individuum derselben Organisation.
- **Artefakte aus älteren Läufen bleiben lesbar:** Fehlt das Label, bleibt der Berufstitel die Vergleichsgröße — das bisherige Verhalten, nie strenger und nie lockerer. Die beiden Namensräume werden über ein Präfix getrennt, damit eine Familie `Lecturer` nicht mit einem gleichlautenden Freitext verschmilzt.
- **Verhältnis zu ADR-0002:** Das ist eine Verschärfung von Hartanker 4, keine Schwächung — die Zahl unterscheidbarer Gruppen kann durch das Label nur sinken. Der `<evidence_gating priority="hard">`-Block und der Hedge-Snapshot sind unverändert.

### Fixed (Nicht-Stakeholder werden keine Personas mehr, und abgelehnte Plätze bleiben nicht leer — 2026-08-11)

- **Die Blockliste konnte den Hauptfall strukturell nicht fangen:** Der Eignungsfilter prüft den Entitätstyp gegen eine harte Blockliste (`city`, `software`, `technology`, `date` …) und funktioniert dabei nachweislich. Gemessen über zwei Referenzläufe tragen aber **28 von 29 Nicht-Stakeholdern den Typ `Organization`** — `Moodle`, `ChatGPT`, `granite-4.0-h-tiny`, `GPU-Server`, `Magdeburg`, `AZAV-Zulassung`, `Kursstart Februar 2027`, `Abschnitt 7 (U1–U5)`. `organization` kann nicht auf die Blockliste, weil Bildungsträger, Betriebe und Behörden legitime Stakeholder-Organisationen sind. Ein enger gefasstes Typvokabular hilft ebenfalls nicht: In einem Lauf lieferte das Modell ausschließlich kanonische Typen — und trotzdem landeten 16 von 16 Nicht-Stakeholdern in `Organization`. Der Typ ist gleichzeitig legitimes Label und Auffangtopf für alles Unklare. Die Frage „kann diese Entität einen menschlichen Träger haben“ wird deshalb jetzt am Namen und am Kontext beantwortet und in den ohnehin stattfindenden Persona-Generierungsaufruf gefaltet — sie kostet keinen zusätzlichen Roundtrip. Das Modell darf mit einer Ablehnung antworten, statt eine Persona erfinden zu müssen. Die Blockliste bleibt als billige erste Stufe erhalten.
- **Wirkung, bis in die Evidence belegt:** In den Reports der Referenzläufe traten `Technische Mitarbeiterin im Rechenzentrum Magdeburg`, `Projektkoordinatorin KI-Lernassistent` und `Teamleiterin AZAV-Zulassung bei der Agentur für Arbeit` (6 Zitate) als zitierte Quellen auf. Ein Slot, der leer bleibt, wäre hinnehmbar; ein Slot, der mitredet und zitiert wird, verfälscht das Ergebnis.
- **Abgelehnte Plätze werden nachbesetzt:** Die typunabhängige Prüfung fällt erst im Generierungsaufruf, also **nach** dem `max_agents`-Cap. Ohne Nachbesetzung unterschritte jede Ablehnung den konfigurierten Wert — bei einem Cap von 30, nach eigener Empfehlung der Floor ohne Puffer, und einer beobachteten Ablehnungsquote von bis zu 32 % wäre das der Unterschied zwischen 30 und 20 Stimmen. Was der Cap wegschneidet, bleibt jetzt als Reservepool erhalten; jeder abgelehnte Platz zieht daraus nach, und auch ein abgelehnter Nachrücker führt zum nächsten Kandidaten. Das Typ-Round-Robin aus #1177 bleibt unverändert und läuft weiterhin vor der Reservebildung, sodass jeder Typ seinen Platz behält.
- **Ablehnung und Ausfall bleiben unterscheidbar:** Eine Zurückweisung ist eine eigene Ausnahme, kein stiller `None`-Rückgabewert. Ein Generierungsfehler führt weiterhin zum Notprofil und belegt seinen Platz; nur eine Ablehnung gibt den Platz frei. Der regelbasierte Pfad lehnt nie ab — dort gibt es kein Modell, das die Frage beantworten könnte, und ein Ausfall darf nicht in einen Ausschluss umgedeutet werden.

### Fixed (Personas sind wieder kohärent sie selbst — 2026-08-11)

- **Anzeigename und Profiltext beschrieben verschiedene Menschen:** `username=katharina_schäfer_846` trug den Profiltext „Sabine Krüger …“, `felix_krause_452` den Text „Klaus Weber …“ — häufig mit abweichendem Geschlecht. Über vier Referenzläufe lag die Quote auf der maschinell messbaren Teilmenge bei 50, 81, 68 und 73 Prozent. Der Interview-Systemprompt setzt beides zusammen: „Du bist \<label\>“ und direkt darunter ein Profil, in dem jemand anders beschrieben wird. Die Persona bekam damit zwei Identitäten in derselben Nachricht — die plausibelste Erklärung für die beobachtete Rollenübernahme, bei der eine Rechenzentrums-Technikerin mit „Als Betriebsrat hätte ich vorab klären müssen…“ antwortete. Der Freitext wird jetzt deterministisch auf den Anzeigenamen gezogen, inklusive späterer Erwähnungen („Sabine schätzt…“, „Frau Krüger meldet…“). Bewusst kein weiterer Prompt-Appell: der Prompt enthielt bereits eine Rollentreue-Regel, das Modell verletzte also eine vorhandene Regel, keine fehlende.
- **Organisationen bekamen eine erfundene Vita:** Aus dem Bildungsträger `Nordharz Bildungswerk gGmbH` (`source_entity_type: Organization`) wurde `juergen_hartmann_nhb_832` mit `profession: "Dozent für IT-Umschulungen und Betriebsratsmitglied"`. Weder „Dozent“ noch „Betriebsratsmitglied“ ist aus einer gGmbH ableitbar. Die Ursache war strukturell: Der Gruppen-Prompt forderte ausdrücklich einen erfundenen Menschen mit Alter, Geschlecht, MBTI-Typ, Bildungsweg und „prägenden Erfahrungen“ an — eine Institution hat davon nichts, also musste der Generator alles erfinden. Gruppen-Entitäten werden jetzt als Kollektiv-Persona geführt: kein Alter, kein Geschlecht, kein Persönlichkeitstyp, keine Berufsbezeichnung, kein erfundener Personenname. Sie äußern sich als „der Träger“ statt als „Jürgen Hartmann, 57“. Das ist eine Darstellungs-, keine Architekturänderung — der Simulations-Agent bleibt ein Agent und führt weiterhin individuelle Aktionen aus. Das neue Feld `persona_kind` (`individual` | `collective`) steht in allen drei Serialisierungen, damit Konsumenten die Ausprägung lesen können, ohne den Entitätstyp nachzuschlagen.
- **Der Entitätstyp wurde als Beruf durchgereicht:** Wo der degradierte Pfad nichts abzuleiten wusste, schrieb er den Typnamen wörtlich ins Berufsfeld — `profession: "AIProvider"`, `"WorkingGroup"`, `"TechnologyVendor"`. Das Feld bleibt jetzt leer, und ein Wächter verwirft jede `profession`, die dem Entitätstyp entspricht, unabhängig davon, welcher Pfad sie erzeugt hat. Lieber keine Angabe als eine falsche.

### Fixed (Twitter verwirft keine Initial-Posts mehr, und das Log zeigt es an — 2026-08-11)

- **Der Twitter-Zweig überschrieb Seed-Posts desselben Agenten:** Die Publish-Schleife hielt die Initial-Posts in einem Dict mit dem Agent-**Objekt** als Schlüssel und wies per einfacher Zuweisung zu. Trugen mehrere Posts dieselbe `poster_agent_id`, gewann der letzte — alle vorherigen verschwanden ersatzlos, ohne Fehler und ohne Warnung. In einem Lauf, in dem alle neun Seed-Posts derselben `agent_id` zugewiesen waren, veröffentlichte Twitter genau einen (den letzten) und Reddit alle neun. Der Reddit-Zweig derselben Datei behandelte diese Kollision bereits korrekt; es war ein Copy-Paste-Divergenzfehler, kein Designunterschied. Beide Zweige benutzen jetzt denselben Helfer, damit die Vorlage nicht erneut auseinanderläuft. Der Fix ist bewusst unabhängig von der Poster-Zuordnung: auch nach deren Korrektur kann eine Entität legitim mehrfach als Sprecher auftreten, und dann verschwänden die Posts weiterhin still.
- **Die Publish-Meldung zählte Agenten und nannte sie Posts:** Die Zeile gab `len(initial_actions)` aus, also die Anzahl distinkter Poster-Agenten. Bei neun auf einen Agenten kollabierten Posts meldete sie `Published 1 initial posts`, bei neun verteilten `Published 9 initial posts` — dieselbe Formulierung für einen Faktor neun Unterschied. Sie war damit die ganze Zeit ein direkter Indikator für den Kollaps, nur als solcher nicht lesbar. Beide Größen stehen jetzt getrennt in der Zeile: `Published 9 initial posts from 1 distinct agent`.

### Fixed (Der Beispiel-Provenance-Anker im Section-Prompt geht nicht mehr als echter Wert durch — 2026-08-11)

- **Modelle kopierten den Beispielwert aus der Prompt-Anweisung in jedes Zitat:** Die Formatbeschreibung für den `seed_anchor` eines Persona-Zitats nannte ein Beispiel in der Form `"seed_doc:" gefolgt von der Dokument-ID (z. B. "seed_doc:interview_transcript_07")`. Dieser Beispielstring ist gleichzeitig ein syntaktisch gültiger Wert — ein Modell, das die Anweisung nicht auflösen kann, greift zur naheliegendsten gültigen Zeichenkette, und das ist das Beispiel. In einem beobachteten Lauf trugen alle acht Zitate von sieben verschiedenen Personas genau diesen Anker; ein Dokument dieses Namens existierte im Lauf nicht. Der Prompt nennt jetzt nur noch die Platzhalter-Syntax `seed_doc:<document_id>` und weist ausdrücklich darauf hin, dass sie zu ersetzen und nicht zu übernehmen ist. Die Formatbeschreibung selbst bleibt vollständig erhalten.
- **Nicht Teil dieser Änderung:** Dass ein `seed_doc:`-Anker die Bindungsprüfung ohne Auflösung passiert, bleibt unverändert bestehen — die Ablehnungspolitik dafür braucht eine eigene Entscheidung und liegt in #1249. Der `<evidence_gating priority="hard">`-Block und der Hedge-Snapshot sind byte-identisch (ADR-0002).

### Fixed (Der Report-Abbruch bricht jetzt tatsächlich ab — 2026-08-11)

- **`POST /api/runs/<id>/cancel` quittierte Erfolg und tat nichts:** Die Workflow-Funktion `generate_report` prüft das Abbruchsignal an zwei Stage-Grenzen völlig korrekt — nach der Outline und zu Beginn jeder Section-Iteration. Der zugehörige Parameter `cancel_run_id` ist aber keyword-only mit Default `None`, und die Prüffunktion steigt bei `None` sofort mit `False` aus. Kein einziger Produktivaufrufer übergab ihn: weder der Report-Generation-Service noch der Resume-Pfad in der Runs-API. Der Parameter kam außerhalb der Signatur nur in `tests/services/test_partial_report.py` vor, wo er explizit gesetzt wird — deshalb war der Test grün, während die Funktion produktiv nie eine `run_id` zu prüfen bekam. Praktische Folge im Feld: Ein laufender Report ließ sich nur per `docker restart` beenden, was alle anderen Jobs im selben Container mitnahm. Beide Aufrufer reichen die `run_id` jetzt durch, und die Agent-Fassade `ReportAgent.generate_report` leitet sie an die Workflow-Ebene weiter, statt sie zu schlucken.
- **Ein abgebrochener Lauf ist nicht mehr von einem vollständigen zu unterscheiden gewesen:** Der Teilreport aus dem kooperativen Abbruch trägt bewusst `status=COMPLETED` (success-with-caveat), weil die bereits geschriebenen Sections lesbar und exportierbar bleiben. Der Run übernahm diesen Status ungeprüft und stand anschließend als regulär abgeschlossen in der Liste. Nach einem Nutzerabbruch endet er jetzt als `stopped` mit `termination_reason="user_cancel"` — dasselbe Endzustandspaar, das der Simulations-Monitor bei einem abgebrochenen OASIS-Subprozess setzt. Die Reihenfolge ist dabei bindend und aus #978 bekannt: `complete_task` spiegelt sich per `RunRegistry.sync_task` auf den Run zurück, der detaillierte Run-Update muss deshalb zuletzt laufen.

### Documentation (CONTEXT.md beschreibt die Laufzeit-Mechanik für Agenten — 2026-08-11)

- **Wer einen Agora-Lauf beobachtet oder auswertet, musste sich die Mechanik bisher aus Code, Logs und Artefakten zusammensuchen:** `README.md` beschreibt das Produkt, `AGENTS.md` die Arbeitsregeln — wie ein Lauf tatsächlich abläuft, stand nirgends. Das kostete wiederholt Zeit an Symptomen, die sich als korrektes Verhalten herausstellten: Reposts sind eigene `post`-Zeilen mit leerem `content`, Twitter kennt keine Kommentare, die Neo4j-Schreibfehler beim Simulationsstart sind ein dokumentierter Fork-Transient, und der Zähler in `Published N initial posts` zählt distinkte Poster-Agenten statt Posts.

  `CONTEXT.md` füllt den in [`docs/agents/domain.md`](docs/agents/domain.md) vorgesehenen, bislang bewusst leeren Slot. Sie beschreibt die fünf Phasen mit ihren Artefakt-IDs, den `interview_agents`-Mechanismus samt seiner drei Eigenheiten (Frage-Echo, Rollenübernahme, und dass ein Zitat im Report meist aus dem Interview stammt und nicht im Feed steht), das Evidence-Modell mit seinen **zwei getrennten Prüfstellen** — `claim_extraction_and_evidence_binding` prüft alle Claims, `verify_prose` nur Sätze mit einer Zahl —, die Artefaktpfade im Container, das Sim-DB-Schema mit der `original_post_id`-Auswertungsfalle, das getrennte Embedding-Routing zwischen Env und Konfigurationsstore, die Standardgriffe zur Auswertung eines Laufs, und eine Liste bekannter Fehlerbilder, die ausdrücklich **nicht** als Neufund zu melden sind.

  `AGENTS.md` und `CLAUDE.md` verweisen darauf, damit Agent-Runtimes die Datei ohne Suche finden.

### Fixed (Vision-Pfad behandelt MiniMax-thinking — 2026-08-23)

- **`LLMClient.describe_image` schickte gegen MiniMax kein `thinking`-Feld.** Der extra_body wurde nur für Ollama gebaut (`think=False` — „never want reasoning noise in vision output“); der MiniMax-Zweig war auf dem Vision-Pfad bewusst ausgeklammert (#1225) und blieb damit ohne Behandlung. Gegen MiniMax-M3 ist das die falsche Voreinstellung: fehlt das Feld, ist Thinking laut API-Spec standardmäßig **an**.
- **MiniMax-M3 ist vision-fähig** und nimmt über den OpenAI-kompatiblen Pfad `image_url`-Content-Parts entgegen — genau die Message-Shape, die `describe_image` baut. Ein Vision-Call gegen `api.minimax.io` lief also mit Reasoning-Rauschen im Bild-Beschreibungstext, den der Pfad nachträglich per `<think>`-Regex abwäscht, statt es am Request zu verhindern.
- **Der Vision-Pfad reicht jetzt denselben Schalter durch wie `chat` und `tool_calls`:** `minimax=self._is_minimax()` ergibt zusammen mit `think=False` den extra_body `{"thinking": {"type": "disabled"}}`. Bei M3 wirksam; M2.x akzeptiert das Feld ohne Verhaltensänderung (dort lässt sich Thinking nicht abschalten). Ollama- und OpenAI-Pfad bleiben unverändert.
- **Abgesichert durch drei Regressionstests** (`tests/llm/test_vision_minimax_thinking.py`): MiniMax-Vision-Request trägt `{"thinking": {"type": "disabled"}}`, OpenAI bleibt ohne `extra_body`, und der Ollama-Zweig behält `think: False`.

### Fixed (Der Tools-Pfad wendet den Temperature-Quirk an — 2026-08-23)

- **Natives Tool-Calling gegen GPT-5-/o-Reasoning-Modelle lief garantiert in einen 400:** `tool_calls._chat_with_tools` setzte `temperature` bedingungslos in den Request. Der Quirk aus #1096 — die GPT-5-/o1/o3/o4-Familie akzeptiert ausschließlich den Default-Wert (1) und antwortet sonst 400 `unsupported_value` mit `param=temperature` — war auf diesem Pfad nie nachgezogen worden, obwohl `chat()` und `describe_image()` ihn beim Requestbau anwenden. Der Pfad trug die Abweichung seit #1225 als sichtbarer Seam (`_never_omits_temperature` / `_TOOLS_REQUEST_OPTIONS`). Der Tools-Pfad verwendet jetzt dasselbe `DEFAULT_REQUEST_OPTIONS`-Shaping wie die übrigen Pfade: gegen ein Quirk-Modell landet `temperature` gar nicht erst im Request.
- **Der Tools-Pfad hat jetzt auch das Retry-Netz (Parität mit `chat()`):** Zusätzlich zum Shaping steht der `TEMPERATURE_QUIRK` in der execute-Quirkliste neben dem bestehenden Token-Key-Quirk. Die `omits_temperature`-Heuristik erkennt bekannte Familien per Prefix; ein unbekanntes Reasoning-Modell oder ein Proxy, der einen solchen 400 durchreicht, bekam bisher keinen zweiten Versuch. Das Netz greift genau einmal und nur bei einem erkennbaren temperature-400; alle anderen Fehler propagieren unverändert.

### Fixed (Seed-Posts treffen wieder ihren Sprecher — 2026-08-11)

- **Alle Eröffnungsbeiträge eines Laufs konnten auf einem einzigen Agenten landen:** Die Zuordnung der Initial-Posts baute ihren Agenten-Index ausschließlich über `entity_type.lower()` — die Schlüssel waren also Typen wie `chamberofcommerce` oder `lecturer`. Verglichen wurde dagegen der `poster_type` aus der LLM-Event-Config, und welchen Namensraum dieser Wert trägt, entscheidet das Modell pro Lauf neu: mal Entity-Typen, mal Entity-**Namen** (`betriebsrat`, `kostenträger`, `geschäftsführung`). Im Namensfall sind beide Namensräume disjunkt und der Direktabgleich kann strukturell nie greifen. Beobachtet in einem Lauf über eine deutsche Umschulungsdomäne: 9 von 9 Seed-Posts auf demselben Agenten, der IHK. Der Eröffnungsbeitrag des Betriebsrats, der des Kostenträgers und der der Teilnehmenden mit Migrationsgeschichte wurden alle von der Prüfungskammer gepostet — und landeten unverändert so in der Simulationsdatenbank, auf der jede Folgerunde und später die Evidence-Bindung des Reports aufbaut. Ein zusätzlicher Index auf `entity_name` löst diesen Lauf mit 9 von 9 korrekt auf und deckt beide Ausgabeformen des Modells ab, unabhängig vom NER-Vokabular.
- **Der Fallback verteilte nicht, er kollabierte:** Blieb ein `poster_type` unauflösbar, wurde immer derselbe Agent gewählt — der Rotationszähler, den der Direktabgleich führt, wurde dort nicht mitgeführt. Ein einziger Miss legte damit sämtliche Seed-Posts auf eine Stimme. Der Fallback verteilt jetzt reihum.
- **Bei Gleichstand im `influence_weight` entschied die Generierungsreihenfolge:** In demselben Lauf lagen `IHK`, `IHK-Prüfungsausschuss` und `Träger` alle bei `3.0`. Wer davon „der Agent mit dem höchsten Einfluss“ ist, hing damit an der stabilen Sortierreihenfolge der Kandidatenliste. Bei Gleichstand entscheidet jetzt die niedrigste `agent_id`, also deterministisch.
- **Die Alias-Tabelle ist als domänenspezifisch gekennzeichnet:** Ihre Einträge (`official`, `university`, `mediaoutlet`, `student`, `professor`, `alumni`) stammen aus der OASIS-Campus-Demo und greifen außerhalb davon nicht — insbesondere für keine deutschsprachige Domäne. Sie bleibt für die Campus-Demo erhalten, suggeriert aber keine Abdeckung mehr, die sie nicht hat.

### Fixed (belegte Zahlenaussagen überleben eine deutsche Umstellung — 2026-08-11)

- **Die Faktenextraktion las den Aussageteil nur rechts der Zahl und erklärte belegte Sätze dadurch zu Widersprüchen:** `extract_numeric_facts` bestimmte das Prädikat eines `NumericFact` ausschließlich aus `sentence[match.end():]`. Deutsch besetzt das Vorfeld aber frei — in „Auf der Personalliste des Trägers stehen 31 Honorarkräfte.“ steht die gesamte Aussage *links* der Zahl, rechts bleibt nichts. `classify_evidence` verglich anschließend ein leeres Prädikat gegen die Evidence, kam auf eine Deckung von 0.00 und vergab `CONTRADICTED` mit der Begründung „der Claim behauptet mehr als die Quelle deckt“. Die Deckung war nicht null, sie war nie gemessen worden. Folge: `verify_prose` entfernte den Satz aus dem Fließtext, obwohl er wörtlich im Evidence-Pool stand, und `detect_contradiction_penalty` senkte zusätzlich die Confidence des Claims. Beobachtet an `report_4786a1a3d4ea` (Section 2, „31 Honorarkräfte“) in #1209 — derselbe Fakt blieb in Section 1 stehen, weil er dort in der Wortstellung der Quelle formuliert war.
- **Das Vorfeld wird jetzt ergänzend herangezogen, aber nur wenn der Teil rechts der Zahl keine eigene Aussage trägt** (weniger als zwei Inhaltswörter). Die Einschränkung ist der Punkt: ein generelles Zusammenziehen beider Satzhälften zog Rahmensprache wie „Die Datenlage zeigt, dass …“ ins Prädikat, blähte die Claim-Seite von `coverage_ratio` auf und machte umgekehrt belegte Aussagen zu `predicate_overreach` — gemessen an den Artefakten zweier abgeschlossener Läufe fielen dadurch zwei zuvor gebundene Claims heraus. Mit der Einengung ändert sich über ~21.000 reale Claim-/Evidence-Paare aus `report_a7bc5c0cbc0d` und `report_6078e644a860` kein einziges `SUPPORTED`-Urteil.
- **Nicht behoben und bewusst als `xfail` mit Begründung geführt:** wechselt zusätzlich das Verb („stehen auf“ → „werden geführt“), bleibt die Aussage unbelegt. `coverage_ratio` vergleicht Prädikate rein lexikalisch ohne Stemming, und der LLM-Judge darf im numerischen Pfad kein `SUPPORTED` erzeugen. Beides zu ändern ist eine ADR-0002-Entscheidung und gehört nicht in diesen Fix.

### Added (Guard gegen Prompt-Regeln auf unerreichbaren Codepfaden — 2026-08-11)

- **Die Konfliktregel und die Tool-Skip-Klausel für `DISLIKE_*` erreichen im Parallel-Lauf keinen Agenten.** Beide stehen ausschließlich in `build_agent_prompt_with_tools` (`backend/scripts/agent_tools.py`), die produktiv nur über `ToolAwareActionLoop.decide_action` erreicht wird. `run_parallel_simulation.py` setzt `tool_loop` in `run_twitter_simulation()` und `run_reddit_simulation()` hart auf `None` („Native CAMEL function-calling replaces the old ReACT-style tool_loop”), womit der einzige Guard, der `decide_action` aufruft, statisch unerreichbar ist. Das erklärt, warum fünf vollständige Läufe über vier Modellkonfigurationen kein einziges Dislike produziert haben, obwohl die Fixes aus #1220 und #1223 gemerged sind. Bestätigt am Log von `sim_fcacad36b13b` (`enable_agent_tools: true`, aber kein `[ToolUse] Tool registry ready` — stattdessen `Attached 2 FunctionTools`).
- **Es ist eine Divergenz zwischen zwei Runnern, kein genereller Defekt.** `SinglePlatformRunner` (`sim_runtime/platform_runner.py`, bedient `run_twitter_simulation.py` und `run_reddit_simulation.py`) weist `self.tool_loop` per `create_tool_aware_loop` regulär zu — dort wirkt die Regel. Produktive Läufe fahren aber `run_parallel_simulation.py`.
- **Neuer Guard `test_parallel_runner_prompt_builder_is_reachable`** meldet per AST jeden `if <name> and …`-Zweig, dessen Name innerhalb derselben Funktion ausschließlich `None` zugewiesen bekommt. Er ist bewusst konservativ: eine zweite Zuweisung — auch in einem anderen Zweig — macht den Fund hinfällig, Tupel-Ziele und `AugAssign` werden nicht erfasst. Das kostet höchstens einen übersehenen Fund, nie einen falschen. Als `xfail(strict=True)` geführt, damit die Suite grün bleibt und der Test laut wird, sobald #1215 entschieden ist. `test_single_platform_runner_keeps_the_tool_loop_reachable` sichert die intakte Gegenseite.
- **Die beiden Tests aus #1220/#1223 tragen jetzt einen Hinweis im Docstring**, dass sie den Prompt-Text prüfen und nicht den Produktivpfad. Ohne ihn liest sich ihr grüner Status als Beleg, dass die Regel wirkt — dieselbe Fehlerklasse, die #1230 für Befund 5c benannt hat („der Test prüfte eine Annahme, nicht die Realität“).

### Behoben

- `test_on_hardcutoff_day_list_must_already_be_empty` verglich das Datum der
  lokalen Zeitzone (`datetime.date.today()`) gegen das UTC-Datum, das
  `scripts/check-pip-audit-hardstop.sh` mit `date -u` bildet. In Zeitzonen mit
  UTC-Versatz fielen beide zwischen Mitternacht und dem Versatz auf
  verschiedene Tage — der Test setzte den Cutoff dann auf den Folgetag aus
  Sicht des Skripts, das nahm korrekt den „vor dem Hardcutoff"-Zweig und lieferte
  Exit 0 statt der erwarteten 2. In Europe/Berlin betraf das das Zeitfenster
  00:00–02:00. Der Test bildet sein „heute" jetzt ebenfalls in UTC. (#1203)

Der HARDSTOP `workers = 1` im Produktions-Gunicorn ist nicht mehr nur ein
Kommentar in der Konfiguration, sondern in ADR-0015 beziffert — und der
Kommentar erwies sich dabei als unvollständig.

Der prozesslokale Zustand zerfällt in drei Klassen: verschiebbare Datenwerte
ohne geteilten Ort, Fälle mit vorhandener Ablage, denen nur Cache oder Sperre
fehlen, und **nicht verschiebbare** Betriebssystem-Handles — Popen-Objekte,
In-Prozess-Queues und offene Dateideskriptoren im `SimulationRunner`. Die dritte
Klasse ist durch keine geteilte Ablage lösbar, sondern nur dadurch, dass genau
ein Prozess einen Lauf besitzt. Genau das liefert die persistente Job-Queue mit
eigenen Workern aus #1472; das Anheben von `workers = 1` ist dessen Folge, keine
Vorarbeit.

Kein Produktionscode geändert.

### Fixed (Der Container-Scan läuft nicht mehr auf einer längst behobenen Distro-CVE rot — 2026-08-17)

- **`build-only` scheiterte acht Läufe am Stück am Schritt „Trivy container scan“, ohne dass ein einziger dieser Commits die Ursache trug.** Auslöser war CVE-2026-53615 (Integer-Overflow in `libblkid/src/partitions/dos.c`) im `util-linux`-Stack des Prod-Basisimages — neun Binärpakete (`bsdutils`, `libblkid1`, `liblastlog2-2`, `libmount1`, `libsmartcols1`, `libuuid1`, `login`, `mount`, `util-linux`) auf `2.41-5`, fixbar ab `2.41.5-0+deb13u1`. Da `ignore-unfixed: true` gesetzt ist, zog das Gate genau deshalb hart: der Fix existierte, das Image hatte ihn nur nicht.
- **Der Befund war im Job-Log nicht sichtbar.** Der Scan läuft mit `format: sarif`, und in dem Modus druckt Trivy keine Findings-Tabelle — das Log endete nach den `Detecting vulnerabilities`-Zeilen direkt auf `exit code 1`. Die CVE ließ sich nur über die hochgeladenen Code-Scanning-Alerts (`tool_name=Trivy`, Kategorie `trivy-container`) bestimmen. Issue [#1328](https://github.com/arn0ld87/agora/issues/1328) vermutete daher zunächst eine fehlende `ignore-unfixed`-Einstellung, die tatsächlich seit `ee2adb9e` gesetzt ist.
- **Ein Digest-Bump hätte nicht geholfen.** Verifiziert: der gepinnte `python:3.14-slim` (`sha256:cea0e604…`) und der am 2026-08-17 aktuellste (`sha256:ce407646…`) lieferten beide weiterhin `util-linux 2.41-5`. Debian hatte den Fix zu dem Zeitpunkt bereits im trixie-Repo (`apt-cache policy` meldet `Candidate: 2.41.5-0+deb13u1`); nachgebaut war das Docker-Official-Image noch nicht.
- **Die `prod`-Stage fährt jetzt `apt-get upgrade -y`,** bevor `tzdata` installiert wird. Bewusst allgemein statt auf `util-linux` verengt: ein Digest-Pin ohne Upgrade-Schritt koppelt die Rotphase der CI an einen fremden Rebuild-Zyklus, und jedes künftige Debian-Advisory wäre erneut ein mehrtägiger Dauerrot-Zustand. Der Digest-Pin bleibt die reproduzierbare Ausgangsbasis; die Security-Patches darauf sind per Definition zeitabhängig.
- **Keine Ausnahme, keine Absenkung.** `severity: CRITICAL,HIGH` und `exit-code: "1"` bleiben unverändert, `.trivyignore` und `docs/dependency-risk-exceptions.json` bekommen keinen Eintrag — Bedingung 1 der Ausnahmeregel („kein Upstream-Fix verfügbar“) war nicht erfüllt, also gilt der Registergrundsatz „sofort fixen“. Der Vorgang ist in `docs/dependency-risk-register.md` als aufgelöster Fall mit Verifikationsprotokoll dokumentiert.
- **Nebenwirkung, die den Anlass mitträgt:** solange das Gate dauerhaft rot steht, steht jeder PR auf `mergeState=UNSTABLE` und die Folgeschritte (`SBOM erzeugen`, `Image-Artefakt hochladen`) werden übersprungen — es entstand seit dem 2026-08-17 keine SBOM mehr. Beides läuft mit diesem Fix wieder.

### Fixed (Fehlkonfigurierter Toolcall-Modus verhält sich wie nicht konfiguriert — 2026-09-08)

- **Ein Tippfehler in `REPORT_TOOLCALL_MODE` wechselte den Modus, statt auf den Default zurückzufallen.** Wer die Variable gar nicht setzt, bekommt `native` — das ist der dokumentierte Default, begründet damit, dass Modelle wie `deepseek-v4-flash:cloud` keinen sauberen XML-Block senden. Wer sich vertippte, bekam dagegen `xml`, den Legacy-XML-Parsing-Pfad. Damit erhielt ausgerechnet die Fehlkonfiguration ein anderes Verhalten als die Nicht-Konfiguration. Der Kommentar begründete den xml-Fallback als „legacy-stable … statt stillschweigend in den native-Pfad zu rutschen und 400er zu provozieren" — die Begründung trug nicht, weil der Default-Pfad genau dorthin führt. Der Fallback zeigt jetzt an allen vier Stellen auf `native`: `Config` (`app/config.py`), `AgoraSettings._normalize_report_toolcall_mode` (`app/settings.py`) sowie die beiden Defense-in-Depth-Normalisierungen in `report_agent/workflow.py` (`generate_section_react`, `chat`). Wer den XML-Pfad will, wählt ihn ausdrücklich.
- **Die Whitelist-Tests der Config-Ebene prüften ihre eigene Testlogik, nicht den Produktionscode.** `test_report_toolcall_mode_normalizes_casing_and_whitespace` und `test_report_toolcall_mode_invalid_falls_back_to_xml` replizierten die Normalisierung (`strip().lower()` + Whitelist) in Python, setzten das selbst berechnete Ergebnis per `monkeypatch.setattr` auf `Config` und prüften es anschließend zurück. Sie wären bei jeder beliebigen Änderung an `app/config.py` grün geblieben. Ersetzt durch `_config_mode_for_env`, das `Config.REPORT_TOOLCALL_MODE` in einem frischen Interpreter mit gesetzter Env ausliest — die Normalisierung läuft damit echt, ohne `importlib.reload` und dessen im Modul-Docstring beschriebene Modul-Cache-Fallstricke. Gegenprobe: mit zurückgedrehter Änderung fallen 8 Tests, vorher keiner.
- **Zwei Invariantentests halten die Entscheidung fest:** `test_invalid_fallback_equals_unset_default` (Config-Ebene) und `test_report_toolcall_mode_fallback_equals_unset_default` (`AgoraSettings`) vergleichen das Verhalten bei Fehlwert direkt mit dem Verhalten ohne gesetzte Variable. Fällt beides künftig auseinander, ist das eine bewusste Entscheidung und bricht sichtbar.
- **Der XML-Pfad bleibt erhalten.** Er ist kein Altlast-Zweig, sondern das Netz für lokale Modelle, die zwar OpenAI-kompatibel sprechen, sich beim Function-Calling aber nicht ans Format halten. Geändert hat sich nur, dass man ihn absichtlich wählt statt versehentlich hineinzurutschen.

### Fixed (Testdouble der Abschnitts-Pipeline nachgezogen — 2026-09-08)

- **Report Agent (Tests):** `FakeReportManager` in `tests/services/test_section_pipeline.py` kennt jetzt `_get_section_path`. #1475 zog `_remove_orphan_markdown` in `process_section` ein und griff damit auf einen Anschluss zu, den dieses Testdouble nicht hatte — `test_restored_section_without_persisted_evidence_still_returns_content` lief in einen `AttributeError` und färbte `main` rot. (#1475)
- **Report Agent (Tests):** derselbe Test prüft jetzt das Sollverhalten seit #1475 statt des abgelösten: Markdown ohne Evidence wird als Waise entfernt und der Abschnitt neu generiert, nicht mehr restauriert. Er heißt entsprechend `test_persisted_section_without_evidence_is_regenerated_and_orphan_removed` und belegt das Löschen an einer echten Datei unter `tmp_path`. (#1475)

### Behoben

- Der parallele Twitter+Reddit-Runner (`run_parallel_simulation.py`) ist der
  Default-Pfad für jeden Simulationslauf, der nicht explizit Twitter- oder
  Reddit-only ist — er hatte bisher weder Hard-Budget noch Pause- noch
  Stop-Kontrolle. Beide Runden-Schleifen prüfen jetzt an jeder Rundengrenze
  über dieselbe `RoundBoundaryControl` wie `sim_runtime.platform_runner`
  (Pause abwarten, kooperativen Stop, hartes Budget); bei Budget-Abbruch
  endet der Lauf deterministisch statt in den Wait-Mode zu gehen, damit der
  Backend-Monitor den Abbruchgrund übernimmt.
- `platform_runner.py` nutzt dieselbe `RoundBoundaryControl` statt eines
  inline duplizierten Prüfblocks — Verhalten unverändert, `budget_abort_info`
  bleibt bei Stop/Normal-Durchlauf `None` und trägt nur beim Budget-Abbruch
  das Info-Dict, damit der nachfolgende Wait-Mode-Guard weiter korrekt greift.
- `ParallelIPCHandler` bucht Interview- und Batch-Interview-Verbrauch jetzt
  auf den Report-Run (`report_run_id`), sobald ein Report-Interview über den
  parallelen Default-Pfad läuft — vorher blieb dieser physische Modellaufruf
  unverbucht und das Hard-Budget eines Report-Laufs war dort umgehbar. Die
  Zuordnung nutzt dieselbe `report_attribution()`-Funktion wie
  `sim_runtime.ipc.IPCHandler` (aus dessen bisheriger Methode extrahiert,
  verhaltensneutral) statt einer zweiten Implementierung.

### Fixed (Simulations-Laufzeit - 2026-09-07)

- **Nutzer-Stop endet als `stopped`/`user_stop` statt `failed`/`error`:** `process_manager.stop_simulation` schreibt vor dem Terminieren des Subprozesses einen `cancel_abort`-Marker mit `source="user_stop"`, damit der Monitor-Thread den SIGTERM-Exit (returncode -15) nicht als technischen Fehler klassifiziert. Der Monitor wertet das `source`-Feld aus und schreibt `termination_reason="user_stop"` in RunRegistry und finales Manifest; Marker ohne `source` oder mit `source="backend-monitor"` (Cancel-Flag-Konsum) bleiben beim bisherigen `user_cancel` (Rückwärtskompatibilität).
- **Force-Restart erzeugt keine Orphan-Finalisierung mehr:** `start_simulation` vergibt pro Simulation einen Generation-Token an den Monitor-Thread. Ein veralteter Monitor (Stop direkt gefolgt von Neustart derselben `simulation_id`) überspringt Finalisierung (Guard vor save_state/RunRegistry/Manifest-Write), `processes.pop` greift nur noch per Identitätscheck auf den eigenen Prozess, und `stop_simulation` joint den Monitor-Thread mit Timeout (grace_period + 2s, min 5s) und warnt bei Überschreitung.
- **Stale `cancel_abort.json` verfälscht keinen Folgelauf mehr:** Der Marker ist first-writer-wins und blieb nach einem Nutzer-Stop im Simulationsverzeichnis liegen, sodass ein Neustart derselben `simulation_id` selbst bei Exit 0 als `stopped`/`user_stop` klassifiziert wurde. `start_simulation` entfernt ihn jetzt (samt verwaister `.tmp`-Datei) vor dem Subprozess-Spawn.
- **Generation-Guard greift vor jedem Monitor-Write:** Der Guard saß bisher nur im Terminal-Pfad. Ein veralteter Monitor konnte den State des neuen Laufs weiterhin über den `save_state`-Aufruf der Schleife oder über den Exception-Handler (`FAILED` + Manifest-Finalisierung) überschreiben. Beide Pfade prüfen die Generation jetzt ebenfalls.
- **Cleanup trifft nur noch eigene Ressourcen:** Der `finally`-Block eines veralteten Monitors entfernte Action-Queue und Log-Handles des Ersatzlaufs und stoppte dessen Graph-Memory-Updater. Queue und Datei-Handles werden jetzt per Identitätscheck abgeräumt, das Graph-Memory-Cleanup nur bei aktueller Generation.

### Changed (`get_status` ist in eine Quellen-Kette zerlegt — 2026-08-17)

- **`ReportStatusService.get_status` war mit cyclomatic complexity 41 der viertgrößte Hotspot im Backend** und beantwortete dieselbe Frage — „wie steht es um diesen Report?“ — aus vier Quellen in einer einzigen Funktion, mit einem Zustandsfluss quer durch die Blöcke: der Zweig für den persistierten Report schrieb `task_id` und `simulation_id` für die nachfolgenden Zweige fort. Der Refactor-Auftrag („Extraktion von Stage-Branching“) stand seit Juni 2026 im Kommentarkopf der radon-Allowlist.
- **Die Quellen sind jetzt einzeln benannte Stufen**, nach Verlässlichkeit geordnet: Run-Registry → persistierter Report → lebender Task → Simulation → Acknowledge. Jede liefert entweder ein fertiges Statusdokument oder `None`, worauf die nächste übernimmt. Der Zustandsfluss ist nicht wegabstrahiert, sondern explizit gemacht: die Stufen reichen ein gemeinsames, veränderliches `_StatusQuery` weiter, und der Modul-Docstring benennt, dass Stufe 1 die späteren Stufen mit IDs versorgt.
- **Komplexität je Funktion:** `get_status` 41 → **7**, Klasse `ReportStatusService` 42 → **8**. Höchster Wert im Modul ist `_status_from_run_registry` mit 15 — unter der D-Schwelle. **Beide Allowlist-Einträge für `report_status.py` entfallen damit ersatzlos**, es kommt kein neuer hinzu.
- **Ein Detail, das vorher nur implizit im Kontrollfluss stand, ist jetzt benannt:** die Menge der Run-Status, bei denen der Registry-Eintrag die Auskunft abschließt, heißt `_CONCLUSIVE_RUN_STATUSES`. Ein *unbekannter* Run-Status beendet die Kette bewusst nicht — dann entscheiden die späteren Stufen. Ebenso dokumentiert ist, warum Stufe 3 bei bekannter `report_id` nicht greift: sonst käme ein fremder Report als Antwort auf die Frage nach einem bestimmten.
- **Abgesichert durch 23 neue Charakterisierungstests** (`test_report_status_resolution_paths.py`), die vor dem Umbau geschrieben wurden und gegen den unveränderten Code grün waren. Sie decken alle fünf Stufen ab, darunter bisher ungetestete Pfade: Durchfallen bei unbekanntem Run-Status, tote `task_id` nach Serverneustart, `simulation_id` aus Task-Metadaten, und ein kaputter Task-Store, der geschluckt und geloggt statt durchgereicht wird. Die drei bestehenden Regressionstests aus #1277-2 laufen unverändert.

### Changed (Outline-Mapping auf den Contract lebt nur noch an einer Stelle — 2026-08-17)

- **`map_outline_for_contract` existierte zweimal:** einmal als `ReportStatusService.map_outline_for_contract` (`report_status.py`), einmal als `ReportExportService.map_outline_for_contract` (`report_export.py`). Beide bilden dieselbe Regel ab — Dataclass-Outline auf die v2-Contract-Form, inklusive der Fallbacks `"Section"`, `"Report"` und `"—"` sowie des `description`-vor-`content`-Vorrangs. Die Rümpfe unterschieden sich ausschließlich in Typannotationen (`dict | None` gegen `Optional[dict[str, Any]]`, `list[dict]` gegen `list[dict[str, Any]]`), die zur Laufzeit wirkungslos sind; über fünf Eingabefälle inklusive `None`, leerem Dict und Nicht-Dict-Einträgen in `sections` lieferten beide dieselbe Ausgabe. Eine Änderung an der Contract-Form hätte nur eine der beiden Stellen erwischt.
- **Der Status-Service bezieht das Mapping jetzt vom Export-Service**, dem `api/report.py` es ohnehin schon entnimmt (`_map_outline_for_contract = ReportExportService.map_outline_for_contract`). Kein neues Modul: die Regel gehört dem Contract-/Export-Pfad, ein dritter Ort hätte die Zahl der Stellen erhöht statt gesenkt. `report_export` importiert `report_status` nicht — es entsteht kein Import-Zyklus. Die Zuweisung ist bewusst in `staticmethod(...)` gehüllt: als blankes Klassenattribut bekäme die Funktion bei Zugriff über eine Instanz `self` als erstes Argument gebunden und verlöre das Outline-Dict.
- **Ein wörtlich doppelter Kommentarblock in `get_status` ist entfernt** — die neunzeilige Begründung zu Issue #1277-2 stand zweimal unmittelbar hintereinander.
- **Die Allowlist-Obergrenze für die Klasse `ReportStatusService` steigt von 27 auf 42, ohne dass Komplexität hinzugekommen wäre.** radon misst Klassen als Mittelwert über ihre Methoden: vorher `get_status` (41) und `map_outline_for_contract` (10) → 27, nachher `get_status` allein → 42. Der Wert steigt, weil die *einfache* Methode verschwunden ist. `get_status` selbst bleibt unverändert bei 41; der Refactor-Auftrag (Stage-Branching extrahieren) steckt vollständig dort und ist weiterhin offen.

Das Projektregal zeigt wieder den Projektnamen statt der rohen `project_id`.
`useShelf` las das Feld `project_name`, das Backend liefert `name` — die
Bedingung fiel deshalb immer auf die Kennung zurück.

Unentdeckt blieb das, weil die Antwortform von Hand als Interface deklariert war
(mit `[key: string]: unknown`, wodurch der Zugriff auf ein nicht existierendes
Feld gültiges TypeScript blieb) und die Testfixture das Feld erfand. Beides ist
durch einen Zod-Spiegel `contracts/projectContract.ts` ersetzt, der die Antwort
`.strict()` prüft. Der strikte Typ hat direkt einen zweiten toten Zweig
aufgedeckt: `useGraphBuildPipeline` verglich den Projektstatus mit `completed`,
den es nur für Tasks gibt — für ein Projekt heißt der Wert `graph_completed`.

`docker-compose.yml` zieht die Redis-Image-Version von `redis:7-alpine` auf
`redis:8-alpine` nach. `agora-redis` lief produktiv bereits seit dem 18.09.
auf Version 8 (manuell hochgezogen); ohne diesen Commit hätte der nächste
`docker compose up` auf dem Deploy-Host die Version stillschweigend wieder
auf 7 zurückgesetzt.

Kein Anwendungscode geändert.

### Fixed (Kollektiv-Personas behalten age/gender/mbti als Schlüssel in `reddit_profiles.json` — 2026-08-11)

- **Kollektiv-Personas ließen `age`, `gender` und `mbti` beim Reddit-Export komplett verschwinden, nicht nur ihren Wert:** `to_reddit_format()` schrieb diese drei Felder nur, wenn ihr Wert wahr war — bei `None` (dem korrekten Wert für Organisationen, Behörden und andere Kollektiv-Entitäten) fehlte der **Schlüssel** in `reddit_profiles.json`, nicht nur der Wert. `oasis/social_agent/agents_generator.py::process_agent` greift auf `agent_info[i]["mbti"]`/`["gender"]`/`["age"]` aber ungeschützt zu und wirft dort ein `KeyError`. Weil Reddit- und Twitter-Zweig über ein gemeinsames `asyncio.gather` laufen, riss ein einziges betroffenes Profil die komplette Simulation mit Exit-Code 1 — beobachtet an einem Lauf mit 12 von 46 betroffenen Profilen, alle mit `persona_kind: collective`. Betroffen war jeder Lauf mit mindestens einer Entität aus `GROUP_ENTITY_TYPES` (`organization`, `company`, `institution`, `group`, `community`, …), praktisch jedes reale Dokument.
- **Der Fix schreibt die drei Schlüssel jetzt immer, mit `""` statt `None` als Wert für Kollektiv-Personas.** Das erfindet keine Demografie: `oasis/social_platform/config/user.py::to_reddit_system_message` baut unbedingt den Satz `"You are a {gender}, {age} years old, with an MBTI personality type of {mbti} from {country}."` — ein `None` stünde dort wörtlich im Agent-Prompt, der Leerstring nicht. Die Substanz einer Kollektiv-Persona steht im vorangehenden `user_profile`, nicht in diesen drei Feldern; die zugrundeliegende Zusage („Organisationen haben keine erfundene Vita“) bleibt unverändert. `to_twitter_format()` ist nicht betroffen: der Twitter-Pfad läuft über ein CSV mit festem Header, das diese Felder gar nicht führt.

### Fixed (Komplexitäts-Gate meldet wieder Wachstum in geduldeten Funktionen — 2026-08-17)

- **Das radon-Gate duldete Bestands-Hotspots in beliebiger Höhe, nicht in gemessener:** `check_complexity.py` unterstützt seit [#1084](https://github.com/arn0ld87/agora/issues/1084) eine cc-Obergrenze je Allowlist-Eintrag (`# cc<=<N>`), aber nur 5 von 55 Einträgen trugen eine. Ein Eintrag ohne Obergrenze prüft ausschließlich, *ob* eine Funktion geduldet ist, nie *wie stark sie gewachsen ist* — der Kommentarkopf der Allowlist benannte diese Lücke bereits am 04.08.2026, ohne dass sie geschlossen wurde. Gemessen am 17.08.2026 gegen die dokumentierten Aufnahmewerte: `ReportAgent._save_evidence_section` 36 → **52**, `degrade_sections_for_violations` 34 → **50**, `monitor_simulation` 23 → **29**, `classify_evidence` 34 → **38**. `generate_report` war durch [#1219](https://github.com/arn0ld87/agora/issues/1219) (SectionPipeline) am 11.08. auf 47 gesenkt worden und stand sechs Tage später wieder bei **55**. Kein einziger dieser Zuwächse hat je einen roten Lauf erzeugt.
- **Jeder Eintrag trägt jetzt eine Obergrenze in Höhe des gemessenen Ist-Werts.** Das zementiert den Bestand nicht, es friert ihn ein: weiteres Wachstum schlägt an, eine Absenkung erzeugt einen Hinweis, die Obergrenze nachzuziehen. Der Refactor-Auftrag je Cluster bleibt im Kommentarkopf stehen und ist unverändert offen.
- **Fünf Einträge sind ersatzlos entfallen, weil ihre Duldung gegenstandslos geworden war.** `app/api/report.py::get_generate_status` stand als „F (cc=44)“, später „F (cc=68)“ in der Liste und misst real **B (cc=9)**; `app/api/report.py::generate_report`, `ReportGenerationService.start_generation` und `OasisProfileGenerator._generate_profile_with_llm` liegen bei C und damit unter der D-Schwelle; `app/api/graph.py::generate_ontology` existiert nicht mehr, die Funktion ist nach `app/api/graph_build.py` gewandert. Fällt eine davon künftig wieder auf D+, schlägt das Gate an — das ist gewollt. Der Bestand beträgt damit 50 Einträge und deckt sich exakt mit den 50 gemessenen D+-Hotspots: keine ungedeckten Hotspots, keine Karteileichen.
- **Zwei Regressionstests halten den Zustand:** `test_every_entry_has_a_complexity_ceiling` schlägt bei einem Eintrag ohne Obergrenze an, `test_no_entry_points_at_a_vanished_symbol` bei einem Eintrag ohne zugehöriges Symbol. Letzterer prüft per AST auf Symbol- statt auf Datei-Ebene — ein Datei-Existenz-Check hätte den historischen Fall `app/api/graph.py::generate_ontology` nicht gefangen, weil die Datei weiterhin existiert und nur die Funktion daraus verschwunden ist.

Die vor PR 4 offen geführte Frage, ob psycopg 3 unter dem gunicorn-gevent-Worker
den Hub blockiert, ist beantwortet: der Treiber kooperiert, sobald
`gevent.monkey.patch_all()` vor dem ersten psycopg-Import gelaufen ist — was
`backend/wsgi.py` bereits sicherstellt. Acht gleichzeitige Abfragen von je einer
Sekunde brauchen 1,08 s statt 8. Der Nachweis liegt als Integrationstest vor
(`backend/tests/integration/test_gevent_psycopg_cooperation.py`), die
Entscheidung samt ihrer Grenzen in ADR-0014.

Projektmetadaten haben einen Pydantic-Vertrag (`app/contracts/project_contract.py`)
und eine Repository-Grenze (`ProjectRepository` mit dem Dateiadapter
`FileProjectRepository`). `Project` war bisher eine Dataclass, deren `to_dict()`
über drei Endpunkte ausgeliefert wurde — eine Dataclass auf einer API-Grenze.

An der Ablage ändert sich nichts: `uploads/projects/<project_id>/project.json`
behält Pfad, Schlüssel und Reihenfolge, `ProjectManager` bleibt als Fassade
stehen, und `AGORA_PROJECT_BACKEND` steht im Default auf `file`. Artefakte
(`files/`, `extracted_text.txt`, Dokument-Manifest) bleiben ausdrücklich außerhalb
des Ports.

Projektmetadaten haben einen zweiten Adapter: `PostgresProjectRepository` auf
der neuen Tabelle `agora.projects`. Der Spaltenschnitt ist Kern plus Nutzlast —
die Felder, nach denen abgefragt und sortiert wird, bekommen eine eigene Spalte,
alles Übrige liegt in `payload jsonb`. Die Aufteilung wird aus
`Project.to_dict()` abgeleitet statt gepflegt, damit ein künftiges Vertragsfeld
nicht still verlorengeht.

`backend/scripts/migrate_projects_to_postgres.py` überträgt den Dateibestand,
lässt das Dateisystem unberührt und vergleicht mit `--verify` jedes Feld jedes
Projekts. Ablauf und Rückweg stehen in
`docs/runbooks/projekt-postgres-umstellung.md`.

Umgeschaltet ist nichts: `AGORA_PROJECT_BACKEND` bleibt im Default auf `file`.
Neu ist, dass `Config.validate()` den Wert `postgres` ohne gesetzte
`DATABASE_URL` schon beim Start ablehnt statt erst beim ersten Projektzugriff.

### Behoben (Post-#1497-Stabilisierung — 2026-09-11)

- **Prepare meldet kein nicht persistiertes `ready` mehr:** `check_simulation_prepared` promotete einen `preparing`-Zustand nach `ready` und verschluckte einen fehlgeschlagenen `store.write_json` still. Weil die Aufrufer `is_prepared=True` unabhängig vom Detailstatus in `status: ready, progress: 100` übersetzen, meldete die API einen Ready-Zustand, den die Persistenz nie gesehen hatte. Die Promotion schreibt jetzt auf einer Kopie, persistiert zuerst und meldet nur bei erfolgreichem Write ein positives Ergebnis; ein Fehlschlag wird auf error-Level protokolliert und als „nicht vorbereitet" mit Grund zurückgegeben.
- **Erschöpftes Hartbudget stoppt wartende Persona-Jobs:** Im Thread-Pfad verließ `BudgetExceededError` den `ThreadPoolExecutor`-Block ungebremst — `__exit__` ruft `shutdown(wait=True)` ohne `cancel_futures`, also setzte jede eingereihte Persona trotzdem noch ihre LLM-Calls ab. Im Gevent-Pfad ist der `imap_unordered`-Produzent kein Pool-Mitglied; `pool.kill()` stoppte ihn nicht, und das `join()` im `finally` ließ ihn den Pool weiter nachfüllen, sodass die Greenlets sogar den Funktionsaustritt überlebten. Beide Pfade brechen jetzt kontrolliert ab; laufende Worker laufen wie bisher aus, kein Retry auf `BudgetExceededError`.
- **Runtime-Override ohne Endpoint wird abgelehnt:** Der `RuntimeLlmConfig`-Zweig von `_resolve_llm_connection` reichte einen aktivierten Override mit API-Key, aber ohne `base_url`, ungeprüft durch — der nachgelagerte Consumer füllte dann `Config.LLM_BASE_URL` auf und schickte Modell und Schlüssel des einen Providers an den Endpoint eines anderen. Bei `require=True` ist eine `base_url` jetzt Pflicht; ausgenommen bleiben Provider mit echtem CLI-Transport (`codex_cli`).
- **Interviewpfad validiert seine Eingaben:** `reddit_profiles.json` wird vor der Nutzung gegen `PersistedAgentProfiles` geprüft (`{"profiles": []}`, `[null]`, `["invalid"]`, `[123]` flogen vorher erst beim ersten `profile.get(...)` auseinander). Die LLM-Antworten der Panel-Auswahl und der Fragengenerierung haben eigene Pydantic-v2-Verträge, die zusätzlich als Schema an `chat_json` gehen: `selected_indices` akzeptiert keine Booleans, keine Strings, keine Duplikate und keine Indizes außerhalb des Profilarrays; `questions` muss eine Liste aus 3–5 nichtleeren Strings sein.
- **Skeptikerquote gilt für die Endpopulation:** `_ensure_skeptic_quota` rechnete `ceil(original_total * min_ratio)` und übersah, dass jeder hinzugefügte Skeptiker die Population mitvergrößert — 10 Personas ohne Skeptiker ergaben bei 20 % zwei Zusätze, also 16,67 %. Gelöst wird jetzt die Zielungleichung nach dem kleinsten passenden Zuwachs.
- **`MAX_CONTEXT_LENGTH` gilt für den ganzen Kontext:** Gekürzt wurde nur `document_text`; ein überlanges `simulation_requirement` oder eine überlange Entity-Zusammenfassung überschritt das Limit allein. Die Abschnitte werden jetzt in Prioritätsreihenfolge gegen ein gemeinsames Budget gefüllt, Header nie angeschnitten, der zeilenstrukturierte Entity-Block an der Zeilengrenze.
- **Truncated-JSON-Reparatur respektiert Verschachtelung:** Offene `{}`/`[]` wurden global gezählt (inklusive der Vorkommen in String-Literalen) und pauschal erst alle `]`, dann alle `}` angehängt. Ein String- und Escape-bewusster Scanner führt jetzt einen Stack und schließt in LIFO-Reihenfolge.
- **Kollektiv-Ablehnung passt zum Kollektiv-Schema:** Der Eignungsblock verlangte bei `ineligible: true` auch von Gruppen-Entitäten `display_name`, `handle`, `age`, `gender`, `mbti` und `profession` — Felder, die `CollectivePersonaSchema` nicht kennt. Der Kollektivzweig hat jetzt einen eigenen Block ohne erfundene Demografie.
- **Geschlossene Persona-Wertemengen werden erzwungen:** `gender` (individuell) und `voice_register` sind `Literal`-Mengen statt freier Strings; `persona_kind` und `generation_source` bekommen einen Laufzeit-Riegel in `OasisAgentProfile`, weil beide unverändert in `reddit_profiles.json` landen und dort Persona-Galerie und Report-Kennzeichnung steuern.
- **Eigenständige Nebenklausel erbt kein fremdes Prädikat:** In „Im Pilotprojekt kamen 120 Teilnehmende; 18 Lehrkräfte streikten." bekam die 18 das Prädikat „Im Pilotprojekt kamen". Die Unterscheidung läuft jetzt über die Satzstruktur — hinter einem Klauseltrenner beginnt eine neue Aussage, hinter einem Aufzählungskomma nicht —, nicht über die Tokenzahl, die Aufzählungen beschädigt hätte.

### Sicherheit

- **Blockierte-URL-Ausnahmen leaken keine Geheimnisse mehr:** `OutboundRequestBlocked` trug die untrusted URL in Message und `.url`; redigiert wurde nur die Userinfo. Query, Fragment und Pfad tragen in der Praxis genauso häufig Token (`?token=`, `?api_key=`, Secrets im Pfadsegment). Die Message trägt jetzt ausschließlich den Grund, `.url` nur noch Schema + Host + ggf. Port; eine nicht sicher zerlegbare URL liefert gar keine Herkunftsangabe.

### Qualitäts-Gates

- **mypy-Schuld ist sichtbar und eingefroren:** `pyproject.toml` schaltet mypy für `app`, `app.services.*`, `app.utils.*`, `app.llm.*` und weitere per `ignore_errors` ab — das reguläre `mypy app` war grün, obwohl dort die eigentliche Arbeit liegt. `scripts/check_mypy_debt.py` misst mit `mypy-debt.ini` (derselben Konfiguration ohne diesen Block) und vergleicht je Datei gegen `mypy-debt-baseline.txt`: **266 Fehler in 55 Dateien**, gemessen am 11.09.2026. Das Gate failt bei mehr Fehlern je Datei, bei neu fehlerbehafteten Dateien und bei einer wachsenden `ignore_errors`-Liste. Es repariert bewusst nichts.
- **Coverage-Gate basiert auf dem gemessenen Istwert:** Die Schwelle stand auf `--cov-fail-under=60` ohne Branch-Messung, 24 Punkte unter dem tatsächlichen Wert — eine Regression war damit nicht erkennbar. Gemessen über die vollständige Backend-Suite: **83,82 % Line** (26661/31806) und **71,94 % Branch** (6571/9134). `scripts/check_coverage.py` prüft beide Quoten einzeln gegen `coverage-baseline.json` (82,8 / 70,9). `branch_min` ist bewusst keine Wunschzahl: 80 % hätte entweder das Gate sofort rot gefärbt oder Tests provoziert, die Zweige berühren statt Verhalten zu prüfen.
- **Keine neue Radon-Schuld:** `radon-allowlist.txt` ist unverändert; kein Bugfix dieses Laufs hat einen Deckel angehoben oder einen neuen Eintrag gebraucht.

### Architekturblocker

- **Verwaiste In-Process-Jobs werden nach einem Neustart korrigiert ([#1472](https://github.com/arn0ld87/agora/issues/1472), teilweise):** `reconcile_stale_runs` deckte ausschließlich `simulation_run` ab — nur dieser Run-Typ trägt eine `process_pid`. Prepare-, Report- und Graph-Build-Jobs laufen als Thread im Webprozess; nach einem SIGTERM blieb ihr Manifest für immer auf `processing`. `app/jobs/identity.py` gibt jedem Webprozess eine PID plus ein einmaliges Token, `enqueue` stempelt beides ins Manifest, bevor der Thread startet, und `reconcile_stale_jobs` markiert daran erkannte Waisen als `failed`/`process_restart`. Kein neuer Statuswert: `PREPARING → FAILED` ist im FSM bereits erlaubt. **Offen bleibt die Wiederaufnahme** — `_BACKEND` ist weiterhin `"thread"`, ein abgebrochener Lauf ist ehrlich gescheitert, aber nicht fortsetzbar.
- **Die aktive Embedding-Konfiguration steuert den Laufzeitpfad ([#1417](https://github.com/arn0ld87/agora/issues/1417), Teil erledigt):** `EmbeddingService()` löst jetzt in der Reihenfolge ausdrückliche Argumente → aktive Store-Konfiguration → `Config.*` auf. Eine aktive, aber unvollständig auflösbare Konfiguration wirft, statt auf die Env zurückzufallen; `activate()` lehnt einen Dimensionswechsel ohne passende Indexversion ab. Zusätzlich lässt die Auflösung nur eine Konfiguration durch, die zum Inhalt des aktiven Index passt — Lese- und Schreibpfad hängen weiterhin am unversionierten Legacy-Index, ein Modellwechsel würde dort Vektoren zweier Modelle vermischen. Der Index-Cutover fehlt und bleibt Folgearbeit an #1417.
- **Restore-Drill ist ausführbar und maschinell prüfbar ([#766](https://github.com/arn0ld87/agora/issues/766), Werkzeug):** `scripts/restore-drill.sh` plus `backend/scripts/restore_verify.py`. Der Drill selbst bleibt offen — er braucht einen frischen Host mit echtem Backup, und ein Dry-Run-Protokoll ist ausdrücklich kein Betriebsnachweis.

### Fixed (Typbasierte Persona-Eligibility spart LLM-Calls fuer nicht-menschliche Entitaeten — 2026-09-07)

- **Stufe 1 der Eligibility-Pruefung erkennt jetzt zusammengesetzte Ontologie-Typen ohne menschlichen Traeger deterministisch, bevor die LLM-Pruefung sie ablehnt.** Die bisherige Blockliste vergleicht exakt; generierte Typen wie `LearningTechnology` oder `SuccessCriterion` trafen sie nie und liefen als "unbekannter Typ" durchs Gate — Produktionsbefund vom 07.09.2026 zeigte 82 von 118 Entitaeten mit genau diesem Muster, jede davon einen vollen Generierungs-Call fuer eine erwartbare Ablehnung.
- **Geprueft wird auf das Kopfnomen als Suffix, nicht als Teilstring** (`INELIGIBLE_TYPE_HEADS`, `_ineligible_head`): `LearningTechnology` endet auf `technology` und wird geblockt, `AIServiceProvider` endet auf `provider` und bleibt zugelassen — ein Teilstringvergleich haette letzteres ueber `service` faelschlich blockiert.
- **Mehrdeutige Koepfe (`service`, `organization`, `provider`, `representative` u. a.) stehen bewusst nicht in der Menge**, damit Unternehmen und Kollektive mit menschlichem Traeger (z. B. `TechnologyProvider`, `CostPayerOrganization`) das Gate erreichen und weiterhin von der LLM-Pruefung bewertet werden.
- Abgesichert durch parametrisierte Tests fuer blockierte Kompositatypen (u. a. `SoftwareProduct`, `LegalFramework`, `DiscussionTopic`), fuer weiterhin zugelassene individuelle und kollektive Typen sowie gezielt fuer `TechnologyProvider`, `RoleModel`, `ServiceProvider` und `EmployeeRepresentative`.

### Behoben

- Der Graph-Build bricht nicht mehr mit `ConstraintValidationFailed` ab, wenn Neo4j die Bestätigung einer bereits committeten Transaktion nicht mehr zustellen kann. Episode-Knoten und RELATION-Kanten werden per `MERGE` statt `CREATE` geschrieben und überstehen damit einen Retry; zuvor riss die zweite Ausführung entweder den ganzen Build ab (Episode, Unique-Constraint) oder legte still eine Dublette an (RELATION, ohne Constraint).

### Fixed (Komplexitäts-Gate wieder grün, Hypothesen-Rendering zerlegt — 2026-08-17)

- **Das radon-Gate (MAI-17) blockierte jeden Backend-PR unabhängig vom Diff:** `render_hypotheses_for_section` war mit `rank=D`/`complexity=21` in den Bestand gerutscht, ohne dass das Gate beim verursachenden Merge lief — auffällig wurde es erst in einem unbeteiligten PR. Die Funktion ist jetzt in `_render_hypothesis_entry` (eine Hypothese → Markdown-Zeilen, leere Liste = überspringen) und `_render_hypotheses_appendix_note` (Restzahl-Hinweis) zerlegt; die Hauptfunktion sammelt nur noch Einträge und hängt den Hinweis an. Verhalten unverändert: unbrauchbare Einträge erzeugen weiterhin weder Überschrift noch Appendix-Hinweis, und der Hinweis hängt weiterhin an mindestens einer sichtbaren Hypothese. Ein Regressionstest nagelt genau diese Randfälle fest.
- **Das Gate konnte auf PRs gar nicht anschlagen:** `contract-gates.yml::complexity-gate` trug seit 2026-05-17 ein `if: github.event_name != 'pull_request'` und lief damit nur auf `push:main`. Neue D+-Hotspots kamen deshalb ungehindert durch den PR und tauchten erst nach dem Merge auf `main` auf — wo sie niemanden mehr blockierten, aber jeden lokalen `pre-push-gate.sh backend` rot färbten. Das Gate läuft wieder auf `pull_request`. Der PR-Skip beim Voice-Lint bleibt: dort gibt es einen sachlichen Grund (False-Positives bei Code-Kommentaren), beim Komplexitäts-Gate nicht — es vergleicht nur Zahlen gegen die Allowlist.
- **Allowlist-Obergrenze ohne Deckung:** `evidence_migrations.py::demote_unanchored_seed_corpus_records` stand mit `cc<=30` in `backend/radon-allowlist.txt`, misst aber `cc=27` — das Gate wies selbst auf die Luft nach unten hin. Die Obergrenze ist auf den gemessenen Wert abgesenkt, damit weiteres Wachstum wieder anschlägt.

### Fixed (Label-gesteuerte CI-Vollsuiten überleben den nächsten Push — 2026-09-13)

- **Ein gesetztes `needs-backend-ci` galt nur für genau einen Commit:** Die `if`-Bedingung der Jobs `Backend tests + lint` und `Frontend build + lint` in `.github/workflows/ci.yml` griff auf PRs ausschließlich über `github.event.action == 'labeled'`. Jeder danach gepushte Commit löst ein `synchronize`-Event aus, bei dem diese Bedingung falsch ist — der Job sprang auf `skipping`, obwohl das Label weiterhin am PR hing. An [#1498](https://github.com/arn0ld87/agora/pull/1498) wurde das am 13.09.2026 konkret beobachtet: erst ein Ab- und Wiederdranhängen des Labels hat die volle Suite auf dem neuen Stand laufen lassen. Wer nach dem Labeln noch einmal pusht und dann merged, merged einen Commit, den nur das kleine `Backend PR smoke gate` gesehen hat — nie `pytest --cov --cov-fail-under=60`.
- **Beide Jobs prüfen jetzt zusätzlich den Label-Zustand des PR** über `contains(github.event.pull_request.labels.*.name, 'needs-<scope>-ci')`. Damit greift das Label auch bei `synchronize`, `reopened` und `opened` und bleibt so lange wirksam, bis es entfernt wird. Der bisherige `labeled`-Zweig bleibt daneben stehen: das Gate soll nicht davon abhängen, dass das Event-Payload das frisch gesetzte Label bereits in `pull_request.labels` führt.
- **Der Zweck der Gatung bleibt unverändert:** Ohne Label läuft die teure Suite auf PRs weiterhin nicht, und ein `unlabeled` auf genau dieses Label schaltet sie sofort wieder ab. Der Job `Integration tests (echtes Neo4j/Redis)` ist nicht betroffen — er ist nicht label-, sondern ereignisgesteuert (`push:main` / `workflow_dispatch`) und trägt das Muster nicht.

### Removed (Toter v2→ReportV3-Migrationspfad entfernt — 2026-09-08)

- **`evidence_migrations.py::migrate_v2_to_v3` war mit cc=68 der zweithöchste Komplexitäts-Hotspot des Projekts und hat nie einen realen Report berührt.** Kein Aufrufer in `backend/app/`, auch nicht aus `scripts/migrate_v2_full_report_to_v3.py`. Der produktive Pfad ist `report_agent/manager.py::build_report_v3`, das Personas/Segments/FrictionPoints/TrustSignals aus `merge_section_metadata` zieht — im Code ausdrücklich als kanonische Quelle kommentiert. Persistierte ReportV3-Dateien hebt `report_agent/storage.py::_upgrade_report_v3_payload` auf Schema 4, eine eigene, kleinere Implementierung. Gemessen gegen `backend/uploads/reports/` (16 Ordner, Mai–August 2026): acht tragen eine `report-v3.json`, **alle auf `schema_version=4`**; die acht ohne sind `incomplete`, `failed` oder `stopped` — abgebrochene Läufe ohne migrierbaren Inhalt. Am Leben gehalten wurde die Funktion allein durch 22 Tests. Begründung und Rückweg: [ADR-0005](docs/decisions/0005-keine-v2-report-migration.md).
- **Entfernt wurden die Funktion und ihre ausschließlich von ihr genutzte Helfer-Hülle:** `_resolve_evidence_refs`, `_label_to_confidence`, `_section_title_matches`, `_load_personas_from_store`, `_map_profile_to_persona`, `_aggregate_segments`. Die Abgrenzung wurde per AST über die transitive Hülle bestimmt, nicht per Textsuche — `_legacy_item_to_record_and_binding` liegt zwar in derselben Hülle, wird aber von `migrate_evidence_map_v2_to_v3` und `normalize_persisted_evidence_map` weiter gebraucht und bleibt. Keine Modul-Konstante musste weichen. `evidence_migrations.py` schrumpft von 1092 auf 702 Zeilen; die einzige Kopplung des Moduls an `artifact_store` entfällt mit dem `TYPE_CHECKING`-Import.
- **Die Evidence-Map-Migration v1→v2→v3 bleibt vollständig erhalten.** Entfallen ist ausschließlich der Report-*Container*-Aufbau. `normalize_persisted_evidence_map`, `migrate_v1_to_v2`, `migrate_evidence_map_v2_to_v3`, `demote_unanchored_seed_corpus_records` und die übrigen Anker-Migrationen sind live über `normalize_persisted_evidence_map` erreichbar und werden quer durch `report.py`, `report_export.py` und vier `report_agent`-Module importiert. Auch die Semantik `legacy_unresolved` bleibt bestehen, abgedeckt über `tests/api/test_report_evidence_route.py`.
- **Zwei Einträge fallen aus `radon-allowlist.txt`** (`migrate_v2_to_v3  # cc<=68`, `_map_profile_to_persona  # cc<=21`), die Refactor-Notiz zum Modul ist auf den verbliebenen Bestand korrigiert.

### Changed (Datei- und Sperrmechanik der JSON-Stores lebt an einer Stelle statt an drei — 2026-08-17)

- **`OnboardingStateStore`, `UserProfileStore` und `WorkspaceRoutingStore` trugen je eine eigene, zeichengleiche Kopie von `__init__`, `_file_lock` und `reset_for_tests`.** Bei der Sperrmechanik ist das die teuerste Sorte Duplikation: ein vergessenes `LOCK_UN` oder ein falsch gesetztes `try`/`finally` in einer der drei Kopien fällt beim Lesen nicht auf, sondern erst als hängender Prozess unter Last — und ein Fix an einer Kopie hätte die beiden anderen nicht erreicht.
- **Neu ist `app/services/json_file_store.py` mit der Basisklasse `JsonFileStore`.** Sie ist bewusst schmal: sie kennt Pfadableitung (`_path`, `_lock_path`), Prozesssperre (`threading.Lock`) und Dateisperre (`fcntl.flock`), aber weder Payload noch Serialisierung. Es gibt keine abstrakten Hooks — die drei Stores behalten ihre `load`/`save`-Logik unverändert und rufen lediglich `super().__init__(_STORE_FILENAME, data_dir=data_dir)`. Sämtliche Attributnamen bleiben gleich, sodass bestehende Zugriffe und Instanz-Patches unberührt sind.
- **Store-spezifisches Wissen ist erhalten geblieben, nicht mit der Kopie verschwunden:** die Zusage aus `WorkspaceRoutingStore`, dass reine `load()`-Aufrufe bewusst auf den File-Lock verzichten (weil `os.replace` POSIX-atomar ist), während `set_stage_override`/`set_global_default` ihn über Load **und** Save halten, steht jetzt im Klassen-Docstring dieses Stores.
- **`tests/services/test_json_file_store.py` nagelt die Sperrmechanik fest:** dass der Lock exklusiv ist, solange er gehalten wird, dass er danach freigegeben ist, und dass er **auch dann** freigegeben wird, wenn der Block eine Exception wirft. Dazu Pfadableitung, Anlegen fehlender Verzeichnisse und das Aufräumen durch `reset_for_tests`.
- **Der Regressionstest aus dem `data_dir`-Slice wurde angepasst statt gelöscht.** Er prüfte Objektidentität (`module._resolve_data_dir is resolve_data_dir`) und schlug durch diesen Umbau fehl, obwohl sich am Verhalten nichts geändert hatte — die drei Stores beziehen die Auflösung jetzt über die Basisklasse statt als Modulfunktion. Er prüft nun das Ergebnis auf beiden Wegen: vier Stores als Modulfunktion, drei über `JsonFileStore`, und alle sieben landen im selben Verzeichnis.

### Fixed (Der Container meldet beim Start nicht mehr kurzzeitig `unhealthy` — 2026-08-30)

- **Beide `HEALTHCHECK`-Instruktionen im `Dockerfile` liefen mit `--start-period=5s`.** Das Backend braucht auf dem Server rund 60 Sekunden, bis `/readyz` antwortet — in der `dev`-Stage zusätzlich wegen des Vite-Boots. Nach fünf Sekunden zählte Docker die Startup-Fehlschläge bereits als echte Fehler, der Container kippte für rund 20 Sekunden auf `unhealthy` und wurde erst danach `healthy`.
- **Das ist kein rein kosmetischer Zustand.** `depends_on: condition: service_healthy` wertet den Status aus, ebenso jedes Monitoring und jedes Deploy-Script, das auf Health wartet — ein Rollout kann dadurch fälschlich als gescheitert gelten und zurückgerollt werden, obwohl der Start normal verläuft.
- **Neue Werte: `dev` 90 s, `prod` 60 s.** Fehlschläge innerhalb der `start-period` lassen den Status auf `starting` stehen, statt auf `unhealthy` zu springen; ein erfolgreicher Check macht den Container weiterhin sofort `healthy`. Die Zeit bis `healthy` verlängert sich dadurch nicht. `interval`, `timeout` und `retries` bleiben unverändert, ein wirklich kaputter Container wird also weiterhin genauso schnell als `unhealthy` erkannt.

### Changed (Fundament fuer „Richtung B · Dossier“ — dunkel-warmes Theme — 2026-08-18)

- **`tokens-v3.css` bleibt namentlich unveraendert, traegt jetzt aber die dunkel-warme Palette aus dem Grilling vom 18.08.2026.** Grund `#0b0a09`, Flaeche `#14110f`, Flaeche erhoeht `#1b1815`, Akzent/Fokusring `#d08a52`, Live/System `#5fb6c9`, belegt/Erfolg `#7fa86a`, Warnung `#d09a3c`. Alle abgeleiteten Tokens (`--surface-inset/-hover/-pressed`, `--hairline*`, `--separator`, `--text-tertiary/-quaternary`, `--accent-hover/-pressed`, `--accent-tint-*`, `--status-*`, `--gray-1..6`) folgen konsistent aus diesen Ankern — keine Fremdfarben.
- **`--text-secondary` bleibt bewusst bei `#7c736a`, dem Vorlagenwert.** Der Wert unterschreitet die eigene Systemregel „Sekundaertext ≥ 4,6:1“ auf allen drei Flaechen (4,26:1 / 4,04:1 / 3,80:1 gegen Grund/Flaeche/Flaeche-erhoeht) — Farbtreue zur Vorlage wurde der Kontrastschwelle am 18.08.2026 ausdruecklich vorgezogen. Ein aufgehellter Kandidat (`#867c72`) haette die Schwelle knapp gehalten, wurde aber nicht uebernommen. Dokumentiert direkt über der Token-Zeile in `tokens-v3.css`.
- **Archivo (UI, 400/500/600) und Newsreader (Berichts-Fliesstext, 400/500 + italic 400) kommen per Google-Fonts-CDN dazu** (`frontend/index.html`: preconnect + Stylesheet-Link), Geist Sans/Mono bleiben lokal fuer `--font-mono`. Neues Token `--font-serif` (einzige Neuanlage in diesem Slice). `fonts.css` behauptete bisher faelschlich, es gebe keinen externen Font-Request mehr — der Kommentarkopf ist korrigiert.
- **`states.css` und `global.css` nachgezogen:** harte `rgba(0,102,204,…)`-Reste (Fokusring) und ein reines Weiss-Glas-System (`--bg-glass-hi`, `.btn--glass`-Rand) folgen jetzt der neuen Kupfer-/Warmton-Palette statt der alten Apple-Enterprise-Werte.
- **Kein Umbenennen, keine `.vue`-Aenderung.** Betroffen: `tokens-v3.css`, `fonts.css`, `states.css`, `global.css`, `index.html`.

### Changed (Block B1 — Fundament: Dark-Block, self-hosted Fonts, Token-Entkernung — 2026-08-18)

- **Echter `[data-theme="dark"]`-Block statt umgefaerbtem Light-Selektor.** Slice D0 hatte die dunkle Palette unter `:root, [data-theme="light"]` abgelegt — die Werte waren dunkel, der Selektor behauptete das Gegenteil. Alle drei Token-Bloecke in `tokens-v3.css` tragen jetzt `:root, [data-theme="dark"]`; `index.html` und `main.ts` setzen `data-theme="dark"` vor dem ersten Paint. Damit greift die Dark-Readiness-Klausel aus `designTokens.spec.ts` erstmals wirklich, statt trivial erfuellt zu sein. Ihr Regex fand allerdings nur den ersten Dark-Block und wurde auf alle erweitert.
- **Light-Geruest bleibt leer stehen.** Ein kommentierter, absichtlich leerer `[data-theme="light"]`-Block am Dateiende markiert die Tuer zurueck. Eine zweite Palette ueber alle Komponenten zu pflegen war der Preis, den die Umstellung nicht wert ist — `[data-theme="light"]` faellt bis auf Weiteres auf die `:root`-Werte zurueck.
- **Fonts self-hosted statt Google-Fonts-CDN.** `@fontsource-variable/archivo` und `@fontsource-variable/newsreader` (inkl. `wght-italic` fuer die kursiven Zitate im Bericht) werden in `main.ts` importiert; preconnect und Stylesheet-Link sind aus `index.html` entfernt. Agora laeuft ueber Tailscale — ein Request an `fonts.googleapis.com` ist dort sowohl ein Datenschutz- als auch ein Verfuegbarkeitsproblem. `GeistSans-Variable.woff2` entfaellt (Archivo ersetzt es), Geist Mono bleibt lokal.
- **Zwei Fontnamen, die nie gegriffen haetten, korrigiert.** `--font-sans: "Archivo"` traf ins Leere, weil `@fontsource-variable` die Familie als `Archivo Variable` registriert — der Stack waere still auf `-apple-system` zurueckgefallen. Ebenso zeigte `--ff-serif` auf `var(--font-sans)` mit dem Kommentar „v4 hat keine Serif“, womit Newsreader trotz Einbindung nirgends angekommen waere.
- **Schatten auf Dark umgestellt.** Alle sechs Shadow-Tokens trugen noch Light-Alphawerte (0.02–0.12) und waren auf `--surface-canvas` (`#0b0a09`) faktisch unsichtbar. Jetzt 0.26–0.52; `--shadow-inset` ist ein heller Innenrand statt eines schwarzen, weil auf dunklem Grund Licht die Kante hebt, nicht Schatten.
- **Hartkodierte Farben in den Bestandskomponenten durch Tokens ersetzt.** Betroffen sind `components/v4/forms/*`, `views/Settings/*`, `components/v4/sim-feed/*`, `components/compare/*`, `components/ui/*`, `components/v4/data/*`, `components/v4/steps/*`, `components/step2..4/*`, `components/v4/dashboard/*`, `components/v4/run-budget/*` sowie einzelne Wurzelkomponenten. Ausgenommen bleiben Dateien, die mit dem Dossier-Umbau ohnehin entfallen (`RunsDashboard.vue`, `RunDetailView.vue`) oder neu entstehen (`components/v4/shell/*`, `components/report/*`, `components/graph/GraphDiffPanel.vue`) — sie zweimal anzufassen waere doppelte Arbeit.
- **Bewusst hart geblieben:** Plattform-Identitaetsfarben im Simulations-Feed (Reddit/Twitter), algorithmisch erzeugte Persona-Avatarfarben, und `#fff` auf farbigen Kreisen.

### Changed (Claim-Extraktion aus `build_report_v3` herausgelöst — 2026-09-08)

- **`ReportManager.build_report_v3` war mit cc=69 der höchste Komplexitäts-Hotspot des Projekts.** Die dichteste Verzweigung darin war die Claim-Extraktion eines Abschnitts: Evidence-Filter auf `supports_claim is True`, Mindestlänge des Statements, Confidence-Label-Ableitung, Single-Source-Abstufung und der `strict`-Drop. Sie liegt jetzt als freie Modul-Funktion `_extract_claims_for_section` vor und hängt nur an ihren Argumenten sowie den Modul-Helfern `derive_aggregation_basis`, `_derive_confidence_scope` und `_text_confidence_for` — kein Instanz-Zustand, keine ID-Zähler-Kopplung zu Hypothesen oder Datenlücken.
- **`build_report_v3` fällt von cc=69 auf cc=47**, die extrahierte Funktion liegt bei cc=23. Die Komplexität ist damit nicht verschwunden, sondern umgezogen — an einen Ort, wo sie isoliert prüfbar ist und weiter zerlegt werden kann. Beide Werte stehen als gemessene Obergrenzen in `radon-allowlist.txt`, der neue Eintrag trägt den nächsten Schnitt als Notiz.
- **Kein Verhaltenswechsel.** Der Zähler läuft weiterhin über die *akzeptierten* Claims, sodass die exportierte ID (`C<n>_<i>`) die finale Liste beschreibt und nicht die Rohextraktion (Issue #1341).

### Removed (Drei unerreichbare Zweige der Confidence-Label-Ableitung — 2026-09-08)

- **In der Label-Ableitung standen drei `elif`-Zweige, die nie feuern konnten.** `if label in _valid_confidence` fängt `speculative`, `low`, `medium`, `high` und `verified` bereits vollständig ab; die nachfolgenden `elif label in {"high", "verified"}`, `elif label == "medium"` und `elif label == "low"` prüften ausschließlich Labels aus genau dieser Menge. Aufgefallen ist das erst, als der Block als eigene Funktion isoliert lesbar wurde — inline in `build_report_v3` stand er zwischen 200 Zeilen anderer Verzweigung.
- **Kein Verhaltenswechsel, belegt statt behauptet:** die 16 neuen Tests in `tests/services/report_agent/test_extract_claims_confidence_mapping.py` laufen gegen den Stand *mit* den toten Zweigen identisch grün. Sie decken jedes bekannte Label, unbekannte Labels samt Casing-Varianten, fehlendes Label, die Single-Source-Abstufung, den `strict`-Drop und die ID-Vergabe über akzeptierte Claims ab.
- **`_extract_claims_for_section` fällt dadurch von cc=23 auf cc=20** und damit unter die D-Schwelle des Komplexitäts-Gates. Ihr Allowlist-Eintrag ist ersatzlos entfallen — steigt sie künftig wieder auf D, schlägt das Gate an.

### Fixed (Erschöpfte Provider-Quota legt nicht mehr das ganze Backend lahm — 2026-08-12)

- **Ein 429 des Embedding-Providers hat Agora in einen Crash-Loop geschickt und das komplette Dashboard mit 502 beantwortet:** `create_app()` validiert die Embedding-Konfiguration beim Start und behandelte dabei *jeden* `EmbeddingError` als fatal (`app/__init__.py`). Als Googles Spend Cap erreicht war und `generativelanguage.googleapis.com/v1beta/openai/embeddings` dauerhaft `429 RESOURCE_EXHAUSTED` antwortete, brach der Start ab, `restart: unless-stopped` startete neu, und das im Takt von rund 13 Sekunden — 162 Restarts am Stück. Der nginx-Sidecar fand kein Upstream und lieferte `502` auf `/api/runs` und `/api/status`, also auf *alle* Routen, obwohl nur die Embedding-Funktion betroffen war. Ein externes Zahlungslimit war damit ein Single Point of Failure für die gesamte Anwendung.
- **Der Fix trennt Provider-Ausfall von Fehlkonfiguration entlang der Frage „hilft ein Neustart?“.** Neu ist `EmbeddingBackendUnavailableError` als Unterklasse von `EmbeddingError` (`app/storage/embedding_service.py`). Sie wird geworfen, wenn die Retries erschöpft sind — Quota (429), Serverfehler (5xx), Verbindungsfehler oder Timeout. `create_app()` fängt sie getrennt ab, setzt `app.config['EMBEDDING_DEGRADED'] = True`, loggt laut auf ERROR und läuft weiter. Semantische Suche und Graph-Embeddings schlagen dann zur Laufzeit fehl, bis der Provider zurück ist; der Rest der Anwendung bleibt bedienbar.
- **`gemini-embedding-001` ist mit 3072 Dimensionen eingetragen, nicht mehr mit 768.** `KNOWN_EMBEDDING_DIMS` führte den Matryoshka-Kürzungswert statt der Default-Ausgabe. Das Modell antwortet per Default mit 3072 und lässt sich nur über `output_dimensionality` kürzen — einen Parameter, den der OpenAI-Compat-Pfad in `EmbeddingService` gar nicht sendet. Mit dem alten Wert legte Agora den Neo4j-Vektorindex auf 768 an, und der erste echte Embed-Call scheiterte am Dimension-Mismatch. Regressionstests pinnen jetzt sowohl die Inferenz (`infer_vector_dim_for_model`) als auch den Validierungspfad (`validate_embedding_configuration`).
- **Echte Fehlkonfiguration bleibt unverändert fatal.** 401/403 (falscher oder fehlender Key), 404 (`model not found, try pulling it first`) und Dimension-Mismatch gegen `KNOWN_EMBEDDING_DIMS` scheitern weiter sofort und hart. Das ist Absicht: ein 404 auf das Embedding-Modell ist ein Konfigurationsfehler, der laut sterben soll, statt Agora dauerhaft ohne Vektoren laufen zu lassen. Zuvor wurden 429 und 5xx zusätzlich unterschiedlich behandelt — 5xx wurde retried, 429 brach sofort ab; beide gelten jetzt einheitlich als transient.

### Changed (ADR-0002-Downgrade-Regeln liegen wieder beieinander — 2026-09-08)

- **Die `medium`-Regel der ADR-0002-Stufe `agent_grounded` lag inline in `ReportAgent._finalize_section_claims`, ihre Schwesterregel für `high`/`verified` dagegen als freie Funktion in `report_agent/evidence.py`.** Beide setzen dieselbe Semantik an unterschiedlichen Labels durch, und der Code benannte den Zusammenhang bereits im Kommentar („Schwesterregel für high/verified: `auto_downgrade_unsupported_high_claims`") — ohne dass er sich in der Struktur wiederfand. Die medium-Regel ist jetzt `downgrade_medium_without_agent_grounded` und steht direkt neben `auto_downgrade_unsupported_high_claims`.
- **Kein Verhaltenswechsel.** Der Claim wird weiterhin in place abgestuft, die Audit-Trail-Entscheidung für `gate_decisions` ist unverändert (`violation`, `action`, auf 500 Zeichen gekürztes `detail`); `section_index` ergänzt weiterhin der Caller. `_finalize_section_claims` bleibt als Methode bestehen und delegiert — zehn Testdateien rufen sie als Methode auf, teils an einer per `__new__` gebauten Instanz ohne `__init__`.
- **Die Regel ist jetzt direkt testbar.** Acht neue Tests in `tests/services/test_downgrade_medium_agent_grounded.py` decken Fälle ab, die über den Agent-Pfad nur umständlich zu stellen waren: Label-Casing, fehlende `claim_id`, evidenzloser medium-Claim, optionaler Logger, `detail`-Länge. Die Funktion normalisiert das Label selbst, statt sich auf die Vornormalisierung des Callers zu verlassen.
- **Komplexität:** `_finalize_section_claims` fällt von cc=27 auf cc=24, die neue Funktion liegt bei cc=8. Die Allowlist-Obergrenze ist von `cc<=35` auf den gemessenen Ist-Wert `cc<=24` abgesenkt.

### Changed (Datenverzeichnis-Auflösung der JSON-Stores lebt an einer Stelle statt an sieben — 2026-08-17)

- **Sieben dateibasierte Stores trugen je eine eigene, zeichengleiche Kopie derselben Auflösung:** `api_keys_persistence`, `embedding_configuration_store`, `llm_provider_secrets_store`, `onboarding_state_store`, `provider_connection_store`, `user_profile_store` und `workspace_routing_store` definierten alle ein privates `_resolve_data_dir()` mit identischem Rumpf — `AGORA_DATA_DIR` per `expanduser().resolve()`, sonst `Path(__file__).resolve().parents[2] / "data"` — plus eine eigene `_DATA_DIR_ENV`-Konstante mit demselben Wert. Eine Änderung am Pfadverhalten, etwa eine zweite Env-Variable oder ein anderer Fallback, hätte an sieben Stellen nachgezogen werden müssen; ein Nachzug an sechs davon wäre nicht aufgefallen.
- **Neu ist `app/services/data_dir.py` mit `resolve_data_dir()`.** Das Modul liegt in derselben Verzeichnistiefe wie die bisherigen Kopien, `parents[2]` zeigt also unverändert auf `backend/`. Die Auflösung bleibt bewusst **pro Aufruf** statt zur Importzeit: `tests/conftest.py` setzt `AGORA_DATA_DIR` je Test auf ein `tmp_path`, was bei einem eingefrorenen Wert wirkungslos wäre. Die Stores importieren die Funktion unter ihrem bisherigen lokalen Namen (`as _resolve_data_dir`), sodass sämtliche Aufrufstellen unverändert bleiben.
- **Verhaltensgleichheit ist gemessen, nicht angenommen:** alle sieben Stores liefern ohne Env denselben Pfad wie zuvor (`backend/data`), mit gesetzter Env denselben aufgelösten Pfad, und die Variable wirkt weiterhin pro Aufruf. Kein Test patchte `_resolve_data_dir` direkt; die Isolation läuft durchgängig über `monkeypatch.setenv("AGORA_DATA_DIR", ...)` und funktioniert unverändert.
- **`app/services/api_keys_store.py` ist bewusst nicht einbezogen.** Es führt ein gleichnamiges `_resolve_data_dir`, das aber `Optional[Path]` zurückgibt und eine andere Semantik hat — es ist keine Kopie, sondern eine andere Funktion.
- **`tests/services/test_data_dir.py` hält den Zustand:** neben Env-Override, Expansion, Leerstring-Fallback und Pro-Aufruf-Auswertung prüft es je Store, dass dessen `_resolve_data_dir` *dasselbe Funktionsobjekt* ist wie das gemeinsame — ein erneut lokal definierter Resolver lässt die Suite fallen.

Neuer LLM-Provider `claude_cli`: spricht die lokal installierte Claude-Code-CLI
per Subprozess an (Claude-Abo statt Pay-per-Token-API), analog zum
bestehenden `codex_cli`-Provider (ChatGPT-Abo).

Anders als `codex_cli` authentifiziert `claude_cli` über einen mit
`claude setup-token` erzeugten Langzeit-Token (Env-Var
`CLAUDE_CODE_OAUTH_TOKEN`, offiziell für CI/Headless-Nutzung dokumentiert)
statt einer gemounteten Login-Session — der Token liegt wie jeder andere
API-Key im bestehenden Fernet-Secret-Store, es ist kein
Verzeichnis-Mount/Compose-Override nötig.

Jeder Aufruf läuft mit isoliertem `HOME` und `cwd`: ohne diese Isolation lädt
die CLI das komplette interaktive Setup des Hosts (CLAUDE.md, Skills,
Plugins) in den Prompt-Cache — gemessen ~64x höhere Kosten für denselben
Prompt (189.466 vs. 2.935 `cache_creation_input_tokens`). `--tools ""` nimmt
der CLI zusätzlich jeden Werkzeugzugriff; Function-Calling für OASIS-Agenten
läuft wie bei `codex_cli` über eine Prompt-basierte `<tool_call>`-Übersetzung.

Der `claude`-Binary wird im Docker-Image über den offiziellen Installer
(`curl https://claude.ai/install.sh`, Version gepinnt) installiert — der
Installer verifiziert die Downloads intern gegen ein von Anthropic
signiertes Checksummen-Manifest.

Neu: `backend/app/llm/providers/claude_cli.py`,
`backend/scripts/sim_runtime/claude_cli_model.py` (OASIS-Subprozess-Backend).
Geändert: Provider-Registry, Provider-Connections-Adapter, `LLMClient`-Routing,
`Dockerfile`, sowie alle Stellen, die bisher `codex_cli` als einzigen
`transport="cli"`-Provider hartkodiert hatten
(`llm_routing_seed`, `prepare_llm`, `simulation_config_generator`,
`oasis_profile_generator`, `tool_calls`).

### Added (Drei Lücken im statischen Security-Scan geschlossen — 2026-09-18)

- **CodeQL analysiert jetzt auch die GitHub-Actions-Workflows** (Sprache `actions` in `.github/workflows/codeql.yml`). `actionlint` prüft nur Syntax und Ausdrücke; Injection über untrusted Event-Felder in `run:`-Blöcken findet erst die CodeQL-Datenflussanalyse.
- **Ruff prüft das Backend mit den flake8-bandit-Regeln (`S`).** Bewusst ausgeblendet bleiben `S311` (Simulation und Persona-Sampling nutzen `random` nicht-kryptografisch), `S603`/`S607` (Subprozesse mit Argumentlisten ohne Shell) sowie `S101`/`S110`/`S112` als Baseline-Altlast. `tests/*` ist von `S` ausgenommen. Die übrigen Funde in `app/` waren Fehlalarme (Env-Variablen- und Attributnamen, Loopback-Hostlisten, Prompt-Text) und tragen jetzt eine begründete `noqa`-Markierung; `network_analytics.py` kennzeichnet den SHA1 für die Snapshot-ID mit `usedforsecurity=False`.
- **Trivy scannt zusätzlich Dockerfile und Compose-Dateien** (`scan-type: config`, Code-Scanning-Kategorie `trivy-config`). Der Schritt blockiert vorerst nicht (`exit-code: "0"`), bis die erste Fundliste gesichtet ist.

### Changed (ReportV3-Vorab-Build ist eine eigene, prüfbare Funktion — 2026-09-08)

- **Der Vorab-Build von ReportV3 (Issue #1299) lag inline in `generate_report` und war nur über einen vollständigen Report-Lauf mit rund einem Dutzend Mocks erreichbar.** Er heißt jetzt `_build_and_validate_report_v3` und liegt als Modul-Funktion in derselben Datei — bewusst nicht in einem neuen Modul, weil 32 Patch-Stellen der Testsuite auf `workflow.ReportManager` als Modul-Global zeigen und ein Umzug sie ins Leere laufen ließe.
- **Kein Verhaltenswechsel.** Der Report wird weiterhin in place mutiert (`status`, `error`, `run_degradations`), der Guard bleibt `COMPLETED` **und** vorhandene Evidence-Map, ein bestehender `error`-Text wird weiterhin nicht überschrieben, `run_degradations` ergänzt statt ersetzt, und nur `ValidationError` wird gefangen — alles andere gehört weiter dem äußeren Handler in `generate_report`.
- **Neun Direkttests** in `tests/services/report_agent/test_build_and_validate_report_v3.py` prüfen genau diese Zusagen. Gegenprobe mit entferntem Guard: vier Tests fallen. Beim Schreiben fiel ein Helper-Defekt im Testfile selbst auf — ein Default, der `None` still durch ein truthy dict ersetzte und damit den Falsy-Zweig unprüfbar gemacht hätte.
- **Komplexität:** `generate_report` fällt von cc=54 auf cc=50, die extrahierte Funktion liegt bei cc=5. Die Allowlist-Obergrenze ist von `cc<=55` auf `cc<=50` abgesenkt; die Refactor-Notiz im Kommentarkopf benennt die verbleibenden offenen Schnitte (Init → Status → Budget-Reraise aus #978, sowie den Red-Team-Block mit seinen zwei verschachtelten Exception-Handlern).

### Hinzugefügt

- `bun run bigpowers:sync` legt das Bigpowers-Tooling als relative Symlinks auf
  `node_modules/bigpowers` in `scripts/` und `.claude/skills/` ab und traegt sie
  zugleich in `.git/info/exclude` ein. Die Symlinks sind maschinenlokale
  Build-Artefakte und bleiben damit aus dem Repo heraus, ohne dass jemand sie
  von Hand ausschliessen muss. Vorhandene AGORA-Dateien werden nie
  ueberschrieben — gleichnamige Bigpowers-Dateien meldet das Skript als
  Konflikt und laesst sie liegen. Symlinks, die auf eine inzwischen entfernte
  Bigpowers-Datei zeigen, raeumt das Skript beim Sync weg.

  `--check` verifiziert das Overlay gegen die installierte Abhaengigkeit statt
  gegen den Ist-Zustand des Arbeitsbaums: fehlende, kaputte oder nicht
  ausgeschlossene Symlinks sind Drift, und ein Lauf ohne installiertes
  Bigpowers meldet Drift statt Erfolg. Damit eignet es sich als Gate-Schritt.
  In Git-Worktrees (`.git` ist dort eine Datei, kein Verzeichnis) findet das
  Skript den gemeinsamen Ausschlusspfad ueber `git rev-parse --git-common-dir`.

### Fixed (Provider-Key-Masking akzeptiert Base64-Suffix — 2026-08-12)

- **`MASKED_KEY_PATTERN` nimmt `=`/`+`/`/` auf:** AWS-Bedrock-Bearer-Tokens sind URL-safe-Base64 und enden häufig auf `=`, was das bisherige Pattern `[A-Za-z0-9_\-]{4}` ablehnte — ein Bedrock-Key ließ sich unter „OpenAI Compatible“ gar nicht persistieren (Pydantic `string_pattern_mismatch`). Die End-Klasse deckt jetzt Standard- und URL-safe-Base64.


### Documentation (Zwei neue Referenzläufe, der aktuelle zweisprachig — 2026-08-11)

- **Der Referenzpfad zeigte bisher nur die Domainmigration, in zwei Varianten derselben Domäne:** Damit ließ sich nicht unterscheiden, welche Befunde am Testfall hingen und welche am System. Zwei neue Referenzläufe in einer anderen Domäne sind jetzt dokumentiert — Einführung eines selbstgehosteten KI-Lernassistenten bei einem AZAV-zertifizierten Umschulungsträger.

  Der **dritte Lauf** (10 Runden, `deepseek-v4-flash`, erstmals `gemini-embedding-2` statt lokalem Ollama) hält vier Mechanismen fest, die vorher nicht benannt waren: dass das Seed-Dokument seine eigenen Antworten mitliefert und der Report sie als Simulationsergebnis abruft; dass von 130 Aussagen genau eine an Evidence bindet, und diese nur, weil sie ihre Evidence wörtlich zitiert; dass der Fließtext-Gate ausschließlich Sätze mit einer Zahl prüft und qualitative Behauptungen ungeprüft durchlässt; und dass das Entfernen einer Aussage in zwei von sechs Sections eine Aufzählung ohne ihren Punkt oder einen Rückverweis ohne Bezug hinterlässt.

  Der **vierte Lauf** (20 Runden, `gemini-3.6-flash` als Writer und NER) ist der neue Referenzlauf in der README und liegt auf Deutsch und Englisch vor. Er ist der erste, in dem die Evidence-Bindung arbeitet — 39 validierte Claims gegen null oder einen in fünf Vorgängerreports — und die Poster-Zuordnung mit 8 von 8 strukturell statt zufällig trifft. Gerade dadurch werden die verbleibenden Lücken messbar: Jedes Zitat trägt jetzt einen eigenen Provenance-Anker, und keiner davon existiert; das Modell erfindet sie pro Persona, und der `seed_doc:`-Präfix umgeht die Prüfung vollständig. Alle 39 Claims stehen auf `low` mit identischem Score. Derselbe Fakt bindet in Section 1 als SUPPORTED und wird in Section 2 als ungedeckt entfernt. Und über 20 Runden, 665 Aktionen und 84 Kommentare fällt — bei erstmals sauber getrennten Konfliktparteien — kein einziges Dislike und kein Widerspruch.

### Fixed

- Der Dashboard-Start reicht Rundenzahl und Run-Budget wieder bis zum
  Simulationsstart durch. Beide reisten über den `pendingUpload`-Store, den
  Schritt 1 nach dem Ontologie-Upload leert — Schritt 3 las anschließend den
  Reset-Default 10 statt der eingestellten Runden und fand gar kein Budget
  mehr vor. Sie laufen jetzt über den Query-Vertrag
  `contracts/runParamsQuery.ts`, der schon die Übergabe Schritt 2 → Schritt 3
  trägt, und überleben damit auch einen Reload auf der Simulationsroute
  ([#1234](https://github.com/arn0ld87/agora/issues/1234)).

### Fixed (Ein stützender Beleg bleibt als Low-Claim sichtbar — 2026-08-11)

- **Der generische Zweier-Floor entfernte gültige ADR-0002-Claims:** Die Bindungsphase fand nach #1217 passende Belege, routete atomisierte Aussagen mit genau einer stützenden Quelle danach aber weiterhin zur Hypothese. Das Gate verlangt jetzt mindestens einen stützenden Beleg; eine einzelne Quelle wird auf `low` begrenzt, während Aussagen ohne stützende Evidence unverändert Hypothese und Data-Gap werden. Der Replay des betroffenen DeepSeek-Artefakts hebt damit drei belegte Claims von 0 auf 3. (#1233)

### Fixed (Reporttext kennzeichnet unbelegte Aussagen — 2026-08-11)

- **Das Evidence-Gate stufte Aussagen korrekt als Hypothesen ein, der narrative Abschnitt formulierte sie aber weiter als Feststellungen:** Die Section-Assembly markiert dieselben Sätze jetzt direkt im Fließtext als `Hypothese (unbelegt)` und behält die separate Hypothesenliste als Audit-Sicht. Section-Datenlücken werden ebenfalls gerendert; sichtbar sind höchstens fünf, danach nennt der Report die Restzahl und verweist auf den maschinenlesbaren Evidence-Export. (#1232)

### Fixed (Die Bindungsphase sieht wieder alle Belege einer Section — 2026-08-11)

- **Kein einziger Claim wurde an Evidence gebunden, obwohl der Beleg wörtlich im Index stand:** Die Bindungsphase reichte dem Binder pro Claim nur die zehn *zuerst erhobenen* Evidence-Items einer Section (`_active_section_evidence[:10]`) plus die ersten sechs globalen Referenzen. Diese Reihenfolge ist die Reihenfolge der Tool-Aufrufe, keine Rangfolge nach Relevanz — und ein einziger `insight_forge`-Aufruf erzeugt bis zu 26 Items. Das Fenster war damit nach dem ersten Tool-Aufruf gefüllt, und was der Agent danach gezielt suchte, war für die Bindung unerreichbar: die Persona-Zitate aus `interview_agents` und die Seed-Corpus-Treffer aus `quick_search` landeten im `evidence_index`, wurden dort gezählt und nie einem Claim angeboten. In zwei vollständigen Läufen blieben so 163 bzw. 131 Claims ungebunden, bei 66 bzw. 79 Einträgen im Index. Die Auswahl bewertet die Kandidaten jetzt erst und kürzt danach: alle Belege einer Section werden gegen den Claim-Text gemessen, und nur die semantisch nächsten gehen weiter. Das Evidence-Gate selbst bleibt unverändert — Schwellenwert, Entailment-Urteil und der Reviewer-Floor von zwei stützenden Quellen entscheiden weiterhin allein darüber, ob eine Aussage ein Claim wird. Ein Claim, der jetzt gebunden wird, hat es unter denselben Regeln verdient wie vorher; er bekommt sie nur erstmals angewandt.
- **Nebeneffekt: die Nachbearbeitung wird schneller statt langsamer.** Die Vektoren hängen jetzt am Text und nicht mehr am Claim. Vorher bettete jeder Claim jeden Kandidaten neu ein — bei 30 Claims und 16 Kandidaten 480 Aufrufe pro Section. Jetzt fällt pro Section einmal die Kandidatenmenge an, plus einen Aufruf je Claim.


## [0.9.5] - 2026-08-11

Das Zusammensetzen eines Provider-Requests und das Durchbringen dieses Requests gegen bekannte Provider-400er liegen nicht mehr in `LLMClient.chat`, sondern hinter `build_request` und `execute` im neuen Modul `app/llm/request_plan.py`. `chat` schrumpft von 315 auf 257 Zeilen und behält nur noch, was wirklich dazugehört: Stub-Pfad, Streaming-Reassembly, Budget- und Telemetrie-Buchführung.

Die Quirks stehen damit genau einmal im Code. Bisher standen sie viermal: `chat`, `describe_image` und `tool_calls` hatten je eine eigene Kopie des Request-Shapings, drei davon je eine eigene Fallback-Kaskade. Jede Kopie hatte eine andere Lücke — der Tools-Pfad kennt den `temperature`-Quirk aus #1096 nicht, der Vision-Pfad kennt MiniMax nicht. Diese Lücken bleiben unverändert bestehen, stehen jetzt aber als benannter Seam sichtbar da statt als stiller Unterschied zwischen drei Textstellen.

Was ein Request über seine Umgebung braucht, kommt über `RequestOptions` herein — Provider-Seams mit Default-Bindung an die echten Heuristiken. Ein Test setzt Fakes in die Options und prüft `build_request` und `execute` direkt am Interface, ohne `patch()` auf Modulnamen.

`detect_provider` bleibt Single Source of Truth für die Provider-Erkennung; `request_plan` erkennt nichts selbst, sondern bekommt das Ergebnis übergeben.

Verhalten unverändert — reiner Deepening-Refactor.

### Fixed (Sim Tool-Skip für DISLIKE — 2026-08-11)

- **DISLIKE_* ohne erzwungenen Tool-Aufruf:** Die Tool-Usage-Rule erlaubte den Tool-Skip nur für `LIKE_POST`/`DO_NOTHING` und zwang für `DISLIKE_POST`/`DISLIKE_COMMENT` einen `web_search`/`web_fetch`-Aufruf, der bei Tool-Limit oder Tool-Fehler auf `DO_NOTHING` zurückfiel — Reddit-Agenten dislike-ten nie (B2 aus #1215). Die Skip-Klausel nennt jetzt die volle Reaktionsmenge (`LIKE_POST`, `DISLIKE_POST`, `DISLIKE_COMMENT`, `LIKE_COMMENT`, `FOLLOW`, `MUTE`, `REPOST`, `QUOTE_POST`, `DO_NOTHING`) und fordert Tools nur, wenn Fakten fehlen, die das Modell nicht schon aus der Observation hat. (#1215)

### Fixed (Persona-Slot-Verteilung und gender-konsistenter Dedup — 2026-08-11)

- **Persona-Generierung verteilt Alter, Gender und MBTI jetzt vorab auf Slots:** Gleichförmige LLM-Antworten werden auf eine geplante Kohorte normalisiert, und der Namens-Dedup zieht gender-konsistente Ersatznamen, ohne die bestehende Namens- und Nachnamens-Eindeutigkeit zu verlieren. (#1214)

### Fixed (CI-Komplexitäts-Gate — 2026-08-11)

- **`contract-gates` auf `main` wieder grün:** Fünf pre-existing D-Hotspots aus der kanonischen Evidence-Identität (#1147) und der seed_corpus-Evidence (#1166) fehlten in `backend/radon-allowlist.txt` und hielten das radon-Komplexitäts-Gate seit mindestens acht `push:main`-Läufen rot. Nachgezogen als Allowlist-Einträge mit `# cc<=N`-Obergrenze — sie dulden den Bestand und schlagen bei weiterem Wachstum an, ohne einen Refactor zu erzwingen. (#1213)

### Added

- **Komplexitäts-Gate im Pre-Push-Gate:** `scripts/pre-push-gate.sh` ruft im Backend-Scope jetzt `scripts/check_complexity.py` auf. Der Driftfall fällt damit lokal vor dem Push auf statt Tage später nur auf `push:main`. (#1213)

Der Abschnitts-Durchlauf der Reportgenerierung liegt nicht mehr als Schleife in `generate_report`, sondern hinter `process_section` im neuen Modul `app/services/report_agent/section_pipeline.py`. `generate_report` schrumpft von 455 auf 322 Zeilen und behält nur noch die Orchestrierung: Abbruchprüfung, Akkumulation der fertigen Abschnitte und Statusableitung.

Was ein Abschnitt beim Verarbeiten braucht, kommt über `SectionContext` herein — Daten und Seams, mit Default-Bindung an die echten Implementierungen. Das Ergebnis steht in `SectionResult` und trägt beobachtbar, was gebunden und was vom Evidence-Gate verworfen wurde. `ReportAgent._save_evidence_section` gibt dieses Ergebnis dafür zurück, statt es nur als Seiteneffekt in der Evidenzkarte abzulegen; die Persistenz bleibt unverändert.

Verhalten unverändert — reiner Deepening-Refactor.

- Live-Feed: Reddit-Kommentare erreichen den Feed wieder. Der Emitter erwartete den
  Elternpost in der OASIS-Trace-Zeile, die ihn nie enthält — er wird jetzt über die
  `comment`-Tabelle aufgelöst. Damit bekommt der Reply-Tree Äste und die rund 86 %
  der Reddit-Aktivität, die Kommentare sind, werden sichtbar (#1209 5c/5d).
- Live-Feed: `score` trägt den echten Voting-Stand aus der Simulations-DB
  (`num_likes - num_dislikes`) statt einer hartkodierten 0; Twitter bleibt bei 0,
  weil es kein Up-/Down-Voting kennt (#1209 5b).
- `PostCreatedEvent`: Feld `sentiment` entfernt. Es gab nie einen Sentiment-Service,
  das Feld trug nie einen Wert und wurde nirgends gerendert (#1209 5b).

### Geändert

- Report-Statusmaschine aus `Step4Report.vue` in das Composable
  `useReportGeneration` gezogen (#1206). Neun offene Status-Refs, die
  141-zeilige `pollStatus()`-Schleife samt Endzustands-Zweigen, die
  Transportfehler-Zählung aus #1023 und die Koordination der drei
  Polling-Instanzen liegen jetzt hinter dem Interface
  `{ status, progress, report, bootstrap(), start(), stop(), regenerate() }`;
  `usePolling` ist damit interne Abhängigkeit statt Detail der Komponente.
  Frontend-Gegenstück zu `RunLifecycle` (#1204). Verhalten unverändert — der
  Flow ist jetzt zusätzlich ohne `mount()` und ohne Modul-Mocks testbar.

### Geändert

- Run-Zustandsführung zentralisiert: das handgeschriebene Muster „Run anlegen
  (pending) → Arbeit → Endzustand" an sechs Stellen (Simulationsstart und
  -vorbereitung, Run-Restarts, Report-Start) läuft jetzt über den
  Kontextmanager `RunLifecycle` (#1204). Kein Abbruchpfad — auch
  `SystemExit`-artige — hinterlässt mehr einen pending-Phantom-Run; ein nicht
  persistierter Statusübergang wird als Fehler sichtbar (500) statt still
  verschluckt.

### Changed (Betriebs- und Security-Doku gegen den Code geprüft, Coverage neu gemessen — 2026-08-11)

- **Die Doku beschrieb an mehreren Stellen einen Paketmanager, den das Projekt nicht mehr benutzt.** `deployment-dev.md` führte `npm run dev`, `npm run setup:all`, `npm run check`, eine `package-lock.json` und Node 18 als Voraussetzung — real fährt das Projekt seit langem `bun` (je eine `bun.lock` in Root und `frontend/`), verlangt `bun >= 1.3.0` und Node >= 20, und das Backend ist auf Python `>=3.14,<3.15` gepinnt, nicht auf 3.11. Auch die CI-Kommandos in `security-hardening.md`, `security-threat-model.md`, `operations.md`, `release-process.md` und `dependency-risk-register.md` nannten `npm audit`, während der Job `Security scans` `bun audit --audit-level=high` ausführt.
- **`release-process.md` beschrieb einen Versionsprozess, den es nicht mehr gibt.** Das Dokument führte „sechs Stellen halten die Versionsnummer", nannte zwei davon als bekannten Drift auf `0.6.1` und `0.8.0`, und gab eine `sed`-Sequenz vor, die unter anderem `backend/app/__init__.py` beschreibt — dort steht seit dem Umbau kein statischer Wert mehr, der Wert kommt aus den Paket-Metadaten. Maßgeblich ist `VERSION` plus `check_version_drift.py --write`; das Dokument verweist dafür jetzt auf `runbooks/release-versioning.md` und beschreibt nur noch, was nach dem Version-Cut passiert.
- **`auth.md` kannte nur einen von drei Auth-Wegen.** Ergänzt sind die Workspace-API-Keys (Präfix `ago_`, Status-Prüfung gegen den Key-Store) und der Open Mode, in dem ohne gesetztes `AGORA_AUTH_TOKEN` jeder Aufruf durchgeht. Korrigiert ist außerdem die Aussage zu `?token=`: der Query-Parameter ist außerhalb des Debug-Modus **abgeschaltet** — der Wert wird verworfen und auf Log-Level `error` protokolliert —, nicht bloß „deprecated mit Warning". Die Ticket-TTL ist Default 60 s bei Maximum 300 s.
- **`deployment-dev.md` behauptete ein Read-Only-Rootfs, das im Dev-Stack nicht gilt.** `docker-compose.yml` setzt `read_only: false`; erst `docker-compose.prod.yml` schaltet es scharf. Wer eine Änderung gegen den Prod-Pfad absichern will, muss deshalb gegen das Prod-Compose testen. Ergänzt sind außerdem `AGORA_BIND_HOST`, `AGORA_FRONTEND_PORT` und `AGORA_BACKEND_PORT`, die die Host-Bindung des Stacks steuern und in keiner Doku standen — auch nicht in der Env-Referenz.
- **Coverage-Baseline neu erzeugt statt weiter als „überholt" markiert:** Backend 79,00 % (vorher 66,00 % vom 10.06.), Frontend 71,03 / 58,44 / 64,19 / 73,32 % für Statements / Branches / Functions / Lines (vorher 50,46 / 39,56 / 38,59 / 52,50 % vom 10.05.). **Damit sind die CI-Schwellen wirkungslos:** 28 % im Frontend liegen 30 bis 45 Punkte unter dem Istwert, 60 % im Backend 19 Punkte darunter. Das Anheben ist eine Code-Änderung und bleibt einem eigenen Issue vorbehalten.
- **Neun tote Verweise entfernt**, darunter zwei gelöschte Planungsdateien, ein nicht mehr existierendes `SECURITY_REVIEW_SUMMARY.md` und zwei Frontend-Dateien, die seit der TypeScript-Migration `index.ts` und `markdown.ts` heißen.
- **Der Prüfumfang steht in den Dokumenten selbst.** Die acht Betriebs- und Security-Dateien tragen jetzt einen Vermerk, dass Pfade, Kommandos und Verweise am 11.08.2026 gegen den Code geprüft wurden — und dass die fachlichen Aussagen dabei **nicht** einzeln nachvollzogen worden sind. Ein „Stand"-Datum ohne diese Einschränkung hätte mehr Prüftiefe behauptet, als stattgefunden hat.

### Fixed (Schaltflächen der Embedding-Konfiguration waren unsichtbar oder unformatiert — 2026-08-11)

- **Die Schaltflächen im Seitenkopf wurden nie angezeigt.** `PageHeader` rendert ausschließlich den benannten Slot `right`; die Ansicht übergab ihre Schaltflächen jedoch im Standard-Slot, dessen Inhalt die Komponente verwirft. Betroffen waren „Neue Konfiguration" und das ältere „Ollama-Modell herunterladen" — letzteres war seit seiner Einführung unsichtbar, ohne dass es auffiel.
- **Die übrigen Schaltflächen trugen Klassennamen, die es nicht gibt.** Die Ansicht verwendete `btn-primary` und `btn-secondary`; das Gestaltungssystem definiert `btn--primary` und `btn--secondary` mit doppeltem Bindestrich. Alle zwanzig Vorkommen waren betroffen, weshalb etwa „Uebernehmen" als unformatierter Text erschien.
- **Der Test deckte das nicht ab, weil der Prüfaufbau großzügiger war als das Original.** Der Platzhalter für `PageHeader` rendert im Test jetzt nur den Slot `right` — übergibt eine Ansicht ihre Schaltflächen künftig am falschen Slot, wird der Test rot statt grün.

### Changed (Dokumentations-Sync auf den Stand nach `0.9.4` — 2026-08-11)

- **Die Doku behauptete an mehreren Stellen offene Arbeit, die längst erledigt war.** README (beide Sprachen) führte den fehlenden Dokumentanker für Seed-Korpus-Belege als offenen Punkt, obwohl #1154 seit dem 09.08. geschlossen ist; `docs/STATUS.md` nannte als erste Priorität das harte Run-Budget (#978, geschlossen am 31.07.) und die nicht normalisierenden Evidence-Sub-Routen (#967, geschlossen); `ROADMAP.md` und `docs/troubleshooting.md` führten den Trivy-OS-Layer-Hardstop 30.08.2026, der mit #772 ersatzlos entfallen ist. Alle vier Stellen nennen jetzt den Istzustand mit Beleg.
- **Ein Überclaim ist entfernt:** die README versprach in beiden Sprachen, Runs könnten „erneut abgespielt" werden. Replay ist nicht implementiert — der stochastische Anteil eines Laufs ist seit #1160 F geseedet und damit wiederholbar, ein Same-Seed-Same-Report verlangt zusätzlich eine Aufzeichnung der Modellantworten und steht offen unter #763. Der Text sagt das jetzt so.
- **Testzähler und Routenzahl neu gemessen** statt fortgeschrieben: `docs/STATUS.md` steht auf 4954 gesammelten Backend-Tests (davon 7 deselektiert) und 188 Frontend-Testdateien; `docs/api.md` auf 171 Routen und Referenzstand `0.9.4` statt `0.8.0` — derselbe veraltete Versionsanker stand auch in `configuration.md` und `troubleshooting.md`.
- **`docs/architecture.md` ist als Zielbild kenntlich gemacht, nicht als Istzustand.** Das Dokument stammt vom 22.04.2026, trug noch den Titel „Agora / MiroFish-Offline" und leitete sich aus zwei Dateien ab, die es im Repository nicht mehr gibt. Der Migrationspfad Phase 0–8 ist inzwischen umgesetzt; jede Phase trägt jetzt eine Belegzeile, und dort, wo der umgesetzte Schnitt anders benannt ist als geplant (`WorkspaceLayout.vue` → `components/v4/shell/`, `SimulationRepository` → `simulation_manager.py` plus Config-Schemas), steht das ausdrücklich dabei. **Was das nicht leistet:** eine Ist-Architektur ist das weiterhin nicht — für den verifizierten Stand bleibt `docs/STATUS.md` zuständig.
- **Zwei tote Verweise entfernt:** `docs/troubleshooting.md` verwies auf ein nie existierendes `docs/testing/`. `OPENAI_API_BASE`/`OPENAI_API_BASE_URL` fehlten in der Env-Referenz und sind jetzt als das dokumentiert, was sie sind — an den OASIS-Subprozess durchgereichte Werte, keine Eingangskonfiguration.

### Added (Embedding-Konfiguration lässt sich in den Einstellungen anlegen und übernehmen — 2026-08-10)

- **Die Einstellungsseite zeigte Embedding-Konfigurationen an, ließ aber keine anlegen.** Wer Agora ohne kanonische Konfiguration betrieb, sah dort den Hinweis „Quelle: Legacy Config.EMBEDDING_* — bitte übernehmen" und darunter „Noch keine Embedding-Konfigurationen vorhanden". Einen Weg, dieser Aufforderung nachzukommen, gab es nicht: Die Übernahme war im Backend seit der Einführung des kanonischen Lifecycles vorbereitet, aber nie mit einer Bedienoberfläche verbunden.
- **Die Legacy-Werte lassen sich jetzt übernehmen.** Der Hinweis trägt einen Schalter, der nach der Provider-Verbindung fragt, über die das Modell erreichbar ist. Modell und Dimension stammen unverändert aus der bestehenden Konfiguration. Die Verbindung wird bewusst abgefragt statt erraten — Verbindungen sind ein eigener Lebenszyklus und werden nie im Hintergrund angelegt. Existiert noch keine, verweist der Dialog auf die Anbieter-Einstellungen.
- **Neue Konfigurationen entstehen über ein Formular** aus Verbindung, Modellname und Dimension. Direkt nach dem Anlegen und nach der Übernahme läuft die Prüfung gegen den Anbieter; ihr Ergebnis steht auf der Karte. Schlägt sie fehl, bleibt die Konfiguration erhalten, statt den Vorgang abzubrechen.
- **Eine falsch angegebene Dimension ist kein Sackgassen-Zustand mehr.** Meldet die Prüfung eine andere Dimension als deklariert, bietet die Karte an, den gemessenen Wert zu übernehmen und erneut zu prüfen. Konfigurationen lassen sich außerdem nach Rückfrage löschen — außer der gerade aktiven, die geschützt bleibt.

### Added (Ein Report sagt jetzt, auf welchem Simulationsstand er beruht — 2026-08-10)

- **Eine Reportgenerierung darf weiterhin starten, während die Simulation noch läuft.** Das bleibt erlaubt und bekommt weder eine Sperre noch eine Warteschlange — bei Einzelnutzung wäre beides mehr Apparat als Nutzen. Fragwürdig war nie der Start, sondern das Schweigen darüber: der Bericht analysierte dann einen Zwischenstand, und wie viele Runden dieser Zwischenstand umfasste, stand nirgends. Einem fertigen Bericht war nicht anzusehen, ob zehn Runden dahinterstehen oder vier.
- **Der Stand steht jetzt im Bericht, gleich im Kopf.** Ausgewiesen werden die abgeschlossenen Runden, die geplante Gesamtzahl und die Feststellung, ob die Simulation zum Startzeitpunkt noch weiterlief. Lief sie weiter, wird der Bericht ausdrücklich als Zwischenstand bezeichnet und vermerkt, dass spätere Runden nicht eingeflossen sind.
- **Erfasst wird beim Start, nicht beim Abschluss.** Das ist der Datenbestand, den die Auswertung tatsächlich gesehen hat. Runden, die während der Berichtserstellung noch dazukommen, stehen in keinem Satz des Berichts — sie hier mitzuzählen wäre die bequemere, aber falsche Zahl.
- **Ist der Stand nicht ermittelbar, steht dort „unbekannt".** Das betrifft Berichte aus der Zeit vor dieser Änderung und Simulationen, die nie über den Runner liefen. Eine erfundene Null wäre schlechter als ein ehrliches Fragezeichen. Bestehende Berichte laden, validieren und exportieren unverändert.

### Fixed (Eine erfolglose Suche wird nicht mehr wiederholt — 2026-08-10)

- **Der Berichtsagent suchte dreimal nach derselben Sache, die es nicht gab.** In einem vermessenen Lauf ging er im Abschnitt „Unsicherheiten und Datenlücken" dreimal einer Stakeholdergruppe nach, die das Personen-Capping zuvor aus dem Pool verdrängt hatte — einmal mit der Panorama-Suche, zweimal mit der Schnellsuche. Er verbrauchte damit fünf statt vier Werkzeugaufrufe und lief in die Iterationsgrenze. Ausgerechnet der Abschnitt, der Datenlücken benennen soll, verlor sein Budget an die Suche nach einer solchen.
- **Ein Leertreffer ist jetzt ein Befund, kein Grund zur Wiederholung.** Bleibt eine Suche ohne Ergebnis, wird dieselbe Suche im selben Abschnitt nicht noch einmal ausgeführt — auch nicht mit einem anderen Werkzeug. Das Modell erhält stattdessen den Hinweis, dass der Gegenstand im Datenbestand nicht vorkommt, und die Aufforderung, das als Datenlücke zu benennen.
- **Der unterdrückte Versuch zählt nicht gegen das Werkzeugbudget.** Täte er es, wäre keine einzige Iteration gespart und die Änderung folgenlos.
- **Als „dieselbe Suche" gilt die normalisierte Anfrage:** Groß- und Kleinschreibung, Leerraum und Satzzeichen bleiben außer Betracht. Keine Ähnlichkeitsschätzung — die Regel ist damit vorhersagbar und prüfbar, statt von einem Schwellenwert abzuhängen. Die Merkliste gilt pro Abschnitt; ein anderer Abschnitt darf dieselbe Suche erneut versuchen.
- **Am Evidenzmodell ändert sich nichts.** Der Hinweis bleibt eine Mitteilung an das Modell und wird kein Eintrag in den Evidenzverträgen — das wäre eine eigene Entscheidung und ist bewusst nicht Teil dieser Änderung. Ergebnislose Interviews sind ebenfalls ausgenommen: dort ist ein zweiter Versuch mit anderem Zuschnitt durchaus sinnvoll.

### Fixed (Evidence-Export bleibt sichtbar — 2026-08-10)

- **Evidence-JSON-Button verschwindet nicht mehr spurlos:** Solange die
  Evidenzkarte eines Reports noch nicht vorliegt, bleibt der Export-Button in
  der Report-Ansicht sichtbar, ist aber deaktiviert (`aria-disabled` plus
  zugängliche Beschreibung). `Step4Report.vue` lädt die Evidenzkarte nach
  Laufende mit exponentiellem Backoff (3 s bis 30 s gedeckelt) über ein
  10-Minuten-Budget nach, statt sie nach wenigen Sekunden dauerhaft leer zu
  belassen — dimensioniert auf die in #1187 gemessene Nachbearbeitungsdauer.
  Ist das Budget ausgeschöpft, zeigt der Tooltip „nicht verfügbar" statt
  weiterhin „wird noch erzeugt" zu behaupten. (#1188)

### Fixed (Die stille Phase der Reportgenerierung meldet Fortschritt — 2026-08-10)

- **Nach jedem fertigen Abschnitt arbeitete die Reportgenerierung minutenlang, ohne das mitzuteilen.** In einem vermessenen Lauf lagen zwischen "Abschnittstext fertig" und "Abschnitt gespeichert" jedes Mal drei bis sechs Minuten ohne eine einzige Logzeile — zusammen 59 % der gesamten Laufzeit. Der Fortschrittsstand blieb derweil auf dem Wert stehen, den er beim letzten Abschnittswechsel hatte, mitsamt einem Zeitstempel, der Minuten alt war. Für den Nutzer war ein arbeitender Lauf damit nicht von einem abgestürzten zu unterscheiden.
- **Diese Phase meldet sich jetzt.** Die Nachbearbeitung ist in benannte Schritte zerlegt — Metadaten-Extraktion, Claim-Extraktion samt Evidenzbindung, Abschluss der Aussagen, Persistenz der Evidenzkarte. Jeder Schritt meldet Beginn und Ende mit seiner Dauer, und der Fortschrittsstand bewegt sich bei jedem Wechsel statt nur beim Abschnittswechsel. Innerhalb der langen Bindungsschleife hält ein Lebenszeichen im Zwanzig-Sekunden-Takt die Anzeige in Bewegung, ohne bei jeder einzelnen Aussage zu schreiben.
- **Eine fehlgeschlagene Fortschrittsmeldung bricht den Lauf nicht ab.** Sie wird protokolliert und die Nachbearbeitung läuft weiter — eine Anzeige darf den Bericht nicht kosten, den sie beschreibt.
- **Was das ausdrücklich nicht leistet: schneller wird dabei nichts.** Die Nachbearbeitung dauert genauso lange wie vorher, sie ist jetzt nur sichtbar und messbar. Die eigentliche Beschleunigung hängt an belastbaren Phasenzeiten aus einem Lauf mit dieser Instrumentierung — ohne die wäre jede Optimierung geraten. Ebenso unverändert bleiben sämtliche Evidenzbindungen und Vertrauenseinstufungen: gemessen wird, nicht eingegriffen.

### Fixed (Persona-Profile verlieren beim Speichern keine Angaben mehr — 2026-08-10)

- **Die Stimmlage einer Persona fehlte in jeder gespeicherten Profildatei.** In 262 Profilen über sechs Simulationsläufe trug kein einziges das Feld — unabhängig davon, ob das Sprachmodell es erzeugt hatte oder die regelbasierte Erzeugung. Drei der betroffenen Läufe stammten vom selben Tag wie dieser Fix; die zugehörige Absicherung im Generator existiert seit Mai. Der Defekt war also aktuell und nicht ein Überbleibsel alter Daten.
- **Ursache war das finale Speichern, nicht die Erzeugung.** Während des Laufs wird die Profildatei fortlaufend korrekt geschrieben. Zum Abschluss speichert die Anwendung sie noch einmal — und baute dabei den Inhalt aus einer von Hand gepflegten Feldliste neu auf, statt das vollständige Profilformat zu verwenden. Jede Angabe, die in dieser Liste fehlte, ging beim Überschreiben verloren: neben der Stimmlage auch die Segmentzuordnung.
- **Behoben ist nicht das einzelne Feld, sondern das Muster.** Dasselbe Problem war schon einmal aufgetreten und damals durch Nachtragen einer einzelnen Angabe behoben worden — die nächste hätte es erneut getroffen. Das Speichern verwendet jetzt das vollständige Profilformat als Grundlage und ergänzt nur noch die Standardwerte, die die Simulationsumgebung zwingend braucht. Ein Test prüft die Vollständigkeit statt einer Aufzählung bekannter Felder: kommt eine Angabe hinzu, wird sie automatisch mitgespeichert.
- Damit ist die Voraussetzung für den Feed-Schnappschuss beim Öffnen einer laufenden Simulation geschaffen — der scheiterte bislang daran, dass die Stimmlage nicht auflösbar war und ein erfundener Wert nicht in Frage kommt.

### Fixed (Personenauswahl verdrängt keine Stakeholdergruppen mehr — 2026-08-10)

- **Die Begrenzung der Personenzahl schnitt die Kandidatenliste bisher stumpf ab.** Wer die Zahl der Simulationsteilnehmer begrenzte, bekam nicht die wichtigsten Kandidaten, sondern schlicht die ersten — die Reihenfolge stammte unverändert aus der Datenbankabfrage, die keine Sortierung vornimmt. Der Kommentar im Code nannte die Sortierung als Voraussetzung; sie existierte nie. In einem gemeldeten Lauf belegte dadurch eine einzige, häufig genannte Gruppe alle 30 Plätze, während kleinere, fachlich wichtige Gruppen wie Betriebsrat und Honorarkraft komplett herausfielen.
- **Jetzt wird zuerst bereinigt, dann verteilt.** Mehrfachnennungen derselben Gruppe — auch in abweichender Schreibweise — zählen als eine und belegen keine Plätze mehr doppelt. Die verbleibenden Plätze werden reihum über die vorkommenden Gruppen vergeben: erst je ein Vertreter pro Gruppe, dann der zweite, und so weiter. Solange Plätze reichen, ist jede Gruppe vertreten.
- **Was das nicht leistet:** *welcher* Vertreter einer Gruppe gewinnt, bleibt willkürlich, solange die Datenbankabfrage nicht sortiert. Eine Auswahl nach Vernetzungsgrad oder Wichtigkeit wäre der nächste Schritt und erfordert eine Änderung am Lesepfad. Der irreführende Kommentar ist entfernt.
- **Die Vorschau zeigt dieselbe Zahl wie der spätere Lauf.** Sie bereinigt jetzt ebenfalls, statt Dubletten mitzuzählen — sonst kündigte sie mehr Personen an, als anschließend erzeugt werden.
- Eine Protokollzeile, die bei praktisch jeder Entität ansprang und dadurch nichts markierte, erscheint nur noch einmal je Durchlauf in zusammengefasster Form. Die eigentlichen Ausschlüsse gingen darin unter.

### Fixed (Simulationsstart bleibt nicht mehr stumm hängen — 2026-08-10)

- **Ein Startversuch endet jetzt immer sichtbar.** Der Start legt zuerst einen Laufeintrag mit dem Status „wartet" an und startet erst danach den Simulationsprozess. Ging dabei irgendetwas schief, blieb der Eintrag auf „wartet" stehen: die Oberfläche zeigte weiterhin „Bereit", in der Laufliste sammelten sich Einträge, die nie etwas taten, und abbrechen ließen sie sich auch nicht. Im gemeldeten Fall waren neun solcher Einträge aufgelaufen. Jeder Abbruch nach dem Anlegen des Eintrags markiert ihn jetzt als fehlgeschlagen — unabhängig davon, woran es lag.
- Zuvor waren zwei bekannte Abbruchgründe einzeln behandelt worden. Das genügte nicht: der eigentliche Prozessstart lag außerhalb der Absicherung, und jeder neu hinzukommende Abbruchweg hätte dieselbe Lücke wieder geöffnet. Die Absicherung umschließt jetzt den gesamten Abschnitt, einschließlich des Falls, dass der Server die Anfrage nach zu langer Laufzeit selbst abbricht — genau dieser Fall hatte die stummen Einträge erzeugt.
- **Hängengebliebene Einträge lassen sich abbrechen.** „Abbrechen" war bisher nur für laufende Simulationen vorgesehen und wies Einträge im Wartezustand ab. Damit waren sie weder abbrechbar (weil nicht laufend) noch wurden sie je laufend (weil der Start nie durchlief). Sie werden jetzt direkt beendet; für bereits abgeschlossene Läufe bleibt „Abbrechen" wie bisher wirkungslos.

### Changed (Mehr Platz für die Antwort — 2026-08-09)

- **Jeder generative Modellaufruf bekommt jetzt mindestens 32.768 Ausgabe-Tokens statt der bisherigen 1.024 bis 4.096:** Ein Berichtsabschnitt mit Belegen passte nicht zuverlässig in vier Kilotoken, und ein am Limit abgeschnittener Abschnitt war im fertigen Report nicht als abgeschnitten erkennbar. Die Untergrenze gilt zentral im Modell-Client, nicht mehr pro Aufrufer. Zwei Grenzen bleiben gewahrt: Modelle mit kleinerem Ausgabelimit werden auf ihr Limit gedeckelt statt mit einem Fehler abzubrechen, und bei lokal betriebenen Modellen wächst das Kontextfenster mit, weil dort Eingabe und Ausgabe sich einen Platz teilen — ohne das hätte die höhere Grenze den Prompt verdrängt statt mehr Text zu erlauben. Klassifizierende Aufrufe mit bewusst enger Antwort behalten ihr kleines Limit. Einstellbar über `LLM_MAX_TOKENS_FLOOR`; `0` stellt das alte Verhalten her.

### Added (Dokumentbelege im Report — 2026-08-09)

- **Ein Fakt aus dem Wissensgraphen zählt jetzt als Dokumentbeleg, wenn seine Herkunft bekannt ist:** Trägt ein gefundener Fakt die Dokument- und Chunk-Herkunft aus der Aufnahme, wird er als Beleg aus dem Seed-Korpus geführt und bekommt einen auflösbaren Anker auf die konkrete Stelle im Ausgangsdokument. Damit können Aussagen, die zusätzlich durch ein Agentenzitat gestützt sind, überhaupt erst mittlere Confidence erreichen — vorher war das strukturell unmöglich und jede solche Aussage blieb auf `low`. Fakten ohne belegte Herkunft bleiben Graph-Relationen; geraten wird nichts. Die Identität eines Dokumentbelegs hängt an der Dokumentstelle, nicht am Wortlaut des Fakts: dieselbe Stelle bleibt derselbe Beleg, auch wenn das Modell sie beim nächsten Mal anders formuliert.

### Changed (Seed-Status verlangt einen auflösbaren Anker — 2026-08-09)

- **Bestehende Berichte verlieren beim Laden unbelegte Dokumentbezüge:** Bis zu dieser Änderung war „Seed-Korpus“ die Standardgattung für alles, was aus dem Wissensgraphen kam — auch ohne jeden Bezug zu einem konkreten Dokument. Solche Belege behaupteten eine Nachprüfbarkeit, die es nicht gab. Sie werden beim Laden zu Graph-Relationen; eine Aussage, die dadurch ihre Grundlage für mittlere Confidence verliert, wird auf `low` gestuft. Berichte bleiben lesbar und laden ohne Fehler — sie zeigen den Belegstand ehrlicher an als zuvor. Aussagen, die von zwei unterschiedlichen Stakeholder-Gruppen gestützt werden, behalten ihre hohe Confidence unverändert.

### Fixed (Report-Abbruch bei nicht agent-grounded medium-Claims — 2026-08-09)

- **Ein Claim mit unverdientem `medium`-Label beendet nicht mehr den ganzen Report:** Die Confidence-Stufe `medium` verlangt laut ADR-0002 mindestens ein Agentenzitat (mit Originalzitat) und mindestens einen Beleg aus dem Seed-Korpus. Der Report-Builder hat das beim Zusammenstellen der Claims nicht geprüft — die Verletzung fiel erst der Schlussvalidierung der Evidence-Map auf, und die bricht die gesamte Report-Erzeugung ab. Der eingebaute Reparaturlauf half nicht: die Validierung meldet pro Durchgang nur den ersten Verstoß je Abschnitt, sodass nach der Reparatur des ersten Claims der nächste stehen blieb. Betroffene Claims werden jetzt beim Bauen ehrlich auf `low` abgestuft und mit Begründung im Gate-Protokoll vermerkt, statt den Lauf zu beenden. Die Prüfung folgt dabei den kanonischen Evidence-Records, nicht den Referenzeinträgen am Claim — sonst könnte sie zu einem anderen Urteil kommen als die Schlussvalidierung. Der Validator selbst bleibt unverändert streng.

### Added (Evidence-Chain-Audit und Paper — 2026-08-09)

- **Der Audit der Evidenzkette liegt als versionierte Quelle im Repository:** `docs/paper/agora-evidence-chain-audit.md` dokumentiert den geprüften Ist-Zustand von Ingest, Graph-Aufbau, Simulation, Evidence-Gating und Report — mit Belegstellen im Code statt aus README-Behauptungen abgeleitet. Die begleitenden Rechercheprotokolle unter `docs/paper/research-notes/` halten je Teilbereich fest, welche Aussage an welcher Codestelle verifiziert wurde.
- **LaTeX-Quellen des Papers zur Evidenzkette:** Kapitel, Literaturverzeichnis, Abbildung und `latexmkrc` (LuaLaTeX + Biber) sind versioniert, das gebaute PDF liegt daneben. LaTeX-Zwischendateien und lokale Render-Ausgaben unter `output/` bleiben per `.gitignore` außen vor — sie enthalten absolute Maschinenpfade und ändern sich bei jedem Build.

### Added (Simulationsläufe sind im Zufallsanteil wiederholbar — 2026-08-10)

- **Ein Lauf trifft seine Zufallsentscheidungen nicht mehr aus dem Nichts.** Wie viele Agenten pro Runde aktiv werden, welche davon in Frage kommen und welche schließlich gezogen werden, entschied bisher der ungeseedete globale Zufallsgenerator des Simulationsprozesses. Zwei Läufe derselben Konfiguration waren damit nicht vergleichbar — und ohne Vergleichbarkeit ist jede Wiederholung und jeder Baseline-Vergleich methodisch angreifbar. Der Lauf setzt jetzt vor der ersten Zufallsentscheidung einen Startwert: entweder das Feld `random_seed` aus `simulation_config.json`, oder — wenn dort nichts steht — einen aus der Lauf-Kennung abgeleiteten Wert. Derselbe Lauf ergibt beim Neustart denselben Startwert, verschiedene Läufe verschiedene.
- **Einen Lauf gezielt wiederholen** geht damit so: den protokollierten Startwert (`Random seed: …` im Simulationslog) als `random_seed` in die Konfiguration des neuen Laufs schreiben. Der Startwert wird über einen stabilen Hash abgeleitet, nicht über Pythons prozesslokalen String-Hash — sonst wäre er zwischen zwei Prozessen verschieden gewesen, also genau das Gegenteil von wiederholbar.
- **Was das ausdrücklich nicht zusichert:** Die Antworten der Sprachmodelle bleiben unvorhersagbar. Gleicher Startwert heißt deshalb *nicht* gleicher Bericht. Reproduzierbar ist der Zufallsanteil des Laufs, nicht sein Ergebnis; für identische Berichte müssten zusätzlich die Modellantworten aufgezeichnet werden, was ein eigenes Vorhaben ist.

### Added (Operative Zahlen weisen aus, woher sie kommen — 2026-08-10)

- **Eine Zahl im Report sagt jetzt, wie sie zustande kam.** Angaben wie „>90 % Traffic-Baseline" oder „14-Tage-Rankinggrenze" sahen im Fließtext alle gleich aus — unabhängig davon, ob sie so im Auftragsdokument standen, aus gemessenen Daten stammten, aus einer Norm, aus einer Festlegung des Betreibers oder schlicht daraus, dass ein Sprachmodell sie plausibel fand. Wer den Bericht las, konnte das nicht unterscheiden und behandelte im Zweifel alle gleich verbindlich. Der Report führt operative Zahlen deshalb in einem eigenen Abschnitt „Operative Zahlen" mit ihrer Rolle (Alarmschwelle, Zielwert, Obergrenze, Ausgangswert), ihrer Herkunft im Klartext und ihrer Beleglage.
- **Sechs Herkunftsarten** stehen zur Verfügung: Vorgabe aus dem Dokument, aus Daten abgeleitet, externer Standard, Betreiber-Festlegung, Modellvorschlag und Simulationsvorschlag. Im Zweifel gilt „Modellvorschlag" — eine Zahl ohne belegbare Herkunft ist ein Vorschlag, keine Anforderung. Die Beleglage steht daneben und ist standardmäßig „unbelegt"; eine Zahl als belegt auszuweisen, ohne einen Beleg zu nennen, weist der Vertrag zurück. Das wäre schlimmer als ehrliche Unbelegtheit, weil der Leser sich dann auf einen Beleg verlässt, den es nicht gibt.
- Die Herkunft einer Zahl ist bewusst **getrennt** von der Quellengattung eines Belegs geführt: die eine beschreibt, wie eine Zahl entstand, die andere, woher ein Beleg stammt. Eine Vermischung hätte die Evidenzregeln verwässert. Berichte ohne Zahlenangaben bleiben unverändert gültig.

### Changed (Gegenprüfung bei entscheidungstragenden Reports — 2026-08-09)

- **Die Red-Team-Gegenprüfung hängt nicht mehr allein am Echo-Kammer-Index:** Bisher lief sie nur, wenn die simulierten Personas auffällig gleichgerichtet waren (Index über 0.6). Im Referenzlauf des Evidenzketten-Audits lag der Index bei 0.55 — die Gegenprüfung entfiel damit ausgerechnet bei einem vollständigen Report, obwohl der Index gar nichts über den Berichtstyp aussagt. Risiko-, Vergleichs- und Vollreports bekommen die Gegenprüfung jetzt immer; sie stützen eine Entscheidung, dort gehört der Widerspruch zum Produkt. Beim Meinungsbild und beim explorativen Report bleibt die Schwelle als Kostenbremse. Ein übersprungener Lauf hinterlässt weiterhin keinen Modelleintrag und ist dadurch von einem Lauf ohne Befunde unterscheidbar.

### Added (Markdown-Report zeigt seine Belege, nicht nur Belegnummern — 2026-08-10)

- **Der Markdown-Export löst seine Belegkennungen auf.** Claim- und Multiplier-Tabellen führten bisher nur Kennungen wie `ev_00000…`; wer den Report als Markdown las, sah Verweise ohne Belege. JSON- und ZIP-Export tragen die Herkunft seit jeher vollständig — ausgerechnet das Format, das weitergereicht und ausgedruckt wird, tat es nicht. Am Ende des Berichts steht jetzt ein Abschnitt „Evidenz-Nachweise": pro Kennung die Quellengattung im Klartext (etwa „Seed-Dokument" statt `seed_corpus`), der Produzent, die Quelle und der belegende Auszug. Wo ein Originalzitat vorliegt, steht es dort — es belegt die Aussage, während der umgebende Textausschnitt sie nur einbettet.
- Der Abschnitt steht bewusst hinten und nicht in den Tabellen selbst: dieselbe Evidenz stützt oft mehrere Aussagen, und die Tabellen bleiben schmal genug zum Lesen. Lange Auszüge werden gekürzt — der Nachweis soll die Zuordnung ermöglichen, nicht die Quelle ersetzen. Die Reihenfolge ist stabil, damit zwei Exporte desselben Berichts nicht grundlos verschiedene Dateien ergeben.

### Fixed (Export liefert keine ungeprüfte Evidenz mehr aus — 2026-08-10)

- **ZIP- und CSV-Export prüften die Evidenz nie.** Wer einen Report als ZIP oder als Claims-CSV zog, bekam eine Datei, die aussieht wie geprüfte Evidenz — ohne dass die Prüfung je stattgefunden hätte. Kein Hinweis, kein Vermerk. Der JSON-Export verhielt sich seit jeher korrekt und wies eine vertragswidrige Evidenz-Übersicht als ausgelassen aus; der Lese-Endpunkt `GET /api/report/<id>/evidence` wiederum brach mit einem Serverfehler ab, an dem nicht zu erkennen war, ob die Anwendung defekt ist oder die Daten. Drei Wege, dieselbe kaputte Datenlage, drei verschiedene Antworten.
- **Alle vier Wege antworten jetzt gleich.** Verletzt die Evidenz auch nach der Migration den Vertrag, tragen JSON-Envelope, ZIP-Archiv, CSV-Abruf und Lese-Endpunkt denselben Grund (`contract_violation`), dieselbe Erläuterung und dieselbe Fehlerliste. Im ZIP liegt statt `evidence-map.json` und `claims.csv` eine Datei `evidence-omitted.json` mit der Begründung — auch lesbar für jemanden, der das Archiv später ohne Agora öffnet. Der Claims-CSV-Abruf wird abgelehnt statt beantwortet: eine CSV-Datei hat keine Stelle, an der ein Auslassungshinweis stehen könnte, und sähe damit wie eine vollständige Evidenzliste aus. Der Lese-Endpunkt antwortet mit einem Datenfehler statt mit einem Serverfehler.
- **Der Report-Rumpf bleibt in allen Fällen vollständig** — Personas, Segmente, Markdown und Verbrauchsdaten sind unberührt. Betroffen ist ausschließlich der Evidenz-Teil, und nur dann, wenn er den Vertrag tatsächlich verletzt.

### Changed (Confidence-Semantik: Geltungsbereich sichtbar, `verified` belastbar — 2026-08-10)

- **Reports weisen jetzt aus, worauf eine Confidence beruht.** Ein Befund, den ausschließlich simulierte Agenten stützen, konnte dasselbe Label tragen wie ein quellengebundener — die Skala allein unterscheidet das nicht, und im Report stand nur „high". Die Claim-Tabelle führt deshalb eine Spalte „Geltungsbereich": *Simulationskonsens* bei Aussagen, hinter denen nur Agentenstimmen stehen, *Quellenbindung*, sobald mindestens ein stützender Beleg aus Seed-Korpus, Wissensgraph oder Recherche stammt. Abgeleitet wird das aus derselben Evidenzmenge, aus der auch die Belegverweise entstehen; ein widersprechender oder nur thematisch verwandter Treffer begründet keine Quellenbindung. Berichte aus der Zeit vor dieser Änderung zeigen „-" statt einer Behauptung über einen Geltungsbereich, der nie erfasst wurde. Die Label-Semantik selbst bleibt unangetastet.
- **Das oberste Vertrauenslabel hängt nicht mehr allein an Textähnlichkeit.** `verified` verlangte bisher nur einen Ähnlichkeitswert ab 0.85 — ein Wert, der beantwortet, ob es um dasselbe Thema geht, nicht, ob die Quelle die Aussage trägt. Die Schwelle bleibt Voraussetzung, genügt aber nicht mehr: dasselbe Belegstück muss zusätzlich das Prüfurteil „stützt die Aussage" tragen. Getrennte Belege dürfen die Bedingung nicht zusammenstückeln. Bestandsreports ohne dieses Urteil werden beim Laden auf `high` abgestuft und mit einer Begründung im Prüfprotokoll versehen, statt abgelehnt zu werden — der Bestand wird ehrlicher, nicht unlesbar.
- **Zwei Schreibweisen derselben Stakeholder-Gruppe zählen als eine.** Das oberste Vertrauenslabel verlangt Stimmen aus mindestens zwei unterschiedlichen Gruppen. Da die Gruppenbezeichnung ein freies Textfeld ist, ließ sich diese Bedingung bisher mit einer einzigen Gruppe erfüllen, indem ihr Name unterschiedlich geschrieben wurde. Verglichen wird jetzt ohne Groß-/Kleinschreibung und ohne Leerzeichenunterschiede. Angezeigt und gespeichert bleibt die Schreibweise der Quelle; eine feste Liste erlaubter Gruppenbezeichnungen ist ausdrücklich nicht eingeführt worden.

### Fixed (Übersetzungsreste in Modell-Anweisungen und einer API-Antwort — 2026-08-10)

- **Aus einem chinesischsprachigen Upstream stehengebliebene Schriftzeichen sind aus den Texten verschwunden, die an das Sprachmodell gehen:** Betroffen waren die Hinweise, mit denen der Report-Agent auf noch ungenutzte Werkzeuge aufmerksam gemacht wird, sowie der Platzhalter für einen noch leeren Bericht im Chat. Dort standen halbseitig geöffnete, aber vollbreit geschlossene Klammern und ein ostasiatisches Aufzählungskomma als Trennzeichen. Das ist kein Schönheitsfehler: Diese Hinweise entscheiden mit darüber, ob der Agent seine Werkzeuge überhaupt einsetzt, und ein Zeichen, mit dem das Modell nicht rechnet, kann diese Wirkung kosten. Ebenfalls bereinigt ist eine Statusmeldung der Vorbereitungs-Schnittstelle, die unverändert an die Oberfläche durchgereicht wird. Die Formulierungen selbst sind absichtlich unangetastet geblieben — geändert wurde ausschließlich die Zeichensetzung, damit sich das Verhalten des Modells nachvollziehbar nicht aus einem anderen Grund verschiebt. Ein Test wacht künftig über beide Dateien.

### Changed (Ingestion-Schutztest läuft ohne Netzzugang — 2026-08-10)

- **Der Regressionstest für den nltk-Import-Schutz braucht keine Downloads mehr:** Er hat bisher einen echten Parse-Aufruf gefahren und damit zwei Sprachmodelle nachgeladen, die auf einem frischen Rechner nicht vorliegen. Wo ausgehender Netzverkehr gesperrt ist — etwa in der CI —, schlug er deshalb fehl, obwohl der geprüfte Schutzmechanismus einwandfrei funktionierte; auf Entwicklerrechnern blieb er grün, weil die Modelle dort aus einem früheren Lauf im Nutzer-Cache lagen. Der Test prüft jetzt genau die Stelle, an der der Fehler tatsächlich auftritt: den nachgelagerten Import, den jeder Parse-Aufruf durchläuft. Er ist damit auf jedem Rechner und in jeder Umgebung gleich aussagekräftig und schlägt nur noch an, wenn der Schutzmechanismus wirklich versagt.

### Fixed (Nachträglich abgestufte Aussagen weisen ihre Herkunft aus — 2026-08-10)

- **Wird eine Aussage nachträglich herabgestuft, änderte sich bisher nur die Vertrauensstufe.** Der Wortlaut blieb, wie er war — und der stammt vom Sprachmodell, das ihn unter der höheren Stufe geschrieben hat: deklarativ, ohne die Vorsicht, die die niedrigere Stufe verlangt. Der Bericht bestand seine Prüfung, transportierte im Fließtext aber weiterhin eine Behauptung in einer Sicherheit, die seine eigene Einstufung nicht mehr deckte.
- **Solche Aussagen sind jetzt als solche erkennbar.** In der Aussagentabelle steht neben der Stufe, unter welcher Stufe der Wortlaut entstanden ist. Die Übersicht am Anfang des Berichts — vor dem Fließtext — nennt zusätzlich, wie viele Aussagen davon betroffen sind. Bei mehrfacher Herabstufung bleibt die *ursprüngliche* Stufe stehen: unter ihr wurde formuliert, eine zwischenzeitliche wäre die falsche Bezugsgröße.
- **Der generierte Text bleibt unangetastet.** Das ist eine bewusste Entscheidung gegen die naheliegende Alternative, dem Satz nachträglich eine abschwächende Formulierung voranzustellen: die hätte Sprachfragen aufgeworfen, sich bei mehrfacher Herabstufung selbst verdoppelt und in einen Text eingegriffen, für den das Modell verantwortlich zeichnet. **Was das nicht leistet:** eine deklarativ formulierte Passage im Fließtext bleibt deklarativ formuliert. Sie steht dort aber nicht mehr unkommentiert — Tabelle und Übersicht weisen sie aus, und die Übersicht liest man zuerst.

### Added — Feed-Snapshot beim Mount (#1009)

- **Feed ist beim Öffnen sofort befüllt:** Die Simulations-Feed-View lädt beim Mount den bisherigen Sim-Bestand aus der SQLite-DB über einen neuen `/feed-snapshot`-Endpoint und ingestiert ihn vor SSE-Stream-Start. `useSimFeed`-Dedup per `post_id` verhindert Doppeleinträge, wenn Live-Events für bereits geladene Posts eintreffen. (#1009)

### Changed — PostCreatedEvent-Vertrag: persona_name + voice_register-Vokabular (#1216)

- **`persona_name` ist Pflichtfeld:** Der Layer-0-Vertrag (`PostCreatedEvent`) führt den Anzeigenamen der Persona als Pflichtfeld; Frontend-Komponenten (RedditPost, TwitterPost, PersonaAvatar) zeigen den Namen statt der technischen `persona_id`. (#1216 5a)
- **`voice_register`-Vokabular an Profil-Generator angebunden:** Die Enum-Werte sind jetzt `formal-de`/`neutral-de`/`technical-de`/`skeptisch-de` (zuvor `formal`/`casual`/`jugendsprache`, was nie an den Generator angebunden war und per Fallback jede Persona verschleierte). Legacy-Werte werden vom Vertrag abgelehnt (Anti-Dekorations-Linie). Twitter-Profile (CSV persistiert kein `voice_register`) erhalten dokumentiert `neutral-de` als Generator-Default. (#1216)
- **Kommentare als PostCreatedEvent:** Der OASIS-Runner emittiert `CREATE_COMMENT`-Aktionen mit plattformpräfixtem `post_id` (`<platform>:comment:<id>`) und `parent_post_id` = Elternpost, sodass der Reddit-Reply-Tree im Live-Feed Äste bekommt. `post_id` ist plattformübergreifend eindeutig (`<platform>:<id>`), was Dedup-Kollisionen zwischen Reddit und Twitter auflöst. (#1216 5c)

### Fixed (Routing-Audit hält den Fallback-Grund fest — 2026-08-10)

- **Der Grund für einen Modell-Fallback verschwand aus dem Routing-Audit, sobald er nicht aus dem Provider-Fallback stammte:** Die Routen-Auflösung leert das oberste `fallback_reason` für jede Ebene außer `provider_fallback`. Ein Modellverweis mit `source="fallback"` landet aber in der Stage- oder Run-Ebene — sein Grund wurde damit verworfen, bevor das Audit ihn schreiben konnte, und im Protokoll stand nur noch `null`. Wer im Nachhinein wissen wollte, warum ein Lauf auf ein Ersatzmodell ausgewichen ist, fand die Antwort nicht mehr. Der Grund reist jetzt im selben Legacy-Kanal mit, den `ai_model_ref_source` schon nutzt, und das Audit liest ihn von dort. Bestandsprotokolle ohne den neuen Schlüssel bleiben gültig: fehlt er, gilt weiterhin das oberste Feld, sodass auch vor dieser Änderung geschriebene Läufe ihren Grund behalten.

### Fixed (Barrierefreiheits-Prüfungen können nicht mehr die falsche Seite prüfen — 2026-08-10)

- **Ein Prüflauf, der versehentlich auf dem Einrichtungs-Assistenten landet, bricht jetzt ab, statt grün zu melden:** Solange die Ersteinrichtung nicht abgeschlossen ist, leitet die Anwendung jeden Aufruf einer anderen Seite dorthin um. Ein automatisierter Barrierefreiheits-Check, der das nicht bemerkt, prüft monatelang den Assistenten und bescheinigt der eigentlich gemeinten Seite Fehlerfreiheit — genau das war bei der Kostenübersicht passiert, wo nach dem Beheben sofort sechs echte Kontrastverstöße sichtbar wurden. Die Prüfung vergleicht nun die angeforderte mit der tatsächlich erreichten Adresse und nennt im Fehlerfall den fehlenden Schritt beim Namen. Wer den Assistenten absichtlich prüft, bekommt weiterhin keinen Fehlalarm. Eine Bestandsaufnahme aller vorhandenen Prüfläufe hat ergeben, dass aktuell keiner weiteren Seite dasselbe passiert.


## [0.9.4] — 2026-08-09

### Added (Dokument-Provenance — 2026-08-09)

- **Dokumentidentität von der Datei-Extraktion bis ins Retrieval:** Hochgeladene Dateien bekommen jetzt eine eindeutige Dokument-ID mit Blob-Offsets, Text-Chunks werden darüber ihrem Ursprungsdokument samt dokumentinterner Chunk-Nummer zugeordnet, und der Graph-Build hält diese Herkunft am Wissensgraph fest. Die Retrieval-Ergebnisse geben sie wieder heraus: zu jedem gefundenen Fakt ist ablesbar, aus welchem Dokument und welchem Abschnitt er stammt. Lässt sich das nicht eindeutig bestimmen, bleibt die Herkunft leer statt geraten. Bestehende Projekte laufen unverändert weiter und liefern wie bisher keine Herkunftsangaben. Auf Reports wirkt sich das noch nicht aus — die Auswertung der Herkunft in der Belegkette folgt in einem Folge-Slice.

### Fixed (Evidence-Persistenz und Report-Gating — 2026-08-09)

- Interview-Antworten und Graph-Fakten werden jetzt als kanonische Evidence
persistiert und sind von Claims referenzierbar — vorher verwarf der
Evidence-Index sie still, und Reports endeten trotz durchgeführter
Interviews mit null validierten Claims. Zusätzlich: das neue
`gate_decision_log` protokolliert jede Gate-Entscheidung (Reviewer-Floor,
fehlende Evidence, Fließtext-Entfernungen) getrennt vom statusrelevanten
`degradation_log`, Key-Takeaways tragen einen `confidence_scope`
(Simulations-Konsens vs. Evidenz), der ReportV3-Export beginnt mit einem
Evidenzstatus-Block, und die Structured-Metadata-Extraktion sieht den
vollständigen Section-Text statt eines 6000-Zeichen-Ausschnitts (beendet
erfundene „Abschnitt bricht ab"-Data-Gaps).

### Added (Referenzlauf Domainmigration — 2026-08-09)

- **Zwei vollständig dokumentierte End-to-End-Referenzläufe im Repository:** Der Fall „Domainmigration `alexle135.de` → `alex-schneider.dev`" liegt als technische Case Study unter `docs/reference-runs/` — inklusive Pipeline-Verlauf, Metrics-Snapshot, Evidence-Gating-Ergebnissen, bekannten Grenzen und Audit-Findings.
- **Deterministische Evidence-Extracts als Artefakte:** Jeder Lauf trägt einen quellentreuen `evidence-extract.json` mit Provenienzangaben, Größen und SHA-256-Prüfsummen; README und Dokumentationsindex verlinken den Referenzlauf.

### Fixed (OASIS-Simulation hängt auf Runde 0 — 2026-08-09)

- **Host-adaptives BERT-Memory-Profil (`auto`-Default):** `install_bert_memory_profile` erzwang TWHIN-BERT bedingungslos auf `torch_dtype=fp16`. fp16 hat auf CPU keine nativen Kernel und fällt auf eine single-threaded Emulation zurück, deren Forward ~12 min dauert — `update_rec_table` ist `async`, ruft den Forward aber synchron (ohne `run_in_executor`) auf und blockiert so den gemeinsamen asyncio-Event-Loop von Twitter- und Reddit-Plattform (Runde-0-Hang). Neuer Default `"auto"` injiziert fp16 nur noch bei knappem Container-RAM (< 4 GB verfügbar, OOM-Schutz für 2.8-GiB-Kleincontainer) und lädt sonst fp32 (native CPU-Kernel, 16-Thread, ~14 s/Forward). `"low"`/`"off"` behalten ihre Semantik. (#1148)

### Fixed (Kanonische Evidence-Identität — 2026-08-09)

- **Report-Claims referenzieren Evidence jetzt über deterministische IDs:** EvidenceMap v3 und ReportV3 v4 trennen unveränderliche Source-Records von Claim-relativen Bindings, validieren alle Cross-References und stufen nicht auflösbare Legacy-Refs ehrlich zu Hypothesen ab.
- **Legacy- und CI-Pfade verwenden denselben aktuellen Evidence-Vertrag:** Persistierte ReportV3-v3-Daten werden vor der Validierung kompatibel hochgestuft, EvidenceMap-v3-Ergänzungen bleiben verlustfrei und der Quality-Gate prüft kanonische v3-Fixtures.

### Fixed

- CI: `prod-proxy-smoke` blockte via Harden-Runner-Egress jeden Zugriff auf `ghcr.io` und scheiterte damit auf jedem Release-/Tag-Push am Pull des `astral-sh/uv`-Basis-Images — der GHCR-Publish wurde dadurch nie erreicht. `ghcr.io:443` und `pkg-containers.githubusercontent.com:443` in die Smoke-Allowlist aufgenommen ([#1145](https://github.com/arn0ld87/agora/pull/1145)).

### Fixed (Drift-Fixer erkennt den README-Version-Badge wieder — 2026-08-08)

- **`check_version_drift.py` meldete „No version badge found in README.md", obwohl Zeile 11 einen Badge trägt:** Die Regex matchte nur `badge/Version-` (großes V), das README nutzt seit dem Redesign `badge/version-<semver>-<hexfarbe>`. Lese- und Schreib-Regex matchen jetzt case-insensitiv; beim Release-Cut 0.9.3 musste der Badge deshalb manuell nachgezogen werden. Regressionstests decken das aktuelle Kleinschreibungs-Format mit Hex-Farbe für Read- und Write-Pfad ab.

### Fixed (Hardstop-Check brach den Backend-Job auf main mit Bash-Syntaxfehler — 2026-08-08)

- **`scripts/check-pip-audit-hardstop.sh` endete bei jedem Lauf mit „syntax error in conditional expression" (Exit 2):** `[[ "$TODAY" >= "$HARDCUTOFF" ]]` — den Operator `>=` gibt es in Bash-`[[ ]]` nicht. Ersetzt durch den äquivalenten lexikografischen `<`-Vergleich; Regressionstests führen das Skript jetzt tatsächlich aus (vor/nach/am Cutoff-Tag). Der Defekt blieb unbemerkt, weil frühere main-Läufe schon am Ruff-Step scheiterten, bevor der Hardstop-Step erreicht wurde.

### Fixed (Robuster Multi-Prozess-Routing-Test — 2026-08-09)

- **Routing-Store-Test misst wieder die Lock-Invariante:** Die sieben Subprocess-Worker melden nach ihren Cold Imports explizit Readiness; erst danach beginnt die gemeinsame Lock-Deadline. Deterministisches Cleanup verhindert zugleich verwaiste Children. (#450)


## [0.9.3] — 2026-08-08

### Fixed (CI auf main wieder grün — 2026-08-08)

- **Ruff E101 in `backend/scripts/_sim_common.py`:** Sechs Docstring-Zeilen mit Tab-Einrückung (eingeschleppt via #1136) durch Spaces ersetzt; der push-Job auf main lintet das ganze Backend und schlug deshalb fehl, obwohl das PR-Gate grün war.
- **Ruff-Scope-Lücke geschlossen:** PR-Smoke-Gate (`ci.yml`) und `scripts/pre-push-gate.sh` linten jetzt wie der main-Job `ruff check .` statt nur `app/ tests/` — `scripts/` fällt nicht mehr durch die Lücke.

### Security (Frontend-Dependency-Audit — 2026-08-08)

- **`bun audit --audit-level=high` wieder grün:** Neue High-Advisories gegen axios, brace-expansion, nanoid, postcss und undici behoben — Lockfile frisch aufgelöst, Overrides auf nanoid ≥3.3.18, postcss ≥8.5.26 und undici ≥7.29.0 angehoben.

### Changed

- Testläufe filtern vier belegte Upstream-Warnquellen (pytest-asyncio, neo4j, OpenTelemetry-Flask) gezielt nach Nachricht und Modul; projekteigene DeprecationWarnings bleiben sichtbar und gate-fähig ([#1090](https://github.com/arn0ld87/agora/issues/1090), [#1140](https://github.com/arn0ld87/agora/pull/1140)).

### Changed (Merge-Friction beseitigt: PRs kollidieren nicht mehr auf CHANGELOG und STATUS-Zählern — 2026-08-08)

- **Jeder Merge machte den nächsten offenen PR konfliktbehaftet,** weil alle PRs ihren CHANGELOG-Eintrag an derselben Zeile unter `[Unreleased]` einfügten und Test-Zähler-Zeilen in `docs/STATUS.md` pro PR neu gemessen und committet wurden. CHANGELOG-Einträge leben jetzt als eindeutige Fragment-Dateien unter `changelog.d/` (Einsammeln beim Release-Schnitt via `scripts/collect-changelog.py`); die STATUS-Zähler prüft und schreibt nur noch ein dedizierter Refresh-Lauf — PR-Gates laufen mit `sync-status.sh --check --skip-counts`. Die flankierende Abschaltung von `strict` („Require branches to be up to date") in der Branch-Protection ist mit #1139 beschlossen und wird separat als Repo-Einstellung umgeschaltet (Stand des Schnitts: noch `strict: true`, siehe `docs/STATUS.md`); Required Checks bleiben unverändert Pflicht, die volle CI auf `main` bleibt der Backstop.


### Fixed (Hypothesen-Sortierung suggerierte ein Ranking-Signal, das nicht existiert — 2026-08-08)

- **`dedup_and_cap_hypotheses` sortierte über `_sort_key` primär nach `confidence_score` — ein Feld, das keiner der drei produktiven Erzeuger setzt, weil `ReportSectionHypothesisModel` als strict-Contract es gar nicht kennt.** In Produktion war `score` durchgängig `0.0`; die Sortierung suggerierte damit eine Rangfolge nach Konfidenz, die es nie gab (Codex-Finding zu PR #1078, siehe #1073). Das betraf beide Auswahlentscheidungen: welche fünf Hypothesen sichtbar sind und welche fünfzig im Appendix überleben.
- **`confidence_score` ist aus `_sort_key` entfernt, statt einen transienten Schlüssel dafür einzuführen.** Die Reihenfolge ist fachlich gleichgültig, weil Hypothesen per Definition unbelegt sind (Lead-Entscheidung, Variante 2 aus #1083) — sortiert wird jetzt allein nach `suggested_evidence`-Länge (das einzige ehrliche Signal, das über die Producer-Grenze existiert) mit dem Hypothesentext als stabilem, deterministischen Tiebreaker. Keine Contract-Erweiterung. (#1083)
### Fixed (GPT-5.x-Familie: 400er bei Function-Tools im CAMEL-Sim-Pfad — 2026-08-08)

- **Jeder tool-fähige CAMEL-Agent-Call gegen GPT-5.1+-Modelle (z. B. `gpt-5.6-luna`) scheiterte mit `400 — Function tools with reasoning_effort are not supported ... set reasoning_effort to 'none'`.** `build_camel_completion_params` in `backend/scripts/_sim_common.py` setzt jetzt für GPT-5.1+ explizit `reasoning_effort: "none"` (neuer Helper `supports_reasoning_effort_none`, Zwilling zu `uses_max_completion_tokens`). Das ursprüngliche `gpt-5` (5.0, ohne Minor-Version) kennt `"none"` nicht und bleibt unverändert — die Heuristik trennt Modelle ohne erkennbare Minor-Version (5.0) von `gpt-5.1`+ anhand des Modellnamens. Zwilling des Temperature-Quirks aus #1096, diesmal im OASIS/CAMEL-Pfad statt im `LLMClient`. (#1112)
### Changed (STATUS.md-Drift-Check im PR-Gate ohne Backend-Testanzahl-Messung — 2026-08-08)

- **Der CI-Step `STATUS.md drift check` im Job „Backend PR smoke gate" kostete ~115 s pro PR**, weil `scripts/sync-status.sh --check` die Backend-Testanzahl per `uv run pytest --collect-only -q` maß. Neues Flag `--skip-backend-count` (alternativ `SYNC_STATUS_SKIP_BACKEND_COUNT=1`) lässt genau diese eine Zeile aus — weder gemessen noch aus dem Cache gelesen noch verifiziert —, während Frontend-Zähler, Autogen-Block-Format und Generator-Konsistenz unverändert scharf geprüft bleiben. Nur dieser eine CI-Step nutzt das Flag; der lokale `sync-status.sh --check` (z. B. in `pre-push-gate.sh`) bleibt unverändert und misst weiterhin vollständig. (#1107)
### Changed (Radon-Gate: Allowlist-Einträge können eine cc-Obergrenze tragen — 2026-08-08)

- **Das Komplexitäts-Gate prüfte bei geduldeten Funktionen nur, OB sie geduldet sind — nicht, wie stark sie weiter wachsen dürfen.** Allowlist-Einträge in `backend/radon-allowlist.txt` können jetzt optional `# cc<=N` tragen: Überschreitet die gemessene Komplexität die Grenze, failt das Gate; unterschreitet sie sie, erscheint ein Absenkungs-Hinweis — auch dann noch, wenn der Hotspot auf rank C gesunken ist. Einträge ohne Obergrenze verhalten sich unverändert (reine Duldung), Bestandseinträge und die D+-Schwelle bleiben unangetastet. Der lokale Schnellcheck `scripts/check_complexity.sh` parst das neue Inline-Kommentar-Format mit. (#1084)
### Fixed (cve-monitor lief in denselben torch-Local-Version-Fehler wie früher ci.yml — 2026-08-08)

- **Der wöchentliche CVE-Monitor scheiterte an einer Infrastrukturzeile statt an echten Advisories:** `uv export` schreibt auf Linux den Pin `torch==2.13.0+cpu`, den pip-audit gegen PyPI nicht auflösen kann — `AUDIT_EC` stand damit permanent auf 1 und wäre ab dem Hardstop 2026-09-28 hart rot geworden. Der Export nutzt jetzt dieselbe Lösung wie ci.yml (#1073/#1074): `uv export --frozen --no-dev --no-hashes --no-emit-project` plus `normalize_audit_requirements.py` (strippt PEP-440-Local-Labels), und der Audit-Aufruf übernimmt `--no-deps --disable-pip`, damit pip die Torch-CUDA-Kette nicht von PyPI nachauflöst. `--ignore-vuln`-Politik und Hardstop unverändert. (#1075)
### Fixed (Trivy-Gate zog MEDIUM-CVEs hart, obwohl es auf CRITICAL/HIGH konfiguriert ist — 2026-08-08)

- **`build-only` (Docker-Image-Workflow) blockierte alle PRs wegen zweier neuer MEDIUM-pypdf-CVEs:** Die trivy-action ignoriert im SARIF-Modus den `severity`-Filter, solange `limit-severities-for-sarif` fehlt — der `exit-code: 1` feuerte damit auf jede fixbare CVE statt nur auf CRITICAL/HIGH. Flag ergänzt; zusätzlich pypdf im Lockfile auf 6.15.0 angehoben (CVE-2026-71852, CVE-2026-71870, transitive Dependency).

### Changed (E2E-Required-Check-Runbook auf aktiven Branch-Protection-Stand korrigiert — 2026-08-08)

- **Das Runbook beschrieb die Required-Erzwingung noch als offen und zeigte ein destruktives `PUT`-Beispiel mit nur sechs Playwright-Checks.** Der dokumentierte Status entspricht jetzt der aktiven `main`-Branch-Protection mit 17 Required Checks; das CLI-Beispiel liest den aktuellen Satz, ergänzt die sechs Playwright-Smokes idempotent und aktualisiert ausschließlich `required_status_checks`, sodass CodeQL-, Dependency-, Schema-, Contract-, Security-, Version- und PR-Smoke-Gates erhalten bleiben. (#1089)

### Changed (Lokales Pre-Push-Gate auf schnellen Sanity-Check verschlankt — 2026-08-08)

- **`scripts/pre-push-gate.sh` ist kein vollständiger CI-Spiegel mehr:** `mypy`, das Backend-Test-Subset und die Frontend-Vitest-Suite laufen lokal nur noch mit `GATE_FULL=1`; per Default bleiben ruff, Contract-Tests, Schema-Drift, `sync-status`, ESLint, `vue-tsc`, Schema-Spiegel-Smoke und Routing-Check (voller Lauf ~63 s statt mehrerer Minuten). Absicherung unverändert über die Required-PR-Smoke-Gates der CI (Backend: `mypy app` + Test-Subset; Frontend: `bun run test` + `vite build`). Ersetzt die frühere Zusage, dass mypy und Vitest lokal Pflicht bleiben. Runbook `docs/runbooks/pre-push-gate.md` entsprechend aktualisiert. (#1127)
### Changed (Dependency-Caching für uv und bun in der Haupt-CI — 2026-08-08)

- **`backend`- und `backend-pr-gate`-Job installieren `uv` jetzt über `astral-sh/setup-uv` statt manuell per `pip install`** (`enable-cache: true`, `cache-dependency-glob: backend/uv.lock`) — derselbe gepinnte SHA (`37802adc94f370d6bfd71619e3f0bf239e1f3b78`, v7), der in `cve-monitor.yml` bereits produktiv ist. `security` bleibt unverändert: der Job installiert `uv` nur für `uv export` (kein `uv sync`, kein Paket-Download) und Bun nur für `bun audit` (kein `bun install`) — Caching hätte dort keinen Effekt gehabt.
- **`frontend`- und `frontend-pr-gate`-Job cachen `~/.bun/install/cache`** über ein neu gepinntes `actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9` (v6.1.0), Key an den `bun.lock`-Hash gebunden. `setup-bun` selbst cacht nur die Bun-Binary, nicht die Paket-Installationen.
- **`step-security/harden-runner`-Allowlist** der vier betroffenen Jobs um `results-receiver.actions.githubusercontent.com:443` und `*.blob.core.windows.net:443` ergänzt — beide Endpunkte sind für den GitHub-Actions-Cache-Service erforderlich. (#1087)

### Fixed (Budget-Enforcement griff nicht in Report-Resume und Prepare-Phasen — 2026-08-06)

- **`POST /api/runs/<id>/resume` baute seinen `LLMClient` ohne `run_id` — ein fortgesetzter Report lief ohne jede Budgetdurchsetzung, selbst mit hartem Budget am Run.** Der Resume-Client entsteht jetzt aus der beim Original-Start gelockten Stage-Route via `LLMClient.from_route(..., run_id=...)` (SSoT aus #817, keine zweite Client-Bauweise neben der Route); Routing-/Key-Fehler antworten weiterhin synchron mit 422. Ein `BudgetExceededError` im Resume-Worker endet als `stopped` + `termination_reason` statt `failed` (Reihenfolge `fail_task()` → `mark_budget_abort()`, #978/#841). (#984)
- **Dieselbe Lücke in den Prepare-Phasen:** Persona- (`OasisProfileGenerator`) und Config-Generierung (`SimulationConfigGenerator`) bauten ihre LLM-Clients ohne `run_id`. Beide Generatoren erhalten jetzt die persistierte `run_id` des Prepare-Runs über die Kette API → `SimulationManager.prepare_simulation` → `prepare_service`-Phasen; ein hartes Call-, Token-, Kosten- oder Zeitlimit beendet auch die Vorbereitung nachvollziehbar als `stopped` + `termination_reason`. (#984)

### Fixed (Export-Parität: ZIP/CSV lasen eine andere Evidence-Wahrheit als der JSON-Export — 2026-08-06)

- **Derselbe Report lieferte je nach Exportformat verschiedene Evidence-Wahrheiten:** Der JSON-Export normalisierte über `normalize_persisted_evidence_map` (#987), `build_zip_bundle`, `stream_zip_bundle` und `build_csv_export` (`table=claims`) lasen die Roh-Map — ein orphan medium-Claim stand im JSON in `data_gaps`, in `claims.csv` und `evidence-map.json` (ZIP) unverändert als `medium`. Alle Export-Formate lesen jetzt eine normalisierte Sicht über genau eine Stelle (`ReportExportService._normalized_evidence_map`); `evidence-map.json` im ZIP ist damit bewusst kein Rohabzug mehr. Regressionstests vergleichen ZIP, CSV und Streaming-ZIP (Threshold klein gepatcht) gegen den JSON-Export als Referenzwahrheit. (#1036)

### Fixed (Cancel beendete die laufende OASIS-Simulation nicht — 2026-08-06)

- **`POST /api/runs/<id>/cancel` setzte für `simulation_run` ein prozesslokales Cancel-Flag, das kein Consumer las — API und UI meldeten „Cancel requested", der OASIS-Subprozess lief ungebremst weiter.** Der Monitor-Thread im Elternprozess konsumiert das Flag jetzt pro Tick (`sim/monitor.py::_cancel_supervision`): Marker schreiben, kooperativen Stop via `control_state.json` signalisieren, dann den Subprozess beenden (SIGTERM, 10 s Grace, dann SIGKILL — über das bestehende `process_manager.terminate_run`). Der Run endet deterministisch als `stopped` mit `termination_reason="user_cancel"`; der SIGTERM-typische non-zero Exit wird nicht mehr als `failed` fehlklassifiziert. Cancel zwischen zwei Runden behält Teilergebnisse: bereits getailte Action-Logs und der persistierte Run-State bleiben erhalten. Die Docstrings von `cancel_flag.py` und der Cancel-Route beschreiben jetzt die tatsächliche Consumer-Lage. (#1082)
## [0.9.0] — 2026-08-06

### Changed (Version-Cut `0.8.0` → `0.9.0` Stability Beta — 2026-08-06)

- **Produktversion auf `0.9.0` Stability Beta angehoben** (`VERSION`, Komponentenmanifeste via `check_version_drift.py --write`, `uv.lock`, README-Badge, STATUS, ROADMAP, AGENTS). Grundlage: Deep-Audit-Stabilisierung Welle 1 ist gemergt (#1116, #1117, #1118), die Kern-Freigabekriterien (E2E als Required Check, Vue-v4-Konsolidierung, Provider-/Secret-SSoTs, Dependency-SSoT) sind erfüllt. Fünf Kriterien der 0.9.0-Liste bleiben offen und werden innerhalb der 0.9.x-Linie geschlossen (siehe `ROADMAP.md`).

### Fixed (v1→v2-Evidence-Migration schrieb einen contractwidrigen Section-Key — 2026-08-06)

- **`migrate_v1_to_v2` schrieb `schema_version` in jede Section, obwohl `ReportSectionModel` strict ist (`extra="forbid"`) und das Feld nicht kennt — die Migration machte damit genau die v1-Maps unlesbar, die sie retten sollte** (`GET /api/report/<id>/evidence` antwortete HTTP 400 mit `Extra inputs are not permitted`). Die Schema-Version gehört an die Map, nicht an jede Section (Variante 1 aus #1037): Die Migration schreibt den Section-Key nicht mehr und entfernt ihn zusätzlich aus Bestandsdaten — auch bei Maps, die bereits auf Top-Level-v2 stehen, weil der In-Memory-Migrationspfad (`report_agent/workflow.py`) vergiftete v2-Bestände persistiert haben kann, für die der frühere Early-Return die Heilung übersprungen hätte. (#1037)
### Fixed (`/simulation/start` hinterließ einen Phantom-Run bei fehlender `simulation_config` — 2026-08-06)

- **Fehlte die persistierte `simulation_config` (z. B. weil `/prepare` nie lief), lehnte `_apply_route_to_simulation_config` mit 404 `simulation_not_prepared` ab, ohne den in Phase 5 bereits registrierten Run als `failed` zu markieren.** Der Run blieb als nicht ausführbarer Geisterlauf in der Run-Liste stehen. Vor dem `raise` markiert die Funktion den Run jetzt best-effort als `failed` — dieselbe Vorlage (`try`/`except` mit Log-Warnung statt hartem Fehler), die der API-Key-Guard in `_resolve_start_route` bereits für den analogen Fall nutzt. Die HTTP-Antwort (404, `simulation_not_prepared`) bleibt unverändert. (#1094)
### Security (Transport-Security-Gate auch für Embedding-Pfade — 2026-08-06)

- **Die Embedding-Pfade bauten weiterhin ungeprüfte credential-behaftete Requests, obwohl #1103 das Transport-Security-Gate für LLM- und Discovery-Pfade eingeführt hatte.** `ensure_credentialed_transport_security` läuft jetzt auch vor jedem credential-behafteten Embedding-Request: im `EmbeddingService` (Konstruktor, analog `LLMClient`), in den drei Embedding-Probe-Adaptern (OpenAI-kompatibel, Ollama, Gemini — eine Gate-Ablehnung wird auf `status="unavailable"` mit sanitisierter Begründung gemappt, weil das Probe-Protokoll Status statt Exceptions meldet) und im Ollama-Modell-Download `pull_model` (Re-Raise als `OllamaPullError`, damit der Endpoint seine bestehende 4xx-Behandlung behält). Identische Policy wie #1103 inklusive `AGORA_LLM_ALLOW_INSECURE_HTTP`-Ausnahme, kein neues Regelwerk. (#1110)

### Security (HTTPS für credential-behaftete LLM-Endpoints erzwingen — 2026-08-05)

- **`LLMClient` und die LLM-Discovery-Pfade (`ModelCatalogService`, Provider-Connection-Adapter) sendeten `Authorization: Bearer <api_key>` auch an `http://`-Endpoints, ohne den Host zu prüfen (CWE-319) — bei einer öffentlich erreichbaren, versehentlich auf `http://` konfigurierten `base_url` ginge der API-Key im Klartext über die Leitung.** Ein neues, zentrales Gate (`ensure_credentialed_transport_security`, `backend/app/llm/transport_security.py`) läuft jetzt vor jedem credential-behafteten Request und lässt `http://` nur für nachweislich lokale/private Hosts zu (`localhost`, Docker-Compose-Servicenamen, Docker-Host-Gateway-Namen, Loopback, RFC1918, CGNAT/Tailscale-Bereich, Link-Local). Gegen alle anderen Hosts bricht ein unverschlüsselter Request mit einem credential-behafteten Key jetzt mit `InsecureTransportError` ab — fail-closed auch bei unparsebaren URLs. Für dokumentierte Ausnahmen (z. B. ein bewusst unverschlüsseltes internes Gateway ohne TLS-Terminierung) steht `AGORA_LLM_ALLOW_INSECURE_HTTP` zur Verfügung; Default bleibt sicher, die Ausnahme loggt eine sanitisierte Warnung statt still durchzulassen. (#1103)

### Fixed (kollidierende `gap_id`-Vergabe bei der Legacy-Claim-Migration — 2026-08-05)

- **`migrate_legacy_claims_to_anchored` vergab neue `gap_id`-Werte über `len(data_gaps) + 1` statt über den tatsächlichen Bestand.** Bei lückenhaft nummerierten Bestands-Gaps (z. B. `gap_01`, `gap_03`) erzeugte das erneut `gap_03` — ein Duplikat. Die Vergabe ermittelt jetzt pro Section das höchste vorhandene `gap_<n>`-Suffix und sichert zusätzlich gegen das Set der bereits vergebenen IDs ab, auch bei mehreren neuen Gaps in derselben Migration. (#986)
### Fixed (Persona-Generierung schickte das Routing-Modell an den `.env`-Endpoint — 2026-08-05)

- **Eine über das Workspace-Routing gewählte Provider-Route (z. B. OpenAI) lief bei der Persona-Generierung trotzdem gegen den `.env`-Endpoint (lokaler Ollama-Gateway) — HTTP 404 und stiller regelbasierter Fallback für alle Personas.** `workspace_llm_routing.json` persistiert pro Route nur `provider_id` + `model`; die Base-URL gehört zur Provider-Connection, wurde aber nirgends aufgelöst: `ResolvedRoute.base_url_sanitized` blieb `None`, und `OasisProfileGenerator` füllte die Lücke mit `Config.LLM_BASE_URL`, während Modell und API-Key aus der Route stammten. `StageModelRouter` löst die Base-URL jetzt aus der Provider-Connection im Store auf (derselbe Lookup, den der OASIS-Subprozess-Pfad bereits nutzt); eine explizite `provider_options.base_url` behält Vorrang. Findet auch der Store keine URL, bricht `_resolve_llm_connection` mit einer handlungsleitenden Meldung ab, statt still `(key, None)` zurückzugeben. Nachfolger von #1101/#1102, die nur den `LLMClient`-Konstruktor fixten. Bestehende Runs behalten ihre gelockte Route — der Fix greift für neue Runs. (#1104)

### Fixed (GPT-5-/o-Reasoning-Modelle brachen jeden Run mit 400 `unsupported_value` ab — 2026-08-05)

- **Jeder Run gegen OpenAI-Reasoning-Modelle (GPT-5-Familie, o1/o3/o4) scheiterte sofort mit `400 unsupported_value` auf `param=temperature`.** `LLMClient` sendet feste `temperature`-Werte (`chat` 0.7, `describe_image` 0.3, `chat_json` 0.3); diese Modelle akzeptieren ausschließlich den Default (1) und lehnen jeden expliziten Wert ab. `chat()`, `describe_image()` und `chat_json()` lassen den `temperature`-Key jetzt weg, wenn das Zielmodell zur GPT-5-/o-Familie gehört (`omits_temperature`, analog zur bestehenden `max_completion_tokens`-Heuristik) — für noch unbekannte Modelle fängt ein einmaliger Retry ohne `temperature` denselben 400 zusätzlich ab. (#1096)
- **`chat_json()` deutete denselben 400er bisher als fehlenden Strict-Schema-Support und fiel grundlos auf `json_object` zurück.** OpenAIs Fehlertext für den `temperature`-Quirk enthält dieselben Wörter ("unsupported", "not supported") wie die Heuristik für "Provider kann kein `json_schema`" — die irreführende Warnung `strict json_schema not supported by provider` erschien, obwohl das Schema nie das Problem war. Ein `temperature`-400 wird jetzt vor der Schema-Fallback-Prüfung erkannt und löst stattdessen einen Retry im selben `json_schema`-Modus aus.
- **Fehlerdiagnose für zukünftige 400er verbessert:** Ein `BadRequestError` loggt jetzt `message`, `code` und `param` aus dem strukturierten API-Fehlerbody, statt nur `error_type=BadRequestError`.

### Fixed (ein fertig geschriebener Report starb nach 35 Minuten an sechs Hypothesen zu viel — 2026-08-04)

- **`Report generation failed: 1 validation error for EvidenceMapModel`, nachdem alle sechs Abschnitte bereits persistiert waren.** `dedup_and_cap_hypotheses` kappt die sichtbaren Hypothesen auf fünf, reichte den Überhang aber ungekappt als Appendix weiter. `ReportSectionModel.hypotheses_appendix` erlaubt fünfzig; ein Abschnitt mit 56 Hypothesen ließ die abschließende Validierung scheitern und damit den gesamten Lauf.
- **Der Producer hält sich an den Vertrag, statt den Vertrag zu lockern.** Die Grenze trägt eine Begründung — sie verhindert unbegrenzte Persistenz bei fehlerhaften LLM-Outputs —, und 56 Hypothesen in einem Abschnitt sind genau der Fall, für den sie geschrieben wurde. Sie anzuheben hätte das Symptom wegdefiniert.
- **Welche fünfzig überleben, ist ehrlicher beschrieben als zunächst behauptet.** Der erste Anlauf hielt fest, der Cap verwerfe „die schwächsten Einträge nach Confidence". Das stimmt für die Produktion nicht: keiner der drei Erzeuger setzt `confidence_score`, weil der strict-Contract das Feld nicht kennt. `_sort_key` liest dort durchgängig 0.0, effektiv sortiert allein die Zahl der Evidence-Vorschläge, und bei Gleichstand bleibt die Erzeugungsreihenfolge stehen. Der Cap trifft damit die letzten einer nur schwach qualitätskorrelierten Reihenfolge. Das bleibt bewusst so — der akute Defekt ist der Abbruch, nicht die Auswahl —, ist aber im Code und im Log-Text benannt statt beschönigt. Ein belastbares Ranking-Signal über die Producer-Grenze zu tragen ist [#1083](https://github.com/arn0ld87/agora/issues/1083).
- **Die Kappung wird protokolliert.** Stilles Abschneiden liest sich beim nächsten Blick in den Report wie Vollständigkeit.
- **Die Testlücke war der Grund, warum es bis in einen echten Lauf durchschlug.** Die vier vorhandenen Fälle gingen bis zwölf Hypothesen; die Contract-Grenze berührte keiner. Neben dem Fall mit 56 Einträgen prüft jetzt ein zweiter, produktionsnah geformter Fall ohne `confidence_score`, dass das Ergebnis tatsächlich durch `EvidenceMapModel` läuft — genau die Validierung, an der der Lauf zerbrach.
### Fixed (alle Post-Simulations-Interviews scheiterten an einem fehlenden `/v1` — 2026-08-04)

- **Im Lauf `sim_d27370937936` schlug jedes der 30 Persona-Interviews mit `404 page not found` fehl.** `LLMClient` baut seinen OpenAI-SDK-Client aus der rohen `base_url` der Connection und ruft `POST {base_url}/chat/completions`. Ollama-Connections führen die URL aber an der Server-Wurzel, weil die Modell-Discovery `/api/tags` direkt daranhängt — über den OpenAI-Compat-Pfad landet der Call damit auf einer Route, die es bei Ollama nicht gibt. Die Antwort ist kein JSON-Fehler, sondern Ollamas Plaintext-404, den das SDK unverändert durchreicht.
- **Getroffen hat es ausschließlich `LLMClient.chat`.** `chat_json` routet bei Ollama auf den nativen `/api/chat`-Schema-Pfad, für den die URL *ohne* `/v1* gerade richtig ist; der Report-Agent lief im selben Lauf über MiniMax und war ohnehin nicht betroffen. Der Interview-Direktpfad nutzt bewusst `chat()`, weil eine Interview-Antwort Freitext ist — und war damit der einzige Consumer in der Lücke. Das Fehlerbild „Ontologie und Report laufen, Interviews nicht" hat genau hier seine Ursache.
- **Die Kanonisierung hängt am URL-Signal, nicht am Modellnamen.** `detect_provider(mode="http")` stuft schon ein `:cloud`-Modelltag als Ollama ein. Für die Provider-Wahl ist das richtig, für die Endpunkt-Frage nicht: ein `openai_compatible`-Gateway, das an seiner Wurzel lauscht und ein Ollama-Modell durchreicht — LiteLLM und vLLM tun das —, hätte ein `/v1` bekommen und wäre damit erst durch diesen Fix kaputtgegangen. `openai_compat_base_url()` prüft deshalb Hostname und Port exakt, wie es die Registry seit CodeQL #750 auch für MiniMax tut. Bekannte Grenze: ein selbstgehostetes Ollama auf einem Nicht-Standard-Port trägt kein URL-Signal und bleibt unkanonisiert — dieser Fall ist heute so kaputt wie vorher, ihn über den Modellnamen aufzufangen würde die Gateway-Regression eintauschen.
- **`self.base_url` bleibt roh.** Provider-Detection, das Invocation-Log und der native `/api/chat`-Pfad hängen daran; nur der SDK-Konstruktor bekommt die kanonisierte Form.
- **Der Katalog-Default für Ollama Cloud bleibt bewusst ohne `/v1`.** Ein Suffix dort würde die Modell-Discovery zu `/v1/api/tags` verbiegen, weil `provider_connections/adapters.py` den Endpunktpfad ungestrippt anhängt. Zwei Konsumenten teilen sich dieselbe URL mit unvereinbaren Erwartungen — ein Kommentar hält das fest, damit die scheinbar fehlende Korrektur nicht später „repariert" wird. Nebenbefund aus derselben Analyse: eine gespeicherte Ollama-Cloud-Connection *mit* `/v1` steht aus genau diesem Grund dauerhaft auf `disconnected`.
- **Anthropic ist bewusst nicht Teil des Fixes.** Der Provider hat keinen Chat-Adapter und wird von `detect_provider(mode="http")` nicht erkannt; seine Katalog-URL ist zwar ebenfalls unvollständig, aber ein `/v1` allein macht ihn nicht funktionsfähig, und ein unverifizierter Pfad soll nicht so aussehen.
### Fixed (acht Tests prüften die lokale Entwicklerkonfiguration statt die Defaults — 2026-08-04)

- **Das lokale Pre-Push-Gate war auf einer Maschine mit gepflegter `.env` nicht grün zu bekommen, in CI dagegen unauffällig.** Acht Tests lasen Betriebswerte statt Code-Defaults: fünf zur Auflösung von `AGORA_PERSONA_DETAIL_LEVEL`, zwei zu den Neo4j-Pool-Kwargs, einer zur `max_tokens`-Ableitung der Persona-Generierung. In CI existieren weder `.env` noch `backend/instance/settings.json`, dort greifen die Defaults ohnehin — der Defekt konnte deshalb beliebig lange unentdeckt bleiben und traf nur den, der lokal entwickelt. Weil das Gate mit `-x` abbricht, wurde nach jedem Fix die nächste Fundstelle sichtbar: 75 → 783 → 2113 → 2646 → 3776 gelaufene Tests.
- **Zwei verschiedene Ursachen, zwei verschiedene Reparaturen.** Beim `settings_layer` schlägt der File-Layer `instance/settings.json` die Umgebungsvariable — betroffen waren deshalb auch die Tests, die den Wert per `monkeypatch.setenv` explizit setzen. Die neue Fixture `hermetic_settings` schiebt eine `SettingsService`-Instanz auf ein leeres `tmp_path` unter; `SettingsService` nimmt genau dafür einen `instance_path` entgegen, und sein Docstring nennt diesen Testfall ausdrücklich, nur genutzt hatte es niemand. Bei `Config` dagegen stehen die Pool-Kwargs seit dem Klassen-Import als Attribute fest, `delenv` kommt zu spät.
- **Die naheliegende Reparatur der Pool-Tests hätte deren Assertion entwertet.** Die Config-Attribute auf die erwarteten Werte zu setzen macht die Tests grün, aber blind: Wird ein Produktions-Default versehentlich geändert, überschreibt die Fixture ihn vor der Instanziierung und alle Assertions halten weiter. Stattdessen werden die fünf Pool-Variablen aus der Umgebung entfernt und `Config` neu geladen. Dabei ist ein zweiter Schritt nötig, der beim ersten Versuch fehlte: `config.py` ruft beim Import `load_dotenv(override=False)` auf und schreibt die gerade entfernten Werte aus der `.env` zurück — der Reload machte das `delenv` wieder rückgängig. `load_dotenv` wird deshalb für die Dauer des Reloads neutralisiert.
- **Der Lazy-Reconnect-Test prüfte nur drei der fünf durchgereichten Pool-Werte.** `connection_acquisition_timeout`, `connection_timeout` und `max_connection_lifetime` waren nach dem Fork-Reset ungeprüft; die Assertions sind ergänzt.
- **Keine Assertion wurde abgeschwächt.** Die Env-Override-Pfade decken unverändert die vorhandenen `test_env_overrides_*`-Tests ab.
- **Nicht angefasst:** `.env` setzt `AGORA_INSTANCE_DIR` auf den Container-Pfad `/app/backend/instance`, der lokal nicht schreibbar ist und `test_graph_ontology_persists_project_meta` mit `OSError: Read-only file system` scheitern lässt. Das ist eine maschinenlokale Konfigurationsdatei, kein Repo-Defekt.
### Fixed (ein Debug-Leak, ein toter Abbrechen-Button und ein Gate, das seit vier Läufen an einer Infrastrukturzeile scheiterte — 2026-08-04)

- **Mit `FLASK_DEBUG=true` hängte jede 500er- und 504er-Antwort den Exception-String als `debug_error` an den Body.** Exception-Strings tragen Dateipfade, Konfigurationswerte und potenziell Schlüsselmaterial; der Modul-Docstring von [`api_responses.py`](backend/app/utils/api_responses.py) versprach in derselben Datei ausdrücklich das Gegenteil. `_debug_extra` und seine vier Aufrufstellen sind ersatzlos entfallen — kein neues Flag, kein abgeschwächter Ersatz. Diagnose bleibt im Server-Log, wie `json_error` das für `include_traceback` seit jeher dokumentiert. (#1058)
- **Der Defekt konnte jeden Pull Request passieren, weil PR-Gate und main-Job unter verschiedenen DEBUG-Werten liefen.** Der Test-Step im `backend-pr-gate` überschrieb `FLASK_DEBUG` auf `false`, der `backend`-Job auf `main` fuhr dieselbe Suite mit `true`. Ein nur unter DEBUG=true auftretender Defekt brach damit systematisch erst nach dem Merge. Beide Jobs erben jetzt denselben Wert; Tests, deren Verhalten vom Debug-Modus abhängt, parametrisieren ihn selbst, statt sich auf die Job-Umgebung zu verlassen.
- **Der Abbrechen-Button in Schritt 3 antwortete immer HTTP 400 und brach nichts ab.** Das Frontend kennt nur die `simulation_id` und schickte sie an `POST /api/runs/<id>/cancel`; `validate_run_id` prüft gegen `^run_[a-f0-9]{12}$`, `simulation_id`s werden aber als `sim_{uuid4().hex[:12]}` vergeben. Kein `create_run`-Aufruf im Repository setzt `run_id` explizit — die einzige Verknüpfung ist `linked_ids.simulation_id`. `cancel_run` löst `sim_`-IDs jetzt über denselben Registry-Pfad auf, den `stop_simulation` bereits nutzt. Unbekannte IDs bleiben 404, formfremde bleiben 400, und das Feld `run_id` in der 202-Antwort trägt immer die aufgelöste `run_`-ID. **Nicht behoben — der Button erreicht den Abbruchmechanismus jetzt, aber der greift für diesen Run-Typ nicht:** `is_cancel_requested` hat im gesamten Backend genau einen Consumer, [`report_agent/workflow.py`](backend/app/services/report_agent/workflow.py); `simulation_runner.py` enthält kein Cancel-Signal. Ein Cancel auf eine laufende Simulation wird registriert und im UI angezeigt, beendet die Simulation aber nicht. Das ist ein Bestandsdefekt neben diesem Fix, kein Nebeneffekt von ihm — ausgelagert als [#1082](https://github.com/arn0ld87/agora/issues/1082).
- **Der Frontend-Test hat die falsche ID-Form zementiert.** Der `cancelRun`-Mock lieferte `run_id: 'sim_test_smoke'` zurück — ein Wert, der weder `validate_run_id` noch `validate_simulation_id` passiert. Mock und Fixture nutzen jetzt echte ID-Formate, und der Cancel-Test assertiert das Format des übergebenen Werts.
- **Der Step „Run Python dependency audit" scheiterte auf jedem `main`-Lauf seit dem 3. August — an keiner einzigen Sicherheitslücke.** `uv export` pinnt Torch marker-getrennt (`torch==2.13.0+cpu ; sys_platform == 'linux'`), und PyPI weist PEP-440-Local-Version-Labels beim Upload grundsätzlich zurück. `pip-audit` löste die Zeile gegen PyPI auf, fand nichts und meldete unter `--strict` „Dependency not found on PyPI and could not be audited" — Exit 1. Lokal auf macOS greift der komplementäre Marker, deshalb meldete der Nachbau desselben Kommandos „No known vulnerabilities found". Ein `--extra-index-url` repariert das nicht: `pip-audit` fragt den Vulnerability-Service, nicht den Paket-Index. [`normalize_audit_requirements.py`](backend/scripts/normalize_audit_requirements.py) strippt das Local-Label vor dem Audit; `--strict` bleibt scharf, kein `continue-on-error`, kein `--ignore-vuln`. Derselbe Defekt in `cve-monitor.yml` — dort bis zum Hardstop als informational geschluckt, `AUDIT_EC: 1` in jedem Lauf — ist als [#1075](https://github.com/arn0ld87/agora/issues/1075) ausgelagert.
- **`assertStubModeActive` hat nichts zugesichert.** Die Funktion las `AGORA_E2E_LLM_MODE` aus dem *Playwright*-Prozess — ein Wert, der über den Zustand des Backends nichts aussagt —, kehrte bei `!res.ok()` früh zurück und verschluckte jeden Fehler im `catch`. Fünf Specs hingen an dieser Zusicherung und konnten grün durchlaufen, obwohl das Backend gegen einen echten Provider lief. `GET /api/status` liefert jetzt einen `e2e`-Teilbaum (`llm_mode`, `stub_active`), gespeist aus der Umgebung des Backend-Prozesses; der Helper assertiert hart darauf und wirft, wenn der Stub nicht aktiv ist. Nebeneffekt für den Betrieb: eine Produktivinstanz, die versehentlich mit Stub-LLM läuft, produziert bisher still erfundene Berichte — das ist jetzt ablesbar.
- **Sieben Tests liefen rot mit, ohne jemanden zu stören.** Drei riefen `_phase_generate_config` weiterhin ohne aufgelöste Route auf, nachdem `_resolve_llm_connection` die stille Provider-Vertauschung mit einem harten `ValueError` abgefangen hatte. Vier mockten `generator.client`, obwohl `_generate_profile_with_llm` seit der `chat_json`-Migration intern einen `LLMClient` konstruiert — der Mock war wirkungslos, die Tests riefen den echten Endpunkt (HTTP 401 gegen `api.minimax.io`) und fielen danach still auf `rule-based generation` zurück. Sie trugen keinen `llm`-Marker und liefen deshalb in jedem CI-Durchgang mit. Alle sieben sind aus der Deselect-Liste des PR-Gates raus.
- **Das Komplexitäts-Gate war rot und deshalb wirkungslos.** Zwölf Funktionen mit radon-Rang D+ standen außerhalb der Allowlist — Bestandskomplexität aus vorangegangenen Service-Zusammenführungen, keine davon in einem aktuellen Slice entstanden. Sie sind mit gemessenen Werten, Datum und Aufgabenkatalog eingetragen; ab jetzt schlägt das Gate nur noch bei *neuer* Komplexität an. Die beiden Rang-F-Handler kommen nicht neu hinzu: sie stehen seit dem 14. Mai in der Datei, damals mit `E (cc=33)` vermessen, inzwischen `F (cc=68)` bzw. `F (cc=65)`. Die Allowlist prüft nur, *ob* eine Funktion geduldet ist, nicht *wie stark* sie gewachsen ist — dieser Zuwachs ist nie aufgefallen. Refactor-Auftrag als [#1079](https://github.com/arn0ld87/agora/issues/1079) und [#1080](https://github.com/arn0ld87/agora/issues/1080).

### Fixed (der self-hosted CI-Runner hatte nie Docker-Zugriff — 2026-08-03)

- **Jeder `push`-auf-`main`-Lauf des Docker-Workflows schlug fehl, seit der self-hosted Runner eingerichtet wurde.** `Set up Docker Buildx` brach mit `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` ab. Der Runner läuft als Container, in den der Docker-Socket nie gemountet wurde — `/var/run/docker.sock` existiert dort schlicht nicht. Sein einziger dokumentierter Zweck war „native arm64-Docker-Builds ohne QEMU", also genau das, was ohne Docker-Zugriff unmöglich ist. Aufgefallen ist es nicht, weil der `publish`-Job ohnehin nur auf Release-/RC-Branches und Tags scharf ist und die Deployments auf `armserver` lokal bauen. Praktische Folge war trotzdem, dass kein Image mehr nach GHCR gelangte.
- **Die naheliegende Reparatur wäre schlimmer gewesen als der Defekt.** Ein Socket-Mount hätte den Runner funktionsfähig gemacht und ihm zugleich Root-äquivalenten Zugriff auf den Host gegeben, der Vaultwarden, Stalwart, n8n und den produktiven Agora-Stack trägt. Bei einem öffentlichen Repository beruhte der Schutz davor auf einer einzigen Zeile — dem `runs-on`-Ausdruck, der `pull_request` auf `ubuntu-latest` umleitet. Eine spätere Trigger-Ergänzung hätte ihn aufgehoben, ohne dass es beim Review auffallen muss.
- **Der arm64-Bedarf war ohnehin nicht belegt.** `build-only` reicht sein Image an `prod-proxy-smoke` weiter, und der läuft auf `ubuntu-latest` — ein arm64-Artefakt startet dort nicht. `publish` baut ebenfalls auf `ubuntu-latest`, das Image in GHCR war also immer amd64, und die Deployments auf `armserver` bauen lokal statt aus der Registry. Der Mangel fiel nie auf, weil `build-only` stets vorher abbrach und der Smoke-Job nie zum Zug kam. Der Workflow läuft jetzt vollständig auf `ubuntu-latest`; werden echte arm64-Images gebraucht, gehört das als Multi-Platform-Build in den publish-Job, nicht als abweichender Runner für einen einzelnen Job. `step-security/harden-runner` verliert seinen `if`-Guard und schützt jetzt auch den push-Pfad — den einzigen, der veröffentlicht; die Einschränkung existierte nur, weil die maschinenweiten Egress-Regeln sonst den produktiven Traffic auf dem self-hosted Host getroffen hätten.
- **`get.anchore.io` fehlte in beiden harden-runner-Allowlists.** Das ist der primäre Download-Host des syft-Installers; `toolbox-data.anchore.io` deckt ihn nicht ab. Der SBOM-Step lief deshalb in `received HTTP status=000` und überlebte nur über einen Fallback auf `raw.githubusercontent.com`.
- **Das Runbook [`self-hosted-runner-meinserver.md`](docs/runbooks/self-hosted-runner-meinserver.md) bleibt bestehen**, jetzt als Außerbetriebnahme-Dokument mit Rückbau-Anleitung und den vier Fragen, die vor einer Wiederinbetriebnahme zu beantworten sind. Die Sicherheitsabwägung für self-hosted Runner an einem public Repository ist bei jeder Neuauflage dieselbe und sollte nicht neu hergeleitet werden müssen.
### Changed (torch aus dem CPU-Index — prod-Image 8,8 GB auf 2,07 GB — 2026-08-03)

- **4,4 GB von 5,3 GB der Backend-venv waren CUDA-Laufzeit für eine GPU, die es nirgends gibt.** Gemessen im laufenden Container: `nvidia/` 2,9 GB, `torch/` 859 MB, `triton/` 650 MB. Ursache ist der Dependency-Marker des PyPI-Wheels: torch deklariert seine CUDA-Abhängigkeiten mit `sys_platform == 'linux'` ohne Architektur- oder Hardware-Einschränkung, uv installiert sie im Container also mit. Agora betreibt seine Modelle über Ollama und OpenAI-kompatible Endpunkte, nicht in-process auf einer GPU.
- **torch kommt jetzt aus PyTorchs CPU-Index**, in derselben Version 2.13.0 und mit Wheels für alle drei Zielplattformen (`manylinux_2_28_aarch64`, `manylinux_2_28_x86_64`, `macosx_14_0_arm64`). Die Umlenkung gilt nur für Linux — auf macOS greifen die CUDA-Marker ohnehin nicht. Ergebnis: prod-Image 8,8 GB → 2,07 GB, venv 5,2 GB → 1,4 GB, 187 → 168 Pakete, Wheel-Download 4m06s → 33s, Installation 1m15s → 10s.
- **torch steht dafür in `[project.dependencies]`, obwohl es kein Produktionscode importiert.** `[tool.uv.sources]` wirkt ausschließlich auf direkt deklarierte Dependencies; die Bezugsquelle einer rein transitiven Abhängigkeit lässt sich anders nicht umlenken. Der Eintrag trägt einen Kommentar, der das erklärt — ohne ihn liest er sich wie ein Versehen. Außerhalb von `app/` wird torch übrigens sehr wohl direkt importiert (`tests/conftest.py`, lazy in `scripts/_sim_common.py`); beide Pfade laufen mit dem CPU-Build unverändert.
- **Die Index-Zuordnung überlebt `uv export` nicht.** Das requirements-txt-Format kennt keine Bezugsquelle pro Paket, der Export schreibt `torch==2.13.0+cpu` ohne jede Index-Direktive. Der wöchentliche `pip-audit` in `cve-monitor.yml` hätte diese Version gegen PyPI aufzulösen versucht, wo es kein `+cpu` gibt. Der Job stellt die verlorene Information jetzt über eine vorangestellte `--extra-index-url`-Zeile wieder her; PyPI bleibt Default-Index.
- **Neue Bezugsquelle heißt neuer Egress-Endpunkt.** `harden-runner` blockiert per Default alles Nicht-Gelistete, und die erste Fassung ließ 13 Checks mit `Connection refused (os error 111)` scheitern — der Signatur des Blocks, nicht der eines fehlenden Wheels. Es sind zwei Hosts: `download.pytorch.org` liefert den Index, die Wheel-URLs darin zeigen auf `download-r2.pytorch.org`. Beide sind in allen 19 Allowlist-Blöcken ergänzt, die bereits `files.pythonhosted.org` führen.
- **Nebenwirkung auf die CI-Stabilität, die den eigentlichen Anlass lieferte.** Der `build-only`-Job trug einen Step „Platz auf dem Runner schaffen" mit der Notiz, das Prod-Image trage „die volle Backend-venv inklusive der CUDA-Wheels" und der Build breche „in genau dieser Kombination ohne Fehlermeldung ab (#994)". Genau dieses Bild trat weiter auf: mal kippte der SBOM-Step, mal der Artefakt-Upload, immer ohne Meldung — 16 von 40 Läufen des Workflows scheiterten. Mit dem kleineren Image läuft der Job in 7m38s durch. Der Platz-schaffen-Step bleibt vorerst stehen; ob er noch nötig ist, entscheidet sich erst nach mehreren stabilen Läufen.
### Fixed (CI: ein Gigabyte-Upload ohne Abnehmer und ein Job, der 30 Minuten schwieg — 2026-08-03)

- **`docker-image.yml::build-only` lud auf jedem Pull Request das komplette Prod-Image als Artefakt hoch, obwohl es dort niemand abholt.** Das Artefakt `docker-image` hat genau einen Konsumenten: `prod-proxy-smoke`. Dessen `if:`-Guard laesst nur `workflow_dispatch`, Tags und Release-/RC-Branches durch, `publish` haengt an ihm und wird mit ihm geskippt — auf einem PR-Lauf war der Upload also folgenlos. Folgenlos war nur sein *Ergebnis*: das Image traegt die volle Backend-venv inklusive der CUDA-Kette, und im Lauf `30825988931` (PR #1045) starb der Runner nach 1,64 GB hochgeladener Bytes mit „The runner has received a shutdown signal", nachdem der Job zuvor bereits zehn Minuten in Build, Trivy und SBOM verbracht hatte. Der Upload steht jetzt unter derselben Bedingung wie sein Konsument.
- **Die zweite Kopie des Images auf der Platte faellt weg, wo sie niemand braucht.** Nach `docker load` liegt das Image doppelt vor — als Tar unter `/tmp` und als Layer im Daemon —, waehrend die SBOM-Erzeugung laeuft. Braucht der Lauf das Artefakt nicht, wird der Tar direkt nach dem Laden freigegeben. Genau diese Kombination aus Tar, Daemon-Layern und Cache-Export war in #994 schon einmal ohne Fehlermeldung abgebrochen; der Runner-Speicher ist an dieser Stelle keine komfortable Reserve.
- **Die Trigger-Bedingung existiert damit an zwei Stellen — und wird zusammengehalten.** [`test_docker_image_artifact_gate.py`](backend/tests/contracts/test_docker_image_artifact_gate.py) vergleicht `build-only.env.IMAGE_ARTIFACT_NEEDED` zeichengleich mit dem `if:` von `prod-proxy-smoke`. Laufen sie auseinander, entsteht der teurere der beiden Fehler lautlos: Der Smoke-Test vor dem Registry-Push startet auf einem Release-Branch und findet kein Artefakt. Der Test liegt in `tests/contracts/`, weil nur dieses Verzeichnis im verpflichtenden PR-Gate laeuft, und parst Rohtext ohne `pyyaml` — dieselbe Begruendung wie in `test_ci_gate_parity.py`.
- **`e2e-smokes.yml` verschwieg, wo ein Job seine Zeit liess.** Im selben Lauf brauchte `Install Playwright browsers` in einem Job 10m48s, waehrend die sechs Geschwister desselben Laufs bei 20–31 s lagen; das restliche 25-min-Budget reichte fuer den eigentlichen Test nicht mehr, und der Job endete nach 30 Minuten als „cancelled" — ohne Hinweis auf den Verursacher. Alle sieben Installations-Steps tragen jetzt `timeout-minutes: 8`, das Sechzehnfache des beobachteten Normalfalls. Das macht keinen roten Lauf gruen: Es trennt einen langsamen Spiegel von einem defekten Runner und benennt den Schritt, statt das Job-Budget still aufzubrauchen.
- **Nicht angefasst:** die Ursache der Runner-Degradierung selbst — sie liegt ausserhalb des Repos. Die elf `e2e-smokes`-Laeufe vor dem betroffenen waren gruen; der Vorfall ist ein Infrastruktur-Ereignis, kein Defekt im Testcode. Ebenfalls offen bleibt, dass jeder E2E-Job das Chromium-Bundle ungecacht neu zieht.

### Changed (Container-Build: Context, Wheel-Caches und ein Cache-Killer im Frontend-Bundle — 2026-08-03)

- **Der Build-Context enthielt rund ein Gigabyte, das in keinem Image landet.** `backend/.cache`, `snapshots/`, `graphify-out/`, `backend/instance` und die mypy-/ruff-Caches standen nicht in `.dockerignore`. BuildKit überträgt den Context vollständig an den Daemon, bevor die erste Instruktion läuft — das war reine Wartezeit vor jedem Build, auch vor einem, der ausschließlich aus Cache-Treffern bestand. Der Context-Transfer liegt jetzt bei 95 kB.
- **`uv sync` und `bun install` luden bei jeder Lockfile-Änderung alles neu, auch das Unveränderte.** Im Dockerfile gab es keinen einzigen `--mount=type=cache`. Der Backend-Baum zieht über `camel-oasis → sentence-transformers → torch` eine CUDA-Kette, die im laufenden Container 4,4 GB der 5,3 GB großen venv ausmacht (`nvidia/` 2,9 GB, `torch/` 859 MB, `triton/` 650 MB) — und deren Downloads dominieren die Buildzeit nach jedem Dependency-Update. Alle drei Installationsschritte teilen sich jetzt einen Cache-Mount, sodass nur die tatsächlich geänderten Pakete über die Leitung gehen. `UV_LINK_MODE=copy` ist ergänzt, weil ein Cache-Mount ein eigenes Dateisystem ist: uv kann von dort nicht per Hardlink in die venv legen und warnt sonst bei jedem Build über den fehlgeschlagenen Versuch.
- **Cache-Mounts wirken nur, wenn die BuildKit-Garbage-Collection sie in Ruhe lässt.** Sie werden von keinem Layer referenziert und fliegen deshalb zuerst raus, sobald der Build-Cache über `defaultKeepStorage` liegt. Auf einem Host mit 20-GB-Ziel und 89 GB Ist-Stand blieben zwei aufeinanderfolgende Läufe bei 4m06s und 4m27s — der Mechanismus selbst ist isoliert nachgewiesen (8,0 s auf 3,3 s, Cache überlebte den Build). Wer nichts von der Änderung merkt, prüft zuerst `docker system df` gegen die GC-Policy des Hosts, nicht das Dockerfile.
- **In `frontend-build` invalidierte das Token-Gate die Dependency-Installation.** Der `RUN`-Block, der `ALLOW_BUILD_TIME_TOKEN`, `VITE_AGORA_TOKEN` und `VITE_UI_VERSION` auswertet, stand vor `bun install`. Ein geänderter Provenance-Marker genügte damit, um die vollständige Frontend-Installation neu zu fahren. Gate-Entscheidung und Vite-Build laufen jetzt hinter der Installation und in einer Shell; der Token-Wert bleibt eine Shell-Variable, statt den Umweg über `/tmp/.vite_token_env` zu nehmen. Am Verhalten ändert das nichts — beide Pfade sind am gebauten Bundle geprüft: Default liefert ein Bundle ohne Token, das Opt-In brennt Token und `VITE_UI_VERSION` ein.
- **Die Toolchain-Images sind auf Digests gepinnt.** `oven/bun:1` war ein Rolling-Tag: jeder Upstream-Push invalidierte die `base`-Stage und damit jede abgeleitete Stage, ohne dass sich im Repo etwas geändert hätte. Jetzt `1.3.14@sha256:e10577f0…`. `ghcr.io/astral-sh/uv:0.9.26` trägt denselben Zusatz, obwohl ein Versionstag in der Praxis stabil ist — beide Digests sind Manifest-List-Digests und decken `linux/amd64` wie `linux/arm64` ab, das Repository wird auf beiden gebaut.
- **Nicht angefasst:** die CUDA-Kette selbst. `torch`, `nvidia/*` und `triton` werden von keiner Stelle im Anwendungscode importiert — der einzige Treffer für `sentence_transformers` in `backend/app/` ist ein `warnings.filterwarnings`. Sie über einen CPU-Index oder einen Dependency-Override aus dem Image zu halten, ist der mit Abstand größte verbleibende Hebel, ändert aber `uv.lock` und gehört in einen eigenen Slice mit eigener Verifikation.

### Fixed (drei Wege, auf denen der konfigurierte Provider den Konsumenten nicht erreicht — 2026-08-03)

- **Ein Lauf gegen Ollama Cloud brach im OASIS-Preflight mit einem HTTP 404 ab, dessen Body eine HTML-Seite war.** Der Kommentar an der auslösenden Stelle behauptete, Ollama Cloud habe seinen OpenAI-Compat-`/v1`-Endpunkt abgeschafft und CAMELs `OllamaModel` spreche nativ `/api/chat`. Beide Hälften sind falsch: `camel/models/ollama_model.py` deklariert `class OllamaModel(OpenAICompatibleModel)`, baut einen `openai.OpenAI(base_url=url)`-Client und ruft `POST {base_url}/chat/completions`. Einen `/api/chat`-Pfad kennt CAMEL nicht. Weil der Kommentar das Gegenteil versprach, normalisierte niemand die URL — der Registry-Default `https://ollama.com` landete roh bei CAMEL, der Probe ging auf `https://ollama.com/chat/completions`, und Ollama antwortete mit seiner Marketing-404-Seite, die das OpenAI-SDK in einen `NotFoundError` verwandelte. Neu ist [`ensure_v1_suffix`](backend/app/llm/providers/registry.py) als Gegenstück zum vorhandenen `_strip_v1_suffix`; beide Formen der URL sind legitim, sie gehören nur zu verschiedenen Konsumenten. Agoras eigener HTTP-Pfad spricht wirklich nativ `/api/chat` und schneidet ein `/v1` ohnehin ab — dort ist die URL ohne Suffix korrekt und bleibt es.
- **Der bestehende Regressionstest hat den Defekt festgeschrieben.** `test_ollama_sets_url_and_api_key` setzte `LLM_BASE_URL=http://localhost:11434` und prüfte, dass genau dieser Wert bei `ModelFactory.create` ankommt. Er belegte die Durchreichung, nie die Erreichbarkeit — mit derselben URL wäre auch der lokale Lauf auf `…/chat/completions` gelaufen. Die Erwartung ist auf die normalisierte URL korrigiert.
- **Eine in der Oberfläche geänderte Base-URL erreichte den Simulationslauf nicht.** `LlmProviderRegistry.get_providers()` liefert laut eigenem Docstring statische, secret-freie Metadaten — also ausschließlich `definition.default_base_url` — und liest den Store nie. `build_route_subprocess_env` fiel direkt darauf zurück, sobald die Route keine eigene `base_url_sanitized` trug, was im Legacy-/Workspace-Default-Pfad ohne `ai_model_ref` der Normalfall ist. Wer unter Einstellungen → LLM-Anbieter eine abweichende URL pflegte, schrieb sie nach `provider_connections.json` und sah sie folgenlos verpuffen: das Eingabefeld nahm die Korrektur an, der Lauf ignorierte sie. Die Präzedenz ist jetzt Route > Store > Registry-Default; die Registry bleibt unangetastet und damit statisch. Ein unlesbarer Store degradiert auf den Default statt den Lauf zu kippen.
- **Die Persona-Generierung schickte das Modell der einen Route an den Endpunkt eines anderen Providers.** `_resolve_llm_connection` gab bei nicht auflösbarer Route `(None, None)` zurück, während `model_name` aus der Route weitergereicht wurde. `OasisProfileGenerator.__init__` füllte die Lücke aus `Config.LLM_BASE_URL` und `Config.LLM_API_KEY` — Ergebnis war eine Halb-Übergabe: Modell aus der UI-Route, Endpoint und Schlüssel aus der `.env`. Beobachtet als `deepseek-v4-flash:0731` gegen `https://api.minimax.io/v1` mit HTTP 401 über den gesamten Persona-Schritt. Der `#778`-Schutz greift dort nicht: er verhindert nur, dass der `.env`-Schlüssel zu einer *übergebenen* Fremd-URL einspringt; wird gar keine URL übergeben, stammen beide aus der `.env` — formal dieselbe Quelle, sachlich die falsche.
- **Sichtbar wurde davon nichts.** Jeder einzelne 401 fiel still auf `rule-based generation` zurück, und der Schritt meldete „30 Personas erfolgreich generiert", gefolgt von sechs nachgefüllten synthetischen Skeptikern. Ein Lauf mit durchgehend regelbasierten Platzhaltern war am Bildschirm nicht von einem gesunden zu unterscheiden — dieselbe Fehlerklasse wie in #1029, eine Ebene früher. `_resolve_llm_connection` bricht deshalb jetzt mit einer erklärenden Meldung ab, statt auf die `.env` auszuweichen. `use_llm_for_profiles=False` bleibt davon unberührt: eine bewusst abgewählte LLM-Generierung ist ein Wunsch und keine Fehlkonfiguration, und wird über `require=False` weiterhin regelbasiert bedient.
- **Nebenwirkung, bewusst in Kauf genommen:** Standalone- und Dev-Läufe, die sich bisher stillschweigend auf die `.env` verlassen haben, brechen künftig sichtbar ab, statt gegen einen unbeabsichtigten Provider zu laufen. Genau das ist der Zweck der Änderung.
### Fixed (JSON-Export verlor die gesamte Evidence-Map — 2026-08-03, Issue #987)

- **Der JSON-Export lieferte HTTP 200 und eine herunterladbare Datei mit `evidence: null`, wenn die Evidence-Map den Vertrag verletzte.** Ein einziger Bestands-Claim genügte, um den kompletten Evidence-Teil des Exports zu entleeren. Nichts an der Antwort wies darauf hin: der Envelope war schemakonform, der Zod-Spiegel im Frontend akzeptierte ihn (`evidence` ist optional), und der Nutzer lud eine Datei herunter, die er für vollständig halten musste. Der einzige Hinweis stand in einer `logger.warning` auf dem Server. Betroffener Nutzerpfad: Schritt 4 → „.json" → `useReportExports.downloadCombinedJson` → `GET /api/report/<id>/export?format=json`.
- **Ursache waren zwei Pfade für dieselbe Aufgabe.** Der Lese-Pfad `GET /api/report/<id>/evidence` fuhr die bindende Kette `migrate_v1_to_v2 → migrate_legacy_claims_to_anchored → migrate_medium_seed_only_claims_to_low` und validierte danach. [`report_export.py`](backend/app/services/report_export.py) rief nur `migrate_v1_to_v2` und fing die daraufhin unvermeidliche `ValidationError` ab. Persistierte Maps mit orphan- oder seed-only-Claims — genau die Fälle, für die die beiden anderen Migrationen existieren — passierten den Lese-Pfad und verschwanden im Export.
- **Die Reihenfolge steht jetzt an genau einer Stelle:** `normalize_persisted_evidence_map` in [`evidence_migrations.py`](backend/app/services/evidence_migrations.py) ist die kanonische Normalisierung; Lese-Pfad und Export rufen sie beide. Die Begründung für die Reihenfolge (#968/#963) ist mit umgezogen, statt in zwei Kommentaren zu leben.
- **Bleibt nach allen Migrationen ein Vertragsbruch, sagt der Envelope das.** Neu `EvidenceOmissionModel` ([`report_contract.py`](backend/app/contracts/report_contract.py)) im Feld `evidence_omitted` — Grund, menschenlesbare Ursache und die ersten Validierungsfehler. Additiv mit Default `null`, ältere Envelopes bleiben gültig. Der Fallback bleibt bestehen: der Report-Rumpf ist unbeschädigt, ein Export ohne Evidence ist besser als gar keiner. Er ist nur nicht länger stumm. Abgegrenzt gegen `EvidenceDegradationModel` (#1006), das die Abstufung eines *einzelnen Claims* protokolliert — hier ist die *gesamte Map* nicht auslieferbar.
- **Der Hinweis erreicht den Nutzer — gerendert, nicht geloggt.** Zod-Spiegel in [`reportContract.ts`](frontend/src/contracts/reportContract.ts), Consumer in [`useReportExports.ts`](frontend/src/composables/useReportExports.ts), sichtbarer `role="alert"`-Block in [`Step4Report.vue`](frontend/src/components/v4/steps/Step4Report.vue). Die erste Fassung rief `addLog()` — das emittiert dort nur ein `add-log`, und der einzige produktive Mount (`StepReportView.vue`) hängt keinen Listener daran und rendert `systemLogs` nicht. Der Hinweis wäre nirgends angekommen: dieselbe Fehlerklasse, eine Ebene höher. Der Text kommt aus `vue-i18n` (`step4.export.evidenceOmitted.*`, de und en), nicht aus dem Backend — `detail` bleibt im Vertrag, ist aber ausdrücklich kein UI-String, sondern die Erklärung für den, der die exportierte Datei später ohne Agora öffnet.
- **Eine vorhandene, aber leere `evidence-map.json` gilt nicht mehr als fehlendes Artefakt.** `if raw_evidence_map` ist für `{}` falsy — Migration und Validierung wurden übersprungen, der Envelope trug `evidence: null` **und** `evidence_omitted: null`. Derselbe stille Verlust eine Ebene tiefer; jetzt `is not None`.
- **Die Regressionstests fahren den HTTP-Endpunkt, nicht die Migrationsfunktion.** Das war der Kern des Defekts: `migrate_legacy_claims_to_anchored` hatte durchgehend grüne Unit-Tests, während der Export sie nicht aufrief. [`test_report_export_evidence_parity.py`](backend/tests/api/test_report_export_evidence_parity.py) exportiert über die Route und vergleicht das Ergebnis zusätzlich mit dem Lese-Pfad — wird eine der beiden Stellen künftig einseitig geändert, geht dieser Vergleich rot. Der Frontend-Test nutzt als Fixture die wörtliche Antwort des echten `ReportExportService`, nicht ein handgebautes Objekt. Der Test zur Sichtbarkeit mountet `Step4Report` und prüft das gerenderte Ergebnis statt eines Callback-Aufrufs; seine Erwartung zieht er aus der echten `de.json` statt aus dem flachen i18n-Stub der Testdatei — gegen einen Stub geprüfte Übersetzungen sagen über das ausgelieferte Locale nichts aus.
- **Nicht angefasst:** die Evidence-Sub-Routen `/evidence/<section>` und `/evidence/<section>/<claim>` migrieren weiterhin gar nicht ([#967](https://github.com/arn0ld87/agora/issues/967)); ZIP- und CSV-Export schreiben die Roh-Map ohne Migration ([#1036](https://github.com/arn0ld87/agora/issues/1036)); `migrate_v1_to_v2` schreibt ein `schema_version` in jede Section, das `ReportSectionModel` verbietet — echte v1-Maps scheitern dadurch auf beiden Pfaden ([#1037](https://github.com/arn0ld87/agora/issues/1037)).
### Fixed (Persona-Eignung und ein Fortschrittszähler, der zu seinem Ziel passt — 2026-08-03, Issue #1034)

- **Länder, Produkte und die Analyseplattform selbst wurden zu Personas.** In der Galerie standen „Mitarbeiter:in bei **USA**", „bei **Europäische Union**", „bei **Agora**" und „bei **KI-Lernassistent**" gleichberechtigt neben fachlich sinnvollen Stakeholdern und wurden in der Simulation gleich gewichtet. Ursache ist ein Catch-all: [`oasis_profile_generator.py`](backend/app/services/oasis_profile_generator.py) kennt `INDIVIDUAL_ENTITY_TYPES` und `GROUP_ENTITY_TYPES`, und jeder nicht gelistete `entity_type` fällt über den `else`-Zweig in den institutionellen Pfad, der eine Person erzeugt, die „FOR the following organization/group" spricht. `EntityReader.filter_defined_entities` filtert davor nur label-technisch — „hat überhaupt ein Label außer `Entity`/`Node`" — und trifft keine fachliche Aussage.
- **[`persona_eligibility.py`](backend/app/services/persona_eligibility.py) filtert zweistufig und bewusst konservativ.** Eine harte Blockliste schließt Typen ohne menschlichen Träger aus (Länder, Orte, Produkte, Technologien, Konzepte, Dokumente). Ein unbekannter `entity_type` wird dagegen **nicht** ausgeschlossen, sondern protokolliert: Die Ontologie erzeugt freie, auch deutschsprachige Labels, und eine harte Allowlist hätte bei `Behörde` oder `Verband` den kompletten Pool geleert — genau die Fehlerklasse stiller Degradierung, die #1029 gerade beseitigt hat.
- **Der Filter greift in beiden Zählpfaden.** Der synchrone Preview in [`simulation_prepare.py`](backend/app/api/simulation_prepare.py) liefert den Nenner für die Oberfläche, `_phase_read_entities` die Menge für die Generierung. Beide rufen dieselbe Funktion; ein Fix in nur einem wäre wirkungslos geblieben.
- **Der Degradations-Kanal aus #1029 war im Prepare-Pfad nie verdrahtet.** `generate_profiles_from_entities` nimmt seit Slice 12 einen `DegradationCollector` entgegen, [`prepare_service.py`](backend/app/services/prepare_service.py) übergab aber keinen — `_report_persona_degradation` lief im produktiven Pfad also nie, und die Meldung über regelbasierte Fallback-Profile existierte nur im Code. Der Sammler entsteht jetzt im Task-Runner, gleiches Muster wie im Graph-Build, und wird durch beide Phasen bis in den Generator gereicht; sein Report landet im Task-Ergebnis, auch im Fehlerfall, weil er dort oft die Ursache nennt, die die Exception-Message nicht mehr kennt. Leert der Eignungsfilter den Pool vollständig, ist das ein `blocking`-Befund.
- **Der Fortschrittszähler lief über seinen eigenen Nenner: „Erzeugt 22 / 7 Personas…".** Der Nenner war `expected_entities_count`, also die Entitätenzahl; gezählt werden aber Personas, deren Menge erst durch einen `PersonaQuotaPlan` oder den Persona-Floor entsteht, der einen zu kleinen Pool per Round-Robin auf `MIN_PERSONA_TABLE_ROWS` hochskaliert. Sieben Entitäten ergeben fünfzig Personas. [`PersonaTargetContract`](backend/app/contracts/persona_target_contract.py) macht das Ziel explizit, `compute_persona_target` ist die einzige Stelle, die es berechnet, und Preview wie Laufpfad rufen sie beide. `expected_entities_count` bleibt unverändert die Entitätenzahl und wird nicht umgedeutet.
- **Zwei Randfälle, an denen eine zweite Rechnung wieder auseinandergelaufen wäre:** Ein bereits aufgelöster Floor wird hereingereicht, statt ihn aus `max_agents` erneut abzuleiten. Und ein leerer Pool bleibt leer — `_apply_persona_floor_to_entities` skaliert nichts hoch, wenn es nichts zu wiederholen gibt; ein Ziel von 50 bei null Entitäten wäre genau die Divergenz, die der Vertrag beseitigen soll.
- **Ein gegriffener Floor ist in der Oberfläche erkennbar** ([`personaTargetContract.ts`](frontend/src/contracts/personaTargetContract.ts) als Zod-Spiegel, Hinweis in Schritt 2). Ohne ihn wirkt der Nenner willkürlich. Der Hilfetext „Ohne Begrenzung wird pro Entität im Graph ein Agent erzeugt." beschrieb kein beobachtetes Verhalten und nennt jetzt sowohl den Eignungsfilter als auch die Mindestzahl. Fehlt oder bricht `persona_target`, fällt die Anzeige auf die Entitätenzahl zurück statt zu kippen — der Nenner ist eine Anzeige, kein Gate.
- **Korrektur an der Triage-Diagnose:** Der Befund zu Slice 21 verortet die Ursache im Persona-Prompt, der Produkte angeblich als Kandidaten nenne. Das trifft nicht zu — die Stelle ist eine Namensvergabe-Regel und verlangt das Gegenteil: bei Rollen, Themen und Produkten wie „Agora" gerade **nicht** den Entitätsnamen als Personennamen verwenden. Der Prompt ist unverändert.

### Fixed (drei stille Degradierungen: Embedding-Ausfall, Graph ohne Kanten, Platzhalter-Personas — 2026-08-02, Issue #1029)

- **Drei Stellen der Pipeline lieferten bei Teilausfall ein Ergebnis, das wie ein gutes aussah.** Der Schritt meldete Erfolg, die Oberfläche schaltete auf „bereit", und der Qualitätsverlust schlug erst mehrere Schritte später als scheinbar unzusammenhängendes Symptom durch — meist im Report, wo die Ursache nicht mehr erkennbar war. Solange das galt, war ein Lauf mit leeren Embeddings, kantenlosem Graph und regelbasierten Platzhalter-Personas am Bildschirm nicht von einem gesunden Lauf zu unterscheiden.
- **Ein gemeinsamer Vertrag statt dreier Sonderfälle:** [`PipelineDegradationModel`](backend/app/contracts/pipeline_degradation_contract.py) trägt Art, Schweregrad, Ursache und die belegenden Zahlen, mit Zod-Spiegel in [`pipelineDegradationContract.ts`](frontend/src/contracts/pipelineDegradationContract.ts) und einem UI-Consumer ([`DegradationNotice.vue`](frontend/src/components/v4/DegradationNotice.vue)). `severity: blocking` heißt, dass ein Schritt den Zustand „bereit" nicht erreichen darf, auch wenn technisch kein Fehler auftrat. Abgegrenzt gegen `EvidenceDegradationModel` (#1006), das die Abstufung eines einzelnen Claims im fertigen Report protokolliert.
- **Embedding-Ausfall (Befund B-05).** [`ingestion_pipeline.py`](backend/app/services/ingestion_pipeline.py) fängt jede Exception und ersetzt sämtliche Vektoren durch `[]`, mit nur einer `logger.warning`. War Ollama nicht gestartet, lief der Lauf ohne erkennbaren Fehler weiter und die Vektorsuche arbeitete auf leeren Embeddings. Der Fallback bleibt — er ist bewusst gewählt —, ist aber nicht länger unsichtbar. Die Meldestelle liegt vier Ebenen unter der Stelle, an der sie sichtbar werden muss, und dazwischen liegt ein `ThreadPoolExecutor`; deshalb ein durchgereichter, thread-safer [`DegradationCollector`](backend/app/services/degradation_collector.py), der gleichartige Meldungen zusammenfasst — vierzig Chunks am selben abwesenden Ollama ergeben einen Befund mit `occurrences=40` statt vierzig Zeilen Rauschen. `contextvars` scheidet aus, weil `ThreadPoolExecutor.submit` den Kontext nicht kopiert.
- **Graph ohne Kanten (Befund B-24).** `gemini-3.5-flash-lite` lieferte für ein 1-KB-Dokument 3 Entitäten und 0 Beziehungen; zwei von vier Chunks meldeten `0 entities, 0 relations`. Der Schritt meldete trotzdem „Graph fertig." und „Weiter zur Umgebung → Bereit". [`graph_builder.py`](backend/app/services/graph_builder.py) rief `complete_task` unbedingt — `node_count` und `edge_count` lagen zu dem Zeitpunkt bereits vor und wanderten sogar ins Ergebnis, sie wurden nur nie bewertet. Fehlende Beziehungen blockieren jetzt: ein Graph ohne eine einzige Kante ist keine Wissensbasis, sondern eine Stichwortliste. Zu wenige Entitäten und eine schwache Chunk-Erfolgsquote bleiben Warnungen. Schwellen konfigurierbar über `GRAPH_MIN_ENTITIES` (3), `GRAPH_MIN_RELATIONS` (1) und `GRAPH_MIN_CHUNK_SUCCESS_RATIO` (0.5), dokumentiert in [`docs/configuration.md`](docs/configuration.md). Im Frontend ist „bereit" damit eine Aussage über das Ergebnis, nicht über den Programmablauf — Karte 3 zeigt „Unzureichend" und sperrt den Weiter-Knopf.
- **Die Chunk-Erfolgsquote hatte keinen Rückkanal.** `extract_entities_and_relations` kennt seine Zahlen, `add_text` gibt nur die `episode_id` zurück. Dafür `ChunkExtractionTally` — ein reiner Zähler und kein `DegradationCollector`-Eintrag, weil ein einzelner leerer Chunk kein Befund ist (er kann eine Kapitelüberschrift sein). Erst der Anteil über den ganzen Build macht ihn zu einem, und bewertet wird deshalb einmal am Ende statt N-mal währenddessen.
- **Platzhalter-Personas (Befund B-02).** Nach drei fehlgeschlagenen LLM-Versuchen wird die Persona regelbasiert erzeugt und nimmt regulär an der Simulation teil; `OasisAgentProfile` besaß kein Feld für Herkunft oder Qualität, die Degradierung war nach dem Erzeugungszeitpunkt nirgends mehr sichtbar. `generation_source` und `generation_error` sitzen jetzt am Profil und im [`PersonaModel`](backend/app/contracts/persona_contract.py)-Contract — additiv mit Default, persistierte Personas validieren unverändert und gelten als `llm`. Die Kennzeichnung passiert in `_generate_profile_rule_based` selbst: es gibt vier Wege zu einem Platzhalterprofil, und jeder einzelne hätte sie beim Aufrufer vergessen können. `to_reddit_format`/`to_twitter_format` führen die Herkunft mit, weil die Persona-Galerie genau diese Datei liest — geschrieben nur bei Abweichung vom Default, damit LLM-Profile byte-identisch zum bisherigen Format bleiben. `use_llm=False` ist eine bewusste Wahl und keine Degradierung; die Meldung hängt deshalb an `generation_error`, nicht an `generation_source`.
- **ADR-0002 ist nicht berührt** — die fünf Hartanker bleiben unverändert, kein `0002-supersedes` nötig. Das Akzeptanzkriterium „Aussagen eines Fallback-Profils können keine Evidence höherer Confidence stützen" ist damit **vorbereitet, aber nicht durchgesetzt**: die Durchsetzung säße in `normalize_source_kind`, das keinen Persona-Bezug kennt, und damit mitten im Evidence-Schreibpfad, den [#1008](https://github.com/arn0ld87/agora/issues/1008) und [#1012](https://github.com/arn0ld87/agora/issues/1012) gerade betreffen. Hinzu kommt, dass der zu schützende Pfad — `agent_quote` aus Interviews — laut RC-1 der Triage derzeit gar nicht erreichbar ist; ein Auffangnetz dafür wäre heute nicht prüfbar. Ausgelagert.
- **Es gibt zwei Graph-Build-Pfade, und das Gate hängt in beiden.** `GraphBuilderService._build_graph_worker` und der `build_task`-Closure in [`graph_build.py`](backend/app/services/graph_build.py) rufen `add_text_batches` je selbst auf und schreiben je ihr eigenes Task-Ergebnis; der Endpunkt `POST /api/graph/build` nimmt den zweiten. Die erste Fassung dieses Slices verdrahtete nur den ersten — vier Ebenen Tests grün, in Produktion wirkungslos. Beide Pfade rufen jetzt dieselbe öffentliche `assess_graph_quality_from_counts`, und [`test_graph_build_degradation_wiring.py`](backend/tests/services/test_graph_build_degradation_wiring.py) nagelt den produktiven fest: er führt `build_graph` synchron aus und liest das Ergebnis, das der Endpunkt liefert.
- **Der Ausnahmetext einer fehlgeschlagenen Einbettung geht durch `describe_exception`.** `detail` verlässt das Backend über das Task-Ergebnis und landet in der Oberfläche — bisher stand der Text nur im Log. Ausnahmen von HTTP-Embedding-Clients tragen die vollständige Request-URL samt Query, und dort steht der API-Key. Behalten werden Ausnahmetyp, Schema und Host; Pfad und Query fallen weg, die Länge ist gedeckelt. Vollständig bleibt der Text im Log.
- **Ein Reload verliert den Befund nicht mehr.** `loadProject` sprang bei `graph_completed` direkt auf Phase 2, und weil `qualityBlocked` allein aus dem Session-State kommt, stand der Weiter-Knopf nach jedem Neuladen wieder offen — ausgerechnet auf dem Weg, den ein Nutzer nach einem schlechten Lauf am ehesten nimmt. Der Bericht wird jetzt vor dem Weiterschalten aus dem abgeschlossenen Task nachgeladen und beim Projektwechsel wie beim Start eines neuen Builds zurückgesetzt. Ist die Task-ID nach einem Backend-Neustart nicht mehr auflösbar, bleibt er leer — derselbe dokumentierte Fallback wie bei `currentRunId` (#1023).
- **Das finale Persona-Artefakt behält die Herkunft.** `_save_reddit_json` baut sein Dict neu, statt `to_reddit_format` zu benutzen, und überschreibt die im Realtime-Pfad bereits korrekt geschriebene Datei. Ohne dieselben Felder dort verlöre das Artefakt, das die Persona-Galerie tatsächlich liest, die Kennzeichnung wieder.
- **Regressionstests decken die Verbindungen einzeln ab, nicht nur die Funktionen:** [`test_degradation_wiring.py`](backend/tests/services/test_degradation_wiring.py) prüft Ebene 2 gegen den echten `Neo4jWriteMixin.add_text`, Ebene 3 gegen `add_text_batches` mit echter Embedding-Phase und Ebene 4 gegen das Task-Ergebnis. Genau an dieser Sorte Lücke sind #961, #966 und #985 nacheinander vorbeigelaufen — und der übersehene zweite Build-Pfad oben ist derselbe Fehler noch einmal, eine Ebene höher.

### Fixed (maschinenübersetzte Log- und Fortschrittsmeldungen im Report-Agent — 2026-08-02, Issue #1026)

- **`reportgeneratefailed`, `outlinesaved`, `Sectionsaved` — die Meldungen des Report-Agents waren teils unlesbar.** `backend/app/services/report_agent/` stammt aus einem chinesischsprachigen Upstream-Fork; beim Übersetzen sind Wortgrenzen verschwunden und Fullwidth-Interpunktion (`，`, `（`, `）`) stehengeblieben. Betroffen waren achtzehn Meldungen — zwölf Log-Zeilen und sechs Fortschrittsmeldungen — in [`manager.py`](backend/app/services/report_agent/manager.py), [`workflow.py`](backend/app/services/report_agent/workflow.py) und [`simulation_prepare.py`](backend/app/api/simulation_prepare.py).
- **Sechs davon waren kein Logtext, sondern Produktoberfläche.** `ReportManager.update_progress` und `progress_callback` reichen ihre Meldung unverändert an die UI durch — `"Initializereport..."`, `"generatinggenerateSection: …"` und `"reportgeneratecomplete"` standen so im Fortschrittspanel. Die Log-Zeilen wiederum sind der einzige Anhaltspunkt, wenn ein Report-Lauf nachts abbricht, und `reportgeneratefailed` taugt als Suchbegriff nicht.
- **Die angefassten `logger.*`-Aufrufe formatieren jetzt lazy über `%`** statt über f-Strings. Kein repoweites Aufräumen: `ruff --select G004` meldet 177 weitere Stellen, die Regel bleibt deshalb aus dem `select` und wird in einem eigenen Slice behandelt.
- **Absicherung gegen die Klasse, nicht gegen die Zeilen:** [`backend/tests/test_log_message_quality.py`](backend/tests/test_log_message_quality.py) parst `backend/app/` per AST und prüft jede Meldung aus `logger.*`, `update_progress` und `progress_callback` auf Fullwidth-Interpunktion und auf zusammengeklebte Wörter aus einer geschlossenen Vokabelliste — auch an der Grenze zu `{}`-Platzhaltern, wo `f"total{n}sections"` im reinen Literaltext unsichtbar bleibt. `ReportAgent` und `ReportManager` lösen bewusst nicht aus: beim Übersetzungsfehler beginnt das zweite Wort klein, bei Klassennamen groß. Der Guard trägt seine eigene Gegenprobe — drei Testfälle füttern ihn mit den Originaldefekten, einer mit den Klassennamen.
- **Nicht angefasst: Prompt-Strings, die API-Antwort in `simulation_prepare.py:777` und die Kommentare aus derselben Quelle.** Eine geänderte Prompt-Formulierung ist Verhalten, keine Kosmetik, und braucht eine eigene Bewertung — [#1027](https://github.com/arn0ld87/agora/issues/1027).
### Fixed (Lauf-Kontext im Frontend: Report-Start, Modell-Herkunft und ID-Räume — 2026-08-02, Issue #1023)

- **Der Report startete ungefragt.** `Step3Simulation.goReport()` rief `generateReport()` direkt auf — der teuerste Pipeline-Schritt lief los, bevor der Nutzer Schritt 4 gesehen hatte, und zwar mit dem Workspace-Default-Modell. Schritt 3 navigiert jetzt nur noch in einen „bereit"-Zustand (`buildReportReadyRoute()` mit Sentinel-`reportId` `'new'`, analog zur `'new'`-Konvention aus `useGraphBuildPipeline.ts`); den Start löst erst der Bestätigungs-Block in Schritt 4 aus.
- **Schritt 4 zeigt und benutzt jetzt das Modell dieses Laufs**, nicht den Workspace-Default: `GET /api/runs/<id>/llm-routing`, Reihenfolge Stage-Snapshot > vom Lauf konfigurierte Route > Workspace-Kanon. Das Lauf-Modell geht auch in den Start-Request (`ai_model_ref` mit `source: 'run-override'`) — `start_generation()` legt einen neuen Report-Lauf an und erbt das Routing des Simulationslaufs nicht, die Anzeige hätte sonst ein Modell versprochen, das nicht zum Einsatz kommt. Der Workspace-Kanon bleibt dagegen reiner Anzeigewert ohne Override. Ein expliziter Picker-Pick gewinnt gegen beides; wählt der Nutzer ab, entfällt der Override.
- **Registry-Run-ID und Simulations-ID sind getrennte ID-Räume** ([`runIdentifiers.ts`](frontend/src/contracts/runIdentifiers.ts) mit Branded Types). `?runId=` transportierte auf der Interaktions-Route eine `sim_…`-ID und ließ Chat/Interview in Schritt 5 mit „Invalid simulation_id format" scheitern (Regression aus PR #997). Beide Routen-Builder und `StepReportView` prüfen den Wert jetzt gegen seinen ID-Raum, statt jeden nicht-leeren String zu übernehmen: eine `sim_…`-ID landet nicht mehr als `runId` im Query. Andernfalls fragte Schritt 4 `/api/runs/sim_…`, läse den 404 als „kein Lauf-Routing" und zeigte still das Workspace-Modell an — der Fall trat nach jedem Reload der Simulationsseite ein, weil die Registry-ID nur in der Session lebt.
- **Das Graph-Build-Badge zeigt das Lauf-Modell.** `StepModelOverrideChip` las für `graph_build` immer den Workspace-/Stage-Default. Liegt ein Run-Snapshot vor, zeigt der Chip dessen Modell, sperrt sich und markiert die Quelle als „aus Lauf"; ohne Snapshot bleibt der Stage-Default, jetzt sichtbar als „Standard" markiert statt kommentarlos.
- **Die GraphPanel-Buttons liefen ins Leere.** `refresh` und `toggle-maximize` sind verdrahtet (Letzteres als CSS-Vollbild-Toggle mit `aria-pressed` und i18n-Beschriftung, kein Browser-Fullscreen-API); `close-graph` wurde entfernt statt verdrahtet — das Panel ist der primäre Inhalt seines Schritts, ein „Schließen" ohne Wieder-Öffnen-Pfad wäre irreführender als ein fehlender Button.
- **Poll-Transportfehler werden gezählt statt verschluckt.** `Step4Report.pollStatus()` hatte ein `catch { /* swallow */ }` ohne Retry-Zähler; bei totem Backend wartete der Nutzer auf ein Ergebnis, das nicht mehr kommen konnte. Drei Fehlschläge in Folge (~7,5 s) zeigen jetzt einen `role="alert"`-Hinweis, der sich beim nächsten erfolgreichen Poll selbst zurücknimmt.
- **Dynamische i18n-Keys werden vor dem Zugriff geprüft.** `formatEdgeLabel()` rief `t(fullKey)` für jede LLM-generierte Relation auf und erzeugte „not found"-Warnungen, bevor der Humanizer griff; ein `te()`-Guard verhindert das. Zusätzlich fehlte `feed.sentimentBar` in `de.json` und `en.json`.

### Security (Trivy und Publish bauen wieder die prod-Stage, nltk-Ausnahmen aufgelöst — 2026-08-02, Issues #994, #995, #661)

- **Trivy und `publish` scannten/publizierten seit dem 2026-07-05 das nginx-Proxy-Image statt des Prod-Images.** Die drei `docker/build-push-action`-Schritte in [`.github/workflows/docker-image.yml`](.github/workflows/docker-image.yml) setzten kein `target:` — BuildKit baut ohne `target` die letzte Dockerfile-Stage, und das ist seit `88172365` `proxy` (nginx), nicht mehr `prod`. Damit war das Trivy-Gate blind für das eigentliche Produktions-Image, und ein Release hätte das nginx-Image statt des App-Images gepusht. Alle drei Schritte (`build-only`, GHCR-Push, Docker-Hub-Push) setzen jetzt `target: prod`. Der separate nginx-Proxy für `prod-proxy-smoke` brauchte keine Anpassung — [`deploy/compose/docker-compose.prod-with-proxy.yml`](deploy/compose/docker-compose.prod-with-proxy.yml) baut ihn bereits eigenständig mit `target: proxy`. (Issue #994)
- **Folgewirkung desselben Fixes: der Build-Cache musste von `mode=max` auf `mode=min`.** Sobald `target: prod` greift, baut der Job zum ersten Mal seit dem 2026-07-05 wieder das echte Prod-Image — mit der vollen Backend-venv inklusive der CUDA-Wheels (cudnn ~700 MB, nvshmem ~300 MB). `cache-to: type=gha,mode=max` exportiert die Layer *aller* Stages, also auch der `backend-build`-Stage; zusammen mit `/tmp/image.tar` sprengte das den Speicher des GitHub-Runners, und der Build brach im Cache-Export ohne Fehlermeldung ab. Am nginx-Proxy-Image (wenige MB) war das nie aufgefallen. Alle drei Build-Steps nutzen jetzt `mode=min` — exportiert nur die Layer des finalen Images, der Cache-Nutzen für den `publish`-Build bleibt. Zusätzlich gibt ein Cleanup-Step die auf dem Runner vorinstallierten SDKs (Android, .NET, GHC, PowerShell, Swift) frei, die kein Schritt dieses Jobs benutzt.
- **`nltk` von 3.9.4 auf 3.10.1 gehoben** (`backend/pyproject.toml`, `tool.uv.override-dependencies`), verifiziert per vollem Backend-Testlauf (4159 passed, 17 vorbestehende Failures identisch auf dem alten Pin reproduziert — kein durch den Bump verursachter Regressions-Fall). `unstructured`/`camel-oasis` lösen unverändert auf. Zwei Advisories, zwei unterschiedliche Wahrheiten: **GHSA-p4gq-832x-fm9v** (Alias `CVE-2026-54293`, `PYSEC-2026-2078`) hat einen echten Upstream-Fix in nltk 3.10.0 — der alte `.trivyignore`-Eintrag griff ohnehin nie, weil Trivy die CVE-ID meldet und Aliase nicht auflöst, und ist jetzt gegenstandslos. **PYSEC-2026-597** (Alias `CVE-2026-12243`) hat weiterhin **keinen** echten Fix — laut OSV existiert kein `fixed`-Event, nur `last_affected: 3.9.4`; ab nltk 3.10.0 fällt das Paket nur aus dem affected-Set, Tooling flaggt es deshalb nicht mehr, ohne dass die Schwachstelle behoben wäre. Beide `.trivyignore`-Einträge und beide `--ignore-vuln`-Flags in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) sind entfernt, [`docs/dependency-risk-exceptions.json`](docs/dependency-risk-exceptions.json) trägt für beide `status: resolved`. Issue #995 (GHSA) ist geschlossen; **Issue #661 (PYSEC-2026-597) bleibt ausdrücklich offen** — die Advisory ist nicht behoben, sie verschwindet nur aus dem Scanning-Fenster. Der tote Tracking-Zeiger auf das seit 2026-07-27 geschlossene Issue #672 in [`docs/dependency-risk-register.md`](docs/dependency-risk-register.md) und `dependency-risk-exceptions.json` ist auf #995 bzw. #661 korrigiert.
- **nltk 3.10 hätte den Ingestion-Pfad zur Laufzeit gebrochen — abgefangen per `NLTK_DISABLE_IMPORT_SECURITY=1`.** Die neue Version installiert einen Import-Hook (`nltk/inisec.py`), der jeden **von nltk ausgelösten** Import blockiert, dessen Modul unterhalb des Arbeitsverzeichnisses liegt. Er unterscheidet nicht zwischen Projektbaum und einer venv, die zufällig darunter liegt — und genau das ist bei Agora der Regelfall (Container: `WORKDIR /app` mit `/app/backend/.venv`; lokal: `cd backend && uv run …`). Damit gilt jedes venv-Paket als „aus dem CWD", und `regex` bzw. `defusedxml` fliegen mit einem `ImportError` heraus, sobald `unstructured` beim Parsen nltk lädt. Der Bruch tritt zur Laufzeit auf, nicht beim Build — kein CI-Schritt hätte ihn gefunden. Der Hook ist jetzt an drei Stellen deaktiviert: in [`backend/app/__init__.py`](backend/app/__init__.py) — das deckt jeden Einstieg ab, der `app` importiert, also auch den nativen Start `cd backend && uv run python run.py` hinter `bun run dev`, dazu gunicorn, Skripte und Worker —, zusätzlich als ENV in der base- und der prod-Stage des [`Dockerfile`](Dockerfile) und in [`backend/tests/conftest.py`](backend/tests/conftest.py) für die Suite. **Der eigentliche CVE-Fix bleibt aktiv** — GHSA-p4gq-832x-fm9v betrifft die Path Traversal in `nltk.data.load()`, der abgeschaltete Hook ist nur zusätzliche Defense-in-Depth gegen CWD-Import-Hijacking, die bei read-only Rootfs und nicht-root User ohnehin ins Leere greift. `PYTHONSAFEPATH=1` ist keine Alternative, obwohl die Fehlermeldung es vorschlägt. Neuer Regressionstest [`backend/tests/test_nltk_import_guard.py`](backend/tests/test_nltk_import_guard.py): alle Subprozesse dort laufen mit **entfernter** `NLTK_DISABLE_IMPORT_SECURITY`, damit sie nicht den Opt-out der Testumgebung erben und grün sind, ohne die produktive Konfiguration je zu prüfen.

### Changed (Worktree-Regel und Permission-Modus — 2026-08-02)

- **Die T7-Worktree-Pflicht gilt nur noch für manuell angelegte Worktrees.** Sie war mit `isolation: worktree`-Subagenten nicht einhaltbar: Ein PreToolUse-Hook der Agent-Runtime sperrt einem isolierten Worker jede Git-Operation außerhalb des ihm zugewiesenen Worktrees unter `.claude/worktrees/agent-<id>/`. Ein vom Lead pflichtgemäß auf T7 vorbereiteter Pfad ist für ihn unerreichbar — der Worker meldet den Konflikt und arbeitet nicht. Das ist eine Permission-Entscheidung, keine Empfehlung.
- **Harness-zugewiesene Worktrees sind damit ausdrücklich zulässig** und der Normalfall bei Subagent-Dispatch. Der Lead bereitet für solche Worker keinen T7-Worktree vor und gibt keinen Zielpfad im Briefing vor; er übernimmt den Commit anschließend per `git cherry-pick` auf einen sprechend benannten Branch. `/private/tmp` bleibt verboten, für manuelle Worktrees gilt die T7-Konvention unverändert. Geändert in [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md) und dem SSoT [`docs/runbooks/worktree-strategy.md`](docs/runbooks/worktree-strategy.md).
- **Ergänzt: Harness-Worktrees überleben keinen Prozess-Neustart zuverlässig.** Vor dem Aufräumen ist auf uncommittete Arbeit zu prüfen. Genau dieser Fall trat bei der Umsetzung ein — ein Systemabsturz kostete zwei Worker-Ergebnisse, eines davon war im Worktree noch zu retten.
- **`.claude/settings.json` läuft auf `defaultMode: "bypassPermissions"`.** Die `allow`- und `ask`-Listen entfallen, weil sie in diesem Modus wirkungslos sind.

### Changed (Review-Gate, mypy-strict und Frontend-Build entschärft — 2026-08-02)

- **Der Regelfall braucht keinen Reviewer-Subagenten mehr.** Bisher verlangten [`CLAUDE.md`](CLAUDE.md), [`agora-next-task`](.claude/commands/agora-next-task.md), [`agora-batch-issues`](.claude/commands/agora-batch-issues.md) und [`subagent-routing.md`](docs/runbooks/subagent-routing.md) übereinstimmend ein `APPROVE` des `agora-opus-reviewer` vor Push und PR. Ein Reviewer ist jetzt optional und seine Antwort eine Einschätzung, kein Freigabetor — der Lead entscheidet, welche Blocker er übernimmt. Erforderlich bleiben ein Regressionstest, der den Defekt trifft, und ein grünes `pre-push-gate.sh`.
- **Kein RED/GREEN-Protokoll im PR-Text, keine Mutationsproben.** Die alte Formulierung verlangte beide Testausgaben wörtlich im PR und war als Aufforderung zur Gegenprobe durch absichtlich verfälschten Code lesbar. Dass der Test vor dem Fix rot ist, prüft man einmal beim Schreiben und dokumentiert es nirgends.
- **`app.contracts.*` läuft nicht mehr unter `mypy --strict`.** Von den rund zehn Flags, die `strict` zuschaltet, trägt bei Pydantic-Modellen nur `disallow_untyped_defs`; der Rest erzeugte Reibung an Dekoratoren und Fremdcode-Aufrufen. Nur dieses eine Flag bleibt aktiv, der Rest der `[tool.mypy]`-Sektion ist unverändert.
- **Der Frontend-Build läuft lokal nur noch mit `GATE_BUILD=1`.** Er war der teuerste Schritt des Gates und fängt nach ESLint, `vue-tsc` und Vitest praktisch nichts mehr ab. Die CI baut weiterhin bei jedem PR — die verbleibende Lücke sind reine Bundler-Fehler. Wer Vite-Config, Aliase oder Chunk-Strategie anfasst, setzt die Variable; [`pre-push-gate.md`](docs/runbooks/pre-push-gate.md) benennt die Ausnahme.
- **Unverändert:** ruff, mypy, Contract-Tests, Schema-Drift, `sync-status --check`, ESLint, `vue-tsc` und Vitest bleiben Pflicht. Die fünf Evidence-Hartanker aus ADR-0002 sind nicht berührt.

### Fixed (die Sim-Uhr im Live-Feed rückte nur an Rundengrenzen vor — 2026-08-02, Issue #1018)

- **Alle Posts einer Runde trugen dieselbe simulierte Zeit.** [`backend/scripts/run_parallel_simulation.py`](backend/scripts/run_parallel_simulation.py) berechnete `_sim_dt` einmal pro Runde — vor der Schleife über die Actions — und gab denselben Wert an jedes `PostCreatedEvent` der Runde weiter. Die Uhr in der Live-Feed-Kopfzeile sprang dadurch nur beim Rundenwechsel und stand dazwischen still; bei kurzen Läufen sah sie schlicht eingefroren aus. Betroffen waren beide Plattform-Pfade, Twitter wie Reddit.
- **Der Transportweg war nie das Problem.** Die Vermutung aus #1018, `simulated_hours` fehle ein Consumer im Frontend, hat sich nicht bestätigt: `sim_time` wird von [`event_bus_redis.py`](backend/app/services/event_bus_redis.py) als flaches Payload durchgereicht, von [`simulation_stream.py`](backend/app/api/simulation_stream.py) unverändert als SSE ausgeliefert, vom Zod-Schema in [`postEventContract.ts`](frontend/src/contracts/postEventContract.ts) behalten und von [`useSimClock.ts`](frontend/src/composables/useSimClock.ts) gerendert. Kein Feldverlust, kein fehlender Consumer — der Wert war nur zu grob aufgelöst.
- **Entscheidung zur kanonischen Quelle: `PostCreatedEvent.sim_time` bleibt es.** Die Alternative — die Status-API zur Quelle der Kopfzeile zu machen — hätte einen neuen Zod-Status-Contract im Frontend erfordert (es gibt keinen) und eine Push-Anzeige an eine Poll-Quelle gekoppelt. `SimulationRunState.simulated_hours` bleibt damit ausdrücklich Backend-Telemetrie ohne UI-Anspruch. Ein zweiter, konkurrierender Zeitwert im Frontend entsteht nicht.
- **Neu ist `compute_post_sim_time`** in [`backend/scripts/_sim_common.py`](backend/scripts/_sim_common.py), direkt neben `compute_start_hour_offset`. Sie verteilt die Actions einer Runde über deren Minutenbudget. Der Index zählt alle Actions der Runde, nicht nur die emittierten Posts — er ist die Zeitachse der Runde, kein Post-Zähler. Bei Index 0 liefert sie exakt den bisherigen Rundenwert, bleibt also am Rundenanfang rückwärtskompatibel.
- **Die Rundengrenze ist die tragende Eigenschaft.** Der Intra-Runden-Versatz bleibt strikt unter `minutes_per_round`, damit der letzte Frame einer Runde strikt früher liegt als der erste der Folgerunde. Das ist kein Schönheitsdetail: `useSimClock` erzwingt Monotonie und verwirft rückwärts laufende Frames kommentarlos — eine überschrittene Grenze hätte die Uhr erneut zum Stehen gebracht, diesmal ohne sichtbare Ursache. Die `log_round_end`-Logik aus #1014 ist unverändert.
- **Absicherung:** [`backend/tests/scripts/test_sim_clock_resolution.py`](backend/tests/scripts/test_sim_clock_resolution.py) prüft strikt wachsende Werte innerhalb einer Runde, die Gleichheit bei Index 0 mit dem alten Rundenwert, die Einhaltung der Rundengrenze, Monotonie über zwei Rundenwechsel hinweg sowie die Randfälle `action_count` 0 und 1 und einen Index jenseits der Aktionszahl.
- **Der Nachweis an der Oberfläche fehlte bisher ganz.** `useSimClock` und `SimulationProgressPanel` waren jeweils für sich getestet, beide nur mit einem einzelnen Zeitwert — dass eine Folge von Frames die *gerenderte* Kopfzeile verändert, prüfte niemand. Genau daran sind #961, #966 und #985 vorbeigelaufen. [`simClockRendering.spec.ts`](frontend/src/components/step3/__tests__/simClockRendering.spec.ts) bindet die Uhr wie `Step3Simulation` an das Panel und prüft den sichtbaren `<time>`-Text über eine Event-Sequenz: er wächst, er steht bei gleichbleibender `sim_time` still (das alte Verhalten), er überlebt Frames ohne `sim_time` und springt bei rückwärts laufenden Frames nicht zurück.

### Fixed (der Skript-Download von action_logger.py brach außerhalb des Repos — 2026-08-02, Issue #1017)

- **Der Einzeldatei-Download riss den Import mit.** Seit [#1016](https://github.com/arn0ld87/agora/issues/1016) importiert [`backend/scripts/action_logger.py`](backend/scripts/action_logger.py) `RoundEndEvent` aus `app.contracts.sim_action_log_contract`. `GET /api/simulation/script/action_logger.py/download` lieferte weiterhin nur diese eine Datei aus — außerhalb des Repos ausgeführt brach der Import sofort mit `ModuleNotFoundError`.
- **`download_simulation_script` liefert für `action_logger.py` jetzt ein in-memory ZIP** ([`backend/app/api/simulation_profiles.py`](backend/app/api/simulation_profiles.py)) statt der Einzeldatei: `scripts/action_logger.py`, zwei leer erzeugte `__init__.py` (`app/__init__.py`, `app/contracts/__init__.py`) und der unveränderte `app/contracts/sim_action_log_contract.py`. Bewusst kein `try/except ImportError`-Fallback mit lokaler Ersatzdefinition — genau dieser doppelte Wahrheitsort war die Ursache von [#1014](https://github.com/arn0ld87/agora/issues/1014).
- **Das Archiv bildet die Repo-Struktur nach, statt Skript und Paket flach nebeneinanderzulegen.** `action_logger.py` setzt seinen Importanker auf *zwei* Ebenen über sich selbst und schiebt ihn auf `sys.path[0]`. Bei flachem Layout zeigte dieser Anker aus dem Entpackverzeichnis heraus: ein beliebiges `app`-Paket im Elternverzeichnis hätte das mitgelieferte verdeckt — je nach Inhalt mit einem veralteten Contract oder demselben `ModuleNotFoundError`, den dieser Fix beheben soll. Die `scripts/`-Ebene hält den Anker innerhalb des Bundles. Die leeren `__init__.py` werden erzeugt statt kopiert; die echten würden die gesamte Flask-App bzw. sämtliche Contracts nachziehen.
- Die anderen drei Skripte (`run_twitter_simulation.py`, `run_reddit_simulation.py`, `run_parallel_simulation.py`) bleiben unverändert Einzeldatei-Downloads.
- **Absicherung:** [`backend/tests/api/test_simulation_script_download.py`](backend/tests/api/test_simulation_script_download.py) prüft ZIP-Inhalt, leere `__init__.py`, Byte-Identität des Contracts, den eigenständigen Subprozess-Import des entpackten Bundles gegen bereinigtes `PYTHONPATH` sowie den Shadowing-Fall: ein fremdes `app`-Paket im Elternverzeichnis darf den Import nicht kapern.

### Fixed (der Simulationsfortschritt stand dauerhaft auf 0 — 2026-08-02, Issue #1014)

- **Writer und Reader tauschten die Rundendaten über ein implizites Dict aus.** [`backend/scripts/action_logger.py`](backend/scripts/action_logger.py) schrieb das `round_end`-Ereignis ohne den Schlüssel `simulated_hours`; [`backend/app/services/sim/action_log_reader.py`](backend/app/services/sim/action_log_reader.py) las genau diesen Schlüssel. Der Reader fand ihn nie und meldete konstant 0 — die Fortschrittsanzeige einer laufenden Simulation bewegte sich nicht, unabhängig davon, wie viele Runden tatsächlich gelaufen waren.
- **Beide Seiten hängen jetzt an einem gemeinsamen Vertrag.** Neu ist `RoundEndEvent` in [`backend/app/contracts/sim_action_log_contract.py`](backend/app/contracts/sim_action_log_contract.py). Kanonisch geführt wird `simulated_minutes` als Ganzzahl; die Stunden sind ein daraus abgeleiteter Wert. Damit kann keine der beiden Seiten den Schlüssel mehr einseitig umbenennen, ohne dass die Verträge auseinanderfallen — das war die eigentliche Fehlerursache, nicht der fehlende Wert selbst.
- **Alt-Logs bleiben lesbar — die verlorene Zeit wird aber nicht rekonstruiert.** `from_log_entry` akzeptiert Einträge ohne `simulated_minutes` und setzt sie über `Field(default=0)` auf 0 Minuten. Hochrechnen ließe sich nichts: Der alte Writer schrieb überhaupt keinen Zeitschlüssel, auch keinen `simulated_hours` — genau das ist die Prämisse von B-28. Ein laufender Run stirbt damit nicht an einem Alteintrag, und weil der Reader den Fortschritt über `max()` führt, zieht eine solche 0 den bereits erreichten Stand auch nicht zurück.
- **Der Vertrag lehnt kaputte Werte jetzt ab, statt sie stillschweigend auf 0 zu glätten.** `simulated_minutes` ist als nicht-negative Ganzzahl validiert; `None`, Strings und negative Werte lösen einen `ValidationError` aus, statt wie bisher als 0 durchzulaufen. Die Umrechnung Minuten→Stunden läuft über die benannte Konstante `MINUTES_PER_HOUR` statt über eine verstreute 60. Der Reader parst nichts mehr selbst: Er reicht den Log-Eintrag an `RoundEndEvent.from_log_entry` durch und liest die Stunden als abgeleiteten Wert zurück. Ein fehlendes Feld ergibt dort 0, ein kaputtes einen `ValidationError` — die Unterscheidung trifft ausschließlich der Vertrag.
- **Contract-Tests sichern beide Seiten ab.** [`backend/tests/contracts/test_sim_action_log_contract.py`](backend/tests/contracts/test_sim_action_log_contract.py) prüft Writer und Reader gegen denselben Vertrag, inklusive Alt-Log-Pfad und Ablehnung ungültiger Werte.

### Fixed (Runden und Tage aus Schritt 2 erreichten Schritt 3 nie — 2026-08-02, Issue #1013)

- **Jede Simulation lief mit dem Auto-Wert, egal was der Nutzer einstellte.** [`StepEnvSetupView.vue`](frontend/src/views/v4/steps/StepEnvSetupView.vue) gab `maxRounds` und `simulationDays` zwar im `next-step`-Ereignis mit, legte beim `router.push` aber nur `simulationId` als Route-Param und `projectId` als Query ab. Da die Ziel-Route mit `props: true` ausschließlich Route-Params durchreicht, fielen beide Werte still auf den Boden; [`StepSimulationView.vue`](frontend/src/views/v4/steps/StepSimulationView.vue) reichte an `Step3Simulation` folglich gar nichts weiter und die Komponente griff auf ihren vom Backend vorgeschlagenen Wert zurück. Es gab keine Fehlermeldung — die Eingabe verschwand zwischen zwei Bildschirmen.
- **Beide Seiten teilen jetzt einen benannten Vertrag statt einer Annahme.** [`runParamsQuery.ts`](frontend/src/contracts/runParamsQuery.ts) hält die Query-Schlüssel sowie das Schreiben und Lesen an einer Stelle zusammen. Die Werte reisen als Query mit, weil das Ziel eine eigene, per URL erreichbare Route ist: Ein Reload auf Schritt 3 behält damit die Einstellung, ein Store-Eintrag hätte sie verloren. Nicht übersteuerte Werte bleiben bewusst aus der URL — fehlt der Parameter, gilt weiterhin der Auto-Vorschlag des Backends.
- **Der Tab-Wechsel verlor zusätzlich die `projectId`.** `onTabChange` in [`StepSimulationView.vue`](frontend/src/views/v4/steps/StepSimulationView.vue) baute die Ziel-Route ohne Query neu auf, wodurch der Zurück-Weg zum Projekt nach einem Blick in den Feed abbrach. Die Query wandert nun mit. Unbrauchbare Werte aus manipulierten URLs (`0`, negative Zahlen, Kommazahlen, Text) werden verworfen statt an das Backend gereicht.
- **Absicherung:** [`runParamsQuery.spec.ts`](frontend/src/contracts/__tests__/runParamsQuery.spec.ts) prüft die Normalisierung samt Roundtrip, [`runParamsHandover.spec.ts`](frontend/src/views/v4/steps/__tests__/runParamsHandover.spec.ts) die Übergabe über beide Views hinweg. Gegenprobe per Mutation: Entfernt man die Query-Anreicherung, die Prop-Bindung oder die Query beim Tab-Wechsel, fällt jeweils genau der zuständige Test.

### Fixed (ein Evidence-Verstoß kippte den ganzen Report — 2026-08-02, Issue #1006)

- **Ein einzelner verletzender Claim vernichtete alle bereits fertigen Abschnitte.** `_save_evidence_section` in [`backend/app/services/report_agent/agent.py`](backend/app/services/report_agent/agent.py) validierte die Evidence-Map ohne lokales `try/except`. Der `ValidationError` lief über die ungeschützte Hauptschleife in [`backend/app/services/report_agent/workflow.py`](backend/app/services/report_agent/workflow.py) bis in den globalen Handler und setzte `report.status = FAILED` mit `md_len=0`. Ein Report mit sechs geplanten und einem bereits ADR-0002-konform ausformulierten Abschnitt endete so als Totalausfall. Acht von acht echten Reports seit dem 27.07. sind daran gescheitert.
- **Der Validator bleibt unverändert streng — geändert wurde ausschließlich die Reaktion.** Keiner der fünf ADR-0002-Hartanker ist angefasst: `agent_grounded_for_medium`, `cross_stakeholder_for_high`, `reject_inferred_in_high_confidence`, der `<evidence_gating priority="hard">`-Block und der Hedge-Snapshot gelten unverändert. Neu ist `degrade_sections_for_violations` in [`backend/app/services/report_agent/evidence.py`](backend/app/services/report_agent/evidence.py): sie liest die `loc`-Pfade des `ValidationError` und repariert lokal. Ein Claim, der Evidence trägt und nur das Stufenkriterium verfehlt, wird auf `low` abgestuft; ein Claim ganz ohne Evidence wandert in den Hypothesen-Slot, für den ADR-0002 ihn ohnehin vorsieht. Die Reaktion ist dreistufig — reparieren, dann gezielt entfernen, dann erst durchreichen; ein dritter Fehlschlag fliegt bewusst weiter, weil stiller Datenverlust schlimmer wäre als ein harter Fehler.
- **Der Report endet auf `incomplete` statt `completed`.** `apply_degradation_downgrade` in [`backend/app/services/report_agent/output_contract.py`](backend/app/services/report_agent/output_contract.py) stuft ein sonst vollständiges Ergebnis ab, sobald repariert wurde. Ein bereits `incomplete` oder `failed` markierter Report wird nicht aufgewertet. Der Nutzer sieht damit, dass der Report Reparaturen enthält, statt ein `completed` zu lesen, das er nicht einlöst.
- **Verstöße sind maschinenlesbar statt nur im Log.** Neu: `EvidenceDegradationModel` und das additive Feld `EvidenceMapModel.degradation_log` in [`backend/app/contracts/report_contract.py`](backend/app/contracts/report_contract.py) mit `section_index`, `claim_id`, `violation`, `action` und `detail`. Default leer, damit bestehende persistierte Evidence-Maps unverändert weiter validieren.
- **Der Degradierungspfad erzeugte selbst ungültige Einträge.** `normalize_sections_for_contract` filterte Platzhalter-Texte aus `hypotheses` und `data_gaps`, nicht aber aus `hypotheses_appendix` — obwohl beide Slots aus denselben ungefilterten LLM-Rohdaten gespeist werden. Genau daher stammt der zweite beobachtete Fehler `hypotheses_appendix.13.hypothesis_text: string_too_short`. Der Filter greift jetzt auf beiden Slots. Ergänzend wird ein Claim, dessen Text für einen gültigen Hypothesen-Eintrag zu kurz wäre, ersatzlos verworfen statt als Reparatur eingefügt, die die Validierung erneut brechen würde.
- **Regressionsnachweis:** [`backend/tests/contracts/test_evidence_degradation.py`](backend/tests/contracts/test_evidence_degradation.py). Der letzte Test belegt ausdrücklich, dass ein `medium`-Claim ohne agent-grounded Evidence weiterhin abgelehnt wird — der Hartanker ist nicht gelockert, nur die Folge eines Verstoßes hat sich geändert.
### Fixed (Live-Feed verlor seinen Bestand und ließ den Tab einfrieren — 2026-08-02, Issue #1007)

- **Ein Wechsel auf die Feed-Route und zurück vernichtete alle empfangenen Posts.** [`frontend/src/views/v4/steps/StepSimulationFeedView.vue`](frontend/src/views/v4/steps/StepSimulationFeedView.vue) rief beim Unmount `clearSimFeed(simulationId)` und löschte damit bei jeder normalen Navigation den kompletten Store. Danach zeigte auch die Pipeline-Ansicht dauerhaft null. „Stream schließen" und „Daten verwerfen" sind jetzt getrennt: beim Unmount endet nur der SSE-Stream, ein echter Reset passiert ausschließlich beim Wechsel der `simulationId`. Gegen unbegrenztes Wachstum über viele Simulationen hinweg bleibt die bestehende `MAX_STORES`-LRU die Rückfallebene.
- **Der Feed wuchs unbegrenzt und rechnete bei jedem einzelnen Event alles neu.** [`frontend/src/composables/useSimFeed.ts`](frontend/src/composables/useSimFeed.ts) hielt Posts ohne Obergrenze; `twitterPosts` sortierte die komplette Liste und `redditTree` baute den vollständigen Baum bei jedem `ingest()` neu, gerendert über `TransitionGroup` ohne Windowing. Der Tab wurde dadurch wiederholt unbedienbar (`Input.dispatchMouseEvent timed out after 30000ms`), sodass die Schaltfläche zum Stoppen nicht mehr erreichbar war. Neu sind ein Ringpuffer mit `MAX_POSTS_PER_FEED = 500` und Batching pro Animation Frame: eingehende Posts werden gepuffert und gebündelt einmal je Frame übernommen. Die teuren Neuberechnungen laufen damit höchstens einmal pro Frame über höchstens 500 Einträge statt einmal pro Event über eine unbegrenzte Liste. Dedup und der `simulation_id`-Filter greifen weiterhin sofort beim `ingest()`.
- **Beim Herausfallen aus dem Ringpuffer wird die Dedup-Menge mitgeführt.** Sonst wäre das `post_id`-Set die neue unbegrenzte Struktur gewesen, und ein später erneut eintreffender alter Post wäre fälschlich als Duplikat verworfen worden.
- **Nicht enthalten: der Snapshot beim Mount.** Ein frisch geöffneter Tab bei laufender Simulation zeigt weiterhin „Noch keine Aktivität". Der dafür vorgesehene bestehende Endpoint liefert rohe OASIS-SQLite-Zeilen ohne `persona_id` und ohne `voice_register`; `PostCreatedEventSchema` ist `.strict()` und verlangt beide. Ein Mapping wäre nur durch Erfinden von Werten möglich gewesen. Nachgezogen in [#1009](https://github.com/arn0ld87/agora/issues/1009).
- **Regressionsnachweis:** Unmount/Remount-Test in [`frontend/src/views/v4/steps/__tests__/StepSimulationFeedView.spec.ts`](frontend/src/views/v4/steps/__tests__/StepSimulationFeedView.spec.ts), Ringpuffer- und Dedup-Tests in [`frontend/src/composables/__tests__/useSimFeed.spec.ts`](frontend/src/composables/__tests__/useSimFeed.spec.ts). Bestehende Specs, die den Feed-State synchron direkt nach dem Handler-Aufruf prüfen, stellen `requestAnimationFrame` lokal auf synchrone Ausführung um — ihre Erwartungen bleiben dadurch unverändert gültig.

### Fixed (Interview-Gate prüfte den falschen Zustand — 2026-08-02, Issue #999)

- **`GraphToolsService.interview_agents()` brach nach jeder abgeschlossenen Simulation sofort mit einem terminalen Soft-Fail ab.** Der Early-Check fragte nur `SimulationRunner.check_env_alive()` ab — diese Prüfung liefert seit PR #997 `False`, sobald der `runner_status` in `{stopped, completed, failed}` liegt, also im Normalzustand jeder Simulation, für die ein Report erzeugt wird. `interview_agents_batch` wurde dadurch nie erreicht, es entstand keine `agent_quote`-Evidence, und ein Claim konnte die ADR-0002-Stufe `agent_grounded` nicht erreichen. Der in PR #997 eingeführte Direktinterview-Fallback lag hinter diesem Gate und war für den ReportAgent damit faktisch toter Code.
- **Neu: `interviews_possible`.** Das Gate in [`backend/app/services/graph_tools.py`](backend/app/services/graph_tools.py) fragt nicht mehr die IPC-Liveness ab, sondern ob ein Interview überhaupt beantwortbar ist — wahr, wenn entweder die IPC-Umgebung lebt oder persistierte Personas den Direktpfad tragen. Die Logik liegt als gleichnamige Funktion in [`backend/app/services/sim/interview_client.py`](backend/app/services/sim/interview_client.py), `SimulationRunner` bekommt dafür eine gleichnamige Classmethod.
- **Die Kostenschutz-Invariante aus Sub-Slice 05.6 bleibt erhalten.** Der Early-Check verhindert weiterhin, dass zwei teure LLM-Calls (Agenten-Auswahl und Fragen-Generierung, zusammen 30–60 Sekunden) für ein aussichtsloses Interview laufen. Ebenso bleibt der Anti-Retry-Hinweis erhalten, der den ReACT-Loop davon abhält, das Tool wiederholt aufzurufen. Neu ist nur, dass der Soft-Fail die konkrete Ursache nennt (weder laufender Worker noch persistierte Personas) statt des pauschalen „TERMINALLY UNAVAILABLE".
- **Regressionstest:** [`backend/tests/services/test_graph_tools_interview_uses_direct_path.py`](backend/tests/services/test_graph_tools_interview_uses_direct_path.py) belegt, dass `interview_agents_batch` bei toter IPC-Umgebung und verfügbarem Direktpfad tatsächlich aufgerufen wird. Vor dem Fix schlägt er mit „Expected 'interview_agents_batch' to have been called once. Called 0 times." fehl. Für dieses Gate existierte zuvor kein Test.
- **Die Kostenschutz-Assertion im bestehenden Test [`backend/tests/services/test_graph_tools_interview_soft_fail.py`](backend/tests/services/test_graph_tools_interview_soft_fail.py) griff zuvor ins Leere.** Sie prüfte ein Attribut `llm_client`, während der Produktivcode über die Property `llm` auf `_llm_client` zugreift. Die Assertion sitzt jetzt auf dem real gelesenen Pfad.
### Fixed (Interview-Antworten nutzten den falschen API-Key — 2026-08-02, Issue #1000)

- **Der Direkt-Interview-Pfad baute den `LLMClient` ohne `api_key` und ohne Connection-Bezug.** `_default_client_factory` in [`backend/app/services/sim/interview_direct.py`](backend/app/services/sim/interview_direct.py) setzte nur `llm_model` und `llm_base_url` aus dem Lauf. In [`backend/app/llm/client.py`](backend/app/llm/client.py) greift die Registry-/SecretResolver-Auflösung aber nur bei `model is None` — bei explizit gesetztem Modell, hier immer der Fall, blieb `api_key` leer und fiel auf `Config.LLM_API_KEY` zurück. Ein Key, der ausschließlich verschlüsselt in der ProviderConnection liegt, erreichte den Pfad nie. Der 1-zu-1-Chat antwortete deshalb mit HTTP 400 („Please pass a valid API key"), obwohl derselbe Provider unmittelbar zuvor den kompletten Report erzeugt hatte. Regression aus PR #997, die diesen Pfad neu angelegt hat.
- **Die naheliegende Lösung ging nicht, weil der Lauf keine Connection-Referenz persistiert.** In `simulation_config` landen nur `llm_model` und `llm_base_url`; die `provider_id` der aufgelösten Route wird nicht mitgeschrieben. Der einzige persistierte Route-Snapshot mit Connection-Bezug hängt an der `run_id`, nicht an der `simulation_id`, und von dort führt kein bestehender Codepfad zurück.
- **Neu: `resolve_connection_for_base_url` in [`backend/app/llm/factory.py`](backend/app/llm/factory.py).** Die im Lauf persistierte Base-URL identifiziert die Connection: die Funktion sucht die eindeutige aktivierte ProviderConnection mit passendem Endpunkt und löst deren Secret auf. Dabei wird bewusst dieselbe Normalisierung wiederverwendet, mit der Legacy-Profile an Connections gebunden werden (`normalize_endpoint_url` / `canonical_connection_base_url` aus [`backend/app/services/profile_connection_resolver.py`](backend/app/services/profile_connection_resolver.py)) — keine neue lokale Endpunkt-Heuristik. Damit gilt auch für den Interview-Pfad die Invariante aus Issue #778: API-Key und Base-URL stammen immer aus derselben Quelle.
- **Mehrdeutigkeit wird nicht still aufgelöst.** Tragen mehrere aktivierte Connections denselben normalisierten Endpunkt, wird kein Secret aufgelöst; die Mehrdeutigkeit wird geloggt statt stillschweigend die erste Connection zu nehmen.
- **Der globale Key wird nie mehr mit der Base-URL des Laufs kombiniert.** Trifft der Endpunkt eine aktivierte Connection, deren Secret aber fehlt oder sich nicht entschlüsseln lässt, wäre `Config.LLM_API_KEY` zuvor an genau diesen fremden Endpunkt gegangen — also derselbe Fehler, den dieses Issue behebt, nur eine Ebene tiefer. Ebenso, wenn zum Endpunkt gar keine Connection existiert und er nicht der globale ist. In beiden Fällen erfolgt jetzt eine vollständige Degradierung auf die aktive Konfiguration statt einer halben Route aus zwei Quellen.
- **`Config.LLM_API_KEY` bleibt eine benannte Degradierung.** Der globale Fallback greift nur noch, wenn der Lauf auf denselben Endpunkt zeigt, aus dem der Key stammt, und dieser Fall wird als solcher geloggt, statt unbemerkt zu passieren.
- **Die Fehlerursache erreichte das Frontend gar nicht.** `_echo_result` in [`backend/app/api/simulation_interviews.py`](backend/app/api/simulation_interviews.py) antwortet bei fachlichen Interview-Fehlern bewusst mit HTTP 200 und legte die Ursache ausschließlich verschachtelt unter `data` ab; im Direktpfad steht sie sogar nur je Agent unter `data.result.results[<key>].error`. Der Response-Interceptor des Frontends liest aber nur top-level `error`/`message` — angezeigt wurde deshalb „Unbekannter Fehler". Der Envelope spiegelt die Ursache jetzt additiv als top-level `error` (und `code`, falls vorhanden); `data` und der HTTP-Status bleiben unverändert, damit bestehende Consumer nicht brechen.
- **Frontend zeigte den Provider-Fehler als Netzwerkfehler an.** Beide `catch`-Blöcke in [`frontend/src/components/Step5Interaction.vue`](frontend/src/components/Step5Interaction.vue) wrappten jeden Fehler unbesehen als `errors.network` — die Diagnose zeigte in die falsche Richtung. Die Klassifizierung liegt jetzt in der testbaren Funktion [`frontend/src/utils/interviewErrorMessage.ts`](frontend/src/utils/interviewErrorMessage.ts): 401/403 als Authentifizierungsfehler, übrige 4xx als Anfragefehler unter Beibehaltung der Backend-Meldung, 5xx als Serverfehler. Ein Envelope-Fehler in einer 200er-Hülle gilt ausdrücklich nicht mehr als Netzwerkfehler — genau dieser Fall trat produktiv auf. Ohne `status` bleibt es beim Netzwerkfehler.
- **Regressionsabsicherung:** Die zuvor 24 Tests in `backend/tests/services/sim/test_interview_direct.py` enthielten keine einzige Assertion zu `api_key`, `SecretResolver` oder `Config.LLM_API_KEY`. Neu abgedeckt sind die Auflösung des Connection-Secrets bei leerem `Config.LLM_API_KEY`, die geloggte Degradierung, das Durchreichen der Fehlerursache im Envelope (inklusive der Direktpfad-Form mit Fehlern je Agent) sowie die Fehlerklassifizierung im Frontend.

### Fixed (Budget-Telemetrie — 2026-08-01, PR #998, Refs #764)

- **Ein lokaler Verarbeitungsfehler nach HTTP 200 zählte nicht als Providerattempt.** Nach erfolgreichem `create()` kann die Antwortverarbeitung noch scheitern — leeres `choices`, `message` ohne `content`, fehlende `usage`-Attribute. Diese Exception flog bisher am Telemetriepfad vorbei: `_provider_attempt` hatte den HTTP-Attempt bereits als Success verbucht, für den anschließend fehlgeschlagenen lokalen Schritt entstand aber weder Failure-Event noch `_budget_record`. Der weiche `max_llm_calls`-Limit zählte den Call damit nicht mit, und die Invocation-Telemetrie verlor ihn still. Jetzt entsteht genau **ein** Failure-Event und **ein** Record, die Exception bleibt unverändert — kein zusätzlicher Providerrequest, kein doppeltes Event.
- **Abgerechnete Tokens bleiben im Fehlerfall erhalten.** `usage` wird vor dem `choices`-Zugriff gelesen: eine malformed Antwort kann trotzdem Prompt- und Completion-Totals tragen. `run_usage_ledger._Bucket.add` leitet Verbrauch und Kosten ausschließlich aus den Event-Feldern ab — fehlen sie, ist der Call zwar gezählt, sein Verbrauch aber unbekannt, und nachfolgende harte Token- und Kostenchecks lassen zu viele Folgecalls durch. Nicht-numerische Providerwerte werden per `isinstance`-Guard verworfen statt als Tokenzahl ins Ledger zu wandern.
- **Herkunft:** Restpunkt aus dem Review zu #764. Der Fix lag als uncommittete Änderung in einem Worktree und ist beim Abschluss von PR #975/#976 nie in einen PR gewandert; beim Branch-Cleanup aufgefallen.

### Fixed (Durchlauf-Blocker aus dem Browser-Test — 2026-08-01, PR #997)

- **Interview-Chat antwortete nach Simulationsende nie und lief in einen 120-Sekunden-Timeout.** Zwei Ursachen, von denen nur die erste offensichtlich war: `SimulationIPCServer.poll_commands()` wird vom regulären Simulations-Worker nie aufgerufen (einzige Aufrufer sind Tests und `run_parallel_simulation.py`), ein Interview-Kommando wurde also nie beantwortet. Zusätzlich meldete `check_env_alive()` weiterhin `alive`: `env_status.json` bleibt nach dem Lauf auf diesem Stand stehen, und ohne `pid` im Status lief auch die PID-Gegenprobe ins Leere. Der zweite Punkt ist der entscheidende — ohne ihn hätte jede Umleitung weiter auf den toten IPC-Pfad gezeigt.
- **Neu: [`backend/app/services/sim/interview_direct.py`](backend/app/services/sim/interview_direct.py).** Post-Simulations-Interviews brauchen keinen lebenden OASIS-Worker: Persona-Profile, Simulationskontext und Trace-DBs sind persistiert. Der Direktpfad beantwortet sie im Flask-Prozess über den zentralen `LLMClient` und spiegelt die IPC-Ergebnisform, sodass API-Layer und Frontend unverändert bleiben. Antworten werden als `action='interview'` in die Trace-DB der Plattform geschrieben, damit `/interview/history` auch diesen Pfad zeigt.
- **Bewusst `LLMClient.chat` statt `chat_json`.** Eine Interview-Antwort ist Freitext, exakt wie die OASIS-Interview-Action sie liefert. Ein JSON-Wrapper um einen einzelnen Prosa-String erzeugt nur eine zusätzliche Fehlerklasse: im Live-Test antwortete MiniMax-M3 trotz `schema=`-Parameter mit Prosa, beide Interviews brachen im JSON-Parser ab. Die chat_json-SSoT-Regel adressiert strukturierte JSON-Outputs, nicht Prosa.
- **Zwei bewusste Abweichungen vom IPC-Verhalten, beide dokumentiert.** Ohne `platform` fächert IPC auf beide Plattformen auf; der Direktpfad tut das nicht — dieselbe Frage an dieselbe Persona zweimal zu stellen verdoppelt nur Kosten, und das Frontend dedupliziert ohnehin auf eine Antwort pro `agent_id`. Personas werden dafür pro *effektiver* Plattform des Items aufgelöst, ein `platform`-Override je Item greift also wirklich, und ein Lauf ganz ohne `reddit_profiles` bleibt beantwortbar. `timeout` gilt als Deadline für den gesamten Batch statt pro Item: ohne sie summieren sich bei mehr als vier Interviews die Worker-Wellen zu einem Vielfachen des angefragten Timeouts auf.
- **Der Direktpfad nutzt die im Lauf persistierte Route.** Ein blanker `LLMClient()` würde die *aktuelle* Workspace-Auswahl auflösen; dieselbe Persona antwortete dann je nach Zeitpunkt mit einem anderen Modell oder über einen anderen Provider, nur weil das Interview nach Simulationsende gestellt wurde. `llm_model` und `llm_base_url` aus `simulation_config` haben Vorrang, mit sichtbarem Fallback auf die aktive Konfiguration, falls die Route nicht mehr nutzbar ist.
- **Die API antwortet nur noch mit 503, wenn weder Worker noch Personas verfügbar sind.** Vorher genügte ein geschlossener Worker.
- **Route-Transition blieb im Hintergrund-Tab hängen.** `App.vue` nutzt `<transition mode="out-in">`; ohne explizite `:duration` wartet Vue auf ein `transitionend`-Event. Chrome lässt CSS-Transitions in einem nicht sichtbaren Tab nicht laufen, das Event bleibt aus, die leave-Phase endet nie: die URL wechselt, der alte View bleibt stehen. Im Browser gegen `/dashboard` → `/runs` reproduziert. Mit expliziter Dauer nutzt Vue einen Timer statt des Events. Der Fehler ist in jsdom **nicht** nachstellbar — `getComputedStyle` liefert dort keine Transition-Dauern, Vue löst die leave-Phase ohnehin sofort auf; ein Unit-Test dafür wäre eine Attrappe gewesen und wurde deshalb wieder entfernt.
- **Graph-Build-Polling sammelte im Hintergrund-Tab nichts ein.** `usePolling` startet bei `document.hidden` weder Interval noch Immediate-Tick; ein dort gestarteter Build hing dauerhaft im Fortschritts-Spinner. Beide Polls laufen jetzt mit `pauseWhenHidden: false`, analog zu `useSimulationPrepare`.
- **Gelöschtes LLM-Profil überlebte im `localStorage`.** `agora.hero.profileId` ging als `profile_id` an den Sim-Start und brach dort mit „LLM-Profil … nicht gefunden" ab. Die Auswahl wird verworfen, sobald sie nicht mehr in der Profilliste steht — und ebenso, wenn der Profilabruf scheitert: ohne Liste ist die ID nicht verifizierbar, sie trotzdem zu senden wäre geraten. Bis der Abruf abgeschlossen ist, bleibt der Start zu.
- **`simulation_id` erreicht die Interaktions-Route.** `/v4/interaction/:reportId` kennt nur die `reportId`; Chat, Interview und Profil-Liste brauchen die `simulation_id`. `?runId=…` wird analog zu `StepReportView` durchgereicht, mit Rückfall auf die `simulation_id` des geladenen Reports. Ohne das blieb die Persona-Liste leer und Interviews gingen mit `simulation_id: undefined` raus.
- **ReportAgent-Antwort rendert als Text statt `[object Object]`.** `/api/report/chat` liefert `data.response` als Agent-Payload (`{ response, tool_calls, sources }`), nicht als String. `extractReportAnswer` packt ihn aus und hält die älteren Antwortformen am Leben; der Fallback-Text ist jetzt lokalisiert statt hartkodiert.
- **Unentschlüsselbarer Provider-Key riss die Discovery-Route als 500 mit.** Passt das Ciphertext nicht mehr zum aktuellen `AGORA_SECRET_KEY`, wird das jetzt als `invalid_credentials` genau dieser Connection gemeldet. Der Fang ist bewusst eng: fehlender oder ungültiger `AGORA_SECRET_KEY` und eine unlesbare Store-Datei sind globale Konfigurationsfehler — als Credential-Defekt getarnt sähe jede Connection einzeln kaputt aus und die eigentliche Diagnose verschwände. Dafür trägt der Store jetzt eine eigene `SecretDecryptionError` (Subklasse von `RuntimeError`, Bestandsaufrufer bleiben unberührt).
- **Irreführende `max_tokens`-Empfehlung im JSON-Fehlerpfad entfernt.** `chat_json` ruft `chat()` mit `require_complete=True`; eine am Token-Limit abgeschnittene Antwort hätte bereits `LLMOutputTruncatedError` geworfen. Wer die Fehlerstelle erreicht, hat eine vollständige, aber ungültige JSON-Antwort — der alte Hinweis „likely truncated — try raising max_tokens" hat Debugging systematisch in die falsche Richtung geschickt. Parse, Reparaturversuch und Diagnose liegen jetzt in `_parse_llm_json` und gelten auch für den nativen Ollama-Schema-Pfad, der vorher einen nackten `JSONDecodeError` warf.

### Security (Trivy-Container-Baseline aufgelöst, Fehldiagnose korrigiert — 2026-07-31, Issue #772)

- **CVE-2026-24049 (`wheel`) und CVE-2026-23949 (`jaraco.context`) sind aus `.trivyignore` entfernt.** Beide sind behoben — nicht durch das erwartete Basis-Image-Update, sondern durch den setuptools-Bump 80.9.0 → 83.0.0 (`33b3f310`, PR #828, seit 2026-07-22 in `main`). Der hebt vendored `wheel` auf 0.46.3 (fixed ≥ 0.46.2) und vendored `jaraco.context` auf 6.1.0 (fixed ≥ 6.1.0). Der Hardstop 2026-08-30 entfällt ersatzlos; es braucht keine Fristverlängerung.
- **Die ursprüngliche Begründung war falsch, und das ist der eigentliche Befund.** Die Einträge vom 2026-07-05 (`63e923db`) lauteten „OS-Layer, transitive via base image — Basis-Image-Update erforderlich". Tatsächlich enthält `python:3.14-slim` weder `wheel` noch `jaraco.context`: der CPython-Build nutzt `--with-ensurepip`, und `ensurepip` bündelt seit Python 3.12 weder `setuptools` noch `wheel` — ausgeliefert wird nur `pip`. Beide Pakete kamen ausschließlich über `setuptools/_vendor/` in die Backend-`.venv`, wo Trivys `python-pkg`-Analyzer die mitgelieferten `.dist-info/METADATA` auswertet. Ein Basis-Image-Update hätte diese Findings nie beheben können — die Ausnahme hätte bis zum Hardstop gestanden und wäre dann vermutlich verlängert worden, ohne dass jemand die Ursache berührt hätte.
- **Am realen Prod-Image verifiziert, nicht am Minimal-Testbild.** Vollständiger Build der Prod-Stage, Scan mit den CI-Optionen (`--severity CRITICAL,HIGH --ignore-unfixed`) und bewusst **ohne** `.trivyignore`: beide CVEs sind fort, die `.venv` enthält `setuptools-83.0.0` mit `_vendor/wheel-0.46.3` und `_vendor/jaraco_context-6.1.0`. Das Gate bleibt unverändert blockierend (`exit-code: "1"`).
- **Basis-Image-Digests nachgezogen** (reine Hygiene, unabhängig von den CVEs): `python:3.14-slim` auf `sha256:cea0e604…` und `python:3.14` auf `sha256:5f1cdbca…`, beide Stand 2026-07-14. Der slim-Digest ist vorher wie nachher Trivy-sauber; der Base-Digest senkt die HIGH/CRITICAL-Findings der Build-Stages von 129 auf 32 und beseitigt die einzige CRITICAL (`CVE-2026-56367`, imagemagick). `nginx:alpine` bleibt unverändert — der Pin entspricht bereits dem aktuellen Tag-Digest.
- **`.trivyignore` ist jetzt nach Hardstop gegliedert.** Vorher mischte ein einziger Kopfkommentar zwei Fristen (2026-09-28 für die nltk-Baseline, 2026-08-30 für die Container-Baseline), was beim Bearbeiten leicht die falschen Einträge mitgenommen hätte. Dazu ein Warnhinweis: Trivy löst Advisory-Aliase (GHSA ↔ CVE ↔ PYSEC) **nicht** auf — ein Eintrag greift nur unter der ID, unter der Trivy das Finding meldet.
- **Prozess-Lücke dokumentiert:** Die beiden CVEs standen nie in `docs/dependency-risk-exceptions.json`. Die Deadline-Prüfung in `cve-monitor.yml` liest diese Datei — ihr Hardstop wurde also nie maschinell überwacht, sondern existierte nur als Fließtext im Register. Künftig gehört jede `.trivyignore`-Zeile auch in die JSON.
- Recherche mit Primärquellen (NVD, OSV, GitHub Advisories, Debian Security Tracker, PyPI, `docker-library/python`): [`docs/2026-07-31-issue-772-cve-basisimage-research.md`](docs/2026-07-31-issue-772-cve-basisimage-research.md).

### Fixed (Herkunft der Routing-Entscheidung überlebt den Snapshot — 2026-07-31, Issue #901)

- **`AiModelRef.source` ging beim Seeden verloren und wurde als `legacy` zurückgelesen.** `seed_run_stage_routing` baute aus einer `AiModelRef` eine `StageLLMRoute` mit `provider_id`/`model`/`provider_options`; die Herkunft fiel weg, weil `StageLLMRoute` kein Feld dafür hatte. `ai_route_from_stage_route` schrieb beim Zurückprojizieren hart `source="legacy"`. Ergebnis: jede explizite UI-Modellwahl erschien im persistierten Snapshot und im `AiRouteAudit` als Legacy-Route — bewusste Nutzerwahl und Provider-Fallback waren nicht mehr unterscheidbar, weder im Audit noch in einer späteren Diagnose.
- **Zwei Vokabulare, bewusst getrennt gehalten.** `AiModelRefSource` (`stage-override`, `explicit`, `fallback`, …) beschreibt, **was das UI ausgewählt hat**; `RouteSource` (`stage_override`, `runtime`, `provider_fallback`, `legacy`, …) den **aufgelösten Routing-Zustand**. Die `StageLLMRoute` führt jetzt das UI-Vokabular wörtlich mit; die Abbildung auf `RouteSource` passiert erst bei der Projektion. Die umgekehrte Reihenfolge — beim Seeden auf `RouteSource` normalisieren — wäre verlustbehaftet gewesen: `explicit` und `project-default` haben dort kein exaktes Pendant, die Nuance wäre unwiederbringlich verloren.
- **Der Rückweg rät nicht.** `stage_route_from_ai_route` kann die Herkunft nicht aus `AiRoute.source` rekonstruieren, weil die Abbildung nicht injektiv ist (`runtime` ließe sich nicht eindeutig auf `explicit` zurücknehmen). Der Wert reist deshalb im bestehenden `__legacy_stage_route__`-Kanal mit, in dem bereits `temperature`/`max_tokens`/`reasoning_effort` transportiert werden — als `NotRequired`, damit Bestands-Options ohne den Schlüssel weiterhin validieren.
- **`fallback` ohne Grund lässt den Seed nicht scheitern.** `AiModelRefSource="fallback"` bildet auf `RouteSource="provider_fallback"` ab, dessen Validator einen nicht-leeren `fallback_reason` verlangt — diese Kombination ist über die UI real erreichbar: `AiModelPicker.vue` setzt bei einer unbekannten Item-ID `source: 'fallback'`, ohne einen Grund ableiten zu können, und `AiModelRefPayload` überträgt `fallback_reason` gar nicht erst. Eine harte Ablehnung im Seed wäre der falsche Ort gewesen: `seed_run_stage_routing` läuft in `api/simulation_run.py` **nach** `run_registry.create_run` und ist dort nicht in ein `try/except` gefasst — eine Exception hinterließe einen verwaisten `pending`-Run und antwortete mit HTTP 500. `_fallback_reason_for` füllt die Lücke stattdessen deterministisch mit `"unspecified_fallback"` auf. Der Wert ist bewusst als Lücke erkennbar und nicht als echter Grund getarnt; die Information „Fallback ohne angegebenen Grund" bleibt im Audit erhalten. Ein echter, mitgelieferter Grund wird unverändert durchgereicht.
- **`AiModelRefPayload` bleibt bewusst ohne `fallback_reason`.** Ein Feld zu übertragen, das an der einzigen erzeugenden Stelle immer leer wäre, hätte nur den Anschein von Vollständigkeit; der Grund ist im Typ dokumentiert.
- **Bestandsdaten brauchen keine Migration.** `ai_model_ref_source=None` ist der Default; solche Routen projizieren weiterhin auf `legacy` — exakt das Verhalten, das vor diesem Slice für *jede* Route galt.
- **`AiModelRefSource` liegt jetzt in `contracts/provider_types.py`.** `ai_provider_contract` importiert bereits aus `llm_routing_contract`; der für das neue Feld nötige Gegenimport wäre ein Zyklus gewesen. Der Name bleibt über einen Re-Export an alter Stelle importierbar.
- **Frontend-Spiegel nachgezogen — und das war kein Formalismus.** `LlmRouteSchema` (`frontend/src/contracts/llmRoute.ts`) ist `.strict()`, laut Kopfkommentar ausdrücklich damit das Schema parse-fähig bleibt, wenn das Frontend Routing-Defaults aus dem Backend zurückliest. Ohne den Spiegel hätte genau dieser Rücklesepfad an den neuen Feldern hart abgebrochen. Das lokale `pre-push-gate.sh frontend` hätte das **nicht** gefangen: sein Zod-Spiegel-Schritt prüft nur, ob beide Sichten als Datei existieren.
- **Zweiter Spiegel, aus dem Review nachgetragen: `LegacyStageRouteOptionsSchema` in `frontend/src/contracts/aiProviderContract.ts`.** Auch dieses Schema ist `.strict()` und spiegelt das TypedDict, das in diesem Slice `ai_model_ref_source` bekommen hat — es war zunächst übersehen worden. Heute kein Live-Bruch, weil `_serialize_public_ai_route` (`backend/app/api/llm_routing.py`) `__legacy_stage_route__` vor der Auslieferung entfernt; der Spiegel ist trotzdem die Aussage über den Vertrag, nicht über den aktuellen Serialisierungspfad. Der eigentliche Grund, warum die Drift unbemerkt blieb: `aiProviderContract.spec.ts` prüfte Key-Parität nur für `AiProviderOptionsSchema`, nicht für den Legacy-Kanal. Diese Paritätsaussage gilt jetzt auch dort, plus vier Fälle für fehlend/`null`/gültig/`RouteSource`-Vokabular.
- **Aus der Codex-Sichtung von PR #991: die Herkunft erreichte das Audit noch nicht.** `resolve_ai_route` setzt `AiRoute.source` auf den Namen der **gewinnenden Ebene** (`stage_override`, `run_override`, …) und verwirft dabei die `source` des Kandidaten — `AiRouteAudit.record_routing_resolved` schrieb genau diesen Wert. Eine bewusste Nutzerwahl, ein Run-Override und ein Provider-Fallback landeten im Audit also weiterhin alle als `stage_override`. Der persistierte `StageLLMRoute`-Snapshot trug die Herkunft korrekt; der Audit-Pfad nicht. Das Audit führt jetzt ein zweites Feld `ai_model_ref_source`, gelesen aus dem `__legacy_stage_route__`-Kanal, der die Auflösung unbeschadet übersteht (`resolve_ai_route` kopiert `provider_options` unverändert). Beide Fragen sind damit getrennt beantwortbar: welche Ebene gewonnen hat und was der Nutzer gewählt hat. Bestandsrouten ohne den Schlüssel liefern `None` statt zu brechen.
- **`AiModelRefPayload` trägt `fallback_reason` doch — die frühere Begründung war falsch.** `AiModelPicker.vue` liefert bei einer Fallback-Auswahl sehr wohl einen Grund: `unknown_provider` bei unbekannter Item-ID, `provider_offline` bei `status: 'unavailable'`, `provider_degraded` bei `status: 'degraded'`. Das Feld wegzulassen verwarf diese Diagnose in `Step4Report.buildModelSelection` und `useRunModelResolver.toPayload`, und `_fallback_reason_for` schrieb `unspecified_fallback` — der Grund wäre nur *scheinbar* unbekannt gewesen. Beide Builder reichen ihn jetzt durch, aber nur wenn vorhanden; ein leeres Feld im Request wäre kein Erkenntnisgewinn. Der Platzhalter bleibt als Netz für die Fälle, in denen wirklich kein Grund ableitbar ist.
- **Tests.** 23 Contract-Tests (`backend/tests/contracts/test_ai_model_ref_source_roundtrip.py`) für Abbildung, verlustfreien Round-Trip über alle `AiModelRefSource`-Werte, Bestandsrouten ohne das Feld und die `fallback`-Ablehnung — inklusive eines Wächters, der fehlschlägt, sobald `AiModelRefSource` einen Wert ohne Abbildung bekommt (sonst fiele er still auf `legacy` zurück, also genau in den Defekt aus #901). Dazu 9 Seed-Tests (`test_llm_routing_seed.py`) für die eigentliche Akzeptanz — die geseedete Route trägt die ursprüngliche Herkunft — darunter drei, die `fallback` mit `None`, leerem und nur aus Leerzeichen bestehendem Grund durch den Seed **und** die anschließende Projektion fahren. Dazu 10 Zod-Tests (`llmRouteSourceMirror.spec.ts`), die auch festhalten, dass `.strict()` als Drift-Melder erhalten bleibt. RED belegt: ohne die Zuweisung im Seed fallen 6 Tests.
### Fixed (E2E-Stack isoliert sich vom Dev-Stack — 2026-07-31, Issue #989)

- **Eigene `container_name`-Werte für den E2E-Stack.** `docker-compose.yml` und der Proxy-Override setzen feste Namen (`agora`, `agora-neo4j`, `agora-redis`, `agora-nginx`). Container-Namen sind Daemon-global und ignorieren den Compose-Projektnamen — `COMPOSE_PROJECT_NAME` isolierte deshalb **nicht**. Ein lokaler E2E-Lauf neben dem laufenden Dev-Stack scheiterte mit `Conflict. The container name "/agora-neo4j" is already in use`. Schlimmer war der Zustand danach: blieb ein E2E-Container zurück, adoptierte Compose ihn beim nächsten Dev-Start unter demselben Namen — samt dessen Neo4j-Speicherwerten. Bei knapp bemessenem Docker-RAM endete das in einer Restart-Schleife (`Invalid memory configuration - exceeds physical memory`), obwohl die `.env` des Dev-Stacks korrekt war. Das E2E-Override vergibt jetzt `agora-e2e`, `agora-e2e-neo4j`, `agora-e2e-redis`, `agora-e2e-nginx` und `agora-e2e-mock-models`. Die Service-Namen bleiben unverändert — Compose-DNS und der nginx-Upstream `agora:5001` hängen am Service-Key, nicht am `container_name`.
- **Fester Projektname `agora-e2e` statt des Verzeichnis-Defaults.** Compose leitet den Projektnamen sonst aus dem Verzeichnis ab: im Hauptrepo `agora`, in einem Worktree z. B. `989-e2e-env-idempotent`. `down` aus dem einen Verzeichnis räumte den Stack des anderen nicht ab. Über `AGORA_E2E_PROJECT` überschreibbar, falls zwei E2E-Stacks nebeneinander gebraucht werden.
- **Neu: [`scripts/e2e-compose.sh`](scripts/e2e-compose.sh) als Single Source of Truth der Compose-Invocation.** `e2e-up.sh`, `e2e-down.sh` und der Log-Dump in `global-teardown.ts` mussten die `-f`-Kette bisher händisch gleich halten. `global-teardown.ts` trug dazu den Kommentar „Compose-Befehl muss identisch mit e2e-down.sh / e2e-up.sh sein" — genau das war er **nicht**: `e2e-down.sh` lud das E2E-Override nicht mit, wodurch `mock-models` als Orphan des Projekts zurückblieb. `down` läuft jetzt mit derselben Dateiliste und zusätzlich `--remove-orphans`.
- **`e2e-up.sh` schreibt die `.env` idempotent.** Vorher reines `>>`. In CI fällt das nicht auf, weil die `.env` pro Job frisch aus `.env.example` entsteht — lokal wuchs sie mit jedem Lauf. Zwei konkrete Schäden: `AGORA_SECRET_KEY` landete mehrfach mit je frisch erzeugtem Fernet-Key in der Datei, der letzte gewinnt, also wurden Secrets unlesbar, die ein früherer Lauf verschlüsselt hatte; und `AGORA_E2E_LLM_MODE=stub` blieb stehen, sodass der Dev-Stack den Schalter beim nächsten Start übernahm und still Stub-Reports statt echter Modellantworten lieferte — ohne Fehlermeldung, nur eine Log-Zeile `E2E-Stub aktiv — ueberspringe LLM-Call`. Jetzt pro Schlüssel genau eine Zeile.
- **`e2e-down.sh` entfernt den Stub-Schalter wieder**, registriert als `EXIT`-Trap statt als letzte Zeile: `docker compose down` scheitert unter `set -e` durchaus (Daemon weg, Volume belegt) — genau dann darf der Schalter erst recht nicht liegen bleiben. Bewusst **nur** `AGORA_E2E_LLM_MODE`: `AGORA_SECRET_KEY` zu entfernen würde alles unlesbar machen, was damit verschlüsselt wurde.
- **`.env`-Manipulation liegt in [`scripts/lib/env-file.sh`](scripts/lib/env-file.sh), nicht doppelt in beiden Skripten.** Aus dem Review dieses Commits kamen drei Befunde, die alle am ersten Entwurf hingen und selbst nachgestellt wurden: (1) die feste Temp-Datei `.env.tmp` fiel durch `.gitignore` — bei einem Abbruch zwischen Redirect und `mv` hätte eine untrackte Datei mit `AGORA_SECRET_KEY`, `NEO4J_PASSWORD` und `AGORA_AUTH_TOKEN` im Klartext im Worktree gelegen; jetzt `mktemp` mit Zufallsnamen, `EXIT`-Trap und zusätzlich passende `.gitignore`-Muster. (2) `mv` übertrug den Modus der Temp-Datei auf die `.env` — gemessen `0600` → `0644`, eine stille Rechteaufweitung auf einer Datei voller Secrets; der Modus der Zieldatei wird jetzt übernommen, neue Dateien bekommen `0600`. (3) Das pauschale `|| true` hinter `grep` verschluckte nicht nur den legitimen Exit 1 („keine Zeile übrig"), sondern auch echte Fehler ab Exit 2 und schob danach eine abgeschnittene Datei über die `.env`. Beim Nachstellen dieses Falls fiel ein vierter, schwererer Punkt auf: ohne `set -e` lief das `mv` selbst nach fehlgeschlagenem Aufbau. Jeder Schritt bricht jetzt **vor** dem `mv` ab, und die Reihenfolge ist umgedreht — erst Inhalt schreiben, Modus zuletzt setzen, damit ein restriktiver Quellmodus die eigenen Schreibzugriffe nicht sperrt.
- **`e2e-up.sh` schreibt `AGORA_PROXY_PORT` jetzt immer.** Vorher nur bei gesetzter Variable — und die Defaults widersprachen sich: der Proxy-Override publiziert ohne Variable auf `8080`, während `e2e-up.sh` und `playwright.config.ts` auf `80` warten. Ein lokaler Lauf ohne gesetzten Port lief damit garantiert in den Health-Timeout. In CI fiel das nie auf, weil dort alle sieben Jobs `AGORA_PROXY_PORT: '80'` explizit setzen. Der Port wird bewusst **nur** aus der Process-Env gelesen: `e2e-up.sh` ist ein Kindprozess von Playwright, ein aus der `.env` gelesener Wert wäre für den Elternprozess unsichtbar — `playwright.config.ts` und `global-setup.ts` lesen beide nur `process.env.AGORA_PROXY_PORT`, der Stack wäre auf dem einen Port gesund und die Specs sprächen den anderen an. Ein nur in der `.env` stehender Wert wird deshalb überschrieben; das Runbook sagt das ausdrücklich.
- **Container-Namen tragen den Projektnamen als Präfix** (`${AGORA_E2E_PROJECT:-agora-e2e}-…`). Feste Namen hätten das Versprechen aus `e2e-compose.sh` gebrochen: Projekt-Netzwerke und -Volumes isolieren zwar, `container_name` aber nicht — ein zweiter Stack mit eigenem `AGORA_E2E_PROJECT` wäre an denselben Namen gescheitert wie zuvor am Dev-Stack. Verifiziert über `compose config` mit zwei verschiedenen Projektnamen.
- **Verifiziert am laufenden System, nicht nur am Skripttext.** Der E2E-Stack (Neo4j + Redis) lief neben dem produktiven Dev-Stack — fünf Container gleichzeitig, keine Namenskollision, beide gesund. `docker inspect` belegt getrennte Konfiguration: Dev-Neo4j behielt `heap_max=768m`/`pagecache=512m` aus seiner `.env`, der E2E-Container fuhr mit `512m`/`512m` aus dem Override. `e2e-down.sh` entfernte danach Container, Volumes und Netzwerk des Projekts `agora-e2e` restlos; der Dev-Stack blieb unverändert `healthy`. Die `.env`-Logik wurde separat gegen eine Sandbox-Datei geprüft: je eine Zeile pro Schlüssel über mehrere Läufe, fremde Einträge unangetastet, Modus bleibt `0600`, eine unlesbare Quelldatei lässt das Ziel unverändert und liefert einen Exitcode ungleich 0, ein `drop` auf einen nicht vorhandenen Schlüssel meldet korrekt „nichts zu tun", keine Temp-Reste, und ein `mktemp`-Name fällt nachweislich unter `.gitignore`. Der Trap greift auch, wenn `docker compose down` fehlschlägt.
- **Neu: [`docs/runbooks/e2e-local.md`](docs/runbooks/e2e-local.md)** — lokaler E2E-Lauf neben dem Dev-Stack, beide Varianten (Playwright fährt den Stack hoch / Stack von außen), die nötigen Env-Vars und die ephemeren Credentials, die `e2e-up.sh` **nicht** setzt. Der Befund in [`docs/ci-e2e-audit.md`](docs/ci-e2e-audit.md) §3 ist als behoben nachgetragen.

### Fixed (Hartes Run-Budget greift im Report-Pfad — 2026-07-31, Issue #978)

- **Der Budgetabbruch wurde in neun Fallback-Handlern verschluckt.** Ein Report-Run mit `{"max_llm_calls": 2, "enforcement": "hard"}` lief bis `status="completed"` durch statt mit `status="stopped"` und `termination_reason="budget_calls"` zu enden. Die im Issue formulierte Hypothese — der Report-Pfad binde den `LLMClient` ohne `run_id`, sodass `_budget_enforcer()` `None` liefert — hat sich am Code **nicht** bestätigt: die Bindung ist über `ReportGenerationService.start_generation` → `LLMClient.from_route(…, run_id=run_record["run_id"])` → `ReportAgent(llm_client=…)` korrekt verdrahtet, der Enforcer feuert. Die tatsächliche Ursache liegt eine Ebene höher: `except Exception`-Blöcke im Report-Agent-Aufrufpfad fingen den `BudgetExceededError` mit ab und lieferten einen Fallback-Wert, statt ihn durchzureichen. Je nachdem, welcher physische LLM-Call das Limit überschreitet, landete der Abbruch in einem davon und degradierte zu einem harmlosen Default-Text — der Run lief klaglos weiter. Betroffen: `report_agent.planning.plan_outline`, `report_agent.workflow.generate_section_metadata`, `report_agent.workflow._run_red_team_review`, `tool_execution.execute_tool`, `graph.insight_forge_tool.generate_sub_queries`, die drei Interview-Helfer in `graph_tools.GraphToolsService` — sowie der Handler in `workflow.generate_report`, der den Red-Team-Aufruf umschließt. Dieser letzte ist der entscheidende: ohne ihn hätte der Fix in `_run_red_team_review` **nichts** bewirkt, weil der dort durchgereichte Abbruch eine Frame höher erneut abgefangen worden wäre und die Folgezeile den Report auf `completed` gesetzt hätte. Alle neun reichen `BudgetExceededError` jetzt hart durch — nach demselben Muster, das `workflow._safe_generate_section_react` und der äußere Handler von `workflow.generate_report` bereits korrekt umsetzten.
- **Gilt für alle vier Budget-Dimensionen.** Der Fix prüft auf den Exception-Typ, nicht auf die Dimension; `calls`, `tokens`, `cost` und `time` werfen dieselbe `BudgetExceededError`. Weiche Limits sind nicht betroffen — sie werfen nicht, sondern schreiben `BudgetWarning`s über `record_after_call()`.
- **Simulationspfad war nicht betroffen.** Er hat mit `SubprocessBudgetGuard` und dem Monitor eine eigene Instrumentierung an Runden-Grenzen und fängt den Abbruch in `sim/monitor.py` selbst ab.
- **`run-budget.spec.ts` ist jetzt als eigener Job `run-budget-smoke` in `e2e-smokes.yml` verdrahtet.** Der Job-`name:` ist bewusst noch **kein** Required Check — erst nach mehreren stabil grünen Läufen wird er in die Branch Protection aufgenommen.
- **Zweite Ursache, im CI-Lauf des neuen Jobs sichtbar geworden: `fail_task()` setzte den Budgetabbruch wieder auf `failed` zurück.** Nachdem der Abbruch den Agent verließ, markierte `report_generation.run_generate` den Run korrekt per `mark_budget_abort()` als `stopped` + `termination_reason` — und rief unmittelbar danach `TaskManager.fail_task()`. Dessen `update_task()` spiegelt den Task per `RunRegistry.sync_task()` auf den Run zurück und überschrieb dabei `status="stopped"` samt Budgetbegründung mit `status="failed"` / `message="Task failed"`. Der E2E-Smoke sah exakt das (`Expected: "stopped", Received: "failed", message=Task failed`). `TaskStatus` kennt keinen `stopped`-Zustand; der Task bleibt fachlich `failed`. Behoben durch die Reihenfolge — `fail_task()` zuerst, der detaillierte Run-Update zuletzt — analog zu der in `api/simulation_prepare.py` (Issue #841) bereits dokumentierten Falle.
- **Dritte Ursache, im zweiten CI-Lauf sichtbar: `run-budget.spec.ts` umging den Onboarding-Guard nicht.** Nachdem die Backend-Aussage grün war (`stopped`, `termination_reason="budget_calls"`, `budget.status="exceeded"`, `usage.totals.llm_calls`), scheiterte erst Schritt 8 — die UI-Assertion auf `usage-totals`. Der DOM-Snapshot des fehlgeschlagenen Laufs zeigt den **Einrichtungs-Wizard**: `router/onboardingGuard.ts` leitet jede nicht-exempte Route auf `/onboarding` um, solange `onboarding_required` gilt — Default eines frischen E2E-Stacks. `page.goto('/runs/<run_id>')` landete also nie auf der Detailseite. Vier andere Specs räumen den Guard aus genau diesem Grund weg — `golden-gate-accessibility` und `ai-model-picker` über `ensureOnboardingDismissed()`, `upload-graph` und `minimal-report` per direktem `POST /api/onboarding/dismiss`; `run-budget.spec.ts` war die einzige ohne. Ergänzt — **keine** Assertion wurde dabei verändert oder abgeschwächt; die Spec prüft jetzt erstmals wirklich die Zielseite statt der Onboarding-Seite.
- **Vierte Ursache, erst durch den Guard-Bypass sichtbar: vier WCAG-AA-Kontrastverstöße auf der Run-Detailseite.** Schritt 9 der Spec (`axe` + 320px) lief bisher gegen den Onboarding-Wizard und traf mit dem Bypass zum ersten Mal `RunDetailView`. Ergebnis: 6 Knoten `color-contrast` [serious]. Nachgemessen (WCAG AA verlangt 4.5:1 für normalen Text): `.timestamp` `#999` auf Weiß = **2.85:1**; `.locked-badge` `#666` = **3.44:1**, weil der `.locked`-Elternteil `opacity: 0.8` trägt und den Text mitdämpft; `Alert.al-text` mit `--text-secondary` auf den getönten Varianten-Hintergründen = **4.43:1** (warning) bzw. **4.34:1** (danger). Behoben über Design-Tokens statt Hex-Werten — `--text-secondary` (5.07:1) für `.timestamp`, `--text-primary` für `.locked-badge` (8.25:1 inkl. Dämpfung) und für die getönten Alert-Varianten (14.7:1 / 14.4:1). `info`/`success` tragen dieselbe 10%-Tönung und wurden bewusst mitgezogen, statt auf den nächsten Zufallsfund zu warten. Das Gate wurde **nicht** aufgeweicht: die Verstöße sind Bestandsdefekte, die nur nie geprüft wurden.
- **Lokal verifiziert.** Der vollständige Smoke läuft grün gegen einen echten Compose-Stack (`AGORA_E2E_LLM_MODE=stub`): `1 passed`. Damit ist die Wirksamkeit aller vier Korrekturen belegt, nicht nur die Grün-Färbung eines Jobs.
- **Der Report-Resume-Pfad (`POST /api/runs/<id>/report`) bleibt bewusst unverändert.** Er baut seinen `LLMClient` ohne `run_id` (`backend/app/api/runs.py`), sodass dort gar kein Enforcer aktiv wird — ein eigenständiger Defekt mit anderer Ursache, nicht die hier behobene Reihenfolge-Falle. Wird als Folge-Issue nachgezogen statt in diesen Fix vermischt.
- **Tests.** 9 neue Backend-Tests (`backend/tests/services/report_agent/test_budget_exceeded_propagation.py`): acht isolieren je eine Fundstelle auf Funktionsebene, der neunte prüft die **Aufrufer**-Ebene — dass ein im Red-Team-Schritt entstandener Abbruch `generate_report` tatsächlich verlässt und den Report nicht auf `completed` setzt. Diese neunte Ebene fehlte zunächst; genau deshalb war der zuvor unentdeckte Re-Swallow im Aufrufer möglich. Funktionsebenen-Tests allein können solche Lücken strukturell nicht sehen. Dazu 2 Tests in `backend/tests/services/test_report_budget_abort_run_status.py`, die den Budgetabbruch mit **echtem** `TaskManager` und **echter** `RunRegistry` durchfahren und prüfen, dass der Run `stopped` + `budget_calls` behält und die Budget-Message nicht von `"Task failed"` verdrängt wird — dieselbe Aussage, die der E2E-Smoke am API-Rand trifft.

### Fixed (Evidence-Lese-Pfad fängt Claims ohne Evidence auf — 2026-07-31, Issue #968)

- **`migrate_legacy_claims_to_anchored` läuft jetzt im Live-Lese-Pfad.** Die Migration existierte seit P2.1, wurde aber ausschließlich in Evaluationstests und im Bulk-Migrations-Skript aufgerufen — nicht in `GET /api/report/<report_id>/evidence`. Persistierte v2-Maps mit Claims, die **gar keine** Evidence tragen und als `medium`/`high`/`verified` gelabelt sind, scheiterten deshalb am Validator `ReportClaimModel.non_low_claims_need_evidence` und die Route antwortete mit HTTP 400 statt mit dem Report. Die Migration ist die einzige Plausibilisierung, die solche Bestandsdaten auffängt, **ohne den Claim zu verwerfen**: sie hängt betroffene Claims nach `data_gaps` mit `gap_reason="no_evidence_bound"` um. „Ohne Datenverlust" wäre zu viel versprochen — `ReportSectionDataGapModel` trägt nur den (auf 1000 Zeichen gekürzten) `claim_text`; `claim_id`, `confidence_label`, `confidence_score`, `audit_trail` und `notes` gehen verloren. Gegenüber einer 400-Antwort, die den kompletten Evidence-Teil des Reports unlesbar macht (die Prosa-Routen sind nicht betroffen), ist das die richtige Abwägung — und das Datenqualitätsproblem wird über `gap_reason` sichtbar ausgewiesen statt still verdeckt.
- **Reihenfolge der Pipeline ist bindend und im Code begründet:** `migrate_v1_to_v2` → `migrate_legacy_claims_to_anchored` → `migrate_medium_seed_only_claims_to_low` (#963) → `EvidenceMapModel.model_validate`. Claims ganz ohne Evidence werden zuerst umgehängt; danach sieht die medium-Logik aus #963 nur noch Claims mit tatsächlich vorhandener Evidence und prüft keine bereits umgehängten Claims doppelt. Getauscht liefert die Pipeline ein **anderes** Ergebnis, kein bloß langsameres: `has_agent_grounded_evidence([])` ist `False`, #963 stuft einen orphan `medium`-Claim also zuerst auf `low` ab — danach greift `_ANCHOR_REQUIRED_LABELS` nicht mehr und der Claim bleibt dauerhaft als evidenzlose Aussage im Report stehen (`claims=[claim_90:low], data_gaps=[]` statt `claims=[], data_gaps=[1]`). Wächter dieser Ordnung ist `test_orphan_medium_claim_becomes_data_gap`.
- **`low`-Claims ohne Evidence bleiben unangetastet** — sie sind vertraglich zulässig, und ein Umhängen würde gültige Aussagen aus dem Report entfernen. Durch eine eigene Gegenprobe abgesichert.
- **Keine Abschwächung der fünf ADR-0002-Hartanker.** Weder Validator noch Contract noch Wording wurden geändert; die Migration bereitet ausschließlich Bestandsdaten so auf, dass der unveränderte Validator sie beurteilen kann.
- **Tests.** 5 neue API-Tests in `backend/tests/api/test_report_evidence_route.py`: orphan `medium`, orphan `high`, orphan `verified`, die `low`-Gegenprobe und ein Idempotenz-Test, der alle drei Migrationen gemeinsam zweimal durch die Route schickt und Gleichheit der Antworten prüft.
### Fixed (Review-Findings zu PR #980 — 2026-07-31)

- **Falsche Trace-Behauptung in `frontend/playwright.config.ts` korrigiert.** Der Kommentar versprach „Trace beider Versuche“; `use.trace` steht aber auf `retain-on-failure`, das den Trace eines **bestandenen** Retrys verwirft. Der Kommentar nennt jetzt, was der Modus tatsächlich liefert — den Trace des fehlgeschlagenen Versuchs — und begründet, warum `retain-on-failure-and-retries` bewusst nicht gesetzt wird. Dieselbe Aussage in `docs/ci-e2e-audit.md` (§5, §8) nachgezogen. Keine Verhaltensänderung.
- **`docs/ci-e2e-audit.md` §9 als datierte Momentaufnahme eingefroren.** Ein Erledigt-Vermerk an E5 hätte das Dokument faktisch als fünften Tracker weitergeführt, obwohl AGENTS.md genau das untersagt. Die Tabelle hält jetzt nur noch fest, was zum Auditzeitpunkt offen war und warum — der Status lebt ausschließlich in #978/#979.
- **Branch-Protection-Angaben in `README.md`, `docs/STATUS.md` und `ROADMAP.md` korrigiert.** Alle drei behaupteten, `main` besitze **keine** Branch-Protection (Beleg: ein 404 der Protection-API). Nachgemessen: die Protection war bereits vor diesem Slice aktiv (15 Required Checks, inzwischen 17), `strict: true`, `enforce_admins: true`. Die Dokumentation war also schon vor dem Audit nachweislich veraltet.
- **Deutsche Schlusszeichen** (`"` → `“`) in den selbst verfassten Passagen von `docs/ci-e2e-audit.md` und `CHANGELOG.md`.

### Fixed (Codex-Findings zu PR #977 — 2026-07-31)

- **`retries: 1` allein hätte das E2E-Gate geschwächt.** Playwright beendet einen Lauf mit flaky-Tests mit **Exit-Code 0**; der Retry-Report allein hält den Check nicht rot. Da alle sechs Smokes Required Checks sind, wäre eine intermittierende Regression damit zum grünen Merge-Gate geworden — das Gate wäre schwächer gewesen als vorher, nicht nur besser instrumentiert. `failOnFlakyTests: !!process.env.CI` ergänzt: Der Retry liefert weiterhin den „flaky“-Ausweis im Report und — via `trace: retain-on-failure` — den Trace des fehlgeschlagenen Versuchs; der Lauf bleibt aber rot.
- **Falsche Aussage in `docs/ci-e2e-audit.md` §9 korrigiert.** Der Text nannte einen „neuen `run-budget`-Job in CI“ als „lokal verifiziert“ — beides unzutreffend: es gibt keinen solchen Job, die Spec ist nicht verdrahtet, und lokal ist sie nicht grün, sondern deckt den offenen Defekt aus #978 auf. Der Pfad hat damit **keinerlei** CI-Abdeckung; genau das steht jetzt dort.
- **Auditdokument ist keine Planungsquelle mehr.** Die Empfehlungen E1–E9 werden ab sofort über GitHub Issues nachverfolgt (#978 für den Budget-Defekt, #979 als Sammel-Issue E1–E8), wie es AGENTS.md verlangt. `docs/ci-e2e-audit.md` bleibt Auditbefund und Belegkontext; bei Abweichungen gilt der Issue-Stand.
- **Branch-Protection erweitert (ehem. E5).** `Backend PR smoke gate` und `Frontend PR smoke gate` sind jetzt Required Checks — 17 statt 15, `strict: true` unverändert. Vorher war ein PR mit rotem Lint, Typecheck oder Unit-Test mergebar.

### Changed (CI- und E2E-Audit — 2026-07-31)

- **`concurrency` in allen 11 Workflows.** Bisher hatte kein einziger Workflow einen `concurrency`-Block; bei schneller Push-Folge liefen mehrere komplette Generationen weiter (beim E2E-Workflow je 6 parallele Docker-Stack-Jobs, gemessen ~3,2–3,8 min pro Job). Abgebrochen werden ausschließlich PR-Läufe: `push:main`, `schedule` und `workflow_dispatch` laufen zu Ende, weil dort jeder Lauf ein eigenständiger Nachweis ist. `docker-image.yml` bricht push/tag-Läufe ausdrücklich nicht ab (halb hochgeladene GHCR-Tags), `cve-monitor.yml` und `scorecard.yml` verwenden `cancel-in-progress: false`.
- **`timeout-minutes` auf allen 27 Jobs** (vorher 7). Ein hängender Job lief bis zum GitHub-Default von 360 min — betroffen waren u. a. alle 5 Jobs in `ci.yml` und alle 3 in `docker-image.yml`.
- **`persist-credentials: false` auf allen 27 `actions/checkout`-Schritten** (vorher 1). Vorab geprüft: kein Workflow führt `git push`/`commit`/`tag` aus oder nutzt eine PR-erstellende Action. **Schließt Issue #805.**
- **Vier fehlende SHA-Pins ergänzt** (`oven-sh/setup-bun`, `actions/upload-artifact` in `e2e-smokes.yml`) — Konsistenz zur Policy aus PR #719.
- **`drawer-focus-trap.spec.ts` läuft wieder.** Die Datei lief seit PR #723 in **keinem** Workflow — sieben Test-Definitionen waren toter Code. Sie hängt jetzt am bestehenden Golden-Gate-Job (inhaltlich ein Accessibility-Gate, gleicher Stack, ~11 s Zusatzlaufzeit) statt an einem eigenen Job mit komplettem Stack-Boot. Lokal verifiziert: 5/5 grün.
- **Playwright-Konfiguration gehärtet.** `forbidOnly` in CI (ein committetes `test.only` hätte den Rest der Datei still übersprungen und trotzdem grün gemeldet) und `retries: 1` **nur** in CI — Playwright meldet einen erst im Retry bestehenden Test als „flaky“, nicht als „passed“, macht Instabilität also sichtbar statt sie zu verstecken. Lokal bleibt es bei 0.
- **Kein Job umbenannt und kein `pull_request`-Trigger entfernt.** Die Branch-Protection auf `main` führt 13 Checks über ihren exakten `name:`-String; ein required Check, der nicht startet, blockiert den PR unbefristet.
- **Neu: [`docs/ci-e2e-audit.md`](docs/ci-e2e-audit.md)** — Baseline-Messungen, Bewertung jeder E2E-Spec, Vorher/Nachher-Tabelle und offene Empfehlungen.

### Fixed (Run-Budget-E2E-Spec: Preflight-Request — 2026-07-31, Audit-Befund)

- **`run-budget.spec.ts` schickte einen ungültigen Preflight-Request.** Die Spec übergab `POST /api/simulation/preflight-estimate` nur `{ simulation_id }`. Der Endpunkt leitet `num_agents`/`max_rounds` aus dem Artefakt `simulation_config` ab, das erst bei der Simulations-**Vorbereitung** entsteht — nicht durch `POST /api/simulation/create` + Profil-Seeding. Ergebnis: deterministisch HTTP 400 (`backend/app/api/simulation_budget.py:140-148`). Beide Felder werden jetzt mitgegeben; `simulation_id` bleibt im Body, damit der Config-Lookup-Zweig weiterhin durchlaufen wird. Der Fehler blieb unentdeckt, weil die Datei seit PR #975 in **keinem** Workflow lief.
- **~~Offen~~ — inzwischen behoben: das harte Budget griff im Report-Pfad nicht.** Nach dieser Korrektur lief die Spec weiter und scheiterte an ihrer Kernaussage — der Report lief trotz `max_llm_calls: 2, enforcement: "hard"` bis `completed` durch statt `stopped`. Die Assertion wurde **nicht** abgeschwächt und **kein** Produktivcode angepasst, um den Test grün zu machen; das Symptom wurde stattdessen als Issue #978 aufgenommen. Ursache und Behebung siehe „Fixed (Hartes Run-Budget greift im Report-Pfad — 2026-07-31, Issue #978)" oben; damit ist auch die dort beschriebene Nicht-Verdrahtung der Spec aufgelöst. Ursprüngliche Analyse in `docs/ci-e2e-audit.md` §5 und §9 (E9).

### Fixed (Budget-Guard-Proxy und Report-Navigation — 2026-07-30, PR #975-Review)

- **Budget-Guard-Proxy blieb für CAMEL unsichtbar.** `_UsageTrackingModelProxy` in `backend/scripts/sim_runtime/budget_guard.py` delegierte ausschließlich über `__getattr__`. CAMEL prüft vorinstanziierte Backends aber in `ChatAgent._resolve_models` per `isinstance(model, BaseModelBackend)` und wirft sonst `TypeError: Unsupported type for model parameter` — jede Simulation mit gesetztem `AGORA_RUN_ID` wäre beim Agent-Graph-Aufbau gestorben. Der Proxy delegiert jetzt zusätzlich `__class__` an das Target; der reale Typ (und damit die Instrumentierung von `run`/`_run`/`arun`/`_arun`) bleibt unverändert. Der Protokoll-Audit im Docstring nannte außerdem zwei nicht existierende Testnamen — auf die tatsächlichen Anker korrigiert.
- **`runId` überlebt die Report-Navigation.** `Step4Report.vue` navigierte bei Report-Start und Regenerierung mit `router.push({ name: 'Report', params: … })` ohne Query. Damit ging die Registry-Run-ID verloren und `loadRunUsage()` fiel still auf die `simulationId` zurück, obwohl `/api/runs/<id>` seit #764 die Run-Registry-ID braucht. Neue Utility `frontend/src/utils/reportRoute.ts` (`buildReportRoute`) hängt `?runId=<id>` an, sofern bekannt.
- **Tests.** 3 neue Backend-Tests (`isinstance`-Transparenz, echter `ChatAgent._resolve_models`-Pfad, Proxy-Typ bleibt distinct) sowie 3 Utility- und 3 Komponententests für die Query-Weitergabe bei Start, Regenerierung und fehlender `runId`.

### Added (Kosten-, Token- und Zeitbudgets für Runs — 2026-07-29, Issue #764)

- **Kanonischer Budget-Vertrag (v1).** Neuer Pydantic-Contract `backend/app/contracts/run_budget_contract.py` mit Schema-Dump (`run-budget-config`, `run-usage`, `run-budget-status`, `run-preflight-estimate`) und Zod-Spiegel `frontend/src/contracts/runBudgetContract.ts` inkl. Drift-Test. Geldbeträge ausschließlich als Integer-Micros; unbekannte Werte sind nullable mit ehrlichem Status (`unknown`/`estimated`/`free`/`measured`) statt 0. Architektur: [ADR-0012](docs/decisions/0012-run-budgets.md).
- **Preflight-Schätzung.** `POST /api/simulation/preflight-estimate` liefert gekennzeichnete Bereiche für Tokens, Kosten und Laufzeit (`is_estimate: true`, `data_quality`, Warnungen) auf Basis von Personas, Runden, Modell/Provider und historischen Verbrauchsdaten. Zentrale, versionierte Preisdatei `backend/app/data/model_pricing.json`; lokale Modelle werden als `free` ausgewiesen, unbekannte Preise als `unknown`.
- **Budgetdurchsetzung.** Weiche Limits erzeugen auditierbare `BudgetWarning`s; harte Limits verhindern planbare Modellaufrufe deterministisch (`RunBudgetEnforcer` im `LLMClient`, `SubprocessBudgetGuard` im OASIS-Subprozess an Runden-Grenzen, Zeitbudget im Simulations-Monitor). Der Abbruchgrund ist über das neue Manifest-Feld `termination_reason` (`budget_tokens`/`budget_cost`/`budget_time`/`budget_calls`) von technischem Fehler und Nutzerabbruch unterscheidbar; das `RunStatus`-Literal bleibt unverändert (additiv, keine Migration).
- **Verbrauchsmessung.** `llm_call_events.jsonl` pro Run erfasst Tokens, Latenz, Provider und Modell; `run_usage_ledger` aggregiert gesamt sowie pro Stage/Provider/Modell. `GET /api/runs/<id>` reichert `budget` und `usage` an, `GET /api/runs/<id>/usage` liefert die Aufstellung; Report-ZIP-Exporte enthalten `usage.json` und `budget.json` (secretsfrei, `serialize_for_manifest` lehnt Key-Material hart ab).
- **Vue-v4-Oberfläche.** Neue Komponenten unter `frontend/src/components/v4/run-budget/`: `RunBudgetForm` (Limits + weich/hart), `PreflightEstimateCard` (Schätzung vor dem Start), `RunResourceMonitor` (Live-Verbrauch, Restbudget, Warnungen, Abbruch-Banner) und `RunUsageBreakdown` (Abschlussanalyse nach Stage/Provider/Modell) — eingebunden in `HeroNewRun`, `Step3Simulation`, `Step4Report` und `RunDetailView`, vollständig i18n (de/en) und tastaturbedienbar.
- **Tests.** 100+ neue Backend-Tests (Contract, Pricing, Ledger, Enforcer, Subprozess-Guard, Monitor, Preflight, API, Secret-Hygiene) sowie Frontend-Unit-Tests für alle neuen Komponenten und Format-Utilities.

### Fixed (Evidence-Lese-Pfad bricht bei Legacy-medium-Claims nicht mehr — 2026-07-29, Issue #963)

- **Neue idempotente Migration `migrate_medium_seed_only_claims_to_low`** in `backend/app/services/evidence_migrations.py`. Seit PR #961 lehnt der `agent_grounded_for_medium`-Validator medium-Claims ab, die nicht mind. 1 `agent_quote` (mit nicht-leerem `quote`-Feld) UND mind. 1 `seed_corpus` enthalten. Persistierte schema-v2 Evidence-Maps aus der Zeit davor (medium-Claims nur auf `seed_corpus`/`graph_relation`-Basis) brachen beim Laden über `GET /<report_id>/evidence` mit HTTP 422, weil der Pfad nur `migrate_v1_to_v2` aufruft. Die neue Migration stuft solche medium-Claims vor der Validation auf `low` herab — Label-Matching case-insensitive wie in `migrate_legacy_claims_to_anchored`; `high`/`verified`-Claims bleiben unangetastet.
- **Geteilte Grounded-Logik statt Duplikat.** `_has_agent_grounded_evidence` in `backend/app/services/report_agent/evidence.py` (spiegelt exakt den Validator) ist jetzt öffentlich als `has_agent_grounded_evidence` und wird von der Migration importiert — Lazy-Import im Funktionskörper, weil `report_agent.schemas` selbst aus `evidence_migrations` importiert und ein Modul-Level-Import zirkulär wäre. Keine Verhaltensänderung am Downgrade-Pfad.
- **Lese-Pfad-Reihenfolge.** `get_report_evidence` in `backend/app/api/report.py` ruft jetzt `migrate_v1_to_v2` → `migrate_medium_seed_only_claims_to_low` → `EvidenceMapModel.model_validate`. Die Section-/Claim-Subrouten (`get_report_evidence_section`, `get_report_evidence_claim`) validieren nicht gegen `EvidenceMapModel` und bleiben bewusst unverändert (Folge-Issue-Kandidat).
- **Tests.** 10 neue Migrationstests in `backend/tests/test_evidence_migration.py` (seed-only/graph-only → low, leeres/fehlendes quote → low, agent-grounded bleibt medium, Case-Insensitivität, Idempotenz, None-/non-dict-/high-verified-Robustheit) plus API-Tests in `backend/tests/api/test_report_evidence_route.py`: eine Legacy-medium-seed-only-Map liefert HTTP 200 und der Claim kommt als `low` zurück (beweist: Migration läuft vor dem Validator).

### Changed (verhaltensneutrales OASIS-Runner-Refactoring — 2026-07-29, PR #962)

- **Neues Paket `backend/scripts/sim_runtime/`.** Drei Module ohne neue öffentliche Schnittstellen: `ipc.py` (oasis-freier `IPCHandler` mit Konstruktor-Injektion: `db_filename`, `interview_action_type`, `manual_action_cls`), `platform_runner.py` (oasis-abhängige `SinglePlatformRunner`-Basis mit Klassen-Attribut-Hooks `PLATFORM_NAME`/`PLATFORM_SLUG`/`PROFILE_FILENAME`/`DB_FILENAME`/`PLATFORM_TYPE`/`AVAILABLE_ACTIONS`/`AVAILABLE_ACTION_NAMES`/`GRAPH_GENERATOR` + Template-Method `_assign_initial_action`), `__init__.py`. Konstruktor-Injektion hält `ipc.py` testbar ohne torch/CAMEL — torch-Segfault auf Py3.14/aarch64 wird so umgangen.
- **IPC-Dedup.** `IPCHandler` aus `run_twitter_simulation.py` und `run_reddit_simulation.py` (jeweils ~280 LOC Duplikat) nach `sim_runtime/ipc.py` extrahiert. Entry-Points re-exportieren `IPCHandler`, `CommandType`, `ENV_STATUS_FILE`, `IPC_COMMANDS_DIR`, `IPC_RESPONSES_DIR` aus dem Paket → bestehende Importer-API bleibt erhalten.
- **Runner-Dedup.** Twitter- und Reddit-Runner reduziert auf dünne Subklassen der `SinglePlatformRunner`-Basis. `_install_runtime_profile`, `_sim_common`-Side-Effects, help-guard, oasis-/IPC-/agent_tools-Import als Modul-Attribut-Quelle und `main` bleiben in den Entry-Points. `_shutdown_event` wird in `main()` auf dem Basis-Modul gesetzt, weil `run` dort das Modul-Global liest.
- **Verhaltensneutral.** Reduziert netto ~1.084 LOC Duplikation ohne sichtbares Verhalten, CLI-Aufrufe oder Konfigurationssemantik zu ändern. Reddit-spezifischer Unterschied (mehrere Initial-Posts pro Agent → append an Liste) bleibt als `_assign_initial_action`-Override in `RedditSimulationRunner` erhalten; Twitter überschreibt weiterhin. Tests sichern diesen Unterschied: 27 IPC-Characterization-Tests + 52 lokale Tests grün, armserver mit echtem oasis: 220 passed + `_assign_initial_action`-Verhaltensunterschied mit echtem `ManualAction` verifiziert. `test_run_simulation_default_tokens.py` auf `sim_runtime/platform_runner.py` als neue SSoT für den 16384-Default umgestellt.
- **Hard Rules gewahrt.** Keine Secrets in Logs, keine zusätzlichen Env-Vars an OASIS-Subprozesse, keine API-/CLI-Konfigurationsänderungen.
- **P4 (Parallel-Extraktion) bewusst übersprungen** nach User-Sign-off: `create_model` ist nicht extrahierbar (`test_oasis_provider_dispatch` patcht `rps.ModelFactory` → Patch greift nur, solange `create_model` im `run_parallel_simulation`-Namespace lebt), `ParallelIPCHandler` (~440 LOC) teilt sich nicht mit dem single-platform `IPCHandler` (redis-integriert, andere Methoden) → Modul-Verschiebung ohne echtes Dedup, parallel-Runner außerdem nicht verhaltensverifizierbar (torch-Segfault) — pure Verschiebung wäre Risiko ohne gegenseitigen Nutzen.
- **Verifikation.** Backend PR smoke gate (ruff + mypy + pytest-contracts), Schema-Drift, Pydantic-Contract-Tests, Evidence-Quality-Gate, Version-Drift-Check, Frontend smoke gate, alle Playwright-Smokes, CodeQL (python + js-ts), GitGuardian, Trivy, Dependency Review — alle grün.

### Fixed (medium-Confidence-Gating nach ADR-0002 fixiert — 2026-07-29, Issue #906)

- **Defekt 1: `agent_grounded_for_medium`-Validator ergänzt.** `ReportClaimModel` in `backend/app/contracts/report_contract.py` kannte keinen Validator für das `medium`-Label, obwohl ADR-0002 die Stufe `agent_grounded` (`agent_quote` + `seed_corpus`) dafür vorsieht. medium-Claims mit ausschließlich `seed_corpus`- oder inferred-Evidence passierten unbeanstandet — der Kernbefund aus Issue #906 (≈325 medium-Claims nur auf Seed-Basis). Der neue `model_validator(mode="after")` lehnt medium ab, wenn nicht mind. 1 `agent_quote` (mit nicht-leerem `quote`-Feld, ADR-0002 Z. 54) UND mind. 1 `seed_corpus` vorliegen; `supports_claim` ist für medium bewusst nicht Pflicht. Die fünf ADR-0002-Hartanker bleiben unangetastet, kein `0002-supersedes.md`.
- **Defekt 2: `auto_downgrade_unsupported_high_claims` dynamisch medium/low.** `backend/app/services/report_agent/evidence.py` stufte nicht-cross-stakeholder-taugliche `high`/`verified`-Claims pauschal auf `medium` ab — ab sofort abhängig vom Provenance-Mix: `medium` nur bei `agent_grounded` (`agent_quote` + `seed_corpus`), sonst `low` (Seed-only bzw. reine Agent-Quote ohne Korpusbezug). Sonst bestünde der downgegradete Claim den neuen medium-Validator nicht und der Report bräche genau dort hart ab, was die Präventivfunktion konterkariert. Der Validator selbst bleibt strikt; die Funktion liefert ihm nur ehrlich downgrade'te Daten. Gespiegelter Helper `_has_agent_grounded_evidence` mit `quote`-Pflicht.
- **Tests/Snapshots nachgezogen.** `test_evidence_source_kind.py`, `test_report_contract.py`, `test_evidence_auto_downgrade.py` um medium-Validator- und dynamische Downgrade-Tests ergänzt (11 neue Tests, 3865 collected). Eval-Fixtures (`bad/orphan_heavy`, `good/clean_small`, `good/medium_with_dedup`) relabeln inferred-only medium-Claims metrik-neutral auf `low`; `evidence_gating_single_stakeholder_high.json` um ein `seed_corpus`-Item erweitert, sodass der Auto-Downgrade auf `medium` greift, `cross_stakeholder_for_high` den Claim aber weiter ablehnt.
- **Dokumentation:** `CLAUDE.md`-ADR-Anker 1 Pfad `report_prompts.py` → `report_prompts/sections.py` korrigiert; `docs/STATUS.md` synchronisiert.

### Fixed (build-only startet jetzt auch bei Docs-PRs — 2026-07-28)

- `.github/workflows/docker-image.yml` `pull_request.paths` um `docs/**` und `**/*.md` erweitert. `build-only` war als Required Check in den Branch-Protection-Settings eingetragen, der paths-Filter schloss aber Doku- und Workflow-Änderungen aus — Docs-PRs hingen dauerhaft in „Expected — Waiting for status to be reported". Pro: jeder PR triggert den Build. Con: ~2 Min Extra-CI pro reiner Doku-PR.

### Changed (Worktree-Pfad auf T7 festgeschrieben — 2026-07-28)

- `CLAUDE.md` und `AGENTS.md` mit expliziter Pflicht-Sektion „Worktree-Pfad" ergänzt: `/Volumes/T7/Worktrees/agora/<slice-id>/`, `/private/tmp` verboten, T7-Mount vor `git worktree add` prüfen. `docs/runbooks/worktree-strategy.md` bleibt SSoT für Details. Globale `~/.claude/CLAUDE.md` analog angepasst.

### Changed (.gitignore um Tool-Artefakte erweitert — 2026-07-28)

- `.claude/workflows/`, `.code-review-graph` (Symlink-Variante, ohne trailing slash), `.env.bak-*` (alle Pre-Dedupe-Backups), `.envsitter/`, `.runtime/` werden jetzt ignoriert. Pro: keine versehentlichen Commits lokaler Tool-Zustände mehr; Con: bewusste Commits müssen explizit `git add -f` nutzen.
- Die im Working Tree liegenden Handover-Protokolle (`HANDOVER-2026-07-*.md`) wurden nach `docs/.local/2026-07-sessions/` verschoben. Sie sind Planungs-Artefakte und gehören laut `AGENTS.md` nicht ins Repo.
### Fixed (Simulations-Crash bei Persona-Generierung, Ollama-Probe gegen Nicht-Ollama-Provider, Chunk-Anfänge — 2026-07-28)

- **`AttributeError: is_patched` bei der Persona-Generierung behoben.** `backend/app/services/oasis_profile_generator.py` prüfte das gevent-Monkey-Patching über `gevent.monkey.is_patched("socket")`, das die eingesetzte gevent-Version nicht mehr bereitstellt — unter dem gevent-Gunicorn-Worker brach damit jede Simulation nach dem Knowledge-Graph-Build ab. Der Aufruf läuft jetzt über die öffentliche API `monkey.is_module_patched("socket")`, der `ImportError`-Fallback bleibt eng gefasst. Bei aktivem Patching wird weiterhin `gevent.pool.Pool` genutzt, sonst der `ThreadPoolExecutor`-Fallback.
- **Ollama-Discovery fragt keine Cloud-Provider mehr ab.** `backend/app/api/status.py` und `backend/app/api/simulation_lifecycle.py` strippten pauschal `/v1` von `LLM_BASE_URL` und hängten `/api/tags` an — bei aktivem MiniMax lief das in wiederholte `404`-Logzeilen gegen `https://api.minimax.io/api/tags`. Beide Pfade nutzen jetzt `resolve_ollama_tags_url` auf Basis der zentralen `detect_provider`-Registry; für Nicht-Ollama-Provider entfällt der Request und der Status meldet `reachable: null` mit `skipped: true` plus Grund.
- **`OLLAMA_BASE_URL` schlägt das Provider-Gate.** Wer die Variable setzt, benennt ausdrücklich einen Ollama-Server — der übliche Fall ist Chat über MiniMax bei gleichzeitigen Embeddings über ein lokales Ollama. Das Gate darf diesen Wunsch nicht überstimmen, sonst verschwindet ein real erreichbarer Server aus dem Status, sobald der Chat-Provider wechselt. Ist die Variable nicht gesetzt, bleibt das Gate hart und `LLM_BASE_URL` wird nicht als Ollama-URL interpretiert.
- **Frontend-Spiegel nachgezogen.** `SystemStatusOllamaSchema` erlaubt jetzt `reachable: null` sowie `skipped`/`reason`; ohne diese Erweiterung hätte die Zod-Validierung des Dashboards genau im übersprungenen Fall geworfen. `SystemHealthCard.vue` zeigt den Skip als neutralen `idle`-Zustand statt fälschlich als „nicht erreichbar".
- **`host.docker.internal` als lokale Ollama-URL zugelassen.** `ProviderConnectionUpsertRequest` akzeptierte nur `localhost` und Loopback-IPs. Im Container-Betrieb ist das die falsche Menge: `localhost` zeigt dort auf den Container selbst, und die einzige funktionierende Adresse für ein Ollama auf dem Host wurde mit „Invalid provider connection request" abgelehnt — der UI-Pfad zum Konfigurieren eines lokalen Ollama war unter Docker damit vollständig blockiert, obwohl `.env.docker.example` genau diesen Host vorgibt. `utils/endpoints.py::LOCAL_HOSTS` kannte ihn längst; der Contract hatte eine eigene, strengere Heuristik daneben. Bewusst enger als `LOCAL_HOSTS`: `0.0.0.0` bleibt abgelehnt, weil es eine Bind- und keine Ziel-Adresse ist. Zod-Spiegel und beide Testsuiten nachgezogen, inklusive Subdomain-Smuggling-Fällen (`host.docker.internal.attacker.test`).
- **Chunk-Anfänge beginnen nicht mehr mitten im Wort.** `split_text_into_chunks` in `backend/app/utils/file_parser.py` setzte den Folgechunk hart auf `end - overlap` und erzeugte dadurch Fragmente wie `"uß-, Rad- und …"` oder `"atische Kennzeichenerfassung …"`, die in der Embedding-/GraphRAG-Pipeline unbrauchbare Vektoren liefern. Der Start wird jetzt rückwärts auf einen Wortanfang gesnappt — die einzige verlustfreie Richtung, da ein Vorwärts-Snap den Rest von Wörtern verschluckt, die länger als der Overlap sind. Zusätzlich sichert ein Mindestfortschritt gegen das Entarten auf Ein-Zeichen-Schritte, das der alte Code bei `overlap > 0.3 · chunk_size` als Endlosschleife zeigte. Verlustfreiheit, Wortgrenzentreue und Terminierung sind über 336 Korpus-/Parameter-Kombinationen verifiziert; ein Wort, das länger als `chunk_size` ist, wird weiterhin zwangsläufig aufgetrennt.

### Removed (Unused Composables `useWorkspaceMode` und `useWorkspaceStatus` entfernt — 2026-07-28, Issue #908)

- `frontend/src/composables/useWorkspaceMode.ts` und `frontend/src/composables/useWorkspaceStatus.ts` mitsamt ihrer Specs unter `frontend/src/composables/__tests__/` entfernt. Beide Composables hatten nach der v4-Routen-Konsolidierung (ADR-0010) keine Importeure mehr.
- `StepWrapperViews.spec.ts` von obsoleten Mocks aufgeräumt; `GraphCanvas.vue` und `useRuntimeLlmOptions.ts` von Kommentaren befreit, die auf die gelöschte `MainView`-Komponente verwiesen.
- Keine Verhaltensänderung am Produktcode; nur Totholz-Bereinigung.

### Changed (Local-Endpoint-Erkennung in neutrales Modul verschoben — 2026-07-28, Issue #800)

- `_is_local_endpoint` und `LOCAL_NO_AUTH_API_KEY` waren als private Symbole in `backend/app/api/simulation_prepare.py` beheimatet, wurden aber bereits aus `runs.py`, `simulation_history.py` und `simulation_run.py` importiert. Beides zieht jetzt nach `backend/app/utils/endpoints.py` und wird öffentlich (`is_local_endpoint`, `LOCAL_HOSTS`).
- Whitelist-Logik (`urlparse`-basierter Hostname-Vergleich gegen `localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, `host.docker.internal`) und der Subdomain-Smuggling-Schutz (Gemini-Review PR #466) bleiben unverändert erhalten.
- Alle Aufrufer und Tests auf den neuen Importpfad umgestellt, kein Verhaltensunterschied.

### Changed (hartkodierte PageHeader-Texte auf vue-i18n umgestellt — 2026-07-28, Issue #796)

- `title`/`subtitle`/`label`-Literale in `HistoryView.vue`, `CompareView.vue`, `StepEnvSetupView.vue`, `StepReportView.vue`, `StepInteractionView.vue`, `StepGraphBuildView.vue` und `StepSimulationView.vue` laufen jetzt über `$t()` statt hartkodierter deutscher Strings, mit neuen Keys in `de.json` und `en.json`.
- Betroffene Specs prüfen den i18n-Key gegen befüllte `messages` statt das deutsche Literal gegen leere `messages`.

### Changed (Legacy-Model-Picker-Guard um ActiveModelBadge.vue erweitert — 2026-07-28, Issue #911)

- `ActiveModelBadge.vue` (entfernt in Issue #835) ist jetzt in `REMOVED_PATHS` von `.github/scripts/check_legacy_model_picker.py` gelistet — eine Wiedereinführung der Datei schlägt künftig schon bei bloßer Existenz fehl, unabhängig von Importen.
- `test_deprecated_target_allows_import`/`test_non_deprecated_target_still_flags` auf `useRuntimeLlmOptions.ts` als Testobjekt umgestellt, da `ActiveModelBadge.vue` selbst nicht mehr als Positiv-/Negativ-Fixture taugt.
- Docstring dokumentiert: die `@deprecated`-Read-Adapter-Freigabe greift jetzt faktisch nur noch für Stores/Composables, da alle bisherigen Komponenten-Ausnahmen in `REMOVED_PATHS` stehen.

### Fixed (Persona-Detail-Level nur einmal pro Generierung aufgelöst — 2026-07-28, Issue #882)

- `_resolve_persona_detail_level()` wird jetzt einmal in `_generate_profile_with_llm` aufgelöst und als `detail_level`-Parameter an `_build_individual_persona_prompt`/`_build_group_persona_prompt` durchgereicht, statt dort erneut aufgelöst zu werden. Bei unbekanntem `AGORA_PERSONA_DETAIL_LEVEL` erscheint die Warnung dadurch nur noch einmal statt doppelt pro Persona.
- Zwei neue Regressionstests verifizieren die Aufruf-Anzahl (`test_issue_882_resolve_persona_detail_level_called_once_individual`/`_group`).

### Changed (v3-Inhaltskomponenten nach v4 migriert — 2026-07-28, PR #938, Issue #922)

- Die drei verbleibenden v3-Inhaltskomponenten `Step2EnvSetup.vue`, `Step3Simulation.vue` und `Step4Report.vue` sind nach `frontend/src/components/v4/steps/` migriert (RENAMED, Inhalt an v4-Typografie und -Ordnerstruktur angepasst). Die v3-Originale sind entfernt; die v4-Wrapper-Views binden die v4-Komponenten direkt ein.
- `EnvSetupModelPanel.vue` enthält nur noch den kanonischen `AiModelPicker` und den Sprach-Selector. Legacy-Credential-Override-Forms (Runtime-Provider-Toggle, Session-Key-Feld, Base-URL-Feld, `modelOption`/`customModel`-Select) sind entfernt.
- `useRuntimeLlmOptions.ts` (credential-basierter Runtime-Provider-Override, `@deprecated` Slice 5.5) ist entfernt; `main.ts` ruft `cleanupStaleRuntimeLlmStorage` nicht mehr auf. `useEnvForm` führt `modelOption`/`customModel` ohne Persistenz weiter, bis [Issue #903](https://github.com/arn0ld87/agora/issues/903) die Ablösung abschließt.
- `check_legacy_model_picker.py` kennt die drei migrierten v3-Pfade als `REMOVED_PATHS` und meldet ihre Rückkehr als Regression.
- Step2-`triggerPrepare` serialisiert `ai_model_ref` nur noch aus einer expliziten Nutzer-Auswahl (`selectedModelOverride`), nicht aus dem beim Mount übernommenen Workspace-Default (`selectedModelRef`). Ein bloß akzeptierter Default erzeugt keinen Backend-Override mehr und unterdrückt weder das konfigurierte Projekt-Profil noch den prepared-Shortcut (Codex-Review P1).
- Persona-Filter "more"-Button setzt `showAllPersonas` statt des nicht existierenden `showAllHomeLayout`, sodass `visiblePersonas` bei >24 Treffern korrekt expandiert (Codex-Review P2).
- Tests aktualisiert: `Step2EnvSetup.providerOverride.spec.ts` und `useRuntimeLlmOptions.spec.ts` entfernt (Pfade existieren nicht mehr); übrige Step2/3/4-Specs importieren die v4-Komponenten. `main.spec.ts` erwartet keinen `cleanupStaleRuntimeLlmStorage`-Aufruf mehr.

### Fixed (Bolt-Connection-Errors unter Gunicorn-Gevent-Worker — 2026-07-28, PR #937, Issue #933)

- `OasisProfileGenerator.generate_profiles_from_entities` erkennt, ob `gevent.monkey` das `socket`-Modul gepatcht hat (Gunicorn `-k gevent --preload`). In diesem Fall läuft die parallele Persona-Erzeugung über ein natives `gevent.pool.Pool` mit `imap_unordered` auf demselben OS-Thread, statt OS-Threads mit kooperativ geschedulten Sockets zu mischen. Das behebt die „Failed to write data"-Bolt-Fehler beim initialen Persona-Burst in parallelen Simulationen.
- Im Nicht-Gevent-Pfad (lokaler/dev-Betrieb) bleiben `ThreadPoolExecutor` und `as_completed` erhalten. Die Ergebnisverarbeitung läuft jetzt zwingend innerhalb des `with`-Blocks, sodass `shutdown(wait=True)` erst nach dem Konsum greift — der Realtime-Fortschritts-Callback und die inkrementellen `reddit_profiles.json`/`twitter_profiles.csv`-Writes funktionieren wieder wie dokumentiert.
- Beide Ausführungspfade nutzen eine vereinheitlichte `_process_result`-Behandlung (Profile ablegen, Lock-zähler, Realtime-Write, Progress, Logging), um Code-Duplikation und abweichendes Fallback-Verhalten zu vermeiden.
- Gevent-Pfad mit `try/finally` + `pool.join()` abgesichert, sodass bei Exceptions keine Greenlets den Pool überleben.
- `GraphBuilderService.add_text_batches` bleibt bewusst beim Standard-`ThreadPoolExecutor`: CPU-bound PyTorch/Transformers NER & Embedding benötigen echte OS-Threads und sind mit gevent-Greenlets nicht stabil.
- Neuer Unit-Test `test_gevent_pool_execution_fallback` mockt `gevent.monkey.is_patched("socket")` über `monkeypatch.setitem(sys.modules, ...)` (pytest restauriert die Moduleinträge nach Testende) und verifiziert, dass der Generator den gevent-Pool korrekt ansteuert.

### Changed (SimulationConfigGenerator auf schema-validierten LLMClient.chat_json umgestellt — 2026-07-28, PR #936)

- `SimulationConfigGenerator` erzeugt Zeit-, Ereignis- und Agenten-Konfigurationen jetzt ausschließlich über das SSoT `LLMClient.chat_json` mit Pydantic-Response-Modellen aus `simulation_config_schemas`. Der rohe `OpenAI(...)`-Client wurde aus der Klasse entfernt, sodass keine direkten `client.chat.completions.create`-Aufrufe mehr versehentlich wieder eingeführt werden können.
- Dynamische Schemavalidierung und Sanitization (Grenzwerte für `agents_per_hour`, `response_delay_min/max`, Agenten-Limits) greifen über Pydantic-Modelle; verletzende Werte werden vom Validator korrigiert statt die Konfiguration abzulehnen.
- Der `LLM_DISABLE_JSON_MODE`/`json_object`-Fallbackpfad bleibt erhalten und ist robuster: Bei Providern ohne `json_schema`-Support oder bei leicht trunkiertem JSON läuft ein Regex-basierter Reparatur-Fallback (`_try_fix_config_json`) auf die rohe `chat()`-Antwort.
- Retry-Strategie in `_call_llm_with_retry` entschaerft (Codex-Review P2): Die äußere 3-Versuche-Schleife retried nur noch Schema-/JSON-Fehler (`ValueError`, `pydantic.ValidationError`); Transport-Retry (`llm_call_with_retry`, bis zu 4 Versuche) bleibt allein bei `LLMClient.chat`. Zuvor konnten bis zu 24 Requests pro Konfigurationsschritt entstehen und Auth-Fehler wurden dreimal durchlaufen — jetzt steigen 4xx/final 5xx sofort durch.
- Umfangreiche Tests in `backend/tests/services/test_simulation_config_generator_refactored.py` decken Validierung, Grenzwert-Korrektur, Schema-Verletzung, Fallback-Verhalten und Batch-Aufrufe ab. Schließt #932.

### Added (Embedding-Konfiguration auf lokales Ollama gepinnt — 2026-07-27, Issue #934)

- Neuer Helper `activate_ollama_embedding` in `backend/app/services/embedding_configurations/activate_ollama.py` pinnt die aktive `EmbeddingConfiguration` idempotent auf `embeddinggemma:300m` (768-dim) via `EmbeddingConfigurationService.activate`. Vorhandene aktive Konfigurationen des gleichen Scopes werden auf `status='rolled_back'` gesetzt (Audit-Trail; Knoten bleibt erhalten, wird nicht gelöscht).
- Operator-Tool `backend/scripts/activate_local_ollama_embedding.py` macht die Festschreibung reproduzierbar dokumentierbar (`uv run python -m scripts.activate_local_ollama_embedding`, optionale Overrides per CLI-Flags).
- Vier Contract-Tests in `backend/tests/contracts/test_embedding_activate_ollama.py` decken Pinning, Vorgänger-Rollback, Idempotenz und Konvergenz nach Gemini→Ollama ab.
- ADR-0007-konform: alle Schreibpfade laufen ausschließlich über `EmbeddingConfigurationStore` / `ProviderConnectionStore` — keine direkten Cypher- oder Datei-Schreibwege. Gemini-Re-Embedding bleibt explizit außerhalb des Scopes.
- Hintergrund: nach dem Wechsel des Embedding-Providers von Gemini (429-Quotenfehler am 2026-07-27) auf lokales Ollama via `.env` war die Neo4j-`EmbeddingConfiguration`-SSoT noch nicht nachgezogen; der Helper schließt diese Lücke.

### Changed (Subagenten-Härtung — Härtung der historischen Subagenten ohne -m3-Suffix, 2026-07-27)

- Die sechs historischen Subagenten ohne Suffix (`agora-doc-worker.md`, `agora-evidence-auditor.md`, `agora-frontend-worker.md`, `agora-opus-reviewer.md`, `agora-refactor-worker.md`, `agora-test-worker.md`) wurden auf dasselbe Härtungsniveau wie ihre `-m3`-Pendants gehoben:
  - Ergänzung einer H1-Überschrift nach Frontmatter in allen sechs Dateien, falls fehlend.
  - Integration eines Branch-Checks im Standard-Loop der schreibenden Worker (`agora-doc-worker.md`, `agora-frontend-worker.md`, `agora-refactor-worker.md`, `agora-test-worker.md`).
  - Dokumentations-Synchronisationsschritt (`docs/STATUS.md`, `ROADMAP.md`, `CHANGELOG.md`, Folge-Issue) im Loop und im Output-Bericht für alle schreibenden Worker.
  - disallowedTools-Härtung (`Edit, Write, Agent`) in `agora-evidence-auditor.md` und `agora-opus-reviewer.md`.
  - Erweiterung der Audit-Tabelle des Evidence-Auditors auf acht Checks.
  - Korrektur der deutschen Anführungszeichen im Doc-Worker.
  - Subshell-Fix im Frontend-Worker und `git diff -- schemas/`-Fix im Refactor-Worker gespiegelt.

### Added (README — „Prozess im UI" mit neun realen Screenshots, 2026-07-27)

- Neue Sektion `## 📸 Prozess im UI` zwischen Pipeline und Architektur mit neun nummerierten Screenshots eines realen Laufs (`proj_c12f138aa04e`, SchulKI). Pro Phase (Run starten, Upload, Personas, Report, Interaktion) kurze Erläuterung plus Bild mit Alt‑Text. Die Assets liegen unter `docs/assets/screenshots/process/01-…09-…jpeg`.

### Changed (README, AGENTS, CLAUDE und install.sh an ehrlichen Ist-Stand angepasst — 2026-07-27, PR #924)

- **README:** Vollständige Umstrukturierung mit Fokus auf den ehrlichen Ist-Stand: Mermaid-Diagramme für Pipeline und Architektur, neuer Schnellstart mit klarer Trennung von Host- und Docker-Variante, ausführliche Tabellen zu Status, Stack, Sicherheit und Release-Weg. Die zehnte Pipeline-Phase „Re-Embedding & Migration" ist im Diagramm ergänzt; die „Grenzen"-Sektion zu Persona-Aussagen, Confidence-Bewertung und statistischer Aussagekraft ist wiederhergestellt.
- **install.sh:** Im Docker-Modus werden `SECRET_KEY`, `AGORA_AUTH_TOKEN` und `NEO4J_PASSWORD` jetzt vor `docker compose up` automatisch via `secrets.token_urlsafe(32)` erzeugt, falls die `.env.docker.example` leer gelassen wurde — verhindert Neo4j-/Backend-Aborts bei Erstinstallation.
- **AGENTS.md / CLAUDE.md:** Token-Efficiency-Regeln präzisiert und an das Section-Format von CLAUDE.md angeglichen.

### Fixed (/home auf kanonisches Dashboard umleiten — 2026-07-27, Issue #915)

- `/home` leitet per ADR-0010 auf `/dashboard` um (benannter Redirect, kein
  Alias). Die klassische Editorial-View `Home.vue` bleibt bis zum
  Entfernungsrelease `1.0.0` physisch erhalten. Der Redirect-Test ersetzt die
  bisherige Routen-Resolution für `/home`; die Golden-Gate-Ausnahme für `/home`
  entfällt, da die Route nicht mehr produktiv geroutet wird.
- Der Dashboard-Start (`HeroNewRun.vue`) portiert die drei Fähigkeiten, die
  Home.vue bisher exklusiv besaß, und stellt damit die vom ADR-0010 geforderte
  Parität des Upload-Start-Flows her: ein Service-Readiness-Gate blockt den
  Start, wenn Neo4j (oder Ollama bei Ollama-Default-Provider) nicht erreichbar
  ist; die Backend-Default-Sprache aus `/api/simulation/available-models`
  überschreibt die hardcodierte `de`-Vorgabe bei frischem Storage; neue Files
  werden an bestehende angehängt statt zu ersetzen.

### Fixed (Kritische Accessibility-Mängel in Filter-, Graph- und Feed-Oberflächen — 2026-07-27, Issue #838)

- **Filter- und Auswahlfelder ohne Namen:** Die vier Filter-Selects der Lauf-Historie
  (`HistoryDatabase`), das generische `ui/Select` und die Edge-Labels-Checkbox der
  Graph-Ansicht (`GraphCanvas`) besaßen keinen für Screenreader lesbaren Namen — in
  `ui/Select` war das sichtbare Label nicht mit dem Feld verknüpft, in `GraphCanvas`
  umschloss das Label nur die Checkbox, nicht ihren Text. Alle Felder tragen jetzt einen
  Namen, der den sichtbaren Text spiegelt. Die Filterleiste der Lauf-Historie ist
  zusätzlich über `vue-i18n` lokalisiert; interne Enum-Werte bleiben unübersetzt.
- **Leere Feed-Spalten mit ungültiger ARIA-Struktur:** Die Spalten der Simulations-Feed-
  Ansicht (`FeedColumn`) meldeten sich unabhängig vom Inhalt als `feed`. Diese Rolle
  verlangt Beitrags-Kinder; eine leere Spalte hat keine — der Zustand, den jede frische
  Simulation zeigt. Leere Spalten werden jetzt als benannte `region` ausgezeichnet und
  wechseln erst mit dem ersten Beitrag auf `feed`.

### Added (Router-, Deep-Link- und Accessibility-Regressionstests — 2026-07-27, Issue #838)

- Die konsolidierte Routenliste (ADR-0010) ist gegen Regressionen abgesichert: jede
  produktive Route löst nachweislich auf genau eine Komponente auf, jede dokumentierte
  Redirect-Entscheidung inklusive Parameter-Umbenennung besitzt einen Testfall, und ein
  Drift-Test schlägt an, sobald Routen hinzukommen oder wegfallen. Bestehende Deep-Links
  landen deterministisch am dokumentierten Ziel.
- Die Accessibility-Gates decken statt zehn nun siebzehn produktive Routen ab, darunter
  erstmals die v4-Step-Routen mit echter Projekt- und Simulations-ID. Vier Routen bleiben
  begründet ausgenommen und sind in den Issues #920 und #921 sowie im Testkopf
  dokumentiert.

### Fixed (E2E-Helper `checkFocusVisible` erkennt implizite Tab-Stops — 2026-07-28, PR #947, Issue #921)

- `frontend/tests/e2e/helpers/accessibility.ts::checkFocusVisible` wertet `document.activeElement` jetzt direkt aus und presst bis zu zwanzig Tab-Tokens, bis ein echtes Element (nicht `document.body`) fokussiert ist. Damit greift der Helper auch auf Routen mit impliziten Tab-Stops (scrollbare Container ohne `tabindex`, z. B. `.fc-scroll` in `FeedColumn.vue`), die per CSS-Selektor nicht vorab erfassbar sind.
- Der Golden-Gate-Test für `/v4/simulation/:simulationId/feed` (Issue #921) ist reaktiviert; die Accessibility-Coverage steigt damit von 17 auf 18 produktive Routen, drei weitere Ausnahmen verbleiben in Issue #920 und im Testkopf.
- **Verlässlichkeit der Gates:** Die Prüfung lief bisher an, bevor Stylesheets und
  Schriften angewendet waren, und meldete dadurch auf schnellen CI-Läufen massenhaft
  Kontrastfehler auf unveränderten Seiten. Die Gates warten jetzt auf einen stabilen
  Renderzustand; die Tastaturprüfung bewertet außerdem nicht mehr fälschlich als Mangel,
  dass der Fokus nach dem letzten Element die Seite verlässt.

### Fixed (Ontology-Upload bereinigt bei File-I/O-Fehlern atomar — 2026-07-26, Issue #899)

- Schlägt beim Ontology-Upload (`/ontology/generate`) ein Datei-I/O-Schritt zwischen
  Projektanlage und Übergabe an den Graph-Build-Service fehl (Datei speichern, Text
  extrahieren, extrahierten Text ablegen, Projekt persistieren), räumt der Endpunkt das
  halb angelegte Projekt jetzt zuverlässig auf, statt ein verwaistes Projekt mit
  Teilartefakten zurückzulassen. Die Antwort bleibt eine generische Fehlermeldung ohne
  Dateipfade oder Provider-Details; scheitert das Aufräumen selbst, wird das protokolliert,
  ohne die ursprüngliche Fehlerantwort zu überdecken oder fälschlich Erfolg zu melden.

### Changed (`/prepare` akzeptiert kanonische `AiModelRef` — Issue #896)

- `/prepare` akzeptiert jetzt eine kanonische, an eine `ProviderConnection` gebundene
  `AiModelRef` als autoritative Route. Mischfälle mit Legacy-Overrides werden abgelehnt;
  eine explizit gesendete Ref löst ein Re-Prepare aus.

### Changed (Graph-Pipeline und Startpfade ohne `agora.lastModel`-Bridge — 2026-07-26, Issue #897)

- **Graph-Ontologie und Graph-Build:** `generate_ontology` und `build_graph` akzeptieren
  `ai_model_ref` als kanonische, connection-gebundene Route. Die API validiert die Pydantic-
  Struktur und die referenzierte `ProviderConnection`, bevor Projekt-, Task- oder Run-
  Seiteneffekte entstehen. Mischfälle mit `llm_model`, `llm_profile_id`, `llm_provider` oder
  `llm_runtime` werden mit HTTP 400 abgelehnt; bei einer gültigen Ref bleiben alle Legacy-
  Overrides aus der Route. Sämtliche synchronen Fehler einer `ai_model_ref`-Route nach der
  Run-Erzeugung bis zum abgeschlossenen Ontologieaufbau beziehungsweise erfolgreichen Enqueue
  terminalisieren Projekt und Run sowie einen bereits angelegten Graph-Task. Routing- und
  Eingabefehler bleiben HTTP 400, Betriebsfehler liefern HTTP 500 und Timeouts HTTP 504;
  Response, persistierte Fehlertexte und Logs bleiben dabei frei von Provider-Details und
  Secrets.
- **Home, Hero, Graph-Pipeline und Step 3:** Ein expliziter Pick wird als vollständige
  `AiModelRef` im tab-skopierten Run-Override gehalten. Die Graph-Pipeline verwendet zuerst
  diesen Override, danach den Kanon aus `routing/defaults.global_default`, und reicht dieselbe
  Ref an Ontologie und Build weiter. Ohne beide Quellen entscheidet das Backend-Routing;
  liegengebliebene `agora.lastModel`-/`agora.lastCustomModel`-Werte werden nicht gelesen,
  geschrieben oder gelöscht. `Step3Simulation` nutzt für Simulation und Report ebenfalls
  keine Legacy-Storage-Route mehr.
- **Persistierte Ref und Resume-Build (Review-Nachtrag PR #900):** Der Ontology-Run legt die
  kanonische `AiModelRef` am Projekt ab (`Project.ai_model_ref`, ohne Secrets). Ein
  Graph-Build ohne eigene Route im Request übernimmt sie, statt — wie zuvor — ganz ohne
  Modell- und Connection-Bindung zu starten, wenn Tab oder Session verloren gehen. Eine
  explizite Legacy-Angabe im Request gewinnt weiterhin; eine defekte persistierte Ref fällt
  protokolliert auf das Legacy-Routing zurück.
- **Fehlerklassifikation über Typ statt Fehlertext (Review-Nachtrag PR #900):** Nur der
  exportierte `AiModelRefRoutingInputError` wird auf die 400-Routing-Antwort abgebildet;
  semantische `ValueError` wie `ONTOLOGY_MISSING` oder `NOT_FOUND` behalten ihren Code. In
  `generate_ontology` deckt die Routing-Terminalisierung nur noch die Routing-Phase ab —
  Fehler der Generierungs- und Persistenzphase tragen eine eigene, nicht-routingbezogene
  Meldung. Die Terminalisierung persistiert den Projektstatus vor dem Registry-Update, damit
  ein fehlschlagendes Registry-I/O den `FAILED`-Zustand nicht nur im Speicher lässt.
- **Adapter-Grenze:** `toStoredModelString` und `toStoredModelStringPure` sind entfernt.
  `useEnvForm` mit `Step2EnvSetup` bleibt bis zur Migration in
  [Issue #890](https://github.com/arn0ld87/agora/issues/890) bewusst der letzte produktive
  Consumer der Legacy-Modell-Keys; Issue #897 entfernt diese Keys daher noch nicht global.

### Changed (Step 2 wählt Modelle über die kanonische `AiModelRef` — 2026-07-26, Issue #890)

- **Modellauswahl in Step 2:** Der Environment-Setup nutzt jetzt den kanonischen
  `AiModelPicker`. Eine Auswahl ist eine vollständige, an eine `ProviderConnection`
  gebundene `AiModelRef` statt eines Modellstrings; Connection und Modell-ID gehen damit
  nicht mehr verloren. Ohne ausdrückliche Auswahl sendet Step 2 kein Modellfeld, sodass
  die Präzedenz des Backends greift: Projektprofil vor Workspace-Default.
- **Eindeutiger `/prepare`-Payload:** Bei ausdrücklicher Auswahl enthält der Request genau
  ein `ai_model_ref` und keines der Felder `llm_model`, `llm_profile_id` oder
  `llm_provider`. Damit kann die Mischfall-Ablehnung aus Issue #896 nicht mehr ausgelöst
  werden. Eine ausdrückliche Auswahl übersteuert das Projektprofil bewusst.
- **Runtime-Provider bleibt erhalten, schließt sich aber aus:** Der Override für Google-,
  OpenAI- und kompatible Runtime-Zugangsdaten ist credential- statt connection-basiert und
  ist deshalb mit einer kanonischen Ref unvereinbar. Solange er aktiv ist, ist der
  `AiModelPicker` deaktiviert und der bisherige Legacy-Pfad gilt weiter; umgekehrt
  deaktiviert eine kanonische Auswahl den Runtime-Block.
- **Storage-Cut:** `useEnvForm` persistiert keine Modellauswahl mehr. `STORAGE_MODEL`,
  `STORAGE_CUSTOM_MODEL` und `storedEffectiveModel()` sind entfernt; `STORAGE_LANG` für die
  Agentensprache bleibt unverändert. Bereits vorhandene `agora.lastModel`- und
  `agora.lastCustomModel`-Werte in Browsern werden weder gelesen noch aktiv gelöscht — sie
  bleiben wirkungslose Altlast. Nach einem Reload startet die Modellauswahl bewusst leer,
  statt eine nicht mehr verbindliche Altauswahl vorzutäuschen.

### Fixed (133 reihenfolgenabhängige Test-Failures in `tests/api` — 2026-07-26)

- **`backend/tests/conftest.py`** — neues autouse-Fixture `_clean_auth_token_env`.
  `tests/api` lief lokal mit **138 Failures**, isoliert waren dieselben Suiten grün.
- **Ursachenkette:** `app/config.py` ruft beim Import `load_dotenv()` auf und zieht den
  echten `AGORA_AUTH_TOKEN` aus `.env` bzw. `backend/.env` prozessweit in `os.environ`.
  Für sich harmlos — kritisch wird es mit den Blueprint-Singletons:
  `install_blueprint_guard` hängt seinen `before_request`-Hook an das Blueprint-*Objekt*
  und markiert es über `_agora_guard_installed` dauerhaft. Ruft irgendein Test `create_app()`
  (`tests/api/test_cors.py`, `tests/test_fork_safety.py`,
  `tests/observability/test_logging_wiring.py`), ist der Guard danach permanent auf
  `simulation_bp`, `graph_bp`, `report_bp` & Co. — auch für jede spätere nackte
  `Flask()`-Testapp. Mit gesetztem Token antwortet er `401 auth_required`. Suiten, deren
  Client-Fixture `AGORA_AUTH_TOKEN` selbst löschte, waren immun; alle anderen kippten,
  sobald vorher ein `create_app()`-Test lief.
- **In CI fiel das nie auf**, weil dort keine `.env` existiert. Betroffen war ausschließlich
  die lokale Entwicklungsschleife — und das PR-Gate deckt es nicht ab, weil es nur
  `tests/contracts/` fährt.
- **Leerer String statt `delenv`.** Der naheliegende `monkeypatch.delenv` funktioniert
  *nicht*: entfernt man den Key, setzt ihn der nächste `load_dotenv(override=False)` sofort
  wieder, denn `override=False` überspringt nur Keys, die bereits in `os.environ` stehen.
  Genau das passierte in Suiten, die `app.config` erst *während* eines Tests importieren
  (`_global_fernet_env` → `api_keys_store` → `app.config`). `monkeypatch.setenv(..., "")`
  belegt den Key, ohne den Guard scharf zu machen — `_expected_token()` und der
  Open-Mode-Check in `scopes.require_scope` prüfen beide auf Truthiness.
- **`backend/tests/contracts/test_suite_hermeticity.py`** — neue Suite (7 Tests) im
  PR-Gate: Verhaltensprüfung, dass die leck-anfälligen Variablen im Test leer sind, eine
  Strukturbremse über `request.fixturenames`, und ein Wirkungsnachweis, der ein pytest im
  Subprozess mit **vorbelegtem** `AGORA_AUTH_TOKEN` startet. Letzterer ist der einzige der
  drei, der einen zum No-op ausgehöhlten Fixture-Body auch **ohne** lokale `.env` fängt —
  die Verhaltensprüfung startet auf CI mit ohnehin abwesendem Token, die Strukturprüfung
  sieht nur die Registrierung (Codex-Finding P2 auf PR #895). Die Assertions vergleichen
  bewusst über Truthiness/Länge statt über den Wert, damit kein Token in den pytest-Report
  gerät.
- Ergebnis: `tests/api` von 138 auf 5 Failures, **keine neue Regression**. Die 5 Reste sind
  ein unabhängiges Problem (`OSError: Read-only file system: '/app'` in den
  `graph_ontology`-Tests, auch isoliert rot). Auth-Suiten (`test_auth`, `test_auth_ticket`,
  `test_logs_api`, `test_settings_api`, `test_report_export`, `test_config_validate`):
  79 passed. Verifiziert durch Mutationen in vier Konstellationen: Fixture-Body
  neutralisiert (mit `.env` 2 Tests rot, **ohne** `.env` 1 Test rot) und `autouse` entfernt
  (2 Tests rot); mit intaktem Fixture und entfernter `.env` bleiben alle 7 grün.

### Fixed (`llm_profile_id` in `/prepare` wirkt jetzt aufs Routing — 2026-07-26, Issue #888)

- **`backend/app/api/simulation_prepare.py`** — `llm_profile_id` war ein reiner
  Fallback-*Unterdrücker* und kehrte damit seine eigene Absicht um: ein mitgeschicktes
  Profil übersprang den P5.3-Projekt-Fallback, löste aber selbst nichts auf, weil
  `expand_profile_in_data` ausschließlich auf ein `llm_model` mit `profile:`-Präfix reagiert.
  **Konkreter Defekt:** Projekt hat ein Profil, User lässt die Modellauswahl auf „default"
  (`useEnvForm.effectiveModel()` liefert dann `null`, also kein `llm_model` im Payload),
  `Step2EnvSetup.vue` sendet `llm_profile_id` mit → die Vorbereitung lief still auf dem
  Server-Default-Modell. Hätte das Frontend das Feld *weggelassen*, hätte der Fallback
  korrekt gegriffen.
- **Neues Verhalten:** `llm_profile_id` ist eine Routing-Anweisung wie in `graph_build.py`
  und `report.py`. Präzedenz: explizites `llm_model` → Request-Profil → Projekt-Profil →
  Server-Default. `llm_model="default"` zählt als UI-Platzhalter, nicht als Modellwahl.
- **Über den kanonischen Pfad, nicht über lokale Expansion.** Die Profil-ID wird als
  `llm_profile_id` an `seed_run_stage_routing` durchgereicht statt hier zu `llm_model`
  expandiert. Nur dessen Profil-Branch löst die aktivierte `ProviderConnection` auf und
  koppelt sie an deren gebundenes Secret (SSoT, Issue #817) — eine lokale Expansion trifft den
  Legacy-Override-Branch davor und brennt Endpoint und Key aus dem Legacy-Profil ein, die nach
  einer Connection- oder Secret-Rotation veraltet sind. Zudem wird ein unauflösbares Profil
  jetzt mit HTTP 400 abgelehnt, statt mit dem literalen Modellnamen `profile:<id>` in die
  Queue zu laufen (Codex-Finding P1 auf PR #894). Der Legacy-Pfad `llm_model="profile:<id>"`
  aus `HeroNewRun.vue` wird weiterhin lokal expandiert — `seed_run_stage_routing` kennt nur
  das separate Feld.
- **Re-Prepare-Semantik entkoppelt.** Der „bereits vorbereitet"-Kurzschluss hing an
  `llm_model_override` bzw. `llm_runtime.enabled`. Beide sind durch das Profil-Routing für
  jedes Projekt mit hinterlegtem Profil gesetzt — `expand_profile_in_data` schreibt zusätzlich
  einen `llm_provider`-Block aus dem Profil. Unverändert hätte der Kurzschluss nie mehr
  gegriffen und jedes Betreten von Step 2 eine volle Neu-Vorbereitung samt
  Persona-Neugenerierung ausgelöst. Er hängt jetzt an `client_requested_override`: nur ein
  vom Client *explizit* gesendetes `llm_model` oder `llm_provider` überspringt ihn. Dafür wird
  `explicit_runtime_request` vor der Expansion festgehalten, sonst wäre der profil-abgeleitete
  Provider-Block von einem echten Override ununterscheidbar. Ein Request-Profil, das vom
  Projekt-Default **abweicht**, zählt dabei sehr wohl als explizite Wahl — sonst käme der
  Endpoint mit `already_prepared` zurück und die Personas blieben die des vorherigen Modells,
  im Widerspruch zur Präzedenz „Request-Profil schlägt Projekt-Profil" (Codex-Finding P1 auf
  PR #894). Dasselbe Profil erneut zu schicken bleibt der billige Revisit — das ist der
  Frontend-Alltag, weil `Step2EnvSetup.vue` immer den Projekt-Default mitsendet.
- **`backend/tests/api/test_simulation_prepare_profile_routing.py`** — neue Suite, 15 Tests:
  Präzedenzkette (Request-Profil schlägt Projekt-Profil, explizites Modell schlägt beide,
  `"default"` ist keine Wahl), Legacy-Token-Expansion, unauflösbares Profil → HTTP 400, und
  acht Tests für die Kurzschluss-Semantik inklusive der Abgrenzungen profil-abgeleiteter vs.
  echter Provider-Override und identisches vs. abweichendes Request-Profil.
- **`backend/tests/api/test_simulation_prepare_routing.py`** — die beiden Fixtures mocken
  jetzt `_check_simulation_prepared`. Der Kurzschluss läuft dort seit der Entkopplung
  tatsächlich an und bräuchte sonst einen initialisierten `SimulationArtifactStore`; die Suite
  prüft Key-Routing, nicht den Prepared-State.
- Verifikation: 8 der 15 Tests sind gegen den alten `simulation_prepare.py` rot (genau die
  Verhaltensänderungen), 7 sichern unverändertes Verhalten ab. `bash scripts/pre-push-gate.sh
  backend` grün; `tests/api` hat mit und ohne diese Änderung dieselben 138 vorbestehenden
  Failures — ein unabhängiges Bestandsproblem: `AGORA_AUTH_TOKEN` kommt via `load_dotenv()`
  aus der lokalen `.env` und der Blueprint-Guard bleibt nach einem `create_app()`-Test
  dauerhaft an `simulation_bp` hängen. Die neue Suite ist im Gesamtlauf sauber, weil ihr
  Client-Fixture den Open-Mode erzwingt.

### Added (Branch-Override-Whitelist gegen Regression festgeschrieben — 2026-07-26, Issue #887)

- **`backend/tests/contracts/test_branch_override_contract.py`** — neue Contract-Suite
  (28 Tests) für `services/branching_service.py::allowed_override_keys`. Die Whitelist ist
  die einzige Stelle, die entscheidet, welche Branch-Overrides das Backend akzeptiert, und
  war bis hierher komplett ungetestet — die vorhandenen Branch-Tests
  (`tests/api/test_simulation_endpoints.py`, `tests/test_simulation_api_routes.py`) decken
  nur den fehlenden `branch_name` ab. Genau diese Lücke hat den in #886 beschriebenen
  Defekt unbemerkt bestehen lassen.
- **Wirkung statt Nicht-Ablehnung:** je ein Test pro erlaubtem Key (`llm_model`, `language`,
  `max_agents`, `time_config`, `enable_twitter`, `enable_reddit`, `persona_additions`,
  `persona_removals`), der belegt, dass der Override im Branch-Artefakt landet — in der
  `simulation_config`, im `SimulationState` oder in den Reddit-Profilen. Zusätzlich gepinnt:
  `time_config` wird gemerged statt ersetzt, `None`/`""` sind Nicht-Overrides, und die
  Quell-Simulation bleibt unverändert. Die Quell-Simulation setzt `enable_twitter=False`
  und `enable_reddit=True` explizit, damit jeder Plattform-Override den Ausgangswert
  umdrehen muss — `create_simulation` hat für beide `True` als Default, ein Override auf
  `True` wäre also auch bei reinem Erben grün (Codex-Finding P2 auf PR #893). Ein
  Gegentest hält fest, dass ohne Override tatsächlich geerbt wird.
- **Ablehnungspfad:** unbekannter Key → `ValueError("Unsupported branch overrides: …")`, die
  Fehlermeldung listet alle unbekannten Keys sortiert, der Guard greift vor jedem
  Seiteneffekt (kein Branch entsteht), und über `utils/api_responses.handle_api_errors`
  wird daraus HTTP 400 am Endpoint `POST /api/simulation/<id>/branch`.
- **Whitelist als Ganzes:** `test_whitelist_matches_pinned_expectation` liest das Set-Literal
  per AST aus `branching_service.py` und vergleicht es gegen die im Test gepinnte Menge.
  Nötig, weil die Whitelist eine lokale Variable in `create_branch` und damit nicht
  importierbar ist — und weil ein *stilles Hinzufügen* eines Keys verhaltensbasiert nicht
  erkennbar wäre (der Key-Raum ist unendlich). Damit wird sowohl Hinzufügen als auch
  Entfernen rot.
- Verortung in `tests/contracts/`, weil dieses Verzeichnis im verpflichtenden PR-Smoke-Gate
  und im Pre-Push-Gate läuft (`uv run pytest tests/contracts/ -x -q`). Die Whitelist ist ein
  API-Vertrag gegenüber dem Frontend (`components/step4/ReportBranchControls.vue`); ein Drift
  soll im Gate auffallen, nicht erst im Full-Run.
- **Kein Produktivcode-Fix:** die Suite schreibt ausschließlich den Ist-Zustand fest. Ob
  `ai_model_ref` in die Whitelist gehört, entscheidet #886 — der Key steht hier bewusst in
  der Negativliste des Ablehnungspfads.
- Verifikation: `uv run pytest tests/contracts/test_branch_override_contract.py -q` → 27 grün.
  Zusätzlich drei Mutationstests gegen den Produktivcode, alle gefangen: `language` aus der
  Wirkungs-Schleife entfernt → `test_language` rot; `ai_model_ref` still zur Whitelist
  hinzugefügt → 3 Tests rot; `time_config` still entfernt → 3 Tests rot; Plattform-Overrides
  auf reines Erben umgestellt → 2 Tests rot; `enable_twitter` hartkodiert → 1 Test rot.

### Changed (CI-Gate: `LlmProfilePicker.vue` gegen Rückkehr gesperrt — 2026-07-26, Issue #889)

- **`.github/scripts/check_legacy_model_picker.py`** — `components/llm/LlmProfilePicker.vue`
  ist jetzt in `REMOVED_PATHS` eingetragen. Die Datei wurde in Issue #834 physisch gelöscht,
  der Guard blockte bis dahin aber nur *Importe* des v3-Pickers über `FORBIDDEN_SUBSTRINGS` —
  eine wieder eingecheckte Datei wäre also unbemerkt durchgelaufen. **Neues CI-Verhalten:**
  Der Check schlägt jetzt allein bei Datei-Existenz fehl (Exit 1, kein Import nötig); ein
  `@deprecated`-JSDoc-Tag hebt die Sperre nicht auf, weil `REMOVED_PATHS` vor der
  Read-Adapter-Freigabe greift. Für `components/ui/ModelPicker.vue` galt das seit Slice 7.7
  bereits.
- Modul-Docstring korrigiert: Er beschrieb die `@deprecated`-Read-Adapter-Freigabe noch über
  „Step-Views", die es nicht mehr gibt (Steps liegen unter `frontend/src/views/v4/steps/`).
  Jetzt benannt sind die tatsächlichen v3-Consumer — `WorkspaceHeader` → `ActiveModelBadge`,
  `Step2EnvSetup`/`Step3Simulation` → `useRuntimeLlmOptions`. Die Clean-Meldung sprach von
  „removed Slice 7.7 paths" und ist durch den #834-Eintrag quellenneutral formuliert.
- **`.github/scripts/test_check_legacy_model_picker.py`** — neuer Test
  `test_removed_llm_profile_picker_path_is_caught` (10 statt 9 Tests). Die Fixtures der
  `@deprecated`-Tests laufen jetzt über `ActiveModelBadge.vue` statt `LlmProfilePicker.vue`,
  da letzterer Pfad durch `REMOVED_PATHS` schon bei Existenz blockt und die Read-Adapter-
  Semantik sonst nicht mehr isoliert prüfbar wäre.
- **`docs/runbooks/pre-push-gate.md`** — Abschnitt „Legacy-Picker-Check" um den Absatz
  „Entfernte Dateien (`REMOVED_PATHS`)" ergänzt, Consumer-Aussage auf den Ist-Stand gebracht,
  Testzahl `8` → `10` korrigiert.
- Verifikation: `python3 .github/scripts/test_check_legacy_model_picker.py` → 10 Tests grün;
  `python3 .github/scripts/check_legacy_model_picker.py --no-github frontend/src` → Exit 0.

### Changed (Legacy-Modell-Picker konsolidiert: `LlmProfilePicker` → `AiModelPicker` — 2026-07-25, Issue #834)

- **`frontend/src/components/Step4Report.vue`** — der v3-Profil-Picker-Block (`LlmProfilePicker`
  + `agora.report.llmProfileId`-Persistenz) ist entfernt. Der kanonische `AiModelPicker`
  (über `ReportModelControls`) war hier bereits aktiv; beide Sinken gleichzeitig hätten den
  Report-Request mit HTTP 400 abgelehnt (`ai_model_ref` und `llm_profile_id` schließen sich
  gegenseitig aus). `buildModelSelection()` sendet jetzt ausschließlich `ai_model_ref`.
- **`frontend/src/components/step4/ReportBranchControls.vue`** — auf `AiModelPicker`
  (`mode="chat"`) migriert. Der frühere `llm_profile_id`-Branch-Override war bereits
  funktionslos, weil `backend/app/services/branching_service.py` dieses Feld nie akzeptiert hat.
  Payload-seitig gibt es genau eine Senke (`llm_model`-String), UI-seitig aber zwei
  Schreibpfade auf dasselbe Feld (Picker-Auswahl und das weiterhin vorhandene Freitext-Input) —
  die zuletzt ausgeführte Bearbeitung gewinnt, jetzt in beide Richtungen testabgesichert.
  `provider_connection_id` geht dabei verloren (nur `model_id` wird gesendet), weil der
  Branch-Override backend-seitig keine Connection-Referenz kennt — diese Lücke trägt Issue #886.
- **`frontend/src/components/step2/EnvSetupModelPanel.vue`** — Legacy-Picker samt
  `is-overridden-by-profile`-Zustand entfernt. Kein Ersatz durch `AiModelPicker` an dieser
  Stelle: der Profil-Pfad ist backend-seitig weiterhin live
  (`backend/app/api/simulation_prepare.py` expandiert `llm_profile_id` zu
  `llm_model="profile:<id>"`); eine vollständige Kanon-Migration ist ein eigener Slice
  (`docs/epics/frontend-next/SLICE-5.2-ENVSETUP-KANON-MIGRATION.md`, Issue #890).
  `Step2EnvSetup.vue`s `triggerPrepare()`-Payload bleibt unverändert erhalten.
  **Entfallene Nutzerfähigkeit:** Ein im Projekt persistiertes LLM-Profil lässt sich in
  Step 2 nicht mehr aktiv auf „Server-Standard" (null) zurücksetzen — `llmProfileId` kommt
  jetzt rein lesend aus `props.projectData`. Laut `simulation_prepare.py` unterdrückte
  dieser Reset lediglich den Fallback auf das Projektprofil, mit Nebenwirkung auf die
  Re-Prepare-Semantik (Issue #888).
- **`frontend/src/components/llm/LlmProfilePicker.vue`** + Spec gelöscht — keine produktiven
  Consumer mehr. Tote i18n-Keys `llmProfilePicker.*`, `step2.llmProfile.*`, `step4.llmProfile.*`
  aus `de.json`/`en.json` entfernt.
- Verifikation: neue/angepasste Vitest-Specs für alle drei Consumer (u. a.
  `frontend/src/components/step4/__tests__/ReportBranchControls.spec.ts`, neu), Regressionscheck
  `rg "LlmProfilePicker" frontend/src frontend/tests` liefert keinen Treffer mehr.

### Fixed (Frontend/API: Wortgrenzen im ERROR_PATTERN + redundantes `all_actions_count` entfernt — 2026-07-24, PR #862)

- **`frontend/src/utils/errorLinePattern.ts` (neu)** — das Regex
  `(error|exception|traceback|fatal|warn|warning)` matchte ohne Wortgrenzen auch Wort-INNERE
  Vorkommen: `forwarded`, `errorless`, `warningless`, `forewarning` und `awareness` wurden als
  Fehlerzeilen gezählt. Das verfälschte Error-Zähler und Log-Filter in `LogDrawer`,
  `Step3Simulation` und `SimulationToolPanel`.
- Fix zieht das Pattern in eine gemeinsame Utility mit `\b`-Ankern
  (`/\b(?:error|exception|traceback|fatal|warn|warning)\b/i`) plus Helper `isErrorLine()`. Alle
  drei Konsumenten nutzen jetzt denselben Token-Satz — vorher divergierten sie, `LogDrawer`
  kannte `warn|warning` gar nicht.
- **`backend/app/api/simulation_run.py`** — `result["all_actions_count"]` war eine exakte
  Duplikation von `actions_total` ohne einen einzigen Frontend-Konsumenten und wurde entfernt.
  `actions_total` bleibt das kanonische Feld.
- Verifikation: 12 Vitest-Fälle in `frontend/src/utils/__tests__/errorLinePattern.spec.ts`
  (inkl. expliziter Negativfälle für die genannten Wort-Inneren Treffer), 7 pytest in
  `backend/tests/api/test_pagination_clamp.py`.

### Fixed (Subprozess-Env-Whitelist: REDIS_URL und HF_TOKEN für OASIS-Bridge und private HF-Mirrors — 2026-07-24, PR #861)

- **`backend/app/services/sim/process_manager.py`** — die Subprozess-Whitelist `SAFE_ENV_KEYS`
  ließ bisher nur technische LLM-Connection-Keys passieren; zwei produktive Use-Cases hingen
  dadurch in der Luft:
  1. `REDIS_URL`: `scripts/subprocess_redis_bridge.py` aktiviert sich nur, wenn die Variable
     gesetzt ist. Ohne Whitelist-Eintrag blieb die Real-Time-IPC zwischen FastAPI-Parent und
     OASIS-Subprozess stumm, obwohl `REDIS_URL` im Backend-Env lag.
  2. `HF_TOKEN`: Hugging-Face-Authentifizierung für private und Gated-Modelle. Public Models wie
     `Twitter/twhin-bert-base` laufen ohne Token, Custom-Mirrors hinter Auth aber nicht.
- `SECRET_KEY`, `AGORA_AUTH_TOKEN`, `NEO4J_PASSWORD`, `LLM_API_KEY` und `AGORA_FERNET_KEY` bleiben
  explizit **draußen**; `TestSubprocessEnvExcludesSecrets` sichert das regressionsfest.
- Verifikation: 9 Tests in `backend/tests/services/test_process_manager_env_whitelist.py` grün.

### Fixed (Gemini-Embedding-URL: doppeltes `/v1`-Segment im OpenAI-Compat-Pfad — 2026-07-24, PR #860)

- **`backend/app/storage/embedding_service.py`** — der Gemini-OpenAI-Compat-Endpoint endet bereits
  auf `/v1beta/openai` (oder `/v1beta/openai/`); ein weiteres `/v1`-Segment in
  `EmbeddingService._build_embed_url` ergab `…/v1beta/openai/v1/embeddings` und antwortete 404.
  Embedding-Discovery schlug für Gemini still fehl, obwohl Provider-Connection, API-Key und
  Modellkatalog korrekt konfiguriert waren.
- Fix erweitert die Whitelist in `_build_embed_url` um die Suffixe `/v1beta/openai` und
  `/v1beta/openai/` (mit und ohne trailing slash).
- Verifikation: 22 Tests in `backend/tests/test_embedding_service.py` grün. Zusätzlich live gegen
  Gemini verifiziert: gebaute URL
  `https://generativelanguage.googleapis.com/v1beta/openai/embeddings`, `health_check() == True`,
  `gemini-embedding-2` liefert einen 3072-dimensionalen Nicht-Null-Vektor.

### Added (TWHIN-BERT-Ladeprofil und RSS-Sampler für OASIS-Subprozesse — 2026-07-24, PR #859)

- **`backend/scripts/_sim_common.py`** plus `run_parallel_simulation.py`,
  `run_twitter_simulation.py` und `run_reddit_simulation.py` — der OASIS-Subprozess starb im
  speicherbegrenzten Container mit Exit-Code -9 (Linux-OOM-Killer), sobald
  `Twitter/twhin-bert-base` im ersten `update_rec_table()`-Tick lazy aus
  `oasis.social_platform.recsys` geladen wurde.
- `install_bert_memory_profile()` patcht `transformers.AutoModel.from_pretrained` für dieses
  Modell und injiziert `low_cpu_mem_usage=True` + `torch_dtype=torch.float16`. Steuerbar über
  `AGORA_BERT_MEMORY_PROFILE` (`low` = Default, `off` = Patch deaktiviert).
- `install_memory_sampler()` startet einen Hintergrund-Thread, der RSS-Snapshots als NDJSON nach
  `.runtime/mem_profile.<pid>.ndjson` schreibt (aktiv bei `AGORA_DEBUG_MEMORY=1`). Der Pfad ist
  PID-getrennt, damit die drei Run-Scripts sich nicht denselben Sink teilen. Der RSS-Reader ist
  über den Parameter `rss_reader` injizierbar und dadurch plattformunabhängig testbar.
- Beide Helper laufen in allen drei Run-Scripts **vor** dem ersten `import oasis`, damit das
  Modul-Level-Caching von Python dafür sorgt, dass der spätere `from transformers import AutoModel`
  in `process_recsys_posts` die gepatchte Klassenmethode sieht.
- Verifikation: 11 Tests in `backend/tests/scripts/test_bert_memory_profile.py` grün; sie decken
  Profilwahl, Idempotenz, Respektieren von Caller-Overrides, NDJSON-Ausgabe des Samplers und den
  Fallback bei fehlendem `transformers` ab. Die Tests prüfen die injizierten Ladeparameter, **nicht**
  den tatsächlichen Speicherverbrauch — eine Messung des realen RSS-Effekts steht aus.

### Fixed (Ontology-Generation: Truncation bei MiniMax-M3 ohne JSON-Schema — 2026-07-24, PR #858)

- **`backend/app/services/ontology_generator.py`** — die Ontology-Generation lief mit MiniMax-M3 in
  rund 20 % der Läufe in eine Truncation (`Invalid JSON format from LLM (len=12325)`): der
  Ontology-Call übergab kein `schema` an `chat_json`, und das Legacy-Flag
  `LLM_DISABLE_JSON_MODE=true` deaktivierte `response_format=json_object`, sodass M3 keine
  JSON-Struktur-Anweisung erhielt und Prosa ins JSON mischte.
- Fix definiert das Pydantic-Schema `OntologyDefinition` und übergibt es an
  `chat_json(schema=OntologyDefinition, schema_name="ontology_definition", force_no_thinking=True)`.
  Belt-and-braces: der verwaiste `.env`-Eintrag `LLM_DISABLE_JSON_MODE` wurde entfernt, da das
  Legacy-Flag mit strict schema irrelevant ist.
- Verifikation: Post-Fix 10/10 + 3/3 Läufe HTTP 200, 0 Truncation-Warnungen, im Schnitt 15.7
  entity_types. Regression-Tests in `backend/tests/test_ontology_generator.py` (6 passed:
  4 bestehend, neu `test_generate_passes_ontology_definition_schema` und
  `test_generate_passes_force_no_thinking_true`).

### Fixed (Persona-Generation: Hänger durch reasoning_tokens-Verschwendung — 2026-07-24, PR #858)

- **`backend/app/services/oasis_profile_generator.py`** — die Persona-Erstellung hing nach der
  ersten von 30 Personas und brauchte rund 1:30 min pro Persona statt der erwarteten 15–20 s; die
  Logs zeigten 11 `JSON parsing failed (attempt N): Extra data / Expecting value` innerhalb von
  5 min. Ursache: `_generate_profile_with_llm` nutzte den rohen `OpenAI`-Client
  (`self.client.chat.completions.create`) mit nur
  `response_format={"type":"json_object"}` — kein strict schema, kein `thinking.type: disabled`
  (MiniMax-`extra_body`), kein `force_no_thinking`. M3 emittierte 583 reasoning_tokens (63 % des
  Token-Budgets) als lesbaren Text im `content`, was das JSON kaputt machte ("Extra data" =
  zweites JSON-Objekt, "Expecting value" = Prosa) und den 3-fachen Retry-Loop auslöste.
- Fix stellt `_generate_profile_with_llm` auf `LLMClient.chat_json` um, mit dem neuen
  `PersonaProfileSchema` (Pydantic, alle 11 Felder, `age` ge=18 le=75),
  `schema_name="persona_profile"`, `force_no_thinking=True` und `max_tokens=16384` (vorher 8192
  → Truncation bei 2349-Token-Personas). Das Post-Processing (bio/persona/voice_register-Fallbacks,
  `_validate_profile_metadata`) bleibt erhalten; der rohe `OpenAI`-Client im Konstruktor bleibt
  für Backwards-Compat.
- Verifikation: Post-Fix 2/2 Personas in 43.2 s, `finish=stop`, 1470–1796 Tokens, 0 Truncation,
  0 Parse-Fehler. Regression-Tests in `backend/tests/test_oasis_profile_generator.py` (4 passed,
  neu: schema, force_no_thinking, max_tokens≥16384, age-range-validation); 2 obsolete Tests in
  `test_oasis_profile_format.py` entfernt (raw-Client-Retry-Pfad obsolet).
  Targeted Suite: 742 passed, 0 skipped, 0 fail. Zusätzlich Test-Isolation für
  `test_llm_max_output_tokens_default` repariert (`_min_env`-Autouse-Fixture in
  `backend/tests/test_settings.py` löscht nun `LLM_MAX_OUTPUT_TOKENS` aus der ENV, damit der
  echte Code-Default `8192` getestet wird — zuvor las Pydantic-Settings die Live-ENV auch
  mit `_env_file=None`).

### Fixed (v4-Dashboard: Hero-Modellwahl wird als autoritatives ai_model_ref zum Sim-Start durchgereicht — 2026-07-23)

- Die Modellwahl im Dashboard (`HeroNewRun`, AiModelPicker) wurde bislang nur als `model_id`-String
  nach `STORAGE_MODEL` gespiegelt; beim späteren Simulationsstart gewann der Kanon
  (`routing/defaults.global_default`) — ein abweichender Dashboard-Pick wurde stillschweigend
  ignoriert bzw. verlor ohne Kanon-Default seine Connection-Bindung (Legacy-`llm_model`-Pfad).
- Neu: `frontend/src/store/runModelOverride.ts` — transiente, Zod-validierte sessionStorage-Senke
  (`agora.run.aiModelRefOverride`). `HeroNewRun` schreibt beim Start den vollen `AiModelRef`
  (Profile-Start bzw. kein Pick cleart die Senke); `Step3Simulation.doStart` liest sie vorrangig
  vor dem Kanon und sendet sie als `ai_model_ref` mit `source: "run-override"` (Backend-Literal
  in `AiModelRefSource` vorhanden). Der persistente Kanon bleibt unberührt — die
  Phase-1-Konsolidierung („eine persistente Modell-Senke") bleibt intakt.
- Tests: `store/__tests__/runModelOverride.spec.ts` (Roundtrip, Source-Normalisierung, defensives
  Entsorgen korrupter Einträge), `Step3Simulation.spec.ts` (Override gewinnt vor Kanon; Override
  ohne Kanon → kein Legacy-Fallback), `HeroNewRun.spec.ts` (Set bei Pick, Clear bei Profile und
  ohne Pick).

### Fixed (Vue-v4: Legacy-Prozessrouten konsolidiert — 2026-07-22, Issue #831)

- Die fünf klassischen Prozessrouten bleiben als benannte, kompatible Redirects erhalten und führen nun auf die kanonischen v4-Step-Routen. Die verwaisten Wrapper-Views `MainView`, `SimulationView`, `SimulationRunView`, `ReportView` und `InteractionView` sowie die einzige zugehörige Spec wurden entfernt.
- Der Graph-Build-Start hinter `Process/new` lebt nun im v4-Step: Pending Upload, Ontologie, Graph-Build und Fortsetzen bestehender Projekte bleiben erhalten; nach erfolgreicher Ontologie ersetzt die Route `new` durch die konkrete Projekt-ID ohne zweiten Build.
- Die interaktive D3-Graph-Visualisierung (`GraphPanel`/`GraphCanvas`) bleibt im v4-Step erhalten: Sobald `graphData` geladen ist, rendert `StepGraphBuildView` den Wissensgraph-Canvas wieder — die mit der `MainView`-Entfernung verwaiste Visualisierung ist nicht länger tot. Der Upload+Graph-E2E-Smoke (`.graph-view`) deckt das ab.

### Fixed (v4-Step-Views: next-step/go-back Navigation verdrahtet — 2026-07-22, Issue #850)

- PR #849 hat die fünf klassischen Prozessrouten auf die kanonischen v4-Step-Routen umgeleitet, dabei aber die `@next-step` / `@go-back`-Listener auf den Wrapper-Views nicht mitgezogen: `StepGraphBuildView`, `StepEnvSetupView` und `StepSimulationView` renderten ihre Kinder zwar, Navigationsereignisse landeten aber nirgends (PR #849 enthielt nur die Redirects in `frontend/src/router/index.ts`, nicht die Event-Wiring). Folge: Nach Beenden des Graph-Builds und nach Persona-Konfiguration blieb der Nutzer auf demselben Screen hängen, vor `Step3Simulation` gab es kein Zurück mehr zu Persona-Konfiguration oder Graph-Build.
- Fix verdrahtet pro Wrapper einen expliziten Handler:
  - **`StepGraphBuildView.vue`** — `@next-step="handleNextStep"` auf `<Step1GraphBuild>`, Handler ruft `router.push({ name: 'StepEnvSetup', params: { projectId: props.projectId } })`.
  - **`StepEnvSetupView.vue`** — `@next-step="handleNextStep"` und `@go-back="handleGoBack"` auf `<Step2EnvSetup>`; `handleNextStep` validiert die geleerte `simulationId` defensiv (`typeof !== 'string' || length === 0` → No-Op) und navigiert ansonsten nach `StepSimulation` mit `params.simulationId` und `query: { projectId: props.projectId }` (Rückwärtsauflösung, da die `StepSimulation`-Route nur `simulationId` führt); `handleGoBack` navigiert nach `StepGraphBuild` mit `params.projectId`.
  - **`StepSimulationView.vue`** — `@go-back="handleGoBack"` auf `<Step3Simulation>`; Handler liest `projectId` aus `route.query.projectId` (von `StepEnvSetupView.handleNextStep` gesetzt) und ruft `router.push({ name: 'StepEnvSetup', params: { projectId } })`. Defensive Guard: bei leerer oder fehlender Query wird nicht navigiert (verhindert eine fehlgeschlagene `:projectId`-Route-Erlaubnis statt eines stillen Tothangs).
- Tests: drei neue Spec-Dateien neben `StepWrapperViews.spec.ts` decken die Übergänge einzeln ab — `StepGraphBuildView.spec.ts` (Happy Path), `StepEnvSetupView.spec.ts` (Happy Path + Empty-`simulationId`-Guard) und `StepSimulationView.spec.ts` (Happy Path + Missing-`projectId`-Guard). Insgesamt 27 Wrapper-Tests grün, Frontend-Pre-Push-Gate läuft sauber durch. Design und Plan unter `docs/superpowers/specs/2026-07-22-v4-step-event-wiring-design.md` und `docs/superpowers/plans/2026-07-22-v4-step-event-wiring.md`.

### Fixed (generate-profiles löst keinen Store-Key auf und liefert 500 statt 422 — 2026-07-22, Issue #799)

- **`generate_profiles` (`backend/app/api/simulation_history.py`)** — der Preview-Endpoint
  `POST /api/simulation/generate-profiles` (erzeugt bewusst keinen Simulation-Run) las API-Keys
  bisher ausschließlich aus dem Request-Payload. Anders als `simulation_prepare` wurde der in den
  Settings hinterlegte Store-Key nie konsultiert; fehlte der Key bei einem Fremd-Provider, warf der
  Generator `ValueError("LLM_API_KEY not configured")`, was auf HTTP 500 statt eines sauberen 422
  mit Handlungsanweisung durchschlug.
- Fix führt Store-Key-Auflösung über denselben Resolver (`resolve_route_api_key`) ein, ohne dabei
  einen persistierten Run zu erzeugen: zwei reine Helper (`_apply_workspace_defaults`,
  `_apply_override`) wurden aus `seed_run_stage_routing` extrahiert (`backend/app/services/llm_routing_seed.py`,
  verhaltensidentisch für bestehende Aufrufer) und in einer neuen zustandslosen Funktion
  `build_preview_stage_route` wiederverwendet — sie schreibt nie auf Platte und versiegelt keine
  Stage, um keine neue Klasse von Orphan-Artefakten einzuführen (vgl. Issue #841). Fehlt der Key bei
  einem nicht-lokalen Endpoint, liefert der Endpoint jetzt HTTP 422 mit derselben Handlungsanweisung
  wie `simulation_prepare`; lokale Endpoints ohne Key erhalten weiterhin den No-Auth-Platzhalter (#778).

### Fixed (Persistenzfehler von update_run im Provider-Key-Guard maskiert bisher als reguläre Ablehnung — 2026-07-22, Issue #844)

- **`prepare_simulation` (`backend/app/api/simulation_prepare.py`)** und
  **`_restart_simulation_prepare` (`backend/app/api/runs.py`)** markierten Run/Task beim
  Provider-Key-Guard (Issue #841) zwar als `failed`, ignorierten dabei aber Rückgabewert und
  Exceptions von `run_registry.update_run(...)`. Lieferte `update_run` `None` (Run-Manifest
  zwischenzeitlich verschwunden) oder warf es eine I/O-Exception, gab der Endpunkt trotzdem die
  reguläre 422-Antwort bzw. den `ValueError` zurück — als sei die Ablehnung sauber persistiert
  worden, obwohl der Run unbemerkt `pending` blieb (CodeRabbit-Major-Befund auf PR #843).
- Fix prüft den Rückgabewert von `update_run` explizit und fängt Exceptions ab: bei bestätigter
  Persistenz bleibt das Verhalten aus #841 unverändert (422 bzw. `ValueError` mit der detaillierten
  Provider-Key-Meldung); bei Persistenzfehler wird stattdessen das bestehende Projektmuster
  `ApiErrorCode.INTERNAL_ERROR` verwendet (Prepare-Pfad: `json_error(..., status=500)`;
  Restart-Pfad: `RuntimeError(ApiErrorCode.INTERNAL_ERROR)`, von `handle_api_errors` auf 500
  gemappt). Run-/Task-Bezug wird serverseitig geloggt, ohne Details an den Client zu leaken.
  `TaskManager.fail_task` bleibt bewusst best-effort (keine prüfbare Fehlersemantik ohne
  Änderung an `task.py`, außerhalb des Slice-Scopes) — dokumentiertes Restrisiko für den
  seltenen Fall, dass die Task-Markierung fehlschlägt, während die Run-Aktualisierung gelingt.

### Fixed (Verwaiste pending-Run-/Task-Records bei fehlendem Store-Key — 2026-07-22, Issue #841)

- **`prepare_simulation` (`backend/app/api/simulation_prepare.py`)** und
  **`_restart_simulation_prepare` (`backend/app/api/runs.py`)** legten `Run`- (und teils
  `Task`-)Datensätze bereits an, bevor der Store-Key-Guard einen Lauf mangels API-Key ablehnte —
  der Datensatz blieb danach dauerhaft `pending` in der Registry, ohne Fehlermeldung. Fix markiert
  den Run (und, wo bereits vorhanden, den Task) auf dem Guard-Pfad jetzt explizit als `failed` mit
  der Guard-Fehlermeldung, bevor die 422-Antwort bzw. der `ValueError` zurückgegeben wird
  (gefunden vom Opus-Reviewer als Nebenbefund bei Issue #798, kein Regress, eigenständiges
  Datenhygiene-/UX-Problem).

### Fixed (Restart eines Prepare-Runs nutzt Store-Key statt .env-Fallback — 2026-07-22, Issue #798)

- **`_restart_simulation_prepare` (`backend/app/api/runs.py`)** übergab `manager.prepare_simulation(...)`
  bisher ohne `llm_runtime` — der Restart eines Runs, der ursprünglich gegen einen Fremd-Provider
  lief, fiel dadurch still auf `Config.LLM_API_KEY`/`Config.LLM_BASE_URL` aus der lokalen `.env`
  zurück statt den in der Settings-DB hinterlegten Store-Key des aktiven Providers zu nutzen
  (Opus-Review-Folgebefund zu Issue #778, dessen Fix nur den Erst-Prepare-Pfad abdeckte).
- Fix nutzt denselben Resolver-Pfad wie `simulation_prepare.py::prepare_simulation`:
  `StageModelRouter.resolve` → `resolve_route_api_key` → `build_runtime_llm_config`. Lokale
  No-Auth-Endpoints bleiben ohne Key funktionsfähig; Fremd-Provider ohne Store-Key lehnen den
  Restart jetzt hart ab statt still auf den falschen Key auszuweichen.

### Fixed (Frontend-Testlauf: verbleibende Vitest-Teardown-Race nach #811 — 2026-07-21, Issue #797)

- **`EnvironmentTeardownError: Closing rpc while "onUserConsoleLog" was pending`** trat
  sporadisch weiter auf, obwohl `test.pool: 'threads'` bereits unter
  [#811](https://github.com/arn0ld87/agora/issues/811) die pinia-4-Race entschärft hatte —
  Restproblem war Vitests eigener console-Intercept-Mechanismus, der jede
  `console.*`-Ausgabe per RPC an den Hauptprozess weiterreicht; beim Worker-Teardown
  konnte dieser RPC-Call noch offen sein. Fix: `test.disableConsoleIntercept: true`
  global in `frontend/vite.config.js` — entfernt den racenden Mechanismus für die
  gesamte Suite statt ihn pro Spec zu umgehen. Der spec-lokale
  `console.warn`/`console.error`-Spy-Workaround in
  `frontend/src/views/v4/__tests__/HistoryView.spec.ts` (unzuverlässig) entfällt.
  10 aufeinanderfolgende `bun run test`-Läufe (170 Files / 1501 Tests) durchgehend
  Exit 0.

### Fixed (Backend-Dependency-SSoT: verwaiste `requirements.txt` entfernt — 2026-07-21, Issue #762)

- **`backend/requirements.txt` divergierte von `backend/pyproject.toml`/`backend/uv.lock`**
  (`nltk==3.10.0` statt der dokumentierten Risikoausnahme `nltk==3.9.4`, PYSEC-2026-597,
  Issue #661) — vermutlich ein isolierter Dependabot-Merge ohne `uv.lock`-Sync. Inventarisierung
  ergab: kein produktiver Pfad (Dockerfile, `install.sh`, `package.json`, `ci.yml`,
  `cve-monitor.yml`) installiert tatsächlich aus der eingecheckten Datei — CI erzeugt bei Bedarf
  bereits einen frischen, deterministischen Snapshot per `uv export` nach `/tmp`. Die verwaiste
  Datei wurde entfernt; `backend/pyproject.toml` + `backend/uv.lock` (via `uv sync --frozen`)
  bleiben die einzige handgepflegte Backend-Dependency-Quelle.
- **Neuer Drift-Guard**: `backend/tests/dependencies/test_dependency_ssot.py` schlägt fehl,
  falls `backend/requirements.txt` wieder manuell eincheckt wird, deren `nltk`-Pin vom
  `pyproject.toml`-Pin abweicht, oder ein produktiver Pfad wieder eine eingecheckte
  `requirements.txt` referenziert.

### Fixed (Report-Route-SSoT: UI-Auswahl ist die autoritative Report-Route — 2026-07-21, Branch `fix/report-provider-route-ssot`, Issue #817)

- **Route-Snapshot ↔ Client-Divergenz in `ReportGenerationService.start_generation`** behoben
  (`backend/app/services/report_generation.py`). Bei gesetztem LLM-Profil beschrieb der
  gelockte `report_generation`-Route-Snapshot den Workspace-/Global-Default (z. B. Google),
  während der ausgeführte `LLMClient` über den Parallelpfad `build_client_from_profile` ein
  anderes Profil (z. B. MiniMax) nutzte. Ursache: `seed_run_stage_routing` wurde ohne
  `llm_profile_id` aufgerufen, und der Client entstand außerhalb der gelockten Route. Fix: ein
  einziger autoritativer Pfad — seed (mit Profil/AiModelRef) → resolve → lock → `LLMClient.from_route`
  ausschließlich aus der gelockten Route. Der Parallelpfad `build_client_from_profile` entfällt in
  `start_generation`; ein Profil ist nur noch Eingang zur Routenerzeugung.
- **Explizite `ai_model_ref` am Generate-Endpunkt** (`POST /api/report/generate`): Der Request
  überträgt jetzt die vollständige kanonische Auswahl (`provider_connection_id`, `model_id`,
  `source`) als autoritative Report-Route. Neuer Backend-Contract `AiModelRef`
  (`backend/app/contracts/ai_provider_contract.py`) spiegelt das Frontend-`AiModelRefSchema`.
  Prioritätsreihenfolge: explizite `ai_model_ref` > Legacy-`llm_profile_id` > Projektprofil >
  Stage-Override > Workspace-Default. Widersprüchliche explizite Eingaben (`ai_model_ref` plus
  Legacy-Feld) werden mit HTTP 400 abgelehnt; unbekannte/deaktivierte ProviderConnection ebenso.
- **Run-Metadaten/Model-Attribution** stammen aus der gelockten Route statt aus den rohen
  Request-Feldern.
- **Frontend** (`frontend/src/components/Step4Report.vue`, `frontend/src/api/report.ts`): Ein
  expliziter Picker-Pick sendet `ai_model_ref` und kein konkurrierendes `llm_profile_id`/`llm_model`;
  ohne Pick wird kein erfundener Override gesendet. `GenerateReportData` ist um `ai_model_ref`
  typisiert.
- **Tests neu**: `backend/tests/services/test_report_provider_route_ssot.py` (RED→GREEN:
  Snapshot ≡ Client, AiModelRef→Route, unbekannte/deaktivierte Connection, Run-Metadaten,
  kein Secret-Leak), `backend/tests/api/test_report_provider_route_api.py` (Contract + Konflikt-400)
  und drei Payload-Tests in `frontend/src/components/__tests__/Step4Report.spec.ts`.
- **Strikte Connection/Model-Katalog-Validierung** (Issue #819, Folge von #817/#818):
  `seed_run_stage_routing` (`backend/app/services/llm_routing_seed.py`) prüft im
  `ai_model_ref`-Zweig jetzt zusätzlich per Live-Discovery (`ProviderConnectionService.probe`
  — derselbe Pfad wie `GET /provider-connections/<id>/models`, kein neuer Katalog, keine lokale
  Provider-Detection-Heuristik), dass `model_id` tatsächlich zum Modell-Katalog der gewählten
  `provider_connection_id` gehört. Gehört das Modell nicht zur Connection, wird die Route mit
  `ValueError` abgelehnt (→ HTTP 400 über das bestehende `except ValueError`-Handling in
  `report.py`). Schlägt die Discovery selbst fehl (Provider nicht erreichbar, ungültige
  Credentials), wird das mit einer eigenen, klar unterscheidbaren Meldung ("Modell-Katalog …
  derzeit nicht abrufbar") signalisiert statt fälschlich einen Model-Mismatch zu behaupten.
  Tests: `backend/tests/services/test_llm_routing_seed.py` (Model-Mismatch, Discovery-Fehlschlag,
  valide Kombination), `backend/tests/api/test_report_provider_route_api.py`
  (400-Mapping für Mismatch und Discovery-Fehlschlag), sowie die Fixture in
  `backend/tests/services/test_report_provider_route_ssot.py` um einen deterministischen
  Probe-Stub erweitert (Regressionsschutz für #817/#818).

### Fixed (Report-Rescue: positionsblinder `title`-Drop im Strict-Schema-Sanitizer — 2026-07-20, Branch `fix/report-rescue-real-provider`)

- **`_enforce_openai_strict_schema` strippte `title` positionsblind** in
  `backend/app/llm/json_mode.py`. Der rekursive `_walk` filterte den
  JSON-Schema-Metadaten-Key `title` über jeden Dict-Knoten — auch dort,
  wo `title` der **Name einer Property** ist (`properties: {"title": {...}}`,
  genutzt von `PlanSection` und `PlanResponse`). Die an
  OpenAI/Google geschickten Schemas verloren die Pflicht-Property
  `title`, die LLM-Antworten scheiterten danach an der Pydantic-
  Validierung mit „12 validation errors for PlanResponse — alle
  `…title: Field required`", und der gesamte Report-Lauf fiel auf
  `failed`. Fix: Sonderbehandlung des `properties`-Keys in `_walk` —
  die Keys darunter sind Property-Namen, keine Schema-Metadaten; nur
  die Feld-Schemata (values) werden rekursiv gewalkt, dort greift das
  Metadaten-Stripping normal.
- **Regressionstest neu** in
  `backend/tests/llm/test_json_mode_strict_schema.py`: drei Tests
  pinnen die positionsbewusste Unterscheidung — `title` als
  Property-Name überlebt in `properties + required`, `title` als
  Metadatum auf Objekt-Ebene wird weiter gestrippt,
  `PlanResponse`-Schema behält `title` top-level und je Section.
  RED → GREEN mit der Code-Änderung verifiziert.
- **End-to-End-Beweis (zwei aufeinanderfolgende Läufe)** auf der
  `minimax`/`MiniMax-M3`-Route mit `llm_model="MiniMax-M3"`
  (umgeht die alte `llm_profile_id`-Präzedenz auf das zu schwache
  `google`/`gemini-2.5-flash-lite`-Profil): Run B
  (`report_47705048af01`, task `526d06c6…`) und Run C
  (`report_715e4a552ce0`, task `5d39cfc1…`) liefen beide auf
  `status: completed`, `progress: 100`, alle 11 Pflichtabschnitte im
  Outline (`missing_sections: []`, Reihenfolge Executive Summary →
  Datenlücken eingehalten), Markdown-Export HTTP 200 mit
  ≥ 131 067 Bytes (`format=md`), keine Fallback-Marker
  (`Scenario Evaluation Report` etc.). Out of scope dieses Slices:
  ReACT-Thinking-Leak, hängende Reports ohne Progress, fehlendes
  `provider_connection_id`-Param am Generate-Endpunkt und der
  `/api/report/export?format=markdown` 400 — diese werden in
  Folgeslices adressiert.

### Fixed (pinia 4 + @pinia/testing 2 Migration — 2026-07-20, Branch `fix/811-pinia4-vitest-teardown-race`)

- **`pinia` `^3.0.4` → `^4.0.2`, `@pinia/testing` `^1.0.3` → `^2.0.1`** in
  `frontend/package.json`. Der zuvor auf [#811](https://github.com/arn0ld87/agora/issues/811)
  vertagte Bump war blockiert durch einen `EnvironmentTeardownError`
  (`[vitest-pool]: Failed to start forks worker` / `Timeout waiting for
  worker to respond`) beim vollen Testlauf. Ursache ist keine pinia-API-
  Änderung, sondern eine Vitest-interne Worker-Teardown-Race im
  Standard-`forks`-Pool unter paralleler Prozesslast — pinia 4 ändert nur
  die Cleanup-Reihenfolge in `setActivePinia`/`createPinia` und erhöht
  damit die Trefferwahrscheinlichkeit. Fix: `test.pool: 'threads'` in
  `frontend/vite.config.js` (Worker-Threads statt Child-Prozesse vermeiden
  die Fork-Spawn/Teardown-Race). `bun run test` läuft wieder grün
  (170 Files / 1496 Tests). Closes #811.

### Changed (Frontend-Dependency-Batch — 2026-07-20, Branch `chore/frontend-deps-batch`)

- **`@types/node` `^25.8.0` → `^26.1.1`** in `frontend/package.json` (Types-only,
  kein Laufzeit-Verhalten-Change). Konsolidiert vier kollidierende
  Dependabot-PRs auf derselben `package.json`-Zeile: #789 (pinia 4) und #791
  (@pinia/testing 2) wegen eines Vitest-`EnvironmentTeardownError`-Race in
  `AppShell.spec.ts` vertagt auf [#811](https://github.com/arn0ld87/agora/issues/811),
  #792 (typescript 7) wegen einer vue-tsc/@typescript-eslint-Toolchain-Blockade
  vertagt auf [#812](https://github.com/arn0ld87/agora/issues/812), #790
  (identischer @types/node-Bump) direkt durch diesen Slice ersetzt. Alle vier
  PRs geschlossen.

### Added (Subagent-Modellmigration — 2026-07-20)

- **Subagenten auf `MiniMax-M3` migriert**: Sechs operative
  Subagenten existieren jetzt als `-m3`-Variante
  (`agora-doc-worker-m3`, `agora-evidence-auditor-m3`,
  `agora-frontend-worker-m3`, `agora-reviewer-m3`,
  `agora-refactor-worker-m3`, `agora-test-worker-m3`). Das
  Lead-Modell dieser Session ist ebenfalls `MiniMax-M3`. Die
  historischen Subagenten ohne `-m3`-Suffix bleiben im Repo
  als Referenz, werden aber nicht mehr dispatcht.
- **Reviewer-Subagent umbenannt**: `agora-opus-reviewer-m3`
  → `agora-reviewer-m3`, weil das Modell nicht mehr Opus ist.
  Routing-Tabellen in [`docs/runbooks/subagent-routing.md`](docs/runbooks/subagent-routing.md)
  und [`CLAUDE.md`](CLAUDE.md) sind nachgezogen.
- **M3-Varianten härter als die Originale**: Branch-Check im
  Standard-Loop der schreibenden Worker, Doku-Sync-Schritt
  (`docs/STATUS.md`, `ROADMAP.md`, `CHANGELOG.md`, Folge-Issue),
  H1 nach Frontmatter, korrekte deutsche Anführungszeichen,
  vollständige Audit-Tabelle mit acht Checks und
  `disallowedTools`-Härtung beim Evidence-Auditor. Die
  Original-Subagenten behalten ihre Schwächen bis zu einem
  eigenen Härtungs-Slice (siehe Folge-Issue unten).
- **`ROADMAP.md`**: Stand-Datum von `18.07.2026` auf `20.07.2026`
  nachgezogen. Strategische Inhalte, Release-Gates und
  Release-Reihenfolge unverändert.
- **Folge-Issue**: Härtung der historischen Subagenten ohne
  `-m3`-Suffix (Branch-Check, Doku-Sync, H1, Audit-Tabelle,
  `disallowedTools`) auf demselben Niveau wie die M3-Varianten;
  siehe [#803](https://github.com/arn0ld87/agora/issues/803).

### Changed (CI/Dependabot — 2026-07-20, Branch `chore/dependabot-ignore-camel-ai`)

- **Dependabot: `camel-ai` im pip-Backend-Block temporär ignoriert**.
  `camel-oasis==0.2.5` pinnt exakt `camel-ai==0.2.78` (alle
  `camel-oasis`-Releases auf PyPI pinnen 0.2.78 fest; kein Release
  akzeptiert `>=0.2.90`). Der offene Dependabot-Bump PR #793 wurde
  deshalb geschlossen. Der `ignore`-Eintrag verhindert weitere
  No-Op-Retry-PRs, bis `camel-oasis` ein Release mit
  `camel-ai>=0.2.90` veröffentlicht (Tracking: [#806](https://github.com/arn0ld87/agora/issues/806))
  oder Issue #762 (`build(0.9): Backend-Dependency-SSoT und
  Security-Drift bereinigen`) das Pin-Set löst. Kein
  Laufzeit-Verhalten-Change.

### Fixed (Issue #778 — 2026-07-20)

- **Key-Routing-Divergenz in Sim-Prep-Generatoren behoben**:
  `SimulationConfigGenerator` und `OasisProfileGenerator` fielen bei fehlendem
  Store-Key still auf `Config.LLM_API_KEY` zurück, auch wenn der Aufrufer
  bereits eine fremde Provider-Base-URL aufgelöst hatte — das lokale
  Ollama-`.env`-Passwort ging dadurch an Fremd-Provider und brach jeden
  Provider-Wechsel über die UI mit `404`/`401`. Beide Generatoren nutzen den
  `.env`-Fallback jetzt ausschließlich, wenn auch die Base-URL aus derselben
  `.env`-Quelle stammt; andernfalls muss der Key vom Aufrufer kommen.
- **Verhaltensänderung für Betreiber**: `LLM_API_KEY` aus der `.env` greift
  nicht mehr automatisch, sobald eine Base-URL explizit über die
  Provider-Route aufgelöst wurde. Setups, die sich bisher auf diesen
  impliziten Fallback verlassen haben, erhalten künftig bereits zur
  Prepare-Zeit `ValueError: LLM_API_KEY not configured`. Abhilfe: Key an der
  Provider-Connection unter Einstellungen → LLM-Anbieter hinterlegen.
- Lokale No-Auth-Endpoints (`localhost`, `127.0.0.1`, `::1`, `0.0.0.0`,
  `host.docker.internal`) laufen weiterhin ohne Key — `simulation_prepare.py`
  und `simulation_history.py` setzen dafür einen dokumentierten
  No-Auth-Platzhalter (`LOCAL_NO_AUTH_API_KEY`), bevor der Wert an die
  Generatoren geht.
- **MiniMax-Fall im Provider-Wechsel-Test parametrisert**: Die
  Akzeptanzkriterien aus #778 verlangen einen Provider-Wechsel
  `Gemini ↔ MiniMax ↔ Ollama` mit umgeschaltetem Sim-Key. Der neue
  Service-Test parametrisert dafür `test_prepare_foreign_provider_with_store_key_passes_store_key_through`
  über `provider_id="google" | "minimax" | "openai"` mit den jeweiligen
  fremden Base-URLs.
- **Kein Eingriff in [#799](https://github.com/arn0ld87/agora/issues/799)**:
  Der No-Auth-Platzhalter-Nachzug in `simulation_history.py::generate_profiles`
  ist **kein** Store-Key-Pfad und **kein** 500→422-Mapping für fehlende
  Provider-Resolution; er zieht nur die bereits in `simulation_prepare.py`
  etablierte No-Auth-Freigabe nach, weil `generate_profiles` denselben
  Generator-Vertrag nutzt und sonst regressionsweise einen `ValueError`
  für lokale Setups werfen würde. [#799](https://github.com/arn0ld87/agora/issues/799)
  bleibt bewusst offen.

### Build (Issue #759 — 2026-07-19)

- **VERSION als Single Source of Truth**: Datei `VERSION` ist die kanonische
  Versionssource; `backend/pyproject.toml`, `package.json`, `frontend/package.json`
  und README-Badge werden automatisch synchronisiert. Tool
  `backend/scripts/check_version_drift.py` um `--write`-Modus erweitert, prüft
  nun auch `frontend/package.json`. CI-Job `version-drift.yml` und lokal
  `pre-push-gate.sh schemas` erzwingen Einhaltung. Abwicklung:
  [`docs/runbooks/release-versioning.md`](docs/runbooks/release-versioning.md).
  [`docs/runbooks/release-versioning.md`](runbooks/release-versioning.md).

### Fixed (Issue #739 — 2026-07-18)

- **Golden-Gate Accessibility E2E-Smoke lokal grün**: Tertiärtext,
  Status-Grün und Embedding-Warntext erfüllen jetzt WCAG AA; Avatar-Dateifeld
  und Reasoning-Auswahl besitzen zugängliche Namen. Der axe-Helper wartet
  bedingungsbasiert auf das Ende der Vue-Route-Transition, und die globale
  Reduced-Motion-Regel begrenzt auch hartkodierte Animationen. Alle zehn
  Routen sind in zwei aufeinanderfolgenden Playwright-Läufen grün.

- **Report-Modi E2E-Smoke lokal grün**: `report-modes.spec.ts` seedet vor der
  Report-Generierung jetzt deterministisch die vom Report-Contract geforderten
  50 Personas. Ohne Fixture endete `generate_report()` bereits am
  Persona-Floor-Gate mit `ReportStatus.INCOMPLETE`; der Poll konnte deshalb
  nie `completed` erreichen. Alle drei Modi und der Balanced-Default sind in
  zwei aufeinanderfolgenden lokalen Playwright-Läufen grün.

- **Upload + Graph E2E-Smoke lokal grün**: Der `upload-graph`-Smoke wurde durch
  den in PR #684 eingeführten Onboarding-Guard (`router/onboardingGuard.ts`)
  blockiert — `page.goto('/process/<projectId>')` wurde zu `/onboarding`
  umgeleitet, `.graph-view` mountete nie. Der Spec räumt den Wizard jetzt per
  idempotentem `POST /api/onboarding/dismiss` vor dem `page.goto` weg. Kein
  Selektor und keine State-Verkettung geändert; die vorgelagerte
  `GET /api/graph/data`-Assertion war stets grün. Folgearbeit (Trigger-Readd,
  restliche Smokes) unter Issue #739.

### Changed (Issue #761 — 2026-07-18)

- **Provider-, Secret- und Routing-SSoT abgeschlossen**: Explizit aufgelöste
  `AiRoute`-Snapshots gewinnen in Ontologie- und Graph-Build-Pfaden vor
  Legacy-Profilen. Cloud-Secrets werden ausschließlich aus einer passenden,
  aktivierten `ProviderConnection` gelesen; eingebettete Profil-Keys sind kein
  Fallback mehr.
- **Provider-Erkennung konsolidiert**: `/api/simulation/available-models`
  delegiert an `registry.detect_provider(mode="http")`. Die getrennte
  Embedding-Erkennung bleibt gemäß ADR-0007 eigenständig und ist über den
  öffentlichen `EmbeddingService.embed()`-Pfad testfixiert.
- **Legacy-HTTP-Pfade terminiert**: `/api/settings/llm-profiles/*` und
  `/api/llm/providers/*` liefern gemäß RFC 9745 `Deprecation: @1784332800`, den
  kanonischen Nachfolger und `X-Agora-Removal-Version: 1.0.0`. Ein
  RFC-`Sunset`-Datum folgt erst, sobald ein belastbares Release-Datum feststeht.

### Fixed (Issue #750 — 2026-07-18)

- **MiniMax-/Google-Provider-Contract synchronisiert**: Der Frontend-Zod-Spiegel
  für `ModelActiveEvent.provider` akzeptiert jetzt die vom Backend publizierten
  Werte `minimax` und `google`; Contract-Tests fixieren den SSE-Pfad. Das
  dokumentierte HTTP-Provider-Vokabular in `registry.detect_provider` und
  `registry.get_adapter` enthält MiniMax nun ebenfalls. Die bereits auf `main`
  vorhandene hostname-basierte Erkennung bleibt durch die
  Backend-Registry-Regressionstests abgesichert.

### Internal (Slice 7.6d — 2026-07-14)

- **Frontend**: `LlmProfileManager.vue` vom legacy `ModelPicker.vue` auf den
  connection-basierten kanonischen `AiModelPicker` (`AiModelRef`) migriert.
  Provider/base_url werden aus der verknüpften Connection bezogen statt aus
  dem Runtime-Mapping; unbekannte Connections blockieren den Save mit
  Fehler-Banner. `v4/forms/ModelPicker.vue` wurde als letzter produktiver
  Legacy-Picker entfernt; der vi.mock-Stub in
  `HeroNewRun.profiles.spec.ts` wurde mit gelöscht. Keine
  Kompatibilitätsschicht, keine zweite Provider-Erkennung. Specs und
  `vue-tsc` grün.

### Breaking Changes (Slice 7.6c — 2026-07-14)

- **Frontend**: LocalStorage-Key `agora.<scope>.route` (Scope = `hero`, `home`,
  `report`) wird nicht mehr gelesen. User mit persistierten Legacy-Werten
  erhalten ab diesem Release den Standard des Eltern-Kontextes (Workspace-
  bzw. Stage-Default). Beim ersten Mount wird der alte Key defensiv aus
  `localStorage` entfernt. Der neue AiModelRef-Persistenz-Pfad
  (`agora.<scope>.aiModelRef`) bleibt für den v4-`AiModelPicker` erhalten;
  die Migration der Legacy-Picker (`ModelPicker`/`ReportModelControls` in
  Home/Step4Report) auf AiModelRef-Persistenz folgt in Slice 7.6d.

### Internal (Slice 7.6c — 2026-07-14)

- **Frontend**: Type `StageLLMRoute` und Zod-Spiegel `StageLLMRouteSchema`
  wurden aus dem Frontend entfernt. Nachfolgetyp ist `LlmRoute`
  (`frontend/src/contracts/llmRoute.ts`), das jetzt auch `StageIdSchema` und
  `ReasoningEffortSchema` definiert (Import-Zyklus mit `llmRoutingContract.ts`
  aufgelöst; beide Enums werden von dort re-exportiert). Das Backend bleibt
  Pydantic-SSoT.
- **Frontend**: `useAiModelRefAdapter.toStageLlmRoute` → `toLlmRoute`.
- **Frontend**: Storage-Migrations-Helper (`migrateStoredRoute*`) entfernt.

### Added (onboarding-model-picker-slice-5-6-final — 2026-07-13)

- **Echte Playwright-E2E für `AiModelPicker`** (Onboarding Slice 5.6):
  Die fünf Skeleton-Tests laufen ohne `test.describe.skip()` und decken
  Tastatur-Navigation, Suche, eine verfügbare und aktivierte Online-Option,
  die Abwesenheit des Offline-Modells sowie den persistierten Run-Snapshot
  ab. Der Snapshot-Test prüft die `PATCH`-Response auf
  `provider_connection_id`, `model_id` und
  `source === 'stage_override'`.

- **Deterministische E2E-Provider-Discovery**: Der Compose-Override startet
  `mock-models` als OpenAI-kompatiblen `/models`-Dienst. Das globale
  Setup legt dedizierte Online- und Offline-Test-Provider-Connections an;
  `scripts/e2e-up.sh` ergänzt `AGORA_SECRET_KEY` für den Secrets-Store.

- **Stabile Routing-Selektoren und Capability-Auswertung**:
  `LlmRoutingTestId` liefert `stageRow` und `stageSave` als SSoT, ergänzt um
  `llm-routing-run-id`. Im Chat-Mode werden Modelle nur bei explizitem
  Eintrag in `unsupported_capabilities` ausgeschlossen; unbekannte
  Capability-Daten bleiben auswählbar. PR
  [#707](https://github.com/arn0ld87/agora/pull/707). Playwright und das
  Pre-Push-Gate auf dem armserver bleiben bewusst als Verifikation offen.

### Added (embedding-reembedder-fact — 2026-07-13)

- **Fact-Embedding-Re-Embed (Onboarding Slice 4.4)**:
  ``Neo4jReEmbedder`` re-embedded neben ``(n:Entity).entity_embedding``
  jetzt auch ``RELATION.fact_embedding`` in einer zweiten, sequenziellen
  Phase. Da ``fact_embedding`` eine echte ``RELATIONSHIP``-Property auf
  ``:RELATION``-Kanten ist (kein reifizierter Fakt-Knoten), nutzt die
  Fact-Phase ``db.create.setRelationshipVectorProperty`` (Neo4j 5.13+,
  Stack ist 5.18 CE) und einen versionierten Relationship-Vector-Index
  ``FOR ()-[r:RELATION]-() ON (r.fact_embedding_vN)`` (``CREATE ...
  IF NOT EXISTS``, niemals DROP, ADR-0007). Cursor ist ``r.uuid``
  (``:RELATION`` hat eine eigene UUID). Ein neues Vertragsfeld
  ``EmbeddingMigrationProgress.phase: Literal["entity","fact"]``
  (default ``"entity"``, backward-kompatibel für persistierte Alt-Jobs;
  inkl. Zod-Spiegel und regenerierter JSON-Schemas) disambiguiert den
  einzigen Cursor ``last_processed_id`` (Entity-UUID vs. RELATION-UUID)
  statt zwei getrennter Cursor-Spalten einzuführen. Der Phasenwechsel
  ``entity -> fact`` wird ohne separaten Checkpoint im Speicher
  vollzogen; ``_drain(fact)`` schreibt den ersten sauberen Fact-
  Checkpoint. Resume nach Crash: ein in der Fact-Phase gecrashter Job
  überspringt beim Wiederaufnehmen die Entity-Phase (``phase=="fact"``)
  und setzt die Fact-Phase am ``last_processed_id`` fort; ein Crash am
  Phasenübergang läuft die (leere) Entity-Phase idempotent durch.
  Schlägt die Entity-Phase fehl (Dimension-Mismatch/None-Vektor), wird
  die Fact-Phase nicht gestartet — kein Switch auf einen
  unvollständigen Index-Satz. Alignment-Drift-Guard (Vektoranzahl ≠
  Textanzahl) bricht hart ab. ``EmbeddingIndexVersion`` bleibt
  bewusst entity-only; Fact-Index-/Property-Namen werden konventionell
  aus der Ziel-Version abgeleitet (``fact_embedding_v{N}``) und der
  Engine explizit übergeben. 9 neue ReEmbedder-Tests, 3 neue Contract-
  Tests, 3 neue Zod-Tests. Bewusst offen: Gemini-Batch-Embedding,
  ``scope="project"``-Filter, fact-spezifische ``EmbeddingIndexVersion``,
  Search-Pfad-Umstellung auf die neue Fact-Property.

### Changed (onboarding-model-picker-slice-5-5 — 2026-07-13)

- **Store-Konsolidierung `aiModels.ts`** (Onboarding Slice 5.5):
  Die drei getrennten Stores `store/llmProviders.ts`,
  `store/llmProfiles.ts` und `store/llmRoutingDefaults.ts` sind in
  `store/aiModels.ts` zusammengeführt (SSoT-Import-Oberfläche,
  Master-Prompt §5.3/§6.1). Die Pinia-Store-IDs bleiben unverändert →
  persistierter State und Verhalten stabil. Neue Facade
  `useAiModelsStore()` bündelt die drei Teil-Stores. Alle 17 Importer
  (prod + test) auf `@/store/aiModels` umgestellt; die alten Store-Dateien
  gelöscht. 19 neue Spec-Tests (`store/__tests__/aiModels.spec.ts`).
- **Legacy-Picker-Check via `@deprecated`** statt Opt-in-Marker: Der
  Grep-CI-Check (`check_legacy_model_picker.py`) erlaubt einen verbotenen
  v3-Import jetzt genau dann, wenn dessen **Ziel** ein
  `@deprecated`-JSDoc-Tag trägt. Alle `legacy-model-picker-allow`-Marker
  aus dem Frontend entfernt.

### Deprecated (onboarding-model-picker-slice-5-5 — 2026-07-13)

- **v3/v4-Legacy-Picker und -Composables** als `@deprecated` markiert,
  bleiben als Read-Adapter für die noch nicht migrierten v3-Consumer:
  `components/ui/ModelPicker.vue` (verwaist),
  `components/llm/LlmProfilePicker.vue` (EnvSetupModelPanel, Step4Report,
  ReportBranchControls), `components/ActiveModelBadge.vue`
  (WorkspaceHeader), `components/v4/forms/ModelPicker.vue`
  (ReportModelControls, Home), `components/v4/forms/LlmProfileManager.vue`
  (SettingsGeneralView) und `composables/useRuntimeLlmOptions.ts`
  (Runtime-Credential-Override; Step2EnvSetup, Step3Simulation, MainView,
  useEnvForm). Migration dieser Consumer folgt in Folge-Slices (kein
  Big-Bang; profiles-/runtime- vs. connection-basiertes Datenmodell).

### Added (onboarding-model-picker-slice-5-4 — 2026-07-13)

- **AiModelPicker an allen v4-Auswahlstellen** (Onboarding
  Slice 5.4): `StepModelOverrideChip.vue` (Run-Stages),
  `views/Settings/LlmProvidersView.vue` (Workspace-Default-Card),
  `v4/dashboard/HeroNewRun.vue` (Dashboard), v3
  `components/LlmRouting/LlmRoutingView.vue` (Global-Default +
  Stage-Overrides) und `views/Settings/SettingsGeneralView.vue`
  (Pilot-Abschluss mit Persistenz an
  `useLlmRoutingDefaultsStore`) nutzen den kanonischen
  `AiModelPicker.vue` aus Slice 5.1. Vertrags-Wechsel
  `StageLLMRoute` (v3, `provider_id`) → `AiModelRef` (v4,
  `provider_connection_id`) wird durch den neuen
  `useAiModelRefAdapter`-Composable (pure + Vue-Factory)
  gekapselt; v3-Stores und -Endpoints bleiben unveraendert.
  HeroNewRun liest bestehende `agora.hero.route`-Eintraege
  (StageLLMRoute-JSON) automatisch via
  `adapter.migrateStoredRoute` und schreibt sie als neue
  `agora.hero.aiModelRef`-Eintraege. 5.5 deprecated die alten
  Picker und Stores; bis dahin ist der Adapter Glue-Layer
  zwingend noetig. 95 neue Spec-Tests
  (Adapter 16, StepChip 16, LlmProviders 16, Hero 19,
  LlmRouting 14, SettingsGeneral 14).

- **Zod-Spiegel fuer `AiModelRef`**: `AiModelRefSchema`,
  `AiModelSourceSchema`, `AiModelRefInputSchema`,
  `AiModelProviderKindSchema`, `AiModelCapabilitySchema`,
  `AiModelStatusSchema`, `AiModelPickerModeSchema` in
  `frontend/src/contracts/aiModelRef.ts`. ermoeglicht
  localStorage-Validierung in HeroNewRun und Adapter-Tests.

- **i18n-Keys fuer neue Stellen**:
  `stepModelOverrideChip.{label,modelPlaceholder,overrideBadge,clearOverride,close,lockedBadge}`
  und `settings.v4.general.workspaceDefaultModel` in `de.json`
  + `en.json`.

### Added (embedding-reembedder — 2026-07-13)

- **Echte Neo4j-Re-Embedding-Engine (Onboarding Slice 4.3.4)**:
  ``backend/app/services/embedding_reembedder.py`` ersetzt den
  ``_NoopReEmbedder``-Stub. ``Neo4jReEmbedder`` liest alle
  ``(n:Entity)``-Knoten batchweise per ``uuid``-Cursor, erzeugt
  Embeddings über den konfigurierten Provider, prüft jede
  Vektor-Dimension gegen die verifizierte Konfiguration und schreibt
  in die versionierte Property (``db.create.setNodeVectorProperty``,
  Index via ``CREATE VECTOR INDEX ... IF NOT EXISTS`` — niemals DROP,
  ADR-0007). Nach jedem Batch wird ein Checkpoint persistiert;
  ``EmbeddingMigrationProgress.last_processed_id`` (neues
  Vertragsfeld inkl. Zod-Spiegel) macht den Lauf nach einem Crash
  über ``POST /migrations/<id>/run`` wiederaufnehmbar (Job-Status
  ``running`` gilt als Resume). Dimension-Mismatch führt zu
  ``failed`` ohne Index-Switch. Gemini-Re-Embedding wird explizit
  als „noch nicht unterstützt" abgelehnt statt vorgetäuscht.
  Bewusst offen: ``scope="project"``-Filter (``RELATION.fact_embedding``-
  Re-Embed folgt in Slice 4.4, siehe oben).

### Added (embedding-migration — 2026-07-12)

- **Embedding-Migrations-Service (Onboarding Slice 4.3)**:
  ``backend/app/services/embedding_migration.py`` orchestriert den
  Re-Embedding-Lifecycle gemaess ADR-0007. Vollstaendige
  Statusuebergaenge ``pending → running → validating → completed |
  rolled_back | failed``, atomarer Switch nach erfolgreicher
  Validierung, idempotenter ``start()`` (kein doppelter Job fuer
  dieselbe Konfiguration), explizites ``cancel()`` setzt auf
  ``rolled_back`` statt ``failed`` (Operator-Entscheidung). Re-Embedder
  ist als Protocol injizierbar — Tests laufen ohne Neo4j, der
  echte Re-Embedding-Loop kommt mit Neo4j-Anbindung in einem
  Folge-Slice.
- **Ollama-Download-Service (Onboarding Slice 4.3)**:
  ``backend/app/services/embedding_ollama_pull.py`` laedt ein
  Embedding-Modell von ``POST {base_url}/api/pull`` (NDJSON-Stream)
  und liefert einen strukturierten Bericht zurueck. Sicherheit:
  strikte Model-Name-Validierung (ASCII a-z, A-Z, 0-9, '-', '_',
  '.', ':', 1-100 Zeichen — schliesst Shell-Injection auf
  Modell-Namens-Ebene aus), keine Shell-Aufrufe (immer strukturierte
  JSON-Requests via ``requests.post``), Loopback/Ollama-Cloud-
  Einschraenkung, 10-Minuten-Default-Timeout, 60-Sekunden-Stream-
  Read-Timeout.
- **Migrations-API** unter ``/api/llm/embedding/migrations``:
  ``POST /`` (startet), ``GET /`` (listet), ``GET /<id>``, ``POST
  /<id>/run``, ``POST /<id>/cancel``.
- **Ollama-Download-API** unter ``/api/llm/embedding/ollama/pull``:
  synchroner Endpoint mit strukturiertem JSON-Report (kein
  Server-Sent-Event-Stream, weil der UI-Setup-Wizard das Ergebnis
  atomar braucht).
- **Embedding-Migration-Vertrag erweitert**: ``source_index_version``
  darf jetzt ``0`` sein (Sentinel fuer Cold-Start-Migration ohne
  Quell-Index). Vertrag stellt sicher, dass ``source=0`` nur mit
  ``target=1`` kombiniert wird und ``source < target`` immer gilt
  (sonst ValueError).
- 35 neue Tests in
  ``tests/services/test_embedding_migration.py`` (12) und
  ``tests/services/test_embedding_ollama_pull.py`` (23) decken
  Lifecycle, Validierung, Abbruch, Model-Name-Validierung,
  Stream-Parsing, Auth-Fehler, Base-URL-Validierung und
  Bearer-Header-Verhalten ab.

### Fixed (Vertrag — 2026-07-12)

- ``EmbeddingMigrationJob`` akzeptiert ``source_index_version=0``
  als Cold-Start-Sentinel; vorher war die strukturelle Annahme
  ``source >= 1`` zu strikt.

### Added (embedding-service — 2026-07-12)

- **Embedding-Configuration-Service (Onboarding Slice 4.2)**: Persistenter
  Store (`backend/app/services/embedding_configuration_store.py` mit
  `flock`-basierter Prozesssperre, atomarem Write via `os.replace`, Modus
  0600, getrennte Dateien für Konfigurationen und versionierte Indizes).
  Service
  (`backend/app/services/embedding_configurations/service.py`) mit
  anbieter-spezifischer Probe (Ollama lokal, Ollama Cloud, OpenAI,
  OpenAI-kompatibel, Gemini), Lifecycle-Wechsel mit Eindeutigkeits-
  Garantie (pro `scope` maximal eine `active` Konfiguration), Probe-
  Status-Übersetzung (`available → probed`, `unavailable/degraded/
  invalid_credentials/unsupported → failed`), Dimensions-Mismatch
  führt zu `failed` mit beschreibendem `status_message`. Legacy-Adapter
  (`legacy.py`) materialisiert `Config.EMBEDDING_*` on-demand in eine
  nicht-persistente `EmbeddingConfiguration` mit `status="proposed"`,
  damit alte Installationen ohne Migration funktionieren — aber kein
  stilles Schreiben in den Store, kein DROP ohne Backup-Plan. Kanonische
  API `GET/POST /api/llm/embedding/configurations[/active]`,
  `GET/PUT/DELETE /api/llm/embedding/configurations/<id>`,
  `POST /api/llm/embedding/configurations/<id>/test` und
  `POST /api/llm/embedding/configurations/<id>/activate`. 43 neue
  Tests in `tests/services/test_embedding_configuration_store.py`,
  `tests/services/embedding_configurations/test_service.py`,
  `tests/services/embedding_configurations/test_legacy.py` und
  `tests/api/test_embedding_configurations_api.py`.

### Fixed (zugehörig zu Slice 4.2)

- Slice-3-API-Test `test_upsert_rejects_invalid_public_base_url` (war
  bereits durch `to_jsonable_python(fallback=str)` aus PR #687
  repariert) bleibt mit dem neuen Service stabil grün; keine Regression.

### Accepted (ADR — 2026-07-12)

- **ADR-0007** (Embedding-Konfiguration und Indexmigration) von
  **Proposed** auf **Accepted** gehoben (User-Sign-off via PR-Merge
  für Slice 4.1+4.2). Die kanonischen Verträge aus Slice 4.1 und der
  Service/Store aus Slice 4.2 setzen die in der ADR geforderten
  Garantien strukturell um. Migrations-Engine und Ollama-Download
  (Slice 4.3) bleiben offen.

### Added (embedding-contracts — 2026-07-12)

- **Kanonische Embedding-Verträge (Onboarding Slice 4.1)**: Neue
  Pydantic-SSoT-Modelle `EmbeddingConfiguration`,
  `EmbeddingConfigurationUpsertRequest`, `EmbeddingConfigurationResponse`,
  `EmbeddingMigrationJob`, `EmbeddingMigrationProgress`,
  `EmbeddingMigrationJobResponse`, `EmbeddingIndexVersion` und
  `EmbeddingModelMetadata` in `backend/app/contracts/embedding_contract.py`.
  Die Verträge sind strikt getrennt von der Chat-Welt (`ProviderConnection`,
  `AiModel`, `AiRoute`); sie teilen nur die `provider_connection_id` als
  Referenz. `EmbeddingProviderKind` ist eine echte Restriktion der
  bestehenden `ProviderConnectionKind`-Menge (`ollama`, `openai`, `google`,
  `custom`, `ollama_cloud`, `openai_compatible`); Anthropic, CLI-Bridges und
  andere Chat-only-Provider sind als Embedding-Quelle explizit
  ausgeschlossen. `scope` ist `global` (Workspace-Default) oder `project`
  (Per-Project-Snapshot, mit strukturell erzwungener `project_id`-Pflicht).
  `EmbeddingMigrationJob` modelliert den vollständigen Lifecycle
  (`pending → running → validating → completed | rolled_back | failed`)
  mit Checkpoint/Progress/Abbruch fuer den Re-Embedding-Workflow aus dem
  Migrations-Plan. `EmbeddingIndexVersion` ermoeglicht versionierte
  Neo4j-Vector-Indizes (parallele `index_name` + `property_key` pro
  Version), damit ein Wechsel alte Daten nicht ploetzlich unlesbar macht.
  Helper `provider_kind_supports_embeddings()` bildet die Bruecke zwischen
  Slice 3 (`ProviderConnection`) und Slice 4 (`EmbeddingConfiguration`).
  Sieben neue JSON-Schemas unter `schemas/embedding-*.schema.json`,
  registriert in `dump_schemas`; `dump_schemas --check` ist gruen fuer
  alle 46 Schemas.

### Fixed (api-responses — 2026-07-12)

- `json_error(extra={...})` crashed, wenn `extra` ein Pydantic
  `ValidationError.errors()`-Payload enthaelt: Pydantic v2 packt im
  `ctx`-Feld eine lebende `ValueError`-Instanz, die Flasks Default-JSON-
  Encoder nicht serialisieren kann — die Folge war 500 statt 4xx auf
  `/api/llm/provider-connections` (u. a. bei `test_upsert_rejects_invalid_
  public_base_url`). Fix: zentraler Helper `_to_jsonable()` in
  `app/utils/api_responses.py`, der via `pydantic_core.to_jsonable_python`
  beliebige Werte (inkl. Pydantic-Validierungs-Exceptions, `SecretStr`,
  `datetime`, `Decimal`) in JSON-kompatible Form bringt, BEVOR sie an
  `jsonify` gehen. Der Fix wirkt automatisch fuer alle API-Routen, die
  `json_error` mit `extra=...` aufrufen (Provider-Connections, API-Keys,
  LLM-Profile, LLM-Routing). Regression-Test in
  `tests/test_api_responses.py::test_json_error_sanitizes_pydantic_
  validation_error_payload` pinnt das Verhalten.

### Added (provider-connections — 2026-07-12)

- **Kanonischer Provider-Connection-Lifecycle (Slice 3, ADR-0006)**:
  persistente Provider-Verbindungen auf Basis des `ProviderConnection`-
  Vertrags aus Slice 1. Neuer datei-basierter Store
  (`provider_connections.json`, atomar, flock, 0600) unter `AGORA_DATA_DIR`;
  Secrets bleiben ausschließlich als `secret_ref` im bestehenden
  Fernet-verschlüsselten Secret-Store. Neue Endpunkte
  `GET/PUT/DELETE /api/llm/provider-connections[/<id>]` sowie
  `POST …/<id>/test` und `GET …/<id>/models` (Test + Modell-Discovery über
  eine Adapter-Schicht für OpenAI-, Anthropic-, Gemini-, MiniMax-,
  Ollama-Cloud-, OpenAI-kompatible und lokale Ollama-Verbindungen).
  Unsupported Provider (z. B. `opencode_go`, Subscription-/CLI-Bridges)
  werden ehrlich mit 409 `provider_unsupported` abgelehnt, bevor Store oder
  Service angefasst werden; lokale Ollama-Verbindungen sind auf
  Loopback-Base-URLs beschränkt, alle übrigen auf öffentliche HTTP(S)-URLs.
  Die Legacy-Routen (`/providers`, `/providers/<id>/models|test`,
  `/api-key`) delegieren als Kompatibilitätsadapter an dieselbe
  Lifecycle-Schicht.
- **Settings-UI für Verbindungen**: `LlmProvidersView` auf den
  Connection-Lifecycle umgestellt (Status-Badges, Test-Ergebnis,
  Discovery-Modellliste, lokaler Ollama-Flow ohne Key-Feld); unsupported
  Provider zeigen einen Hinweis statt Formularfeldern. Neuer API-Client
  `providerConnections.ts` validiert jede Response-Grenze mit Zod;
  API-Keys werden nie im Pinia-State oder Browser-Storage gehalten.

### Fixed (provider-connections — 2026-07-12)

- `ProviderDescriptorSchema.type` (Zod) spiegelte nur 5 von 12
  Backend-`ProviderType`-Werten; die Enum ist additiv auf die volle
  Literal-Menge erweitert (vorbestehender Drift).

### Added (profile/onboarding — 2026-07-11)

- **Lokales Benutzerprofil (Slice 2, ADR-0008)**: neuer Pydantic-v2-Vertrag
  `UserProfile` (Anzeigename, Sprache, Zeitzone, Report-Sprache, Theme,
  Datenschutzmodus, Avatar-Referenz) mit striktem Zod-Spiegel und
  JSON-Schemas. Persistenz als datei-basierter Single-User-Store
  (`user_profile.json`, atomar, flock, 0600) unter `AGORA_DATA_DIR`.
  Endpunkte `GET/PUT /api/profile` plus Avatar-Upload mit MIME-Allowlist
  (PNG/JPEG/WebP), Magic-Bytes-Prüfung (SVG strukturell abgelehnt) und
  2-MB-Limit; Avatar-Referenzen sind per Contract-Pattern gegen
  Path-Traversal gesichert. Benutzerprofil und KI-Presets (`LlmProfile`)
  bleiben getrennte Schlüsselräume.
- **Resumierbares Erst-Onboarding**: backendseitig persistierter
  `OnboardingState` (`onboarding_state.json`) mit deterministischer
  Schrittfolge, Wiederaufnahme nach jedem Schritt, `dismiss`/`reopen` und
  serverseitig geprüfter Completion (gültiges Profil + konfiguriertes
  Chat-Modell + gültige Embedding-Konfiguration). Endpunkte unter
  `/api/onboarding` (`GET /`, `PUT /step`, `POST /complete|dismiss|reopen`).
  Frontend: Wizard unter `/onboarding` (Betriebsmodus-Wahl, Profilformular,
  ehrliche Status-Schritte für Provider/Modelle/Embeddings mit Verweis auf
  die Settings, Zusammenfassung), Router-Guard mit Fail-open-Semantik —
  API-Fehler oder `dismissed` sperren niemals aus.
- **Settings-IA**: neue Seite `/settings/profile` (gemeinsames
  `ProfileForm` mit dem Onboarding); Sidebar-Eintrag „Users & Teams" wird
  zu „Profil", `/settings/users-teams` leitet auf `/settings/profile` um
  (Single-User-Grenze bleibt explizit, ADR-0008).

### Added (contracts — 2026-07-10)

- **Kanonische KI-Provider-Verträge**: `ProviderConnection`, `AiModel` und
  `AiRoute` sind als secret-freie Pydantic-v2-SSoT mit strikten
  Zod-Spiegeln und JSON-Schemas verfügbar. Explizite Legacy-Adapter lesen
  `ProviderDescriptor`, `ModelEntry`, `LlmProfile` und `StageLLMRoute`, ohne
  bestehende Profile zu migrieren oder Provider-Detection zu verändern.
  Kanonische `base_url`-Werte erlauben ausschließlich öffentliche HTTP(S)-
  Basis-URLs mit Host und optionalem Pfad; Userinfo, Query und Fragment werden
  abgelehnt. Der Descriptor-Legacy-Adapter entfernt diese privaten URL-Anteile,
  markiert die Verbindung als `degraded` und verlangt Neukonfiguration.
- **Legacy-Adapter total gemacht** (Review-Findings PR #683): der
  `base_url`-Validator erzwingt jetzt auch das Feld-Pattern, wodurch
  Sanitizer und Modell-Konstruktion deckungsgleich sind; großgeschriebene
  Schemes werden beim Sanitizing normalisiert statt abgelehnt, nicht
  rettbare Hosts degradieren zu `base_url=null` statt eine
  `ValidationError` zu werfen. `llm_profile_to_canonical` saniert
  Legacy-`base_url` jetzt ebenfalls und kombiniert Degradationsgründe
  secret-frei in `status_message`.

### Changed (infra/ci — 2026-07-05)

- **Proxy-Binding und Frontend-Image-Artefakt**: Proxy bindet standardmäßig nur noch auf `127.0.0.1:8080` (via `AGORA_PROXY_BIND_HOST`/`AGORA_PROXY_PORT`-Overrides). Frontend wird als Image-Artefakt in den Proxy gebaut statt per Host-Volume gemountet; reduziert Dev-Container-Overhead bei Prod-Stack-Tests.
- **Docker-Image-CI erweitert**: Workflow läuft jetzt auf PRs (pfadgefiltert) und main (Build + Trivy); Smoke-Test und Push nur noch auf release/rc/Tags/dispatch.
- **Frontend-PR-Gate mit Unit-Tests**: Job führt jetzt auch `bun run test` (Vitest) aus — schnelle Regression-Prüfung vor Build.
- **Doku-Fixes**: README auf `bun run setup:all` und `bun run dev` (statt `npm`); Dependency-Risk-Register-Datum korrekt.

### Changed (refactor — 2026-07-05)

- **M3-Port — Unified Provider Abstraction** (PR #666, Branch `feat/m3-port`): `#590` (unified provider abstraction) + `#591` (unified provider detection) auf dem `#582`-LLM-Client-Split neu portiert. Single Source of Truth für Provider-Detection: `backend/app/llm/providers/registry.py::detect_provider(base_url, model, *, mode="http"|"oasis")` — Vokabular `ollama|cloud|openai|google|unknown` (HTTP) bzw. `google|ollama|openai` (OASIS). Schließt #590, #591, #582 und #636 (M3-Milestone-Tracker). Rest-Detection-Delegation als Folge-Issues #669/#670/#671 ausgelagert (Phase F).

### Changed (deps — 2026-07-05)

- **transformers v5.13.0** (PR #667): Upgrade auf v5 via `tool.uv.override-dependencies`, unblocked durch `sentence-transformers>=5.3.0`. Löst CVE-2026-4372, CVE-2026-1839 und PYSEC-2025-217. Schließt #124, #624, #662.

### Security (deps — 2026-07-05)

- **nltk 3.9.4 — Risk Exception** (PR #668): PYSEC-2026-597 (Path Traversal in `nltk.data.load()`) und GHSA-p4gq-832x-fm9v ohne Upstream-Fix in 3.9.x. Agora nutzt `nltk` nur transitiv (via `unstructured`/`camel-oasis`), kein direkter `nltk.data.load()`-Aufruf mit user-kontrolliertem Pfad → Risikoakzeptanz mit Allowlist-Eintrag. Tracking-Issue #672, Hardstop 2026-07-30. Source of Truth: `docs/dependency-risk-register.md`.

### Fixed (bug — 2026-06-10)

- **Projekt-Meta ging beim Ontology-Upload verloren** (Regression aus dem
  #562-Refactor): `POST /api/graph/ontology/generate` setzte
  `simulation_requirement`, `files` und `total_text_length` nur am
  In-Memory-Objekt, während `GraphBuildService.generate_ontology` das Projekt
  frisch von Platte lud und die Meta ohne diese Felder zurückschrieb. Folge:
  jeder Report-Generate und jede Simulation-Vorbereitung scheiterte mit 400
  "Missing simulation requirement description" (e2e-Smokes report-modes +
  minimal-report, CI-Run 27241443657). Fix: explizites
  `ProjectManager.save_project()` in der Route vor dem Service-Aufruf;
  Regressionstest `tests/api/test_graph_ontology_persists_project_meta.py`
  mit echter Persistenz gegen `tmp_path`.

### CI (fix — 2026-06-10)

- Ruff-Heavy-Gate (`ruff check .`) auf main wieder grün: `BLE001`-Baseline
  für `scripts/*` und `tests/*` als `per-file-ignores` (CLI-Runner und Tests
  fangen bewusst breit; Aufräumen unter Milestone M5, #638) plus ungenutzten
  `os`-Import in `tests/test_no_silent_exceptions.py` entfernt. `app/` bleibt
  vollständig BLE001-enforced (#626).

### Operations / Observability (refactor — 2026-06-09)

- Replaced all ~120 silent `except Exception: pass` blocks in `backend/app/`
  with logged equivalents (`logger.debug`/`logger.warning`) or explicit
  `# noqa: BLE001 — <reason>` comments per the Issue #583 fix policy.
  Ruff rule `BLE001` (blind exception) added to `pyproject.toml` select list
  and enforced going forward. Behaviour is unchanged — exceptions are still
  swallowed where recovery is intentional; they are now visible in logs.
  New test `tests/test_no_silent_exceptions.py` guards the policy. (#583)

### Fixed (bug — 2026-06-09)

- `llm_client._resolve_num_ctx` silently truncated unknown cloud models to 8 k
  context. Now emits a structured WARNING (exactly once per model name, deduplicated
  via `lru_cache`) when the legacy `OLLAMA_NUM_CTX`/8192 fallback fires, so
  misconfigured models surface in the log viewer instead of producing cut-off
  or incoherent output. Resolves #581.

### Fixed (deploy — 2026-05-18)

- Persona-Generation wurde nach MAI-12 + PR #519 stark verlangsamt: gunicorn
  `-k gevent --preload --workers 1` vererbte den im Master geöffneten
  Neo4j-Driver-Pool, die `os.register_at_fork`-Handler aus MAI-12 wurden unter
  gevents `os.fork`-Monkey-Patch nicht zuverlässig gefeuert, und die ersten
  DB-Writes im Worker liefen in einen `Failed to write data to connection`
  Transient-Retry-Loop (1.15 s, 2.3 s, 4.6 s pro Aufruf). Bei zehn parallelen
  Persona-LLM-Threads serialisierte sich das Persona-Batch praktisch.
- Fix: Pool-Reset jetzt aus einem expliziten `post_fork`-Hook in
  `backend/gunicorn.conf.py`. `app.extensions.reset_pools_after_fork()` ist die
  kanonische Reset-Funktion; `os.register_at_fork` bleibt als
  Defence-in-Depth-Fallback erhalten (One-Shot-Guard verhindert Stapeln bei
  wiederholten `create_app()`-Aufrufen). `RedisEventBus.reset_after_fork()`
  schliesst den geerbten Redis-Client und baut ihn im Worker neu auf —
  analog zum Neo4j-Driver. Dockerfile-CMD vereinfacht auf
  `--config /app/backend/gunicorn.conf.py`.

### Changed (chore/deps — 2026-05-17)

- Python-Floor auf 3.14 vereinheitlicht. `pyproject.toml` (`requires-python`,
  `tool.ruff.target-version`, `tool.mypy.python_version`) und alle CI-Workflows
  (`ci.yml`, `contract-gates.yml`, `cve-monitor.yml`) sind jetzt auf `3.14`.
  Vorher gemischt: pyproject `>=3.11`, Dockerfile `3.14`, CI-Matrix mit
  `3.11`-Stable + `3.14-dev`-Preview. Issue #199 (cp314-Wheel-Lag bei tiktoken)
  ist seit 2026-05-14 closed; der `tool.uv.override-dependencies`-Block bleibt
  bestehen, weil er die cp314-Bumps für tiktoken/pillow/pandas/numpy/sentence-
  transformers + den Sec-Override für `unstructured` (GHSA-Path-Traversal)
  trägt. **Breaking für lokale Dev-Setups:** `.venv` muss mit
  `uv venv --python 3.14` neu gebaut werden, sonst meckert `uv sync`.
- Neo4j-Default-Image von `neo4j:5.18-community` (Feb 2024) auf `neo4j:5.26-community`
  (Nov 2024 LTS) gebumpt. Betrifft `docker-compose.yml` (Default-Image) und
  `.env.example` (Beispiel-Override-Kommentar). Gleiche 5.x-Linie, gleicher
  Cypher-Dialect, keine Code-Anpassungen nötig. Wer `NEO4J_IMAGE` lokal pinnt,
  bleibt unangetastet.

### Added (Sub-Slice S1 — 2026-05-17)

- Report-Quality Slice 1: Evidence-Coverage-Floor (min=2) — Claims mit <2 Evidence-Items werden zur Hypothesis geroutet, Cap auf 0.59 in compute_confidence. Reviewer-Feedback report_4fe2dacd80ba. (#493)

### Fixed (Sub-Slice 05.9 — 2026-05-16)

- `backend/scripts/_sim_common.py::compute_start_hour_offset()` shiftet die
  simulierte Uhr bei kurzen Runs (`max_rounds=3` mit `minutes_per_round=60`
  durchläuft nur die Stunden 0–2) auf den meistgenutzten `active_hours`-Bucket
  aus `agent_configs`. Vorher: alle Smoke-Runs starteten um Mitternacht, kein
  Agent war wach, jede Runde meldete „0 actions, 0.0s". Verdrahtet in
  `run_parallel_simulation.py`, `run_reddit_simulation.py`,
  `run_twitter_simulation.py`. Explizite `time_config.start_hour` gewinnt
  weiter; bei Runs ≥ 24 h simulierter Zeit greift Offset nicht. 14 neue Tests
  in `backend/tests/scripts/test_sim_common_start_hour_offset.py` decken
  Explicit-Override, Long-Run-Bypass, Active-Hour-Heuristik, Modulo-24 und
  Edge-Cases ab. (Sub-Slice 05.9)

### Fixed (Sub-Slice 05.8 — 2026-05-16)

- Frontend-Zod-Spiegel zu `EvidenceItemModel.sentiment_score` (Backend hat
  das Feld seit MAI-14, der Zod-Schema fehlte aber). Live-Smoke mit
  Gemini 3 via Google API zeigte 50+ „Unrecognized key: 'sentiment_score'"-
  Mismatches im strict-Mode des Frontend-Zod, was den ganzen Report-Body
  hinter einem Schema-Banner versteckte. Jetzt: `sentiment_score:
  z.number().min(-1).max(1).optional().nullable()` in
  `EvidenceItemSchema`. Pendant zur bereits offiziellen Backend-Definition,
  Range konsistent zu `PostEvent.sentiment`. Layer-0 unverändert (kein
  Backend-Touch). (Sub-Slice 05.8)

### Fixed (Sub-Slice 05.6 — 2026-05-16)

- `GraphToolsService.interview_agents` führt jetzt einen Early-Check auf
  `SimulationRunner.check_env_alive(simulation_id)` durch, bevor LLM-Calls für
  Agent-Selection und Question-Generation ausgelöst werden. Bei toter Sim
  spart das pro fehlgeschlagenem Tool-Aufruf 30-60 s LLM-Zeit + Tokens.
  Wichtiger noch: die drei Soft-Fail-`result.summary`-Strings verleiten den
  ReACT-Loop nicht mehr zu Retry-Schleifen. Vorher endete die Summary mit
  *"Please ensure the OASIS environment is running"* — Live-Smoke zeigte, dass
  das LLM das als „später nochmal versuchen" las und Section-Loops bis zur
  `maximum iterations count`-Force-Generate-Grenze trieb. Jetzt: klarer
  Terminal-Hint `TERMINALLY UNAVAILABLE ... Do NOT call interview_agents
  again. Use insight_forge, panorama_search, or quick_search instead.`
  (Sub-Slice 05.6)

### Fixed (Sub-Slice 05.5 — 2026-05-16)

- `LLMClient.__init__` resolved `num_ctx` jetzt modellabhängig statt
  hardcoded `OLLAMA_NUM_CTX=8192`. Cloud-Modelle wie `gemini-3-pro:cloud`
  (1 M), `qwen3-coder-next:cloud` (256 k), `gpt-oss:120b` (128 k) und
  `nemotron-3-nano:30b` (128 k) bekommen ab jetzt ihren echten
  Context-Window. Helper `_resolve_num_ctx()` mit Override-Hierarchie:
  (1) `provider_options.num_ctx`, (2) `LLM_MODEL_CONTEXT_LIMITS_JSON`
  env-Map, (3) Heuristik-Tabelle, (4) `LLM_CONTEXT_LIMIT` env,
  (5) Legacy-Fallback `OLLAMA_NUM_CTX`. Tabelle synced mit
  `backend/scripts/agent_tools.py::_MODEL_CONTEXT_HEURISTICS` (TODO:
  später in shared module extrahieren, heute Zirkular-Import-Sperre).
  Wirkt automatisch auf `chat()`, `describe_image()`, `_chat_with_tools()`,
  `_ollama_chat_with_schema()` — alle vier setzen `extra_body.options.num_ctx`
  aus `self._num_ctx`. (Sub-Slice 05.5)

### Fixed (Sub-Slice 05.4 — 2026-05-16)

- NER-Extraktor (`backend/app/storage/ner_extractor.py`) auf strict-Pydantic-Schema
  umgestellt: `NerEntity` / `NerRelation` / `NerExtractionResult` werden via
  `chat_json(schema=NerExtractionResult)` an den nativen Ollama-`/api/chat::format`-
  Pfad aus 05.1/05.3 durchgereicht. Vorher rief NER `chat_json` ohne Schema und
  bekam unter `json_object`-Mode oft `{"entities": [...], "relations": []}` —
  Relations-Ratio im Live-Smoke 10/73 (~13 %). Strict-Schema zwingt das Modell,
  beide Listen tatsächlich zu füllen. `max_tokens` von 4096 auf 8192 erhöht —
  adressiert den `finish=length`-Truncation-Bug, der im Smoke zu hartem
  Datenverlust auf Chunk 37/48 führte (Repair-Mechanismus scheiterte, `len=0`).
  `_validate_and_clean` bleibt unverändert (semantische Ontology-Validierung +
  Dedup + auto-create-Entity-for-Relation). (Sub-Slice 05.4)

### Fixed (Sub-Slice 05.3 — 2026-05-16)

- Ollama-Cloud-Support für den Native-Schema-Pfad aus 05.1. Zwei Bugs:
  (a) `_is_ollama()` prüfte nur Port `11434` und erkannte `ollama.com` nicht
  → Cloud-Provider fielen unbemerkt auf den OpenAI-Wrapper-Pfad zurück und
  verloren die Schema-Garantie. Jetzt matcht die Heuristik beide Hosts
  case-insensitiv. (b) `_ollama_chat_with_schema` sendete keinen
  `Authorization: Bearer <api_key>`-Header → Cloud-Calls hätten 401
  bekommen. Jetzt wird der Header gesetzt, sobald `api_key` ≠ Dummy
  `"ollama"`. Lokales Ollama (Dummy-Key) bleibt headerlos. (Sub-Slice 05.3)

### Fixed (Sub-Slice 05.2 — 2026-05-16)

- `LLMClient.__init__` respektiert jetzt `OLLAMA_THINKING` aus der env als
  Override für `reasoning_effort`. Vorher wurde die Env-Variable nur in
  `backend/scripts/run_*_simulation.py` (OASIS-Subprozesse) gelesen, im
  Flask-Backend aber ignoriert — `_think` ergab sich ausschließlich aus
  `reasoning_effort != "none"`. Folge: thinking-Modelle (qwen3, gpt-oss)
  lieferten bei schemalosen `chat_json`-Calls (Persona-Generierung)
  manchmal leere `content`-Outputs → `JSON parsing failed: Expecting
  value: line 1 column 1 (char 0)`. Adressiert die Honcho-Pflicht-Env
  `OLLAMA_THINKING=false` für Agent-Workflows. (Sub-Slice 05.2)

### Added (Sub-Slice 05.1 — 2026-05-16)

- Native Ollama `/api/chat`-Pfad in `LLMClient.chat_json` fuer Schema-Calls. Wenn
  `_is_ollama()` und `schema=<PydanticClass>` → direkter httpx-POST mit
  `format=<flattened_schema>` statt OpenAI-Kompat-Wrapper. Garantiert
  Schema-Enforcement laut Ollama-Doku, statt schweigendem Schema-Drop.
  Fallback auf bestehenden OpenAI-SDK-Pfad bei Netz-/Schema-Fehler. (Sub-Slice 05.1)

### Changed (Repo-Hygiene — 2026-05-16)

- `chore(docs): docu/ → docs/ — Worklogs nach docs/archive/worklogs/, Themen-Doku unter docs/, Detail-Runbooks nach docs/runbooks/.`
- `chore(root): Ad-hoc-Dateien aus dem Repo-Root nach docs/archive/root-junk/ verschoben (REFACTORING_PLAN, SECURITY_REVIEW, agora_bewertung_komplett, …).`
- `docs(readme): README.md auf 339 → 147 Zeilen gekürzt, einsprachig DE, Links auf docs/ aktualisiert.`
- `docs(agents): AGENTS.md auf 508 → 143 Zeilen, Detail-Runbooks extrahiert nach docs/runbooks/{tool-pflicht,pr-workflow,worktree-strategy,subagent-routing,architecture-layers}.md.`
- `docs(claude): CLAUDE.md auf 456 → 107 Zeilen entmistet, verweist auf AGENTS.md und Runbooks statt Inhalte zu duplizieren.`
- `ci(docker-image): pull_request-Trigger entfernt — Prod-Proxy-Smoke nur noch auf main, release/**, rc/**, Tags und workflow_dispatch (spart ~30 min pro PR).`
- `ci(contract-gates): pull_request-Trigger hinzugefügt — Schema-/Voice-/Komplexitäts-Drift wird vor Merge gefangen statt erst auf main.`

### Fixed (Smoke-Fix Welle 2 — 2026-05-15)

- `fix(report-agent): Ollama-Outline-Robustness — max_tokens=16384, force_no_thinking=True, Retry-Loop (#2)`
- `fix(auth): Ticket-Refresh ohne bestehenden Ticket via Cookie/API-Key (#4)`
- `fix(api): Provider-Override propagiert DB-Key automatisch via SecretResolver (#3, #17)`
- `fix(ui): Sidebar-Stubs disabled+Tooltip, Persona-Slider min=10, Step4-Modell-Sync (#5, #6, #7)`
- `feat(i18n): Locale-Parity + ontology_generate + graph.edgeLabels.* (#8, #9, #10)`

### Added (Smoke-Fix Welle 2)

- test(backend): 12 neue Unit-Tests (Ollama-Outline, Auth-Refresh, SecretResolver, Modell-Store)
- test(frontend): 13 neue Tests (Sidebar-Stubs, Persona-Quota-Warning, Report-Model-Store, Locale-Coverage-Linter)

### Changed
- ci(coverage): Coverage-Schwellen auf Step 2 angehoben: Backend 55 → 60 %, Frontend 26 → 28 %. Backend-Istwert durch neue Tests für `file_parser.py` auf 66 % gesteigert. (Sub-Slice M11.2/M11.3 Step 2).

### Added
- test(backend): Unit-Tests für `app/utils/file_parser.py` hinzugefügt (`tests/utils/test_file_parser.py`). Deckt Text-Extraktion (TXT/MD) mit Encoding-Fallback und Text-Chunking ab.

- MAI-12 · Fork-safe Neo4j/Redis-Pools via `os.register_at_fork`; gunicorn `--preload` aktiviert — eliminiert doppelte Init-Logs, ~40 % schnellerer Worker-Start.
- MAI-06 · ReportV3 als Single Source of Truth, full_report.md nur noch on-demand-Render.
- MAI-11 · prod-proxy-smoke nur auf release/rc/Tags/main automatisch; Feature-PRs opt-in via needs-prod-smoke-Label.
- MAI-01 · P4.4 Mode-Smokes als CI-Job verdrahtet (e2e-smokes.yml::report-modes-smoke).
- MAI-04 · Schema-Drift-Gate (dump_schemas --check) als CI-Pflichtschritt.
- MAI-13 · mistune + pygments Lockfile-Bump (Dependabot #323 + #326 closed).
- MAI-16 · sync-status.sh --check als CI-Pflicht-Gate für STATUS.md.
- MAI-14 · Confidence-Contradiction-Penalty (Std-Dev>0.6 ODER Range>0.6 ⇒ -0.2).
- MAI-03 · ReportV3.hypotheses[] als dedizierter Slot, getrennt von data_gaps[].
- MAI-08 · `report_prompts.py` zu Paket aufgesplittet.
- MAI-17 · radon-Komplexitäts-Gate (rank D+ blockiert, allowlist-basiert).

### Documentation
- Repo-Reorg (Review Punkt 1): `BIG_PLAN.md` entfernt, `docs/ROADMAP.md` → `ROADMAP.md` (Root) mit „Now/Next/Later"-Struktur und verbindlicher Trennung (ROADMAP = strategisch, Issues = Tasks, CHANGELOG = shipped, STATUS = generiert, PLAN = operativ); neue Verzeichnisstruktur `docs/plans/{active,archive}/`, `docs/worklogs/archive/`, `docs/audits/`; Observability-Slice-Pläne nach `docs/plans/active/` verschoben; `docs/.local/` vollständig aus dem Git-Index entfernt (bleibt lokal, gitignored); STATUS-Drift-Check (`scripts/sync-status.sh --check`) als CI-Job in `contract-gates.yml` reaktiviert.

## [1.0.0] - 2026-05-11

Output-Vertrag-Release. Alle 14 PR-Slices der v1.0-Roadmap aus [PLAN.md](PLAN.md) sind durch.
Schwerpunkt: Pflichtabschnitt-Validator, Evidence-Härtung, ReportV3-Persistenz + Markdown-Renderer,
drei Vertrauensmodi, Export-Vollständigkeit (CSV/ZIP), End-to-End-Smokes. Siehe ausführliche
Release Notes (`docs/2026-05-11-v1.0.0-release-notes.md`).

### Added
- test(e2e): Playwright-Smokes für die drei Report-Modi strict/balanced/explorative (Sub-Slice P4.4, Refs PLAN.md §5.4). `frontend/tests/e2e/report-modes.spec.ts` (185 LOC) triggert pro Modus einen Report via `?mode=`-Query-Param + `force_regenerate=true` und prüft (1) Mode-Banner-Prefix `**Report-Modus:**` plus Mode-Name im Markdown-Export, (2) `report_mode`-Feld im JSON-Export, (3) Default ohne Mode-Param == `balanced`. `helpers/report.ts::triggerReport` um optionale `mode`+`forceRegenerate`-Optionen erweitert. `test.describe.serial`, damit `force_regenerate` nicht in parallele Status-Files schreibt. Schließt v1.0-DoD Phase 4.
- feat(report): Frontend Mode-Selector für strict/balanced/explorative — localStorage-Persistenz, i18n, Backend-Übergabe via POST /api/report/generate (PLAN.md §5.1 Frontend-Teil).
- feat(report): Report-Modi strict/balanced/explorative — Mode-abhängige Claim-Filterung, Quote-Validator-Härte, Markdown-Banner (PLAN.md §5.1). `_resolve_report_mode()` in `api/report.py` liest `?mode=`-Query-Param (400 bei Unknown). `build_report_v3` + `save_report` in `manager.py` nehmen `report_mode: ReportMode`; strict droppt Low-confidence-Claims. `workflow.generate_report` überspringt Quote-Anchor-Validator in explorative, escaliert auf `logger.error` in strict. `markdown_renderer.render_report_v3` rendert Mode-Banner vor erstem Section-Header. Zod-Spiegel `reportV3Contract.ts` um `ReportModeSchema` + Default ergänzt. 25 neue Backend-Tests, 3 neue Frontend-Tests.
- feat(report): echte Persona/Segment/FrictionPoint/TrustSignal-Aggregation in `migrate_v2_to_v3` (P3.1-Followup, Refs PLAN.md §4.1). Personas aus `reddit_profiles` via `artifact_store` (optionaler Parameter), Segments per Gruppen-Aggregation nach Segment-Tag, FrictionPoints/TrustSignals aus Section-Claims per Keyword-Matching auf Section-Titel ("Reibungspunkt", "Vertrauenssignal"). Fallback: DataGap-Marker bleibt wenn kein Store/keine Profiles. 15 neue Tests in `test_evidence_migrations_aggregation.py`.
- feat(report): ReportV3 als zusätzliche Persistenz-Schicht (Sub-Slice P3.1, Refs PLAN.md §4.1). `migrate_v2_to_v3()` in `evidence_migrations.py` wandelt v2-Report-dicts in `ReportV3`-valide Struktur. `write_report_v3()` + `read_report_v3()` in `storage.py` atomar. `ReportManager.save_report()` schreibt `report-v3.json` additiv neben `meta.json` bei `COMPLETED`-Reports. `CURRENT_SCHEMA_VERSION` bleibt 2 (Evidence-Map-Version). 6 neue Contract-Tests.
- feat(report): Evidence-Anker als Pflicht für medium/high/verified Claims (Sub-Slice P2.1, Refs PLAN.md §3.1). `ReportClaimModel.non_low_claims_need_evidence` verwirft Claims ohne Evidence-Anker. `_finalize_section_claims` routet medium/high/verified-Orphans in `data_gaps[]` statt `claims[]`. `migrate_legacy_claims_to_anchored()` in `evidence_migrations.py` überführt bestehende `evidence-map.json`-Dateien beim Reload. 10 neue Tests in `tests/eval/test_evidence_routing.py`.
- feat(report): ZIP-Bundle-Export via `GET /api/report/<id>/export?format=zip` (Sub-Slice P4.3, Refs PLAN.md §5.3). ZIP wird serverseitig mit Python-stdlib `zipfile` + `io.BytesIO` gebaut — kein jszip-Install nötig. Enthält: `report-v3.md`, `report-v3.json`, `evidence-map.json`, `personas.csv`, `segments.csv`, `claims.csv` im Top-Level-Ordner `agora-report-<id>/`. Helper `_build_zip_bundle()` in `backend/app/api/report.py`. Frontend: `fetchReportBundle()` in `api/report.ts`, `downloadAllBundle()` in `useReportExports.ts`. TODO(jszip)-Marker aus `useReportExports.ts:175` entfernt und durch Hinweis auf serverseitiges ZIP ersetzt.
- feat(report): CSV-Export für Personas/Segmente/Claims + Bundle (Sub-Slice P4.2, Refs PLAN.md §5.2). Neuer Endpoint `GET /api/report/<id>/export?format=csv&table=personas|segments|claims` (RFC-4180, `text/csv; charset=utf-8`). Helper `backend/app/services/report_agent/csv_export.py` (pure Funktionen, keine Flask-Abhängigkeit). Frontend: `fetchReportCsv()` in `api/report.ts`, `downloadCsv()` + `downloadCsvBundle()` in `useReportExports.ts`.
- feat(report-agent): Pflichtabschnitt-Validator erzwungen (Sub-Slice P1.1). `validate_required_sections()` in `contract_validator.py` prüft case-insensitiv und whitespace-tolerant. `ReportOutlineModel` wirft `ValidationError` bei fehlenden Default-Sections. `workflow.generate_report()` blockt nach `plan_outline()` und setzt `ReportStatus.INCOMPLETE` + `missing_sections[]`, ohne `report.md` zu schreiben. `GET /api/report/<id>` liefert `status` und `missing_sections[]` strukturiert aus.

### Changed
- refactor(services): `os.getenv` via `settings_layer` für AGORA_PARALLEL_PERSONA_COUNT, AGORA_PERSONA_DETAIL_LEVEL, ONTOLOGY_MAX_TOKENS — schließt Issue #212 (Refs #212).
- docs(p3.4): Print/PDF-Export ist offiziell als Browser-Print dokumentiert (P3.4). Button-Label in Step4Report.vue auf i18n-Key `step4.view.printPdf` migriert. Abschnitt „Report-Export & PDF" in `deployment-prod-like.md` ergänzt; Mini-Abschnitt in `README.md` (DE + EN). Kein server-seitiges PDF, keine Headless-Chrome-Pipeline.
- chore(status): STATUS.md test-count nach P1.1 syncen (1722 → 1725 Backend Tests collected).
- **Layer 2 / Report Agent:** Evidence-Gating-Prompt-Block in `SECTION_SYSTEM_PROMPT_TEMPLATE` eingeführt (Sub-Slice M11.7a). LLM klassifiziert Claims jetzt nach vier Provenance-Stufen (hypothesis, seed_only, agent_grounded, cross_stakeholder) mit Confidence-Gating und Hedge-Word-Regeln. Forward-kompatibel zu `EvidenceSourceKind` Enum (Slice B).

### Fixed
- fix(sim): OpenAI GPT-5/o-Series-Hotfix — `model_config_dict` mappt jetzt provider-aware auf `max_completion_tokens` (für `gpt-5*`, `o1*`, `o3*`, `o4*`) statt `max_tokens`. OpenAI rejected `max_tokens` für GPT-5-Familie und Reasoning-Modelle mit 400 `Unsupported parameter`, wodurch jeder Agent-Tick in `run_parallel_simulation.py`/`run_reddit_simulation.py`/`run_twitter_simulation.py` abbrach und die Simulation null Reaktionen produzierte. Neuer Helper `build_camel_completion_params()` + `uses_max_completion_tokens()` in `_sim_common.py` (32 Tests). Sanity-Log in `agent_tools.py` liest beide Keys. Spiegelpattern zu `build_camel_extra_body()` (33eb10e), das den Token-Key-Mismatch nicht abdeckte.
- fix(event-bus): M11.4-Followup-5 — FilePollingEventBus tmp-File-Race in `LocalFilesystemArtifactStore.list_artifacts()` behoben. `write_json_atomic` erzeugt `.tmp-json-XXXXXX.json` in `ipc_commands/`; der Polling-Loop übergab diese dot-prefixten Einträge an `_resolve_relative_path`, das mit `ValueError` abbrach und den gesamten Poll-Tick kippte. Fix: Filter analog `run_registry.py:281` vor dem `_reverse_lookup`-Aufruf. Test-Timeout `test_request_response_correlation` 10.0 s → 5.0 s zurückgedreht (Workaround-Historie: 2.0 → 5.0 → 10.0 → 5.0). Neuer Regressionstest `test_tmp_files_do_not_disrupt_file_polling`.
- fix(contracts): M11.4b-Followup-4 — Zod-Spiegel-Drift `ReportOutlineSchema.sections` `.max(5)` → `.max(15)`, `.min(2)` → `.min(1)`. Backend-Pydantic wurde in M11.4b-Followup-2 auf `max_length=15` angehoben, Zod-Mirror nicht synchronisiert. Folge: Stub liefert 11 Pflichtabschnitte → `ReportOutlineSchema.parse()` warf → `schemaError` gesetzt → `reportOutline` blieb `null` → `ol.outline` nie gerendert → E2E-Minimalreport-Smoke timeout. Neuer Drift-Guard in `reportContract.spec.ts` verhindert künftige Regression.
- fix(e2e): M11.4b-Followup-3 — Playwright Test-Total-Timeout + `waitUntil`-Anti-Pattern behoben. `test.setTimeout(180_000)` in `upload-graph.spec.ts` und `test.setTimeout(300_000)` in `minimal-report.spec.ts` (targeted, kein Global-Bump in `playwright.config.ts`). `waitUntil: 'networkidle'` in allen drei E2E-Specs durch `'domcontentloaded'` ersetzt — SPAs mit Pinia-State-Polling erreichen `networkidle` (>=500 ms ohne Request) strukturell nie. `health.spec.ts` Test 3 ebenfalls korrigiert (war seit M11.4a per Timing-Glück grün). Sub-Slice M11.4b-Followup-3.
- fix(e2e-stub): M11.4b-Followup-2 — Embedding-Service-Stub + Outline-Validation-Fix. `EmbeddingService.embed()` / `embed_batch()` / `health_check()` liefern im Stub-Modus (`AGORA_E2E_LLM_MODE=stub`) deterministischen, L2-normierten Vector (`Config.VECTOR_DIM`) ohne Ollama-Netzwerkaufruf. `ReportOutlineModel.sections` `max_length=5 → 15` (Schema-Drift zwischen M11.8a-Followup Prompt-Cap-Entfernung und ungeändertem Contract — ließ 11 Pflichtabschnitte nicht validieren). E2E-Timeout `page.goto` explizit auf 60 s. 10 neue Backend-Tests. Adressiert CI-Run 25622221164 Symptome A+B+C.
- fix(e2e): Stub-Snapshot fehlte im prod-Image — `Dockerfile` kopiert `backend/tests/eval/snapshots` ins prod-Stage, `llm_e2e_stub._eleven_required_sections()` wirft kein `ImportError` mehr sondern fällt auf eingebettete Konstante zurück. Root-Cause für 500 in `Upload+Graph`/`Minimalreport`-Smokes (Runs 25621119693/25621557226). Container-Logs werden ab sofort von `global-teardown.ts` in CI gedumpt. Sub-Slice M11.4b-Followup-1.
- fix(e2e): Health-Smoke Test 4 prüft `body.backend.auth_mode` statt `body.auth_mode` — `/api/status` liefert die Felder nested unter `backend` im `json_success`-Envelope (siehe `backend/app/api/status.py::_get_backend_status`). Test 4 war seit M11.4a (#338) konstant rot auf main.
- fix(e2e): Health-Smoke Test 3 wartet auf das erste Kind-Element von `#app` (statt nur auf den leeren Wrapper-Div) und nutzt `waitUntil:'networkidle'` + 15s Timeout. `#app` ohne intrinsische Höhe fiel in CI-Headless durch `toBeVisible()`, bevor Vue gemountet hatte.
- fix(status): STATUS.md Drift-Check → Backend-Tests 1619 → 1683 (nach M11.8c/d/e), Frontend Specs 44 → 45 gesynced via `scripts/sync-status.sh`. Blockierte `contract-gates::status-sync-drift` auf PRs gegen main.
- fix(e2e): test_event_bus.test_request_response_correlation Timeout 2.0 s → 5.0 s (M11.4a-Followup #8) — CI-Failure 25595884772 zeigte sporadische TimeoutError auf Shared-Filesystem-Runnern; lokale Reproduktion stabil, keine echte Race-Condition. 5.0 s ergibt ~100 Poll-Zyklen statt 40.
- fix(e2e): scripts/e2e-up.sh legt `backend/uploads/{run_registry,simulations}` mit Container-User-Permissions an (chown 1000:1000 als root, chmod 0777 als Dev-User), bevor Compose-Stack startet. Adressiert PermissionError aus CI-Failure 25595884785 (RunRegistry konnte beim Boot nicht in Bind-Mount-Source schreiben, weil Docker-Daemon das Verzeichnis als root erzeugt hatte). M11.4a-Followup #8.

### Documentation
- docs(plan): F8 Frontend-Hotspot-Status auf grün gesynced. `Step2EnvSetup.vue` 1804→667 LOC (-63 %), `Step4Report.vue` 1287→797 LOC (-38 %), beide unter Schwelle. Issue #203 vorbereitet zum Schließen.

### Tooling
- ci(complexity): M11.5a — Cyclomatic-Complexity-Gate (radon). `radon>=6.0.1` als Dev-Dep in beiden Listen (`[project.optional-dependencies] dev` + `[dependency-groups] dev`). `scripts/check_complexity.sh` misst alle D/E/F-Klassen-Funktionen (cc >= 21) in `backend/app/`; neue Einträge außerhalb `backend/radon-allowlist.txt` → Exit 1. Bestands-Allow-List: 27 Funktionen (1 × F, 4 × E, 22 × D). Neuer CI-Job `contract-gates.yml::complexity-gate` (timeout-minutes: 5).
- ci(status): `scripts/sync-status.sh` Marker-basiert (HTML-Comment-Marker `BEGIN_AUTOGEN_VERSIONS`/`BEGIN_AUTOGEN_TESTS`); ersetzt nur dynamische Versions- und Test-Count-Tabellen, lässt Layer-Status, Coverage-Sektion, Aktualisierungs-Protokoll und Aktuelles Milestone unangetastet. Neuer CI-Job `contract-gates.yml::status-sync-drift` blockiert auf `--check`.

### Documentation
- docs(m11): Phase-7-Schnittanalyse für Playwright-Smokes (`docs/2026-05-09-m11-phase7-playwright-smokes-cut-analysis.md`). Verifiziert Endpoints, Auth-Flow, Fixture-Quelle und CI-Strategie gegen den realen Code-Stand 2d42962 (post-M11.8b). Cut in 5 Sub-Slices: M11.4a Setup+Health, M11.4b-pre LLM-Stub-Modus, M11.4b Upload+Graph, M11.4c Minimalreport. Reuse von `scripts/verify-deploy.sh`-Compose-Stack und PR-Trigger-Strategie analog `docker-image.yml::prod-proxy-smoke` (kein PR-Spam, paths-Filter + nightly).
- docs(plan): M11.8 Output-Vertrag-Hardening-Block in PLAN.md aufgenommen (5 Sub-Slices a–e). Externer Bewertungs-Score 5,8/10 als `docs/2026-05-09-output-vertrag-bewertung-evidence-quality.md` eingecheckt. Root-Cause: `report_prompts.py:53-57` deckelt LLM auf 2–5 Sections; `report_agent/schemas.py` hat nur 10 LOC ohne Persona/Claim/Segment-DTOs. Reihenfolge: M11.8 vor Phase 7 Playwright-Smokes (sonst E2E auf falschem Output-Vertrag).
- docs(tools): code-review-graph als MCP-First-Stop in CLAUDE.md/AGENTS.md verankert. Tool-Routing-Tabelle für Code-Exploration, Code-Review, Impact-Analysis und Refactor-Planung; `rg`/`grep`/`Read` werden zum Fallback für Nicht-Code-Files (Bash, yml, Markdown, Config). Graph-Updates automatisch via Hooks; Workflow zeigt Rich-Snippets mit `get_review_context` statt komplette Files zu lesen.
- docs(plan): sync M11-Status auf 2026-05-08 — `AGENTS.md`/`CLAUDE.md`/`PLAN.md`/`STATUS.md` an realen Code-Stand angeglichen (M11 Phase 1–5b abgeschlossen, M11.2/M11.3 Coverage-Gates aktiv, ADR-0001 Accepted, Layer 9–10 grün).

### Added
- Pflichtabschnitt-Validator (`contract_validator.validate_required_sections`) blockt unvollständige Outlines mit `ReportStatus.incomplete` und strukturiertem `missing_sections[]` (Sub-Slice P1.1, PLAN.md §2.1).
- feat(contracts): M11.7c — `ReportSectionModel.hypotheses[]` als separater Slot fuer Hypothesen ohne Evidence. Backend-Pydantic und Frontend-Zod spiegeln `ReportSectionHypothesisModel` (`hypothesis_id`, `hypothesis_text`, `rationale`, `suggested_evidence`), `ReportEvidencePanel` rendert Hypothesen getrennt von belegten Claims, und neue Contract-/Vitest-Guards pinnen das Verhalten.
- `EvidenceSourceKind`-Enum + `EvidenceItemModel.source_kind` + Cross-Stakeholder/Inferred-Validators (ADR-0002 Anker 3–5, Sub-Slice M11.7b).
- feat(e2e): M11.4c — Minimalreport-Smoke: `frontend/tests/e2e/minimal-report.spec.ts` testet Graph-Setup → Simulation anlegen → `POST /api/report/generate` → Polling bis `completed` → alle 11 Section-Header aus `output-contract-required-sections.txt` als `span.outline-title` sichtbar. Neuer Helper `helpers/report.ts` (`triggerReport`, `pollReportReady`). CI-Job `minimal-report-smoke` in `e2e-smokes.yml` (timeout-minutes: 25). Stub-Erweiterung: `chat_json(PlanResponse)` → `_stub_plan_response()` liefert alle 11 Sections; `chat()` → `e2e_stub_chat_response()` liefert deterministischen ReACT-Loop (3 Tool-Calls + Final Answer).
- feat(e2e): M11.4b — Upload+Graph-Smoke: `frontend/tests/e2e/upload-graph.spec.ts` testet Markdown-Upload → `POST /api/graph/ontology/generate` → `POST /api/graph/build` → Task-Polling bis `completed` → GraphPanel sichtbar im UI. Neue Helpers `helpers/upload.ts` + `helpers/graph.ts`. CI-Job `upload-graph-smoke` in `e2e-smokes.yml` mit `AGORA_E2E_LLM_MODE=stub` (deterministisch ohne Ollama).
- feat(e2e-stub): M11.4b-pre — Deterministischer LLM-Stub-Modus: `llm_client.chat_json` gibt bei `AGORA_E2E_LLM_MODE=stub` ein valides ReportV3-Objekt zurück ohne LLM-Call; Stub-Pfad liegt vor Cache/Retry/Metriken und ist ohne Env-Var vollständig inaktiv.
- feat(report): simulated_quote XML-Tag als Output-Pflicht + validate_quote_anchors-Validator mit Repair-Retry-Hook in workflow (Sub-Slice M11.8e, Refs PLAN.md PR 10). `SECTION_SYSTEM_PROMPT_TEMPLATE` schreibt `<simulated_quote persona_id="..." seed_anchor="...">` für jedes Persona-Zitat vor. `validate_quote_anchors()` in `evidence.py` prüft Bindung an EvidenceMap (`source_id_anchor`) und Persona-Plan; `seed_doc:`-Prefix ist opaque OK. `generate_report()` in `workflow.py` triggert bei quote-relevanten Sections einmaligen Repair-Retry; bei persistentem Fehler: `section.metadata["quote_validation_failed"] = True`. 13 neue Tests in `tests/services/test_report_agent_quote_anchors.py` + `test_report_agent_workflow_quote_validation.py`.
- feat(report): chat_json strict-json_schema-Mode mit ReportV3-DTO-Injection in report_agent/planning + workflow (Sub-Slice M11.8d, Refs PLAN.md PR 9). `PlanResponse`/`PlanSection`-DTOs in `schemas.py` erzwingen Outline-Struktur. `generate_section_metadata()` in `workflow.py` extrahiert strukturierte Metadaten via `_section_schema_for()` mit dem passenden Pflichtabschnitt-DTO. 34 neue Tests in `tests/services/test_report_agent_strict_schema.py`.
- feat(contracts): M11.8c: ReportV3-Contract mit 11 Pflichtabschnitt-DTOs (Persona, Segment, Claim, Multiplier, FrictionPoint, TrustSignal, ChangeRecommendation, ProjectImpact, PositioningVariant, ContentIdea, DataGap) inkl. Pydantic-`extra=forbid`, Zod-Spiegel und Schema-Dump. Re-Export über `app.contracts` und `app.services.report_agent.schemas`. 17 Backend-Contract-Tests + 9 Frontend-Vitest-Tests. Vorbereitung M11.8d (Strict-Schema-Forced-Output).
- test(e2e): Playwright + Health-Smoke (M11.4a). Drei API-Probes (`/healthz`, `/health`, `/api/status`) plus SPA-Mount-Smoke. Container-Lifecycle über `scripts/e2e-up.sh` + `scripts/e2e-down.sh` in Playwright-`globalSetup`/`globalTeardown` (kein `webServer`-Hook). Neuer CI-Workflow `e2e-smokes.yml` mit paths-Filter, `workflow_dispatch` und nightly schedule. Auth via localStorage + Bearer-Header, NICHT `VITE_AGORA_TOKEN` (Bundle-Token-Gate Phase 1 bleibt hart).
- test(report): Output-Contract-Snapshot pinnt DEFAULT_REPORT_SECTIONS gegen `tests/eval/snapshots/output-contract-required-sections.txt` (11 Zeilen, in Reihenfolge). Neue Konstante `MIN_PERSONA_TABLE_ROWS=50` in `report_agent/contract_constants.py` macht das Mengengerüst aus der externen Bewertung (§6.1) maschinenprüfbar. Drift in beiden Werten erfordert bewussten Sub-Slice mit Bewertungs-Begründung. M11.8b.
- docs(m11): add `graph_tools.py` Phase-5b cut analysis (Refs F7)
- **M11 Phase 5 Vorbereitung:** Schnittanalyse für `backend/app/services/simulation_runner.py` (1904 LOC) unter `docs/2026-05-07-m11-phase5-simulation-runner-cut-analysis.md`05-07-m11-phase5-simulation-runner-cut-analysis.md). Dokumentiert Verantwortlichkeiten, externe Call-Sites, Test-Coverage und fünf Extraktionskandidaten mit empfohlener PR-Reihenfolge (read-only Doku, kein Code-Edit). Refs F7.

### Changed
- ci(coverage): Coverage-Schwellen Backend 53 → 55 %, Frontend 24 → 26 % vorgezogen (war 2026-06-04 geplant; Ist-Werte 2026-05-10: Backend 61.41 %, Frontend branches 39.56 % / statements 50.46 % / functions 38.59 % / lines 52.50 % decken beide Schwellen). Nächste Anhebung: 2026-06-10 → Backend 57 %, Frontend 28 %.
- feat(report): Pflichtabschnitt-Liste über `{required_sections}`-Variable im PLAN-Prompt; harter Section-Cap (Min 2 / Max 5) raus aus `report_prompts.PLAN_SYSTEM_PROMPT_TEMPLATE`. Default `DEFAULT_REPORT_SECTIONS` enthält die 11 DACH-Report-Standardabschnitte (Executive Summary bis Datenlücken). Adressiert externen Bewertungs-Befund 5,8/10 zur Prompt-Erfüllung. M11.8a Quick-Win.
- refactor(graph): extract `insight_forge_tool` (LLM-gestuetzte Retrieval-Pipeline) from `graph_tools.py` to `app.services.graph.insight_forge_tool` (Refs F7, M11 Phase 5b PR 3)
- refactor(graph): extract `graph_reader` (10 Storage-Reader-Methoden) from `graph_tools.py` to `app.services.graph.graph_reader` (Refs F7, M11 Phase 5b PR 2)
- refactor(graph): extract `graph_dtos` (7 Dataclasses) from `graph_tools.py` to `app.services.graph.graph_dtos` — Wording-Audit auf neuen Pfad erweitert (Refs F7, M11 Phase 5b PR 1)
- refactor(sim): extract `process_manager` (start/stop/cleanup/register_cleanup, _compute_oasis_db_path, _inject_oasis_db_env) from `SimulationRunner` to `app.services.sim.process_manager` — schließt M11 Phase 5 (Refs F7, M11 Phase 5 PR 5)
- refactor(sim): extract `interview_client` (8 IPC-/Interview-Methoden) from `SimulationRunner` to `app.services.sim.interview_client` (Refs F7, M11 Phase 5 PR 4)
- refactor(sim): extract `monitor_thread` (`_monitor_simulation`, `get_timeline`, `get_agent_stats`) from `SimulationRunner` to `app.services.sim.monitor` (Refs F7, M11 Phase 5 PR 3)
- **M11 Phase 5 PR 2:** `action_log_reader` aus `backend/app/services/simulation_runner.py` extrahiert. Neue Datei `backend/app/services/sim/action_log_reader.py` mit Module-Funktionen `read_action_log_chunk`, `check_all_platforms_completed`, `read_actions_from_file`, `get_all_actions`, `get_actions`. `simulation_runner.py` behält die fünf Klassen-Methoden als Wrapper, damit Monkeypatch-Stubs (`setattr(sr.SimulationRunner, "get_all_actions", …)`) in `test_compare_service.py`, `test_simulation_metrics_export.py`, `test_report_manager.py` weiter laufen. Kein Verhaltens-Diff. Refs F7.
- **M11 Phase 5 PR 1:** `run_state_store` aus `backend/app/services/simulation_runner.py` extrahiert. Neue Datei `backend/app/services/sim/run_state_store.py` enthält `RunnerStatus`, `AgentAction`, `RoundSummary`, `SimulationRunState` plus Module-Funktionen `load_run_state`, `save_run_state`, `read_console_log`, `cleanup_run_logs`. `simulation_runner.py` re-exportiert die Klassen für Backward-Compat; alle bestehenden Imports bleiben grün. Kein Verhaltens-Diff. Refs F7, `docs/2026-05-07-m11-phase5-simulation-runner-cut-analysis.md`05-07-m11-phase5-simulation-runner-cut-analysis.md).
- **Container Runtime Hardening:** `Dockerfile` trennt `frontend-build`, `backend-build` und finalen `prod`-Runtime-Stage. Das finale Prod-Image basiert auf `python:3.11-slim`, enthaelt kein Node/npm/curl mehr, installiert Backend-Dependencies via `uv sync --frozen --no-dev` aus `uv.lock`, nutzt einen Python-basierten Healthcheck und kopiert nur `.venv`, Backend-App/Skripte und `frontend/dist`. `docker-compose.prod.yml` setzt fuer `agora` jetzt `read_only: true` mit expliziten tmpfs-Mounts fuer Runtime-Schreibpfade. Image-Groesse lokal: 747 MB -> 320 MB (-427 MB, -57 %).
- **CI Static-Analysis-Gates:** `ci.yml` blockiert jetzt explizit auf `uv run mypy app` im Backend und `npm run typecheck` (`vue-tsc --noEmit`) im Frontend. Backend-mypy startet mit strengem Contract-Scope und dokumentierter Legacy-Baseline fuer API-/Service-Pfade; Ruff ist auf `E/F/B/I/UP/SIM` konfiguriert, bestehende Import-/pyupgrade-/simplify-Altlasten sind als Phase-2-Baseline markiert. Frontend-TS laeuft ohne JS-Restbestand (`allowJs=false`) und ESLint parst Vue-SFC-`<script>`-Bloecke ueber `@typescript-eslint/parser`.
- **CI Publish-Scope:** `docker-image.yml::publish` trennt den harten GHCR-Publish vom optionalen Docker-Hub-Mirror. Beide Pfade bleiben smoke-gated; Docker-Hub-HTTP-400 bei grossen Layern blockiert den GHCR-Release-Pfad bis zur Phase-3-Image-Verkleinerung nicht mehr.
- **CI Release-Gating:** `docker-image.yml` ist fuer v1.0 gehärtet: globale Permissions sind auf `contents: read` reduziert, Publish-Rechte liegen nur noch am `publish`-Job, Tag-Pushes haben keinen `success() || tag`-Bypass mehr, `latest` wird nur auf dem Default-Branch gesetzt, und der Reverse-Proxy-Smoke validiert das aus dem gebauten Image extrahierte Frontend-Bundle statt eines zweiten Runner-Builds. Release-/RC-Smokes laufen automatisch fuer `release/**` und `rc/**`; normale Feature-PRs bleiben wegen Laufzeit ausgenommen. Drittanbieter-Actions im Workflow sind auf volle Commit-SHAs gepinnt.
- **CI:** Docker-Image-Build und Reverse-Proxy-Stack-Smoke laufen nicht mehr auf jedem Pull Request; der teure Smoke bleibt auf `main`/Tags und `workflow_dispatch` beschränkt und wird vor dem finalen Release-Gate wieder bewertet.
- Frontend-Vokabular und README synchronisiert: Knoten→Entitäten, Kanten→Beziehungen, Entitätstypen→Attribute (Sub-Slice 43). Tagline auf Hybrid-Wording „lokal oder Cloud" aktualisiert. Tool-Call-USP („Agenten halluzinieren nicht") als Differenzierungsmerkmal in step3.sub und neuem home.differentiators-Block ergänzt.

### Fixed
- **CI prod-proxy-smoke:** `scripts/verify-deploy.sh` prueft laufende Compose-Container jetzt ueber den Docker-Running-State aus `docker compose ps -a` mit Container-Namen-Fallback statt ueber den noch startenden Health-Status und ersetzt den bruechigen DOMPurify-Grep im minifizierten Bundle durch Bundle-Praesenz im Runtime-Image plus Source-Vertrag gegen `frontend/src/utils/markdown.ts`.
- **Security-CI:** Neue Pillow-Findings `CVE-2026-42308`, `CVE-2026-42310`, `CVE-2026-42311` als temporäre `pip-audit`-Baseline mit Issues #296–#298, Owner und Hardstop 2026-07-30 aufgenommen; direkter Upgrade bleibt durch `camel-oasis==0.2.5`/`camel-ai==0.2.78` blockiert.
- **Frontend-CI:** Vue-Template-`as`-Casts in `AddPersonaModal.vue` und `PersonaDetailModal.vue` durch typisierte Event-Handler ersetzt; `npm run lint` ist wieder grün.
- **`useSimulationPrepare`:** `fetchProfilesRealtime` als öffentliche Methode exposen — beseitigt ReferenceError beim Hinzufügen/Löschen von Personas in Step2EnvSetup (Sub-Slice 36, Closes #292, Regression aus Sub-Slice 34)

### Added
- **Supply Chain Security:** Neue `dependency-review.yml` blockiert Pull Requests bei neuen High-severity Dependency-Funden. Neue `codeql.yml` aktiviert CodeQL fuer Python und JavaScript/TypeScript auf `main`, PRs und woechentlichem Schedule. `docker-image.yml::publish` erzeugt nach GHCR-Push eine Build-Provenance-Attestation und laedt ein SPDX-JSON-SBOM als Workflow-Artefakt hoch.
- **M10.5 Security:** `POST /api/auth/ticket` bekommt ein app-seitiges Fixed-Window-Rate-Limit (Default 60 Requests / 60 s pro Remote-Adresse) mit `429`-JSON-Envelope und `Retry-After`-Header. Konfiguration via `AGORA_TICKET_RATE_LIMIT_MAX` und `AGORA_TICKET_RATE_LIMIT_WINDOW_SECONDS`; Werte `<= 0` deaktivieren den Limiter fuer lokale Experimente. Refs #302.
- **M10.5 Security:** Der Upload-Pfad `POST /api/graph/ontology/generate` bekommt ebenfalls ein app-seitiges Fixed-Window-Rate-Limit (Default 10 Requests / 60 s pro Remote-Adresse) mit `429`-JSON-Envelope und `Retry-After`-Header. Konfiguration via `AGORA_UPLOAD_RATE_LIMIT_MAX` und `AGORA_UPLOAD_RATE_LIMIT_WINDOW_SECONDS`; Werte `<= 0` deaktivieren den Limiter fuer lokale Experimente. Refs #302.
- **M10.5 Security:** Simulation-LLM-Trigger `POST /api/simulation/generate-profiles` und `POST /api/simulation/prepare` bekommen ein app-seitiges Fixed-Window-Rate-Limit (Default 20 Requests / 60 s pro Remote-Adresse und Endpoint) mit `429`-JSON-Envelope und `Retry-After`-Header. Konfiguration via `AGORA_LLM_TRIGGER_RATE_LIMIT_MAX` und `AGORA_LLM_TRIGGER_RATE_LIMIT_WINDOW_SECONDS`; Werte `<= 0` deaktivieren den Limiter fuer lokale Experimente. Refs #302.
- **M10.5 Security:** Report-Trigger `POST /api/report/generate` und `POST /api/report/chat` bekommen ein app-seitiges Fixed-Window-Rate-Limit (Default 10 Requests / 60 s pro Remote-Adresse und Endpoint) mit `429`-JSON-Envelope und `Retry-After`-Header. Konfiguration via `AGORA_REPORT_RATE_LIMIT_MAX` und `AGORA_REPORT_RATE_LIMIT_WINDOW_SECONDS`; Werte `<= 0` deaktivieren den Limiter fuer lokale Experimente. Refs #302.
- **Persona-Regenerate UI:** Button + State-Pill `regenerating` + Start-Gate-Block in `Step2EnvSetup.vue`, `regenerate()`-Methode in `usePersonaReview`-Composable, `regenerateSimulationProfile()` in API-Client, 4 i18n-Keys (`step2.persona.regenerate/regenerateHint/regeneratingPill/regeneratingBlock`) in de.json + en.json (Sub-Slice 33, Closes #70)

### Changed
- refactor(frontend): useEnvForm-Composable aus Step2EnvSetup.vue extrahiert (Sub-Slice 37, Refs #203).
- **Step2EnvSetup:** Quota-State, LocalStorage-Persistenz und Zod-Validierung nach `usePersonaQuota`-Composable extrahiert (Sub-Slice 35, Refs #203)
- **Step2EnvSetup:** Simulation-Prepare-Lifecycle nach `useSimulationPrepare`-Composable extrahiert (Sub-Slice 34, Refs #203)

### Refactored
- Step4Report.vue unter 800 LOC gebracht: Report-Modellsteuerung, Outline/Sections, Evidence-Inspector, Branch-Controls, Export-/Download-Logik und Agent-Log-Parsing in dedizierte `step4/*`-Komponenten, `useReportExports` und `reportAgentLog` ausgelagert. Aktueller Stand: 795 LOC.
- Step2EnvSetup.vue unter 800 LOC gebracht (Task 47, Refs #203): tote scoped Styles aus früheren Step2-Subkomponenten-Extraktionen entfernt und verbliebene hartkodierte Setup-/Run-Labels auf i18n umgestellt. Aktueller Stand: 667 LOC.
- Persona-Library-Section aus Step2EnvSetup.vue in `step2/PersonaLibraryPanel.vue`-Subkomponente extrahiert (Sub-Slice 45, Refs #203). Step2EnvSetup.vue von 1065 LOC → 1044. Existierende `step2.library.*`-i18n-Keys weiterverwendet, keine neuen Keys nötig.
- Persona-Cards-Loop aus Step2EnvSetup.vue in `step2/PersonaCardGrid.vue`-Subkomponente extrahiert (Sub-Slice 44, Refs #203). Step2EnvSetup.vue von 1099 LOC → 1065. i18n-Keys unter `step2.cardGrid.*` neu mit Pluralisierung für Hinweis-Anzahl (de.json + en.json).
- Persona-Detail-Modal aus Step2EnvSetup.vue in `step2/PersonaDetailModal.vue`-Subkomponente extrahiert (Sub-Slice 42, Refs #203). Step2EnvSetup.vue von 1235 LOC → 1099. i18n-Keys unter `step2.detailModal.*` neu (kicker, reviewActive, actions.{edit,reject,approve,save}, fields.* in de.json + en.json).
- Add-Persona-Modal aus Step2EnvSetup.vue in `step2/AddPersonaModal.vue`-Subkomponente extrahiert (Sub-Slice 41, Refs #203). Step2EnvSetup.vue von 1295 LOC → 1235. i18n-Keys unter `step2.addPersona.*` neu (kicker, title, submit, fields.*, placeholders.* in de.json + en.json).
- Persona-Suche/Filter aus Step2EnvSetup.vue in `usePersonaFilter`-Composable extrahiert (Sub-Slice 40, Refs #203). Step2EnvSetup.vue von 1314 LOC → 1295. Defensive Härtung: `interested_topics`-String-Fallback, Null-safe-Field-Access.
- Persona-Library + CRUD aus Step2EnvSetup.vue in `usePersonaLibrary`-Composable extrahiert (Sub-Slice 39, Refs #203). Step2EnvSetup.vue von 1467 LOC → 1314.
- Persona-Review-Aktionen aus `Step2EnvSetup.vue` in `usePersonaActions`-Composable extrahiert (Sub-Slice 38, Refs #203). Step2EnvSetup.vue von 1574 LOC → 1467.
- **Sub-Slice 31 (Phase 1, Refs #203):** `QuotaPlanEditor.vue` aus `Step2EnvSetup.vue` extrahiert. Neues `frontend/src/components/step2/QuotaPlanEditor.vue` (`<script setup lang="ts">`, Props/Emits Zod-typisiert via `personaQuotaContract.ts`, vollständige i18n-Abdeckung). `Step2EnvSetup.vue` von 1817 → 1712 LOC. 6 Vitest-Cases in `step2/__tests__/QuotaPlanEditor.spec.ts` (render valid plan, edit emits update, invalid plan shows error, disabled inputs, add segment, toggle emit). Alle 247 Frontend-Tests grün, `npm run check` grün.

### Changed
- **README + Versions-Bump auf `0.9.1-dev`:** README einladender überarbeitet (weg von „Local-first, cloud-kompatibel"-Tagline, hin zu use-case-orientiertem Hero), Layer-Tabelle auf 0–10, neuer „Was ist neu seit 2026-05-04"-Block, Container-Rebuild-Anleitung („Nach größeren Umbauten neu bauen") in den Schnellstart eingebaut, Demo-Video als komprimiertes MP4 + Inline-GIF im Workflow-Schritt 2 (Graph aufbauen), Footer mit Maintainer-Brand-Link auf alexle135.de. Versions-Bump in `backend/pyproject.toml`, `frontend/package.json`, `package.json` (Root) von `0.9.0` auf `0.9.1-dev`. Tag bleibt `v0.9.0` — `0.9.1-dev` signalisiert post-tag Iteration. Neue Assets unter `media/screenshots/graph-build.{mp4,gif}` (komprimiert via ffmpeg: 36 MB MOV → 747 KB MP4 + 5.6 MB GIF). Platzhalter-Pfade `media/logo.png` (überschreiben), `media/screenshots/persona-step.png` (neu) und `media/credits/alexle135-brand.png` (neu) — Bilder folgen vom Maintainer.

### Refactored
- `backend/app/services/report_agent.py` (2400 LOC Monolith) in ein Package `services/report_agent/` aufgesplittet (Sub-Slice M11.13, Closes [#202](https://github.com/arn0ld87/agora/issues/202)). Neue Module: `agent.py` (ReportAgent-Klasse), `manager.py` (Persistence-Facade), `planning.py` (plan_outline), `storage.py` (I/O-Helfer), `tools.py` (Tool-Definitionen/Execution), `workflow.py` (generate_report, generate_section_react, chat), `evidence.py` (EvidenceMap-Helfer), `prompts.py`, `schemas.py`, `sections.py`. Alle oeffentlichen Imports bleiben rueckwaertskompatibel via `__init__.py`-shim. Vollsuite: 1424 passed. Monkeypatch-Targets in `test_anti_dekoration.py` und `test_report_agent_contradiction_wiring.py` auf die neuen Submodul-Pfade aktualisiert. `check_voice.py` und `test_wording_glossary.py` setzt jetzt auf Verzeichnis-Scan statt Einzel-Datei-Pfad.

### Fixed
- **CI prod-proxy-smoke Embedding-Crash-Loop (Issue #276):** `validate_embedding_configuration()` bekommt neuen Parameter `skip_probe: bool = False`. Bei gesetztem Flag läuft nur die statische `KNOWN_EMBEDDING_DIMS`-Lookup — kein HTTP-Call gegen Ollama. `backend/app/__init__.py` liest `AGORA_SKIP_EMBEDDING_PROBE` (default `false`) und reicht es als `skip_probe` weiter; bei aktivem Skip wird ein WARNING geloggt. `.github/workflows/docker-image.yml::prod-proxy-smoke` setzt `AGORA_SKIP_EMBEDDING_PROBE=true` im `env:`-Block und schreibt den Wert in die CI-`.env`-Datei, damit Compose den Wert in den Container reicht. Der `continue-on-error: github.event_name == 'pull_request'`-Workaround (PR #273) entfällt — PR-Smokes sind jetzt strict (M9.6). Tag-Pushes behalten `continue-on-error: github.ref_type == 'tag'` wegen instabiler externer Image-Pulls. `publish`-Job-Bedingung bleibt unverändert (`success() || github.ref_type == 'tag'`). Drei neue Tests in `tests/test_embedding_service.py`: `skip_probe_returns_none`, `skip_probe_still_rejects_known_dim_mismatch`, `default_still_probes`.
- **Neo4j-Startup-Race:** `Neo4jStorage._verify_connectivity` retried jetzt transient connect-Fehler (`ServiceUnavailable`/`SessionExpired`/`TransientError`/`OSError`) mit Backoff, bevor das Backend permanent in den `neo4j_storage = None`-Zustand fällt. Hintergrund: Compose bringt `agora` und `agora-neo4j` parallel hoch; der Compose-Healthcheck pingt HTTP/7474, Bolt/7687 öffnet aber ein paar Sekunden später, und `restart: unless-stopped` ignoriert `depends_on: service_healthy` beim Auto-Restart — ein einziger `Connection refused` beim Container-Start machte das UI-Badge bisher dauerhaft rot, bis manuell `docker restart agora`. Default 5 Versuche × 2 s, env-tunable via `NEO4J_STARTUP_RETRY_MAX` und `NEO4J_STARTUP_RETRY_DELAY`. Auth-/Konfigurationsfehler werden weiterhin sofort propagiert (kein Retry-Loop bei „bad password"). Tests: `backend/tests/test_neo4j_startup_retry.py` mit 3 Fällen (transient → success, permanent → raise, non-transient → no retry); 9/9 grün gemeinsam mit den bestehenden `test_neo4j_resilience.py`.

### Changed
- **Issue #217 Stufe 2b — Persona-Detail-Level (Output-Größen-Steuerung):** Neues env `AGORA_PERSONA_DETAIL_LEVEL=compact|standard|rich` steuert die Wortanzahl pro Persona-Beschreibung direkt. Default `standard` (700–900 Wörter) ersetzt den alten Stand von ~1500–2000 Wörtern — das ist eine **breaking-ish Änderung** für Nutzer die bisher Richtext-Persona-Reichhaltigkeit implizit erwartet haben; `rich` stellt den alten Stand exakt wieder her. `compact` (300–500 Wörter) ist für Bulk-Simulationen gedacht. Output-Token-Reduktion ist direkter Hebel auf Cloud-LLM-Inference-Zeit (Streaming-Decoder ist linear in Token-Anzahl). Erwartete Speedups: standard ≈ −50–60 %, compact ≈ −75–80 % vs. `rich`. Context-Limit in den Prompt-Funktionen (`_build_individual_persona_prompt`, `_build_group_persona_prompt`) ebenfalls level-abhängig: 1200/2000/3000 Zeichen. `.env.example` um `AGORA_PERSONA_DETAIL_LEVEL=standard` im Performance-Block erweitert. Neue Tests: `test_resolve_persona_detail_level_default_is_standard`, `test_resolve_persona_detail_level_known_values` (5 parametrisiert inkl. case-insensitive + whitespace), `test_resolve_persona_detail_level_unknown_falls_back_to_standard`. Backward-compat: `rich` = exakt alter Stand (1500–2000 Wörter, context_limit=3000). `_validate_profile_metadata`-Semantik unberührt. Refs #217.
- **Issue #217 Stufe 2a — Persona-Latenz erste Optimierungs-Welle:** `parallel_count`-Default in `OasisProfileGenerator.generate_profiles_from_entities` von hartkodiert 5 auf `Optional[int] = None` umgestellt; Auflösungsreihenfolge: explizit übergebener Wert → env `AGORA_PARALLEL_PERSONA_COUNT` → Fallback 10. Gleiches Muster in `prepare_simulation()` (`prepare_service.py`): `parallel_profile_count` war `int = 3`, jetzt `Optional[int] = None`, Auflösung einmalig vor `_phase_generate_profiles`. `.env.example` dokumentiert `AGORA_PARALLEL_PERSONA_COUNT`, `LLM_DISABLE_JSON_MODE`, `OLLAMA_THINKING` als Performance-Kommentar-Block. Neue Tests: `test_generate_profiles_from_entities_resolves_parallel_count_from_env` (deterministisch, Default-CI) + `test_persona_generation_perf_real_llm` (Marker `perf` + `llm`, nur manuell via `pytest -m 'perf and llm'`). Refs #217.
- **M11.1 Evidence-Quality-Gate hart geschaltet:** `--soft` aus `.github/workflows/contract-gates.yml` entfernt. Bisher schwächte ein Bad-Case-Fixture (`orphan_heavy.json` mit coverage=0.5/orphan=0.5) den Mittelwert unter die Hard-Schwellen (0.85/0.75/0.10), sodass der Gate niemals zuverlässig hart schalten konnte. Lösung: `tests/eval/fixtures/` aufgeteilt in `good/` (clean_small.json, medium_with_dedup.json — Hard-Gate-Mittelwert-Quelle) und `bad/` (orphan_heavy.json — separater Detector-Pin). `contract-gates.yml::evidence-quality` nutzt jetzt `--fixtures tests/eval/fixtures/good` ohne `--soft`. Bad-Case-Fixtures werden weiterhin von `tests/eval/test_eval_baselines.py` Snapshot-getestet (gegen `expected_metrics.json`); Drift im Detector wird dort gefangen, ohne den Hard-Gate auszuhebeln. Test-Validierung lokal: 13/13 Eval-Tests grün; Hard-Gate-Mittelwert über Good-Cases: coverage=1.000 / support=0.938 / orphan=0.000. CI ist damit echt-strikt — neue Quality-Drifts in Good-Case-Fixtures failen den Workflow sofort, statt nur eine Warning zu drucken.
- **M10.4-Followup:** ADR-0001 von **Proposed** auf **Accepted** gehoben (User-Sign-off via Merge PR #277, 2026-05-04). Code-Folgeschritt: `backend/app/api/status.py::_get_auth_mode()` returnt jetzt `"single_user_token"` statt `"token"` bei gesetztem `AGORA_AUTH_TOKEN` — der `single_user_`-Prefix macht für Operatoren in `/api/status.backend.auth_mode` direkt sichtbar, dass Agora kein Multi-User-Modell hat. `backend/tests/test_anonymous_in_healthcheck.py` an den neuen Wert angepasst (zwei Assertions). Übrige Werte (`anonymous`, `open`, `misconfigured`) unverändert. README/security-hardening Single-User-Block + Token-Rotation-Prozedur sind als nächster Doku-Slice eingeplant.

### Documentation
- **Slice F (#275) Context-Truncation-Audit:** `agora-evidence-auditor`-Run hat den Bug-Bericht „CAMEL-Truncation auf 8192 trotz PR #270" gegen alle vier Verdachtsfälle (A: Rebuild, B: env-Override, C: anderer ContextCreator, D: Nicht-OASIS-Pfad) verifiziert. Ergebnis: **Fall A bestätigt** — Image-Build (2026-05-04 12:33 CEST, `sha256:9d0a748a`) liegt 83 Minuten vor dem PR-#270-Merge (commit `acb6fef`, 13:56 CEST). `_sim_common.py` ist im laufenden Container nicht vorhanden (`ModuleNotFoundError`); `apply_camel_context_floor()`/`enforce_memory_token_limit()` sind in den Sim-Runner-Skripten des Images nicht verdrahtet. Env-Overrides (`OLLAMA_NUM_CTX=262144`, `LLM_CONTEXT_LIMIT=262144`) sind korrekt und würden den Floor-Patch sofort wirksam machen, sobald das Image rebuilt ist. Kein Code-Change nötig. Empfehlung im Audit dokumentiert: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` + Marker-Verifikation (`[context-patch] token_limit floor = 262144`, `[enforce_memory_token_limit] agent N: 8192 -> <limit>`) + Re-Test, danach Issue schließbar. Audit: `docs/2026-05-05-275-context-truncation-audit.md`05-05-275-context-truncation-audit.md).
- **Slice E (#213) Verify-and-Close:** `agora-evidence-auditor`-Audit hat alle 8 Akzeptanzpunkte des Live-Modell-Badge-Slices als erfüllt verifiziert (LLM-Client publiziert `model.active`-Event, SSE-Endpoint `/api/llm/model-stream` mit Signed-Ticket-Auth, Pinia-Store `useActiveModelStore`, `ActiveModelBadge.vue` im `WorkspaceHeader`, `STALE_AFTER_MS=30s`-Idle-Fallback, `aria-live="polite"`, vollständige `activeModel.*`-i18n-Keys in `de.json`+`en.json`, 26 Backend-Pytests + 7 Vitests grün). Issue #213 wird als Doku-Schuld geschlossen ohne Code-Change. Audit-Tabelle: `docs/2026-05-04-213-active-model-verify-close-arbeitsprotokoll.md`05-04-213-active-model-verify-close-arbeitsprotokoll.md).
- **M10.4-Doku-Folge:** README.md (DE+EN-Status-Block) auf Single-User-only mit Verweis auf ADR-0001 erweitert — explizit dass es kein User-Konzept, kein Logout und keinen Multi-User-Pfad gibt, plus Hinweis auf Reverse-Proxy für Tailnet/LAN. `docs/security-hardening.md` neue Sektion **„Auth-Modell v1.0 (ADR-0001, Accepted 2026-05-04)"** mit (a) Garantien-Liste (kein User-Konzept, kein Logout, kein Audit, kein Multi-User), (b) Was-schützt-was-nicht-Gegenüberstellung — explizit dass Brute-Force ohne Rate-Limits (M10.5 in Planung) ein offener Hardstop ist, (c) **Token-Rotation-Prozedur** als 6-Schritt-Anleitung (Generate → `.env`-Update → Container-Recreate → Frontend-Bundle-Rebuild bei opt-in `ALLOW_BUILD_TIME_TOKEN=true` → `curl`-Verifikation gegen alten und neuen Token → Browser-Session-Cleanup), (d) Trigger für ADR-Supersedes (Klassenraum, Public-Internet, DSGVO-Multi-User, Rollen/Permissions), (e) Hardstops-Liste. Der existierende „Langfristig: echte Session-/Login-Auth"-Bullet wurde mit `~~strikethrough~~` als durch ADR-0001 beantwortet markiert. Damit ist die v1.0-Auth-Story dokumentarisch geschlossen.

### Added
- `POST /api/simulation/<sim>/profiles/<username>/regenerate` — Persona in den Status `"regenerating"` setzen (Sub-Slice 31, Refs [#70](https://github.com/arn0ld87/agora/issues/70)). State-Machine erweitert um `regenerating`-Zustand (erlaubte Vorgaenger: `pending`, `approved`, `rejected`, `regenerating`). `evaluate_start_gate` blockt die Sim-Start-Gate solange mind. eine Persona `regenerating` ist. Audit-Felder `review_notes` und `review_requested_by` werden gesetzt. Tatsaechliche Re-Generierung folgt im naechsten Generator-Pfad-Slice. 13 neue Tests (9 Service + 4 API). Ruff/mypy/schemas clean.
- `GET /api/simulation/<sim>/profiles/<username>/entity-context` — Knowledge-Graph-Entity-Kontext pro Persona (Layer-0-Boundary via `PersonaEntityContext.model_validate()`, Refs #69 EPIC-13-ST-02). Neuer Pydantic-Contract `PersonaEntityContext` + `EntityRelationship` (`extra="forbid"`), Service `PersonaEntityContextService` (Storage-API-aware: `storage.get_node()` + `EntityReader.get_node_edges()`), Fallback-Pfad fuer Legacy-Personas ohne `source_entity_uuid` (`source="fallback"`). Schema-Dump idempotent (neue `schemas/persona-entity-context.schema.json`). Frontend-UI folgt in Sub-Slice 30.
- `RunsDashboard.vue` mit Live-Polling (5s, Tab-aware), Status-Filter-Pills (Aktiv/Abgeschlossen/Fehlerhaft) und Click-through zur neuen `/runs/:id` Detail-View (`RunDetailView.vue`). Closes #63.
- Frontend: BranchComparePanel.vue — Side-by-side-Compare-View für zwei Branches mit Δ-Highlights (Sub-Slice 27, Closes [#67](https://github.com/arn0ld87/agora/issues/67))
- Frontend: GraphDiffPanel.vue — Diff-View für Graph-Snapshots mit visuellen Annotations (Sub-Slice 26, Closes [#76](https://github.com/arn0ld87/agora/issues/76))
- API: `GET /api/simulation/<id>/compare?branch_a=...&branch_b=...` liefert BranchComparison-Pydantic-Response mit Metriken beider Branches und signierten Deltas (B − A). CompareService aggregiert NetworkAnalytics + Report + Neo4j-Persona-Reach. Layer-0-Boundary über `BranchComparison.model_validate()` in der Response. (Sub-Slice 24, Closes [#66](https://github.com/arn0ld87/agora/issues/66))
- `GET /api/graph/<graph_id>/diff?start_round=X&end_round=Y` — Graph-Snapshot-Diff-Endpoint (Layer-0-Boundary via `GraphDiff.model_validate()`, Closes [#74](https://github.com/arn0ld87/agora/issues/74)): Konvertierung service-Dataclass (`temporal_graph.GraphDiff`) → Pydantic-Contract mit Phase-2-Defaults für Cluster-/Bridge-Agent-Felder. Hilfsfunktionen in `app/utils/graph_diff_helpers.py`. 5 neue Tests in `tests/test_graph_diff_api.py`, 1 neuer Test in `tests/test_temporal_graph.py`. Ruff/mypy grün auf den neuen Dateien. Schemas idempotent.
- **Issue #217 Stufe 1 — LLM-Latenz-Messung:** Neuer `@measure_llm_latency`-Decorator (`backend/app/utils/llm_latency.py`) loggt strukturiert `operation`, `function`, `latency_ms`, `roundtrips`, `success`, `model`, `prompt_chars`, `error_type` via Logger `agora.llm_latency`. Angewendet auf `OasisProfileGenerator._generate_profile_with_llm` (chirurgischer Messpunkt direkt um den LLM-Roundtrip, nicht um den Public-Wrapper). Neuer pytest-Marker `perf` (deterministisch via Mock, kein Ollama). 5 neue Tests in `tests/perf/`. Stufe 2 (Optimierung ≥ 30 % Reduktion) folgt als separater Slice. Arbeitsprotokoll: `docs/2026-05-05-217-persona-latency-stufe-1-messung-arbeitsprotokoll.md`05-05-217-persona-latency-stufe-1-messung-arbeitsprotokoll.md). Refs #217.
- Frontend-Coverage-Gate via `@vitest/coverage-v8`, Schwelle 24 % als Startwert (M11.3). Coverage-Report als CI-Artifact `frontend-coverage` (14 Tage Retention). Roadmap: monatlich +2 Punkte bis 80 %.
- Backend-Coverage-Gate via `pytest-cov`, Schwelle 53 % als Startwert (M11.2). Coverage-Report als CI-Artifact `backend-coverage` (14 Tage Retention). Roadmap: monatlich +2 Punkte bis 85 %.
- M10.4 Auth-Zielbild-ADR (Proposed): Neue ADR-Reihe unter [`docs/decisions/`](docs/decisions/) mit [`0001-auth-model.md`](docs/decisions/0001-auth-model.md) und [`README.md`](docs/decisions/README.md) (Index + MADR-Light-Konvention). ADR-0001 wägt drei Auth-Optionen für v1.0 ab — Single-User-only-v1 (Status quo formalisieren), HttpOnly-Session (Multi-User mit Cookies), Bearer+Refresh (OAuth2-ähnlich). **Empfehlung: Option A (Single-User-only-v1)** — Begründung: Local-first ist Kernprinzip (siehe `docs/archive/plans/plan.heuristic.md`), Hauptangriffsvektoren sind durch F2.1/F2.2/P0.2/S2/S3 bereits geschlossen, v1.0 in 4-6 Wochen erreichbar, Migrationspfad nach v2 mit Option B bleibt offen. Status: **Proposed**, wartet auf User-Sign-off. Bei Accept: Folge-Slices README/security-hardening-Update, `auth_mode: "single_user_token"` in `/api/status`, Token-Rotation-Prozedur in `docs/security-hardening.md`.
- M10.1/M10.2/M10.3 CVE-Monitor + Hardstop: Neuer Workflow `.github/workflows/cve-monitor.yml` läuft Mo 06:00 UTC `pip-audit --strict` ohne `--ignore-vuln` und schreibt das Ergebnis in `$GITHUB_STEP_SUMMARY` plus Audit-Output als 30-Tage-Artefakt. **Hardstop 2026-07-30** ist verdrahtet: ab diesem Datum fail bei pip-audit-Findings — die `--ignore-vuln`-Liste in `ci.yml` muss bis dahin leer sein, sonst greift der Eskalationspfad (Vendoring / Soft-Fork / Replacement / Risikoakzeptanz-PR mit User-Sign-off). `docs/dependency-risk-register.md` um Eskalationspfad-Sektion und Upstream-Release-Watch-Spalte mit GitHub-Release-Links erweitert (die Owner-Spalte war bereits vorhanden). `ci.yml` Kommentar verweist auf den Hardstop-Workflow. Layer 10 (Security Watchlist) damit von „dokumentiert" auf „grün".
- M9.6 Prod-Stack-Smoke als PR-Gate: `.github/workflows/docker-image.yml::prod-proxy-smoke` triggert jetzt zusätzlich auf `pull_request: [main]` (Doku-PRs via `paths-ignore` ausgeschlossen — `**.md`, `docs/**`, `CHANGELOG.md`, Issue-/PR-Templates). Damit smoket der vollständige Compose-Stack inkl. `deploy/compose/docker-compose.prod-with-proxy.yml` vor jedem nicht-Doku-PR. `publish`-Job bleibt durch `if: github.event_name != 'pull_request'` gegated und pusht nicht aus PRs. `scripts/verify-deploy.sh` smoket zusätzlich `/api/auth/ticket` via Proxy (POST mit `X-Agora-Token`-Header und `sse:smoke`-Scope, prüft `"ticket"`-Key in JSON-Response). Lokal skippt der Check sauber wenn `AGORA_AUTH_TOKEN` nicht im env steht. Damit ist M9 (Prod-Hardening) abgeschlossen — nächste Slice-Priorität: M10.

### Removed
- CI: `.github/workflows/claude.yml` und `.github/workflows/claude-code-review.yml` entfernt. Die beiden Anthropic-Boilerplate-Workflows scheiterten auf jedem PR mit *"Claude Code is not installed on this repository"* und tauchten als FAILURE in der Status-Rollup auf, obwohl in CLAUDE.md als ignorierbar markiert. Wer den Service später re-aktivieren möchte: Workflow-Templates aus dem [claude-code-action](https://github.com/anthropics/claude-code-action)-Repo neu beziehen plus `ANTHROPIC_API_KEY`-Secret im Repo setzen.

### Documentation
- Doku-Status zum pausierten Docker-PR-Smoke synchronisiert: `docs/STATUS.md`, `docs/archive/plans/plan.heuristic.md` (lokal), `AGENTS.md` und `CLAUDE.md` dokumentieren jetzt, dass `docker-image.yml::prod-proxy-smoke` weiter auf `main`/Tags/`workflow_dispatch` läuft, der PR-Trigger aber seit 2026-05-06 wegen der Laufzeit bewusst pausiert ist.
- Doku-Sync 2026-05-04: Top-Level-Doku auf realen Code-Stand 2026-05-04 gezogen. `AGENTS.md` von **v0.6.0 alpha** auf **v0.9.0+** überholt (Layer-Tabelle, Pydantic-Contracts, signed tickets, gevent, Pinia, Subagent-Routing). `CLAUDE.md` Layer-9-Status mit ✅-Markierungen (Reverse-Proxy, gevent, Bundle-Token-Gate, `?token=`-Block, signed-tickets-Frontend) und neu fokussierten Hot-Spots (M9.6, M10.4, CVE-Monitor, Evidence-Gate, Coverage). `PLAN.md` mit neuer Top-Sektion „Status-Sync 2026-05-04" — F1/F2.1/F2.2/F3 sind code-verifiziert grün. `docs/STATUS.md` Aktive-Slices-Block korrigiert (M9.6/M10.1/M10.4 statt der bereits durchgeführten F1/F2/F3). `ROADMAP.md` Now-Block auf M9-Wrap-up + M10-Start. `docs/archive/plans/plan.heuristic.md` als Subagent-Routing-Single-Source-of-Truth (M9.1–M13.5 mit Status-Spalte, ADR-Register, Tech-Debt-Register, Hardstops, lokal). User-Drop-Audit-Snapshots unter `docs/archive/history/2026-05-04-plan-update-audit-snapshot.md` und `docs/archive/history/2026-05-04-plan-heuristic-adr-snapshot.md` archiviert (lokal).
- Incident-Bericht zum Vector-Index Dimension-Drift vom 2026-05-04 angelegt: alte 2560-dim Indexe (qwen3-embedding) blieben nach OpenAI-Switch (1536-dim) bestehen, weil `CREATE VECTOR INDEX … IF NOT EXISTS` nur über den Namen matcht. Manueller Cleanup (Index-Drop + 316 Entity-Delete + 14 Graph-Delete + Container-Restart) ist dokumentiert; Code-Hardening folgt in Issue [#263](https://github.com/arn0ld87/agora/issues/263). Details in `docs/2026-05-04-vector-index-dimension-drift-incident.md`.

### Fixed
- Vector-Index Dimension-Drift: `_ensure_schema()` droppt+recreated Indexe bei Dimension-Mismatch (#263, P1).
- Persona-Default-Branchenverteilung folgt Destatis-WZ-2008; IT-Anteil ≤ 12 %, ≥ 7 Branchen (#215).
- bug(report): `plan_outline()` baut `ReportOutlineModel` mit `description`-Feld; Frontend-Zod-Validation wieder grün (Closes #274)
- `test_add_progress_callback_sets_progress_detail_on_task_manager` (Slice 137-Followup): Wartet jetzt via `threading.Event` statt 50×0.05 s `time.sleep`-Loop auf den Background-Thread. Verhindert intermittente Failures unter CI-Last und gibt sofort frei, sobald `progress_detail`-Call durch ist. Gemini-MEDIUM auf #265.
- Step4Report-Spec auf Report/EvidenceMap-Types typisiert, um vue-tsc Fehler zu beheben (kein Runtime-Effekt)
- Fixed: LogDrawer SSE Reconnect ist jetzt nach 5 Fehlversuchen gecappt; UI bietet einen Reload-Button (Slice J.6, Audit-Empfehlung 7).
- `docker-compose.yml`/`docker-compose.prod.yml` `LLM_BASE_URL` und `EMBEDDING_BASE_URL` auf `${VAR:-default}`-Substitution umgestellt — `.env`-Werte gewinnen jetzt, Default-Fallback bleibt host-Ollama. Vorher wurden die Werte hardcoded überschrieben, sodass OpenAI-Embedding-Switch via `.env` ins Leere lief und der Container in den Reboot-Loop ging (404 von Ollama auf `text-embedding-3-small`). Slice K.2.
- `/api/logs/stream` verwirft Halb-Zeilen bei EOF und rückt `offset` nicht vor (`readline`-Result endet nicht auf `\n` → Retry im nächsten Poll-Zyklus). Verhindert Datenverlust bei Multi-Byte-UTF-8 mid-write. Followup: `time.sleep(_STREAM_POLL_SEC)` vor `break` ergänzt, weil `size > offset` wahr bleibt und der reguläre Sleep-Zweig sonst nie erreicht wird (Hot-Loop, 100 % CPU). Gemini MEDIUM #254 + HIGH #255, Slice K.0.1.
- `/api/logs/stream` öffnet die Logdatei jetzt im Binärmodus, damit `tell()` garantiert Byte-Offsets liefert (Gemini HIGH-Finding auf #253, Slice K.0).
- SSE-Reconnect: `/api/logs/stream` sendet jetzt `id:`-Frames pro Datenzeile und wertet `Last-Event-ID`-Header aus (überstimmt `?offset=`), wodurch Duplikate und Datenverlust beim Browser-Reconnect verschwinden. `/api/simulation/<id>/stream` loggt Reconnect-IDs (Bus-Replay folgt) (Slice J.5.1, #233).
- SimulationRunView: doppelten `/run-status`-Poll entfernt; Step3Simulation propagiert `paused`/`current_round`/`total_rounds` jetzt via `update-progress`-Event (Slice J.2, #220).
- **Slice J.1 (#219, P1): refreshQuality aus 3-s-Tick herausgelöst.** `Step2EnvSetup.vue` rief bei jedem `fetchProfilesRealtime`-Tick (alle 3 s) `personaReview.refreshQuality()` auf — ein versteckter Doppel-HTTP-Call pro Poll-Runde. Fix: Aufruf aus dem Tick-Pfad entfernt; stattdessen `watch(() => profiles.value.length, (n, prev) => { if (prev === 0 && n > 0) ... })` — Trigger exakt einmal beim Übergang 0 → erste Profile. Sim-Wechsel ohne Unmount wird durch zweiten `watch(() => props.simulationId)` abgedeckt, der den Guard zurücksetzt. Vitest: 5 Ticks → exakt 1 `refreshQuality`-Call. Arbeitsprotokoll: `docs/2026-05-04-j1-refresh-quality-watch-arbeitsprotokoll.md`. (Gemini-Followup auf PR #245: Sim-Wechsel-Trigger-Lücke + Race-Guard, 1-watch-Variante)
- **Sub-Slice N1 (M9): Docker-Image-Publish hinter prod-proxy-smoke gaten.** `.github/workflows/docker-image.yml` gliedert den bisherigen `build-and-push`-Job in drei separate Jobs um: `build-only` (Buildx ohne Push, Image-Export als Artefakt), `prod-proxy-smoke` (lädt Artefakt via `docker load`, führt Sidecar-Nginx-Stack-Smoke durch) und `publish` (Push zu Docker Hub + GHCR erst nach grünem Smoke). `main`-Pushes sind strikt smoke-gated; `tag`-Pushes laufen mit `continue-on-error: true` auf dem Smoke-Job. Arbeitsprotokoll: `docs/2026-05-04-n1-docker-publish-order-arbeitsprotokoll.md`. Refs PLAN.md N1.
- ci: prod-proxy-smoke pipeline — `SECRET_KEY` + `LLM_API_KEY` in CI-`.env` ergänzt. Der M9-0/N3-Slice hatte beide vergessen; `Config.validate()` erzwingt sie in Non-Debug, agora-Container kollabierte deshalb in Restart-Loop, nginx lieferte `502 Bad Gateway` für `/health`. Folge-Failures (`nginx laeuft`, `Backend /health (via Proxy)`, `S1 (XSS-Fix)`) waren reine Cascade. Werte sind Smoke-Dummies (`SECRET_KEY=ci_smoke_secret_key_…`, `LLM_API_KEY=ollama`), keine echten Geheimnisse. Refs M9-0-Followup zu Run 25296986030. Arbeitsprotokoll: `docs/2026-05-04-m9-0-followup-secret-key-arbeitsprotokoll.md`.
- ci: prod-proxy-smoke pipeline repariert — kein doppelter Frontend-Build, ALLOW_BUILD_TIME_TOKEN korrekt durchgereicht, NEO4J_PASSWORD als CI-Test-Wert gesetzt (Closes #227). Details: `docs/2026-05-04-n3-prod-smoke-env-arbeitsprotokoll.md`.
- test: `test_gevent_importable` prüft nur Importierbarkeit (`gevent.__version__`), kein `patch_all()` im Test-Body (Refs PR #241, Gemini-HIGH). Fix eliminiert `MonkeyPatchWarning` und ruff-F401 auf `gevent.monkey`-Top-Level-Import.
- **Dev-Stack: Compose-Portkollision + Docker-Build-Context entschärft.** `docker-compose.override.yml` publiziert Port `5173` nicht mehr doppelt zusätzlich zum Basis-Compose — `docker compose up -d --build agora` scheitert damit nicht mehr an `failed to bind host port 127.0.0.1:5173`. Parallel wurde `.dockerignore` bereinigt, um lokale Caches und nicht laufzeitrelevante Repo-Artefakte (u. a. `backend/.cache`, `docs/`, `design/`, lokale Agent-/Editor-Ordner) aus dem Build-Context auszuschließen; der Docker-Context schrumpft damit von ~1.14 GB auf ~25.56 kB. Arbeitsprotokoll: `docs/2026-05-04-dev-stack-docker-compose-port-context-fix-arbeitsprotokoll.md`.
- **Sub-Slice F2.2 (M9-4): `?token=` Query-Parameter in Prod deaktiviert.** `backend/app/utils/auth.py:_extract_token()` ignoriert `?token=<bearer>` jetzt in Nicht-Debug-Umgebungen (FLASK_DEBUG=false). Stattdessen wird ein ERROR geloggt mit Hinweis auf Signed-Tickets (`POST /api/auth/ticket`). Der Query-Token-Pfad war seit P0.2 als Deprecation-Warning markiert, wurde aber weiterhin akzeptiert — ein Sicherheitsrisiko (Token in URL = Browser-History, Server-Logs, Referrer). Tests: `test_blueprint_guard_rejects_query_token_in_prod` (401 bei `?token=` in Prod); `test_blueprint_guard_accepts_query_token_in_debug` (weiterhin 200 in Dev). Arbeitsprotokoll: `docs/2026-05-03-f22-token-query-prod-arbeitsprotokoll.md`. Refs PLAN.md F2.2.

### Added
- **Slice #137 (Closes): Graph-Build Auto-Freeze — Backend setzt während Build `progress_detail.batch_count`/`total_batches`/`batch_at` pro committetem Chunk (SUB1); Frontend liest das beim Status-Polling und freezed die Force-Simulation 800 ms pro Batch über einen optionalen `batchSignal`-Hook in `useGraphRender` (SUB2). Manuelle Pause hat Vorrang: `_isManuallyPaused` verhindert Auto-Freeze-Start und überstimmt ausstehende Timer. Settings-konfigurierbare Freeze-Dauer (#133/#212) ist als Folgeslice markiert (SUB3, out-of-scope). Backend: `add_text_batches` in `graph_builder.py` → `progress_callback(msg, ratio, completed, total)`; `add_progress_callback` in `graph.py` setzt `Task.progress_detail`. Frontend: `BuildProgressDetail`-Interface in `api/graph.ts`; `batchSignal`-Prop-Kette `MainView → GraphPanel → GraphCanvas → useGraphRender`; 7 neue Vitest-Tests (batch-trigger, no-op same count, manual-pause-wins, manual-during-freeze, cleanup-on-unmount). Arbeitsprotokolle: `docs/2026-05-04-137-sub1-batch-marker-arbeitsprotokoll.md`, `docs/2026-05-04-137-sub2-auto-freeze-arbeitsprotokoll.md`.

- **Slice E.2 (#213): Frontend zeigt das aktive LLM-Modell als Badge im `WorkspaceHeader`.** Pinia-Store `useActiveModelStore` öffnet einen Signed-Ticket-SSE-Stream (`scope=llm-stream`) zum Backend-`/api/llm/model-stream`-Endpoint, parst `ModelActiveEvent`-Frames strikt mit Zod und fällt nach 30 s ohne Events auf "idle" zurück. Reconnect-Cap analog Slice J.6 (5 Versuche, dann manueller Reload-Button). Volle vue-i18n-de+en-Abdeckung, `aria-live="polite"`. Neue Dateien: `frontend/src/contracts/modelActiveContract.ts`, `frontend/src/store/useActiveModelStore.ts`, `frontend/src/components/ActiveModelBadge.vue` + Icon-Komponenten. Arbeitsprotokoll: `docs/2026-05-04-e2-active-model-badge-arbeitsprotokoll.md`.

- **Slice E.1 (#213): Backend publiziert vor jedem LLM-Call ein `model.active`-Event und streamt es via `GET /api/llm/model-stream` (Signed-Ticket-Auth, Scope `llm-stream`).** Neuer `ModelEventBus` (Queue-basierter Fan-out, Drop-Oldest-Backpressure, fire-and-forget) in `app/services/model_event_bus.py`. `LLMClient.chat()` und `chat_json()` rufen `_publish_model_active()` vor jedem API-Call auf; publish-Fehler werden als Warning geloggt und unterbrechen den LLM-Call nicht. Provider-Erkennung via Modell-Suffix (`:cloud`) und `base_url`-Heuristik. SSE-Frame-Format: `retry:5000`, `id:<hex>`, `data:<ModelActiveEvent JSON>`, Heartbeat alle 15 s. Frontend-Anzeige (`useActiveModelStore`, `ActiveModelBadge.vue`) folgt in Slice E.2. Arbeitsprotokoll: `docs/2026-05-04-E1-model-active-backend-arbeitsprotokoll.md`.

- **Slice K.1: OpenAI-kompatible Embedding-Endpoints + Doku.** `EmbeddingService` erkennt OpenAI-kompatible `EMBEDDING_BASE_URL` automatisch und schaltet auf Bearer-Auth (`Authorization: Bearer <EMBEDDING_API_KEY>`) sowie `/v1/embeddings`-Payload-Format um. `KNOWN_EMBEDDING_DIMS` ergänzt um `text-embedding-3-small` (1536), `text-embedding-3-large` (3072), `text-embedding-ada-002` (1536), `bge-m3` (1024), `all-minilm` (384). `Config.EMBEDDING_API_KEY` neu (Fallback `LLM_API_KEY`). `.env.example` bekommt einen kommentierten OpenAI-Block; neue Anleitung `docs/embedding-provider-switch.md`provider-switch.md) erklärt Ollama ↔ OpenAI inkl. Pflicht-Index-Drop in Neo4j und Verifikations-Snippet. Code-Defaults bleiben Ollama (`qwen3-embedding:4b`, 2560-dim) — Local-first ist Default, Cloud-Switch passiert ausschließlich über `.env`.
- **Sub-Slice F5 (M9-1): Doku-Sync — `STATUS.md` regeneriert, README inline-Zahl entfernt.** `docs/STATUS.md` zeigte `Stand: 2026-05-03` und `Backend Tests collected: 1330`; reale Lage `1370` collected nach Layer-9-Slices (N2, N6, F2.2, N3). `bash scripts/sync-status.sh` regeneriert das File deterministisch; das Aktualisierungs-Protokoll bekommt einen 2026-05-04-Eintrag. Zusätzlich `README.md:415` (englischer Engineering-Block) auf `docs/STATUS.md` umgehängt — die hartcodierte v0.9.0-Plateau-Zahl `1258 backend + 125 frontend = 1383 green` war seit Sub-Slice 44 (das den deutschen Block migriert hatte) übersehen worden. CLAUDE.md ist clean. Arbeitsprotokoll: `docs/2026-05-04-f5-doku-sync-arbeitsprotokoll.md`05-04-f5-doku-sync-arbeitsprotokoll.md). Refs PLAN.md F5.

- **Sub-Slice F3 (M9-5): Gunicorn auf gevent-Worker migriert.** `Dockerfile` installiert jetzt `gevent` neben `gunicorn` (`uv pip install --project backend gunicorn gevent`). Gunicorn-CMD um `-k gevent` erweitert; `--timeout 600` → `--timeout 60` reduziert (gevent-Worker sind non-blocking, SSE-Streams blockieren nicht mehr). Timeout bleibt konservativ für Ollama-TTFB. `backend/tests/test_gevent_fork.py` prüft Importierbarkeit. Arbeitsprotokoll: `docs/2026-05-03-f3-gunicorn-gevent-arbeitsprotokoll.md`05-03-f3-gunicorn-gevent-arbeitsprotokoll.md). Refs PLAN.md F3.

- **Sub-Slice N6 (M9-3.5): Compose-Token-Gate konsistent mit Dockerfile.** `docker-compose.prod.yml` reichte `VITE_AGORA_TOKEN` als Build-Arg durch, ohne das `ALLOW_BUILD_TIME_TOKEN`-Gate zu setzen — das Gate (F2.1/Slice 46) war im Compose-Pfad unwirksam. Jetzt: `args:` bekommt `ALLOW_BUILD_TIME_TOKEN: ${ALLOW_BUILD_TIME_TOKEN:-false}` vor `VITE_AGORA_TOKEN`. `.env.example` dokumentiert beide Variablen mit Security-Hinweis (nur Single-User-Tailnet-Opt-In). Arbeitsprotokoll: `docs/2026-05-03-n6-compose-token-gate-arbeitsprotokoll.md`05-03-n6-compose-token-gate-arbeitsprotokoll.md). Refs PLAN.md N6.

- **Sub-Slice N2 (M9-2.5): Dev-Compose Loopback-Binding.** `docker-compose.yml:23-24` bindet Vite (5173) und Flask (5001) jetzt explizit an `127.0.0.1` statt an `0.0.0.0` (Docker-Default ohne IP-Prefix). Auf Linux exponierte der Dev-Stack die Dienste ans LAN, obwohl README/CLAUDE.md „loopback first" versprachen. macOS-Bug-Hinweis im Kommentar entfernt (Docker Desktop 4.30+ behandelt 127.0.0.1 korrekt). `scripts/verify-deploy.sh` bekommt neuen N2-Check (`ss -tlnp | grep -E ':(5173|5001)' | grep -q '127.0.0.1'`). Arbeitsprotokoll: `docs/2026-05-03-n2-loopback-binding-arbeitsprotokoll.md`05-03-n2-loopback-binding-arbeitsprotokoll.md). Refs PLAN.md N2.

- **Sub-Slice N5 (M9-1.5): Veraltete Repo-Root-Audits nach `docs/archive/history/` verschoben.** Vier historische Audit-Dateien (`agora_evidence_pipeline_testfall.md`, `agora_json_evdence_review.md`, `agora_repo_review_neuer_stand.md`, `agora_repository_review.md`) mit Header-Caveat („HISTORISCHER SNAPSHOT Stand 2026-04-2x") in `docs/archive/history/` abgelegt. Diese Dateien enthielten veraltete Behauptungen (z. B. „kein DOMPurify", „kein Vitest in CI" — beides inzwischen implementiert) und erzeugten falsche Erwartungen bei neuen Reviewern. Repo-Root ist jetzt aufgeräumt. Keine Links in `README.md`/`CLAUDE.md` betroffen. Arbeitsprotokoll: `docs/2026-05-03-n5-history-move-arbeitsprotokoll.md`05-03-n5-history-move-arbeitsprotokoll.md). Refs PLAN.md F13.


- Frontend-Modellauswahl wird vom Backend respektiert. Zwei konkrete Lücken geschlossen: (1) `/api/simulation/generate-profiles` konstruierte `OasisProfileGenerator()` ohne `model_name` — das `llm_model`-Feld aus dem Request-Body wurde vollständig ignoriert. (2) `_resume_report_generate` in `runs.py` konstruierte `ReportAgent(...)` ohne `model_name` — der Resume-Pfad ignorierte jedes Model-Override. Zusätzlich schreibt `/api/report/generate` das `llm_model`-Override jetzt in die Run-Metadaten, damit der Resume-Pfad es wiederfinden kann. Die bereits korrekt verdrahteten Pfade (`/api/simulation/prepare` → `OasisProfileGenerator` und `/api/report/generate` → `ReportAgent`) waren nicht betroffen. `Config.LLM_MODEL_NAME` (Env-Var) bleibt als Fallback erhalten; kein `os.getenv("OLLAMA_MODEL")` war in `backend/app/services/` vorhanden (kein Removal nötig). (Sub-Slice C, schließt #211)
- SSE-Streams (`/api/simulation/<id>/stream`, `/api/logs/stream`) senden jetzt `retry: 5000` als erstes Frame — Browser-Reconnect-Backoff ist damit vom Backend steuerbar (vorher: Browser-Default ~3 s, unsteuerbar). `LogDrawer.onerror`-Handler loggt Connection-Fehler jetzt via `console.warn` + i18n-Nachricht statt sie zu schlucken. (Sub-Slice J.5, schließt #223)
- Step3Simulation: Phase-Übergang auf `2` ist robust gegen verlorene SSE-Frames; HTTP-Detail-Polling promotet ebenfalls. Behebt fehlenden „Weiter zum Bericht"-Button (Sub-Slice A, schließt #209).
- **Graph-Pipeline: Entitäts-Beziehungen werden zuverlässiger extrahiert (Edge-Yield ≥ 1 pro 2 Entitäten auf Fixture-Set). Root-Cause: Prompt-Regel 1 in `NERExtractor._SYSTEM_PROMPT` verbot dem LLM explizit, Relationen zu emittieren, die nicht exakt im Ontologie-Vokabular standen. Bei unvollständigen oder schmalen Ontologien (häufig in frühen Graph-Build-Phasen) emittierte das Modell deshalb gar keine Edges. Fix: Regel 1 umformuliert auf „bevorzuge Ontologie-Typen, erfinde UPPER_SNAKE_CASE-Label wenn kein Typ passt"; drei konkrete Few-Shot-Beispiele (ACQUIRED, LEADS/REPORTS_TO, COLLABORATES_WITH) ergänzt. `_validate_and_clean` war bereits korrekt konfiguriert (kein Type-Filter auf Relations). Neuer `pytest.mark.llm`-Marker in `pyproject.toml` registriert. Tests in `tests/services/test_edge_yield.py` (8 Stub-Tests, 3 opt-in LLM-Smoke-Tests). Fixtures unter `tests/fixtures/edge_yield/`. (Sub-Slice H, schließt #216)**


- **Sub-Slice B (Issue #210): Manuell hinzugefügte Personas werden in der Simulation berücksichtigt.** `add_simulation_profile` (`backend/app/api/simulation_profiles.py`) ergänzte Pflichtfelder `karma` (Default 1000) und `created_at` (UTC-ISO-String), sowie Fallback-Werte für leere `bio`/`persona`. Ohne diese Felder ignoriert OASIS's `generate_reddit_agent_graph` die Agenten still — die Personas erschienen nicht in der Simulation. Defensiv: `next_id` startet bei 1 statt 0 wenn noch keine Profile existieren, um Kollision mit generiertem `user_id=0` zu verhindern. Die Defaults spiegeln `_save_reddit_json` exakt (Schema-Parity). Frontend `Step2EnvSetup.vue` bleibt unverändert — der POST-Payload war korrekt, die Lücke lag ausschliesslich serverseitig. 7 neue Regressionstests in `backend/tests/api/test_simulation_profiles_manual_persistence.py`. Arbeitsprotokoll: `docs/2026-05-03-slice-B-arbeitsprotokoll.md`05-03-slice-B-arbeitsprotokoll.md).


- **Sub-Slice 24 — Gemini-Followup auf 20c (Frontend).** [Gemini-Code-Review auf PR #185](https://github.com/arn0ld87/agora/pull/185) hatte drei Findings: (HIGH) `buildQuotaPlanFromEntries` überschrieb bei doppeltem Segment-Namen statt zu addieren — UI-Anzeige (`quotaTotal` als Array-Sum) wich vom gesendeten Payload (last-wins-Dict) ab, Backend-Validator failte mit `total != sum(targets)`; (MEDIUM) hartkodierte deutsche Strings im Quoten-Editor statt `vue-i18n`; (MEDIUM) `v-for :key="idx"` führte zu Fokus-Verlust beim Löschen mittlerer Zeilen. Fix: `targets[segment] = (targets[segment] || 0) + count` addiert; neue i18n-Keys `step2.quota.{toggle, hintOff, hintOn, segmentPlaceholder, addSegment, total, invalid}` in [`de.json`](frontend/src/i18n/locales/de.json) + [`en.json`](frontend/src/i18n/locales/en.json); jeder `quotaEntry` bekommt eine eigene `id` via `_newEntryId()` (Counter + `Date.now`), `v-for :key="entry.id"` statt Index — LocalStorage-Reload bleibt kompatibel (alte Daten ohne `id` kriegen beim Laden eine neue zugewiesen). **Verifikation:** 2 neue Cases (HIGH-Behavior gepinnt) → 137 Tests grün, `npm run lint`/`npm run build` clean. Arbeitsprotokoll: `docs/2026-05-03-task-24-quota-frontend-gemini-followup-arbeitsprotokoll.md`05-03-task-24-quota-frontend-gemini-followup-arbeitsprotokoll.md).

- **Sub-Slice 22 — `PersonaQuotaPlan`-Persistenz + Gemini-Followup (zu 20a).** [Gemini-Code-Review auf PR #181](https://github.com/arn0ld87/agora/pull/181) hatte drei Findings: (HIGH) `quota_plan` wurde im Restart-Pfad aus `simulation_config.json` gelesen, aber nirgends gespeichert — Restart bekam immer `None`, Plan-Drift ohne Warnung; (MEDIUM) `except Exception` im View-Handler maskierte echte 500er als 400; (MEDIUM) `pydantic.ValidationError`-Import fehlte. Fix: [`_phase_generate_config`](backend/app/services/prepare_service.py) bekommt einen optionalen `quota_plan`-kwarg und schreibt ihn als Top-Level-Key `quota_plan` (`model_dump()`) ins persistierte `simulation_config.json`. `prepare_simulation` reicht den Plan an Phase 3 durch. Damit liest der Restart-Pfad in [`runs.py`](backend/app/api/runs.py) den Plan über `_parse_quota_plan(config)` korrekt wieder ein (Helper akzeptierte bereits `dict`-Payload via `model_validate` → Roundtrip ohne Schema-Drift). View-Exception verengt auf `(ValidationError, ValueError, TypeError)` — andere Fehler propagieren jetzt korrekt als 500. **Out of Scope:** Generator-Erzwingung weiterhin offen (Sub-Slice 20b). **Verifikation:** 5 neue Cases in [`backend/tests/test_quota_persistence.py`](backend/tests/test_quota_persistence.py), `uv run pytest -x -q` 1276 passed (2 skipped), `ruff check` clean, `dump_schemas` ohne Drift. Arbeitsprotokoll: `docs/2026-05-03-task-22-quota-persistence-arbeitsprotokoll.md`05-03-task-22-quota-persistence-arbeitsprotokoll.md).

- **Sub-Slice 21 — OASIS-DB-Pfad pro Sim (read-only-FS-Hotfix).** Sim-Subprozess crashed nach erfolgreicher Persona-Generation am ersten OASIS-`step()` mit `OSError: [Errno 30] Read-only file system: '/app/backend/.venv/lib/python3.11/site-packages/oasis/data'`. OASIS' [`get_db_path()`](backend/.venv/lib/python3.11/site-packages/oasis/social_platform/database.py) versucht eine SQLite-DB **innerhalb der venv** anzulegen (`site-packages/oasis/data/social_media.db`), was im Prod-Container mit `read_only: true` aus [`docker-compose.yml:23`](docker-compose.yml:23) scheitert. OASIS hat einen sauberen ENV-Override `OASIS_DB_PATH`, der den `mkdir`-Branch komplett umgeht — der wurde im `SimulationRunner.start_simulation`-Subprozess-Env aber nicht gesetzt. Zwei neue Standalone-Helper in [`backend/app/services/simulation_runner.py`](backend/app/services/simulation_runner.py): `_compute_oasis_db_path(sim_dir)` legt `<sim_dir>/oasis_db/social_media.db` an (idempotent, mkdir vorab — OASIS macht selbst kein mkdir wenn ENV gesetzt ist) und `_inject_oasis_db_env(env, sim_dir)` setzt `OASIS_DB_PATH` nur, wenn der User es nicht selbst überschrieben hat (z. B. via Compose-Env oder `.env`). Aufruf direkt vor `subprocess.Popen` neben `PYTHONUTF8`/`PYTHONIOENCODING`. **Bonus — Sim-Isolation:** Vorher teilten sich alle Sims eine DB im Site-Packages — bei parallelen Runs Race-Condition auf SQLite-Locks. Jetzt hat jede Sim ihre eigene DB unter `<uploads>/simulations/<sim_id>/oasis_db/`. **Verifikation:** 4 neue Cases in [`backend/tests/test_simulation_runner_oasis_db_path.py`](backend/tests/test_simulation_runner_oasis_db_path.py), `uv run pytest -x -q` 1271 passed (2 skipped, beide Redis-Integration), `ruff check app/ tests/` clean. Arbeitsprotokoll: `docs/2026-05-03-task-21-oasis-db-path-arbeitsprotokoll.md`05-03-task-21-oasis-db-path-arbeitsprotokoll.md).

- **Sub-Slice 19 — Gunicorn-Worker-Timeout für LLM-Streaming.** Nach Sub-Slice 18 startete der Prod-Stack sauber, aber jeder LLM-Streaming-Call (`POST /api/graph/ontology/generate`, Report-Agent, Persona-Generation) kollabierte nach exakt 30 s mit `[CRITICAL] WORKER TIMEOUT (pid:73) … SystemExit: 1`. Grund: Im Dockerfile-CMD aus 18 war kein `--timeout` explizit gesetzt, sync-Worker-Default 30 s griff. `llm_client.chat()` blockiert legitim im `httpcore`-`recv()` während des Streams — Master killte den Worker mitten im Antwortpfad. [`Dockerfile`](Dockerfile) prod-Stage CMD um `--timeout 600 --graceful-timeout 30` erweitert (10 min Worker-Timeout deckt 15 k+-Token-Inputs gegen lokale Ollama-Modelle ab; 30 s graceful für SIGTERM bei Compose-Restart). Verifikation via `docker exec agora ps -ef | grep gunicorn` zeigt Flags aktiv, `/health` weiterhin OK. **Out of Scope (Folge-Slice 20):** Migration auf gevent-Worker (`-k gevent --workers 1 --worker-connections 100`) wie in `docs/2026-04-29-prod-slice2-gunicorn.md`04-29-prod-slice2-gunicorn.md) ursprünglich vorgesehen — dann sind Streams non-blocking und der hohe Timeout wird unnötig. Caveats (gevent-Monkey-Patching, Neo4j-Driver-Kompatibilität, OASIS-Subprozess-Entkopplung) sind im Slice-2-Plan dokumentiert. Arbeitsprotokoll: `docs/2026-05-03-task-19-gunicorn-timeout-arbeitsprotokoll.md`05-03-task-19-gunicorn-timeout-arbeitsprotokoll.md).

- **Sub-Slice 18 — Prod-Boot-Fix (Compose + Dockerfile).** `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` führte in einen Restart-Loop. Drei kaskadierende Defekte, alle in einem Commit gefixt: (1) [`Dockerfile`](Dockerfile) base-Stage bekommt `ENV UV_HTTP_TIMEOUT=600`, weil der uv-Default von 30 s den `nvidia-cudnn-cu12`-Download (~700 MB) auf langsamen Leitungen abschoss. (2) [`Dockerfile`](Dockerfile) prod-Stage CMD von `["uv", "run", ...]` auf direkten Binary-Aufruf `["/app/backend/.venv/bin/gunicorn", ...]` umgestellt — `uv run` triggerte bei jedem Container-Start einen `.venv`-Sync (lud sogar Dev-Deps `lupa`/`ruff` nach), der am `read_only: true` aus [`docker-compose.yml:23`](docker-compose.yml:23) scheiterte. (3) [`docker-compose.prod.yml:44–45`](docker-compose.prod.yml:44) hatte `LLM_BASE_URL=http://ollama:11434/v1` und `EMBEDDING_BASE_URL=http://ollama:11434` hardgecoded — erwartet einen Sibling-Container `ollama` im `agora_default`-Netz, widerspricht aber [README.md:175](README.md:175) und [`docs/deployment-prod-like.md:289–296`](docs/deployment-prod-like.md:289), die Host-Ollama via `host.docker.internal` als Standardpfad festlegen. Auf `host.docker.internal` zurückgesetzt; `extra_hosts: host-gateway` aus dem Default-Compose ([`docker-compose.yml:38–39`](docker-compose.yml:38)) wird per Compose-Merge ins Prod-Override übernommen (kein `!reset` nötig). Inline-Kommentar auf Variante-A/Variante-B umgestellt — Sibling-Container-Setup bleibt dokumentiert, ist aber nicht mehr versteckter Default. **Verifikation:** `docker compose ... up -d --build agora` läuft sauber durch, `docker exec agora curl -fsS http://localhost:5001/health` liefert `{"service":"Agora Backend","status":"ok"}`, Worker-Boot-Log zeigt `Embedding configuration validated (qwen3-embedding:4b → 2560 dims)`, Neo4j+Redis-Connections, Static-SPA-Serving aus `/app/frontend/dist`. Boot-Zeit ~22 s, FS bleibt `read_only: true`. **Out of Scope:** Reverse-Proxy (offen [#106](https://github.com/arn0ld87/Agora/issues/106)), `--preload` für gunicorn (Fork-Safety der Neo4j/Redis-Pools verifizieren — Folge-Slice). Arbeitsprotokoll: `docs/2026-05-03-task-18-prod-bootfix-arbeitsprotokoll.md`05-03-task-18-prod-bootfix-arbeitsprotokoll.md).

- report_agent: kein dekoratives `global_items[:2]`-Fallback mehr; orphan-Claim erhält `low`-Confidence + `no_direct_evidence_bound`-Audit-Entry — Sub-Slice 07, Refs #105.

- **Sub-Slice 02a (PLAN.md Layer 0 Task 02 · Schema-Version-Drift, Refs #107).** Hebt persistierte und exportierte Evidence-Maps konsequent auf `schema_version=2` und schließt damit den Drift, den der ChatGPT-Audit am echten Code belegt hat ([`backend/app/services/report_agent.py:564`](backend/app/services/report_agent.py:564), [`:567`](backend/app/services/report_agent.py:567), [`:1127`](backend/app/services/report_agent.py:1127), [`backend/app/api/report.py:379`](backend/app/api/report.py:379)). Neuer Migrations-Helper [`backend/app/services/evidence_migrations.py`](backend/app/services/evidence_migrations.py) (`migrate_v1_to_v2` + Konstante `CURRENT_SCHEMA_VERSION = 2`) — idempotent, in-place, hebt zusätzlich Section-Einträge (Refs #107). Aufrufstellen: (a) `ReportAgent.generate_report` migriert beim Laden persistierter Evidence-Maps (`report_agent.py:1127`), bevor `or {…}` greift; (b) `EXPORT_SCHEMA_VERSION` setzt jetzt auf `CURRENT_SCHEMA_VERSION`, der JSON-Export-Endpoint `GET /api/report/<id>/export?format=json` migriert die Evidence-Map vor der Auslieferung. `_save_evidence_section` setzt seinen Default und neue Section-Einträge auf v2. Tests: 8 neue Cases in [`backend/tests/test_evidence_migration.py`](backend/tests/test_evidence_migration.py) (None, v1→v2, v2-Idempotenz, fehlender `schema_version`-Key, fehlende/`null` Sections, Round-Trip-Erhalt der Claim-Felder); bestehende Export-Assertion in [`backend/tests/test_report_export.py`](backend/tests/test_report_export.py) auf `schema_version=2` plus zusätzliche Assertion auf `payload["evidence"]["schema_version"] == 2`. **Auto-Close erst** mit Sub-Slice 02b/02c (API-Boundary-Validierung via Pydantic, Persistenz-Round-Trip im `ReportManager`); deshalb hier nur `Refs #107`. Arbeitsprotokoll: `docs/2026-05-02-task-02a-schema-version-drift-arbeitsprotokoll.md`05-02-task-02a-schema-version-drift-arbeitsprotokoll.md).

- **Issue #133 Followup (Gemini-Findings auf PR #155).** Drei Sub-Slices, drei kleine Commits ohne neue Doku-Surfaces — [Arbeitsprotokoll: `docs/2026-05-02-issue133-followup-arbeitsprotokoll.md`05-02-issue133-followup-arbeitsprotokoll.md). **SUB1 (Cross-Field state-aware):** [`backend/app/services/settings_validator.py`](backend/app/services/settings_validator.py) `validate_payload(...)` bekommt einen optionalen `effective_settings`-Parameter, der vor dem `EMBEDDING_MODEL` ↔ `VECTOR_DIM`-Check über das Payload gemergt wird. Vorher griff die Regel nur, wenn beide Felder im selben PUT lagen — ein Partial-Update mit nur einer Seite konnte einen Mismatch gegen den persistierten Gegenpart in `instance/settings.json` schreiben (Gemini-Finding High). [`backend/app/services/settings_layer.py`](backend/app/services/settings_layer.py) liefert dafür eine neue `effective_snapshot()`-Methode (alle non-secret Felder mit ihrem aktuell effektiven Wert inkl. Defaults); [`backend/app/api/settings.py`](backend/app/api/settings.py) reicht den Snapshot in `validate_payload`. Wording-Fix für die `null`-Errormessage: vorher hieß es „Feld weglassen, um den Default wiederherzustellen", was nicht stimmte (PUT macht ein Merge-Update, weglassen lässt den Override stehen) — Text auf neutrale Form gekürzt. **SUB2 (Atomic-Write tmp-Cleanup):** `_write_file_layer_atomic` in `settings_layer.py` umschließt den Schreibpfad mit `try/finally` und unlinked die `settings.*.json.tmp`, falls `json.dump`/`fsync` vor dem `os.replace` scheitert — das Verzeichnis bleibt sauber statt mit `.tmp`-Resten zu verwaisen (Gemini-Finding Medium). **SUB3 (GitGuardian-Whitelist):** Neue [`.gitguardian.yaml`](.gitguardian.yaml) listet die vier Settings-Test-Files mit ihren synthetischen Marker-Strings (`new-pw`, `tok-xyz`, `super-secret`) als `ignored-paths` — Production-Code bleibt voll im Scan. Tests: +1 API-Test (Partial-Update wird gegen Persisted-State abgewiesen), +2 Validator-Tests (Partial mit Mismatch + ohne Beteiligung der Cross-Field-Felder), +3 Layer-Tests für `effective_snapshot`, +1 Persistence-Test für tmp-Cleanup nach forced exception. Refs #133.

- **Slice 11 (Repo-Review-Folge, Versions-Sync): pyproject + `__version__` auf 0.9.0 hochgezogen.** Folge-Slice aus F4: [`backend/pyproject.toml`](backend/pyproject.toml) `version = "0.6.1"` → `"0.9.0"`, [`backend/app/__init__.py`](backend/app/__init__.py) `__version__ = "0.8.0"` → `"0.9.0"`, `backend/uv.lock` via `uv lock` aktualisiert (`agora-backend v0.6.1 -> v0.9.0`, sonst keine Drift). Damit stehen alle sechs Versionsquellen aus [`docs/release-process.md`](docs/release-process.md) auf `0.9.0` (bzw. `v0.9.0 alpha` in den i18n-Locales). `/api/status.backend.version` lieferte vorher `"0.8.0"` und stimmt jetzt mit dem Tag-Stand. Bestehender `tests/test_status.py` liest `__version__` dynamisch — Pin-Bruch ausgeschlossen. Arbeitsprotokoll: `docs/2026-05-01-slice-11-version-sync-arbeitsprotokoll.md`05-01-slice-11-version-sync-arbeitsprotokoll.md).


### Performance
- usePolling: neuer `pauseWhenHidden`-Default (`true`) pausiert alle Polling-Loops bei inaktivem Browser-Tab und springt mit Catch-up-Tick wieder an, sobald der Tab wieder sichtbar wird. Schätzung: 40–60 % Request-Reduktion bei Multi-Tab-Nutzung. Opt-out via `{ pauseWhenHidden: false }` für Loops, die im Hintergrund laufen müssen. Kein bestehender Aufrufer benötigt den Opt-out. Backwards-Compat-Hinweis: Default-Verhalten ändert sich (vorher: immer aktiv; nachher: pausiert im Hintergrund). Arbeitsprotokoll: `docs/2026-05-03-slice-J4-arbeitsprotokoll.md`05-03-slice-J4-arbeitsprotokoll.md). (Sub-Slice J.4, schließt #222)


- Step4Report: agent-log-Polling-Intervall von 1500 auf 2500 ms angeglichen (Konsistenz mit statusPolling). Reduziert Backend-Last in der Report-Phase um ~33 %. (Sub-Slice J.3, schließt #221)


### Build
- **Sub-Slice 15 (Layer 4, Task 15): Step4Report.vue strict-Zod — Export validiert.** `frontend/src/components/Step4Report.vue` importiert jetzt `parseReportContract` aus `../contracts/reportContract`. `downloadCombinedJson` validiert den JSON-Export-Response gegen den vollständigen `ReportContractSchema`-Envelope; bei Mismatch wird `recordSchemaError('export', ...)` gesetzt und der Download abgebrochen (statt ungültigen Daten zu liefern). Keine Änderung an den bestehenden `.parse()`-Aufrufen für Report/Evidence/Outline — diese waren bereits strikt. TypeScript clean, 146 Frontend-Tests grün, Build success. Arbeitsprotokoll: `docs/2026-05-03-task-15-step4report-strict-zod-arbeitsprotokoll.md`05-03-task-15-step4report-strict-zod-arbeitsprotokoll.md). Refs #15.
- **Sub-Slice 46 (F2.1, M9 #3): VITE_AGORA_TOKEN per ALLOW_BUILD_TIME_TOKEN-Gate.** [`Dockerfile`](Dockerfile) `prod-builder`-Stage gated den Build-Arg-Pfad jetzt hinter einem expliziten `ARG ALLOW_BUILD_TIME_TOKEN=false` (Default). Im Default-Pfad wird `VITE_AGORA_TOKEN` ignoriert; das Frontend-Bundle bekommt einen leeren Token einkompiliert und der Operator muss den Token zur Laufzeit über das UI setzen (siehe `setAgoraToken` in [`frontend/src/api/index.ts`](frontend/src/api/index.ts)). Opt-In via `--build-arg ALLOW_BUILD_TIME_TOKEN=true --build-arg VITE_AGORA_TOKEN=...` für Single-User-Tailnet-Deploys. [`docs/security-hardening.md`](docs/security-hardening.md) erweitert um F2.1-Section mit Default- und Opt-In-Pfad. Frontend-Code unangetastet (Memory-Mode-Pfad existiert seit P0.2). Refs PLAN.md F2.1.

- **Sub-Slice 45 (F1.1, M9 #2): Reverse-Proxy-Sidecar (Closes #106).** Neue Datei [`deploy/nginx/agora.conf`](deploy/nginx/agora.conf) mit SSE-tauglichen Proxy-Routes (`proxy_buffering off`, `proxy_read_timeout 600s` für `/api/simulation/<id>/stream`), gzip für statisches Frontend-Bundle, eigener `/healthz`-Endpoint für Container-Healthcheck. Neue Datei [`deploy/compose/docker-compose.prod-with-proxy.yml`](deploy/compose/docker-compose.prod-with-proxy.yml) ergänzt einen `nginx:alpine`-Sidecar zum Prod-Stack: Bind-Mounts auf `frontend/dist` (Operator muss `npm run build` lokal vorab laufen lassen) und auf die nginx-Conf, `agora`-Backend-Ports per `!reset []` komplett gestrichen — Backend ist nur noch über das Compose-Netz erreichbar. [`docs/deployment-prod-like.md`](docs/deployment-prod-like.md) erweitert um drei symmetrische Sections **Sidecar-Nginx**, **Traefik-Labels**, **Tailscale-Funnel**. [`scripts/verify-deploy.sh`](scripts/verify-deploy.sh) auto-detected den Proxy-Stack und smoket `:80/healthz` + `:80/health` + `:80/`. [`.github/workflows/docker-image.yml`](.github/workflows/docker-image.yml) bekommt einen neuen Job `prod-proxy-smoke`, der den vollen Drei-File-Compose-Stack hochfährt und gegen den Proxy smoket. Arbeitsprotokoll: `docs/2026-05-03-slice-45-reverse-proxy-arbeitsprotokoll.md`05-03-slice-45-reverse-proxy-arbeitsprotokoll.md). Refs PLAN.md F1.

- Sub-Slice 48 — `.gitattributes` neu am Repo-Root: `design/**` als `linguist-vendored=true` (statische HTML/JSX/CSS-Mockups, ~4400 LOC inkl. 1:1-Duplikat unter `design/Agora/export/src/`, keine Imports aus `backend/` oder `frontend/src/`); `schemas/**` als `linguist-generated=true` (auto-generiert via `app.contracts.dump_schemas`). Zweck: GitHub-Sprach-Statistik und LOC-Audits werden ehrlich, keine Verhaltensänderung. Folge-Slices [#201](https://github.com/arn0ld87/Agora/issues/201) (`_sim_common.py`-Extraktion), [#202](https://github.com/arn0ld87/Agora/issues/202) (`report_agent.py`-Paket-Split), [#203](https://github.com/arn0ld87/Agora/issues/203) (`Step2EnvSetup.vue`-Composables) als Hot-Spot-Backlog angelegt. Branch-Name `feat/task-44-design-vendored` ist Legacy; Task-Nummer wurde nach Kollision mit Slice-44-Doku-Sync auf 48 umgezogen. Arbeitsprotokoll: `docs/2026-05-03-task-48-design-vendored-arbeitsprotokoll.md`05-03-task-48-design-vendored-arbeitsprotokoll.md).
- Sub-Slice 43 — `mypy>=1.10` als offizielle dev-Dependency in [`backend/pyproject.toml`](backend/pyproject.toml) (sowohl `[project.optional-dependencies].dev` als auch `[dependency-groups].dev`) plus pragmatische `[tool.mypy]`-Baseline (`python_version = "3.11"`, `ignore_missing_imports = true`, `follow_imports = "silent"`); per-Modul-Override silenced den einen vorhandenen `attr-defined`-Finding in `app.contracts.dump_schemas` (Pydantic-`type`-Narrow), bleibt aber explizit als pragmatische Übergangslösung markiert. CLAUDE.md-Standard-Check `uv run mypy app` und alle `agora-*-worker`-Verify-Schritte sind damit ohne `--with mypy`-Workaround lauffähig. `uv lock` + `uv sync --group dev` sauber, `uv run mypy app/contracts/` clean (7 Files). Keine bestehenden Code-Pfade angefasst — Tightening folgt in einem separaten Slice.


### Documentation
- **Sub-Slice 44 (F5, M9 #1): Doku-Sync — STATUS.md, ROADMAP-Refresh, CONTRIBUTING.md.** Neue Datei [`docs/STATUS.md`](docs/STATUS.md) als Single Source of Truth für Test-Counts (1330 Backend collected, 17 Frontend Spec-Files) und Versionsstände (0.9.0); neues Skript [`scripts/sync-status.sh`](scripts/sync-status.sh) regeneriert sie idempotent (`--check`-Modus für CI-Drift). [`ROADMAP.md`](ROADMAP.md) auf v0.9.0+ / 2026-05-03 gehoben mit Now/Next/Later-Block (M9–M13), 0.5/0.6-Linien-Beschreibung in expliziten `## Historie`-Block verschoben. Neue Datei [`CONTRIBUTING.md`](CONTRIBUTING.md) am Repo-Root erklärt Datei-Rollen, Branch-Hygiene, Quality-Gates. README + CLAUDE.md verweisen jetzt nur noch auf STATUS.md, keine Inline-Zahlen mehr (vorher: README sagte 1383 Tests, CLAUDE.md sagte 1289+141 — Drift damit aufgelöst). Slice ist auf 44 umnummeriert, weil parallel der mypy-Tooling-Slice ebenfalls als „Sub-Slice 43" gemerged wurde. Arbeitsprotokoll: `docs/2026-05-03-slice-44-doku-sync-arbeitsprotokoll.md`05-03-slice-44-doku-sync-arbeitsprotokoll.md). Refs PLAN.md F5.
- Sub-Slice 37 — Graph-Diff Modell-Spike (Refs #74): Neue Doku `docs/2026-05-03-task-22-graph-diff-spike.md`05-03-task-22-graph-diff-spike.md) definiert Vergleichsdimensionen zwischen zwei Graph-Snapshots (Added/Removed/Reinforced/Weakened-Edges, Node-Property-Drift, Cluster-Shifts, Bridge-Agent-Shifts, Density-Delta, New/Removed-Clusters). Datenmodell skizziert: `GraphDiff` mit `snapshot_a`/`snapshot_b` (je `GraphSnapshot`) + Kanten-/Knoten-/Cluster-Diffs. API-Schnitt: `GET /api/simulation/<sim_id>/graph-diff?branch_a=<id>&branch_b=<id>` mit Error-Cases (404 branch nicht gefunden, 400 inkompatible Netzwerk-Versionen, 422 unvollständiger Graph-Status). 6 offene Fragen für Implementation (#74 API, #76 UI): Edge-Identität (UUID vs. Composite-Key), Cluster-Matching-Strategie, Snapshot-Quelle, Node-Isolation-Definition, Cluster-Seed-Nondeterminismus, Performance bei 10k+ Nodes.


### Tests
- Sub-Slice 11 — Voice-Lint CI-Check für DACH-Voice-Register (Layer 2, Task 11): Neue Contract-Tests in `tests/contracts/test_voice_register.py` (9 Tests, 2 Klassen). `TestVoiceRegisterContract` pinnen die 4 erlaubten Werte (`formal-de`, `neutral-de`, `technical-de`, `skeptisch-de`), rejecten ungültige Werte, prüfen Default (`neutral-de`) und Legacy-Compat (`None`). `TestVoiceRegisterGeneration` validiert, dass `_rule_based_voice_register` nur erlaubte Werte liefert und deterministisch ist. Keine Code-Änderungen — reiner Test-/Lint-Slice. Arbeitsprotokoll: `docs/2026-05-03-task-11-voice-lint-arbeitsprotokoll.md`.
- Sub-Slice 35 — Tests für Resume/Stop-Endpoints und HistoryDatabase-Buttons (Closes #64, Layer 7): 6 Backend-Tests in `tests/api/test_runs_resume_stop.py` (404/409-Negativpfade für `/resume` und `/stop`), 4 Frontend-Tests in `src/components/__tests__/HistoryDatabase.spec.ts` (Button-Visibility, resumeRun-Call, stopRun/confirm-Gating).


### Changed
- Persona-Generierung: Namen folgen DACH-Mikrozensus-Verteilung (~26 % Migrationshintergrund) statt nur deutsch-sprachig (Sub-Slice F, schließt #214). Quoten in `persona_demographics.py`, Prompt zieht aus Single Source of Truth. Fallback-Pfad (`_pick_dach_name`) und alle 4 Prompt-Varianten (DE+EN × Individual+Group) vollständig migriert. `classify_name_origin()` als regelbasierter Bucket-Klassifizierer ohne LLM. `print()`-Statements im Profil-Generator durch `logger.info()`/`logger.debug()` ersetzt.

- **Dev-Stack:** `docker-compose.override.yml` ist jetzt repo-getrackt (aus `.gitignore` entfernt) — Vite-HMR funktioniert neu ohne `docker compose build` bei Frontend-Edits. Lessons-Learned aus PR #207 & PR #208 (TDZ-Bug-Hunt 2026-05-03). Datei mit Bind-Mounts für `frontend/src`, `frontend/public`, `frontend/index.html`, `frontend/vite.config.js`, `frontend/tsconfig.json`. `node_modules` bewusst nicht gemountet (Container-Installation gewinnt). Der bisher persönliche Dev-Override wird damit für alle Devs Default. `docker-compose.prod.yml` bleibt unverändert — Prod-Pipeline nutzt explizit `-f docker-compose.yml -f docker-compose.prod.yml` und ignoriert `override.yml`. Arbeitsprotokoll: `docs/2026-05-03-dev-stack-frontend-bindmount-arbeitsprotokoll.md`. (Sub-Slice DEV-01)

- Sub-Slice 32 — Contradiction-Penalty in compute_confidence()-Aufruf verdrahtet (report_agent.py:637): detect_contradiction_penalty(evidence_items) speist jetzt den bisher hardcoded `0.0`-Hook. Audit-Trail-Eintrag bei Penalty>0. Closes #105 (Layer 1).

- Sub-Slice 30 — Step4-Report-Logs auf Sticky-Scroll: useIncrementalLogPolling akzeptiert optionalen stickyScroll-Parameter (Backwards-Compat erhalten); Step4Report.vue verdrahtet je eine useStickyScroll-Instanz für Agent- und Console-Logs mit StickyScrollBanner. Closes #141 (Layer 8).
- Step4Report.vue: strict-Zod-Parse fuer Report + EvidenceMap + Outline; toleranter Fallback (claim.confidence, evidence_items, JSON.stringify-Snippet, silent catch) raus; Schema-Mismatch zeigt UI-Banner mit ZodError-Issue-Pfaden. (Sub-Slice 15, Closes #172, Layer 4)
- oasis_profile_generator + persona_contract: voice_register-Pflichtfeld pro Persona (formal-de | neutral-de | technical-de | skeptisch-de) — OasisAgentProfile erweitert, JSON-Spec im Individual- und Group-Persona-Prompt um Pflichtfeld + Register-Anker, Validation in `_validate_profile_metadata`, Auto-Fallback `neutral-de` mit `logger.warning` bei fehlendem/ungültigem Wert, rule-based-Fallback heuristisch, PersonaModel-Default `neutral-de` für Backwards-Compat (Sub-Slice 10, Closes #167, Layer 2)
- confidence_calculator: Match-Score-Cap (alle < 0.55 → max 0.69) + Verified-Quellen-Gate (>= 2 unabhaengige Quellen noetig) (Sub-Slice 08, Closes #165, Refs #105)
- report_prompts, report_agent, graph_tools: Scenario-Vokabular ersetzt „future prediction"/„rehearsal of the future"/„god's eye view" — entfernt Forecast-Autoritätsclaims aus LLM-Prompts (8 Prompt-Phrasen) und Report-Headings (Default Fallback Outline Z. 775–782, GraphAnalysisResult.to_text() Z. 168–177) (Sub-Slice 09 + Erweiterung, Layer 2).
- report_agent: EvidenceMapModel-Validation am Schreib-Boundary (`_init_evidence_map`, `_save_evidence_section`, Tool-Loop-Fallback) — Sub-Slice 02c, Refs #107.
- **Sub-Slice 02b (Refs #107): `ReportContractModel`-Envelope für JSON-Export.** Der Endpoint [`backend/app/api/report.py`](backend/app/api/report.py) `GET /api/report/<id>/export?format=json` baut den Envelope nicht mehr als rohes Dict, sondern via `ReportContractModel.model_dump_json(indent=2)` aus [`backend/app/contracts/`](backend/app/contracts/). `schema_version` ist damit per `Literal[2]` strikt typgepinnt — der frühere Drift-Vektor (`EXPORT_SCHEMA_VERSION = 1` in `api/report.py:379`) ist nicht mehr re-introducierbar. Neuer Boundary-Mapper `_map_outline_for_contract` löst die strukturelle Diskrepanz zwischen `ReportSection.to_dict()` (`{"title", "content"}`) und `ReportOutlineSectionModel` (`{"title", "description"}` mit `extra="forbid"`) am API-Boundary, ohne die Dataclass-Konsumenten anzufassen — Storage-Reshape ist explizit 02c-Scope. Helper `_build_export_envelope(report_obj, raw_evidence_map)` strikt-validiert `ReportModel`, läuft `migrate_v1_to_v2` vor `EvidenceMapModel.model_validate` und droppt persistierte v1-geformte Evidence-Maps (claim_id `c1`, `section_index=0`, fehlendes `section_summary`) bewusst nur mit `logger.warning` aus dem Envelope, statt 500 für Bestands-Reports zu werfen — der `try/except`-Pfad fliegt mit 02c raus, sobald der `ReportManager` die Persist-Form auf den Vertrag hebt. [`backend/tests/test_report_export.py`](backend/tests/test_report_export.py): Fixture jetzt v2-vertragsform — `outline.sections` mit 2 Einträgen (`min_length=2`), Evidence-Map mit `simulation_id`/`section_index=1`/`section_summary`/`claim_id="claim_01"`/`audit_trail=[]` und Evidence mit `match_score=0.7`+`supports_claim=True`; `test_export_json_returns_combined_envelope` assertet zusätzlich `payload["report"]["schema_version"] == 2`. **Verifikation:** `uv run pytest -x -q` 913 Backend-Tests grün (2 skipped, beide Redis-Integration aus dem Schwesterprojekt), `uv run python -m app.contracts.dump_schemas` sauber, `git diff schemas/` leer (Vertrags-Shape unverändert — wir konsumieren, definieren nicht), `rg '"schema_version": 1' backend/app/` leer, `ruff check app/api/report.py` clean. Out of Scope: Persist-Boundary in `ReportManager`, Generator-Output-Validation in `ReportAgent.generate_report`, Frontend-Strict-Mode (Task 04). Arbeitsprotokoll: `docs/2026-05-02-task-02b-export-contract-arbeitsprotokoll.md`05-02-task-02b-export-contract-arbeitsprotokoll.md).


### Added
- Sub-Slice 42 — BranchComparison Pydantic-v2-Contracts (Refs #66, Layer-7-Vorarbeit für Task 24): Neue Modelle in [`backend/app/contracts/branch_comparison.py`](backend/app/contracts/branch_comparison.py) (`BranchComparison`, `BranchMetrics`, `SegmentReach`, `ComparisonDeltas`, `ClusterChange`) decken das Datenmodell aus dem Compare-Spike `docs/2026-05-03-task-23-compare-model-spike.md` § 3 ab. Reuse von `ClusterSummary` aus [`backend/app/contracts/graph_diff.py`](backend/app/contracts/graph_diff.py) (Single Source of Truth für Cluster-Konzept). Alle Modelle mit `extra="forbid"` und `Literal`-typisierten Confidence-Distribution-Keys. Schema-Dump erzeugt [`schemas/branch-comparison.schema.json`](schemas/branch-comparison.schema.json). Contract-Tests in [`backend/tests/contracts/test_branch_comparison.py`](backend/tests/contracts/test_branch_comparison.py).

- Sub-Slice 40 — GraphDiff Pydantic-v2-Contracts (Refs #74, Layer-7-Vorarbeit für Task 22): Neue Modelle in [`backend/app/contracts/graph_diff.py`](backend/app/contracts/graph_diff.py) (`GraphDiff`, `GraphSnapshot`, `EdgeData`, `EdgeReinforcement`, `EdgeWeakening`, `NodePropertyShift`, `ClusterShift`, `ClusterSummary`, `BridgeAgentShift`, `GraphDiffMetrics`) decken das Datenmodell aus dem Spike `docs/2026-05-03-task-22-graph-diff-spike.md` § 3 ab. Alle Modelle mit `extra="forbid"`. Schema-Dump erzeugt [`schemas/graph-diff.schema.json`](schemas/graph-diff.schema.json). Contract-Tests in [`backend/tests/contracts/test_graph_diff.py`](backend/tests/contracts/test_graph_diff.py).

- Sub-Slice 33 — /api/runs erweitert: Filter (status, simulation_id, since, limit, offset), Status-Aggregation (?aggregate=status), Live-Metriken (eta_seconds, metrics, log_tail) im Detail-Endpoint. Pydantic-Verträge RunSummary/RunDetail/RunsListResponse/RunsAggregation in app/contracts/runs_contract.py + Zod-Spiegel runsContract.ts. Closes #62 (Layer 7).

- **Sub-Slice 31 — Security-Watchlist konsolidiert (Refs #121–#126, Layer 10).** Neue Doku `docs/2026-05-03-task-34-security-watchlist.md`05-03-task-34-security-watchlist.md): Übersicht aller 6 ignorierten CVEs (pillow 10.3.0, pytest 8.2.0, transformers 4.57.6, unstructured 0.13.7), uv.lock-Versionen, Pinning-Sources (camel-ai 0.2.78, camel-oasis 0.2.5, sentence-transformers 3.0.0), Risk-Levels (5× Medium, 1× Low), Deadlines (alle 2026-07-30, +90 Tage), wöchentliche pip-audit-Action, Hardstop-Bedingung. **Kein Dep-Upgrade in diesem Slice** — `pyproject.toml` und `uv.lock` unverändert. Issues bleiben offen, bis Upstream-Pins gelöst sind. (kein Closes — Watchlist nur)

- **Sub-Slice 29 — Spike-Dokument: Vergleichsmodell für Simulations-Branches (Closes #65, Layer 7).** Neue Doku `docs/2026-05-03-task-23-compare-model-spike.md`05-03-task-23-compare-model-spike.md) definiert Vergleichsmetriken zwischen zwei Branches (Polarisation/Echo-Chamber, Cluster-Struktur, Bridge-Agenten, Top-Themen, Confidence-Verteilung, Evidence-Coverage, Persona-Reach-Index, Interaction-Density, Contradiction-Penalty). Datenmodell skizziert: `BranchComparison` mit `metrics_a`/`metrics_b` (je `BranchMetrics`) + `deltas` (signed Differences). API-Schnitt: `GET /api/simulation/<id>/compare?branch_a=<id>&branch_b=<id>` mit Error-Cases (404 not found, 400 schema-incompat, 422 incomplete-state). 6 offene Fragen für Implementation (#66 API, #67 UI): Segment-Klassifizierung, Window-Sliding, Cluster-Matching-Strategie, Confidence-Summary, Contradiction-Live-Status, Performance-Caching. Spike-Closure: alle Dimensionen identifiziert, Datenmodell definiert, API-Schnitt skizziert, Out-of-Scope explizit benannt.

- **Sub-Slice 25 — v1→v2 Report-Migration-Skript für Bestandsdaten (Closes #107, Layer 5).** Neues CLI [`backend/scripts/migrate_reports_v1_to_v2.py`](backend/scripts/migrate_reports_v1_to_v2.py) hebt persistierte v1-Evidence-Maps atomar auf `schema_version=2`: Backup `.v1.bak.json` (idempotent), Re-Validation via `EvidenceMapModel.model_validate`, `--dry-run`-Flag, atomic write via `os.replace`. Reuse `migrate_v1_to_v2()` aus `app.services.evidence_migrations` (kein Logik-Duplikat zur Runtime-Migration in `api/report.py:434`). 6 neue Tests in [`backend/tests/scripts/test_migrate_reports_v1_to_v2.py`](backend/tests/scripts/test_migrate_reports_v1_to_v2.py): Roundtrip, Idempotenz, Dry-Run, kaputtes JSON, Mixed-Dir, Contract-Re-Validation. **Verifikation:** `uv run pytest -x -q` 1282 passed, 9 skipped, `ruff check` clean, `dump_schemas` ohne Drift. Arbeitsprotokoll: `docs/2026-05-03-sub-slice-25-arbeitsprotokoll.md`05-03-sub-slice-25-arbeitsprotokoll.md).

- **Sub-Slice 23 — Vite-Dev-Server für Tailscale-Zugriff (`*.ts.net`).** [`frontend/vite.config.js`](frontend/vite.config.js) setzt jetzt `server.host: true` (Bind auf alle Interfaces statt nur Loopback) und `server.allowedHosts: ['.ts.net', 'localhost', '127.0.0.1']`, damit der Vite-Dev-Server Anfragen von Tailscale-Magic-DNS-Hosts (`<machine>.<tailnet>.ts.net`) annimmt. Vite v5+ blockiert sonst per Host-Header-Check fremde Hosts mit `Blocked request. This host is not allowed`. **Sicherheits-Notiz:** Dev-only — Prod liefert das gebaute Bundle aus dem Container, ist davon nicht betroffen. `host: true` öffnet den Dev-Server für alle erreichbaren Netze; im Single-User-Tailnet-Setup OK, in Multi-User-LANs sollte das per Compose-Override eingeschränkt werden.

- **Sub-Slice 20c — `PersonaQuotaPlan` Frontend-Editor in Step 2.** Schließt die 20a/20b/22-Pipeline ab. Vorher war der Plan nur per Postman/`curl`-Body setzbar — praktisch unbenutzbar. Neu: [`frontend/src/contracts/personaQuotaContract.ts`](frontend/src/contracts/personaQuotaContract.ts) als Zod-Spiegel zu `schemas/persona-quota-plan.schema.json` (1:1 zu Pydantic-Vertrag, `superRefine` für `total != sum(targets)` und leere `targets`), plus Helper `buildQuotaPlanFromEntries(entries)` für UI-State → API-Body-Konversion. [`Step2EnvSetup.vue`](frontend/src/components/Step2EnvSetup.vue) bekommt optionalen Toggle „Persona-Quote pro Segment erzwingen" mit Liste von `[segment-name] [count] [−]`-Zeilen, `+`-Button, Total-Anzeige und ⚠-Hint bei Validierungsfehler. LocalStorage-Persistenz unter `agora.quotaPlan`, Reload-Resilience via `Object.entries(targets)` (insertion-order). `startPrepare()` validiert client-seitig vor dem API-Call, hängt `payload.quota_plan` nur bei erfolgreicher Validierung an — verhindert unnötige HTTP-400-Roundtrips. **Verifikation:** 10 neue Cases in [`frontend/src/contracts/__tests__/personaQuotaContract.spec.ts`](frontend/src/contracts/__tests__/personaQuotaContract.spec.ts), `npm test -- --run` 16 Files / 135 Tests grün, `npm run build` clean (Bundle unverändert), `npm run lint` clean. Backend-Regression `uv run pytest -x -q` 1283 passed. **Pipeline jetzt komplett:** Slice 06 (Contracts) → 20a (API) → 22 (Persistence) → 20b (Service) → 20c (Frontend). Arbeitsprotokoll: `docs/2026-05-03-task-20c-quota-frontend-arbeitsprotokoll.md`05-03-task-20c-quota-frontend-arbeitsprotokoll.md).

- **Sub-Slice 20b — `PersonaQuotaPlan` Generator-Erzwingung.** Vervollständigt die Quoten-Pipeline serverseitig (Sub-Slice 20c folgt für Frontend). Vorher: bei 16 Entitäten + `quota_plan.total = 50` lief Phase 2 weiter „1 Persona pro Entity", `_validate_persona_quota` (Sub-Slice 06) failte mit `ValidationError("Soll=50, Ist=16")` und der Run ging in `FAILED` — sauberer Drift-Marker, aber kein Fix. Neuer Helper [`_expand_entities_for_quota(entities, plan)`](backend/app/services/prepare_service.py) erweitert den Entity-Pool **vor** der Generation auf den Soll-Plan: pro Segment so viele Entities wie `plan.targets[seg]` vorgibt, Round-Robin durch den Segment-Pool wenn der Pool kleiner ist als die Quote — keine Synth-Entities (würde semantische KG-Verankerung aufgeben). Wenn ein Plan-Segment im Pool nicht existiert, propagiert ein `ValueError` mit Liste der verfügbaren Segmente — kein heimliches Reduzieren. Pool-Segmente ohne Plan-Eintrag werden gedroppt (Plan ist Source of Truth). `_phase_generate_profiles` bekommt `quota_plan`-kwarg und ruft den Expander direkt vor `generator.generate_profiles_from_entities` auf. `prepare_simulation` reicht den Plan an Phase 2 durch. Identitäts-Caveat bei Replikation: jeder Generator-Aufruf bekommt einen eigenen `user_id` (per `enumerate`-Index), bestehende Display-Name-/User-Name-Dedup-Logik im Generator ([`oasis_profile_generator.py` Z. 1269+](backend/app/services/oasis_profile_generator.py)) fängt LLM-Name-Kollisionen ab. **Out of Scope:** Frontend-Quoten-Editor in Step 2 (Sub-Slice 20c), Plan-Vorschlag aus Prompt parsen. **Verifikation:** 7 neue Cases in [`backend/tests/test_quota_generator_expansion.py`](backend/tests/test_quota_generator_expansion.py), `uv run pytest -x -q` 1283 passed (2 skipped), `ruff check` clean, `dump_schemas` ohne Drift. Arbeitsprotokoll: `docs/2026-05-03-task-20b-quota-generator-erzwingung-arbeitsprotokoll.md`05-03-task-20b-quota-generator-erzwingung-arbeitsprotokoll.md).

- **Sub-Slice 20a — `PersonaQuotaPlan` API-Pass-Through.** `POST /api/simulations/<id>/prepare` und der Restart-Pfad in `runs.py` lesen jetzt einen optionalen `quota_plan`-Body-Key, validieren ihn am API-Boundary via `PersonaQuotaPlan.model_validate` und reichen ihn an `SimulationManager.prepare_simulation(quota_plan=…)` und damit an den Service-Layer durch. Helper [`_parse_quota_plan`](backend/app/api/simulation_prepare.py) — fehlendes / `None` / leeres `{}`-Feld → `None` (Backwards-Compat); inkonsistenter Plan (`total != sum(targets)`, `count<1`, nicht-Dict) → HTTP 400 mit `ApiErrorCode.VALIDATION_FAILED`. Restart liest den Plan aus dem persistierten Run-Config-Snapshot — bewusst **kein** Silent-Fallback bei kaputtem Snapshot, ValidationError propagiert in den Restart und markiert ihn als `FAILED`, sonst würde ein Restart einen ursprünglich gesetzten Plan stillschweigend ignorieren. **Was 20a NICHT tut:** Generator-Erzwingung — bei 16 Entitäten + `quota_plan.total=50` läuft Phase 2 weiter „1 Persona pro Entity" und der Run failt im post-generation `_validate_persona_quota`-Check (Sub-Slice 06) als sauberer Drift-Marker. Generator-Modus „bis Quote auffüllen" ist Sub-Slice 20b, Frontend-Quoten-Eingabe in Step 2 ist Sub-Slice 20c. **Verifikation:** 9 neue Cases in [`backend/tests/api/test_simulation_prepare_quota.py`](backend/tests/api/test_simulation_prepare_quota.py), `uv run pytest -x -q` 1267 passed (2 skipped, beide Redis-Integration), `ruff check app/ tests/` clean, `dump_schemas` ohne Drift. Arbeitsprotokoll: `docs/2026-05-03-task-20a-quota-api-passthrough-arbeitsprotokoll.md`05-03-task-20a-quota-api-passthrough-arbeitsprotokoll.md).

- backend/tests/eval/: Baseline-Eval-Suite mit 3 Fixtures + Snapshot-Pinning gegen expected_metrics.json (evidence_coverage, claim_support_ratio, orphan_claim_rate, dedup_rate, concentration_index). check_evidence_quality.py liefert die zwei neuen Metriken jetzt mit aus. Voice-Lint im CI ist auf hart umgeschaltet (Wording-Glossar v1 + Layer 2 sauber). (Sub-Slice 17, Closes #174, Layer 5 abgeschlossen)
- frontend: klickbare Quotes mit source_id_anchor-Scroll. Evidence-Items mit quote-Feld rendern jetzt als <blockquote>; source_id_anchor-Buttons springen smooth zum Agent-Log-Entry, oeffnen Web-URLs in neuem Tab oder loggen KG-Anchors. Layer 4 abgeschlossen. (Sub-Slice 16b, Closes #173, Layer 4)
- frontend: ConfidenceBadge-Komponente (oklch-Pills mit ok/warn/err-Tokens) plus Hover-Popover für audit_trail. Step4Report.vue rendert pro Section ein Aggregat-Badge (mean confidence_score, label nach Schwelle). (Sub-Slice 16a, Refs #173, Layer 4)
- network_analytics: deterministisches Cluster-Naming via TF-Top-3 (Stopword-Filter DE+EN, Tie-Break alphabetisch). ClusterDef.label propagiert in compute_metrics + CSV-Export. (Sub-Slice 14, Closes #171, Layer 3)
- report_agent: Time-Series-Sampling (8 Bins ueber round_num/created_at) statt action_dicts[:8] — Burst-Verzerrung verhindern. Section-Dedup-Audit (cosine >=0.92, Jaccard-Fallback >=0.85) markiert Duplikat-Sections im audit_trail, ohne sie zu droppen. (Sub-Slice 13, Closes #170, Layer 3)
- evidence_item: Optional-Felder quote (Original-Zitat ≤500 chars) + source_id_anchor (≤200 chars) — Section-Builder leitet beide pro Evidence-Item ab; Frontend-Zod-Spiegel mit. (Sub-Slice 12, Closes #169, Layer 3)
- backend/scripts/check_voice.py: Voice-Lint als CI-Gate (Forecast + US-Marketing-Phrasen). Bootstrap-Soft, Hartmacher in Layer 5. (Sub-Slice 11, Closes #168)
- evidence_binder: `detect_contradiction_penalty(evidence)` — strukturierte Contradiction-Erkennung via Boolean-Flags + Stance-Konflikte (Sub-Slice 08, Refs #75)


- prepare_service: optionaler `quota_plan: PersonaQuotaPlan`-Parameter; nach Profil-Generation läuft `PersonaQuotaActual.model_validate` und propagiert ValidationError bei Drift/Toleranzbruch/unbekanntem Segment. OasisAgentProfile bekommt `segment`-Feld (Default = entity_type, None für generischen Fallback-Typ "Entity"). Backwards-Compat: ohne quota_plan keine Verhaltensänderung. (Sub-Slice 06)
- `llm_client.chat_json`: optionaler `schema`-Parameter (Pydantic-Modell oder JSON-Schema-Dict) → strict `response_format={"type": "json_schema", ...}`. Provider-Fallback auf json_object bei „unsupported"-Fehler, Pydantic-Validation bei Erfolg. `LLM_DISABLE_JSON_MODE` skipped beide Pfade. Backwards-Compat: bestehende Caller unverändert (Sub-Slice 05).
- **Issue #133 (SUB4): i18n DE/EN + Reload-Badges + Frontend-Tests.** Schließt die Settings-UI für #133 ab (Closes #133, Folge zu SUB1/SUB2/SUB3). [`frontend/src/i18n/locales/de.json`](frontend/src/i18n/locales/de.json) und [`frontend/src/i18n/locales/en.json`](frontend/src/i18n/locales/en.json) bekommen einen vollständigen `settings.*`-Block: Tab-Labels (`sections.<id>`), Tabellen-Header, Quellen-Labels (`Default`/`.env`/`Datei`/`Override` ↔ `Default`/`.env`/`File`/`Override`), Flag-Badges (`Reload nötig`/`Reload required` und `Secret`), Secret-Input-Placeholder, Bool-on/off, Modal-Body mit `<i18n-t>`-Slots für die `NEO4J_PASSWORD`/`AGORA_AUTH_TOKEN`-Hervorhebung, pluralisierter `dirtyCount` (`Keine ungespeicherte Änderung | Eine | {count}`). [`frontend/src/views/SettingsView.vue`](frontend/src/views/SettingsView.vue) ist komplett auf `useI18n().t` umgezogen — `sectionLabel`/`sourceLabel` machen einen Fallback auf den rohen Key, falls das Backend irgendwann eine neue Sektion liefert, deren Übersetzung noch fehlt. Modal nutzt `<i18n-t keypath="settings.modal.body">` mit `#neoPw`/`#authToken`-Slots, das Modal hat jetzt `role="dialog"` + `aria-modal="true"`. **Frontend-Tests:** 16 neue Vitest-Cases. [`frontend/src/store/__tests__/settings.spec.js`](frontend/src/store/__tests__/settings.spec.js) (10 Cases) deckt `loadSettings` (parallelisiert + Draft-Init), dirty-Tracking (Secrets gelten dirty, sobald getippt), `dirtySectionFlags`, das Save-Splitting (nur `putSettings`, nur `putSecrets`, beide bei gemischtem Dirty-Set), den synchronen `confirm_secrets_required`-Wurf, das Übernehmen der Validation-Errors aus `ApiError.originalResponse.errors` und `discardChanges`. [`frontend/src/views/__tests__/SettingsView.spec.js`](frontend/src/views/__tests__/SettingsView.spec.js) (6 Cases) mountet die View mit `vue-i18n` + `vue-router` (`createMemoryHistory`), mockt `AppFooter`/`AgoraGlyph` aus (Modul-Loading-Pfad triggert sonst `localStorage` aus dem globalen i18n-Init) und prüft: Tab-Labels rendern aus dem Schema, Reload-Badge erscheint pro Field mit `reload_required`, Secret-Field rendert `<input type="password">` mit `is_set`-Placeholder ohne Klartext, Inline-Validation-Hints landen aus dem Store im DOM (`.hint--error`), Source-Badge zeigt das i18n-Label (`source: env` → `.env`), und ein zweiter Mount mit `locale: 'en'` verifiziert die EN-Strings. `npm run check` grün (870 Backend-Tests, 85 Frontend-Tests +16, Build 124 KB CSS / 537 KB JS, unverändertes Lint-Warning). Closes #133.
- **Issue #133 (SUB3): Frontend SettingsView + Router-Eintrag + Store.** UI-Skelett für #133 (Refs #133, Folge zu SUB1/SUB2). Neue View [`frontend/src/views/SettingsView.vue`](frontend/src/views/SettingsView.vue) rendert die 12 Sektions-Tabs (LLM, Neo4j, Embedding, Ontology, Hybrid Search, Agent Tools, Event Bus, Logging, Locale, Webtools, OASIS, Secrets) als Pill-Tablist und pro Sektion eine Tabelle mit `Feld | Quelle-Badge | Wert-Input | Flags`. Field-Render je nach Schema-Typ: `text` für `string`, `number` (mit `step` 1/0.01) für `int`/`float`, `select` mit `enum_values`, `password` für Secrets (kein Klartext-Render aus dem Backend, Placeholder zeigt nur „•••••••• (gesetzt)" oder „leer"), Checkbox für `bool`. Source-Badge nutzt das v2-Design-System (`accent` für `file`/`override`, `info` für `env`, `outline` für `default`). Reload- und Secret-Flags rendern als Warn-Badges. Sticky-Action-Footer mit Speichern/Verwerfen, Counter ungespeicherter Änderungen, Inline-Validation-Hints aus `validation_failed`-Errors. Wenn der Save-Set Secrets enthält, öffnet sich ein Confirm-Modal („Tippfehler kann dich aussperren") — die Logik ist im Store gekapselt: `saveSettings({ confirmSecrets: false })` wirft synchron mit `code: confirm_secrets_required`, die View fängt den Wurf und zeigt das Modal. Neuer Router-Eintrag `/settings` (`Settings`) in [`frontend/src/router/index.js`](frontend/src/router/index.js). Neuer API-Client [`frontend/src/api/settings.js`](frontend/src/api/settings.js) (`fetchSettings`, `fetchSettingsSchema`, `putSettings`, `putSecrets`) auf der gemeinsamen Axios-Instanz mit Auth-Header. Neuer Store [`frontend/src/store/settings.js`](frontend/src/store/settings.js) als reaktiver Singleton (analog zu `pendingUpload.js`, kein Pinia): `loadSettings()` parallelisiert Schema- und Werte-Fetch via `Promise.all`, `dirtyKeys()` und `dirtySectionFlags()` liefern den Tab-Indikator-State, `_splitDirtyByKind()` trennt Secrets von Non-Secrets vor dem Save, sodass jeweils der richtige Endpoint angesprochen wird. Sprache vorerst hartkodiert deutsch — i18n-Ziehung auf `vue-i18n` plus EN-Locales und Frontend-Tests folgen in SUB4. `npm run check` grün (870 Backend-Tests, 69 Frontend-Tests, Build 124 KB CSS / 537 KB JS, unverändertes Lint-Warning).
- **Issue #133 (SUB2): Backend PUT /api/settings + Atomic-Write + Secrets-Endpunkt.** Schreibseite des Settings-Override-Layers (Refs #133, Folge zu SUB1). Neuer Validator [`backend/app/services/settings_validator.py`](backend/app/services/settings_validator.py) interpretiert die `FieldSpec`-Liste direkt (bewusst kein zweites Pydantic-Schema, das wäre Doppelpflege): Type-Coercion mit strikter `bool`-Trennung von `int`, fraktionale Floats werden für `int`-Felder abgelehnt, Range-Checks (`min_value`/`max_value`), Enum-Whitelist, Cross-Field-Konsistenz `EMBEDDING_MODEL` ↔ `VECTOR_DIM` (gleicher Validator wie der Startup-Check via `app.config.infer_vector_dim_for_model`). Strukturierte `ValidationError(key, code, message)`-Liste — der Validator sammelt **alle** Fehler in einem Pass, damit das Frontend mehrere Inline-Hints simultan zeigen kann statt Salami-Taktik. `SettingsService` erweitert um `apply_payload(payload, persist=True)` (mergt mit existierender File-Layer, schreibt atomar, räumt Override nach Persist auf, sodass `GET /api/settings` `source: file` ausweist) und `remove_persisted([keys])` für Reset-auf-Default. **Atomic-Write** via `tempfile.NamedTemporaryFile(dir=parent, suffix='.json.tmp', delete=False)` + `os.fsync` (best-effort) + `os.replace` — POSIX-atomar auf demselben Filesystem, korrupte `instance/settings.json` ist ausgeschlossen, lediglich zurückgelassene `.tmp`-Reste nach Crash möglich. Zwei neue PUT-Routen in [`backend/app/api/settings.py`](backend/app/api/settings.py): `PUT /api/settings` (bulk-Update non-secret Felder, Secrets werden mit `code: secret_not_allowed` aktiv abgelehnt; All-or-Nothing — bei Validation-Failure wird **nichts** persistiert) und `PUT /api/settings/secrets` (separater Pfad für `SECRET_KEY`/`NEO4J_PASSWORD`/`AGORA_AUTH_TOKEN`/`*_API_KEY` mit Pflicht-`confirm: true` als Self-Lockout-Schutz; non-secret Keys werden hier symmetrisch abgelehnt mit `code: non_secret_field`). Beide PUT-Antworten enthalten den frischen Sektions-Snapshot (gleiche Form wie GET) plus `updated_keys`, damit das Frontend ohne Round-Trip den neuen Source-Status rendern kann. Secret-Maske bleibt **strukturell** auch im PUT-Response: `value: null`, `is_set: bool`, kein Klartext im Response-Body — ein Substring-Test-Canary (`super-secret-leak-canary`) sichert das. Tests: 60 neue Backend-Cases — `test_settings_validator.py` (31 Cases: Coercion-Matrix, Edge-Cases, Cross-Field, Multi-Error-Sammlung), `test_settings_persistence.py` (14 Cases: File-Merge, kein zurückgelassenes `.tmp` im Happy-Path, ein Test pinnt `os.replace` als finalen Schritt mit Substitut-Spy), `test_settings_api.py` um 15 PUT-Cases erweitert (Round-Trip, Validation-400, Multi-Error, All-or-Nothing-Persist, Secrets-Confirm-Flag, Secrets-Endpoint-Auth, Plaintext-Leak-Canary). `npm run check` grün (870 Backend-Tests, 69 Frontend-Tests, Build 119 KB CSS / 528 KB JS, unverändertes Lint-Warning).
- **Issue #133 (SUB1): Backend Settings-Layer + GET /api/settings.** Erste Etappe der Settings-UI (Refs #133). Neue Module [`backend/app/services/settings_schema.py`](backend/app/services/settings_schema.py) (deklarative `FieldSpec`-Liste mit 31 Feldern in 12 Sektionen — LLM, Neo4j, Embedding, Ontology, Hybrid Search, Agent Tools, Event Bus, Logging, Locale, Webtools, OASIS, Security; Sektionen-Reihenfolge spiegelt `.env.example`) und [`backend/app/services/settings_layer.py`](backend/app/services/settings_layer.py) (`SettingsService` löst die Lade-Reihenfolge `Defaults → env → instance/settings.json → in-memory Override` auf, liefert pro Feld den effektiven Wert plus `source ∈ {default,env,file,override}` und `is_set`-Flag; Type-Coercion für `int`/`float`/`bool` und ein Modul-Singleton via `get_default_service()`). Neuer Blueprint [`backend/app/api/settings.py`](backend/app/api/settings.py) hängt unter `/api/settings` mit zwei Endpunkten: `GET /api/settings` (alle Felder gruppiert nach Sektion) und `GET /api/settings/schema` (reine Meta für den Frontend-Form-Render). Beide hinter dem Standard-Blueprint-Guard (`AGORA_AUTH_TOKEN`). **Secret-Felder** (`SECRET_KEY`, `NEO4J_PASSWORD`, `AGORA_AUTH_TOKEN`, `LLM_API_KEY`, `TAVILY_API_KEY`, `OPENAI_API_KEY`) werden im Response strukturell maskiert: `value: null`, nur `is_set: bool` — Secret-Defaults erscheinen auch im Schema-Endpunkt nicht. **Pin-Test gegen Drift**: 21 parametrisierte Cases prüfen, dass die Schema-Defaults 1:1 mit den Code-Defaults aus `app/config.py` übereinstimmen (Test gegen literal Werte, weil `Config.X` zur Import-Zeit aus `os.environ` belegt wird und kein zuverlässiger Anker ist, sobald die Test-Shell die Variable setzt). Tests: 54 neue Backend-Cases (`test_settings_layer.py` mit Schema-Konsistenz, Lade-Reihenfolge, Coercion, Secret-Maske, Edge-Cases für korrupte/missing `instance/settings.json`; `test_settings_api.py` mit Auth-Guard, Sektions-Gruppierung, Secret-Leak-Check via Substring-Suche im Response-Body). Out of Scope dieses Sub-Slices: PUT, Atomic-Write, Frontend — folgen in SUB2/3/4. `npm run check` grün (810 Backend-Tests, 69 Frontend-Tests, Build 119 KB CSS / 528 KB JS, unverändertes Lint-Warning). Arbeitsprotokoll: [`docs/p2-issue133-settings-protokoll.md`](docs/p2-issue133-settings-protokoll.md).
- **Issue #150 (Slice C · Design v2 Surfaces): Stepper, Persona, Tabellen, Logs, KPI, Toast, Popover, Kbd auf v2.** Schließt die 2026-Design-Migration ab (Refs #147, Folge zu #148/#149). [`frontend/src/assets/styles/global.css`](frontend/src/assets/styles/global.css): **Stepper** bekommt Glass-Backdrop (`backdrop-filter`) statt soliden Background, aktiver Step nutzt jetzt `var(--accent-soft)` statt `--mono-900` und behält die 2-px-Accent-Bottom-Bar (ohne Outer-Glow für ruhigeres Verhalten); Hover schaltet auf `var(--bg-glass-hi)`. **Persona-Cards** kriegen Avatar-Gradients (Iris→Violet als Default, mit `is-aurora`/`is-mint`/`is-violet`-Varianten), Hover-Background, neue **Stance-Bar** (`stance-track`/`stance-fill` mit Iris→Aurora-Gradient für Polarization-Indikatoren) und `is-approved`/`is-flagged`-Tints (oklch-Soft-Backgrounds + Border-Color-Mix). **Tabellen** auf 14-px-Padding, Mono-Caps mit `--ls-mono-wide`, Hover auf `var(--bg-glass)`, Selected auf `var(--accent-soft)` mit 2-px-Accent-Inset-Border. **Log/Log-Block** mit `--r-3`-Radius, Level-Farben auf oklch (`--info`/`--warn`/`--err`/`--ok`/`--accent` für Agent), Timestamp auf `--fg-meta`. Neuer **KPI-Block** (`.kpi`/`.kpi .label`/`.kpi .value`/`.kpi .delta`) mit Serif-Numerale (40 px, `--ls-display`, tabular-nums) + Mono-Caps-Label + farbcodiertem Delta (`--ok`/`--err`). **Toast** auf Glass-Surface (`--bg-glass-hi` + `backdrop-filter: blur(20px)`) und 3-px-Accent-Border-Left, status-spezifische Border-Colors auf oklch gemappt. **Popover** in Glass-Form (`backdrop-filter`, `--r-3`), **Tooltip** als bg-inverse-Pill (statt mono-50-Hardcoded), **Kbd-Key** mit `--shadow-1` und `--r-2`. **Marketing-`.nav`** kriegt Glass-Backdrop, sodass Aurora-Mesh durchscheint. `npm run check` grün (756 Backend-Tests, 69 Frontend-Tests, Build 119 KB CSS / 528 KB JS gz). Closes #150.
- **Issue #149 (Slice B · Design v2 Visual Language): UI-Primitives & Workspace-Header auf v2.** Folge-Slice zu #148 (Refs #147). [`frontend/src/assets/styles/global.css`](frontend/src/assets/styles/global.css) ist die Hauptbühne — Buttons, Badges, Inputs, Tabs, Segmented, Panel und Switch wurden komplett auf das v2-Vokabular gehoben: Buttons sind jetzt **pill-shaped** (`--r-pill`) mit tactiler Tiefe (Inset-Highlight, Drop-Shadow + Press-Glow, `translateY(-1px)`-Hover); Variants `--primary` (ink-on-paper Solid), `--accent` (Aurora-Gradient mit Glow), `--info`/`--plasma` (Iris-Gradient), `--secondary`/`--ghost` (Glass-Backings), `--glass` (Backdrop-Blur), `--danger` (Error-Soft → Solid auf Hover). Badges bekommen Glass-Surface (`backdrop-filter`) + oklch-Soft-Backgrounds für `--accent`/`--info`/`--success`/`--warn`/`--error` plus neue `.badge--live`-Klasse mit Pulse-Animation. Inputs (`.input`/`.select-trigger`/`.textarea`) sind pill-shaped mit Accent-Glow-Focus-Ring (`box-shadow: 0 0 0 4px var(--accent-soft)`); Tabs und Segmented sind jetzt **pill-segmented** (statt Underline) im Glass-Container; Switch ist 44×26 px mit weißem Thumb und Inset-Highlight; Panel hat größeren Radius (`--r-3`) und `--shadow-1` mit Glass-Variant. UI-Atome: [`Card.vue`](frontend/src/components/ui/Card.vue) bekommt eine `glass`-Prop für Liquid-Glass-Surfaces; [`Field.vue`](frontend/src/components/ui/Field.vue) und [`Select.vue`](frontend/src/components/ui/Select.vue) sind von der Bare-Underline-Form auf das v2-Pill-Input-Treatment migriert (mit Accent-Glow-Focus); [`StickyScrollBanner.vue`](frontend/src/components/ui/StickyScrollBanner.vue) ist als Aurora-Gradient-Pill mit Glow neu gestaltet (statt flat-accent). [`WorkspaceHeader.vue`](frontend/src/layouts/WorkspaceHeader.vue) bindet jetzt den `<ThemeToggle>` rechts neben dem `status`-Slot ein und bekommt selbst Glass-Treatment (`background: var(--bg-glass)` + `backdrop-filter: blur(20px) saturate(160%)`), sodass das Aurora-Mesh aus Slice A durchscheint. Alle Konsumenten (Step1–Step5, MainView, RunsView, SimulationRunView, ReportView, InteractionView, HistoryDatabase) erben den neuen Look automatisch über die zentralen Klassen — kein zusätzlicher Refactor nötig. `npm run check` grün (756 Backend-Tests, 69 Frontend-Tests, Build 116 KB CSS / 528 KB JS, ein bestehender Lint-Warning unverändert). Closes #149.
- **Issue #148 (Slice A · Design v2 Foundation): Light/Dark-Theme + Aurora-Mesh-Background.** Frontend-Foundation für die 2026-Design-Language v2 (Refs #147). [`frontend/src/assets/styles/tokens.css`](frontend/src/assets/styles/tokens.css) komplett auf das v2-oklch-System umgestellt: Aurora coral als primärer Akzent, Iris/Violet/Mint als Sekundärachsen; Light-Theme als Default (`:root, [data-theme="light"]`), Dark-Theme als Override (`[data-theme="dark"]`); generösere Radien (`--r-3: 14px`, `--r-pill`), liquid-glass Surfaces (`--bg-glass`, `--bg-glass-hi`), tactile Shadow-Stack mit Inset-Highlights, Aurora-Mesh-Variablen (`--mesh-1..4`, `--mesh-alpha`); alle Legacy-Aliase (`--mono-*`, `--neon-orange-*`, `--plasma-*`, `--paper-*`, `--status-*`, `--bg-page`, `--bg-grid`, `--shadow-popover`, `--glow-plasma`) bleiben für die staged Migration in Slice B/C erhalten. Type-Stack auf **Instrument Serif** + **Inter Tight** + **JetBrains Mono** umgestellt: [`frontend/index.html`](frontend/index.html) lädt die drei Familien per Google-Fonts-`<link>` (Fraunces/IBM Plex weg) und ein winziges Pre-Paint-Script setzt `data-theme` aus `localStorage` (`agora-theme`) noch vor dem ersten Render — kein FOUC. Neue Composable [`frontend/src/composables/useTheme.js`](frontend/src/composables/useTheme.js) (singleton-`watch`, persistierter Toggle, fail-safe gegen blockiertes `localStorage`); neues UI-Atom [`frontend/src/components/ui/ThemeToggle.vue`](frontend/src/components/ui/ThemeToggle.vue) (Pill-Switch Sun/Moon, `aria-pressed`); [`frontend/src/components/ui/AuroraBackground.vue`](frontend/src/components/ui/AuroraBackground.vue) montiert vier animierte Aurora-Blobs (60/50/40/36 vw, 22 s `ease-in-out`) plus `mix-blend-mode`-Filmkorn-Overlay, beide `pointer-events:none`/`z-index:0` und respektieren `prefers-reduced-motion`. [`frontend/src/App.vue`](frontend/src/App.vue) initialisiert `useTheme()` beim App-Start und mountet `<AuroraBackground />` unter dem Router-View; `#app` bekommt `position:relative; z-index:2`, sodass alle Views sauber über dem Mesh stehen. [`frontend/src/assets/styles/fonts.css`](frontend/src/assets/styles/fonts.css) entkernt (Geist-`@font-face`-Blöcke nicht mehr nötig, Datei bleibt als Import-Slot). `npm run check` grün (744 Backend-Tests, 69 Frontend-Tests, Build 109 KB CSS / 523 KB JS, ein bestehender Lint-Warning unverändert). Closes #148.
- **Issue #132: Backend-Log-Viewer.** Neuer Blueprint `backend/app/api/logs.py` mit `GET /api/logs` (Tail, Default 200 / Cap 2000, optionaler `level`-Filter `error|warn|info|debug`) und `GET /api/logs/stream` (SSE, Heartbeat 15 s, `X-Accel-Buffering: no`). Path-Traversal-Schutz: kein `?file=`-Parameter, Pfad hardcoded aus `LOG_DIR` + heutigem Datum mit `relative_to`-Check. Auth: Standard-Blueprint-Guard. Frontend: globaler `LogDrawer.vue` (Bottom-Drawer max 50vh / 480 px), FAB-Button und Hotkey `Ctrl+Shift+L`, Persistenz in `localStorage` (`agora.ui.logDrawer.open`); Sticky-Scroll wiederverwendet aus #130, Level-Select, Suchfeld, Pause-Toggle, Ringpuffer 5000 Lines. i18n DE/EN für `logs.drawer.*`. Tests: 9 neue Backend-Cases (`test_logs_api.py`). **PR #146-Review-Fixes:** (a) Tail-Endpoint strippt Trailing-Newlines (`rstrip('\r\n')`) und nutzt `path.stat().st_size` statt `fh.tell()` für den Offset — ersteres macht das Frontend-Rendering konsistent mit dem Stream-Endpoint (kein doppelter Zeilenabstand bei `white-space: pre-wrap`), zweites ist robuster gegen Pythons internes Text-File-Buffering. (b) Stream akzeptiert optional `?offset=…`; `LogDrawer.vue` reicht den Offset aus dem Tail-Response weiter, sodass Lines, die zwischen Tail-Antwort und Stream-Connect geschrieben werden, nicht verloren gehen. (c) Level-`re.compile`-Pattern wird einmal pro Stream-Lebenszeit aufgelöst statt pro Zeile aus dem Dictionary geholt. Drei neue Tests: `test_get_logs_strips_trailing_newlines`, `test_get_logs_offset_matches_file_size`, `test_parse_offset_arg_rejects_negative_and_garbage`. Schließt Issue #132 ab.
- **Issue #131 (SUB2 + SUB3): Tool-Panel collapsible mit Hotkey/Badge/Filter/Copy.** Neues collapsible Card unterhalb des Live-Feeds (`role="region"`, `aria-label`); Toggle-Button im Live-Feed-Header mit `aria-expanded`, Badge zeigt ungesehene Errors (Counter resettet beim Öffnen). Hotkey `Ctrl+L`/`Cmd+L` toggelt; State persistiert in `localStorage` (`agora.ui.toolPanel.open`, default `false`). Filter-Toggle `[Alle | Nur Fehler]` (Heuristik: `/(error|exception|traceback|fatal|warn|warning)/i`). Pro Log-Zeile ein 📋-Button kopiert `{"line": "...", "ts": …}` ins Clipboard via `navigator.clipboard.writeText` mit `document.execCommand('copy')`-Fallback. i18n-Keys `step3.toolPanel.*`. Schließt Issue #131 ab.
- **Issue #131 (SUB1): Sticky-Scroll im Console-Pane.** `useIncrementalLogPolling` akzeptiert optional eine `useStickyScroll`-Instanz und ruft `markAppended(deltaCount)` statt blind `scrollTop = scrollHeight`. Default-Verhalten unverändert (rückwärts-kompatibel zu `Step4Report.vue` und allen anderen Konsumenten). `Step3Simulation.vue` verdrahtet eine zweite Sticky-Instanz für `consoleScrollEl`; Banner unter dem Console-Pane. Tests: 4 neue Vitest-Cases (`useIncrementalLogPolling.spec.js`). Arbeitsprotokoll: [`docs/p2-issue131-tool-panel-toggle-protokoll.md`](docs/p2-issue131-tool-panel-toggle-protokoll.md).
- **Issue #130 (SUB3): Mention/Hashtag-Highlight im Live-Feed.** Neue Util `frontend/src/utils/feedHighlight.js` (`tokenizeFeedText`) zerlegt Beiträge in `text`/`mention`/`hashtag`-Tokens (Unicode-tolerant via `\p{L}`); `Step3Simulation.vue` rendert sie mit `v-for` als `<span>`-Sequenz — XSS-frei, kein `v-html`. CSS-Klassen `.tok-mention` (accent, fett) und `.tok-hashtag` (status-warn) heben Marker hervor. Tests: 6 neue Vitest-Cases (`feedHighlight.spec.js`). Schließt Issue #130 ab.
- **Issue #130 (SUB2): Feed-Layout + Density-Toggle.** Live-Feed- und Console-Pane bekommen `min-height: 480px` / `max-height: clamp(480px, 60vh, 720px)` — sind also auf jedem Display deutlich größer als die alte 360-px-Box. Neuer Density-Toggle (Komfort / Kompakt) mit `localStorage`-Persistenz (`agora.ui.feedDensity`) verändert Schriftgröße, Line-Height und Margin der Feed-Zeilen; max. Zeilenbreite 75 ch. i18n-Keys `step3.feed.density.*` und `common.scrollToBottom` neu. Arbeitsprotokoll: [`docs/p2-issue130-simulation-feed-sticky-protokoll.md`](docs/p2-issue130-simulation-feed-sticky-protokoll.md).
- **Issue #130 (SUB1): Sticky-Scroll im Live-Feed.** Neue Composable `frontend/src/composables/useStickyScroll.js` (32-px-Bottom-Schwelle, `markAppended`, `scrollToBottom`, reaktiver `unreadCount`) plus UI-Banner `frontend/src/components/ui/StickyScrollBanner.vue` mit i18n-Pluralisierung (`step3.feed.unread`, `common.scrollToBottom`). `Step3Simulation.vue` nutzt die Composable für `scrollEl`; `pollDetail` ruft nach jedem Append `markAppended(deltaCount)` statt blind `scrollTop = scrollHeight`. Tests: 5 neue Vitest-Cases (`useStickyScroll.spec.js`). Arbeitsprotokoll: [`docs/p2-issue130-simulation-feed-sticky-protokoll.md`](docs/p2-issue130-simulation-feed-sticky-protokoll.md).
- **Issue #129 (SUB3): Graph-Layout Pause/Resume.** `useGraphRender` exponiert `pauseSimulation`/`resumeSimulation`/`togglePause` plus reaktiven `isPaused`-Status; beim Re-Render wird ein aktiv pausiertes Layout respektiert (`simulation.stop()` direkt nach Setup). `GraphCanvas` reicht den State an `GraphPanel` und `GraphToolbar` durch; neue Toolbar-Schaltfläche mit Pause/Resume-Icon und i18n-Beschriftung (`graph.ui.pauseLayout` / `graph.ui.resumeLayout`). Schließt Issue #129 ab. Out-of-Scope: Auto-Freeze pro Batch erfordert ein Backend-Batch-Signal und ist als Folge-Issue dokumentiert.
- **Issue #129 (SUB2): Graph-Lesbarkeit-Polish.** Edge-Label-Schrift von 9 px auf 12 px erhöht, Pillen-Padding von 4/2 auf 6/3 px ausgebaut. Knoten-Label-Trunkation von 8 auf 14 Zeichen entspannt; vollständiger Knoten-Name bleibt im SVG-`<title>` als nativer Browser-Tooltip erreichbar. Auto-Hide der Edge-Labels bei Zoomstufe <0.6 (Schwelle dominiert vom Toggle-State, springt nur bei Übergängen). Arbeitsprotokoll: [`docs/p2-issue129-graph-de-labels-protokoll.md`](docs/p2-issue129-graph-de-labels-protokoll.md).
- **Issue #129 (SUB1): Graph-Edge-Labels via i18n.** Neuer Display-Layer `frontend/src/components/graph/edgeLabelI18n.js` (`formatEdgeLabel`, `normalizeEdgeKey`, `humanizeEdgeKey`) übersetzt LLM-generierte Beziehungs-Labels in die aktuelle UI-Locale (`graph.edgeLabels.*` mit ~75 Standard-Edge-Types in DE/EN, plus `graph.ui.toggleEdgeLabels`). Heuristik-Fallback (UPPER_SNAKE → Title Case) für unbekannte Edge-Types. `useGraphRender` akzeptiert optionalen `translateLabel`-Hook; `GraphCanvas.vue` reicht `useI18n().t` durch und rendert bei `locale`-Wechsel neu. Neo4j-Persistenz unverändert (Display only). Tests: `frontend/src/components/graph/__tests__/edgeLabelI18n.spec.js` (12 Cases). Arbeitsprotokoll: [`docs/p2-issue129-graph-de-labels-protokoll.md`](docs/p2-issue129-graph-de-labels-protokoll.md).


### Security
- **Slice 12 (Repo-Review-Folge, F5): Test-Coverage SSRF + Upload + Cypher-Sanitizer + Auth-Mode.** Vier neue Test-Dateien, +54 Backend-Tests (690 → 744). [`backend/tests/test_ssrf_blocker.py`](backend/tests/test_ssrf_blocker.py) (10 Cases) pinnt `app.services.web_tools._is_public_url` gegen Loopback (v4+v6), RFC1918 (10.0.0.1), AWS-Metadata (169.254.169.254), IPv6-Link-Local (fe80::1), unsupported-Scheme (`ftp://`), DNS-Resolve-Fail und Multi-Result-DNS mit gemischt public/private — plus Positiv-Kontrolle (93.184.216.34 / example.com). [`backend/tests/test_upload_limits.py`](backend/tests/test_upload_limits.py) (10 Cases) sichert die Extension-Whitelist (`pdf`/`md`/`txt`/`markdown`), `MAX_CONTENT_LENGTH = 50 MB`, PDF-Magic-Header-Check, Path-Traversal-Filename-Stripping (`../../etc/passwd` → UUID-Filename via `secure_filename` + Prefix-Guard) und ungueltige `project_id`s. [`backend/tests/test_cypher_label_sanitizer.py`](backend/tests/test_cypher_label_sanitizer.py) (27 Cases) pinnt `app.storage.neo4j_mappings.sanitize_label` gegen Backtick-Injection (`` Person`}; DROP DATABASE neo4j; // ``), 50-Zeichen-Cap, Sonderzeichen, leere Strings, `Entity`-Default-Reject und Non-String-Inputs (`None`, `int`, `bytes`); Positiv-Kontrolle fuer `Person`/`Organization`/`_Internal`/`Film`. **Bonus-Code (Slice 12, klein):** `_get_auth_mode()` in [`backend/app/api/status.py`](backend/app/api/status.py) klassifiziert `/api/status.backend.auth_mode` als `token` / `anonymous` / `open` / `misconfigured` — der Operator sieht damit per Status-Endpoint, ob `AGORA_ALLOW_ANONYMOUS=true` heimlich gesetzt ist. [`backend/tests/test_anonymous_in_healthcheck.py`](backend/tests/test_anonymous_in_healthcheck.py) (7 Cases) sichert die vier Modi inkl. Praezedenz-Regeln (Token > Anonymous > Debug > Misconfigured) und Payload-Smoke. README-Status-Block (DE + EN) zeigt jetzt **796 Tests gruen** (744 Backend + 52 Frontend; +85 ggue. v0.9.0-Tag). Arbeitsprotokoll: `docs/2026-05-01-slice-12-test-coverage-arbeitsprotokoll.md`05-01-slice-12-test-coverage-arbeitsprotokoll.md).


- **Slice 5 (Repo-Review-Umsetzung, PR5): Frontend-Token-Haertung + Auth-Doku.** `frontend/src/api/index.js`: `getAgoraToken` unterstuetzt jetzt Memory-Mode (`VITE_AGORA_TOKEN_STORAGE=memory`) als Prod-Haertung — das Token lebt dann nur im JS-Heap und uebersteht keinen Page-Reload, was XSS-Residuum in `localStorage` vermeidet. `setAgoraToken()` zentralisiert Token-Setzen fuer beide Modi. `localStorage`-Pfad bleibt bewusster Dev-Default. Neue Auth-Doku `docs/auth.md` mit Token-Header-Vertrag, Ticket-Flow, Query-Token-Deprecation, Storage-Risiko-Vergleich und Empfehlung HttpOnly-Cookie fuer Prod-Zielarchitektur. XSS-Sanitizer (`frontend/src/utils/markdown.js` + 9 Regression-Tests) war bereits in v0.9.0 erfuellt. Arbeitsprotokoll: `docs/2026-05-01-slice-5-auth-token-arbeitsprotokoll.md`.

- **Slice 4 (Repo-Review-Umsetzung, PR4): CVE-Baseline aktiv abbauen.** Sechs `pip-audit --ignore-vuln`-Einträge in `.github/workflows/ci.yml` bekommen Inline-Kommentare mit Paket, Upstream-Pin und GitHub-Issue-Verweis. Neue Datei `docs/dependency-risk-register.md` mit Tabelle (CVE, Paket, Owner, Frist, Status, Issue-Link) und Prozessbeschreibung. 6 GitHub-Issues #121–#126 erstellt (Titel: `security: track ignored <CVE> until upstream fix`, Frist +90 Tage = 2026-07-30). Arbeitsprotokoll: `docs/2026-05-01-slice-4-cve-baseline-arbeitsprotokoll.md`.

- **Slice 3 (Repo-Review-Umsetzung, PR3): Redis-basierte Single-Use-Tickets.** `signed_ticket.consume()` versucht jetzt zuerst ein atomisches `SET ticket:<sig> 1 NX EX <ttl>` gegen Redis; erst wenn Redis nicht erreichbar ist, fällt es auf den bestehenden in-process `_seen`-Speicher zurück. Das schließt die Multi-Worker-Replay-Lücke unter gunicorn. `fakeredis[lua]>=2.30.0` als neue Dev-Dependency. Tests: `backend/tests/test_signed_ticket_redis.py` (6 Cases: Replay-Block, Multi-Worker-Race, In-Memory-Fallback + Warning). Arbeitsprotokoll: `docs/2026-05-01-slice-3-redis-tickets-arbeitsprotokoll.md`.

- **Slice 1 (Repo-Review-Umsetzung, PR1): Secure Defaults + Config-Validation.** `Config.validate()` lehnt im Nicht-Debug-Betrieb jetzt bekannte Platzhalter-Werte aus `.env.example` hart ab (`SECRET_KEY` ∈ {`change-me`, `change-me-use-token_urlsafe-32`, `agora`, `password`}; `NEO4J_PASSWORD` ∈ {`change-me`, `agora`, `neo4j`, `password`}). Vergleich ist case-insensitive. Im Debug-Betrieb erzeugt das gleiche Setup eine laute `agora.config`-Warning, blockt aber nicht. `.env.example` defaultet `FLASK_DEBUG=false` (secure-by-default) und kommentiert die Placeholder-Reject-Policy. Auth-Token-Pflicht im Nicht-Debug bleibt unverändert (P0.1a). Neue Test-Datei `backend/tests/test_config_security.py` (12 Cases inkl. Parametrize-Coverage je Platzhalter); Bestand `test_config_validate.py` weiter grün. README-Sicherheits-Sektion um `python -c "import secrets; print(secrets.token_urlsafe(32))"` ergänzt. Arbeitsprotokoll: `docs/2026-05-01-slice-1-secure-defaults-arbeitsprotokoll.md`.


### Docs
- **Slice 13 (Repo-Review-Folge, F6): Plan-Abschluss + Branch-Cleanup.** Letzter Sub-Slice der Repo-Review-Folge. `docs/2026-05-01-v0.9.0-review-folge-slices-plan.md`05-01-v0.9.0-review-folge-slices-plan.md) bekommt einen Abschluss-Statusblock oben (Tabelle F1–F6 mit Merge-Commits + PR-Links) und F6-Sektion ist als ✅ done markiert. `docs/2026-05-01-v0.9.0-repository-review.md`05-01-v0.9.0-repository-review.md) Statusblock spiegelt das: sieben neue Zeilen (F1/Slice 7 → F6/Slice 13) in der Action-Plan-Tabelle, drei Test-Cross-Check-Eintraege (SSRF, Upload, Cypher) und der Anonymous-Health-Eintrag von ❌ auf ✅ umgestellt, sechs Doku-Cross-Check-Eintraege (Threat-Model, Deployment-Dev, Deployment-Prod-Like, Backup-Restore, Operations, Release-Process) auf ✅ — alle Original-Review-Forderungen der Doku-Tabelle sind damit gruen. **Branch-Cleanup:** Lokaler Branch `claude/v0.9.0-frontend-version` wird nach diesem Merge per `git branch -D` entfernt (Remote war zum Zeitpunkt des Slice-Starts bereits weg). Akzeptanz F6 erfuellt: `git branch -a | grep v0.9.0-frontend-version` leer, README-Doku-Liste aktuell. Arbeitsprotokoll: `docs/2026-05-01-slice-13-cleanup-arbeitsprotokoll.md`05-01-slice-13-cleanup-arbeitsprotokoll.md).

- **Slice 10 (Repo-Review-Folge, F4): Release-Process-Doku.** Neue Datei [`docs/release-process.md`](docs/release-process.md) macht den Release-Pfad reproduzierbar: alle sechs Versionsquellen tabelliert (`package.json`, `frontend/package.json`, `backend/pyproject.toml`, `backend/app/__init__.py`, README-Banner/Status-Block, `frontend/src/i18n/locales/{de,en}.json`-Frontend-Badge); SemVer-Regeln pre-1.0; sechs-stufige Reihenfolge (CHANGELOG `[Unreleased]` → SemVer-Bump in allen Quellen mit konkreten `sed`/`npm version`-Snippets → Release-Notes-Datei → `git tag -a` → `gh release create` → optional Container-Image-Build fuer GHCR und Docker-Hub); Verifikation per `/api/status.backend.version`-Probe; Hotfix-Pfad ohne Release-Branch (Linear-Git); Tag-Rollback-Regeln. Vorlage fuer Release-Notes ist `docs/2026-05-01-v0.9.0-release-notes.md`05-01-v0.9.0-release-notes.md). **Bekannter Drift sichtbar gemacht:** `backend/pyproject.toml` steht auf `0.6.1`, `backend/app/__init__.py` auf `0.8.0` — Sync ist als Folge-Slice gefuehrt, weil das einen `git tag`-Pfad anschneidet, den diese Doku nur beschreibt. README-Doku-Index (DE + EN) bekommt eine neue `Release-Process`-Zeile. Arbeitsprotokoll: `docs/2026-05-01-slice-10-release-process-arbeitsprotokoll.md`05-01-slice-10-release-process-arbeitsprotokoll.md).

- **Slice 9 (Repo-Review-Folge, F3): Operations + Backup/Restore.** Zwei neue Dateien als Ops-Bezugsdoku: [`docs/operations.md`](docs/operations.md) deckt Healthchecks (`/health` public, `/api/status` aggregiert mit Backend/Neo4j/Ollama/Disk/GPU), Logs (Quellen, Rotation via `RotatingFileHandler` 10 MB / 5 Backups, JSON-Mode via `AGORA_LOG_FORMAT`, Logger-Redaction-Reichweite, Cheat-Sheet wichtiger Marker), Ressourcenbedarf (RAM/CPU/Disk je Komponente, GPU-Probe via Ollama REST `/api/ps`) und sechs konkrete Ausfall-Szenarien (Neo4j down, Redis down, Ollama down, Backend 5xx, Disk voll, Container-Restart-Loop) mit Diagnose-Befehlen und Fallback-Hinweisen. [`docs/backup-restore.md`](docs/backup-restore.md) listet Asset-Klassen mit Restore-Verlust-Bewertung, Neo4j-Online-Dump via `neo4j-admin database dump` (inkl. Backend-Pause-Sequenz), Btrfs-Snapshot-Variante, Restore-Pfad mit Pre-Wipe und Verifikation, Restic-/Borg-Pattern fuer Uploads/Reports, Cron-Strategie (taeglich Neo4j-Dump, stuendlich Restic-Inkrement, woechentlich `forget`), Retention-Vorschlag und einen Worst-Case-Recovery-Ablauf. Restore-Drill ist als Quartals-Pflicht verankert. README-Doku-Index (DE + EN) bekommt neue `Operations`-Zeile mit Verweis auf beide Dateien plus `security-threat-model.md`. Arbeitsprotokoll: `docs/2026-05-01-slice-9-ops-backup-arbeitsprotokoll.md`05-01-slice-9-ops-backup-arbeitsprotokoll.md).

- **Slice 8 (Repo-Review-Folge, F2): Security-Threat-Model.** Neue Datei [`docs/security-threat-model.md`](docs/security-threat-model.md) bringt das implizite Threat-Model in den Repo: Asset-Tabelle (Neo4j-Daten, Uploads, Reports, OASIS-Artefakte, Auth-Token, Tickets, `SECRET_KEY`, Neo4j-Passwort, HF-Cache, Logs), sechs Trust Boundaries (B0 Reverse-Proxy, B1 Browser↔Frontend, B2 Frontend↔Backend, B3 Backend↔Neo4j/Redis/Ollama, B4 Backend↔OASIS-Subprozess, B5 Backend↔Outbound-HTTP) inkl. ASCII-Diagramm, sechs Angreifer-Modelle (A1 untrusted LAN/Tailnet, A2 XSS/Plugin, A3 Supply-Chain, A4 geleakter Token, A5 boesartiges Upload-Dokument, A6 SSRF), Top-5-Restrisiken (kein echtes AuthN/AuthZ, keine Secrets-Rotation, OASIS-Subprozess-Vertrauen, Prompt-Injection im Quelldokument, Browser-Token-Storage), Mapping aller Mitigations zu Slices/Phasen (PR1 Secure-Defaults, PR3 Redis-Tickets, PR4 CVE-Register, PR5 Memory-Mode, Phase 3.1-3.4 SSRF/Persona-Whitelist/Vision-Cap/Cypher-Sanitizer, Slice 2 Compose-Dev/Prod-Split) und Review-Pflichten bei Boundary-Touch. Konsistent mit [`auth.md`](docs/auth.md), [`security-hardening.md`](docs/security-hardening.md), [`dependency-risk-register.md`](docs/dependency-risk-register.md), [`deployment-prod-like.md`](docs/deployment-prod-like.md). Arbeitsprotokoll: `docs/2026-05-01-slice-8-threat-model-arbeitsprotokoll.md`05-01-slice-8-threat-model-arbeitsprotokoll.md).

- **Slice 7 (Repo-Review-Folge, F1): Deployment-Doku Dev + Prod-Like.** Zwei neue Dateien als Single-Source-of-Truth fuer Setup-Pfade: [`docs/deployment-dev.md`](docs/deployment-dev.md) deckt Bare-Metal (`npm run dev`) und Compose-Dev-Stage (`target: dev`, Loopback-Ports, Hot-Reload) ab inkl. Voraussetzungen (`uv`, `npm`, Neo4j, Ollama, optional Redis), Tests-Gate, Volume-Layout und Dev-Stolperfallen; verweist auf [`auth.md`](docs/auth.md) fuer das Token-Setup. [`docs/deployment-prod-like.md`](docs/deployment-prod-like.md) dokumentiert Gunicorn (`--workers 2`), Reverse-Proxy (Traefik/Nginx-Beispiele inkl. SSE-`proxy_buffering off`), Tailscale/WireGuard-Pattern, CORS-/Auth-Pflichtkonfig (`AGORA_AUTH_TOKEN`, kein `AGORA_CORS_ALLOW_ALL`, kein `AGORA_ALLOW_ANONYMOUS`), Compose-Prod-Override (Vite-Port entfaellt, Neo4j-Ports per `!reset []`), Update-/Rollback-Pfad und verweist auf [`dependency-risk-register.md`](docs/dependency-risk-register.md) fuer die CVE-Baseline. README-Schnellstart und Quick-Start (DE + EN) bekommen einen Hinweisblock auf beide Dateien; Doku-Index-Sektion am Ende der `Entwicklung`/`Development checks`-Bloecke nennt Deployment, Auth, API-Contracts und Architektur explizit. Arbeitsprotokoll: `docs/2026-05-01-slice-7-deployment-doku-arbeitsprotokoll.md`05-01-slice-7-deployment-doku-arbeitsprotokoll.md).


- **Slice 6 (Repo-Review-Umsetzung): Review archiviert + Folge-Sub-Slice-Plan.** Externer Repo-Review aus `claude/v0.9.0-frontend-version` (Commit `e375d42`) als Audit-Artefakt unter `docs/2026-05-01-v0.9.0-repository-review.md` archiviert: vorangestellter Statusblock referenziert pro Action-Plan-Punkt (PR 1–5) den umsetzenden Commit (`28a5f2d`, `4bda1d8`, `821b4dd`, `21028d7`, `aace638`) plus Followups (`95cfee6`, `9d566b1`); Test-Cross-Check-Tabelle (12 Forderungen vs. Bestand in `backend/tests/`) und Doku-Cross-Check-Tabelle (8 Forderungen vs. `docs/`) machen Restpunkte sichtbar. Folge-Plan `docs/2026-05-01-v0.9.0-review-folge-slices-plan.md` definiert sechs Sub-Slices F1–F6 (Deployment-Doku Dev/Prod, Threat-Model, Operations + Backup/Restore, Release-Process, Test-Lücken SSRF/Upload/Cypher-Sanitizer, Branch-Cleanup). Quell-Branch wird in F6 gelöscht; `rolle-du-bist-temporal-otter.md` bewusst nicht ins Repo übernommen. Arbeitsprotokoll: `docs/2026-05-01-slice-6-review-archivierung-arbeitsprotokoll.md`.

- **Slice 0 (Repo-Review-Umsetzung): README/Doku-Sync auf v0.9.0.** README-Status-Block, deutsche und englische Engineering-Stand-Sektionen, Testzahlen-Block (519 → 711, 488 → 671 Backend, 31 → 40 Frontend) und Release-Notes-Verweis auf v0.9.0 / Vorgänger v0.8.0 aktualisiert. Schnellstart-Sektion um expliziten Hardening-Drift-Hinweis ergänzt: `docker-compose.yml` baut aktuell den `prod`-Stage statt `dev`, Neo4j (`7474`/`7687`), Backend (`5001`) und Vite (`5173`) binden noch auf `0.0.0.0` — wird in Slice 2 entschärft. Arbeitsprotokoll: `docs/2026-05-01-slice-0-readme-v090-sync-arbeitsprotokoll.md`.

### Deploy
- **Slice 2 (Repo-Review-Umsetzung, PR2): Compose Dev/Prod-Trennung.** `docker-compose.yml` baut jetzt explizit `target: dev` (Vite + Flask, Hot-Reload statt vorher `prod`-Stage via Default). Alle Host-Ports auf `127.0.0.1` gelockt (5173, 5001, 7474, 7687). `docker-compose.prod.yml` entfernt Vite- und Neo4j-Host-Ports komplett via `!reset []` (Docker Compose v2.24+), Backend-Port bleibt auf Loopback. README-Schnellstart in Dev-/Prod-Blöcke aufgeteilt mit Endpoint-Tabelle. Neuer optionaler Compose-Snapshot-Test (`backend/tests/test_compose_snapshot.py`, skip-if-no-docker, 8 Cases). Arbeitsprotokoll: `docs/2026-05-01-slice-2-compose-dev-prod-arbeitsprotokoll.md`.

## [0.9.0] — 2026-05-01

Milestone „Domain Cleanup" abgeschlossen — 12/12 Issues geschlossen, **711 Tests grün** (671 Backend + 40 Frontend; +192 gegenüber v0.8.0). Drei Hot-Spot-Module signifikant entkernt: `simulation_manager.py` 789 → 403 LOC (−49 %), `report_agent.py` 3184 → 2179 LOC (−31,6 %), `neo4j_storage.py` 1127 → 195 LOC (−82,7 %). Domain-Schichten klar getrennt: neue Service-Module für Branching, Prepare-Pipeline, Report-Logging/Models/Prompts/Tools, Ingestion-Pipeline; Storage in fünf Module gesplittet (Mappings + Read/Write/Search-Mixins). Wire-Identity gepinnt: Backend-Graph-DTOs für Frontend-API, FSM-Validierung aller Statusübergänge, Re-Export-Pattern hält alle Caller stabil. Drei Issues retrospektiv als bereits erledigt geschlossen (#41 SimulationRepository, #49 Evidence-Layer; beide durch frühere Slices abgedeckt).

### Geändert

- **Issue #50 (EPIC-08-ST-01: Neo4jStorage in Read/Write/Search schneiden) abgeschlossen — Sub-Slice 3/3, Search-Mixin + Closure. EPIC-08 vollständig (3/3); v0.9.0 vollständig (12/12).** Letzte Etappe des Boss-Fights: `search`-Methode in `Neo4jSearchMixin` (`backend/app/storage/neo4j_search.py`, 57 LOC) gezogen. Klassen-Definition final: `class Neo4jStorage(Neo4jReadMixin, Neo4jWriteMixin, Neo4jSearchMixin, GraphStorage)`. **`neo4j_storage.py` schrumpft 228 → 195 LOC**; **gesamt für Issue #50: 1127 → 195 LOC (−932, −82,7 %, vier Fünftel weg)**. Verbleibend im Storage-Modul: nur noch Konstruktor/Lifecycle (`__init__`, `close`, `set_ontology_mutation_service`, `_verify_connectivity`, `_ensure_schema`), Health-Status-Properties (`is_connected`, `last_error`, `last_success_ts` — exposed via `/api/status`), Retry-Wrapper `_call_with_retry` und Re-Export-Aliasse für `_node_to_dict`/`_edge_to_dict`. Akzeptanzkriterien beide ✓: „Schreiblogik, Leselogik und Suche liegen nicht mehr in einer Datei" (`neo4j_read.py` + `neo4j_write.py` + `neo4j_search.py`) und „Mappings sind zentral wiederverwendbar" (`neo4j_mappings.py`). **Aufteilung gesamt: 195 + 381 + 513 + 57 + 118 = 1264 LOC in 5 Dateien** (Steigerung um +137 durch Modul-Docstrings, Mixin-Signaturen und Re-Export-Kommentare — explizite API-Dokumentation, kein Logic-Duplikat). **671 Backend-Tests** (unverändert) + 40 Frontend-Tests grün, alle bestehenden Suiten durch Mixin-MRO Verhalten-identisch. **Milestone v0.9.0 „Domain Cleanup" komplett**: Test-Counter 531 → 671 (+140 in v0.9.0-Pfad-A); Hot-Spots-Reduktion: `simulation_manager.py` 789 → 403 (−49 %), `report_agent.py` 3184 → 2179 (−31,6 %), `neo4j_storage.py` 1127 → 195 (−82,7 %). Arbeitsprotokoll: `docs/2026-05-01-issue50-sub3-search-mixin-arbeitsprotokoll.md`.
- **Issue #50 (EPIC-08-ST-01: Neo4jStorage in Read/Write/Search schneiden), Sub-Slice 2/3 — Write-Mixin extrahiert.** Alle 11 mutierenden Methoden aus `neo4j_storage.py` ins neue Modul `backend/app/storage/neo4j_write.py` (513 LOC) gezogen: Graph-Lifecycle (`create_graph`, `delete_graph`, `set_ontology`), Add-Data (`add_text` als 3-Phasen-Orchestrator, `_persist_episode` mit 163 LOC Cypher, `add_text_batch`, `wait_for_processing`), Temporal-Edges Issue #10 (`reinforce_relation`, `tombstone_relation`, `backfill_temporal_defaults`) und der Best-Effort-Helper `_evaluate_ontology_mutations`. `Neo4jStorage` erbt jetzt `(Neo4jReadMixin, Neo4jWriteMixin, GraphStorage)` und enthält nur noch Konstruktor, Health-Status, Retry-Wrapper und (vorerst) `search`. Imports `uuid`, `json`, `typing.List`/`Callable` und `services.ingestion_pipeline.*` entfallen aus `neo4j_storage.py`. **`neo4j_storage.py` schrumpft 701 → 228 LOC** (−67,5 %); seit Issue #50-Start von 1127 auf 228 (**−899, −79,8 %, vier Fünftel weg**). Keine neuen Tests — Verhalten Wire-Identical zur Vorher-Variante, gedeckt durch `test_neo4j_resilience` (6), `test_neo4j_ontology_wiring` (8), `test_ingestion_pipeline` (11), `test_neo4j_filtered_entities` (4). **671 Backend-Tests** (unverändert) + 40 Frontend-Tests grün. Folge-Sub-Slice: Search-Mixin (#50/3) schließt EPIC-08 und v0.9.0. Arbeitsprotokoll: `docs/2026-05-01-issue50-sub2-write-mixin-arbeitsprotokoll.md`.
- **Issue #50 (EPIC-08-ST-01: Neo4jStorage in Read/Write/Search schneiden), Sub-Slice 1/3 — Mappings + Read-Mixin extrahiert.** Erste Etappe des EPIC-08-Boss-Fights. Zwei neue Module: `backend/app/storage/neo4j_mappings.py` (118 LOC) mit den state-losen Helfern `node_to_dict`, `edge_to_dict` und `sanitize_label` (zentral wiederverwendbar — Akzeptanzkriterium ✓), und `backend/app/storage/neo4j_read.py` (381 LOC) mit `Neo4jReadMixin`, das alle 10 Read-Methoden aufnimmt (`get_ontology`, `get_all_nodes`, `get_node`, `get_node_edges`, `get_nodes_by_label`, `get_filtered_entities_with_edges`, `get_all_edges`, `get_edges_at_round`, `get_graph_info`, `get_graph_data`). Mixin-Pattern statt Komposition — `self._driver`/`self._call_with_retry` bleiben über Python-MRO geteilt, kein Konstruktor-Refactoring nötig. **`neo4j_storage.py` schrumpft 1127 → 701 LOC** (−426, −37,8 %, größter Einzelcut in v0.9.0-Pfad-A); `_node_to_dict`/`_edge_to_dict` als `staticmethod`-Re-Export der Modul-Funktionen erhalten, `_sanitize_label` (mitsamt `_LABEL_SAFE_RE`) nach `neo4j_mappings` umgezogen, weil Read- und Write-Pfad sie beide brauchen (zirkuläre Imports vermieden). 23 neue Tests in `test_neo4j_mappings.py` (3 Klassen): node-Mapping inkl. Internal-Field-Stripping und JSON-Fallback, edge-Mapping mit Temporalfeldern und episode_ids-Skalar-Wrapping, sanitize_label inkl. Backtick-Injection-Neutralization und 50-Zeichen-Limit. Bestehende 18 Neo4j-Tests unverändert grün — Verhalten via Mixin-MRO identisch. **671 Backend-Tests** (+23) + 40 Frontend-Tests grün. Folge-Sub-Slices: Write-Mixin (#50/2) und Search-Mixin (#50/3). Arbeitsprotokoll: `docs/2026-05-01-issue50-sub1-mappings-read-arbeitsprotokoll.md`.
- **Issue #51 (EPIC-08-ST-02: Ingestion-Pipeline in Schritte zerlegen) abgeschlossen.** Die 197-LOC-monolithische Methode `Neo4jStorage.add_text` ist in drei klar getrennte Phasen zerlegt: **Phase 1 (NER + RE)** und **Phase 2 (Batch-Embedding)** liegen als pure Funktionen `extract_entities_and_relations()` und `embed_entities_and_relations()` im neuen Modul `backend/app/services/ingestion_pipeline.py` (97 LOC); **Phase 3 (Persist)** bleibt storage-nah als private Methode `Neo4jStorage._persist_episode` (kwargs-only, 163 LOC, Cypher und Retry 1:1 portiert). `add_text` ist jetzt ein 47-Zeilen-Orchestrator — **−76 % gegenüber dem 197-LOC-Block** vorher. Domain-Logik (NER, Embedding) wandert nach `services/`, Persistenz bleibt in `storage/` — saubere Schichtentrennung als Vorbereitung für #50. 11 neue Tests in `test_ingestion_pipeline.py` (3 Klassen): NER-Delegation und Schema-Pass-Through; Batch-Embedding mit Empty-Skip, Konkatenations-Reihenfolge, Fact-Fallback, Position-Alignment, Crash → Leere-Vektoren, Nur-Entities/Nur-Relations; End-to-End-Komposition Phase 1 → 2. Bestehende Neo4j-Tests (`test_neo4j_resilience`, `test_neo4j_filtered_entities`, `test_neo4j_ontology_wiring`, 18 Tests) unverändert grün — Verhalten identisch. **648 Backend-Tests** (+11) + 40 Frontend-Tests grün. EPIC-08 zu 50 % (2/4); v0.9.0 zu 92 % (11/12). Verbleibend: nur noch **#50** (Boss-Fight, Read/Write/Search-Split). Arbeitsprotokoll: `docs/2026-05-01-issue51-ingestion-pipeline-arbeitsprotokoll.md`.
- **Issue #48 (EPIC-07-ST-04: Prompt-Building modularisieren) abgeschlossen — EPIC-07 vollständig (5/5).** Zwölf Prompt-Konstanten aus `backend/app/services/report_agent.py` ins neue Modul `backend/app/services/report_prompts.py` (356 LOC) gezogen, semantisch in vier Cluster gegliedert: **Planning** (`PLAN_SYSTEM_PROMPT_TEMPLATE`, `PLAN_USER_PROMPT_TEMPLATE`), **Sections** (`SECTION_SYSTEM_PROMPT_TEMPLATE`, `SECTION_USER_PROMPT_TEMPLATE`), **Reflection / ReACT-Loop** (`REACT_OBSERVATION_TEMPLATE`, `REACT_INSUFFICIENT_TOOLS_MSG`/`_ALT`, `REACT_TOOL_LIMIT_MSG`, `REACT_UNUSED_TOOLS_HINT`, `REACT_FORCE_FINAL_MSG`) und **Chat** (`CHAT_SYSTEM_PROMPT_TEMPLATE`, `CHAT_OBSERVATION_SUFFIX`). Re-Export im Service-Modul hält alle Konsumstellen (`plan_outline`, `_generate_section`, `_run_react_loop`, `chat_with_report`) unverändert. **`report_agent.py` schrumpft 2474 → 2179 LOC** (−295, −11,9 %); seit v0.9.0-Pfad-A-Beginn von 3184 auf 2179 (**−1005 LOC, −31,6 %, ein Drittel weg**). 47 neue Tests in `test_report_prompts.py`: 12 Existenz/Nicht-Leere (parametrisiert), 12 Platzhalter-Inventur (sichert `str.format`-Verträge), `__all__`-Vollständigkeit, 12 Re-Export-Identitätstests, 5 Semantik-Pinning-Tests (JSON-Outline-Forderung, Markdown-Header-Verbot, Tool-Counter-Anzeige, Report-First-Policy, knapper Suffix), 5 Format-Callability-Tests (fängt unbalancierte `{{`/`}}` zur Test- statt Laufzeit). **637 Backend-Tests** (+47) + 40 Frontend-Tests grün. EPIC-07 abgeschlossen; v0.9.0 zu 83 % (10/12). Verbleibend: nur noch EPIC-08 #50, #51 auf `neo4j_storage.py`. Arbeitsprotokoll: `docs/2026-05-01-issue48-prompt-modularisierung-arbeitsprotokoll.md`.
- **Issue #47 (EPIC-07-ST-03: Tool-Schema und Tool-Execution trennen) abgeschlossen — Sub-Slice 3/3, Tool-Execution extrahiert.** Der 130-LOC-Dispatcher `ReportAgent._execute_tool` ist als state-lose Top-Level-Funktion `execute_tool()` in das neue Modul `backend/app/services/tool_execution.py` (222 LOC) gezogen. Alle bisher aus `self` gelesenen Werte (`graph_tools`, `web_tools`, `graph_id`, `simulation_id`, `simulation_requirement`) sind jetzt explizite kwargs (kwargs-only via `*`); der Evidence-Callback (`_record_tool_evidence`) wird als optionaler `record_evidence`-Parameter durchgereicht. Vollständig portiert: alle 6 aktiven Tools (`insight_forge`, `panorama_search`, `quick_search`, `interview_agents`, `web_search`, `fetch_url`), die Backwards-Compat-Redirects (`search_graph`→`quick_search`, `get_simulation_context`→`insight_forge` jeweils via rekursiven Selbstaufruf) sowie die drei Raw-JSON-Tools (`get_graph_statistics`, `get_entity_summary`, `get_entities_by_type`). `ReportAgent._execute_tool` ist eine 12-Zeilen-Delegation. **`report_agent.py` schrumpft 2591 → 2474 LOC** (−4,5 %). 30 neue Tests in `test_tool_execution.py` (10 Test-Klassen: alle Tool-Pfade einzeln, parametrisierte Coercion-Edge-Cases, Backwards-Compat-Redirects, Evidence-Callback-Verhalten, Exception-Swallowing, Re-Export-Identität). **Issue #47 gesamt: report_agent 2705 → 2474 LOC (−231, −8,5 %); seit v0.9.0-Pfad-A-Beginn von 3184 auf 2474 (−22,3 %).** **590 Backend-Tests** (+59 für #47 gesamt) + 40 Frontend-Tests grün. EPIC-07 zu 80 % (4/5 Stories durch); v0.9.0 zu 75 % (9/12). Arbeitsprotokoll: `docs/2026-05-01-issue47-sub3-tool-execution-arbeitsprotokoll.md`.
- **Issue #47 (EPIC-07-ST-03: Tool-Schema und Tool-Execution trennen), Sub-Slice 2/3 — Tool-Validation extrahiert.** Parsing und Validation der LLM-Tool-Calls aus `backend/app/services/report_agent.py` ins neue Modul `backend/app/services/tool_validation.py` (108 LOC) gezogen: Modul-Konstante `VALID_TOOL_NAMES` (jetzt `frozenset`, vorher mutables Klassen-Set), pure Funktionen `is_valid_tool_call()` und `parse_tool_calls()`. Drei Parsing-Strategien (XML-Tag, Roh-JSON, Trailing-JSON nach Reasoning) sind 1:1 portiert; Key-Alias-Normalisierung (`tool`→`name`, `params`→`parameters`) bleibt als Vertrag dokumentiert. Klassen-Konstante `ReportAgent.VALID_TOOL_NAMES` entfernt (keine externen Caller); `ReportAgent._parse_tool_calls`/`_is_valid_tool_call` als 1-Zeilen-Delegationen erhalten. **`report_agent.py` schrumpft 2640 → 2591 LOC** (−1,9 %); seit v0.9.0-Pfad-A-Beginn von 3184 auf 2591 (−18,6 %). 21 neue Tests in `test_tool_validation.py` (7 Test-Klassen: Konstante, Validation, XML-Format, Raw-JSON, Tail-JSON, Edge-Cases, Re-Export-Identität). **560 Backend-Tests** (+25) + 40 Frontend-Tests grün. Folge-Sub-Slice: Tool-Execution (#47/3). Arbeitsprotokoll: `docs/2026-05-01-issue47-sub2-tool-validation-arbeitsprotokoll.md`.
- **Issue #47 (EPIC-07-ST-03: Tool-Schema und Tool-Execution trennen), Sub-Slice 1/3 — Tool-Beschreibungen extrahiert.** Die vier Tool-Beschreibungs-Konstanten (`TOOL_DESC_INSIGHT_FORGE`, `TOOL_DESC_PANORAMA_SEARCH`, `TOOL_DESC_QUICK_SEARCH`, `TOOL_DESC_INTERVIEW_AGENTS`) sind aus `backend/app/services/report_agent.py` in das neue Modul `backend/app/services/tool_schema.py` (96 LOC) gezogen. Re-Export im Service-Modul hält das Tool-Registry-Dict in `_define_tools()` und alle übrigen Aufrufstellen unverändert. Pattern analog zu `services/report_logger.py` (Issue #46). **`report_agent.py` schrumpft 2705 → 2640 LOC** (−2,4 %); seit v0.9.0-Pfad-A-Beginn von 3184 auf 2640 (−17 %). Vier neue Smoke-Tests (`test_tool_schema.py`) sichern Existenz, Nicht-Leere, Re-Export-Identität und Schema-Format (`[Use Cases]`/`[Return Content]`-Bereiche). **535 Backend-Tests** (+4) + 40 Frontend-Tests grün. Folge-Sub-Slices: Tool-Validation (#47/2) und Tool-Execution (#47/3). Arbeitsprotokoll: `docs/2026-05-01-issue47-sub1-tool-schema-arbeitsprotokoll.md`.
- **Issue #52 (EPIC-08-ST-03: Frontend-taugliche Graph-DTOs definieren) abgeschlossen.** Neue Datei `backend/app/models/graph.py` (170 LOC) mit drei dataclasses: `GraphNodeDTO`, `GraphEdgeDTO`, `GraphDataDTO`. Wire-Format-Spiegel zum Storage-Output von `Neo4jStorage.get_graph_data` inkl. der vier Enriched-Fields (`fact_type`, `source_node_name`, `target_node_name`, `episodes`-Legacy-Alias) — Frontend-Mapper in `frontend/src/components/graph/graphPanelData.js` bleibt unangetastet. `api/graph.py:get_graph_data` schickt die Response jetzt durch `GraphDataDTO.from_storage_dict().to_dict()` für stabiles, dokumentiertes Wire-Schema. **Wire-Identity getestet** (`test_graph_dtos.py`, 6 neue Tests, +6 → 531 Backend-Tests grün): jede künftige Storage-Schema-Änderung färbt die DTO-Tests rot, bevor das Frontend bricht. Snapshot/Diff-Endpoints (`/snapshot`, `/diff`) bleiben mit ihren `temporal_graph`-eigenen `to_dict()`-Outputs out-of-scope. Arbeitsprotokoll: `docs/2026-05-01-issue52-graph-dtos-arbeitsprotokoll.md`.
- **Issue #43 (EPIC-06-ST-03: Prepare-Service extrahieren) abgeschlossen — EPIC-06 vollständig (4/4).** Die 244-LOC-monolithische Methode `SimulationManager.prepare_simulation` ist in das neue Modul `backend/app/services/prepare_service.py` (376 LOC) gezogen, gegliedert in drei Phasen-Funktionen (`_phase_read_entities`, `_phase_generate_profiles`, `_phase_generate_config`) plus Top-Level-Orchestrator. Symmetrisch zum `branching_service`-Pattern. Manager-Methode bleibt als 14-Zeilen-Delegation erhalten — Caller in `api/simulation_prepare.py` und Tests unverändert. Manager-Imports `EntityReader`, `OasisProfileGenerator`, `SimulationConfigGenerator`, `json` entfernt. **`simulation_manager.py` schrumpft 622 → 403 LOC (−35 %)**; seit v0.9.0-Pfad-A-Beginn von 789 auf 403 (−49 %, fast halbiert). 520 Backend- + 40 Frontend-Tests grün. Arbeitsprotokoll: `docs/2026-05-01-issue43-prepare-service-arbeitsprotokoll.md`.
- **Issue #42 (EPIC-06-ST-02: Statusübergänge formalisieren) abgeschlossen.** Die FSM in `backend/app/services/simulation_state_machine.py` (vorher passives Modell) wird jetzt aktiv vom `SimulationManager` und allen API-Routen konsumiert. Zentraler Helper `SimulationManager._set_status(state, new)` validiert jeden Übergang gegen `ALLOWED_TRANSITIONS` und wirft `InvalidStatusTransition` (`ValueError`-Subklasse) bei Verletzung — die Fehlermeldung listet die erlaubten Nachfolgestatus. **FSM erweitert** um `FAILED → PREPARING` (Retry-Pattern: User triggert prepare nach Fehler nochmal). **Branching** durchläuft jetzt explizit `CREATED → PREPARING → READY` statt direkt READY. **Force-Restart** in `simulation_run.start_run` mit `force=True` nutzt eine separate Methode `_reset_to_ready(state, *, reason=…)` mit Log-Begründung — kein FSM-Übergang, sondern dokumentierter Lifecycle-Reset. Tests: `test_simulation_state_machine.py` von 25 auf 33 Tests (+`assert_valid_transition`-Verhalten, FAILED-Retry-Edge); 520 Backend-Tests grün. Arbeitsprotokoll: `docs/2026-05-01-issue42-fsm-integration-arbeitsprotokoll.md`.
- **Issue #46 (EPIC-07-ST-02: Report-Logging trennen) abgeschlossen.** `ReportLogger` und `ReportConsoleLogger` (zusammen 352 LOC) aus `backend/app/services/report_agent.py` (3053 LOC) in neue Datei `backend/app/services/report_logger.py` (377 LOC) verschoben. Re-Export im Service-Modul hält Modul-interne Aufrufe und potentielle Test-Mocks stabil. Type-Hint-Cleanup beim Move (`Optional[str]`/`Optional[int]` statt `str = None`/`int = None`); `import logging` von zwei lokalen Imports auf Modul-Ebene gehoben. `report_agent.py` schrumpft auf **2705 LOC** — von 3184 LOC vor Pfad A nun −15 %. Verhalten unverändert, 517 Backend- + 40 Frontend-Tests grün. Arbeitsprotokoll: `docs/2026-05-01-issue46-report-logger-arbeitsprotokoll.md`.
- **Issue #49 (EPIC-07-ST-05: Evidence-Layer explizit modellieren, p2) als bereits erledigt geschlossen.** Inventur nach Pfad A3 + Issue #103 zeigt: `EvidenceItem` und `ReportClaim` (Tracking pro Aussage inkl. `tool_name`/`query`/`agent_log_ref`) sind seit #45 in `backend/app/models/report.py`; `evidence_binder.py` (S4a) macht Cosine-basiertes Binding pro Claim mit Threshold; `confidence_calculator.py` (S6) implementiert die Vier-Komponenten-Formel als Vorbereitung für EPIC-15; Self-Evidence ist seit S5 in `audit_trail` ausgegliedert. Tests: `test_evidence_binder.py`, `test_confidence_calculator.py`, `test_report_manager.py`. Status-Doku: `docs/2026-05-01-issue49-evidence-layer-status.md`.
- **Issue #45 (EPIC-07-ST-01: Report-Models extrahieren) abgeschlossen.** Sechs Datenklassen (`ReportStatus`, `ReportSection`, `ReportOutline`, `Report`, `EvidenceItem`, `ReportClaim`) aus `backend/app/services/report_agent.py` (3184 LOC) in neue Datei `backend/app/models/report.py` (165 LOC) verschoben. Re-Export im Service-Modul hält bestehende Caller (`api/report.py`, `api/runs.py`, `test_report_manager.py`, `test_report_export.py`) unverändert. Unused Imports `dataclasses.dataclass` und `enum.Enum` aus `report_agent.py` entfernt; Datei schrumpft auf 3053 LOC (−4 %). `models/__init__.py` exportiert die neuen Klassen mit. Verhalten unverändert, 517 Backend- + 40 Frontend-Tests grün. Arbeitsprotokoll: `docs/2026-05-01-issue45-report-models-arbeitsprotokoll.md`.
- **Issue #44 (EPIC-06-ST-04: Branching-Service extrahieren) abgeschlossen.** Neue Datei `backend/app/services/branching_service.py` (230 LOC) übernimmt `list_branches`, `create_branch` und `_apply_persona_overrides` als Funktionsmodul mit `SimulationManager` als Parameter — vermeidet zirkuläre Importe und hält die Manager-API stabil (keine Caller-Anpassungen in `api/simulation_profiles.py` oder Tests nötig). `simulation_manager.py` reduziert sich um 167 LOC auf 622 (−21 %); Manager-Methoden sind 1-Zeilen-Delegationen, unused Imports `shutil`/`Config`/`ArtifactLocator`/`RunRegistry` entfernt. `SimulationStatus`-Import in `create_branch` ist lazy, damit der Manager-→-Service-Import nicht in einen Zyklus kippt. Verhalten unverändert, 517 Backend-Tests + 40 Frontend-Tests grün. Arbeitsprotokoll: `docs/2026-05-01-issue44-branching-service-arbeitsprotokoll.md`.
- **Issue #41 (EPIC-06-ST-01: SimulationRepository einführen) als bereits erledigt geschlossen.** Inventur zum v0.9.0-Slice-Start zeigt, dass `backend/app/services/artifact_store.py` (Issue #13, Hexagonal-Port mit `LocalFilesystemArtifactStore` und `InMemoryArtifactStore`) alle Akzeptanzkriterien retrospektiv erfüllt. `SimulationManager` (Konstruktor-DI, 7+ Store-Aufrufstellen) und `SimulationRunner` (`resolve_default_store()`) konsumieren den Store durchgängig; `state.json`-Zugriffe sind über den logischen Namen `"state"` gekapselt; File-Pfade zentralisiert in `ArtifactLocator`. Restliche `open()`-Calls im Manager betreffen Report-Meta (Folge-Issue #46) oder den Twitter-CSV-Export (out-of-scope). Status-Doku: `docs/2026-05-01-issue41-simulation-repository-status.md`.
- **Neo4j-Memory-Settings angehoben** (`docker-compose.yml`): `server.memory.pagecache.size` 256m → **4g**, `heap.max_size` 1g → 2g, `heap.initial_size` 256m → 512m. Reaktion auf I/O-Last bei mittelgroßen Graphen — der alte 256m-Pagecache verursachte Random-Reads von der Platte. Werte sind im Compose-File die Source-of-Truth, kein `.env`-Override nötig. Rollback durch alte Werte. Live verifiziert in Neo4j 5.18 via `CALL dbms.listConfig()`.

## [0.8.0] — 2026-05-01

Milestone „Frontend Consolidation" abgeschlossen — 13/13 Issues geschlossen, **519 Tests grün** (488 Backend + 31 Frontend). Schwerpunkt: 933-zeiliges `GraphPanel.vue` zerlegt in fünf Subkomponenten plus ein Render-Composable, Polling-Stack vereinheitlicht (alle 12 Polling-Stellen über `usePolling`, drei Log-Stellen über `useIncrementalLogPolling`), Composable-Test-Coverage von 11 auf 31 hochgezogen, EPIC-02 (Backend-API-Splitting) und EPIC-05-ST-01 (`usePolling`) retrospektiv als bereits erledigt dokumentiert. Vier weitere v0.8.0-Story-Issues (#37, #40, #68, alle EPIC-02-Stories) wurden durch Status-Dokus geschlossen — der eigentliche Code-Stand der Anwendung ist seit v0.6.0/v0.7.0 schon dort.

### Hinzugefügt

- **`frontend/src/components/graph/GraphHints.vue`** — neue rein präsentationale Komponente für Building-/Simulating-Hint und Simulation-Finished-Hint. Erste Etappe von Issue #34 (EPIC-04-ST-01: GraphPanel zerlegen). Props: `currentPhase`, `isSimulating`, `showFinishedHint`. Emits: `dismiss-finished`. Styles 1:1 aus `GraphPanel.vue` übernommen, kein Visual-Diff. Sub-Slice 2.1 von 3.
- **`frontend/src/components/graph/GraphToolbar.vue`** — neue rein präsentationale Header-Toolbar mit Refresh-, GraphML-, SVG-, PNG-, PDF- und Maximize-Buttons. Props: `loading`, `hasGraphId`, `hasGraphData`. Emits: `refresh`, `download-graphml`, `download-svg`, `download-png`, `print-pdf`, `toggle-maximize`. Styles 1:1 aus `GraphPanel.vue` übernommen, kein Visual-Diff. Sub-Slice 2.2 von 3.
- **`frontend/src/components/graph/GraphCanvas.vue`** — neue Komponente mit der gesamten D3-Renderlogik, SVG-Container, Selektions-State (`selectedItem`, `expandedSelfLoops`), Edge-Labels-Toggle, Loading/Empty-States, Hint- und Detail-Panel-Einbindung sowie allen vier Export-Funktionen (`downloadGraphml`, `downloadSvg`, `downloadPng`, `printPdf`). Exportiert die vier Funktionen via `defineExpose`, sodass die Toolbar-Click-Events vom Composer aus per `canvasRef.value.X()` aufgerufen werden. Props: `graphData` (bereits round-gefiltert), `entityTypes`, `loading`, `currentPhase`, `isSimulating`, `showFinishedHint`. Emits: `dismiss-finished-hint`. Styles 1:1 aus `GraphPanel.vue` übernommen. Sub-Slice 2.3 von 3 — schließt Issue #34 ab.
- **Frontend-Composable-Tests (Vitest).** `usePolling`, `useEventStream` und `useWorkspaceStatus` haben jetzt jeweils 6–7 Tests in `frontend/src/composables/__tests__/`. Schwerpunkte: Lifecycle (start/stop, Cleanup auf Unmount), Intervall-Pacing/Concurrent-Guard, `immediate`-Option, Handler-Wrapping mit `lastEventAt`-Reset, Fehlerpfade, Map-Fallback. Setup: `jsdom` und `@vue/test-utils` als Dev-Deps; `frontend/vite.config.js` `test.environment` von `node` auf `jsdom` umgestellt. **Gesamt-Frontend-Tests jetzt 31** (vorher 11). **Schließt Issue #84 (EPIC-10-ST-07) ab — und damit Milestone v0.8.0.**
- **`frontend/src/components/graph/graphPanelData.js` Graph-DTO-Mapper härter dokumentiert.** JSDoc-Typdefinitionen `GraphNodeViewModel` und `GraphEdgeViewModel` an den Modul-Header; `buildGraphRenderData` hat jetzt einen vollen `@returns`-Block. `normalizeEdgeAliases(edge)` extrahiert die einzige Stelle im Modul, an der die Backend-Aliasse `fact_type` und `name` aufgelöst werden — vorher waren die Aliasse inline in `buildCurvedEdge`. Kein Verhaltens-Diff. **Schließt Issue #36 (EPIC-04-ST-03) ab.**
- **`frontend/src/composables/useIncrementalLogPolling.js`** — neues Composable, das die duplizierte Append-/Cursor-/Scroll-Logik aus drei Log-Konsumenten zusammenführt. Vertrag: `useIncrementalLogPolling({ fetcher, intervalMs, parseLine })` → `{ lines, containerRef, polling, reset, tick }`. `Step3Simulation.vue` (Simulation-Console) und `Step4Report.vue` (Agent-Log mit `parseAgentEntry` als `parseLine`-Hook plus Console-Log raw) sind umgestellt — der Konsument hängt nur seinen `containerRef` an das Log-Element und liest `lines`. Cursor `since_line` und Auto-Scroll-Logik leben jetzt an einer Stelle. **Schließt Issue #39 (EPIC-05-ST-03) ab.**
- **`frontend/src/composables/useGraphRender.js`** — neues Composable, das die D3-Force-Renderlogik aus `GraphCanvas.vue` heraushebt. Übernimmt den gesamten Render-Lifecycle: `window.resize`-Listener, deep-watch auf `graphData`, watch auf `showEdgeLabels` (Live-Toggle ohne Neuaufbau), Erst-Render im `onMounted`, Cleanup von `currentSimulation` im `onUnmounted`. Eingaben: `svgRef`, `containerRef`, `graphData`, `entityTypes`, `showEdgeLabels`. Ausgabe: `selectedItem`-Ref (D3-Click-Handler schreiben rein, Konsument darf zurücksetzen) plus `render` als manueller Trigger. **Schließt Issue #35 (EPIC-04-ST-02) ab.**

### Geändert

- **`frontend/src/components/GraphPanel.vue` ist jetzt reine Kompositionsdatei** (933 → **98 Zeilen**, −90 %). Hält nur noch `selectedRound`/`showSimulationFinishedHint`/`wasSimulating` plus `displayedGraphData`/`entityTypes`/`maxRound` als Computed, dazu den `watch` auf `props.isSimulating`. Komponiert `<GraphToolbar>`, `<GraphCanvas>`, `<GraphLegend>`, `<GraphRoundSlider>`. Toolbar-Click-Events werden via `canvasRef`-Methoden in den Canvas durchgereicht. **Issue #34 (EPIC-04-ST-01) abgeschlossen** — Zielstruktur aus dem Backlog vollständig erreicht.
- **`frontend/src/components/graph/GraphCanvas.vue`** schlanker (641 → 375 Zeilen): `renderGraph` plus die drei Watch-/Resize-Lifecycle-Hooks sind jetzt im Composable `useGraphRender`. Die Komponente reicht nur noch `svgRef`/`containerRef`/`showEdgeLabels` rein und konsumiert das zurückgegebene `selectedItem`-Ref. Export-Funktionen bleiben hier (DOM-nah) — sie sind kein Render-Belang.
- **`MainView.vue` und `SimulationRunView.vue` migrieren ihre vier raw-`setInterval`-Stellen auf das zentrale `usePolling`-Composable** (Build-Task, Graph-Daten-Polling, Global-Status, Graph-Refresh). Cleanup bei Unmount übernimmt jetzt `usePolling` selbst (`onUnmounted(stop)` ist im Composable verdrahtet); View-seitige `onUnmounted`-Aufräumblöcke für Polling sind entfallen. Kein zusätzlicher `useTaskPolling`-Wrapper — die Akzeptanz ist mit dem bestehenden `usePolling` voll erfüllt. **Schließt Issue #38 (EPIC-05-ST-02) ab.** Damit nutzen alle 12 Polling-Stellen im Frontend denselben Mechanismus.
- **Issue #37 (EPIC-05-ST-01: generisches `usePolling`) als bereits erledigt geschlossen.** Inventur zum Slice-Start zeigt: `frontend/src/composables/usePolling.js` existiert seit v0.4.1 mit `start`/`stop`/`tick`-Schnittstelle plus `onUnmounted`-Cleanup; 8 Konsumenten (Step2EnvSetup ×3, Step3Simulation ×2, Step4Report ×3) nutzen es bereits. Vier raw-`setInterval`-Stellen in `MainView.vue` und `SimulationRunView.vue` sind Scope der Folge-Issues #38/#39. Status-Doku: `docs/2026-05-01-issue37-usepolling-status.md`.
- **Issue #68 (EPIC-13-ST-01: Persona Review UI) als bereits erledigt geschlossen.** Die Persona-Review-Oberfläche wurde vollständig in den Slices 2.1–2.4 implementiert und in v0.7.0 ausgeliefert: `usePersonaReview.js`-Composable, Quality-Report, Approve/Reject/Edit in `Step2EnvSetup.vue`. Status-Doku: `docs/2026-05-01-issue68-persona-review-ui-status.md`.
- **Issue #40 (EPIC-05-ST-04: SSE/WebSocket-Strategie) als bereits erledigt geschlossen.** Der Spike ist durch die Implementierung von Issue #9 beantwortet: SSE (`useEventStream.js`) ist der gewählte Ansatz für Run-Live-Updates und Report-Stream. WebSocket brächte keinen Mehrwert für die unidirektionalen Use-Cases. Status-Doku: `docs/2026-05-01-issue40-sse-strategy-status.md`.
- **EPIC-02 (Backend-API-Splitting) als bereits erledigt geschlossen.** Die Inventur zum v0.8.0-Slice-Start zeigt, dass der Split aus `backend/app/api/simulation.py` in zehn fokussierte Module bereits in v0.4.0 vollständig umgesetzt wurde. `simulation.py` ist seither ein 17-zeiliger Compatibility-Shim ohne Routen. 48 Routen liegen unter `simulation_bp` thematisch verteilt (Lifecycle 4, Prepare 2, Run 12, Profiles 16, Interviews 4, History 4, Entities 3, Stream 1, Metrics 2), gemeinsame Helfer in `simulation_common.py`. Issue #29 wird retrospektiv durch `docs/2026-05-01-epic02-api-split-status.md` erfüllt; #30, #31, #32, #33 schließen mit Verweis auf v0.4.0-CHANGELOG-Eintrag und dieses Status-Dokument. Konsequenz: v0.8.0-Backlog reduziert sich von 13 auf 8 echte Issues (EPIC-04 ×3, EPIC-05 ×4, EPIC-10 ×1).

## [0.7.0] — 2026-05-01

Milestone "API Contracts & Quality Gate" abgeschlossen: einheitliche `ApiErrorCode`-Envelopes über Backend und Frontend, dokumentierte Response-Schemas mit JSON-Schema-Tests, Frontend-Mapper für code-basierte deutsche Fehler-Toasts, deklarative Simulation-State-Machine als Vorbereitung auf EPIC-06, und ein erstes Vitest-Setup im Frontend. 13/13 Issues geschlossen, **499 Tests grün** (488 Backend + 11 Frontend).

### Hinzugefügt

- **Simulation-State-Machine (deklarativ)** — neuer `backend/app/services/simulation_state_machine.py` mit `ALLOWED_TRANSITIONS`-Tabelle für alle 8 `SimulationStatus`-Werte plus `is_valid_transition`, `get_allowed_next`, `is_terminal`. Tabelle spiegelt 1:1 die 13 real beobachteten Transition-Call-Sites in Manager und API. **In v0.7.0 nur passiv** — EPIC-06-ST-02 wird die Helper aktiv in `SimulationManager` und API-Routes integrieren. Tests: `backend/tests/test_simulation_state_machine.py` (46 Tabellen-Tests) und `backend/tests/services/test_simulation_manager_transitions.py` (23 Behavior- und Compliance-Tests, pinnen Code gegen Tabelle).
- **Frontend-Vitest-Setup** — `vitest@4.1.5` als Dev-Dependency, minimaler `test`-Block in `frontend/vite.config.js` (Triple-Slash-Reference auf `vitest/config`, `environment: 'node'`). Erste 11 Smoke-Tests in `frontend/src/api/__tests__/envelope.spec.ts` decken `unwrap`, `ApiError`-Konstruktor und `isApiError`-Type-Guard ab. Root-`npm run check` hat jetzt 5 Stufen (lint:backend → test:backend → lint:frontend → test:frontend → build:frontend).
- **`docs/api-contracts.md`** — Single Source of Truth für Response-Envelopes und alle 23 `ApiErrorCode` (HTTP-Status, Backend-Default-DE, Frontend-UX-DE, Retry-Flag). Inhalte 1:1 aus `backend/app/utils/api_errors.py` und `frontend/src/api/errorMessages.ts` extrahiert. `.gitignore` erhält Negativ-Pattern für die zwei getrackten Files unter `/docs/` (`api-contracts.md` plus Release-Notes), Rest des Ordners bleibt lokal.
- **`docs/2026-05-01-v0.7.0-release-notes.md`** — Release-Notes mit Highlights, Migrations-Hinweisen und Test-Stand für Frontend- und Backend-Entwickler.
- **`ApiErrorCode`-Katalog** — 23 standardisierte Fehlercodes mit deutschen Default-Meldungen in `backend/app/utils/api_errors.py` (`INVALID_ID`, `NOT_FOUND`, `VALIDATION_FAILED`, `BAD_REQUEST`, `METHOD_NOT_ALLOWED`, `AUTH_REQUIRED`, `AUTH_INVALID`, `AUTH_FORBIDDEN`, `RATE_LIMITED`, `TIMEOUT`, `SERVICE_UNAVAILABLE`, `NEO4J_UNAVAILABLE`, `LLM_UNAVAILABLE`, `ONTOLOGY_MISSING`, `ONTOLOGY_GENERATION_FAILED`, `SIMULATION_NOT_PREPARED`, `SIMULATION_ALREADY_RUNNING`, `PERSONA_REVIEW_REQUIRED`, `UPLOAD_TOO_LARGE`, `UNSUPPORTED_FORMAT`, `INTERNAL_ERROR`, `NOT_IMPLEMENTED`, `GRAPH_BUILD_IN_PROGRESS`). `json_error()` akzeptiert `ApiErrorCode` als Argument und fällt auf Default-Message zurück; neuer `message=`-Override-Kwarg ermöglicht punktuelle Anpassung. Backwards-Compat: 198 bestehende positional-string-Aufrufe funktionieren unverändert.
- **Frontend-Envelope-Mapper** — neuer `frontend/src/api/envelope.ts` (`ApiError`-Klasse mit `code`/`status`/`details`/`originalResponse`, `unwrap<T>()` Helper, `isApiError()` Type-Guard) und `frontend/src/api/errorMessages.ts` (Map aller 23 Codes auf deutsche UX-Texte plus `userMessageFor()`/`isRetryable()` Helfer). Response-Interceptor in `frontend/src/api/index.js` wirft jetzt strukturierte `ApiError`-Exceptions. `HistoryDatabase.vue` als Smoke-Komponente nutzt code-basierte Toast-Texte mit bedingtem Retry-Button (nur bei transient-Codes: `service_unavailable`, `neo4j_unavailable`, `llm_unavailable`, `rate_limited`, `timeout`, `ontology_generation_failed`).
- **Response-Schema-Tests** — neuer `backend/tests/api/test_response_schemas.py` mit 31 Tests über 7 Domänen (Project, Simulation, RunStatus, ReportStatus, GraphData, OntologyDefinition, Persona). Pure JSON-Schema-Validation ohne Live-Endpoints. `jsonschema>=4.0.0` als Dev-Dependency.
- **Endpoint-Coverage** — 16 Tests in `backend/tests/api/test_graph_endpoints.py` plus 23 in `backend/tests/api/test_simulation_endpoints.py` validieren `code`-Feld über alle migrierten Pfade.
- CI-Security-Stage ergänzt: Frontend-`npm audit`, Python-`pip-audit` auf Basis des `uv.lock`-Exports und Gitleaks Secret Scan laufen als eigener GitHub-Actions-Job.
- `.gitleaksignore` ergänzt zwei fingerprint-genaue False-Positive-Baselines aus der bestehenden Git-Historie.
- `docs/p1-security-ci-error-envelope-protokoll.md` dokumentiert P1-Umsetzung, Checks und Rollback.
- `docs/v1-development-log.md` dokumentiert die v1.0-Entwicklungsschritte.
- Tests für den Auth-Guard decken Open-Mode, fehlende Tokens sowie Header-/Bearer-/Query-Token ab.
- Simulationsstarts akzeptieren zusätzlich `simulation_days`; die UI schreibt daraus `time_config.total_simulation_hours`, während das bestehende Rundenlimit als optionaler Cap erhalten bleibt.
- Lokale Persona-Bibliothek: erzeugte oder manuelle Personas können gespeichert, gelistet, gelöscht und in späteren Simulationen wiederverwendet werden.

### Geändert

- **API-Layer einheitlich auf `ApiErrorCode` migriert** — `backend/app/api/graph.py` (27 Stellen) und alle 9 Simulation-Module (107 Stellen). Codes semantisch vergeben: `INVALID_ID` für Validierungsfehler, `NOT_FOUND` (404), `VALIDATION_FAILED` (400), `SERVICE_UNAVAILABLE` (503) für System-Ausfälle, `SIMULATION_ALREADY_RUNNING` / `PERSONA_REVIEW_REQUIRED` (409 Conflict). Frontend kann Fehler jetzt semantisch behandeln — `service_unavailable` und `neo4j_unavailable` triggern Retry-UI, `not_found` zeigt klare Toast-Meldung statt HTTP-Status-Dump.
- **Internationalisierung bereinigt** — Chinesische Punctuation aus dem API-Layer entfernt (`，` → `, `, `（）` → `()`, 6 Stellen). Pidgin-English-Capitalizations (`max_rounds Must be...` → `must`, `Or` → `or`) gleich mitkorrigiert.
- `_require_env_alive` in `simulation_interviews.py` liefert jetzt 503 (Service Unavailable) statt implizit 400 — semantisch korrekt für Subprocess-Ausfall.
- API-Error-Envelopes sind für 5xx-Fehler jetzt security-safe: ungefangene Exceptions liefern außerhalb von `Config.DEBUG=true` nur noch generische Meldungen plus `code`, während konkrete Exception-Details im Log bleiben.
- Backend-Lockfile sicherheitsseitig aktualisiert: `pip-audit`-Findings in 14 Python-Paketen durch kompatible `uv.lock`-Upgrades reduziert; 6 verbleibende Upstream-Pin-Findings sind eng im CI dokumentiert und gebaselined.
- API-Contract-Härtung begonnen: Auth-Fehler aus `token_required()` und `install_blueprint_guard()` nutzen jetzt die zentrale `json_error()`-Envelope mit `success: false`.
- `@handle_api_errors` setzt seine dokumentierte Contract-Regel jetzt auch technisch um: rohe `dict`-Returns werden in `json_success()` gewrappt.
- Framework-seitige `/api/*`-HTTP-Fehler und ungefangene API-Exceptions liefern jetzt ebenfalls standardisierte JSON-Envelopes statt HTML-Fehlerseiten.
- Ontologie-Generierung ist nicht mehr auf exakt 10 Entitätstypen fixiert; Defaults sind 8-16 Typen und per `ONTOLOGY_MIN_ENTITY_TYPES` / `ONTOLOGY_MAX_ENTITY_TYPES` konfigurierbar.

### Behoben

- **`graph.py:269` Bug**: `json_error("...", task_id=...)` warf seit jeher `TypeError` (task_id kein bekannter kwarg), wurde als 500 ausgeliefert. Jetzt sauber 409 Conflict mit `extra={"task_id": ...}`.

## [0.6.1] — 2026-04-27

Kleines Hygiene-Release nach v0.6.0: Dependency-Advisories im Frontend beseitigt, Versionsdrift korrigiert und Doku/Testzahlen synchronisiert.

### Geändert

- Frontend-Lockfile per kompatiblem `npm audit fix` aktualisiert: `axios` → 1.15.2, `follow-redirects` → 1.16.0, `postcss` → 8.5.12.
- `/api/status` liest die Backend-Version jetzt aus `app.__version__` statt aus einem alten Literal.
- README und Roadmap auf den aktuellen Quality-Gate-Stand gebracht: 207 Backend-Tests grün, 2 Redis-Integrationstests skippen ohne `TEST_REDIS_URL`.

### Sicherheit

- `npm audit --omit=dev` ist im Frontend wieder ohne Findings.
- README-Warnung korrigiert: Agora hat inzwischen optionalen `AGORA_AUTH_TOKEN`-Schutz und restriktive CORS-Defaults, bleibt aber nicht für öffentlichen Betrieb gedacht.

## [0.6.0] — 2026-04-26

Ship des v0.6-Backlogs: RPC/Interview-IPC-Migration auf Redis Pub/Sub (#17), Frontend Round-Slider für den Temporal-Graph (#10 optional), EPIC-03 Workspace-Konsolidierung vollständig (Layout-Shell + State-Composables), konfigurierbare Hybrid-Search-Weights, LLM-Retry-Resilienz, NER-→-Ontology-Mutation-Wiring (#11 Phase 2). 207 Backend-Tests, Frontend warning-frei.

### Hinzugefügt

- **Hybrid-Search-Weights konfigurierbar.** `Config.HYBRID_SEARCH_VECTOR_WEIGHT` (Default 0.7) und `Config.HYBRID_SEARCH_KEYWORD_WEIGHT` (Default 0.3) lesen aus den gleichnamigen env-Vars. `SearchService` nimmt beide als optionale Constructor-Argumente; `Neo4jStorage` reicht die Config-Werte automatisch durch. Class-Konstanten `VECTOR_WEIGHT`/`KEYWORD_WEIGHT` bleiben als Backward-Compat. Doku in `.env.example` + CLAUDE.md/AGENTS.md. Tests: `tests/test_search_service.py` (5).
- **Workspace-State-Composables (EPIC-03 ST-02 + ST-03).** Zwei neue Composables unter `frontend/src/composables/` ersetzen identische Boilerplate-Blöcke aus den 5 Pipeline-Views:
  - `useWorkspaceMode(initialMode)` kapselt `viewMode` + `leftPanelStyle` + `rightPanelStyle` + `toggleMaximize` + `workspaceModes`. Alle 5 Views (Main, Simulation, SimulationRun, Report, Interaction) nutzen es; identische 12-Zeilen-Blöcke pro Datei sind weg.
  - `useWorkspaceStatus({ initial, map, fallback })` kapselt `currentStatus` + `statusKind` + `statusText` + `updateStatus` mit konfigurierbarem `{ status: { kind, text-key } }`-Mapping; löst die `useI18n()`-Aufrufe gleich im Composable auf, sodass die Views nur noch `statusText` direkt rendern. SimulationView, ReportView und InteractionView konsumieren das Composable. SimulationRunView behält bewusst seine paused-Overlay-Computed (Status mit Round-Counter), MainView seine phasen-basierte Status-Logik (`error` + `currentPhase`) — beide Sonderfälle sind im Composable-Header dokumentiert.
  - Schließt EPIC-03 vollständig ab (ST-01 Layout-Shell war schon vor diesem Sprint erledigt).
- **Frontend Round-Slider für Temporal-Graph-Snapshots (#10 optional).** Neue Komponente `frontend/src/components/graph/GraphRoundSlider.vue` lebt direkt im `GraphPanel` und blendet sich automatisch ein, sobald der Graph mindestens eine Simulationsrunde gesehen hat (`maxRound > 0`). Filter läuft client-seitig: `filterEdgesAtRound` in `graphPanelData.js` mirrort die Backend-Snapshot-Semantik (`valid_from_round <= R AND (valid_to_round IS NULL OR valid_to_round > R)`) — kein zusätzlicher API-Round-Trip beim Scrubben. Live-Mode (Default) zeigt alle aktuellen Edges; Reset-Button springt zurück. `getGraphSnapshot` und `getGraphDiff` in `frontend/src/api/graph.js` ergänzt für späteren server-side Bedarf (Diff-View, große Graphen). Schließt einen offenen v0.6.0-Roadmap-Punkt ab.
- **Frontend `useSystemLog`-Composable** (`frontend/src/composables/useSystemLog.js`). Ersetzt fünf identische `addLog`/`systemLogs`-Implementierungen in `MainView` / `SimulationView` / `SimulationRunView` / `ReportView` / `InteractionView` durch eine Quelle der Wahrheit. Cap pro Call-Site konfigurierbar (100 vs. 200 — bestehendes Verhalten erhalten). Schließt den UI-Konsolidierungs-Teil von EPIC-03 ab.
- **TypeScript-PoC.** `frontend/tsconfig.json` mit `allowJs: true` für sukzessive Migration; `frontend/src/types/run.ts` als erstes typisiertes Schema für die Run-Registry-API; `frontend/src/api/runs.ts` als migriertes Pendant. Vite/esbuild kompiliert TS nativ — keine zusätzliche Dependency nötig. Bereitet EPIC-14 (Frontend-API-Schicht typisiert) vor.
- **Issue #17 Phase D — RPC/Interview-IPC auf Redis Pub/Sub migriert.**
  - `RedisEventBus.publish` / `subscribe` / `request_response` für `CHANNEL_RPC_COMMAND` und `rpc.response.*` laufen jetzt **hybrid**: Redis Pub/Sub für Live-Latenz + File-IPC parallel als Rolling-Upgrade-Pfad und Fallback. Backend bewertet beide Quellen mit `_await_response`, first-come-wins, der Verlierer wird via `_cleanup_rpc_artifacts` aufgeräumt um Doppel-Dispatch zu verhindern. `request_response` armiert die Pub/Sub-Subscription **vor** dem Publish, um Race-Conditions mit schneller antwortenden Subprozessen zu vermeiden.
  - Subprocess-Listener `backend/scripts/subprocess_redis_bridge.py` (`RedisIPCBridge`): async `redis.asyncio` Pub/Sub im OASIS-Eventloop, `publish_response`-Mirror, sauberes `aclose()`. Stays inactive wenn `REDIS_URL` unset oder Redis unerreichbar.
  - Cutover für alle drei OASIS-Subprocess-Scripts (`run_reddit_simulation.py`, `run_twitter_simulation.py`, `run_parallel_simulation.py`): `IPCHandler.send_response` → async mit Redis-Mirror, `_execute_command` extrahiert (gemeinsamer Pfad für File-Polling und Bridge), `dispatch_bus_event` als Bridge-Callback, `seen_command_ids` dedupliziert beide Pfade.
  - Tests: 3 neue Hybrid-Round-Trip-Tests in `test_event_bus_redis.py` (Backend-publish reicht raw-Redis-Subscriber durch, raw-Redis-publish wird von Backend-subscribe konsumiert, voller `request_response`-Round-Trip ohne File-I/O), File-Fallback-Test als Regression-Garantie für Rolling-Upgrade. 3 Bridge↔Bus-Integrationstests in `test_subprocess_redis_bridge.py` (End-to-end ohne OASIS, `REDIS_URL=None`-Pfad, `publish_response` reicht raw-Subscriber durch). Phase-B-Delegation-Tests (`test_event_bus_redis_rpc_delegation.py`) gelöscht — sie sicherten den alten File-Pfad ab und sind mit der Migration obsolet.
  - Backout-Plan unverändert: `EVENT_BUS_BACKEND=file` setzen → Container baut `FilePollingEventBus`, Subprocess-Bridge geht in Standby, alles läuft wie vor #17.
  - Plan-Dokument `docs/archive/plans/issue-17-rpc-redis-plan.md` reflektiert den Abschluss der Phasen 1–6.
- **Issue #11 Phase 2 — NER → OntologyMutationService verdrahtet.** `Neo4jStorage` bekommt einen Setter `set_ontology_mutation_service()` (Late-Binding, vermeidet die zirkuläre Dependency `OntologyManager → Neo4jStorage → Service`). In `add_text` filtert `_evaluate_ontology_mutations()` NER-Output gegen die aktuelle `entity_types`-Liste der Ontologie und reicht alles Unbekannte an `OntologyMutationService.evaluate_batch` weiter — der Service entscheidet per Mode (`disabled`/`review_only`/`auto`) ob nur geloggt, im Audit-Log gehalten oder direkt patcht. `AgoraContainer.ontology_mutation_service()` ist jetzt Singleton und wird in `create_app` eagerly konstruiert, damit das Late-Binding noch vor dem ersten Build greift. Service-Exceptions werden geschluckt — Ontologie-Mutation ist Best-Effort und darf Ingestion nie blockieren. Tests: `test_neo4j_ontology_wiring.py` (8).

### Geändert

- **Backend-Lint-Scope auf `app/ tests/` gehoben.** `npm run lint:backend` lief bisher als gescopter Whitelist-Rollout; jetzt deckt er den ganzen Backend-Baum ab. 31 Pre-existing Ruff-Findings dafür erschlagen: 16 auto-fixed (F401/F541/F841), 15 manuell (E402-Importsortierung in `neo4j_storage.py`, E741 `l` → `lbl`, E722 bare-except → `(JSONDecodeError, ValueError)`, F841 ungenutztes Listing). Erledigt das „schrittweise Ausweitung von Ruff Richtung Default-strict" aus dem CLAUDE.md-Backlog.

### Behoben

- **`HistoryDatabase.vue::loadRuns()` schluckte Backend-Fehler ohne Catch.** Wenn `listRuns()` einen Reject lieferte (Run-Registry-API down, Auth-Token falsch, Timeout), bubbelte der Promise-Reject als unhandled Rejection durch — UI zeigte stumm eine leere Liste, Browser-Konsole spammte „Axios response error". Neuer `.catch`-Branch setzt `loadError`, rendert eine sichtbare Fehlerzeile mit „Erneut versuchen"-Button und behält die leere Liste konsistent.
- **LLM-Resilienz gegen transiente Upstream-5xx.** `LLMClient.chat()` und `LLMClient.describe_image()` rufen den OpenAI-kompatiblen Endpoint jetzt über `llm_call_with_retry()` (`backend/app/utils/retry.py`) auf — Exponential-Backoff mit Jitter analog zu `neo4j_call_with_retry`. Retry auf `APIConnectionError`, `APITimeoutError`, `RateLimitError` und `APIStatusError` mit Status 5xx / 408 / 429; 4xx-Client-Fehler fallen sofort durch. Ollama-Cloud-Hickser killen damit nicht mehr die Pipeline-Init (Symptom: `POST /api/graph/ontology/generate` → `Error code: 500 - {'error': 'Internal Server Error (ref: ...)'}`). Konfigurierbar per `LLM_MAX_RETRIES` (Default 3), `LLM_RETRY_INITIAL_DELAY` (1.0 s), `LLM_RETRY_MAX_DELAY` (30 s). Tests: `test_retry.py` (+4 → 13).

## [0.5.0] — 2026-04-24

Ship der kompletten Priorisierungs-Kette #13 → #14 → #9 → #10 → #12 → #11 plus Release-Polish.

### Hinzugefügt

- **Issue #9 Phase A–C — Event Bus + SSE Bridge.**
  - `SimulationEventBus`-Port (`backend/app/services/event_bus.py`) mit `InMemoryEventBus`, `FilePollingEventBus` (offline-first, wrappt `SimulationArtifactStore`) und `RedisEventBus` (`backend/app/services/event_bus_redis.py`).
  - Redis-Service (`redis:7-alpine` mit Healthcheck + Volume) in `docker-compose.yml`; `Config.REDIS_URL` + `Config.EVENT_BUS_BACKEND` (`auto`/`redis`/`file`) wählen den Transport im `AgoraContainer`.
  - `SimulationRunner._save_run_state` spiegelt Snapshots auf `CHANNEL_STATE`.
  - SSE-Endpoint `GET /api/simulation/<id>/stream` (`backend/app/api/simulation_stream.py`) bridged `state`/`control` an `EventSource`-Clients. Heartbeat alle 15 s.
  - Frontend: `useEventStream.js` + `api/stream.js`; `Step3Simulation.vue` ersetzt 2,5-s-Status-Polling durch den Stream.
  - Tests: `test_event_bus.py` (13), `test_event_bus_redis.py` (6, skip ohne Redis), `test_simulation_stream.py` (2).
- **Issue #10 — Temporal Graph Evolution.**
  - RELATION-Kanten: `valid_from_round`, `valid_to_round`, `reinforced_count` (neu in `Neo4jStorage.add_text` + `_edge_to_dict`).
  - `Neo4jStorage.get_edges_at_round` (coalesce-Legacy-Semantik), `reinforce_relation`, `tombstone_relation`, idempotenter `backfill_temporal_defaults`. `GraphStorage`-Protocol bekommt Default-Stubs für Non-Neo4j-Adapter.
  - `TemporalGraphService` (`backend/app/services/temporal_graph.py`) mit `get_snapshot` + `compute_diff` (added / removed / reinforced); lazy Per-Graph-Backfill.
  - API: `GET /api/graph/snapshot/<gid>/<round>` und `GET /api/graph/diff/<gid>?start_round=..&end_round=..`.
  - Ingest: `GraphBuilderService` stamped `round_num=0`, `GraphMemoryUpdater` nutzt max(round_num) des Batches.
  - Tests: `test_temporal_graph.py` (7).
- **Issue #12 — Polarization-Metriken.**
  - `NetworkAnalyticsService` (`backend/app/services/network_analytics.py`) — `networkx`-Interaktionsgraph, Louvain-Communities, Echo-Chamber-Index, Betweenness-Bridge-Agents.
  - `networkx>=3.2` als Runtime-Dep.
  - API: `GET /api/simulation/<id>/metrics` mit `window_size_rounds` + `platform` Query-Params.
  - Dokumentation `docs/analytics.md` erklärt Filter (nur gerichtete Aktionen), Graph-Projektion, Heuristiken, API-Schema, Follow-ups.
  - Tests: `test_network_analytics.py` (7).
- **Issue #11 Phase 1 — Dynamic Ontology Mutation.**
  - `OntologyManager` (`backend/app/services/ontology_mutation.py`) mit per-graph `threading.Lock` für thread-safe `update()`.
  - `OntologyMutationService` mit Modi `disabled`/`review_only`/`auto`, pluggable `ConceptScorer` (Default-Heuristik: rejectet generische Platzhalter, belohnt PascalCase + context match), bounded In-Memory-Audit-Log + optional `audit_sink`.
  - Config: `ONTOLOGY_MUTATION_MODE` (default `disabled`), `ONTOLOGY_MUTATION_MIN_CONFIDENCE` (default 0.6).
  - `AgoraContainer.ontology_manager` + `ontology_mutation_service()`.
  - Tests: `test_ontology_mutation.py` (14) — Sanitization, Scorer, Manager-Idempotenz, Thread-Safety (20 concurrent writers), Modes, Audit-Log.
- **Issue #14 — `AgoraContainer` (DI).** Hand-rolled Container ersetzt `app.extensions[...]`-Service-Locator; Singletons (`neo4j_storage`, `artifact_store`, `event_bus`, `ontology_manager`) + Factories (`graph_builder()`, `temporal_graph()`, `network_analytics()`, `ontology_mutation_service()`). `app.extensions['*']` bleiben als Backward-Compat-Aliase. Tests ohne Flask-App-Context (`test_container.py`).
- **Issue #13 — `SimulationArtifactStore`-Port.** Hexagonal-Port (`backend/app/services/artifact_store.py`) mit `LocalFilesystemArtifactStore` (Produktion, atomare Writes) und `InMemoryArtifactStore` (Tests). Alle Simulation-JSON-I/Os laufen über den Store. Constraint-Guard `tests/test_no_json_io_leakage.py` hält die SoC-Regel aufrecht.
- **fix(startup)** — Neo4j-Startup-Exception wird in `app.extensions['neo4j_storage_error']` persistiert und über `/api/status` + `/api/simulation/available-models` ausgeliefert. UI (`Home.vue`) zeigt den echten Fehler statt eines Platzhalters.
- **Dependency-Additionen:** `redis>=5.0.0`, `networkx>=3.2`.
- **Contract- und Smoke-Tests:** `test_artifact_store.py` (30), `test_no_json_io_leakage.py` (3).

### Geändert

- `Neo4jStorage.add_text` und `add_text_batch` akzeptieren jetzt einen optionalen `round_num`-Parameter.
- `SimulationIPCClient/Server` publishen/subscriben jetzt über den `SimulationEventBus` statt direkt den Store. Public-API unverändert.
- `docker-compose.yml`: Agora-Container hängt an `redis: service_healthy`, `REDIS_URL=redis://redis:6379/0` in Service-Env fest verdrahtet.

### Notiz — offen / Follow-up

- **Issue #17** (neu): RPC/Interview-IPC komplett von File-Polling auf Redis Pub/Sub migrieren. Der `RedisEventBus` delegiert `CHANNEL_RPC_COMMAND` + `rpc.response.*` derzeit bewusst an den `FilePollingEventBus`, weil der OASIS-Subprozess (`run_reddit_simulation.py` / `run_twitter_simulation.py`) seinen eigenen File-IPC-Handler hat. Dessen Umbau ist eigenständig getrackt.
- **Issue #11 Phase 2**: NER→Mutation-Wiring. Der `OntologyMutationService` ist aufrufbar, aber noch nicht vom Ingest-Pfad getriggert.
- **Issue #10 Optional**: Frontend-Round-Slider in `GraphPanel`; und echter MERGE-basierter Reinforce-Pfad in `add_text` (heute nur `reinforce_relation` als separater Helper).
- `services/run_registry.py` bleibt bewusst beim direkten `json_io`-Zugriff — eigener Store-Adapter folgt in separater PR.

## [0.4.1] — 2026-04-23

### Hinzugefügt
- fail-fast Validierung für `EMBEDDING_MODEL` / `VECTOR_DIM` inklusive echter Embedding-Probe beim Backend-Start
- `frontend/src/composables/usePolling.js` als gemeinsamer Polling-Baustein für Langläufer
- `backend/app/utils/json_io.py` für atomische JSON-Schreibvorgänge und defensive Reads
- `docs/README.md` sowie `docs/README.md` als klarerer Einstieg in die neue Dokumentationsstruktur
- `GraphStorage.get_filtered_entities_with_edges` — Cypher-Pushdown für gefilterte Entitäten inkl. Adjazenz (ersetzt In-Memory-Filterung im `EntityReader`)
- Bounded Queue + Backpressure im `GraphMemoryUpdater` (`GRAPH_MEMORY_QUEUE_MAX`, `GRAPH_MEMORY_PUT_TIMEOUT`) — OOM-Schutz bei langsamer Neo4j-Ingestion

### Geändert
- Report-Status-Polling ist robuster gegen leere/trunkierte `progress.json` / `meta.json`
- Simulation-nahe JSON-Artefakte (`state.json`, `run_state.json`, `simulation_config.json`, `reddit_profiles.json`) werden defensiver gelesen und teils atomisch geschrieben
- Root von temporären Hilfsdateien entlastet; historische Notizen liegen jetzt unter `docs/archive/history/`, Log-Helfer unter `scripts/logs/`
- Dokumentationsbestand weiter nach `docs/` konsolidiert
- `EntityReader.filter_defined_entities` lädt nicht mehr alle Nodes/Edges in den RAM, sondern delegiert Filter + Adjazenz an die Storage-Schicht
- `GraphMemoryUpdater.get_stats()` meldet zusätzlich `dropped_count` und `queue_max`

### Test-Status
- 102/102 Backend-Tests grün (+14 für Cypher-Pushdown und Bounded Queue)
- Frontend-Lint: 0 Fehler
- Frontend-Build: erfolgreich

## [0.4.0] — 2026-04-22

Scope-Fokus: **Operability, Refactoring-Basis & Resilienz**. Details siehe `docs/archive/plans/plan_0.4.md` sowie die P0-Protokolle unter `docs/`.

### Hinzugefügt
- `GET /api/status` — konsolidierter Ops-Endpoint mit `backend`, `neo4j`, `ollama`, `disk`, `gpu`, `timestamp` (`backend/app/api/status.py`, 7 Tests)
- `backend/app/utils/gpu_probe.py` — `detect_gpu()` erkennt `nvidia-smi` und parst `ollama ps` (wirft nie, 8 Tests)
- `AGORA_LOG_FORMAT=text|json` Env-Toggle — Opt-in JSON-Logging via neuem `JSONFormatter` in `backend/app/utils/logger.py` (stdlib-only, 10 Tests)
- Request-ID-Middleware in `backend/app/__init__.py` (8-Zeichen-UUID, loggt bei `after_request`)
- `simulation_id`-Context in Simulation-Logs (`simulation_runner.py`, `api/simulation.py`)
- Kommentierte GPU-Reservation-Sektion in `docker-compose.yml` + README-Abschnitt „GPU/CPU Fallback"

### Geändert
- `Neo4jStorage` mit transientem Retry (`ServiceUnavailable`, `SessionExpired`, `TransientError`, exp. Backoff + Jitter, max 3 Retries) — via neuem `neo4j_call_with_retry` in `backend/app/utils/retry.py`
- Neue Read-only-Properties auf `Neo4jStorage`: `is_connected`, `last_error`, `last_success_ts` — vom `/api/status`-Endpoint konsumiert
- `get_ontology()` und `search()` durchlaufen jetzt das Retry-Wrapper
- Root-Quality-Gates vereinheitlicht (`npm run check`, Backend-Ruff scoped rollout, Frontend-ESLint, CI-Workflow)
- `backend/app/api/simulation.py` in fokussierte Module zerlegt (`simulation_lifecycle`, `simulation_prepare`, `simulation_profiles`, `simulation_run`, `simulation_interviews`, `simulation_history`)
- `frontend/src/components/GraphPanel.vue` in erste Teilmodule zerlegt (Detailpanel, Legende, Datenaufbereitung)

### Verschoben
- Python-3.12/CAMEL/OASIS-Kompatibilität → v0.4.1/v0.5 (Upstream-blockiert, Host-Python im Container irrelevant)

### Test-Status
- 63/63 Backend-Tests grün
- Frontend-Lint: 0 Fehler (verbleibende Warnungen dokumentiert und schrittweise abzubauen)
- Frontend-Build: erfolgreich

### Entwicklungs-Vorgehen
- Feature-Arbeit parallel über isolierte Git-Worktrees: Haiku 4.5 für GPU-Probe + `/api/status`, Sonnet 4.6 für Neo4j-Reconnect + JSON-Logging
- Merges als `--no-ff` in main, GPU-Detect in `/api/status` nachverdrahtet

## [0.3.1] — 2026-04-22

### Geändert
- **Logo & Favicon**: Agora-Branding auf neues Logo (`media/logo.png`, 1254×1254) umgestellt
  - `frontend/public/icon.png` (Favicon, 256×256)
  - `frontend/src/assets/logo/agora-logo.jpg` (Home-View, 1024×1024)
  - `static/image/agora-logo.jpg` + `agora-logo-source.jpg` (README/Banner-Assets)
  - Commits: `97aca71` → Rebase auf `2dd1e58`

## [0.3.0] — vorher

Siehe Git-Historie vor Einführung dieses Changelogs.
