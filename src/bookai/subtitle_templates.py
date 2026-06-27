"""
CapCut-style subtitle templates for BookAI video pipeline.

Generates styled subtitle overlay images using PIL and composites them
onto video using FFmpeg. Supports multiple template styles including
rounded box, keyword highlighting, neon glow, karaoke, and more.

Usage:
    from bookai.subtitle_templates import burn_styled_subtitles, TEMPLATES
    
    success = burn_styled_subtitles(
        video_path="input.mp4",
        srt_path="subtitle.srt",
        output_path="output.mp4",
        template="capcut_white_box",
        video_width=1080,
        video_height=1920,
    )
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None  # type: ignore


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

@dataclass
class SubtitleTemplate:
    """Defines visual style for subtitle rendering."""
    name: str
    description: str

    # Font
    font_name: str = "BeVietnamPro-Bold"
    font_size: int = 42          # Relative to 1080px width
    font_color: str = "#FFFFFF"
    font_bold: bool = True

    # Background box
    bg_enabled: bool = False
    bg_color: str = "#FFFFFF"
    bg_opacity: float = 0.95     # 0-1
    bg_corner_radius: int = 20
    bg_padding_x: int = 40       # Horizontal padding inside box
    bg_padding_y: int = 20       # Vertical padding inside box

    # Outline / stroke
    outline_enabled: bool = True
    outline_color: str = "#000000"
    outline_width: int = 3

    # Shadow
    shadow_enabled: bool = False
    shadow_color: str = "#00000080"
    shadow_offset_x: int = 3
    shadow_offset_y: int = 3

    # Keyword highlight
    highlight_enabled: bool = False
    highlight_color: str = "#4A90D9"  # Blue like CapCut
    highlight_bg_color: str = ""      # Background for highlighted words
    highlight_uppercase: bool = False

    # Position (percentage from bottom: 0=bottom edge, 100=top)
    position_bottom_pct: float = 12.0

    # Text transform
    uppercase: bool = False
    max_chars_per_line: int = 25
    line_spacing: int = 8

    # Animation (future)
    animation: str = "none"  # none, fade, pop, slide_up


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, SubtitleTemplate] = {
    "classic": SubtitleTemplate(
        name="classic",
        description="Chữ trắng viền đen — kinh điển",
        font_size=40,
        font_color="#FFFFFF",
        outline_enabled=True,
        outline_color="#000000",
        outline_width=4,
        shadow_enabled=True,
        shadow_color="#00000080",
        shadow_offset_x=2,
        shadow_offset_y=2,
        position_bottom_pct=10.0,
    ),

    "capcut_white_box": SubtitleTemplate(
        name="capcut_white_box",
        description="Hộp trắng bo tròn, chữ đen — kiểu CapCut",
        font_size=38,
        font_color="#1A1A1A",
        font_bold=True,
        bg_enabled=True,
        bg_color="#FFFFFF",
        bg_opacity=0.95,
        bg_corner_radius=25,
        bg_padding_x=45,
        bg_padding_y=25,
        outline_enabled=False,
        shadow_enabled=True,
        shadow_color="#00000030",
        shadow_offset_x=0,
        shadow_offset_y=4,
        highlight_enabled=True,
        highlight_color="#2B7DE9",
        position_bottom_pct=15.0,
        max_chars_per_line=22,
    ),

    "capcut_dark_box": SubtitleTemplate(
        name="capcut_dark_box",
        description="Hộp đen bo tròn, chữ trắng — tối giản",
        font_size=38,
        font_color="#FFFFFF",
        font_bold=True,
        bg_enabled=True,
        bg_color="#1A1A1A",
        bg_opacity=0.88,
        bg_corner_radius=25,
        bg_padding_x=45,
        bg_padding_y=25,
        outline_enabled=False,
        shadow_enabled=False,
        highlight_enabled=True,
        highlight_color="#FFD700",
        position_bottom_pct=15.0,
        max_chars_per_line=22,
    ),

    "capcut_gradient_box": SubtitleTemplate(
        name="capcut_gradient_box",
        description="Hộp gradient xám-đen, chữ trắng — sang trọng",
        font_size=38,
        font_color="#FFFFFF",
        font_bold=True,
        bg_enabled=True,
        bg_color="#2D2D2D",
        bg_opacity=0.85,
        bg_corner_radius=20,
        bg_padding_x=45,
        bg_padding_y=22,
        outline_enabled=False,
        shadow_enabled=True,
        shadow_color="#00000050",
        shadow_offset_x=0,
        shadow_offset_y=3,
        highlight_enabled=True,
        highlight_color="#00E5FF",
        position_bottom_pct=14.0,
        max_chars_per_line=22,
    ),

    "neon_glow": SubtitleTemplate(
        name="neon_glow",
        description="Chữ phát sáng neon — nổi bật",
        font_size=44,
        font_color="#00FF88",
        font_bold=True,
        outline_enabled=True,
        outline_color="#00FF88",
        outline_width=3,
        shadow_enabled=True,
        shadow_color="#00FF8880",
        shadow_offset_x=0,
        shadow_offset_y=0,
        position_bottom_pct=12.0,
        max_chars_per_line=20,
    ),

    "bold_impact": SubtitleTemplate(
        name="bold_impact",
        description="Chữ to đậm vàng — gây ấn tượng mạnh",
        font_size=56,
        font_color="#FFD700",
        font_bold=True,
        outline_enabled=True,
        outline_color="#000000",
        outline_width=5,
        shadow_enabled=True,
        shadow_color="#000000AA",
        shadow_offset_x=4,
        shadow_offset_y=4,
        position_bottom_pct=20.0,
        uppercase=True,
        max_chars_per_line=16,
    ),

    "minimal_clean": SubtitleTemplate(
        name="minimal_clean",
        description="Chữ nhỏ gọn, tinh tế — tối giản",
        font_name="BeVietnamPro-Medium",
        font_size=30,
        font_color="#FFFFFF",
        font_bold=False,
        outline_enabled=False,
        shadow_enabled=True,
        shadow_color="#00000060",
        shadow_offset_x=1,
        shadow_offset_y=1,
        position_bottom_pct=8.0,
        max_chars_per_line=35,
    ),

    "karaoke_word": SubtitleTemplate(
        name="karaoke_word",
        description="Đổi màu từng từ theo giọng đọc — karaoke",
        font_size=42,
        font_color="#FFFFFF",
        font_bold=True,
        outline_enabled=True,
        outline_color="#000000",
        outline_width=3,
        highlight_enabled=True,
        highlight_color="#FFD700",
        position_bottom_pct=12.0,
        animation="karaoke",
        max_chars_per_line=25,
    ),

    "modern_pill": SubtitleTemplate(
        name="modern_pill",
        description="Hộp viên thuốc (pill) tròn — hiện đại",
        font_size=32,
        font_color="#FFFFFF",
        font_bold=True,
        bg_enabled=True,
        bg_color="#000000",
        bg_opacity=0.75,
        bg_corner_radius=50,  # Very round = pill shape
        bg_padding_x=50,
        bg_padding_y=18,
        outline_enabled=False,
        shadow_enabled=False,
        position_bottom_pct=10.0,
        max_chars_per_line=28,
    ),

    # --- 3 New templates ---

    "word_by_word_highlight": SubtitleTemplate(
        name="word_by_word_highlight",
        description="Highlight từng từ đang đọc — kiểu TikTok trending",
        font_size=48,
        font_color="#AAAAAA",  # Non-active words are gray
        font_bold=True,
        outline_enabled=True,
        outline_color="#000000",
        outline_width=4,
        highlight_enabled=True,
        highlight_color="#FFFFFF",  # Active word is bright white
        shadow_enabled=True,
        shadow_color="#00000090",
        shadow_offset_x=0,
        shadow_offset_y=3,
        position_bottom_pct=18.0,
        animation="karaoke",
        max_chars_per_line=18,
    ),

    "the_classic": SubtitleTemplate(
        name="the_classic",
        description="Kiểu phụ đề phim — vàng nhạt trên nền đen mờ",
        font_size=36,
        font_color="#FFFDD0",  # Cream/pale yellow
        font_bold=False,
        bg_enabled=True,
        bg_color="#000000",
        bg_opacity=0.6,
        bg_corner_radius=0,  # No rounding = cinematic bar
        bg_padding_x=60,
        bg_padding_y=12,
        outline_enabled=False,
        shadow_enabled=False,
        position_bottom_pct=5.0,
        max_chars_per_line=40,
    ),

    "chat_bubble": SubtitleTemplate(
        name="chat_bubble",
        description="Bong bóng chat — kiểu tin nhắn iMessage",
        font_size=34,
        font_color="#FFFFFF",
        font_bold=False,
        bg_enabled=True,
        bg_color="#007AFF",  # iMessage blue
        bg_opacity=0.92,
        bg_corner_radius=30,
        bg_padding_x=40,
        bg_padding_y=20,
        outline_enabled=False,
        shadow_enabled=True,
        shadow_color="#00000040",
        shadow_offset_x=0,
        shadow_offset_y=5,
        position_bottom_pct=12.0,
        max_chars_per_line=24,
    ),
}


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

@dataclass
class SRTEntry:
    """Single subtitle entry."""
    index: int
    start_seconds: float
    end_seconds: float
    text: str
    words: list[dict] = field(default_factory=list)  # For karaoke: [{word, start, end}]


def parse_srt(srt_path: str) -> list[SRTEntry]:
    """Parse SRT file into list of entries."""
    entries = []
    content = Path(srt_path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0])
        except ValueError:
            continue

        time_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1],
        )
        if not time_match:
            continue

        g = time_match.groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        end = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        text = "\n".join(lines[2:])

        entries.append(SRTEntry(index=idx, start_seconds=start, end_seconds=end, text=text))

    return entries


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

_FONT_DIRS = [
    os.path.join(os.path.dirname(__file__), "..", "..", "resource", "fonts"),
    "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF",
    "/usr/share/fonts/truetype/dejavu",
]


def _find_font(name: str, size: int) -> "ImageFont.FreeTypeFont":
    """Find and load a font by name."""
    if ImageFont is None:
        raise ImportError("Pillow required: pip install Pillow")

    # Try direct path first
    if os.path.isfile(name):
        return ImageFont.truetype(name, size)

    # Try common font file patterns
    candidates = [
        f"{name}.ttf",
        f"{name}.otf",
        name.replace(" ", "-") + ".ttf",
        name.replace(" ", "") + ".ttf",
    ]

    for font_dir in _FONT_DIRS:
        font_dir = os.path.normpath(font_dir)
        if not os.path.isdir(font_dir):
            continue
        for candidate in candidates:
            path = os.path.join(font_dir, candidate)
            if os.path.isfile(path):
                return ImageFont.truetype(path, size)

    # Fallback to system default
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _hex_to_rgba(hex_color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """Convert hex color + opacity to RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 8:
        r, g, b, a = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16), int(hex_color[6:8], 16)
        return (r, g, b, int(a * opacity))
    elif len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return (r, g, b, int(255 * opacity))
    return (255, 255, 255, int(255 * opacity))


