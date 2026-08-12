# Prompt — Agora-Run: KI-Azubi-Match Dortmund

## Run-Konfiguration

```
run_name: ki-azubi-match-dortmund-v1
seed_document: docs/test-seeds/ki-azubi-match-dortmund/seed_document.md
ziel: Stakeholder-Analyse zur Einführung eines KI-gestützten Matching-Portals
```

## Modell-Routing

| Phase | Provider/Modell | Begründung |
|---|---|---|
| Ontologie | bel. Provider, small-fast | Ein Call, einfaches Schema |
| NER | bel. Provider, small-fast | Paralelle Chunks, hohes Volumen |
| Personas | sonnet | Pro Entität ein Call, braucht Konsistenz |
| Simulation | günstig/lokal (Qwen, DeepSeek) | Hohe Callzahl, Fehlertoleranz hoch |
| Report | sonnet (oder besser) | ReAct-Loop, Qualität entscheidet |
| Embedding | bel. Modell, fixe Dim | Nur für Graph-Build nötig |

> **Hinweis:** Provider-Detection läuft über `registry.py` — bei Ollama/ lokal
> muss `base_url` korrekt gesetzt sein, sonst wird `detect_provider` fehlschlagen.

## Ontologie-Vorgabe (Orientierung)

Die NER erfindet ihr Vokabular pro Lauf — diese Liste ist NICHT als Fix-Schema
zu setzen, sondern als Erwartungsrahmen für die Auswertung.

```json
{
  "erwartete_entitaetentypen": [
    "Person", "Organization", "City", "Region",
    "Concept", "Technology", "Document",
    "AcademicRole", "StakeholderGroup"
  ],
  "erwartete_beziehungstypen": [
    "works_at", "leads", "opposes", "supports",
    "funds", "studies", "evaluates", "represents"
  ]
}
```

## Prompt für den Report-Agenten

> Dieser Prompt wird (sinngemäß) für den ReAct-Loop (Phase 4) verwendet.
> Er steuert die Section-Bildung, die Interview-Fragen und die
> Evidence-Bewertung.

### Auftrag

Erstelle eine Stakeholder-Analyse zur Einführung des „KI-Azubi-Match Dortmund",
einem KI-gestützten Matching-Portal für Ausbildungsplätze. Das Seed-Dokument
beschreibt die Ausgangslage, 6 Stakeholder-Gruppen, rechtliche Rahmenbedingungen
und internationale Erfahrungen.

### Sections (erwartet)

1. **Ausgangslage und Problem** — Warum wird das Portal gebraucht? (Passungsquote 38 %,
   2.847 unbesetzte Plätze)
2. **Stakeholder-Übersicht** — Wer sind die Beteiligten, welche Positionen vertreten sie?
3. **KI vs. Mensch** — Der zentrale Konflikt zwischen Effizienzgewinn und Diskriminierungsrisiko
4. **Rechtliche Hürden** — DSGVO, AGG, BBiG, Haftungsfragen
5. **Internationale Erfahrungen** — Was kann Dortmund aus anderen Ländern lernen?
6. **Bewertung und Ausblick** — Abwägung, Erfolgsfaktoren, Empfehlung

### Interview-Fokus

- Leite aus den Stakeholder-Positionen kontroverse Fragethemen ab
- Wähle bis zu 8 Personas aus, die möglichst unterschiedliche Positionen vertreten
- Stelle 4–5 neutrale Fragen, die Konfliktlinien sichtbar machen
- Gute Themen: „Automation Bias", „Diskriminierung durch Algorithmen",
  „Kosten-Nutzen-Abwägung", „Datenschutzbedenken"
- Achte auf Rollenklarheit — prüfe ob Antworten zur Persona-Rolle passen

### Evidence-Regeln (gemäß ADR-0002)

- **`high`/`verified`**: Braucht `agent_quote` aus zwei unterschiedlichen
  Stakeholder-Gruppen (`cross_stakeholder_for_high`)
- **`medium`**: Braucht `seed_corpus`-Evidence (aktuell selten erreichbar,
  vgl. ADR-0013)
