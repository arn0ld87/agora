# Slice 1.3 — Graph-Build-Resume

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

Das schließt auch den Prozess-Neustart-Fall aus Slice 1.1 (#1472a): dessen
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
