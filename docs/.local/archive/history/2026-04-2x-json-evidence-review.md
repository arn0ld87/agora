> **HISTORISCHER SNAPSHOT (Stand 2026-04-2x).**
>
> Aktueller Stand siehe:
> - Architektur & Plan: `CLAUDE.md` / `PLAN.md` / `plan.heuristic.md`
> - Test-Status: `docu/STATUS.md`
> - Diese Datei wurde aus dem Repo-Root nach `docu/history/` verschoben.
>
---

| Vertrauenswürdigkeit | 3/10 | Confidence wirkt nicht kalibriert |
| Demo-Tauglichkeit | 6/10 | Für Showcase nutzbar, aber nur mit Disclaimer |
| Produktreife | 3/10 | Noch nicht für belastbare Analyseberichte geeignet |

Kritische Findings1. Metriken widersprechen den Actions

Die globalen Metriken melden:  
"total\_agents": 0,  
"total\_interactions": 0,  
"cluster\_count": 0,  
"echo\_chamber\_index": 0  
Gleichzeitig enthält die Datei mehrere `simulation_actions` wie:  
`"action_type": "CREATE_COMMENT"`, `"action_type": "CREATE_POST"`, `"action_type": "LIKE_POST"`  
Das ist ein harter Datenkonsistenzfehler.  
Entweder sind die Metriken falsch berechnet, zu früh erzeugt oder stammen aus einem anderen Snapshot.2. Claims bekommen offenbar denselben Evidence-Block

Mehrere unterschiedliche Claims enthalten nahezu dieselbe Evidence-Liste. Dadurch wirkt die Belegstruktur formal sauber, ist aber inhaltlich nicht claim-spezifisch.

**Problem:**  
Ein Claim über konkrete politische Ereignisse, Datum, Ort und Minister wird mit allgemeinen Graph-Facts, globalen Metriken und beliebigen Actions belegt. Das ist kein echtes Evidence-Binding.3. section\_synthesis als Evidence ist zirkulär

Wenn ein Claim durch die eigene generierte Zusammenfassung belegt wird, ist das kein Beleg, sondern eine Selbstbestätigung.

**Problematisch:**  
`"source": "section_synthesis"`, `"type": "model_generated_inference"`  
Das darf höchstens als Herkunft des generierten Textes gelten, aber nicht als belastbare Evidence.4. Confidence ist nicht glaubwürdig kalibriert

Viele Claims haben:  
`"confidence_score": 0.95`, `"confidence_label": "high"`  
Auch Überschriften wie:  
**Der Beschluss und seine Architekten**  
werden als Claim mit hoher Confidence behandelt. Das ist ein klares Zeichen, dass Claim Extraction und Confidence Scoring noch zu grob sind.5. Überschriften werden als Claims behandelt

Eine Markdown-Überschrift ist kein überprüfbarer Claim. Sie sollte nicht in der Evidence-Map landen.

**Filter-Regel:**  
def is\_claim(text: str) \-\> bool:  
    stripped \= text.strip()  
    if stripped.startswith("\#"):  
        return False  
    if stripped.startswith("\*\*") and stripped.endswith("\*\*") and len(stripped.split()) \< 8:  
        return False  
    return any(token in stripped.lower() for token in \[ ".", "soll", "ist", "wird", "beschloss", "fordert" \])  
6\. Action Logs sind noch keine Analyse-Evidence

Eine Action wie `LIKE_POST` ist nützlich, aber nicht direkt ein Beleg für einen komplexen Report-Claim. Daraus muss erst ein normalisiertes Behavioral-Evidence-Objekt entstehen.

**Besseres Modell:**  
{  
  "type": "agent\_behavior",  
  "actor\_id": 14,  
  "actor\_name": "Gesamtschule Brünninghausen",  
  "action": "LIKE\_POST",  
  "target\_type": "post",  
  "target\_id": 3,  
  "stance": "supportive",  
  "round": 11,  
  "content\_ref": "post:3",  
  "confidence": 0.72  
}  
Empfohlene Fix-ReihenfolgePR 1: Metrik-Snapshot reparieren

**Ziel:** Keine globalen Metriken exportieren, wenn sie offensichtlich leer oder widersprüchlich sind.  
**Akzeptanzkriterien:**

* `total_agents > 0`, wenn `simulation_actions` Agenten enthalten  
* `total_interactions > 0`, wenn `CREATE_COMMENT`, `CREATE_POST`, `LIKE_POST` existieren  
* `cluster_count=0` nur zulassen, wenn wirklich keine Interaktionsgraph-Kanten existieren  
* Snapshot-ID und Berechnungszeitpunkt speichern

PR 2: Claim Extraction härten

