### Fixed

- **Supabase-Login: Recovery-Session und Abmeldung** — Eine Session ohne aktiven Workspace (Passwort-Reset über den Mail-Link) erreicht nur noch den Reset, sonst führt der Guard zum Login. `signOut()` verwirft Session, Token, Workspace und SSE-Tickets auch dann, wenn die Abmeldung bei Supabase scheitert, und löscht die Session dann lokal (`scope: 'local'`). (#1617)
