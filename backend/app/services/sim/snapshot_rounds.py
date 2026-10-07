"""Runden-Zuordnung fuer den Feed-Snapshot beendeter Laeufe (#1801 Etappe 4).

Die OASIS-SQLite-Tabellen ``post``/``comment`` kennen keine Runde; die
``trace``-Tabelle ebenfalls nicht. Die Runde steht nur im Aktionsprotokoll
``<sim>/<platform>/actions.jsonl`` (Feld ``round``, identisch zu dem Wert, den
der Live-Emit als ``round_num`` sendet). Dieses Modul verknuepft Datenbankzeilen
und Protokolleintraege **ausschliesslich ueber eindeutige Schluessel**:

* Kommentar -> ``CREATE_COMMENT.action_args.comment_id``
* Repost/Zitat -> ``REPOST``/``QUOTE_POST.action_args.new_post_id``
* Originalpost -> ``(agent_id, content)`` von ``CREATE_POST`` (``CREATE_POST``
  traegt im Protokoll keine ``post_id``)

Zusaetzlich liefert der Index den Protokollzeitpunkt der Aktion. Twitter-
Datenbanken speichern in ``post``/``comment`` keinen Zeitstempel, sondern den
OASIS-Zeitschritt als Ganzzahl (belegt an sim_504dc7b26443: ``0..6`` bei 48
Runden); der Snapshot nutzt dann den Protokollzeitpunkt — dieselbe Semantik
wie der Live-Emit (Wanduhr beim Emittieren).

Gibt es zu einem Schluessel mehrere Runden, oder passt die Zahl der
Protokolleintraege nicht zur Zahl der Datenbankzeilen, bleibt die Runde
``None`` — es wird nichts geschaetzt. Dasselbe gilt fuer Protokolle, die
mehrere ``simulation_start``-Ereignisse enthalten: dort ist nicht belegbar,
zu welchem Start die Datenbankzeile gehoert.
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from typing import Any, NamedTuple, Optional

logger = logging.getLogger(__name__)

_REFERENCE_ACTIONS = frozenset({"QUOTE_POST", "REPOST"})


def _as_round(raw: Any) -> Optional[int]:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return None
    return raw


class ActionRef(NamedTuple):
    """Belegte Protokoll-Zuordnung einer Datenbankzeile.

    ``timestamp`` ist der Protokollzeitpunkt der Aktion (Wanduhr, ISO-8601
    ohne Zeitzone) und nur gesetzt, wenn genau ein Protokolleintrag passt.
    """

    round_num: int
    timestamp: Optional[str]


def _resolve(entries: Optional[list[ActionRef]], expected: Optional[int] = None) -> Optional[ActionRef]:
    """Eindeutige Zuordnung oder None.

    Runde: alle Eintraege liegen in derselben Runde (und ``expected`` passt, falls
    gegeben). Zeitstempel: zusaetzlich nur bei genau einem Eintrag.
    """
    if not entries or (expected is not None and len(entries) != expected):
        return None
    rounds = {entry.round_num for entry in entries}
    if len(rounds) != 1:
        return None
    return ActionRef(next(iter(rounds)), entries[0].timestamp if len(entries) == 1 else None)


class SnapshotRoundIndex:
    """Eindeutige Protokoll-Zuordnung je Datenbankzeile; ``None`` wenn nicht belegbar."""

    __slots__ = ("_comments", "_references", "_originals")

    def __init__(self) -> None:
        self._comments: dict[str, list[ActionRef]] = defaultdict(list)
        self._references: dict[str, list[ActionRef]] = defaultdict(list)
        self._originals: dict[tuple[int, str], list[ActionRef]] = defaultdict(list)

    def add(
        self, action_type: str, agent_id: int, args: dict[str, Any], ref: ActionRef
    ) -> None:
        if action_type == "CREATE_COMMENT":
            comment_id = args.get("comment_id")
            if comment_id is not None:
                self._comments[str(comment_id)].append(ref)
        elif action_type in _REFERENCE_ACTIONS:
            new_post_id = args.get("new_post_id")
            if new_post_id is not None:
                self._references[str(new_post_id)].append(ref)
        elif action_type == "CREATE_POST":
            content = args.get("content")
            if isinstance(content, str):
                self._originals[(agent_id, content)].append(ref)

    def comment(self, comment_id: Any) -> Optional[ActionRef]:
        return _resolve(self._comments.get(str(comment_id)))

    def reference(self, post_id: Any) -> Optional[ActionRef]:
        """Repost/Zitat (die Zeile hat eine eigene ``post_id``)."""
        return _resolve(self._references.get(str(post_id)))

    def original_post(
        self, agent_id: Optional[int], content: str, rows_with_same_key: int
    ) -> Optional[ActionRef]:
        """Originalpost, geschluesselt ueber Autor und Text.

        ``rows_with_same_key``: Zahl der ``post``-Zeilen mit demselben Autor und
        Text. Nur wenn Protokoll und Datenbank dieselbe Anzahl kennen und alle
        Eintraege in derselben Runde liegen, ist die Zuordnung belegt.
        """
        if agent_id is None:
            return None
        entries = self._originals.get((agent_id, content)) or []
        if len(entries) > rows_with_same_key:
            # Startposts (Runde 0) werden aus der trace-Tabelle nach dem ersten
            # env.step gelesen (run_parallel_simulation, Startphase) und sind
            # damit datenbankgestuetzt; in Laeufen taucht derselbe Startpost
            # spaeter ein zweites Mal im Protokoll auf, ohne zweite
            # Datenbankzeile (belegt: 269 von 269 Faellen in den Artefakten
            # haben genau eine Zeile und Runden (0, n)). Die Datenbankzeilenzahl
            # begrenzt daher die Eintraege auf die der Runde 0.
            entries = [entry for entry in entries if entry.round_num == 0]
        return _resolve(entries, rows_with_same_key)


def load_round_index(actions_path: str) -> SnapshotRoundIndex:
    """Liest ``actions.jsonl`` und baut den Index; fehlende Datei -> leerer Index."""
    index = SnapshotRoundIndex()
    if not os.path.exists(actions_path):
        return index

    starts = 0
    unreadable = 0
    staged: list[tuple[str, int, dict[str, Any], ActionRef]] = []
    try:
        with open(actions_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    unreadable += 1
                    continue
                if not isinstance(data, dict):
                    unreadable += 1
                    continue
                if data.get("event_type") == "simulation_start":
                    starts += 1
                    continue
                if "event_type" in data or data.get("success", True) is False:
                    continue
                rnd = _as_round(data.get("round"))
                agent_id = data.get("agent_id")
                args = data.get("action_args")
                action_type = data.get("action_type")
                if (
                    rnd is None
                    or isinstance(agent_id, bool)
                    or not isinstance(agent_id, int)
                    or not isinstance(args, dict)
                    or not isinstance(action_type, str)
                ):
                    continue
                stamp = data.get("timestamp")
                staged.append(
                    (action_type, agent_id, args, ActionRef(rnd, stamp if isinstance(stamp, str) else None))
                )
    except OSError as exc:
        logger.warning("Aktionsprotokoll nicht lesbar (%s): %s", actions_path, exc)
        return SnapshotRoundIndex()

    if unreadable:
        logger.warning(
            "Aktionsprotokoll %s: %d unlesbare Zeilen uebersprungen", actions_path, unreadable
        )
    if starts > 1:
        logger.info(
            "Aktionsprotokoll %s enthaelt %d simulation_start-Ereignisse; "
            "Runden werden nicht zugeordnet",
            actions_path,
            starts,
        )
        return SnapshotRoundIndex()

    for action_type, agent_id, args, ref in staged:
        index.add(action_type, agent_id, args, ref)
    return index
