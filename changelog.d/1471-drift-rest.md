### Fixed

- Persona-Generierung: Die Branchenquote lenkt nur noch bewusst synthetische Personas — trägt die Quelle einer Entität erkennbares Fachvokabular, bleibt der Prompt-Block weg und die Persona behält ihre Branche. Erkannte Domänendrift korrigiert jetzt Beruf, Bio und Freitext über `LLMClient.chat_json` statt nur `profession` zu leeren; scheitert die Korrektur, bleibt die konservative Linie und `generation_error` zeigt die Degradation an (#1471).
