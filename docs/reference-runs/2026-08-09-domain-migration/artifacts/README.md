# Artefakte des aktuellen Referenzlaufs

Dieser Ordner gehört zum aktuellen Domainmigration-Referenzlauf `report_37944872ec76` vom 9. August 2026.

Der frühere historische Evidence-Extract zu `report_41f7b1bcf1e4` wurde entfernt, damit im Referenzpfad nicht zwei unterschiedliche Runs vermischt werden.

## Maschinenlesbare Zusammenfassung

[`run-summary.json`](./run-summary.json) enthält die für die öffentliche Case Study verwendeten, eng begrenzten Laufdaten:

- Report-ID und Writer-Modell,
- Anzahl der Report-Sections und geladenen Persona-Profile,
- Claim-/Hypothesen-/Data-Gap-Zahlen,
- Anzahl eindeutiger IDs,
- Red-Team-Befunde und Echo-Index,
- bestätigte positive Guardrail-Beobachtungen,
- bekannte Fehlerklassen und priorisierte Folgearbeit.

Die Datei ist **kein vollständiger Evidence-Export** und kein Ersatz für ReportV3 oder Rohlogs. Sie dient nur dazu, die in der Referenzlauf-README genannten Kennzahlen und Befunde maschinenlesbar zusammenzufassen.

## Warum der vollständige Report und die Logs hier nicht dupliziert werden

Der Referenzlauf soll reviewbar bleiben, ohne große generierte Artefakte als zweite Dokumentations-SSoT in den Git-Tree zu kopieren. Die öffentliche README dokumentiert deshalb die überprüften Befunde und die kleine strukturierte Zusammenfassung.

Für einen späteren reproduzierbaren Benchmark sollten vollständige Run-Bundles mit Input-Hashes, Modell-/Provider-Routen, Prompt-/Schema-Versionen, Seeds, Evidence-Export und Logs über einen versionierten Release- oder Zenodo-Snapshot veröffentlicht werden.
