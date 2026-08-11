"""
History, standalone profile generation, and database-query routes split from the main module.
"""

import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import current_app, request

from . import simulation_bp
from ..contracts.post_event_contract import Platform, PostCreatedEvent
from ..utils.endpoints import LOCAL_NO_AUTH_API_KEY, is_local_endpoint
from ..models.project import ProjectManager
from ..services.ai_route_resolver import AiRouteResolutionError
from ..services.entity_reader import EntityReader
from ..services.llm_routing_seed import build_preview_stage_route, resolve_route_api_key
from ..services.llm_runtime import parse_runtime_llm_config
from ..services.oasis_profile_generator import OasisProfileGenerator
from ..services.simulation_manager import SimulationManager
from ..services.simulation_runner import SimulationRunner
from ..utils.api_errors import ApiErrorCode
from ..utils.api_responses import handle_api_errors, json_error, json_success
from ..utils.artifact_locator import ArtifactLocator
from ..utils.llm_profile_resolver import expand_profile_in_data
from ..utils.validation import validate_simulation_id
from .simulation_common import logger


def _get_report_id_for_simulation(simulation_id: str) -> Optional[str]:
    """Return the ``report_id`` of the most recent report linked to ``simulation_id``."""
    reports_dir = ArtifactLocator.reports_dir()
    if not os.path.exists(reports_dir):
        return None

    matching_reports = []
    try:
        for report_folder in os.listdir(reports_dir):
            meta_file = ArtifactLocator.report_file(report_folder, 'meta.json')
            if not os.path.isdir(ArtifactLocator.report_dir(report_folder)):
                continue
            if not os.path.exists(meta_file):
                continue

            # Reports live outside the SimulationArtifactStore namespace
            # (separate ReportStore on the roadmap). Inline JSON read keeps
            # services-/api-layer free of json_io imports.
            try:
                with open(meta_file, "r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(f"Skipping unreadable report meta {meta_file}: {exc}")
                continue
            if meta and meta.get('simulation_id') == simulation_id:
                matching_reports.append({
                    'report_id': meta.get('report_id'),
                    'created_at': meta.get('created_at', ''),
                    'status': meta.get('status', ''),
                })

        if not matching_reports:
            return None
        matching_reports.sort(key=lambda item: item.get('created_at', ''), reverse=True)
        return matching_reports[0].get('report_id')
    except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.warning(f"Failed to find report for simulation {simulation_id}: {exc}")
        return None


def _connect_sqlite_readonly(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection in read-only mode with ``Row`` factory.

    Uses the ``file:<path>?mode=ro`` URI form so the driver both rejects any
    write attempt and refuses to create an empty database file if ``db_path``
    is missing — the caller is expected to ``os.path.exists`` beforehand.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@simulation_bp.route('/history', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get historical simulations")
def get_simulation_history():
    """Get enriched simulation history for the homepage/history views."""
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
        except Exception:  # noqa: BLE001 — defensive read; caller gets None/empty
            sim_dict['created_date'] = ''

        enriched_simulations.append(sim_dict)

    return json_success(enriched_simulations, count=len(enriched_simulations))


@simulation_bp.route('/generate-profiles', methods=['POST'])
@handle_api_errors(logger=logger, log_prefix="GenerateProfileFailed")
def generate_profiles():
    """Generate profiles directly from a graph without creating a simulation."""
    data = request.get_json() or {}
    graph_id = data.get('graph_id')
    if not graph_id:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            message="Please provide graph_id",
        )

    entity_types = data.get('entity_types')
    use_llm = data.get('use_llm', True)
    platform = data.get('platform', 'reddit')
    # Defensive Type-Prüfung: Endpoint hat keine strikte Pydantic-Validation,
    # Client kann auch Zahlen/Booleans senden. (Gemini-Code-Assist Finding,
    # PR #231.)
    llm_model_val = data.get('llm_model')
    llm_model_override = llm_model_val.strip() or None if isinstance(llm_model_val, str) else None

    # Track 3c: UI-Profil-Token in echtes Modell + Provider-Creds expandieren,
    # damit OasisProfileGenerator den aktiven api_key/base_url des Users
    # mitbekommt — sonst fällt LLMClient auf Config.LLM_API_KEY zurück, was
    # nach Track-1-Hardening bei OpenAI-Profilen sauber ValueError statt
    # 401-Loop wirft, aber den User-Workflow zerschießt.
    expand_profile_in_data(data)
    try:
        llm_runtime = parse_runtime_llm_config(data)
    except ValueError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=str(exc),
        )

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
        return json_error(
            ApiErrorCode.NOT_FOUND,
            status=404,
            message="No matching entities found",
        )

    # storage + graph_id durchreichen, damit OasisProfileGenerator die
    # Knowledge-Graph-Hybrid-Suche nutzen kann (Gemini-Code-Assist Finding,
    # PR #231).
    # Issue #799: api_key + base_url über denselben Store-Key-fähigen Resolver
    # wie simulation_prepare auflösen (statt nur Payload-Overrides zu lesen),
    # damit ein Fremd-Provider ohne Payload-Key sauber 422 statt 500 liefert.
    try:
        resolved_route = build_preview_stage_route(
            "persona_generation",
            llm_model_override=llm_model_override,
            llm_runtime=llm_runtime,
        )
    except AiRouteResolutionError as exc:
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=422,
            message=str(exc),
        )

    api_key = resolve_route_api_key(resolved_route, llm_runtime)
    base_url = resolved_route.base_url_sanitized
    if api_key is None and not is_local_endpoint(base_url):
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=422,
            message=(
                "kein api_key im Payload und kein Key in der Settings-DB "
                f"für Provider '{resolved_route.provider_id}'. "
                "Bitte in Einstellungen → LLM-Anbieter einen Schlüssel speichern "
                "oder im Sitzungsfeld eingeben."
            ),
        )
    if api_key is None and is_local_endpoint(base_url):
        # Lokaler Endpoint ohne Key ist zulaessig (#778) — Platzhalter statt
        # `None`, damit der Generator-Vertrag "Key + Base-URL aus derselben
        # Quelle" hier nicht faelschlich einen ValueError wirft.
        api_key = LOCAL_NO_AUTH_API_KEY
    generator = OasisProfileGenerator(
        model_name=llm_model_override,
        storage=storage,
        graph_id=graph_id,
        api_key=api_key,
        base_url=base_url,
    )
    profiles = generator.generate_profiles_from_entities(entities=filtered.entities, use_llm=use_llm)
    if platform == 'reddit':
        profiles_data = [profile.to_reddit_format() for profile in profiles]
    elif platform == 'twitter':
        profiles_data = [profile.to_twitter_format() for profile in profiles]
    else:
        profiles_data = [profile.to_dict() for profile in profiles]

    return json_success({
        "platform": platform,
        "entity_types": list(filtered.entity_types),
        "count": len(profiles_data),
        "profiles": profiles_data,
    })


