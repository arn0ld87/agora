# Runbook: Upgrade zwischen Release-Linien

Zugehöriges Issue: [#1673](https://github.com/arn0ld87/agora/issues/1673) (Release-Gate vor `0.10.0-rc.1`, siehe [`../../ROADMAP.md`](../../ROADMAP.md)).
**Stand:** 30.09.2026, Produktversion `0.9.6` ([`VERSION`](../../VERSION)). `0.10.0-rc.1` ist noch nicht geschnitten.

## Warum dieses Runbook existiert

Ein Upgrade besteht in Agora aus mehr als einem neuen Image: Ab `0.10` gehören ein PostgreSQL-Schema, fünf Umschalter für die Metadaten-Ablage und ein Supabase-Stack dazu. Die Einzelheiten stehen in Runbooks pro Thema. Dieses Dokument ist der **Einstieg** je Versionssprung: Es nennt die Reihenfolge, den Kurzbefehl je Schritt, die Prüfung und den Rückweg, und verweist für alles Weitere auf das Detail-Runbook. Es dupliziert deren Inhalt nicht.

| Sprung | Stand | Abschnitt |
|---|---|---|
| `0.9.x` → `0.10` | beschrieben | [unten](#09x--010) |
| `0.10` → `1.0` | Platzhalter, wird im Freeze gefüllt | [unten](#010--10) |

## Was dieses Runbook nicht ist

- **Kein Betriebsnachweis.** Belegt sind der reale Cutover auf armserver am 25.09.2026 ([#1592](https://github.com/arn0ld87/agora/issues/1592), Protokoll im Issue) und das CI-Gate [#1589](https://github.com/arn0ld87/agora/issues/1589) (Migration und Rückweg gegen PostgreSQL). Ein Fresh-Host-Restore mit vollem Supabase-Stack ist es nicht: Der Drill [#766](https://github.com/arn0ld87/agora/issues/766) ist offen, und ein trockenes Runbook ersetzt ihn nicht ([`../agents/release-priority.md`](../agents/release-priority.md)).
- **Keine Pflege-Ausrede.** Ändert ein PR Persistenz, Migrationen, Env-Defaults oder den Compose-Stack, zieht er dieses Runbook im selben PR nach ([`../../AGENTS.md`](../../AGENTS.md), Abschnitt „Arbeitsweise“).

---

## Persistenz-Änderungen außerhalb des Versionssprungs

**Modellgeplante Berichts-Gliederung (#1832).** Neue Standardberichte erhalten eine freie, strukturell validierte Outline statt eines festen Titelpresets. Vorhandene valide Outlines bleiben beim Resume verwendbar; als `fallback_outline_used` markierte Ersatzgliederungen werden neu geplant. Historische Reports werden nicht migriert oder umgeschrieben. Scheitert die neue Planung, ist der Bericht `failed` mit der ursprünglichen Ursache statt eines leeren Ersatzschemas. Vor Wiederaufnahme muss deshalb die Stage-Route betriebsfähig sein. Inhalts-/Evidence-Gates bleiben unverändert; freie Titel garantieren keinen vollständigen Bericht.

**Codex-CLI-Mount prüfen (#1834).** Beim Hostwechsel den tatsächlichen Wert von `AGORA_CODEX_HOME` gegen das vorhandene Agora-eigene Verzeichnis prüfen, bevor Compose den Container erstellt. Das Verzeichnis muss für den Containerbenutzer les- und beschreibbar sein; ein von Docker angelegtes leeres root-Verzeichnis ist keine Anmeldung. Keine persönlichen Codex-Homes oder Credentials pauschal kopieren und keine Schreibrechte global freigeben. Anleitung und Override: [`../../deploy/compose/docker-compose.codex-cli.yml`](../../deploy/compose/docker-compose.codex-cli.yml). Nach einer Mountkorrektur ohne aktive Jobs neu erstellen, den wirksamen Mount und einen echten CLI-Call prüfen. Die globale Modellauswahl überschreibt einen gespeicherten `report_generation`-Stage-Override nicht.

Nicht jede neue persistierte Ablage gehört zu `0.9.x → 0.10` oder `0.10 → 1.0` — dieser Abschnitt sammelt Persistenz-Änderungen, die ein PR unabhängig vom Postgres-Umstieg eingeführt hat (AGENTS.md, Abschnitt „Arbeitsweise“, Punkt 6).

**JWT-Nutzerprofile und Avatare** (GNS3 account-profile API slice). Bei Requests mit einem verifizierten Supabase-Principal werden Profile und Avatare getrennt nach Principal.user_id unter AGORA_DATA_DIR/user_profiles/<user_id>/ gespeichert. user_profile.json und avatars/ liegen damit innerhalb desselben Nutzerverzeichnisses. Aufrufe mit Legacy-Authentifizierung behalten AGORA_DATA_DIR/user_profile.json und AGORA_DATA_DIR/avatars/; das gemeinsame Onboarding bleibt an diesen Legacy-Store gebunden und operator-only.

- **Upgrade:** Keine Migration und kein manueller Schritt. Bestehende Legacy-Dateien werden nicht automatisch einem Supabase-Nutzer zugeordnet, da kein sicherer Eigentümer ableitbar ist. JWT-Nutzer erhalten ein eigenes Profil beim ersten Speichern.
- **Rollback-Implikation:** Ein Rollback auf eine Version ohne nutzerspezifische Pfade lässt user_profiles/<user_id>/ liegen und liest weiter nur den Legacy-Store. Alte Versionen exponieren die neuen Dateien nicht über /api/profile; sie können nach erfolgreichem Backup manuell entfernt werden, wenn der Multi-User-Pfad endgültig verworfen wird.

**Neuer `jev`-Eintrag im Provider-Secret-Store** (f005, Slice `jev-key-cli`). `backend/data/llm_provider_secrets.json` (Fernet-verschlüsselt mit `AGORA_SECRET_KEY`) bekommt neben den bestehenden LLM-Chat-Provider-Keys (`openai`, …) eine weitere, eigene Ref `jev` (`app.services.decisions.jev_provider.JEV_SECRET_REF`) für den TypeSafe-API-Key des Jev-Decision-Piloten.

- **Provisionierung:** `backend/scripts/bind_decision_secret.py jev` (nie `llm-secrets-doctor.py`, das akzeptiert jede `provider_id` und könnte versehentlich einen LLM-Chat-Key überschreiben). Details, inklusive Container-Aufruf: [`decision-secrets.md`](decision-secrets.md).
- **Entfernen:** `bind_decision_secret.py jev --delete`, danach zwingend `docker compose restart agora` — der Backend-Prozess cacht den Jev-Client samt Key, das Löschen des Store-Eintrags allein widerruft ihn operativ nicht.
- **Rollback-Implikation:** Ein Rückweg auf eine Agora-Version ohne Jev-Pilot lässt den `jev`-Eintrag in derselben Store-Datei unberührt zurück (keine Schema-Migration nötig — zusätzliche Ref im selben JSON-Objekt). Ein Master-Key-Wechsel (`AGORA_SECRET_KEY` rotieren) re-encryptet über `llm-secrets-doctor.py rotate` wie jeden anderen Eintrag auch automatisch mit.
- **Master-Key-Prüfung vor dem Schreiben:** Seit dieser Slice verweigert `bind_decision_secret.py` das Binden/Überschreiben, wenn der aktuelle `AGORA_SECRET_KEY` einen bereits vorhandenen Store-Eintrag nicht entschlüsseln kann (Exit `2`) — ein syntaktisch gültiger, aber falscher Master-Key hätte sonst klaglos überschrieben und den vorherigen Ciphertext unwiederbringlich verloren.

**`schema_version` in Dokument-Manifest und Personasatz** ([#1663](https://github.com/arn0ld87/agora/issues/1663)). `uploads/projects/<id>/extracted_documents.json` bekommt ein Feld `schema_version: 1` auf oberster Ebene. Jeder Eintrag von `uploads/simulations/<id>/reddit_profiles.json` bekommt dasselbe Feld, `twitter_profiles.csv` eine zusätzliche Spalte `schema_version`.

- **Upgrade:** Es ist kein Schritt nötig. Altbestand ohne Feld liest die neue Version als Version 1 und schreibt ihn nicht um. Das Feld kommt erst dazu, wenn die Datei ohnehin neu geschrieben wird, etwa beim nächsten Graph-Build oder bei der nächsten Persona-Bearbeitung.
- **Rollback-Implikation:** Ältere Versionen lehnen ein Manifest **mit** `schema_version` ab, weil `DocumentManifest` dort `extra="forbid"` ist. Die Folgen nach einem Rückweg: Der Graph-Build eines solchen Projekts bricht ab, und Dokument-Rollen fallen mit Warnung weg. Abhilfe ist, `schema_version` aus `extracted_documents.json` zu entfernen. Der Personasatz ist nicht betroffen: Ältere Leser akzeptieren Zusatzfelder, und OASIS greift auf CSV-Spalten über den Namen zu.

**Prepare-Checkpoint, Ontologie-Typen und `state.json` während des Laufs** ([#1759](https://github.com/arn0ld87/agora/issues/1759)). Drei Ablagen bekommen zusätzliche Inhalte, keine braucht eine Migration:

- **`prepare_persona_checkpoint.json`** trägt neu `requirement_hash` (Hash der Simulationsfrage) und `selection_reasons` (Begründung je ausgewählter Entität). Ältere Checkpoints ohne die Felder bleiben lesbar und resumable. Ein Checkpoint, dessen Frage sich geändert hat, gilt nicht mehr als resumable; die Vorbereitung beginnt dann neu.
- **Persistierte Projekt-Ontologie:** Jeder Entitätstyp trägt neu `kind` (`entity` oder `contested_topic`) und `actor_capable`. Altbestand ohne die Felder liest sich als `entity` und akteursfähig; die Persona-Eignung fällt dann auf die bisherigen festen Typlisten zurück. Die neue, typgesteuerte Eignung und die Stance aus dem Graph greifen erst nach einer neu erzeugten Ontologie.
- **`uploads/simulations/<id>/state.json`** wird jetzt auch während eines laufenden Simulations-Jobs geschrieben (`current_round`, `twitter_status`, `reddit_status`), nicht erst am Ende. Gibt die Route keine Basis-URL vor, steht in der Simulations-Config `llm_base_url` als leerer Wert statt der `.env`-HTTP-URL. `run_state.json` bekommt die Zusatzfelder `twitter_logged_actions_count` und `reddit_logged_actions_count` (protokollierte Zähler); Dateien ohne diese Felder werden über die alten Feldnamen gelesen, ein älterer Stand ignoriert die neuen.
- **Personas und `twitter_profiles.csv`:** `voice_register` kennt drei zusätzliche Werte (`betroffen-de`, `emotional-de`, `umgangssprachlich-de`), die CSV führt neu die Spalte `voice_register`. Altbestand ohne die Spalte bleibt lesbar; das Register kommt dann aus der Rolle des Entitätstyps. Ältere Versionen kennen die drei Werte nicht: Nach einem Rollback sind Personasätze mit diesen Registern neu zu erzeugen.
- **Upgrade:** Es ist kein Schritt nötig.
- **Rollback-Implikation:** Ältere Versionen lehnen einen Checkpoint **mit** den neuen Feldern ab (`extra="forbid"`) und behandeln ihn als nicht vorhanden; die Vorbereitung startet neu, ohne Abbruch. Die Zusatzfelder der Ontologie ignorieren ältere Versionen.

**Gecachte Eingabe-Tokens in Call-Events und Usage-Summary** ([#1772](https://github.com/arn0ld87/agora/issues/1772)). `instance/runs/<run_id>/llm_call_events.jsonl` bekommt je Zeile das optionale Feld `cached_input_tokens` (`null`, wenn der Provider keine Angabe liefert), und `usage_summary.json` führt in `totals` und den Aufschlüsselungen das Feld `cached_input_tokens`. Die Run-API (`/api/runs/<id>`, Usage, Runs-Liste) liefert es mit; die Schemas unter `schemas/` und der Zod-Spiegel `frontend/src/contracts/runBudgetContract.ts` sind nachgezogen.

- **Upgrade:** Es ist kein Schritt nötig. Altbestand ohne das Feld bleibt lesbar und liefert `null`, nie 0; das Feld erscheint erst in neu geschriebenen Events und Summaries.
- **Rollback-Implikation:** Ältere Versionen lehnen ein `usage_summary.json` **mit** dem Feld ab (`UsageMetrics` ist dort `extra="forbid"`) und behandeln die Zusammenfassung als nicht vorhanden; Zeilen in `llm_call_events.jsonl` liest die Leseseite tolerant. Abhilfe ist, `cached_input_tokens` aus `usage_summary.json` zu entfernen oder die Datei neu aggregieren zu lassen. Das Frontend vor diesem Stand (strikter Zod-Spiegel) lehnt Run-Antworten mit dem Feld ab, solange Backend und Frontend nicht gemeinsam zurückgerollt werden.

**Neue Ablage für Personasätze: `AGORA_PERSONA_SET_BACKEND`, `uploads/persona_sets/<set_id>.json`, Tabelle `agora.persona_sets`** ([#1807](https://github.com/arn0ld87/agora/issues/1807), Etappe 7, Slices 7a und 7b). Ein Personasatz ist eine benannte Sammlung synthetischer Personas, die in mehreren Läufen verwendet werden kann; ein Lauf bekommt eine Kopie. Der Stand umfasst Vertrag, Repository-Port mit beiden Adaptern, den Dienst `persona_set_service` und die API `/api/persona-sets` (Sätze und Einträge anlegen, ändern, löschen, duplizieren, Qualität). Ein Lauf aus einem Satz entsteht über `POST /api/simulation/create-from-personas` mit `persona_set_id`; der erste Lauf sperrt den Satz (`locked_at`), danach sind nur noch Name und Beschreibung änderbar, Duplizieren bleibt möglich. Der Altbestand der Persona-Bibliothek (`uploads/simulations/_persona_library/`) wird beim ersten `GET /api/persona-sets` einmalig in den Sammelsatz „Importiert“ (`pset_importiert`) übernommen; die alten Vorlagen bleiben unverändert liegen, ein Marker in `_persona_library/` verhindert, dass ein gelöschter Sammelsatz wiederkehrt. Ohne Vorlagen entsteht kein Satz. Schlägt der Import an der Ablage fehl, antwortet die Liste mit `500` statt still ohne den Altbestand; die Ursache (Rechte, Datenträger) ist dann vor dem nächsten Aufruf zu beheben. Die Oberfläche bietet die Personasatz-Bibliothek, den Editor und die Auswahl vorhandener Sätze im Startdialog.

- **Neuer Schalter `AGORA_PERSONA_SET_BACKEND`** (Default `file`, gültig `file` | `postgres`; ein anderer Wert lässt den Start abbrechen). `file` legt jeden Satz als `backend/uploads/persona_sets/<set_id>.json` ab (atomar mit `fsync`); das Verzeichnis entsteht erst beim ersten Satz und gehört damit zu jeder Sicherung von `backend/uploads`. `postgres` verlangt nur `DATABASE_URL`, keinen anderen Schalter: `agora.persona_sets` hat keinen Fremdschlüssel auf Projekte oder Simulationen, `graph_id`, `project_id` und die Simulationskennungen sind reine Verweise. Der Schalter zählt wie die anderen `*_BACKEND`-Schalter für Readiness, Schema-Gate und Backup, und er gehört zu den Schaltern, die mit Supabase-JWT alle auf `postgres` stehen müssen (`WORKSPACE_SCOPED_BACKENDS`); ohne JWT-Betrieb (Multi-User bleibt aus, ADR-0019) ändert das nichts.
- **Kennungsvalidierung:** Der Dateiadapter akzeptiert nur vollständig passende Kennungen (`A-Z`, `a-z`, Ziffern, `_`, `-`, 1–64 Zeichen); nachgestellte Zeilenumbrüche sind ungültig. Normal erzeugte Kennungen und das Dateiformat bleiben unverändert, eine Migration ist nicht erforderlich.
- **Neue Tabelle `agora.persona_sets`** (Alembic `3b7f9d21a8c4`, Vorgänger `dc4e84e7c000`; neuer Alembic-Head). Kernspalten `id`, `workspace_id` (`NOT NULL`, Fremdschlüssel auf `agora.workspaces`, `UNIQUE (id, workspace_id)`), `name`, `graph_id`, `project_id`, `locked_at`, `created_at`, `updated_at`, dazu `payload` (JSONB). Die Tabelle trägt Row Level Security wie die übrigen Tabellen (`ENABLE` und `FORCE`, Policy `agora_workspace_isolation`); die Lese-Policy für `authenticated` und die Publication `supabase_realtime` gibt es für sie nicht. Die Migration ist reiner `CREATE TABLE`, sie berührt keine bestehende Tabelle und braucht keine Datenübertragung.
- **Upgrade:** Steht irgendein Schalter auf `postgres`, ist vor dem Start `alembic upgrade head` zu fahren (das Start-Gate bricht sonst mit „Datenbankschema liegt hinter dem Code zurück“ ab, siehe Abschnitt „2. Ziel-Stand einspielen“). Die Laufzeitrolle bekommt die Rechte auf die neue Tabelle über `ALTER DEFAULT PRIVILEGES` aus [`rls-rollen.md`](rls-rollen.md); fehlt diese Zeile, wird einmalig `GRANT SELECT, INSERT, UPDATE, DELETE ON agora.persona_sets TO agora_app;` nötig. Auf reinem Dateibetrieb ist kein Schritt nötig.
- **Rollback-Implikation:** Ältere Versionen kennen weder Schalter noch Datei und ignorieren beides; `uploads/persona_sets/` kann liegen bleiben. Bei PostgreSQL gilt: `alembic downgrade dc4e84e7c000` entfernt `agora.persona_sets` samt Policy und **löscht alle dort gespeicherten Personasätze**; vorher mit `pg_dump -t agora.persona_sets` sichern, wenn Sätze bestehen. Läufe sind nicht betroffen, sie tragen eine Kopie der Personas. Bleibt die Datenbank auf dem neuen Head und läuft ein älterer Code-Stand, meldet das Start-Gate „Datenbankschema ist neuer als der Code“; dann entweder zuerst downgraden oder den neueren Code-Stand beibehalten. Ein Wechsel des Schalters zwischen `file` und `postgres` überträgt keine Sätze (es gibt noch kein Migrationsskript); Sätze bleiben in der Ablage, in der sie angelegt wurden.

**Rückverweis `persona_set_id` am Simulationszustand und `persona_set_origin` im Laufprofil** ([#1807](https://github.com/arn0ld87/agora/issues/1807), Etappe 7, E7-B1). Ein Lauf aus einem Personasatz vermerkt die Satz-Kennung jetzt in `state.json` (bei `AGORA_SIMULATION_BACKEND=postgres` im `payload` von `agora.simulations`) und führt in jedem Laufprofil (`reddit_profiles.json`, Spalte in `twitter_profiles.csv`) die Herkunft `persona_set_origin`. Ohne Satz bleiben beide Dateien byte-identisch: der Schlüssel fehlt.

- **Upgrade:** Es ist kein Schritt nötig, keine Migration, keine neue Tabelle oder Spalte (das Feld liegt im bestehenden `payload`). Läufe aus einem Satz, die vor diesem Stand angelegt wurden, tragen den Rückverweis nicht (`persona_set_id` fehlt); die Zuordnung steht weiter in `used_by_simulation_ids` des Satzes und in den Metadaten des Prepare-Runs. Es gibt keine Rückfüllung.
- **Rollback-Implikation:** Ältere Versionen lesen `state.json` mit `extra="ignore"` und verwerfen `persona_set_id` beim nächsten Schreiben still; der Rückverweis geht dann verloren, die Läufe laufen unverändert. Die zusätzliche CSV-Spalte und das JSON-Feld im Laufprofil stören OASIS nicht (es greift über Spaltennamen zu). Das Frontend vor diesem Stand (strikter Zod-Spiegel für `SimulationStatusResponse`) lehnt die Antwort eines Laufs aus einem Satz ab, solange Backend und Frontend nicht gemeinsam zurückgerollt werden; Läufe ohne Satz sind nicht betroffen.

**Herkunftsmerkmal an Knoten und Kanten im Graphen** ([#1808](https://github.com/arn0ld87/agora/issues/1808), [ADR-0022](../decisions/0022-manuelle-herkunft-im-graphen.md)). Neo4j-Knoten (`Entity`) und -Kanten (`RELATION`) bekommen die optionalen Eigenschaften `origin` (`manual` oder `edited`) und `origin_changed_at` (ISO-8601). Sie entstehen nur, wenn ein Graph von Hand bearbeitet wird; es gibt keine neuen Constraints oder Indizes.

- **Upgrade:** Es ist kein Schritt nötig und keine Migration des Bestands. Ein Element ohne `origin` gilt als extrahiert; Altgraphen werden nicht nachgerüstet. Evidence-Items und -Records tragen das optionale Feld `graph_origin` (`manual` | `edited`); Bestand ohne Feld bleibt lesbar. Backend und Zod-Spiegel behalten für Handarbeit `source_kind=graph_relation`, verbieten `seed_doc:`-Anker und lassen sie für keine Confidence-Stufe zählen. Ein erneuter Berichtslauf kann damit weniger belastbare Belege als ein alter Bericht ausweisen; bestehende Berichte werden nicht automatisch neu bewertet.
- **Verhaltenswechsel ohne Zutun:** `DELETE /api/graph/delete/<graph_id>`, `DELETE /api/graph/project/<project_id>` und `POST /api/graph/project/<project_id>/reset` antworten für einen Graphen, den eine Simulation verwendet (Projekt oder `graph_id`), mit `409 graph_locked` statt zu löschen bzw. zurückzusetzen. Wer einen benutzten Graphen bewusst entfernen will, löscht zuerst die Simulationen. Die Sperre ist kein gespeichertes Feld, sondern wird aus den Simulationsdatensätzen abgeleitet; es gibt nichts zu entsperren.
- **Rollback-Implikation:** Ältere Versionen ignorieren die Eigenschaften `origin` und `origin_changed_at` (Neo4j-Eigenschaften ohne Schema). Von Hand angelegte Elemente erscheinen dort als gewöhnliche Graph-Elemente, ohne Herkunftsmerkmal; manuelle Beziehungen haben leere `episode_ids`. Die Sperre entfällt, die alten Lösch- und Reset-Endpunkte arbeiten wieder ohne Prüfung.

**Graph duplizieren** ([#1808](https://github.com/arn0ld87/agora/issues/1808)). `POST /api/graph/<graph_id>/duplicate` legt je Aufruf ein neues Projekt unter `uploads/projects/<project_id>/` an (Metadaten, `files/`, `extracted_text.txt`, `extracted_documents.json`, kopiert vom Quellprojekt) und einen neuen Graphen in Neo4j (neue `graph_id`, `Entity`, `RELATION`, `Episode` mit neuen UUIDs). Die Kopie belegt Plattenplatz und Neo4j-Speicher in der Größe der Quelle, einschließlich der Embedding-Vektoren. Der Job steht in `uploads/run_registry/` (`run_type=graph_duplicate`).

- **Upgrade:** Es ist kein Schritt nötig, keine Migration, keine neuen Constraints, Indizes oder Umgebungsvariablen.
- **Aufräumen:** Bei einem Fehler entfernt der Job Zielgraph und Zielprojekt selbst. Ein Prozess-Neustart während des Jobs lässt die Teilkopie stehen (der Job steht danach auf `failed/process_restart`); sie lässt sich über `DELETE /api/graph/delete/<graph_id>` (Graph) und `DELETE /api/graph/project/<project_id>` (Projekt) entfernen, die Kennungen stehen im Job (`GET /api/runs/<run_id>`, `linked_ids`).
- **Rollback-Implikation:** Ältere Versionen kennen den Run-Typ `graph_duplicate` nicht und zeigen ihn als unbekannten Job; die kopierten Projekte und Graphen sind gewöhnliche Projekte und Graphen und bleiben benutzbar.

**HuggingFace-Cache-Verzeichnis im Repository** (TwhinCacheError auf gns3, 2026-10-10). `backend/.cache/huggingface/` ist Bind-Mount-Quelle für `/home/agora/.cache/huggingface` (`docker-compose.yml`) und liegt jetzt mit einem `.gitkeep` getrackt im Repo — die `.gitignore`-Regel `backend/.cache/` wurde dafür auf `backend/.cache/*` plus zwei Ausnahmen umgestellt. Der Cache-Inhalt selbst bleibt ignoriert.

- **Upgrade:** Auf einem frischen Klon kein Schritt nötig. Bestehende Deployments, in denen der Docker-Daemon das Verzeichnis bereits als `root:root` angelegt hat, scheitern beim nächsten `git pull` einmalig an der neuen Platzhalterdatei (`EACCES`); vorher räumen oder umschreiben:
  ```bash
  sudo rm -rf backend/.cache/huggingface    # regenerierbarer Cache, ~1,1 GB Nachladen
  sudo chown -R 1000:1000 backend/.cache/huggingface   # Alternative ohne Cache-Verlust
  ```
  Ohne den Schritt bleibt der Simulationsstart auf einem Linux-Host mit `TwhinCacheError` stehen, weil der Container-User (uid 1000) im Verzeichnis nicht schreiben kann. Im Container hilft kein `chown` — der Stack läuft mit `cap_drop: ALL`.
- **Rollback-Implikation:** Ältere Stände kennen die Platzhalterdatei nicht und ignorieren sie; sie mounten weiter dasselbe Verzeichnis. Ein Revert der `.gitignore`-Regel lässt den Cache-Inhalt erneut ignoriert, verliert aber das Verzeichnis aus dem Klon — der ursprüngliche Fehler kommt dann zurück.

**Profile für synthetische Skeptiker, `reddit_profiles.json` und `twitter_profiles.csv`** ([#1779](https://github.com/arn0ld87/agora/issues/1779)). Ergänzt die Skeptiker-Quote die Konfiguration um Agenten (`entity_uuid` beginnt mit `synthetic-skeptic-`), schreibt `prepare` nach der Konfigurationsphase beide Profildateien neu und hängt für jeden dieser Agenten einen Eintrag an (`user_id` bzw. `source_user_id` = `agent_id` der Konfiguration, `persona_kind="collective"`, `generation_source="rule_based"`, `voice_register="skeptisch-de"`, keine erfundene Demografie). Die Zahl der Profile kann damit größer sein als die Zahl der Entitäten (`profiles_count` zählt sie mit). Der Befund steht als Degradation `persona_rule_based_fallback` (Schweregrad `warning`) im Ergebnis des Prepare-Jobs. **Verhaltenswechsel ohne Zutun, nur für neu vorbereitete Simulationen:** Die Skeptiker existieren dann in OASIS und können schreiben; bisher hatten sie kein Profil und blieben stumm. Bereits vorbereitete Simulationen behalten ihre Dateien und werden nicht nachträglich ergänzt. **Kein Upgrade-Schritt, keine Migration, keine Env-Variable.** **Rollback:** Ältere Versionen lesen die zusätzlichen Einträge wie jedes andere Profil; wer sie entfernen will, bereitet die Simulation neu vor.

**Feld `config_source` je Agent in `simulation_config.json`** ([#1779](https://github.com/arn0ld87/agora/issues/1779)). Neu vorbereitete Simulationen schreiben je Eintrag in `agent_configs` das Feld `config_source` (`llm` | `rule_fallback` | `synthetic_skeptic`); bei einem Rückfall auf die Regel-Defaults meldet der Prepare-Lauf zusätzlich die Degradation `agent_config_rule_fallback` (`warning`). **Kein Upgrade-Schritt, keine Migration, keine Env-Variable.** Ältere Konfigurationen haben das Feld nicht und lesen sich als `llm`; kein Leser setzt es voraus. **Rollback:** Eine ältere Version ignoriert das zusätzliche Feld; die neue Degradationsart `agent_config_rule_fallback` kennt ein älteres Frontend nicht (der Zod-Spiegel ist ein geschlossenes Enum). Frontend und Backend deshalb gemeinsam zurückrollen.

## Env-Default-Änderungen außerhalb des Versionssprungs

Nicht jede neue Umgebungsvariable gehört zu `0.9.x → 0.10` oder `0.10 → 1.0` — dieser Abschnitt sammelt Env-Defaults, die ein PR unabhängig vom Postgres-Umstieg eingeführt hat (AGENTS.md, Abschnitt „Arbeitsweise“, Punkt 6).

**`AGORA_DECISION_LAYER_MODE`** (f005/ADR-0016, Jev-Decision-Pilot). Default `disabled` — kein Verhaltenswechsel. `shadow` lässt zusätzlich einen `RuleProvider` parallel mitlaufen (nur Telemetrie). `authoritative` schaltet für den Use Case `local-search-relevance` echten Jev-Betrieb scharf: Jev entscheidet, `RuleProvider` ist Rückfall bei jedem Jev-Fehler/fehlendem Key. Ein Upgrade ändert diesen Wert nie automatisch — ein Betreiber, der `authoritative` setzt, sendet damit Suchanfrage und bestbewerteten Fakt im Klartext an TypeSafe (Maintainer-Datenschutzfreigabe 30.09.2026, Alexander Schneider, beschränkt auf genau diesen Modus mit Rule-Rückfall). Siehe [`../STATUS.md`](../STATUS.md), Abschnitt „Decision Layer (Jev-Pilot)“.

**`AGORA_JEV_TIMEOUT_S`** (float, Default `2.0`, gültiger Bereich `0 < Wert <= 30`, von `Config.validate()` erzwungen). Timeout-Budget für genau einen Jev-Aufruf im `authoritative`-Pfad. Wirkt nur, wenn `AGORA_DECISION_LAYER_MODE=authoritative` gesetzt ist; da `local-search-relevance` ein heißer Retrieval-Pfad ist, blockiert ein hängender Jev-Aufruf lokale Suchen höchstens um dieses Budget (plus ein interner Retry mit demselben Timeout), bevor der Rule-Rückfall greift. Kein Upgrade-Schritt nötig — reiner Opt-in über `AGORA_DECISION_LAYER_MODE`.

**`AGORA_SIM_MAX_CONCURRENCY`** ([#1772](https://github.com/arn0ld87/agora/issues/1772)). Gleichzeitige Modellaufrufe je Simulationsplattform. Der Wert war bis dahin fest `30`; der neue Default ist `8` (gültig 1 bis 256). Twitter und Reddit laufen parallel, die Gesamtlast ist daher bis zu doppelt so hoch wie der Wert. **Verhaltenswechsel ohne Zutun:** Simulationsrunden laufen mit dem neuen Default langsamer, dafür gehen weniger Agentenschritte an `RateLimitError` verloren (Messung `sim_cc6067a70603`: bei 30 + 30 scheiterten 68 % der Aufrufe). Wer einen Anbieter ohne enges Minutenlimit nutzt, setzt den Wert in `.env` zurück auf `30`. Ungültige Werte fallen mit Warnung im `simulation.log` auf `8`.

**`AGORA_SIM_INPUT_TOKENS_PER_MINUTE`** ([#1772](https://github.com/arn0ld87/agora/issues/1772)). Der Default wechselt von `0` (aus) auf `1500000` (75 % des Kontolimits von 2 Mio. TPM für `gpt-6-luna`). **Verhaltenswechsel ohne Zutun:** Simulationsläufe werden gedrosselt und dadurch langsamer, verlieren aber weniger Agentenschritte (Messung `sim_c8c6b30aa652` ohne Limiter: 872 von 2.091 Aufrufen `RateLimitError`, 209 verlorene Schritte). Der erste Aufruf eines Laufs läuft als Sonde allein, danach reserviert jeder laufende Aufruf das gemessene Mittel. Wer ein höheres Kontolimit hat, setzt den Wert entsprechend; wer die alte Ungedrosseltheit braucht (Rückweg), setzt `AGORA_SIM_INPUT_TOKENS_PER_MINUTE=0`. Der Wert gilt je Simulationsprozess; im Standard-Parallelrunner teilen sich Twitter und Reddit ihn. Zusammen mit `AGORA_SIM_MAX_CONCURRENCY` stand der Wert bisher nicht in der Env-Whitelist des Simulations-Subprozesses (`SAFE_ENV_KEYS`): ein in `.env` oder Compose gesetzter Wert erreichte den Subprozess nie, beide Variablen wirken erst seit diesem Stand.

**`AGORA_SIM_AGENTS_PER_HOUR_MIN_RATIO` / `AGORA_SIM_AGENTS_PER_HOUR_MAX_RATIO`** ([#1772](https://github.com/arn0ld87/agora/issues/1772)). Die Aktivitäts-Untergrenze aus [#1713](https://github.com/arn0ld87/agora/issues/1713) S4 war fest `0,4`/`0,7` und ist jetzt einstellbar; der neue Default ist `0,25`/`0,5` (gültig `0 < min ≤ max ≤ 1`, sonst Warnung und Rückfall auf den Default). **Verhaltenswechsel ohne Zutun:** Neu erzeugte Simulationskonfigurationen aktivieren je Runde weniger Agenten, also weniger Beiträge und weniger Modellaufrufe; das Liveness-Ziel L2 (≥ 40 % aktive Agenten je Runde) liegt im Mittel bei rund 37 %. Wer das alte Verhalten braucht, setzt `0.4`/`0.7`. Bereits gespeicherte `simulation_config.json` bleiben unverändert; die Quoten wirken erst beim Erzeugen einer neuen Konfiguration.

**`AGORA_SIM_MAX_HOURS`** ([#1772](https://github.com/arn0ld87/agora/issues/1772)). Obergrenze für `time_config.total_simulation_hours` beim Erzeugen der Simulationskonfiguration, Default `24` (gültig ganze Zahl 1 bis 168, sonst Warnung und Rückfall auf `24`). **Verhaltenswechsel ohne Zutun, nur für neu erzeugte Konfigurationen:** Der Konfigurations-Assistent schlug zuvor bis zu 168 Stunden vor (Modell-Default 72 Stunden, teils 4 Tage und 90 Runden); jetzt ist der Standard 1 Tag bei 60 Minuten je Runde, also 24 Runden, und jede längere LLM-Antwort wird auf den Wert geklemmt (Log-Warnung, Hinweis im `generation_reasoning`). Kürzere Runden (`minutes_per_round` unter 60) werden auf 60 Minuten angehoben, wenn sie mehr Runden als die Obergrenze ergäben. Bereits gespeicherte `simulation_config.json` bleiben unverändert; wer längere Läufe will, gibt beim Start `simulation_days`/`max_rounds` an (wirkt nach der Erzeugung und wird nicht geklemmt) oder setzt `AGORA_SIM_MAX_HOURS` höher und bereitet neu vor. Kein Migrationsschritt, Rollback = Variable auf `168` setzen (Prompt-Standard bleibt 24) oder den Stand vor diesem Commit deployen.

**`AGORA_SIM_DEFAULT_MAX_TOKENS`** ([#1772](https://github.com/arn0ld87/agora/issues/1772)). Harter Standard-Tokendeckel für Simulationen ohne Nutzerbudget, Default `20000000` (20 Mio.), `0` schaltet ihn ab. **Verhaltenswechsel ohne Zutun:** Jeder Simulationsstart ohne `budget` im Aufruf bekommt `budget={max_tokens: 20000000, enforcement: "hard"}` (sichtbar in `metadata.budget` des Runs und in `budget_config.json`). Große Läufe ohne begrenztes Agenten-Gedächtnis überschreiten das: Der Referenzlauf `sim_cc6067a70603` (52 Agenten, 24 Runden, zwei Plattformen) verbrauchte rund 36 Mio. Tokens und würde mit `termination_reason=budget_tokens` enden. Wer solche Läufe braucht, setzt den Wert höher oder auf `0`, oder übergibt im Startaufruf ein eigenes `budget`. Der Wächter prüft nur an Rundengrenzen und zählt nur erfolgreiche Aufrufe, eine einzelne Runde kann den Deckel also überschreiten. Replay, Neustart und Branch erben das Budget des Ursprungslaufs und erhalten keinen nachträglichen Deckel.

**Standardgrenzen für Kosten, Zeit und Aufrufe: `AGORA_SIM_DEFAULT_MAX_COST_MICROS`, `AGORA_SIM_DEFAULT_MAX_DURATION_SECONDS`, `AGORA_SIM_DEFAULT_MAX_LLM_CALLS`, `AGORA_SIM_DEFAULT_BUDGET_ENFORCEMENT`** ([#1799](https://github.com/arn0ld87/agora/issues/1799)). Neben dem Standard-Tokendeckel gibt es jetzt Standardgrenzen für Kosten (Mikro-USD, `1000000` = 1 USD), Laufzeit (Sekunden) und Modellaufrufe sowie die Durchsetzung `soft`/`hard` (Default `hard`). Die drei neuen Grenzen haben den Default `0` (= kein Limit); `0` schaltet auch den Tokendeckel ab, sind alle vier auf `0`, bekommt ein Start ohne Nutzerbudget gar kein Budget. **Kein Verhaltenswechsel ohne Zutun:** Mit den Defaults entsteht exakt das bisherige Standardbudget `{max_tokens: 20000000, enforcement: "hard"}`. Gesetzte Werte wirken auf jeden Simulationsstart ohne eigenes `budget`, auch auf Starts über die API; ein im Startaufruf übergebenes `budget` gewinnt komplett und wird nicht ergänzt. Replay, Neustart und Branch erben weiter das Budget des Ursprungslaufs. Die Durchsetzung gilt für alle Standardgrenzen gemeinsam, auch für den Tokendeckel: bei `soft` warnt der Lauf nur, statt zu enden (die Preflight-Schätzung nennt dann keinen Abbruch durch den Standarddeckel). Die Einstellungen stehen in der Oberfläche im Abschnitt „Budgets“; der Tokendeckel `AGORA_SIM_DEFAULT_MAX_TOKENS` ist dorthin vom Abschnitt „OASIS“ umgezogen (Schlüssel, Default und Eintrag in `instance/settings.json` bleiben gleich). Kein Migrationsschritt. Rollback: Werte auf `0` setzen bzw. den Eintrag aus `instance/settings.json` entfernen (dann gilt wieder der Default).

**Agenten-Zuordnung der Simulation, Spalte `source_user_id` in `twitter_profiles.csv`** ([#1778](https://github.com/arn0ld87/agora/issues/1778)). Neu vorbereitete Simulationen schreiben in `twitter_profiles.csv` die zusätzliche Spalte `source_user_id` (Nummer des Agenten in `simulation_config.json`); `user_id` bleibt die fortlaufende Zeilenposition, die OASIS liest. **Verhaltenswechsel ohne Zutun:** Runner und Bericht ordnen Name, Aktivität, Haltung und Startbeiträge über `user_id` (`reddit_profiles.json`) bzw. `source_user_id` (`twitter_profiles.csv`) dem OASIS-Agenten zu. Das wirkt nur, wenn einzelne Profile fehlen; bei vollständigen Profilen ändert sich nichts. Keine Migration: Simulationen mit `reddit_profiles.json` werden auch im Bestand richtig zugeordnet. Eine bestehende Simulation nur mit Twitter hat die Spalte nicht; dort bleibt die Zuordnung wie bisher (keine Angleichung), bis die Simulation neu vorbereitet wird. Aktionsprotokolle bereits gelaufener Simulationen behalten ihre Namen. Rollback: Die zusätzliche Spalte stört ältere Versionen nicht.

**Aktivitätsmodell der Simulation, `AGORA_SIM_ACTIVITY_MODE`** ([#1779](https://github.com/arn0ld87/agora/issues/1779)). Neue Env-Variable, Default `realistic` (gültig `realistic` | `active`; ein ungültiger Wert fällt mit Warnung auf den Default zurück). **Verhaltenswechsel ohne Zutun, nur für neu vorbereitete Simulationen:** Die Konfiguration bekommt `time_config.activity_model` und je Agent `actor_class`. Der Runner wählt die aktiven Agenten dann nach Tagesraten je Akteursklasse statt nach `agents_per_hour_min/max` und `activity_level`, zieht einmal je Runde für alle Plattformen und führt je Aktivierung höchstens einen Textbeitrag und zwei Reaktionen aus. Folge: deutlich weniger Aktionen je Runde als bisher (Größenordnung bei 30 Agenten und 24 Runden: rund 25 Textbeiträge im Modus `realistic`, 60 bis 120 im Modus `active`, statt mehrerer hundert). Wer mehr Material braucht, wählt mehr Agenten, mehr simulierte Tage oder den Modus `active`. `AGORA_SIM_AGENTS_PER_HOUR_MIN_RATIO`/`..._MAX_RATIO` und die Aktivitäts-Untergrenzen aus #1713 wirken für solche Simulationen nicht mehr auf die Auswahl; die Felder bleiben im Artefakt. **Kein Upgrade-Schritt, keine Migration.** Bereits vorbereitete Simulationen (`simulation_config.json` ohne `activity_model`) laufen unverändert nach dem bisherigen Muster; wer das neue Modell will, bereitet die Simulation neu vor (ein ausdrücklich übergebenes `activity_mode` löst das aus). **Rollback:** Eine ältere Version ignoriert `activity_model` und `actor_class` und nutzt wieder die bisherige Auswahl.

**Neues Berichtsartefakt `evidence_density.json`** ([#1779](https://github.com/arn0ld87/agora/issues/1779)). Neu erzeugte Berichte schreiben beim Abschluss (auch bei `INCOMPLETE` und beim Teilbericht nach Abbruch) die Datei `evidence_density.json` in `backend/uploads/reports/<report_id>/`. **Kein Upgrade-Schritt, keine Migration, keine Env-Variable.** Ältere Berichte haben die Datei nicht und bekommen sie nicht nachträglich; nichts im Produkt setzt sie voraus, kein API-Endpunkt liefert sie aus. **Rollback:** Eine ältere Version ignoriert die Datei; sie kann liegen bleiben oder gelöscht werden. Sie liegt im Berichtsverzeichnis und ist damit Teil jeder Sicherung von `backend/uploads`.

**`AGORA_REPORT_POSITIONING_RATIO_MIN`** ([#1778](https://github.com/arn0ld87/agora/issues/1778)). Mindestanteil der Stimmen, die in der Simulation Stellung zur Streitfrage beziehen, Default `0.5` (gültig `0` bis `1`). **Verhaltenswechsel ohne Zutun, nur für neu erzeugte Berichte:** Vor dem ersten Abschnitt klassifiziert der Bericht jeden Simulationsbeitrag einmal nach seiner Haltung zur Streitfrage (ein Modellaufruf je 25 Beiträge, über den LLM-Client des Berichts und damit im Budget-Ledger des Berichts) und schreibt das Ergebnis als `stance_analysis.json` ins Berichtsverzeichnis. Liegt die Positionierungsquote unter dem Wert, trägt der Bericht in `run_degradations` einen Eintrag `simulation_positioning` mit `severity="warning"`; der Berichtsstatus ändert sich dadurch nicht. Läufe ohne Streitfrage (Altbestand, `origin="none"`) lösen weder Modellaufrufe noch einen Eintrag aus. `0` schaltet die Warnung ab, die Klassifikation läuft weiter. Kein Datenbestand betroffen, kein Migrationsschritt; bestehende Berichte bleiben unverändert.

**Agentengedächtnis der Simulation ([#1772](https://github.com/arn0ld87/agora/issues/1772)): `AGORA_SIM_MEMORY_PRUNE_FEEDS`, `AGORA_SIM_MEMORY_KEEP_FEEDS`, `AGORA_SIM_MEMORY_TOKEN_CAP`.** Defaults `true`, `4`, `32000`; **das ändert das Verhalten neuer Läufe ohne jede Einstellung.** Bisher wuchs das CAMEL-Gedächtnis jedes Agenten über den Lauf bis zum Modell-Kontextlimit (`LLM_CONTEXT_LIMIT`, Default 262.144), weil jeder Feed für immer im Verlauf blieb. Jetzt ersetzt Agora nach jeder Runde die Feeds älterer Aktivierungen durch einen Platzhalter (behalten werden die letzten `AGORA_SIM_MEMORY_KEEP_FEEDS`, Minimum 1) und begrenzt das Gedächtnis-Token-Limit auf `AGORA_SIM_MEMORY_TOKEN_CAP` (`0` = keine Obergrenze, Werte unter 8.192 werden auf 8.192 angehoben). Der Schalter `AGORA_SIM_MEMORY_PRUNE_FEEDS=false` plus `AGORA_SIM_MEMORY_TOKEN_CAP=0` stellt den alten Zustand her. Folgen: weniger Eingabe-Tokens und Kosten je Lauf; Agenten kennen ältere Feeds nicht mehr, nur ihre eigenen früheren Aktionen. Läufe mit unterschiedlicher Einstellung sind nicht vergleichbar. Die Variablen stehen in `SAFE_ENV_KEYS` und erreichen den Simulations-Subprozess über die Umgebung des Backends (Compose-`environment:` oder `.env`). Kein Datenbestand betroffen, kein Migrationsschritt; ein Rollback auf eine ältere Version ignoriert die Variablen.

**`AGORA_SIM_FEED_MAX_COMMENTS`** (ebenfalls [#1772](https://github.com/arn0ld87/agora/issues/1772)). Default `5`, `0` = aus; **ändert das Verhalten neuer Läufe ohne Einstellung:** Im Feed jedes Agenten stehen je Post höchstens die neuesten fünf Kommentare, die Zahl der weggelassenen steht als `omitted_comments` am Post, und das Feed-JSON ist kompakt statt eingerückt. Mit `0` bleibt der Feed byte-identisch zu OASIS. Die Variable steht in `SAFE_ENV_KEYS`; kein Datenbestand betroffen, kein Migrationsschritt. Läufe mit unterschiedlichem Wert sind nicht vergleichbar (der Agent sieht andere Diskussionsstände).

---

## 0.9.x → 0.10

### Was sich ändert

| Bereich | Änderung | Aktion |
|---|---|---|
| Metadaten-Ablage | fünf Domänen (LLM-Profile, Projekte, Simulationen, Runs, Reports) können in PostgreSQL liegen, Schema `agora`, per Alembic | Schritte 3 bis 9 |
| Supabase-Stack | eigenes Compose-Projekt unter [`supabase/`](../../supabase/README.md), PostgreSQL 17 hinter Supavisor | Schritt 3 |
| Neo4j, Redis, Artefakte unter `uploads/` | unverändert. Blob-Ablage hat keinen Adapter ([#1584](https://github.com/arn0ld87/agora/issues/1584), [#1586](https://github.com/arn0ld87/agora/issues/1586)) | keine |
| Supabase-Auth, JWT, Realtime, Workspaces | im Code inaktiv. `AGORA_AUTH_BACKEND=hybrid` verhält sich ohne `AGORA_SUPABASE_JWT_ISSUER` wie `legacy`, `AGORA_SUPABASE_REALTIME` ist aus. Multi-User folgt erst nach 1.0 (ADR-0019) | keine, nicht setzen |

**Die Umschalter stehen im Code auf Legacy und müssen explizit gesetzt werden.** Das sind die Werte aus `backend/app/config.py` und [`.env.example`](../../.env.example):

| Schalter | Code-Default (Legacy) | Ziel nach dem Upgrade | Rückweg-Wert |
|---|---|---|---|
| `AGORA_LLM_PROFILE_BACKEND` | `sqlite` | `postgres` | `sqlite` |
| `AGORA_PROJECT_BACKEND` | `file` | `postgres` | `file` |
| `AGORA_SIMULATION_BACKEND` | `file` | `postgres` | `file` |
| `AGORA_RUN_BACKEND` | `file` | `postgres` | `file` |
| `AGORA_REPORT_BACKEND` | `file` | `postgres` | `file` |

`AGORA_METADATA_BACKEND` bleibt `legacy`; maßgeblich sind die fünf Einzel-Schalter. Ob `0.10.0` die Defaults auf `postgres` dreht, ist **noch nicht festgelegt** (siehe [Offene Lücken](#offene-lücken), [#1654](https://github.com/arn0ld87/agora/issues/1654)). Wer die Schalter nicht setzt, bleibt mit dem neuen Stand auf den Legacy-Ablagen.

### Voraussetzungen

- Eine laufende `0.9.x`-Installation mit Legacy-Ablage, Zugriff auf Host, Docker und `uv`.
- Docker-Host, dessen `nofile`-Limit Supavisor erlaubt ([`supabase/README.md`](../../supabase/README.md), Abschnitt „Voraussetzungen“).
- Ein **Wartungsfenster** für Schritt 5 bis 8. Agora bleibt von der ersten Übertragung bis zum Neustart mit den neuen Schaltern angehalten ([`metadata-postgres-cutover.md`](metadata-postgres-cutover.md)).
- Der Secret-Wert `AGORA_SECRET_KEY` bleibt **derselbe**. Eine Rotation ohne Neuverschlüsselung macht die migrierten Profil-Schlüssel unbrauchbar ([`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md), Abschnitt „Der Sonderfall Schlüssel“).
- Secret-Werte kommen aus dem Secret-Store des Betreibers, nie in einen Commit, ein Log oder einen Chat.

### 1. Backup, mit geprobtem Restore

Vor jeder Änderung Dateiverzeichnisse und Neo4j sichern. Läuft der Stack mit mehreren Compose-Dateien, muss vorher `COMPOSE_FILE` genau diese Dateien nennen ([`restore-drill.md`](restore-drill.md), Abschnitt „Durchführung“).

```bash
bash scripts/restore-drill.sh --phase backup --backup-dir /srv/agora-backup
```

Neo4j ist für die Dauer des Dumps gestoppt. Solange kein Schalter auf `postgres` steht, ist der PostgreSQL-Teil des Backups ein No-Op. Der Restore muss vor dem Cutover geprobt sein, und zwar aus Sicht der Verifikation:

```bash
cd backend
uv run python scripts/restore_verify.py --data-dir uploads --store-dir data
```

Exit `0` ist bestanden. Exit `2` (etwas blieb ungeprüft) ist **kein** Erfolg. Einzelheiten und der vollständige Drill: [`restore-drill.md`](restore-drill.md), Verfahren in [`../backup-restore.md`](../backup-restore.md).

**Rückweg:** entfällt, der Schritt verändert nichts außer dem Backup-Verzeichnis.

### 2. Ziel-Stand einspielen, Schalter noch auf Legacy

Erst den Code, dann die Daten. Checkout oder Image des Ziel-Stands ausrollen, **ohne** einen Schalter zu setzen, und prüfen, dass die Installation wie zuvor läuft. Damit bleibt der Rückweg für den Code ein Tag-Wechsel. Den bisherigen Stand notieren (Image-Tag oder Commit).

Für Images aus GHCR: [`ghcr-deploy.md`](ghcr-deploy.md) (feste `sha-<7>`- oder `vX.Y.Z`-Tags, nie `edge`/`latest`). Für den lokalen Build: [`../deployment-prod-like.md`](../deployment-prod-like.md).

Das laufende Image und der Checkout, aus dem die Migration läuft, müssen **denselben Alembic-Head** kennen. Sonst bricht das Start-Gate ([#1582](https://github.com/arn0ld87/agora/issues/1582)) nach dem Umschalten ab, und der Container startet in einer Schleife neu (so geschehen bei #1592):

```bash
cd backend && uv run alembic -c migrations/alembic.ini heads
docker compose exec -T agora sh -c \
  'cd /app/backend && .venv/bin/alembic -c migrations/alembic.ini heads'
```

Beide Ausgaben müssen dieselbe Revision zeigen ([`metadata-postgres-cutover.md`](metadata-postgres-cutover.md), Abschnitt „Image und Checkout auf denselben Head prüfen“).

**Rückweg:** vorherigen Image-Tag oder Commit setzen und neu starten ([`ghcr-deploy.md`](ghcr-deploy.md), Abschnitt „Rollback“). Bis hier sind keine Daten angefasst.

### 3. Supabase-Stack aufsetzen

Ausführlich: [`supabase/README.md`](../../supabase/README.md), Abschnitt „Einrichtung“. Die Reihenfolge ist zwingend, `bootstrap.sh` kommt **vor** dem ersten `docker compose up`.

```bash
cd supabase
./bootstrap.sh                        # holt die Fremdkonfiguration nach volumes/ (gepinnter Commit)
cp .env.example .env                  # jedes Secret-Feld füllen, siehe README
docker network create agora-backend   # einmalig pro Host
docker compose up -d
curl -f -H "apikey: $ANON_KEY" http://127.0.0.1:8000/auth/v1/health
```

Der `apikey`-Header ist Pflicht, das Gateway antwortet sonst mit 401. Läuft der Stack, hängt das Overlay Agora ans gemeinsame Netz (weitere Overlays wie Prod, Proxy oder Host-Overlay bleiben dabei, das GHCR-Overlay steht als letztes `-f`, siehe [`ghcr-deploy.md`](ghcr-deploy.md)):

```bash
cd ..
docker compose -f docker-compose.yml \
  -f deploy/compose/docker-compose.supabase.yml up -d
```

Aus dem Agora-Container sind dann `api-gw:8000` und `supavisor:5432` erreichbar. Redis und Neo4j bleiben außerhalb von `agora-backend`.

Wer auf einem Host bereits einen self-hosted Supabase-Stack betreibt, kann Agora dort als eigenes Schema `agora` ansiedeln, wie auf armserver ([`../STATUS.md`](../STATUS.md), Abschnitt „Metadaten-Cutover armserver (#1592)“). Dann entfallen `bootstrap.sh` und der eigene Stack, alle übrigen Schritte gelten.

#### Sicherheitsminimum (Teilmenge aus Plan §37)

Plan [`§37 „Security Gates“`](../plans/supabase.md) gilt „vor Internet-Exposition“. Für die Einrichtung im Einzelnutzer-Betrieb (JWT und offene Registrierung bleiben aus, ADR-0019) sind aus §37 diese Punkte im Repo belegt und hier verbindlich:

- [ ] Standard-Secrets ersetzt: kein Secret-Feld in `supabase/.env` bleibt leer. `POSTGRES_PASSWORD` nur aus `[A-Za-z0-9]` (`openssl rand -hex 32`).
- [ ] `SERVICE_ROLE_KEY` nur in der Backend-Umgebung, nie im Frontend, in einem Image oder in einem Log.
- [ ] DB-Port und Studio nicht öffentlich: alle Host-Ports bleiben an `127.0.0.1` gebunden, nach außen geht nur das Gateway über den Reverse Proxy ([`supabase/README.md`](../../supabase/README.md), Abschnitt „Exposition“).
- [ ] Images gepinnt: `SUPABASE_REF` in `bootstrap.sh` und die Image-Tags in `supabase/.env.example` passen zusammen.
- [ ] Backup vorhanden und Restore geprobt (Schritt 1).
- [ ] RLS aktiv: kommt mit Alembic (Schritt 4); die Laufzeitrolle ohne RLS-Umgehung steht in Schritt 4.

Die übrigen §37-Punkte (HTTPS, CORS, Redirect-URLs, Rate-Limits, Login-Bruteforce, Audit) betreffen Internet-Exposition und offene Registrierung: [`offene-registrierung.md`](offene-registrierung.md), [`../security-hardening.md`](../security-hardening.md). Welche §37-Punkte für `0.10` verbindlich sind, ist nirgends festgelegt (siehe [Offene Lücken](#offene-lücken)).

**Rückweg:** solange Agora den Stack nicht nutzt, lässt er sich ersatzlos entfernen ([`supabase/README.md`](../../supabase/README.md), Abschnitt „Rückbau“). Dort steht auch, warum das `down -v` nur mit ausdrücklich benannter Compose-Datei läuft: Ein nacktes `docker compose down -v` im Repository-Root löscht die Volumes von Redis und Neo4j.

### 4. Datenbank-URL, Rollen und Schema

`DATABASE_URL` hat keinen Default und muss mit `postgresql+psycopg://` beginnen. Der Benutzername trägt am Pooler die Tenant-ID als Suffix (`postgres.<POOLER_TENANT_ID>`). Zwei Formen laut [`.env.example`](../../.env.example): `supavisor:5432` im Container, `127.0.0.1:5432` für Skripte auf dem Host.

Empfohlen ist die Trennung in eine Owner-Rolle (Alembic, Backup, `AGORA_MIGRATION_DATABASE_URL`) und die Laufzeitrolle `agora_app` ohne `BYPASSRLS` (`DATABASE_URL`). Einmandantig ist sie nicht erzwungen. Einrichtung und Prüfung: [`rls-rollen.md`](rls-rollen.md).

Schema auf den Head bringen:

```bash
cd backend
uv run alembic -c migrations/alembic.ini upgrade head
```

`alembic upgrade head` nimmt `AGORA_MIGRATION_DATABASE_URL`, falls gesetzt, sonst `DATABASE_URL`. Fehlt dieser Schritt, existieren die `agora.*`-Tabellen nicht, und jede Übertragung bricht ab, statt eine Tabelle zu raten ([`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md)).

**Rückweg:** solange nichts umgeschaltet ist, lässt sich das Schema mit `alembic downgrade` zurücknehmen. Die Ziel-Revisionen je Domäne stehen in der Tabelle von [`metadata-postgres-cutover.md`](metadata-postgres-cutover.md); `downgrade` auf die Revision **vor** der Domäne löscht deren Tabelle samt Inhalt und alle späteren. Für RLS: `alembic downgrade 14d60476b8ce` ([`rls-rollen.md`](rls-rollen.md), Abschnitt „Rückweg“).

### 5. Agora anhalten, Baseline vorher

```bash
docker compose stop agora
cd backend
uv run python scripts/migration_baseline.py --output /tmp/vorher.json
```

Laufende Graph-Builds, Simulationen und Report-Erzeugungen vorher beenden oder abbrechen. Das Manifest enthält keine Secrets, aber die vollständige ID-Liste der Installation: neben das Backup legen, nicht committen ([`migration-baseline.md`](migration-baseline.md)).

**Rückweg:** `docker compose up -d agora`. Es wurde nichts verändert.

### 6. Legacy → PostgreSQL übertragen

Die Reihenfolge folgt den Fremdschlüsseln und ist **nicht verhandelbar**: LLM-Profile → Projekte → Simulationen → Runs → Reports. Jedes Skript zählt vorher mit `--dry-run`, überträgt idempotent (bekannte Kennungen werden übersprungen, nie überschrieben) und prüft mit `--verify` feldweise. Erst weiter, wenn `--verify` Exit 0 liefert. Meldet ein Skript `Failed > 0`, erklärt das Detail-Runbook die Fehlerarten.

Die Skripte laufen im Verzeichnis `backend/` in der Umgebung des Backends (`DATABASE_URL`, für Profile zusätzlich `AGORA_SECRET_KEY`).

#### 6.1 LLM-Profile

```bash
uv run python scripts/migrate_llm_profiles_to_postgres.py --dry-run
uv run python scripts/migrate_llm_profiles_to_postgres.py
uv run python scripts/migrate_llm_profiles_to_postgres.py --verify
```

Detail: [`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md). Die Profil-Schlüssel wandern in den Fernet-Store `llm_profile_secrets.json`.

**Rückweg:** `AGORA_LLM_PROFILE_BACKEND=sqlite`. `instance/llm_profiles.db` wird nur mit `mode=ro` gelesen und bleibt unverändert; neu hinzugekommen ist nur der Fernet-Store. Profile, die nach dem Umschalten in PostgreSQL entstanden oder geändert wurden, fehlen in der SQLite.

#### 6.2 Projekte

```bash
uv run python scripts/migrate_projects_to_postgres.py --dry-run
uv run python scripts/migrate_projects_to_postgres.py
uv run python scripts/migrate_projects_to_postgres.py --verify
```

Detail: [`projekt-postgres-umstellung.md`](projekt-postgres-umstellung.md).

**Rückweg:** `AGORA_PROJECT_BACKEND=file`. Die `project.json`-Dateien wurden nie verändert. Nach dem Umschalten in PostgreSQL entstandene Änderungen fehlen dort.

#### 6.3 Simulationen

```bash
uv run python scripts/migrate_simulations_to_postgres.py --dry-run
uv run python scripts/migrate_simulations_to_postgres.py
uv run python scripts/migrate_simulations_to_postgres.py --verify
```

Voraussetzung: Projekte migriert und verifiziert. Detail: [`simulation-postgres-umstellung.md`](simulation-postgres-umstellung.md).

**Rückweg:** `AGORA_SIMULATION_BACKEND=file`, aber erst **nach** dem Rückweg von Runs und Reports. Die `state.json`-Dateien wurden nie verändert.

#### 6.4 Runs

```bash
uv run python scripts/migrate_runs_to_postgres.py --dry-run
uv run python scripts/migrate_runs_to_postgres.py
uv run python scripts/migrate_runs_to_postgres.py --verify
```

Voraussetzung: Simulationen migriert und verifiziert. Detail: [`run-postgres-umstellung.md`](run-postgres-umstellung.md).

**Rückweg:** `AGORA_RUN_BACKEND=file`. Die Manifeste unter `uploads/run_registry/` wurden nie verändert. Runs, die nach dem Umschalten entstanden, fehlen dort.

#### 6.5 Reports

```bash
uv run python scripts/migrate_reports_to_postgres.py --dry-run
uv run python scripts/migrate_reports_to_postgres.py
uv run python scripts/migrate_reports_to_postgres.py --verify
```

Voraussetzung: Simulationen migriert und verifiziert. Detail: [`report-postgres-umstellung.md`](report-postgres-umstellung.md).

**Rückweg:** `AGORA_REPORT_BACKEND=file`. Die `meta.json`-Dateien wurden nie verändert. Reports, die nach dem Umschalten entstanden, haben Inhalte unter `uploads/reports/`, aber keine `meta.json` und sind nach dem Rückweg nicht sichtbar.

### 7. Sammelprüfung

Baseline nachher, dann alle Prüfungen in Cutover-Reihenfolge. Die Sammelprüfung darf **vor** dem Umschalten laufen; die Ziel-Schalter werden dafür für den Aufruf gesetzt:

```bash
uv run python scripts/migration_baseline.py --output /tmp/nachher.json
AGORA_LLM_PROFILE_BACKEND=postgres AGORA_PROJECT_BACKEND=postgres \
AGORA_SIMULATION_BACKEND=postgres AGORA_RUN_BACKEND=postgres \
AGORA_REPORT_BACKEND=postgres \
uv run python scripts/verify_metadata_cutover.py --baseline /tmp/vorher.json /tmp/nachher.json
```

Exit `0` nur, wenn jeder Schritt `OK` ist. Exit `1`: mindestens ein `FEHLER`. Exit `2`: nichts rot, aber etwas `UNGEPRÜFT` (etwa Neo4j nicht erreichbar). Ein ungeprüfter Schritt ist kein Erfolg. Was jeder Schritt prüft: [`metadata-postgres-cutover.md`](metadata-postgres-cutover.md), Abschnitt „Baseline nachher und Sammelprüfung“.

**Rückweg:** entfällt, das Skript liest nur.

### 8. Umschalten und neu starten

Alle fünf Schalter in der Umgebung der Installation (`.env`) setzen, dann neu starten. Die Schalter werden beim Import der `Config` einmal gelesen; ohne Neustart greift nichts.

```bash
AGORA_LLM_PROFILE_BACKEND=postgres
AGORA_PROJECT_BACKEND=postgres
AGORA_SIMULATION_BACKEND=postgres
AGORA_RUN_BACKEND=postgres
AGORA_REPORT_BACKEND=postgres
```

```bash
docker compose up -d agora
```

`Config.validate()` verweigert den Start, wenn ein Schalter auf `postgres` steht und seine Voraussetzung nicht (`DATABASE_URL`, Fremdschlüssel-Reihenfolge). Das Start-Gate bricht ab, wenn das Schema nicht auf dem Head steht.

**Rückweg:** siehe [Rollback](#rollback-09x--010), Stufe 2.

### 9. Prüfen und Backup nachher

```bash
curl -fsS http://127.0.0.1:${AGORA_BACKEND_PORT:-5001}/readyz
```

Der Check `postgres` muss `ok` melden (`disabled` hieße: kein Schalter greift). Danach die Punkte „Prüfen, dass die Oberfläche arbeitet“ der fünf Detail-Runbooks nacheinander abarbeiten (Profilliste, Projektliste, Simulationsliste und Zweig, Run-Übersicht und Resume, Report-Liste und Export).

Dann ein Backup, das PostgreSQL enthält (`postgres.dump` und `postgres-manifest.json`, sobald ein Schalter auf `postgres` steht):

```bash
bash scripts/restore-drill.sh --phase backup --backup-dir /srv/agora-backup-nachher
```

Ein Datensatz, der beim Übertragen nicht ankam, ist nach dem Umschalten nicht mehr sichtbar. Deshalb sind Schritt 6 und 7 vor dem Umschalten vollständig durchzuarbeiten. Das Löschen der Legacy-Ablagen kommt frühestens zwei stabile Releases nach dem Cutover (Plan §35).

### Rollback (0.9.x → 0.10)

| Stufe | Situation | Weg | Daten |
|---|---|---|---|
| 1 | vor Schritt 8, nichts umgeschaltet | Agora starten (`docker compose up -d agora`). Optional Schema per `alembic downgrade` zurück und Supabase-Stack entfernen (Schritt 3, 4). | Legacy-Ablagen sind unberührt und die Wahrheit. |
| 2 | nach Schritt 8, Stunden bis wenige Tage | Schalter **in umgekehrter Reihenfolge** zurück, dann neu starten (unten). | Legacy-Daten sind unberührt, aber alles, was nur in PostgreSQL entstand oder geändert wurde, fehlt. |
| 3 | Code-Fehler im neuen Stand | vorherigen Image-Tag oder Commit ausrollen ([`ghcr-deploy.md`](ghcr-deploy.md), Abschnitt „Rollback“). | Macht keine Datenmigration und keine Alembic-Revision rückgängig. Stehen Schalter auf `postgres`, vorher Stufe 2 ausführen: Ein Stand ohne Postgres-Adapter liest nur die Legacy-Ablagen. |
| 4 | Daten unbrauchbar | Restore aus dem Backup aus Schritt 1 ([`restore-drill.md`](restore-drill.md), [`../backup-restore.md`](../backup-restore.md)). | Stand des Backups. Der Restore ist als Drill noch nicht nachgewiesen (#766). |

Stufe 2, in dieser Reihenfolge, sonst verweigert `Config.validate()` den Start:

```bash
export AGORA_REPORT_BACKEND=file
export AGORA_RUN_BACKEND=file
export AGORA_SIMULATION_BACKEND=file
export AGORA_PROJECT_BACKEND=file
export AGORA_LLM_PROFILE_BACKEND=sqlite
```

Ein Teil-Rückweg ist möglich, solange die Reihenfolge stimmt (Reports allein zurück geht, Simulationen allein nicht, solange Runs oder Reports auf `postgres` stehen). Der Rückweg ist für die ersten Stunden nach dem Cutover gedacht, nicht für Wochen später: Eine Migration in Gegenrichtung (PostgreSQL → Legacy) gibt es nicht ([`metadata-postgres-cutover.md`](metadata-postgres-cutover.md), Abschnitt „Rückweg“; [`llm-profile-postgres-umstellung.md`](llm-profile-postgres-umstellung.md), Abschnitt „Der Rückweg“). Der Ablauf Umschalten und Zurück ist als CI-Gate belegt (#1589).

---

## 0.10 → 1.0

**Platzhalter.** Dieser Abschnitt wird im Freeze vor `1.0.0-rc.1` gefüllt (ROADMAP: „RC-Notes und Upgrade-Hinweise nach [#1673](https://github.com/arn0ld87/agora/issues/1673)“). `0.10.0` stabil ist die Upgrade-Quelle für 1.0.

Noch nicht festgelegt, Eingaben für den Abschnitt:

- Ob und wie sich die Code-Defaults der Metadaten-Schalter ändern und wie der 1.0-Install-Pfad mit vollem Supabase-Stack aussieht ([#1654](https://github.com/arn0ld87/agora/issues/1654)).
- Die Entscheidungen zu den offenen Einzelfällen aus [ADR-0021](../decisions/0021-kompatibilitaet-ab-1-0.md) §5, Stichtag `1.0.0-rc.1`: was davon vor 1.0 entfernt wird und was bis `2.0.0` bleibt. Die Policy selbst steht im ADR ([#1664](https://github.com/arn0ld87/agora/issues/1664)). `schema_version` für Dateiartefakte ist mit [#1663](https://github.com/arn0ld87/agora/issues/1663) eingeführt, siehe „Persistenz-Änderungen außerhalb des Versionssprungs“.
- Der Fresh-Host-Install/Restore als Nachweis ([#766](https://github.com/arn0ld87/agora/issues/766), [#1659](https://github.com/arn0ld87/agora/issues/1659)).

---

## Offene Lücken

Was im Repository nicht belegt ist, steht hier statt als Behauptung im Ablauf:

- **Zielversion:** `0.10.0-rc.1` und `0.10.0` sind nicht getaggt. Der Ziel-Stand in Schritt 2 ist bis dahin ein Commit von `main`, kein Tag.
- **Default-Umstellung:** Ob `0.10.0` die fünf `AGORA_*_BACKEND`-Defaults auf `postgres` dreht, ist noch nicht festgelegt ([#1654](https://github.com/arn0ld87/agora/issues/1654)). Im Code sind die Legacy-Defaults aktiv ([`../STATUS.md`](../STATUS.md), Abschnitt „0.10-Blocker aus heutiger Sicht“).
- **§37-Teilmenge:** Die Auswahl im Sicherheitsminimum ist aus `supabase/README.md`, Plan §37 und ADR-0018 abgeleitet. Eine verbindliche Liste für `0.10` gibt es nicht.
- **Fresh-Host-Nachweis:** Der Restore-Drill ([#766](https://github.com/arn0ld87/agora/issues/766)) ist nicht durchgeführt. Der reale Cutover (#1592) lief mit dem bestehenden Supabase des Hosts, nicht mit dem Stack aus `supabase/`; dessen Fresh-Install ist noch nicht nachgewiesen.
- **`agora_app` hinter Supavisor:** [`rls-rollen.md`](rls-rollen.md) zeigt die Laufzeit-URL ohne Tenant-Suffix. Wie der Benutzername der Rolle am Pooler lautet, ist dort nicht ausgeführt.
- **Compose-Servicename:** Die Detail-Runbooks schreiben `docker compose stop backend` mit dem Zusatz „oder der für die Installation übliche Weg“. Der Service in `docker-compose.yml` heißt `agora`, dieses Runbook nutzt ihn.
- **Dateiartefakt-Schemas:** Eine Migration bestehender Dateiartefakte auf neue Schema-Versionen ist nicht Teil des Sprungs ([#1663](https://github.com/arn0ld87/agora/issues/1663) offen).
