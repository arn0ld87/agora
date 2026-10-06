# Entwürfe zum Frontend-Umbau (Etappe 0)

Prototypen aus Claude Design zum Bauplan [`docs/plans/active/frontend-umbau.md`](../../plans/active/frontend-umbau.md), Epic #1790. Beide Durchgänge sind vom Maintainer am 06.10.2026 abgenommen; die Abweichungen vom Auftrag stehen in Abschnitt 11 des Bauplans.

Die Dateien sind Vorlage, kein Produktivcode. Maße, Farben und Layoutregeln stehen im Quelltext und werden in Vue nachgebaut; die innere Struktur der Prototypen wird nicht übernommen.

## Dateien

| Datei | Inhalt |
|---|---|
| `Agora Durchgang 1.dc.html` | Übersichtsseite Durchgang 1 |
| `Agora Durchgang 2.dc.html` | Übersichtsseite Durchgang 2 |
| `AgoraApp.dc.html` | Hülle und Kernstrecke; die Ansicht wird über die Eigenschaft `screen` gewählt |
| `AgoraAppD1.dc.html` | Stand von Durchgang 1, unverändert |
| `AgoraBausteine.dc.html` | Bausteinblatt mit Tokens und Komponenten |
| `AgoraGraph.dc.html` | Graph ansehen und bearbeiten |
| `AgoraPersonas.dc.html` | Personasätze und Persona-Editor |
| `AgoraSim.dc.html` | Simulation als Feed und Threads |
| `AgoraBericht.dc.html` | Bericht als Lesedokument mit Belegspalte |
| `AgoraInterviews.dc.html` | Interviews |
| `AgoraEinstellungen.dc.html` | Einstellungsfenster |
| `AgoraAktivitaet.dc.html` | Aktivität und Job-Details |
| `AgoraLog.dc.html` | Backend-Log |

## Nicht enthalten

Die Laufzeitdatei `support.js` von Claude Design liegt bewusst nicht im Repo, ihre Lizenz ist ungeklärt. Ohne sie lassen sich die Prototypen nicht im Browser öffnen. Wer sie ansehen will, legt `support.js` aus dem Handoff-Archiv lokal daneben, ohne sie zu committen.
