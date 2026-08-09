# Referenzlauf: Domainmigration alexle135.de → alex-schneider.dev

> [!IMPORTANT]
> Dieser Referenzlauf demonstriert Agoras **aktuelle End-to-End-Pipeline, Evidence-Gating und bekannte Grenzen** an einem absichtlich schwierigen Szenario. Er validiert **keine** Vorhersage realen menschlichen Verhaltens und ersetzt keine Interviews, Nutzertests oder empirische Stakeholderforschung.

| Feld | Wert |
|---|---|
| Datum | 9. August 2026 |
| Report | `report_37944872ec76` |
| Report-Modus | `balanced` |
| Report-Writer | Gemini 3.6 Flash |
| Simulationsprofile | 30 geladene Agentenprofile |
| Report-Sections | 6 |
| Validierte Claim-Zeilen | 24 |
| Eindeutige Claim-IDs | 17 |
| Hypothesen | 157 |
| Eindeutige Hypothesen-IDs | 157 |
| Data-Gap-Zeilen | 133 |
| Eindeutige Gap-IDs | 41 |
| Red-Team | 6 Findings bei `echo_index=0.690` |

## Warum dieser Lauf jetzt der Referenzlauf ist

Der frühere Domainmigrations-Lauf dokumentierte einen älteren Stand der Evidence-Pipeline. Seitdem wurden unter anderem Interview-Binding, kanonische Evidence-Referenzen, Reviewer-Floor und Claim-Gating überarbeitet.

Der aktuelle Lauf ist deshalb aussagekräftiger: **Gemini 3.6 Flash erzeugt einen gut lesbaren, aber stellenweise sehr selbstsicheren Report. Agora muss anschließend entscheiden, welche Aussagen tatsächlich als Claims bestehen dürfen.**

Das ist für die Evaluation wertvoller als ein Writer, der von sich aus extrem vorsichtig formuliert.

```text
Seed / Szenario
      ↓
Knowledge Graph + Simulation
      ↓
Section-spezifische Agenteninterviews
      ↓
Gemini 3.6 Flash als Report-Writer
      ↓
Claim Extraction
      ↓
Evidence Retrieval + Entailment
      ↓
Reviewer-Floor / Confidence-Degradation
      ↓
Claims + Hypothesen + Data Gaps
      ↓
Red-Team Review
```

## Was Agora als Input bekam

Das Testszenario beschreibt die Migration von `alexle135.de` zu `alex-schneider.dev`. Das Seed-Material enthält absichtlich unterschiedliche epistemische Klassen:

1. dokumentierte Ausgangszustände,
2. Planungsziele und Optionen,
3. synthetische Stakeholder-Aussagen,
4. plausible, aber unbelegte Behauptungen,
5. Widersprüche und fehlende Informationen.

Die Fragestellung verlangt ausdrücklich, dokumentbelegte Aussagen, Hypothesen, unbelegte Behauptungen und Datenlücken auseinanderzuhalten und anschließend genau eine Migrationsstrategie zu empfehlen.

Synthetische Aussagen im Seed sowie Aussagen der simulierten Agenten sind **Simulationsevidenz, keine empirische Nutzerforschung**.

## Ablauf des Reports

Der Planner erkannte den Intent `risk` und erzeugte sechs Sections:

1. Kurzfazit
2. Betroffene Gruppen
3. Zentrale Risiken
4. Reibungspunkte und Eskalationspfade
5. Gegenmaßnahmen
6. Unsicherheiten und Datenlücken

Für mehrere Sections wurden jeweils thematisch relevante Agenten aus den 30 geladenen Profilen ausgewählt und über `interview_agents` vertieft befragt. Die Auswahl variierte je Section. Dadurch beziehen sich Aussagen aus den Interviews auf die jeweilige Teilmenge und nicht automatisch auf die gesamte Simulationspopulation.

## Ergebnis des strukturierten ReportV3

Der exportierte ReportV3 weist aus:

