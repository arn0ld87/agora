Ein Lauf mit dem `claude_cli`-Provider baute Ontologie und Graph sauber auf und
brach dann in der Persona-Erzeugung mit `LLM_API_KEY not configured` ab — und von
dort aus in jedem weiteren LLM-Schritt des Vorbereitungs-Jobs.

Die Ursache lag nicht im Persona-Generator, sondern eine Ebene darüber. Die
Stage-Route der Persona-Erzeugung gab für **jeden** Provider mit
`transport="cli"` `api_key=None` zurück, ohne den Secret-Store überhaupt zu
fragen. Für `codex_cli` ist das richtig: der Provider authentifiziert über die
lokale `codex login`-Session und hat per Definition kein Secret. `claude_cli` ist
ebenfalls `transport="cli"`, trägt aber einen echten Langzeit-Token aus
`claude setup-token`, der als Umgebungsvariable an den Subprozess geht statt als
HTTP-Header. Der Kurzschluss auf den Transport verwarf diesen Token. Weil der
Rückgabewert einmal in die effektive Runtime-Konfiguration gegossen und durch
alle Phasen gereicht wird, zog sich der eine verworfene Wert über den gesamten
Lauf. Der Graph-Build lief mit derselben Verbindung durch, weil er den Key
direkt auflöst und diesen Pfad nicht benutzt.

Die Unterscheidung hängt jetzt am `auth_mode`, nicht am Transport, und liegt als
`LlmProviderRegistry.uses_session_auth` an einer einzigen Stelle. Zwei weitere
Aufrufer trugen dieselbe Verwechslung: Simulationsstart und die Profil-Verbindung
von `/generate-profiles` lösten den Key zwar korrekt auf, sprangen aber mit
derselben Transport-Bedingung am 422-Guard vorbei — ein `claude_cli`-Lauf ohne
hinterlegten Token wäre dort gestartet und erst im Subprozess gescheitert.

Zusätzlich benennt die Fehlermeldung bei fehlendem Key jetzt den Provider und die
Route statt der `.env`-Variablen `LLM_API_KEY`, die für einen aufgelösten
Provider gar nicht die Quelle ist. Der nie gelesene rohe `OpenAI`-Client im
Persona-Generator ist entfallen; er hätte für einen CLI-Provider ohne Base-URL
auf den OpenAI-Default gezeigt.
