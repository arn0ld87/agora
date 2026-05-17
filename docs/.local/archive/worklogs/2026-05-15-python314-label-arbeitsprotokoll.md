# Arbeitsprotokoll: Python 3.14-dev PR Label Check

## Ziel
Einführung eines label-basierten CI-Checks für Python 3.14-dev in Pull Requests, um riskante Backend-Änderungen gezielt prüfen zu können, ohne die Standard-PR-Laufzeit zu erhöhen.

## Befund
- `main` und `workflow_dispatch` testen bereits Python 3.11 und 3.14-dev.
- Pull Requests testen standardmäßig nur Python 3.11.
- Das CI-Budget soll geschont werden, daher ist eine selektive Zuschaltung von 3.14-dev sinnvoll.

## Geänderte Dateien
- `.github/workflows/ci.yml`: Trigger erweitert um `labeled`/`unlabeled`; Job-Filter für Label-Events hinzugefügt; Matrix-Logik angepasst.
- `README.md`: Hinweis auf den optionalen 3.14-Check unter CI-Hardening.
- `CONTRIBUTING.md`: Erklärung des `needs-python314` Labels.
- `CLAUDE.md`: PR-Workflow ergänzt.

## Akzeptanz-Checks
- [x] PR ohne Label: Fährt nur Python 3.11 (Matrix-Logik verifiziert).
- [x] PR mit `needs-python314`: Fährt 3.11 + 3.14-dev (Matrix-Logik verifiziert).
- [x] `main`/`workflow_dispatch`: Fährt weiterhin 3.11 + 3.14-dev.
- [x] YAML-Validität: `yaml.safe_load` erfolgreich.
- [x] Label-Filter: Andere Labels lösen keinen unnötigen Run aus.

## Folgen
- Entwickler können bei riskanten Backend-Änderungen proaktiv den 3.14-Check anfordern.
- Transparenz über den 3.14-Status im PR-Feedback.
