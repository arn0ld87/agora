# Bewertung der Agora-App anhand von Seed, Prompt, Evidence und Report

**Projekt:** Agora  
**Bewertungsgegenstand:** Simulation und Report-Erzeugung für alexle135.de / Alexander Schneider  
**Input-Dateien:** `seed.md`, `prompt.md`, `agora-report-report_3be730161722-evidence.json`, `agora_1.pdf`  
**Ziel:** Prüfen, ob Agora aus Seed und Prompt einen belastbaren, evidenzbasierten DACH-Wahrnehmungsreport erzeugt hat.

---

## 1. Kurzurteil

**Agora arbeitet inhaltlich in die richtige Richtung, aber methodisch noch zu weich.**

**Gesamtscore: 5,8 / 10**

Die App erkennt viele relevante Muster aus Seed und Prompt:

- DACH-Skepsis gegenüber KI-Hype
- Datenschutzbedenken bei KI-Agenten
- Umschüler-Status als Risiko und Vertrauenssignal zugleich
- technische Glaubwürdigkeit durch echte Projekte
- starke Wirkung von Docker Compose Builder und Terminal Missionen
- unklare Kontaktlogik auf alexle135.de
- Local-first als Vertrauenssignal bei Agora

Der Report klingt jedoch belastbarer, als die Evidence-Datei hergibt. Viele Aussagen sind sauber formuliert, aber nicht sauber belegt. Das ist für eine Hypothesenmaschine akzeptabel, für einen belastbaren Simulationsreport aber noch zu schwach.

---

## 2. Gesamtbewertung nach Bereichen

| Bereich | Score | Bewertung |
|---|---:|---|
| Prompt-Erfüllung | 4/10 | Viele geforderte Abschnitte fehlen oder sind nur angerissen. |
| Seed-Grounding | 6/10 | Themen passen, aber Belege sind oft zu allgemein. |
| DACH-Spezifik | 7/10 | Datenschutz, KMU-Skepsis, IHK/HWK, Local-first gut getroffen. |
| Persona-Simulation | 4/10 | 50 Personas werden behauptet, aber nicht vollständig tabellarisch ausgegeben. |
| Evidence-Qualität | 3/10 | Viele Claims haben keine direkte Evidenzbindung. |
| Report-Lesbarkeit | 7/10 | Gut lesbar, aber zu essayistisch. |
| Actionability | 6/10 | Gute Hinweise, aber zu wenig konkrete To-dos im geforderten Format. |
| Produktreife | 5/10 | Starkes Konzept, aber Ausgabevertrag und Validierung fehlen. |

---

## 3. Hauptbefund

Der Prompt verlangte eine klar strukturierte Ausgabe mit:

1. Executive Summary in maximal 12 Sätzen
2. Segment-Tabelle
3. Persona-Tabelle mit 50 Zeilen
4. Multiplikator-Auswertung mit 4 Einzelprofilen
5. Top 10 Reibungspunkte
6. Top 10 Vertrauenssignale
7. Top 10 Änderungen
8. Projektwirkungsbewertung
9. Drei Positionierungsvarianten
10. Konkrete Content-Ideen
11. Datenlücken

Der PDF-Report liefert stattdessen vor allem eine essayistische Zusammenfassung mit einigen Beispielpersonas. Das ist lesbar und teilweise nützlich, erfüllt aber den Prompt nicht vollständig.

**Klares Urteil:**  
Agora hat die Analyse-Richtung verstanden, aber den Output-Vertrag nicht eingehalten.

---

## 4. Technischer Befund aus der Evidence-Datei

Aus der Evidence-Datei ergeben sich folgende zentrale Kennzahlen:

| Kennzahl | Wert |
|---|---:|
| Agents gesamt | 54 |
| Interaktionen | 805 |
| Cluster | 4 |
| Echo-Chamber-Index | 0.4683 |
| Bridge Agents | 5 |
| Claims gesamt | 87 |
| Claims mit Evidence | 17 |
| Claims ohne direkte Evidence | 70 |
| Durchschnittliche Confidence | ca. 0.259 |

### Interpretation

Die Simulation hat Aktivität erzeugt. Es gab Interaktionen, Cluster und Bridge Agents. Das ist als Simulationsbasis brauchbar.

Das Problem liegt bei der Belegkette:

- Viele Report-Claims sind als `low confidence` markiert.
- Viele Claims haben `no_direct_evidence_bound`.
- Der finale Report unterscheidet nicht klar genug zwischen:
  - belegten Aussagen
  - Simulationsergebnissen
  - Modellinterpretationen
  - Seed-Hypothesen
  - Datenlücken

Damit wirkt der Report sicherer, als er methodisch ist.

---

## 5. Was Agora gut macht

### 5.1 Inhaltliche Richtung

