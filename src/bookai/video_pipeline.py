"""Full video creation pipeline for BookAI — inspired by MoneyPrinterTurbo.

Orchestrates the complete flow:
  Script → Search terms → Stock video/image fetch → TTS audio → SRT subtitle
  → Video clip+resize+transition → Concat → Subtitle overlay → Audio+BGM → Output

Supports three material sources:
  1. "pexels"/"pixabay" — auto-search & download stock footage by keywords
  2. "local" — user-provided images/videos from a folder
  3. "ai" — solid color / AI-generated backgrounds (fallback)

Usage::

    from bookai.video_pipeline import create_book_video, PipelineConfig

    result = create_book_video(
        script_text="...",
        book_title="Sách AI",
        config=PipelineConfig(
            material_source="pexels",
            pexels_api_key="...",
            subtitle_enabled=True,
        ),
        output_path="output/book_video.mp4",
    )
"""

from __future__ import annotations

import os
import random
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from bookai.bgm import get_bgm_file
from bookai.stock_video import (
    StockVideoConfig,
    search_and_download,
)
from bookai.subtitle import (
    generate_srt_from_tts,
)
from bookai.tts_providers import TTSConfig, tts_synthesize

# ---------------------------------------------------------------------------
# Pipeline Config
# ---------------------------------------------------------------------------


@dataclass
class PipelineConfig:
    """Full pipeline configuration."""

    # Material source: "pexels", "pixabay", "coverr", "local", "ai"
    material_source: str = "pexels"
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    coverr_api_key: str = ""
    local_material_dir: str = ""  # Folder with user images/videos

    # Video settings
    aspect: str = "9:16"  # "9:16", "16:9", "1:1"
    max_clip_duration: int = 5  # Max seconds per clip
    transition: str = "fade_in"  # none, fade_in, fade_out, slide_in, slide_out, shuffle
    concat_mode: str = "random"  # random, sequential

    # TTS
    tts_provider: str = "edge_tts"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    voice_volume: float = 1.0

    # Subtitle
    subtitle_enabled: bool = True
    subtitle_position: str = "bottom"  # top, center, bottom, custom
    subtitle_custom_y: float = 80.0
    subtitle_font_size: int = 24        # Smaller default — scales well on 1080p
    subtitle_font_name: str = ""
    subtitle_color: str = "#FFFFFF"
    subtitle_stroke_color: str = "#000000"
    subtitle_stroke_width: float = 1.5
    subtitle_bg_color: str = ""  # "#00000090" for semi-transparent black
    subtitle_bg_opacity: float = 0.6

    # Subtitle template (overrides individual subtitle settings when set)
    # Options: classic, capcut_white_box, capcut_dark_box, capcut_gradient_box,
    #          neon_glow, bold_impact, minimal_clean, karaoke_word, modern_pill
    subtitle_template: str = ""  # Empty = use individual settings above

    # BGM
    bgm_mode: str = "random"  # random, none, or specific file
    bgm_file: str = ""
    bgm_volume: float = 0.15

    # Output
    fps: int = 30
    codec: str = "libx264"
    preset: str = "medium"
    audio_bitrate: str = "192k"
    threads: int = 2

    # Search terms (auto-generated if empty)
    search_terms: list[str] = field(default_factory=list)

    # LLM-based keyword generation (MPT-style)
    keyword_mode: str = "llm"  # "llm" or "regex"
    match_script_order: bool = True
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Local material settings
    local_mode: str = "supplement"  # "only", "supplement", "priority"
    scan_recursive: bool = True

    # Video sections (hooks, title cards, outros)
    hook_style: str = ""  # Empty = no hook. Options: bold_question, shocking_fact, book_rating, quote_reveal, mystery
    hook_text: str = ""
    title_card_style: str = ""  # Empty = no title card. Options: book_cover, minimalist, gradient_card, split_screen
    outro_style: str = ""  # Empty = no outro. Options: subscribe_cta, rating_summary, next_book
    outro_text: str = "Cảm ơn đã xem!"
    cover_image_path: str = ""  # Book cover image for title card

    @property
    def width(self) -> int:
        return _aspect_to_resolution(self.aspect)[0]

    @property
    def height(self) -> int:
        return _aspect_to_resolution(self.aspect)[1]


