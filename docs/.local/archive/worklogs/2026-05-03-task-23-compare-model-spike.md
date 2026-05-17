# Task 23 — Vergleichsmodell für Simulations-Branches (Spike #65)

**Datum:** 2026-05-03  
**Status:** Spike — Spezifikation, kein Code-Commit  
**Closes:** #65  
**Vorbedingung für:** #66 (Compare-API), #67 (Compare-UI)

---

## 1. Ziel & Scope

Zwei Branches einer Simulation sollen auf definierte Vergleichsmetriken hin analysiert werden. Ein Branch ist eine persistierte Variante einer Simulation mit eigenen Personas, Reports und Netzwerk-Analysen (Neo4j SimulationBranch-Knoten). Ziel: Identifikation von Unterschieden in Agentenverhalten, Netzwerkstruktur und Evidence-Qualität.

**Was wird verglichen:**
- Branch A und Branch B (beide vollständig simuliert, mit Reports und Netzwerk-Metriken)
- Aggregierte Metriken pro Branch, dann als Differenzen

**Was wird nicht verglichen:**
- Einzelne Persona-Profile (→ Layer 8 #69)
- Queries über zeitliche Entwicklung (→ Layer 8)
- Diff von Personas zwischen Branches (→ separate Task #69)

---

## 2. Vergleichsdimensionen

| Dimension | Beschreibung | Datenquelle | Aggregat | Status |
|---|---|---|---|---|
| **Polarisation (Echo-Chamber-Index)** | Anteil Agenteninteraktionen, die innerhalb desselben Clusters bleiben (0.0 = vollständig integriert, 1.0 = völlig polarisiert). | `NetworkAnalyticsService.compute_metrics()` → `PolarizationMetrics.echo_chamber_index` | `float [0.0, 1.0]` | Existiert |
| **Cluster-Struktur** | Anzahl dominanter Cluster pro Branch, Top-3 Labels (deterministisch aus TF-Top-3 mit Stopword-Filter). | `PolarizationMetrics.cluster_count`, `.dominant_clusters[].label` | Cluster-Count (`int`), Label-Liste | Existiert |
| **Bridge-Agent-Aktivität** | Top-k Agenten mit höchster Betweenness-Zentralität, die zwei unterschiedliche Cluster verbinden (Indikator für Cross-Cluster-Brückenbau). | `PolarizationMetrics.bridge_agents` | Liste von `agent_id` (Top 5) | Existiert |
| **Top-Themen pro Cluster** | Die 3 häufigsten Begriffe pro Cluster, deterministisch aus Agent-Action-Texten extrahiert (TF-Ranking + alphabetischer Tie-Break). | `PolarizationMetrics.dominant_clusters[].label` | Cluster-ID → Label (String) | Existiert |
| **Confidence-Verteilung** | Histogramm der Report-Claim-Confidence-Scores (low/medium/high/verified). Pro Branch: wie viele Claims in jeder Confidence-Kategorie. | `Report` → `sections[].claims[].confidence_score` + `confidence_calculator.compute_confidence()` | `{low: int, medium: int, high: int, verified: int}` | Existiert (partiell) |
| **Evidence-Coverage** | Durchschnittliche Anzahl Evidence-Items pro Claim; auch: Anteil Claims ohne Evidence (struktureller Drift-Marker). | `Report` → `sections[].claims[].evidence_items` | Durchschnitt (`float`), Anteil-ohne (`float [0, 1]`) | Existiert |
| **Persona-Reach-Index** | Pro Segment: wie viele der generierten Personas haben mindestens eine Aktion in der Simulation ausgeführt? (Aktivitäts-Indikator für Segment-Repräsentanz). | Neo4j: `MATCH (sim:SimulationBranch)-[:HAS_AGENT]->(a:Agent)-[:HAS_PERSONA]->(p:Persona)` mit Agent-Action-Count > 0 | Segment → Aktivquote (`float [0, 1]`), Absolut (Aktiv / Total) | Neu — nicht in Code |
| **Interaction-Density** | Mittelwert der Agenten-Interaktionen pro Round (Engagement-Indikator). | `PolarizationMetrics.total_interactions` / Anzahl Rounds | `float` | Existiert (partiell) |
| **Contradiction-Penalty (Evidence-Konsistenz)** | Anteil Claims mit strukturierten Widerspruchsmarkierungen in der Evidence (z. B. Stance-Konflikte). | `Report` → `sections[].claims[].audit_trail` mit `contradiction_detected` | Anteil (`float [0, 1]`) | Existiert (Hook, noch nicht live) |

---

## 3. Datenmodell (Pseudocode)

```python
# Branch-Vergleich-Antwort (Skizze, kein .py-Datei)

class BranchComparison(BaseModel):
    """Vergleich zweier Branches einer Simulation."""
    
    simulation_id: str              # Gemeinsamer Parent-Sim
    branch_a_id: str                # UUID oder Sim-Branch-ID aus Neo4j
    branch_b_id: str                # dto.
    
    # Metadaten
    created_at: datetime            # Zeitstempel des Vergleichs (nicht der Simulation)
    branch_a_completed_at: datetime # Simulation-Completion-Zeit Branch A
    branch_b_completed_at: datetime # dto. Branch B
    
    # Metriken pro Branch
    metrics_a: BranchMetrics        # Snapshot Branch A
    metrics_b: BranchMetrics        # Snapshot Branch B
    
    # Differenzen (Branch B - Branch A)
    deltas: ComparisonDeltas        # Signed Differences
    

class BranchMetrics(BaseModel):
    """Aggregierte Metriken eines einzelnen Branches."""
    
    # Netzwerk
    echo_chamber_index: float       # [0, 1]
    cluster_count: int
    dominant_clusters: List[ClusterSummary]  # Top 3
    bridge_agent_ids: List[int]     # Top 5
    total_agents: int
    total_interactions: int
    interaction_density: float      # interactions / rounds (approx)
    
    # Report / Evidence
    confidence_distribution: Dict[str, int]  # {low, medium, high, verified}
    avg_evidence_per_claim: float
    claims_without_evidence_ratio: float     # [0, 1]
    contradiction_ratio: float      # [0, 1]
    
    # Personas
    persona_reach: Dict[str, SegmentReach]   # segment_name → {active, total, ratio}
    

class ClusterSummary(BaseModel):
    cluster_id: int
    size: int
    label: str  # Deterministic TF-Top-3 oder "cluster-{id}"
    

class SegmentReach(BaseModel):
    segment_name: str
    active_count: int   # Personas mit mindestens 1 Action
    total_count: int    # Alle generierten Personas in Segment
    ratio: float        # active_count / total_count
    

class ComparisonDeltas(BaseModel):
    """Unterschiede Branch B vs Branch A (signed)."""
    
    # Welche Branch hat höhere Polarisation? Positive Delta = mehr Polarisation in B
    echo_chamber_delta: float
    cluster_delta: int                      # Mehr/weniger Cluster in B
    bridge_agents_delta: int                # Mehr/weniger Bridge-Agents aktiv
    
    # Evidence-Qualität
    confidence_distribution_delta: Dict[str, int]  # Differenz pro Label
    avg_evidence_delta: float
    contradiction_ratio_delta: float
    
    # Engagement
    interaction_density_delta: float        # Denser = höhere Aktivität
    
    # Semantic Highlight: welche Cluster sind neu/verändert in B?
    clusters_only_in_a: List[ClusterSummary]
    clusters_only_in_b: List[ClusterSummary]
    clusters_changed: List[Dict]  # {cluster_id, size_a, size_b, label_change}
```

**Feldtypen / Semantik:**
- `float`: Floats mit 2–4 Dezimalstellen (ROUND in API-Response)
- `Dict[str, int]`: Confidence-Distribution z. B. `{"low": 5, "medium": 12, "high": 8, "verified": 2}`
- `List[ClusterSummary]`: Top 3 Cluster nach Größe, deterministisch sortiert
- Alle `_delta`-Felder: negative = Branch A größer, positive = Branch B größer

---

## 4. API-Schnitt (Skizze)

### Endpoint-Pfad
```http
GET /api/simulation/<sim_id>/compare?branch_a=<id>&branch_b=<id>
```

### Anfrage

**Query-Parameter:**
- `branch_a` (erforderlich): ID des ersten Branches
- `branch_b` (erforderlich): ID des zweiten Branches
- `window_size_rounds` (optional): Sliding Window für Netzwerk-Metriken (default: `None` = alle Rounds)

**Beispiel:**
```
GET /api/simulation/sim-abc123/compare?branch_a=branch-001&branch_b=branch-002
```

### Antwort (200 OK)

**Content-Type:** `application/json`

**Body Schema:**
```json
{
  "status": "ok",
  "data": {
    "comparison": {
      "simulation_id": "sim-abc123",
      "branch_a_id": "branch-001",
      "branch_b_id": "branch-002",
      "created_at": "2026-05-03T14:22:15Z",
      "branch_a_completed_at": "2026-05-03T14:10:00Z",
      "branch_b_completed_at": "2026-05-03T14:18:45Z",
      
      "metrics_a": {
        "echo_chamber_index": 0.62,
        "cluster_count": 3,
        "dominant_clusters": [
          {"cluster_id": 0, "size": 18, "label": "energiepolitik, diskurs, europaeisch"},
          {"cluster_id": 1, "size": 12, "label": "finanzmarkt, handel, europa"},
          {"cluster_id": 2, "size": 8, "label": "digital, datenschutz, reform"}
        ],
        "bridge_agent_ids": [5, 12, 18],
        "total_agents": 38,
        "total_interactions": 287,
        "interaction_density": 3.58,
        
        "confidence_distribution": {"low": 3, "medium": 8, "high": 12, "verified": 1},
        "avg_evidence_per_claim": 2.1,
        "claims_without_evidence_ratio": 0.08,
        "contradiction_ratio": 0.02,
        
        "persona_reach": {
          "Politik": {"segment_name": "Politik", "active_count": 8, "total_count": 10, "ratio": 0.8},
          "Medien": {"segment_name": "Medien", "active_count": 6, "total_count": 8, "ratio": 0.75},
          "Akademie": {"segment_name": "Akademie", "active_count": 4, "total_count": 5, "ratio": 0.8}
        }
      },
      
      "metrics_b": {
        "echo_chamber_index": 0.71,
        "cluster_count": 4,
        "dominant_clusters": [
          {"cluster_id": 0, "size": 20, "label": "energiepolitik, fossil, transition"},
          {"cluster_id": 1, "size": 10, "label": "finanzmarkt, gruen, esg"},
          {"cluster_id": 2, "size": 6, "label": "digital, blockchain, web3"},
          {"cluster_id": 3, "size": 5, "label": "klima, migration, sozialpolitik"}
        ],
        "bridge_agent_ids": [3, 7, 15, 22],
        "total_agents": 41,
        "total_interactions": 312,
        "interaction_density": 3.9,
        
        "confidence_distribution": {"low": 2, "medium": 7, "high": 14, "verified": 3},
        "avg_evidence_per_claim": 2.4,
        "claims_without_evidence_ratio": 0.05,
        "contradiction_ratio": 0.01,
        
        "persona_reach": {
          "Politik": {"segment_name": "Politik", "active_count": 9, "total_count": 10, "ratio": 0.9},
          "Medien": {"segment_name": "Medien", "active_count": 7, "total_count": 8, "ratio": 0.875},
          "Akademie": {"segment_name": "Akademie", "active_count": 5, "total_count": 5, "ratio": 1.0}
        }
      },
      
      "deltas": {
        "echo_chamber_delta": 0.09,
        "cluster_delta": 1,
        "bridge_agents_delta": 1,
        "confidence_distribution_delta": {"low": -1, "medium": -1, "high": 2, "verified": 2},
        "avg_evidence_delta": 0.3,
        "contradiction_ratio_delta": -0.01,
        "interaction_density_delta": 0.32,
        
        "clusters_only_in_a": [],
        "clusters_only_in_b": [
          {"cluster_id": 3, "size": 5, "label": "klima, migration, sozialpolitik"}
        ],
        "clusters_changed": [
          {
            "cluster_id": 0,
            "size_a": 18,
            "size_b": 20,
            "label_change": "energiepolitik, diskurs, europaeisch → energiepolitik, fossil, transition"
          }
        ]
      }
    }
  },
  "timing": {
    "compute_ms": 324
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

**400 Bad Request** — wenn Branches unterschiedliche Schema-Versionen haben (z. B. eine v0.8, eine v0.9):
```json
{
  "status": "error",
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Branches haben inkompatible Schema-Versionen",
    "details": {
      "branch_a_schema_version": "0.8",
      "branch_b_schema_version": "0.9",
      "note": "Bitte neu simulieren oder migrieren"
    }
  }
}
```

**422 Unprocessable Entity** — wenn einer der Branches unvollständig ist (z. B. noch nicht simuliert, Report fehlt):
```json
{
  "status": "error",
  "error": {
    "code": "INCOMPLETE_STATE",
    "message": "Branch 'branch-001' ist nicht simuliert (Status: PREPARED)",
    "details": {
      "branch_id": "branch-001",
      "simulation_status": "PREPARED",
      "requires": ["COMPLETED"]
    }
  }
}
```

---

## 5. Out of Scope (explizit)

- ❌ **Side-by-Side-UI** — Visualisierung der Deltas (→ Sub-Slice 25 / Task 25, #67)
- ❌ **Implementierung der API** — Design und Spezifikation nur (→ Sub-Slice 24 / Task 24, #66)
- ❌ **Branch-Erstellungs-Flow** — existiert bereits in `backend/app/services/branching_service.py`
- ❌ **Diff über Persona-Profile** — z. B. Neue-vs.-Alte Traits (→ Layer 8, #69 Persona Review Flow)
- ❌ **Zeithistorie-Vergleich** — z. B. Polarisation Round-by-Round (→ Layer 8)
- ❌ **Multi-Way-Compare** — nur 2 Branches (später evtl. Erweiterung)

---

## 6. Offene Fragen für #66/#67

### Design-Entscheidungen

1. **Persona-Segment-Klassifizierung:**
   - Sollen Segmente aus der Simulation selbst kommen (z. B. über KG-Entity-Types)?
   - Oder vorab in der Quota-Plan-Konfiguration stehen?
   - → Consequence: Persona-Reach-Index hängt von dieser Antwort ab.

2. **Window-Sliding für Netzwerk-Metriken:**
   - `window_size_rounds` ist optional. Sinnvoll, um jüngste Rundenschwingungen zu filtern.
   - Sollte das auch auf Evidence-Count/Confidence-Distribution angewendet werden, oder nur auf Network-Metrics?

3. **Cluster-Matching zwischen Branches:**
   - Zwei Branches haben potentiell unterschiedliche Cluster-IDs für ähnliche Communities (z. B. beide mit Label „energiepolitik, …" aber cluster_id 0 vs. cluster_id 1).
   - Sollen wir im Delta-Block nach Semantic-Ähnlichkeit (Label-Ähnlichkeit) oder nur nach ID-Gleichheit matchen?
   - → Consequence: `clusters_changed` wird entweder einfach oder komplex.

4. **Confidence-Distribution vs. Single-Number-Summary:**
   - Histogramm ist semantisch reich, aber schwer zu vergleichen auf den ersten Blick.
   - Brauchst du zusätzlich einen Single-Number-Score (z. B. „Weighted Avg Confidence")? Oder ist das bei #67 UI-Sache?

5. **Contradiction-Penalty — noch nicht live:**
   - Hook existiert in `confidence_calculator.py`, aber keine aktive Erkennung.
   - Sollen wir die Metrik in dieser Spec einbauen oder auf #66/#67 verschieben, wenn die Erkennung verfügbar ist?

6. **Performance für große Simulationen:**
   - Neo4j-Abfragen für Persona-Reach können bei 1000+ Personas teuer werden.
   - Sollen wir Caching / Pre-Aggregation implementieren, oder lässt sich die Abfrage einfach optimieren?
   - → Consequence: Timeout-Handling, optionales `format=summary` (nur Deltas, keine Metrics-Details)?

---

## 7. Akzeptanz für #65 (Spike-Closure)

- [x] Vergleichsdimensionen identifiziert (≥6 implementiert, 1 neu)
- [x] Datenmodell skizziert (BranchComparison, Metrics, Deltas)
- [x] API-Schnitt skizziert (HTTP-Pfad, Request/Response, Error-Cases)
- [x] Out-of-Scope dokumentiert
- [x] Offene Fragen für Implementierung aufgelistet
- [x] Anbindung an bestehende Services nachgewiesen (`NetworkAnalyticsService`, `confidence_calculator`, `Report`)

---

## 8. Referenzen im Bestands-Code

**Datenquellen:**
- `backend/app/services/network_analytics.py` — `NetworkAnalyticsService.compute_metrics()` → `PolarizationMetrics`
- `backend/app/services/confidence_calculator.py` — `compute_confidence(evidence)` → `(score, label)`
- `backend/app/models/report.py` — `Report`, `ReportSection`, `ReportClaim` (Evidence-Items, Audit-Trail)
- `backend/app/contracts/` — Pydantic-Schemata für Persistierung & API
- Neo4j Graph: `SimulationBranch`, `Agent`, `Persona`, `AgentAction`, Entity-KG

**Branch-Verwaltung existiert bereits:**
- `backend/app/services/branching_service.py` — Branch-Erstellung, Persona-Override
- `backend/app/storage/neo4j_storage.py` — Neo4j-Reader für Branches

---

## 9. Arbeitsprotokoll

**Spike durchgeführt:**
- 2026-05-03, 14:30–15:15 CEST
- Recherche: `network_analytics.py`, `confidence_calculator.py`, `report_agent.py` (ersten 100 Zeilen), `refactoring-backlog-priorisiert.md` (EPIC-12-Analyse)
- Dimensionen-Matrix: 9 Metriken, 7 existieren im Code, 2 neu (Persona-Reach, Interaction-Density-Aggregat)
- Datenmodell: Pseudocode-Schemata für 5 Klassen (BranchComparison, BranchMetrics, ClusterSummary, SegmentReach, ComparisonDeltas)
- API-Schnitt: GET-Endpoint mit Full-Response + Error-Cases (404, 400, 422)
- Offene Fragen: 6 Design-Punkte für #66/#67-Implementierung
- Voice-Lint: Keine US-Marketing-Phrasen, keine verbotenen Wording-Glossar-Verletzungen

