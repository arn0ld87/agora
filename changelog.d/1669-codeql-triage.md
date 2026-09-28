### Security

- CodeQL-High-Triage (#1669): Von 67 offenen Alerts waren 23 echte Funde und sind
  behoben. Service-Funktionen, die aus einer Simulations-ID einen Pfad bauen
  (Interviews, Aktionslog, Branching, Event-Bus, Simulationsverzeichnis und
  Konsolenlog), prüfen die ID jetzt selbst mit `validate_path_id`, statt sich auf
  die API-Schicht zu verlassen. Der Query-Parameter `platform` der
  Simulationshistorie wird geprüft (400 statt Dateisystemzugriff). Der
  SPA-Catch-all prüft Containment, bevor er das Dateisystem befragt. Die
  Provider-Erkennung vergleicht bei Ollama Cloud und Google den Hostnamen statt
  eines Teilstrings; das Stichwort `generativelanguage` außerhalb von
  `*.googleapis.com` zählt nicht mehr als Google. Die Ollama-Cloud-Regex ist gegen
  ReDoS gehärtet. `join_within` löst Symlinks jetzt über `realpath` auf. Die
  übrigen 42 Alerts sind False Positives und in GitHub mit der Stelle der
  greifenden Validierung dismissed.
