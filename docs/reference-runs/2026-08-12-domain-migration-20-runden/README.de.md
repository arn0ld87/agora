# Referenzlauf 5: Domainmigration, 20 Runden, Trust-Audit nach dem Hardening

*[English](./README.md) · Deutsch*

> [!IMPORTANT]
> Dieser Lauf dokumentiert das Verhalten von Agora in einer simulierten Multi-Agenten-Umgebung. Er ist **kein** Nachweis dafür, dass die simulierten Personas reale Menschen repräsentieren, die Empfehlung richtig ist oder die Simulation menschliches Verhalten vorhersagt.

## Warum dies der aktuelle Referenzlauf ist

Dieser Lauf verschiebt die Referenzfrage eine Ebene tiefer als [Referenzlauf 4](../2026-08-11-ki-lernassistent-20-runden/README.de.md).

Referenzlauf 4 zeigte erstmals Evidence Binding in brauchbarer Größenordnung: 39 validierte Claims, nachdem fünf Vorgängerberichte nur null oder einen Claim binden konnten. Seine dominanten Fehler waren noch überwiegend mechanisch, darunter erfundene Provenance-Anker, eine Confidence-Metrik mit nur einem Wert, inkonsistentes Entailment und Nicht-Stakeholder als Personas.

Der Domainmigration-Lauf vom 12.08.2026 ist für die heutige Trust-Architektur aussagekräftiger, weil die Binding-Pipeline weit genug funktioniert, um eine schwierigere Fehlerklasse freizulegen: **Agora kann eine Aussage an das richtige Quellfragment binden und trotzdem den epistemischen Status dieses Fragments verlieren.** Ein Satz, den das Seed-Dokument ausdrücklich als unbelegt kennzeichnet, kann dadurch als validierter Weltfakt erscheinen, nur weil der Satz in der Quelle vorkommt.

Das ist ein reiferer Fehler als „keine Evidence gebunden“, aber auch ein gefährlicherer: Die Ausgabe wirkt auditierbar, obwohl die Audit-Semantik noch unvollständig ist.

## Run-Identität

| Feld | Wert |
|---|---|
| Report-ID | `report_fb5dfaf69ffa` |
| Generiert | `2026-08-12T13:57:13.249205+00:00` |
| Szenario | Migration `alexle135.de` → `alex-schneider.dev` |
| Report-Modus | `balanced` |
| Runden | **20 / 20**, Simulation beim Start der Reportgenerierung bereits beendet |
| Report-Modell | im gelieferten Markdown-Artefakt nicht exportiert |
| Simulations-ID | im gelieferten Markdown-Artefakt nicht exportiert |
| Graph-ID | im gelieferten Markdown-Artefakt nicht exportiert |

Fehlende Modell-/Run-IDs werden als fehlende Metadaten dokumentiert und nicht aus benachbarten Logs rekonstruiert.

## Report-Snapshot

| Metrik | Wert |
|---|---:|
| validierte Claim-Zeilen | **46** |
| eindeutige gerenderte Claim-IDs | **22** |
| Hypothesen | **141** |
| Data Gaps | **133** |
| nachträgliche Abstufungen | **0** |
| Evidence-Index-Einträge | **70** |
| Claim-Confidence | 45 `low`, 1 `medium` |
| gerenderter Confidence-Scope | 46 × `Simulationskonsens` |
| gerenderte Claim-Basis | 46 × `persona` |
| Interaktionen gesamt | **109** |
| Cluster | **3** |
| Echo-Chamber-Index | **0.5963** |

Der Evidence Index besteht aus 33 simulierten Agentenzitaten, 16 Seed-Dokument-Einträgen, 13 Graph-Relationen/-Metriken und 8 simulierten Agentenaktionen.

Noch aufschlussreicher ist die tatsächliche Evidence der 46 validierten Claim-Zeilen: **38 sind ausschließlich Seed-gestützt**, 6 ausschließlich durch Agentenzitate, 1 durch Seed plus Zitat und 1 ausschließlich durch eine Agentenaktion. Das widerspricht der Darstellung aller validierten Claims als `Simulationskonsens` mit Basis `persona`.

## Was in diesem Lauf funktioniert

- Alle **20 von 20 Runden** waren vor der Reportgenerierung abgeschlossen.
- Evidence Binding arbeitet in brauchbarer Größenordnung statt bei null oder einem gebundenen Claim stehenzubleiben.
- Kanonische Evidence-Klassen erreichen den Report: Seed-Dokument, simuliertes Zitat, simulierte Aktion und Graph-Relation.
- Unbelegte numerische Zielwerte werden in insufficient/unsupported-Zustände geleitet, statt still zu Fakten zu werden.
- Die starke Aussage, Option B sei die „einzig tragfähige“ Strategie, wird nicht als belegter Fakt akzeptiert.
- **141 Hypothesen** und **133 Data Gaps** bleiben sichtbar, statt in validierte Claims hineinzurutschen.

