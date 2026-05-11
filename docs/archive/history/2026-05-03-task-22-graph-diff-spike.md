# Task 22 — Graph-Diff Modell und API (Spike #74)

**Datum:** 2026-05-03  
**Status:** Spike — Spezifikation, kein Code-Commit  
**Closes:** #74  
**Vorbedingung für:** #76 (Graph-Diff-UI)

---

## 1. Ziel & Scope

Zwei Snapshots eines Netzwerk-Graphs (z. B. zwei verschiedene Branches einer Simulation oder zwei unterschiedliche Simulationsrunden) sollen auf Unterschiede hin verglichen werden. Ein Snapshot ist ein Graph-Zustand an einem bestimmten Punkt (z. B. nach Round N). Ziel: Identifikation von Unterschieden in Knoten-Eigenschaften, Kanten-Struktur und Cluster-Zusammensetzung.

**Was wird verglichen:**
- Graph Snapshot A und Graph Snapshot B (beide vollständig geladen aus Neo4j oder Simulation-Cache)
- Edge-Übergänge (hinzugefügt, gelöscht, verstärkt, geschwächt)
- Node-Eigenschaften (Entity-Drift, z. B. Cluster-Wechsel, Sentiment-Änderung)
- Cluster-Struktur (neue Cluster, aufgelöste Cluster, Größen-Shifts)
- Aggregierte Metriken pro Graph-Snapshot

