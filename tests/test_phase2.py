"""Tests for Phase 2 — TTS + Task System + Batch + API.

Tests the new modules:
- tts_providers
- state
- task_manager
- batch
- api (models/utilities only, no server)
"""

import os
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# tts_providers tests
# ===========================================================================


class TestTTSProviders:
    """Test multi-provider TTS module."""

    def test_tts_config_defaults(self):
        from bookai.tts_providers import TTSConfig

        cfg = TTSConfig()
        assert cfg.provider == "edge_tts"
        assert cfg.voice == "vi-VN-HoaiMyNeural"
        assert cfg.rate == "+0%"

    def test_tts_config_env_loading(self):
        from bookai.tts_providers import TTSConfig

        with patch.dict(os.environ, {"AZURE_SPEECH_KEY": "test-key-123"}):
            cfg = TTSConfig()
            assert cfg.azure_key == "test-key-123"

    def test_tts_result(self):
        from bookai.tts_providers import TTSResult

        r = TTSResult(output_path=Path("/tmp/test.mp3"), ok=True, provider="edge_tts")
        assert r.filename == "test.mp3"
        assert r.ok

    def test_tts_provider_enum(self):
        from bookai.tts_providers import TTSProvider

        assert TTSProvider.EDGE_TTS.value == "edge_tts"
        assert TTSProvider.NO_VOICE.value == "no_voice"

    def test_list_all_voices(self):
        from bookai.tts_providers import list_all_voices

        voices = list_all_voices()
        assert "vi-VN-HoaiMyNeural" in voices
        assert voices["vi-VN-HoaiMyNeural"]["provider"] == "edge_tts"

    def test_list_all_voices_with_multilingual(self):
        from bookai.tts_providers import list_all_voices

        voices = list_all_voices(include_multilingual=True)
        assert "en-US-JennyNeural" in voices

    def test_list_voices_by_provider(self):
        from bookai.tts_providers import list_voices_by_provider

        edge = list_voices_by_provider("edge_tts")
        assert len(edge) >= 2
        assert "vi-VN-HoaiMyNeural" in edge

    def test_get_siliconflow_voices(self):
        from bookai.tts_providers import get_siliconflow_voices

        voices = get_siliconflow_voices()
        assert len(voices) == 8
        assert any("alex" in v for v in voices)

    def test_estimate_duration(self):
        from bookai.tts_providers import estimate_duration

        # 25 words at 2.5 wps = 10 seconds
        assert estimate_duration("word " * 25) == pytest.approx(10.0, abs=0.5)

    def test_estimate_duration_faster(self):
        from bookai.tts_providers import estimate_duration

        # Faster rate should decrease duration
        normal = estimate_duration("word " * 25, rate_percent=0)
        faster = estimate_duration("word " * 25, rate_percent=50)
        assert faster < normal

    def test_convert_rate_to_percent(self):
        from bookai.tts_providers import convert_rate_to_percent

        assert convert_rate_to_percent(1.0) == "+0%"
        assert convert_rate_to_percent(1.5) == "+50%"
        assert convert_rate_to_percent(0.8) == "-20%"

    def test_clean_text(self):
        from bookai.tts_providers import _clean_text_for_tts

        text = "**bold** https://example.com #tag 🎉"
        cleaned = _clean_text_for_tts(text)
        assert "**" not in cleaned
        assert "https://" not in cleaned
        assert "#tag" not in cleaned

    def test_escape_xml(self):
        from bookai.tts_providers import _escape_xml

        assert _escape_xml("<tag>&amp;") == "&lt;tag&gt;&amp;amp;"

    def test_synth_unknown_provider(self):
        from bookai.tts_providers import TTSConfig, tts_synthesize

        cfg = TTSConfig(provider="nonexistent")
        result = tts_synthesize("test", "/tmp/test.mp3", config=cfg)
        assert not result.ok
        assert "Unknown TTS provider" in result.error

    def test_synth_empty_text(self):
        from bookai.tts_providers import TTSConfig, tts_synthesize

        cfg = TTSConfig(provider="edge_tts")
        result = tts_synthesize("", "/tmp/test.mp3", config=cfg)
        assert not result.ok
        assert "Empty text" in result.error

    def test_synth_no_voice_empty_text(self):
        from bookai.tts_providers import TTSConfig, tts_synthesize

        # no_voice should work even with empty text (uses silence_duration)
        cfg = TTSConfig(provider="no_voice", silence_duration=5.0)
        result = tts_synthesize("", "/tmp/test_silent.wav", config=cfg)
        # May fail without ffmpeg but should not error on "Empty text"
        assert "Empty text" not in result.error

    def test_synth_azure_no_key(self):
        from bookai.tts_providers import TTSConfig, tts_synthesize

        cfg = TTSConfig(provider="azure", azure_key="")
        result = tts_synthesize("test", "/tmp/test.mp3", config=cfg)
        assert not result.ok
        assert "key not set" in result.error

    def test_synth_siliconflow_no_key(self):
        from bookai.tts_providers import TTSConfig, tts_synthesize

        cfg = TTSConfig(provider="siliconflow", siliconflow_key="")
        result = tts_synthesize("test", "/tmp/test.mp3", config=cfg)
        assert not result.ok
        assert "key not set" in result.error

    def test_synth_elevenlabs_no_key(self):
        from bookai.tts_providers import TTSConfig, tts_synthesize

        cfg = TTSConfig(provider="elevenlabs", elevenlabs_key="")
        result = tts_synthesize("test", "/tmp/test.mp3", config=cfg)
        assert not result.ok
        assert "key not set" in result.error

    def test_tts_synthesize_script(self):
        from bookai.tts_providers import TTSConfig, tts_synthesize_script

        script = MagicMock()
        script.hook = "Hook"
        script.body = ""  # Empty body
        script.cta = ""

        cfg = TTSConfig(provider="azure", azure_key="")  # Will fail at API
        result = tts_synthesize_script(script, "/tmp/test.mp3", config=cfg)
        assert not result.ok  # No key, expected failure


