from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from pydantic import ValidationError

from ...contracts import EvidenceRecordModel
from ..evidence_identity import build_evidence_id
from ..evidence_migrations import normalize_persisted_evidence_map
from .schemas import CURRENT_SCHEMA_VERSION, EvidenceMapModel


def init_evidence_map(
    *,
    report_id: str,
    simulation_id: str,
    global_evidence: List[Dict[str, Any]],
) -> Dict[str, Any]:
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "report_id": report_id,
        "simulation_id": simulation_id,
        "evidence_index": {},
        "global_evidence_refs": [],
        "sections": [],
    }
    for item in global_evidence:
        record = register_evidence_record(payload, item, scope_id=simulation_id)
        if record is not None:
            payload["global_evidence_refs"].append(record["evidence_id"])
    return EvidenceMapModel.model_validate(payload).model_dump(mode="json")


#: Präfix des kanonischen Seed-Dokument-Ankers (ADR-0013, Issue #1154).
_SEED_DOC_ANCHOR_PREFIX = "seed_doc:"


def build_seed_document_anchor(provenance: Optional[Dict[str, Any]]) -> Optional[str]:
    """``seed_doc:<document_id>#chunk:<chunk_id>`` — oder ``None`` (ADR-0013).

    Erwartet die Retrieval-Provenance aus Issue #1152
    (``provenance_at(...)``). Beide Bestandteile sind Pflicht: Ohne
    ``chunk_id`` zeigt der Anker auf ein ganzes Dokument statt auf die Stelle,
    aus der der Fakt stammt, und wäre nicht mehr überprüfbar. Mehrdeutige oder
    fehlende Herkunft ergibt ``None`` — der Fakt bleibt dann ``graph_relation``,
    statt einen Dokumentbezug zu behaupten, den niemand nachschlagen kann.

    Autorengegebene Quellen-Labels aus dem Chunk-Text (etwa ``A1``–``J1``)
    gehen hier bewusst NICHT ein: sie sind über mehrere Uploads nicht
    eindeutig, zwei Dateien mit gleichem Label und gleicher Chunk-Nummer
    ergäben denselben Anker (Codex-Review zu PR #1153, ADR-0013 Punkt 2).
    """
    if not isinstance(provenance, dict):
        return None
    document_id = str(provenance.get("document_id") or "").strip()
    chunk_id = provenance.get("chunk_id")
    if not document_id or not isinstance(chunk_id, int) or isinstance(chunk_id, bool):
        return None
    anchor = f"{_SEED_DOC_ANCHOR_PREFIX}{document_id}#chunk:{chunk_id}"
    # ``EvidenceRecordModel.source_id_anchor`` ist auf 200 Zeichen begrenzt.
    # Ein gekappter Anker wäre nicht mehr auflösbar — dann lieber keiner.
    if len(anchor) > 200:
        return None
    # Schreib- und Lesepfad müssen dieselbe Regel anwenden. Sonst entsteht ein
    # Record, den der Schreibpfad für verankert hält und der Lesepfad nicht —
    # er würde bei jedem Laden abgestuft und umgeschlüsselt und wechselte so
    # dauerhaft seine Identität. Deshalb prüft der Bau mit dem Leser gegen
    # (negative Chunk-Nummer, ``#`` in der Dokument-ID).
    return anchor if is_verified_seed_document_anchor(anchor) else None


def is_verified_seed_document_anchor(anchor: Any) -> bool:
    """Prüft, ob ``anchor`` das kanonische Seed-Dokument-Format trägt.

    Gegenstück zu :func:`build_seed_document_anchor` für den Lesepfad: ein
    persistiertes ``seed_corpus``-Item ohne solchen Anker ist nicht als
    Dokumentfakt überprüfbar (ADR-0013).
    """
    if not isinstance(anchor, str):
        return False
    return _SEED_DOC_ANCHOR_RE.fullmatch(anchor.strip()) is not None


_SEED_DOC_ANCHOR_RE = re.compile(r"seed_doc:(?P<document_id>[^#]+)#chunk:(?P<chunk_id>\d+)")


