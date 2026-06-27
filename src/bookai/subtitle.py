"""Subtitle generation and rendering for BookAI.

Generates SRT subtitle files from Edge-TTS word-level timestamps,
with Whisper fallback for pre-recorded audio. Also provides functions
to burn subtitles into video using MoviePy.

Inspired by MoneyPrinterTurbo subtitle.py and voice.py subtitle creation.

Usage::

    from bookai.subtitle import generate_srt_from_tts, burn_subtitles

    # Generate SRT during TTS
    srt_path = generate_srt_from_tts(text, audio_path, srt_path, voice="vi-VN-HoaiMyNeural")

    # Burn subtitles into video
    video_with_subs = burn_subtitles(video_clip, srt_path, config=SubtitleConfig())
"""

from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Subtitle Config
# ---------------------------------------------------------------------------


@dataclass
class SubtitleConfig:
    """Configuration for subtitle rendering on video."""

    enabled: bool = True
    position: str = "bottom"          # top, center, bottom, custom
    custom_y_percent: float = 80.0    # used when position="custom" (% from top)
    font_name: str = ""               # empty = auto-detect Vietnamese font
    font_size: int = 48
    text_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: float = 2.0
    background_color: str = ""        # empty = no background, or hex like "#000000AA"
    background_opacity: float = 0.6
    max_chars_per_line: int = 25      # Vietnamese text wraps shorter

    # Font search paths for Vietnamese
    _font_search_paths: list[str] = field(default_factory=lambda: [
        # BeVietnamPro from MPT resource
        "resource/fonts/BeVietnamPro-SemiBold.ttf",
        "resource/fonts/BeVietnamPro-Bold.ttf",
        # System fonts
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ])

    def resolve_font(self) -> str:
        """Return the first available font path, or empty for default."""
        if self.font_name:
            p = Path(self.font_name)
            if p.exists():
                return str(p)
        for candidate in self._font_search_paths:
            if Path(candidate).exists():
                return candidate
        return ""


# ---------------------------------------------------------------------------
# SRT generation from Edge-TTS
# ---------------------------------------------------------------------------


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def _is_sentence_end(word: str) -> bool:
    """Check if a word ends a sentence (Vietnamese/English punctuation)."""
    return bool(re.search(r'[.!?…。！？]\s*$', word))


def _chunk_words_to_subtitle_lines(
    word_timestamps: list[dict],
    max_chars: int = 25,
    max_duration: float = 4.0,
) -> list[dict]:
    """Group word-level timestamps into subtitle lines.

    Each subtitle line respects:
    - max_chars: maximum characters per line
    - max_duration: maximum duration per line in seconds
    - sentence boundaries: always break at sentence-ending punctuation
      so subtitles never start with the tail of a previous sentence
      or end with the head of a new sentence.

    Args:
        word_timestamps: List of {"word": str, "start": float, "end": float}.
        max_chars: Max characters per subtitle line.
        max_duration: Max duration per subtitle line in seconds.

    Returns:
        List of {"text": str, "start": float, "end": float}.
    """
    if not word_timestamps:
        return []

    subtitles = []
    current_words: list[dict] = []
    current_text = ""
    current_start = word_timestamps[0]["start"]

    _need_new_start = False  # flag: next word should start a new group

    def _flush():
        """Emit current accumulated words as a subtitle entry."""
        nonlocal current_words, current_text, current_start, _need_new_start
        if current_words:
            subtitles.append({
                "text": current_text.strip(),
                "start": current_start,
                "end": current_words[-1]["end"],
            })
        current_words = []
        current_text = ""
        _need_new_start = True  # next word sets current_start

    for wt in word_timestamps:
        word = wt["word"]

        # After a flush (sentence end or overflow), reset start to this word
        if _need_new_start:
            current_start = wt["start"]
            _need_new_start = False

        new_text = f"{current_text} {word}".strip() if current_text else word
        duration = wt["end"] - current_start

        # Check if adding this word exceeds limits
        exceeds_chars = len(new_text) > max_chars
        exceeds_duration = duration > max_duration

        if exceeds_chars or exceeds_duration:
            # Flush what we have first, then start new group with this word
            _flush()
            current_words = [wt]
            current_text = word
            current_start = wt["start"]
            _need_new_start = False
        else:
            current_words.append(wt)
            current_text = new_text

        # If this word ends a sentence, force a break here
        # so the next subtitle starts cleanly at the new sentence
        if _is_sentence_end(word) and current_words:
            _flush()

    # Flush remaining words
    _flush()

    # Remove any empty entries
    return [s for s in subtitles if s["text"].strip()]


