"""Batch Video Generation for BookAI — Phase 2.

Generate multiple video variants from a single script for A/B testing.
Each variant can use different stock footage, transitions, BGM, voices.

Inspired by MoneyPrinterTurbo's video_count parameter.

Usage::

    from bookai.batch import batch_generate, BatchConfig

    config = BatchConfig(
        video_count=3,
        shuffle_stock=True,
        vary_transitions=True,
    )
    results = batch_generate(script, audio_path, config)
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("bookai.batch")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class BatchConfig:
    """Configuration for batch video generation."""

    # Number of variants
    video_count: int = 3

    # Variation options
    shuffle_stock: bool = True       # Randomize stock footage order per variant
    vary_transitions: bool = True    # Use different transitions per variant
    vary_bgm: bool = True           # Use different BGM tracks per variant
    vary_aspect: bool = False        # Generate in different aspect ratios

    # Base video config (shared across variants)
    aspect: str = "9:16"
    transition: str = "fade_in"
    bgm_mode: str = "random"
    bgm_file: str = ""
    subtitle_enabled: bool = True
    subtitle_position: str = "bottom"

    # Stock video
    stock_search_terms: list[str] = field(default_factory=list)
    pexels_api_key: str = ""

    # TTS
    tts_provider: str = "edge_tts"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    tts_rate: str = "+0%"

    # Output
    output_dir: str = "output"
    filename_prefix: str = "variant"


@dataclass
class BatchResult:
    """Result of a batch generation run."""

    batch_id: str
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    variants: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.succeeded > 0


# ---------------------------------------------------------------------------
# Available variations
# ---------------------------------------------------------------------------

_TRANSITION_OPTIONS = [
    "fade_in", "fade_out", "slide_in", "slide_out",
    "zoom_in", "zoom_out", "shuffle",
]

_ASPECT_OPTIONS = ["9:16", "16:9", "1:1"]


# ---------------------------------------------------------------------------
# Main batch function
# ---------------------------------------------------------------------------


def batch_generate(
    script: object,
    audio_path: str | Path,
    config: BatchConfig | None = None,
    cover_image: str | Path | None = None,
    subtitle_path: str | Path | None = None,
    stock_videos: list[str] | None = None,
    on_progress: Any = None,
) -> BatchResult:
    """Generate N video variants from one script + audio.

    Each variant may differ in:
        - Stock footage ordering (shuffled)
        - Transition effect
        - BGM track
        - Aspect ratio (if vary_aspect=True)

    Args:
        script: RadioScript object.
        audio_path: Path to voice audio file.
        config: BatchConfig.
        cover_image: Optional cover image.
        subtitle_path: Optional SRT file.
        stock_videos: Optional list of stock video paths.
        on_progress: Optional callback(variant_index, total, status_msg).

    Returns:
        BatchResult with all variant info.
    """
    cfg = config or BatchConfig()
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    batch_dir = Path(cfg.output_dir) / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    result = BatchResult(batch_id=batch_id, total=cfg.video_count)

    from bookai.video_render import VideoConfig, render_radio_video

    for i in range(cfg.video_count):
        variant_name = f"{cfg.filename_prefix}_{i + 1:03d}"
        variant_dir = batch_dir / variant_name

        if on_progress:
            try:
                on_progress(i, cfg.video_count, f"Rendering {variant_name}...")
            except Exception:
                pass

        # Build variant-specific config
        video_cfg = _build_variant_config(cfg, i)

        # Shuffle stock videos for this variant
        variant_stocks = None
        if stock_videos:
            variant_stocks = list(stock_videos)
            if cfg.shuffle_stock:
                random.shuffle(variant_stocks)

        # Determine output path
        output_path = batch_dir / f"{variant_name}.mp4"

        try:
            video_result = render_radio_video(
                script=script,
                audio_path=str(audio_path),
                output_path=str(output_path),
                cover_image=str(cover_image) if cover_image else None,
                subtitle_path=str(subtitle_path) if subtitle_path else None,
                stock_videos=variant_stocks,
                config=video_cfg,
            )

            variant_info = {
                "name": variant_name,
                "output_path": str(output_path),
                "ok": video_result.ok,
                "error": video_result.error,
                "duration": video_result.duration_seconds,
                "size_mb": video_result.file_size_mb,
                "engine": video_result.engine,
                "config": {
                    "aspect": video_cfg.aspect,
                    "transition": video_cfg.transition,
                    "bgm_mode": video_cfg.bgm_mode,
                },
            }
            result.variants.append(variant_info)

            if video_result.ok:
                result.succeeded += 1
                result.files.append(str(output_path))
                logger.info(f"Variant {variant_name}: OK ({video_result.duration_seconds:.1f}s)")
            else:
                result.failed += 1
                result.errors.append(f"{variant_name}: {video_result.error}")
                logger.warning(f"Variant {variant_name}: FAILED — {video_result.error}")

        except Exception as e:
            result.failed += 1
            result.errors.append(f"{variant_name}: {e}")
            result.variants.append({
                "name": variant_name, "ok": False, "error": str(e),
            })
            logger.exception(f"Variant {variant_name} exception")

    result.duration_seconds = time.time() - start_time

    if on_progress:
        try:
            on_progress(
                cfg.video_count, cfg.video_count,
                f"Done: {result.succeeded}/{result.total} succeeded",
            )
        except Exception:
            pass

    logger.info(
        f"Batch {batch_id} complete: {result.succeeded}/{result.total} OK "
        f"in {result.duration_seconds:.1f}s"
    )
    return result


def batch_generate_async(
    script: object,
    audio_path: str | Path,
    config: BatchConfig | None = None,
    **kwargs,
) -> str:
    """Submit batch generation to the task manager (non-blocking).

    Returns the task_id for tracking.
    """
    from bookai.task_manager import TaskManager, TaskParams, get_task_manager

    cfg = config or BatchConfig()
    manager = get_task_manager()

    params = TaskParams(
        task_type="batch",
        script=script,
        audio_path=str(audio_path),
        output_dir=cfg.output_dir,
        aspect=cfg.aspect,
        transition=cfg.transition,
        bgm_mode=cfg.bgm_mode,
        subtitle_enabled=cfg.subtitle_enabled,
        tts_provider=cfg.tts_provider,
        tts_voice=cfg.tts_voice,
        video_count=cfg.video_count,
    )

    return manager.submit(params)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_variant_config(cfg: BatchConfig, index: int):
    """Build a VideoConfig with variant-specific settings."""
    from bookai.video_render import VideoConfig

    # Start with base config
    transition = cfg.transition
    if cfg.vary_transitions:
        transition = _TRANSITION_OPTIONS[index % len(_TRANSITION_OPTIONS)]

    aspect = cfg.aspect
    if cfg.vary_aspect:
        aspect = _ASPECT_OPTIONS[index % len(_ASPECT_OPTIONS)]

    bgm_mode = cfg.bgm_mode
    if cfg.vary_bgm and bgm_mode == "none":
        bgm_mode = "random"

    return VideoConfig(
        aspect=aspect,
        transition=transition,
        bgm_mode=bgm_mode,
        bgm_file=cfg.bgm_file,
        subtitle_enabled=cfg.subtitle_enabled,
        subtitle_position=cfg.subtitle_position,
    )
