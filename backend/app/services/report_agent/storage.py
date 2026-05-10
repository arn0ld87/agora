from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional


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
    "write_json_atomic",
    "write_outline",
    "write_section_markdown",
]


def write_outline(path: str, outline: Dict[str, Any]) -> None:
    write_json_atomic(path, outline)


def write_section_markdown(path: str, title: str, cleaned_content: str) -> str:
    md_content = f"## {title}\n\n"
    if cleaned_content:
        md_content += f"{cleaned_content}\n\n"
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(md_content)
    return path
