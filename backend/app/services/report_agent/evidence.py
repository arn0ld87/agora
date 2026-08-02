from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from pydantic import ValidationError

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
        "global_evidence": global_evidence,
        "sections": [],
    }
    return EvidenceMapModel.model_validate(payload).model_dump(mode="json")


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
        group = entry.get("persona_stakeholder_group")
        if group:
            groups.add(group)
    return len(groups)


def has_agent_grounded_evidence(evidence: List[Dict[str, Any]]) -> bool:
    """True, wenn die Evidence mind. 1 ``agent_quote`` (mit nicht-leerem
    ``quote``-Feld) UND mind. 1 ``seed_corpus`` enthält (ADR-0002 Stufe
    agent_grounded → rechtfertigt ``medium``). Spiegelt
    ``ReportClaimModel.agent_grounded_for_medium`` (Issue #906 Defekt 1).
    ``supports_claim`` wird hier nicht gefordert — analog zum medium-Validator.
    Das Quote-Feld ist Pflicht (ADR-0002 Z. 54; Codex PR-Review #961 P2): ein
    zusammengefasstes Interview ohne Original-Zitat ist nicht agent_grounded.
    """
    has_agent_quote = False
    has_seed_corpus = False
    for entry in evidence or []:
        if not isinstance(entry, dict):
            continue
        sk = entry.get("source_kind")
        if sk == "agent_quote" and entry.get("quote"):
            has_agent_quote = True
        elif sk == "seed_corpus":
            has_seed_corpus = True
    return has_agent_quote and has_seed_corpus


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
_SEED_DOC_PREFIX = "seed_doc:"


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
    if hasattr(evidence_map, "global_evidence"):
        # EvidenceMapModel-Instanz
        for item in evidence_map.global_evidence:
            anchor = getattr(item, "source_id_anchor", None)
            if anchor:
                known.add(anchor)
    elif isinstance(evidence_map, dict):
        for item in evidence_map.get("global_evidence", []):
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
        annotiert sind (persona_id vorhanden + bekannt, seed_anchor vorhanden +
        gebunden ODER mit seed_doc:-Prefix). Sections ohne Quotes → valid=True.
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
        else:
            # seed_doc:-Prefix ist immer akzeptiert (opaque Referenz)
            if not seed_anchor.startswith(_SEED_DOC_PREFIX):
                if seed_anchor not in known_anchors:
                    # Strukturell korrekt aber Referenz ungebunden → kein invalid_quote,
                    # aber unbound_evidence_refs-Eintrag
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
        if len(loc) < 4 or loc[0] != "sections":
            continue

        si = loc[1]
        kind = loc[2]
        if not isinstance(si, int) or not (0 <= si < len(repaired)):
            continue
        section = repaired[si]
        section_index_value = section.get("section_index", 0)
        violation_type = str(err.get("type") or "unknown")
        detail = str(err.get("msg") or "")[:500]

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
    "resolve_embedder",
    # M11.8e
    "QuoteValidationResult",
    "validate_quote_anchors",
    # Smoke-Live 2026-05-15 — Auto-Downgrade
    "auto_downgrade_unsupported_high_claims",
    # Issue #1006 — Graceful Degradation
    "degrade_sections_for_violations",
]
