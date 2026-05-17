"""
Task Status Management
Tracks long-running tasks (like graph building)
"""

import uuid
import threading
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from ..utils.logger import get_logger

logger = get_logger("agora.task_manager")


class TaskStatus(str, Enum):
    """Task status enumeration"""
    PENDING = "pending"          # Pending
    PROCESSING = "processing"    # Processing
    COMPLETED = "completed"      # Completed
    FAILED = "failed"            # Failed


@dataclass
class Task:
    """Task data class"""
    task_id: str
    task_type: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    progress: int = 0              # Overall progress percentage 0-100
    message: str = ""              # Status message
    result: Optional[Dict] = None  # Task result
    error: Optional[str] = None    # Error message
    metadata: Dict = field(default_factory=dict)  # Additional metadata
    progress_detail: Dict = field(default_factory=dict)  # Detailed progress information

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": self.progress,
            "message": self.message,
            "progress_detail": self.progress_detail,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskManager:
    """
    Task Manager
    Thread-safe task status management
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._tasks: Dict[str, Task] = {}
                    cls._instance._task_lock = threading.Lock()
        return cls._instance

    def create_task(self, task_type: str, metadata: Optional[Dict] = None) -> str:
        """
        Create new task

        Args:
            task_type: Task type
            metadata: Additional metadata

        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        now = datetime.now()

        task = Task(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )

        with self._task_lock:
            self._tasks[task_id] = task

        try:
            from ..services.run_registry import RunRegistry
            RunRegistry().sync_task(task)
        except Exception as exc:
            logger.warning("sync_task failed on create_task task_id=%s: %s", task_id, exc)

        return task_id

    def _task_from_run_manifest(self, run: Dict[str, Any]) -> Optional["Task"]:
        """Reconstruct a Task from a RunRegistry manifest.

        The reconstructed task is NOT written back into the in-memory cache
        (Stateless-Probe principle from PR 1 / Gemini review).
        """
        raw_status = run.get("status", "pending")
        # Status mapping: paused → PROCESSING (preserve pause semantics),
        # stopped → FAILED (terminal state, run was aborted).
        status_map: Dict[str, TaskStatus] = {
            "pending": TaskStatus.PENDING,
            "processing": TaskStatus.PROCESSING,
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
            "paused": TaskStatus.PROCESSING,
            "stopped": TaskStatus.FAILED,
        }
        status = status_map.get(raw_status, TaskStatus.PENDING)
        error: Optional[str] = run.get("error")
        if raw_status == "stopped" and not error:
            error = "stopped"

        task_type: str = (
            run.get("metadata", {}).get("task_type")
            or run.get("run_type")
            or "unknown"
        )

        try:
            created_at = datetime.fromisoformat(run["started_at"])
        except (KeyError, ValueError):
            created_at = datetime.now()
        try:
            updated_at = datetime.fromisoformat(run["updated_at"])
        except (KeyError, ValueError):
            updated_at = datetime.now()

        linked_ids = run.get("linked_ids", {})
        task_id = linked_ids.get("task_id") or run.get("run_id", "")

        return Task(
            task_id=task_id,
            task_type=task_type,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            progress=run.get("progress") or 0,
            message=run.get("message") or "",
            error=error,
            metadata=run.get("metadata", {}),
        )

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task — cache first, then RunRegistry fallback."""
        with self._task_lock:
            cached = self._tasks.get(task_id)
            if cached is not None:
                return cached

        # Cache miss — attempt reconstruction from RunRegistry.
        try:
            from ..services.run_registry import RunRegistry
            matches = RunRegistry().find_by_linked_id("task_id", task_id)
            if matches:
                return self._task_from_run_manifest(matches[0])
        except Exception as exc:
            logger.warning("RunRegistry fallback failed for task_id=%s: %s", task_id, exc)

        return None

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None,
        progress_detail: Optional[Dict] = None
    ):
        """
        Update task status

        Args:
            task_id: Task ID
            status: New status
            progress: Progress
            message: Message
            result: Result
            error: Error message
            progress_detail: Detailed progress information
        """
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task:
                task.updated_at = datetime.now()
                if status is not None:
                    task.status = status
                if progress is not None:
                    task.progress = progress
                if message is not None:
                    task.message = message
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error
                if progress_detail is not None:
                    task.progress_detail = progress_detail
                try:
                    from ..services.run_registry import RunRegistry
                    RunRegistry().sync_task(task)
                except Exception as exc:
                    logger.warning("sync_task failed on update_task task_id=%s: %s", task_id, exc)

    def complete_task(self, task_id: str, result: Dict):
        """Mark task as completed"""
        self.update_task(
            task_id,
            status=TaskStatus.COMPLETED,
            progress=100,
            message="Task completed",
            result=result
        )

    def fail_task(self, task_id: str, error: str):
        """Mark task as failed"""
        self.update_task(
            task_id,
            status=TaskStatus.FAILED,
            message="Task failed",
            error=error
        )

    def list_tasks(self, task_type: Optional[str] = None) -> list:
        """List tasks"""
        with self._task_lock:
            tasks = list(self._tasks.values())
            if task_type:
                tasks = [t for t in tasks if t.task_type == task_type]
            return [t.to_dict() for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)]

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Clean up old tasks"""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)

        with self._task_lock:
            old_ids = [
                tid for tid, task in self._tasks.items()
                if task.created_at < cutoff and task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
            ]
            for tid in old_ids:
                del self._tasks[tid]
