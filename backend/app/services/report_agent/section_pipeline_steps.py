"""Einzelschritte der Abschnittsverarbeitung (Issue #1212)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ...utils.logger import get_logger
from .attribution_guard import (
    attribution_findings,
    correct_attribution,
    profile_from_evidence_index,
    resolve_section_evidence_records,
)
from .section_pipeline_types import (
    SectionContext,
    SectionEvidenceOutcome,
    SectionResult,
    _section_expects_quotes,
)

logger = get_logger('agora.report_agent')


def _restore_persisted_section(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
    persisted_entry: Dict[str, Any],
) -> SectionResult:
    """Übernimmt einen bereits persistierten Abschnitt unverändert.

    Der Aufrufer prüft vorher, ob Evidence vorhanden ist. Siehe process_section().

    Issue #1479 (Codex-Review Runde 3, Finding 1): ``generation_failed`` steht
    bereits in der persistierten Evidence — ein Resume baut aber einen neuen
    Aufruf mit einer leeren ``failed_section_indices``-Liste, und diese
    Funktion gab den Fehlschlag bisher nicht weiter. Ein zuvor gescheiterter,
    beim Resume nur restaurierter Abschnitt verschwand damit aus der
    Fehlerliste, und ein sonst vollständiger Rest-Lauf konnte den Report auf
    COMPLETED heben, obwohl der Abschnitt weiterhin Fallback-Text enthält.
    """
    section.content = ctx.report_manager._clean_section_content(
        ctx.persisted_section_contents[section_index], section.title
    )
    generation_failed = bool(persisted_entry.get("generation_failed", False))
    quote_validation_failed = bool(persisted_entry.get("quote_validation_failed", False))
    metadata = dict(
        persisted_entry.get("structured_metadata")
        or persisted_entry.get("metadata")
        or {}
    )
    unbound_evidence_refs = list(
        persisted_entry.get("unbound_evidence_refs") or []
    )

    if metadata:
        if not hasattr(section, "metadata") or section.metadata is None:
            section.metadata = {}
        section.metadata["structured_metadata"] = metadata
        if hasattr(agent, "_record_section_metadata"):
            agent._record_section_metadata(section_index, metadata)

    if quote_validation_failed:
        if not hasattr(section, "metadata") or section.metadata is None:
            section.metadata = {}
        section.metadata["quote_validation_failed"] = True

    if unbound_evidence_refs:
        pending = getattr(agent, "_pending_unbound_evidence_refs", None)
        if pending is None:
            pending = {}
            agent._pending_unbound_evidence_refs = pending
        pending[section_index] = unbound_evidence_refs

    evidence_map = getattr(agent, "evidence_map", None)
    if isinstance(evidence_map, dict):
        evidence_outcome = SectionEvidenceOutcome.from_persisted_section(
            evidence_map,
            section_index,
            gate_decisions=[],
            generation_failed=generation_failed,
        )
    else:
        evidence_outcome = SectionEvidenceOutcome(generation_failed=generation_failed)

    return SectionResult(
        section_index=section_index,
        title=section.title,
        content=section.content,
        failed=generation_failed,
        quote_validation_failed=quote_validation_failed,
        metadata=metadata,
        evidence=evidence_outcome,
        unbound_evidence_refs=unbound_evidence_refs,
        restored=True,
    )


def _remove_orphan_markdown(
    ctx: SectionContext, *, section_index: int, title: str
) -> None:
    """Entfernt eine verwaiste Markdown-Datei, bevor die Sektion neu generiert wird.

    Codex-Review PR #1475, Finding 1: ``process_section`` schreibt bei einer
    Regeneration zuerst neue Evidence, dann neues Markdown (Commit-Marker).
    Bliebe die alte, evidence-lose Markdown-Datei bis dahin liegen, sähe ein
    Absturz zwischen beiden Schritten sowohl die neue Evidence als auch das
    ALTE Markdown auf der Platte — ein nächster Resume würde das alte Markdown
    gegen die neue Evidence restaurieren, obwohl beide aus unterschiedlichem
    Inhalt stammen.
    Einfachste Lösung statt einer Bindung beider Artefakte über einen
    Generations-Identifier: die Waise sofort entfernen. Ohne Evidence-Eintrag
    darf ohnehin niemand dem alten Inhalt vertrauen, ein Identifier-Abgleich
    wäre hier reiner Mehraufwand für dasselbe Ergebnis.

    Codex-Review PR #1475, Runde 2, Finding 1: ein ``OSError`` beim Entfernen
    wird NICHT mehr geschluckt — er propagiert an ``process_section`` und
    damit VOR dem Schreiben neuer Evidence. Ein geschluckter Fehler ließe die
    Waise liegen, während ``_save_evidence_section`` trotzdem neue Evidence
    persistiert — exakt die Inkonsistenz, die dieser Slice beseitigen soll
    (das nachfolgende ``os.replace`` scheitert unter denselben
    Rechteproblemen typischerweise ebenfalls). Die Sektion scheitert damit
    sauber, statt stillschweigend inkonsistent zu werden.

    CodeRabbit-Review PR #1475, Runde 3, Finding 2: eine ``FileNotFoundError``
    ist die eine Ausnahme davon. Der DELETE-Endpunkt löscht den Report-Ordner
    per ``shutil.rmtree`` und kann ``stale_path`` genau zwischen der
    ``os.path.exists``-Prüfung oben und diesem ``os.remove`` entfernen
    (TOCTOU). In dem Fall ist der gewünschte Endzustand — keine Waise mehr
    auf der Platte — bereits erreicht, also wird das als Erfolg gewertet.
    ``PermissionError`` und jeder andere ``OSError`` propagieren weiterhin
    unverändert (siehe Finding 1 oben).
    """
    import sys
    # Falls tests os.remove in section_pipeline mocken
    pipe_mod = sys.modules.get("app.services.report_agent.section_pipeline")
    os_remove_fn = getattr(pipe_mod, "os", os).remove if pipe_mod else os.remove

    stale_path = ctx.report_manager._get_section_path(ctx.report_id, section_index)
    if not os.path.exists(stale_path):
        return
    try:
        os_remove_fn(stale_path)
    except FileNotFoundError:
        logger.info(
            "section %d (%r): verwaiste Markdown-Datei bereits entfernt (%s)",
            section_index,
            title,
            stale_path,
        )
        return
    logger.info(
        "section %d (%r): verwaiste Markdown-Datei entfernt (%s)",
        section_index,
        title,
        stale_path,
    )


def _generate_content(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    *,
    section_index: int,
    base_progress: int,
) -> str:
    """Meldet den Start und erzeugt den Abschnittsinhalt."""
    generating_message = (
        f"Generating section: {section.title} "
        f"({section_index}/{ctx.total_sections})"
    )
    ctx.report_manager.update_progress(
        ctx.report_id,
        "generating",
        base_progress,
        generating_message,
        current_section=section.title,
        completed_sections=ctx.completed_section_titles,
    )
    if ctx.progress_callback:
        ctx.progress_callback("generating", base_progress, generating_message)

    def _section_progress(stage: str, prog: int, msg: str) -> None:
        if ctx.progress_callback:
            ctx.progress_callback(
                stage,
                base_progress + int(prog * 0.7 / ctx.total_sections),
                msg,
            )

    return ctx.generate_section(
        agent,
        section=section,
        outline=ctx.outline,
        previous_sections=ctx.previous_sections,
        progress_callback=_section_progress if ctx.progress_callback else None,
        section_index=section_index,
        report_id=ctx.report_id,
    )


def _validate_quotes_with_repair(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    content: str,
    *,
    section_index: int,
) -> tuple[str, bool, List[str]]:
    """Prüft Persona-Zitate und versucht bei Verstoß genau einen Repair-Retry.

    M11.8e + P4.1 — nur für Abschnittstypen, die Zitate erwarten:
    ``explorative`` überspringt die Prüfung, ``balanced`` repariert
    best-effort, ``strict`` protokolliert den gescheiterten Repair prominent.
    In keinem Modus wird der Abschnitt verworfen.

    Liefert ``(Inhalt, quote_validation_failed, ungebundene Evidence-Refs)``.

    Issue #1324: Die ungebundenen Refs standen bisher nur im Log. Ein Leser
    des Artefakts sah damit nicht, welcher Beleg zitiert, aber nie gebunden
    wurde — genau die Information, die den ``incomplete``-Status erklärt.
    """
    if not _section_expects_quotes(section.title, getattr(section, "kind", None)) or ctx.report_mode == "explorative":
        return content, False, []

    evidence_map_for_validation = agent.evidence_map or {}
    persona_ids_for_validation: List[str] = getattr(agent, "persona_ids", []) or []
    quote_result = ctx.validate_quotes(
        content,
        evidence_map_for_validation,
        persona_ids_for_validation,
    )
    if quote_result.valid:
        return content, False, []

    logger.warning(
        "quote_anchor_validation: section=%d title=%r mode=%s — "
        "invalid quotes detected, attempting repair retry. "
        "invalid_quotes=%r unbound_refs=%r",
        section_index,
        section.title,
        ctx.report_mode,
        quote_result.invalid_quotes,
        quote_result.unbound_evidence_refs,
    )
    repair_content = ctx.generate_section(
        agent,
        section=section,
        outline=ctx.outline,
        previous_sections=ctx.previous_sections,
        progress_callback=None,
        section_index=section_index,
        report_id=ctx.report_id,
    )
    repair_result = ctx.validate_quotes(
        repair_content,
        evidence_map_for_validation,
        persona_ids_for_validation,
    )
    if repair_result.valid:
        logger.info(
            "quote_anchor_validation: section=%d repair successful",
            section_index,
        )
        return repair_content, False, []

    # Repair fehlgeschlagen — Section trotzdem weiter, Flag setzen
    log_fn = logger.error if ctx.report_mode == "strict" else logger.warning
    log_fn(
        "quote_anchor_validation: section=%d mode=%s repair retry also failed. "
        "Setting quote_validation_failed=True. "
        "repair_invalid_quotes=%r repair_unbound=%r",
        section_index,
        ctx.report_mode,
        repair_result.invalid_quotes,
        repair_result.unbound_evidence_refs,
    )
    return repair_content, True, list(repair_result.unbound_evidence_refs)


def _correct_attribution(
    agent: Any,
    section: Any,
    content: str,
    *,
    section_index: int,
) -> str:
    """Stellt Zuschreibungen richtig, für die es keine Belege gibt.

    Im Referenzlauf ``report_cc2ef45da5e9`` trug einer von 13 validierten
    Claims Simulations-Evidence, und der Text schrieb durchgehend "Die
    Simulation zeigt …". Ersetzt wird nur die Zeugenformel, nie der Satz —
    die Aussage bleibt, ihre Herkunft wird richtiggestellt.

    Läuft **vor** der Faktenprüfung: der Sanitizer arbeitet dann auf dem Text,
    der auch ausgeliefert wird, und seine Satzgrenzen stimmen mit denen des
    Endergebnisses überein.
    """
    ev_map = getattr(agent, "evidence_map", None) or {}
    index = ev_map.get("evidence_index") or {}
    active_sec_ev = getattr(agent, "_active_section_evidence", None)
    if isinstance(active_sec_ev, (list, dict)):
        combined_sec_ev: List[Any] = (
            list(active_sec_ev.values())
            if isinstance(active_sec_ev, dict)
            else list(active_sec_ev)
        )
        for global_refs in (
            ev_map.get("global_evidence_refs"),
            getattr(agent, "global_evidence_refs", None),
        ):
            if isinstance(global_refs, (list, tuple, set)):
                combined_sec_ev.extend(global_refs)
            elif isinstance(global_refs, dict):
                combined_sec_ev.extend(global_refs.values())
        evidence_source = resolve_section_evidence_records(combined_sec_ev, index)
    else:
        evidence_source = index
    profile = profile_from_evidence_index(evidence_source)
    findings = attribution_findings(content, profile)
    if not findings:
        return content

    logger.warning(
        "section %d (%r): %d Zuschreibung(en) ohne Grundlage — %s",
        section_index,
        getattr(section, "title", ""),
        len(findings),
        "; ".join(finding["kind"] for finding in findings),
    )
    return correct_attribution(content, profile)


def _verify_prose_facts(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    content: str,
    *,
    section_index: int,
) -> str:
    """Prüft die Faktenaussagen des sichtbaren Fließtexts (P0).

    Quantitative Aussagen, denen eine Quelle widerspricht, werden entfernt.
    Aussagen ohne auffindbaren Beleg bleiben stehen und werden markiert —
    beide wandern zusätzlich in die Hypothesen (Issue #1356).
    """
    if ctx.is_fallback(content):
        return content
    import sys
    pipe_mod = sys.modules.get("app.services.report_agent.section_pipeline")
    corr_fn = getattr(pipe_mod, "_correct_attribution", _correct_attribution) if pipe_mod else _correct_attribution
    content = corr_fn(agent, section, content, section_index=section_index)
    verified = ctx.verify_prose_fn(content, agent._prose_evidence_pool())
    if not verified.changed:
        return content
    logger.warning(
        "section %d (%r): %d widersprochene Faktenaussage(n) entfernt, "
        "%d unbelegte im Text markiert — beide als Hypothese geführt.",
        section_index,
        section.title,
        len(verified.rejected),
        len(verified.unverified),
    )
    agent._record_prose_hypotheses(section_index, verified.flagged)
    agent._record_unverified_statements(section_index, verified.unverified)
    return verified.content


def _extract_metadata(
    agent: Any,
    section: Any,
    ctx: SectionContext,
    content: str,
    *,
    section_index: int,
    base_progress: int,
) -> Dict[str, Any]:
    """Strukturierte Metadaten-Extraktion via strict-schema chat_json (M11.8d).

    Fehler blockieren nicht die Hauptgenerierung (``generate_section_metadata``
    gibt bei Exception ``{}`` zurück).
    """
    metadata_phase_tracker = ctx.phase_tracker_factory(
        ctx.report_id,
        section_index=section_index,
        section_title=section.title,
        base_progress=base_progress,
        completed_sections=ctx.completed_section_titles,
        report_logger=agent.report_logger,
        report_manager=ctx.report_manager,
    )
    with metadata_phase_tracker.phase("section_metadata"):
        return ctx.generate_metadata(
            agent,
            section_title=section.title,
            section_content=content,
            section_index=section_index,
        )


def _apply_metadata(
    agent: Any,
    section: Any,
    section_meta: Dict[str, Any],
    *,
    section_index: int,
) -> None:
    """Schreibt die Metadaten an Section und Agent (P0-6)."""
    if section_meta and agent.report_logger and hasattr(
        agent.report_logger, "log_section_metadata"
    ):
        agent.report_logger.log_section_metadata(
            section_title=section.title,
            section_index=section_index,
            metadata=section_meta,
        )
    if not section_meta:
        return
    if not hasattr(section, "metadata") or section.metadata is None:
        section.metadata = {}
    section.metadata["structured_metadata"] = section_meta
    agent._record_section_metadata(section_index, section_meta)


# ---------------------------------------------------------------------------
# Metadaten-Grounding & Validierungs-Reparatur (Befund 3.1 / #1885 / #1475)
# ---------------------------------------------------------------------------

_METADATA_TEXT_KEYS = (
    "text",
    "description",
    "title",
    "content",
    "recommendation",
    "risk",
    "action",
    "step",
    "milestone",
    "item",
    "titel",
    "beschreibung",
    "begruendung",
    "massnahme",
    "risiko",
    "meilenstein",
)

_GROUNDED_METADATA_LIST_KEYS = (
    "recommendations",
    "change_recommendations",
    "risks",
    "timeline",
    "next_steps",
    "items",
)


def _collect_evidence_refs_from_claim(claim: Dict[str, Any], target: set[str]) -> None:
    """Sammelt alle Evidence-IDs und -Referenzen aus einem Claim-Dict."""
    for ev in claim.get("evidence") or []:
        if isinstance(ev, dict) and ev.get("evidence_id"):
            target.add(str(ev["evidence_id"]).strip())
        elif isinstance(ev, str) and ev.strip():
            target.add(ev.strip())
    for ref in claim.get("evidence_refs") or []:
        if ref and str(ref).strip():
            target.add(str(ref).strip())
    for ref in claim.get("supporting_evidence_ids") or []:
        if ref and str(ref).strip():
            target.add(str(ref).strip())


def _extract_verified_claims_and_evidence_ids(
    verified_claims: Optional[List[Dict[str, Any]]],
) -> tuple[set[str], set[str], dict[str, set[str]], dict[str, str]]:
    """Extrahiert verifizierte Claim-IDs, Evidence-IDs, Claim->Evidence-Map und Claim->Statement-Map."""
    claim_ids: set[str] = set()
    evidence_ids: set[str] = set()
    claim_evidence_map: dict[str, set[str]] = {}
    claim_statements: dict[str, str] = {}
    if not verified_claims:
        return claim_ids, evidence_ids, claim_evidence_map, claim_statements

    for idx, c in enumerate(verified_claims):
        if not isinstance(c, dict):
            continue
        cid = c.get("claim_id")
        cid_str = str(cid).strip() if cid is not None and str(cid).strip() else None
        synthetic_key = cid_str or f"__idx_{idx}"
        claim_ev: set[str] = set()
        _collect_evidence_refs_from_claim(c, claim_ev)
        stmt = str(c.get("statement") or c.get("text") or "").strip().lower()
        if stmt:
            claim_statements[synthetic_key] = stmt
        if cid_str:
            claim_ids.add(cid_str)
        claim_evidence_map.setdefault(synthetic_key, set()).update(claim_ev)
        evidence_ids.update(claim_ev)

    return claim_ids, evidence_ids, claim_evidence_map, claim_statements


def _find_metadata_entry_text(entry: Dict[str, Any]) -> str:
    """Sucht den ersten nicht-leeren Textwert aus bekannten Metadatenfeldern."""
    for key in _METADATA_TEXT_KEYS:
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _extract_metadata_entry_refs(entry: Dict[str, Any]) -> List[str]:
    """Extrahiert alle Evidence-Referenzstrings aus einem Metadateneintrag."""
    raw = list(entry.get("evidence_refs") or []) + list(entry.get("supporting_evidence_ids") or [])
    return [str(r).strip() for r in raw if r and str(r).strip()]


def _extract_metadata_entry_claim_ids(entry: Dict[str, Any]) -> List[str]:
    """Extrahiert alle referenzierten Claim-IDs aus einem Metadateneintrag."""
    raw: List[str] = []
    cid = entry.get("claim_id")
    if cid is not None and str(cid).strip():
        raw.append(str(cid).strip())
    cids = entry.get("claim_ids") or entry.get("supporting_claim_ids") or []
    if isinstance(cids, (list, tuple, set)):
        for item in cids:
            if item is not None and str(item).strip():
                raw.append(str(item).strip())
    elif isinstance(cids, str) and cids.strip():
        raw.append(cids.strip())
    return list(dict.fromkeys(raw))


def _refs_belong_to_single_claim_context(
    entry_refs: List[str],
    entry_text: str,
    *,
    verified_evidence_ids: set[str],
    claim_evidence_map: Optional[dict[str, set[str]]],
    claim_statements: Optional[dict[str, str]],
    persisted_content_lower: str,
) -> bool:
    """Prüft für Einträge ohne claim_id, ob alle Evidence-Refs zu einem gemeinsamen Claim gehören."""
    if not all(r in verified_evidence_ids for r in entry_refs):
        return False
    ev_map = claim_evidence_map or {}
    ref_set = set(entry_refs)
    owning_cids = [cid for cid, evs in ev_map.items() if ref_set.issubset(evs)]
    if not owning_cids:
        return False
    if not entry_text:
        return True
    snippet = entry_text[:60].lower()
    stmts = claim_statements or {}
    matching_cids = [
        cid for cid, st in stmts.items() if st and (snippet in st or st[:60] in snippet)
    ]
    if matching_cids:
        return all(cid in owning_cids for cid in matching_cids)
    return True


def _check_claim_and_refs_grounding(
    referenced_claim_ids: List[str],
    entry_refs: List[str],
    entry_text: str,
    *,
    verified_claim_ids: set[str],
    verified_evidence_ids: set[str],
    claim_evidence_map: Optional[dict[str, set[str]]],
    claim_statements: Optional[dict[str, str]],
    persisted_content_lower: str,
) -> bool:
    """Prüft, ob Claim-IDs verifiziert sind und Evidence-Refs zu den referenzierten Claims passen."""
    if referenced_claim_ids:
        if any(cid not in verified_claim_ids for cid in referenced_claim_ids):
            return False
        if entry_refs:
            allowed_refs: set[str] = set()
            for cid in referenced_claim_ids:
                allowed_refs.update((claim_evidence_map or {}).get(cid, set()))
            return bool(allowed_refs) and all(r in allowed_refs for r in entry_refs)
        return True

    if entry_refs:
        return _refs_belong_to_single_claim_context(
            entry_refs,
            entry_text,
            verified_evidence_ids=verified_evidence_ids,
            claim_evidence_map=claim_evidence_map,
            claim_statements=claim_statements,
            persisted_content_lower=persisted_content_lower,
        )

    return True


def _is_metadata_entry_grounded(
    entry: Dict[str, Any],
    *,
    verified_claim_ids: set[str],
    verified_evidence_ids: set[str],
    claim_evidence_map: Optional[dict[str, set[str]]] = None,
    claim_statements: Optional[dict[str, str]] = None,
    persisted_content_lower: str,
    has_claims: bool,
    has_content: bool,
) -> bool:
    """Prüft, ob ein einzelner strukturierter Metadateneintrag ausreichend gestützt ist."""
    if not has_claims or not has_content:
        return False

    referenced_claim_ids = _extract_metadata_entry_claim_ids(entry)
    entry_refs = _extract_metadata_entry_refs(entry)
    entry_text = _find_metadata_entry_text(entry)

    if referenced_claim_ids or entry_refs:
        return _check_claim_and_refs_grounding(
            referenced_claim_ids,
            entry_refs,
            entry_text,
            verified_claim_ids=verified_claim_ids,
            verified_evidence_ids=verified_evidence_ids,
            claim_evidence_map=claim_evidence_map,
            claim_statements=claim_statements,
            persisted_content_lower=persisted_content_lower,
        )

    return bool(entry_text and entry_text[:60].lower() in persisted_content_lower)


def filter_structured_metadata_against_verified_section(
    structured_metadata: Optional[Dict[str, Any]],
    *,
    verified_claims: Optional[List[Dict[str, Any]]],
    persisted_content: Optional[str],
) -> Dict[str, Any]:
    """Filtert Metadaten-Listen gegen die verifizierten Claims und den Sektionsinhalt."""
    if not structured_metadata or not isinstance(structured_metadata, dict):
        return {}

    verified_claims_list = verified_claims or []
    persisted_content_str = persisted_content or ""
    persisted_content_lower = persisted_content_str.lower()
    has_claims = bool(verified_claims_list)
    has_content = bool(persisted_content_str.strip())

    claim_ids, evidence_ids, claim_evidence_map, claim_statements = (
        _extract_verified_claims_and_evidence_ids(verified_claims_list)
    )

    filtered: Dict[str, Any] = dict(structured_metadata)
    for key in _GROUNDED_METADATA_LIST_KEYS:
        items = filtered.get(key)
        if not items or not isinstance(items, list):
            continue

        filtered[key] = [
            entry
            for entry in items
            if isinstance(entry, dict)
            and _is_metadata_entry_grounded(
                entry,
                verified_claim_ids=claim_ids,
                verified_evidence_ids=evidence_ids,
                claim_evidence_map=claim_evidence_map,
                claim_statements=claim_statements,
                persisted_content_lower=persisted_content_lower,
                has_claims=has_claims,
                has_content=has_content,
            )
        ]

    return filtered


_filter_structured_metadata_against_verified_section = (
    filter_structured_metadata_against_verified_section
)


def _extract_droppable_section_index(
    err: Any, sections: List[Dict[str, Any]]
) -> Optional[tuple[int, str, int]]:
    """Prüft einen ValidationError-Eintrag und liefert (section_pos, kind, item_idx) falls entfernbar."""
    loc: List[Any] = list(err.get("loc") or ()) if isinstance(err, dict) else []
    if len(loc) < 4 or loc[0] != "sections":
        return None
    si, kind, idx = loc[1], loc[2], loc[3]
    if kind not in ("claims", "hypotheses", "hypotheses_appendix"):
        return None
    if not isinstance(si, int) or not (0 <= si < len(sections)):
        return None
    entries = sections[si].get(kind) or []
    if not isinstance(idx, int) or not (0 <= idx < len(entries)):
        return None
    return (si, str(kind), idx)


def drop_unrepairable_section_entries(
    sections: List[Dict[str, Any]], second_error: ValidationError
) -> List[Dict[str, Any]]:
    """Entfernt nach fehlgeschlagener Erst-Reparatur verbleibende fehlerhafte Einträge."""
    indices_to_remove: Dict[tuple[int, str], set[int]] = {}
    removed_entries: List[Dict[str, Any]] = []
    for err in second_error.errors():
        target = _extract_droppable_section_index(err, sections)
        if target is None:
            continue
        si, kind, idx = target
        key = (si, kind)
        if idx in indices_to_remove.get(key, set()):
            continue
        indices_to_remove.setdefault(key, set()).add(idx)
        entries = sections[si].get(kind) or []
        entry = entries[idx]
        entry_id = (
            str(entry.get("claim_id") or entry.get("hypothesis_id") or "")
            if isinstance(entry, dict)
            else ""
        )
        removed_entries.append(
            {
                "section_index": sections[si].get("section_index", 0),
                "claim_id": entry_id,
                "violation": str(err.get("type") or "unknown"),
                "action": "dropped",
                "detail": str(err.get("msg") or "")[:500],
            }
        )
    for (si, kind), indices in indices_to_remove.items():
        entries = sections[si].get(kind)
        if isinstance(entries, list):
            for i in sorted(indices, reverse=True):
                del entries[i]
    return removed_entries


_drop_unrepairable_section_entries = drop_unrepairable_section_entries

