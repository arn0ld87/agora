### Added

- Graphen lassen sich von Hand bearbeiten (Backend, Etappe 8 des Frontend-Umbaus, ADR-0022): Entitäten und Beziehungen anlegen, ändern und löschen, Entitäten zusammenführen (`POST/PATCH/DELETE /api/graph/<graph_id>/entities…` und `…/relations…`). Knoten und Kanten tragen ein Herkunftsmerkmal (`provenance.origin`: `manual`, `edited` oder `null` für extrahiert); manuelle Beziehungen haben keine Episoden, bearbeitete behalten sie zur Anzeige. Anlegen ist über `client_request_id` wiederholbar, die Einbettung wird bei Änderung von Name, Typ oder Fakt neu berechnet. `GET /api/graph/data/<graph_id>` liefert additiv `entity_type` und `provenance`. Neuer Vertrag `graph_edit_contract.py` samt Schemas `schemas/graph-*.schema.json`. (#1808)
- `GET /api/graph/<graph_id>/lock` meldet, ob und von welchen Simulationen ein Graph verwendet wird. Neue Fehlercodes `graph_locked`, `graph_edit_conflict`, `embedding_migration_running`. (#1808)

### Changed

- Ein Graph ist gesperrt, sobald eine Simulation sein Projekt oder seine `graph_id` verwendet (abgeleitet aus dem Bestand, kein neues Feld). `DELETE /api/graph/delete/<graph_id>`, `DELETE /api/graph/project/<project_id>` und `POST /api/graph/project/<project_id>/reset` antworten dafür mit `409 graph_locked` und der Liste der nutzenden Simulationen. (#1808)
