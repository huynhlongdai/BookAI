"""Task Manager for BookAI — Phase 2.

Concurrent task execution with queue, progress tracking, and cancellation.

Inspired by MoneyPrinterTurbo's task.py + controllers/manager/.

Features:
    - Thread pool for concurrent task execution
    - Task queue with configurable max concurrent / max queued
    - Stop-at parameter (stop pipeline at a specific stage)
    - Progress callbacks
    - Task cancellation
    - Full pipeline orchestration: script → TTS → subtitle → video

Usage::

    from bookai.task_manager import TaskManager, TaskParams

    manager = TaskManager(max_concurrent=3)
    task_id = manager.submit(
        TaskParams(task_type="video", script=radio_script, ...)
    )
    status = manager.get_status(task_id)
    manager.cancel(task_id)
    manager.shutdown()
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import Queue
from typing import Any, Callable, Optional

from bookai.state import TaskInfo, TaskState, get_state

logger = logging.getLogger("bookai.task_manager")


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------


class PipelineStage(str, Enum):
    """Stages in the video generation pipeline."""

    SCRIPT = "script"
    TTS = "tts"
    SUBTITLE = "subtitle"
    MATERIALS = "materials"
    VIDEO = "video"
    ALL = "all"

    @classmethod
    def ordered(cls) -> list[PipelineStage]:
        return [cls.SCRIPT, cls.TTS, cls.SUBTITLE, cls.MATERIALS, cls.VIDEO]


# ---------------------------------------------------------------------------
# Task parameters
# ---------------------------------------------------------------------------


@dataclass
class TaskParams:
    """Parameters for a video generation task."""

    task_type: str = "full_pipeline"  # video, audio, subtitle, batch, full_pipeline

    # Script (input — at least one required)
    script: Any = None          # RadioScript object
    text: str = ""              # Raw text for TTS
    audio_path: str = ""        # Pre-existing audio (skip TTS)

    # Video config
    cover_image: str = ""
    output_dir: str = "output"
    aspect: str = "9:16"
    transition: str = "fade_in"
    bgm_mode: str = "none"
    bgm_file: str = ""
    subtitle_enabled: bool = True

    # TTS config
    tts_provider: str = "edge_tts"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_rate: str = "+0%"

    # Stock video
    stock_search_terms: list[str] = field(default_factory=list)
    pexels_api_key: str = ""

    # Pipeline control
    stop_at: str = "all"        # Stop pipeline at this stage
    video_count: int = 1        # Number of video variants (for batch)

    # Metadata
    book_title: str = ""
    author: str = ""

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "text": self.text[:100] + "..." if len(self.text) > 100 else self.text,
            "aspect": self.aspect,
            "transition": self.transition,
            "tts_provider": self.tts_provider,
            "tts_voice": self.tts_voice,
            "stop_at": self.stop_at,
            "video_count": self.video_count,
            "book_title": self.book_title,
        }


# ---------------------------------------------------------------------------
# Task result
# ---------------------------------------------------------------------------


@dataclass
class TaskResult:
    """Result of a completed task."""

    task_id: str
    ok: bool = True
    error: str = ""
    files: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task Manager
# ---------------------------------------------------------------------------


class TaskManager:
    """Manages concurrent task execution with queuing.

    Args:
        max_concurrent: Maximum tasks running simultaneously.
        max_queued: Maximum tasks in queue (0 = unlimited).
    """

    def __init__(self, max_concurrent: int = 3, max_queued: int = 50):
        self._max_concurrent = max_concurrent
        self._max_queued = max_queued
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrent, thread_name_prefix="bookai-task"
        )
        self._futures: dict[str, Future] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.RLock()
        self._state = get_state()
        self._progress_callbacks: dict[str, list[Callable]] = {}

    # -----------------------------------------------------------------------
    # Submit / cancel
    # -----------------------------------------------------------------------

    def submit(
        self,
        params: TaskParams,
        task_id: str | None = None,
        on_progress: Callable[[str, int, str], None] | None = None,
    ) -> str:
        """Submit a task for execution.

        Args:
            params: Task parameters.
            task_id: Optional custom task ID.
            on_progress: Callback(task_id, progress_pct, message).

        Returns:
            Task ID string.

        Raises:
            RuntimeError: If queue is full.
        """
        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"

        with self._lock:
            # Check queue limit
            active = len([f for f in self._futures.values() if not f.done()])
            if self._max_queued > 0 and active >= self._max_queued:
                raise RuntimeError(
                    f"Queue full: {active} tasks pending (max {self._max_queued})"
                )

            # Register callbacks
            if on_progress:
                self._progress_callbacks[task_id] = [on_progress]

            # Create task in state store
            self._state.create_task(
                task_id, task_type=params.task_type, params=params.to_dict()
            )

            # Submit to thread pool
            future = self._executor.submit(self._run_task, task_id, params)
            self._futures[task_id] = future

        logger.info(f"Task {task_id} submitted (type={params.task_type})")
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task.

        Returns True if the cancellation was registered.
        """
        with self._lock:
            self._cancelled.add(task_id)
            future = self._futures.get(task_id)
            if future and not future.done():
                future.cancel()
            self._state.cancel_task(task_id)
        logger.info(f"Task {task_id} cancelled")
        return True

    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled."""
        return task_id in self._cancelled

    # -----------------------------------------------------------------------
    # Status / query
    # -----------------------------------------------------------------------

    def get_status(self, task_id: str) -> Optional[TaskInfo]:
        """Get current status of a task."""
        return self._state.get_task(task_id)

    def list_tasks(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[TaskInfo], int]:
        """List all tasks with pagination."""
        return self._state.get_all_tasks(page, page_size)

    def delete_task(self, task_id: str) -> bool:
        """Delete a task from state store."""
        with self._lock:
            self._futures.pop(task_id, None)
            self._cancelled.discard(task_id)
        return self._state.delete_task(task_id)

    def get_active_count(self) -> int:
        """Number of currently running tasks."""
        with self._lock:
            return len([f for f in self._futures.values() if f.running()])

    def get_queue_count(self) -> int:
        """Number of tasks in the queue (submitted but not started)."""
        with self._lock:
            return len([
                f for f in self._futures.values()
                if not f.done() and not f.running()
            ])

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the task manager."""
        self._executor.shutdown(wait=wait)
        logger.info("TaskManager shut down")

    # -----------------------------------------------------------------------
    # Internal: task execution
    # -----------------------------------------------------------------------

    def _run_task(self, task_id: str, params: TaskParams) -> TaskResult:
        """Execute a task in a worker thread."""
        self._state.start_task(task_id)
        self._emit_progress(task_id, 0, "Started")

        try:
            if self.is_cancelled(task_id):
                return TaskResult(task_id=task_id, ok=False, error="Cancelled before start")

            result = self._execute_pipeline(task_id, params)

            if result.ok:
                self._state.complete_task(task_id, result_files=result.files)
                self._emit_progress(task_id, 100, "Completed")
            else:
                self._state.fail_task(task_id, error=result.error)
                self._emit_progress(task_id, -1, f"Failed: {result.error}")

            return result

        except Exception as e:
            error_msg = str(e)
            self._state.fail_task(task_id, error=error_msg)
            self._emit_progress(task_id, -1, f"Error: {error_msg}")
            logger.exception(f"Task {task_id} failed with exception")
            return TaskResult(task_id=task_id, ok=False, error=error_msg)

        finally:
            with self._lock:
                self._progress_callbacks.pop(task_id, None)

    def _execute_pipeline(self, task_id: str, params: TaskParams) -> TaskResult:
        """Execute the full pipeline with stop_at support."""
        stop_at = PipelineStage(params.stop_at) if params.stop_at != "all" else PipelineStage.ALL
        output_dir = Path(params.output_dir) / task_id
        output_dir.mkdir(parents=True, exist_ok=True)
        result_files: list[str] = []
        details: dict[str, Any] = {}

        # Stage 1: Script (10%)
        if self.is_cancelled(task_id):
            return TaskResult(task_id=task_id, ok=False, error="Cancelled")

        script = params.script
        script_text = ""
        if script:
            script_text = "\n\n".join(filter(None, [
                getattr(script, "hook", ""),
                getattr(script, "body", ""),
                getattr(script, "cta", ""),
            ]))
        elif params.text:
            script_text = params.text

        if not script_text and not params.audio_path:
            return TaskResult(task_id=task_id, ok=False, error="No script text or audio provided")

        self._update_progress(task_id, 10, "Script ready")
        details["script_length"] = len(script_text)

        if stop_at == PipelineStage.SCRIPT:
            script_file = output_dir / "script.txt"
            script_file.write_text(script_text, encoding="utf-8")
            result_files.append(str(script_file))
            return TaskResult(task_id=task_id, ok=True, files=result_files, details=details)

        # Stage 2: TTS (30%)
        if self.is_cancelled(task_id):
            return TaskResult(task_id=task_id, ok=False, error="Cancelled")

        audio_path = params.audio_path
        if not audio_path and script_text:
            self._update_progress(task_id, 15, "Synthesizing audio...")
            audio_path = str(output_dir / "voice.mp3")

            from bookai.tts_providers import TTSConfig, tts_synthesize
            tts_cfg = TTSConfig(
                provider=params.tts_provider,
                voice=params.tts_voice,
                rate=params.tts_rate,
            )
            tts_result = tts_synthesize(script_text, audio_path, config=tts_cfg)
            if not tts_result.ok:
                return TaskResult(
                    task_id=task_id, ok=False,
                    error=f"TTS failed: {tts_result.error}",
                )
            result_files.append(audio_path)
            details["audio_duration"] = tts_result.duration_seconds
            details["word_timestamps"] = len(tts_result.word_timestamps)

        self._update_progress(task_id, 30, "Audio ready")

        if stop_at == PipelineStage.TTS:
            return TaskResult(task_id=task_id, ok=True, files=result_files, details=details)

        # Stage 3: Subtitle (45%)
        if self.is_cancelled(task_id):
            return TaskResult(task_id=task_id, ok=False, error="Cancelled")

        subtitle_path = None
        if params.subtitle_enabled and audio_path:
            self._update_progress(task_id, 35, "Generating subtitles...")
            subtitle_path = str(output_dir / "subtitles.srt")

            try:
                from bookai.subtitle import generate_srt
                # Try with word timestamps from TTS first
                if hasattr(tts_result, "word_timestamps") and tts_result.word_timestamps:
                    from bookai.subtitle import generate_srt_from_words
                    srt_path = generate_srt_from_words(
                        tts_result.word_timestamps, subtitle_path, script_text
                    )
                else:
                    srt_path = generate_srt(audio_path, subtitle_path, text=script_text)
                if srt_path:
                    subtitle_path = srt_path
                    result_files.append(subtitle_path)
            except Exception as e:
                logger.warning(f"Subtitle generation failed: {e}")
                subtitle_path = None

        self._update_progress(task_id, 45, "Subtitles ready")

        if stop_at == PipelineStage.SUBTITLE:
            return TaskResult(task_id=task_id, ok=True, files=result_files, details=details)

        # Stage 4: Stock materials (60%)
        if self.is_cancelled(task_id):
            return TaskResult(task_id=task_id, ok=False, error="Cancelled")

        stock_videos: list[str] = []
        if params.stock_search_terms:
            self._update_progress(task_id, 50, "Downloading stock materials...")
            try:
                from bookai.stock_video import StockVideoConfig, download_material, search_pexels

                scfg = StockVideoConfig(pexels_api_key=params.pexels_api_key)
                cache_dir = str(output_dir / "materials")

                for term in params.stock_search_terms[:8]:
                    if self.is_cancelled(task_id):
                        return TaskResult(task_id=task_id, ok=False, error="Cancelled")
                    materials = search_pexels(term, config=scfg)
                    for m in materials[:2]:
                        if m.url:
                            local = download_material(m.url, cache_dir=cache_dir)
                            if local:
                                stock_videos.append(local)
            except Exception as e:
                logger.warning(f"Stock video download failed: {e}")

        self._update_progress(task_id, 60, "Materials ready")

        if stop_at == PipelineStage.MATERIALS:
            return TaskResult(task_id=task_id, ok=True, files=result_files, details=details)

        # Stage 5: Video rendering (100%)
        if self.is_cancelled(task_id):
            return TaskResult(task_id=task_id, ok=False, error="Cancelled")

        self._update_progress(task_id, 65, "Rendering video...")

        from bookai.video_render import VideoConfig, render_radio_video

        video_cfg = VideoConfig(
            aspect=params.aspect,
            transition=params.transition,
            bgm_mode=params.bgm_mode,
            bgm_file=params.bgm_file,
            subtitle_enabled=params.subtitle_enabled,
        )

        video_path = str(output_dir / "output.mp4")
        video_result = render_radio_video(
            script=script,
            audio_path=audio_path,
            output_path=video_path,
            cover_image=params.cover_image or None,
            subtitle_path=subtitle_path,
            stock_videos=stock_videos or None,
            config=video_cfg,
        )

        self._update_progress(task_id, 95, "Finalizing...")

        if video_result.ok:
            result_files.append(str(video_result.output_path))
            details["video_duration"] = video_result.duration_seconds
            details["video_size_mb"] = video_result.file_size_mb
            details["video_engine"] = video_result.engine
        else:
            return TaskResult(
                task_id=task_id, ok=False,
                error=f"Video rendering failed: {video_result.error}",
            )

        return TaskResult(
            task_id=task_id, ok=True, files=result_files,
            duration_seconds=video_result.duration_seconds,
            details=details,
        )

    # -----------------------------------------------------------------------
    # Progress helpers
    # -----------------------------------------------------------------------

    def _update_progress(self, task_id: str, progress: int, message: str = "") -> None:
        """Update task progress in state store and notify callbacks."""
        self._state.update_task(task_id, TaskState.PROCESSING, progress=progress)
        self._emit_progress(task_id, progress, message)

    def _emit_progress(self, task_id: str, progress: int, message: str = "") -> None:
        """Call registered progress callbacks."""
        with self._lock:
            callbacks = self._progress_callbacks.get(task_id, [])
        for cb in callbacks:
            try:
                cb(task_id, progress, message)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Global manager singleton
# ---------------------------------------------------------------------------


_manager_instance: TaskManager | None = None
_manager_lock = threading.Lock()


def get_task_manager(
    max_concurrent: int = 3, max_queued: int = 50
) -> TaskManager:
    """Get or create the global TaskManager."""
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = TaskManager(
                    max_concurrent=max_concurrent,
                    max_queued=max_queued,
                )
    return _manager_instance