## Kritischer Befund 1: Vorkommen in der Quelle wird mit Wahrheit verwechselt

Der adversariale Seed enthält absichtlich die Aussage, die alte Domain sei für Google „praktisch wertlos“, **und klassifiziert diese Aussage ausdrücklich als unbelegt**.

Der Report validiert trotzdem einen Claim, der die Aussage als dokumentbelegt darstellt, und verwendet genau das Seed-Fragment mit der unbelegten Behauptung als Evidence. An anderer Stelle beschreibt Agora dieselbe Aussage korrekt als empirisch nicht gestütztes Postulat.

Der Report kann damit gleichzeitig ausdrücken:

1. „Das Dokument belegt X“, und
2. „Das Dokument behauptet X nur unbelegt“.

Damit ist der fehlende Contract sauber isoliert: Provenance erfasst **woher Text stammt**, aber noch nicht zuverlässig **welchen epistemischen Status die Quelle diesem Text zuweist**.

Ein Seed-Corpus-Evidence-Item benötigt daher einen Assertion-Status wie `documented_fact`, `internal_claim`, `hypothesis`, `synthetic_statement`, `unverified_data`, `contradiction` oder `unknown`. `seed_corpus + unverified_claim` darf den Meta-Claim **„die Quelle sagt X“** stützen, aber nicht allein den Welt-Claim **X** validieren.

## Kritischer Befund 2: Fremdrollen-Übernahme erreicht validierte Evidence

Der einzige `medium`-Claim ist ein simuliertes Zitat von `lisa_hartmann_610`, wonach die Migration **ihre** Personenmarke als selbstständige Software-Entwicklerin und IT-Consultant stärke. Die Migration betrifft Alexander Schneiders Domain, nicht Lisa Hartmanns. Die Antwort hat die Rolle des Untersuchungsgegenstands übernommen.

Das rohe Interview sollte im Trace erhalten bleiben, aber eine Fremdrollen-Antwort muss als claim-stützende `agent_quote`-Evidence unzulässig sein. Hier überlebt sie das Binding und wird zum Claim mit der höchsten Confidence des Reports. Damit ist sie ein brauchbarer Regressionstest für Identity-/Role-Guards.

## Kritischer Befund 3: Evidence-Scope wird falsch gerendert

Alle 46 validierten Claim-Zeilen erscheinen als:

```text
scope = Simulationskonsens
basis = persona
```

Tatsächlich werden **38 ausschließlich durch Seed-Dokument-Evidence** gestützt. Das ist kein kosmetischer Fehler: Ein quellengebundener Claim und ein Simulationskonsens tragen unterschiedliche Trust-Semantik und dürfen nicht dasselbe Scope-Label erhalten.

## Kritischer Befund 4: Der Gate weiß mehr als die finale Prosa

Die Trust-Schicht verwirft oder schwächt mehrere unbelegte Kennzahlen sowie die Behauptung, Option B sei eindeutig überlegen. Trotzdem können starke Formulierungen in der sichtbaren Section-Prosa verbleiben, während spätere Gate-Tabellen sie als Hypothese, unzureichend, widersprochen oder nur thematisch verwandt klassifizieren.

Nach dem Gating braucht die finale Ausgabe deshalb eine Reconciliation-Stufe. Sätze mit finalem Zustand `INSUFFICIENT`, `CONTRADICTED` oder `related_evidence_only` müssen entfernt oder ausdrücklich als Hypothese qualifiziert werden.

## Kritischer Befund 5: Simulierte Autorität kann wie reale Autorität wirken

Der Evidence Index enthält eine simulierte Persona mit `persona_id="google_692"`. Ihre Aussagen werden als `Agentenzitat` gespeichert und nicht als offizielle Web-Quelle. Diese Trennung muss der Renderer bewahren: simulierte Persona → „simulierte Suchmaschinen-Perspektive“; offizielle Dokumentation → `web_source` mit Provenance.

## Kritischer Befund 6: Persona-Eignung ist besser, aber nicht gelöst

Ältere Läufe ließen offensichtliche Software-/Produktentitäten als Personas zu. Dieser Lauf ist sauberer, enthält im Evidence Index aber weiterhin:

```text
Fachblog CREATE_POST on reddit in round 0
```

Ein Fachblog ist Content/Medium, kein individueller oder kollektiver Stakeholder. Das Report-Artefakt exportiert `generation_source` nicht. Der Lauf beweist daher **nicht**, ob die Entität über den normalen oder degradierten Persona-Pfad kam. Er beweist nur, dass ein Nicht-Stakeholder weiterhin die finale Simulation erreicht hat.

