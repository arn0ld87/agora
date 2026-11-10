### Fixed

- **Report-Modus bleibt beim Resume erhalten (#1479):** Ein fortgesetzter Report
  benutzt jetzt den Modus, mit dem der Lauf gestartet wurde (`strict`,
  `balanced`, `explorative`). Vorher speicherte der Resume-Pfad den Report
  ohne Modus, sodass jeder fortgesetzte Lauf auf `balanced` zurueckfiel —
  unabhaengig davon, mit welchem Modus er gestartet worden war.
- **`report_status` landet auch beim normalen Start in den Run-Metadaten (#1479):**
  Der Erfolgspfad des Report-Starts setzt das Metadatum `report_status`
  (`completed`/`incomplete`) genauso wie der Resume-Pfad. Bisher trug nur der
  Resume die ehrliche Status-Angabe; ein normal gestarteter Report blieb
  ohne sie.
- **Gemeinsame Job-Implementierung fuer Start und Resume (#1479):** Start- und
  Resume-Pfad teilen sich jetzt einen einzigen Report-Job
  (`ReportGenerationService.execute_report_job`). Die beiden Kopien waren
  auseinandergedriftet und trugen die beiden Fehler oben.
