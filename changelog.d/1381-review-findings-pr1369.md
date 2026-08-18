### Behoben

- Der Coverage-Ledger persistiert keine rohen `producer_key`-Werte mehr —
  Web-Items tragen dort die volle Tool-URL samt Query.
- Ein Interview-Ausfall gilt nur bei explizit bekannter, nicht behebbarer
  Ursache als terminal. `503` und `connection refused` schalten das Tool nicht
  mehr für den ganzen Lauf ab; der Hinweistext folgt derselben Einschätzung.
- Der Coverage-Ledger ist referenzinteger: eine kanonisierte Zeile muss auf
  vorhandene Evidence zeigen, und Status und Feldbelegung schließen einander aus.
- Ein Schwellenwert in Tagen wird nicht mehr von einer Angabe in Minuten belegt.
- Zwei einander ausschließende Schranken ("mindestens 80" gegen "höchstens 70")
  gelten als Widerspruch.
- Ein an der Producer-Grenze gescheiterter Fakt zählt für die Data-Gap-Prüfung
  als vorhanden — sonst wird ein Registrierungsfehler zur fehlenden Information.
- Ein später Contract-Validierungsfehler landet in `run_degradations`.
- Ein Interview-Record deckt keine Simulationszuschreibung mehr ab.
- Die Red-Team-Invarianten prüfen komponentenscharf; ein unbezogener Mangel
  stellt keine fremde Prüfung mehr still.
- Ein zuerst als wiederholbar vermerkter Tool-Ausfall blockiert die spätere
  Abschaltung nicht mehr.
- Kein `KeyError` mehr im Sanitizer: Aufzählungswörter und Zählpositionen sind
  jetzt dieselbe Menge, durch eine Modul-Invariante gesichert.
- Threshold-Labels werden auf zehn statt sechs Zeichen gekürzt —
  "Fallbackdauer" und "Fallbackzeit" fielen sonst zusammen.
- Der Persona-Kohärenz-Log nennt keinen Entitätsnamen mehr (CodeQL).
