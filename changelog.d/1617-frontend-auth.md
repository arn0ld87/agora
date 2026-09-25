### Added

- **Supabase-Login im Frontend** — Ist JWT aktiv, meldet sich das Frontend über `@supabase/supabase-js` an. Der Client dient nur der Anmeldung (PKCE, Auto-Refresh), Fachdaten laufen weiter über Flask.
  - **Store `auth`:** hält Konfiguration, Session, Workspaces und den aktiven Workspace. Beim ersten Login legt er den persönlichen Workspace an (Bootstrap).
  - **Header:** Der Interceptor sendet `Authorization: Bearer` und `X-Agora-Workspace`. Bei `401` folgt einmal ein Refresh, danach Abmeldung.
  - **Views** unter `/auth/*`: Login, Registrierung, Passwort-Reset und E-Mail-Bestätigung. Der Guard leitet ohne Session auf den Login, `next` nur auf interne Pfade.
  - **Nutzermenü:** Workspace-Wechsel und Abmelden.
  - **Verträge:** Zod-Spiegel für `/api/auth/config` und die Workspace-Verträge.
  - **Legacy-Modus unverändert.** (#1617)
