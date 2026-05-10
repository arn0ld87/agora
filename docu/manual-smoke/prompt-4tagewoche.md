# Smoke-Prompt · 4-Tage-Woche bei Heinrich Söhne GmbH

Quellmaterial: [`seed-4tagewoche.md`](seed-4tagewoche.md)

## simulation_requirement (Copy-Paste in Step 1)

```
Wie reagieren die fünf Stakeholder-Gruppen rund um die Heinrich Söhne GmbH
(Schmölln, Thüringen) auf die Einführung der 4-Tage-Woche bei vollem
Lohnausgleich zum 01.01.2026?

Stakeholder:
1. Werkstatt-Belegschaft (138 Personen, IG-Metall-Anteil hoch)
2. Verwaltung und Vertrieb (49 Personen, gemischte Rollen)
3. Stammkunden (Automotive Tier-1, Maschinenbau, mittelständisch DACH)
4. Lieferanten (Stahl, Sonderwerkzeuge, Logistik)
5. Regionale Wettbewerber (Spitzwieser Werkzeugbau Plauen, Cluster Plauen)

Zeithorizont: 6 Monate ab Vollumstellung (Jan – Jun 2026).

Fokus auf:
- Kippt-die-Belegschaft-Risiko bei der Betriebsversammlung am 10.06.2025
- Vertriebs-Erreichbarkeit Freitag und resultierender Auftragsverlust
- Konkurrenz-Reaktion (Recruiting + Kundenakquise)
- Erreichung der Bewerberzahlen-Ziele +40 % bis Q3 2026

Persona-Quoten so wählen, dass Werkstatt-Belegschaft mit IG-Metall-
Affinität die größte Gruppe ist, gefolgt von Stammkunden und Verwaltung.
Wettbewerber- und Lieferanten-Personas als kleinere Quoten.
```

## Warum dieser Case

| Eigenschaft | Wirkung |
|---|---|
| Klare benannte Akteure (Pforr, Lehmann, Heinrich, Wahlster …) | NER-Extraction findet sofort 12 – 18 Entities, kein Cold-Start-Stuttern |
| Vier eindeutige Konfliktlinien (Werkstatt vs. GF, Vertrieb vs. Office, Stammkunden vs. Wettbewerb, Generation Y vs. Boomer) | Persona-Quoten lassen sich nicht-trivial ableiten |
| DACH-Kontext mit konkreten Orten/Firmen | Wording-Glossar v1 wird sauber getriggert (kein „revolutionary" / „seamless" zu erwarten) |
| Kompakter Korpus (~ 4 KB) | Ontology + Graph-Build laufen bei Cloud-Modell in < 90 Sek |
| Klare Entscheidungs-Endpunkte (Kippt? Auftragsverlust? Recruiting-Ziel?) | Confidence-Kalibrierung hat etwas zum Festmachen |
| Branche bewusst unaufregend | Du erkennst sofort, ob ein Bericht halluziniert (Buzzwords, Entrepreneur-Stories) oder beim Material bleibt |

## Bedienungsanleitung

### Variante A — UI

1. `docker compose up -d` (Stack hochfahren), dann `http://localhost:5001`.
2. Step 1 Upload: `seed-4tagewoche.md` per Drag & Drop hochladen.
3. Field „Was soll simuliert werden?": den `simulation_requirement` oben einfügen.
4. Step 2 Quoten: Werkstatt 40 %, Stammkunden 25 %, Verwaltung 15 %, Lieferanten 10 %, Wettbewerb 10 %.
5. Step 3 Simulation starten — bei Cloud-Modell (Qwen 3-Coder oder Gemini) ca. 4 – 7 Min für 30 Personas.
6. Step 4 Report ansehen — Pflichtabschnitte 1 – 11 sollten alle befüllt sein, kein „Data Gap"-Spam.

### Variante B — schneller API-Smoke (kein UI)