@dataclass
class PipelineResult:
    """Result of the video pipeline."""

    output_path: str = ""
    duration_seconds: float = 0.0
    file_size_mb: float = 0.0
    ok: bool = False
    error: str = ""

    # Intermediate artifacts
    audio_path: str = ""
    subtitle_path: str = ""
    material_paths: list[str] = field(default_factory=list)
    search_terms_used: list[str] = field(default_factory=list)

    # Steps completed
    steps_completed: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aspect_to_resolution(aspect: str) -> tuple[int, int]:
    mapping = {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
    }
    return mapping.get(aspect, (1080, 1920))


def _get_duration_ffprobe(path: str | Path) -> float:
    """Get media duration using ffprobe."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(r.stdout.strip()) if r.stdout.strip() else 0.0
    except Exception:
        return 0.0


def _get_media_info(path: str) -> dict:
    """Get width, height, duration of a video file."""
    info = {"width": 0, "height": 0, "duration": 0.0, "is_image": False}
    ext = Path(path).suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}

    if ext in image_exts:
        info["is_image"] = True
        try:
            from PIL import Image
            with Image.open(path) as img:
                info["width"], info["height"] = img.size
        except Exception:
            pass
        return info

    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        import json
        data = json.loads(r.stdout)
        if data.get("streams"):
            s = data["streams"][0]
            info["width"] = int(s.get("width", 0))
            info["height"] = int(s.get("height", 0))
        if data.get("format"):
            info["duration"] = float(data["format"].get("duration", 0))
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# Step 1: Generate search terms from script
# ---------------------------------------------------------------------------


def generate_search_terms(
    script_text: str,
    book_title: str = "",
    num_terms: int = 8,
    config: PipelineConfig | None = None,
    book_genre: str = "",
) -> list[str]:
    """Extract English search terms from book script for stock footage.

    Uses LLM-based extraction with automatic language detection and
    translation (MPT-style). Falls back to regex if LLM unavailable.

    Args:
        script_text: Script text in any language.
        book_title: Book title for context.
        num_terms: Number of search terms to generate.
        config: PipelineConfig with LLM settings.
        book_genre: Book genre for better visual matching.

    Returns:
        List of English search terms for stock APIs.
    """
    try:
        from bookai.keyword_generator import KeywordConfig, generate_keywords

        kw_config = KeywordConfig(
            num_terms=num_terms,
            match_script_order=config.match_script_order if config else True,
            fallback_to_regex=True,
        )

        if config and config.llm_api_key:
            kw_config.llm_api_key = config.llm_api_key
            kw_config.llm_base_url = config.llm_base_url
            kw_config.llm_model = config.llm_model

        return generate_keywords(
            script_text=script_text,
            book_title=book_title,
            book_genre=book_genre,
            config=kw_config,
        )
    except ImportError:
        # Fallback to basic regex extraction
        import re
        base_terms = ["reading book", "education", "knowledge"]
        english_words = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', script_text)
        tech_terms = re.findall(
            r'\b(?:AI|Machine Learning|Deep Learning|NLP|Data|Science|Technology)\b',
            script_text, re.IGNORECASE,
        )
        terms = list(set(tech_terms + english_words[:5] + base_terms))
        random.shuffle(terms)
        return terms[:num_terms]


# ---------------------------------------------------------------------------
# Step 2: Collect materials
# ---------------------------------------------------------------------------


def collect_stock_materials(
    search_terms: list[str],
    audio_duration: float,
    config: PipelineConfig,
    output_dir: str,
) -> list[str]:
    """Download stock videos from Pexels/Pixabay."""
    stock_cfg = StockVideoConfig(
        provider=config.material_source,
        pexels_api_key=config.pexels_api_key,
        pixabay_api_key=config.pixabay_api_key,
        coverr_api_key=config.coverr_api_key,
        min_duration=config.max_clip_duration,
        max_results_per_term=3,
        cache_dir=os.path.join(output_dir, "stock_cache"),
    )

    materials = search_and_download(
        search_terms=search_terms,
        video_aspect=config.aspect,
        output_dir=os.path.join(output_dir, "materials"),
        config=stock_cfg,
    )

    return [m.local_path for m in materials if m.local_path and os.path.exists(m.local_path)]


def collect_local_materials(
    material_dir: str,
    config: PipelineConfig,
) -> list[str]:
    """Collect videos and images from a local directory.

    Supports: .mp4, .avi, .mov, .mkv, .jpg, .jpeg, .png, .gif, .webp
    Images are automatically converted to short video clips.
    """
    if not material_dir or not os.path.isdir(material_dir):
        return []

    video_exts = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    valid_exts = video_exts | image_exts

    paths = []
    for f in sorted(os.listdir(material_dir)):
        ext = Path(f).suffix.lower()
        if ext in valid_exts:
            full_path = os.path.join(material_dir, f)
            if os.path.isfile(full_path) and os.path.getsize(full_path) > 0:
                paths.append(full_path)

    return paths


def _convert_image_to_video(
    image_path: str,
    output_path: str,
    duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Convert a single image to a video clip with zoom effect using FFmpeg."""
    try:
        # Ken Burns zoom effect: zoom in from 100% to 120% over duration
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image_path),
            "-vf", (
                f"scale={width * 2}:{height * 2},"
                f"zoompan=z='min(zoom+0.0015,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d={int(duration * 30)}:s={width}x{height}:fps=30"
            ),
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "fast",
            str(output_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=60)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Step 3: Clip, resize, transition individual clips
