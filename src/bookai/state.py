"""Task State Management for BookAI — Phase 2.

Two backends:
    - MemoryState  — in-process dict, for development / single-worker
    - RedisState   — Redis-backed, for production / multi-worker

Inspired by MoneyPrinterTurbo's state.py.

Usage::

    from bookai.state import state, TaskState

    state.update_task("task_001", TaskState.PROCESSING, progress=25)
    task = state.get_task("task_001")
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

# ---------------------------------------------------------------------------
# Task states
# ---------------------------------------------------------------------------


class TaskState(IntEnum):
    """Task lifecycle states."""

    PENDING = 0
    QUEUED = 1
    PROCESSING = 2
    COMPLETED = 3
    FAILED = 4
    CANCELLED = 5
    PAUSED = 6

    @property
    def is_terminal(self) -> bool:
        return self in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED)

    @property
    def label(self) -> str:
        labels = {
            0: "Pending", 1: "Queued", 2: "Processing",
            3: "Completed", 4: "Failed", 5: "Cancelled", 6: "Paused",
        }
        return labels.get(self.value, "Unknown")


# ---------------------------------------------------------------------------
# Task info dataclass
# ---------------------------------------------------------------------------


@dataclass
class TaskInfo:
    """Snapshot of a task's current state."""

    task_id: str
    state: TaskState = TaskState.PENDING
    progress: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""
    result_files: list[str] | None = None
    params: dict[str, Any] | None = None
    task_type: str = ""  # "video", "audio", "subtitle", "batch", "full_pipeline"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "state_label": self.state.label,
            "progress": self.progress,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result_files": self.result_files or [],
            "params": self.params or {},
            "task_type": self.task_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TaskInfo:
        return cls(
            task_id=d.get("task_id", ""),
            state=TaskState(d.get("state", 0)),
            progress=d.get("progress", 0),
            created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0),
            started_at=d.get("started_at", 0.0),
            completed_at=d.get("completed_at", 0.0),
            error=d.get("error", ""),
            result_files=d.get("result_files"),
            params=d.get("params"),
            task_type=d.get("task_type", ""),
        )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseState(ABC):
    """Abstract state backend."""

    @abstractmethod
    def update_task(
        self, task_id: str, state: TaskState, progress: int = 0, **kwargs
    ) -> None:
        ...

    @abstractmethod
    def get_task(self, task_id: str) -> TaskInfo | None:
        ...

    @abstractmethod
    def get_all_tasks(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[TaskInfo], int]:
        ...

    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        ...

    def create_task(
        self, task_id: str, task_type: str = "", params: dict | None = None
    ) -> TaskInfo:
        """Create a new task in PENDING state."""
        now = time.time()
        info = TaskInfo(
            task_id=task_id,
            state=TaskState.PENDING,
            progress=0,
            created_at=now,
            updated_at=now,
            task_type=task_type,
            params=params,
        )
        self.update_task(
            task_id, TaskState.PENDING,
            created_at=now, updated_at=now,
            task_type=task_type, params=params,
        )
        return info

    def start_task(self, task_id: str) -> None:
        """Mark a task as processing."""
        self.update_task(
            task_id, TaskState.PROCESSING,
            started_at=time.time(), updated_at=time.time(),
        )

    def complete_task(self, task_id: str, result_files: list[str] | None = None) -> None:
        """Mark a task as completed."""
        self.update_task(
            task_id, TaskState.COMPLETED, progress=100,
            completed_at=time.time(), updated_at=time.time(),
            result_files=result_files,
        )

    def fail_task(self, task_id: str, error: str = "") -> None:
        """Mark a task as failed."""
        self.update_task(
            task_id, TaskState.FAILED,
            completed_at=time.time(), updated_at=time.time(),
            error=error,
        )

    def cancel_task(self, task_id: str) -> None:
        """Mark a task as cancelled."""
        self.update_task(
            task_id, TaskState.CANCELLED,
            completed_at=time.time(), updated_at=time.time(),
        )


# ---------------------------------------------------------------------------
# Memory state (development)
# ---------------------------------------------------------------------------


