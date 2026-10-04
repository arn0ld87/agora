"""Suche in den Simulationsbeiträgen für den Report-Agenten (Issue #1778).

Im Referenzlauf ``sim_c8c6b30aa652`` beruhten 3 von 164 stützenden Belegen auf
Simulationsaktionen: Der Report-Agent sah nur eine feste Stichprobe von acht
Aktionen und konnte nicht gezielt nachsehen, was öffentlich gesagt wurde. Das
Werkzeug ``search_simulation_actions`` macht die Beiträge durchsuchbar.

Bewusst ohne LLM-Aufruf und ohne Embeddings: eine deterministische
Stichwortsuche über den Wortlaut, gefiltert nach Stimme und Runde.

Jeder Treffer wird ein Beleg vom Typ ``agent_action``.
``build_action_evidence_item`` ist dafür die gemeinsame Quelle von Stichprobe
(``ReportAgent._collect_simulation_evidence_items``) und Suche, damit dieselbe
Aktion in beiden Wegen dieselbe Evidence-ID bekommt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ...models.report import EvidenceItem
from .sections import action_content, truncate_text

#: Grenzen für ``limit``; der Standardwert steht in der Signatur.
_MIN_LIMIT = 1
_MAX_LIMIT = 20

#: Suchwörter unter dieser Länge zählen nicht (Artikel, Füllwörter).
_MIN_QUERY_WORD_LENGTH = 4

#: Höchstlänge des Wortlauts im Beleg-Snippet und in der Trefferliste.
_SNIPPET_TEXT_LIMIT = 600

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass
class ActionSearchResult:
    """Ergebnis von ``search_simulation_actions``.

    ``total_matching`` zählt alle Treffer vor der Begrenzung durch ``limit``,
    ``total_actions`` alle durchsuchbaren Beiträge (mit Text, ohne harte
    Rollenkonflikte).
    """

    query: str
    hits: List[Dict[str, Any]] = field(default_factory=list)
    total_matching: int = 0
    total_actions: int = 0

    def to_text(self) -> str:
        """Trefferliste für den ReACT-Loop: Stimme, Plattform, Runde, Wortlaut."""
        label = f' for "{self.query}"' if self.query else ""
        if not self.hits:
            return (
                f"Simulation posts{label}: no matching posts or comments "
                f"({self.total_actions} posts with text in the simulation)."
            )
        lines = [
            f"Simulation posts{label}: showing {len(self.hits)} of "
            f"{self.total_matching} matching posts "
            f"({self.total_actions} posts with text in the simulation)."
        ]
        for position, action in enumerate(self.hits, 1):
            lines.append(f"{position}. {_describe_action(action)}")
        return "\n".join(lines)


def _describe_action(action: Dict[str, Any]) -> str:
    """Eine Zeile je Aktion — dieselbe Form wie das Snippet des Belegs."""
    action_type = action.get("action_type") or "action"
    agent = action.get("agent_name") or f"Agent {action.get('agent_id')}"
    platform = action.get("platform") or "unknown"
    description = f"{agent} {action_type} on {platform} in round {action.get('round_num')}"
    # Issue #1304 (S2): Der Beitragstext gehört in das Snippet. Gegen eine
    # reine Metabeschreibung kann kein Entailment eine Aussage stützen.
    action_text = action_content(action)
    if action_text:
        description = f"{description}: {truncate_text(action_text, _SNIPPET_TEXT_LIMIT)}"
    return description


def build_action_evidence_item(action: Dict[str, Any]) -> Dict[str, Any]:
    """Baut den Beleg ``agent_action`` für eine Simulationsaktion.

    Gemeinsame Quelle für Stichprobe und Suche: gleiche Aktion, gleicher
    ``producer_key``, gleiche Evidence-ID.
    """
    item = EvidenceItem(
        type="agent_action",
        source="simulation_actions",
        value=action.get("action_type") or "action",
        snippet=_describe_action(action),
        raw=action,
    ).to_dict()
    # Issue #1778 (Schritt 1.2): Stimme des Belegs — dieselbe agent_id wie im
    # Interview derselben Persona.
    if action.get("agent_id") is not None:
        item["voice_key"] = f"agent:{action.get('agent_id')}"
    action_identity = (
        action.get("platform"),
        action.get("round_num"),
        action.get("agent_id"),
        action.get("action_type"),
        action.get("timestamp"),
    )
    if all(value is not None and str(value).strip() for value in action_identity):
        item["producer_key"] = "simulation-action:" + ":".join(
            str(value) for value in action_identity
        )
    return item


def text_contributions(actions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Die Beiträge einer Simulation: Aktionen mit eigenem Text.

    Aktionen mit hartem Rollenkonflikt stehen nicht für ihren Agenten
    (Issue #1323) und fallen heraus, ebenso Handlungen ohne Text (Like, Repost).
    """
    # Lazy-Import: ``agent`` importiert dieses Modul. Die Konstante wird
    # importiert statt kopiert, damit Stichprobe und Suche dieselbe Regel teilen.
    from .agent import _HARD_ROLE_CONFLICTS

    return [
        action
        for action in actions
        if action.get("role_conflict") not in _HARD_ROLE_CONFLICTS and action_content(action)
    ]


