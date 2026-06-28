"""Task queue abstraction — current: asyncio.Queue backed; future: pluggable backend.

Design contract (Adapter pattern):
    The public surface is QueueBackend (ABC) + get_queue().
    To swap in Celery / Redis later, implement QueueBackend for the new backend
    and register it in get_queue().  No caller code changes.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import traceback
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared data types
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


@dataclass
class TaskRecord:
    """Snapshot of one task, safe to serialise and return via API."""
    task_id: str
    task_type: str                # e.g. "download", "subtitle"
    status: TaskStatus = TaskStatus.QUEUED
    percent: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # When the task was queued (ISO timestamp string)
    created_at: str = field(default_factory=lambda: __import__("datetime").datetime.now().isoformat())


# job function signature: async def job(task_id: str, **kwargs) -> Any
JobFunc = Callable[[str, Any], Awaitable[Any]]


# ---------------------------------------------------------------------------
# Abstract backend — implement this to plug in a different queue engine
# ---------------------------------------------------------------------------

class QueueBackend(abc.ABC):
    @abc.abstractmethod
    async def enqueue(self, task_type: str, job: JobFunc, **kwargs) -> str:
        """Submit a job; return task_id."""
        ...

    @abc.abstractmethod
    def get(self, task_id: str) -> Optional[TaskRecord]:
        """Return a snapshot of a task (or None if unknown)."""
        ...

    @abc.abstractmethod
    def list(self) -> Dict[str, TaskRecord]:
        """Return all known tasks."""
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        """Graceful drain of running workers."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (asyncio.Queue workers)
# ---------------------------------------------------------------------------

class _InMemoryBackend(QueueBackend):
    """Single-process, async worker pool backed by asyncio.Queue.

    Suitable for ≤50 concurrent tasks on one machine.
    """

    def __init__(self, max_concurrent: int = 2) -> None:
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._records: Dict[str, TaskRecord] = {}
        self._running: Dict[str, asyncio.Task] = {}

    # -- public API ----------------------------------------------------------

    async def enqueue(self, task_type: str, job: JobFunc, **kwargs) -> str:
        task_id = str(uuid.uuid4())[:8]
        record = TaskRecord(task_id=task_id, task_type=task_type)
        self._records[task_id] = record

        t = asyncio.create_task(self._run(task_id, task_type, job, kwargs))
        self._running[task_id] = t
        return task_id

    def get(self, task_id: str) -> Optional[TaskRecord]:
        return self._records.get(task_id)

    def list(self) -> Dict[str, TaskRecord]:
        return dict(self._records)

    async def shutdown(self) -> None:
        for t in self._running.values():
            t.cancel()
        if self._running:
            await asyncio.gather(*self._running.values(), return_exceptions=True)
        self._running.clear()

    # -- internals -----------------------------------------------------------

    async def _run(
        self, task_id: str, task_type: str, job: JobFunc, kwargs: dict
    ) -> None:
        async with self._semaphore:
            record = self._records[task_id]
            record.status = TaskStatus.PROCESSING
            try:
                result = await job(task_id, **kwargs)
                record.status = TaskStatus.DONE
                record.percent = 100.0
                record.result = result if isinstance(result, dict) else {"value": result}
            except asyncio.CancelledError:
                record.status = TaskStatus.ERROR
                record.error = "Cancelled"
            except Exception:
                record.status = TaskStatus.ERROR
                record.error = traceback.format_exc()
                log.exception("Task %s[%s] failed", task_type, task_id)
            finally:
                self._running.pop(task_id, None)


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------

_backend: Optional[QueueBackend] = None
_backend_lock = asyncio.Lock()


async def get_queue() -> QueueBackend:
    """Return the active queue backend (lazy-init)."""
    global _backend
    if _backend is not None:
        return _backend

    async with _backend_lock:
        if _backend is not None:
            return _backend

        # -- switch backends here in the future --
        # if config.QUEUE_BACKEND == "celery":
        #     _backend = _CeleryBackend(...)
        # else:
        _backend = _InMemoryBackend(max_concurrent=config.MAX_CONCURRENT)

        log.info("Queue backend initialised: %s (max_concurrent=%d)",
                 type(_backend).__name__, config.MAX_CONCURRENT)
        return _backend