**Ziel:** Nur prüfbare Aussagen als Claims aufnehmen.  
**Regeln:**

* Überschriften ignorieren  
* reine Übergangssätze ignorieren  
* Claims atomarisieren  
* ein Claim \= eine überprüfbare Aussage

PR 3: Evidence-Binding claim-spezifisch machen

**Ziel:** Jeder Claim bekommt nur Evidence, die semantisch zu diesem Claim passt.

**Minimaler Algorithmus:**  
def bind\_evidence\_to\_claim(claim, candidates, embedder, threshold=0.72):  
    claim\_vec \= embedder.embed(claim\["claim\_text"\])  
    scored \= \[\]  
    for item in candidates:  
        text \= " ".join(\[  
            str(item.get("snippet", "")),  
            str(item.get("raw", "")),  
            str(item.get("value", ""))  
        \])  
        score \= cosine\_similarity(claim\_vec, embedder.embed(text))  
        if score \>= threshold:  
            scored.append({  
                \*\*item,  
                "match\_score": round(score, 3\)  
            })  
    return sorted(scored, key=lambda x: x\["match\_score"\], reverse=True)\[:5\]  
PR 4: Self-Evidence verbieten

**Regel:**  
FORBIDDEN\_EVIDENCE\_TYPES \= { "model\_generated\_inference", "section\_synthesis" }

def is\_allowed\_evidence(item):  
    return item.get("type") not in FORBIDDEN\_EVIDENCE\_TYPES  
Diese Quellen dürfen im Audit-Trail bleiben, aber nicht als Beleg zählen.PR 5: Confidence neu berechnen

Confidence darf nicht aus Bauchgefühl oder Prompt-Magie kommen.

**Vorschlag:**  
`confidence_score = 0.40 * evidence_relevance + 0.25 * source_quality + 0.20 * evidence_specificity + 0.15 * consistency_score - contradiction_penalty`

**Labels:**  
| Score | Label |  
|---|---|  
| 0.00-0.39 | low |  
| 0.40-0.69 | medium |  
| 0.70-0.89 | high |  
| 0.90-1.00 | verified |

`verified` nur erlauben, wenn direkte, claim-spezifische Evidence existiert.Empfohlenes JSON-Zielschema  
{  
  "report\_id": "report\_x",  
  "simulation\_id": "sim\_x",  
  "schema\_version": 2,  
  "metrics": {  
    "snapshot\_id": "metrics\_x",  
    "calculated\_at": "2026-05-01T04:59:23Z",  
    "total\_agents": 18,  
    "total\_interactions": 42,  
    "cluster\_count": 3,  
    "echo\_chamber\_index": 0.31  
  },  
  "claims": \[  
    {  
      "claim\_id": "claim\_001",  
      "text": "Das Fach KIDM soll ab 2027/28 verpflichtend eingeführt werden.",  
      "claim\_type": "timeline",  
      "confidence\_score": 0.68,  
      "confidence\_label": "medium",  
      "evidence": \[  
        {  
          "evidence\_id": "ev\_001",  
          "type": "graph\_fact",  
          "source": "panorama\_search",  
          "snippet": "NRW announces ...",  
          "match\_score": 0.81,  
          "supports\_claim": true,  
          "raw\_ref": {  
            "node\_id": "node\_123",  
            "edge\_id": "edge\_456",  
            "log\_line": 187  
          }  
        }  
      \],  
      "warnings": \[  
        "No direct source for exact date found"  
      \]  
    }  
  \]  
}  
Harte Wahrheit

Agora ist als Idee deutlich stärker als der aktuelle Evidence-Export.  
Der aktuelle Report sieht so aus, als hätte er Quellenarbeit. Tatsächlich ist es eher ein dekorierter Report mit Evidence-Anmutung. Das ist für eine Demo okay, aber für ein Tool, das Vertrauen erzeugen soll, gefährlich.  
Die gute Nachricht: Das Problem ist lösbar. Nicht durch bessere Prompts, sondern durch saubere Datenpipeline:

1. saubere Metrik-Snapshots  
2. atomare Claim Extraction  
3. echtes Claim-to-Evidence Matching  
4. kalibrierte Confidence  
5. keine selbstgenerierten Inhalte als Beleg

Nächste Schritte

1. Metrik-Export fixen: `total_agents`, `total_interactions`, `cluster_count` gegen echte Actions und Graph-Kanten validieren.  
2. Claim Extraction härten: Überschriften raus, lange Claims atomarisieren, nur prüfbare Aussagen exportieren.  
3. Evidence-Binding neu bauen: Jeder Claim bekommt nur semantisch passende Evidence mit `match_score`, keine globalen Belegeimer mehr.
