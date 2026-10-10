### Changed

- **Abnahme Frontend-Umbau Etappe 7 (Personasätze) und Etappe 8 (Graph-Bearbeitung): Verhalten durch UI-Tests belegt (#1811, #1812).** Zusätzliche Evidenz in den Frontend-Specs und ein dabei gefundener Fix. Etappe 7: Bearbeiten einer bestehenden Persona (Aufruf mit Personasatz, Eintrag und Profil), Einzellöschen mit Rückfrage, Umbenennen, gesperrter Personasatz (Duplizieren bleibt als Ausweg erreichbar, der Editor öffnet nur lesbar und speichert nicht), Tastatur (Escape im Editor und im Umbenennen-Formular, Rückfrage bei ungespeicherten Änderungen) und zugängliche Namen von Symbolleiste, Kartenliste, Auswahlfeldern, Rückfrage und Editor-Dialog. Etappe 8: gesperrter Graph ohne Schreibweg (kein Formular, kein Löschen, kein Zusammenführen, keine Schreibaufrufe), Sperrband als Statusmeldung mit Grund und Ausweg Kopie, fail-closed bei unklarem Sperrzustand, Herkunftsmarken (manuell, bearbeitet, extrahiert) mit Text und Symbol, auch bei gesperrtem Graphen, sowie benannte Bedienelemente.

### Fixed

- **Personasatz: Tastaturfokus geht nach dem Löschen nicht mehr verloren.** Nach erfolgreichem Löschen ist die Auswahl leer und der Löschknopf deaktiviert; der Fokus fiel dadurch auf die Seite zurück. Er geht jetzt auf „+ Persona“. Bei fehlgeschlagenem Löschen bleibt er wie bisher auf dem Löschknopf.
