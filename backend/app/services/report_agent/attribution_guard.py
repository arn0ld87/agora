"""Der Bericht darf nur zuschreiben, was seine Belege hergeben.

Von 13 validierten Claims des Referenzlaufs ``report_cc2ef45da5e9`` trug genau
einer Simulations-Evidence. Der Bericht schrieb trotzdem durchgehend "Die
Simulation zeigt …", "Die Simulation verdichtet …", "Die Simulation legt nahe
…". Tatsächlich waren die meisten Aussagen Seed-Synthesen oder analytische
Ableitungen.

Das ist keine Stilfrage. Eine Aussage, die "die Simulation" als Zeugen anruft,
behauptet eine empirische Grundlage: fünfzig Personas haben reagiert, und
daraus ergibt sich ein Befund. Steht dahinter in Wahrheit ein Satz aus dem
Projektplan, hat der Leser eine andere Grundlage vor sich, als er zu lesen
meint — und er kann es dem Text nicht ansehen.

Verschärfend kommt die Konsenssprache dazu: "durchweg", "einhellig", "breiter
Konsens" behaupten eine Verteilung. Zwei einzelne Agentenaktionen tragen sie
nicht, und null Interviews tragen "die interviewten Personas" überhaupt nicht.

Geprüft wird deterministisch gegen die Quellengattungen des Evidence-Index.
Ein LLM-Red-Team hat genau diese Stellen im Referenzlauf übersehen — sie sind
abzählbar, und Abzählbares gehört nicht in einen Prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

#: Quellengattungen, die eine Simulationsaussage tragen können.
SIMULATION_SOURCE_KINDS = frozenset({"agent_quote", "agent_action"})

#: Evidence-*Typ* einer Interviewaussage.
#:
#: Nicht die Quellengattung: ``source_kind`` fasst Interview-Antwort und
#: Simulationsbeitrag beide zu ``agent_quote`` zusammen (ADR-0002 Anker 3,
#: bewusst). Wer danach fragt, hält jeden Post der Simulation für ein
#: Interview — und lässt "die interviewten Personas" ausgerechnet dort
#: durchgehen, wo eine Simulation lief und kein Interview zustande kam.
INTERVIEW_EVIDENCE_TYPES = frozenset({"agent_interview"})

#: Ab wie vielen Belegen eine Konsensaussage ("durchweg", "einhellig") gedeckt
#: ist. Bewusst niedrig gewählt: der Wert soll die eklatanten Fälle fangen —
#: zwei Aktionen, die sprachlich zu einer Belegschaftsmeinung werden — und
#: nicht jede Verallgemeinerung zur Beanstandung machen.
CONSENSUS_MIN_EVIDENCE = 5


def _formula(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


#: Formeln, die die Simulation als Zeugen anrufen. Die Ersetzung führt dieselbe
#: Wortart und denselben Satzbau — "Die Simulation zeigt" wird zu "Die
#: Quellenlage zeigt", nicht zu einem umgebauten Satz. Alles andere hieße,
#: fremden Text zu redigieren, und das kann kein Muster leisten.
_SIMULATION_FORMULAS: List[tuple[re.Pattern[str], str]] = [
    (_formula(r"\bdie Simulation zeigt\b"), "Die Quellenlage zeigt"),
    (_formula(r"\bdie Simulation verdichtet\b"), "Die Quellenlage verdichtet"),
    (_formula(r"\bdie Simulation legt nahe\b"), "Die Quellenlage legt nahe"),
    (_formula(r"\bdie Simulation belegt\b"), "Die Quellenlage belegt"),
    (_formula(r"\bdie Simulation ergibt\b"), "Die Quellenlage ergibt"),
    (_formula(r"\bdie Simulation macht deutlich\b"), "Die Quellenlage macht deutlich"),
    (_formula(r"\blaut Simulation\b"), "laut Quellenlage"),
    (_formula(r"\bin der Simulation zeigt sich\b"), "in der Quellenlage zeigt sich"),
]

#: Formeln, die Interviews als Zeugen anrufen.
_INTERVIEW_FORMULAS: List[tuple[re.Pattern[str], str]] = [
    (_formula(r"\bdie interviewten Personas\b"), "Die verfügbaren Quellen"),
    (_formula(r"\bdie befragten Personas\b"), "Die verfügbaren Quellen"),
    (_formula(r"\bin den Interviews\b"), "in den verfügbaren Quellen"),
    (_formula(r"\baus den Interviews\b"), "aus den verfügbaren Quellen"),
    (_formula(r"\bdie Interviews zeigen\b"), "Die verfügbaren Quellen zeigen"),
]

#: Konsenssprache. Sie behauptet eine Verteilung, nicht nur einen Befund.
_CONSENSUS_MARKERS = (
    "einhellig",
    "durchweg",
    "breiter konsens",
    "breite zustimmung",
    "flächendeckend",
    "flaechendeckend",
    "ausnahmslos",
    "übereinstimmend",
    "uebereinstimmend",
)


@dataclass(frozen=True)
class EvidenceProfile:
    """Woraus dieser Bericht tatsächlich besteht.

    Gezählt werden Evidence-Records nach Quellengattung, nicht Claims: ein
    einzelner Record kann mehrere Aussagen tragen, und für die Frage "gibt es
    überhaupt Simulationsmaterial?" ist der Record die richtige Einheit.
    """

    simulation_evidence: int = 0
    interview_evidence: int = 0
    seed_evidence: int = 0

    @property
    def has_simulation(self) -> bool:
        return self.simulation_evidence > 0

    @property
    def has_interviews(self) -> bool:
        return self.interview_evidence > 0

    @property
    def supports_consensus(self) -> bool:
        return self.simulation_evidence >= CONSENSUS_MIN_EVIDENCE


def profile_from_evidence_index(
    evidence_index: Mapping[str, Any] | Sequence[Any],
) -> EvidenceProfile:
    """Zählt die Quellengattungen eines Evidence-Index oder einer Recordliste."""
    records = (
        list(evidence_index.values())
        if isinstance(evidence_index, Mapping)
        else list(evidence_index or [])
    )
    simulation = interview = seed = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        kind = str(record.get("source_kind") or "")
        is_interview = str(record.get("type") or "") in INTERVIEW_EVIDENCE_TYPES
        if is_interview:
            interview += 1
        elif kind in SIMULATION_SOURCE_KINDS:
            # Ausschließend: ein Interview trägt ``agent_quote`` wie ein
            # Simulationsbeitrag. Zählte es beidseitig, deckte ein reiner
            # Interview-Lauf die Formel "Die Simulation zeigt" ab, obwohl
            # keine Simulation als Zeuge auftreten kann — die Gegenrichtung
            # des Problems, das INTERVIEW_EVIDENCE_TYPES für Interviews löst.
            simulation += 1
        if kind == "seed_corpus":
            seed += 1
    return EvidenceProfile(
        simulation_evidence=simulation,
        interview_evidence=interview,
        seed_evidence=seed,
    )


def attribution_findings(text: str, profile: EvidenceProfile) -> List[Dict[str, str]]:
    """Welche Zuschreibungen im Text ihre Grundlage nicht haben.

    Reine Feststellung. Leer heißt: jede Zuschreibung ist gedeckt.
    """
    findings: List[Dict[str, str]] = []
    content = text or ""

    if not profile.has_simulation:
        for pattern, _ in _SIMULATION_FORMULAS:
            match = pattern.search(content)
            if match:
                findings.append({
                    "kind": "simulation_attribution_without_simulation_evidence",
                    "detail": (
                        f"'{match.group(0)}' ruft die Simulation als Zeugen an, "
                        "es liegt aber keine Simulations-Evidence vor."
                    ),
                })
                break

    if not profile.has_interviews:
        for pattern, _ in _INTERVIEW_FORMULAS:
            match = pattern.search(content)
            if match:
                findings.append({
                    "kind": "interview_attribution_without_interviews",
                    "detail": (
                        f"'{match.group(0)}' beruft sich auf Interviews, es kam "
                        "aber keines zustande."
                    ),
                })
                break

    if not profile.supports_consensus:
        lowered = content.lower()
        for marker in _CONSENSUS_MARKERS:
            if marker in lowered:
                findings.append({
                    "kind": "consensus_language_without_broad_evidence",
                    "detail": (
                        f"'{marker}' behauptet eine Verteilung; belegt sind "
                        f"{profile.simulation_evidence} Simulationsquelle(n)."
                    ),
                })
                break

    return findings


def correct_attribution(text: str, profile: EvidenceProfile) -> str:
    """Ersetzt Zuschreibungen, die ihre Grundlage nicht haben.

    Ersetzt wird nur die Zeugenformel, nie der Satz. "Die Simulation zeigt X"
    wird zu "Die Quellenlage zeigt X" — die Aussage bleibt, ihre Herkunft wird
    richtiggestellt. Ein Umbau des Satzes wäre Redigieren, und das kann kein
    Muster leisten, ohne mehr kaputtzumachen als es rettet.

    Konsenssprache bleibt unangetastet: sie steckt mitten im Satzbau, und ein
    ersatzloser Wegfall würde Sätze zerreißen. Sie wird nur gemeldet.
    """
    content = text or ""
    if not content:
        return content

    if not profile.has_simulation:
        for pattern, replacement in _SIMULATION_FORMULAS:
            content = pattern.sub(
                lambda match, target=replacement: _match_case(match.group(0), target),
                content,
            )
    if not profile.has_interviews:
        for pattern, replacement in _INTERVIEW_FORMULAS:
            content = pattern.sub(
                lambda match, target=replacement: _match_case(match.group(0), target),
                content,
            )
    return content


def _match_case(original: str, replacement: str) -> str:
    """Übernimmt die Groß-/Kleinschreibung des ersetzten Satzanfangs.

    "Die Simulation zeigt" steht am Satzanfang, "…, wie die Simulation zeigt"
    mitten im Satz. Ein pauschal großgeschriebener Ersatz risse dort ein
    Großwort in die Satzmitte.
    """
    if original[:1].islower():
        return replacement[:1].lower() + replacement[1:]
    return replacement[:1].upper() + replacement[1:]


__all__ = [
    "CONSENSUS_MIN_EVIDENCE",
    "INTERVIEW_EVIDENCE_TYPES",
    "EvidenceProfile",
    "attribution_findings",
    "correct_attribution",
    "profile_from_evidence_index",
]
