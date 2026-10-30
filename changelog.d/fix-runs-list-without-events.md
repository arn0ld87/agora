### Fixed

- **Run-Liste ohne Event-Log:** `GET /api/runs` liefert kein `events`-Feld mehr. Die Liste wird alle 5 bis 10 Sekunden gepollt und war auf gns3 mit den Event-Logs 18,7 MB groß. Detail- und Events-Endpunkt bleiben unverändert.
- **Berichtsliste ohne Berichtstext:** `GET /api/report/list` liefert kein `markdown_content` mehr. Das Frontend prüft Listeneinträge gegen den eigenen Vertrag `ReportListItemSchema`.
- **Gzip für JSON:** Das Backend komprimiert JSON-Antworten ab 1 KiB, wenn der Client `Accept-Encoding: gzip` sendet. SSE-Streams und Dateidownloads bleiben unkomprimiert.
