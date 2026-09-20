# Slice 2.1 — Kanonische Index-Auflösung

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
