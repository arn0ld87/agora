"""
History, standalone profile generation, and database-query routes split from the main module.
"""

import os
import traceback

from flask import current_app, jsonify, request

from . import simulation_bp
from ..config import Config
from ..models.project import ProjectManager
from ..services.entity_reader import EntityReader
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager
from ..services.simulation_runner import SimulationRunner
from ..utils.validation import validate_simulation_id
from .simulation_common import logger


def _get_report_id_for_simulation(simulation_id: str) -> str:
    """Get the latest report_id associated with a simulation."""
    import json

    reports_dir = os.path.join(os.path.dirname(__file__), '../../uploads/reports')
    if not os.path.exists(reports_dir):
        return None

    matching_reports = []
    try:
        for report_folder in os.listdir(reports_dir):
            report_path = os.path.join(reports_dir, report_folder)
            if not os.path.isdir(report_path):
                continue

            meta_file = os.path.join(report_path, 'meta.json')
            if not os.path.exists(meta_file):
                continue

            try:
                with open(meta_file, 'r', encoding='utf-8') as handle:
                    meta = json.load(handle)
                if meta.get('simulation_id') == simulation_id:
                    matching_reports.append({
                        'report_id': meta.get('report_id'),
                        'created_at': meta.get('created_at', ''),
                        'status': meta.get('status', ''),
                    })
            except Exception:
                continue

        if not matching_reports:
            return None
        matching_reports.sort(key=lambda item: item.get('created_at', ''), reverse=True)
        return matching_reports[0].get('report_id')
    except Exception as exc:
        logger.warning(f"Failed to find report for simulation {simulation_id}: {exc}")
        return None


@simulation_bp.route('/history', methods=['GET'])
def get_simulation_history():
    """Get enriched simulation history for the homepage/history views."""
    try:
        limit = request.args.get('limit', 20, type=int)
        manager = SimulationManager()
        simulations = manager.list_simulations()[:limit]

        enriched_simulations = []
        for sim in simulations:
            sim_dict = sim.to_dict()
            config = manager.get_simulation_config(sim.simulation_id)
            if config:
                sim_dict['simulation_requirement'] = config.get('simulation_requirement', '')
                time_config = config.get('time_config', {})
                sim_dict['total_simulation_hours'] = time_config.get('total_simulation_hours', 0)
                recommended_rounds = int(
                    time_config.get('total_simulation_hours', 0) * 60 /
                    max(time_config.get('minutes_per_round', 60), 1)
                )
            else:
                sim_dict['simulation_requirement'] = ''
                sim_dict['total_simulation_hours'] = 0
                recommended_rounds = 0

            run_state = SimulationRunner.get_run_state(sim.simulation_id)
            if run_state:
                sim_dict['current_round'] = run_state.current_round
                sim_dict['runner_status'] = run_state.runner_status.value
                sim_dict['total_rounds'] = run_state.total_rounds if run_state.total_rounds > 0 else recommended_rounds
            else:
                sim_dict['current_round'] = 0
                sim_dict['runner_status'] = 'idle'
                sim_dict['total_rounds'] = recommended_rounds

            project = ProjectManager.get_project(sim.project_id)
            if project and hasattr(project, 'files') and project.files:
                sim_dict['files'] = [
                    {'filename': file_info.get('filename', 'Unknown file')}
                    for file_info in project.files[:3]
                ]
            else:
                sim_dict['files'] = []

            sim_dict['report_id'] = _get_report_id_for_simulation(sim.simulation_id)
            sim_dict['source_simulation_id'] = sim.source_simulation_id
            sim_dict['root_simulation_id'] = sim.root_simulation_id or sim.simulation_id
            sim_dict['branch_name'] = sim.branch_name
            sim_dict['branch_depth'] = sim.branch_depth
            sim_dict['version'] = 'v1.0.2'
            try:
                sim_dict['created_date'] = sim_dict.get('created_at', '')[:10]
            except Exception:
                sim_dict['created_date'] = ''

            enriched_simulations.append(sim_dict)

        return jsonify({"success": True, "data": enriched_simulations, "count": len(enriched_simulations)})
    except Exception as exc:
        logger.error(f"Failed to get historical simulations: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/generate-profiles', methods=['POST'])
def generate_profiles():
    """Generate profiles directly from a graph without creating a simulation."""
    try:
        data = request.get_json() or {}
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({"success": False, "error": "Please provide graph_id"}), 400

        entity_types = data.get('entity_types')
        use_llm = data.get('use_llm', True)
        platform = data.get('platform', 'reddit')

        storage = current_app.extensions.get('neo4j_storage')
        if not storage:
            raise ValueError('GraphStorage not initialized')
        reader = EntityReader(storage)
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True,
        )
        if filtered.filtered_count == 0:
            return jsonify({"success": False, "error": "No matching entities found"}), 400

        generator = OasisProfileGenerator()
        profiles = generator.generate_profiles_from_entities(entities=filtered.entities, use_llm=use_llm)
        if platform == 'reddit':
            profiles_data = [profile.to_reddit_format() for profile in profiles]
        elif platform == 'twitter':
            profiles_data = [profile.to_twitter_format() for profile in profiles]
        else:
            profiles_data = [profile.to_dict() for profile in profiles]

        return jsonify({
            "success": True,
            "data": {
                "platform": platform,
                "entity_types": list(filtered.entity_types),
                "count": len(profiles_data),
                "profiles": profiles_data,
            },
        })
    except Exception as exc:
        logger.error(f"GenerateProfileFailed: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
def get_simulation_posts(simulation_id: str):
    """Get posts from a simulation SQLite database."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        platform = request.args.get('platform', 'reddit')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)

        sim_dir = os.path.join(os.path.dirname(__file__), f'../../uploads/simulations/{simulation_id}')
        db_path = os.path.join(sim_dir, f"{platform}_simulation.db")
        if not os.path.exists(db_path):
            return jsonify({
                "success": True,
                "data": {
                    "platform": platform,
                    "count": 0,
                    "posts": [],
                    "message": "Database does not exist，SimulationMay not have run yet",
                },
            })

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT * FROM post
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            posts = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            posts = []
            total = 0
        conn.close()

        return jsonify({
            "success": True,
            "data": {"platform": platform, "total": total, "count": len(posts), "posts": posts},
        })
    except Exception as exc:
        logger.error(f"Failed to get posts: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
def get_simulation_comments(simulation_id: str):
    """Get comments from the Reddit simulation database."""
    if not validate_simulation_id(simulation_id):
        return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400
    try:
        post_id = request.args.get('post_id')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        sim_dir = os.path.join(os.path.dirname(__file__), f'../../uploads/simulations/{simulation_id}')
        db_path = os.path.join(sim_dir, 'reddit_simulation.db')
        if not os.path.exists(db_path):
            return jsonify({"success": True, "data": {"count": 0, "comments": []}})

        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            if post_id:
                cursor.execute("""
                    SELECT * FROM comment
                    WHERE post_id = ?
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (post_id, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM comment
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                """, (limit, offset))
            comments = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            comments = []
        conn.close()

        return jsonify({"success": True, "data": {"count": len(comments), "comments": comments}})
    except Exception as exc:
        logger.error(f"Failed to get comments: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500
