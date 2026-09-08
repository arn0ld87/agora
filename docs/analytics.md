# Netzwerk-Analytik

**Stand:** 08.09.2026  
**Geprüfte Main-Baseline:** `0c47737f`  
**Code:** `backend/app/services/network_analytics.py` · `GET /api/simulation/<id>/metrics`

Die Netzwerk-Analytik beschreibt Strukturen **innerhalb eines konkreten synthetischen Simulationslaufs**. Sie misst weder reale öffentliche Meinung noch macht sie einen Agora-Lauf insgesamt reproduzierbar.

---

## 1. Kennzahlen

| Kennzahl | Bedeutung |
|---|---|
| `echo_chamber_index` | Anteil verwerteter Interaktionen, die innerhalb derselben erkannten Community bleiben |
| `cluster_count` | Anzahl erkannter Communities |
| `dominant_clusters[]` | Communities, typischerweise nach Größe sortiert |
| `bridge_agents[]` | Agenten mit hoher Betweenness, die mindestens eine clusterübergreifende Verbindung besitzen |
| `total_agents` | Agenten, die im projizierten Interaktionsgraphen vorkommen |
| `total_interactions` | Anzahl der für die Projektion verwerteten gerichteten Interaktionen |

`total_agents` ist nicht zwingend identisch mit der konfigurierten Persona-/Agentenzahl: Agenten ohne verwertete Interaktion können im Analysegraph fehlen.

---

## 2. Welche Aktionen zählen

Die Analyse verwendet paarweise Interaktionen, also Aktionen mit einem identifizierbaren Sender und Empfänger.

Broadcast-/No-op-Aktionen wie `CREATE_POST` oder `DO_NOTHING` erzeugen keine Sender→Empfänger-Kante und werden deshalb nicht wie eine direkte Interaktion behandelt.

Die konkrete Action-Whitelist und Target-ID-Auflösung sind im Code führend. Bei OASIS-Upgrades oder neuen ActionTypes muss die Analytik dagegen geprüft werden; ein neuer Action-Name zählt nicht automatisch sinnvoll in denselben Graph.

Self-Interaktionen (`src == tgt`) werden verworfen.

---

## 3. Graphprojektion

Die verwerteten Interaktionen werden für Community-/Bridge-Analyse zu einem gewichteten, ungerichteten Graphen aggregiert.

Eine Kante repräsentiert damit die Interaktionsstärke zwischen zwei Agenten, unabhängig von der Richtung einzelner Aktionen.

Diese Projektion ist eine bewusste Heuristik:

- gut für Community-/Bridge-Struktur,
- nicht geeignet, um Richtung/Initiator einer Beziehung direkt abzulesen.

Wer gerichtete Einfluss- oder Antwortketten untersuchen will, braucht die Rohaktionen bzw. eine andere Projektion.

---

## 4. Community Detection

Die aktuelle Implementierung verwendet NetworkX-Louvain mit einem festen Algorithmus-Seed.

Wichtig zur Begrifflichkeit:

> Der feste Seed macht **diesen Clustering-Schritt auf identischer Eingabe** deterministischer. Er macht weder die vorausgehende Multi-Agenten-Simulation noch den Report insgesamt reproduzierbar.

Die offene Gesamt-Reproduzierbarkeit wird unter #763/#1274 verfolgt.

Cluster-IDs sind Implementierungs-/Laufartefakte und keine fachlich stabilen Identitäten über unterschiedliche Simulationen hinweg.

---

## 5. Echokammer-Index

Konzeptuell:

```text
intra = Interaktionen, deren Endpunkte im selben Cluster liegen
total = alle verwerteten Interaktionen
echo_chamber_index = intra / total
```

Interpretation:

- nahe `1.0`: Interaktionen bleiben überwiegend innerhalb erkannter Communities,
- nahe `0.0`: viele Interaktionen verlaufen clusterübergreifend.

Aber:

- bei nur einer Community ist der Wert strukturell hoch/trivial,
- ein hoher Wert ist kein Beweis realer gesellschaftlicher Polarisierung,
- das Ergebnis hängt von simulierten Aktionen, Community-Algorithmus und Projektion ab.

Immer zusammen mit `cluster_count`, Interaktionsmenge und dem Laufkontext lesen.

---

## 6. Bridge Agents

Ein Bridge-Kandidat braucht:

1. einen hohen Betweenness-Wert und
2. mindestens einen Nachbarn außerhalb der eigenen Community.

Damit wird ein reiner interner Hub nicht automatisch als „Bridge“ bezeichnet.

Auch hier gilt: Das ist eine Eigenschaft des **simulierten Interaktionsgraphen**, keine Aussage über die reale Person/Organisation, aus der eine Persona abgeleitet wurde.

---

## 7. API

```text
GET /api/simulation/<simulation_id>/metrics
```

Optionale Filter wie Zeitfenster/Plattform sind im aktuellen API-/Contract-Code führend. Siehe [`api.md`](api.md) für die Route und die Contracts für die genaue Response-Form.

Für Exporte existiert zusätzlich der in `api.md` dokumentierte Metrics-Exportpfad.

---

## 8. Datenqualität

Die Netzwerkmetrik ist nur so gut wie die zugrunde liegenden Aktionen.

Bekannte Trust-Themen der Simulation:

- Role Leakage / Persona-Konsistenz (#1323),
- Twitter-Recommender-/Ranking-Reproduzierbarkeit (#1236),
- Persona-/Entitätskohärenz (#1470/#1471).

Wenn die Simulation systematisch falsche Rollen oder Interaktionen erzeugt, kann die Netzwerkanalyse diese Fehler sehr ordentlich quantifizieren. Ordentlich quantifizierter Unsinn bleibt allerdings Unsinn.

---

## 9. Vergleich zwischen Läufen

Für Vergleiche möglichst konstant halten:

- Eingabedaten,
- Persona-/Agentenzahl,
- Plattform,
- Rundenanzahl,
- Routing/Modelle,
- Agent-Tools/Feature Flags,
- Analytics-Codeversion.

Bis vollständige Run-Manifeste/Replay (#763/#1274) vorliegen, Vergleichsergebnisse nicht als streng kontrolliertes Experiment verkaufen.

---

## 10. Erweiterungen

Sinnvolle spätere Erweiterungen sind:

- Zeitreihen pro Runde,
- getrennte gerichtete und ungerichtete Projektionen,
- Action-Typ-Gewichtungen mit begründeter fachlicher Semantik,
- Unsicherheits-/Stabilitätsanalyse über mehrere Läufe,
- Verknüpfung mit vollständig reproduzierbaren Run-Manifests.

Neue Metriken brauchen eine dokumentierte Interpretation und einen Test gegen triviale/degenerierte Fälle. Eine Zahl allein ist noch keine Analyse.
