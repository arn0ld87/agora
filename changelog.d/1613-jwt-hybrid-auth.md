### Added

- **Supabase-JWT im Auth-Guard** — `AGORA_AUTH_BACKEND=legacy|hybrid|supabase` (Default `hybrid`, ohne `AGORA_SUPABASE_JWT_ISSUER` identisch mit `legacy`). Die Prüfung nach Plan §15 umfasst Signatur über JWKS oder HS256-Secret, eine Algorithmus-Allowlist je Schlüsselquelle, `iss`, `aud`, `exp`, `nbf` und `sub`. Der Workspace wird per `X-Agora-Workspace` gewählt und gegen `agora.workspace_members` geprüft. Jeder Request trägt einen `Principal`. `require_scope` leitet die Scopes aus der Workspace-Rolle ab, und signierte Tickets sind an ihren Aussteller gebunden. (#1613)

### Security

- **Betreiber-Endpunkte für JWT-Nutzer gesperrt** — Settings, API-Keys, Logs, Onboarding, Profil und Modell-Stream verwalten prozessweiten Zustand und antworten Supabase-Nutzern mit `403 operator_only`. JWT verlangt alle fünf Metadaten-Backends auf PostgreSQL. Bis zur Workspace-Isolation der Repositories (#1614) lehnt `Config.validate()` jede JWT-Konfiguration ab. Weder Token noch Claims noch das Secret erscheinen in Logs oder Fehlermeldungen. (#1613)
