# Artefakt-Provenienz – Referenzlauf v2

Diese Datei bindet die öffentliche Case Study an die vollständigen Originalartefakte des Runs `report_06f654800817` / `sim_464a7a8e6310`.

Die vollständigen generierten Dateien werden bewusst nicht als zweite Dokumentations-SSoT in diesem Ordner dupliziert. Stattdessen enthält [`evidence-extract.json`](./evidence-extract.json) einen deterministischen Auszug der in der Case Study verwendeten Metriken, Sampling-Metadaten, Section-Statuswerte und Auditbefunde.

## Originalartefakte

| Artefakt | Größe | SHA-256 |
|---|---:|---|
| `logs.md` | 19,218 Bytes | `aaf3025da8e325d7b7374b5cf552a172f3e7fe1488692948cf4103d29bd0b234` |
| `agora-report-report_06f654800817-evidence.json` | 518,272 Bytes | `07525f0b76cd7d39f69dea09014063212d5299a0d8c51b3729b99528ff764b02` |
| `agora-report-report_06f654800817.html` | 118,649 Bytes | `11976cd3c20bbf796cf3f0ec18f719bfbc929dc62d58df4262cb450b1ff42ff1` |
| `agora-report-report_06f654800817.md` | 385,098 Bytes | `1431672e94ca0007897c0dac86f560e95f6b7cbc6c26ad01497e1648f78bb4f2` |

## Was der Extract enthält

Der öffentliche Extract enthält nur Felder, die für die Case Study relevant sind:

- Report-/Simulation-ID,
- Metrics-Snapshot,
- 8 gesampelte Social-Action-Metadaten aus einem Sampling-Universum von 540 Actions,
- Evidence-Index-Typen,
- Claim-/Hypothesen-/Data-Gap-Zählung pro Section,
- section-spezifische Interviewauswahl aus den Logs,
- die protokollierten Evidence-Gate-Entfernungen,
- klar als `derived_audit_findings` markierte, aus den gelieferten Artefakten berechnete Befunde.

## Wichtige Grenze

`derived_audit_findings` sind **keine zusätzlichen Agora-Evidence-Records**. Sie sind für diese Dokumentation berechnete Prüfergebnisse, zum Beispiel:

- insgesamt `0` validierte Claims im exportierten ReportV3,
- `12` kanonische Evidence-Items,
- davon `8 agent_action` und `4 graph_metric`,
- keine im Evidence Index erkannte kanonische Interview-Evidence,
- leerer `degradation_log`.

Die Case Study interpretiert diese Befunde als Integrationsproblem zwischen Deep Interviews und kanonischer Evidence-Persistenz. Die exakte Root Cause muss im Produktcode reproduziert werden.

## Reproduzierbarkeit

Die SHA-256-Werte erlauben zu prüfen, ob ein später bereitgestelltes vollständiges Export-Bundle exakt zu diesem dokumentierten Run gehört. Dieser Ordner allein ist jedoch kein vollständiges Replay-Bundle und ersetzt keinen zukünftigen RunManifest-/Replay-Vertrag.