# ---------------------------------------------------------------------------


def _resize_clip_ffmpeg(
    input_path: str,
    output_path: str,
    target_w: int,
    target_h: int,
    max_duration: float = 5.0,
    start_time: float = 0.0,
) -> bool:
    """Resize and trim a video clip to exact target dimensions using FFmpeg.

    Uses scale + pad to letterbox/pillarbox any aspect ratio to target.
    """
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", str(input_path),
            "-t", str(max_duration),
            "-vf", (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black"
            ),
            "-c:v", "libx264", "-preset", "fast",
            "-an",  # No audio for clips
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        return r.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


def _apply_transition_ffmpeg(
    input_path: str,
    output_path: str,
    transition: str = "fade_in",
    duration: float = 0.8,
) -> bool:
    """Apply a transition effect to a clip using FFmpeg."""
    try:
        if transition == "none" or not transition:
            shutil.copy(input_path, output_path)
            return True

        clip_dur = _get_duration_ffprobe(input_path)
        if clip_dur <= 0:
            shutil.copy(input_path, output_path)
            return True

        if transition == "fade_in":
            vf = f"fade=t=in:st=0:d={duration}"
        elif transition == "fade_out":
            vf = f"fade=t=out:st={max(0, clip_dur - duration)}:d={duration}"
        elif transition in ("slide_in", "slide_out"):
            # Simulate with fade
            vf = f"fade=t=in:st=0:d={duration}"
        elif transition == "shuffle":
            # Random fade in/out
            vf = f"fade=t=in:st=0:d={duration},fade=t=out:st={max(0, clip_dur - duration)}:d={duration}"
        else:
            vf = f"fade=t=in:st=0:d={duration}"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        if r.returncode == 0 and os.path.exists(output_path):
            return True
        # Fallback: just copy
        shutil.copy(input_path, output_path)
        return True
    except Exception:
        shutil.copy(input_path, output_path)
        return True


# ---------------------------------------------------------------------------
# Step 4: Concatenate clips
# ---------------------------------------------------------------------------


def _concat_clips_ffmpeg(
    clip_paths: list[str],
    output_path: str,
) -> bool:
    """Concatenate video clips using FFmpeg concat demuxer."""
    if not clip_paths:
        return False

    if len(clip_paths) == 1:
        shutil.copy(clip_paths[0], output_path)
        return True

    # Write concat list
    concat_list = output_path + ".concat.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            safe = os.path.abspath(p).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        return r.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False
    finally:
        try:
            os.remove(concat_list)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Step 5: Burn subtitles onto video
# ---------------------------------------------------------------------------


def _burn_subtitles(
    video_path: str,
    subtitle_path: str,
    output_path: str,
    config: PipelineConfig,
) -> bool:
    """Burn subtitles — uses styled template if set, else plain FFmpeg."""
    if config.subtitle_template:
        try:
            from bookai.subtitle_templates import burn_styled_subtitles
            return burn_styled_subtitles(
                video_path=video_path,
                srt_path=subtitle_path,
                output_path=output_path,
                template=config.subtitle_template,
                video_width=config.width,
                video_height=config.height,
            )
        except Exception:
            pass  # Fallback to plain FFmpeg
    return _burn_subtitles_ffmpeg(video_path, subtitle_path, output_path, config)