def _draw_rounded_rect(
    draw: "ImageDraw.ImageDraw",
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple[int, int, int, int],
) -> None:
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = xy
    # PIL >= 8.2 has rounded_rectangle
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(xy, radius=radius, fill=fill)
    else:
        # Fallback: rectangles + circles
        draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill)
        draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill)
        draw.pieslice([x1, y1, x1 + 2 * radius, y1 + 2 * radius], 180, 270, fill=fill)
        draw.pieslice([x2 - 2 * radius, y1, x2, y1 + 2 * radius], 270, 360, fill=fill)
        draw.pieslice([x1, y2 - 2 * radius, x1 + 2 * radius, y2], 90, 180, fill=fill)
        draw.pieslice([x2 - 2 * radius, y2 - 2 * radius, x2, y2], 0, 90, fill=fill)


def _scale_template(template: SubtitleTemplate, video_width: int) -> SubtitleTemplate:
    """Scale template dimensions relative to 1080px reference width."""
    import copy
    t = copy.deepcopy(template)
    scale = video_width / 1080.0

    t.font_size = max(16, int(t.font_size * scale))
    t.bg_corner_radius = max(5, int(t.bg_corner_radius * scale))
    t.bg_padding_x = max(10, int(t.bg_padding_x * scale))
    t.bg_padding_y = max(5, int(t.bg_padding_y * scale))
    t.outline_width = max(1, int(t.outline_width * scale))
    t.shadow_offset_x = int(t.shadow_offset_x * scale)
    t.shadow_offset_y = int(t.shadow_offset_y * scale)
    t.line_spacing = max(2, int(t.line_spacing * scale))

    return t


