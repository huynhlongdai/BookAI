"""Video transition effects for BookAI.

Inspired by MoneyPrinterTurbo's video_effects.py, adapted for BookAI's
book-to-content pipeline. Provides composable transition functions that
accept a MoviePy clip and return a transformed clip.

Available transitions:
    - FadeIn / FadeOut
    - SlideIn / SlideOut (from any side)
    - ZoomKenBurns (slow zoom + pan — very effective for TikTok quote videos)
    - CrossDissolve (blend between two clips)

Usage::

    from bookai.video_effects import fadein, fadeout, zoom_ken_burns, apply_transition
    from bookai.models import TransitionMode

    clip = fadein(clip, duration=0.5)
    clip = zoom_ken_burns(clip, zoom_ratio=1.15)
    clip = apply_transition(clip, TransitionMode.FADE_IN, duration=0.5)
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

try:
    from moviepy import (
        ColorClip,
        CompositeVideoClip,
        vfx,
    )

    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False


def _require_moviepy() -> None:
    if not MOVIEPY_AVAILABLE:
        raise ImportError(
            "moviepy is required for video effects. Install with: pip install moviepy"
        )


# ---------------------------------------------------------------------------
# Basic transitions
# ---------------------------------------------------------------------------


def fadein(clip, duration: float = 0.5):
    """Apply fade-in from black."""
    _require_moviepy()
    return clip.with_effects([vfx.FadeIn(duration)])


def fadeout(clip, duration: float = 0.5):
    """Apply fade-out to black."""
    _require_moviepy()
    return clip.with_effects([vfx.FadeOut(duration)])


def slidein(clip, duration: float = 0.5, side: str = "left"):
    """Slide clip in from the given side (left/right/top/bottom).

    Uses explicit position animation on a black background for reliable results.
    """
    _require_moviepy()
    width, height = clip.size

    def position(t: float):
        progress = min(max(t / max(duration, 0.001), 0), 1)
        if side == "left":
            return (-width + width * progress, 0)
        if side == "right":
            return (width - width * progress, 0)
        if side == "top":
            return (0, -height + height * progress)
        if side == "bottom":
            return (0, height - height * progress)
        return (0, 0)

    bg = ColorClip(size=(width, height), color=(0, 0, 0)).with_duration(clip.duration)
    moving = clip.with_position(position)
    return CompositeVideoClip([bg, moving], size=(width, height)).with_duration(clip.duration)


def slideout(clip, duration: float = 0.5, side: str = "right"):
    """Slide clip out toward the given side."""
    _require_moviepy()
    width, height = clip.size
    start = max(clip.duration - duration, 0)

    def position(t: float):
        if t <= start:
            return (0, 0)
        progress = min(max((t - start) / max(duration, 0.001), 0), 1)
        if side == "left":
            return (-width * progress, 0)
        if side == "right":
            return (width * progress, 0)
        if side == "top":
            return (0, -height * progress)
        if side == "bottom":
            return (0, height * progress)
        return (0, 0)

    bg = ColorClip(size=(width, height), color=(0, 0, 0)).with_duration(clip.duration)
    moving = clip.with_position(position)
    return CompositeVideoClip([bg, moving], size=(width, height)).with_duration(clip.duration)


# ---------------------------------------------------------------------------
# Ken Burns zoom (BookAI specialty)
# ---------------------------------------------------------------------------


def zoom_ken_burns(
    clip,
    zoom_ratio: float = 1.15,
    direction: str = "in",
    pan: str = "center",
):
    """Apply slow zoom (Ken Burns effect) — excellent for quote/book videos.

    Args:
        clip: MoviePy VideoClip or ImageClip.
        zoom_ratio: Final zoom factor (1.15 = 15% zoom).
        direction: 'in' (zoom towards) or 'out' (zoom away).
        pan: Pan direction during zoom: 'center', 'left', 'right', 'up', 'down'.

    Returns:
        Transformed clip with zoom effect.
    """
    _require_moviepy()
    w, h = clip.size

    def make_frame(get_frame, t):
        """Create zoomed frame at time t."""
        import numpy as np
        from PIL import Image

        frame = get_frame(t)
        progress = t / max(clip.duration, 0.001)

        if direction == "out":
            scale = zoom_ratio - (zoom_ratio - 1.0) * progress
        else:  # "in"
            scale = 1.0 + (zoom_ratio - 1.0) * progress

        new_w = int(w * scale)
        new_h = int(h * scale)

        # Pan offsets
        cx = (new_w - w) / 2
        cy = (new_h - h) / 2
        if pan == "left":
            cx = (new_w - w) * (1 - progress)
        elif pan == "right":
            cx = (new_w - w) * progress
        elif pan == "up":
            cy = (new_h - h) * (1 - progress)
        elif pan == "down":
            cy = (new_h - h) * progress

        img = Image.fromarray(frame)
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        left = int(cx)
        top = int(cy)
        cropped = img_resized.crop((left, top, left + w, top + h))
        return np.array(cropped)

    return clip.transform(make_frame, apply_to="mask" if hasattr(clip, "mask") else [])


# ---------------------------------------------------------------------------
# Cross-dissolve between two clips
# ---------------------------------------------------------------------------


def cross_dissolve(clip_a, clip_b, duration: float = 0.5):
    """Create a cross-dissolve transition between two clips.

    Returns a composite where clip_a fades out and clip_b fades in over ``duration`` seconds.
    The returned clip duration = clip_a.duration + clip_b.duration - duration.
    """
    _require_moviepy()
    a_out = clip_a.with_effects([vfx.FadeOut(duration)])
    b_in = clip_b.with_effects([vfx.FadeIn(duration)])
    b_start = clip_a.duration - duration
    b_delayed = b_in.with_start(b_start)

    total = clip_a.duration + clip_b.duration - duration
    return CompositeVideoClip(
        [a_out, b_delayed], size=clip_a.size
    ).with_duration(total)


# ---------------------------------------------------------------------------
# Dispatcher (apply by TransitionMode enum)
# ---------------------------------------------------------------------------

# Transition mode names matching the enum values
_TRANSITION_MAP = {
    "fade_in": lambda c, d: fadein(c, d),
    "fade_out": lambda c, d: fadeout(c, d),
    "slide_in": lambda c, d: slidein(c, d, side="left"),
    "slide_out": lambda c, d: slideout(c, d, side="right"),
    "zoom_in": lambda c, d: zoom_ken_burns(c, zoom_ratio=1.15, direction="in"),
    "zoom_out": lambda c, d: zoom_ken_burns(c, zoom_ratio=1.15, direction="out"),
}

_SHUFFLE_POOL = ["fade_in", "slide_in", "zoom_in"]


def apply_transition(clip, mode: str, duration: float = 0.5):
    """Apply a named transition to a clip.

    Args:
        clip: MoviePy clip.
        mode: Transition name: 'fade_in', 'fade_out', 'slide_in', 'slide_out',
              'zoom_in', 'zoom_out', 'shuffle' (random), or 'none'.
        duration: Transition duration in seconds.

    Returns:
        Transformed clip.
    """
    if mode == "none" or mode is None:
        return clip
    if mode == "shuffle":
        mode = random.choice(_SHUFFLE_POOL)
    fn = _TRANSITION_MAP.get(mode)
    if fn is None:
        return clip
    return fn(clip, duration)
