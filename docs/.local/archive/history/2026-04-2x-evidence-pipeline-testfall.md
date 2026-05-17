> **HISTORISCHER SNAPSHOT (Stand 2026-04-2x).**
>
> Aktueller Stand siehe:
> - Architektur & Plan: `CLAUDE.md` / `PLAN.md` / `plan.heuristic.md`
> - Test-Status: `docu/STATUS.md`
> - Diese Datei wurde aus dem Repo-Root nach `docu/history/` verschoben.
>
---

- Mehrsatz-Absätze müssen in atomare Claims zerlegt werden.
- Irrelevante Inhalte dürfen keine starke Evidence für Fach-/Politik-Claims werden.
- Evidence soll claim-spezifisch mit `match_score` gebunden werden.
- `model_generated_inference` und `section_synthesis` gehören in `audit_trail`, nicht in `evidence`.
- Confidence darf nicht pauschal `0.95 high` sein.

---

# Testdokument: KI-Pflichtfach an Schulen in NRW

**Der Beschluss und seine Architekten**

Am 22. Mai 2024 beschloss die Landesregierung Nordrhein-Westfalen einen Pilotversuch für das Schulfach „Künstliche Intelligenz und digitale Mündigkeit“. Das Fach soll ab dem Schuljahr 2027/28 an zunächst 25 Schulen verpflichtend eingeführt werden. Das Bildungsministerium plant dafür ein Startbudget von 12,4 Millionen Euro.

**Umsetzung in den Schulen**

Die RWTH Aachen soll ein Curriculum für die Klassen 8 bis 10 entwickeln. Das Curriculum soll Grundlagen maschinellen Lernens, Datenschutz, Quellenkritik und automatisierte Entscheidungsprozesse behandeln. Lehrkräfte sollen vor dem Start des Pilotfachs an 18 Fortbildungstagen geschult werden.

Die Schülervertretung NRW unterstützt das Ziel digitaler Bildung, fordert aber eine klare Trennung zwischen praktischer KI-Nutzung und Leistungsbewertung. Die GEW Nordrhein-Westfalen kritisiert den Zeitplan als zu knapp. Der Landeselternrat fordert transparente Regeln für Datenschutz und den Einsatz externer KI-Dienste.

**Konflikt um Bewertung**

Das Bildungsministerium erklärte, dass im ersten Pilotjahr keine klassischen Noten vergeben werden sollen. Eine Schulleiterin aus Dortmund sagte dagegen, ihre Schule plane von Beginn an bewertete Projektarbeiten. Diese Aussagen widersprechen sich teilweise und sollen im Bericht sauber getrennt werden.

**Ablenkendes Material ohne Relevanz**

Die Cafeteria des Pilotgymnasiums verkauft dienstags vegetarische Lasagne. Beim Schulfest spielte die Jazz-AG drei Stücke. Der Hausmeister reparierte im April mehrere defekte Fahrradständer.

## Erwartete Testsignale

### Claims, die erkannt werden sollten

- Das Pilotfach heißt „Künstliche Intelligenz und digitale Mündigkeit“.
- Das Fach soll ab 2027/28 an 25 Schulen verpflichtend eingeführt werden.
- Das Startbudget beträgt 12,4 Millionen Euro.
- Die RWTH Aachen soll das Curriculum entwickeln.
- Die GEW Nordrhein-Westfalen kritisiert den Zeitplan.
- Das Bildungsministerium will im ersten Pilotjahr keine klassischen Noten vergeben.
- Eine Schulleiterin aus Dortmund plant bewertete Projektarbeiten von Beginn an.

### Inhalte, die nicht als Claims zählen sollten

- `# Testdokument: KI-Pflichtfach an Schulen in NRW`
- `**Der Beschluss und seine Architekten**`
- `**Umsetzung in den Schulen**`
- `**Konflikt um Bewertung**`
- Cafeteria, Jazz-AG und Fahrradständer als Evidence für KI-Politik-Claims

---

# Agora-Prompt für den Testlauf

Nutze das hochgeladene Testdokument als Ausgangspunkt für eine Simulation.

Simuliere eine öffentliche Debatte in Nordrhein-Westfalen über die geplante Einführung des Pflichtfachs „Künstliche Intelligenz und digitale Mündigkeit“ ab dem Schuljahr 2027/28. Berücksichtige mindestens diese Akteursgruppen: Bildungsministerium, RWTH Aachen, GEW Nordrhein-Westfalen, Schülervertretung NRW, Landeselternrat, Schulleitung Dortmund und lokale Medien.

Ziel der Simulation:

1. Zeige, welche Gruppen die Einführung unterstützen.
2. Zeige, welche Gruppen den Zeitplan oder Datenschutz kritisieren.
3. Zeige, ob sich ein Konflikt um Leistungsbewertung entwickelt.
4. Unterscheide sauber zwischen belegten Fakten aus dem Dokument und simulierten Reaktionen der Agenten.
5. Ignoriere irrelevante Details wie Cafeteria, Jazz-AG und Fahrradständer für die politische Analyse.

Erstelle danach einen kurzen Zukunftsreport mit 2 bis 3 Abschnitten. Der Report soll klar belegt sein und keine unbelegten Behauptungen als sichere Fakten darstellen.

---

# Erwartete Prüfung nach dem Lauf

Prüfe nach dem Report-Export die Evidence-JSON:

```json
{
  "schema_version": 2,
  "checks": [
    "Keine Markdown-Header als Claims",
    "Keine kurzen Bold-Zwischenüberschriften als Claims",
    "Claims sind atomar und nicht als Mehrsatz-Blöcke gespeichert",
    "Evidence enthält match_score bei gebundenen Items",
    "Irrelevante Cafeteria/Jazz/Fahrradständer-Inhalte haben keinen hohen match_score für KI-Claims",
    "model_generated_inference steht in audit_trail, nicht in evidence",
    "section_synthesis steht nicht in evidence",
    "confidence_score ist nicht pauschal 0.95",
    "verified wird nur bei starker claim-spezifischer Evidence vergeben"
  ]
}
```

---

# Mini-Auswertungsvorlage

Nach dem Lauf kannst Du diese Tabelle ausfüllen:

| Check | Erwartung | Ergebnis |
|---|---|---|
| Header-Claims entfernt | Ja | offen |
| Bold-Titel entfernt | Ja | offen |
| Claim-Atomisierung | Ja | offen |
| Evidence mit `match_score` | Ja | offen |
| Self-Evidence nur in `audit_trail` | Ja | offen |
| Keine 0.95-Confidence-Flut | Ja | offen |
| Irrelevante Inhalte niedrig bewertet | Ja | offen |
| Widerspruch zur Bewertung sauber getrennt | Ja | offen |
