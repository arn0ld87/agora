### Behoben

- Die Evidence-Bindung trug ein Feld, das der strikte Contract verbietet. Die
  Section-Validierung schlug dadurch fehl, und der Reparaturlauf verwarf jeden
  Claim mit gebundener Evidence.
- Interviews werden am Evidence-Typ erkannt, nicht an der Quellengattung:
  `agent_post` und `agent_interview` fallen beide auf `agent_quote`. Die
  Interview-Prüfungen waren dadurch genau dann still, wenn eine Simulation lief.
- Eine Quellenangabe links der Zahl ("Laut Betriebsrat") galt als
  Populationsunterschied und unterdrückte echte Widersprüche.
- Eine überschrittene Ober- oder Untergrenze gilt wieder als Widerspruch.
  Schrankenwörter bestimmen die Schranke, nicht mehr auch die Absicht.
- `run_degradations` wird beim Laden zurückgelesen; die API meldete sonst
  jeden Lauf als ungestört.
- Nur blockierende Mängel stufen `completed` ab — ein Bericht über eine noch
  laufende Simulation bleibt vollständig.
- Der Belegprüfungs-Anhang trägt wieder Abschnittsüberschriften.
- Ein Interview-Timeout schaltet das Tool nicht mehr für den ganzen Lauf ab.
- Modellableitungen und Web-Fundstellen können keinen Schwellenwert auf
  `verified` heben.
- "station" wird nicht mehr in "Ladestation" gelesen; ein solcher Fehlalarm
  löschte den Beruf einer korrekten Persona.
