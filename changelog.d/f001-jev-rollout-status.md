### Changed

- `docs/STATUS.md` hält den Rollout-Stand von f001 fest: Der Jev-Use-Case
  `local-search-relevance` ist fertig implementiert, löst im Normalbetrieb
  aber praktisch nie aus, weil `local_search` nur als Fallback bei einem
  Fehler der Neo4j-Suche läuft. `authoritative` wird deshalb produktiv nicht
  eingeschaltet; der Rückweg (`shadow`/`disabled` plus Neustart) ist
  dokumentiert. Jev an den Urteilsstellen eines ganzen Runs folgt als
  eigenes Feature.
