"""Auszählung über geführte Interviews als eigenes Evidence-Item (#1357).

Eine Aussage wie „die Mehrheit der Stakeholder lehnt den ungestaffelten
Vollstart ab" ist von *keinem* einzelnen Interview belegbar. Jedes Zitat trägt
genau eine Stimme; die Menge steht nirgends. Regel 2 in
``evidence_entailment`` prüft Mengenaussagen gegen einen Prozentwert und fand
bisher keinen — Konsens-Claims blieben deshalb strukturell unbelegt, egal wie
gut die Einzelinterviews banden.

Dieses Modul zählt aus, was geführt wurde, und schreibt das Ergebnis als
Evidence-Item mit einer expliziten Prozentangabe.

**Es ist eine Auszählung, keine Stimme.** Das ist die tragende Unterscheidung
und der Grund für die Wahl der Quellengattung:

``source_kind`` ist ``agent_action``, nicht ``agent_quote``. Damit zählt das
Aggregat als Simulationsbeitrag (``SIMULATION_SOURCE_KINDS``, also in
``simulation_share``), aber **nicht** als Stakeholder-Stimme für
``cross_stakeholder_for_high`` — der Anker 4 verlangt ausdrücklich
``agent_quote``. Ein Aggregat, das mehrere Gruppen zusammenfasst und als eine
davon aufträte, würde die Cross-Stakeholder-Regel mit einem einzigen Item
erfüllen und damit aushöhlen. Die Anker-Erfüllung läuft weiterhin über die
einzeln gebundenen Interviews.

Warum nicht ``inferred``, was semantisch näher läge: Anker 5
(``reject_inferred_in_high_confidence``) verwirft *jedes* ``inferred``-Item in
einem ``high``-Claim. Ein Aggregat dieser Gattung würde also einen sonst
belegbaren Claim herunterstufen — schädlicher als gar kein Aggregat. Keiner
der sechs kanonischen Werte beschreibt „Auszählung über Stimmen" sauber; von
den verfügbaren ist ``agent_action`` der einzige, der die Herkunft nicht
falsch behauptet und keinen Anker verletzt. Das Enum selbst (Anker 3) bleibt
unangetastet — dies ist ein Mapping, wie ``seed_document → seed_corpus`` es
vormacht.

Gezählt wird über ``persona_role_family``, nicht über den Jobtitel: derselbe
Zählschlüssel wie in Anker 4 (Issue #1248). Die Zahl der Rollen*familien*
steht zusätzlich als ``cluster_count`` im Item — sie wird ausgewiesen, nicht
verrechnet. Vier Interviews aus einer einzigen Familie sind ein schwächerer
Beleg als zwei aus zweien, und diese Information soll der Leser sehen, statt
dass eine Formel sie stillschweigend einpreist.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

#: Mindestzahl geführter Interviews für eine Auszählung. Unter drei Stimmen
#: ist „die Mehrheit" keine Aussage über eine Gruppe, sondern über zwei
#: Personen — und eine Prozentangabe darauf täuscht Präzision vor.
MIN_INTERVIEWS_FOR_CONSENSUS = 3

#: Ab dieser Stimmung gilt eine Antwort als zustimmend bzw. ablehnend. Der
#: Korridor dazwischen ist bewusst breit: eine Antwort ohne klare Richtung
#: soll in keine der beiden Zahlen einfließen, sondern die Grundgesamtheit
#: erhöhen. So senkt eine ambivalente Stimme den Anteil, statt ihn zu drehen.
POSITIVE_SENTIMENT_THRESHOLD = 0.2
NEGATIVE_SENTIMENT_THRESHOLD = -0.2


def _role_family(item: Mapping[str, Any]) -> Optional[str]:
    """Zählschlüssel — Rollenfamilie, ersatzweise die Stakeholder-Gruppe.

    Der Fallback ist derselbe wie in Anker 4: Artefakte aus Läufen vor
    Issue #1248 tragen keine Familie, dort bleibt der Jobtitel der beste
    verfügbare Schlüssel.
    """
    family = str(item.get("persona_role_family") or "").strip()
    if family:
        return family
    group = str(item.get("persona_stakeholder_group") or "").strip()
    return group or None


def _sentiment(item: Mapping[str, Any]) -> Optional[float]:
    raw = item.get("sentiment_score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_consensus_item(
    interviews: Sequence[Mapping[str, Any]],
    *,
    section_index: int,
    topic: str,
    evidence_ids: Sequence[str],
    tool_name: str = "interview_agents",
) -> Optional[Dict[str, Any]]:
    """Baut das Auszählungs-Item, oder ``None``, wenn nichts zu zählen ist.

    ``interviews`` sind die bereits persistierten Interview-Items derselben
    Sektion, ``evidence_ids`` ihre IDs in derselben Reihenfolge. Ohne
    Stimmungswerte entsteht kein Item: eine Auszählung ohne Richtung wäre
    eine Zahl ohne Aussage.
    """
    if len(interviews) < MIN_INTERVIEWS_FOR_CONSENSUS:
        return None

    scored = [
        (item, score)
        for item, score in ((entry, _sentiment(entry)) for entry in interviews)
        if score is not None
    ]
    if len(scored) < MIN_INTERVIEWS_FOR_CONSENSUS:
        return None

    total = len(scored)
    critical = sum(1 for _, score in scored if score <= NEGATIVE_SENTIMENT_THRESHOLD)
    supportive = sum(1 for _, score in scored if score >= POSITIVE_SENTIMENT_THRESHOLD)

    families = sorted({
        family for family, _ in (
            (_role_family(item), score) for item, score in scored
        ) if family
    })

    # Die dominante Richtung trägt die Aussage. Bei Gleichstand entsteht keine
    # Mehrheitsaussage — der Satz nennt dann beide Zahlen und Regel 2 findet
    # keinen Beleg für "die Mehrheit", was korrekt ist.
    critical_share = round(100.0 * critical / total, 1)
    supportive_share = round(100.0 * supportive / total, 1)

    snippet = (
        f"Von {total} befragten Stakeholder-Rollen äußerten sich "
        f"{critical} kritisch ({critical_share:g} Prozent der befragten "
        f"Stakeholder-Rollen) und {supportive} zustimmend "
        f"({supportive_share:g} Prozent der befragten Stakeholder-Rollen)"
    )
    if topic:
        snippet += f" zum Thema {topic}"
    snippet += (
        f". Die Befragten verteilen sich auf {len(families)} Rollenfamilie"
        f"{'n' if len(families) != 1 else ''}"
    )
    if families:
        snippet += f" ({', '.join(families)})"
    snippet += "."

    return {
        "type": "agent_interview_consensus",
        # Auszählung, keine Stimme — siehe Modul-Docstring. Explizit gesetzt
        # statt über das Typ-Mapping abgeleitet, damit die Wahl an der Stelle
        # steht, an der sie begründet ist.
        "source_kind": "agent_action",
        "tool_name": tool_name,
        "query": topic,
        "snippet": snippet,
        "raw": {
            "interviews_counted": total,
            "critical": critical,
            "supportive": supportive,
            "critical_share_percent": critical_share,
            "supportive_share_percent": supportive_share,
            "role_families": families,
            "cluster_count": len(families),
            "contributing_evidence_ids": list(evidence_ids),
        },
        # Ausgewiesen, nicht verrechnet: vier Stimmen aus einer Familie sind
        # ein schwächerer Beleg als zwei aus zweien, und das soll sichtbar
        # bleiben statt in einer Gewichtung zu verschwinden.
        "cluster_count": len(families),
        "contributing_evidence_ids": list(evidence_ids),
        "agent_log_ref": {
            "section_index": section_index,
            "action": "tool_result",
            "tool_name": tool_name,
        },
        "producer_key": (
            f"interview-consensus:s{section_index}:{topic or 'no-topic'}:{total}"
        ),
    }


__all__ = [
    "MIN_INTERVIEWS_FOR_CONSENSUS",
    "NEGATIVE_SENTIMENT_THRESHOLD",
    "POSITIVE_SENTIMENT_THRESHOLD",
    "build_consensus_item",
]