def _is_abbreviation(word: str) -> bool:
    """Kurze Namen und Abkürzungen wie „AfD", „EU" oder „G7".

    Erkannt an der Schreibweise der Suchanfrage: ein Großbuchstabe nach dem
    ersten Zeichen oder eine Ziffer. „die" und „Die" sind damit keine.
    """
    return len(word) >= 2 and (
        any(char.isupper() for char in word[1:]) or any(char.isdigit() for char in word)
    )


def _query_terms(query: str) -> tuple[List[str], List[str]]:
    """Suchwörter der Anfrage: (Wörter für Teilstring-Treffer, Abkürzungen).

    Wörter ab vier Zeichen treffen als Teilstring. Kürzere zählen nur, wenn
    sie eine Abkürzung sind, und treffen dann nur als ganzes Wort — sonst
    fände „EU" jeden Beitrag mit „neu".
    """
    words: List[str] = []
    abbreviations: List[str] = []
    for word in _WORD_RE.findall(query or ""):
        if len(word) >= _MIN_QUERY_WORD_LENGTH:
            words.append(word.lower())
        elif _is_abbreviation(word):
            abbreviations.append(word.lower())
    return words, abbreviations


def _score(text: str, words: Sequence[str], abbreviations: Sequence[str]) -> int:
    lowered = text.lower()
    score = sum(1 for word in words if word in lowered)
    if abbreviations:
        text_words = set(_WORD_RE.findall(lowered))
        score += sum(1 for abbreviation in abbreviations if abbreviation in text_words)
    return score


def _in_round_range(action: Dict[str, Any], round_from: Optional[int], round_to: Optional[int]) -> bool:
    if round_from is None and round_to is None:
        return True
    round_num = action.get("round_num")
    if not isinstance(round_num, int):
        return False
    if round_from is not None and round_num < round_from:
        return False
    return round_to is None or round_num <= round_to


def search_simulation_actions(
    simulation_id: str,
    query: str = "",
    agent_name: str = "",
    round_from: int | None = None,
    round_to: int | None = None,
    limit: int = 12,
) -> ActionSearchResult:
    """Sucht in den Beiträgen der Simulation.

    Filter: ``agent_name`` als Teilstring ohne Groß-/Kleinschreibung,
    ``round_from``/``round_to`` einschließlich. ``query`` wird in Wörter mit
    mindestens vier Zeichen zerlegt, dazu kommen kürzere Abkürzungen wie
    „AfD" als ganzes Wort (``_query_terms``); die Punktzahl eines Beitrags ist
    die Zahl der Suchwörter, die in seinem Text vorkommen, Beiträge ohne
    Treffer fallen heraus. Eine leere ``query`` filtert nicht nach Text.

    Sortierung: Punktzahl absteigend, dann Runde aufsteigend.
    """
    from ..simulation_runner import SimulationRunner

    contributions = text_contributions(
        action.to_dict() for action in SimulationRunner.get_all_actions(simulation_id)
    )
    name_filter = (agent_name or "").strip().lower()
    has_query = bool((query or "").strip())
    words, abbreviations = _query_terms(query)

    scored: List[tuple[int, Dict[str, Any]]] = []
    for action in contributions:
        if name_filter and name_filter not in str(action.get("agent_name") or "").lower():
            continue
        if not _in_round_range(action, round_from, round_to):
            continue
        score = 0
        if has_query:
            score = _score(action_content(action), words, abbreviations)
            if score == 0:
                continue
        scored.append((score, action))

    def _round_of(action: Dict[str, Any]) -> int:
        round_num = action.get("round_num")
        return round_num if isinstance(round_num, int) else 0

    scored.sort(key=lambda entry: (-entry[0], _round_of(entry[1])))
    bounded_limit = max(_MIN_LIMIT, min(int(limit), _MAX_LIMIT))
    return ActionSearchResult(
        query=query or "",
        hits=[action for _score, action in scored[:bounded_limit]],
        total_matching=len(scored),
        total_actions=len(contributions),
    )


__all__ = [
    "ActionSearchResult",
    "build_action_evidence_item",
    "search_simulation_actions",
    "text_contributions",
]
