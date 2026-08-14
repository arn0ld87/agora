<p align="center">
  <a href="./README.md">English</a> · <strong>Deutsch</strong>
</p>

# Referenzlauf 6 — AURORA-Rollout-Entscheidungsbericht

**Datum:** 14.08.2026  
**Simulation:** `sim_4245ff3d7b23`  
**Report:** `report_3c594fcc7613`  
**Szenario:** fiktiver Städtischer Klinikverbund Falkenbrück / AURORA (`Nexora Triage Assist`)

Dieser Referenzlauf untersucht die Entscheidung, ob ein KI-gestütztes Triage- und Dokumentationssystem gleichzeitig an zwei Klinikstandorten produktiv gehen, zunächst gestaffelt in Falkenbrück-Mitte pilotiert oder vollständig verschoben werden soll.

Der Report wurde bewusst aus **derselben bereits abgeschlossenen Simulation** neu erzeugt, die auch dem vorherigen AURORA-Report zugrunde lag. Damit eignet sich der Lauf als Referenz für Reporter- und Pipeline-Änderungen: Unterschiede in Reportqualität und Laufzeit stammen nicht aus einem anderen stochastischen Simulationsverlauf.

## Was der Lauf zeigt

- sechs Reportabschnitte auf Basis derselben abgeschlossenen Simulation,
- Quellenrecherche über `insight_forge`, `panorama_search` und `quick_search`,
- gezielte `interview_agents`-Aufrufe über den gesamten Report statt erst in späten Abschnitten,
- einen Evidence Inspector für Claims, Hypothesen, Confidence und gebundene Belege,
- konkrete `agent_interview`-Evidence-Cards direkt bei einzelnen Claims,
- nachgelagertes Evidence Gating, das unbelegte Präzision entfernt oder herabstuft,
- deutlich kürzere Reportgenerierung als beim vorherigen Report über dieselbe Simulation.

Die resultierende Empfehlung ist ein **konditionierter, gestaffelter Rollout** ab Falkenbrück-Mitte, bei dem eine Ausweitung an Sicherheits-, Schulungs-, Mitbestimmungs- und Fallback-Bedingungen gekoppelt wird.

## Evidence Inspector

![AURORA-Report mit Sections, Claims und Hypothesen im Evidence Inspector](../../assets/screenshots/reference-runs/2026-08-14-aurora/01-evidence-inspector.webp)

Der Screenshot ist bewusst auf den Inspector zugeschnitten, damit Claim-Text und Metadaten auch in normaler GitHub-README-Breite lesbar bleiben. Der Report wird damit nicht nur als Fließtext präsentiert: Claims und Hypothesen lassen sich zusammen mit den von der Report-Pipeline gebundenen Evidence Records prüfen.

## Agenteninterviews als Evidence

![AURORA-Report mit Agent-Interview-Evidence-Cards](../../assets/screenshots/reference-runs/2026-08-14-aurora/02-agent-interviews.webp)

Die zweite Ansicht fokussiert den ausgewählten Claim und die zugehörigen `agent_interview`-Records. Genau hier unterscheidet sich der Workflow von einer reinen Dokument-RAG-Zusammenfassung: simulierte Stakeholder werden während der Reportgenerierung erneut gezielt befragt und ihre Antworten sind als Evidence sichtbar.

## Warum Referenzlauf und keine Showcase-Demo

Der Lauf wird gerade deshalb dokumentiert, weil er sowohl Fortschritte als auch noch offene Trust-Grenzen sichtbar macht.

Bekannte Grenzen im Artefakt sind unter anderem:

- ein dokumentierter Seed-Fakt zu **38 Fällen mit abweichender Dringlichkeitseinstufung** wird in einzelnen Abschnitten weiterhin so behandelt, als fehle der passende Zahlenbeleg,
- einige simulierte Interviewzitate tragen noch den generischen Anker `seed_doc:seed_aurora#chunk:0` statt eines präzisen Interview-Records,
- stark passende `SUPPORTED` Evidence kann weiterhin als `low` Confidence erscheinen,
- das ReportV3-Artefakt kann die Vertragsvalidierung verfehlen, während der Gesamtauftrag trotzdem den Zustand `completed` erreicht,
- vorhandene Simulationsnetzwerk-Metriken wie Cluster- und Bridge-Strukturen werden im finalen Report noch zu wenig genutzt.

Damit ist Referenzlauf 6 eine **beobachtbare Reporter-Referenz und ein Regressionstestfall**, aber **kein aus einem frischen Checkout vollständig reproduzierbares Replay-Fixture**. Im Repository liegen derzeit nicht der vollständige AURORA-Simulationssnapshot, sämtliche Reportartefakte, die Modellantwort-Aufzeichnung und alle Aufrufparameter, die für eine exakte Reproduktion dieses konkreten Laufs erforderlich wären.

## Empfohlene Regressionstests

Wenn die ursprünglichen AURORA-Laufartefakte verfügbar sind, sollten spätere Änderungen der Report-Pipeline mindestens prüfen:

1. Der Seed-Fakt zu den `38 Fällen` wird überall als gestützte Evidence gebunden, sofern der Claim nicht über die Quelle hinausgeht.
2. Simulierte Persona-Zitate verweisen auf konkrete `agent_interview`-Evidence statt auf einen generischen Seed-Anker.
3. `SUPPORTED` Quellenfakten werden nicht automatisch als `low` Confidence ausgegeben.
4. Ein fehlgeschlagener kanonischer Report-Contract kann keinen irreführenden vollständig abgeschlossenen Zustand erzeugen.
5. Prompt-Anforderungen zu Frühwarnindikatoren, Stop-/Expand-Kriterien und Reaktionsketten bleiben im finalen Report sichtbar.