- **`low`**: Alle anderen Claims, insbesondere inferred ohne Quellbeleg
- **Hypothese**: Claim ohne deckende Evidence → aus validiertem Bestand entfernt
- **Data Gap**: Explizit benannte Wissenslücke

> **Hinweis:** `cross_stakeholder_for_high` wertet NUR `agent_quote`, nicht
> `seed_corpus`. Ein Claim mit zwei Interview-Quellen erreicht also auch ohne
> Seed-Bezug `high` — das ist systemkonform.

### Qualitätskriterien

- Jeder Claim muss eine nachvollziehbare Quelle im `evidence_index` haben
- Zitate tragen `persona_id` und `seed_anchor` als `<simulated_quote>`-Tag
  (Freitext-Zitate ohne Tag werden vom Parser nicht als Zitat erkannt)
- Vermeide Frage-Echo: Wenn alle Personas gleich klingen, hast du die
  Fragen suggestiv formuliert
- Prüfe Rollenübernahme: Antwortet ein Rechenzentrums-Techniker als
  „Betriebsrat", ist das ein bekanntes Phänomen — dokumentiere es

## Erwartete Herausforderungen (aus CONTEXT.md)

Diese Liste warnt den Report-Agenten vor bekannten Systemeigenheiten:

- **Frage-Echo** (§2): Personas wiederholen die Frage in der Antwort → wirkt
  wie unabhängige Bestätigung, ist es nicht
- **Rollenübernahme** (§2): Persona antwortet in falscher Rolle
- **Zitat ≠ Simulationsäußerung** (§2): Zitate kommen aus Interviews, nicht
  aus der Simulation
- **verify_prose-Lücke** (§3): Nur Sätze mit Zahlen werden geprüft —
  meinungsstarke Aussagen ohne Zahl passieren ungeprüft
- **seed_doc:-Anker** (§3): auflösbare Referenz im Format `seed_doc:<id>#chunk:<n>`, serverseitig gegen `known_anchors` verifiziert
- **Twitter ohne Kommentare** (§6): Twitter kennt nur `quote_post`, keine
  Comments — kein Defekt
- **Reposts mit leerem `content`** (§4): `original_post_id IS NULL` filtert
  sie raus

## Auswertungs-Prompt (nach Run-Ende)

Nach Abschluss des Runs:

1. **Evidence-Bilanz ziehen:**
   ```bash
   docker exec agora python -c "
   import json
   m=json.load(open('/app/backend/uploads/reports/<report_id>/evidence_map.json'))
   for s in m['sections']:
       print(s['section_index'], len(s.get('claims') or []),
             len(s.get('hypotheses') or []))
   print('Seed-Anker:', [k for k in (m.get('evidence_index') or {})
         if 'seed_doc' in k or 'seed' in k.lower()])
   "
   ```

2. **Gegen Erwartungshorizont abgleichen:**
   - Liegen alle 6 Personen als Personas vor?
   - Sind alle 5 Evidence-Typen vertreten?
   - Liegt die Claim-Zahl im erwarteten Bereich (16–26)?

3. **Interview-Qualität prüfen:**
   ```bash
   docker exec agora grep -c 'interview' \
     /app/backend/uploads/reports/<report_id>/agent_log.jsonl
   ```
   → Sollte ≥ 4 Fragen, ≥ 6 Antworten enthalten.

4. **verify_prose-Wirksamkeit prüfen:**
   ```bash
   docker exec agora python -c "
   import json
   with open('/app/backend/uploads/reports/<report_id>/evidence_map.json') as f:
       m = json.load(f)
   verified = [s for s in m.get('sections', [])
               if s.get('section_verification')]
   print(f'{len(verified)} sections with verification data')
   for s in verified:
       print(f'  Section {s[\"section_index\"]}: ',
             len(s.get('section_verification', {}).get('verified_sentences', [])),
             'verified,',
             len(s.get('section_verification', {}).get('removed_sentences', [])),
             'removed')
   "
   ```

---

*Prompt-Dokument erstellt am 11.08.2026 zum Testen des Agora-Pipelines
mit dem Fokus auf Evidence-Gating, Interview-Mechanik und bekannte
Fehlerbilder aus CONTEXT.md.*
