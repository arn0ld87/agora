"""
Entity-read endpoints split from the main simulation API module.
"""

from flask import request

from . import simulation_bp
from ..services.entity_reader import EntityReader
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.validation import validate_graph_id
from .simulation_common import get_simulation_storage, logger


@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get knowledge graph entities")
def get_graph_entities(graph_id: str):
    """Get all entities from the knowledge graph (filtered)."""
    if not validate_graph_id(graph_id):
        return json_error("Invalid graph_id format")

    entity_types_str = request.args.get('entity_types', '')
    entity_types = [t.strip() for t in entity_types_str.split(',') if t.strip()] if entity_types_str else None
    enrich = request.args.get('enrich', 'true').lower() == 'true'

    logger.info(
        f"Get knowledge graph entities: graph_id={graph_id}, entity_types={entity_types}, enrich={enrich}"
    )

    storage = get_simulation_storage()
    reader = EntityReader(storage)
    result = reader.filter_defined_entities(
        graph_id=graph_id,
        defined_entity_types=entity_types,
        enrich_with_edges=enrich,
    )
    return json_success(result.to_dict())


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get entity details")
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Get detailed information for a single entity."""
    if not validate_graph_id(graph_id):
        return json_error("Invalid graph_id format")

    storage = get_simulation_storage()
    reader = EntityReader(storage)
    entity = reader.get_entity_with_context(graph_id, entity_uuid)

    if not entity:
        return json_error(f"Entity does not exist: {entity_uuid}", status=404)

    return json_success(entity.to_dict())


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get entities")
def get_entities_by_type(graph_id: str, entity_type: str):
    """Get all entities of the specified type."""
    if not validate_graph_id(graph_id):
        return json_error("Invalid graph_id format")

    enrich = request.args.get('enrich', 'true').lower() == 'true'

    storage = get_simulation_storage()
    reader = EntityReader(storage)
    entities = reader.get_entities_by_type(
        graph_id=graph_id,
        entity_type=entity_type,
        enrich_with_edges=enrich,
    )

    return json_success({
        "entity_type": entity_type,
        "count": len(entities),
        "entities": [entity.to_dict() for entity in entities],
    })
