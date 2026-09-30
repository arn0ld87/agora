"""OASIS-Trace-Ingest: gemeinsame Logik fuer den Parallel- und den
Single-Platform-Runner (#1713).

``run_parallel_simulation.py`` (Twitter+Reddit gleichzeitig) und
``sim_runtime/platform_runner.py`` (``SinglePlatformRunner``, eine Plattform)
lasen dieselbe OASIS-SQLite-``trace``-Tabelle bisher mit unterschiedlichem
Code — der Single-Platform-Pfad rief den Action-Logger nie auf, Runs darueber
hatten kein ``actions.jsonl``. Die Lese-/Anreicherungs-Logik ist plattform-
neutral (reine SQLite-Abfragen + Dict-Transformation) und liegt deshalb hier
als gemeinsamer Helfer statt zweimal dupliziert zu werden.

``run_parallel_simulation.py`` importiert alle oeffentlichen Namen re-exportierend
weiter, damit bestehende Tests (``import run_parallel_simulation as rps``,
``rps.fetch_new_actions_from_db(...)``) unveraendert funktionieren.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Non-core action types to be filtered (these actions have low analytical value)
FILTERED_ACTIONS = {'refresh', 'sign_up'}

# Action type mapping table (Database name -> standard name)
ACTION_TYPE_MAP = {
    'create_post': 'CREATE_POST',
    'like_post': 'LIKE_POST',
    'dislike_post': 'DISLIKE_POST',
    'repost': 'REPOST',
    'quote_post': 'QUOTE_POST',
    'follow': 'FOLLOW',
    'mute': 'MUTE',
    'create_comment': 'CREATE_COMMENT',
    'like_comment': 'LIKE_COMMENT',
    'dislike_comment': 'DISLIKE_COMMENT',
    'search_posts': 'SEARCH_POSTS',
    'search_user': 'SEARCH_USER',
    'trend': 'TREND',
    'do_nothing': 'DO_NOTHING',
    'interview': 'INTERVIEW',
}


def get_agent_names_from_config(config: Dict[str, Any]) -> Dict[int, str]:
    """
    Get mapping of agent_id -> entity_name from simulation_config

    This allows displaying real entity names in actions.jsonl instead of codes like "Agent_0"

    Args:
        config: Content of simulation_config.json

    Returns:
        Mapping dictionary of agent_id -> entity_name
    """
    agent_names = {}
    agent_configs = config.get("agent_configs", [])

    for agent_config in agent_configs:
        agent_id = agent_config.get("agent_id")
        entity_name = agent_config.get("entity_name", f"Agent_{agent_id}")
        if agent_id is not None:
            agent_names[agent_id] = entity_name

    return agent_names


def get_max_trace_rowid(db_path: str) -> int:
    """Liefert den hoechsten ``rowid`` in der ``trace``-Tabelle.

    Nach einem manuell geloggten Initial-Post-Step muss ``last_rowid`` auf
    diesen Stand gesetzt werden, sonst liest ``fetch_new_actions_from_db`` in
    der ersten Hauptrunde dieselbe(n) Zeile(n) erneut und der Startpost landet
    doppelt im Action-Log (#1713).

    Args:
        db_path: Pfad zur OASIS-SQLite

    Returns:
        Hoechster ``rowid`` in ``trace``, oder 0 wenn Datei/Tabelle leer
        oder nicht vorhanden ist.
    """
    if not os.path.exists(db_path):
        return 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(rowid) FROM trace")
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.warning("get_max_trace_rowid failed for %s: %s", db_path, e)
        return 0


def fetch_new_actions_from_db(
    db_path: str,
    last_rowid: int,
    agent_names: Dict[int, str]
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Get new action records from Database and supplement complete context information

    Args:
        db_path: Database file path
        last_rowid: Maximum rowid value from last read (use rowid instead of created_at because different platforms have different created_at formats)
        agent_names: agent_id -> agent_name mapping

    Returns:
        (actions_list, new_last_rowid)
        - actions_list: List of actions, each element contains agent_id, agent_name, action_type, action_args (including context information)
        - new_last_rowid: New maximum rowid value
    """
    actions = []
    new_last_rowid = last_rowid

    if not os.path.exists(db_path):
        return actions, new_last_rowid

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Use rowid to track processed records (rowid is SQLite's built-in auto-increment field)
        # This avoids created_at format differences (Twitter uses integers, Reddit uses datetime strings)
        cursor.execute("""
            SELECT rowid, user_id, action, info
            FROM trace
            WHERE rowid > ?
            ORDER BY rowid ASC
        """, (last_rowid,))

        for rowid, user_id, action, info_json in cursor.fetchall():
            # Update maximum rowid
            new_last_rowid = rowid

            # Filter non-core actions
            if action in FILTERED_ACTIONS:
                continue

            # Parse action arguments
            try:
                action_args = json.loads(info_json) if info_json else {}
            except json.JSONDecodeError:
                action_args = {}

            # Simplify action_args, keep only key fields (keep full content, no truncation)
            simplified_args = {}
            if 'content' in action_args:
                simplified_args['content'] = action_args['content']
            if 'post_id' in action_args:
                simplified_args['post_id'] = action_args['post_id']
            if 'comment_id' in action_args:
                simplified_args['comment_id'] = action_args['comment_id']
            if 'quoted_id' in action_args:
                simplified_args['quoted_id'] = action_args['quoted_id']
            if 'new_post_id' in action_args:
                simplified_args['new_post_id'] = action_args['new_post_id']
            if 'reposted_id' in action_args:
                simplified_args['reposted_id'] = action_args['reposted_id']
            if 'follow_id' in action_args:
                simplified_args['follow_id'] = action_args['follow_id']
            if 'query' in action_args:
                simplified_args['query'] = action_args['query']
            if 'like_id' in action_args:
                simplified_args['like_id'] = action_args['like_id']
            if 'dislike_id' in action_args:
                simplified_args['dislike_id'] = action_args['dislike_id']

            # Convert action type names
            action_type = ACTION_TYPE_MAP.get(action, action.upper())

            # Supplement context information (post content, usernames, etc.)
            _enrich_action_context(cursor, action_type, simplified_args, agent_names)

            actions.append({
                'agent_id': user_id,
                'agent_name': agent_names.get(user_id, f'Agent_{user_id}'),
                'action_type': action_type,
                'action_args': simplified_args,
            })

        conn.close()
    except Exception as e:
        logger.warning("Failed to read Database actions from %s: %s", db_path, e)

    return actions, new_last_rowid


def _enrich_action_context(
    cursor,
    action_type: str,
    action_args: Dict[str, Any],
    agent_names: Dict[int, str]
) -> None:
    """
    for actionSupplement context information (post content, usernames, etc.)

    Args:
        cursor: Database cursor
        action_type: Action type
        action_args: Action arguments (will be modified)
        agent_names: agent_id -> agent_name mapping
    """
    try:
        # Like/dislike post: supplement post content and author
        if action_type in ('LIKE_POST', 'DISLIKE_POST'):
            post_id = action_args.get('post_id')
            if post_id:
                post_info = _get_post_info(cursor, post_id, agent_names)
                if post_info:
                    action_args['post_content'] = post_info.get('content', '')
                    action_args['post_author_name'] = post_info.get('author_name', '')

        # Repost: supplement original post content and author
        elif action_type == 'REPOST':
            new_post_id = action_args.get('new_post_id')
            if new_post_id:
                # Repost's original_post_id points to original post
                cursor.execute("""
                    SELECT original_post_id FROM post WHERE post_id = ?
                """, (new_post_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    original_post_id = row[0]
                    action_args['original_post_id'] = original_post_id
                    original_info = _get_post_info(cursor, original_post_id, agent_names)
                    if original_info:
                        action_args['original_content'] = original_info.get('content', '')
                        action_args['original_author_name'] = original_info.get('author_name', '')
                        action_args['original_author_agent_id'] = original_info.get('author_agent_id')

        # Quote post: supplement original post content, author, and quote comment
        elif action_type == 'QUOTE_POST':
            quoted_id = action_args.get('quoted_id')
            new_post_id = action_args.get('new_post_id')

            if quoted_id:
                original_info = _get_post_info(cursor, quoted_id, agent_names)
                if original_info:
                    action_args['original_content'] = original_info.get('content', '')
                    action_args['original_author_name'] = original_info.get('author_name', '')
                    action_args['original_author_agent_id'] = original_info.get('author_agent_id')

            # Get quote post comment content (quote_content)
            if new_post_id:
                cursor.execute("""
                    SELECT quote_content FROM post WHERE post_id = ?
                """, (new_post_id,))
                row = cursor.fetchone()
                if row and row[0]:
                    action_args['quote_content'] = row[0]

        # Follow user: supplement followed user name
        elif action_type == 'FOLLOW':
            follow_id = action_args.get('follow_id')
            if follow_id:
                # Get followee_id from follow table
                cursor.execute("""
                    SELECT followee_id FROM follow WHERE follow_id = ?
                """, (follow_id,))
                row = cursor.fetchone()
                if row:
                    followee_id = row[0]
                    target_name = _get_user_name(cursor, followee_id, agent_names)
                    if target_name:
                        action_args['target_user_name'] = target_name

        # Mute user: supplement muted user name
        elif action_type == 'MUTE':
            # Get user_id or target_id from action_args
            target_id = action_args.get('user_id') or action_args.get('target_id')
            if target_id:
                target_name = _get_user_name(cursor, target_id, agent_names)
                if target_name:
                    action_args['target_user_name'] = target_name

        # Like/dislike comment: supplement comment content and author
        elif action_type in ('LIKE_COMMENT', 'DISLIKE_COMMENT'):
            comment_id = action_args.get('comment_id')
            if comment_id:
                comment_info = _get_comment_info(cursor, comment_id, agent_names)
                if comment_info:
                    action_args['comment_content'] = comment_info.get('content', '')
                    action_args['comment_author_name'] = comment_info.get('author_name', '')

        # Post comment: supplement commented post information
        elif action_type == 'CREATE_COMMENT':
            # OASIS schreibt in die trace-Zeile einer Kommentar-Aktion nur
            # content + comment_id; der Elternpost steht ausschließlich in der
            # comment-Tabelle. Ohne diese Auflösung bleibt post_id leer, der
            # Live-Emit verwirft jeden realen Kommentar und der Reddit-Feed
            # bleibt leer — 86 % der Reddit-Aktivität sind Kommentare
            # (#1209 5c/5d).
            post_id = action_args.get('post_id')
            if not post_id:
                comment_id = action_args.get('comment_id')
                if comment_id:
                    cursor.execute(
                        "SELECT post_id FROM comment WHERE comment_id = ?", (comment_id,)
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        post_id = row[0]
                        action_args['post_id'] = post_id
            if post_id:
                post_info = _get_post_info(cursor, post_id, agent_names)
                if post_info:
                    action_args['post_content'] = post_info.get('content', '')
                    action_args['post_author_name'] = post_info.get('author_name', '')
                    action_args['post_author_agent_id'] = post_info.get('author_agent_id')
            _attach_engagement_score(cursor, 'comment', 'comment_id', action_args)

        # Create post: Voting-Stand zum Erzeugungszeitpunkt mitführen, damit der
        # Live-Feed einen echten Wert zeigt statt einer hartkodierten 0
        # (#1209 5b). Die Post-ID wird vorher normalisiert: der Emitter kennt
        # den Fallback post_id → new_post_id, und ohne dieselbe Normalisierung
        # bliebe ein Post, dessen Trace-Zeile new_post_id trägt, ohne Score —
        # der Feed zeigte wieder eine unechte 0. Den dritten Emitter-Fallback
        # `id` gibt es hier bewusst nicht: fetch_new_actions_from_db reicht
        # diesen Schlüssel gar nicht durch, er kann action_args nie erreichen.
        elif action_type == 'CREATE_POST':
            if not action_args.get('post_id') and action_args.get('new_post_id'):
                action_args['post_id'] = action_args['new_post_id']
            _attach_engagement_score(cursor, 'post', 'post_id', action_args)

    except Exception:
        # Context supplement failure does not affect main process
        logger.warning("Failed to supplement action context", exc_info=True)


def _attach_engagement_score(
    cursor,
    table: str,
    id_field: str,
    action_args: Dict[str, Any],
) -> None:
    """Setzt ``action_args['score']`` auf ``num_likes - num_dislikes``.

    Quelle ist die OASIS-SQLite (``post`` bzw. ``comment``). Der Wert gilt für
    den Erzeugungszeitpunkt der Action — spätere Votes derselben Simulation
    aktualisieren ein bereits emittiertes Feed-Event nicht. Der Mount-Snapshot
    liefert dafür den akkumulierten Endstand.

    ``table`` und ``id_field`` sind ausschließlich modulinterne Literale
    ('post'/'post_id', 'comment'/'comment_id') — keine Nutzereingabe.
    """
    row_id = action_args.get(id_field)
    if not row_id:
        return
    cursor.execute(
        f"SELECT num_likes, num_dislikes FROM {table} WHERE {id_field} = ?",  # noqa: S608
        (row_id,),
    )
    row = cursor.fetchone()
    if not row:
        return
    action_args['score'] = int(row[0] or 0) - int(row[1] or 0)


def _get_post_info(
    cursor,
    post_id: int,
    agent_names: Dict[int, str]
) -> Optional[Dict[str, str]]:
    """
    Get post information

    Args:
        cursor: Database cursor
        post_id: Post ID
        agent_names: agent_id -> agent_name mapping

    Returns:
        Dictionary containing content and author_name, or None
    """
    try:
        cursor.execute("""
            SELECT p.content, p.user_id, u.agent_id
            FROM post p
            LEFT JOIN user u ON p.user_id = u.user_id
            WHERE p.post_id = ?
        """, (post_id,))
        row = cursor.fetchone()
        if row:
            content = row[0] or ''
            user_id = row[1]
            agent_id = row[2]

            # Preferentially use name from agent_names
            author_name = ''
            if agent_id is not None and agent_id in agent_names:
                author_name = agent_names[agent_id]
            elif user_id:
                # Get name from user table
                cursor.execute("SELECT name, user_name FROM user WHERE user_id = ?", (user_id,))
                user_row = cursor.fetchone()
                if user_row:
                    author_name = user_row[0] or user_row[1] or ''

            # author_agent_id (#1713 UI-2a): stabile Persona-ID des Autors,
            # damit Emitter/Snapshot eine parent_persona_id fuellen koennen
            # statt nur den Anzeigenamen. None wenn agent_id unaufloesbar
            # (Fallback-User ohne OASIS-agent_id-Zuordnung).
            return {
                'content': content,
                'author_name': author_name,
                'author_agent_id': agent_id,
            }
    except Exception:
        pass
    return None


def _get_user_name(
    cursor,
    user_id: int,
    agent_names: Dict[int, str]
) -> Optional[str]:
    """
    Get user name

    Args:
        cursor: Database cursor
        user_id: User ID
        agent_names: agent_id -> agent_name mapping

    Returns:
        User name, or None
    """
    try:
        cursor.execute("""
            SELECT agent_id, name, user_name FROM user WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        if row:
            agent_id = row[0]
            name = row[1]
            user_name = row[2]

            # Preferentially use name from agent_names
            if agent_id is not None and agent_id in agent_names:
                return agent_names[agent_id]
            return name or user_name or ''
    except Exception:
        pass
    return None


def _get_comment_info(
    cursor,
    comment_id: int,
    agent_names: Dict[int, str]
) -> Optional[Dict[str, str]]:
    """
    Get comment information

    Args:
        cursor: Database cursor
        comment_id: Comment ID
        agent_names: agent_id -> agent_name mapping

    Returns:
        Dictionary containing content and author_name, or None
    """
    try:
        cursor.execute("""
            SELECT c.content, c.user_id, u.agent_id
            FROM comment c
            LEFT JOIN user u ON c.user_id = u.user_id
            WHERE c.comment_id = ?
        """, (comment_id,))
        row = cursor.fetchone()
        if row:
            content = row[0] or ''
            user_id = row[1]
            agent_id = row[2]

            # Preferentially use name from agent_names
            author_name = ''
            if agent_id is not None and agent_id in agent_names:
                author_name = agent_names[agent_id]
            elif user_id:
                # Get name from user table
                cursor.execute("SELECT name, user_name FROM user WHERE user_id = ?", (user_id,))
                user_row = cursor.fetchone()
                if user_row:
                    author_name = user_row[0] or user_row[1] or ''

            return {'content': content, 'author_name': author_name}
    except Exception:
        pass
    return None
