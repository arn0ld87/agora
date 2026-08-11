### Added — Feed-Snapshot beim Mount (#1009)

- **Feed ist beim Öffnen sofort befüllt:** Die Simulations-Feed-View lädt beim Mount den bisherigen Sim-Bestand aus der SQLite-DB über einen neuen `/feed-snapshot`-Endpoint und ingestiert ihn vor SSE-Stream-Start. `useSimFeed`-Dedup per `post_id` verhindert Doppeleinträge, wenn Live-Events für bereits geladene Posts eintreffen. (#1009)

### Changed — PostCreatedEvent-Vertrag: persona_name + voice_register-Vokabular (#1216)

- **`persona_name` ist Pflichtfeld:** Der Layer-0-Vertrag (`PostCreatedEvent`) führt den Anzeigenamen der Persona als Pflichtfeld; Frontend-Komponenten (RedditPost, TwitterPost, PersonaAvatar) zeigen den Namen statt der technischen `persona_id`. (#1216 5a)
- **`voice_register`-Vokabular an Profil-Generator angebunden:** Die Enum-Werte sind jetzt `formal-de`/`neutral-de`/`technical-de`/`skeptisch-de` (zuvor `formal`/`casual`/`jugendsprache`, was nie an den Generator angebunden war und per Fallback jede Persona verschleierte). Legacy-Werte werden vom Vertrag abgelehnt (Anti-Dekorations-Linie). Twitter-Profile (CSV persistiert kein `voice_register`) erhalten dokumentiert `neutral-de` als Generator-Default. (#1216)
- **Kommentare als PostCreatedEvent:** Der OASIS-Runner emittiert `CREATE_COMMENT`-Aktionen mit plattformpräfixtem `post_id` (`<platform>:comment:<id>`) und `parent_post_id` = Elternpost, sodass der Reddit-Reply-Tree im Live-Feed Äste bekommt. `post_id` ist plattformübergreifend eindeutig (`<platform>:<id>`), was Dedup-Kollisionen zwischen Reddit und Twitter auflöst. (#1216 5c)