#: Interner Evidence-`type` → Provenance-`source_kind`.
#: Ohne diese Abbildung liefen Agentenaktionen, Interviews und Web-Treffer in
#: den Default und wurden als Seed-Fakt persistiert.
#: Deckt jeden Wert von ``EvidenceType`` ab (ausser
#: ``model_generated_inference``, das ohnehin nicht als Evidence zulaessig ist).
#: Ein fehlender Eintrag laesst echte Graph-Evidence als ``inferred`` gelten —
#: der E2E-Lauf zeigte genau das fuer ``graph_fact`` (125 von 125 Items).
_TYPE_TO_SOURCE_KIND: Dict[str, str] = {
    "seed_corpus": "seed_corpus",
    "seed_document": "seed_corpus",
    "agent_post": "agent_quote",
    "agent_quote": "agent_quote",
    "agent_interview": "agent_quote",
    "agent_action": "agent_action",
    "agent_behavior": "agent_action",
    "graph_fact": "graph_relation",
    "relationship_chain": "graph_relation",
    "entity_summary": "graph_relation",
    "graph_metric": "graph_relation",
    "graph_metric_status": "graph_relation",
    "graph_relation": "graph_relation",
    "web_search_result": "web_source",
    "web_fetch": "web_source",
    "web_source": "web_source",
}


#: Kanonische ``EvidenceSourceKind``-Werte (ADR-0002 Anker 3). Ein explizit
#: gesetztes ``source_kind`` muss gegen diese Menge geprüft werden, nicht gegen
#: ``_TYPE_TO_SOURCE_KIND.values()`` — sonst schließt die Prüfung ``inferred``
#: aus und ein Caller, der ein Modellableitungs-Fakt bewusst als ``inferred``
#: markiert, wird ignoriert (CodeRabbit PR #929).
_VALID_SOURCE_KINDS: frozenset[str] = frozenset(
    {"seed_corpus", "agent_quote", "agent_action", "graph_relation", "web_source", "inferred"}
)


def normalize_source_kind(item: Dict[str, Any]) -> str:
    """Ermittelt die Provenance eines Evidence-Items.

    Ein explizit gesetztes ``source_kind`` gewinnt — inklusive ``inferred``,
    wenn ein Caller einen Modellableitungs-Fakt bewusst so markiert. Sonst
    entscheidet der interne ``type``. Was sich nicht zuordnen lässt, wird
    ``inferred`` — niemals ``seed_corpus``: ein Simulations-Post ist kein
    Dokumentfakt, und eine unbekannte Herkunft erst recht nicht.
    """
    explicit = str(item.get("source_kind") or "").strip()
    if explicit in _VALID_SOURCE_KINDS:
        return explicit

    item_type = str(item.get("type") or "").strip().lower()
    return _TYPE_TO_SOURCE_KIND.get(item_type, "inferred")


def record_evidence_item(
    active_section_evidence: Optional[List[Dict[str, Any]]],
    item: Dict[str, Any],
) -> List[Dict[str, Any]]:
    target = list(active_section_evidence or [])
    enriched = dict(item)
    enriched.setdefault("source_kind", normalize_source_kind(item))
    target.append(enriched)
    return target


_CLAIM_RELATIVE_FIELDS = frozenset({
    "match_score",
    "retrieval_score",
    "entailment",
    "entailment_reason",
    "supports_claim",
    "contradicts_claim",
})


def register_evidence_record(
    evidence_map: Dict[str, Any],
    item: Dict[str, Any],
    *,
    scope_id: str,
) -> Optional[Dict[str, Any]]:
    """Validiert und registriert ein Producer-Item mit explizitem Schluessel."""

    producer_key = str(item.get("producer_key") or "").strip()
    if not producer_key:
        return None
    source_kind = normalize_source_kind(item)
    payload = {
        key: value
        for key, value in item.items()
        if key not in _CLAIM_RELATIVE_FIELDS
    }
    payload.update({
        "evidence_id": build_evidence_id(scope_id, source_kind, producer_key),
        "producer_key": producer_key,
        "source_kind": source_kind,
    })
    record = EvidenceRecordModel.model_validate(payload).model_dump(mode="json")
    evidence_index = evidence_map.setdefault("evidence_index", {})
    existing = evidence_index.get(record["evidence_id"])
    if existing is not None:
        return existing
    evidence_index[record["evidence_id"]] = record
    return record


def resolve_embedder(
    *,
    cached: Any,
    logger: Any,
) -> Optional[Callable[[str], List[float]]]:
    if cached != "missing":
        return cached
    try:
        from ...storage.embedding_service import EmbeddingService

        service = EmbeddingService()
        return service.embed
    except Exception as exc:  # pragma: no cover - environment dependent  # noqa: BLE001 — exception is logged; swallowed intentionally
        logger.debug(f"EvidenceBinder: kein Embedder verfügbar ({exc!r})")
        return None


