### Fixed

- Betreiber-Token im Browser eingeben: Ohne JWT (Modus `hybrid`/`legacy` mit gesetztem `AGORA_AUTH_TOKEN`) zeigt die Anmeldeseite ein Feld „Zugangstoken“ statt E-Mail/Passwort. Das Token wird per geschützter Anfrage geprüft und erst dann gespeichert; eine API-Antwort `401 auth_required` leitet zur Anmeldung. Bisher ging das nur per DevTools, damit war Safari unbenutzbar.