| Status | Zeilen |
|---|---:|
| Validierte Claims | 24 |
| Hypothesen | 157 |
| Data Gaps | 133 |

Die reine Zeilenzahl darf allerdings nicht mit eindeutigen Objekten verwechselt werden. Im Export sind nur **17 eindeutige Claim-IDs** und **41 eindeutige Gap-IDs** vorhanden; die Hypothesen-IDs sind dagegen in diesem Lauf **157/157 eindeutig**.

Das ist ein bewusst dokumentierter Contract-Fehler des aktuellen Stands.

## Was das Evidence-Gating korrekt abgefangen hat

Der Gemini-Writer erzeugte mehrere plausible, aber nicht belegte Details. Ein wichtiger Teil davon wurde korrekt zurückgestuft.

### Erfundenes Infrastrukturdetail bleibt Hypothese

Gemini erfand konkrete Alt-Subdomains:

- `blog.alexle135.de`
- `demo.alexle135.de`

Diese Hosts sind im Seed nicht dokumentiert. Der ReportV3 führt den entsprechenden TLS-Eskalationspfad nicht als validierten Claim, sondern als ungegroundete Hypothese/Data Gap.

### Erfundenes E-Mail-Ziel bleibt Hypothese

Gemini erzeugte die konkrete Adresse `schneider@alex-schneider.dev`, obwohl das Seed keine endgültige neue Mailadresse festlegt. Auch diese Aussage wurde nicht als validierter Claim übernommen.

### Recruiting-Kausalität wird zurückgestuft

Aussagen wie eine systematische Fehlausrichtung im Recruiting-Funnel oder reale Skepsis technischer Entscheider erhielten keine ausreichende bindende Evidence und verblieben als Hypothesen beziehungsweise `RELATED_ONLY`.

### Numerische Overclaims werden entfernt

Der Lauf entfernte numerische Aussagen, wenn Zahl, Bezugsgruppe oder Aussage nicht ausreichend gedeckt waren. Dazu gehören beispielsweise künstliche Schwellenwerte und zu starke 30-/60-/90-Tage-Aussagen.

## Wichtigster aktueller Fehler: Compound Claims umgehen den Gate

Der deutlichste Befund dieses Laufs ist `claim_12`.

Dieser eine „Claim“ enthält sieben komplette Risikopunkte gleichzeitig, unter anderem:

- Identitätswirkung auf SRE-/DevOps-Teamleads,
- E-Mail-/Spam-Kausalität,
- TLS für nicht belegte Alt-Subdomains,
- `.dev`-Wahrnehmung,
- SEO-Risiko,
- Auswirkungen auf Lernende,
- Monitoring.

Besonders problematisch ist die eingebettete Aussage, das Seed-Dokument **belege**, dass `alexle135` für Google praktisch wertlos sei und das SEO-Risiko deshalb niedrig sei.

Dieselbe SEO-Aussage fällt an anderer Stelle korrekt durch das Evidence-Gating und wird nur als `RELATED_ONLY` beziehungsweise Hypothese geführt. Innerhalb des großen Compound Claims wird der gesamte Block jedoch als validierter Claim persistiert.

Damit zeigt der Lauf eine zentrale Grenze:

```text
atomarer problematischer Claim
→ Gate
→ RELATED_ONLY
→ Hypothese ✅

identischer Claim in großem Mehrfach-Block
→ Gesamtblock erhält passende Evidence
→ VALIDATED ❌
```

**Folgerung:** Claim-Atomicity ist ein P0-Thema. Ein Claim darf nur eine eigenständig überprüfbare Proposition enthalten.

## Context-Scope-Loss

Ein zweiter struktureller Fehler betrifft den Kontext von Evidence.

Das Seed enthält ein Banner `alexle135.de wird alex-schneider.dev` im Kontext einer bestimmten Migrationsoption. Der Writer übernimmt dieses Element später als allgemeine beziehungsweise Option-B-Maßnahme. Weil der Text selbst im Seed vorkommt, kann ein einfacher Provenance-Check die Kontextverschiebung nicht erkennen.

