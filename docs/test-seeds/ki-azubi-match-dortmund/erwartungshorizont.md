# Erwartungshorizont — KI-Azubi-Match Dortmund

> Dieses Dokument beschreibt die erwarteten Ergebnisse eines Agora-Laufs mit dem
> Seed-Dokument `seed_document.md` aus demselben Ordner. Es dient als Prüfstein:
> Abweichungen zeigen systematische Schwächen in der Pipeline.

## 1. Erwartete Entitäten (NER-Phase)

Das Seed-Dokument enthält folgende klar identifizierbare Entitäten. Hinweis: Die NER
erfindet ihr Typvokabular pro Lauf neu (CONTEXT.md §1), daher sind hier die **inhaltlich
erwarteten** Entitäten gelistet, nicht die Typbezeichnungen.

### Personen (sollten Personas werden)
| Name | Rolle | expected_type (ca.) |
|---|---|---|
| Dr. Sarah Kling | Stabsstelle Digitalisierung | Person/Stakeholder/Representative |
| Thomas Bergmann | IHK-Hauptgeschäftsführer | Person/Stakeholder/Representative |
| Prof. Dr. Markus Jensen | TU Dortmund | Person/Academic/Researcher |
| Elena Richter | Dortmund Digital e. V. | Person/Stakeholder/Vereinsvorsitzende |
| Jessica Nowak | DGB-Jugend | Person/Stakeholder/Gewerkschaft |
| Martina Fuchs | Berufskolleg | Person/Stakeholder/Schulleitung |

### Organisationen (sollten NICHT als Personas auftauchen — blocklist check)
| Entität | Typ-Erwartung |
|---|---|
| IHK Dortmund | Organization/Institution |
| Stadt Dortmund | Organization/Government |
| TU Dortmund | Organization/University |
| Dortmund Digital e. V. | Organization/Association |
| DGB-Jugend | Organization/Union |
| Berufskolleg 1 | Organization/School |

### Konzepte / Orte (sollten von Blocklist gefangen werden)
| Entität | expected_type | INELIGIBLE_ENTITY_TYPES? |
|---|---|---|
| Dortmund | city | Ja → keine Persona |
| NRW | region/state | Ja → keine Persona |
| Österreich | country | Ja → keine Persona |

### Erwartung Persona-Eligibility-Log (CONTEXT.md §1, §2)
- 6 Personen-Entitäten sollten als Persona-Kandidaten erkannt werden
- Organisationen können auftauchen, wenn die NER sie als Personen klassifiziert
  (häufig bei „IHK Dortmund“ als `Organization`)
- Unbekannte entity_types werden konservativ zugelassen → Log-Meldung
  `ausserhalb der bekannten Liste und werden konservativ zugelassen`

## 2. Simulationsdynamik (erwartete Konfliktlinien)

Auf beiden Plattformen (Twitter, Reddit) sollten sich folgende Mikro-Konflikte
in Posts und Kommentaren manifestieren:

| Konflikt | Pro | Contra |
|---|---|---|
| KI vs. Mensch | Dr. Kling, Bergmann (bedingt) | Jessica Nowak, Martina Fuchs |
| Effizienz vs. Diskriminierung | Dr. Kling, Jensen (bedingt) | Nowak, Fuchs |
| Kosten KI vs. Kosten Personal | Bergmann, Richter | Nowak |
| Open Source vs. Proprietär | Elena Richter | Dr. Kling (implizit) |
| Datenschutz vs. Nutzen | Nowak, Fuchs | Kling, Bergmann (bedingt) |

**Zu prüfen:** Bilden sich mindestens 3 dieser Konfliktlinien in der Simulation ab?
Bei Fehlen mehrerer Konfliktlinien liegt ein Problem in der initial_posts-Konfiguration
oder im Recruiting vor.

## 3. Erwartete Evidence-Verteilung (Report-Phase)

### Evidence-Typen (sollten alle vorkommen)

| Typ | Erwartung | Prüfhinweis |
|---|---|---|
| `agent_interview` | Größter Beitrag (6 Personas × 2 Plattformen) | CONTEXT.md §2 — Viele Frage-Echos erwarten |
| `seed_document` | Sollte VORKOMMEN, nicht notwendigerweise häufig | Anker müssen auflösbar sein (`seed_doc:<id>#chunk:<n>`) |
| `graph_relation` | Mittel (Fakten aus dem Graph-Retrieval) | Gekoppelt an Jensen-Studie, Kosten, Zeitplan |
| `agent_action` | Wenig (Simulation produziert viele Aktionen, aber nur wenige werden als Evidence gebunden) | CONTEXT.md §3 |
| `graph_metric` | Kaum bis gar nicht | Echo-Chamber-Index etc. |

### Claims und Hypothesen

| Section | Erwartete Claims (ca.) | Erwartete Hypothesen |
|---|---|---|
| Stakeholder-Übersicht | 4–6 | 1–3 |
| Effizienzargument | 3–5 | 0–2 |
| Diskriminierungsrisiko | 4–7 | 1–3 |
| Rechtlicher Rahmen | 2–4 | 1–2 |
| Internationale Erfahrung | 3–4 | 0–1 |
| Gesamt | 16–26 | 3–11 |

**Prüfhinweis:** Seed-Dokument enthält 4 Tabellenzeilen mit konkreten Zahlen
(Internationale Erfahrungen) — diese sollten zu `verify_prose`-Prüfungen führen
(CONTEXT.md §3: „nur Sätze mit einer Zahl“).

