### Fixed (Simulationsbeiträge als Belege im Bericht — 2026-10-05)

- **Evidence-Binding:** Simulationsbeiträge werden über ihren reinen Wortlaut gesucht und bekommen bis zu zwei eigene Kandidatenplätze neben den fünf besten. Vorher verdrängten Interviews sie; im Abnahmelauf wurden nur 7 von 29 Beiträgen je einem Claim vorgelegt. Schwelle und Entailment-Prüfung sind unverändert. (#1778)
- **Bericht:** Treffer der Beitragssuche sind in jedem Abschnitt Kandidat, nicht nur im suchenden. (#1778)
- **Bericht:** Die Beitragssuche läuft zu Beginn jedes Abschnitts einmal durch das System und zählt gegen das Limit von fünf Werkzeugaufrufen. Der Abschnitts-Prompt verlangt, öffentlich Gesagtes als Aussage im Fließtext zu berichten. (#1778)
- **Simulation:** Name, Aktivität, Haltung und Startbeitrag folgen dem OASIS-Agenten, auch wenn einzelne Profile fehlen. Vorher trugen ab der ersten Lücke alle Beiträge den Namen eines anderen Agenten (449 von 522 im Lauf `sim_b51b759f58f6`). Aktionsprotokolle älterer Läufe bleiben unverändert. (#1778)
