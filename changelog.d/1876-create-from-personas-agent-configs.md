### Fixed (Läufe aus Personas: Agenten werden aktiviert — 2026-10-13)

- **`POST /api/simulation/create-from-personas` schreibt je Persona einen `agent_configs`-Eintrag:** Bisher blieb die Liste leer. Die Rundenauswahl zieht ihre Kandidaten nur daraus, also wurde nie ein Agent aktiviert, und der Lauf endete mit 0 Aktionen als `completed`. Die Einträge tragen `agent_id` = `user_id` des Profils, Standardwerte ohne Modell und `config_source="persona_default"`. Vor dem Fix angelegte Läufe aus Personas müssen neu angelegt werden. (#1876)
