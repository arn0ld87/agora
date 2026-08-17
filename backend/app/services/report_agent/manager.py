from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import ValidationError

from ...contracts.report_v3 import DEFAULT_REPORT_MODE, ReportMode, ReportV3
from ...contracts.report_v3 import Claim as ReportV3Claim
from ...contracts.report_v3 import DataGap as ReportV3DataGap
from ...contracts.report_v3 import Hypothesis as ReportV3Hypothesis
from .metadata_merge import merge_section_metadata
from ...config import Config
from ...models.report import Report, ReportOutline, ReportSection, ReportStatus
from ...utils.logger import get_logger
from ..evidence_migrations import normalize_persisted_evidence_map
from .evidence import text_confidence_label_of
from .storage import (
    ensure_report_folder,
    ensure_reports_dir,
    get_agent_log_path,
    get_console_log_path,
    get_evidence_map_path,
    get_generated_sections as storage_get_generated_sections,
    get_outline_path,
    get_progress_path,
    get_report_folder,
    get_report_markdown_path,
    get_report_path,
    get_report_v3_path,
    get_report_v3_markdown_path,
    get_section_path,
    read_agent_log,
    read_console_log,
    read_json_safe,
    write_json_atomic,
    write_outline,
    write_section_markdown,
)
from .markdown_renderer import render_report_v3
from .sections import (
    mark_hypotheses_in_content,
    render_confidence_markers_for_section,
    render_data_gaps_for_section,
    render_hypotheses_for_section,
)

logger = get_logger('agora.report_agent')


# ---------------------------------------------------------------------------
# Slice P3.3 — Quote-Marker-Render
# ---------------------------------------------------------------------------
#
# Wandelt rohe `<simulated_quote persona_id="..." seed_anchor="...">…</simulated_quote>`
# Tags vor der Section-Persistenz in lesbare Markdown-Blockquotes mit explizit
# sichtbarem Persona- und Seed-Anker-Header. Damit ist im exportierten Markdown
# ohne UI-Render erkennbar, dass es sich um simulierte Persona-O-Töne handelt
# (Anti-Halluzinations-Disziplin, ADR-0004).
_SIMULATED_QUOTE_TAG_RE = re.compile(
    r"<simulated_quote(?:\s+([^>]*?))?>(.*?)</simulated_quote>",
    re.DOTALL,
)
_SIMULATED_QUOTE_ATTR_RE = re.compile(r'(\w+)\s*=\s*["\']([^"\']*)["\']')


def _render_simulated_quote_blocks(content: str) -> str:
    """Ersetzt <simulated_quote>-Tags durch Markdown-Blockquotes mit Anker-Header."""

    def _replace(match: "re.Match[str]") -> str:
        attrs = dict(_SIMULATED_QUOTE_ATTR_RE.findall(match.group(1) or ""))
        text = match.group(2).strip()
        persona_id = attrs.get("persona_id", "unbekannt")
        seed_anchor = attrs.get("seed_anchor", "unbekannt")
        header = (
            f"> **Simulierter Persona-O-Ton** "
            f"(persona_id: {persona_id}, seed_anchor: {seed_anchor})"
        )
        body_lines = [f"> {line}" if line else ">" for line in text.split("\n")]
        return "\n\n" + "\n".join([header, *body_lines]) + "\n\n"

    return _SIMULATED_QUOTE_TAG_RE.sub(_replace, content)


# ---------------------------------------------------------------------------
# Issue #1160 A — Geltungsbereich der Confidence ableiten
# ---------------------------------------------------------------------------

# Quellengattungen, die den Claim an etwas ausserhalb der Simulation binden.
# ``agent_quote`` und ``agent_action`` fehlen hier bewusst: beides sind
# Aeusserungen bzw. Handlungen simulierter Agenten. Ein Claim, den nur sie
# stuetzen, ist Simulationskonsens — unabhaengig davon, wie hoch sein Label
# ausfaellt.
_EVIDENCE_BOUND_SOURCE_KINDS = frozenset({"seed_corpus", "graph_relation", "web_source"})