def generate_srt_from_tts(
    text: str,
    audio_path: str | Path,
    srt_path: str | Path,
    voice: str = "vi-VN-HoaiMyNeural",
    rate: str = "+0%",
    max_chars_per_line: int = 25,
) -> Path | None:
    """Generate TTS audio AND SRT subtitle file simultaneously.

    Uses Edge-TTS communicate with word boundary events to get precise
    word-level timestamps, then groups them into subtitle lines.

    Args:
        text: Text to synthesize.
        audio_path: Output audio file path (.mp3).
        srt_path: Output SRT file path.
        voice: Edge-TTS voice name.
        rate: Speaking rate.
        max_chars_per_line: Max chars per subtitle line.

    Returns:
        Path to SRT file, or None on failure.
    """
    try:
        import edge_tts
    except ImportError:
        return None

    audio_path = Path(audio_path)
    srt_path = Path(srt_path)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.parent.mkdir(parents=True, exist_ok=True)

    # Clean text for TTS
    clean = _clean_for_tts(text)
    if not clean.strip():
        return None

    word_timestamps: list[dict] = []

    async def _synthesize():
        # IMPORTANT: boundary="WordBoundary" is required for word-level
        # timestamps. Edge-TTS 7.x defaults to "SentenceBoundary" which
        # only gives sentence-level timing — unusable for sync.
        communicate = edge_tts.Communicate(
            clean, voice, rate=rate, boundary="WordBoundary"
        )

        with open(str(audio_path), "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    # Extract timing from WordBoundary events
                    offset = chunk.get("offset", 0)  # in 100-nanosecond units
                    duration_ticks = chunk.get("duration", 0)
                    word_text = chunk.get("text", "")

                    start_sec = offset / 1e7
                    end_sec = (offset + duration_ticks) / 1e7

                    if word_text.strip():
                        word_timestamps.append({
                            "word": word_text,
                            "start": start_sec,
                            "end": end_sec,
                        })

    try:
        asyncio.run(_synthesize())
    except Exception:
        return None

    # Create SRT from word timestamps
    if word_timestamps:
        subtitle_lines = _chunk_words_to_subtitle_lines(
            word_timestamps, max_chars=max_chars_per_line
        )
    else:
        # Fallback: generate simple time-based subtitles
        subtitle_lines = _fallback_text_subtitles(clean, max_chars_per_line)

    _write_srt(subtitle_lines, srt_path)
    return srt_path


def generate_srt_from_audio(
    audio_path: str | Path,
    srt_path: str | Path,
    original_text: str = "",
    language: str = "vi",
) -> Path | None:
    """Generate SRT from existing audio using Whisper (fallback method).

    Args:
        audio_path: Path to audio file.
        srt_path: Output SRT path.
        original_text: Original script text for correction.
        language: Audio language code.

    Returns:
        Path to SRT, or None on failure.
    """
    try:
        import whisper
    except ImportError:
        return None

    audio_path = Path(audio_path)
    srt_path = Path(srt_path)

    if not audio_path.exists():
        return None

    try:
        model = whisper.load_model("base")
        result = model.transcribe(str(audio_path), language=language, word_timestamps=True)
    except Exception:
        return None

    word_timestamps = []
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            word_timestamps.append({
                "word": word_info["word"].strip(),
                "start": word_info["start"],
                "end": word_info["end"],
            })

    if not word_timestamps:
        return None

    subtitle_lines = _chunk_words_to_subtitle_lines(word_timestamps)

    # Auto-correct subtitles against original text
    if original_text:
        subtitle_lines = _correct_subtitles(subtitle_lines, original_text)

    _write_srt(subtitle_lines, srt_path)
    return srt_path


# ---------------------------------------------------------------------------
# Subtitle correction (Levenshtein, inspired by MPT)
# ---------------------------------------------------------------------------


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def _similarity(a: str, b: str) -> float:
    """String similarity ratio (0.0 to 1.0)."""
    if not a or not b:
        return 0.0
    dist = _levenshtein_distance(a.lower(), b.lower())
    max_len = max(len(a), len(b))
    return 1.0 - dist / max_len


def _correct_subtitles(
    subtitles: list[dict], original_text: str, threshold: float = 0.6
) -> list[dict]:
    """Correct subtitle text by matching against original script.

    Replaces ASR output with original text when similarity is high enough.
    """
    # Split original into sentences
    sentences = re.split(r"[.!?。！？\n]+", original_text)
    sentences = [s.strip() for s in sentences if s.strip()]

    corrected = []
    for sub in subtitles:
        best_sim = 0.0
        best_match = sub["text"]
        for sent in sentences:
            sim = _similarity(sub["text"], sent)
            if sim > best_sim:
                best_sim = sim
                best_match = sent
        if best_sim >= threshold:
            corrected.append({**sub, "text": best_match})
        else:
            corrected.append(sub)
    return corrected


# ---------------------------------------------------------------------------
# SRT file writer
# ---------------------------------------------------------------------------


def _write_srt(subtitles: list[dict], srt_path: Path) -> None:
    """Write subtitle lines to SRT format."""
    lines = []
    for i, sub in enumerate(subtitles, 1):
        start = _format_srt_time(sub["start"])
        end = _format_srt_time(sub["end"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(sub["text"])
        lines.append("")

    srt_path.write_text("\n".join(lines), encoding="utf-8")


def _fallback_text_subtitles(
    text: str, max_chars: int = 25, wps: float = 2.5
) -> list[dict]:
    """Generate time-estimated subtitles when no word timestamps available.

    Args:
        text: Full text.
        max_chars: Max chars per line.
        wps: Estimated words per second (Vietnamese ~2.5).
    """
    import textwrap

    lines = textwrap.wrap(text, width=max_chars, break_long_words=False)
    subtitles = []
    t = 0.0
    for line in lines:
        word_count = len(line.split())
        duration = max(word_count / wps, 1.0)
        subtitles.append({"text": line, "start": t, "end": t + duration})
        t += duration
    return subtitles


# ---------------------------------------------------------------------------
# Burn subtitles into video (MoviePy)
# ---------------------------------------------------------------------------


def parse_srt(srt_path: str | Path) -> list[dict]:
    """Parse an SRT file into a list of subtitle dicts.

    Returns:
        List of {"index": int, "start": float, "end": float, "text": str}.
    """
    srt_path = Path(srt_path)
    if not srt_path.exists():
        return []

    content = srt_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", content.strip())
    subtitles = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            index = int(lines[0])
        except ValueError:
            continue

        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            lines[1],
        )
        if not time_match:
            continue

        start = _parse_srt_time(time_match.group(1))
        end = _parse_srt_time(time_match.group(2))
        text = "\n".join(lines[2:])

        subtitles.append({"index": index, "start": start, "end": end, "text": text})

    return subtitles


def _parse_srt_time(time_str: str) -> float:
    """Parse SRT time string to seconds."""
    time_str = time_str.replace(",", ".")
    parts = time_str.split(":")
    h, m = int(parts[0]), int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def burn_subtitles(video_clip, srt_path: str | Path, config: SubtitleConfig | None = None):
    """Burn SRT subtitles onto a video clip using MoviePy.

    Args:
        video_clip: MoviePy VideoClip.
        srt_path: Path to SRT file.
        config: SubtitleConfig for styling.

    Returns:
        New VideoClip with subtitles burned in.
    """
    try:
        from moviepy import CompositeVideoClip, TextClip
    except ImportError:
        raise ImportError("moviepy is required. Install: pip install moviepy")

    cfg = config or SubtitleConfig()
    if not cfg.enabled:
        return video_clip

    subtitles = parse_srt(srt_path)
    if not subtitles:
        return video_clip

    w, h = video_clip.size
    font_path = cfg.resolve_font()

    # Calculate Y position
    if cfg.position == "top":
        y_pos = int(h * 0.08)
    elif cfg.position == "center":
        y_pos = int(h * 0.45)
    elif cfg.position == "custom":
        y_pos = int(h * cfg.custom_y_percent / 100)
    else:  # bottom (default)
        y_pos = int(h * 0.80)

    text_clips = []
    for sub in subtitles:
        try:
            txt_kwargs = {
                "text": sub["text"],
                "font_size": cfg.font_size,
                "color": cfg.text_color,
                "stroke_color": cfg.stroke_color,
                "stroke_width": cfg.stroke_width,
                "text_align": "center",
                "size": (int(w * 0.9), None),
                "method": "caption",
            }
            if font_path:
                txt_kwargs["font"] = font_path

            txt_clip = (
                TextClip(**txt_kwargs)
                .with_duration(sub["end"] - sub["start"])
                .with_start(sub["start"])
                .with_position(("center", y_pos))
            )
            text_clips.append(txt_clip)
        except Exception:
            continue

    if not text_clips:
        return video_clip

    return CompositeVideoClip([video_clip] + text_clips, size=(w, h))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_for_tts(text: str) -> str:
    """Clean text for TTS (remove markdown, emoji, URLs)."""
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(https?://\S+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        r"\u2600-\u26FF\u2700-\u27BF]",
        "",
        text,
    )
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
