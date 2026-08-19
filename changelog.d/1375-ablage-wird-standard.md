### Changed (Die Ablage ist der Standard, 2026-08-19)

- **`/` führt jetzt in die Ablage statt aufs Dashboard.** Der Shell-Standard ist von `classic` auf `dossier` gewechselt: Ablage und Dossier sind gebaut, Abbrechen und Pause hängen an der Zeile, Personasätze und Berichte sind Startpunkte. `agora.shell=classic` im localStorage bleibt als Rückweg erreichbar, bis die alten Ansichten gelöscht sind — dann fällt der Flag ganz.
- **`views/Home.vue` ist entfernt.** Sie war seit dem `/home`→`/dashboard`-Redirect (ADR-0010) an keiner Stelle mehr eingebunden. `RunsView`, `RunDetailView` und `RunsDashboard` bleiben: sie leben in den v4-Wrappern weiter und werden von den Weiter-Aktionen der Ablage angesteuert.
