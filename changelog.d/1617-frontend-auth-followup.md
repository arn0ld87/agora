### Fixed

- **Supabase-Login: Recovery-Session und Abmeldung** — Eine Session ohne aktiven Workspace (Passwort-Reset über den Mail-Link) erreicht nur noch den Reset, sonst führt der Guard zum Login. `signOut()` verwirft Session, Token, Workspace und SSE-Tickets auch dann, wenn die Abmeldung bei Supabase scheitert, und löscht dann die gespeicherte Session direkt aus dem Browser-Speicher (fester Schlüssel `agora-supabase-auth`), ohne zweiten Netzaufruf. (#1617)