Agora erkennt die wichtigsten Wahrnehmungsmuster korrekt:

- Technische Zielgruppen reagieren positiv auf echte Projekte.
- Kaufmännische Entscheider brauchen konkrete Nutzenübersetzung.
- Recruiter achten auf Umschulung, Lebenslauf, formale Nachweise.
- Datenschutzsensible Rollen springen bei KI-Agenten sofort an.
- Local-first und nachvollziehbare Dokumentation erzeugen Vertrauen.
- Der Stil von alexle135.de wirkt pragmatisch statt überverkauft.

### 5.2 DACH-spezifische Denkweise

Der Report trifft typische DACH-Fragen gut:

- „Wo landen die Daten?“
- „Was kostet das?“
- „Wer wartet das?“
- „Gibt es Dokumentation?“
- „Ist das DSGVO-sauber?“
- „Ist das eine Bewerbung, ein Portfolio oder ein Dienstleistungsangebot?“
- „Kann das jemand anderes übernehmen, wenn Alex ausfällt?“

Das ist deutlich besser als generische Persona-Simulationen, die meistens klingen, als hätte ein Werbepraktikant mit zu viel Kaffee und zu wenig Realitätssinn Zielgruppen erfunden.

### 5.3 Projektwahrnehmung

Die stärksten Projekte im Report sind nachvollziehbar:

| Projekt | Wirkung | Bewertung |
|---|---|---|
| Docker Compose Builder | sehr stark | Konkreter Nutzen, gut demo-fähig, technisch passend |
| Terminal Missionen | sehr stark | Bildung, FISI-Praxis, Didaktik, direkte Zielgruppe |
| Ticket-Routing mit KI-Agenten | mittel bis stark | Business-Nutzen klar, aber Datenschutzrisiko hoch |
| Agora | stark, aber erklärungsbedürftig | Local-first und DACH-Personas gut, aber Gefahr falscher Marktforschungs-Versprechen |
| OpenClaw-Workflows | technisch stark | Wirkt tief, aber braucht reproduzierbare Beispiele |
| Wortwerk/MentoQ | interessant | Bildungsnutzen vorhanden, Datenschutz und Zielniveau müssen klarer werden |

---

## 6. Was Agora schlecht macht

### 6.1 Fehlende vollständige Persona-Tabelle

Der Prompt fordert explizit 50 Persona-Zeilen. Der Report zeigt nur repräsentative Beispiele.

**Problem:**  
Segmentwerte wie „Kontaktwahrscheinlichkeit 70 %“ wirken dadurch wie berechnet, sind aber im Report nicht nachvollziehbar.

**Fix:**  
Jede Persona muss strukturiert gespeichert und ausgegeben werden.

```json
{
  "persona_id": "P01",
  "segment": "KMU-Geschäftsführer",
  "role": "Handwerksmeister",
  "goal": "IT-Modernisierung prüfen",
  "first_impression": "Modern, aber technisch schwer greifbar",
  "clicked_sections": ["Leistungen", "Kontakt"],
  "dropoff_point": "Leistungsseite: zu viele technische Begriffe",
  "decision": "ignorieren",
  "trust_score": 5,
  "contact_intent_score": 2,
  "concrete_improvement": "Leistung in Nicht-IT-Sprache erklären",
  "evidence_refs": ["seed:3.2", "seed:6"]
}
```

---

### 6.2 Claims ohne harte Belegkette

Viele Aussagen klingen wie Ergebnisse, sind aber intern nur Modellinterpretationen.

Beispielproblem:

```text
Die Simulation zeigt, dass die Tonalität der Website genau den Nerv der DACH-Zielgruppe trifft.
```

Das klingt stark. Wenn aber keine direkte Persona- oder Aggregat-Evidence gebunden ist, muss es abgeschwächt werden:

```text
Die Simulation deutet darauf hin, dass die pragmatische Tonalität bei technischen Zielgruppen positiv wirkt. Die Beleglage ist jedoch schwach, da nicht alle Persona-Reaktionen direkt an diesen Claim gebunden sind.
```

---

### 6.3 Simulierte O-Töne nicht sauber markiert

Der Seed enthält Platzhalter-O-Töne. Der Report nutzt ähnliche Zitate. Diese dürfen nicht wie echte Nutzerzitate wirken.

Besser:

```text
Simulierter Persona-O-Ton, abgeleitet aus Seed-Hypothese:
„Bei KI-Agenten frage ich sofort: Wo landen die Daten?“
```

Nicht:

```text
„Bei KI-Agenten frage ich sofort: Wo landen die Daten?“
```

Ohne Markierung wirkt das wie echtes Feedback. Das ist methodisch unsauber.

---

### 6.4 Zu essayistischer Report

