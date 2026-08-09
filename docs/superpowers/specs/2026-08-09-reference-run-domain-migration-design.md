# Design: Reference Run „Domainmigration alexle135.de → alex-schneider.dev“

Stand: 2026-08-09

## Ziel

Der reale Agora-Lauf `report_41f7b1bcf1e4` wird als öffentlicher Referenzlauf im Repository dokumentiert. Er soll nachvollziehbar zeigen, dass die Agora-Pipeline end-to-end arbeitet, ohne die Simulation als empirischen Beweis für reales menschliches Verhalten zu verkaufen.

Der Referenzlauf soll gleichzeitig offen dokumentieren, welche Schwächen im Lauf sichtbar wurden, welche Aussagen nur simulationsbasiert sind und welche technischen Findings daraus bereits in die Remediation eingeflossen sind.

## Kommunikationsprinzip

Die Dokumentation verwendet bewusst nicht die Formulierung „Proof that Agora predicts people“.

Die zentrale Aussage lautet sinngemäß:

> This reference run demonstrates Agora's current end-to-end capabilities, evidence-gating behavior and known limitations. It does not establish predictive validity for real-world human behavior.

Damit bleibt die Darstellung konsistent mit der bestehenden README-Grenze, dass Personas simuliert sind und Simulationsergebnisse keine Interviews, Nutzertests oder empirische Forschung ersetzen.

## Zielstruktur im Repository

```text
docs/
└── reference-runs/
    ├── README.md
    └── 2026-08-09-domain-migration/
        ├── README.md
        └── artifacts/
            ├── report.md
            └── evidence.json
```

Zusätzlich werden zwei bestehende Einstiegspunkte erweitert:

- `README.md`: kompakter Teaser direkt nach dem Demo-Bereich.
- `docs/README.md`: neuer Abschnitt „Referenzläufe und Evaluationen“.

## README-Teaser

Die Haupt-README erhält bewusst nur einen kurzen Abschnitt von ungefähr 20 bis 30 Zeilen.

Er enthält:

1. Titel des Referenzlaufs.
2. Szenario: Domainmigration `alexle135.de` → `alex-schneider.dev`.
3. Pipeline: Dokumente → Knowledge Graph → Personas → Social Simulation → Evidence Gating → Report.
4. wenige belastbare Laufmetriken aus dem exportierten Evidence-Snapshot.
5. Hinweis auf die soziale Reddit-/Twitter-Simulation.
6. klare Einschränkung: kein Nachweis prädiktiver Validität.
7. Link auf die vollständige Case Study.

Nicht in die Haupt-README gehören:

- der vollständige 60-Seiten-Report,
- lange Persona-Zitate,
- sämtliche Hypothesenlisten,
- vollständige Audit- oder Remediation-Details,
- Roh-JSON.

## Vollständige Case Study

Die zentrale Datei `docs/reference-runs/2026-08-09-domain-migration/README.md` wird als technische Case Study aufgebaut.

### 1. Why this run exists

Erklärt, warum dieser Lauf als Referenzfall geeignet ist:

- reale, aber überschaubare Entscheidung,
- mehrere Stakeholder-Perspektiven,
- technische und kommunikative Risiken,
- absichtlich widersprüchliche Seed-Aussagen,
- klare Evidenzlücken,
- geeignet zum Testen von Social Simulation und Evidence Gating.

### 2. Evaluation scenario

Kurze Beschreibung der Migration von `alexle135.de` zu `alex-schneider.dev`.

Die Case Study unterscheidet zwischen:

- realem Ausgangsbestand,
- Planungsannahmen,
- synthetischen Stakeholder-Aussagen,
- bewusst eingebauten Widersprüchen.

### 3. What was given to Agora

Dokumentiert die Eingabearten und die Fragestellung, ohne jede Zeile des Seed-Dokuments zu kopieren.

Die Case Study muss ausdrücklich erwähnen, dass synthetische Stakeholder-Aussagen Teil des Inputs waren und daher nicht als reale Nutzerforschung gelten.

### 4. Simulation setup

Dokumentiert soweit aus den Artefakten eindeutig rekonstruierbar:

- Simulation-ID `sim_1d96603073ae`,
- Report-ID `report_41f7b1bcf1e4`,
- Social-Simulation auf Reddit-/Twitter-artigen Umgebungen,
- Anzahl der Interaktionen,
- aktive Agenten im Metrics-Snapshot,
- Cluster und Bridge Agents,
- vorhandene Metriken.

Die bekannte Diskrepanz zwischen den laut Run erzeugten 33 Agenten und `total_agents: 24` im Metrics-Snapshot wird nicht erklärt oder glattgebügelt, solange die Ursache nicht aus Artefakten oder Produktcode eindeutig hervorgeht.

Sie wird als bekannte Accounting-/Instrumentation-Lücke dokumentiert.

### 5. What happened in the social simulation

Zeigt ausgewählte Beispiele für:

- Posts,
- Antworten,
- Likes/Follows, soweit im Artefakt vorhanden,
- Übernahme und Widerspruch von Argumenten,
- entstehende Narrative.

Der Schwerpunkt liegt nicht auf einzelnen Persona-Zitaten, sondern auf der sozialen Dynamik.

### 6. Graph and interaction metrics

Tabellarische Darstellung der sicher belegten Werte aus dem Evidence-Export, unter anderem:

- `total_agents: 24` im Metrics-Snapshot,
- `total_interactions: 267`,
- `cluster_count: 3`,
- `echo_chamber_index: 0.4794`,
- Bridge Agents `[24, 15, 11, 18, 0]`,
- Clustergrößen 13, 6 und 5.

Jeder Wert wird ausdrücklich als Metrik dieses konkreten Snapshots bezeichnet.

### 7. Report outcome

Fasst den Report zusammen:

- starke Tendenz zur kontrollierten 90-Tage-Migration,
- Identitätsinkonsistenz als wichtiges Risiko,
- Redirect-/SEO-/E-Mail-Risiken,
- mögliche Fehlwahrnehmung der `.dev`-Positionierung.

Die Case Study übernimmt keine simulationsbasierten Aussagen als empirische Tatsachen.

### 8. Evidence-gating behaviour

Dies ist ein Kernabschnitt.

Gezeigt werden soll:

- dass simulierte Aussagen nicht automatisch als reale Fakten gelten,
- dass unbelegte Aussagen als Hypothesen oder Datenlücken erscheinen,
- dass `RELATED_ONLY` nicht als Beleg zählt,
- dass Confidence heruntergestuft werden kann,
- dass numerische Aussagen bei unzureichender Evidenz entfernt oder abgewertet werden.

Dieser Abschnitt ist wichtiger als Marketingaussagen über die Qualität des Reports.

### 9. What worked

Nur beobachtbare Fähigkeiten dieses Laufs nennen:

- vollständiger End-to-End-Lauf,
- Social-Agent-Aktivität,
- Graphmetriken,
- Reportgenerierung,
- Hypothesen-/Gap-Kennzeichnung,
- Evidence-Entailment und Confidence-Degradation,
- mehrere Exportformate.

Keine Aussage wie „Agora sagt reale Stakeholder korrekt voraus“.

### 10. What failed or remains unclear

Mindestens folgende Punkte aufnehmen:

1. Population Accounting: 33 erzeugte Agenten laut Laufkontext vs. 24 im Metrics-Snapshot.
2. Reportdarstellung reduziert die breite Social Simulation teilweise auf wenige vertiefend zitierte Personas.
3. Begriffe wie „Konsens“ sind stellenweise stärker formuliert als die gebundene Evidence erlaubt.
4. Social-Graph-Metriken werden im finalen Bericht noch nicht ausreichend genutzt.
5. Legacy-Evidence-Identität war zum Zeitpunkt des Laufs nicht kanonisch genug.
6. Mehrere Claims/Hypothesen zeigen `no_evidence_bound`, `RELATED_ONLY` oder Reviewer-Floor-Probleme.
7. Reproduzierbarkeit des historischen Laufs ist noch nicht vollständig durch einen RunManifest-/Replay-Vertrag abgesichert.

### 11. Findings discovered through this run

Die Case Study darf auf technische Findings verweisen, sofern klar ist, ob sie aus diesem Lauf, einem parallelen Audit oder einer anschließenden Analyse stammen.

Wichtig ist die Trennung:

- Laufbeobachtung,
- Audit-Finding,
- daraus abgeleitete Remediation.

### 12. Remediation triggered afterwards

Dokumentiert den Bezug zum Audit-/Remediation-Plan.

Insbesondere:

- Problem der freien/duplizierbaren Evidence-Referenzen,
- Einführung kanonischer `evidence_id`-Werte,
- Trennung von Evidence-Records und Claim-Bindings,
- Cross-Reference-Validierung,
- Legacy-Unresolved-Verhalten,
- PR #1147 als bereits gemergte Remediation.

Nicht behaupten, dass damit sämtliche im Referenzlauf sichtbaren Schwächen behoben sind.

### 13. What this run demonstrates

Zulässige Schlussfolgerungen:

- Agora kann einen realen Dokument-/Entscheidungsfall end-to-end verarbeiten.
- Agenten können in einer sozialen Simulationsumgebung interagieren.
- Agora kann Interaktions- und Graphmetriken erzeugen.
- Der Report kann Konflikte, Risiken, Hypothesen und Datenlücken strukturieren.
- Evidence-Gating kann ungeeignete Evidenz erkennen und Claims abwerten.
- Ein realer Lauf kann konkrete Produktmängel sichtbar machen und Remediation auslösen.

### 14. What this run does NOT demonstrate

Explizit ausschließen:

