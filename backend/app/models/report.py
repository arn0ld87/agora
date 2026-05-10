"""Report-Domain-Models.

Issue #45 (EPIC-07-ST-01): Aus ``services/report_agent.py`` extrahiert. Reine
Datenklassen plus Status-Enum, keine Service-Logik. Logger und Agent verbleiben
in ``services/report_agent.py`` — die Trennung verläuft entlang der
Reine-Daten-vs-Verhalten-Grenze.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReportStatus(str, Enum):
    """Report status"""
    PENDING = "pending"
    PLANNING = "planning"
    GENERATING = "generating"
    INCOMPLETE = "incomplete"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ReportSection:
    """Report section"""
    title: str
    content: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "content": self.content,
            "description": self.description,
        }

    def to_markdown(self, level: int = 2) -> str:
        """Convert to Markdown format"""
        md = f"{'#' * level} {self.title}\n\n"
        if self.content:
            md += f"{self.content}\n\n"
        return md


@dataclass
class ReportOutline:
    """Report outline"""
    title: str
    summary: str
    sections: List[ReportSection]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "sections": [s.to_dict() for s in self.sections]
        }

    def to_markdown(self) -> str:
        """Convert to Markdown format"""
        md = f"# {self.title}\n\n"
        md += f"> {self.summary}\n\n"
        for section in self.sections:
            md += section.to_markdown()
        return md


@dataclass
class Report:
    """Complete report"""
    report_id: str
    simulation_id: str
    graph_id: str
    simulation_requirement: str
    status: ReportStatus
    outline: Optional[ReportOutline] = None
    markdown_content: str = ""
    missing_sections: List[str] = field(default_factory=list)
    created_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    has_evidence: bool = False
    evidence_sections: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "simulation_id": self.simulation_id,
            "graph_id": self.graph_id,
            "simulation_requirement": self.simulation_requirement,
            "status": self.status.value,
            "outline": self.outline.to_dict() if self.outline else None,
            "markdown_content": self.markdown_content,
            "missing_sections": list(self.missing_sections),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "has_evidence": self.has_evidence,
            "evidence_sections": self.evidence_sections,
        }


@dataclass
class EvidenceItem:
    """Structured evidence attached to a report claim."""
    type: str
    source: str
    value: Any = None
    snippet: str = ""
    tool_name: Optional[str] = None
    query: Optional[str] = None
    raw: Any = None
    agent_log_ref: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "type": self.type,
            "source": self.source,
            "snippet": self.snippet,
        }
        if self.value is not None:
            data["value"] = self.value
        if self.tool_name:
            data["tool_name"] = self.tool_name
        if self.query:
            data["query"] = self.query
        if self.raw is not None:
            data["raw"] = self.raw
        if self.agent_log_ref is not None:
            data["agent_log_ref"] = self.agent_log_ref
        return data


@dataclass
class ReportClaim:
    """Backward-compatible claim model for report evidence maps."""
    claim_id: str
    claim_text: str
    confidence_score: float
    confidence_label: str
    evidence: List[Dict[str, Any]]
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        score = round(max(0.0, min(1.0, self.confidence_score)), 2)
        return {
            "claim_id": self.claim_id,
            "claim": self.claim_text,
            "claim_text": self.claim_text,
            # Keep the legacy label field stable for existing UI/export consumers.
            "confidence": self.confidence_label,
            "confidence_label": self.confidence_label,
            "confidence_score": score,
            "evidence": self.evidence,
            "evidence_items": self.evidence,
            "notes": self.notes,
        }


__all__ = [
    "ReportStatus",
    "ReportSection",
    "ReportOutline",
    "Report",
    "EvidenceItem",
    "ReportClaim",
]