# ---------------------------------------------------------------------------
# Render single subtitle card as transparent PNG
# ---------------------------------------------------------------------------

def _detect_keywords(text: str) -> list[str]:
    """Auto-detect keywords to highlight (capitalized, quoted, or key phrases)."""
    keywords = []
    # Find quoted words
    for m in re.finditer(r'"([^"]+)"', text):
        keywords.append(m.group(1))
    # Find ALL-CAPS words (3+ chars)
    for m in re.finditer(r'\b([A-ZÀ-Ỹ]{3,})\b', text):
        keywords.append(m.group(1))
    # Common highlight patterns: numbers with %, brand names
    for m in re.finditer(r'\b(\d+\s*%)\b', text):
        keywords.append(m.group(1))
    # BookAI brand
    if "BookAI" in text:
        keywords.append("BookAI")
    return keywords


def render_subtitle_card(
    text: str,
    template: SubtitleTemplate,
    video_width: int,
    video_height: int,
    keywords: Optional[list[str]] = None,
) -> Image.Image:
    """Render a single subtitle as a transparent PNG overlay (full video size)."""
    if Image is None:
        raise ImportError("Pillow required")

    t = _scale_template(template, video_width)

    # Create full-size transparent canvas
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Load font
    font = _find_font(t.font_name, t.font_size)

    # Transform text
    display_text = text.upper() if t.uppercase else text

    # Wrap text to max width
    max_text_width = video_width - 2 * t.bg_padding_x - 100  # Leave margins
    lines = _wrap_text(display_text, font, max_text_width, draw)

    # Measure text block
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        line_widths.append(w)

    total_text_height = sum(line_heights) + t.line_spacing * (len(lines) - 1)
    max_line_width = max(line_widths) if line_widths else 100

    # Calculate position
    y_bottom = int(video_height * (1 - t.position_bottom_pct / 100))

    if t.bg_enabled:
        # Box dimensions
        box_w = max_line_width + 2 * t.bg_padding_x
        box_h = total_text_height + 2 * t.bg_padding_y
        box_x = (video_width - box_w) // 2
        box_y = y_bottom - box_h

        # Shadow behind box
        if t.shadow_enabled:
            shadow_color = _hex_to_rgba(t.shadow_color)
            _draw_rounded_rect(
                draw,
                (box_x + t.shadow_offset_x, box_y + t.shadow_offset_y,
                 box_x + box_w + t.shadow_offset_x, box_y + box_h + t.shadow_offset_y),
                t.bg_corner_radius,
                shadow_color,
            )

        # Background box
        bg_color = _hex_to_rgba(t.bg_color, t.bg_opacity)
        _draw_rounded_rect(
            draw,
            (box_x, box_y, box_x + box_w, box_y + box_h),
            t.bg_corner_radius,
            bg_color,
        )

        # Text start position (centered in box)
        text_y = box_y + t.bg_padding_y
    else:
        text_y = y_bottom - total_text_height

    # Auto-detect keywords if highlight enabled and none provided
    if t.highlight_enabled and not keywords:
        keywords = _detect_keywords(text)

    # Draw each line
    for i, line in enumerate(lines):
        line_w = line_widths[i]
        text_x = (video_width - line_w) // 2  # Center

        if t.highlight_enabled and keywords:
            _draw_line_with_highlights(
                draw, line, text_x, text_y, font, t, keywords
            )
        else:
            _draw_text_styled(draw, line, text_x, text_y, font, t)

        text_y += line_heights[i] + t.line_spacing

    return canvas


