### Fixed

- Bericht: Ein Claim trägt das Geltungsbereich-Label „Simulationskonsens" erst,
  wenn mindestens zwei verschiedene Personas ihn stützen. Stützt genau eine
  Persona (auch über mehrere Evidence-Einträge, etwa zwei Fragen an dieselbe
  Person), steht der neue Wert `simulation_single_voice` („Einzelstimme
  (Simulation)") am Claim. Im Lauf `report_a8fa9ff9fad0` trugen vier Claims
  „Simulationskonsens", obwohl je ein einziges Interview sie stützte. Die
  Persona-Identität kommt aus `raw.agent_name` des Evidence-Records,
  ersatzweise aus `persona_stakeholder_group`; ist keine ermittelbar, gilt
  konservativ „eine Stimme". Der Wert ist in `Claim.confidence_scope`
  (`report-v3.schema.json`) und im Zod-Spiegel ergänzt; bestehende Berichte mit
  `simulation_consensus` bleiben gültig und werden nicht umgeschrieben (#1766).
- Bericht: Kernaussagen (`SectionMetadata.key_takeaways`) haben kein eigenes
  Confidence-Urteil mehr. Das Feld `confidence` ist ein Enum
  (`low`/`medium`/`high`, optional) und wird nach der Claim-Finalisierung des
  Abschnitts, vor dem Schreiben von `evidence_map.json`, auf das höchste Label
  der verbliebenen Claims gedeckelt; ohne validierten Claim (oder nur
  `speculative`) entfällt es (`null`). Im Lauf `report_a8fa9ff9fad0` standen 7
  von 29 Kernaussagen auf `high`, während alle fünf finalen Claims `low` waren.
  `confidence_scope` einer Kernaussage bleibt nur dann `evidence`, wenn ein
  Claim des Abschnitts quellengebunden ist; `empirical` wird nie bestätigt. Ein
  Wert außerhalb des Enums kippt den Abschnitt nicht, sondern wird `null`.
  Bestehende `evidence_map.json` mit freien Strings bleiben lesbar; sie werden
  nicht migriert (#1766).
