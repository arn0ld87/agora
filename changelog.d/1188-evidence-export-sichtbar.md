### Fixed (Evidence-Export bleibt sichtbar — 2026-08-10)

- **Evidence-JSON-Button verschwindet nicht mehr spurlos:** Solange die
  Evidenzkarte eines Reports noch nicht vorliegt, bleibt der Export-Button in
  der Report-Ansicht sichtbar, ist aber deaktiviert (`aria-disabled` plus
  zugängliche Beschreibung). `Step4Report.vue` lädt die Evidenzkarte nach
  Laufende mit exponentiellem Backoff (3 s bis 30 s gedeckelt) über ein
  10-Minuten-Budget nach, statt sie nach wenigen Sekunden dauerhaft leer zu
  belassen — dimensioniert auf die in #1187 gemessene Nachbearbeitungsdauer.
  Ist das Budget ausgeschöpft, zeigt der Tooltip „nicht verfügbar" statt
  weiterhin „wird noch erzeugt" zu behaupten. (#1188)
