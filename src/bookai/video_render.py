"""Video rendering module for BookAI — v2 (MoviePy engine).

Combines TTS audio + background (cover/stock video/solid) + subtitle overlay +
BGM + transitions into production-ready short videos for TikTok/Reels/YouTube.

Upgraded from FFmpeg subprocess to MoviePy for compositing, while keeping FFmpeg
for encoding. Inspired by MoneyPrinterTurbo's video pipeline.

Output formats: 1080×1920 (9:16), 1920×1080 (16:9), 1080×1080 (1:1).

Usage::

    from bookai.video_render import render_radio_video, VideoConfig

    cfg = VideoConfig(aspect="9:16", transition="fade_in")
    result = render_radio_video(
        script=radio_script,
        audio_path="output/script_001.mp3",
        cover_image="cover.jpg",
        subtitle_path="output/script_001.srt",
        output_path="output/video_001.mp4",
        config=cfg,
    )
"""

from __future__ import annotations

import gc
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Try MoviePy, fallback to FFmpeg-only mode
# ---------------------------------------------------------------------------

try:
    from moviepy import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        TextClip,
        VideoFileClip,
        afx,
        vfx,
    )

    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"
FPS = 30
_VIDEO_DURATION_SAFETY_MARGIN = 0.1

# Supported hardware codecs (tried in order after software libx264)
_SUPPORTED_CODECS = (
    "libx264",
    "h264_nvenc",
    "h264_amf",
    "h264_qsv",
    "h264_videotoolbox",
)


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------