**Was wird nicht verglichen:**
- Persona-Profile-Diff (→ Layer 8 #69 Persona-Diff)
- Time-Series über mehrere Rounds (→ Layer 8)
- Multi-Way-Compare (>2 Snapshots) (→ Erweiterung nach Task 22)
- Knoten-Löschen vs. Isolation (strukturelle Unterscheidung → Offen Frage 4)

---

## 2. Vergleichsdimensionen

| Dimension | Beschreibung | Datenquelle | Aggregat | Status |
|---|---|---|---|---|
| **Hinzugefügte Kanten** | Kanten, die in Snapshot B existieren, aber nicht in A. Identität über UUID oder Composite-Key (source_id, target_id, relation_type). | `TemporalGraphService.get_snapshot()` → edges nach Round | Liste von `EdgeData` mit UID, Source, Target, Type, Gewicht | Existiert (Hook in `temporal_graph.py` ab Zeile 102) |
| **Gelöschte Kanten** | Kanten, die in Snapshot A existieren, aber nicht in B. | `TemporalGraphService.get_snapshot()` → edges nach Round | Liste von `EdgeData` | Existiert |
| **Verstärkte Kanten** | Kanten, die in beiden Snapshots existieren, aber in B höheres `reinforced_count` oder Gewicht haben. | `TemporalGraphService.compute_diff()` → reinforced-Block | Liste mit Feld-Tuple `{edge, before_weight, after_weight, delta}` | Existiert (partiell, `.reinforced_count` vorhanden) |
| **Geschwächte Kanten** | Kanten mit sinkendem `reinforced_count` oder Gewicht zwischen A und B. | `TemporalGraphService.compute_diff()` | Liste mit `{edge, before_weight, after_weight, delta}` | Neu — nicht in Code |
| **Node-Property-Drift** | Änderungen an Knoten-Eigenschaften, z. B. Entity-Sentiment, Label, Entity-Type (falls vorhanden). | Neo4j-Query: `MATCH (n) WHERE n in Snapshot A nodes` → Eigenschaften vor/nach | Dict[node_id] → {property_name, before, after} | Neu |
| **Cluster-Zuordnung-Shift** | Agenten, die zwischen Clustern wechseln (z. B. Agent 5 war in Cluster 0, ist jetzt in Cluster 2). Basiert auf erneuter Louvain-Analyse pro Snapshot. | `NetworkAnalyticsService.compute_metrics()` → dominant_clusters mit Member-Agenten | Liste {agent_id, cluster_a_id, cluster_b_id, cluster_a_label, cluster_b_label} | Neu |
| **Neue / Aufgelöste Cluster** | Cluster, die nur in B existieren (neu) oder nur in A existieren (aufgelöst). Matching über Semantic-Ähnlichkeit (Label-Ähnlichkeit) oder strikter Cluster-ID. | `NetworkAnalyticsService` output → dominant_clusters | {new: [ClusterSummary], removed: [ClusterSummary]} | Neu (partiell — Hook in Task 23 vorhanden) |
| **Density-Delta** | Dichte-Unterschied: (Kanten-Count in B) / (Max-Kanten) - (Kanten-Count in A) / (Max-Kanten). Indikator für Netzwerk-Verdichtung. | `TemporalGraphService` → edge_count, Node-Count → Dichte | float (signed delta) | Neu |
| **Betweenness-Centrality-Shift** | Agent mit hohem Betweenness wandert aus/in Top-k-Bridge-Agenten-Liste. Ändert Vermittler-Struktur. | `NetworkAnalyticsService.bridge_agents` | {joined: [agent_id], left: [agent_id]} pro Threshold-Tier | Neu |

---

## 3. Datenmodell (Pseudocode)

```python
# Graph-Diff-Antwort (Pseudocode, kein .py-Datei)

class EdgeData(BaseModel):
    """Edge-Metadaten mit eindeutigem Identifikator."""
    uuid: str                           # Eindeutige Kanten-ID aus Neo4j
    source_id: str | int                # Quell-Knoten (Agent/Entity)
    target_id: str | int                # Ziel-Knoten
    relation_type: str                  # z. B. "FOLLOWS", "LIKES_COMMENT", "OPPOSES"
    weight: float | None                # Optionales Gewicht / Stärke
    reinforced_count: int | None        # Häufigkeit, mit der Kante verstärkt wurde
    properties: Dict[str, Any]          # Weitere Metadaten


class NodePropertyShift(BaseModel):
    """Eigenschafts-Änderung an einem Knoten."""
    node_id: str | int
    node_label: str                     # z. B. "Agent", "Entity"
    property_name: str                  # z. B. "sentiment", "cluster_id"
    before: Any
    after: Any


class ClusterShift(BaseModel):
    """Agent wechselt zwischen Clustern."""
    agent_id: int
    cluster_a_id: int
    cluster_a_label: str
    cluster_b_id: int
    cluster_b_label: str
    cluster_a_size: int                 # Cluster-Größe in A
    cluster_b_size: int                 # Cluster-Größe in B


class BridgeAgentShift(BaseModel):
    """Betweenness-Centrality-Status-Wechsel."""
    agent_id: int
    action: str                         # "joined_top_k" | "left_top_k"
    centrality_before: float | None
    centrality_after: float | None
    tier: str | None                    # Optional: Ranking-Tier


class ClusterSummary(BaseModel):
    """Cluster-Zusammenfassung."""
    cluster_id: int
    size: int
    label: str                          # Deterministisches TF-Top-3-Label
    member_count: int                   # Anzahl Agenten in Cluster


class GraphSnapshot(BaseModel):
    """Graph-Zustand an einem Punkt (Snapshot)."""
    graph_id: str
    round_num: int | None               # Falls rund-basiert; sonst None
    snapshot_id: str | None             # UUID oder eindeutiger Snapshot-Key
    created_at: datetime
    node_count: int
    edge_count: int
    edges: List[EdgeData]
    density: float                      # edge_count / (node_count * (node_count - 1))
    cluster_count: int
    dominant_clusters: List[ClusterSummary]  # Top-k Cluster
    bridge_agents: List[int]            # Top-k Agenten mit Betweenness


class GraphDiffMetrics(BaseModel):
    """Aggregierte Metriken über den Diff."""
    total_edges_added: int
    total_edges_removed: int
    total_edges_reinforced: int
    total_edges_weakened: int
    avg_reinforcement_delta: float      # Durchschnittlicher Gewichts-Anstieg bei verstärkten
    avg_weakening_delta: float          # Durchschnittlicher Gewichts-Rückgang
    density_delta: float                # Signed: B_density - A_density
    node_properties_changed: int        # Anzahl Knoten mit mindestens einer Eigenschafts-Änderung
    agents_changed_clusters: int        # Anzahl Agenten, die Cluster wechselten
    clusters_new: int                   # Neu hinzugekommene Cluster
    clusters_removed: int               # Aufgelöste Cluster
    bridge_agents_joined: int           # Neue Bridge-Agenten
    bridge_agents_left: int             # Nicht mehr in Top-k


class GraphDiff(BaseModel):
    """Vollständiger Diff zwischen zwei Graph-Snapshots."""
    
    # Metadaten
    graph_id: str
    snapshot_a_id: str
    snapshot_b_id: str
    created_at: datetime
    comparison_type: str                # z. B. "round-to-round", "branch-diff"
    
    # Snapshots
    snapshot_a: GraphSnapshot
    snapshot_b: GraphSnapshot
    
    # Kanten-Diffs
    edges_added: List[EdgeData]
    edges_removed: List[EdgeData]
    edges_reinforced: List[Dict]        # {edge, before: {weight, reinforced_count}, after: {...}}
    edges_weakened: List[Dict]          # dto.
    
    # Knoten-Property-Diffs
    node_properties_changed: List[NodePropertyShift]
    
    # Cluster-Diffs
    cluster_shifts: List[ClusterShift]  # Agenten, die Cluster wechselten
    clusters_new: List[ClusterSummary]
    clusters_removed: List[ClusterSummary]
    
    # Bridge-Agent-Diffs
    bridge_agent_shifts: List[BridgeAgentShift]
    
    # Aggregierte Metriken
    metrics: GraphDiffMetrics
```

**Feldtypen / Semantik:**
- `float`: Floats mit 2–4 Dezimalstellen (ROUND in API-Response)
- `uuid` / Identifikatoren: String (UUID oder numerisch, je nach Neo4j-Schema)
- `List[EdgeData]`: Alle Kanten werden vollständig serialisiert (kein `...`-Platzhalter)
- Alle `before`/`after`-Felder: Semantik muß konsistent sein (z. B. Gewicht immer Dezimal, `reinforced_count` immer int)

---

## 4. API-Schnitt (Skizze)

### Endpoint-Pfad

Option A (bevorzugt, konsistent mit Task 23):
```http
GET /api/simulation/<sim_id>/graph-diff?branch_a=<id>&branch_b=<id>
```

Option B (Graph-zentriert):
```http
GET /api/graph/<graph_id>/diff?snapshot_a=<id>&snapshot_b=<id>
```

**Begründung für Option A:** Konsistenz mit `/api/simulation/{sim_id}/compare` (Task 23). Graph-Diffs sind meist im Simulationskontext interessant (zwei Branches = zwei Graph-Varianten).

### Anfrage

**Query-Parameter:**
- `branch_a` (erforderlich): ID des ersten Branch (oder Simulation-Round für Round-to-Round)
- `branch_b` (erforderlich): ID des zweiten Branch
- `include_node_properties` (optional, default: `true`): Ob Node-Property-Diffs einbezogen werden
- `include_cluster_shifts` (optional, default: `true`): Ob Agent-Cluster-Shifts einbezogen werden
- `bridge_agent_top_k` (optional, default: `5`): Top-K-Threshold für Bridge-Agent-Detection

**Beispiel:**
```
GET /api/simulation/sim-abc123/graph-diff?branch_a=branch-001&branch_b=branch-002&include_cluster_shifts=true
```

### Antwort (200 OK)

**Content-Type:** `application/json`

**Body Schema:**
```json
{
  "status": "ok",
  "data": {
    "diff": {
      "graph_id": "sim-abc123-graph",
      "snapshot_a_id": "branch-001",
      "snapshot_b_id": "branch-002",
      "created_at": "2026-05-03T14:45:20Z",
      "comparison_type": "branch-diff",
      
      "snapshot_a": {
        "graph_id": "sim-abc123-graph",
        "round_num": null,
        "snapshot_id": "branch-001",
        "created_at": "2026-05-03T14:10:00Z",
        "node_count": 38,
        "edge_count": 127,
        "density": 0.0878,
        "cluster_count": 3,
        "dominant_clusters": [
          {"cluster_id": 0, "size": 18, "label": "energiepolitik, diskurs, europa", "member_count": 18},
          {"cluster_id": 1, "size": 12, "label": "finanzmarkt, handel, europa", "member_count": 12},
          {"cluster_id": 2, "size": 8, "label": "digital, datenschutz, reform", "member_count": 8}
        ],
        "bridge_agents": [5, 12, 18]
      },
      
      "snapshot_b": {
        "graph_id": "sim-abc123-graph",
        "round_num": null,
        "snapshot_id": "branch-002",
        "created_at": "2026-05-03T14:18:45Z",
        "node_count": 41,
        "edge_count": 142,
        "density": 0.0846,
        "cluster_count": 4,
        "dominant_clusters": [
          {"cluster_id": 0, "size": 20, "label": "energiepolitik, fossil, transition", "member_count": 20},
          {"cluster_id": 1, "size": 10, "label": "finanzmarkt, gruen, esg", "member_count": 10},
          {"cluster_id": 2, "size": 6, "label": "digital, blockchain, web3", "member_count": 6},
          {"cluster_id": 3, "size": 5, "label": "klima, migration, sozialpolitik", "member_count": 5}
        ],
        "bridge_agents": [3, 7, 15, 22]
      },
      
      "edges_added": [
        {
          "uuid": "e-9c3d2f15",
          "source_id": 3,
          "target_id": 7,
          "relation_type": "FOLLOWS",
          "weight": 1.0,
          "reinforced_count": 1,
          "properties": {}
        },
        {
          "uuid": "e-7a1b4e8c",
          "source_id": 22,
          "target_id": 5,
          "relation_type": "LIKES_COMMENT",
          "weight": 0.8,
          "reinforced_count": 1,
          "properties": {}
        }
      ],
      
      "edges_removed": [
        {
          "uuid": "e-5f2a1b3c",
          "source_id": 18,
          "target_id": 12,
          "relation_type": "OPPOSES",
          "weight": 0.6,
          "reinforced_count": 2,
          "properties": {}
        }
      ],
      
      "edges_reinforced": [
        {
          "edge": {
            "uuid": "e-2c4f1a9d",
            "source_id": 5,
            "target_id": 12,
            "relation_type": "FOLLOWS",
            "weight": 1.0,
            "reinforced_count": 4,
            "properties": {}
          },
          "before": {"weight": 0.8, "reinforced_count": 2},
          "after": {"weight": 1.0, "reinforced_count": 4},
          "delta": {"weight": 0.2, "reinforced_count": 2}
        }
      ],
      
      "edges_weakened": [],
      
      "node_properties_changed": [
        {
          "node_id": 5,
          "node_label": "Agent",
          "property_name": "sentiment_score",
          "before": 0.62,
          "after": 0.55
        },
        {
          "node_id": 12,
          "node_label": "Agent",
          "property_name": "interaction_count",
          "before": 28,
          "after": 35
        }
      ],
      
      "cluster_shifts": [
        {
          "agent_id": 18,
          "cluster_a_id": 0,
          "cluster_a_label": "energiepolitik, diskurs, europa",
          "cluster_b_id": 2,
          "cluster_b_label": "digital, blockchain, web3",
          "cluster_a_size": 18,
          "cluster_b_size": 6
        }
      ],
      
      "clusters_new": [
        {"cluster_id": 3, "size": 5, "label": "klima, migration, sozialpolitik", "member_count": 5}
      ],
      
      "clusters_removed": [],
      
      "bridge_agent_shifts": [
        {
          "agent_id": 22,
          "action": "joined_top_k",
          "centrality_before": null,
          "centrality_after": 0.42,
          "tier": "top-5"
        },
        {
          "agent_id": 18,
          "action": "left_top_k",
          "centrality_before": 0.38,
          "centrality_after": 0.15,
          "tier": "top-5"
        }
      ],
      
      "metrics": {
        "total_edges_added": 8,
        "total_edges_removed": 2,
        "total_edges_reinforced": 12,
        "total_edges_weakened": 0,
        "avg_reinforcement_delta": 0.22,
        "avg_weakening_delta": 0.0,
        "density_delta": -0.0032,
        "node_properties_changed": 5,
        "agents_changed_clusters": 1,
        "clusters_new": 1,
        "clusters_removed": 0,
        "bridge_agents_joined": 1,
        "bridge_agents_left": 1
      }
    }
  },
  "timing": {
    "compute_ms": 487
  }
}
```

### Error Cases

**404 Not Found** — wenn Simulation, Branch A oder Branch B nicht existiert:
```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "Branch 'branch-002' nicht gefunden in Simulation 'sim-abc123'",
    "details": {
      "simulation_id": "sim-abc123",
      "branch_id": "branch-002"
    }
  }
}
```

**400 Bad Request** — wenn Branches unterschiedliche Netzwerk-Versionen haben (z. B. einmal Louvain-gepuffert, einmal neu):
```json
{
  "status": "error",
  "error": {
    "code": "INCOMPATIBLE_GRAPH_VERSION",
    "message": "Branches haben inkompatible Netzwerk-Clusterings",
    "details": {
      "branch_a_clustering_method": "louvain-v1",
      "branch_b_clustering_method": "louvain-v2",
      "note": "Bitte mit gleicher Netzwerk-Analyse recompute"
    }
  }
}
```

**422 Unprocessable Entity** — wenn einer der Branches unvollständig ist:
```json
{
  "status": "error",
  "error": {
    "code": "INCOMPLETE_GRAPH_STATE",
    "message": "Branch 'branch-001' hat keinen Netzwerk-Snapshot (Graph-Status: INITIALIZING)",
    "details": {
      "branch_id": "branch-001",
      "graph_status": "INITIALIZING",
      "requires": ["COMPLETE"]
    }
  }
}
```

---

## 5. Out of Scope (explizit)

- ❌ **Graph-Diff-UI** — Visualisierung der Edits und Cluster-Shifts (→ Sub-Slice 26 / Task 26, #76)
- ❌ **Implementierung der API** — Design und Spezifikation nur (→ Sub-Slice 22 / Task 22, #74)
- ❌ **Persona-Diff** — z. B. Personas, die zwischen Branches unterschiedliche Traits haben (→ Layer 8, #69)
- ❌ **Multi-Way-Diff** — nur 2 Snapshots (später evtl. Erweiterung)
- ❌ **Round-by-Round-Historik** — Zeitreihe von Diffs (→ Layer 8)
- ❌ **Node-Matching-Intelligenz** — strikte ID-Gleichheit; Semantisches Matching → Offen Frage 3

---

## 6. Offene Fragen für #74/#76

### Design-Entscheidungen

1. **Edge-Identität: UUID vs. Composite-Key**
   - Sollen Kanten über Neo4j-UUID identifiziert werden oder über Composite-Key (source_id, target_id, relation_type)?
   - UUID ist einzigartig, aber Composite-Key ist semantisch verständlicher für Diffs.
   - → Consequence: Performance bei großen Graphs, Fehlerquoten bei Matching.

2. **Cluster-Matching zwischen Snapshots**
   - Zwei Branches haben potentiell unterschiedliche Cluster-IDs für ähnliche Communities (z. B. beide mit Label „energiepolitik, …" aber cluster_id 0 vs. cluster_id 1).
   - Sollen wir Cluster nach Semantic-Ähnlichkeit (Label-String-Ähnlichkeit, z. B. Levenshtein/Jaccard) oder nur nach ID-Gleichheit matchen?
   - → Consequence: `clusters_new/removed` wird entweder einfach oder sehr komplex; Risk von Falsch-Positivs.

3. **Snapshot-Quelle: Neo4j-Abfrage vs. persistierte Pickle/Archive**
   - Sollen Graph-Snapshots live aus Neo4j abgerufen werden (flexibel, aber langsam bei großen Graphs) oder sollten sie beim Simulationsende gesammelt und gelagert werden?
   - → Consequence: Storage-Overhead, Query-Performance, Wiederherstellbarkeit historischer Diffs.

4. **Node-Isolation vs. physisches Löschen**
   - Wenn ein Node in Snapshot B fehlt: ist das "Node gelöscht" oder nur "Node ist isoliert (keine Kanten mehr)"?
   - → Consequence: Interpretation von Node-Property-Changes (können wir auf gelöschten Knoten Properties lesen?).

5. **Cluster-Matching-Fallback bei Seed-Differenzen**
   - Louvain-Clustering ist nondeterministisch (seed-abhängig). Zwei Simulationen mit gleichem Seed → identische Cluster-IDs; unterschiedliche Seeds → unterschiedliche IDs für ähnliche Communities.
   - Sollen wir im Diff ein `cluster_seed_mismatch`-Flag setzen, um Falsch-Alarm zu vermeiden?
   - → Consequence: Notwendigkeit von Metadaten (Seed-Tracking) pro Snapshot.

6. **Performance bei sehr großen Graphs (10k+ Nodes, 100k+ Edges)**
   - Neo4j-Abfragen für vollständige Snapshot-Extraktion können Timeout-Anfällig sein.
   - Sollen wir optional ein `sampling` oder `top_k_edges`-Mode haben, oder ist Pagination die Lösung?
   - → Consequence: API-Komplexität, Unvollständigkeit der Diffs.

---

## 7. Akzeptanz für Spike-Closure (#74)

- [ ] Vergleichsdimensionen identifiziert (≥8 definiert)
- [ ] Datenmodell skizziert (GraphDiff, GraphSnapshot, EdgeData, ClusterShift, GraphDiffMetrics)
- [ ] API-Schnitt skizziert (HTTP-Pfad, Request/Response mit echtem JSON, Error-Cases)
- [ ] Out-of-Scope dokumentiert (≥5 Punkte)
- [ ] Offene Fragen für Implementierung aufgelistet (≥5 Design-Entscheidungen)
- [ ] Anbindung an bestehende Services nachgewiesen (`TemporalGraphService`, `NetworkAnalyticsService`, Neo4j-Storage)

---

## 8. Referenzen im Bestands-Code

**Datenquellen:**
- `backend/app/services/temporal_graph.py` (Zeilen 70–150) — `TemporalGraphService.get_snapshot()`, `TemporalGraphService.compute_diff()` → liefert Added/Removed/Reinforced-Kanten
- `backend/app/services/network_analytics.py` (Zeilen 1–100+) — `NetworkAnalyticsService.compute_metrics()` → `PolarizationMetrics` mit Cluster-Info und Bridge-Agents
- `backend/app/storage/neo4j_storage.py` (Zeilen 37–120) — Neo4j-Driver, Snapshot-Abfragen, RELATION-Edge-Eigenschaften
- `backend/app/contracts/__init__.py` (Re-Exports) — Bestehende Pydantic-Modelle, wo GraphDiff-Modelle andocken können

**Graph-Struktur und Temporal-Tracking existiert bereits:**
- `valid_from_round`, `valid_to_round`, `reinforced_count` Eigenschaften auf RELATION-Edges (Zeile 4–7 in `temporal_graph.py`)
- `GraphSnapshot`, `GraphDiff` Dataclasses bereits definiert (Zeilen 26–67 in `temporal_graph.py`, aber noch nicht als Pydantic v2)

**Netzwerk-Metriken existieren:**
- `PolarizationMetrics` mit `echo_chamber_index`, `cluster_count`, `dominant_clusters`, `bridge_agents` (`network_analytics.py`)
- Deterministisches Cluster-Labeling via TF-Top-3 + Stopword-Filter (`network_analytics.py`, Zeilen 78–100)

---

## 9. Arbeitsprotokoll

**Spike durchgeführt:**
- 2026-05-03, 15:30–16:15 CEST
- **Recherche-Pfade:**
  - `backend/app/services/temporal_graph.py` — vollständig (GraphSnapshot, GraphDiff, TemporalGraphService)
  - `backend/app/services/network_analytics.py` — erste 100 Zeilen (PolarizationMetrics, Cluster-Labeling)
  - `backend/app/api/graph.py` — erste 100 Zeilen (bestehende Endpoints, kein `/diff` vorhanden)
  - `backend/app/contracts/__init__.py` — vollständig (verfügbare Pydantic-Re-Exports)
  - `backend/app/storage/neo4j_storage.py` — erste 120 Zeilen (Neo4j-Treiber, Schema)
  - `docs/glossary-wording.md` — vollständig (Wording-Regeln)

- **Dimensions-Matrix:** 9 Vergleichsdimensionen definiert
  - 3 existieren im Code (Added/Removed/Reinforced-Edges aus `TemporalGraphService`)
  - 6 neue oder Hooks (Weakened-Edges, Node-Property-Drift, Cluster-Shifts, Bridge-Agent-Shifts, Density-Delta, New/Removed-Clusters)

- **Datenmodell:** Pseudocode-Schemata für 8 Klassen
  - `EdgeData`, `NodePropertyShift`, `ClusterShift`, `BridgeAgentShift`, `ClusterSummary`, `GraphSnapshot`, `GraphDiffMetrics`, `GraphDiff`
  - Feldtypen konsistent (float, int, str, List, Dict, datetime)
  - Keine echte `.py`-Datei geschrieben (Pseudocode nur im Markdown)

- **API-Schnitt:** GET-Endpoint mit vollständiger Response
  - Pfad: `GET /api/simulation/<sim_id>/graph-diff?branch_a=<id>&branch_b=<id>` (konsistent mit Task 23)
  - Anfrage mit 4 Query-Parametern (davon 2 erforderlich, 2 optional)
  - Response-Body mit echtem JSON (kein `...`-Platzhalter) — Länge ~200 Zeilen
  - Error-Cases: 404 (Branches nicht gefunden), 400 (inkompatible Netzwerk-Versionen), 422 (unvollständiger Graph-Status)

- **Out-of-Scope:** 6 explizite ❌-Markierungen (UI, Implementation, Persona-Diff, Multi-Way, Round-by-Round, Node-Matching-Intelligenz)

- **Offene Fragen:** 6 Design-Entscheidungen für Implementierung
  1. Edge-Identität (UUID vs. Composite-Key)
  2. Cluster-Matching (ID-Gleichheit vs. Semantic-Ähnlichkeit)
  3. Snapshot-Quelle (Live Neo4j vs. Archive)
  4. Node-Isolation vs. Löschen
  5. Cluster-Seed-Nondeterminismus
  6. Performance bei 10k+ Nodes

- **Voice-Lint:** Keine US-Marketing-Phrasen, keine Wording-Glossar-v1-Verstöße (siehe `docs/glossary-wording.md`).

- **Konsistenz mit Task 23 (Spike #65):**
  - Gleiche Sektionsstruktur (1–9)
  - Gleicher JSON-Stil (vollständige Response-Bodies, keine Platzhalter)
  - Gleiche Fehler-Case-Struktur (404, 400, 422)
  - Gleiche Pseudocode-Konvention (Klassen mit Typen-Hints, ohne Implementation)