## Auditierbarkeitsproblem: Claim-IDs sind im Flat Export nicht global eindeutig

Der Report enthält **46 Claim-Zeilen, aber nur 22 eindeutige `claim_*`-IDs**. Intern können sie section-scoped sein; der Markdown-Renderer zeigt diesen Scope jedoch nicht. Menschliche Verweise wie `claim_07` sind dadurch mehrdeutig. Reportweite IDs müssen global eindeutig werden oder den Section-Scope sichtbar tragen.

## Simulationsdynamik: schwächeres Signal als Referenzlauf 4

| Metrik | Referenzlauf 4 | Dieser Lauf |
|---|---:|---:|
| Runden | 20 | 20 |
| validierte Claims | 39 | **46** |
| Hypothesen | 141 | 141 |
| Data Gaps | 131 | 133 |
| Social Actions / Interaktionen | **665** | 109 |
| Cluster | **6** | 3 |
| Echo-Chamber-Index | 0.5741 | 0.5963 |

Der neue Lauf liefert etwa **5,45 Interaktionen pro konfigurierter Runde**, gegenüber etwa **33,25 Aktionen pro Runde** in Referenzlauf 4. Das ist ein Warnsignal, kein bewiesener Regressionsbefund: Agentenzahl, Provider-/Modellrouting, Action-Konfiguration und Recommender-Verhalten können die Dynamik erheblich verändern.

Dieser Lauf ist deshalb die bessere **Trust-Pipeline-Referenz**; Referenzlauf 4 bleibt die reichhaltigere **Simulationsdynamik-Referenz**.

## Was dieser Lauf zeigt

- Evidence Binding arbeitet in brauchbarer Größenordnung.
- Seed-Dokument-Provenance erreicht den Report.
- Numerisches Prosa-Gating fängt mehrere unbelegte Zielwerte ab.
- Viele Hypothesen und Data Gaps bleiben von validierten Claims getrennt.
- Die verbleibenden Fehler sind konkret genug für deterministische Regressionstests.
- Der Domainmigration-Seed ist ein starker adversarialer Testfall für die Trust-Schicht.

## Was dieser Lauf ausdrücklich nicht zeigt

- **Keine prädiktive Validität.**
- **Keine echte Recruiter-, Arbeitgeber-, Google- oder Nutzerforschung.**
- **Kein Beweis, dass die empfohlene Migrationsstrategie objektiv die beste ist.**
- **Noch keine vollständige epistemische Provenance.**
- **Keine Garantie, dass ein validierter Claim ein wahrer Weltfakt ist, nur weil sein Source-Span real ist.**
- **Kein Beweis, dass die geringere Interaktionszahl eine Simulation-Regression darstellt.**

## Remediation-Priorität

1. **P1 — Seed-Assertion-Status Ende-zu-Ende erhalten.** Unbelegte, hypothetische oder synthetische Source-Spans dürfen keine direkten Weltfakten validieren.
2. **P1 — Fremdrollen-Interviewantworten als claim-stützende Evidence sperren.** Rohtrace erhalten, Evidence-Eignung blockieren.
3. **P2 — finale Prosa mit dem finalen Gate-Urteil synchronisieren.** `INSUFFICIENT`, `CONTRADICTED` und related-only müssen qualifiziert oder entfernt werden.
4. **P2 — korrekten Confidence-Scope und Basis rendern.** Seed-gebundene Claims dürfen nicht als Simulationskonsens erscheinen.
5. **P2 — Persona-Eignung gegen Content-Objekte wie `Fachblog` härten.**
6. **P3 — exportierte Claim-IDs global eindeutig machen.**
7. **P3 — Risk-Objekte zentralisieren, damit Summary/Detail bei Likelihood und Impact nicht auseinanderlaufen.**

## Artefakte

- Maschinenlesbare Audit-Zusammenfassung: [`artifacts/run-summary.json`](./artifacts/run-summary.json)
- Quellreport: `report_fb5dfaf69ffa` (vollständiger Markdown-Export ist mit dem Run-Audit außerhalb dieses Repository-Snapshots archiviert)

## Fazit

Referenzlauf 4 bewies, dass Agora Evidence endlich binden kann. Referenzlauf 5 zeigt die nächste Grenze: **Die richtige Quelle zu binden reicht nicht, wenn das System vergisst, ob die Quelle selbst eine Aussage als Fakt, Hypothese, synthetische Aussage, Widerspruch oder unbelegte Behauptung klassifiziert hat.**

Deshalb ist dies der aktuelle Referenzlauf. Er ist nicht die schönste Simulation und nicht der reichhaltigste Social-Trace. Er ist der klarste End-to-End-Test der Trust-Architektur, die Agora für 1.0 stabil bekommen muss.
