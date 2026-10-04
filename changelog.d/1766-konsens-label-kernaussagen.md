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
