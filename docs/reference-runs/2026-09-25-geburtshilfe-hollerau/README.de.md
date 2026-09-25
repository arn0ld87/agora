# Referenzlauf 8: Geburtshilfe Hollerau

**Datum:** 25.09.2026  
**Rolle:** visueller End-to-End-Vorzeigelauf; **kein** Reproduzierbarkeits- oder Trust-Golden-Run.

## Szenario

Der Lauf verwendet ein vollständig fiktives kommunales Szenario zur Zukunft der Geburtshilfe im Landkreis Hollerau. Untersucht wird, welche Risiken bei einer Schließung des Kreißsaals Brenkhausen vor der Entscheidung über einen möglichen Sicherstellungszuschlag sichtbar werden und welche Gruppen diese Risiken tragen.

Der Seed ist absichtlich unbequem: Für Brenkhausen stehen 318 bzw. 341 Geburten mit unterschiedlicher Zählweise im Material, für Kleinwiese und Moorhagen liegen die Wege nach Hollerau-Nord über dem genannten 40-Minuten-Richtwert, und Zuschlag, Haftpflicht, zusätzlicher Rettungswagen sowie Wechselbereitschaft der Hebammen sind offen.

## Laufidentität

| Merkmal | Wert |
|---|---|
| Simulation | `sim_8fd9a6e4bc97` |
| Bericht | `report_e315511c2cb9` |
| Simulationsstand | 24 von 24 Runden abgeschlossen |
| Report-Modus | `explorative` |
| Evidence-Schema | 3 |
| Evidence-Einträge | 46 |
| Evidence-Typen | 14 Seed-Dokument, 12 Agenteninterviews, 8 Agentenaktionen, 8 Relationship-Chains, 4 Graph-Metriken |
| Graph im UI-Capture | 59 Entitäten, 46 Beziehungen, 14 Entitätstypen |

## Warum dieser Lauf als Vorzeigelauf taugt

- Er zeigt die aktuelle Produktoberfläche durchgehend von Graph Build über Simulation und Live-Feed bis zur Berichtansicht.
- Das Szenario erzeugt sichtbar konkurrierende Stakeholder-Positionen statt einer einzigen linearen Antwort.
- Die veröffentlichten Screenshots und das Demo-Video enthalten nur die Agora-Oberfläche; Browser-Chrome, Dock, Menüleiste und sonstige Desktop-Inhalte sind ausgeschlossen.
- Die Reportgrenzen bleiben sichtbar und werden nicht für eine hübschere Demo wegretuschiert.

## Evidenzstatus und bekannte Degradationen

Der exportierte ReportV3 enthält **2 validierte Claims**, **31 Hypothesen** und **6 Data Gaps**. Beide validierten Claims besitzen Simulationsevidenz; einer der beiden stützt sich auf eine beobachtete Agentenaktion.

Fünf Reportabschnitte wurden wegen LLM-Fehlern nicht erzeugt und sind als Data Gaps ausgewiesen: zentrale Risiken, Reibungspunkte/Eskalationspfade, Gegenmaßnahmen, Unsicherheiten/Datenlücken und Handlungsempfehlung. Genau deshalb bleibt Referenzlauf 7 die technische Report-/Trust-Regression.

Persona-Zitate und Agentenaktionen sind **synthetische Modellausgaben**, keine empirische Nutzerforschung und keine Vorhersage menschlichen Verhaltens. Ein gespeicherter `random_seed` macht den Lauf nicht reproduzierbar; „same seed = same run“ gilt ausdrücklich nicht.

## Medien

- [Zusammengesetzter Showcase-Screenshot](../../../media/agora-demo-poster.jpg)
- [Geschnittenes Demo-Video](../../../media/agora-demo.mp4)

Die Medien zeigen ausschließlich Agora-Ansichten dieses Laufs; Browser- und Betriebssystem-Chrome sind entfernt.
