"""Video section generators for BookAI — hooks, title cards, intros, outros.

Generates PIL-rendered frame sequences → FFmpeg video clips for each
section type. Inspired by CapCut templates with BookAI-specific
book review focus.

Usage:
    from bookai.video_sections import generate_hook, generate_title_card, SectionConfig

    config = SectionConfig(width=1080, height=1920, fps=30)
    hook_path = generate_hook(
        text="Cuốn sách này thay đổi cách tôi nghĩ về mọi thứ",
        style="bold_question",
        output_path="output/hook.mp4",
        config=config,
    )
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = ImageFilter = None
    logger.warning("Pillow not installed — video_sections will not work")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SectionConfig:
    """Configuration for video section rendering."""
    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration: float = 3.0  # Default duration in seconds

    # Colors
    bg_color: tuple = (15, 15, 15)       # Dark background
    text_color: tuple = (255, 255, 255)  # White text
    accent_color: tuple = (59, 130, 246) # Blue accent
    secondary_color: tuple = (156, 163, 175)  # Gray

    # Fonts
    font_path: str = ""      # Path to .ttf font
    font_size_title: int = 72
    font_size_body: int = 48
    font_size_small: int = 32

    # Animation
    fade_frames: int = 8  # Frames for fade in/out


# ---------------------------------------------------------------------------
# Font utilities
# ---------------------------------------------------------------------------

def _load_font(config: SectionConfig, size: int) -> ImageFont.FreeTypeFont:
    """Load a font, trying user path first, then system fallbacks."""
    if config.font_path and os.path.exists(config.font_path):
        try:
            return ImageFont.truetype(config.font_path, size)
        except Exception:
            pass

    # Try common Vietnamese-capable fonts
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    # Also check BookAI's bundled fonts
    bookai_fonts = Path(__file__).parent.parent.parent / "assets" / "fonts"
    if bookai_fonts.exists():
        for f in bookai_fonts.glob("*.ttf"):
            font_paths.insert(0, str(f))

    for fp in font_paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue

    # Last resort — default bitmap font
    return ImageFont.load_default()


def _wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test = f"{current_line} {word}".strip() if current_line else word
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines or [text]


# ---------------------------------------------------------------------------
# Frame rendering helpers
# ---------------------------------------------------------------------------

def _render_frames_to_video(
    frame_dir: str,
    output_path: str,
    fps: int = 30,
    audio_path: str = "",
) -> str:
    """Convert a sequence of PNG frames to an MP4 video."""
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frame_dir, "frame_%04d.png"),
    ]

    if audio_path and os.path.exists(audio_path):
        cmd.extend(["-i", audio_path, "-shortest"])

    cmd.extend([
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "23",
        output_path,
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.error(f"FFmpeg error: {result.stderr[:500]}")
        return ""

    return output_path


def _ease_in_out(t: float) -> float:
    """Smooth ease-in-out function (t in 0..1)."""
    if t < 0.5:
        return 2 * t * t
    return 1 - (-2 * t + 2) ** 2 / 2


def _ease_out(t: float) -> float:
    """Ease-out function for slide effects."""
    return 1 - (1 - t) ** 3


# ---------------------------------------------------------------------------
# HOOK GENERATORS
# ---------------------------------------------------------------------------

def generate_hook(
    text: str,
    style: str = "bold_question",
    output_path: str = "hook.mp4",
    config: SectionConfig | None = None,
    bg_image_path: str = "",
) -> str:
    """Generate a hook video section.

    Styles:
        - bold_question: Large text with zoom-in effect
        - shocking_fact: Shake/emphasis effect
        - book_rating: Star rating display
        - quote_reveal: Typewriter reveal
        - mystery: Blur-to-clear reveal

    Returns:
        Path to the generated MP4 clip.
    """
    if Image is None:
        raise ImportError("Pillow is required for video section generation")

    if config is None:
        config = SectionConfig()

    generators = {
        "bold_question": _hook_bold_question,
        "shocking_fact": _hook_shocking_fact,
        "book_rating": _hook_book_rating,
        "quote_reveal": _hook_quote_reveal,
        "mystery": _hook_mystery,
    }

    generator = generators.get(style, _hook_bold_question)
    return generator(text, output_path, config, bg_image_path)


def _hook_bold_question(
    text: str, output_path: str, config: SectionConfig, bg_image: str = "",
) -> str:
    """Bold text zoom-in hook."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)
    _load_font(config, config.font_size_title)

    tmpdir = tempfile.mkdtemp(prefix="hook_bold_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            if bg_image and os.path.exists(bg_image):
                try:
                    bg = Image.open(bg_image).resize((W, H), Image.LANCZOS)
                    # Darken background
                    overlay = Image.new("RGB", (W, H), (0, 0, 0))
                    img = Image.blend(bg, overlay, 0.5)
                except Exception:
                    pass

            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            # Zoom effect: scale from 0.3 to 1.0 with ease-out
            if progress < 0.3:
                scale = 0.3 + 0.7 * _ease_out(progress / 0.3)
            else:
                scale = 1.0

            # Fade in first 20% of frames
            alpha_factor = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            # Fade out last 10%
            if progress > 0.9:
                alpha_factor = (1.0 - progress) / 0.1

            scaled_size = int(config.font_size_title * scale)
            scaled_font = _load_font(config, max(12, scaled_size))

            # Wrap text
            max_w = int(W * 0.85)
            lines = _wrap_text(text, scaled_font, max_w, draw)

            # Calculate total text height
            line_height = scaled_size + 10
            total_h = line_height * len(lines)
            y_start = (H - total_h) // 2

            # Draw each line centered
            color = tuple(int(c * alpha_factor) for c in config.text_color)
            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=scaled_font)
                tw = bbox[2] - bbox[0]
                x = (W - tw) // 2
                y = y_start + j * line_height

                # Shadow
                shadow_color = tuple(int(c * alpha_factor * 0.3) for c in (0, 0, 0))
                draw.text((x + 3, y + 3), line, font=scaled_font, fill=shadow_color)
                draw.text((x, y), line, font=scaled_font, fill=color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _hook_shocking_fact(
    text: str, output_path: str, config: SectionConfig, bg_image: str = "",
) -> str:
    """Shocking fact with emphasis pulse effect."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)
    _load_font(config, config.font_size_title)

    tmpdir = tempfile.mkdtemp(prefix="hook_shock_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            # Flash effect at start
            if progress < 0.1:
                flash = int(255 * (1 - progress / 0.1))
                img = Image.new("RGB", (W, H), (flash, flash, flash))
                draw = ImageDraw.Draw(img)

            # Shake effect in first half
            import math
            shake_x = int(8 * math.sin(progress * 20) * max(0, 1 - progress * 2))
            shake_y = int(4 * math.cos(progress * 15) * max(0, 1 - progress * 2))

            # Pulse scale
            pulse = 1.0
            if 0.1 < progress < 0.4:
                t = (progress - 0.1) / 0.3
                pulse = 1.0 + 0.15 * math.sin(t * math.pi * 3) * (1 - t)

            scaled_size = int(config.font_size_title * pulse)
            scaled_font = _load_font(config, max(12, scaled_size))

            max_w = int(W * 0.85)
            lines = _wrap_text(text, scaled_font, max_w, draw)
            line_height = scaled_size + 10
            total_h = line_height * len(lines)
            y_start = (H - total_h) // 2

            # Red accent color for emphasis
            alpha = min(1.0, progress / 0.15) if progress < 0.15 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1
            color = tuple(int(c * alpha) for c in (255, 50, 50))

            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=scaled_font)
                tw = bbox[2] - bbox[0]
                x = (W - tw) // 2 + shake_x
                y = y_start + j * line_height + shake_y
                draw.text((x + 2, y + 2), line, font=scaled_font, fill=(0, 0, 0))
                draw.text((x, y), line, font=scaled_font, fill=color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _hook_book_rating(
    text: str, output_path: str, config: SectionConfig, bg_image: str = "",
) -> str:
    """Book rating with animated stars."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    # Parse rating from text (e.g. "4.5/5" or just "4.5")
    import re
    rating_match = re.search(r'(\d+\.?\d*)\s*/?\s*5?', text)
    rating = float(rating_match.group(1)) if rating_match else 5.0
    rating = min(5.0, max(0, rating))
    full_stars = int(rating)
    half_star = rating - full_stars >= 0.5

    tmpdir = tempfile.mkdtemp(prefix="hook_rating_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            # Title font
            title_font = _load_font(config, config.font_size_body)
            star_font = _load_font(config, 64)

            # Fade in
            alpha = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            # Draw title text
            title_color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(text, title_font, int(W * 0.85), draw)
            line_h = config.font_size_body + 10
            y_text = H // 2 - 100
            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=title_font)
                tw = bbox[2] - bbox[0]
                x = (W - tw) // 2
                draw.text((x, y_text + j * line_h), line, font=title_font, fill=title_color)

            # Draw stars — animate appearance
            star_y = H // 2 + 50
            star_width = 60
            total_star_w = 5 * star_width
            star_x_start = (W - total_star_w) // 2

            for s in range(5):
                # Each star appears sequentially
                star_progress = max(0, (progress * 5 - s * 0.8)) / 1.5
                star_alpha = min(1.0, star_progress) * alpha

                sx = star_x_start + s * star_width
                sy = star_y

                if s < full_stars:
                    # Full star — gold
                    color = tuple(int(c * star_alpha) for c in (255, 215, 0))
                    draw.text((sx, sy), "★", font=star_font, fill=color)
                elif s == full_stars and half_star:
                    # Half star
                    color = tuple(int(c * star_alpha) for c in (255, 215, 0))
                    draw.text((sx, sy), "★", font=star_font, fill=color)
                    # Overlay half gray
                    gray = tuple(int(c * star_alpha) for c in (100, 100, 100))
                    draw.text((sx, sy), "☆", font=star_font, fill=gray)
                else:
                    # Empty star
                    gray = tuple(int(c * star_alpha) for c in (100, 100, 100))
                    draw.text((sx, sy), "☆", font=star_font, fill=gray)

            # Rating number
            num_font = _load_font(config, 56)
            rating_text = f"{rating:.1f}/5"
            bbox = draw.textbbox((0, 0), rating_text, font=num_font)
            rw = bbox[2] - bbox[0]
            rx = (W - rw) // 2
            ry = star_y + 80
            num_color = tuple(int(c * alpha) for c in config.accent_color)
            draw.text((rx, ry), rating_text, font=num_font, fill=num_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _hook_quote_reveal(
    text: str, output_path: str, config: SectionConfig, bg_image: str = "",
) -> str:
    """Typewriter quote reveal effect."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)
    font = _load_font(config, config.font_size_body)

    tmpdir = tempfile.mkdtemp(prefix="hook_quote_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            # Typewriter: reveal characters over 70% of duration
            if progress < 0.7:
                chars_to_show = int(len(text) * (progress / 0.7))
            else:
                chars_to_show = len(text)

            visible_text = text[:chars_to_show]

            # Draw quotation marks
            quote_font = _load_font(config, config.font_size_title)
            alpha = min(1.0, progress / 0.1)
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            quote_color = tuple(int(c * alpha * 0.3) for c in config.accent_color)
            draw.text((W * 0.1, H * 0.3), '"', font=quote_font, fill=quote_color)

            # Draw text
            text_color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(visible_text, font, int(W * 0.75), draw)
            line_h = config.font_size_body + 12
            y_start = int(H * 0.4)

            for j, line in enumerate(lines):
                x = int(W * 0.12)
                y = y_start + j * line_h
                draw.text((x, y), line, font=font, fill=text_color)

            # Blinking cursor
            if progress < 0.7 and (i // 8) % 2 == 0:
                cursor_x = int(W * 0.12)
                if lines:
                    last_line = lines[-1]
                    bbox = draw.textbbox((0, 0), last_line, font=font)
                    cursor_x += bbox[2] - bbox[0] + 5
                cursor_y = y_start + (len(lines) - 1) * line_h
                draw.rectangle(
                    [cursor_x, cursor_y, cursor_x + 3, cursor_y + config.font_size_body],
                    fill=config.accent_color,
                )

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _hook_mystery(
    text: str, output_path: str, config: SectionConfig, bg_image: str = "",
) -> str:
    """Mystery blur-to-clear reveal."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)
    font = _load_font(config, config.font_size_title)

    tmpdir = tempfile.mkdtemp(prefix="hook_mystery_")
    try:
        # Pre-render the final clear frame
        clear_img = Image.new("RGB", (W, H), config.bg_color)
        draw = ImageDraw.Draw(clear_img)
        lines = _wrap_text(text, font, int(W * 0.85), draw)
        line_h = config.font_size_title + 10
        total_h = line_h * len(lines)
        y_start = (H - total_h) // 2

        for j, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (W - tw) // 2
            draw.text((x + 3, y_start + j * line_h + 3), line, font=font, fill=(30, 30, 30))
            draw.text((x, y_start + j * line_h), line, font=font, fill=config.text_color)

        for i in range(num_frames):
            progress = i / max(num_frames - 1, 1)

            # Blur amount decreases over time
            if progress < 0.6:
                blur_amount = int(20 * (1 - progress / 0.6))
            else:
                blur_amount = 0

            frame = clear_img.copy()
            if blur_amount > 0:
                frame = frame.filter(ImageFilter.GaussianBlur(radius=blur_amount))

            # Fade
            if progress < 0.1:
                alpha = progress / 0.1
                black = Image.new("RGB", (W, H), (0, 0, 0))
                frame = Image.blend(black, frame, alpha)
            elif progress > 0.9:
                alpha = (1.0 - progress) / 0.1
                black = Image.new("RGB", (W, H), (0, 0, 0))
                frame = Image.blend(black, frame, alpha)

            frame.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TITLE CARD GENERATORS
# ---------------------------------------------------------------------------

def generate_title_card(
    book_title: str,
    author: str = "",
    style: str = "book_cover",
    output_path: str = "title.mp4",
    config: SectionConfig | None = None,
    cover_image_path: str = "",
) -> str:
    """Generate a title card video section.

    Styles:
        - book_cover: Cover image with title overlay
        - minimalist: Clean text on dark background
        - gradient_card: Gradient background with text
        - split_screen: Cover left, info right

    Returns:
        Path to the generated MP4 clip.
    """
    if Image is None:
        raise ImportError("Pillow is required")

    if config is None:
        config = SectionConfig()

    generators = {
        "book_cover": _title_book_cover,
        "minimalist": _title_minimalist,
        "gradient_card": _title_gradient_card,
        "split_screen": _title_split_screen,
    }

    generator = generators.get(style, _title_minimalist)
    return generator(book_title, author, output_path, config, cover_image_path)


def _title_minimalist(
    title: str, author: str, output_path: str, config: SectionConfig, cover: str = "",
) -> str:
    """Clean minimalist title card."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="title_min_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            alpha = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            # Title
            title_font = _load_font(config, config.font_size_title)
            title_color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(title, title_font, int(W * 0.8), draw)
            line_h = config.font_size_title + 8
            y = H // 2 - 60
            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=title_font)
                x = (W - (bbox[2] - bbox[0])) // 2
                draw.text((x, y + j * line_h), line, font=title_font, fill=title_color)

            # Accent line
            line_y = y + len(lines) * line_h + 20
            line_w = int(200 * min(1.0, progress / 0.3))
            accent = tuple(int(c * alpha) for c in config.accent_color)
            draw.rectangle(
                [(W // 2 - line_w // 2, line_y), (W // 2 + line_w // 2, line_y + 4)],
                fill=accent,
            )

            # Author
            if author:
                author_font = _load_font(config, config.font_size_small)
                author_color = tuple(int(c * alpha) for c in config.secondary_color)
                bbox = draw.textbbox((0, 0), author, font=author_font)
                ax = (W - (bbox[2] - bbox[0])) // 2
                draw.text((ax, line_y + 30), author, font=author_font, fill=author_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _title_book_cover(
    title: str, author: str, output_path: str, config: SectionConfig, cover: str = "",
) -> str:
    """Title card with book cover image."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="title_cover_")
    try:
        # Load cover image
        cover_img = None
        if cover and os.path.exists(cover):
            try:
                cover_img = Image.open(cover)
                # Resize to fit — max 60% of width, center
                cw = int(W * 0.5)
                ratio = cw / cover_img.width
                ch = int(cover_img.height * ratio)
                if ch > int(H * 0.4):
                    ch = int(H * 0.4)
                    ratio = ch / cover_img.height
                    cw = int(cover_img.width * ratio)
                cover_img = cover_img.resize((cw, ch), Image.LANCZOS)
            except Exception:
                cover_img = None

        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            alpha = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            y_offset = 0
            if cover_img:
                # Slide cover in from top
                slide = _ease_out(min(1.0, progress / 0.3))
                cx = (W - cover_img.width) // 2
                cy = int(H * 0.15 * slide)
                if alpha < 1.0:
                    tmp = cover_img.copy()
                    img.paste(tmp, (cx, cy))
                else:
                    img.paste(cover_img, (cx, cy))
                y_offset = cy + cover_img.height + 30

            # Title below cover
            title_font = _load_font(config, config.font_size_body)
            title_color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(title, title_font, int(W * 0.85), draw)
            line_h = config.font_size_body + 8
            ty = y_offset if cover_img else (H // 2 - 40)

            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=title_font)
                x = (W - (bbox[2] - bbox[0])) // 2
                draw.text((x, ty + j * line_h), line, font=title_font, fill=title_color)

            # Author
            if author:
                author_font = _load_font(config, config.font_size_small)
                author_color = tuple(int(c * alpha) for c in config.secondary_color)
                ay = ty + len(lines) * line_h + 15
                bbox = draw.textbbox((0, 0), author, font=author_font)
                ax = (W - (bbox[2] - bbox[0])) // 2
                draw.text((ax, ay), f"— {author}", font=author_font, fill=author_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _title_gradient_card(
    title: str, author: str, output_path: str, config: SectionConfig, cover: str = "",
) -> str:
    """Gradient background title card."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="title_grad_")
    try:
        # Create gradient background
        gradient = Image.new("RGB", (W, H))
        for y in range(H):
            ratio = y / H
            r = int(config.accent_color[0] * (1 - ratio) + config.bg_color[0] * ratio)
            g = int(config.accent_color[1] * (1 - ratio) + config.bg_color[1] * ratio)
            b = int(config.accent_color[2] * (1 - ratio) + config.bg_color[2] * ratio)
            for x in range(W):
                gradient.putpixel((x, y), (r, g, b))

        for i in range(num_frames):
            img = gradient.copy()
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            alpha = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            # Title
            title_font = _load_font(config, config.font_size_title)
            color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(title, title_font, int(W * 0.8), draw)
            line_h = config.font_size_title + 8
            y_start = H // 2 - len(lines) * line_h // 2

            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=title_font)
                x = (W - (bbox[2] - bbox[0])) // 2
                # Shadow
                draw.text((x + 3, y_start + j * line_h + 3), line, font=title_font,
                          fill=tuple(int(c * alpha * 0.3) for c in (0, 0, 0)))
                draw.text((x, y_start + j * line_h), line, font=title_font, fill=color)

            if author:
                author_font = _load_font(config, config.font_size_small)
                auth_color = tuple(int(c * alpha * 0.8) for c in config.text_color)
                ay = y_start + len(lines) * line_h + 20
                bbox = draw.textbbox((0, 0), author, font=author_font)
                ax = (W - (bbox[2] - bbox[0])) // 2
                draw.text((ax, ay), author, font=author_font, fill=auth_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _title_split_screen(
    title: str, author: str, output_path: str, config: SectionConfig, cover: str = "",
) -> str:
    """Split screen: cover left, text right."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="title_split_")
    try:
        cover_img = None
        if cover and os.path.exists(cover):
            try:
                cover_img = Image.open(cover).resize(
                    (W // 2, H), Image.LANCZOS,
                )
            except Exception:
                pass

        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            alpha = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            # Left side: cover or accent color
            left_w = W // 2
            if cover_img:
                slide = _ease_out(min(1.0, progress / 0.3))
                offset = int(left_w * (1 - slide))
                img.paste(cover_img, (-offset, 0))
            else:
                accent_rect = Image.new("RGB", (left_w, H), config.accent_color)
                img.paste(accent_rect, (0, 0))

            # Right side: text
            text_x = left_w + 40
            text_w = W - text_x - 40

            title_font = _load_font(config, config.font_size_body)
            title_color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(title, title_font, text_w, draw)
            line_h = config.font_size_body + 8
            ty = H // 2 - len(lines) * line_h // 2

            for j, line in enumerate(lines):
                draw.text((text_x, ty + j * line_h), line,
                          font=title_font, fill=title_color)

            if author:
                author_font = _load_font(config, config.font_size_small)
                auth_color = tuple(int(c * alpha) for c in config.secondary_color)
                ay = ty + len(lines) * line_h + 20
                draw.text((text_x, ay), f"— {author}",
                          font=author_font, fill=auth_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# OUTRO GENERATORS
# ---------------------------------------------------------------------------

def generate_outro(
    text: str = "Cảm ơn đã xem!",
    style: str = "subscribe_cta",
    output_path: str = "outro.mp4",
    config: SectionConfig | None = None,
    channel_name: str = "",
    next_book: str = "",
) -> str:
    """Generate an outro video section.

    Styles:
        - subscribe_cta: Follow/subscribe call to action
        - rating_summary: Final rating card
        - next_book: Preview next book
        - social_links: Social media icons

    Returns:
        Path to generated MP4 clip.
    """
    if Image is None:
        raise ImportError("Pillow is required")

    if config is None:
        config = SectionConfig()

    generators = {
        "subscribe_cta": _outro_subscribe,
        "rating_summary": _outro_rating,
        "next_book": _outro_next_book,
    }

    generator = generators.get(style, _outro_subscribe)
    return generator(text, output_path, config, channel_name, next_book)


def _outro_subscribe(
    text: str, output_path: str, config: SectionConfig,
    channel: str = "", next_book: str = "",
) -> str:
    """Subscribe/follow CTA outro."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="outro_sub_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            alpha = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            # Main text
            font = _load_font(config, config.font_size_title)
            color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(text, font, int(W * 0.85), draw)
            line_h = config.font_size_title + 10
            y = H // 2 - 120

            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                x = (W - (bbox[2] - bbox[0])) // 2
                draw.text((x, y + j * line_h), line, font=font, fill=color)

            # Subscribe button
            btn_y = y + len(lines) * line_h + 50
            btn_w = 300
            btn_h = 60
            btn_x = (W - btn_w) // 2

            # Button slide-in
            if progress > 0.3:
                btn_progress = min(1.0, (progress - 0.3) / 0.2)
                btn_alpha = _ease_out(btn_progress) * alpha

                btn_color = tuple(int(c * btn_alpha) for c in (220, 38, 38))
                draw.rounded_rectangle(
                    [(btn_x, btn_y), (btn_x + btn_w, btn_y + btn_h)],
                    radius=30,
                    fill=btn_color,
                )

                btn_font = _load_font(config, 28)
                btn_text = "FOLLOW ❤️"
                bbox = draw.textbbox((0, 0), btn_text, font=btn_font)
                tw = bbox[2] - bbox[0]
                tx = (W - tw) // 2
                ty = btn_y + (btn_h - 28) // 2
                btn_text_color = tuple(int(255 * btn_alpha) for _ in range(3))
                draw.text((tx, ty), btn_text, font=btn_font, fill=btn_text_color)

            # Channel name
            if channel:
                ch_font = _load_font(config, config.font_size_small)
                ch_color = tuple(int(c * alpha) for c in config.secondary_color)
                bbox = draw.textbbox((0, 0), channel, font=ch_font)
                cx = (W - (bbox[2] - bbox[0])) // 2
                draw.text((cx, btn_y + btn_h + 30), channel, font=ch_font, fill=ch_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _outro_rating(
    text: str, output_path: str, config: SectionConfig,
    channel: str = "", next_book: str = "",
) -> str:
    """Rating summary outro — reuses book_rating hook style."""
    return _hook_book_rating(text, output_path, config)


def _outro_next_book(
    text: str, output_path: str, config: SectionConfig,
    channel: str = "", next_book: str = "",
) -> str:
    """Next book preview outro."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="outro_next_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            alpha = min(1.0, progress / 0.2) if progress < 0.2 else 1.0
            if progress > 0.9:
                alpha = (1.0 - progress) / 0.1

            # "Tiếp theo:" header
            header_font = _load_font(config, config.font_size_small)
            header_color = tuple(int(c * alpha) for c in config.accent_color)
            bbox = draw.textbbox((0, 0), "Tiếp theo:", font=header_font)
            hx = (W - (bbox[2] - bbox[0])) // 2
            draw.text((hx, H // 2 - 80), "Tiếp theo:", font=header_font, fill=header_color)

            # Next book title
            title_font = _load_font(config, config.font_size_body)
            title_text = next_book or text
            title_color = tuple(int(c * alpha) for c in config.text_color)
            lines = _wrap_text(title_text, title_font, int(W * 0.8), draw)
            line_h = config.font_size_body + 8
            ty = H // 2 - 20

            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=title_font)
                x = (W - (bbox[2] - bbox[0])) // 2
                draw.text((x, ty + j * line_h), line, font=title_font, fill=title_color)

            # Animated arrow
            import math
            arrow_y = ty + len(lines) * line_h + 40 + int(10 * math.sin(progress * 8))
            arrow_font = _load_font(config, 48)
            arrow_color = tuple(int(c * alpha) for c in config.accent_color)
            bbox = draw.textbbox((0, 0), "→", font=arrow_font)
            ax = (W - (bbox[2] - bbox[0])) // 2
            draw.text((ax, arrow_y), "→", font=arrow_font, fill=arrow_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# TEXT OVERLAY GENERATORS
# ---------------------------------------------------------------------------

def generate_text_overlay(
    text: str,
    style: str = "lower_third",
    output_path: str = "overlay.mp4",
    config: SectionConfig | None = None,
) -> str:
    """Generate a text overlay video section.

    Styles:
        - lower_third: Text bar at bottom
        - full_screen_quote: Centered quote
        - bullet_points: Animated bullet list
        - highlight_box: Text in colored box

    Returns:
        Path to generated MP4 clip (with transparency where possible).
    """
    if Image is None:
        raise ImportError("Pillow is required")

    if config is None:
        config = SectionConfig()

    generators = {
        "lower_third": _overlay_lower_third,
        "full_screen_quote": _overlay_full_quote,
        "bullet_points": _overlay_bullets,
        "highlight_box": _overlay_highlight,
    }

    generator = generators.get(style, _overlay_lower_third)
    return generator(text, output_path, config)


def _overlay_lower_third(
    text: str, output_path: str, config: SectionConfig,
) -> str:
    """Lower-third text bar."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="overlay_lt_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            # Bar slide-in from left
            bar_h = 80
            bar_y = H - bar_h - 100
            if progress < 0.2:
                bar_w = int(W * _ease_out(progress / 0.2))
            elif progress > 0.85:
                bar_w = int(W * _ease_out((1 - progress) / 0.15))
            else:
                bar_w = W

            # Semi-transparent bar
            bar_color = tuple(int(c * 0.8) for c in config.accent_color)
            draw.rectangle([(0, bar_y), (bar_w, bar_y + bar_h)], fill=bar_color)

            # Text on bar
            if bar_w > W * 0.3:
                font = _load_font(config, config.font_size_body)
                text_alpha = min(1.0, (progress - 0.15) / 0.1) if progress > 0.15 else 0
                if progress > 0.85:
                    text_alpha *= (1 - progress) / 0.15
                text_color = tuple(int(255 * text_alpha) for _ in range(3))
                draw.text(
                    (40, bar_y + (bar_h - config.font_size_body) // 2),
                    text, font=font, fill=text_color,
                )

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _overlay_full_quote(
    text: str, output_path: str, config: SectionConfig,
) -> str:
    """Full screen centered quote — reuses quote_reveal."""
    return _hook_quote_reveal(text, output_path, config)


def _overlay_bullets(
    text: str, output_path: str, config: SectionConfig,
) -> str:
    """Animated bullet points (split text by newlines or •)."""
    import re
    items = [s.strip() for s in re.split(r'[\n•\-]', text) if s.strip()]
    if not items:
        items = [text]

    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="overlay_bul_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            font = _load_font(config, config.font_size_body)
            dot_font = _load_font(config, config.font_size_body)

            line_h = config.font_size_body + 20
            y_start = (H - len(items) * line_h) // 2

            for idx, item in enumerate(items):
                # Each bullet appears sequentially
                item_delay = idx * 0.12
                item_progress = max(0, progress - item_delay) / max(0.15, 1 - item_delay)
                item_progress = min(1.0, item_progress)

                if item_progress <= 0:
                    continue

                alpha = _ease_out(item_progress)
                if progress > 0.9:
                    alpha *= (1.0 - progress) / 0.1

                # Slide in from left
                x_offset = int(80 * (1 - alpha))
                x = 80 - x_offset
                y = y_start + idx * line_h

                # Bullet dot
                dot_color = tuple(int(c * alpha) for c in config.accent_color)
                draw.text((x, y), "•", font=dot_font, fill=dot_color)

                # Text
                text_color = tuple(int(c * alpha) for c in config.text_color)
                draw.text((x + 30, y), item, font=font, fill=text_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _overlay_highlight(
    text: str, output_path: str, config: SectionConfig,
) -> str:
    """Text in a highlighted colored box."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)

    tmpdir = tempfile.mkdtemp(prefix="overlay_hl_")
    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), config.bg_color)
            draw = ImageDraw.Draw(img)
            progress = i / max(num_frames - 1, 1)

            alpha = min(1.0, progress / 0.15) if progress < 0.15 else 1.0
            if progress > 0.85:
                alpha = (1.0 - progress) / 0.15

            font = _load_font(config, config.font_size_body)
            lines = _wrap_text(text, font, int(W * 0.75), draw)
            line_h = config.font_size_body + 12
            total_h = line_h * len(lines)

            # Box dimensions
            pad = 30
            box_w = int(W * 0.85)
            box_h = total_h + pad * 2
            box_x = (W - box_w) // 2
            box_y = (H - box_h) // 2

            # Rounded box with accent color
            box_color = tuple(int(c * alpha * 0.9) for c in config.accent_color)
            draw.rounded_rectangle(
                [(box_x, box_y), (box_x + box_w, box_y + box_h)],
                radius=20,
                fill=box_color,
            )

            # Text inside box
            text_color = tuple(int(255 * alpha) for _ in range(3))
            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                tx = (W - (bbox[2] - bbox[0])) // 2
                ty = box_y + pad + j * line_h
                draw.text((tx, ty), line, font=font, fill=text_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Font helper for standalone section generators
# ---------------------------------------------------------------------------


def _get_font(size: int, bold: bool = False):
    """Load a font by size, standalone helper for intro generators."""
    font_paths_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    font_paths_regular = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    paths = (font_paths_bold if bold else font_paths_regular) + font_paths_bold + font_paths_regular
    for fp in paths:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Intro Templates
# ---------------------------------------------------------------------------


def generate_intro(
    text: str = "",
    style: str = "logo_reveal",
    output_path: str = "intro.mp4",
    config: SectionConfig | None = None,
    logo_text: str = "BookAI",
    channel_name: str = "",
    genre: str = "",
) -> str:
    """Generate an intro video section.

    Styles:
        - logo_reveal:       Logo/brand text zooms in with glow
        - countdown:         3-2-1 countdown with circles
        - channel_branding:  Channel name + tagline slide-in
        - genre_mood:        Genre-themed mood intro (fiction, business, etc.)

    Returns:
        Path to generated MP4 clip.
    """
    if Image is None:
        raise ImportError("Pillow is required for video sections")

    if config is None:
        config = SectionConfig(duration=4.0)

    dispatch = {
        "logo_reveal": _intro_logo_reveal,
        "countdown": _intro_countdown,
        "channel_branding": _intro_channel_branding,
        "genre_mood": _intro_genre_mood,
    }

    generator = dispatch.get(style, _intro_logo_reveal)
    return generator(
        text=text, output_path=output_path, config=config,
        logo_text=logo_text, channel_name=channel_name, genre=genre,
    )


def _intro_logo_reveal(
    text: str, output_path: str, config: SectionConfig,
    logo_text: str = "BookAI", **kwargs,
) -> str:
    """Logo/brand text zoom-in with glow effect."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)
    tmpdir = tempfile.mkdtemp(prefix="intro_logo_")

    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), (10, 10, 20))
            draw = ImageDraw.Draw(img)
            t = i / max(num_frames - 1, 1)

            # Phase 1 (0-0.4): zoom in
            # Phase 2 (0.4-0.7): glow pulse
            # Phase 3 (0.7-1.0): hold + subtitle fade in

            if t < 0.4:
                scale = 0.3 + 0.7 * (t / 0.4) ** 0.5
                alpha = min(1.0, t / 0.2)
            elif t < 0.7:
                scale = 1.0
                alpha = 1.0
            else:
                scale = 1.0
                alpha = 1.0

            # Logo text
            font_size = int(W * 0.12 * scale)
            font = _get_font(font_size, bold=True)
            text_color = tuple(int(255 * alpha) for _ in range(3))

            bbox = draw.textbbox((0, 0), logo_text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tx = (W - tw) // 2
            ty = int(H * 0.42) - th // 2

            # Glow effect (circle behind text)
            if t > 0.15:
                glow_alpha = int(40 * alpha)
                glow_r = int(tw * 0.8)
                for r in range(glow_r, 0, -5):
                    glow_c = (glow_alpha // 3, glow_alpha // 2, glow_alpha)
                    cx, cy = W // 2, int(H * 0.42)
                    draw.ellipse(
                        [(cx - r, cy - r), (cx + r, cy + r)],
                        fill=glow_c,
                    )

            draw.text((tx, ty), logo_text, font=font, fill=text_color)

            # Subtitle text
            if t > 0.6 and text:
                sub_alpha = min(1.0, (t - 0.6) / 0.3)
                sub_font = _get_font(int(W * 0.04))
                sub_color = tuple(int(200 * sub_alpha) for _ in range(3))
                sbbox = draw.textbbox((0, 0), text, font=sub_font)
                stw = sbbox[2] - sbbox[0]
                draw.text(
                    ((W - stw) // 2, int(H * 0.52)),
                    text, font=sub_font, fill=sub_color,
                )

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _intro_countdown(
    text: str, output_path: str, config: SectionConfig, **kwargs,
) -> str:
    """3-2-1 countdown with animated circles."""
    W, H = config.width, config.height
    # Force 3 seconds for countdown
    duration = max(config.duration, 3.0)
    num_frames = int(duration * config.fps)
    tmpdir = tempfile.mkdtemp(prefix="intro_count_")

    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), (15, 15, 25))
            draw = ImageDraw.Draw(img)
            t = i / max(num_frames - 1, 1)

            # Which number? 3→2→1
            third = 1.0 / 3.0
            if t < third:
                number = "3"
                local_t = t / third
                circle_color = (255, 100, 100)
            elif t < 2 * third:
                number = "2"
                local_t = (t - third) / third
                circle_color = (255, 200, 50)
            else:
                number = "1"
                local_t = (t - 2 * third) / third
                circle_color = (100, 255, 100)

            # Animated circle (expand + fade)
            circle_r = int(min(W, H) * 0.2 * (0.5 + 0.5 * (1 - abs(local_t - 0.5) * 2)))
            alpha_mult = 1.0 - abs(local_t - 0.5) * 1.5
            alpha_mult = max(0, min(1, alpha_mult))

            cx, cy = W // 2, H // 2
            fill = tuple(int(c * alpha_mult * 0.3) for c in circle_color)
            draw.ellipse(
                [(cx - circle_r, cy - circle_r), (cx + circle_r, cy + circle_r)],
                fill=fill,
                outline=tuple(int(c * alpha_mult) for c in circle_color),
                width=4,
            )

            # Number
            font_size = int(min(W, H) * 0.15 * (0.8 + 0.4 * alpha_mult))
            font = _get_font(font_size, bold=True)
            num_color = tuple(int(c * alpha_mult) for c in circle_color)
            bbox = draw.textbbox((0, 0), number, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((W - tw) // 2, (H - th) // 2), number, font=font, fill=num_color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _intro_channel_branding(
    text: str, output_path: str, config: SectionConfig,
    channel_name: str = "", **kwargs,
) -> str:
    """Channel name + tagline slide-in from left."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)
    tmpdir = tempfile.mkdtemp(prefix="intro_brand_")

    display_name = channel_name or "BookAI Channel"
    tagline = text or "Review sách hay mỗi tuần"

    try:
        for i in range(num_frames):
            img = Image.new("RGB", (W, H), (18, 18, 30))
            draw = ImageDraw.Draw(img)
            t = i / max(num_frames - 1, 1)

            # Slide-in from left (0-0.3), hold (0.3-0.8), fade out (0.8-1.0)
            if t < 0.3:
                slide = t / 0.3
                offset_x = int(W * (1 - slide))
                alpha = slide
            elif t < 0.8:
                offset_x = 0
                alpha = 1.0
            else:
                offset_x = 0
                alpha = 1.0 - (t - 0.8) / 0.2

            # Channel name
            name_font = _get_font(int(W * 0.08), bold=True)
            name_color = tuple(int(255 * alpha) for _ in range(3))
            nbbox = draw.textbbox((0, 0), display_name, font=name_font)
            ntw = nbbox[2] - nbbox[0]
            nx = (W - ntw) // 2 - offset_x
            draw.text((nx, int(H * 0.40)), display_name, font=name_font, fill=name_color)

            # Divider line
            line_w = int(W * 0.4 * min(1, alpha * 1.5))
            line_y = int(H * 0.47)
            line_color = (int(100 * alpha), int(200 * alpha), int(255 * alpha))
            draw.line(
                [(W // 2 - line_w // 2, line_y), (W // 2 + line_w // 2, line_y)],
                fill=line_color, width=3,
            )

            # Tagline
            if t > 0.15:
                tag_alpha = min(1.0, (t - 0.15) / 0.3) * alpha
                tag_font = _get_font(int(W * 0.04))
                tag_color = tuple(int(180 * tag_alpha) for _ in range(3))
                tbbox = draw.textbbox((0, 0), tagline, font=tag_font)
                ttw = tbbox[2] - tbbox[0]
                draw.text(
                    ((W - ttw) // 2, int(H * 0.50)),
                    tagline, font=tag_font, fill=tag_color,
                )

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _intro_genre_mood(
    text: str, output_path: str, config: SectionConfig,
    genre: str = "", **kwargs,
) -> str:
    """Genre-themed mood intro with color scheme."""
    W, H = config.width, config.height
    num_frames = int(config.duration * config.fps)
    tmpdir = tempfile.mkdtemp(prefix="intro_genre_")

    # Genre color schemes
    genre_themes = {
        "fiction": {"bg": (20, 15, 35), "accent": (180, 100, 255), "label": "📖 Fiction"},
        "business": {"bg": (15, 25, 20), "accent": (80, 200, 120), "label": "💼 Business"},
        "self_help": {"bg": (35, 25, 10), "accent": (255, 180, 50), "label": "🌟 Self-Help"},
        "science": {"bg": (10, 20, 35), "accent": (100, 180, 255), "label": "🔬 Science"},
        "history": {"bg": (30, 20, 15), "accent": (200, 150, 100), "label": "📜 History"},
        "romance": {"bg": (35, 15, 25), "accent": (255, 100, 150), "label": "❤️ Romance"},
    }
    theme = genre_themes.get(genre, genre_themes.get("fiction"))
    display_text = text or theme["label"]

    try:
        for i in range(num_frames):
            bg = theme["bg"]
            img = Image.new("RGB", (W, H), bg)
            draw = ImageDraw.Draw(img)
            t = i / max(num_frames - 1, 1)

            # Fade in (0-0.3), pulse (0.3-0.7), fade out (0.7-1.0)
            if t < 0.3:
                alpha = t / 0.3
            elif t < 0.7:
                alpha = 1.0
            else:
                alpha = 1.0 - (t - 0.7) / 0.3

            accent = theme["accent"]

            # Ambient circles
            import math as _math
            for j in range(3):
                phase = t * 2 + j * 2.1
                cx = int(W * (0.3 + 0.4 * _math.sin(phase)))
                cy = int(H * (0.3 + 0.4 * _math.cos(phase * 0.7)))
                r = int(min(W, H) * 0.15)
                c = tuple(int(v * alpha * 0.08) for v in accent)
                draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=c)

            # Genre label
            font = _get_font(int(W * 0.09), bold=True)
            color = tuple(int(v * alpha) for v in accent)
            bbox = draw.textbbox((0, 0), display_text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(((W - tw) // 2, (H - th) // 2), display_text, font=font, fill=color)

            img.save(os.path.join(tmpdir, f"frame_{i:04d}.png"))

        return _render_frames_to_video(tmpdir, output_path, config.fps)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
