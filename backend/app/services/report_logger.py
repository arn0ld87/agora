"""Report-Agent Logger.

Issue #46 (EPIC-07-ST-02): Aus ``services/report_agent.py`` extrahiert.
Zwei Logger-Klassen:

* :class:`ReportLogger` — strukturierter JSONL-Log (`agent_log.jsonl`) für
  jeden Schritt der Report-Generierung. Konsumiert vom Frontend für die
  Live-Agent-Trace-Ansicht.
* :class:`ReportConsoleLogger` — Plain-Text-Konsolen-Log (`console_log.txt`)
  via ``logging.FileHandler``, attached an die ``agora.report_agent``- und
  ``agora.graph_tools``-Logger.

Beide schreiben unter ``Config.UPLOAD_FOLDER/reports/<report_id>/`` und werden
vom :class:`ReportAgent` über ``__init__`` instanziiert.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from ..config import Config

#: Der Report, zu dem die aktuell laufende Arbeit gehört.
#:
#: ``ReportConsoleLogger`` hängt seinen FileHandler an die *globalen* Logger
#: ``agora.report_agent`` und ``agora.graph_tools``. Laufen zwei Reports
#: gleichzeitig, hängen beide Handler an denselben Loggern, und jede Zeile
#: landet in beiden ``console_log.txt``. Genau das zeigte der Referenzlauf: die
#: Datei zu ``report_cc2ef45da5e9`` enthielt Einträge zu
#: ``report_e5734b31241d``. Für eine Forensik ist ein Log, das fremde Läufe
#: mitschreibt, schlechter als keins — man kann ihm nicht mehr trauen.
_current_report_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "agora_current_report_id", default=""
)


def current_report_id() -> str:
    """Der Report, dem die aktuelle Arbeit zugeordnet ist; leer wenn unbekannt."""
    return _current_report_id.get()


class ReportScopeFilter(logging.Filter):
    """Lässt nur durch, was nicht nachweislich zu einem anderen Report gehört.

    Die Regel ist bewusst asymmetrisch. Ein Record mit *fremder* Report-Zuordnung
    wird verworfen — das ist der Schaden, um den es geht. Ein Record *ohne*
    Zuordnung wird durchgelassen: ``ThreadPoolExecutor.submit`` kopiert den
    Kontext nicht, und ein Worker-Thread ohne gesetzten Kontext würde sonst
    still aus dem Log fallen. Ein unzugeordneter Eintrag ist unscharf, ein
    fremder ist falsch.
    """

    def __init__(self, report_id: str) -> None:
        super().__init__()
        self.report_id = report_id

    def filter(self, record: logging.LogRecord) -> bool:
        active = current_report_id()
        return not active or active == self.report_id


class ReportLogger:
    """
    Report Agent Detailed Logger

    Generates agent_log.jsonl file in the report folder, recording detailed actions at each step.
    Each line is a complete JSON object containing timestamp, action type, details, etc.
    """

    def __init__(self, report_id: str):
        """
        Initialize the logger

        Args:
            report_id: Report ID, used to determine the log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'agent_log.jsonl'
        )
        self.start_time = datetime.now()
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Ensure the log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _get_elapsed_time(self) -> float:
        """Get elapsed time from start to now (in seconds)"""
        return (datetime.now() - self.start_time).total_seconds()

    def log(
        self,
        action: str,
        stage: str,
        details: Dict[str, Any],
        section_title: Optional[str] = None,
        section_index: Optional[int] = None,
    ):
        """
        Log an entry

        Args:
            action: Action type, e.g. 'start', 'tool_call', 'llm_response', 'section_complete', etc
            stage: Current stage, e.g. 'planning', 'generating', 'completed'
            details: Details dictionary, not truncated
            section_title: Current section title (optional)
            section_index: Current section index (optional)
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_seconds": round(self._get_elapsed_time(), 2),
            "report_id": self.report_id,
            "action": action,
            "stage": stage,
            "section_title": section_title,
            "section_index": section_index,
            "details": details
        }

        # Append to JSONL file
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

    def log_start(self, simulation_id: str, graph_id: str, simulation_requirement: str):
        """Log report generation start"""
        self.log(
            action="report_start",
            stage="pending",
            details={
                "simulation_id": simulation_id,
                "graph_id": graph_id,
                "simulation_requirement": simulation_requirement,
                "message": "Report generation task started"
            }
        )

    def log_planning_start(self):
        """Log outline planning start"""
        self.log(
            action="planning_start",
            stage="planning",
            details={"message": "Started planning report outline"}
        )

    def log_planning_context(self, context: Dict[str, Any]):
        """Log context information acquired during planning"""
        self.log(
            action="planning_context",
            stage="planning",
            details={
                "message": "Acquired simulation context information",
                "context": context
            }
        )

    def log_planning_complete(self, outline_dict: Dict[str, Any]):
        """Log outline planning completion"""
        self.log(
            action="planning_complete",
            stage="planning",
            details={
                "message": "Outline planning completed",
                "outline": outline_dict
            }
        )

    def log_section_start(self, section_title: str, section_index: int):
        """Log section generation start"""
        self.log(
            action="section_start",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={"message": f"Started generating section: {section_title}"}
        )

    def log_react_thought(self, section_title: str, section_index: int, iteration: int, thought: str):
        """Log ReACT thinking process"""
        self.log(
            action="react_thought",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "thought": thought,
                "message": f"ReACT round {iteration} thought"
            }
        )

    def log_tool_call(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        parameters: Dict[str, Any],
        iteration: int
    ):
        """Log tool call"""
        self.log(
            action="tool_call",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "parameters": parameters,
                "message": f"Called tool: {tool_name}"
            }
        )

    def log_tool_result(
        self,
        section_title: str,
        section_index: int,
        tool_name: str,
        result: str,
        iteration: int
    ):
        """Log tool call result (full content, not truncated)"""
        self.log(
            action="tool_result",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "tool_name": tool_name,
                "result": result,  # Full result, not truncated
                "result_length": len(result),
                "message": f"Tool {tool_name} returned result"
            }
        )

    def log_llm_response(
        self,
        section_title: str,
        section_index: int,
        response: str,
        iteration: int,
        has_tool_calls: bool,
        has_final_answer: bool
    ):
        """Log LLM response (full content, not truncated)"""
        self.log(
            action="llm_response",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "iteration": iteration,
                "response": response,  # Full response, not truncated
                "response_length": len(response),
                "has_tool_calls": has_tool_calls,
                "has_final_answer": has_final_answer,
                "message": f"LLM response (tool calls: {has_tool_calls}, final answer: {has_final_answer})"
            }
        )

    def log_section_content(
        self,
        section_title: str,
        section_index: int,
        content: str,
        tool_calls_count: int
    ):
        """Log section content generation completion (records content only, not the whole section completion)"""
        self.log(
            action="section_content",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": content,  # Full content, not truncated
                "content_length": len(content),
                "tool_calls_count": tool_calls_count,
                "message": f"Section {section_title} content generation completed"
            }
        )

    def log_section_full_complete(
        self,
        section_title: str,
        section_index: int,
        full_content: str
    ):
        """
        Log section generation completion

        Frontend should listen to this log to determine if a section is truly complete and get full content
        """
        self.log(
            action="section_complete",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "content": full_content,
                "content_length": len(full_content),
                "message": f"Section {section_title} generation completed"
            }
        )

    def log_phase_timing(
        self,
        phase: str,
        duration_seconds: float,
        section_title: Optional[str] = None,
        section_index: Optional[int] = None,
    ):
        """Log start/end duration of a post-processing phase (Issue #1187).

        Makes the previously silent post-processing (claim extraction,
        evidence binding, section-metadata extraction, evidence-map
        persistence) measurable. A follow-up run with this instrumentation
        is the prerequisite for Issue #1190 (performance optimisation).
        """
        self.log(
            action="phase_timing",
            stage="generating",
            section_title=section_title,
            section_index=section_index,
            details={
                "phase": phase,
                "duration_seconds": round(duration_seconds, 3),
                "message": f"Phase {phase} completed in {duration_seconds:.2f}s",
            },
        )

    def log_report_complete(self, total_sections: int, total_time_seconds: float):
        """Log report generation completion"""
        self.log(
            action="report_complete",
            stage="completed",
            details={
                "total_sections": total_sections,
                "total_time_seconds": round(total_time_seconds, 2),
                "message": "Report generation completed"
            }
        )

    def log_error(self, error_message: str, stage: str, section_title: Optional[str] = None):
        """Log error"""
        self.log(
            action="error",
            stage=stage,
            section_title=section_title,
            section_index=None,
            details={
                "error": error_message,
                "message": f"Error occurred: {error_message}"
            }
        )


class ReportConsoleLogger:
    """
    Report Agent Console Logger

    Writes console-style logs (INFO, WARNING, etc.) to console_log.txt file in the report folder.
    These logs are different from agent_log.jsonl and are plain text console output.
    """

    def __init__(self, report_id: str):
        """
        Initialize console logger

        Args:
            report_id: Report ID, used to determine the log file path
        """
        self.report_id = report_id
        self.log_file_path = os.path.join(
            Config.UPLOAD_FOLDER, 'reports', report_id, 'console_log.txt'
        )
        self._ensure_log_file()
        self._file_handler: Optional[logging.FileHandler] = None
        # Der Kontext wird hier gesetzt und in ``close`` zurückgenommen: der
        # Logger lebt genau so lange wie der Report-Lauf und im selben Thread.
        self._scope_token = _current_report_id.set(report_id)
        self._setup_file_handler()

    def _ensure_log_file(self):
        """Ensure the log file directory exists"""
        log_dir = os.path.dirname(self.log_file_path)
        os.makedirs(log_dir, exist_ok=True)

    def _setup_file_handler(self):
        """Set up file handler to write logs to file"""
        # Create file handler
        self._file_handler = logging.FileHandler(
            self.log_file_path,
            mode='a',
            encoding='utf-8'
        )
        self._file_handler.setLevel(logging.INFO)

        # Use the same concise format as console
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        self._file_handler.setFormatter(formatter)
        self._file_handler.addFilter(ReportScopeFilter(self.report_id))

        # Add to report_agent related loggers
        loggers_to_attach = [
            'agora.report_agent',
            'agora.graph_tools',
        ]

        for logger_name in loggers_to_attach:
            target_logger = logging.getLogger(logger_name)
            # Avoid duplicate additions
            if self._file_handler not in target_logger.handlers:
                target_logger.addHandler(self._file_handler)

    def close(self):
        """Close file handler and remove it from logger"""
        if self._file_handler:
            loggers_to_detach = [
                'agora.report_agent',
                'agora.graph_tools',
            ]

            for logger_name in loggers_to_detach:
                target_logger = logging.getLogger(logger_name)
                if self._file_handler in target_logger.handlers:
                    target_logger.removeHandler(self._file_handler)

            self._file_handler.close()
            self._file_handler = None

        token = getattr(self, "_scope_token", None)
        if token is not None:
            try:
                _current_report_id.reset(token)
            except ValueError:
                # Der Finalizer läuft in einem anderen Kontext als das Set —
                # typischerweise, wenn der Garbage Collector einen alten Logger
                # einsammelt, während ein anderer Report läuft. Den Scope hier
                # zu leeren würde genau die Vermischung wiederherstellen, die
                # dieser Filter verhindert: ein leerer Scope lässt jeden Record
                # in *alle* offenen Logdateien. Fremder Zustand wird nicht
                # angefasst.
                pass
            self._scope_token = None

    def __del__(self):
        """Ensure file handler is closed during destructor"""
        self.close()


__all__ = ["ReportLogger", "ReportConsoleLogger"]
