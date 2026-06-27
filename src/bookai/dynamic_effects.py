"""CapCut Phase 2 — Dynamic text effects and advanced subtitle presets.

Adds higher-level effects that go beyond static subtitle templates:
  - Glow / highlight presets (animated glow pulse, neon flicker, gradient sweep)
  - Text overlay manager (lower-third, full-screen quotes, bullet lists)
  - Transition text effects (between scenes)
  - Dynamic color animations (rainbow, gradient shift)

Usage::

    from bookai.dynamic_effects import (
        DynamicEffectEngine,
        GlowPreset,
        TextOverlayConfig,
        apply_dynamic_subtitle,
    )

    engine = DynamicEffectEngine(width=1080, height=1920)
    frames = engine.render_glow_text("Amazing book!", GlowPreset.NEON_PULSE, duration=2.0)
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = ImageFilter = None  # type: ignore


# ---------------------------------------------------------------------------
# Glow Presets
# ---------------------------------------------------------------------------


class GlowPreset(str, Enum):
    """Pre-configured glow animation styles."""
    NEON_PULSE = "neon_pulse"        # Pulsing neon glow (green/blue/pink)
    NEON_FLICKER = "neon_flicker"    # Random flickering neon
    SOFT_GLOW = "soft_glow"         # Soft white glow in/out
    FIRE_GLOW = "fire_glow"         # Orange-red ember glow
    RAINBOW_CYCLE = "rainbow_cycle"  # HSV rainbow color rotation
    GRADIENT_SWEEP = "gradient_sweep" # Left-to-right gradient reveal
    SHADOW_POP = "shadow_pop"        # Growing shadow depth effect
    FROST_SHINE = "frost_shine"      # Cool blue → white shimmer


# Preset color configs
GLOW_COLORS: dict[str, dict] = {
    "neon_pulse": {"primary": "#00FF88", "glow": "#00FF8880", "bg": "#00000000"},
    "neon_flicker": {"primary": "#FF00FF", "glow": "#FF00FF60", "bg": "#00000000"},
    "soft_glow": {"primary": "#FFFFFF", "glow": "#FFFFFF40", "bg": "#00000000"},
    "fire_glow": {"primary": "#FF6600", "glow": "#FF330060", "bg": "#00000000"},
    "rainbow_cycle": {"primary": "#FF0000", "glow": "#FF000040", "bg": "#00000000"},
    "gradient_sweep": {"primary": "#00BFFF", "glow": "#00BFFF40", "bg": "#00000000"},
    "shadow_pop": {"primary": "#FFFFFF", "glow": "#00000080", "bg": "#00000000"},
    "frost_shine": {"primary": "#E0F7FF", "glow": "#00CCFF40", "bg": "#00000000"},
}


# ---------------------------------------------------------------------------
# Text Overlay Config
# ---------------------------------------------------------------------------


class OverlayType(str, Enum):
    """Types of text overlay for video."""
    LOWER_THIRD = "lower_third"         # Name/title bar at bottom
    FULL_SCREEN_QUOTE = "full_screen_quote"  # Big centered quote
    BULLET_LIST = "bullet_list"         # Animated bullet points
    CHAPTER_MARKER = "chapter_marker"   # "Chapter 1: ..."
    PROS_CONS = "pros_cons"             # Split screen comparison
    HIGHLIGHT_BOX = "highlight_box"     # Key insight in a box
    STATS_COUNTER = "stats_counter"     # Animated number counter


@dataclass
class TextOverlayConfig:
    """Configuration for a text overlay effect."""
    overlay_type: OverlayType = OverlayType.LOWER_THIRD
    text: str = ""
    subtitle: str = ""  # Secondary text (e.g., subtitle for lower_third)
    items: list[str] = field(default_factory=list)  # For bullet_list, pros_cons
    duration: float = 3.0  # seconds
    font_size: int = 40
    font_color: str = "#FFFFFF"
    accent_color: str = "#2B7DE9"
    bg_color: str = "#000000CC"
    entrance: str = "slide_up"  # fade_in, slide_up, slide_left, pop
    exit: str = "fade_out"
    position: str = "bottom"  # top, center, bottom


# ---------------------------------------------------------------------------
# Dynamic Effect Engine
# ---------------------------------------------------------------------------


@dataclass
class DynamicEffectEngine:
    """Renders dynamic text effects as video clips.

    All effects are rendered frame-by-frame using PIL → FFmpeg.
    """

    width: int = 1080
    height: int = 1920
    fps: int = 30
    font_dir: str = ""

    def _get_font(self, size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
        """Get a font, trying custom fonts first, then system defaults."""
        if not ImageFont:
            raise ImportError("Pillow is required: pip install Pillow")

        # Try custom fonts
        font_names = (
            ["BeVietnamPro-Bold.ttf", "BeVietnamPro-SemiBold.ttf"]
            if bold
            else ["BeVietnamPro-Medium.ttf", "BeVietnamPro-Regular.ttf"]
        )
        search_dirs = [self.font_dir, "assets/fonts", os.path.join(os.path.dirname(__file__), "..", "..", "assets", "fonts")]

        for d in search_dirs:
            if not d:
                continue
            for fname in font_names:
                path = os.path.join(d, fname)
                if os.path.exists(path):
                    return ImageFont.truetype(path, size)

        # Fallback system fonts
        for fallback in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
            if os.path.exists(fallback):
                return ImageFont.truetype(fallback, size)

        return ImageFont.load_default()

    # ----- Glow text rendering -----

    def render_glow_text(
        self,
        text: str,
        preset: GlowPreset | str = GlowPreset.NEON_PULSE,
        duration: float = 2.0,
        font_size: int = 48,
        output_path: str | None = None,
    ) -> str:
        """Render animated glow text as MP4 video clip.

        Returns path to the output MP4.
        """
        if isinstance(preset, str):
            preset = GlowPreset(preset)

        colors = GLOW_COLORS.get(preset.value, GLOW_COLORS["neon_pulse"])
        total_frames = int(duration * self.fps)

        tmp_dir = tempfile.mkdtemp(prefix="bookai_glow_")
        if output_path is None:
            output_path = os.path.join(tmp_dir, "glow_text.mp4")

        font = self._get_font(font_size)

        for i in range(total_frames):
            t = i / total_frames  # 0.0 → 1.0
            frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(frame)

            # Calculate glow intensity based on preset
            if preset == GlowPreset.NEON_PULSE:
                glow_intensity = 0.5 + 0.5 * math.sin(t * math.pi * 4)
            elif preset == GlowPreset.NEON_FLICKER:
                import random
                glow_intensity = 0.3 + 0.7 * (1 if random.random() > 0.15 else 0.1)
            elif preset == GlowPreset.SOFT_GLOW:
                glow_intensity = 0.3 + 0.7 * (math.sin(t * math.pi * 2) ** 2)
            elif preset == GlowPreset.FIRE_GLOW:
                glow_intensity = 0.4 + 0.6 * abs(math.sin(t * math.pi * 6))
            elif preset == GlowPreset.RAINBOW_CYCLE:
                glow_intensity = 1.0
            elif preset == GlowPreset.GRADIENT_SWEEP:
                glow_intensity = min(1.0, t * 2) if t < 0.5 else 1.0
            elif preset == GlowPreset.SHADOW_POP:
                glow_intensity = min(1.0, t * 3)
            else:  # FROST_SHINE
                glow_intensity = 0.5 + 0.5 * math.sin(t * math.pi * 3)

            # Parse primary color and apply glow
            primary = self._hex_to_rgba(colors["primary"])
            glow_color = self._hex_to_rgba(colors["glow"])

            # For rainbow, rotate hue
            if preset == GlowPreset.RAINBOW_CYCLE:
                hue = (t * 360) % 360
                primary = self._hsv_to_rgba(hue, 1.0, 1.0)
                glow_color = (*primary[:3], 80)

            # Text bounding box
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (self.width - tw) // 2
            y = (self.height - th) // 2

            # Draw glow (blurred text behind)
            glow_layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)
            glow_alpha = int(glow_color[3] * glow_intensity)
            glow_rgba = (*glow_color[:3], glow_alpha)

            # Draw glow text multiple times with offset for blur effect
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    glow_draw.text((x + dx, y + dy), text, fill=glow_rgba, font=font)
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))
            frame = Image.alpha_composite(frame, glow_layer)

            # Draw main text
            draw2 = ImageDraw.Draw(frame)
            alpha = int(255 * min(1.0, glow_intensity + 0.3))
            text_color = (*primary[:3], alpha)
            draw2.text((x, y), text, fill=text_color, font=font)

            # Save frame
            frame_path = os.path.join(tmp_dir, f"frame_{i:05d}.png")
            frame.save(frame_path)

        # FFmpeg encode
        self._frames_to_mp4(tmp_dir, output_path, duration)

        # Cleanup frames
        for f in Path(tmp_dir).glob("frame_*.png"):
            f.unlink()

        return output_path

    # ----- Text Overlay rendering -----

    def render_text_overlay(
        self,
        config: TextOverlayConfig,
        output_path: str | None = None,
    ) -> str:
        """Render a text overlay effect as MP4 clip.

        Supports: lower_third, full_screen_quote, bullet_list,
        chapter_marker, highlight_box, stats_counter.
        """
        total_frames = int(config.duration * self.fps)
        tmp_dir = tempfile.mkdtemp(prefix="bookai_overlay_")
        if output_path is None:
            output_path = os.path.join(tmp_dir, "overlay.mp4")

        renderers = {
            OverlayType.LOWER_THIRD: self._render_lower_third,
            OverlayType.FULL_SCREEN_QUOTE: self._render_full_screen_quote,
            OverlayType.BULLET_LIST: self._render_bullet_list,
            OverlayType.CHAPTER_MARKER: self._render_chapter_marker,
            OverlayType.HIGHLIGHT_BOX: self._render_highlight_box,
            OverlayType.STATS_COUNTER: self._render_stats_counter,
        }

        renderer = renderers.get(config.overlay_type, self._render_lower_third)

        for i in range(total_frames):
            t = i / max(total_frames - 1, 1)
            frame = renderer(config, t, i, total_frames)
            frame_path = os.path.join(tmp_dir, f"frame_{i:05d}.png")
            frame.save(frame_path)

        self._frames_to_mp4(tmp_dir, output_path, config.duration)

        for f in Path(tmp_dir).glob("frame_*.png"):
            f.unlink()

        return output_path

    # ----- Lower Third -----

    def _render_lower_third(
        self, cfg: TextOverlayConfig, t: float, frame_idx: int, total: int
    ) -> Image.Image:
        """Lower-third name bar with entrance/exit animation."""
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Entrance/exit timing
        enter_t = min(1.0, t * 5)  # 0-20% entrance
        exit_t = max(0.0, (t - 0.8) * 5)  # 80-100% exit
        alpha_mult = min(enter_t, 1.0 - exit_t)

        # Bar dimensions
        bar_h = 100
        bar_y = int(self.height * 0.78)

        # Slide in from left
        bar_x = int(-self.width + self.width * self._ease_out(enter_t))
        if exit_t > 0:
            bar_x = int(bar_x - self.width * self._ease_in(exit_t))

        # Background bar
        bg = self._hex_to_rgba(cfg.bg_color)
        bg_alpha = int(bg[3] * alpha_mult)
        draw.rectangle(
            [bar_x, bar_y, bar_x + self.width + 20, bar_y + bar_h],
            fill=(*bg[:3], bg_alpha),
        )

        # Accent strip
        accent = self._hex_to_rgba(cfg.accent_color)
        draw.rectangle(
            [bar_x, bar_y, bar_x + 6, bar_y + bar_h],
            fill=(*accent[:3], int(255 * alpha_mult)),
        )

        # Text
        font_main = self._get_font(cfg.font_size, bold=True)
        font_sub = self._get_font(int(cfg.font_size * 0.65), bold=False)
        text_alpha = int(255 * alpha_mult)
        color = (*self._hex_to_rgba(cfg.font_color)[:3], text_alpha)

        draw.text((bar_x + 30, bar_y + 12), cfg.text, fill=color, font=font_main)
        if cfg.subtitle:
            sub_color = (*color[:3], int(text_alpha * 0.7))
            draw.text((bar_x + 30, bar_y + 58), cfg.subtitle, fill=sub_color, font=font_sub)

        return frame

    # ----- Full Screen Quote -----

    def _render_full_screen_quote(
        self, cfg: TextOverlayConfig, t: float, frame_idx: int, total: int
    ) -> Image.Image:
        """Large centered quote with fade + scale animation."""
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        # Fade timing
        fade_in = min(1.0, t * 3)
        fade_out = max(0.0, min(1.0, (t - 0.7) * 3.33))
        alpha = fade_in * (1.0 - fade_out)

        # Semi-transparent background
        bg = self._hex_to_rgba(cfg.bg_color)
        bg_frame = Image.new("RGBA", (self.width, self.height), (*bg[:3], int(bg[3] * alpha * 0.5)))
        frame = Image.alpha_composite(frame, bg_frame)

        draw = ImageDraw.Draw(frame)

        # Quote marks
        quote_font = self._get_font(int(cfg.font_size * 2.5), bold=True)
        accent = self._hex_to_rgba(cfg.accent_color)
        quote_alpha = int(accent[3] * alpha * 0.3 if len(accent) > 3 else 255 * alpha * 0.3)
        draw.text(
            (self.width // 2 - 60, self.height // 2 - 150),
            "❝", fill=(*accent[:3], quote_alpha), font=quote_font,
        )

        # Main text (word-wrapped)
        font = self._get_font(cfg.font_size, bold=True)
        lines = self._wrap_text(cfg.text, font, self.width - 120)
        text_alpha = int(255 * alpha)
        color = (*self._hex_to_rgba(cfg.font_color)[:3], text_alpha)

        total_text_h = len(lines) * (cfg.font_size + 10)
        y = (self.height - total_text_h) // 2
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            draw.text(((self.width - lw) // 2, y), line, fill=color, font=font)
            y += cfg.font_size + 10

        return frame

    # ----- Bullet List -----

    def _render_bullet_list(
        self, cfg: TextOverlayConfig, t: float, frame_idx: int, total: int
    ) -> Image.Image:
        """Animated bullet list — items appear one by one."""
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        items = cfg.items or cfg.text.split("\n")
        n_items = len(items)
        if n_items == 0:
            return frame

        font = self._get_font(int(cfg.font_size * 0.85), bold=False)
        title_font = self._get_font(cfg.font_size, bold=True)

        # Background panel
        panel_h = 100 + n_items * 60
        panel_y = (self.height - panel_h) // 2
        bg = self._hex_to_rgba(cfg.bg_color)
        draw.rounded_rectangle(
            [60, panel_y, self.width - 60, panel_y + panel_h],
            radius=20, fill=bg,
        )

        # Title
        if cfg.subtitle:
            accent = self._hex_to_rgba(cfg.accent_color)
            draw.text((100, panel_y + 20), cfg.subtitle, fill=accent, font=title_font)

        # Items with staggered entrance
        y = panel_y + 80
        for idx, item in enumerate(items):
            item_t = (t * n_items) - idx  # Stagger timing
            item_alpha = max(0.0, min(1.0, item_t * 2))

            if item_alpha > 0:
                color = (*self._hex_to_rgba(cfg.font_color)[:3], int(255 * item_alpha))
                bullet_color = (*self._hex_to_rgba(cfg.accent_color)[:3], int(255 * item_alpha))

                # Slide from right
                x_offset = int(30 * (1.0 - self._ease_out(min(1.0, item_t))))

                draw.text((100 + x_offset, y), "●", fill=bullet_color, font=font)
                draw.text((130 + x_offset, y), item, fill=color, font=font)

            y += 60

        return frame

    # ----- Chapter Marker -----

    def _render_chapter_marker(
        self, cfg: TextOverlayConfig, t: float, frame_idx: int, total: int
    ) -> Image.Image:
        """Chapter marker overlay — "Chapter 1: Title" with accent bar."""
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        alpha = min(1.0, t * 4) * max(0.0, 1.0 - max(0.0, (t - 0.75) * 4))

        font = self._get_font(cfg.font_size, bold=True)
        sub_font = self._get_font(int(cfg.font_size * 0.6), bold=False)

        # Center position
        y = self.height // 2 - 40

        # Accent bar (animated width)
        accent = self._hex_to_rgba(cfg.accent_color)
        bar_w = int(self.width * 0.4 * min(1.0, t * 3))
        bar_x = (self.width - bar_w) // 2
        draw.rectangle(
            [bar_x, y - 10, bar_x + bar_w, y - 4],
            fill=(*accent[:3], int(255 * alpha)),
        )

        # Text
        text_alpha = int(255 * alpha)
        color = (*self._hex_to_rgba(cfg.font_color)[:3], text_alpha)

        # Chapter number
        if cfg.subtitle:
            bbox = draw.textbbox((0, 0), cfg.subtitle, font=sub_font)
            lw = bbox[2] - bbox[0]
            sub_color = (*accent[:3], int(200 * alpha))
            draw.text(((self.width - lw) // 2, y + 10), cfg.subtitle, fill=sub_color, font=sub_font)

        # Title
        bbox = draw.textbbox((0, 0), cfg.text, font=font)
        lw = bbox[2] - bbox[0]
        draw.text(((self.width - lw) // 2, y + 50), cfg.text, fill=color, font=font)

        return frame

    # ----- Highlight Box -----

    def _render_highlight_box(
        self, cfg: TextOverlayConfig, t: float, frame_idx: int, total: int
    ) -> Image.Image:
        """Key insight in a rounded highlight box."""
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Pop entrance
        scale = min(1.0, t * 4)
        scale = self._ease_out_bounce(scale)
        alpha = min(1.0, t * 3) * max(0.0, 1.0 - max(0.0, (t - 0.8) * 5))

        font = self._get_font(int(cfg.font_size * 0.9), bold=True)
        lines = self._wrap_text(cfg.text, font, self.width - 200)
        line_h = int(cfg.font_size * 0.9) + 8
        text_h = len(lines) * line_h

        # Box dimensions
        box_w = int((self.width - 120) * scale)
        box_h = int((text_h + 60) * scale)
        box_x = (self.width - box_w) // 2
        box_y = (self.height - box_h) // 2

        # Accent box
        accent = self._hex_to_rgba(cfg.accent_color)
        bg = self._hex_to_rgba(cfg.bg_color)
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=20, fill=(*bg[:3], int(bg[3] * alpha)),
        )
        # Top accent bar
        draw.rectangle(
            [box_x, box_y, box_x + box_w, box_y + 5],
            fill=(*accent[:3], int(255 * alpha)),
        )

        # Icon
        icon_font = self._get_font(int(cfg.font_size * 1.2))
        icon_alpha = int(255 * alpha)
        draw.text(
            (box_x + 20, box_y + 15),
            "💡", fill=(255, 255, 255, icon_alpha), font=icon_font,
        )

        # Text
        color = (*self._hex_to_rgba(cfg.font_color)[:3], int(255 * alpha))
        y = box_y + 30
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            draw.text(((self.width - lw) // 2, y), line, fill=color, font=font)
            y += line_h

        return frame

    # ----- Stats Counter -----

    def _render_stats_counter(
        self, cfg: TextOverlayConfig, t: float, frame_idx: int, total: int
    ) -> Image.Image:
        """Animated counter (e.g., '4.8/5 ⭐' counting up)."""
        frame = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        alpha = min(1.0, t * 3) * max(0.0, 1.0 - max(0.0, (t - 0.8) * 5))

        # Parse target number from text
        import re
        match = re.search(r"([\d.]+)", cfg.text)
        target = float(match.group(1)) if match else 100.0
        suffix = cfg.text[match.end():] if match else ""
        prefix = cfg.text[:match.start()] if match else ""

        # Animated count
        count_t = min(1.0, t * 1.5)  # Count up in first 66% of duration
        current = target * self._ease_out(count_t)

        big_font = self._get_font(int(cfg.font_size * 2.5), bold=True)
        sub_font = self._get_font(int(cfg.font_size * 0.7), bold=False)

        # Display number
        if target == int(target):
            display = f"{prefix}{int(current)}{suffix}"
        else:
            display = f"{prefix}{current:.1f}{suffix}"

        color = (*self._hex_to_rgba(cfg.accent_color)[:3], int(255 * alpha))
        bbox = draw.textbbox((0, 0), display, font=big_font)
        lw = bbox[2] - bbox[0]
        draw.text(
            ((self.width - lw) // 2, self.height // 2 - 60),
            display, fill=color, font=big_font,
        )

        # Subtitle
        if cfg.subtitle:
            sub_color = (*self._hex_to_rgba(cfg.font_color)[:3], int(200 * alpha))
            bbox = draw.textbbox((0, 0), cfg.subtitle, font=sub_font)
            lw = bbox[2] - bbox[0]
            draw.text(
                ((self.width - lw) // 2, self.height // 2 + 50),
                cfg.subtitle, fill=sub_color, font=sub_font,
            )

        return frame

    # ----- Utility helpers -----

    @staticmethod
    def _hex_to_rgba(hex_color: str) -> tuple[int, int, int, int]:
        """Convert hex color to RGBA tuple."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            return (r, g, b, 255)
        elif len(hex_color) == 8:
            r, g, b, a = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16), int(hex_color[6:8], 16)
            return (r, g, b, a)
        return (255, 255, 255, 255)

    @staticmethod
    def _hsv_to_rgba(h: float, s: float, v: float) -> tuple[int, int, int, int]:
        """Convert HSV to RGBA (h=0-360, s=0-1, v=0-1)."""
        import colorsys
        r, g, b = colorsys.hsv_to_rgb(h / 360, s, v)
        return (int(r * 255), int(g * 255), int(b * 255), 255)

    @staticmethod
    def _ease_out(t: float) -> float:
        return 1 - (1 - t) ** 3

    @staticmethod
    def _ease_in(t: float) -> float:
        return t ** 3

    @staticmethod
    def _ease_out_bounce(t: float) -> float:
        if t < 1 / 2.75:
            return 7.5625 * t * t
        elif t < 2 / 2.75:
            t -= 1.5 / 2.75
            return 7.5625 * t * t + 0.75
        elif t < 2.5 / 2.75:
            t -= 2.25 / 2.75
            return 7.5625 * t * t + 0.9375
        else:
            t -= 2.625 / 2.75
            return 7.5625 * t * t + 0.984375

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
        """Word-wrap text to fit within max_width."""
        if not ImageDraw:
            return [text]
        tmp = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(tmp)

        words = text.split()
        lines = []
        current = ""

        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)

        return lines or [text]

    def _frames_to_mp4(self, frames_dir: str, output_path: str, duration: float) -> None:
        """Convert PNG frames to MP4 using FFmpeg."""
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(self.fps),
            "-i", os.path.join(frames_dir, "frame_%05d.png"),
            "-c:v", "libx264",
            "-pix_fmt", "yuva420p",
            "-preset", "fast",
            "-t", str(duration),
            output_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)


