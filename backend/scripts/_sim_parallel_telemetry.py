"""Telemetry, logging, and Redis event emission for parallel simulation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import shutil
import sys
from typing import Any, Dict, Optional

from oasis.social_platform.typing import ActionType
from app.contracts.persona_contract import VOICE_REGISTER_VALUES

try:
    from ._sim_common import (
        apply_camel_context_floor,
        install_bert_memory_profile,
        install_memory_sampler,
        install_recsys_mean_pooling_patch,
        install_reddit_nested_comments_patch,
        make_default_memory_sink,
        resolve_runtime_paths,
    )
except ImportError:
    from _sim_common import (
        apply_camel_context_floor,
        install_bert_memory_profile,
        install_memory_sampler,
        install_recsys_mean_pooling_patch,
        install_reddit_nested_comments_patch,
        make_default_memory_sink,
        resolve_runtime_paths,
    )

def _get_rps_attr(name: str, fallback: Any) -> Any:
    mod = sys.modules.get("run_parallel_simulation")
    if mod is not None and hasattr(mod, name):
        return getattr(mod, name)
    return fallback

def _noop_memory_stop() -> None:
    """No-Op-Placeholder, bis ``_install_runtime_profile()`` das echte Stop setzt."""

_memory_stop = _noop_memory_stop

def _install_runtime_profile(project_root: Optional[str] = None) -> None:
    """BERT-Memory-Profil + Sampler + Camel-Context-Floor installieren."""
    global _memory_stop
    _bert_profile = install_bert_memory_profile()
    if project_root is None:
        _runtime_paths = resolve_runtime_paths(__file__)
        project_root = _runtime_paths.project_root
    _memory_stop = install_memory_sampler(make_default_memory_sink(project_root))
    logging.getLogger("agora.run_parallel_simulation").info("bert-memory profile = %s", _bert_profile)
    _mean_pooling_patched = install_recsys_mean_pooling_patch()
    logging.getLogger("agora.run_parallel_simulation").info(
        "twhin-bert mean-pooling patch installed = %s (#1236)", _mean_pooling_patched
    )
    _nested_comments_patched = install_reddit_nested_comments_patch()
    logging.getLogger("agora.run_parallel_simulation").info(
        "reddit nested-comments patch installed = %s (#1713 S5)", _nested_comments_patched
    )
    _camel_context_floor = apply_camel_context_floor()
    logging.getLogger("agora.run_parallel_simulation").info("context-patch token_limit floor = %s", _camel_context_floor)

def disable_oasis_logging():
    """
    Disable verbose logging output from OASIS library
    OASIS logging is too verbose (logs every agent's observation and action), we use our own action_logger
    """
    oasis_loggers = [
        "social.agent",
        "social.twitter",
        "social.rec",
        "oasis.env",
        "table",
    ]

    for logger_name in oasis_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)
        logger.handlers.clear()
        logger.propagate = False

def init_logging_for_simulation(simulation_dir: str):
    """
    Initialize simulation log configuration

    Args:
        simulation_dir: Simulation directory path
    """
    disable_oasis_logging()

    old_log_dir = os.path.join(simulation_dir, "log")
    if os.path.exists(old_log_dir):
        shutil.rmtree(old_log_dir, ignore_errors=True)

_redis_clients: Dict[str, Any] = {}

def _get_redis_client(redis_url: str) -> Any:
    """Lazy-init und cache eines asyncio-Redis-Clients pro URL."""
    if redis_url not in _redis_clients:
        import redis.asyncio as aioredis  # type: ignore[import-not-found]
        _redis_clients[redis_url] = aioredis.from_url(redis_url, decode_responses=True)
    return _redis_clients[redis_url]

async def _emit_post_created_to_redis(
    simulation_id: str,
    platform: str,
    action_data: Dict[str, Any],
    redis_url: Optional[str],
    sim_time_iso: Optional[str] = None,
    round_num: Optional[int] = None,
) -> None:
    """Publish a PostCreatedEvent to Redis after a CREATE_POST/CREATE_COMMENT/
    REPOST/QUOTE_POST action.

    Runs inside the asyncio event loop of the OASIS subprocess (Pfad B).
    Silently no-ops when REDIS_URL is unset or Redis is unreachable.

    Channel: agora:sim:{simulation_id}:post_created

    ``post_id`` ist plattformpräfixt (``<platform>:<id>`` bzw.
    ``<platform>:comment:<id>``), damit es plattformübergreifend eindeutig ist
    und mit dem Mount-Snapshot (#1009) dedupliziert. Kommentare tragen
    ``parent_post_id`` = Elternpost, damit der Reddit-Reply-Tree Äste bekommt
    (#1216 5c).

    #1713 UI-2a — ``kind``/Bezugsfelder fuer die Thread-/Diskursdarstellung:
    REPOST und QUOTE_POST lesen ``original_post_id``/``original_content``/
    ``original_author_name``/``quote_content``, die
    ``oasis_action_ingest._enrich_action_context`` bereits anreichert.
    ``parent_comment_id`` bleibt None — Reddit kennt bislang nur eine
    Verschachtelungsebene (Kommentar -> Post), ein Backfill fuer tiefere
    Kommentar-Baeume ist ein Folge-Slice. ``root_post_id`` wird nur gesetzt,
    wenn er sich ohne mehrstufige Aufloesung direkt aus den vorhandenen
    Referenzfeldern ergibt (Kommentar -> Elternpost, Repost -> Original) —
    ein Zitat startet konzeptionell einen eigenen Strang und bekommt daher
    keinen root_post_id.
    """
    if not redis_url:
        return
    action_args = action_data.get("action_args", {})
    action_type = action_data.get("action_type", "CREATE_POST")
    platform_value = "twitter" if "twitter" in platform.lower() else "reddit"

    kind = {
        "CREATE_COMMENT": "comment",
        "REPOST": "repost",
        "QUOTE_POST": "quote",
    }.get(action_type, "post")

    quoted_post_id: Optional[str] = None
    quote_body: Optional[str] = None
    reposted_post_id: Optional[str] = None
    root_post_id: Optional[str] = None
    parent_persona_id: Optional[str] = None
    parent_persona_name: Optional[str] = None

    # post_id / parent_post_id plattformpräfixen; Kommentare referenzieren
    # ihren Elternpost, Posts haben keinen Parent (top-level).
    parent_comment_id_val: Optional[str] = None
    if action_type == "CREATE_COMMENT":
        body = action_args.get("content") or action_args.get("text") or ""
        raw_id = action_args.get("comment_id") or action_args.get("id")
        parent_raw = action_args.get("post_id") or action_args.get("new_post_id")
        if not raw_id or not parent_raw or not body:
            return
        post_id = f"{platform_value}:comment:{raw_id}"
        parent_post_id = f"{platform_value}:{parent_raw}"
        root_post_id = parent_post_id
        author_agent_id = action_args.get("post_author_agent_id")
        parent_persona_id = str(author_agent_id) if author_agent_id is not None else None
        parent_persona_name = action_args.get("post_author_name") or None
        # #1713 S5: parent_comment_id aus enriched action_args (oasis_action_ingest befuellt).
        raw_pcid = action_args.get("parent_comment_id")
        if raw_pcid is not None:
            parent_comment_id_val = str(raw_pcid)
    elif action_type == "REPOST":
        # Ein reiner Repost hat keinen eigenen Text — der geteilte Beitrag
        # steht unter reposted_post_id (Contract-Ausnahme fuer body).
        body = ""
        raw_id = str(action_args.get("new_post_id") or action_args.get("post_id") or "")
        if not raw_id:
            return
        post_id = f"{platform_value}:{raw_id}"
        parent_post_id = None
        original_raw = action_args.get("original_post_id")
        if original_raw:
            reposted_post_id = f"{platform_value}:{original_raw}"
            root_post_id = reposted_post_id
        author_agent_id = action_args.get("original_author_agent_id")
        parent_persona_id = str(author_agent_id) if author_agent_id is not None else None
        parent_persona_name = action_args.get("original_author_name") or None
    elif action_type == "QUOTE_POST":
        # quote_content ist die eigene Kommentierung der zitierenden Person
        # (Feed-body); original_content ist der Text des zitierten Beitrags
        # (quote_body, nested Block).
        body = action_args.get("quote_content") or ""
        raw_id = str(action_args.get("new_post_id") or action_args.get("post_id") or "")
        if not raw_id or not body:
            return
        post_id = f"{platform_value}:{raw_id}"
        parent_post_id = None
        quoted_raw = action_args.get("quoted_id")
        if quoted_raw:
            quoted_post_id = f"{platform_value}:{quoted_raw}"
        quote_body = action_args.get("original_content") or None
        author_agent_id = action_args.get("original_author_agent_id")
        parent_persona_id = str(author_agent_id) if author_agent_id is not None else None
        parent_persona_name = action_args.get("original_author_name") or None
    else:  # CREATE_POST
        body = action_args.get("content") or action_args.get("text") or ""
        raw_id = str(
            action_args.get("post_id")
            or action_args.get("new_post_id")
            or action_args.get("id")
            or ""
        )
        if not raw_id or not body:
            return
        post_id = f"{platform_value}:{raw_id}"
        parent_raw = action_args.get("parent_post_id")
        parent_post_id = f"{platform_value}:{parent_raw}" if parent_raw else None

    persona_id = str(action_data.get("agent_id", ""))
    persona_name = action_data.get("agent_name") or f"Agent {persona_id}"
    # voice_register-Vokabular ist der Profil-Generator-SSoT
    # (siehe ``persona_contract.VoiceRegister``); altes Vokabular
    # (formal/casual/jugendsprache) war nie an den Generator angebunden.
    voice_register = str(action_args.get("voice_register", "neutral-de"))
    if voice_register not in VOICE_REGISTER_VALUES:
        voice_register = "neutral-de"

    # Voting-Stand aus der Simulations-DB (fetch_new_actions_from_db reichert
    # ihn an). Twitter kennt kein Up/Down-Voting → 0, gleiche Semantik wie im
    # Mount-Snapshot (#1209 5b).
    if platform_value == "reddit":
        try:
            score = int(action_args.get("score", 0) or 0)
        except (TypeError, ValueError):
            score = 0
    else:
        score = 0

    payload: Dict[str, Any] = {
        "event_type": "post_created",
        "simulation_id": simulation_id,
        "post_id": post_id,
        "parent_post_id": parent_post_id,
        "platform": platform_value,
        "persona_id": persona_id,
        "persona_name": persona_name,
        "voice_register": voice_register,
        "is_simulated": True,
        "body": body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": score,
        # Task 1 — virtuelle Sim-Zeit pro CREATE_POST. None bei alten Callern.
        "sim_time": sim_time_iso,
        # #1713 UI-2a — Thread-/Diskursfelder.
        "kind": kind,
        "round_num": round_num,
        # #1713 S5: aus action_args befuellt wenn nested-comments-Patch aktiv (Reddit).
        "parent_comment_id": parent_comment_id_val,
        "root_post_id": root_post_id,
        "quoted_post_id": quoted_post_id,
        "reposted_post_id": reposted_post_id,
        "quote_body": quote_body,
        "parent_persona_id": parent_persona_id,
        "parent_persona_name": parent_persona_name,
        # Ein frisch erzeugter Beitrag hat per Definition 0 Likes — spaetere
        # Votes aktualisieren dieses bereits gesendete Live-Event nicht
        # (gleiche Semantik wie ``score``, siehe Docstring oben).
        "like_count": 0,
    }
    channel = f"agora:sim:{simulation_id}:post_created"
    try:
        get_client_fn = _get_rps_attr("_get_redis_client", _get_redis_client)
        client = get_client_fn(redis_url)
        await client.publish(channel, json.dumps(payload, ensure_ascii=False))
    except Exception:
        # Non-fatal: SSE post-events are best-effort; simulation must not crash.
        logging.getLogger("agora.run_parallel_simulation").debug(
            "emit_post_created_to_redis failed for sim=%s post=%s (non-fatal)",
            simulation_id,
            post_id,
        )


TWITTER_ACTIONS = [
    ActionType.CREATE_POST,
    ActionType.LIKE_POST,
    ActionType.REPOST,
    ActionType.FOLLOW,
    ActionType.DO_NOTHING,
    ActionType.QUOTE_POST,
    ActionType.CREATE_COMMENT,
    ActionType.LIKE_COMMENT,
]

# Reddit available actions (INTERVIEW not included, INTERVIEW can only be triggered manually via ManualAction)
REDDIT_ACTIONS = [
    ActionType.LIKE_POST,
    ActionType.DISLIKE_POST,
    ActionType.CREATE_POST,
    ActionType.CREATE_COMMENT,
    ActionType.LIKE_COMMENT,
    ActionType.DISLIKE_COMMENT,
    ActionType.SEARCH_POSTS,
    ActionType.SEARCH_USER,
    ActionType.TREND,
    ActionType.REFRESH,
    ActionType.DO_NOTHING,
    ActionType.FOLLOW,
    ActionType.MUTE,
]