# ===========================================================================
# state tests
# ===========================================================================


class TestState:
    """Test task state management."""

    def test_task_state_enum(self):
        from bookai.state import TaskState

        assert TaskState.PENDING.value == 0
        assert TaskState.COMPLETED.is_terminal
        assert TaskState.FAILED.is_terminal
        assert not TaskState.PROCESSING.is_terminal
        assert TaskState.PROCESSING.label == "Processing"

    def test_task_info_to_dict(self):
        from bookai.state import TaskInfo, TaskState

        info = TaskInfo(task_id="test_001", state=TaskState.PROCESSING, progress=50)
        d = info.to_dict()
        assert d["task_id"] == "test_001"
        assert d["state"] == 2
        assert d["state_label"] == "Processing"
        assert d["progress"] == 50

    def test_task_info_from_dict(self):
        from bookai.state import TaskInfo, TaskState

        d = {"task_id": "test_002", "state": 3, "progress": 100}
        info = TaskInfo.from_dict(d)
        assert info.task_id == "test_002"
        assert info.state == TaskState.COMPLETED
        assert info.progress == 100

    def test_memory_state_crud(self):
        from bookai.state import MemoryState, TaskState

        ms = MemoryState()

        # Create
        ms.update_task("t1", TaskState.PENDING, 0, created_at=1.0)
        task = ms.get_task("t1")
        assert task is not None
        assert task.task_id == "t1"
        assert task.state == TaskState.PENDING

        # Update
        ms.update_task("t1", TaskState.PROCESSING, 50)
        task = ms.get_task("t1")
        assert task.progress == 50

        # List
        ms.update_task("t2", TaskState.COMPLETED, 100, created_at=2.0)
        tasks, total = ms.get_all_tasks(page=1, page_size=10)
        assert total == 2
        assert len(tasks) == 2

        # Delete
        assert ms.delete_task("t1")
        assert ms.get_task("t1") is None
        assert not ms.delete_task("nonexistent")

    def test_memory_state_pagination(self):
        from bookai.state import MemoryState, TaskState

        ms = MemoryState()
        for i in range(15):
            ms.update_task(f"t{i:02d}", TaskState.PENDING, created_at=float(i))

        page1, total = ms.get_all_tasks(page=1, page_size=10)
        assert total == 15
        assert len(page1) == 10

        page2, _ = ms.get_all_tasks(page=2, page_size=10)
        assert len(page2) == 5

    def test_memory_state_progress_clamp(self):
        from bookai.state import MemoryState, TaskState

        ms = MemoryState()
        ms.update_task("t1", TaskState.PROCESSING, progress=150)
        task = ms.get_task("t1")
        assert task.progress == 100

        ms.update_task("t1", TaskState.PROCESSING, progress=-10)
        task = ms.get_task("t1")
        assert task.progress == 0

    def test_memory_state_thread_safety(self):
        from bookai.state import MemoryState, TaskState

        ms = MemoryState()
        errors = []

        def update_many(prefix, count):
            try:
                for i in range(count):
                    ms.update_task(f"{prefix}_{i}", TaskState.PROCESSING, progress=i)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=update_many, args=(f"t{j}", 100))
            for j in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        _, total = ms.get_all_tasks(page=1, page_size=1000)
        assert total == 500  # 5 threads × 100 tasks

    def test_memory_state_count_by_state(self):
        from bookai.state import MemoryState, TaskState

        ms = MemoryState()
        ms.update_task("t1", TaskState.PROCESSING)
        ms.update_task("t2", TaskState.PROCESSING)
        ms.update_task("t3", TaskState.COMPLETED)

        assert ms.count_by_state(TaskState.PROCESSING) == 2
        assert ms.count_by_state(TaskState.COMPLETED) == 1
        assert ms.count_by_state(TaskState.FAILED) == 0

    def test_create_task_helper(self):
        from bookai.state import MemoryState, TaskState

        ms = MemoryState()
        info = ms.create_task("t1", task_type="video", params={"text": "hello"})
        assert info.task_id == "t1"
        assert info.task_type == "video"

        # Verify it's in state
        t = ms.get_task("t1")
        assert t is not None

    def test_start_complete_fail_cancel(self):
        from bookai.state import MemoryState, TaskState

        ms = MemoryState()
        ms.create_task("t1")

        ms.start_task("t1")
        t = ms.get_task("t1")
        assert t.state == TaskState.PROCESSING

        ms.complete_task("t1", result_files=["out.mp4"])
        t = ms.get_task("t1")
        assert t.state == TaskState.COMPLETED
        assert t.progress == 100

        ms.create_task("t2")
        ms.fail_task("t2", error="test error")
        t = ms.get_task("t2")
        assert t.state == TaskState.FAILED

        ms.create_task("t3")
        ms.cancel_task("t3")
        t = ms.get_task("t3")
        assert t.state == TaskState.CANCELLED


