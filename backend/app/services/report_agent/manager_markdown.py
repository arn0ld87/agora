"""Markdown-Rendering, Bereinigung und Assemblierung für ReportManager (Issue #1864)."""

from __future__ import annotations

import re
from typing import Any, List, Optional

from pydantic import ValidationError

from ...contracts.report_v3 import ReportV3
from ...models.report import ReportOutline
from ...utils.logger import get_logger
from .markdown_renderer import render_report_v3
from .sections import (
    mark_hypotheses_in_content,
    render_confidence_markers_for_section,
    render_data_gaps_for_section,
    render_hypotheses_for_section,
)

logger = get_logger("agora.report_agent")

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
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


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


def build_report_v3_markdown(cls: Any, report_id: str) -> Optional[str]:
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


def prepare_content_for_evidence(cls: Any, content: str) -> str:
    """Bereitet Abschnittsinhalt für die Claim-Extraktion auf (#1316)."""
    return _render_simulated_quote_blocks(content or "")


def _strip_leading_blanks_and_separators(lines: List[str]) -> List[str]:
    while lines and lines[0].strip() == "":
        lines.pop(0)
    while lines and lines[0].strip() in ["---", "***", "___"]:
        lines.pop(0)
        while lines and lines[0].strip() == "":
            lines.pop(0)
    return lines


def clean_section_content(cls: Any, content: str, section_title: str) -> str:
    """Bereinigt Abschnittsinhalt vor der Persistenz (Slice P3.3, ADR-0004)."""
    if not content:
        return content

    content = _render_simulated_quote_blocks(content).strip()
    lines = content.split("\n")
    cleaned_lines: List[str] = []
    skip_next_empty = False
    norm_section_title = section_title.replace(" ", "")

    for i, line in enumerate(lines):
        stripped = line.strip()
        heading_match = _HEADING_RE.match(stripped)

        if heading_match:
            title_text = heading_match.group(2).strip()
            if i < 5 and (
                title_text == section_title
                or title_text.replace(" ", "") == norm_section_title
            ):
                skip_next_empty = True
                continue
            cleaned_lines.append(f"**{title_text}**")
            cleaned_lines.append("")
            continue

        if skip_next_empty and stripped == "":
            skip_next_empty = False
            continue

        skip_next_empty = False
        cleaned_lines.append(line)

    cleaned_lines = _strip_leading_blanks_and_separators(cleaned_lines)
    return "\n".join(cleaned_lines)


def assemble_full_report(cls: Any, report_id: str, outline: ReportOutline) -> str:
    """Assembliert den vollständigen Markdown-Report aus den gespeicherten Sektionen."""
    md_content = f"# {outline.title}\n\n"
    md_content += f"> {outline.summary}\n\n"
    md_content += "---\n\n"

    sections = cls.get_generated_sections(report_id)
    evidence_sections = {
        int(section.get("section_index", 0)): section
        for section in (cls.get_evidence_map(report_id) or {}).get("sections", [])
        if section.get("section_index") is not None
    }
    audit_appendix: list[str] = []
    for section_info in sections:
        evidence_section = evidence_sections.get(
            int(section_info.get("section_index", 0))
        )
        md_content += mark_hypotheses_in_content(
            section_info["content"], evidence_section
        )
        hypotheses = render_hypotheses_for_section(evidence_section)
        data_gaps = render_data_gaps_for_section(evidence_section)
        confidence_markers = render_confidence_markers_for_section(evidence_section)
        annotations = [
            item for item in (hypotheses, data_gaps, confidence_markers) if item
        ]
        if annotations:
            title = str((evidence_section or {}).get("section_title") or "").strip()
            index = section_info.get("section_index")
            heading = f"**{title}**" if title else f"**Abschnitt {index}**"
            audit_appendix.append(
                "\n\n".join(part for part in (heading, *annotations) if part)
            )

    md_content = cls._post_process_report(md_content, outline)

    if audit_appendix:
        md_content = (
            md_content.rstrip()
            + "\n\n---\n\n## Anhang: Belegprüfung\n\n"
            + "\n\n".join(audit_appendix)
            + "\n"
        )

    logger.info(
        "Markdown-String assembliert (wird in meta.json persistiert, keine separate .md-Datei): %s",
        report_id,
    )
    return md_content


def _is_duplicate_heading(processed_lines: List[str], title: str) -> bool:
    for j in range(max(0, len(processed_lines) - 5), len(processed_lines)):
        prev_match = _HEADING_RE.match(processed_lines[j].strip())
        if prev_match and prev_match.group(2).strip() == title:
            return True
    return False


_ALLOWED_LEVEL3_TITLES = frozenset({
    "Hypothesen ohne Evidence",
    "Datenlücken dieses Abschnitts",
})


def _format_heading_line(
    line: str,
    level: int,
    title: str,
    outline_title: str,
    section_titles: set[str],
) -> tuple[List[str], bool]:
    if level == 1:
        if title == outline_title:
            return [line], True
        if title in section_titles:
            return [f"## {title}"], True
        return [f"**{title}**", ""], False
    if level == 2:
        if title in section_titles or title == outline_title:
            return [line], True
        return [f"**{title}**", ""], False
    if level == 3 and title in _ALLOWED_LEVEL3_TITLES:
        return [line], True
    return [f"**{title}**", ""], False


def _collapse_empty_lines(processed_lines: List[str]) -> List[str]:
    result_lines: List[str] = []
    empty_count = 0
    for line in processed_lines:
        if line.strip() == "":
            empty_count += 1
            if empty_count <= 2:
                result_lines.append(line)
        else:
            empty_count = 0
            result_lines.append(line)
    return result_lines


def post_process_report(cls: Any, content: str, outline: ReportOutline) -> str:
    """Nachbereitung der Überschriften, Trennlinien und Leerzeilen im Gesamtbericht."""
    lines = content.split("\n")
    processed_lines: List[str] = []
    prev_was_heading = False
    section_titles = {section.title for section in outline.sections}

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        heading_match = _HEADING_RE.match(stripped)

        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if _is_duplicate_heading(processed_lines, title):
                i += 1
                while i < len(lines) and lines[i].strip() == "":
                    i += 1
                continue
            emitted, prev_was_heading = _format_heading_line(
                line, level, title, outline.title, section_titles
            )
            processed_lines.extend(emitted)
            i += 1
            continue

        if stripped == "---" and prev_was_heading:
            i += 1
            continue

        if stripped == "" and prev_was_heading:
            if processed_lines and processed_lines[-1].strip() != "":
                processed_lines.append(line)
            prev_was_heading = False
        else:
            processed_lines.append(line)
            prev_was_heading = False

        i += 1

    return "\n".join(_collapse_empty_lines(processed_lines))