@dataclass
class VideoConfig:
    """Full video rendering configuration."""

    # Dimensions
    aspect: str = "9:16"              # "9:16", "16:9", "1:1"
    fps: int = FPS

    # Text
    font_name: str = ""               # path to .ttf, empty = auto-detect
    font_size: int = 52
    hook_font_size: int = 64
    font_color: str = "#FFFFFF"
    bg_color: str = "black"

    # Cover/background
    cover_blur: bool = True
    blur_strength: int = 20
    overlay_opacity: float = 0.55

    # Text layout
    max_chars_per_line: int = 30
    watermark: str = ""

    # Encoding
    video_bitrate: str = "4M"
    audio_bitrate: str = AUDIO_BITRATE
    codec: str = "libx264"
    preset: str = "fast"

    # Transitions (Phase 1 upgrade)
    transition: str = "fade_in"       # fade_in, fade_out, slide_in, slide_out,
    #                                   zoom_in, zoom_out, shuffle, none
    transition_duration: float = 0.5

    # BGM (Phase 1 upgrade)
    bgm_mode: str = "none"            # random, specific, none
    bgm_file: str = ""
    bgm_volume: float = 0.15
    voice_volume: float = 1.0

    # Subtitle (Phase 1 upgrade)
    subtitle_enabled: bool = True
    subtitle_position: str = "bottom"  # top, center, bottom, custom
    subtitle_font_size: int = 48
    subtitle_color: str = "#FFFFFF"
    subtitle_stroke_color: str = "#000000"
    subtitle_stroke_width: float = 2.0

    @property
    def width(self) -> int:
        return _aspect_to_resolution(self.aspect)[0]

    @property
    def height(self) -> int:
        return _aspect_to_resolution(self.aspect)[1]

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    def _resolve_font(self) -> str:
        """Find a usable font file."""
        if self.font_name and Path(self.font_name).exists():
            return self.font_name
        candidates = [
            "resource/fonts/BeVietnamPro-SemiBold.ttf",
            "resource/fonts/BeVietnamPro-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        ]
        for c in candidates:
            if Path(c).exists():
                return c
        return ""


def _aspect_to_resolution(aspect: str) -> tuple[int, int]:
    """Convert aspect ratio string to (width, height)."""
    mapping = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
    return mapping.get(aspect, (1080, 1920))


@dataclass
class VideoResult:
    """Result of a video render operation."""

    output_path: Path
    duration_seconds: float = 0.0
    file_size_mb: float = 0.0
    ok: bool = True
    error: str = ""
    engine: str = "moviepy"  # "moviepy" or "ffmpeg"


# ---------------------------------------------------------------------------
# Material clip helper (inspired by MPT SubClippedVideoClip)
# ---------------------------------------------------------------------------


@dataclass
class ClipSegment:
    """Represents a video/image clip segment for compositing."""

    file_path: str
    start_time: float = 0.0
    end_time: float = 0.0
    width: int = 0
    height: int = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


# ---------------------------------------------------------------------------
# Main render functions
# ---------------------------------------------------------------------------


def render_radio_video(
    script: object,
    audio_path: str | Path,
    output_path: str | Path,
    cover_image: str | Path | None = None,
    subtitle_path: str | Path | None = None,
    stock_videos: list[str] | None = None,
    config: VideoConfig | None = None,
) -> VideoResult:
    """Render a complete TikTok/Reels video from a RadioScript + audio.

    Supports both MoviePy (preferred) and FFmpeg-only (fallback) engines.

    Layout:
        - Background: stock video clips / blurred cover / solid color
        - Hook text: large, centered, first 3s
        - Subtitles: synced to audio via SRT
        - BGM: mixed underneath voice
        - CTA: shown in final section
        - Transitions: between clips (if stock_videos provided)

    Args:
        script: RadioScript from content_studio.
        audio_path: Path to MP3/WAV voiceover.
        output_path: Output MP4 path.
        cover_image: Optional book cover for background.
        subtitle_path: Optional SRT file for subtitle overlay.
        stock_videos: Optional list of stock video file paths.
        config: VideoConfig.

    Returns:
        VideoResult.
    """
    cfg = config or VideoConfig()
    output_path = Path(output_path)
    audio_path = Path(audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        return VideoResult(output_path=output_path, ok=False,
                           error=f"Audio not found: {audio_path}")

    duration = _get_duration(audio_path)
    if duration <= 0:
        return VideoResult(output_path=output_path, ok=False,
                           error="Could not determine audio duration")

    # Choose engine
    if MOVIEPY_AVAILABLE:
        return _render_moviepy(
            script=script,
            audio_path=audio_path,
            output_path=output_path,
            cover_image=cover_image,
            subtitle_path=subtitle_path,
            stock_videos=stock_videos,
            duration=duration,
            cfg=cfg,
        )
    else:
        return _render_ffmpeg_legacy(
            script=script,
            audio_path=audio_path,
            output_path=output_path,
            cover_image=cover_image,
            duration=duration,
            cfg=cfg,
        )


def render_quote_video(
    quote_text: str,
    audio_path: str | Path,
    output_path: str | Path,
    book_title: str = "",
    author: str = "",
    cover_image: str | Path | None = None,
    config: VideoConfig | None = None,
) -> VideoResult:
    """Render a short quote video (15-30s) with ZoomKenBurns effect."""
    cfg = config or VideoConfig()
    cfg.transition = "zoom_in"  # Ken Burns is perfect for quote videos
    output_path = Path(output_path)
    audio_path = Path(audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        return VideoResult(output_path=output_path, ok=False,
                           error=f"Audio not found: {audio_path}")

    duration = _get_duration(audio_path)
    if duration <= 0:
        return VideoResult(output_path=output_path, ok=False, error="Invalid audio")

    if not MOVIEPY_AVAILABLE:
        return _render_ffmpeg_legacy_quote(
            quote_text, audio_path, output_path, book_title, author, cover_image, duration, cfg
        )

    w, h = cfg.width, cfg.height
    font_path = cfg._resolve_font()

    try:
        # Background
        bg_clip = _make_background_clip(cover_image, w, h, duration, cfg)

        # Apply Ken Burns zoom
        from bookai.video_effects import zoom_ken_burns
        bg_clip = zoom_ken_burns(bg_clip, zoom_ratio=1.12, direction="in", pan="center")

        # Quote text
        attribution = f"— {author}, {book_title}" if author and book_title else book_title or author

        txt_kwargs = {
            "text": quote_text[:300],
            "font_size": cfg.font_size,
            "color": cfg.font_color,
            "stroke_color": "#000000",
            "stroke_width": 2.0,
            "text_align": "center",
            "size": (int(w * 0.85), None),
            "method": "caption",
        }
        if font_path:
            txt_kwargs["font"] = font_path

        quote_clip = (
            TextClip(**txt_kwargs)
            .with_duration(duration)
            .with_position(("center", "center"))
        )

        layers = [bg_clip, quote_clip]

        if attribution:
            attr_kwargs = {
                "text": attribution,
                "font_size": int(cfg.font_size * 0.6),
                "color": "#FFFFFF",
                "text_align": "center",
                "size": (int(w * 0.8), None),
                "method": "caption",
            }
            if font_path:
                attr_kwargs["font"] = font_path
            attr_clip = (
                TextClip(**attr_kwargs)
                .with_duration(duration)
                .with_position(("center", int(h * 0.72)))
            )
            layers.append(attr_clip)

        # Compose
        video = CompositeVideoClip(layers, size=(w, h)).with_duration(duration)

        # Add audio
        audio_clip = AudioFileClip(str(audio_path))

        # BGM
        video_with_audio = _add_audio_and_bgm(video, audio_clip, cfg)

        # Write
        video_with_audio.write_videofile(
            str(output_path),
            fps=cfg.fps,
            codec=cfg.codec,
            preset=cfg.preset,
            audio_codec=AUDIO_CODEC,
            audio_bitrate=cfg.audio_bitrate,
            logger=None,
        )

        _close_clips(video_with_audio, video, bg_clip, quote_clip, audio_clip)

        return VideoResult(
            output_path=output_path,
            duration_seconds=_get_duration(output_path),
            file_size_mb=output_path.stat().st_size / (1024 * 1024),
            ok=True,
            engine="moviepy",
        )

    except Exception as e:
        return VideoResult(output_path=output_path, ok=False, error=str(e), engine="moviepy")


def render_slideshow_video(
    slides: list[dict],
    output_path: str | Path,
    audio_path: str | Path | None = None,
    seconds_per_slide: float = 4.0,
    config: VideoConfig | None = None,
) -> VideoResult:
    """Render a slideshow video with transitions between slides."""
    cfg = config or VideoConfig()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not slides:
        return VideoResult(output_path=output_path, ok=False, error="No slides")

    if not MOVIEPY_AVAILABLE:
        return _render_ffmpeg_legacy_slideshow(slides, output_path, audio_path, seconds_per_slide, cfg)

    w, h = cfg.width, cfg.height
    font_path = cfg._resolve_font()

    try:
        slide_clips = []
        for slide in slides:
            text = slide.get("text", "")
            img = slide.get("image")

            bg = _make_background_clip(img, w, h, seconds_per_slide, cfg)

            # Apply transition
            from bookai.video_effects import apply_transition
            bg = apply_transition(bg, cfg.transition, cfg.transition_duration)

            # Text overlay
            if text:
                txt_kwargs = {
                    "text": text[:300],
                    "font_size": cfg.font_size,
                    "color": cfg.font_color,
                    "stroke_color": "#000000",
                    "stroke_width": 1.5,
                    "text_align": "center",
                    "size": (int(w * 0.85), None),
                    "method": "caption",
                }
                if font_path:
                    txt_kwargs["font"] = font_path

                txt_clip = (
                    TextClip(**txt_kwargs)
                    .with_duration(seconds_per_slide)
                    .with_position(("center", "center"))
                )
                slide_clip = CompositeVideoClip([bg, txt_clip], size=(w, h))
            else:
                slide_clip = bg

            slide_clips.append(slide_clip.with_duration(seconds_per_slide))

        # Concatenate
        from moviepy import concatenate_videoclips
        video = concatenate_videoclips(slide_clips, method="compose")

        # Audio
        if audio_path and Path(audio_path).exists():
            audio_clip = AudioFileClip(str(audio_path))
            video = _add_audio_and_bgm(video, audio_clip, cfg)

        video.write_videofile(
            str(output_path),
            fps=cfg.fps,
            codec=cfg.codec,
            preset=cfg.preset,
            audio_codec=AUDIO_CODEC,
            audio_bitrate=cfg.audio_bitrate,
            logger=None,
        )

        _close_clips(video, *slide_clips)

        return VideoResult(
            output_path=output_path,
            duration_seconds=_get_duration(output_path),
            file_size_mb=output_path.stat().st_size / (1024 * 1024),
            ok=True,
            engine="moviepy",
        )

    except Exception as e:
        return VideoResult(output_path=output_path, ok=False, error=str(e), engine="moviepy")


# ---------------------------------------------------------------------------
# MoviePy rendering engine
# ---------------------------------------------------------------------------


def _render_moviepy(
    script: object,
    audio_path: Path,
    output_path: Path,
    cover_image,
    subtitle_path,
    stock_videos: list[str] | None,
    duration: float,
    cfg: VideoConfig,
) -> VideoResult:
    """Full MoviePy render pipeline."""
    w, h = cfg.width, cfg.height
    font_path = cfg._resolve_font()

    try:
        # Step 1: Build background
        if stock_videos and any(Path(v).exists() for v in stock_videos):
            bg_clip = _build_stock_video_background(stock_videos, w, h, duration, cfg)
        else:
            bg_clip = _make_background_clip(cover_image, w, h, duration, cfg)

        # Step 2: Apply transition to background
        from bookai.video_effects import apply_transition
        bg_clip = apply_transition(bg_clip, cfg.transition, cfg.transition_duration)

        layers = [bg_clip]

        # Step 3: Hook text overlay (first 3s)
        hook = getattr(script, "hook", "") or ""
        if hook:
            hook_kwargs = {
                "text": hook[:120],
                "font_size": cfg.hook_font_size,
                "color": cfg.font_color,
                "stroke_color": "#000000",
                "stroke_width": 2.0,
                "text_align": "center",
                "size": (int(w * 0.85), None),
                "method": "caption",
            }
            if font_path:
                hook_kwargs["font"] = font_path

            hook_clip = (
                TextClip(**hook_kwargs)
                .with_duration(3.0)
                .with_start(0)
                .with_position(("center", int(h * 0.12)))
            )
            layers.append(hook_clip)

        # Step 4: CTA text overlay (last ~12s)
        cta = getattr(script, "cta", "") or ""
        cta_start = max(duration - 12.0, duration * 0.85)
        if cta:
            cta_kwargs = {
                "text": cta[:200],
                "font_size": int(cfg.font_size * 0.9),
                "color": "#FFD700",  # gold
                "stroke_color": "#000000",
                "stroke_width": 1.5,
                "text_align": "center",
                "size": (int(w * 0.85), None),
                "method": "caption",
            }
            if font_path:
                cta_kwargs["font"] = font_path

            cta_clip = (
                TextClip(**cta_kwargs)
                .with_duration(duration - cta_start)
                .with_start(cta_start)
                .with_position(("center", int(h * 0.82)))
            )
            layers.append(cta_clip)

        # Step 5: Watermark
        if cfg.watermark:
            wm_kwargs = {
                "text": cfg.watermark,
                "font_size": 28,
                "color": "white",
            }
            if font_path:
                wm_kwargs["font"] = font_path
            wm_clip = (
                TextClip(**wm_kwargs)
                .with_duration(duration)
                .with_position(("right", "bottom"))
                .with_effects([vfx.MultiplyColor(0.6)])
            )
            layers.append(wm_clip)

        # Step 6: Compose video
        video = CompositeVideoClip(layers, size=(w, h)).with_duration(duration)

        # Step 7: Burn subtitles
        if subtitle_path and Path(subtitle_path).exists() and cfg.subtitle_enabled:
            from bookai.subtitle import SubtitleConfig, burn_subtitles
            sub_cfg = SubtitleConfig(
                enabled=True,
                position=cfg.subtitle_position,
                font_size=cfg.subtitle_font_size,
                text_color=cfg.subtitle_color,
                stroke_color=cfg.subtitle_stroke_color,
                stroke_width=cfg.subtitle_stroke_width,
            )
            video = burn_subtitles(video, subtitle_path, config=sub_cfg)

        # Step 8: Audio + BGM
        audio_clip = AudioFileClip(str(audio_path))
        video = _add_audio_and_bgm(video, audio_clip, cfg)

        # Step 9: Write output
        video.write_videofile(
            str(output_path),
            fps=cfg.fps,
            codec=cfg.codec,
            preset=cfg.preset,
            audio_codec=AUDIO_CODEC,
            audio_bitrate=cfg.audio_bitrate,
            logger=None,
        )

        _close_clips(video, bg_clip, audio_clip)

        result_dur = _get_duration(output_path)
        result_size = output_path.stat().st_size / (1024 * 1024) if output_path.exists() else 0

        return VideoResult(
            output_path=output_path,
            duration_seconds=result_dur,
            file_size_mb=result_size,
            ok=True,
            engine="moviepy",
        )

    except Exception as e:
        # Fallback to FFmpeg if MoviePy fails
        return _render_ffmpeg_legacy(
            script=script,
            audio_path=audio_path,
            output_path=output_path,
            cover_image=cover_image,
            duration=duration,
            cfg=cfg,
        )


# ---------------------------------------------------------------------------
# MoviePy helpers
# ---------------------------------------------------------------------------


def _make_background_clip(
    cover_image, w: int, h: int, duration: float, cfg: VideoConfig
):
    """Create background clip from cover image or solid color."""
    if cover_image and Path(str(cover_image)).exists():
        try:
            img_clip = ImageClip(str(cover_image)).resized((w, h))

            if cfg.cover_blur:
                # Apply blur via PIL
                from PIL import Image, ImageFilter
                import numpy as np

                frame = img_clip.get_frame(0)
                pil_img = Image.fromarray(frame)
                blurred = pil_img.filter(ImageFilter.GaussianBlur(radius=cfg.blur_strength))
                img_clip = ImageClip(np.array(blurred))

            # Dark overlay
            overlay = ColorClip(
                size=(w, h), color=(0, 0, 0)
            ).with_effects([vfx.MultiplyColor(cfg.overlay_opacity)])

            bg = CompositeVideoClip(
                [img_clip, overlay], size=(w, h)
            ).with_duration(duration)

            return bg
        except Exception:
            pass

    # Solid color fallback
    return ColorClip(size=(w, h), color=_parse_color(cfg.bg_color)).with_duration(duration)


def _build_stock_video_background(
    video_paths: list[str], w: int, h: int, target_duration: float, cfg: VideoConfig
):
    """Build background from stock video clips, concatenated to fill duration."""
    from moviepy import concatenate_videoclips

    clips = []
    total = 0.0

    for vp in video_paths:
        if not Path(vp).exists():
            continue
        try:
            clip = VideoFileClip(vp, audio=False)
            # Resize to target
            clip = clip.resized((w, h))
            clips.append(clip)
            total += clip.duration
            if total >= target_duration + _VIDEO_DURATION_SAFETY_MARGIN:
                break
        except Exception:
            continue

    if not clips:
        return ColorClip(size=(w, h), color=(0, 0, 0)).with_duration(target_duration)

    # Loop if not enough footage
    while total < target_duration:
        for clip in list(clips):
            clips.append(clip.copy())
            total += clip.duration
            if total >= target_duration:
                break

    video = concatenate_videoclips(clips, method="compose")
    video = video.subclipped(0, min(target_duration, video.duration))

    # Dark overlay for readability
    overlay = ColorClip(
        size=(w, h), color=(0, 0, 0)
    ).with_effects([vfx.MultiplyColor(0.3)])
    overlay = overlay.with_duration(video.duration)

    return CompositeVideoClip([video, overlay], size=(w, h)).with_duration(video.duration)


def _add_audio_and_bgm(video_clip, audio_clip, cfg: VideoConfig):
    """Add voice audio + optional BGM to video."""
    voice = audio_clip

    if cfg.voice_volume != 1.0:
        voice = voice.with_effects([afx.MultiplyVolume(cfg.voice_volume)])

    # BGM
    if cfg.bgm_mode != "none":
        from bookai.bgm import get_bgm_file
        bgm_path = get_bgm_file(mode=cfg.bgm_mode, filename=cfg.bgm_file)

        if bgm_path and Path(bgm_path).exists():
            try:
                bgm_clip = AudioFileClip(bgm_path)

                # Loop BGM if needed
                if bgm_clip.duration < voice.duration:
                    loops = int(voice.duration / bgm_clip.duration) + 1
                    bgm_clip = bgm_clip.with_effects([afx.AudioLoop(nloops=loops)])

                bgm_clip = bgm_clip.subclipped(0, voice.duration)
                bgm_clip = bgm_clip.with_effects([afx.MultiplyVolume(cfg.bgm_volume)])

                # Fade out BGM at end
                fade = min(2.0, voice.duration * 0.1)
                bgm_clip = bgm_clip.with_effects([afx.AudioFadeOut(fade)])

                mixed = CompositeAudioClip([voice, bgm_clip])
                return video_clip.with_audio(mixed)
            except Exception:
                pass

    return video_clip.with_audio(voice)


def _close_clips(*clips):
    """Safely close MoviePy clips and free memory."""
    for clip in clips:
        try:
            if hasattr(clip, "close"):
                clip.close()
        except Exception:
            pass
    gc.collect()


def _parse_color(color: str) -> tuple[int, int, int]:
    """Parse color string to RGB tuple."""
    color = color.strip().lower()
    named = {
        "black": (0, 0, 0), "white": (255, 255, 255),
        "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
    }
    if color in named:
        return named[color]
    if color.startswith("#") and len(color) >= 7:
        return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
    return (0, 0, 0)


# ---------------------------------------------------------------------------
# FFmpeg legacy fallback (original BookAI v1 logic)
# ---------------------------------------------------------------------------


def _render_ffmpeg_legacy(
    script, audio_path, output_path, cover_image, duration, cfg
) -> VideoResult:
    """Original FFmpeg subprocess rendering (backward compatibility)."""
    hook = getattr(script, "hook", "") or ""
    cta = getattr(script, "cta", "") or ""
    cta_start = max(duration - 12.0, duration * 0.85)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        bg_video = _ffmpeg_build_background(
            tmp_path / "bg.mp4", duration=duration, cover_image=cover_image, cfg=cfg
        )
        with_text = _ffmpeg_add_text(
            bg_video, tmp_path / "with_text.mp4",
            hook=hook, cta=cta, cta_start=cta_start, cfg=cfg
        )
        result = _ffmpeg_merge_audio(with_text, audio_path, output_path, cfg=cfg)

    if result.ok and output_path.exists():
        result.duration_seconds = _get_duration(output_path)
        result.file_size_mb = output_path.stat().st_size / (1024 * 1024)
        result.engine = "ffmpeg"

    return result


def _render_ffmpeg_legacy_quote(
    quote_text, audio_path, output_path, book_title, author, cover_image, duration, cfg
) -> VideoResult:
    """FFmpeg fallback for quote video."""
    attribution = f"— {author}, {book_title}" if author and book_title else book_title or author

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bg = _ffmpeg_build_background(tmp_path / "bg.mp4", duration, cover_image, cfg)
        with_text = _ffmpeg_add_centered_text(bg, tmp_path / "text.mp4", quote_text, attribution, cfg)
        result = _ffmpeg_merge_audio(with_text, audio_path, output_path, cfg=cfg)

    if result.ok and output_path.exists():
        result.duration_seconds = _get_duration(output_path)
        result.file_size_mb = output_path.stat().st_size / (1024 * 1024)
        result.engine = "ffmpeg"
    return result


def _render_ffmpeg_legacy_slideshow(slides, output_path, audio_path, sps, cfg) -> VideoResult:
    """FFmpeg fallback for slideshow."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        slide_files = []
        for i, s in enumerate(slides):
            bg = _ffmpeg_build_background(tmp_path / f"bg_{i}.mp4", sps, s.get("image"), cfg)
            txt = _ffmpeg_add_centered_text(bg, tmp_path / f"slide_{i}.mp4", s.get("text", ""), "", cfg)
            slide_files.append(txt)

        concat_list = tmp_path / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p}'" for p in slide_files), encoding="utf-8")
        concat_out = tmp_path / "concat.mp4"
        _run_ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                      "-i", str(concat_list), "-c", "copy", str(concat_out)])

        if audio_path and Path(audio_path).exists():
            result = _ffmpeg_merge_audio(concat_out, Path(audio_path), output_path, cfg=cfg)
        else:
            shutil.copy(str(concat_out), str(output_path))
            result = VideoResult(output_path=output_path, ok=True, engine="ffmpeg")

    if result.ok and output_path.exists():
        result.duration_seconds = _get_duration(output_path)
        result.file_size_mb = output_path.stat().st_size / (1024 * 1024)
    return result


# ---------------------------------------------------------------------------
# FFmpeg building blocks (v1 code, preserved)
# ---------------------------------------------------------------------------


def _ffmpeg_build_background(output, duration, cover_image, cfg):
    w, h = cfg.width, cfg.height
    if cover_image and Path(str(cover_image)).exists():
        vf_parts = [
            f"scale={w}:{h}:force_original_aspect_ratio=increase",
            f"crop={w}:{h}",
        ]
        if cfg.cover_blur:
            vf_parts.append(f"gblur=sigma={cfg.blur_strength}")
        vf = ",".join(v for v in vf_parts if v)
        overlay_color = f"color=black:size={w}x{h}:rate={cfg.fps}"
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(cover_image),
            "-f", "lavfi", "-i", overlay_color,
            "-filter_complex",
            f"[0:v]{vf}[bg];[bg][1:v]blend=all_mode=multiply:all_opacity={cfg.overlay_opacity}[v]",
            "-map", "[v]", "-t", str(duration), "-r", str(cfg.fps),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(output),
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"color=c={cfg.bg_color}:size={w}x{h}:rate={cfg.fps}:duration={duration}",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(output),
        ]
    _run_ffmpeg(cmd)
    return output


def _ffmpeg_add_text(input_video, output, hook, cta, cta_start, cfg):
    hook_esc = _escape_ffmpeg_text(hook[:120])
    cta_esc = _escape_ffmpeg_text(cta[:200])
    hook_w = _wrap_text(hook_esc, cfg.max_chars_per_line)
    cta_w = _wrap_text(cta_esc, cfg.max_chars_per_line)

    vf = (
        f"drawtext=text='{hook_w}':fontsize={cfg.hook_font_size}:fontcolor={cfg.font_color}:"
        f"x=(w-tw)/2:y=100:enable='between(t,0,3)':shadowcolor=black:shadowx=2:shadowy=2,"
        f"drawtext=text='{cta_w}':fontsize={cfg.font_size}:fontcolor=yellow:"
        f"x=(w-tw)/2:y=(h-200):enable='gte(t,{cta_start:.1f})':"
        "shadowcolor=black:shadowx=2:shadowy=2"
    )
    if cfg.watermark:
        wm = _escape_ffmpeg_text(cfg.watermark)
        vf += f",drawtext=text='{wm}':fontsize=28:fontcolor=white@0.6:x=(w-tw-20):y=(h-th-20)"

    cmd = [
        "ffmpeg", "-y", "-i", str(input_video), "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "copy",
        str(output),
    ]
    _run_ffmpeg(cmd)
    return output


def _ffmpeg_add_centered_text(input_video, output, main_text, subtitle, cfg):
    main_esc = _escape_ffmpeg_text(main_text[:300])
    main_w = _wrap_text(main_esc, cfg.max_chars_per_line)
    vf = (
        f"drawtext=text='{main_w}':fontsize={cfg.font_size}:fontcolor={cfg.font_color}:"
        "x=(w-tw)/2:y=(h-th)/2:shadowcolor=black:shadowx=3:shadowy=3"
    )
    if subtitle:
        sub_esc = _escape_ffmpeg_text(subtitle[:100])
        vf += (
            f",drawtext=text='{sub_esc}':fontsize={int(cfg.font_size * 0.65)}:"
            "fontcolor=white@0.8:x=(w-tw)/2:y=(h*3/4):shadowcolor=black:shadowx=2:shadowy=2"
        )
    cmd = [
        "ffmpeg", "-y", "-i", str(input_video), "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "copy",
        str(output),
    ]
    _run_ffmpeg(cmd)
    return output


def _ffmpeg_merge_audio(video, audio, output, cfg):
    cmd = [
        "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
        "-map", "0:v", "-map", "1:a", "-c:v", "copy",
        "-c:a", "aac", "-b:a", cfg.audio_bitrate, "-shortest", str(output),
    ]
    returncode, stderr = _run_ffmpeg(cmd)
    if returncode != 0:
        return VideoResult(output_path=output, ok=False,
                           error=f"FFmpeg merge failed:\n{stderr[-500:]}", engine="ffmpeg")
    return VideoResult(output_path=output, ok=True, engine="ffmpeg")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _run_ffmpeg(cmd: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "FFmpeg timed out"
    except FileNotFoundError:
        return -1, "ffmpeg not found — install with: sudo apt install ffmpeg"


def _get_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _escape_ffmpeg_text(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("%", "\\%")
    return text


def _wrap_text(text: str, max_chars: int) -> str:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return "\\n".join(lines)


def check_ffmpeg() -> bool:
    """Return True if ffmpeg is available."""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def check_moviepy() -> bool:
    """Return True if MoviePy is available."""
    return MOVIEPY_AVAILABLE
