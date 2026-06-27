"""Text animation effects engine for BookAI video pipeline.

Renders animated text as video clips using PIL frame generation + FFmpeg.
Supports entrance, emphasis, and exit animations inspired by CapCut effects.

Usage:
    from bookai.text_animations import render_animated_text, AnimationConfig

    config = AnimationConfig(width=1080, height=1920)
    path = render_animated_text(
        text="Cuốn sách thay đổi cuộc đời tôi",
        entrance="slide_up",
        emphasis="word_highlight",
        exit_anim="fade_out",
        output_path="output/animated.mp4",
        config=config,
    )
"""

from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = ImageFilter = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class AnimationConfig:
    """Configuration for text animations."""
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # Timing (seconds)
    entrance_duration: float = 0.8
    hold_duration: float = 1.5
    exit_duration: float = 0.5
    total_duration: float = 0.0  # Auto-calculated if 0

    # Style
    bg_color: tuple = (15, 15, 15)
    text_color: tuple = (255, 255, 255)
    accent_color: tuple = (59, 130, 246)
    highlight_color: tuple = (255, 215, 0)  # Gold for highlights

    # Font
    font_path: str = ""
    font_size: int = 56

    # Position (0.0-1.0 of height)
    y_position: float = 0.5  # Center by default


# ---------------------------------------------------------------------------
# Easing functions
# ---------------------------------------------------------------------------

def _ease_in(t: float) -> float:
    return t * t

def _ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3

def _ease_in_out(t: float) -> float:
    if t < 0.5:
        return 2 * t * t
    return 1 - (-2 * t + 2) ** 2 / 2

def _ease_out_back(t: float) -> float:
    """Overshoot ease-out for bounce effects."""
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2

def _ease_out_elastic(t: float) -> float:
    """Elastic ease-out."""
    if t == 0 or t == 1:
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * (2 * math.pi) / 3) + 1


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def _load_font(config: AnimationConfig, size: int = 0) -> ImageFont.FreeTypeFont:
    """Load font with fallbacks."""
    size = size or config.font_size

    if config.font_path and os.path.exists(config.font_path):
        try:
            return ImageFont.truetype(config.font_path, size)
        except Exception:
            pass

    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for fp in paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """Word-wrap text."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip() if current else word
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _text_size(text: str, font, draw) -> tuple[int, int]:
    """Get text width, height."""
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


# ---------------------------------------------------------------------------
# Entrance animations
# ---------------------------------------------------------------------------

def _entrance_none(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """No animation — instant appear."""
    return x, y, 1.0


def _entrance_fade_in(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Fade from transparent to opaque."""
    alpha = _ease_in_out(progress)
    return x, y, alpha


