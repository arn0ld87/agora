# Agora Netzwerk-Analytik (Issue #12)

Dieses Dokument beschreibt die Heuristiken hinter
`backend/app/services/network_analytics.py` und
`GET /api/simulation/<id>/metrics`.

## Was wird gemessen?

| Kennzahl | Kurzdefinition |
|----------|----------------|
| `echo_chamber_index` | Anteil der Interaktionen, die innerhalb einer Community bleiben. `0.0` = vollständig durchmischt, `1.0` = strikte Echokammern. |
| `cluster_count` | Anzahl der gefundenen Communities. |
| `dominant_clusters[]` | Sortierte Liste der Communities (größte zuerst) mit Mitglieder-`agent_id`s. |
| `bridge_agents[]` | Top-*k* (Default 5) Agenten mit höchstem Betweenness-Score, die mindestens einen Nachbarn in einer anderen Community haben. |
| `total_agents` | Knotenzahl im Interaktionsgraphen (nicht alle Simulationsagenten — nur die mit mindestens einer in- oder out-going Interaktion). |
| `total_interactions` | Gewichtete Anzahl der verwerteten Aktionen (siehe Filter). |

## Welche OASIS-Aktionen gehen in den Graph?

Nur **gerichtete, paarweise** Aktionen. Broadcasts wie `CREATE_POST` oder
`DO_NOTHING` werden ignoriert, weil sie keine Sender→Empfänger-Kante
erzeugen.

Whitelist in `_DIRECTED_ACTIONS`:

- Reddit + Twitter: `FOLLOW`, `LIKE_POST`, `DISLIKE_POST`, `REPOST`,
  `CREATE_COMMENT`, `LIKE_COMMENT`, `DISLIKE_COMMENT`, `MUTE`,
  `QUOTE_POST`.

Die Ziel-Agent-ID wird aus `action_args` extrahiert
(`target_agent_id` / `followee_id` / `user_id` / `target_user_id` /
`author_id`). Aktionen ohne Ziel-Agent (z. B. `LIKE_POST` mit nur
`post_id` im Log) werden übersprungen — bewusst: sonst mischen wir
User- und Post-Knoten im selben Graph.

Self-Interaktionen (`src == tgt`) werden verworfen.

## Graph-Projektion

Die Interaktionen werden zu einem **gewichteten, ungerichteten** Graphen
zusammengefasst:

- Jede Kante hat `weight = Anzahl Interaktionen zwischen den beiden
  Agenten in beide Richtungen`.
- Ungerichtet, weil Louvain und Betweenness auf ungerichteten Graphen
  robuster sind; die Richtungsinformation wird für Echokammer-/Bridge-
  Analyse nicht benötigt.

## Community-Detection

`networkx.algorithms.community.louvain_communities(graph, weight='weight', seed=42)`

- Louvain maximiert die Modularität; die Communities landen in
  `dominant_clusters` absteigend nach Größe.
- Fixer `seed=42` macht Reports reproduzierbar — zwei Aufrufe auf
  identischen Aktionen liefern identische Cluster-IDs.
- Alternativen (Leiden, Infomap) wurden evaluiert, aber nicht benötigt:
  `networkx>=3.2` bringt Louvain ohne Zusatzabhängigkeit mit.

## Echokammer-Index

```
intra = sum(1 for src,tgt in interactions if cluster[src] == cluster[tgt])
total = len(interactions)
echo_chamber_index = intra / total
```

Interaktionen sind hier *nicht* deduplizierte Paare, sondern alle
verwerteten Aktionen (die Gewichtung steckt also in der Zählweise).

Interpretation:

- `echo_chamber_index ≈ 1.0` → jede Kommunikation bleibt innerhalb der
  eigenen Tribe (starke Polarisierung).
- `echo_chamber_index ≈ 0.0` → Agenten reden überwiegend
  cluster-übergreifend (integrierte Diskussion).
- Bei wenigen Clustern (z. B. 1 großes) ist der Wert trivial hoch —
  immer zusammen mit `cluster_count` bewerten.

## Bridge-Agents

1. `networkx.betweenness_centrality(graph, weight='weight', normalized=True)` —
   Score pro Agent.
2. Für jeden Kandidaten: nimm nur diejenigen, die mindestens einen
   Nachbarn in einer *anderen* Community haben (sonst ist „Bridge“
   irreführend: hohe Zentralität innerhalb einer einzigen Community
   bedeutet *Hub*, nicht Bridge).
3. Sortiere absteigend, liefere die Top `top_bridge_k` (Default 5).

## API

`GET /api/simulation/<simulation_id>/metrics`

Optionale Query-Parameter:

- `window_size_rounds` (int > 0) — nur die letzten *N* Runden werden
  analysiert. Default: ganze Simulation.
- `platform` (`twitter` | `reddit`) — Filter auf einen Kanal.

Antwort (Schema — gekürzt):

```json
{
  "success": true,
  "data": {
    "simulation_id": "sim_abcdef012345",
    "window_size_rounds": 10,
    "total_agents": 42,
    "total_interactions": 318,
    "echo_chamber_index": 0.7123,
    "cluster_count": 3,
    "dominant_clusters": [
      {"cluster_id": 0, "size": 18, "agent_ids": [1, 2, ...]},
      {"cluster_id": 1, "size": 16, "agent_ids": [...]}
    ],
    "bridge_agents": [7, 23, 41]
  }
}
```

## Ausblick

- **Live-Push statt Polling**: sobald `CHANGE_ACTION` auf dem
  `SimulationEventBus` vollständig gespiegelt ist, kann ein Daemon
  (`AnalyticsWorker`) die Metriken pro Runde berechnen und über SSE
  schieben. Aktuell reicht der synchrone `GET`-Pfad — `networkx` auf
  ≤ 10k Interaktionen liegt im Millisekundenbereich.
- **Zeitliche Serie**: Kombination mit `TemporalGraphService` (Issue
  #10) ermöglicht „Echokammer-Index pro Runde“ — offen als Analytics-
  Dashboard-Follow-up.
- **Heuristik-Tuning**: Gewichtung nach Action-Typ (`FOLLOW` > `LIKE`
  > `DISLIKE`?) ist derzeit uniform. Falls die Simulation das braucht,
  vor der Graph-Aggregation die Kantengewichte skalieren.