Evidence benötigt deshalb nicht nur eine Quelle, sondern auch semantischen Scope, beispielsweise:

```yaml
source_context:
  option_id: C
  object_type: proposed_measure
  section: migration_options
```

Eine korrekte Quelle im falschen Entscheidungskontext ist kein belastbarer Beleg.

## Recommendation benötigt Counter-Evidence

Ähnlich verhält es sich mit Empfehlungen zur GitHub-Umbenennung. Der Report schlägt konkrete GitHub-/Repository-Renames vor und Teile davon gelangen in validierte Claims.

Für Entscheidungsempfehlungen reicht es nicht, nur stützende Evidence zu suchen. Der Binder muss auch widersprechende oder einschränkende Evidence abrufen:

```text
Recommendation Candidate
        ↓
Supporting Evidence
        +
Contradicting Evidence
        ↓
SUPPORTED / CONFLICT / INSUFFICIENT
```

## Claim- und Gap-Identität

Der Export enthält 24 Claim-Zeilen, aber nur 17 eindeutige Claim-IDs. Beispiele für mehrfach vergebene IDs sind `claim_01`, `claim_08`, `claim_10` und `claim_14`.

Bei den Data Gaps ist die Wiederverwendung stärker ausgeprägt: 133 Zeilen teilen sich nur 41 eindeutige `gap_*`-IDs. Die Nummerierung startet offenbar abschnittsweise neu.

Die Hypothesen-IDs sind dagegen in diesem Lauf eindeutig. Das zeigt, dass globale Identität technisch erreichbar ist, aber noch nicht über alle Report-Objekttypen konsistent erzwungen wird.

Erwarteter Contract:

```text
UNIQUE(report_id, claim_id)
UNIQUE(report_id, hypothesis_id)
UNIQUE(report_id, gap_id)
```

## Data Gaps sind noch zu breit definiert

Nicht alles, was keine Evidence erhält, ist eine Datenlücke.

Im Export erscheinen beispielsweise auch:

- Empfehlungen,
- Überschriften,
- narrative Übergänge,
- Einleitungen zu Persona-Zitaten,
- komplette Eskalationsszenarien

als `Data Gap`.

Vor dem Evidence-Binding sollte deshalb zunächst der Satz-/Blocktyp bestimmt werden:

```text
FACT
SIMULATION_OBSERVATION
HYPOTHESIS
RECOMMENDATION
QUESTION
HEADING
TRANSITION
QUOTE
DATA_GAP
```

Nur echte fehlende Informationen sollten als Data Gaps gezählt werden. Die aktuelle Kennzahl `133` ist deshalb als Rohzahl sichtbar, aber noch keine saubere Qualitätsmetrik.

## Strukturierte Extraktion ist noch unvollständig

Einzelne validierte Claims beginnen mitten in Listen oder enthalten mehrere Markdown-Blöcke. Beispiele sind abgeschnittene Listenfragmente wie ein Claim, der mit `B. via Let's Encrypt / ACME)` beginnt.

Das deutet darauf hin, dass Claim Extraction teilweise noch auf Textsegmenten statt auf strukturierten Markdown-/AST-Blöcken arbeitet.

Quotes, Listen, Tabellen und Maßnahmenblöcke sollten vor der Claim-Extraktion atomar strukturiert werden.

## Red-Team Review

Nach Abschluss der Sections lief ein Red-Team-Schritt und meldete:

- **6 Findings**
- `echo_index=0.690`

Die Logs zeigen allerdings, dass der Report unmittelbar vor dem Red-Team-Schritt gespeichert wurde und danach kein weiterer Persist-/Export-Schritt sichtbar ist.

Deshalb bleibt für diesen Referenzlauf offen, ob die sechs Findings den final ausgelieferten ReportV3-Zustand tatsächlich verändern oder nur als nachgelagerte Review-Metadaten existieren.

Das sollte künftig explizit nachvollziehbar sein:

