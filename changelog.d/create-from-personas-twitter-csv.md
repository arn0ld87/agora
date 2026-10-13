### Fixed (Lauf aus Personas auf Twitter — 2026-10-13)

- **Simulation aus Personas stürzt auf Twitter nicht mehr ab:** `POST /api/simulation/create-from-personas` schrieb `twitter_profiles.csv` mit den Schlüsseln des Reddit-Profils, OASIS brach beim Laden der Agenten mit `KeyError: 'user_char'` ab. Der Pfad nutzt jetzt den Schreiber der Persona-Generierung (`write_twitter_csv`) und liefert `user_char` und `description`. Vor dem Fix angelegte Simulationen müssen neu angelegt werden.