def _text_confidence_for(
    claim: dict[str, Any], current: str
) -> "Literal['speculative', 'low', 'medium', 'high', 'verified'] | None":
    """Die Stufe, unter der der Wortlaut entstand — oder ``None`` (#1012).

    ``None`` ist der Normalfall: der Wortlaut passt zum Label. Stimmt die
    protokollierte Ausgangsstufe mit dem aktuellen Label ueberein, wurde
    faktisch nichts abgestuft — dann ebenfalls ``None``, statt eine Abstufung
    auszuweisen, die keine ist.
    """
    recorded = text_confidence_label_of(claim)
    if not recorded or recorded == current:
        return None
    if recorded not in {"speculative", "low", "medium", "high", "verified"}:
        return None
    return recorded  # type: ignore[return-value]


def _derive_confidence_scope(
    evidence: Any,
) -> Literal["simulation_consensus", "evidence", "empirical"]:
    """Leitet den Geltungsbereich aus den stuetzenden Evidence-Items ab.

    Gezaehlt wird nur ``supports_claim is True`` — dieselbe Menge, aus der
    ``evidence_refs`` entsteht. Widersprechende oder nur thematisch verwandte
    Items begruenden keine Quellenbindung.

    ``empirical`` wird hier nie vergeben: der Wert bezeichnet reale empirische
    Daten, die Agora nicht erhebt. Die Ableitung kennt daher nur die beiden
    Faelle, die im Lauf tatsaechlich vorkommen.
    """
    if not isinstance(evidence, list):
        return "simulation_consensus"
    for item in evidence:
        if not isinstance(item, dict) or item.get("supports_claim") is not True:
            continue
        if str(item.get("source_kind") or "") in _EVIDENCE_BOUND_SOURCE_KINDS:
            return "evidence"
    return "simulation_consensus"


