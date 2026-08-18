### Behoben

- Ein terminal ausgefallenes Tool wird abgeschaltet statt abgeraten. Der
  Hinweis "Do NOT call interview_agents again" stand nur im Tool-Ergebnis und
  blieb folgenlos; das Tool verschwindet jetzt aus dem angebotenen Schema und
  ein trotzdem angeforderter Aufruf wird nicht ausgeführt.
- Der Reportstatus bildet den Zustand des Laufs ab. Gescheiterte Simulation,
  unvollständige Runden, angeforderte Interviews ohne Ergebnis und
  fehlgeschlagene Abschnitte stufen `completed` auf `incomplete` ab.
- Parallele Reports schreiben nicht mehr in die Logdateien des jeweils anderen.

### Neu

- `run_degradations` am Report: strukturierte Qualitätsmängel des Laufs mit
  Komponente, Grund und Schweregrad. Additiv mit Default.
- Deterministische Red-Team-Invarianten über den fertigen Lauf
  (`assert_run_invariants`) — abzählbar statt erzählt.
