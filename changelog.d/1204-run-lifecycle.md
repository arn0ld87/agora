### Geändert

- Run-Zustandsführung zentralisiert: das handgeschriebene Muster „Run anlegen
  (pending) → Arbeit → Endzustand" an sechs Stellen (Simulationsstart und
  -vorbereitung, Run-Restarts, Report-Start) läuft jetzt über den
  Kontextmanager `RunLifecycle` (#1204). Kein Abbruchpfad — auch
  `SystemExit`-artige — hinterlässt mehr einen pending-Phantom-Run; ein nicht
  persistierter Statusübergang wird als Fehler sichtbar (500) statt still
  verschluckt.