```text
Report Draft
→ Red Team
→ Findings anwenden / Confidence degradieren
→ Final Validation
→ Final Export
```

## Tool-Routing-Beobachtung

Während der letzten Section protokollierte der Lauf mehrfach Fehler wie:

`'DefaultApi' object has no attribute 'insight_forge'`

und entsprechende Varianten für weitere Tools. Die eigentlichen Tool-Aufrufe wurden anschließend dennoch ausgeführt. Section 4 erreichte außerdem das maximale Iterationslimit und wurde zwangsfinalisiert.

Das beeinträchtigte den Abschluss des Runs nicht, zeigt aber unnötige Routing- und Orchestrierungsinstabilität.

## Was dieser Lauf aktuell demonstriert

Aus den eingefrorenen Artefakten lässt sich für diesen Run belastbar ableiten:

- die Report-Pipeline lief über sechs geplante Sections bis zum ReportV3,
- section-spezifische Agenteninterviews wurden erfolgreich ausgeführt,
- der Writer erzeugte mehrere konkrete Halluzinationen und Overclaims,
- ein relevanter Teil davon wurde durch Evidence-Gating und Reviewer-Floor in Hypothesen verschoben,
- numerische Überdehnungen konnten als `INSUFFICIENT` beziehungsweise `CONTRADICTED` entfernt werden,
- Confidence wurde für nicht ausreichend agent-grounded Claims heruntergestuft,
- Hypothesen erhielten reportweit eindeutige IDs,
- der Red-Team-Mechanismus wurde bei erhöhtem Echo-Index aktiviert.

Damit zeigt der Run einen realen systemischen Mehrwert gegenüber einem ungeprüften Single-Prompt-Report: **Der Writer darf plausible Fehler erzeugen, und ein separater Pfad verwirft einen Teil davon maschinenlesbar.**

## Was dieser Lauf ausdrücklich noch nicht beweist

Der Lauf beweist nicht:

- dass ein als `VALIDATED` markierter Claim automatisch fachlich wahr ist,
- dass Simulationsevidenz empirische Stakeholderforschung ersetzt,
- dass die aktuelle Claim-Extraktion atomar genug ist,
- dass Recommendation-Konflikte vollständig erkannt werden,
- dass Source-Status und Optionskontext lückenlos erhalten bleiben,
- dass die Zahl der Data Gaps bereits eine sinnvolle Qualitätsmetrik ist,
- dass Red-Team-Findings den finalen Export nachweisbar verändern,
- dass ein einzelner Run statistische oder prädiktive Validität zeigt.

## Priorisierte Folgearbeit aus diesem Lauf

1. **P0 — Compound Claims atomisieren und pro Proposition binden.**
2. **P0 — globale Eindeutigkeit von Claim- und Gap-IDs erzwingen.**
3. **P0 — Source-Status und Context-Scope als Teil der Evidence-Provenance erhalten.**
4. **P0 — für Recommendations aktiv Counter-Evidence abrufen.**
5. **P1 — Markdown-/Quote-/List-Blöcke strukturell vor Claim Extraction parsen.**
6. **P1 — echte Data-Gap-Typisierung statt `ungedeckt = Gap`.**
7. **P1 — Red-Team-Findings vor dem finalen Export nachweisbar anwenden.**
8. **P2 — Tool-Routing und Max-Iteration-Verhalten stabilisieren.**

## Fazit

Dieser Lauf wird nicht als „Beweis, dass Agora recht hat“ veröffentlicht. Er ist interessanter als das:

> **Gemini 3.6 Flash erzeugt einen überzeugend klingenden Bericht mit mehreren plausiblen Fehlern. Agora fängt einen Teil dieser Fehler bereits systematisch ab — und der Referenzlauf zeigt ebenso offen, an welchen Stellen der aktuelle Evidence-Vertrag noch versagt.**

Genau diese Kombination aus funktionierendem Guardrail und reproduzierbar sichtbaren Schwächen macht den Lauf zu einem geeigneten aktuellen Referenzfall.