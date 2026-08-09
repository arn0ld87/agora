# Domain Migration Reference Run Implementation Plan

**Goal:** Den realen Agora-Lauf `report_41f7b1bcf1e4` als öffentlichen, kritisch dokumentierten End-to-End-Referenzlauf veröffentlichen und ihn knapp aus README und Dokumentationsindex verlinken.

**Branch:** `docs/reference-run-domain-migration`

## Constraints

- Der Lauf demonstriert End-to-End-Fähigkeiten, keine prädiktive Validität für reales menschliches Verhalten.
- `33` Agenten ist die Betreiberangabe zur erzeugten Population; `total_agents: 24` ist der artefaktbelegte Metrics-Snapshot. Die Differenz bleibt ungeklärt.
- Belegte Snapshot-Metriken: `267` Interaktionen, `3` Cluster, Echo-Chamber-Index `0.4794`, Bridge Agents `[24, 15, 11, 18, 0]`, Clustergrößen `13 / 6 / 5`.
- `sampled_from_total: 473` bei Social-Actions wird nicht mit `total_interactions: 267` gleichgesetzt.
- Persona-/Agentenaussagen sind Simulationsereignisse, keine realen Interviews.
- Laufbeobachtung, Audit-Finding und Remediation werden getrennt benannt.
- PR #1147 wird nur als gemergte Teil-Remediation der Evidence-Identität dargestellt.
- Keine Produktcode-, Report-Engine- oder Simulationsänderung in diesem Slice.

## Artefaktstrategie

Die erste Planfassung sah vollständige Kopien von `report.md` und `evidence.json` im Git-Tree vor. Während der Ausführung wurde dies bewusst angepasst:

- Die vollständigen Originalexporte bleiben unverändert und werden über Größe und SHA-256 gebunden.
- Im Repo liegt ein deterministischer `artifacts/evidence-extract.json`, der ausschließlich die in der Case Study ausgewerteten Evidence-Felder enthält.
- `artifacts/README.md` dokumentiert Provenienz und Prüfsummen der vollständigen Markdown-, JSON-, HTML- und PDF-Exporte.
- Der Extract ist kein neues Agora-Reportformat und ersetzt den vollständigen historischen Export nicht.
- Ein vollständiges Export-Bundle kann später in einem GitHub Release oder Zenodo-Snapshot veröffentlicht werden.

Diese Anpassung vermeidet, einen mehrere hundert Kilobyte großen generierten Reportbestand als zweite Dokumentations-SSoT im Git-Tree zu etablieren, ohne die Nachprüfbarkeit der Case Study zu verschleiern.

## Task 1: Referenzlauf-Struktur und Artefakt-Provenienz

- [x] `docs/reference-runs/README.md` angelegt.
- [x] `docs/reference-runs/2026-08-09-domain-migration/artifacts/evidence-extract.json` angelegt.
- [x] `docs/reference-runs/2026-08-09-domain-migration/artifacts/README.md` mit Größen und SHA-256 der Originalexporte angelegt.
- [x] Evidence-Extract enthält Report-/Simulation-ID, Snapshot-Metriken, Social-Action-Samples, `RELATED_ONLY`, `INSUFFICIENT`, Reviewer-Floor und vollständigen `degradation_log`.

## Task 2: Vollständige Case Study

- [x] `docs/reference-runs/2026-08-09-domain-migration/README.md` angelegt.
- [x] klare Warnung gegen prädiktive/empirische Überinterpretation.
- [x] 33-vs-24-Diskrepanz sichtbar und ohne erfundene Erklärung dokumentiert.
- [x] 267 Interaktionen, 3 Cluster, Echo-Chamber-Index 0.4794, Bridge Agents und Clustergrößen dokumentiert.
- [x] Social-Simulation als Reddit-/Twitter-artige Interaktion dargestellt, nicht als Sammlung isolierter Interviews.
- [x] simulationsgenerierte ungesicherte Betriebsbehauptung als konkretes Beispiel aufgenommen.
- [x] Evidence-Gating anhand `RELATED_ONLY`, `INSUFFICIENT`, Reviewer-Floor und Confidence-Degradation erklärt.
- [x] sichtbarer Abschnitt „Was nicht funktioniert hat oder unklar blieb“.
- [x] Laufbeobachtung, Audit und Remediation getrennt.
- [x] PR #1147 als gemergte Teil-Remediation verlinkt.
- [x] Reproduzierbarkeit ehrlich als `frozen historical reference run` eingeordnet.

## Task 3: Sichtbare Repo-Einstiege

- [x] Haupt-`README.md` nach dem Demo-Bereich um kompakten Referenzlauf-Teaser ergänzt.
- [x] `docs/README.md` um „Referenzläufe und Evaluationen“ ergänzt.
- [x] beide Einstiegspunkte verlinken auf die ausführliche Case Study.

## Task 4: Endprüfung

Vor PR-Erstellung noch ausführen:

- [ ] Branch-Diff gegen `main` prüfen.
- [ ] sicherstellen, dass nur Dokumentation/Referenzartefakte/Spec/Plan geändert wurden.
- [ ] alle relativen Referenzlauf-Links gegen vorhandene Dateien prüfen.
- [ ] Remote-`evidence-extract.json` erneut lesen und zentrale IDs/Metriken verifizieren.
- [ ] Case Study auf unzulässige Übertreibungen prüfen.
- [ ] 33-vs-24-Terminologie in README und Case Study prüfen.
- [ ] PR #1147 erneut als `merged` verifizieren.
- [ ] finalen PR-Diff reviewen.

## Definition of Done

- [x] kurzer Haupt-README-Teaser.
- [x] Dokumentationsindex verlinkt den Lauf.
- [x] vollständige Case Study vorhanden.
- [x] deterministischer Evidence-Extract vorhanden.
- [x] SHA-256-Provenienz der vollständigen historischen Exporte dokumentiert.
- [x] Kritikpunkte stehen im Haupttext und nicht nur in einem Appendix.
- [x] keine Aussage verkauft simulierte Personas als reale Stakeholdermeinungen.
- [ ] finale Branch-/Link-/Inhaltsprüfung abgeschlossen.
- [ ] reviewfähiger Pull Request erstellt.