def _count_supporting_stakeholder_groups(evidence: List[Dict[str, Any]]) -> int:
    """Zähle die unterschiedlichen Stakeholder-Gruppen unter ``agent_quote``-Evidence,
    die den Claim stützen. Spiegelt die Logik aus
    ``ReportClaimModel.cross_stakeholder_for_high`` (ADR-0002, Anker 4).
    """
    groups: set = set()
    for entry in evidence or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("source_kind") != "agent_quote":
            continue
        if not entry.get("supports_claim"):
            continue
        # Issue #1248: Gezaehlt wird das kontrollierte Rollenfamilien-Label,
        # nicht der frei formulierte Berufstitel — sonst zaehlen Wortwahl- und
        # Genusvarianten derselben Rolle als verschiedene Gruppen. Die
        # Praefixe halten die beiden Namensraeume auseinander; ohne sie waere
        # eine Familie "Lecturer" nicht von einem gleichnamigen Jobtitel zu
        # unterscheiden. Spiegelt ``report_contract._role_family_key``.
        family = entry.get("persona_role_family")
        family_key = " ".join(str(family or "").split()).casefold()
        # Issue #1248 (CodeRabbit PR #1260): Auffangtypen bezeichnen keine
        # Rollenfamilie. Spiegelt ``report_contract._GENERIC_ENTITY_TYPES``.
        if family_key and family_key not in {
            "person", "organization", "entity", "node", "unknown", "other",
        }:
            groups.add(f"family:{family_key}")
            continue
        group = entry.get("persona_stakeholder_group")
        if group:
            groups.add(f"title:{' '.join(str(group).split()).casefold()}")
    return len(groups)


def has_agent_grounded_evidence(
    evidence: List[Dict[str, Any]],
    *,
    evidence_index: Optional[Dict[str, Any]] = None,
) -> bool:
    """True, wenn die Evidence mind. 1 ``agent_quote`` (mit nicht-leerem
    ``quote``-Feld) UND mind. 1 ``seed_corpus`` enthält (ADR-0002 Stufe
    agent_grounded → rechtfertigt ``medium``). Spiegelt
    ``ReportClaimModel.agent_grounded_for_medium`` (Issue #906 Defekt 1).
    ``supports_claim`` wird hier nicht gefordert — analog zum medium-Validator.
    Das Quote-Feld ist Pflicht (ADR-0002 Z. 54; Codex PR-Review #961 P2): ein
    zusammengefasstes Interview ohne Original-Zitat ist nicht agent_grounded.

    Mit ``evidence_index`` wird jede Referenz zuerst über ihre ``evidence_id``
    auf den kanonischen Record aufgelöst und nur ersatzweise am Inline-Eintrag
    gemessen. ``EvidenceMapModel.validate_evidence_cross_references`` urteilt
    ausschließlich über die Records; ohne diese Auflösung könnte ein Claim hier
    als agent_grounded gelten und dort trotzdem durchfallen — genau der
    Report-Abbruch, den der Aufrufer verhindern will.
    """
    has_agent_quote = False
    has_seed_corpus = False
    index = evidence_index or {}
    for entry in evidence or []:
        if not isinstance(entry, dict):
            continue
        record = index.get(str(entry.get("evidence_id") or ""))
        source = record if isinstance(record, dict) else entry
        sk = source.get("source_kind")
        if sk == "agent_quote" and source.get("quote"):
            has_agent_quote = True
        elif sk == "seed_corpus":
            has_seed_corpus = True
    return has_agent_quote and has_seed_corpus


TEXT_CONFIDENCE_DOWNGRADE_EVENT = "text_confidence_downgraded"
"""``audit_trail``-Ereignis: der Wortlaut stammt aus einer hoeheren Stufe."""


def _record_text_confidence_downgrade(
    claim: Dict[str, Any], *, from_label: str, to_label: str
) -> None:
    """Haelt fest, unter welchem Label der ``claim_text`` entstanden ist (#1012).

    Wird ein Claim nachtraeglich abgestuft, aendert sich nur das Label. Der
    ``claim_text`` — und der bereits gerenderte Abschnittstext — behalten ihre
    Formulierung, oft eine deklarative ohne Hedge, weil das Modell sie unter
    ``high`` geschrieben hat. Der Report besteht die Validierung, transportiert
    im Fliesstext aber weiter eine Behauptung in einer Sicherheit, die das
    Label nicht mehr deckt.

    Statt den generierten Text zu bearbeiten (mit den Folgefragen Sprache,
    Doppel-Hedging und Idempotenz bei mehrfachem Downgrade) wird die Abstufung
    ausgewiesen — dieselbe Linie wie #1160 A/B/E: Agora aendert nicht, was das
    Modell geschrieben hat, sondern sagt dem Leser, was er vor sich hat.

    Der erste Eintrag gewinnt: bei einem zweiten Downgrade bleibt die
    *urspruengliche* Stufe stehen, unter der der Wortlaut tatsaechlich
    entstanden ist. Ein spaeteres ``medium`` waere bereits abgestuft und
    damit die falsche Referenz.
    """
    trail = claim.get("audit_trail")
    if not isinstance(trail, list):
        trail = []
    if any(
        isinstance(entry, dict)
        and entry.get("event") == TEXT_CONFIDENCE_DOWNGRADE_EVENT
        for entry in trail
    ):
        return
    claim["audit_trail"] = [
        *trail,
        {
            "event": TEXT_CONFIDENCE_DOWNGRADE_EVENT,
            "text_confidence_label": from_label,
            "to": to_label,
            "issue": "1012",
        },
    ]