class ReportManager:
    """Persistence and retrieval facade for generated reports."""
    
    # Reportstorage directory
    REPORTS_DIR = os.path.join(Config.UPLOAD_FOLDER, 'reports')
    
    @classmethod
    def _ensure_reports_dir(cls):
        """ensurereportroot directory exists"""
        ensure_reports_dir(cls.REPORTS_DIR)
    
    @classmethod
    def _get_report_folder(cls, report_id: str) -> str:
        """getreportfolderpath"""
        return get_report_folder(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _ensure_report_folder(cls, report_id: str) -> str:
        """ensurereportfolderexists andreturnedpath"""
        return ensure_report_folder(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _get_report_path(cls, report_id: str) -> str:
        """getreportmetainformationfile path"""
        return get_report_path(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _get_report_markdown_path(cls, report_id: str) -> str:
        """getcompletereportMarkdownfile path"""
        return get_report_markdown_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_report_v3_path(cls, report_id: str) -> str:
        """getstructuredReportV3file path"""
        return get_report_v3_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_report_v3_markdown_path(cls, report_id: str) -> str:
        """getstructuredReportV3Markdownfile path"""
        return get_report_v3_markdown_path(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _get_outline_path(cls, report_id: str) -> str:
        """getoutlinefile path"""
        return get_outline_path(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _get_progress_path(cls, report_id: str) -> str:
        """getprogressfile path"""
        return get_progress_path(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _get_section_path(cls, report_id: str, section_index: int) -> str:
        """getSectionMarkdownfile path"""
        return get_section_path(cls.REPORTS_DIR, report_id, section_index)
    
    @classmethod
    def _get_agent_log_path(cls, report_id: str) -> str:
        """get Agent logsfile path"""
        return get_agent_log_path(cls.REPORTS_DIR, report_id)
    
    @classmethod
    def _get_console_log_path(cls, report_id: str) -> str:
        """getconsolelogsfile path"""
        return get_console_log_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _get_evidence_map_path(cls, report_id: str) -> str:
        """Get evidence map path"""
        return get_evidence_map_path(cls.REPORTS_DIR, report_id)

    @classmethod
    def _write_json_atomic(cls, path: str, payload: Dict[str, Any]) -> None:
        """Write JSON atomically so polling never sees a half-written file."""
        write_json_atomic(path, payload)

    @classmethod
    def _read_json_safe(cls, path: str) -> Optional[Dict[str, Any]]:
        """Read JSON defensively; return None for empty/truncated files during polling."""
        return read_json_safe(path, logger)
    
    @classmethod
    def get_console_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        return read_console_log(cls.REPORTS_DIR, report_id, from_line)

    @classmethod
    def get_console_log_stream(cls, report_id: str) -> List[str]:
        """
        Get the complete console log (fetch all lines at once).

        Args:
            report_id: report ID

        Returns:
            list of log lines
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        return read_agent_log(cls.REPORTS_DIR, report_id, from_line)

    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        Get the complete agent log (fetch all entries at once).

        Args:
            report_id: report ID

        Returns:
            list of log entries
        """
        result = cls.get_agent_log(report_id, from_line=0)
        return result["logs"]

    @classmethod
    def save_evidence_map(cls, report_id: str, evidence_map: Dict[str, Any]) -> None:
        cls._ensure_report_folder(report_id)
        cls._write_json_atomic(cls._get_evidence_map_path(report_id), evidence_map)

    @classmethod
    def get_evidence_map(cls, report_id: str) -> Optional[Dict[str, Any]]:
        return cls._read_json_safe(cls._get_evidence_map_path(report_id))

    @classmethod
    def save_report_v3(cls, report_v3: ReportV3) -> None:
        cls._ensure_report_folder(report_v3.report_id)
        cls._write_json_atomic(
            cls._get_report_v3_path(report_v3.report_id),
            report_v3.model_dump(mode="json"),
        )
        # MAI-06: Kein .md-Write mehr — Markdown wird on-demand via build_report_v3_markdown() gerendert.

    @classmethod
    def get_report_v3(cls, report_id: str) -> Optional[Dict[str, Any]]:
        return cls._read_json_safe(cls._get_report_v3_path(report_id))

    @classmethod
    def build_report_v3_markdown(cls, report_id: str) -> Optional[str]:
        """MAI-06: On-demand-Render des v3-Markdowns aus report-v3.json.

        Ersetzt den stummen full_report.md-Write. Liefert None wenn kein
        report-v3.json vorhanden (Bestandsreport ohne v3-Artefakt).
        """
        raw = cls.get_report_v3(report_id)
        if raw is None:
            return None
        try:
            v3 = ReportV3.model_validate(raw)
            return render_report_v3(v3)
        except ValidationError as exc:
            logger.warning("report-v3.json validation failed for %s: %s", report_id, exc)
            return None
        except Exception as exc:  # noqa: BLE001 — exception is logged; swallowed intentionally
            logger.error("Unexpected error rendering report-v3 for %s: %s", report_id, exc)
            return None

    @classmethod
    def build_report_v3(
        cls,
        report: Report,
        evidence_map: Dict[str, Any],
        *,
        report_mode: ReportMode = DEFAULT_REPORT_MODE,
    ) -> ReportV3:
        evidence_map = normalize_persisted_evidence_map(evidence_map) or evidence_map
        claims: List[ReportV3Claim] = []
        data_gaps: List[ReportV3DataGap] = []
        hypotheses: List[ReportV3Hypothesis] = []
        for section in evidence_map.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_index = int(section.get("section_index") or 0)
            for claim in section.get("claims") or []:
                if not isinstance(claim, dict):
                    continue
                claim_id = str(claim.get("claim_id") or f"claim_{len(claims) + 1:02d}")
                evidence_refs = list(dict.fromkeys(
                    str(item.get("evidence_id"))
                    for item in claim.get("evidence") or []
                    if isinstance(item, dict)
                    and item.get("evidence_id")
                    and item.get("supports_claim") is True
                ))
                # balanced/explorative: Claims ohne Evidence → überspringen (kein Evidence-Anker)
                # strict: Claims ohne Evidence → gedroppt (gleiche Logik, aber auch low-conf)
                if not evidence_refs:
                    continue
                statement = str(claim.get("claim_text") or claim.get("claim") or "").strip()
                if len(statement) < 8:
                    continue
                label = str(claim.get("confidence_label") or "speculative")
                _valid_confidence = {"speculative", "low", "medium", "high", "verified"}
                confidence: Literal["speculative", "low", "medium", "high", "verified"]
                if label in _valid_confidence:
                    confidence = label  # type: ignore[assignment]
                elif label in {"high", "verified"}:
                    confidence = "high"
                elif label == "medium":
                    confidence = "medium"
                elif label == "low":
                    confidence = "low"
                else:
                    confidence = "speculative"
                single_source_text_confidence: Literal[
                    "speculative", "low", "medium", "high", "verified"
                ] | None = None
                if len(evidence_refs) == 1 and confidence in {"medium", "high", "verified"}:
                    single_source_text_confidence = confidence
                    confidence = "low"
                # strict: speculative/low-confidence Claims werden gedroppt
                if report_mode == "strict" and confidence in {"speculative", "low"}:
                    continue
                claims.append(ReportV3Claim(
                    id=claim_id,
                    statement=statement,
                    evidence_refs=evidence_refs,
                    confidence=confidence,
                    aggregation_basis="persona",
                    confidence_scope=_derive_confidence_scope(claim.get("evidence")),
                    # Issue #1012: nur gesetzt, wenn der Claim nachtraeglich
                    # abgestuft wurde. Der Wortlaut stammt dann aus einer
                    # hoeheren Stufe und deckt mehr Sicherheit ab als das
                    # Label — ohne dass irgendetwas am Text geaendert wird.
                    text_confidence=(
                        _text_confidence_for(claim, confidence)
                        or single_source_text_confidence
                    ),
                ))
            # Slice 3 (Issue #495): stable Re-ID after Dedup.
            # visible hypotheses get IDs H{section_idx}_{i:02d} (1-based),
            # appendix hypotheses get IDs HA{section_idx}_{i:02d} (1-based).
            _hypothesis_slots: list[tuple[str, list[dict[str, Any]]]] = [
                ("H", list(section.get("hypotheses") or [])),
                ("HA", list(section.get("hypotheses_appendix") or [])),
            ]
            # Issue #1319: Die Datenlücke verweist auf die abschnittsinterne
            # Rohform (``hypothesis_01``); exportiert wird die Hypothese unter
            # ``H<n>_<i>``. Ohne diese Abbildung zeigt der Verweis auf eine ID,
            # die in der Hypothesentabelle nicht vorkommt. Dazwischen liegen
            # ausserdem Dedup und Appendix-Cap: eine Hypothese kann ganz
            # verschwinden. Was die Abbildung nicht kennt, hat kein Ziel — der
            # Verweis entfaellt dann, statt ins Leere zu zeigen.
            hypothesis_export_ids: dict[str, str] = {}
            for _id_prefix, _slot in _hypothesis_slots:
                for _h_slot_idx, _hypothesis in enumerate(_slot, start=1):
                    if not isinstance(_hypothesis, dict):
                        continue
                    if not str(_hypothesis.get("hypothesis_text") or "").strip():
                        continue
                    _raw_id = str(_hypothesis.get("hypothesis_id") or "").strip()
                    if _raw_id:
                        hypothesis_export_ids[_raw_id] = (
                            f"{_id_prefix}{section_index}_{_h_slot_idx:02d}"
                        )
            for gap in section.get("data_gaps") or []:
                if not isinstance(gap, dict):
                    continue
                gap_id = str(gap.get("gap_id") or f"gap_{len(data_gaps) + 1:02d}")
                claim_text = str(gap.get("claim_text") or gap.get("gap_reason") or "")
                reason = str(gap.get("gap_reason") or "").strip()
                description = claim_text if not reason else f"{claim_text} ({reason})"
                description = description.strip() or "Datenluecke ohne Claim-Text."
                # Issue #1319: Hypothese und Datenluecke tragen denselben
                # Claim-Text — sie entstehen im selben Zweig. Der Verweis macht
                # aus der stummen Doppelung eine erkennbare Beziehung, statt
                # den Leser zweimal dasselbe lesen zu lassen ohne zu sagen,
                # dass es dasselbe ist.
                hypothesis_ref = hypothesis_export_ids.get(
                    str(gap.get("hypothesis_id") or "").strip()
                )
                suggested_fix = gap.get("suggested_fix")
                # Issue #1319: severity war hartkodiert "medium" — unabhaengig
                # davon, ob ueberhaupt keine Quelle gebunden ist (schwerer) oder
                # nur eine thematisch verwandte ohne Aussagebezug (leichter).
                severity: Literal["low", "medium", "high"] = (
                    "high" if reason == "no_evidence_bound" else "medium"
                )
                data_gaps.append(ReportV3DataGap(
                    id=gap_id,
                    beschreibung=description,
                    severity=severity,
                    suggested_fixes=[str(suggested_fix)] if suggested_fix else [],
                    related_hypothesis_id=hypothesis_ref,
                ))
            for _id_prefix, _slot in _hypothesis_slots:
                for _h_slot_idx, hypothesis in enumerate(_slot, start=1):
                    if not isinstance(hypothesis, dict):
                        continue
                    text = str(hypothesis.get("hypothesis_text") or "").strip()
                    if not text:
                        continue
                    # Stable Re-ID: section-scoped, prefix separates visible from appendix
                    hypothesis_id = f"{_id_prefix}{section_index}_{_h_slot_idx:02d}"
                    origin_section_index = hypothesis.get(
                        "origin_section_index", section_index
                    )
                    try:
                        origin_index = (
                            int(origin_section_index)
                            if origin_section_index is not None
                            else None
                        )
                    except (TypeError, ValueError):
                        origin_index = None
                    try:
                        confidence_score = float(
                            hypothesis.get("confidence_score") or 0.0
                        )
                    except (TypeError, ValueError):
                        confidence_score = 0.0
                    hypotheses.append(ReportV3Hypothesis(
                        id=hypothesis_id,
                        hypothesis_text=text,
                        rationale=str(hypothesis.get("rationale") or ""),
                        suggested_evidence=[
                            str(item)
                            for item in (hypothesis.get("suggested_evidence") or [])
                            if str(item).strip()
                        ],
                        origin_section_index=origin_index,
                        confidence_score=max(0.0, min(1.0, confidence_score)),
                    ))
        # P0-6: Die pro Abschnitt extrahierten Struktur-Daten sind die
        # kanonische Quelle für Personas, Segmente, Reibungspunkte usw.
        # Ohne diesen Schritt blieb ReportV3 leer, während der Prosa-Report
        # dieselben Inhalte anzeigte ("Keine Personas im ReportV3-Artefakt").
        merged = merge_section_metadata(evidence_map.get("sections") or [])
        if merged.rejected:
            logger.warning(
                "build_report_v3: %d Metadaten-Eintrag/Einträge verworfen: %s",
                len(merged.rejected),
                "; ".join(merged.rejected[:5]),
            )
        evidence_index = dict(evidence_map.get("evidence_index") or {})
        metadata_kwargs = merged.as_report_v3_kwargs()
        for slot, items in list(metadata_kwargs.items()):
            metadata_kwargs[slot] = [
                item.model_copy(update={
                    "evidence_refs": [
                        ref for ref in item.evidence_refs if ref in evidence_index
                    ]
                })
                if hasattr(item, "evidence_refs")
                else item
                for item in items
            ]
        return ReportV3(
            report_id=report.report_id,
            generated_at=datetime.now(timezone.utc),
            evidence_index=evidence_index,
            report_mode=report_mode,
            claims=claims,
            data_gaps=data_gaps,
            hypotheses=hypotheses,
            # Issue #1192: der Stand wandert unveraendert aus meta.json ins
            # v3-Artefakt, damit der Markdown-Export ihn ausweisen kann.
            simulation_snapshot=report.simulation_snapshot,
            **metadata_kwargs,
        )
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        cls._ensure_report_folder(report_id)
        write_outline(cls._get_outline_path(report_id), outline.to_dict())
        logger.info("Outline saved: %s", report_id)

    @classmethod
    def save_section(
        cls,
        report_id: str,
        section_index: int,
        section: ReportSection
    ) -> str:
        cls._ensure_report_folder(report_id)
        cleaned_content = cls._clean_section_content(section.content, section.title)
        file_suffix = f"section_{section_index:02d}.md"
        file_path = os.path.join(cls._get_report_folder(report_id), file_suffix)
        write_section_markdown(file_path, section.title, cleaned_content)
        logger.info("Section saved: %s/%s", report_id, file_suffix)
        return file_path

    @classmethod
    def _clean_section_content(cls, content: str, section_title: str) -> str:
        """
        cleanSectioncontent

        1. <simulated_quote>-Tags zu lesbaren Persona-O-Ton-Blockquotes rendern
           (Slice P3.3, ADR-0004 Quote-Marker)
        2. removecontentbeginningandSection TitleduplicateMarkdowntitlerow
        3. convertall ### and below levelstitleconvert toboldtext

        Args:
            content: originalcontent
            section_title: Section Title

        Returns:
            after cleaningcontent
        """
        import re

        if not content:
            return content

        content = _render_simulated_quote_blocks(content)

        content = content.strip()
        lines = content.split('\n')
        cleaned_lines = []
        skip_next_empty = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Checkwhether isMarkdowntitlerow
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                title_text = heading_match.group(2).strip()
                
                # Check whether this duplicates the section title (only within the first 5 lines)
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # convert headings of all levels (#, ##, ###, #### etc.) to bold
                # since the section title is added by the system, the content should not have its own heading
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # addempty line
                continue
            
            # if the previous line was a skipped heading and the current line is empty, skip it too
            if skip_next_empty and stripped == '':
                skip_next_empty = False
                continue
            
            skip_next_empty = False
            cleaned_lines.append(line)
        
        # removebeginningempty line
        while cleaned_lines and cleaned_lines[0].strip() == '':
            cleaned_lines.pop(0)
        
        # removebeginningseparatorline
        while cleaned_lines and cleaned_lines[0].strip() in ['---', '***', '___']:
            cleaned_lines.pop(0)
            # meanwhileremoveseparatorline afterempty line
            while cleaned_lines and cleaned_lines[0].strip() == '':
                cleaned_lines.pop(0)
        
        return '\n'.join(cleaned_lines)
    
    @classmethod
    def update_progress(
        cls, 
        report_id: str, 
        status: str, 
        progress: int, 
        message: str,
        current_section: str = None,
        completed_sections: List[str] = None
    ) -> None:
        """
        UpdateReportgenerateProgress
        
        frontend can getReadprogress.jsonGetrealtimeProgress
        """
        cls._ensure_report_folder(report_id)
        
        progress_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "current_section": current_section,
            "completed_sections": completed_sections or [],
            "updated_at": datetime.now().isoformat()
        }
        
        cls._write_json_atomic(cls._get_progress_path(report_id), progress_data)
    
    @classmethod
    def get_progress(cls, report_id: str) -> Optional[Dict[str, Any]]:
        """getreportgenerateprogress"""
        return cls._read_json_safe(cls._get_progress_path(report_id))
    
    @classmethod
    def get_generated_sections(cls, report_id: str) -> List[Dict[str, Any]]:
        return storage_get_generated_sections(cls.REPORTS_DIR, report_id)

    @classmethod
    def assemble_full_report(cls, report_id: str, outline: ReportOutline) -> str:
        """
        Assemble the complete report.

        Assembles the complete report from the saved section files and cleans up heading lines.
        """
        # BuildReportheader
        md_content = f"# {outline.title}\n\n"
        md_content += f"> {outline.summary}\n\n"
        md_content += "---\n\n"
        
        # sequentiallyReadallSectionfile
        sections = cls.get_generated_sections(report_id)
        evidence_sections = {
            int(section.get("section_index", 0)): section
            for section in (cls.get_evidence_map(report_id) or {}).get("sections", [])
            if section.get("section_index") is not None
        }
        for section_info in sections:
            evidence_section = evidence_sections.get(int(section_info.get("section_index", 0)))
            md_content += mark_hypotheses_in_content(
                section_info["content"], evidence_section
            )
            hypotheses = render_hypotheses_for_section(evidence_section)
            data_gaps = render_data_gaps_for_section(evidence_section)
            confidence_markers = render_confidence_markers_for_section(
                evidence_section
            )
            annotations = [
                item for item in (hypotheses, data_gaps, confidence_markers) if item
            ]
            if annotations:
                md_content = md_content.rstrip() + "\n\n" + "\n\n".join(annotations) + "\n\n"
        
        # post-processing: clean up heading issues in the entire report
        md_content = cls._post_process_report(md_content, outline)

        # MAI-06: Nicht mehr auf Disk schreiben — nur zurückgeben.
        # Aufrufer ist save_report(), das setzt report.markdown_content.
        # Der Export-Endpoint rendert on-demand via build_report_v3_markdown().
        logger.info(f"Markdown-String assembliert (wird in meta.json persistiert, keine separate .md-Datei): {report_id}")
        return md_content
    
    @classmethod
    def _post_process_report(cls, content: str, outline: ReportOutline) -> str:
        """
        post-processingReportcontent
        
        1. removeduplicatetitle
        2. keep the report main title (#) and section titles (##); remove headings of other levels (###, #### etc.)
        3. clean redundantempty lineandseparatorline
        
        Args:
            content: originalReportcontent
            outline: Reportoutline
            
        Returns:
            after processingcontent
        """
        import re
        
        lines = content.split('\n')
        processed_lines = []
        prev_was_heading = False
        
        # collectoutlineinallSection Title
        section_titles = set()
        for section in outline.sections:
            section_titles.add(section.title)
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Checkwhether istitlerow
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            
            if heading_match:
                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                
                # check whether this is a duplicate heading (same title appears again within the last 5 processed lines)
                is_duplicate = False
                for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
                    prev_line = processed_lines[j].strip()
                    prev_match = re.match(r'^(#{1,6})\s+(.+)$', prev_line)
                    if prev_match:
                        prev_title = prev_match.group(2).strip()
                        if prev_title == title:
                            is_duplicate = True
                            break
                
                if is_duplicate:
                    # skipduplicatetitleand subsequentempty line
                    i += 1
                    while i < len(lines) and lines[i].strip() == '':
                        i += 1
                    continue
                
                # heading level handling:
                # - # (level=1) onlykeepReportmain title
                # - ## (level=2) keepSection Title
                # - ### and below (level>=3) convert toboldtext
                
                if level == 1:
                    if title == outline.title:
                        # keepReportmain title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # section title incorrectly used #, corrected to ##
                        processed_lines.append(f"## {title}")
                        prev_was_heading = True
                    else:
                        # other first-leveltitleconvert tobold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 2:
                    if title in section_titles or title == outline.title:
                        # keepSection Title
                        processed_lines.append(line)
                        prev_was_heading = True
                    else:
                        # nonSectionsecond-leveltitleconvert tobold
                        processed_lines.append(f"**{title}**")
                        processed_lines.append("")
                        prev_was_heading = False
                elif level == 3 and title in {
                    "Hypothesen ohne Evidence",
                    "Datenlücken dieses Abschnitts",
                }:
                    processed_lines.append(line)
                    prev_was_heading = True
                else:
                    # ### and below levelstitleconvert toboldtext
                    processed_lines.append(f"**{title}**")
                    processed_lines.append("")
                    prev_was_heading = False
                
                i += 1
                continue
            
            elif stripped == '---' and prev_was_heading:
                # skiptitlefollowed immediately byseparatorline
                i += 1
                continue
            
            elif stripped == '' and prev_was_heading:
                # titleafter onlykeeponeempty line
                if processed_lines and processed_lines[-1].strip() != '':
                    processed_lines.append(line)
                prev_was_heading = False
            
            else:
                processed_lines.append(line)
                prev_was_heading = False
            
            i += 1
        
        # clean up consecutive multiple empty lines (keep at most 2)
        result_lines = []
        empty_count = 0
        for line in processed_lines:
            if line.strip() == '':
                empty_count += 1
                if empty_count <= 2:
                    result_lines.append(line)
            else:
                empty_count = 0
                result_lines.append(line)
        
        return '\n'.join(result_lines)
    
    @classmethod
    def save_report(
        cls,
        report: Report,
        *,
        report_mode: ReportMode = DEFAULT_REPORT_MODE,
    ) -> None:
        """SavereportmetainformationandcompleteReport"""
        cls._ensure_report_folder(report.report_id)

        evidence_map = cls.get_evidence_map(report.report_id)
        report.has_evidence = bool(evidence_map and evidence_map.get("sections"))
        report.evidence_sections = len((evidence_map or {}).get("sections", []))

        # savemetainformationJSON
        cls._write_json_atomic(cls._get_report_path(report.report_id), report.to_dict())

        # saveoutline
        if report.outline:
            cls.save_outline(report.report_id, report.outline)

        # MAI-06: Kein full_report.md-Write mehr.
        # markdown_content bleibt in meta.json (für Frontend-getReport()).
        # Der Markdown-Export läuft über export-Endpoint → build_report_v3_markdown().
        # Issue #1315: auch bei INCOMPLETE wird das v3-Artefakt geschrieben, sofern
        # build_report_v3 valide durchlaeuft — sonst faellt der Export auf die
        # annotierte Roh-Narrative zurueck (91x "Hypothese (unbelegt):" im
        # Fliesstext). Der Statuswert selbst bleibt unberuehrt (#1299-Gating).
        if report.status in (ReportStatus.COMPLETED, ReportStatus.INCOMPLETE) and evidence_map:
            try:
                cls.save_report_v3(cls.build_report_v3(report, evidence_map, report_mode=report_mode))
            except ValidationError as exc:
                logger.warning(f"report-v3 artifact skipped for {report.report_id}: {exc}")
        
        logger.info(f"report saved (meta + v3-json): {report.report_id}")
    
    @classmethod
    def get_report(cls, report_id: str) -> Optional[Report]:
        """getreport"""
        path = cls._get_report_path(report_id)
        
        if not os.path.exists(path):
            # backward-compatible format: check for files stored directly in the reports directory
            old_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
            if os.path.exists(old_path):
                path = old_path
            else:
                return None
        
        data = cls._read_json_safe(path)
        if not data:
            return None
        
        # rebuildReportobject
        outline_data = data.get('outline')
        if not outline_data:
            outline_data = cls._read_json_safe(cls._get_outline_path(report_id))

        outline = None
        if outline_data:
            sections = []
            for s in outline_data.get('sections', []):
                # Prefer stored description; fall back to content for legacy
                # entries that predate the description field.
                stored_desc = s.get('description') or s.get('content') or ""
                sections.append(ReportSection(
                    title=s['title'],
                    content=s.get('content', ''),
                    description=stored_desc if stored_desc.strip() else "—",
                ))
            outline = ReportOutline(
                title=outline_data['title'],
                summary=outline_data['summary'],
                sections=sections
            )
        
        # if markdown_content is empty, attempt to read it from full_report.md
        markdown_content = data.get('markdown_content', '')
        if not markdown_content:
            full_report_path = cls._get_report_markdown_path(report_id)
            if os.path.exists(full_report_path):
                with open(full_report_path, 'r', encoding='utf-8') as f:
                    markdown_content = f.read()
        evidence_map = cls.get_evidence_map(report_id)
        
        return Report(
            report_id=data['report_id'],
            simulation_id=data['simulation_id'],
            graph_id=data['graph_id'],
            simulation_requirement=data['simulation_requirement'],
            status=ReportStatus(data['status']),
            outline=outline,
            markdown_content=markdown_content,
            missing_sections=list(data.get('missing_sections') or []),
            created_at=data.get('created_at', ''),
            completed_at=data.get('completed_at', ''),
            error=data.get('error'),
            has_evidence=bool(data.get('has_evidence') or (evidence_map and evidence_map.get("sections"))),
            evidence_sections=int(
                data.get('evidence_sections', 0) or len((evidence_map or {}).get("sections", []))
            ),
            # Issue #1192: fehlt bei Reports, die vor der Einfuehrung
            # geschrieben wurden — dort bleibt der Stand unbekannt.
            simulation_snapshot=data.get('simulation_snapshot'),
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """based onsimulationIDgetreport"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # new format: report is a folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # Backward-compatible format: single JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report and report.simulation_id == simulation_id:
                    return report
        
        return None
    
    @classmethod
    def list_reports(cls, simulation_id: Optional[str] = None, limit: int = 50) -> List[Report]:
        """columnappearreport"""
        cls._ensure_reports_dir()
        
        reports = []
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # new format: report is a folder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # Backward-compatible format: single JSON file
            elif item.endswith('.json'):
                report_id = item[:-5]
                report = cls.get_report(report_id)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
        
        # sorted by creation time descending
        reports.sort(key=lambda r: r.created_at, reverse=True)
        
        return reports[:limit]
    
    @classmethod
    def delete_report(cls, report_id: str) -> bool:
        """Delete a report (the entire report folder)."""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # New format: delete the entire report folder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info("Report folder deleted: %s", report_id)
            return True
        
        # Backward-compatible format: delete the standalone JSON file
        deleted = False
        old_json_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.json")
        old_md_path = os.path.join(cls.REPORTS_DIR, f"{report_id}.md")
        
        if os.path.exists(old_json_path):
            os.remove(old_json_path)
            deleted = True
        if os.path.exists(old_md_path):
            os.remove(old_md_path)
            deleted = True
        
        return deleted
