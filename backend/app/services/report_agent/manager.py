from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import ValidationError

from ...contracts.report_v3 import CLAIM_MIN_EVIDENCE_FOR_CLAIM, DEFAULT_REPORT_MODE, ReportMode, ReportV3
from ...contracts.report_v3 import Claim as ReportV3Claim
from ...contracts.report_v3 import DataGap as ReportV3DataGap
from ...contracts.report_v3 import Hypothesis as ReportV3Hypothesis
from ...config import Config
from ...models.report import Report, ReportOutline, ReportSection, ReportStatus
from ...utils.logger import get_logger
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
    render_confidence_markers_for_section,
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
        GetCompleteconsolelog（one-timeGetall）
        
        Args:
            report_id: ReportID
            
        Returns:
            logrowlist
        """
        result = cls.get_console_log(report_id, from_line=0)
        return result["logs"]
    
    @classmethod
    def get_agent_log(cls, report_id: str, from_line: int = 0) -> Dict[str, Any]:
        return read_agent_log(cls.REPORTS_DIR, report_id, from_line)

    @classmethod
    def get_agent_log_stream(cls, report_id: str) -> List[Dict[str, Any]]:
        """
        GetComplete Agent log（for one-timeGetall）
        
        Args:
            report_id: ReportID
            
        Returns:
            logentrylist
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
        except Exception as exc:
            logger.error("Unexpected error rendering report-v3 for %s: %s", report_id, exc)
            return None

    @classmethod
    def _evidence_ref_for_item(
        cls,
        item: Dict[str, Any],
        *,
        section_index: int,
        claim_id: str,
        item_index: int,
    ) -> str:
        ref = str(
            item.get("source_id_anchor")
            or item.get("anchor")
            or item.get("source")
            or f"section_{section_index}:{claim_id}:evidence_{item_index:02d}"
        )
        return ref.strip() or f"section_{section_index}:{claim_id}:evidence_{item_index:02d}"

    @classmethod
    def build_report_v3(
        cls,
        report: Report,
        evidence_map: Dict[str, Any],
        *,
        report_mode: ReportMode = DEFAULT_REPORT_MODE,
    ) -> ReportV3:
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
                evidence_refs = [
                    cls._evidence_ref_for_item(
                        item,
                        section_index=section_index,
                        claim_id=claim_id,
                        item_index=index,
                    )
                    for index, item in enumerate(claim.get("evidence") or [], 1)
                    if isinstance(item, dict)
                ]
                # balanced/explorative: Claims ohne Evidence → überspringen (kein Evidence-Anker)
                # strict: Claims ohne Evidence → gedroppt (gleiche Logik, aber auch low-conf)
                if not evidence_refs:
                    continue
                # Reviewer-Floor (report_4fe2dacd80ba, Sub-Slice S1):
                # Claim braucht ≥2 Evidence-Items, sonst Routing zur Hypothesis.
                if len(evidence_refs) < CLAIM_MIN_EVIDENCE_FOR_CLAIM:
                    h_index = len(hypotheses) + 1
                    h_text = str(claim.get("claim_text") or claim.get("claim") or "").strip()
                    if h_text:
                        hypotheses.append(ReportV3Hypothesis(
                            id=f"hypothesis_{h_index:02d}",
                            hypothesis_text=h_text,
                            rationale=(
                                f"Reviewer-Floor: nur {len(evidence_refs)} Evidence-Item(s) — "
                                "Claim-Floor ist 2."
                            ),
                        ))
                    continue
                statement = str(claim.get("claim_text") or claim.get("claim") or "").strip()
                if len(statement) < 8:
                    continue
                label = str(claim.get("confidence_label") or "low")
                confidence: Literal["low", "medium", "high"]
                confidence = "high" if label in {"high", "verified"} else "low"
                if label == "medium":
                    confidence = "medium"
                if confidence not in {"low", "medium", "high"}:
                    confidence = "low"
                # strict: Low-confidence Claims werden gedroppt
                if report_mode == "strict" and confidence == "low":
                    continue
                claims.append(ReportV3Claim(
                    id=claim_id,
                    statement=statement,
                    evidence_refs=evidence_refs,
                    confidence=confidence,
                    aggregation_basis="persona",
                ))
            for gap in section.get("data_gaps") or []:
                if not isinstance(gap, dict):
                    continue
                gap_id = str(gap.get("gap_id") or f"gap_{len(data_gaps) + 1:02d}")
                claim_text = str(gap.get("claim_text") or gap.get("gap_reason") or "")
                reason = str(gap.get("gap_reason") or "").strip()
                description = claim_text if not reason else f"{claim_text} ({reason})"
                description = description.strip() or "Datenluecke ohne Claim-Text."
                suggested_fix = gap.get("suggested_fix")
                data_gaps.append(ReportV3DataGap(
                    id=gap_id,
                    beschreibung=description,
                    severity="medium",
                    suggested_fixes=[str(suggested_fix)] if suggested_fix else [],
                ))
            for hypothesis in section.get("hypotheses") or []:
                if not isinstance(hypothesis, dict):
                    continue
                hypothesis_id = str(
                    hypothesis.get("hypothesis_id")
                    or f"hypothesis_{len(hypotheses) + 1:02d}"
                )
                text = str(hypothesis.get("hypothesis_text") or "").strip()
                if not text:
                    continue
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
        return ReportV3(
            report_id=report.report_id,
            generated_at=datetime.now(timezone.utc),
            report_mode=report_mode,
            claims=claims,
            data_gaps=data_gaps,
            hypotheses=hypotheses,
        )
    
    @classmethod
    def save_outline(cls, report_id: str, outline: ReportOutline) -> None:
        cls._ensure_report_folder(report_id)
        write_outline(cls._get_outline_path(report_id), outline.to_dict())
        logger.info(f"outlinesaved: {report_id}")

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
        logger.info(f"Sectionsaved: {report_id}/{file_suffix}")
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
                
                # Checkwhether isandSection Titleduplicatetitle（skip first5rowwithinduplicate）
                if i < 5:
                    if title_text == section_title or title_text.replace(' ', '') == section_title.replace(' ', ''):
                        skip_next_empty = True
                        continue
                
                # convertallleveltitle（#, ##, ###, ####etc）convert tobold
                # becauseSection Titleadded by system，contentshould not have anytitle
                cleaned_lines.append(f"**{title_text}**")
                cleaned_lines.append("")  # addempty line
                continue
            
            # if previousrowwas skippedtitle，and currentrowempty，also skip
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
        assembleComplete report
        
        fromsaveSectionfileassembleComplete report，and processrowtitleclean
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
            md_content += section_info["content"]
            evidence_section = evidence_sections.get(int(section_info.get("section_index", 0)))
            hypotheses = render_hypotheses_for_section(evidence_section)
            confidence_markers = render_confidence_markers_for_section(
                evidence_section
            )
            annotations = [item for item in (hypotheses, confidence_markers) if item]
            if annotations:
                md_content = md_content.rstrip() + "\n\n" + "\n\n".join(annotations) + "\n\n"
        
        # post-processing：clean entireReporttitlequestion
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
        2. keepReportmain title(#)andSection Title(##)，removeother levelstitle(###, ####etc)
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
                
                # Checkwhether isduplicatetitle（inconsecutive5rowappear the same withincontenttitle）
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
                
                # titlelevel handling：
                # - # (level=1) onlykeepReportmain title
                # - ## (level=2) keepSection Title
                # - ### and below (level>=3) convert toboldtext
                
                if level == 1:
                    if title == outline.title:
                        # keepReportmain title
                        processed_lines.append(line)
                        prev_was_heading = True
                    elif title in section_titles:
                        # Section Titleerrorusing#，corrected to##
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
                elif level == 3 and title == "Hypothesen ohne Evidence":
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
        
        # cleanconsecutivemultipleempty line（keepat most2)
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
        if report.status == ReportStatus.COMPLETED and evidence_map:
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
            # backward compatibleformat：Checkdirectlystored inreportsunder directoryfile
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
        
        # ifmarkdown_contentempty，attempt tofromfull_report.mdRead
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
        )
    
    @classmethod
    def get_report_by_simulation(cls, simulation_id: str) -> Optional[Report]:
        """based onsimulationIDgetreport"""
        cls._ensure_reports_dir()
        
        for item in os.listdir(cls.REPORTS_DIR):
            item_path = os.path.join(cls.REPORTS_DIR, item)
            # newformat：filefolder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report and report.simulation_id == simulation_id:
                    return report
            # backward compatibleformat：JSONfile
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
            # newformat：filefolder
            if os.path.isdir(item_path):
                report = cls.get_report(item)
                if report:
                    if simulation_id is None or report.simulation_id == simulation_id:
                        reports.append(report)
            # backward compatibleformat：JSONfile
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
        """Deletereport（entirefolder）"""
        import shutil
        
        folder_path = cls._get_report_folder(report_id)
        
        # newformat：Deleteentirefilefolder
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            shutil.rmtree(folder_path)
            logger.info(f"reportfolderhasDelete: {report_id}")
            return True
        
        # backward compatibleformat：Deleteseparatefile
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
