# Wording-Glossar — Agora

**Stand:** 08.09.2026  
**Status:** verbindliche Produkt-/Trust-Sprache für aktuelle UI, README, lebende Doku und nutzersichtbare Reporttexte.

Agora ist eine **evidenzorientierte Plattform zur Stakeholder-, Risiko- und Szenarioanalyse**. Die Multi-Agenten-Simulation ist ein Werkzeug innerhalb dieser Pipeline, nicht die Behauptung, menschliche Zukunft vorhersagen zu können.

---

## 1. Produktpositionierung

### Bevorzugt

Deutsch:

> **Evidenzorientierte Plattform zur Stakeholder-, Risiko- und Szenarioanalyse**

Kurzform:

> **Evidenzorientierte Stakeholder- und Szenarioanalyse**

Englisch:

> **Evidence-oriented stakeholder, risk, and scenario analysis**

### Nicht als Hauptpositionierung verwenden

- „Prediction Engine“
- „Future Simulator“
- „Digitaler Zwilling der Gesellschaft“
- „Public Opinion Prediction“
- „hochpräzise Verhaltensprognose“
- „reproduzierbare Simulationsumgebung“ als pauschale Produkteigenschaft

Die letzte Formulierung ist wichtig: Agora arbeitet an Reproduzierbarkeit, garantiert sie in `0.9.5` aber noch nicht (#763/#1274).

---

## 2. Verbindliche Trust-Begriffe

| Vermeiden | Bevorzugt EN | Bevorzugt DE |
|---|---|---|
| `prediction` | `scenario analysis` / `scenario evaluation` | Szenarioanalyse / Szenarioauswertung |
| `predict human behavior` | `explore simulated stakeholder reactions` | simulierte Stakeholder-Reaktionen untersuchen |
| `future behavior` | `simulated reaction` | simulierte Reaktion |
| `rehearse the future` | `test assumptions` | Annahmen testen |
| `public opinion prediction` | `stakeholder analysis` | Stakeholderanalyse |
| `high-fidelity digital world` | `controlled multi-agent simulation` | kontrollierte Multi-Agenten-Simulation |
| `god's eye view` | `analytical observer perspective` | analytische Beobachtungsperspektive |
| `prediction findings` | `analysis findings` | Analysebefunde |
| `simulation predictions` | `simulation observations` | Simulationsbeobachtungen |
| `proven by the simulation` | `observed in this simulation run` | in diesem Simulationslauf beobachtet |
| `same seed = same run` | `seed recorded; full replay not yet guaranteed` | Seed erfasst; vollständiger Replay noch nicht garantiert |

---

## 3. Evidence-Wording

### Claim

Eine im Report geführte Aussage mit zugeordneten Evidence-/Contract-Metadaten. Ein Claim ist nicht automatisch „wahr“.

### Evidence

Ein konkreter Beleg-/Beobachtungsdatensatz aus einer verfügbaren Quellenklasse, z. B. Dokument, Graphrelation, Interview oder Simulationsaktion.

### Hypothese

Eine plausible, aber nicht ausreichend belegte Aussage.

### Data Gap

Eine für die Fragestellung relevante Information, die in den verfügbaren Quellen nicht vorhanden ist.

Nicht jeden fehlgeschlagenen Matcher als Data Gap bezeichnen. Wenn die Information vorhanden ist, aber Binding scheitert, ist das ein Binding-/Gate-Problem.

### Confidence

Confidence beschreibt die systeminterne Evidenz-/Supportlage eines Claims. Es ist **keine Wahrscheinlichkeit, dass die Aussage in der realen Welt wahr ist**.

### `INCOMPLETE`

Ein auslieferbarer, aber strukturell oder fachlich unvollständiger Report. Nicht als Fehler kaschieren, aber auch nicht als normal `COMPLETED` beschreiben.

---

## 4. Lauf-/Job-Begriffe

| Begriff | Bedeutung |
|---|---|
| **Lauf** | fachliches Vorhaben von Quelle bis Bericht |
| **Job** | einzelner technischer Schritt, verwaltet durch RunRegistry |
| **Graph** | Quellenumfeld aus Entitäten/Relationen/Embeddings |
| **Personasatz** | Sammlung synthetischer Personas |
| **Bericht** | lesbares Ergebnis mit Claims/Evidence/Degradationen |
| **Projekt** | vor allem technischer `project_id`-Begriff, nicht bevorzugtes UI-Wort für den Gesamtprozess |

### Stop-/Abbruchsprache

- expliziter Nutzer-Stop: **gestoppt / `user_stop`**
- Budgetlimit: **durch Budget beendet**
- Webprozess-/Prozessverlust: **fehlgeschlagen / `process_restart`**, wenn so reconciliiert
- unvollständiger Report: **`INCOMPLETE`**

Nicht alles unter „failed“ oder „cancelled“ zusammenwerfen.

---

## 5. Persona-Sprache

Personas sind:

- synthetisch,
- aus Quellen/Graph/Modellen abgeleitet,
- überprüfbar und bearbeitbar,
- keine realen Befragten.

Vermeiden:

- „Kunden sagten …“
- „Bürger wollen …“
- „die Zielgruppe bestätigt …“

wenn die Aussage nur aus synthetischen Personas stammt.

Bevorzugt:

- „Die simulierten Personas äußerten …“
- „Im Lauf trat als Konfliktmuster auf …“
- „Die Persona-Interviews stützten …“

und nur dann, wenn die entsprechende Evidence tatsächlich vorhanden ist.

---

## 6. Reproduzierbarkeit

### In `0.9.5` zulässig

- „Run-/Seed-Metadaten werden gespeichert.“
- „Bestimmte deterministische Teilalgorithmen verwenden feste Seeds.“
- „Die 0.10-Roadmap zielt auf vollständige Manifeste und Replay.“

### Nicht zulässig

- „Agora-Läufe sind reproduzierbar.“
- „Gleicher Seed erzeugt denselben Report.“
- „Der Referenzlauf kann aus einem frischen Checkout identisch nachgestellt werden.“

Solange #763/#1274 offen sind, sind diese Aussagen stärker als der Code trägt.

---

## 7. Baseline-/Produktnutzen

Bis eine externe Evaluation vorliegt:

Bevorzugt:

- „Agora soll zusätzliche Konfliktlinien und Datenlücken gegenüber einer einfachen LLM-Baseline sichtbar machen.“
- „Der Mehrwert wird über #765 evaluiert.“

Nicht:

- „Agora liefert bessere Entscheidungen als ein einzelnes LLM.“
- „Die Simulation erhöht nachweislich die Prognosequalität.“

ohne entsprechende Messung.

---

## 8. Historische Dokumente

Historische Logs, Referenzläufe, Audits und Worklogs werden nicht rückwirkend umformuliert, solange sie klar als historische Belege erkennbar sind.

Aktuelle README-/Status-/Architekturtexte müssen dagegen diesem Glossar folgen.

---

## 9. Verifikation

Für aktuelle Produkt-/Reporttexte lohnt ein gezielter Drift-Check:

```bash
rg -ni \
  "future prediction|public opinion prediction|rehears(e|al).*future|god.s eye|high.fidelity digital world|same seed.*same run|reproducible simulation environment" \
  README.md README.de.md CONTEXT.md docs/ backend/app/ \
  --glob '!docs/archive/**' \
  --glob '!docs/reference-runs/**' \
  --glob '!docs/audits/**'
```

Treffer sind zu **prüfen**, nicht blind zu ersetzen: Tests, ADR-Zitate oder historische Kontexte können legitime Vorkommen enthalten.
