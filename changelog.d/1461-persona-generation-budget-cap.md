### Behoben

- Ein hartes `max_llm_calls`-Budget wird bei paralleler Arbeit jetzt tatsächlich eingehalten, nicht nur angenähert. Ein bestandener `check_before_call()` reserviert einen Slot, und die Reservierung zählt wie ein verbrauchter Call, bis der Call verbucht ist — zuvor lasen alle gleichzeitigen Aufrufer denselben Vor-Aufruf-Stand und kamen durch. Zusätzlich deckelt die Persona-Generierung die Anzahl gleichzeitig gestarteter Worker auf das verbleibende Kontingent.
- Ein erschöpftes hartes Budget bricht die Persona-Stufe ab, statt drei Versuche lang zu warten und regelbasierte Ersatzprofile zu liefern. `BudgetExceededError` wird von den breiten Fehlerbehandlungen auf dem Persona-Pfad nicht mehr verschluckt.
