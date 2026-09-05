### Fixed

- Persona-Vorbereitung akzeptiert CLI-Provider mit lokaler Anmeldung ohne HTTP-API-Key. Die Transportart kommt aus der Provider-Registry; HTTP- und unbekannte Provider werden weiterhin auf fehlende Schlüssel geprüft. Modellwahl und Stage-Routing bleiben unverändert. (#1438)
