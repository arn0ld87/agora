### Fixed

- Replay-Overrides verwenden den kanonischen `AiModelRef` statt eines offenen
  Dictionaries. Die `provider_connection_id` wird jetzt an das Stage-Routing
  durchgereicht — dieselbe Modell-ID auf zwei Provider-Connections landete
  vorher auf der falschen Connection.
- Validierungsfehler beim Replay liefern einen strukturierten Fehler-Envelope
  mit `code` und sanitisierten Details, statt das rohe
  `ValidationError.errors()`-Payload als Fehlertext zu setzen.
- Run-Manifeste werden atomar geschrieben (tmp-Datei + `os.replace`). Ein
  fehlgeschlagener Schreibvorgang lässt das vorhandene Manifest unverändert;
  parallele Leser sehen kein halbfertiges JSON.
- `runtime.usage_summary` wird beim Finalisieren aus `usage_summary.json`
  übernommen und blieb bisher in jedem Simulations-Manifest leer.
- `RunManifest` mit `status="final"` verlangt jetzt Laufzeitdaten. `draft` und
  `legacy` bleiben ohne `runtime` gültig.
- Der Replay-Dialog bietet keine Eingabefelder mehr für Seed-Dokument und
  Zufalls-Seed an — beide werden serverseitig mit HTTP 400 abgelehnt. Ein halb
  ausgefülltes Modell-Override sperrt den Submit, statt still auf das
  Originalmodell zurückzufallen.
- Der Fehlerpfad des Replay-Dialogs verwendet einen i18n-Key statt eines
  hartkodierten deutschen Texts.