def _wrap_text(
    text: str, font: "ImageFont.FreeTypeFont", max_width: int, draw: "ImageDraw.ImageDraw"
) -> list[str]:
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        test_line = f"{current_line} {word}".strip() if current_line else word
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines or [""]


def _draw_text_styled(
    draw: "ImageDraw.ImageDraw",
    text: str,
    x: int,
    y: int,
    font: "ImageFont.FreeTypeFont",
    t: SubtitleTemplate,
) -> None:
    """Draw text with outline and/or shadow."""
    color = _hex_to_rgba(t.font_color)

    # Shadow
    if t.shadow_enabled and not t.bg_enabled:
        shadow_c = _hex_to_rgba(t.shadow_color)
        draw.text((x + t.shadow_offset_x, y + t.shadow_offset_y), text, font=font, fill=shadow_c)

    # Outline (draw text in outline color offset in 8 directions)
    if t.outline_enabled:
        outline_c = _hex_to_rgba(t.outline_color)
        ow = t.outline_width
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx * dx + dy * dy <= ow * ow:  # Circular outline
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_c)

    # Main text
    draw.text((x, y), text, font=font, fill=color)


def _draw_line_with_highlights(
    draw: "ImageDraw.ImageDraw",
    line: str,
    x: int,
    y: int,
    font: "ImageFont.FreeTypeFont",
    t: SubtitleTemplate,
    keywords: list[str],
) -> None:
    """Draw a line with keyword highlighting."""
    # Split line into segments: normal and highlighted
    segments = _split_by_keywords(line, keywords)
    cursor_x = x

    for segment_text, is_highlight in segments:
        if is_highlight:
            # Draw highlighted word
            color = _hex_to_rgba(t.highlight_color)
            if t.highlight_bg_color:
                # Background for keyword
                bbox = draw.textbbox((cursor_x, y), segment_text, font=font)
                pad = 4
                _draw_rounded_rect(
                    draw,
                    (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
                    8,
                    _hex_to_rgba(t.highlight_bg_color, 0.8),
                )
        else:
            color = _hex_to_rgba(t.font_color)

        # Outline for all text
        if t.outline_enabled:
            outline_c = _hex_to_rgba(t.outline_color)
            ow = t.outline_width
            for dx in range(-ow, ow + 1):
                for dy in range(-ow, ow + 1):
                    if dx * dx + dy * dy <= ow * ow:
                        draw.text((cursor_x + dx, y + dy), segment_text, font=font, fill=outline_c)

        draw.text((cursor_x, y), segment_text, font=font, fill=color)

        # Advance cursor
        bbox = draw.textbbox((0, 0), segment_text, font=font)
        cursor_x += bbox[2] - bbox[0]


def _split_by_keywords(text: str, keywords: list[str]) -> list[tuple[str, bool]]:
    """Split text into (segment, is_keyword) tuples."""
    if not keywords:
        return [(text, False)]

    # Build regex pattern for all keywords
    escaped = [re.escape(kw) for kw in keywords]
    pattern = re.compile(r"(" + "|".join(escaped) + r")", re.IGNORECASE)

    segments = []
    last_end = 0
    for m in pattern.finditer(text):
        if m.start() > last_end:
            segments.append((text[last_end:m.start()], False))
        segments.append((m.group(), True))
        last_end = m.end()

    if last_end < len(text):
        segments.append((text[last_end:], False))

    return segments or [(text, False)]


# ---------------------------------------------------------------------------
# Render karaoke subtitles (word-by-word highlight)
# ---------------------------------------------------------------------------

def render_karaoke_frames(
    words: list[dict],  # [{word, start, end}, ...]
    template: SubtitleTemplate,
    video_width: int,
    video_height: int,
    group_text: str,
    group_start: float,
    group_end: float,
    fps: int = 30,
) -> list[tuple[float, float, Image.Image]]:
    """Render karaoke-style frames where current word is highlighted.
    
    Returns: list of (start_sec, end_sec, overlay_image)
    """
    if Image is None:
        raise ImportError("Pillow required")

    t = _scale_template(template, video_width)
    frames = []

    for i, word_info in enumerate(words):
        # Render full group text with current word highlighted
        canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        font = _find_font(t.font_name, t.font_size)

        # Position
        y_bottom = int(video_height * (1 - t.position_bottom_pct / 100))

        # Build display with word-level highlighting
        all_words = group_text.split()
        total_width = 0
        word_widths = []
        for w in all_words:
            bbox = draw.textbbox((0, 0), w + " ", font=font)
            ww = bbox[2] - bbox[0]
            word_widths.append(ww)
            total_width += ww

        start_x = (video_width - total_width) // 2
        cursor_x = start_x

        bbox = draw.textbbox((0, 0), "Ag", font=font)
        text_h = bbox[3] - bbox[1]
        text_y = y_bottom - text_h

        for j, w in enumerate(all_words):
            is_current = (j == i)
            color = _hex_to_rgba(t.highlight_color) if is_current else _hex_to_rgba(t.font_color)

            # Outline
            if t.outline_enabled:
                oc = _hex_to_rgba(t.outline_color)
                ow = t.outline_width
                for dx in range(-ow, ow + 1):
                    for dy in range(-ow, ow + 1):
                        if dx * dx + dy * dy <= ow * ow:
                            draw.text((cursor_x + dx, text_y + dy), w, font=font, fill=oc)

            draw.text((cursor_x, text_y), w, font=font, fill=color)
            cursor_x += word_widths[j]

        w_start = word_info["start"]
        w_end = word_info["end"]
        if i + 1 < len(words):
            w_end = words[i + 1]["start"]  # Extend to next word start

        frames.append((w_start, w_end, canvas))

    return frames


# ---------------------------------------------------------------------------
# Main: Burn styled subtitles onto video
# ---------------------------------------------------------------------------

def burn_styled_subtitles(
    video_path: str,
    srt_path: str,
    output_path: str,
    template: str | SubtitleTemplate = "capcut_white_box",
    video_width: int = 1080,
    video_height: int = 1920,
    keywords: Optional[list[str]] = None,
    word_timestamps: Optional[list[dict]] = None,
) -> bool:
    """Burn CapCut-style subtitles onto video using PIL overlays.

    Args:
        video_path: Input video path
        srt_path: SRT subtitle file path
        output_path: Output video path
        template: Template name (str) or SubtitleTemplate object
        video_width: Video width in pixels
        video_height: Video height in pixels
        keywords: Optional list of words to highlight
        word_timestamps: Optional word-level timestamps for karaoke mode

    Returns:
        True if successful
    """
    if not srt_path or not os.path.exists(srt_path):
        shutil.copy(video_path, output_path)
        return True

    # Resolve template
    if isinstance(template, str):
        tmpl = TEMPLATES.get(template)
        if not tmpl:
            # Fallback to classic
            tmpl = TEMPLATES["classic"]
    else:
        tmpl = template

    entries = parse_srt(srt_path)
    if not entries:
        shutil.copy(video_path, output_path)
        return True

    # Create temp directory for overlay PNGs
    import tempfile
    work_dir = tempfile.mkdtemp(prefix="bookai_sub_")

    try:
        # Render each subtitle as a PNG overlay
        overlay_paths = []
        for entry in entries:
            img = render_subtitle_card(
                text=entry.text,
                template=tmpl,
                video_width=video_width,
                video_height=video_height,
                keywords=keywords,
            )
            png_path = os.path.join(work_dir, f"sub_{entry.index:04d}.png")
            img.save(png_path, "PNG")
            overlay_paths.append((entry.start_seconds, entry.end_seconds, png_path))

        # Build FFmpeg filter complex to overlay all subtitle PNGs
        success = _ffmpeg_overlay_subtitles(
            video_path, overlay_paths, output_path
        )
        return success

    finally:
        # Cleanup
        shutil.rmtree(work_dir, ignore_errors=True)


def _ffmpeg_overlay_subtitles(
    video_path: str,
    overlays: list[tuple[float, float, str]],  # [(start, end, png_path), ...]
    output_path: str,
) -> bool:
    """Use FFmpeg to overlay subtitle PNGs on video with timing."""
    if not overlays:
        shutil.copy(video_path, output_path)
        return True

    # Build input args and filter chain
    inputs = ["-i", video_path]
    for _, _, png_path in overlays:
        inputs.extend(["-i", png_path])

    # Build filter complex
    n = len(overlays)
    filter_parts = []
    prev = "0:v"

    for i, (start, end, _) in enumerate(overlays):
        inp_idx = i + 1
        out_label = f"v{i}"
        enable = f"between(t,{start:.3f},{end:.3f})"
        filter_parts.append(
            f"[{prev}][{inp_idx}:v]overlay=0:0:enable='{enable}'[{out_label}]"
        )
        prev = out_label

    # The last output shouldn't have a label — it goes to output
    if filter_parts:
        # Remove the last label
        last = filter_parts[-1]
        last = last.rsplit("[", 1)[0]  # Remove [vN] output label
        filter_parts[-1] = last

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        output_path,
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode == 0 and os.path.exists(output_path):
            return True

        # If too many overlays cause FFmpeg issues, try chunked approach
        if n > 15:
            return _ffmpeg_overlay_chunked(video_path, overlays, output_path)

        # Fallback: copy without subtitles
        shutil.copy(video_path, output_path)
        return False
    except Exception:
        shutil.copy(video_path, output_path)
        return False


def _ffmpeg_overlay_chunked(
    video_path: str,
    overlays: list[tuple[float, float, str]],
    output_path: str,
    chunk_size: int = 10,
) -> bool:
    """Apply overlays in chunks to avoid FFmpeg complexity limits."""
    import tempfile

    current_input = video_path
    temp_files = []

    for i in range(0, len(overlays), chunk_size):
        chunk = overlays[i:i + chunk_size]
        is_last = (i + chunk_size >= len(overlays))

        if is_last:
            chunk_output = output_path
        else:
            fd, chunk_output = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            temp_files.append(chunk_output)

        success = _ffmpeg_overlay_subtitles(current_input, chunk, chunk_output)
        if not success:
            break
        current_input = chunk_output

    # Cleanup temp files
    for tf in temp_files:
        try:
            os.remove(tf)
        except Exception:
            pass

    return os.path.exists(output_path)


# ---------------------------------------------------------------------------
# Convenience: get template list for UI
# ---------------------------------------------------------------------------

def list_templates() -> list[dict]:
    """Return list of available templates for UI display."""
    return [
        {
            "id": name,
            "name": t.name,
            "description": t.description,
            "has_highlight": t.highlight_enabled,
            "has_background": t.bg_enabled,
        }
        for name, t in TEMPLATES.items()
    ]