def _entrance_slide_up(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Slide up from below."""
    offset = int(100 * (1 - _ease_out(progress)))
    alpha = _ease_in_out(progress)
    return x, y + offset, alpha


def _entrance_slide_left(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Slide in from the right side."""
    offset = int(200 * (1 - _ease_out(progress)))
    alpha = _ease_in_out(progress)
    return x + offset, y, alpha


def _entrance_zoom_in(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Text zooms from small to full size."""
    0.3 + 0.7 * _ease_out_back(progress)
    alpha = _ease_in_out(progress)
    return x, y, alpha  # Scale applied separately


def _entrance_pop_bounce(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Pop in with bounce effect."""
    scale = _ease_out_elastic(progress)
    y_offset = int(-20 * (1 - scale))
    alpha = min(1.0, progress * 3)
    return x, y + y_offset, alpha


def _entrance_typewriter(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Typewriter — characters appear one by one."""
    # Special: handled in main render loop
    return x, y, 1.0


def _entrance_blur_reveal(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Blur to sharp reveal."""
    alpha = _ease_in_out(progress)
    return x, y, alpha  # Blur applied as post-process


# ---------------------------------------------------------------------------
# Emphasis animations
# ---------------------------------------------------------------------------

def _emphasis_none(
    draw, words: list[str], font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> list[tuple[str, tuple, tuple]]:
    """No emphasis — all same color."""
    return [(w, config.text_color, (0, 0)) for w in words]


def _emphasis_word_highlight(
    draw, words: list[str], font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> list[tuple[str, tuple, tuple]]:
    """Highlight words one by one (like CapCut 958K uses style)."""
    result = []
    current_word_idx = int(progress * len(words))

    for idx, word in enumerate(words):
        if idx == current_word_idx:
            color = config.highlight_color
        elif idx < current_word_idx:
            color = config.text_color
        else:
            # Dim future words
            color = tuple(int(c * 0.4) for c in config.text_color)
        result.append((word, color, (0, 0)))

    return result


def _emphasis_pulse(
    draw, words: list[str], font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> list[tuple[str, tuple, tuple]]:
    """Gentle pulse/scale oscillation."""
    1.0 + 0.05 * math.sin(progress * math.pi * 4)
    # Can't easily scale individual words in PIL, so just shift y slightly
    y_shift = int(3 * math.sin(progress * math.pi * 4))
    return [(w, config.text_color, (0, y_shift)) for w in words]


def _emphasis_color_change(
    draw, words: list[str], font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> list[tuple[str, tuple, tuple]]:
    """Cycle through accent colors for keywords."""
    result = []
    colors = [
        config.text_color,
        config.accent_color,
        config.highlight_color,
        (76, 175, 80),  # Green
    ]
    for idx, word in enumerate(words):
        color_idx = int((progress * 3 + idx * 0.5) % len(colors))
        result.append((word, colors[color_idx], (0, 0)))
    return result


def _emphasis_underline_sweep(
    draw, words: list[str], font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> list[tuple[str, tuple, tuple]]:
    """Underline sweeps across text."""
    # Underline drawn in post-process; words get normal color
    return [(w, config.text_color, (0, 0)) for w in words]


# ---------------------------------------------------------------------------
# Exit animations
# ---------------------------------------------------------------------------

def _exit_none(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """No exit — stays visible."""
    return x, y, 1.0


def _exit_fade_out(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Fade to transparent."""
    alpha = 1.0 - _ease_in(progress)
    return x, y, alpha


def _exit_slide_out(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Slide out to left."""
    offset = int(-300 * _ease_in(progress))
    alpha = 1.0 - _ease_in(progress)
    return x + offset, y, alpha


def _exit_shrink(
    draw, text: str, font, x: int, y: int,
    progress: float, config: AnimationConfig,
) -> tuple[int, int, float]:
    """Shrink to nothing."""
    alpha = 1.0 - _ease_in(progress)
    return x, y, alpha


# ---------------------------------------------------------------------------
# Animation registries
# ---------------------------------------------------------------------------

ENTRANCE_EFFECTS = {
    "none": _entrance_none,
    "fade_in": _entrance_fade_in,
    "slide_up": _entrance_slide_up,
    "slide_left": _entrance_slide_left,
    "zoom_in": _entrance_zoom_in,
    "pop_bounce": _entrance_pop_bounce,
    "typewriter": _entrance_typewriter,
    "blur_reveal": _entrance_blur_reveal,
}

EMPHASIS_EFFECTS = {
    "none": _emphasis_none,
    "word_highlight": _emphasis_word_highlight,
    "pulse": _emphasis_pulse,
    "color_change": _emphasis_color_change,
    "underline_sweep": _emphasis_underline_sweep,
}

EXIT_EFFECTS = {
    "none": _exit_none,
    "fade_out": _exit_fade_out,
    "slide_out": _exit_slide_out,
    "shrink": _exit_shrink,
}


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render_animated_text(
    text: str,
    entrance: str = "fade_in",
    emphasis: str = "none",
    exit_anim: str = "fade_out",
    output_path: str = "animated_text.mp4",
    config: AnimationConfig | None = None,
) -> str:
    """Render animated text as an MP4 video clip.

    Args:
        text: The text to animate.
        entrance: Entrance effect name (see ENTRANCE_EFFECTS).
        emphasis: Emphasis effect name (see EMPHASIS_EFFECTS).
        exit_anim: Exit effect name (see EXIT_EFFECTS).
        output_path: Where to save the MP4.
        config: AnimationConfig.

    Returns:
        Path to the generated MP4 clip.
    """
    if Image is None:
        raise ImportError("Pillow required for text animations")

    if config is None:
        config = AnimationConfig()

    # Calculate total duration
    total = config.total_duration
    if total <= 0:
        total = config.entrance_duration + config.hold_duration + config.exit_duration
    num_frames = int(total * config.fps)

    # Get effect functions
    entrance_fn = ENTRANCE_EFFECTS.get(entrance, _entrance_fade_in)
    emphasis_fn = EMPHASIS_EFFECTS.get(emphasis, _emphasis_none)
    exit_fn = EXIT_EFFECTS.get(exit_anim, _exit_fade_out)

    W, H = config.width, config.height
    font = _load_font(config)
    text.split()

    # Phase boundaries (in frames)
    entrance_frames = int(config.entrance_duration * config.fps)
    hold_start = entrance_frames
    exit_start = num_frames - int(config.exit_duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="text_anim_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)

            # Determine phase and progress
            if i < hold_start:
                # Entrance phase
                phase = "entrance"
                phase_progress = i / max(entrance_frames - 1, 1)
            elif i >= exit_start:
                # Exit phase
                phase = "exit"
                phase_progress = (i - exit_start) / max(num_frames - exit_start - 1, 1)
            else:
                # Hold phase
                phase = "hold"
                hold_frames = exit_start - hold_start
                phase_progress = (i - hold_start) / max(hold_frames - 1, 1)

            # Base position
            max_w = int(W * 0.85)
            lines = _wrap_text(text, font, max_w, draw)
            line_h = config.font_size + 12
            total_text_h = line_h * len(lines)
            base_y = int(H * config.y_position) - total_text_h // 2

            # Apply entrance/exit transforms
            if phase == "entrance":
                _, y_offset, alpha = entrance_fn(draw, text, font, 0, 0, phase_progress, config)
                base_y += y_offset
                x_offset = 0

                # Special typewriter handling
                if entrance == "typewriter":
                    visible_chars = int(len(text) * phase_progress)
                    visible_text = text[:visible_chars]
                    vis_lines = _wrap_text(visible_text, font, max_w, draw)
                    for j, line in enumerate(vis_lines):
                        bbox = draw.textbbox((0, 0), line, font=font)
                        tw = bbox[2] - bbox[0]
                        lx = (W - tw) // 2
                        ly = base_y + j * line_h
                        draw.text((lx, ly), line, font=font, fill=config.text_color)

                    # Blinking cursor
                    if (i // 8) % 2 == 0 and vis_lines:
                        last = vis_lines[-1]
                        bbox = draw.textbbox((0, 0), last, font=font)
                        cx = (W - (bbox[2] - bbox[0])) // 2 + (bbox[2] - bbox[0]) + 3
                        cy = base_y + (len(vis_lines) - 1) * line_h
                        draw.rectangle(
                            [cx, cy, cx + 3, cy + config.font_size],
                            fill=config.accent_color,
                        )

                    # Blur for blur_reveal
                    if entrance == "blur_reveal":
                        blur_r = int(15 * (1 - phase_progress))
                        if blur_r > 0:
                            img = img.filter(ImageFilter.GaussianBlur(radius=blur_r))

                    img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))
                    continue

            elif phase == "exit":
                x_off, y_off, alpha = exit_fn(draw, text, font, 0, 0, phase_progress, config)
                base_y += y_off
                x_offset = x_off
            else:
                alpha = 1.0
                x_offset = 0

            # Draw text with emphasis effects
            for j, line in enumerate(lines):
                line_words = line.split()
                if not line_words:
                    continue

                # Calculate line width for centering
                bbox = draw.textbbox((0, 0), line, font=font)
                line_w = bbox[2] - bbox[0]
                lx = (W - line_w) // 2 + x_offset
                ly = base_y + j * line_h

                if phase == "hold" and emphasis != "none":
                    # Apply emphasis per word
                    word_results = emphasis_fn(
                        draw, line_words, font, lx, ly,
                        phase_progress, config,
                    )
                    current_x = lx
                    for word, color, (dx, dy) in word_results:
                        # Apply alpha
                        final_color = tuple(int(c * alpha) for c in color)
                        draw.text((current_x + dx, ly + dy), word, font=font, fill=final_color)
                        space_w = _text_size(word + " ", font, draw)[0]
                        current_x += space_w
                else:
                    # Simple draw with alpha
                    color = tuple(int(c * alpha) for c in config.text_color)
                    # Shadow
                    shadow = tuple(int(c * alpha * 0.3) for c in (0, 0, 0))
                    draw.text((lx + 2, ly + 2), line, font=font, fill=shadow)
                    draw.text((lx, ly), line, font=font, fill=color)

                # Underline sweep effect
                if phase == "hold" and emphasis == "underline_sweep":
                    sweep_x = int(lx + line_w * phase_progress)
                    underline_y = ly + config.font_size + 4
                    accent = tuple(int(c * alpha) for c in config.accent_color)
                    draw.line([(lx, underline_y), (sweep_x, underline_y)],
                              fill=accent, width=3)

            # Post-process blur for blur_reveal entrance
            if phase == "entrance" and entrance == "blur_reveal":
                blur_r = int(15 * (1 - phase_progress))
                if blur_r > 0:
                    img = img.filter(ImageFilter.GaussianBlur(radius=blur_r))

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        # Convert frames to video
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(config.fps),
            "-i", os.path.join(tmpdir, "frame_%04d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-crf", "23",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr[:500]}")
            return ""

        return output_path

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def list_entrance_effects() -> list[str]:
    """List available entrance effect names."""
    return list(ENTRANCE_EFFECTS.keys())


def list_emphasis_effects() -> list[str]:
    """List available emphasis effect names."""
    return list(EMPHASIS_EFFECTS.keys())


def list_exit_effects() -> list[str]:
    """List available exit effect names."""
    return list(EXIT_EFFECTS.keys())