@simulation_bp.route('/<simulation_id>/posts', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get posts")
def get_simulation_posts(simulation_id: str):
    """Get posts from a simulation SQLite database."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    platform = request.args.get('platform', 'reddit')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    db_path = ArtifactLocator.simulation_file(simulation_id, f"{platform}_simulation.db")
    if not os.path.exists(db_path):
        return json_success({
            "platform": platform,
            "count": 0,
            "posts": [],
            "message": "Database does not exist, simulation may not have run yet",
        })

    conn = _connect_sqlite_readonly(db_path)
    try:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM post ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            posts = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT COUNT(*) FROM post")
            total = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            posts = []
            total = 0
    finally:
        conn.close()

    return json_success({
        "platform": platform,
        "total": total,
        "count": len(posts),
        "posts": posts,
    })


@simulation_bp.route('/<simulation_id>/comments', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get comments")
def get_simulation_comments(simulation_id: str):
    """Get comments from the Reddit simulation database."""
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    post_id = request.args.get('post_id')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    db_path = ArtifactLocator.simulation_file(simulation_id, 'reddit_simulation.db')
    if not os.path.exists(db_path):
        return json_success({"count": 0, "comments": []})

    conn = _connect_sqlite_readonly(db_path)
    try:
        cursor = conn.cursor()
        try:
            if post_id:
                cursor.execute(
                    "SELECT * FROM comment WHERE post_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (post_id, limit, offset),
                )
            else:
                cursor.execute(
                    "SELECT * FROM comment ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            comments = [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            comments = []
    finally:
        conn.close()

    return json_success({"count": len(comments), "comments": comments})


# ---------------------------------------------------------------------------
# Feed-Snapshot (#1009) — /posts-Join (Option 1) gegen PostCreatedEvent.
# ---------------------------------------------------------------------------

# Twitter-CSV persistiert kein voice_register (analog #1186, aber CSV-Pfad);
# neutral-de ist der designierte Generator-Default, keine Erfindung.
_VOICE_REGISTER_FALLBACK = "neutral-de"


def _load_profiles_by_user_id(simulation_id: str, platform: str) -> Dict[int, Dict[str, Any]]:
    """Lädt die Profil-Datei einer Plattform und keyed sie nach ``user_id``.

    Reddit legt JSON ab, Twitter CSV. Stimmt ``platform`` mit keinen Profilen
    überein, wird ein leeres Mapping geliefert — der Caller fällt auf
    ``user``-Tabellen-Namen bzw. den voice_register-Default zurück.
    """
    if platform == "reddit":
        path = ArtifactLocator.simulation_file(simulation_id, "reddit_profiles.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Unlesbare reddit_profiles.json für %s: %s", simulation_id, exc)
            return {}
        return {int(entry["user_id"]): entry for entry in data if "user_id" in entry}

    if platform == "twitter":
        path = ArtifactLocator.simulation_file(simulation_id, "twitter_profiles.csv")
        if not os.path.exists(path):
            return {}
        profiles: Dict[int, Dict[str, Any]] = {}
        try:
            with open(path, "r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    if "user_id" in row and row["user_id"] != "":
                        profiles[int(row["user_id"])] = row
        except OSError as exc:
            logger.warning("Unlesbare twitter_profiles.csv für %s: %s", simulation_id, exc)
            return {}
        return profiles

    return {}


def _parse_created_at_tz(raw: Any) -> Optional[datetime]:
    """Macht den naiven SQLite-DATETIME-Wert tz-aware (UTC).

    OASIS schreibt ``created_at`` als naive Zeichenkette (``CURRENT_TIMESTAMP``
    bzw. Sim-Zeit). Wir interpretieren sie als UTC, damit das Frontend keinen
    Local-Time-Drift bekommt, sobald Container und Browser unterschiedliche
    Zeitzonen haben.
    """
    if raw is None:
        return None
    try:
        dt = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _build_snapshot_event(
    *,
    simulation_id: str,
    platform: str,
    post_id_prefixed: str,
    parent_post_id: Optional[str],
    user_id: Optional[int],
    agent_id: Optional[int],
    user_name: Optional[str],
    body: str,
    created_at: Any,
    num_likes: int,
    num_dislikes: int,
    profiles: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Baut ein validiertes PostCreatedEvent-Dict oder None bei unbrauchbaren Daten."""
    timestamp = _parse_created_at_tz(created_at)
    if timestamp is None or not body:
        return None

    profile = profiles.get(int(user_id)) if user_id is not None else None
    persona_name = (
        (profile.get("name") if profile else None)
        or user_name
        or (f"Agent {user_id}" if user_id is not None else "Unbekannt")
    )
    voice_register = (
        (profile.get("voice_register") if profile else None)
        or _VOICE_REGISTER_FALLBACK
    )
    persona_id = str(agent_id) if agent_id is not None else str(user_id)
    # Twitter hat kein Up/Down-Voting → score 0 (contract-semantik); Reddit
    # liefert den akkumulierten Voting-Stand.
    score = (num_likes - num_dislikes) if platform == "reddit" else 0

    event = PostCreatedEvent(
        simulation_id=simulation_id,
        post_id=post_id_prefixed,
        parent_post_id=parent_post_id,
        platform=Platform(platform),
        persona_id=persona_id,
        persona_name=persona_name,
        voice_register=voice_register,  # type: ignore[arg-type]
        is_simulated=True,
        body=body,
        timestamp=timestamp,
        score=score,
    )
    return event.model_dump(mode="json")


def _build_feed_snapshot(
    simulation_id: str,
    platform: str,
    limit: int,
) -> list[Dict[str, Any]]:
    """Joined SQLite post/comment + user + Profil-Datei → PostCreatedEvent-Liste."""
    db_path = ArtifactLocator.simulation_file(simulation_id, f"{platform}_simulation.db")
    if not os.path.exists(db_path):
        return []

    profiles = _load_profiles_by_user_id(simulation_id, platform)
    events: list[Dict[str, Any]] = []
    conn = _connect_sqlite_readonly(db_path)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT p.post_id, p.user_id, p.content, p.created_at, "
                "p.num_likes, p.num_dislikes, u.agent_id, u.name "
                "FROM post p LEFT JOIN user u ON p.user_id = u.user_id "
                "ORDER BY p.created_at ASC",
            )
            for row in cur.fetchall():
                ev = _build_snapshot_event(
                    simulation_id=simulation_id,
                    platform=platform,
                    post_id_prefixed=f"{platform}:{row['post_id']}",
                    parent_post_id=None,
                    user_id=row["user_id"],
                    agent_id=row["agent_id"],
                    user_name=row["name"],
                    body=row["content"] or "",
                    created_at=row["created_at"],
                    num_likes=row["num_likes"] or 0,
                    num_dislikes=row["num_dislikes"] or 0,
                    profiles=profiles,
                )
                if ev is not None:
                    events.append(ev)
        except sqlite3.OperationalError:
            return []

        # Reddit ist die Kommentar-Plattform; Kommentare hängen unter ihrem
        # Elternpost und füllen den Reply-Tree (#1216 5c).
        if platform == "reddit":
            try:
                cur.execute(
                    "SELECT c.comment_id, c.post_id, c.user_id, c.content, "
                    "c.created_at, c.num_likes, c.num_dislikes, u.agent_id, u.name "
                    "FROM comment c LEFT JOIN user u ON c.user_id = u.user_id "
                    "ORDER BY c.created_at ASC",
                )
                for row in cur.fetchall():
                    ev = _build_snapshot_event(
                        simulation_id=simulation_id,
                        platform=platform,
                        post_id_prefixed=f"{platform}:comment:{row['comment_id']}",
                        parent_post_id=f"{platform}:{row['post_id']}",
                        user_id=row["user_id"],
                        agent_id=row["agent_id"],
                        user_name=row["name"],
                        body=row["content"] or "",
                        created_at=row["created_at"],
                        num_likes=row["num_likes"] or 0,
                        num_dislikes=row["num_dislikes"] or 0,
                        profiles=profiles,
                    )
                    if ev is not None:
                        events.append(ev)
            except sqlite3.OperationalError:
                # Ohne comment-Tabelle liefert der Snapshot nur Posts.
                pass
    finally:
        conn.close()

    # Chronologisch sortieren (ältester zuerst — useSimFeed.ingestMany hängt an)
    # und auf das Limit kappen. Bei fertigen Simulationen mit > limit Posts gäbe
    # `events[:limit]` nur den Anfang wieder und keine nachfolgenden SSE-Events
    # füllen die Lücke — also die NEUESTEN limit Entries behalten (#1009).
    events.sort(key=lambda e: e["timestamp"])
    if limit > 0 and len(events) > limit:
        events = events[-limit:]
    return events