def text_confidence_label_of(claim: Dict[str, Any]) -> str | None:
    """Die Stufe, unter der der Wortlaut entstand — oder ``None``.

    ``None`` heisst: nicht abgestuft, der Wortlaut passt zum Label. Das ist
    der Normalfall und darf nicht mit "unbekannt" verwechselt werden.
    """
    trail = claim.get("audit_trail")
    if not isinstance(trail, list):
        return None
    for entry in trail:
        if (
            isinstance(entry, dict)
            and entry.get("event") == TEXT_CONFIDENCE_DOWNGRADE_EVENT
        ):
            label = entry.get("text_confidence_label")
            return str(label) if label else None
    return None


def auto_downgrade_unsupported_high_claims(
    claims: List[Dict[str, Any]],
    *,
    logger: Any = None,
) -> List[Dict[str, Any]]:
    """Senkt ``confidence_label`` von ``high``/``verified`` ab, wenn die
    Cross-Stakeholder-Anforderung aus ADR-0002 (Anker 4) nicht erfüllt ist.

    Der Zielwert hängt vom Provenance-Mix ab (Issue #906 Defekt 2, ADR-0002
    Stufe agent_grounded): ``medium``, wenn mind. 1 ``agent_quote`` UND mind.
    1 ``seed_corpus`` vorliegen; sonst ``low`` (Seed-only bzw. reine
    agent_quote ohne Korpusbezug). Damit bestünde der downgegradete Claim
    den nachfolgenden ``medium``-Validator und vermeidet gerade den harten
    Report-Abbruch, den diese Funktion verhindern soll.

    Der Validator selbst bleibt strikt (ADR-0002 verbietet Schwächung);
    diese Funktion liefert ihm nur ehrlich downgrade'te Daten, statt
    ihn mit unrealistischen Labels zu konfrontieren.
    """
    downgraded: List[Dict[str, Any]] = []
    for raw in claims:
        if not isinstance(raw, dict):
            downgraded.append(raw)
            continue
        item = dict(raw)
        label = item.get("confidence_label")
        if label in ("high", "verified"):
            groups = _count_supporting_stakeholder_groups(item.get("evidence") or [])
            if groups < 2:
                evidence = item.get("evidence") or []
                target = "medium" if has_agent_grounded_evidence(evidence) else "low"
                claim_id = item.get("claim_id", "<no-id>")
                if logger is not None:
                    logger.warning(
                        "auto_downgrade_unsupported_high_claims: %s '%s' → '%s' "
                        "(nur %d stützende Stakeholder-Gruppe(n), 2 erforderlich; "
                        "agent_grounded=%s)",
                        claim_id, label, target, groups,
                        target == "medium",
                    )
                item["confidence_label"] = target
                _record_text_confidence_downgrade(item, from_label=label, to_label=target)
        downgraded.append(item)
    return downgraded