def _burn_subtitles_ffmpeg(
    video_path: str,
    subtitle_path: str,
    output_path: str,
    config: PipelineConfig,
) -> bool:
    """Burn SRT subtitles onto video using FFmpeg's subtitles filter."""
    if not subtitle_path or not os.path.exists(subtitle_path):
        shutil.copy(video_path, output_path)
        return True

    # Build subtitle style string (ASS format)
    font_size = config.subtitle_font_size
    color_hex = config.subtitle_color.lstrip("#")
    # FFmpeg ASS colors are in &HBBGGRR& format
    if len(color_hex) == 6:
        r, g, b = color_hex[0:2], color_hex[2:4], color_hex[4:6]
        ass_color = f"&H00{b}{g}{r}&"
    else:
        ass_color = "&H00FFFFFF&"

    stroke_hex = config.subtitle_stroke_color.lstrip("#")
    if len(stroke_hex) == 6:
        r, g, b = stroke_hex[0:2], stroke_hex[2:4], stroke_hex[4:6]
        ass_outline = f"&H00{b}{g}{r}&"
    else:
        ass_outline = "&H00000000&"

    # Position: bottom=2, top=6, center=5
    pos_map = {"bottom": 2, "top": 6, "center": 5}
    alignment = pos_map.get(config.subtitle_position, 2)

    outline_width = int(config.subtitle_stroke_width)

    # Background box: 0=none, 1=opaque, 3=outline, 4=shadow with box
    bg_style = ""
    if config.subtitle_bg_color:
        bg_hex = config.subtitle_bg_color.lstrip("#")
        if len(bg_hex) >= 6:
            r, g, b = bg_hex[0:2], bg_hex[2:4], bg_hex[4:6]
            alpha = bg_hex[6:8] if len(bg_hex) == 8 else "60"
            bg_style = f",BackColour=&H{alpha}{b}{g}{r}&,BorderStyle=4"

    # Margins — keep text away from screen edges
    margin_v = 40 if config.subtitle_position == "bottom" else 25
    margin_lr = 50  # Left/right margin to prevent full-width text

    # Font name for ASS style (use Vietnamese font if available)
    font_name = config.subtitle_font_name or "BeVietnamPro SemiBold"
    font_clause = f"FontName={font_name}," if font_name else ""

    style = (
        f"{font_clause}"
        f"FontSize={font_size},"
        f"PrimaryColour={ass_color},"
        f"OutlineColour={ass_outline},"
        f"Outline={outline_width},"
        f"Alignment={alignment},"
        f"MarginV={margin_v},"
        f"MarginL={margin_lr},"
        f"MarginR={margin_lr},"
        f"WrapStyle=0"  # Smart wrapping at word boundaries
        f"{bg_style}"
    )

    # Escape paths for FFmpeg filter
    safe_sub = str(subtitle_path).replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles='{safe_sub}':force_style='{style}'"

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        if r.returncode == 0 and os.path.exists(output_path):
            return True
        # Fallback: copy without subtitles
        shutil.copy(video_path, output_path)
        return True
    except Exception:
        shutil.copy(video_path, output_path)
        return True


# ---------------------------------------------------------------------------
# Step 6: Add audio + BGM to video
# ---------------------------------------------------------------------------


