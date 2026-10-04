# Review-Regeln für Agora

Diese Datei ist Kontext für den Review-Bot. Sie ergänzt die strukturierten Regeln in `config.json` um das, was sich nur im Zusammenhang erklären lässt.

## Was Agora ist und was nicht

Agora simuliert Reaktionen von Stakeholdern auf ein Vorhaben. Personas und Simulationen sind synthetische Modellausgaben. Agora sagt kein menschliches Verhalten vorher. Code, Prompts und Texte, die das Gegenteil nahelegen, sind ein Befund. Dasselbe gilt für jede Aussage, ein gespeicherter Seed mache einen Lauf reproduzierbar.

## Begriffe

- **Lauf**: das ganze Vorhaben von der Quelle bis zum Bericht.
- **Job**: ein einzelner Schritt eines Laufs in der `RunRegistry`. Im Code heißt er `run_id` und `run_type`.
- **Bericht**: das lesbare Ergebnis mit eigenem Status. `INCOMPLETE` ist eine sichtbare Degradation, kein anderer Name für `COMPLETED`.
- **Personasatz**: die synthetischen Personas eines Laufs.
- **Claim, Hypothese, Data Gap**: ein Claim ist eine berichtete Aussage mit Beleg. Eine Hypothese ist plausibel, aber nicht ausreichend belegt. Ein Data Gap heißt, die Information fehlt in den Quellen.

Status von Job, Simulation und Bericht beschreiben verschiedene Ebenen. Code, der aus einem dieser Felder auf die ganze Pipeline schließt, ist verdächtig.

## Wo in diesem Repo die Fehler liegen

Die teuren Fehler der letzten Wochen lagen fast alle zwischen zwei Dateien. Prüfe bei jeder Änderung die Gegenseite:

- **Vertrag gegen Erzeuger.** Ein Modul liefert einen Wert, den der Pydantic-Vertrag nicht kennt. Beispiel: Der Confidence-Rechner vergab ein Label, das im Enum `ConfidenceLabel` fehlt; die Vertragsprüfung schlug fehl und der Claim wurde stillschweigend herabgestuft.
- **Elternprozess gegen Subprozess.** Die Simulation läuft als eigener Prozess unter `backend/scripts/`. Er sieht nur die Umgebungsvariablen aus `SAFE_ENV_KEYS`. Eine neue Einstellung, die dort fehlt, wirkt lokal und im Docker-Betrieb nicht.
- **Backend-Vertrag gegen Frontend-Spiegel.** Ein neues Feld im Vertrag braucht das regenerierte Schema und den Zod-Spiegel.
- **Datei gegen Registry.** Derselbe Zustand steht in einer Artefakt-Datei und in der `RunRegistry`. Wird nur eine Seite geschrieben, zeigt die Oberfläche etwas anderes als der Lauf.
- **Budget.** Text-, Tool-, Vision- und Interview-Aufrufe laufen durch das Budget-Ledger. Ein neuer Aufrufpfad am Ledger vorbei ist ein Befund.

## Nebenläufigkeit

Der Webprozess läuft unter Gunicorn mit genau einem Worker und gevent. Die Simulation nutzt asyncio mit begrenzter Parallelität je Plattform. Achte auf geteilten Zustand ohne Schutz, auf blockierende Aufrufe im Eventloop und auf Schleifen, die bei Fehlern ohne Pause wiederholen.

## Was kein Befund ist

- Formatierung, Zeilenlänge, Importreihenfolge, fehlende Typannotationen: Das prüfen ruff und mypy.
- Deutsche Bezeichner in Kommentaren und Logmeldungen: Das ist gewollt.
- ASCII-Umschreibungen von Umlauten in Code-Kommentaren unter `backend/`.
- `apt` oder `apt-get` in Skripten und Dockerfiles.
- Fehlende Folge-Issues: Befunde werden im selben PR behoben, nicht ausgelagert.
- Testdaten mit erfundenen Schlüsseln, wenn sie zur Laufzeit zusammengesetzt werden.

## Form der Kommentare

Ein Kommentar je Fehlverhalten. Nenne die Zeile, was passiert, unter welcher Bedingung, und was der Code stattdessen tun müsste. Wenn du unsicher bist, ob etwas ein Fehler ist, schreibe, was du geprüft hast und was offen blieb.