Der Report liest sich gut, aber er ist zu wenig maschinenprüfbar.

Für Agora sollte gelten:

- Erst strukturierte Rohdaten
- Dann Aggregation
- Dann Report
- Dann PDF

Nicht:

- Modell schreibt Fließtext
- Validator versucht nachträglich zu retten, was noch zu retten ist

---

## 7. Konkrete Verbesserung: Output-Contract-Validator

Agora braucht einen Validator, der prüft, ob der Prompt-Vertrag erfüllt wurde.

```python
REQUIRED_SECTIONS = [
    "Executive Summary",
    "Segment-Tabelle",
    "Persona-Tabelle",
    "Multiplikator-Auswertung",
    "Top 10 Reibungspunkte",
    "Top 10 Vertrauenssignale",
    "Top 10 Änderungen",
    "Projektwirkung",
    "Positionierung",
    "Content-Ideen",
    "Datenlücken",
]

def validate_report_contract(report_text: str) -> list[str]:
    missing = []
    lower = report_text.lower()

    for section in REQUIRED_SECTIONS:
        if section.lower() not in lower:
            missing.append(section)

    return missing
```

### Empfehlung

Wenn Pflichtabschnitte fehlen:

- keinen finalen Report erzeugen
- stattdessen `report_status = incomplete`
- fehlende Abschnitte ausgeben
- erneute Generierung für genau diese Abschnitte anstoßen

---

## 8. Konkrete Verbesserung: Claim-Evidence-Schema

Jeder Claim sollte ein Evidence-Schema bekommen.

```json
{
  "claim_id": "claim_042",
  "claim_text": "Docker Compose Builder erzeugt bei technischen Entscheidern Vertrauen.",
  "claim_type": "simulation_aggregate",
  "confidence": 0.78,
  "evidence": [
    {
      "type": "persona_response",
      "persona_id": "P21",
      "field": "strongest_trust_trigger",
      "value": "Docker Compose Builder"
    },
    {
      "type": "segment_aggregate",
      "segment": "IT-Admins",
      "trust_score_avg": 9.0
    },
    {
      "type": "seed_anchor",
      "section": "4.3 Docker Compose Builder"
    }
  ],
  "limitations": [
    "Simulation basiert auf Seed-Daten, nicht auf echter Nutzerbefragung."
  ]
}
```

---

## 9. Konkrete Verbesserung: Report in zwei Ebenen trennen

### Ebene 1: Machine-readable Report

```json
{
  "executive_summary": [],
  "segments": [],
  "personas": [],
  "multipliers": [],
  "friction_points": [],
  "trust_signals": [],
  "project_impact": [],
  "positioning_variants": [],
  "content_ideas": [],
  "data_gaps": []
}
```

### Ebene 2: Human-readable Report

Aus der JSON-Struktur wird Markdown/PDF erzeugt.

Vorteil:

- Tabellen sind vollständig prüfbar.
- Scores sind nachvollziehbar.
- Fehlende Felder fallen sofort auf.
- PDF kann hübsch sein, ohne die Datenstruktur zu ruinieren.

---

## 10. Bewertung der einzelnen Report-Aussagen

| Aussage im Report | Bewertung |
|---|---|
| Technische Profile reagieren positiv | plausibel |
| KMU-Geschäftsführer brauchen konkretere Nutzenkommunikation | stark plausibel |
| Umschüler-Status wird teilweise neutralisiert | plausibel, aber stärker belegen |
| Docker Compose Builder wirkt stark | plausibel |
| Terminal Missionen wirken stark im Bildungsbereich | plausibel |
| Datenschutz ist kritischer Absprungpunkt | stark plausibel |
| Multiplikatoren reagieren überwiegend positiv | zu schwach belegt |
| Tech-Community würde Projekte teilen | möglich, aber belegen |
| Kontaktwahrscheinlichkeiten in Prozent | ohne Persona-Tabelle nicht belastbar |
| Exzellente GitHub-Aktivität | nur nutzbar, wenn echte Repo-Daten eingebunden wurden |

---

## 11. Empfohlene Produkt-Roadmap für Agora

### Phase 1: Output-Vertrag absichern

- Prompt-Contract-Validator bauen
- Pflichtabschnitte prüfen
- Mindestanzahl Personas erzwingen
- JSON-Schema für Persona, Segment, Claim, Evidence festlegen

### Phase 2: Evidence-Härtung

- Seed-Anker je Claim erzwingen
- Persona-IDs je aggregierter Aussage speichern
- Low-Confidence-Claims im Report markieren
- Claims ohne Evidence automatisch in Datenlücken verschieben

### Phase 3: Reportqualität verbessern

- Markdown zuerst generieren
- PDF nur als Export
- Tabellen vollständig ausgeben
- Zusammenfassung klar von Rohdaten trennen

