"""
EntityReadandFilterserveservice
from Neo4j GraphinReadNode，FilteroutputcharactermergepresetmeaningEntityTypesNode

Replaces zep_entity_reader.py — all Zep Cloud calls replaced by GraphStorage.
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field

from ..utils.logger import get_logger
from ..storage import GraphStorage

logger = get_logger('mirofish.entity_reader')


@dataclass
class EntityNode:
    """Entity node data structure"""
    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    # Related edges
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    # Related other nodes
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        """Get entity type (exclude default Entity label)"""
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Filtered entity set"""
    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class EntityReader:
    """
    Entity reading and filtering service (via GraphStorage / Neo4j)

    mainneedsuccesscan：
    1. fromGraphReadallhaveNode
    2. FilteroutputcharactermergepresetmeaningEntityTypesNode（LabelsnotonlyisEntitysNode）
    3. GeteachEntitysrelatedrelatedEdgeandrelatedlinkNodeInformation
    """

    def __init__(self, storage: GraphStorage):
        self.storage = storage

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        GetGraphsallhaveNode

        Args:
            graph_id: GraphID

        Returns:
            Nodelisttable
        """
        logger.info(f"Getting all nodes in graph {graph_id}...")
        nodes = self.storage.get_all_nodes(graph_id)
        logger.info(f"Got {len(nodes)} nodes total")
        return nodes

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        GetGraphsallhaveEdge

        Args:
            graph_id: GraphID

        Returns:
            Edgelisttable
        """
        logger.info(f"Getting all edges in graph {graph_id}...")
        edges = self.storage.get_all_edges(graph_id)
        logger.info(f"Got {len(edges)} edges total")
        return edges

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """
        GetspecifysetNodesallhaverelatedrelatedEdge

        Args:
            node_uuid: NodeUUID

        Returns:
            Edgelisttable
        """
        try:
            return self.storage.get_node_edges(node_uuid)
        except Exception as e:
            logger.warning(f"Failed to get edges for node {node_uuid}: {str(e)}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True
    ) -> FilteredEntities:
        """
        FilteroutputcharactermergepresetmeaningEntityTypesNode

        Filterlogiclogic：
        - suchresultNodesLabelsonlyhavea"Entity"，speakbrightthisEntitynotcharactermergewespresetmeaningsType，skipthrough
        - suchresultNodesLabelsincludecontainexcept"Entity"and"Node"ofexceptsmarktag，speakbrightcharactermergepresetmeaningType，keepkeep

        Args:
            graph_id: GraphID
            defined_entity_types: presetmeaningsEntityTypelisttable（canselect，suchresultprovideprovidethenonlykeepkeepthissomeType）
            enrich_with_edges: isnoGeteachEntitysrelatedrelatedEdgeInformation

        Returns:
            FilteredEntities: FilteraftersEntitycollectmerge
        """
        logger.info(f"Starting to filter entities in graph {graph_id}...")

        # Get all nodes
        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)

        # Get all edges (for subsequent association lookup)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []

        # Build mapping from node UUID to node data
        node_map = {n["uuid"]: n for n in all_nodes}

        # Filter entities matching criteria
        filtered_entities = []
        entity_types_found: Set[str] = set()

        for node in all_nodes:
            labels = node.get("labels", [])

            # Filter logic: Labels must contain labels besides "Entity" and "Node"
            custom_labels = [la for la in labels if la not in ["Entity", "Node"]]

            if not custom_labels:
                # Only default labels, skip
                continue

            # If predefined types specified, check if matching
            if defined_entity_types:
                matching_labels = [la for la in custom_labels if la in defined_entity_types]
                if not matching_labels:
                    continue
                entity_type = matching_labels[0]
            else:
                entity_type = custom_labels[0]

            entity_types_found.add(entity_type)

            # CreateEntityNodetoelement
            entity = EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=labels,
                summary=node.get("summary", ""),
                attributes=node.get("attributes", {}),
            )

            # GetrelatedrelatedEdgeandNode
            if enrich_with_edges:
                related_edges = []
                related_node_uuids: Set[str] = set()

                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge.get("fact", ""),
                            "target_node_uuid": edge["target_node_uuid"],
                        })
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append({
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge.get("fact", ""),
                            "source_node_uuid": edge["source_node_uuid"],
                        })
                        related_node_uuids.add(edge["source_node_uuid"])

                entity.related_edges = related_edges

                # GetrelatedlinkNodesbaseoriginalInformation
                related_nodes = []
                for related_uuid in related_node_uuids:
                    if related_uuid in node_map:
                        related_node = node_map[related_uuid]
                        related_nodes.append({
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node.get("labels", []),
                            "summary": related_node.get("summary", ""),
                        })

                entity.related_nodes = related_nodes

            filtered_entities.append(entity)

        logger.info(f"Filter completed: total nodes {total_count}, matched {len(filtered_entities)}, "
                     f"entity types: {entity_types_found}")

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(
        self,
        graph_id: str,
        entity_uuid: str
    ) -> Optional[EntityNode]:
        """
        GetSingleEntityanditscompletewholeondowntext（EdgeandrelatedlinkNode）

        Optimized: uses get_node() + get_node_edges() instead of loading ALL nodes.
        Only fetches related nodes individually as needed.

        Args:
            graph_id: GraphID
            entity_uuid: EntityUUID

        Returns:
            EntityNodeorNone
        """
        try:
            # Get the node directly by UUID (O(1) lookup)
            node = self.storage.get_node(entity_uuid)
            if not node:
                return None

            # Get edges for this node (O(degree) via Cypher)
            edges = self.storage.get_node_edges(entity_uuid)

            # Process related edges and collect related node UUIDs
            related_edges = []
            related_node_uuids: Set[str] = set()

            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append({
                        "direction": "outgoing",
                        "edge_name": edge["name"],
                        "fact": edge.get("fact", ""),
                        "target_node_uuid": edge["target_node_uuid"],
                    })
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append({
                        "direction": "incoming",
                        "edge_name": edge["name"],
                        "fact": edge.get("fact", ""),
                        "source_node_uuid": edge["source_node_uuid"],
                    })
                    related_node_uuids.add(edge["source_node_uuid"])

            # Fetch related nodes individually (avoids loading ALL nodes)
            related_nodes = []
            for related_uuid in related_node_uuids:
                related_node = self.storage.get_node(related_uuid)
                if related_node:
                    related_nodes.append({
                        "uuid": related_node["uuid"],
                        "name": related_node["name"],
                        "labels": related_node.get("labels", []),
                        "summary": related_node.get("summary", ""),
                    })

            return EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=node.get("labels", []),
                summary=node.get("summary", ""),
                attributes=node.get("attributes", {}),
                related_edges=related_edges,
                related_nodes=related_nodes,
            )

        except Exception as e:
            logger.error(f"Failed to get entity {entity_uuid}: {str(e)}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True
    ) -> List[EntityNode]:
        """
        GetspecifysetTypesallhaveEntity

        Args:
            graph_id: GraphID
            entity_type: EntityType（such "Student", "PublicFigure" etc）
            enrich_with_edges: isnoGetrelatedrelatedEdgeInformation

        Returns:
            Entitylisttable
        """
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges
        )
        return result.entities
