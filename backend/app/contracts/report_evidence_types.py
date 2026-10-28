"""Grundlegende Enums, Typen und Helper für Evidence- und Report-Contracts.

Ausgelagert für kohäsive Modularisierung — alle Symbole werden über
``report_evidence_contract.py`` und ``report_contract.py`` re-exportiert.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, Literal, Mapping, Optional

from pydantic import ConfigDict

# Strenger Default für Vertrags-Modelle
_STRICT = ConfigDict(extra="forbid", populate_by_name=True)


class ConfidenceLabel(str, Enum):
    speculative = "speculative"
    low = "low"
    medium = "medium"
    high = "high"
    verified = "verified"


class ClaimType(str, Enum):
    """Art der Aussage — nicht ihr Beleggrad (Issue #1400).

    ``empirical`` heisst hier „Tatsachenbehauptung über Quelle oder
    Simulation" und ist nicht zu verwechseln mit ``Claim.confidence_scope =
    "empirical"`` in ``report_v3`` (reale Erhebungsdaten). Nur empirische
    Claims werden voll gegen den Evidence-Index abgewertet; die anderen drei
    Typen erhalten einen Confidence-Boden, der nie ueber ``low`` hinausgeht
    (ADR-0002 Anker 4/5 bleiben die einzige Route zu ``high``).
    """

    empirical = "empirical"
    analytical = "analytical"
    recommendation = "recommendation"
    structural = "structural"


class EvidenceType(str, Enum):
    """Übernommen aus report_agent.py — bestehende Typen plus model_generated_inference."""
    graph_fact = "graph_fact"
    graph_metric = "graph_metric"
    graph_metric_status = "graph_metric_status"
    relationship_chain = "relationship_chain"
    entity_summary = "entity_summary"
    agent_action = "agent_action"
    agent_interview = "agent_interview"
    web_search_result = "web_search_result"
    web_fetch = "web_fetch"
    # ADR-0013 / Issue #1154: Graph-Fakt mit verifizierter Dokumentherkunft.
    # Additiv — kein bestehender Wert wird angefasst, ``EvidenceSourceKind``
    # bleibt unverändert (ADR-0002 Anker 3). Das Mapping nach ``seed_corpus``
    # existiert in ``report_agent/evidence.py::_TYPE_TO_SOURCE_KIND`` bereits.
    seed_document = "seed_document"
    # NICHT als evidence verwenden, nur in audit_trail (siehe report_agent.py S5-Kommentar)
    model_generated_inference = "model_generated_inference"


class EvidenceSourceKind(str, Enum):
    """ADR-0002 Anker 3 — Quellengattung pro Evidence-Item.

    Wird von den Cross-Stakeholder-/Inferred-Validators auf
    ``ReportClaimModel`` ausgewertet (Sub-Slice M11.7b, Anker 4 + 5).
    Drift-Guard: Diese Werte sind im Prompt-Block
    ``backend/app/services/report_prompts/sections.py`` referenziert (Anker 1).

    Erweiterung (Report-Trust-Slice): ``agent_action`` und ``web_source``
    ergänzen die ursprünglichen vier Werte. Das ist additiv und verschärft
    ADR-0002, statt es zu schwächen — vorher liefen Agentenaktionen und
    Web-Treffer über den Default ``seed_corpus`` und verschmolzen damit
    Seed-Dokument, Simulation und Recherche zu einer einzigen Quellengattung.
    Für die Confidence-Anker gilt weiterhin: nur ``agent_quote`` zählt als
    Stakeholder-Stimme, nur ``seed_corpus`` als Dokumentfakt.
    """
    seed_corpus = "seed_corpus"
    agent_quote = "agent_quote"
    agent_action = "agent_action"
    graph_relation = "graph_relation"
    web_source = "web_source"
    inferred = "inferred"


#: Quellengattungen, die aus der Simulation stammen — nie ein Seed-Fakt.
SIMULATION_SOURCE_KINDS: frozenset[EvidenceSourceKind] = frozenset({
    EvidenceSourceKind.agent_quote,
    EvidenceSourceKind.agent_action,
})

#: Präfix des kanonischen Seed-Dokument-Ankers (ADR-0013). Issue #1300: Ein
#: ``seed_doc:``-Anker behauptet eine überprüfbare Dokumentstelle — für
#: Interview-Evidence (``agent_quote``) ist das eine erfundene Quelle.
#: Bewusst nur der Präfix statt des vollen Formats: auch ein deformierter
#: ``seed_doc:``-Anker auf einer Persona-Aussage darf nicht durchgehen.
SEED_DOC_ANCHOR_PREFIX = "seed_doc:"

#: Herkunftsmarke für Evidence aus von Hand angelegten (``manual``) oder
#: bearbeiteten (``edited``) Graph-Elementen (ADR-0022 §3). Bewusst ein eigenes
#: Feld neben ``source_kind`` und kein neuer Wert in ``EvidenceSourceKind``:
#: Anker 3 aus ADR-0002 bleibt geschlossen. Die Werte entsprechen der
#: Graph-Eigenschaft ``origin`` (``app.storage.neo4j_mappings.ORIGIN_*``) und
#: ``graph_edit_contract.GraphOrigin``; fehlt das Feld, gilt die Evidence als
#: nicht von Hand erzeugt.
EvidenceGraphOrigin = Literal["manual", "edited"]


def _reject_graph_origin_as_document_fact(
    graph_origin: Optional[str],
    source_kind: "EvidenceSourceKind",
    source_id_anchor: Optional[str],
) -> None:
    """ADR-0022 §2/§3: Handarbeit ist nie ein Dokumentfakt.

    Eine manuelle Beziehung hat keine Quelle im Dokument, und der geänderte
    Text einer bearbeiteten Beziehung stand so nie darin. Beides bleibt
    ``graph_relation`` und trägt keinen ``seed_doc:``-Anker — sonst täuschte
    der Record genau die Prüfbarkeit vor, die ADR-0013 ausschließt.
    """
    if graph_origin is None:
        return
    if source_kind != EvidenceSourceKind.graph_relation:
        raise ValueError(
            f"graph_origin={graph_origin} verlangt source_kind=graph_relation, "
            f"nicht {source_kind.value}: von Hand angelegte oder bearbeitete "
            "Graph-Evidence ist kein Dokumentfakt und keine Stimme (ADR-0022)."
        )
    if source_id_anchor and source_id_anchor.startswith(SEED_DOC_ANCHOR_PREFIX):
        raise ValueError(
            f"graph_origin={graph_origin} darf keinen seed_doc:-Anker tragen: "
            "für Handarbeit im Graphen gibt es keine Dokumentstelle (ADR-0022)."
        )


def counts_for_confidence(item: Any) -> bool:
    """``False`` für Evidence aus Handarbeit im Graphen (ADR-0022 §4).

    Solche Evidence bleibt im Bericht sichtbar, zählt aber für keine
    Confidence-Stufe.

    Nimmt Contract-Modelle *und* die rohen Evidence-Dicts des Schreibpfads
    entgegen: der Validator urteilt über Modelle, die Confidence-Berechnung
    über Dicts. Beide müssen dieselbe Frage beantworten, sonst hinge die
    Stufe an zwei verschiedenen Regeln.
    """
    if isinstance(item, Mapping):
        return item.get("graph_origin") is None
    return getattr(item, "graph_origin", None) is None


#: #1778 / ADR-0002-Nachtrag 2026-10-10: Mindestzahl verschiedener Aktionsstimmen,
#: ab der ``medium`` auch ohne ``agent_quote`` plus ``seed_corpus`` zulässig ist.
MIN_ACTION_VOICES_FOR_MEDIUM = 2


def has_two_action_voices(pairs: Iterable[tuple[Any, Any]]) -> bool:
    """``True``, wenn die Belege mind. zwei verschiedene Aktionsstimmen tragen.

    ``pairs`` sind ``(Quellengattung, voice_key)``-Paare. Gezählt werden
    verschiedene, nicht leere ``voice_key``-Werte von Belegen der Gattung
    ``agent_action`` (``EvidenceSourceKind`` oder ``EvidenceType``, beide tragen
    denselben Wert; Enum und String werden gleich behandelt). Der Aufrufer
    filtert vorher nach stützenden Belegen und ADR-0022-Handarbeit.

    Die eine Stelle für Vertrag (``agent_grounded_for_medium``), Bindung
    (``_require_quote_and_seed``), Schreibpfad
    (``report_agent.evidence.has_agent_grounded_evidence``) und Rechner
    (``confidence_calculator``), damit die vier nicht auseinanderlaufen. Sie
    berührt ``high``/``verified`` nicht: Anker 4 und 5 bleiben unverändert.
    """
    voices: set[str] = set()
    for kind, voice_key in pairs:
        if str(getattr(kind, "value", kind)) != "agent_action":
            continue
        if voice_key:
            voices.add(str(voice_key))
    return len(voices) >= MIN_ACTION_VOICES_FOR_MEDIUM


class EntailmentVerdict(str, Enum):
    """Urteil der zweiten Binding-Stufe.

    Spiegelt ``app.services.evidence_entailment.EntailmentVerdict``. Nur
    ``SUPPORTED`` rechtfertigt ``supports_claim=True``; ``RELATED_ONLY`` und
    ``INSUFFICIENT`` erhöhen die Confidence nie.
    """
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    RELATED_ONLY = "RELATED_ONLY"
    INSUFFICIENT = "INSUFFICIENT"


__all__ = [
    "ConfidenceLabel",
    "ClaimType",
    "EvidenceType",
    "EvidenceSourceKind",
    "SIMULATION_SOURCE_KINDS",
    "SEED_DOC_ANCHOR_PREFIX",
    "EvidenceGraphOrigin",
    "EntailmentVerdict",
    "MIN_ACTION_VOICES_FOR_MEDIUM",
    "_STRICT",
    "_reject_graph_origin_as_document_fact",
    "counts_for_confidence",
    "has_two_action_voices",
]

