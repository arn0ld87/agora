### Behoben

- Ein Lauf, bei dem **alle** Personas nach gescheiterten LLM-Versuchen als
  regelbasierte Platzhalter in die Simulation gingen, meldete sich nach außen
  als erfolgreich. Die Degradierung war erfasst, blieb aber folgenlos: sie
  stand als `warning` im Task-Ergebnis, und der Report, der am Ende
  weitergegeben wird, wusste nichts davon. Ein Nutzer ohne Blick ins
  Backend-Log hielt das Ergebnis für belastbar. Zwei Stellen ziehen die
  Konsequenz jetzt nach:
  - `persona_rule_based_fallback` wird `blocking`, wenn keine einzige Persona
    vom Modell kam — der Vorbereitungsschritt erreicht „bereit" dann nicht.
    Bei einer Teilquote bleibt es `warning`: echte Stimmen sind dabei, die
    Platzhalter sind einzeln gekennzeichnet, der Lauf ist verwertbar.
  - `RunDegradationModel.component` kennt `persona_generation`. Ein Report,
    dessen Personas Platzhalter waren, wird über die bestehende
    `apply_run_degradation_downgrade`-Mechanik auf `INCOMPLETE` abgestuft
    statt als `completed` hinauszugehen.

  Die bewusste Wahl `use_llm_for_profiles=False` bleibt degradierungsfrei —
  gezählt wird `generation_error`, nicht `generation_source`. (#1419)