- keine Validierung realen menschlichen Verhaltens,
- keine statistische Vorhersagegüte,
- keine Repräsentativität der Agentenpopulation,
- kein Nachweis, dass Recruiter `.dev` tatsächlich bevorzugen,
- kein Nachweis realer SEO-Auswirkungen,
- keine allgemeingültige Qualität aller Agora-Runs,
- keine vollständige Reproduzierbarkeit des historischen Laufs.

### 15. Reproducibility status

Der historische Run wird als eingefrorener Referenzlauf dokumentiert, nicht als vollständig reproduzierbarer Benchmark.

Die Case Study nennt:

- vorhandene IDs und Artefakte,
- bekannte fehlende RunManifest-/Replay-Daten,
- geplante Reproduzierbarkeitsarbeit aus der Roadmap/Remediation.

Wenn später ein vollständig reproduzierbarer Replay-Run existiert, wird dieser als separater Referenzlauf ergänzt, statt die Historie umzuschreiben.

### 16. Raw artifacts

Verlinkung auf die eingefrorenen Artefakte.

Die Artefakte werden nicht redaktionell verändert, außer wenn aus Sicherheits-/Datenschutzgründen eine klar dokumentierte Redaction nötig wäre.

## Artefakte

Für den Referenzlauf werden zunächst nur textbasierte, diffbare Artefakte versioniert:

- `report.md`
- `evidence.json`

Der HTML- und PDF-Export bleiben als lokale/Release-Artefakte optional. Sie müssen nicht zwingend im Git-Repository liegen, weil sie groß sind und inhaltlich den Markdown-/JSON-Quellen entsprechen.

Falls später ein Release-Bundle oder Zenodo-Artefakt angelegt wird, können PDF und HTML dort eingefroren werden.

## Sprache

Die Haupt-README bleibt in ihrer bestehenden deutschen Sprache.

Die Case Study wird ebenfalls auf Deutsch geschrieben, technische Schlüsselbegriffe wie `Evidence Gating`, `Reference Run`, `Simulation Snapshot`, `Claim`, `Hypothesis` und `Data Gap` dürfen dort verwendet werden, wenn sie dem bestehenden Projektvokabular entsprechen.

## Umgang mit Kritik

Kritikpunkte werden nicht in einen versteckten Appendix verschoben.

Die Case Study erhält einen sichtbaren Abschnitt „Was nicht funktioniert hat oder unklar blieb“ vor der Schlussfolgerung.

Ziel ist nicht, den Lauf makellos erscheinen zu lassen, sondern nachvollziehbar zu zeigen:

1. was tatsächlich funktioniert hat,
2. wo Agora selbst Grenzen erkannt hat,
3. wo der Lauf Produktmängel offengelegt hat,
4. welche davon bereits behoben wurden,
5. welche weiterhin offen sind.

## Verlinkung aus `docs/README.md`

Neuer Abschnitt:

```markdown
## Referenzläufe und Evaluationen

- [Domainmigration alexle135.de → alex-schneider.dev](./reference-runs/2026-08-09-domain-migration/README.md) — realer End-to-End-Lauf mit Social Simulation, Evidence Gating, bekannten Grenzen und Remediation-Folgen.
```

## Qualitätsanforderungen

Vor Merge muss geprüft werden:

- alle genannten Zahlen gegen das Evidence-JSON,
- alle Reportaussagen gegen `report.md`,
- Audit-/Remediation-Aussagen gegen den Remediation-Plan und gemergte PRs,
- keine Aussage über 33 vs. 24 Agenten ohne belegte Erklärung,
- keine Persona-Aussage wird als reale Stakeholdermeinung formuliert,
- README-Teaser bleibt kurz,
- Links innerhalb des Repos funktionieren,
- Rohartefakte bleiben unverändert,
- keine Secrets oder privaten personenbezogenen Daten werden neu veröffentlicht.

## Nicht-Ziele

Dieser Slice umfasst nicht:

- Änderung der Report-Engine,
- Änderung der Simulation,
- neue Graphvisualisierung,
- Reparatur der 33/24-Agenten-Diskrepanz,
- Re-Run der Simulation,
- neuen Benchmark-Framework-Code,
- wissenschaftliche Validierungsstudie,
- Änderungen an Evidence-Gating-Logik.

Diese Punkte können aus der Case Study als Folgearbeit verlinkt werden, gehören aber nicht in denselben Dokumentations-PR.

## Definition of Done

Der Dokumentations-PR ist fertig, wenn:

1. die Haupt-README einen kurzen Referenzlauf-Teaser enthält,
2. `docs/README.md` den Referenzlauf aufführt,
3. die vollständige Case Study vorhanden ist,
4. `report.md` und `evidence.json` eingefroren im Referenzlauf liegen,
5. alle harten Metriken belegt sind,
6. Einschränkungen und Kritik sichtbar dokumentiert sind,
7. PR #1147 und relevante offene Remediation-Arbeit korrekt verlinkt sind,
8. keine Aussage den Referenzlauf als empirischen Beweis für menschliches Verhalten darstellt.
