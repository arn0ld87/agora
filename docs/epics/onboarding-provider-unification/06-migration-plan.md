# Migration and Rollback Plan

## Provider und Modelle

1. Neue Verträge ergänzen, Legacy-Verträge unverändert lesbar lassen.
2. Adapter mit explizitem Mapping und Telemetrie einführen.
3. Neue Writes in kanonischem Format speichern.
4. Bestehende Profile idempotent migrieren; Original sichern.
5. Read-After-Write und Route-Auflösung vergleichen.
6. Legacy-Writes abschalten, Leser erst in einem späteren Slice entfernen.

Rollback: Feature-Flag auf Legacy-Writes, neue Daten über Adapter lesbar halten.

## Benutzerprofil und KI-Presets

Das heutige `LlmProfile` wird sichtbar als KI-Preset bezeichnet, ohne seine
Persistenz vorschnell umzubenennen. Das neue Benutzerprofil erhält einen eigenen
Schlüsselraum. Es gibt keine automatische Vermischung.

## Embeddings

1. Bestand, Dimension, Modell und betroffene Knoten inventarisieren.
2. Backup-/Restore-Punkt bestätigen.
3. neue versionierte Embedding-Property und neuen Index anlegen.
4. re-embedden mit Checkpoint, Fortschritt, Abbruch und Retry.
5. Anzahl, Dimension und Suchstichproben validieren.
6. Konfigurationsalias atomar umschalten.
7. alten Index für eine definierte Rollback-Frist behalten.
8. Löschung nur nach expliziter Bestätigung.

Rollback: Alias zurück, neuen Job stoppen, neue Property/Index später
kontrolliert entfernen. Alte Daten bleiben unangetastet.

## Persona-Zahl

Persistierte Runs ohne `requested_persona_count` behalten ihr historisches
Verhalten und erhalten im Audit `source=legacy`. Neue Runs müssen die Invariante
erzwingen. Bestehende Artefakte werden nicht umgeschrieben.
