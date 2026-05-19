"""
Service for exporting graphs as GraphML.
"""

import io
import json

def stringify(value):
    """GraphML only accepts scalars — coerce lists/dicts to JSON strings."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)

def build_networkx_graph(graph_data: dict):
    import networkx as nx

    g = nx.MultiDiGraph()
    g.graph["graph_id"] = graph_data.get("graph_id", "")

    for node in graph_data.get("nodes", []) or []:
        node_id = node.get("uuid") or node.get("id")
        if not node_id:
            continue
        attrs = {k: stringify(v) for k, v in node.items() if k != "uuid"}
        g.add_node(node_id, **attrs)

    for edge in graph_data.get("edges", []) or []:
        src = edge.get("source_uuid") or edge.get("source")
        tgt = edge.get("target_uuid") or edge.get("target")
        if not src or not tgt:
            continue
        attrs = {
            k: stringify(v)
            for k, v in edge.items()
            if k not in ("source_uuid", "target_uuid", "source", "target")
        }
        g.add_edge(src, tgt, **attrs)

    return g

class GraphExportService:
    @staticmethod
    def export_graphml(graph_data: dict) -> bytes:
        import networkx as nx
        g = build_networkx_graph(graph_data)
        buf = io.BytesIO()
        nx.write_graphml(g, buf, named_key_ids=True)
        return buf.getvalue()