def _add_audio_bgm_ffmpeg(
    video_path: str,
    audio_path: str,
    output_path: str,
    config: PipelineConfig,
) -> bool:
    """Merge voice audio + BGM into the video."""
    bgm_file = ""
    if config.bgm_mode != "none":
        bgm_file = get_bgm_file(mode=config.bgm_mode, filename=config.bgm_file)

    try:
        if bgm_file and os.path.exists(bgm_file):
            # Mix voice + BGM, then add to video
            video_dur = _get_duration_ffprobe(video_path)

            # Complex filter: voice at full volume, BGM at reduced volume, loop BGM
            filter_complex = (
                f"[1:a]volume={config.voice_volume}[voice];"
                f"[2:a]aloop=loop=-1:size=2e+09,atrim=0:{video_dur},"
                f"volume={config.bgm_volume},afade=t=out:st={max(0, video_dur - 3)}:d=3[bgm];"
                f"[voice][bgm]amix=inputs=2:duration=first[aout]"
            )

            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),     # 0: video (no audio)
                "-i", str(audio_path),     # 1: voice
                "-i", str(bgm_file),       # 2: BGM
                "-filter_complex", filter_complex,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", config.audio_bitrate,
                "-shortest",
                str(output_path),
            ]
        else:
            # Just voice, no BGM
            cmd = [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", config.audio_bitrate,
                "-shortest",
                str(output_path),
            ]

        r = subprocess.run(cmd, capture_output=True, timeout=300)
        return r.returncode == 0 and os.path.exists(output_path)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def create_book_video(
    script_text: str,
    book_title: str = "",
    config: PipelineConfig | None = None,
    output_path: str = "output/book_video.mp4",
    search_terms: list[str] | None = None,
    local_materials: list[str] | None = None,
) -> PipelineResult:
    """Create a complete book video from script text.

    Full pipeline:
    1. Generate search terms from script (if using stock footage)
    2. Collect materials (stock download / local folder / fallback)
    3. Generate TTS audio from script
    4. Generate SRT subtitles (word-level from edge-tts)
    5. Process clips: trim → resize → transition
    6. Concatenate clips to match audio duration
    7. Burn subtitles onto video
    8. Add voice audio + BGM
    9. Final output

    Args:
        script_text: The narration script (Vietnamese or any language).
        book_title: Book title for search term generation.
        config: Pipeline configuration. Uses defaults if None.
        output_path: Where to save the final video.
        search_terms: Override auto-generated search terms.
        local_materials: Override with specific local file paths.

    Returns:
        PipelineResult with output path and metadata.
    """
    if config is None:
        config = PipelineConfig()

    result = PipelineResult()
    output_path = str(Path(output_path).resolve())
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Create temp working directory
    work_dir = tempfile.mkdtemp(prefix="bookai_video_")

    try:
        w, h = config.width, config.height

        # ===== STEP 1: TTS Audio =====
        audio_file = os.path.join(work_dir, "audio.mp3")
        tts_cfg = TTSConfig(
            provider=config.tts_provider,
            voice=config.tts_voice,
        )
        tts_result = tts_synthesize(script_text, audio_file, tts_cfg)
        if not tts_result.ok:
            result.error = f"TTS failed: {tts_result.error}"
            return result
        result.audio_path = audio_file
        result.steps_completed.append("tts")
        audio_duration = tts_result.duration_seconds

        # ===== STEP 2: Generate SRT Subtitles =====
        srt_file = ""
        if config.subtitle_enabled:
            srt_file = os.path.join(work_dir, "subtitle.srt")
            try:
                srt_result = generate_srt_from_tts(
                    text=script_text,
                    audio_path=audio_file,
                    srt_path=srt_file,
                    voice=config.tts_voice,
                )
                if srt_result and os.path.exists(srt_file) and os.path.getsize(srt_file) > 0:
                    result.subtitle_path = srt_file
                    result.steps_completed.append("subtitle")
                else:
                    srt_file = ""
            except Exception:
                srt_file = ""

        # ===== STEP 3: Collect Materials =====
        material_paths = []

        if local_materials:
            material_paths = [p for p in local_materials if os.path.exists(p)]
        elif config.material_source == "local" and config.local_material_dir:
            material_paths = collect_local_materials(config.local_material_dir, config)
        elif config.material_source in ("pexels", "pixabay", "coverr"):
            # Generate search terms (LLM-based with translation)
            terms = search_terms or config.search_terms
            if not terms:
                terms = generate_search_terms(
                    script_text, book_title,
                    config=config,
                )
            result.search_terms_used = terms

            material_paths = collect_stock_materials(
                search_terms=terms,
                audio_duration=audio_duration,
                config=config,
                output_dir=work_dir,
            )

        # Mixed mode: supplement with local materials
        if (config.local_material_dir and config.local_mode == "supplement"
                and config.material_source in ("pexels", "pixabay", "coverr")):
            local_paths = collect_local_materials(config.local_material_dir, config)
            material_paths = material_paths + local_paths
        elif (config.local_material_dir and config.local_mode == "priority"
              and config.material_source in ("pexels", "pixabay", "coverr")):
            local_paths = collect_local_materials(config.local_material_dir, config)
            material_paths = local_paths + material_paths

        # Filter valid materials
        valid_materials = []
        for mp in material_paths:
            if not os.path.exists(mp):
                continue
            info = _get_media_info(mp)
            # Skip too-small files
            if info.get("is_image"):
                if info.get("width", 0) >= 200 and info.get("height", 0) >= 200:
                    valid_materials.append(mp)
            elif info.get("width", 0) >= 480 and info.get("height", 0) >= 480:
                valid_materials.append(mp)
            elif info.get("duration", 0) > 0:
                valid_materials.append(mp)

        result.material_paths = valid_materials
        if valid_materials:
            result.steps_completed.append("materials")

        # ===== STEP 4: Process clips =====
        clips_dir = os.path.join(work_dir, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        processed_clips = []
        clip_idx = 0

        if valid_materials:
            if config.concat_mode == "random":
                random.shuffle(valid_materials)

            total_clip_duration = 0.0
            target_duration = audio_duration + 0.5  # safety margin

            for mat_path in valid_materials:
                if total_clip_duration >= target_duration:
                    break

                info = _get_media_info(mat_path)

                if info.get("is_image"):
                    # Convert image to video clip with Ken Burns effect
                    img_clip = os.path.join(clips_dir, f"img_{clip_idx:03d}.mp4")
                    converted = _convert_image_to_video(
                        mat_path, img_clip,
                        duration=min(config.max_clip_duration, 4.0),
                        width=w, height=h,
                    )
                    if converted:
                        clip_idx += 1
                        dur = _get_duration_ffprobe(converted)
                        total_clip_duration += dur
                        processed_clips.append(converted)
                    continue

                # Video: split into max_clip_duration segments
                vid_dur = info.get("duration", 0)
                if vid_dur <= 0:
                    continue

                start = 0.0
                while start < vid_dur and total_clip_duration < target_duration:
                    end = min(start + config.max_clip_duration, vid_dur)
                    segment_dur = end - start

                    if segment_dur < 0.5:
                        break

                    # Resize + trim
                    resized_clip = os.path.join(clips_dir, f"clip_{clip_idx:03d}_raw.mp4")
                    ok = _resize_clip_ffmpeg(
                        mat_path, resized_clip, w, h,
                        max_duration=segment_dur,
                        start_time=start,
                    )
                    if not ok:
                        start = end
                        continue

                    # Apply transition
                    transition = config.transition
                    if transition == "shuffle":
                        transition = random.choice(["fade_in", "fade_out", "none"])

                    final_clip = os.path.join(clips_dir, f"clip_{clip_idx:03d}.mp4")
                    _apply_transition_ffmpeg(resized_clip, final_clip, transition)

                    clip_dur = _get_duration_ffprobe(final_clip)
                    if clip_dur > 0:
                        processed_clips.append(final_clip)
                        total_clip_duration += clip_dur
                        clip_idx += 1

                    # Clean raw
                    try:
                        os.remove(resized_clip)
                    except Exception:
                        pass

                    start = end
                    if config.concat_mode == "sequential":
                        break  # Only first segment per material in sequential mode

            # Loop clips if not enough footage
            if total_clip_duration < target_duration and processed_clips:
                base_clips = list(processed_clips)
                while total_clip_duration < target_duration:
                    for bc in base_clips:
                        if total_clip_duration >= target_duration:
                            break
                        processed_clips.append(bc)
                        total_clip_duration += _get_duration_ffprobe(bc)

        # Fallback: generate solid color background if no materials
        if not processed_clips:
            bg_clip = os.path.join(clips_dir, "bg_solid.mp4")
            _generate_solid_bg(bg_clip, w, h, audio_duration, config)
            if os.path.exists(bg_clip):
                processed_clips.append(bg_clip)

        result.steps_completed.append("clips")

        # ===== STEP 4b: Generate video sections (hook, title card, outro) =====
        section_clips = {"hook": None, "title": None, "outro": None}
        try:
            from bookai.video_sections import (
                SectionConfig,
                generate_hook,
                generate_outro,
                generate_title_card,
            )
            sec_config = SectionConfig(
                width=w, height=h, fps=config.fps,
            )

            if config.hook_style and config.hook_text:
                hook_path = os.path.join(clips_dir, "hook.mp4")
                hook_clip = generate_hook(
                    text=config.hook_text,
                    style=config.hook_style,
                    output_path=hook_path,
                    config=sec_config,
                )
                if hook_clip and os.path.exists(hook_clip):
                    section_clips["hook"] = hook_clip

            if config.title_card_style:
                title_path = os.path.join(clips_dir, "title_card.mp4")
                title_clip = generate_title_card(
                    book_title=book_title,
                    style=config.title_card_style,
                    output_path=title_path,
                    config=sec_config,
                    cover_image_path=config.cover_image_path,
                )
                if title_clip and os.path.exists(title_clip):
                    section_clips["title"] = title_clip

            if config.outro_style:
                outro_path = os.path.join(clips_dir, "outro.mp4")
                outro_clip = generate_outro(
                    text=config.outro_text,
                    style=config.outro_style,
                    output_path=outro_path,
                    config=sec_config,
                )
                if outro_clip and os.path.exists(outro_clip):
                    section_clips["outro"] = outro_clip

            result.steps_completed.append("sections")
        except ImportError:
            pass  # video_sections not available — skip
        except Exception:
            pass  # Non-fatal — continue without sections

        # Assemble final clip order: [hook] + [title] + content_clips + [outro]
        all_clips = []
        if section_clips["hook"]:
            all_clips.append(section_clips["hook"])
        if section_clips["title"]:
            all_clips.append(section_clips["title"])
        all_clips.extend(processed_clips)
        if section_clips["outro"]:
            all_clips.append(section_clips["outro"])

        # ===== STEP 5: Concatenate clips =====
        combined_video = os.path.join(work_dir, "combined.mp4")
        _concat_clips_ffmpeg(all_clips, combined_video)

        if not os.path.exists(combined_video):
            result.error = "Failed to concatenate video clips"
            return result

        # Trim to audio duration
        trimmed_video = os.path.join(work_dir, "trimmed.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", combined_video,
                "-t", str(audio_duration + 0.2),
                "-c:v", "libx264", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-an",
                trimmed_video,
            ],
            capture_output=True, timeout=120,
        )
        if os.path.exists(trimmed_video):
            combined_video = trimmed_video

        result.steps_completed.append("concat")

        # ===== STEP 6: Burn subtitles =====
        if srt_file and config.subtitle_enabled:
            subtitled_video = os.path.join(work_dir, "subtitled.mp4")
            _burn_subtitles(combined_video, srt_file, subtitled_video, config)
            if os.path.exists(subtitled_video) and os.path.getsize(subtitled_video) > 0:
                combined_video = subtitled_video
                result.steps_completed.append("subtitle_burn")

        # ===== STEP 7: Add audio + BGM =====
        final_video = os.path.join(work_dir, "final.mp4")
        ok = _add_audio_bgm_ffmpeg(combined_video, audio_file, final_video, config)

        if not ok or not os.path.exists(final_video):
            result.error = "Failed to add audio/BGM to video"
            return result

        result.steps_completed.append("audio_bgm")

        # ===== STEP 8: Copy to output =====
        shutil.copy2(final_video, output_path)

        if os.path.exists(output_path):
            result.output_path = output_path
            result.duration_seconds = _get_duration_ffprobe(output_path)
            result.file_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            result.ok = True
            result.steps_completed.append("complete")

    except Exception as e:
        result.error = str(e)

    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass

    return result


def _generate_solid_bg(
    output_path: str,
    w: int, h: int,
    duration: float,
    config: PipelineConfig,
) -> bool:
    """Generate a solid color background video."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=0x1a1a2e:s={w}x{h}:d={duration}:r={config.fps}",
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Convenience: Create video from book analysis
# ---------------------------------------------------------------------------


def create_video_from_book(
    book_markdown: str,
    book_title: str = "",
    config: PipelineConfig | None = None,
    output_path: str = "output/book_video.mp4",
) -> PipelineResult:
    """Higher-level: generate a narration script from book markdown, then create video.

    This creates a simple narration script from the book content, then runs
    the full video pipeline.
    """
    # Create a simple script from the book content
    lines = book_markdown.strip().split("\n")
    # Take first meaningful paragraphs
    paragraphs = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    script = " ".join(paragraphs[:10])

    # Limit to ~60 seconds of narration (roughly 150 words/min Vietnamese)
    words = script.split()
    if len(words) > 200:
        script = " ".join(words[:200])

    return create_book_video(
        script_text=script,
        book_title=book_title,
        config=config,
        output_path=output_path,
    )