# ---------------------------------------------------------------------------
# Convenience function: apply dynamic effect to subtitle entries
# ---------------------------------------------------------------------------


def apply_dynamic_subtitle(
    srt_entries: list[dict],
    glow_preset: str = "",
    highlight_words: list[str] | None = None,
) -> list[dict]:
    """Enhance SRT entries with dynamic effect metadata.

    Adds `effect_meta` to each entry for the renderer to use:
      - glow_preset: which glow animation to apply
      - highlighted_words: words to emphasize
      - intensity: effect intensity 0-1

    This doesn't render frames — it annotates entries for the
    subtitle burn step to use.
    """
    result = []
    for entry in srt_entries:
        enhanced = dict(entry)
        enhanced["effect_meta"] = {
            "glow_preset": glow_preset,
            "highlighted_words": highlight_words or [],
            "intensity": 1.0,
        }

        # Auto-detect words to highlight
        if not highlight_words:
            text = enhanced.get("text", "")
            import re
            # Highlight: numbers, percentages, quoted text, capitalized words
            auto_highlights = []
            for m in re.finditer(r"\d+%?|\d+\.\d+|\"[^\"]+\"|'[^']+'|[A-Z][a-z]{3,}", text):
                auto_highlights.append(m.group())
            enhanced["effect_meta"]["highlighted_words"] = auto_highlights

        result.append(enhanced)

    return result


# ---------------------------------------------------------------------------
# List available effects
# ---------------------------------------------------------------------------


def list_glow_presets() -> list[dict]:
    """Return list of available glow presets."""
    return [
        {"id": p.value, "name": p.name, "colors": GLOW_COLORS.get(p.value, {})}
        for p in GlowPreset
    ]


def list_overlay_types() -> list[dict]:
    """Return list of available overlay types."""
    return [
        {"id": o.value, "name": o.name}
        for o in OverlayType
    ]
