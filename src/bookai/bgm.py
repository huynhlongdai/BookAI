"""Background Music (BGM) manager for BookAI.

Manages a library of background music tracks for video rendering.
Inspired by MoneyPrinterTurbo's BGM system.

Features:
    - Song directory with MP3 tracks
    - Random, specific, or no-music modes
    - Volume control
    - Auto-loop for long videos

Usage::

    from bookai.bgm import get_bgm_file, list_bgm, BgmConfig

    # Random BGM
    bgm = get_bgm_file(mode="random")

    # Specific BGM
    bgm = get_bgm_file(mode="specific", filename="chill_lofi_01.mp3")

    # Mix BGM into video audio
    mixed = mix_bgm_with_audio(voice_path, bgm_path, output_path, bgm_volume=0.15)
"""

from __future__ import annotations

import glob
import os
import random
import shutil
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Default songs directory (relative to project root)
_DEFAULT_SONGS_DIR = "resource/songs"
_BGM_EXTENSIONS = (".mp3",)


@dataclass
class BgmConfig:
    """BGM configuration."""

    mode: str = "random"            # "random", "specific", "none"
    filename: str = ""              # specific file (when mode="specific")
    volume: float = 0.15            # 0.0 to 1.0 (relative to voice)
    songs_dir: str = _DEFAULT_SONGS_DIR

    @property
    def enabled(self) -> bool:
        return self.mode != "none"


# ---------------------------------------------------------------------------
# BGM file management
# ---------------------------------------------------------------------------


def get_songs_dir(custom_dir: str = "") -> Path:
    """Resolve the songs directory path."""
    if custom_dir:
        p = Path(custom_dir)
    else:
        p = Path(_DEFAULT_SONGS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def list_bgm(songs_dir: str = "") -> list[dict]:
    """List available BGM files.

    Returns:
        List of {"name": str, "size": int, "path": str}.
    """
    directory = get_songs_dir(songs_dir)
    files = []
    for ext in _BGM_EXTENSIONS:
        files.extend(glob.glob(str(directory / f"*{ext}")))
    files.sort()

    return [
        {
            "name": os.path.basename(f),
            "size": os.path.getsize(f),
            "path": f,
        }
        for f in files
    ]


def get_bgm_file(
    mode: str = "random",
    filename: str = "",
    songs_dir: str = "",
) -> str | None:
    """Get a BGM file path based on mode.

    Args:
        mode: "random" (pick random), "specific" (use filename), "none" (no BGM).
        filename: Specific filename when mode="specific".
        songs_dir: Custom songs directory.

    Returns:
        Path to BGM file, or None if mode="none" or no files available.
    """
    if mode == "none":
        return None

    directory = get_songs_dir(songs_dir)

    if mode == "specific" and filename:
        path = directory / filename
        if path.exists():
            return str(path)
        # Fallback to random if specific file not found
        mode = "random"

    # Random mode
    all_files = []
    for ext in _BGM_EXTENSIONS:
        all_files.extend(glob.glob(str(directory / f"*{ext}")))

    if not all_files:
        return None

    return random.choice(all_files)


def add_bgm_file(source_path: str | Path, songs_dir: str = "") -> str:
    """Copy a BGM file into the songs directory.

    Returns:
        Path to the copied file.
    """
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"BGM file not found: {source}")

    directory = get_songs_dir(songs_dir)
    dest = directory / source.name
    shutil.copy2(str(source), str(dest))
    return str(dest)


# ---------------------------------------------------------------------------
# Audio mixing (BGM + voice)
# ---------------------------------------------------------------------------


def mix_bgm_with_audio(
    voice_path: str | Path,
    bgm_path: str | Path,
    output_path: str | Path,
    bgm_volume: float = 0.15,
    voice_volume: float = 1.0,
) -> Path | None:
    """Mix background music with voice audio.

    BGM is looped if shorter than voice, and faded out at the end.

    Args:
        voice_path: Path to voice/narration audio.
        bgm_path: Path to BGM audio.
        output_path: Output mixed audio path.
        bgm_volume: BGM volume (0.0 to 1.0, relative).
        voice_volume: Voice volume (0.0 to 1.0).

    Returns:
        Path to mixed audio, or None on failure.
    """
    try:
        from moviepy import AudioFileClip, CompositeAudioClip, afx
    except ImportError:
        # Fallback to FFmpeg
        return _mix_with_ffmpeg(voice_path, bgm_path, output_path, bgm_volume, voice_volume)

    voice_path = Path(voice_path)
    bgm_path = Path(bgm_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not voice_path.exists() or not bgm_path.exists():
        return None

    try:
        voice_clip = AudioFileClip(str(voice_path))
        bgm_clip = AudioFileClip(str(bgm_path))

        voice_duration = voice_clip.duration

        # Loop BGM if shorter than voice
        if bgm_clip.duration < voice_duration:
            loops_needed = int(voice_duration / bgm_clip.duration) + 1
            bgm_clip = bgm_clip.with_effects([afx.AudioLoop(nloops=loops_needed)])

        # Trim BGM to voice duration
        bgm_clip = bgm_clip.subclipped(0, voice_duration)

        # Adjust volumes
        if voice_volume != 1.0:
            voice_clip = voice_clip.with_effects([afx.MultiplyVolume(voice_volume)])
        bgm_clip = bgm_clip.with_effects([afx.MultiplyVolume(bgm_volume)])

        # Fade out BGM in last 2 seconds
        fade_duration = min(2.0, voice_duration * 0.1)
        bgm_clip = bgm_clip.with_effects([afx.AudioFadeOut(fade_duration)])

        # Composite
        mixed = CompositeAudioClip([voice_clip, bgm_clip])
        mixed.write_audiofile(str(output_path), codec="libmp3lame", bitrate="192k")

        voice_clip.close()
        bgm_clip.close()
        mixed.close()

        return output_path

    except Exception:
        return _mix_with_ffmpeg(voice_path, bgm_path, output_path, bgm_volume, voice_volume)


def _mix_with_ffmpeg(
    voice_path, bgm_path, output_path, bgm_volume: float, voice_volume: float
) -> Path | None:
    """Fallback: Mix audio using FFmpeg subprocess."""
    import subprocess

    voice_path = Path(voice_path)
    bgm_path = Path(bgm_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(voice_path),
        "-stream_loop", "-1", "-i", str(bgm_path),
        "-filter_complex",
        f"[0:a]volume={voice_volume}[voice];"
        f"[1:a]volume={bgm_volume},afade=t=out:st=0:d=2[bgm];"
        f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[out]",
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and output_path.exists():
            return output_path
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Copy default BGM tracks from MoneyPrinterTurbo (bootstrap)
# ---------------------------------------------------------------------------


def bootstrap_bgm_from_mpt(mpt_songs_dir: str, target_dir: str = "") -> int:
    """Copy BGM tracks from MoneyPrinterTurbo's resource/songs/ directory.

    Args:
        mpt_songs_dir: Path to MPT's resource/songs/ directory.
        target_dir: Target songs directory (default: BookAI resource/songs/).

    Returns:
        Number of files copied.
    """
    src = Path(mpt_songs_dir)
    if not src.exists():
        return 0

    dest = get_songs_dir(target_dir)
    count = 0

    for ext in _BGM_EXTENSIONS:
        for f in src.glob(f"*{ext}"):
            target = dest / f.name
            if not target.exists():
                shutil.copy2(str(f), str(target))
                count += 1

    return count
