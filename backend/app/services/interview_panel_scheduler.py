"""Interview-Panel-Rotation über einen gesamten Report-Lauf (Issue #1303).

Problem: ``GraphToolsService._select_agents_for_interview`` lässt ein LLM pro
``interview_agents``-Tool-Call unabhängig auswählen. Ohne Gedächtnis über den
Report hinweg bevorzugt das Modell durchgehend dieselben "relevantesten"
Personas — Abschnitte 1, 3 und 5 eines Reports befragen dann im Wesentlichen
dasselbe Fünfer-Panel, statt neue Perspektiven zu erschließen.

``InterviewPanelScheduler`` trägt — als eine Instanz pro Report, nicht pro
Section und nicht pro Tool-Call (siehe ``ReportAgent.__init__``) — Buch
darüber, welche Personas unter welchem ``interview_topic`` bereits interviewt
wurden, und liefert eine bevorzugte/gefilterte Kandidatenliste für den
Auswahl-Prompt.

Persona-Identität
------------------
``index`` innerhalb einer ``interview_agents``-Kandidatenliste ist kein
Merkmal der Persona selbst — er ist nur die Position in der aktuell geladenen
Profil-Liste (siehe ``GraphToolsService._load_agent_profiles``). Zur
Report-weiten Wiedererkennung wird stattdessen bevorzugt:

1. ``username`` (stabiler Handle, wenn vorhanden),
2. sonst ``realname``,
3. sonst ein deterministischer Fingerprint über den restlichen Profilinhalt
   (kein Zufall — zwei Aufrufe mit demselben Profil-Dict liefern denselben
   Fingerprint, aber ohne echte Identität ist Kollisionsfreiheit nicht
   garantiert; das ist der bewusst akzeptierte Rest-Fall).

Cap-Regel (Akzeptanzkriterium 2)
---------------------------------
Eine Persona darf im selben Report höchstens ``max_uses_per_persona``
(Default 2) Mal interviewt werden — ein harter Deckel, keine weiche
Priorisierung. Der Scheduler filtert dazu die Kandidatenliste, die der
Auswahl-LLM überhaupt zu sehen bekommt (Kandidaten am/über dem Cap fehlen im
Normalfall komplett) und filtert die vom LLM zurückgegebenen Indizes zusätzlich
gegen die angebotene Kandidatenmenge — der Cap gilt also auch dann, wenn das
Modell die Prompt-Instruktion ignoriert.

"Meaningfully different context"-Heuristik (Akzeptanzkriterium 3)
-------------------------------------------------------------------
Eine Persona unterhalb des Caps wird nur dann erneut angeboten, wenn sich das
neue ``interview_topic`` von JEDEM Topic unterscheidet, unter dem sie in
diesem Report bereits befragt wurde (normalisierter Stringvergleich — siehe
``_normalize_topic``). Das ist die einfachste verteidigbare Operationalisierung
von "meaningfully different": kein Topic-Duplikat, keine Wiederverwendung.

Exhaustion-Fallback (Testplan: "sonst reuse mit unterschiedlichem Kontext")
-----------------------------------------------------------------------------
Sind für ein neues Topic weder unbefragte noch unterhalb des Caps mit neuem
Topic wiederverwendbare Personas übrig, darf das Interview-Tool nicht mit
einem leeren Kandidatenpool stranden. Der Scheduler erlaubt dann Wiederver-
wendung auch am/über dem Cap, sortiert die Kandidaten aber danach, wie stark
sich ihr zuletzt genutztes Topic vom neuen unterscheidet (größte
Token-Jaccard-Distanz zuerst) — der Aspektwechsel wird damit maximiert, auch
wenn die Wiederverwendung selbst erzwungen ist.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Sequence, Set

# Default-Obergrenze für Interviews derselben Persona innerhalb eines Reports.
# Klein und bewusst als einfacher Konstruktor-Parameter gehalten statt als
# volles Settings-System — Präzedenzfall: MIN_PERSONA_TABLE_ROWS in
# app/services/report_agent/contract_constants.py.
DEFAULT_MAX_INTERVIEWS_PER_PERSONA: int = 2


def persona_identity(profile: Dict[str, Any]) -> str:
    """Stabile Kennung einer Persona über mehrere ``interview_agents``-Aufrufe.

    Siehe Moduldoc "Persona-Identität". Bewusst NICHT ``index`` — der ist nur
    eine Listenposition, kein Personamerkmal.
    """
    username = str(profile.get("username") or "").strip()
    if username:
        return f"username:{username}"
    realname = str(profile.get("realname") or "").strip()
    if realname:
        return f"realname:{realname}"
    fingerprint = hashlib.sha256(
        json.dumps(profile, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"anon:{fingerprint}"


def _normalize_topic(topic: str) -> str:
    return " ".join((topic or "").strip().lower().split())


def _topic_distance(a: str, b: str) -> float:
    """1 − Jaccard-Overlap der Tokenmengen zweier Topic-Strings.

    1.0 = keine gemeinsamen Tokens (maximal unterschiedlich), 0.0 = identische
    Tokenmenge. Nur der Exhaustion-Fallback nutzt diese Distanz, um unter
    zwangsweise wiederverwendeten Personas die mit dem größten Aspektwechsel
    vorzuziehen.
    """
    tokens_a = set(_normalize_topic(a).split())
    tokens_b = set(_normalize_topic(b).split())
    if not tokens_a or not tokens_b:
        return 1.0 if tokens_a != tokens_b else 0.0
    overlap = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    return 1.0 - overlap


class InterviewPanelScheduler:
    """Trackt Interview-Historie über alle Sections eines Reports hinweg.

    Eine Instanz lebt so lange wie der ``ReportAgent``, der sie erzeugt (ein
    Konstruktor-Aufruf pro Report, siehe ``ReportAgent.__init__`` — analog zu
    ``self.evidence_map``), nicht pro Section und nicht pro Tool-Call.
    """

    def __init__(self, max_uses_per_persona: int = DEFAULT_MAX_INTERVIEWS_PER_PERSONA) -> None:
        if max_uses_per_persona < 1:
            raise ValueError("max_uses_per_persona muss >= 1 sein")
        self.max_uses_per_persona = max_uses_per_persona
        # persona_identity -> Liste der Topics, unter denen bereits interviewt wurde
        # (chronologisch, ein Eintrag pro Interview).
        self._history: Dict[str, List[str]] = {}
        # section_index -> Set befragter Persona-Identitäten, für die Diversity-Metrik.
        self._section_panels: Dict[int, Set[str]] = {}

    # -- Lesen -----------------------------------------------------------

    def uses_of(self, identity: str) -> int:
        return len(self._history.get(identity, []))

    def is_exhausted(self, identity: str) -> bool:
        return self.uses_of(identity) >= self.max_uses_per_persona

    def topics_of(self, identity: str) -> List[str]:
        return list(self._history.get(identity, []))

    # -- Kandidaten biasen -------------------------------------------------

    def rank_candidates(
        self,
        agent_summaries: List[Dict[str, Any]],
        profiles: List[Dict[str, Any]],
        interview_topic: str,
        max_agents: int,
    ) -> List[Dict[str, Any]]:
        """Liefert eine bevorzugte, ggf. gefilterte Kandidatenliste für den Auswahl-Prompt.

        ``agent_summaries`` (jeweils mit ``"index"``-Schlüssel) und
        ``profiles`` sind positionsparallel indiziert. Reihenfolge im
        Regelfall:

        1. Personas, die in diesem Report noch nie interviewt wurden.
        2. Personas unterhalb des Caps, aber bereits einmal interviewt —
           NUR wenn ``interview_topic`` sich von jedem ihrer bisherigen
           Topics unterscheidet.

        Ist diese Menge leer (Exhaustion — niemand mehr regulär verfügbar),
        greift der Fallback: alle übrigen Kandidaten werden zugelassen,
        sortiert nach absteigender Themen-Distanz zum neuen Topic (größter
        Aspektwechsel zuerst), damit eine erzwungene Wiederverwendung
        wenigstens einen möglichst anderen Kontext trifft.
        """
        never_interviewed: List[Dict[str, Any]] = []
        reusable_below_cap: List[Dict[str, Any]] = []
        remaining: List[Dict[str, Any]] = []

        for summary in agent_summaries:
            idx = summary.get("index")
            profile = profiles[idx] if isinstance(idx, int) and 0 <= idx < len(profiles) else {}
            identity = persona_identity(profile)
            topics = self._history.get(identity)

            if not topics:
                never_interviewed.append(summary)
                continue

            topic_is_new = _normalize_topic(interview_topic) not in {
                _normalize_topic(t) for t in topics
            }

            if not self.is_exhausted(identity) and topic_is_new:
                reusable_below_cap.append(summary)
            else:
                remaining.append(summary)

        if never_interviewed or reusable_below_cap:
            return never_interviewed + reusable_below_cap

        # Exhaustion-Fallback: nichts regulär verfügbar — nicht stranden.
        def _distance_key(summary: Dict[str, Any]) -> float:
            idx = summary.get("index")
            profile = profiles[idx] if isinstance(idx, int) and 0 <= idx < len(profiles) else {}
            identity = persona_identity(profile)
            topics = self._history.get(identity, [])
            last_topic = topics[-1] if topics else ""
            # Größte Distanz zuerst -> negieren für aufsteigende Sortierung.
            return -_topic_distance(last_topic, interview_topic)

        return sorted(remaining, key=_distance_key)

    # -- Schreiben ---------------------------------------------------------

    def record(
        self,
        profiles: List[Dict[str, Any]],
        selected_indices: Sequence[int],
        interview_topic: str,
        section_index: Optional[int] = None,
    ) -> None:
        """Vermerkt tatsächlich durchgeführte Interviews.

        Nur für Personas aufrufen, die wirklich interviewt wurden (nicht bei
        Soft-Fail-Pfaden ohne Interview-Durchführung).
        """
        for idx in selected_indices:
            if not isinstance(idx, int) or not (0 <= idx < len(profiles)):
                continue
            identity = persona_identity(profiles[idx])
            self._history.setdefault(identity, []).append(interview_topic)
            if section_index is not None:
                self._section_panels.setdefault(section_index, set()).add(identity)

    # -- Metrik --------------------------------------------------------------

    def panel_diversity_score(self) -> float:
        """1 − mittlere paarweise Jaccard-Überlappung der Section-Panels.

        1.0 = jedes Section-Panel ist von jedem anderen komplett disjunkt
        (maximale Diversität), 0.0 = alle Section-Panels sind identisch
        (keine Rotation). Weniger als zwei nicht-leere Section-Panels liefern
        1.0 (nichts überlappt sich per definitionem, wenn es nichts zu
        vergleichen gibt).
        """
        panels = [panel for panel in self._section_panels.values() if panel]
        if len(panels) < 2:
            return 1.0

        overlaps: List[float] = []
        for i in range(len(panels)):
            for j in range(i + 1, len(panels)):
                union = panels[i] | panels[j]
                if not union:
                    continue
                overlaps.append(len(panels[i] & panels[j]) / len(union))

        if not overlaps:
            return 1.0
        return 1.0 - (sum(overlaps) / len(overlaps))


__all__ = [
    "InterviewPanelScheduler",
    "DEFAULT_MAX_INTERVIEWS_PER_PERSONA",
    "persona_identity",
]
