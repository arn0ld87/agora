# Runbook: Migrations-Baseline (Phase 0)

Zugehöriger Plan: [`docs/plans/supabase.md`](../plans/supabase.md) §6 „Phase 0: Baseline und Sicherheitsnetz".
Werkzeug: [`backend/scripts/migration_baseline.py`](../../backend/scripts/migration_baseline.py).

## Warum dieses Runbook existiert

Vor dem ersten Datenumbau muss feststehen, welcher Stand als „funktioniert" gilt — und zwar als vergleichbare Zahlenreihe, nicht als Prosa. „Die Migration lief sauber durch" ist keine Aussage, gegen die sich irgendetwas prüfen lässt; „Projects: 47 vorher, 47 nachher, alle IDs identisch" ist es. `migration_baseline.py` liefert genau diese Zahlenreihe: Es wird zweimal gefahren, einmal vor und einmal nach einer Migrationsphase, und die beiden Manifeste werden mit `--compare` gegeneinander gehalten. Fehlt danach eine ID oder weicht ein Zeitstempel ab, steht es im Diff — nicht drei Wochen später in einem Bericht, wenn niemand mehr sagen kann, wann genau der Datensatz verschwunden ist.

## Abgrenzung zu den Nachbarwerkzeugen

Drei Fragen, drei Werkzeuge:

| Werkzeug | Beantwortet |
|---|---|
| [`scripts/restore-drill.sh`](../../scripts/restore-drill.sh) | Lässt sich ein Backup sichern? |
| [`backend/scripts/restore_verify.py`](../../backend/scripts/restore_verify.py) | Funktioniert eine Wiederherstellung? |
| `backend/scripts/migration_baseline.py` | Hat eine Migration etwas verloren? |

`migration_baseline.py` sichert nichts und prüft keinen Restore — es liest ausschließlich und schreibt nur die Manifestdatei. Details zu Backup und Restore stehen in [`restore-drill.md`](restore-drill.md).

## Durchführung

Vor der Migrationsphase ein Manifest erzeugen:

```bash
cd backend
uv run python scripts/migration_baseline.py --data-dir uploads --instance-dir instance --output ../baseline-vorher.json
```

Dann die Migrationsphase fahren.

Danach ein zweites Manifest erzeugen:

```bash
cd backend
uv run python scripts/migration_baseline.py --data-dir uploads --instance-dir instance --output ../baseline-nachher.json
```

Und beide vergleichen:

```bash
cd backend
uv run python scripts/migration_baseline.py --compare ../baseline-vorher.json ../baseline-nachher.json
```

Weitere Optionen: `--json` gibt das Manifest zusätzlich auf stdout aus (nützlich zum Ablegen in einer Issue-Notiz), `--skip-checksums` lässt die Artefaktprüfsummen aus (schneller, aber ohne Inhaltsnachweis), `--skip-graph` fragt Neo4j nicht ab, falls kein erreichbarer Graph existiert — beide Graph-Klassen bleiben dann als ungeprüft markiert statt als „null Knoten".

## Exit-Codes

`0` heißt: beide Manifeste sind identisch — Anzahl, IDs, Felder und Prüfsummen unverändert. `1` heißt: eine echte Abweichung wurde gefunden, etwa eine verschwundene ID oder eine geänderte Prüfsumme. `2` heißt: kein Unterschied gefunden, aber nicht alles war vergleichbar — mindestens eine Quelle war in einem der beiden Läufe nicht erreichbar (Neo4j down, `llm_profiles.db` fehlt) und wurde als `unchecked` markiert statt als Nullstand gezählt.

`2` ist kein Erfolg. Dieselbe Regel gilt in `restore_verify.py` für übersprungene Prüfpunkte: eine Quelle, die man nicht erreichen konnte, ist kein Nachweis dafür, dass dort nichts verloren ging — sie ist ein blinder Fleck, der vor dem nächsten Lauf geschlossen werden muss, nicht ein grünes Ergebnis mit Fußnote.

## Was gemessen wird

Sechs Klassen aus dem Artefakt- und Instanzverzeichnis, plus zwei aus Neo4j:

| Klasse | Quelle | Felder |
|---|---|---|
| `projects` | `uploads/projects/proj_*/project.json` | `status`, `created_at`, `updated_at`, `graph_id` |
| `simulations` | `uploads/simulations/sim_*/state.json` | `status`, `created_at`, `updated_at`, `project_id`, `graph_id`, `source_simulation_id`, `root_simulation_id` |
| `runs` | `uploads/run_registry/*.json` | `run_type`, `status`, `started_at`, `updated_at`, `completed_at`, `entity_id`, `parent_run_id` |
| `reports` | `uploads/reports/report_*/meta.json` | `status`, `created_at`, `completed_at`, `simulation_id`, `graph_id`, `has_evidence` |
| `personas` | `uploads/simulations/sim_*/reddit_profiles.json` | Personazahl je Simulation (kein zentraler Store — eine Verschiebung zwischen zwei Simulationen wäre in einer reinen Summe unsichtbar) |
| `llm_profiles` | `instance/llm_profiles.db`, Tabelle `llm_profiles` | `provider`, `is_default`, `created_at`, `updated_at` |
| `graph_nodes` | Neo4j, `MATCH (n:Graph|Entity|Episode)` | Knotenzahl je Label |
| `graph_edges` | Neo4j, `MATCH ()-[r:RELATION]->()` | Kantenzahl |

Zusätzlich, wenn `--skip-checksums` nicht gesetzt ist: eine sha256-Prüfsumme je Datei unter dem Artefaktverzeichnis (`uploads/`), Pfad relativ dazu.

Eine Quelle, die nicht erreichbar war — ein fehlendes Verzeichnis, eine nicht lesbare `llm_profiles.db`, ein nicht erreichbares Neo4j —, wird als `unchecked` geführt und nicht mit `count = 0` verwechselt. `0` und „nicht geprüft" bedeuten im Vergleich etwas völlig anderes.

## Was ausdrücklich nicht gemessen wird

LLM- und Simulationsausgaben werden nicht byteweise verglichen. Diese Läufe sind nicht deterministisch, und ein gespeichertes `random_seed` macht einen Lauf nicht reproduzierbar — verglichen wird die Struktur der Persistenz, nicht der erzeugte Text.

Keine Dateiinhalte und keine Geheimnisse landen im Manifest. Die Spalte `api_key` aus `instance/llm_profiles.db` wird nicht gelesen — sie steht dort im Klartext. `base_url` und `model_name` bleiben aus demselben Grund draußen: eine Basis-URL kann ein Token tragen. Von den Fernet-Stores unter `backend/data/` würde, falls sie einmal in die Klassenliste aufgenommen werden, nur die Eintragsanzahl erhoben, nie ein Wert — aktuell ist `backend/data/` nicht Teil der erfassten Klassen.

## Wo die Manifeste liegen

Ein Manifest enthält keine Geheimnisse, aber die vollständige ID- und Zeitstempelliste der Installation — Projekt-, Simulations-, Run- und Report-IDs, Profil-Zuordnungen. Es gehört neben das jeweilige Backup und bleibt lokal. Nicht ins Repository committen.
