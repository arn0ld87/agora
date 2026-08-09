from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ...contracts.report_v3 import ReportV3

_storage_logger = logging.getLogger("agora.report_agent.storage")


def ensure_reports_dir(reports_dir: str) -> None:
    os.makedirs(reports_dir, exist_ok=True)


def get_report_folder(reports_dir: str, report_id: str) -> str:
    return os.path.join(reports_dir, report_id)


def ensure_report_folder(reports_dir: str, report_id: str) -> str:
    folder = get_report_folder(reports_dir, report_id)
    os.makedirs(folder, exist_ok=True)
    return folder


def get_report_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "meta.json")


def get_report_markdown_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "full_report.md")


def get_report_v3_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "report-v3.json")


def get_report_v3_markdown_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "report-v3.md")


def get_outline_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "outline.json")


def get_progress_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "progress.json")


def get_section_path(reports_dir: str, report_id: str, section_index: int) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), f"section_{section_index:02d}.md")


def get_agent_log_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "agent_log.jsonl")


def get_console_log_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "console_log.txt")


def get_evidence_map_path(reports_dir: str, report_id: str) -> str:
    return os.path.join(get_report_folder(reports_dir, report_id), "evidence_map.json")


def write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix='.tmp-report-', suffix='.json', dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def read_json_safe(path: str, logger: Any) -> Optional[Dict[str, Any]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Skipping unreadable report JSON {path}: {exc}")
        return None


def read_console_log(reports_dir: str, report_id: str, from_line: int = 0) -> Dict[str, Any]:
    log_path = get_console_log_path(reports_dir, report_id)
    if not os.path.exists(log_path):
        return {"logs": [], "total_lines": 0, "from_line": 0, "has_more": False}

    logs: List[str] = []
    total_lines = 0
    with open(log_path, 'r', encoding='utf-8') as handle:
        for i, line in enumerate(handle):
            total_lines = i + 1
            if i >= from_line:
                logs.append(line.rstrip('\n\r'))
    return {"logs": logs, "total_lines": total_lines, "from_line": from_line, "has_more": False}


def read_agent_log(reports_dir: str, report_id: str, from_line: int = 0) -> Dict[str, Any]:
    log_path = get_agent_log_path(reports_dir, report_id)
    if not os.path.exists(log_path):
        return {"logs": [], "total_lines": 0, "from_line": 0, "has_more": False}

    logs: List[Dict[str, Any]] = []
    total_lines = 0
    with open(log_path, 'r', encoding='utf-8') as handle:
        for i, line in enumerate(handle):
            total_lines = i + 1
            if i >= from_line:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
    return {"logs": logs, "total_lines": total_lines, "from_line": from_line, "has_more": False}


def get_generated_sections(reports_dir: str, report_id: str) -> List[Dict[str, Any]]:
    folder = get_report_folder(reports_dir, report_id)
    if not os.path.exists(folder):
        return []

    sections: List[Dict[str, Any]] = []
    for filename in sorted(os.listdir(folder)):
        if filename.startswith('section_') and filename.endswith('.md'):
            file_path = os.path.join(folder, filename)
            with open(file_path, 'r', encoding='utf-8') as handle:
                content = handle.read()
            parts = filename.replace('.md', '').split('_')
            section_index = int(parts[1])
            sections.append({
                "filename": filename,
                "section_index": section_index,
                "content": content,
            })
    return sections


__all__ = [
    "ensure_reports_dir",
    "ensure_report_folder",
    "get_agent_log_path",
    "get_console_log_path",
    "get_evidence_map_path",
    "get_generated_sections",
    "get_outline_path",
    "get_progress_path",
    "get_report_folder",
    "get_report_markdown_path",
    "get_report_path",
    "get_report_v3_path",
    "get_report_v3_markdown_path",
    "get_section_path",
    "read_agent_log",
    "read_console_log",
    "read_json_safe",
    "read_report_v3",
    "write_json_atomic",
    "write_outline",
    "write_report_v3",
    "write_section_markdown",
]


def write_report_v3(
    report_id: str,
    report_v3: "ReportV3",
    reports_dir: Optional[str] = None,
) -> str:
    """Schreibt report-v3.json atomar in den Report-Ordner.

    Args:
        report_id: Report-ID (wird als Unterordner unter reports_dir genutzt).
        report_v3: Valides ReportV3-Objekt.
        reports_dir: Optionaler Override des Report-Verzeichnisses (für Tests).

    Returns:
        Absoluter Pfad zur geschriebenen ``report-v3.json``.
    """
    from ...config import Config  # Import hier, um zirkuläre Imports zu vermeiden

    base_dir = reports_dir or os.path.join(Config.UPLOAD_FOLDER, "reports")
    folder = ensure_report_folder(base_dir, report_id)
    path = get_report_v3_path(base_dir, report_id)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp-report-v3-", suffix=".json", dir=folder
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(report_v3.model_dump_json(indent=2, by_alias=False))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    _storage_logger.info("report-v3.json geschrieben: %s", path)
    return path


_REPORT_V3_REF_COLLECTIONS = (
    "personas",
    "claims",
    "multipliers",
    "friction_points",
    "trust_signals",
    "change_recommendations",
    "project_impacts",
    "positioning_variants",
    "content_ideas",
)


def _upgrade_report_v3_payload(
    raw: Dict[str, Any],
    *,
    report_id: str,
    reports_dir: str,
) -> Dict[str, Any]:
    """Hebt persistierte ReportV3-v3-Daten verlustarm auf Schema 4."""

    if raw.get("schema_version") != 3:
        return raw

    from ..evidence_migrations import normalize_persisted_evidence_map

    evidence_index: Dict[str, Any] = {}
    evidence_path = get_evidence_map_path(reports_dir, report_id)
    if os.path.exists(evidence_path):
        try:
            with open(evidence_path, "r", encoding="utf-8") as handle:
                evidence_raw = json.load(handle)
            normalized = normalize_persisted_evidence_map(evidence_raw)
            if isinstance(normalized, dict):
                evidence_index = dict(normalized.get("evidence_index") or {})
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            _storage_logger.warning(
                "Evidence-Index fuer ReportV3-Upgrade nicht lesbar (%s): %s",
                report_id,
                exc,
            )

    aliases: Dict[str, set[str]] = {}
    for evidence_id, record in evidence_index.items():
        if not isinstance(record, dict):
            continue
        for value in (
            evidence_id,
            record.get("evidence_id"),
            record.get("producer_key"),
            record.get("source_id_anchor"),
        ):
            alias = str(value or "").strip()
            if alias:
                aliases.setdefault(alias, set()).add(evidence_id)
    unique_aliases = {
        alias: next(iter(candidates))
        for alias, candidates in aliases.items()
        if len(candidates) == 1
    }

    upgraded = dict(raw)
    upgraded["schema_version"] = 4
    upgraded["evidence_index"] = evidence_index
    for collection_name in _REPORT_V3_REF_COLLECTIONS:
        for entry in upgraded.get(collection_name) or []:
            if not isinstance(entry, dict):
                continue
            entry["evidence_refs"] = list(dict.fromkeys(
                unique_aliases[ref]
                for value in entry.get("evidence_refs") or []
                if (ref := str(value or "").strip()) in unique_aliases
            ))
    return upgraded


def read_report_v3(
    report_id: str,
    reports_dir: Optional[str] = None,
) -> "Optional[ReportV3]":
    """Liest report-v3.json und liefert ein valides ReportV3-Objekt oder None.

    Args:
        report_id: Report-ID.
        reports_dir: Optionaler Override des Report-Verzeichnisses (für Tests).

    Returns:
        ``ReportV3`` wenn vorhanden und valide, sonst ``None``.
    """
    from ...config import Config  # Import hier, um zirkuläre Imports zu vermeiden
    from ...contracts.report_v3 import ReportV3
    from pydantic import ValidationError

    base_dir = reports_dir or os.path.join(Config.UPLOAD_FOLDER, "reports")
    path = get_report_v3_path(base_dir, report_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        raw = _upgrade_report_v3_payload(
            raw,
            report_id=report_id,
            reports_dir=base_dir,
        )
        return ReportV3.model_validate(raw)
    except (json.JSONDecodeError, OSError, ValidationError) as exc:
        _storage_logger.warning(
            "report-v3.json nicht lesbar für %s: %s", report_id, exc
        )
        return None


def write_outline(path: str, outline: Dict[str, Any]) -> None:
    write_json_atomic(path, outline)


def write_section_markdown(path: str, title: str, cleaned_content: str) -> str:
    md_content = f"## {title}\n\n"
    if cleaned_content:
        md_content += f"{cleaned_content}\n\n"
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(md_content)
    return path