def normalize_claims_for_contract(
    claims: List[Dict[str, Any]],
    *,
    logger: Any = None,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for claim in claims:
        item = dict(claim)
        item.pop("claim", None)
        item.pop("confidence", None)
        item.pop("evidence_items", None)
        normalized.append(item)
    return auto_downgrade_unsupported_high_claims(normalized, logger=logger)


# ---------------------------------------------------------------------------
# M11.8e — Quote-Anchor-Validator
# ---------------------------------------------------------------------------

_QUOTE_TAG_RE = re.compile(
    r"<simulated_quote\s+([^>]+)>(.*?)</simulated_quote>",
    re.DOTALL,
)
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
# Issue #1249: ``_SEED_DOC_PREFIX`` ist mit der Praefix-Ausnahme entfallen.
# Sie war die einzige Verwendung — ein Anker wird jetzt unabhaengig von seinem
# Praefix gegen ``known_anchors`` geprueft.


@dataclass(frozen=True)
class QuoteValidationResult:
    """Ergebnis der <simulated_quote>-Anker-Validierung für einen Report-Abschnitt."""

    valid: bool
    quotes: List[Dict[str, Any]] = field(default_factory=list)
    invalid_quotes: List[Dict[str, Any]] = field(default_factory=list)
    unbound_evidence_refs: List[str] = field(default_factory=list)
    missing_evidence_refs: List[str] = field(default_factory=list)


def _extract_known_anchors(evidence_map: Union[Dict[str, Any], Any]) -> set:
    """Extrahiert alle bekannten source_id_anchor-Werte aus der EvidenceMap.

    Unterstützt sowohl rohe dicts (agent.evidence_map) als auch
    EvidenceMapModel-Instanzen.
    """
    known: set = set()
    if hasattr(evidence_map, "evidence_index"):
        # EvidenceMapModel-Instanz
        for evidence_id, item in evidence_map.evidence_index.items():
            known.add(evidence_id)
            anchor = getattr(item, "source_id_anchor", None)
            if anchor:
                known.add(anchor)
    elif isinstance(evidence_map, dict):
        evidence_map = normalize_persisted_evidence_map(evidence_map) or evidence_map
        for evidence_id, item in (evidence_map.get("evidence_index") or {}).items():
            known.add(evidence_id)
            anchor = item.get("source_id_anchor")
            if anchor:
                known.add(anchor)
    return known


def validate_quote_anchors(
    section_text: str,
    evidence_map: Union[Dict[str, Any], Any],
    persona_ids: List[str],
) -> QuoteValidationResult:
    """Parst <simulated_quote>-Tags und prüft Bindung an EvidenceMap + Persona-Plan.

    Args:
        section_text: Der vollständige Markdown-Text eines generierten Abschnitts.
        evidence_map: Die aktuelle EvidenceMap (raw dict oder EvidenceMapModel-Instanz).
        persona_ids: Liste bekannter Persona-IDs aus dem Report-Plan.

    Returns:
        QuoteValidationResult mit valid=True nur wenn alle Quotes korrekt
        annotiert sind (persona_id vorhanden + bekannt, seed_anchor vorhanden).
        Ein vorhandener, aber nicht aufloesbarer Anker macht das Zitat nicht
        ungueltig, erscheint aber in ``unbound_evidence_refs`` — seit #1249
        unabhaengig davon, ob er ein ``ev_``- oder ein ``seed_doc:``-Anker ist.
        Sections ohne Quotes → valid=True.
    """
    known_anchors = _extract_known_anchors(evidence_map)
    persona_id_set = set(persona_ids)

    valid_quotes: List[Dict[str, Any]] = []
    invalid_quotes: List[Dict[str, Any]] = []
    unbound_refs: List[str] = []

    for match in _QUOTE_TAG_RE.finditer(section_text):
        attrs_raw = match.group(1)
        text = match.group(2).strip()
        raw_tag = match.group(0)

        attrs = dict(_ATTR_RE.findall(attrs_raw))
        persona_id = attrs.get("persona_id")
        seed_anchor = attrs.get("seed_anchor")

        reasons: List[str] = []

        if not persona_id:
            reasons.append("missing persona_id")
        elif persona_id_set and persona_id not in persona_id_set:
            # Nur prüfen wenn die Whitelist nicht leer ist; leere Liste = unkonfiguriert
            reasons.append(f"unknown persona_id={persona_id!r}")

        if not seed_anchor:
            reasons.append("missing seed_anchor")
        elif seed_anchor not in known_anchors:
            # Issue #1249: Bis zu diesem Slice umging jeder Anker mit
            # ``seed_doc:``-Praefix die Bindungspruefung vollstaendig — er galt
            # als opake Referenz und wurde nie aufgeloest. Ein ``ev_``-Anker
            # ohne Bindung war als ``unbound_evidence_refs`` sichtbar,
            # ``seed_doc:beliebig`` niemals.
            #
            # Das Modell waehlte in den beobachteten Laeufen exakt diesen einen
            # ungeprueften Pfad, mit dem Wert, den der Prompt ihm vorgab: alle
            # acht Zitate einer Section trugen ``seed_doc:interview_transcript_07``,
            # ein Dokument dieses Namens existierte im Lauf nicht. Ein
            # staerkeres Modell konstruierte stattdessen pro Persona einen
            # individuell klingenden Anker, der ebenfalls auf nichts verweist —
            # dann sieht jedes Zitat einzeln belegt aus.
            #
            # Eine eigene Aufloesungsquelle braucht es dafuer nicht: echte
            # Seed-Anker haben nach ADR-0013 die Form
            # ``seed_doc:<document_id>#chunk:<chunk_id>`` und stehen als
            # ``source_id_anchor`` bereits in ``known_anchors``.
            #
            # Politik (Sign-off 2026-08-11): fuehren wie einen ungebundenen
            # ``ev_``-Anker — sichtbar, ohne das Zitat hart zu verwerfen. Ein
            # real existierendes, aber aus technischen Gruenden nicht
            # indiziertes Dokument kostet damit Sichtbarkeit, keinen Inhalt.
            if not reasons:
                unbound_refs.append(seed_anchor)

        if reasons:
            invalid_quotes.append({
                "raw": raw_tag,
                "persona_id": persona_id,
                "seed_anchor": seed_anchor,
                "text": text,
                "reason": "; ".join(reasons),
            })
        else:
            valid_quotes.append({
                "persona_id": persona_id,
                "seed_anchor": seed_anchor,
                "text": text,
            })

    # valid=True wenn keine Invalid-Quotes und keine ungebundenen Refs vorhanden.
    # Sections ohne Quotes → valid=True (Aufrufer entscheidet ob Pflicht).
    is_valid = len(invalid_quotes) == 0 and len(unbound_refs) == 0

    return QuoteValidationResult(
        valid=is_valid,
        quotes=valid_quotes,
        invalid_quotes=invalid_quotes,
        unbound_evidence_refs=unbound_refs,
        missing_evidence_refs=[],  # Reserviert für Claim-DTO-Pflichtfelder (separater Slice)
    )


_PLACEHOLDER_TEXTS = frozenset({"", "---", "—", "–", "n/a", "n.a.", "tbd", "todo", "?"})


def _is_placeholder(value: Any) -> bool:
    """True wenn ein LLM-Text-Feld ein Platzhalter ist (leer, ``---``, ``n/a`` …).

    LLMs liefern bei unsicheren Sub-Items gern Trenner statt echtem Inhalt;
    der strikte Pydantic-Validator (``min_length=8``) lehnt sie ab → ganzer
    Report failed. Wir entfernen sie defensiv in der Boundary
    (Smoke-Live 2026-05-15).
    """
    if not isinstance(value, str):
        return value is None
    return value.strip().lower() in _PLACEHOLDER_TEXTS


def _filter_placeholder_items(
    items: List[Dict[str, Any]],
    text_field: str,
    *,
    logger: Any = None,
    item_kind: str = "item",
) -> List[Dict[str, Any]]:
    """Wirft Items mit leerem/Platzhalter-Text-Feld raus."""
    keep: List[Dict[str, Any]] = []
    dropped = 0
    for entry in items or []:
        if not isinstance(entry, dict):
            keep.append(entry)
            continue
        if _is_placeholder(entry.get(text_field)):
            dropped += 1
            continue
        keep.append(entry)
    if dropped and logger is not None:
        logger.warning(
            "normalize_sections_for_contract: %d %s mit leerem/Platzhalter-%s entfernt",
            dropped, item_kind, text_field,
        )
    return keep


def normalize_sections_for_contract(
    sections: List[Dict[str, Any]],
    *,
    logger: Any = None,
) -> List[Dict[str, Any]]:
    normalized_sections: List[Dict[str, Any]] = []
    for section in sections:
        item = {k: v for k, v in dict(section).items() if k != "schema_version"}
        item["section_title"] = (item.get("section_title") or "Recovered section").strip()
        summary = (item.get("section_summary") or item.get("section_title") or "Recovered summary").strip()
        item["section_summary"] = summary or "Recovered summary"
        item["claims"] = normalize_claims_for_contract(item.get("claims") or [], logger=logger)
        item["hypotheses"] = _filter_placeholder_items(
            list(item.get("hypotheses") or []),
            "hypothesis_text",
            logger=logger,
            item_kind="hypotheses",
        )
        item["hypotheses_appendix"] = _filter_placeholder_items(
            list(item.get("hypotheses_appendix") or []),
            "hypothesis_text",
            logger=logger,
            item_kind="hypotheses_appendix",
        )
        item["data_gaps"] = _filter_placeholder_items(
            list(item.get("data_gaps") or []),
            "claim_text",
            logger=logger,
            item_kind="data_gaps",
        )
        normalized_sections.append(item)
    return normalized_sections


# ---------------------------------------------------------------------------
# Issue #1006 — Graceful Degradation nach fehlgeschlagener Contract-Validierung
# ---------------------------------------------------------------------------

_MIN_HYPOTHESIS_TEXT_LEN = 8
_MAX_HYPOTHESIS_FIELD_LEN = 1000
_FALLBACK_RATIONALE = (
    "Automatisch aus einem Claim ohne ausreichende Evidence in eine "
    "Hypothese überführt, da der ursprüngliche Validierungsfehler keine "
    "verwertbare Begründung lieferte."
)


def _collect_existing_hypothesis_ids(section: Dict[str, Any]) -> set:
    ids: set = set()
    for list_name in ("hypotheses", "hypotheses_appendix"):
        for entry in section.get(list_name) or []:
            if isinstance(entry, dict):
                hid = entry.get("hypothesis_id")
                if hid:
                    ids.add(hid)
    return ids


def _next_hypothesis_id(existing: set) -> str:
    i = 1
    while True:
        candidate = f"hypothesis_{i:02d}"
        if candidate not in existing:
            return candidate
        i += 1


def degrade_sections_for_violations(
    sections: List[Dict[str, Any]],
    error: "ValidationError",
    *,
    logger: Any = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Repariert Sections nach einem fehlgeschlagenen Contract-Validate.

    Liest ``error.errors()`` (Pydantic) und wendet je nach ``loc``-Pfad eine
    von drei Reparaturregeln an (ADR-0002-konform: die Reaktion auf einen
    Verstoss wird angepasst, nicht der Verstoss selbst toleriert):

    - Claim-Verstoss mit Evidence → ``confidence_label`` auf ``low``.
    - Claim-Verstoss ohne Evidence → Claim entfernen, ggf. als Hypothese
      wiederaufleben lassen (nur bei ausreichend langem ``claim_text``).
    - Hypothesen-Verstoss (``hypotheses`` oder ``hypotheses_appendix``) →
      Eintrag entfernen.

    Verstösse, die keiner dieser Formen entsprechen, werden ignoriert
    (Section bleibt unverändert, kein Protokolleintrag) — hier wird bewusst
    nicht geraten.

    Mutiert die Eingabe nicht; arbeitet auf einer tiefen Kopie.
    """
    repaired: List[Dict[str, Any]] = copy.deepcopy(sections)
    violations: List[Dict[str, Any]] = []

    claims_to_remove: Dict[int, set] = {}
    hyps_to_remove: Dict[Tuple[int, str], set] = {}
    processed_claims: set = set()
    processed_hyps: set = set()

    def _log_violation(entry: Dict[str, Any]) -> None:
        violations.append(entry)
        if logger is not None:
            logger.warning(
                "degrade_sections_for_violations: section=%s claim_id=%s "
                "violation=%s action=%s detail=%s",
                entry["section_index"],
                entry["claim_id"],
                entry["violation"],
                entry["action"],
                entry["detail"],
            )

    for err in error.errors():
        loc = err.get("loc") or ()
        violation_type = str(err.get("type") or "unknown")
        detail = str(err.get("msg") or "")[:500]
        if len(loc) < 4 or loc[0] != "sections":
            # Cross-Record-Validatoren hängen ihre Fehler an die EvidenceMap
            # selbst. Den betroffenen Claim transportieren sie deshalb stabil
            # im Fehlertext (``Claim <id>: ...``), nicht im ``loc``-Pfad.
            section_claim_match = re.search(
                r"\bSection ([^ ]+) Claim ([^:]+):", detail
            )
            claim_match = re.search(r"\bClaim ([^:]+):", detail)
            target_section = (
                section_claim_match.group(1) if section_claim_match else None
            )
            if section_claim_match:
                target_id = section_claim_match.group(2)
            elif claim_match:
                target_id = claim_match.group(1)
            else:
                target_id = None
            if target_id:
                targeted = False
                for fallback_si, fallback_section in enumerate(repaired):
                    if (
                        target_section is not None
                        and str(fallback_section.get("section_index")) != target_section
                    ):
                        continue
                    for fallback_ci, claim in enumerate(fallback_section.get("claims") or []):
                        if not isinstance(claim, dict) or claim.get("claim_id") != target_id:
                            continue
                        if (fallback_si, fallback_ci) in processed_claims:
                            break
                        processed_claims.add((fallback_si, fallback_ci))
                        if claim.get("evidence"):
                            # Issue #1012: auch dieser Pfad haelt fest, unter
                            # welcher Stufe der Wortlaut entstanden ist.
                            _record_text_confidence_downgrade(
                                claim,
                                from_label=str(claim.get("confidence_label") or ""),
                                to_label="low",
                            )
                            claim["confidence_label"] = "low"
                            _log_violation({
                                "section_index": fallback_section.get("section_index", 0),
                                "claim_id": target_id,
                                "violation": violation_type,
                                "action": "downgraded_to_low",
                                "detail": detail,
                            })
                        targeted = True
                        break
                    if targeted:
                        break
            continue

        si = loc[1]
        kind = loc[2]
        if not isinstance(si, int) or not (0 <= si < len(repaired)):
            continue
        section = repaired[si]
        section_index_value = section.get("section_index", 0)
        if kind == "claims":
            ci = loc[3]
            claims_list = section.get("claims") or []
            if not isinstance(ci, int) or not (0 <= ci < len(claims_list)):
                continue
            if (si, ci) in processed_claims:
                continue
            processed_claims.add((si, ci))
            claim = claims_list[ci]
            if not isinstance(claim, dict):
                continue
            claim_id = str(claim.get("claim_id") or "")
            evidence = claim.get("evidence") or []

            if evidence:
                # Issue #1012: siehe oben — beide Abstufungspfade werden
                # gleich behandelt, sonst haengt die Sichtbarkeit davon ab,
                # welcher Validator zuerst anschlaegt.
                _record_text_confidence_downgrade(
                    claim,
                    from_label=str(claim.get("confidence_label") or ""),
                    to_label="low",
                )
                claim["confidence_label"] = "low"
                _log_violation({
                    "section_index": section_index_value,
                    "claim_id": claim_id,
                    "violation": violation_type,
                    "action": "downgraded_to_low",
                    "detail": detail,
                })
                continue

            claims_to_remove.setdefault(si, set()).add(ci)
            claim_text = claim.get("claim_text")
            stripped_text = claim_text.strip() if isinstance(claim_text, str) else ""

            if len(stripped_text) >= _MIN_HYPOTHESIS_TEXT_LEN:
                existing_ids = _collect_existing_hypothesis_ids(section)
                new_id = _next_hypothesis_id(existing_ids)
                hypothesis_text = stripped_text[:_MAX_HYPOTHESIS_FIELD_LEN]
                rationale = detail.strip() if len(detail.strip()) >= _MIN_HYPOTHESIS_TEXT_LEN else _FALLBACK_RATIONALE
                rationale = rationale[:_MAX_HYPOTHESIS_FIELD_LEN]
                new_hypothesis = {
                    "hypothesis_id": new_id,
                    "hypothesis_text": hypothesis_text,
                    "rationale": rationale,
                }
                section.setdefault("hypotheses", []).append(new_hypothesis)
                _log_violation({
                    "section_index": section_index_value,
                    "claim_id": claim_id,
                    "violation": violation_type,
                    "action": "moved_to_hypotheses",
                    "detail": detail,
                })
            else:
                _log_violation({
                    "section_index": section_index_value,
                    "claim_id": claim_id,
                    "violation": violation_type,
                    "action": "dropped",
                    "detail": detail,
                })

        elif kind in ("hypotheses", "hypotheses_appendix"):
            hi = loc[3]
            hyp_list = section.get(kind) or []
            if not isinstance(hi, int) or not (0 <= hi < len(hyp_list)):
                continue
            key = (si, kind)
            if (key, hi) in processed_hyps:
                continue
            processed_hyps.add((key, hi))
            hyp_entry = hyp_list[hi]
            hyp_id = ""
            if isinstance(hyp_entry, dict):
                hyp_id = str(hyp_entry.get("hypothesis_id") or "")
            hyps_to_remove.setdefault(key, set()).add(hi)
            _log_violation({
                "section_index": section_index_value,
                "claim_id": hyp_id,
                "violation": violation_type,
                "action": "dropped",
                "detail": detail,
            })
        # Alles andere: keine bekannte Regel, Section bleibt unverändert.

    for si, indices in claims_to_remove.items():
        claims_list = repaired[si].get("claims")
        if not isinstance(claims_list, list):
            continue
        for idx in sorted(indices, reverse=True):
            del claims_list[idx]

    for (si, list_name), indices in hyps_to_remove.items():
        hyp_list = repaired[si].get(list_name)
        if not isinstance(hyp_list, list):
            continue
        for idx in sorted(indices, reverse=True):
            del hyp_list[idx]

    return repaired, violations


__all__ = [
    "init_evidence_map",
    "normalize_claims_for_contract",
    "normalize_sections_for_contract",
    "record_evidence_item",
    "register_evidence_record",
    "resolve_embedder",
    # M11.8e
    "QuoteValidationResult",
    "validate_quote_anchors",
    # Smoke-Live 2026-05-15 — Auto-Downgrade
    "auto_downgrade_unsupported_high_claims",
    # Issue #1006 — Graceful Degradation
    "degrade_sections_for_violations",
]
