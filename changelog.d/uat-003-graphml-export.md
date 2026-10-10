# UAT-003 — GraphML-Dateien mit Inhalt herunterladen

GraphCanvas und GraphReader verwenden beim GraphML-Export den bereits vom API-Client entpackten Blob direkt. Der erneute Zugriff auf `.data` hatte gültige XML-Antworten durch Nullbyte-Dateien ersetzt. Eine Regression durch die echte Axios-Pipeline prüft beide Downloadwege, XML-Inhalt, Dateinamen und Fehlerantworten.
