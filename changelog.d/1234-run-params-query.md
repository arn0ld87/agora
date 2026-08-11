### Fixed

- Der Dashboard-Start reicht Rundenzahl und Run-Budget wieder bis zum
  Simulationsstart durch. Beide reisten über den `pendingUpload`-Store, den
  Schritt 1 nach dem Ontologie-Upload leert — Schritt 3 las anschließend den
  Reset-Default 10 statt der eingestellten Runden und fand gar kein Budget
  mehr vor. Sie laufen jetzt über den Query-Vertrag
  `contracts/runParamsQuery.ts`, der schon die Übergabe Schritt 2 → Schritt 3
  trägt, und überleben damit auch einen Reload auf der Simulationsroute
  ([#1234](https://github.com/arn0ld87/agora/issues/1234)).
