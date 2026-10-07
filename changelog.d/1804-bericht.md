### Added

- Frontend-Umbau Etappe 5: Der Bericht ist ein Reiter am Lauf (`/simulations/:simulationId/report/:reportId?`) mit Gliederung, Lesespalte, Belegspalte und Rückfragen an den Berichtsagenten. Aus der Belegspalte führen verifizierte Sprünge in Feed, Graph und Interviews (#1804).

### Changed

- `/v4/report/:reportId`, `/report/:reportId`, `/v4/interaction/:reportId` und `/interaction/:reportId` leiten in den Bericht-Reiter um; die alten Berichts- und Interaktionsansichten sind nicht mehr erreichbar (#1804).
