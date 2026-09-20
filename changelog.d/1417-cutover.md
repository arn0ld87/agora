# Slice 2.2 — Echter Cutover

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
