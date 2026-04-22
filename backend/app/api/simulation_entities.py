"""
Entity-read endpoints split from the main simulation API module.
"""

import traceback

from flask import jsonify, request

from . import simulation_bp
from ..config import Config
from ..services.entity_reader import EntityReader
from ..utils.validation import validate_graph_id
from .simulation_common import get_simulation_storage, logger


@simulation_bp.route('/entities/<graph_id>', methods=['GET'])
def get_graph_entities(graph_id: str):
    """
    Get all entities from the knowledge graph (filtered).
    """
    if not validate_graph_id(graph_id):
        return jsonify({"success": False, "error": "Invalid graph_id format"}), 400

    try:
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

        return jsonify({
            "success": True,
            "data": result.to_dict(),
        })

    except Exception as exc:
        logger.error(f"Failed to get knowledge graph entities: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/entities/<graph_id>/<entity_uuid>', methods=['GET'])
def get_entity_detail(graph_id: str, entity_uuid: str):
    """Get detailed information for a single entity."""
    if not validate_graph_id(graph_id):
        return jsonify({"success": False, "error": "Invalid graph_id format"}), 400

    try:
        storage = get_simulation_storage()
        reader = EntityReader(storage)
        entity = reader.get_entity_with_context(graph_id, entity_uuid)

        if not entity:
            return jsonify({
                "success": False,
                "error": f"Entity does not exist: {entity_uuid}",
            }), 404

        return jsonify({
            "success": True,
            "data": entity.to_dict(),
        })

    except Exception as exc:
        logger.error(f"Failed to get entity details: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/entities/<graph_id>/by-type/<entity_type>', methods=['GET'])
def get_entities_by_type(graph_id: str, entity_type: str):
    """Get all entities of the specified type."""
    if not validate_graph_id(graph_id):
        return jsonify({"success": False, "error": "Invalid graph_id format"}), 400

    try:
        enrich = request.args.get('enrich', 'true').lower() == 'true'

        storage = get_simulation_storage()
        reader = EntityReader(storage)
        entities = reader.get_entities_by_type(
            graph_id=graph_id,
            entity_type=entity_type,
            enrich_with_edges=enrich,
        )

        return jsonify({
            "success": True,
            "data": {
                "entity_type": entity_type,
                "count": len(entities),
                "entities": [entity.to_dict() for entity in entities],
            },
        })

    except Exception as exc:
        logger.error(f"Failed to get entities: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500
