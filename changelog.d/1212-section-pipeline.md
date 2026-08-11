Der Abschnitts-Durchlauf der Reportgenerierung liegt nicht mehr als Schleife in `generate_report`, sondern hinter `process_section` im neuen Modul `app/services/report_agent/section_pipeline.py`. `generate_report` schrumpft von 455 auf 322 Zeilen und behält nur noch die Orchestrierung: Abbruchprüfung, Akkumulation der fertigen Abschnitte und Statusableitung.

Was ein Abschnitt beim Verarbeiten braucht, kommt über `SectionContext` herein — Daten und Seams, mit Default-Bindung an die echten Implementierungen. Das Ergebnis steht in `SectionResult` und trägt beobachtbar, was gebunden und was vom Evidence-Gate verworfen wurde. `ReportAgent._save_evidence_section` gibt dieses Ergebnis dafür zurück, statt es nur als Seiteneffekt in der Evidenzkarte abzulegen; die Persistenz bleibt unverändert.

Verhalten unverändert — reiner Deepening-Refactor.
