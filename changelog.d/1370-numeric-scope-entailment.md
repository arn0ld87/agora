### Behoben

- Ein abweichender Zahlenwert allein gilt nicht mehr als Widerspruch. Vor einem
  `CONTRADICTED` prüft der Trust-Layer jetzt Einheit, Faktenart (Ist-Wert gegen
  Zielvorgabe oder Schranke) und Teilpopulation. Ein gemessener Anteil einer
  Teilgruppe widerlegt damit keine Mindestanforderung an die Gesamtheit mehr.
- Zahlen, deren Bezugsgruppe links steht ("Die Verwaltung erreichte 91 Prozent"),
  werden überhaupt erst als Fakt erkannt. Vorher waren sie für Beleg *und*
  Widerspruch unsichtbar.
- Ausgeschriebene Aufzählungen ("Erstens … Zweitens …") werden nach dem
  Entfernen eines widerlegten Punkts lückenlos neu gezählt — bisher galt dieser
  Schutz nur für nummerierte Listen.