```bash
TOKEN="$AGORA_AUTH_TOKEN"
BASE="http://localhost:5001"

# 1) Upload + Ontologie
curl -fsS -X POST "$BASE/api/graph/ontology/generate" \
  -H "X-Agora-Token: $TOKEN" \
  -F "project_name=4-Tage-Woche-Smoke" \
  -F "simulation_requirement=$(cat docu/manual-smoke/prompt-4tagewoche.md | sed -n '/^```$/,/^```$/p' | sed '1d;$d')" \
  -F "files=@docu/manual-smoke/seed-4tagewoche.md" \
  | jq -r '.data.project_id'
# → speichere PROJECT_ID

# 2) Graph bauen
curl -fsS -X POST "$BASE/api/graph/build" \
  -H "X-Agora-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"project_id\": \"$PROJECT_ID\"}" \
  | jq -r '.data.task_id'
# → speichere TASK_ID

# 3) Status pollen
watch -n 5 "curl -s -H 'X-Agora-Token: $TOKEN' $BASE/api/graph/task/$TASK_ID | jq '.data.status'"
# warte auf "completed"

# 4) Restlichen Wizard im UI weitermachen, oder weiter via API
#    (Profile generieren, Simulation, Report — siehe backend/app/api/)
```

### Variante C — E2E-Stub (deterministisch, keine LLM-Kosten, < 30 Sek)

Diese Daten sind kompatibel mit dem Stub-Modus aus M11.4b-Followup-2.
Für reine Pipeline-Verifikation:

```bash
AGORA_E2E_LLM_MODE=stub docker compose up -d
# Pipeline läuft mit deterministischen Stub-Antworten,
# Persona/Quote-Output ist fix, aber alle Layer werden durchlaufen.
```

## Erwartete Befunde im Report (zur Plausibilitäts-Prüfung)

Wenn Agora sauber läuft, sollten folgende Themen im Report auftauchen
(ohne dass du sie im Prompt explizit nennen musst):

- **Werkstatt-Personas:** Spaltung zwischen IG-Metall-Linie (Pforr-Typ,
  skeptisch wegen 10-Stunden-Tag-Risiko) und jüngerer Generation
  (Krasniqi-Typ, Karriere-Argument).
- **Vertrieb:** Bauer-Typ wird als Friction-Point auftauchen — „Freitag
  ist Auftragstag", Punkt.
- **Stammkunden:** Wahlster-Typ (Tier-1, Pönale-Drohung) vs. Mörth-Typ
  (Österreich-KV-Erfahrung, supportiv) als zwei klar unterscheidbare
  Cluster.
- **Wettbewerb:** Spitzwieser-Typ als „Konkurrent freut sich"-Stimme —
  sollte als Trust-Signal auf Heinrich-Seite gewertet werden, nicht als
  neutrale Position.
- **Recommendation-Cluster:** Vertriebs-Rumpf-Crew Freitag, Pilot in
  Verwaltung, IG-Metall-Mediation früh ins Boot.

Wenn der Report stattdessen Generika liefert („Stakeholder sehen Chancen
und Risiken"), ist die Prompt-Semantik kaputt — sehr direkter Hinweis
auf Layer-2-Drift.

## Kosten-Schätzung

| Modus | LLM-Kosten | Wallclock |
|---|---|---|
| Stub (`AGORA_E2E_LLM_MODE=stub`) | 0 EUR | ~ 25 Sek |
| Lokal Ollama (qwen3-coder:30b) | 0 EUR | ~ 8 Min, GPU-load |
| Cloud Qwen3-Coder (256k) | ~ 0,15 EUR | ~ 4 Min |
| Cloud Gemini 3 Flash | ~ 0,08 EUR | ~ 3 Min |
| Cloud Claude Sonnet 4.6 | ~ 0,90 EUR | ~ 5 Min |

Für „mal gucken ob alles läuft" → **Variante A mit Gemini 3 Flash** oder
**Variante C mit Stub**.