# ===========================================================================
# task_manager tests
# ===========================================================================


class TestTaskManager:
    """Test task manager."""

    def test_pipeline_stage_ordered(self):
        from bookai.task_manager import PipelineStage

        stages = PipelineStage.ordered()
        assert stages[0] == PipelineStage.SCRIPT
        assert stages[-1] == PipelineStage.VIDEO

    def test_task_params_to_dict(self):
        from bookai.task_manager import TaskParams

        p = TaskParams(task_type="video", text="Hello world", book_title="Test Book")
        d = p.to_dict()
        assert d["task_type"] == "video"
        assert d["book_title"] == "Test Book"

    def test_task_params_text_truncation(self):
        from bookai.task_manager import TaskParams

        p = TaskParams(text="x" * 200)
        d = p.to_dict()
        assert len(d["text"]) <= 103  # 100 + "..."

    def test_task_result(self):
        from bookai.task_manager import TaskResult

        r = TaskResult(task_id="t1", ok=True, files=["out.mp4"])
        assert r.ok
        assert len(r.files) == 1

    def test_task_manager_submit_and_status(self):
        from bookai.task_manager import TaskManager, TaskParams

        # Use a custom manager (not global) for test isolation
        manager = TaskManager(max_concurrent=1, max_queued=10)

        # Submit a task that will fail (no real audio/script)
        params = TaskParams(task_type="video", text="Test text")
        task_id = manager.submit(params, task_id="test_task_001")

        assert task_id == "test_task_001"

        # Wait briefly for task to start
        time.sleep(0.5)

        status = manager.get_status(task_id)
        assert status is not None
        assert status.task_id == "test_task_001"

        manager.shutdown(wait=True)

    def test_task_manager_cancel(self):
        from bookai.task_manager import TaskManager, TaskParams

        manager = TaskManager(max_concurrent=1)

        params = TaskParams(task_type="video", text="Test")
        task_id = manager.submit(params)

        result = manager.cancel(task_id)
        assert result is True
        assert manager.is_cancelled(task_id)

        manager.shutdown(wait=True)

    def test_task_manager_list(self):
        from bookai.task_manager import TaskManager, TaskParams

        manager = TaskManager(max_concurrent=2)

        # Record baseline count from shared state
        _, baseline = manager.list_tasks(page=1, page_size=1000)

        for i in range(3):
            manager.submit(TaskParams(text=f"Task {i}"))

        time.sleep(0.3)

        tasks, total = manager.list_tasks(page=1, page_size=1000)
        assert total == baseline + 3

        manager.shutdown(wait=True)

    def test_task_manager_delete(self):
        from bookai.task_manager import TaskManager, TaskParams
        from bookai.state import MemoryState

        manager = TaskManager(max_concurrent=1)
        task_id = manager.submit(TaskParams(text="Delete me"), task_id="to_delete")

        time.sleep(0.5)

        deleted = manager.delete_task(task_id)
        assert deleted is True
        assert manager.get_status(task_id) is None

        manager.shutdown(wait=True)