class MemoryState(BaseState):
    """In-memory task state storage (thread-safe)."""

    def __init__(self):
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def update_task(
        self, task_id: str, state: TaskState, progress: int = 0, **kwargs
    ) -> None:
        progress = min(max(int(progress), 0), 100)
        with self._lock:
            existing = self._tasks.get(task_id, {})
            existing.update({
                "task_id": task_id,
                "state": int(state),
                "progress": progress,
                "updated_at": time.time(),
                **kwargs,
            })
            self._tasks[task_id] = existing

    def get_task(self, task_id: str) -> TaskInfo | None:
        with self._lock:
            data = self._tasks.get(task_id)
            if data is None:
                return None
            return TaskInfo.from_dict(copy.deepcopy(data))

    def get_all_tasks(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[TaskInfo], int]:
        start = (page - 1) * page_size
        end = start + page_size
        with self._lock:
            all_tasks = list(self._tasks.values())
            total = len(all_tasks)
            # Sort by created_at descending (newest first)
            all_tasks.sort(key=lambda t: t.get("created_at", 0), reverse=True)
            page_tasks = [
                TaskInfo.from_dict(copy.deepcopy(t))
                for t in all_tasks[start:end]
            ]
        return page_tasks, total

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def count_by_state(self, state: TaskState) -> int:
        """Count tasks in a given state."""
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.get("state") == int(state))


# ---------------------------------------------------------------------------
# Redis state (production)
# ---------------------------------------------------------------------------


class RedisState(BaseState):
    """Redis-backed task state storage."""

    def __init__(
        self, host: str = "localhost", port: int = 6379,
        db: int = 0, password: str | None = None,
        key_prefix: str = "bookai:task:",
    ):
        try:
            import redis
            self._redis = redis.StrictRedis(
                host=host, port=port, db=db, password=password,
                decode_responses=True,
            )
            self._redis.ping()
        except ImportError:
            raise RuntimeError("redis package not installed. Run: pip install redis")
        except Exception as e:
            raise RuntimeError(f"Redis connection failed: {e}")

        self._prefix = key_prefix

    def _key(self, task_id: str) -> str:
        return f"{self._prefix}{task_id}"

    def update_task(
        self, task_id: str, state: TaskState, progress: int = 0, **kwargs
    ) -> None:
        progress = min(max(int(progress), 0), 100)
        data = {
            "task_id": task_id,
            "state": int(state),
            "progress": progress,
            "updated_at": time.time(),
        }
        # Serialize complex types
        for k, v in kwargs.items():
            if isinstance(v, (dict, list)):
                data[k] = json.dumps(v, ensure_ascii=False)
            else:
                data[k] = v

        self._redis.hset(self._key(task_id), mapping=data)

    def get_task(self, task_id: str) -> TaskInfo | None:
        data = self._redis.hgetall(self._key(task_id))
        if not data:
            return None
        return TaskInfo.from_dict(self._deserialize(data))

    def get_all_tasks(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[TaskInfo], int]:
        # Scan for all task keys
        keys = []
        cursor = 0
        while True:
            cursor, batch = self._redis.scan(cursor, match=f"{self._prefix}*", count=100)
            keys.extend(batch)
            if cursor == 0:
                break

        total = len(keys)
        # Sort by key (approximation; in production use sorted set)
        keys.sort(reverse=True)
        start = (page - 1) * page_size
        end = start + page_size
        page_keys = keys[start:end]

        tasks = []
        for key in page_keys:
            data = self._redis.hgetall(key)
            if data:
                tasks.append(TaskInfo.from_dict(self._deserialize(data)))

        return tasks, total

    def delete_task(self, task_id: str) -> bool:
        return self._redis.delete(self._key(task_id)) > 0

    def _deserialize(self, data: dict) -> dict:
        """Convert Redis hash values back to Python types."""
        result = {}
        for k, v in data.items():
            if isinstance(v, str):
                # Try JSON first
                if v.startswith(("{", "[")):
                    try:
                        result[k] = json.loads(v)
                        continue
                    except json.JSONDecodeError:
                        pass
                # Try numeric
                try:
                    if "." in v:
                        result[k] = float(v)
                    else:
                        result[k] = int(v)
                    continue
                except ValueError:
                    pass
            result[k] = v
        return result


# ---------------------------------------------------------------------------
# Global state singleton
# ---------------------------------------------------------------------------


def _create_state() -> BaseState:
    """Create state backend from environment config."""
    use_redis = os.getenv("BOOKAI_REDIS_ENABLED", "false").lower() in ("true", "1", "yes")
    if use_redis:
        return RedisState(
            host=os.getenv("BOOKAI_REDIS_HOST", "localhost"),
            port=int(os.getenv("BOOKAI_REDIS_PORT", "6379")),
            db=int(os.getenv("BOOKAI_REDIS_DB", "0")),
            password=os.getenv("BOOKAI_REDIS_PASSWORD") or None,
        )
    return MemoryState()


# Lazy initialization to avoid startup errors when redis isn't needed
_state_instance: BaseState | None = None
_state_lock = threading.Lock()


def get_state() -> BaseState:
    """Get the global state backend (lazy init)."""
    global _state_instance
    if _state_instance is None:
        with _state_lock:
            if _state_instance is None:
                _state_instance = _create_state()
    return _state_instance


# Convenience alias
state = property(lambda self: get_state())
