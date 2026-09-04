### Behoben

- Ein Lauf, bei dem **alle** Personas nach gescheiterten LLM-Versuchen als
  regelbasierte Platzhalter in die Simulation gingen, meldete sich nach außen
  als erfolgreich. Die Degradierung war erfasst, blieb aber folgenlos: sie
  stand als `warning` im Task-Ergebnis, und der Report, der am Ende
  weitergegeben wird, wusste nichts davon. Ein Nutzer ohne Blick ins
  Backend-Log hielt das Ergebnis für belastbar. Zwei Stellen ziehen die
  Konsequenz jetzt nach:
  - `persona_rule_based_fallback` wird `blocking`, wenn keine einzige Persona
    vom Modell kam. `prepare_simulation` setzt dann `failed` statt `ready`
    und trägt die Ursache in `state.error` — der Vertrag verlangt seit jeher,
    dass ein blockierender Ausfall „bereit" nicht erreicht, durchgesetzt hat
    das bis hierher niemand. Bei einer Teilquote bleibt es `warning`: echte
    Stimmen sind dabei, die Platzhalter sind einzeln gekennzeichnet, der Lauf
    ist verwertbar und bleibt startbar.
  - `RunDegradationModel.component` kennt `persona_generation`. Ein Report,
    dessen Personas Platzhalter waren, wird über die bestehende
    `apply_run_degradation_downgrade`-Mechanik auf `INCOMPLETE` abgestuft
    statt als `completed` hinauszugehen. Das gilt auch für den nach einem
    Abbruch finalisierten Teil-Report, der bislang an der einzigen
    Degradations-Aggregation am Laufende vorbeilief.

  Die bewusste Wahl `use_llm_for_profiles=False` bleibt degradierungsfrei —
  gezählt wird `generation_error`, nicht `generation_source`. (#1419)