# ===========================================================================
# batch tests
# ===========================================================================


class TestBatch:
    """Test batch video generation."""

    def test_batch_config_defaults(self):
        from bookai.batch import BatchConfig

        cfg = BatchConfig()
        assert cfg.video_count == 3
        assert cfg.shuffle_stock is True
        assert cfg.vary_transitions is True

    def test_batch_result(self):
        from bookai.batch import BatchResult

        r = BatchResult(batch_id="b1", total=3, succeeded=2, failed=1)
        assert r.ok  # At least 1 succeeded
        assert r.total == 3

    def test_batch_result_none_ok(self):
        from bookai.batch import BatchResult

        r = BatchResult(batch_id="b1", total=3, succeeded=0, failed=3)
        assert not r.ok

    def test_build_variant_config(self):
        from bookai.batch import BatchConfig, _build_variant_config

        cfg = BatchConfig(vary_transitions=True, vary_aspect=False)

        # Different indices should yield different transitions
        configs = [_build_variant_config(cfg, i) for i in range(5)]
        transitions = {c.transition for c in configs}
        assert len(transitions) > 1  # Should have variation

    def test_build_variant_config_no_vary(self):
        from bookai.batch import BatchConfig, _build_variant_config

        cfg = BatchConfig(
            vary_transitions=False,
            vary_bgm=False,
            vary_aspect=False,
            transition="zoom_in",
        )

        configs = [_build_variant_config(cfg, i) for i in range(3)]
        assert all(c.transition == "zoom_in" for c in configs)

    def test_build_variant_config_vary_aspect(self):
        from bookai.batch import BatchConfig, _build_variant_config

        cfg = BatchConfig(vary_aspect=True)

        configs = [_build_variant_config(cfg, i) for i in range(3)]
        aspects = [c.aspect for c in configs]
        assert len(set(aspects)) == 3  # 9:16, 16:9, 1:1


# ===========================================================================
# api model tests (no server required)
# ===========================================================================


class TestAPIModels:
    """Test API request/response models (if FastAPI available)."""

    def test_fastapi_availability(self):
        # Just check the import flag
        from bookai.api import FASTAPI_AVAILABLE
        # Don't assert True since FastAPI may not be installed
        assert isinstance(FASTAPI_AVAILABLE, bool)

    @pytest.mark.skipif(
        not __import__("bookai.api", fromlist=["FASTAPI_AVAILABLE"]).FASTAPI_AVAILABLE,
        reason="FastAPI not installed",
    )
    def test_video_request_defaults(self):
        from bookai.api import VideoRequest

        req = VideoRequest()
        assert req.aspect == "9:16"
        assert req.tts_provider == "edge_tts"
        assert req.subtitle_enabled is True

    @pytest.mark.skipif(
        not __import__("bookai.api", fromlist=["FASTAPI_AVAILABLE"]).FASTAPI_AVAILABLE,
        reason="FastAPI not installed",
    )
    def test_batch_request(self):
        from bookai.api import BatchRequest

        req = BatchRequest(text="Hello", video_count=5)
        assert req.video_count == 5

    @pytest.mark.skipif(
        not __import__("bookai.api", fromlist=["FASTAPI_AVAILABLE"]).FASTAPI_AVAILABLE,
        reason="FastAPI not installed",
    )
    def test_health_response(self):
        from bookai.api import HealthResponse

        h = HealthResponse()
        assert h.status == "ok"
        assert h.version == "0.2.0"

    @pytest.mark.skipif(
        not __import__("bookai.api", fromlist=["FASTAPI_AVAILABLE"]).FASTAPI_AVAILABLE,
        reason="FastAPI not installed",
    )
    def test_build_script_from_request(self):
        from bookai.api import VideoRequest, _build_script_from_request

        req = VideoRequest(text="Hello world")
        script = _build_script_from_request(req)
        assert script is not None
        assert script.body == "Hello world"

        req2 = VideoRequest(script_hook="Hook!", script_body="Body", script_cta="CTA")
        script2 = _build_script_from_request(req2)
        assert script2.hook == "Hook!"
        assert script2.body == "Body"
        assert script2.cta == "CTA"

        req3 = VideoRequest()  # No text, no script
        assert _build_script_from_request(req3) is None