@simulation_bp.route('/<simulation_id>/feed-snapshot', methods=['GET'])
@handle_api_errors(logger=logger, log_prefix="Failed to get feed snapshot")
def get_simulation_feed_snapshot(simulation_id: str):
    """Feed-Snapshot beim Mount — bestehende Posts als PostCreatedEvent-Liste (#1009).

    Joined die SQLite ``post``/``comment``/``user``-Tabellen gegen die
    Plattform-Profil-Datei und liefert echte ``PostCreatedEvent``-Einträge,
    die gegen den Layer-0-Vertrag validieren — ohne erfundene Feldwerte.
    ``post_id`` ist plattformpräfixt (``<platform>:<id>`` bzw.
    ``<platform>:comment:<id>``), damit es plattformübergreifend eindeutig ist
    und mit nachfolgenden SSE-Events dedupliziert.
    """
    if not validate_simulation_id(simulation_id):
        return json_error(
            ApiErrorCode.INVALID_ID,
            message="Invalid simulation_id format",
        )

    platform = request.args.get('platform', 'reddit')
    if platform not in ("reddit", "twitter"):
        return json_error(
            ApiErrorCode.VALIDATION_FAILED,
            status=400,
            message=f"platform muss 'reddit' oder 'twitter' sein, erhalten: {platform}",
        )
    limit = request.args.get('limit', 200, type=int)

    posts = _build_feed_snapshot(simulation_id, platform, limit)
    return json_success({
        "platform": platform,
        "count": len(posts),
        "posts": posts,
    })