## 4. Spezifische Risiken und Fallstricke (aus CONTEXT.md)

### 4.1 Frage-Echo (§2)
Erwartet: Mindestens 2 Personas teilen im Interview dieselbe Frage-Formulierung
im Antwort-String. Das ist kein Defekt, aber ein Qualitätsmerkmal der Rohdaten.

**Prüfung:** `agent_log.jsonl` nach `"Welcher Moment"` oder ähnlichen
Frage-Wiederholungen durchsuchen.

### 4.2 Rollenübernahme (§2)
Erwartet: Jessica Nowak (DGB) könnte als „Betriebsrätin“ antworten, obwohl sie
Gewerkschaftssekretärin ist. Thomas Bergmann könnte als „IHK-Präsident“ statt
Hauptgeschäftsführer auftreten.

**Prüfung:** Gibt es Antwort-Präfixe wie „Als Betriebsrat…“ oder „Als Vorstand…“?
Das wäre ein Hinweis auf das bekannte Rollenübernahme-Phänomen.

### 4.3 Zitat ≠ Simulationsäußerung (§2)
Erwartet: Zitate im Report stammen primär aus Interviews, nicht aus der Simulation.
Wer das Feed nach Zitaten durchsucht, wird sie dort nicht finden.

**Prüfung:** Zitat aus Report nehmen und gegen `reddit_simulation.db.posts.content`
und `twitter_simulation.db.posts.content` matchen — sollte kein Treffer sein.

### 4.4 seed_doc:-Anker mit Laufzeitprüfung (§3)
Erwartet: Mindestens ein `seed_doc:`-Anker im Evidence-Index im Format
`seed_doc:<id>#chunk:<n>`, der gegen `known_anchors` auflösbar ist.
Nicht auflösbare Anker setzen `QuoteValidationResult.valid` auf `False`
und lösen einen zweiten ReAct-Durchlauf für die Section aus.

**Prüfung:** Im `evidence_map.json` nach `seed_doc:` suchen — das Format
muss `#chunk:` enthalten, sonst schlägt `_SEED_DOC_ANCHOR_RE` fehl.

### 4.5 verify_prose beschränkt sich auf Zahlen (§3)
Erwartet: Nur Sätze mit konkreten Zahlen werden von `verify_prose` geprüft.
Das Seed-Dokument enthält viele Aussagen ohne Zahl („Ein Algorithmus kann in
Sekunden...") — diese werden nicht geprüft und bleiben im Bericht.

**Prüfung:** Der Bericht enthält Text ohne Zahlen, der nie verifiziert wurde.
Das ist systemkonform, kein Defekt.

### 4.6 Auswertungsfalle: Reposts (§4)
Erwartet: In der Simulation gibt es Reposts mit leerem `content` und gesetztem
`original_post_id`. Ohne Filter `original_post_id IS NULL` sieht die Statistik
nach Mode-Collapse aus.

**Prüfung:** `SELECT content FROM posts WHERE content = ''` liefert Treffer.
Bei Auswertung `WHERE original_post_id IS NULL` filtern.

## 5. Erwartete Report-Qualität

| Kriterium | Erwartung | Toleranz |
|---|---|---|
| Sections | 5–7 | ±1 |
| Gesamtlänge | 800–1.500 Wörter | ±300 |
| Claims gesamt | 16–26 | ±5 |
| Davon `high`/`verified` | 12–19 | ±4 |
| Davon `medium` | 3–6 | ±2 |
| Davon `low` | 1–4 | ±2 |
| Hypothesen gesamt | 3–11 | ±3 |
| Data Gaps | 0–3 | — |
| Ungehedgte Claims (Frage-Echo) | ≤ 30 % aller Claims | Risikokennzahl |

## 6. Akzeptanzkriterien für den Testlauf

Ein Testlauf gilt als **erfolgreich**, wenn:

- [ ] Mindestens 4 der 6 Personen-Entitäten als Personas erscheinen
- [ ] Die Simulation auf beiden Plattformen (Reddit + Twitter) mehr als 50 Aktionen erzeugt
- [ ] Mindestens 3 der 5 erwarteten Konfliktlinien sichtbar sind
- [ ] Mindestens 3 der 5 Evidence-Typen im `evidence_index` auftauchen
- [ ] Der Report 5–7 Sections enthält
- [ ] `verify_prose` mindestens einen Satz mit Zahl geprüft hat
- [ ] `seed_doc:`-Anker im `evidence_index` vorhanden und im Format `seed_doc:<id>#chunk:<n>` auflösbar sind

Ein Testlauf gilt als **auffällig**, wenn:

- [ ] Weniger als 3 Personas generiert werden (NER-Problem)
- [ ] Eine Plattform überhaupt keine Posts zeigt (Simulationsproblem)
- [ ] Der Report keine Hypothesen enthält (keine Prüfung erfolgt)
- [ ] Alle Claims auf `low` oder alle auf `verified` (Validator-Problem)
- [ ] Die Simulation weniger als 20 Aktionen erzeugt (Recsys-/Agentenproblem)

---

*Erwartungshorizont erstellt am 11.08.2026, basierend auf CONTEXT.md §1–8 und
ADR-0013. Gültig für Agora ≥ 0.9.5.*
