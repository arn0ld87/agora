### Behoben

- Gruppenentitäten werden nicht mehr zu erfundenen Einzelpersonen. Erkannt wird
  jetzt am Grundwort des Entitätstyps (`HospitalNetwork`, `EmployeeGroup`,
  `PatientAdvisoryCouncil`), nicht mehr an einer festen Liste, die jede neue
  Ontologie überholte.
- Ein Beruf, der einer Fachdomäne entstammt, die in keiner Quelle vorkommt,
  wird geleert statt erfunden. Ein Klinik-Rollout wird damit nicht mehr zu
  Fertigungsplanung oder Maschinenbau.