### Phase 4: Vertrauensmodus einbauen

Berichtsmodi:

| Modus | Verhalten |
|---|---|
| `strict` | Nur belegte Claims |
| `balanced` | Belegte Claims plus markierte Hypothesen |
| `explorative` | Breitere Interpretation, aber deutlich als Simulation markiert |

Empfehlung: Standardmodus `balanced`.

---

## 12. Zielarchitektur

```text
seed.md
  -> Fakten extrahieren
  -> Anchors setzen

prompt.md
  -> Output-Vertrag extrahieren
  -> Pflichtabschnitte definieren

Simulation
  -> Persona-Rows erzeugen
  -> Aktionen speichern
  -> Scores speichern
  -> Entscheidungen speichern

Aggregation
  -> Segmentwerte berechnen
  -> Projektwirkung berechnen
  -> Dropoff-Ranking erzeugen

Evidence Binder
  -> Claim -> Seed
  -> Claim -> Persona
  -> Claim -> Aggregat
  -> Claim -> Datenlücke

Report Generator
  -> Markdown
  -> PDF
  -> JSON-Anhang
  -> CSV-Anhang

Validator
  -> Pflichtabschnitte vorhanden?
  -> Persona-Anzahl korrekt?
  -> Zahlen ableitbar?
  -> Low-Confidence markiert?
  -> Claims ohne Evidence blockiert?
```

---

## 13. Priorisierte Fixes

| Priorität | Fix | Wirkung |
|---:|---|---|
| 1 | Persona-Tabelle vollständig erzeugen | macht Simulation nachvollziehbar |
| 2 | Claim-Evidence-Binding erzwingen | verhindert hübsches Halluzinieren |
| 3 | Pflichtabschnitt-Validator | verhindert unvollständige Reports |
| 4 | Low-Confidence sichtbar markieren | erhöht Vertrauenswürdigkeit |
| 5 | Simulierte Zitate kennzeichnen | verhindert falschen Eindruck echter Marktforschung |
| 6 | JSON + Markdown getrennt erzeugen | bessere Weiterverarbeitung |
| 7 | Datenlücken automatisch ausgeben | macht Reports ehrlicher |
| 8 | Projektwirkung aus Persona-Scores berechnen | weniger Bauchgefühl |
| 9 | Report-Modi einführen | passend für Exploration oder strenge Analyse |
| 10 | Export als MD/PDF/CSV/JSON | produktiver nutzbar |

---

## 14. Was Agora aus dem konkreten Test lernen sollte

### Wichtigster positiver Befund

Agora kann aus einem Seed-Dokument eine brauchbare strategische Wahrnehmungsanalyse erzeugen. Die inhaltlichen Muster sind nicht zufällig daneben, sondern nah an den Seed-Themen.

### Wichtigster negativer Befund

Agora erzeugt noch zu viel Report-Prosa und zu wenig prüfbare Struktur. Das Ergebnis wirkt wie ein guter Beratertext, aber nicht wie ein sauber belegter Simulationsbericht.

### Produktpositionierung für Agora

Agora sollte nicht versprechen:

```text
Wir simulieren echte Marktforschung.
```

Besser:

```text
Agora erzeugt nachvollziehbare Zielgruppen-Hypothesen aus strukturierten Seed-Dokumenten. Jede Aussage wird mit Seed-Bezug, Persona-Reaktion oder Datenlücke markiert.
```

Das ist ehrlicher, stärker und DACH-kompatibler.

---

## 15. Endurteil

**Agora ist als Idee stark. Der aktuelle Output ist ein guter Strategie-Entwurf, aber noch kein belastbarer Simulationsreport.**

Die App hat das richtige Thema getroffen:

- lokale Analyse
- DACH-Personas
- strukturierte Wahrnehmung
- Projektbewertung
- Datenschutzsensibilität
- Portfolio-/Positionierungsanalyse

Aber sie muss strenger werden:

1. vollständige Tabellen liefern
2. Scores nachvollziehbar berechnen
3. Claims sauber belegen
4. Datenlücken sichtbar markieren
5. Low-Confidence nicht als Gewissheit verkaufen
6. simulierte Aussagen klar als Simulation kennzeichnen

**Empfehlung:**  
Baue Agora als prüfbare Hypothesenmaschine, nicht als Report-Schreiber. Der Report ist nur die Oberfläche. Der eigentliche Wert liegt in sauber strukturierten Persona-Daten, Aggregaten und belegten Claims.

---

## 16. Nächste Schritte

1. JSON-Schema für Persona-, Segment- und Claim-Daten festlegen.
2. Validator bauen, der fehlende Pflichtabschnitte und unbelegte Claims blockiert.
3. Report-Generator auf Markdown-first umbauen und PDF nur noch als Export behandeln.
