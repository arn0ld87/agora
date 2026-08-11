- Live-Feed: Reddit-Kommentare erreichen den Feed wieder. Der Emitter erwartete den
  Elternpost in der OASIS-Trace-Zeile, die ihn nie enthält — er wird jetzt über die
  `comment`-Tabelle aufgelöst. Damit bekommt der Reply-Tree Äste und die rund 86 %
  der Reddit-Aktivität, die Kommentare sind, werden sichtbar (#1209 5c/5d).
- Live-Feed: `score` trägt den echten Voting-Stand aus der Simulations-DB
  (`num_likes - num_dislikes`) statt einer hartkodierten 0; Twitter bleibt bei 0,
  weil es kein Up-/Down-Voting kennt (#1209 5b).
- `PostCreatedEvent`: Feld `sentiment` entfernt. Es gab nie einen Sentiment-Service,
  das Feld trug nie einen Wert und wurde nirgends gerendert (#1209 5b).
