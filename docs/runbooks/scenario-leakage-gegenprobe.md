# Runbook: Gegenprobe Testfall-Leakage (#1240, Slice 6.4)

**Zweck:** messen, wie viel eines Reports aus dem Testfall selbst stammt — aus
Konstruktionsnotizen, Fragestellung oder erwarteten Ergebnissen — statt aus
der Simulation. Seit #1240 stützt solcher Text keinen Claim mehr und ist in der
Tool-Ausgabe als „Vorgabe des Testfalls – kein Simulationsbefund"
gekennzeichnet. Voraussetzung ist, dass die Textsorte beim Upload stimmt.

## Textsorten

| Rolle | Wofür | Stützt Claims |
|---|---|---|
| `domain_fact` (Default) | Fallbeschreibung und Domänenfakten, auch das geplante Vorhaben selbst | ja |
| `background` | Hintergrundmaterial ohne Fallbezug | ja |
| `scenario_statement` | Konstruktionsnotiz über den Testfall („Der Fall ist so gebaut, dass …") | nein |
| `requirement` | Fragestellung / Auftrag an die Simulation („Simuliere …") | nein |
| `expected_result` | Erwartete Ergebnisse, Lösungsschlüssel | nein |

Die Fallbeschreibung ist **keine** Konstruktionsnotiz. Wer sie als
`scenario_statement` markiert, nimmt dem Report alle echten Fakten.

## Gegenprobe fahren (lokal, braucht Neo4j und LLM)

1. Seed in getrennte Dateien schneiden: Fallbeschreibung, Konstruktionsnotizen,
   Auftrag, erwartete Ergebnisse. Vorbild: `docs/test-seeds/ki-azubi-match-dortmund/`
   (`seed_document.md`, `prompt.md`, `erwartungshorizont.md`).
2. Im Dashboard alle Dateien hochladen und je Datei die Textsorte wählen
   (API: Formularfeld `document_roles` als JSON-Liste in Upload-Reihenfolge).
3. Simulation und Report wie gewohnt fahren.
4. Auswerten:

   ```bash
   cd backend
   uv run python scripts/evidence_role_audit.py <data>/reports/<report_id>/evidence_map.json
   ```

   Erwartung: `supporting_bindings_by_role` enthält keine der drei nicht
   stützenden Rollen, `claims_supported_only_by_testcase_text` ist 0.
   `testcase_share` misst, wie viel des abgerufenen Seed-Materials Testfall-Text war.
5. Gegenlauf mit demselben Seed **ohne** Meta-Dateien: Kernaussagen, die dort
   verschwinden, stammten aus dem Testfall.

## Messung an vorhandenen Artefakten (Stand 2026-09-25)

Das Seed des KI-Lernassistent-Laufs liegt nicht im Repo, und beide Reports
wurden aus **einer** Datei (`agora_testfall_ki-lernassistent-umschulung`)
erzeugt. Die Rolle je Dokument hätte dort nicht getrennt; Evidence trägt kein
`document_role`. Gemessen wurde deshalb über eine manuelle Einordnung der
Seed-Snippets (`agora-lauf-20260811-sim_54c1c2a6a875/document-role-labels.json`):

- `requirement`: Imperative an die Simulation („Simuliere …", „Behandle …")
- `expected_result`: Reaktionen von Stakeholdern, die das Seed als feststehendes
  Ergebnis vorwegnimmt und die #1240 als erwartete Ergebnisse belegt
  („Die IHK sieht generierte Übungsaufgaben unkritisch.", „Der Betriebsrat wird
  zustimmen, weil …", „Honorarkräfte lehnen stärker ab …, weil …")
- `scenario_statement`: „der Konflikt Honorarkräfte ↔ Geschäftsführung braucht Gegenrede"
- alles Übrige `domain_fact`

```bash
cd backend
uv run python scripts/evidence_role_audit.py \
  ../agora-lauf-20260811-sim_54c1c2a6a875/report_glm-5.2_9107e3d60b10/evidence_map.json \
  ../agora-lauf-20260811-sim_54c1c2a6a875/report_deepseek_7ce9e4882bae/evidence_map.json \
  --labels ../agora-lauf-20260811-sim_54c1c2a6a875/document-role-labels.json
```

| Report | Seed-Items | davon Testfall-Text | Anteil |
|---|---:|---:|---:|
| glm-5.2 | 14 | 4 (1 Auftrag, 2 Erwartung, 1 Notiz) | 28,6 % |
| deepseek-v4-flash | 12 | 5 (3 Auftrag, 1 Erwartung, 1 Notiz) | 41,7 % |

Beide Läufe hatten 0 validierte Claims, ein Claim-Effekt ist an ihnen also
nicht messbar. Der Befund ist das Retrieval: rund ein Drittel dessen, was der
Report als Seed-Beleg abrief, war Testfall-Text. Der Referenzlauf
`report_40236c4a59f0`, dessen einziger validierter Claim (`claim_20`) an einem
erwarteten Ergebnis hing, liegt nur als Zusammenfassung vor.

**Offen:** der echte Gegenlauf (Schritte 1–5) mit getrenntem Seed. Er braucht
Neo4j, LLM und das Original-Seed und ist im Container nicht fahrbar.
