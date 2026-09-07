## Fixed

- **Report Agent**: Sektions-Persistenz ist jetzt atomar und prüft beide Artefakte. Zuvor wurde `write_section_markdown` nicht-atomar ausgeführt, was bei Crashes zwischen Evidence und Markdown zu Orphan-Dateien führte (nur Markdown ohne Evidence). `_restore_persisted_section` überprüft jetzt, dass BEIDE Artefakte vorhanden sind, bevor ein Abschnitt als persistiert restauriert wird — fehlt die Evidence, wird die Sektion neu generiert. `write_section_markdown` nutzt jetzt das gleiche atomare Muster wie `write_json_atomic` (tmp-Datei + `os.replace`).
