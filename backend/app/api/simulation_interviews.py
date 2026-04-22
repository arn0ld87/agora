"""
Interview-related simulation API routes split from the main module.
"""

import traceback

from flask import jsonify, request

from . import simulation_bp
from ..config import Config
from ..services.simulation_runner import SimulationRunner
from ..utils.validation import validate_simulation_id
from .simulation_common import logger, optimize_interview_prompt


@simulation_bp.route('/interview', methods=['POST'])
def interview_agent():
    """Interview a single agent."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

        agent_id = data.get('agent_id')
        prompt = data.get('prompt')
        platform = data.get('platform')
        timeout = data.get('timeout', 60)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400
        if agent_id is None:
            return jsonify({"success": False, "error": "Please provide agent_id"}), 400
        if not prompt:
            return jsonify({"success": False, "error": "Please provide prompt（Interview question）"}), 400
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({"success": False, "error": "platform Parameter can only be 'twitter' Or 'reddit'"}), 400
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress.",
            }), 400

        optimized_prompt = optimize_interview_prompt(prompt)
        result = SimulationRunner.interview_agent(
            simulation_id=simulation_id,
            agent_id=agent_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout,
        )
        return jsonify({"success": result.get("success", False), "data": result})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except TimeoutError as exc:
        return jsonify({"success": False, "error": f"WaitInterviewResponse timeout: {str(exc)}"}), 504
    except Exception as exc:
        logger.error(f"InterviewFailed: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/interview/batch', methods=['POST'])
def interview_agents_batch():
    """Interview multiple agents in one request."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

        interviews = data.get('interviews')
        platform = data.get('platform')
        timeout = data.get('timeout', 120)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400
        if not interviews or not isinstance(interviews, list):
            return jsonify({"success": False, "error": "Please provide interviews（Interview list）"}), 400
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({"success": False, "error": "platform Parameter can only be 'twitter' Or 'reddit'"}), 400

        for index, interview in enumerate(interviews, 1):
            if 'agent_id' not in interview:
                return jsonify({"success": False, "error": f"Interview list item{index}Missing agent_id"}), 400
            if 'prompt' not in interview:
                return jsonify({"success": False, "error": f"Interview list item{index}Missing prompt"}), 400
            item_platform = interview.get('platform')
            if item_platform and item_platform not in ("twitter", "reddit"):
                return jsonify({
                    "success": False,
                    "error": f"Interview list item {index}: platform must be 'twitter' or 'reddit'",
                }), 400

        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress.",
            }), 400

        optimized_interviews = []
        for interview in interviews:
            optimized = interview.copy()
            optimized['prompt'] = optimize_interview_prompt(interview.get('prompt', ''))
            optimized_interviews.append(optimized)

        result = SimulationRunner.interview_agents_batch(
            simulation_id=simulation_id,
            interviews=optimized_interviews,
            platform=platform,
            timeout=timeout,
        )
        return jsonify({"success": result.get("success", False), "data": result})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except TimeoutError as exc:
        return jsonify({"success": False, "error": f"Wait for batchInterviewResponse timeout: {str(exc)}"}), 504
    except Exception as exc:
        logger.error(f"BatchInterviewFailed: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/interview/all', methods=['POST'])
def interview_all_agents():
    """Interview all agents with a shared prompt."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

        prompt = data.get('prompt')
        platform = data.get('platform')
        timeout = data.get('timeout', 180)

        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400
        if not prompt:
            return jsonify({"success": False, "error": "Please provide prompt（Interview question）"}), 400
        if platform and platform not in ("twitter", "reddit"):
            return jsonify({"success": False, "error": "platform Parameter can only be 'twitter' Or 'reddit'"}), 400
        if not SimulationRunner.check_env_alive(simulation_id):
            return jsonify({
                "success": False,
                "error": "Simulation environment not running or closed. Please ensure simulation is started and wait for it to progress.",
            }), 400

        optimized_prompt = optimize_interview_prompt(prompt)
        result = SimulationRunner.interview_all_agents(
            simulation_id=simulation_id,
            prompt=optimized_prompt,
            platform=platform,
            timeout=timeout,
        )
        return jsonify({"success": result.get("success", False), "data": result})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except TimeoutError as exc:
        return jsonify({"success": False, "error": f"Wait for globalInterviewResponse timeout: {str(exc)}"}), 504
    except Exception as exc:
        logger.error(f"GlobalInterviewFailed: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500


@simulation_bp.route('/interview/history', methods=['POST'])
def get_interview_history():
    """Get stored interview history for a simulation."""
    try:
        data = request.get_json() or {}
        simulation_id = data.get('simulation_id')
        if simulation_id and not validate_simulation_id(simulation_id):
            return jsonify({"success": False, "error": "Invalid simulation_id format"}), 400

        platform = data.get('platform')
        agent_id = data.get('agent_id')
        limit = data.get('limit', 100)
        if not simulation_id:
            return jsonify({"success": False, "error": "Please provide simulation_id"}), 400

        history = SimulationRunner.get_interview_history(
            simulation_id=simulation_id,
            platform=platform,
            agent_id=agent_id,
            limit=limit,
        )
        return jsonify({
            "success": True,
            "data": {"count": len(history), "history": history},
        })
    except Exception as exc:
        logger.error(f"Failed to get interview history: {str(exc)}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "traceback": traceback.format_exc() if Config.DEBUG else None,
        }), 500
