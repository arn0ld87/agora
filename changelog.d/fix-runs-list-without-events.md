### Fixed

- **Run-Liste ohne Event-Log:** `GET /api/runs` liefert kein `events`-Feld mehr. Die Liste wird alle 5 bis 10 Sekunden gepollt und war auf gns3 mit den Event-Logs 18,7 MB groß. Detail- und Events-Endpunkt bleiben unverändert.
