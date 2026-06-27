"""TTS Multi-Provider module for BookAI — Phase 2.

Adds support for multiple TTS providers beyond Edge-TTS:
    - edge_tts      (default, free, Vietnamese support)
    - azure         (Microsoft Azure Speech Services)
    - siliconflow   (SiliconFlow CosyVoice2)
    - elevenlabs    (ElevenLabs)
    - no_voice      (silent audio — for subtitle-only videos)

Each provider implements the same interface: text + config → audio file + SubMaker.

Usage::

    from bookai.tts_providers import tts_synthesize, TTSConfig, list_all_voices

    cfg = TTSConfig(provider="edge_tts", voice="vi-VN-HoaiMyNeural")
    result = tts_synthesize("Xin chào!", "output.mp3", config=cfg)

    voices = list_all_voices()
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------


class TTSProvider(str, Enum):
    """Supported TTS providers."""

    EDGE_TTS = "edge_tts"
    AZURE = "azure"
    SILICONFLOW = "siliconflow"
    ELEVENLABS = "elevenlabs"
    NO_VOICE = "no_voice"


# ---------------------------------------------------------------------------
# Vietnamese voices catalog
# ---------------------------------------------------------------------------

VIETNAMESE_VOICES: dict[str, dict[str, str]] = {
    # Edge TTS (free)
    "vi-VN-HoaiMyNeural": {
        "provider": "edge_tts", "gender": "Female",
        "desc": "Clear, warm — recommended for book radio",
    },
    "vi-VN-NamMinhNeural": {
        "provider": "edge_tts", "gender": "Male",
        "desc": "Authoritative, deeper tone",
    },
    # Azure (paid)
    "vi-VN-HoaiMyNeural-Azure": {
        "provider": "azure", "gender": "Female",
        "desc": "Azure premium — richer prosody, SSML support",
    },
    "vi-VN-NamMinhNeural-Azure": {
        "provider": "azure", "gender": "Male",
        "desc": "Azure premium — richer prosody, SSML support",
    },
}

# Well-known non-Vietnamese voices for multi-language content
MULTILINGUAL_VOICES: dict[str, dict[str, str]] = {
    "en-US-JennyNeural": {"provider": "edge_tts", "gender": "Female", "desc": "English US female"},
    "en-US-GuyNeural": {"provider": "edge_tts", "gender": "Male", "desc": "English US male"},
    "ja-JP-NanamiNeural": {"provider": "edge_tts", "gender": "Female", "desc": "Japanese female"},
    "ko-KR-SunHiNeural": {"provider": "edge_tts", "gender": "Female", "desc": "Korean female"},
    "zh-CN-XiaoxiaoNeural": {"provider": "edge_tts", "gender": "Female", "desc": "Chinese female"},
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class TTSConfig:
    """Configuration for TTS synthesis."""

    provider: str = "edge_tts"
    voice: str = "vi-VN-HoaiMyNeural"
    rate: str = "+0%"           # Speed: "+10%", "-5%", "+0%"
    pitch: str = "+0Hz"         # Pitch: "+5Hz", "-3Hz"
    volume: str = "+0%"         # Volume: "+20%", "-10%"

    # Azure specific
    azure_key: str = ""
    azure_region: str = "southeastasia"

    # SiliconFlow specific
    siliconflow_key: str = ""
    siliconflow_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    siliconflow_voice: str = "alex"  # alex, anna, bella, benjamin, etc.

    # ElevenLabs specific
    elevenlabs_key: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"

    # No-voice options
    silence_duration: float = 0.0  # If > 0 and provider=no_voice, generate this duration
    reading_speed_wps: float = 2.5  # Words per second for duration estimation

    def __post_init__(self):
        # Load from environment if not set
        if not self.azure_key:
            self.azure_key = os.getenv("AZURE_SPEECH_KEY", "")
        if not self.azure_region:
            self.azure_region = os.getenv("AZURE_SPEECH_REGION", "southeastasia")
        if not self.siliconflow_key:
            self.siliconflow_key = os.getenv("SILICONFLOW_API_KEY", "")
        if not self.elevenlabs_key:
            self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")


@dataclass
class TTSResult:
    """Result of a TTS synthesis operation."""

    output_path: Path
    voice: str = ""
    provider: str = "edge_tts"
    duration_seconds: float = 0.0
    text_length: int = 0
    word_timestamps: list[dict] = field(default_factory=list)
    ok: bool = True
    error: str = ""

    @property
    def filename(self) -> str:
        return self.output_path.name


# ---------------------------------------------------------------------------
# Main synthesis function
# ---------------------------------------------------------------------------


def tts_synthesize(
    text: str,
    output_path: str | Path,
    config: TTSConfig | None = None,
) -> TTSResult:
    """Synthesize text to speech using the configured provider.

    Args:
        text: Text to synthesize.
        output_path: Output audio file path (.mp3).
        config: TTSConfig with provider selection and credentials.

    Returns:
        TTSResult with output path, duration, and word timestamps.
    """
    cfg = config or TTSConfig()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text = _clean_text_for_tts(text)
    if not text.strip() and cfg.provider != TTSProvider.NO_VOICE.value:
        return TTSResult(
            output_path=output_path, voice=cfg.voice, provider=cfg.provider,
            ok=False, error="Empty text after cleaning",
        )

    provider = cfg.provider.lower()
    dispatch = {
        "edge_tts": _synth_edge_tts,
        "azure": _synth_azure,
        "siliconflow": _synth_siliconflow,
        "elevenlabs": _synth_elevenlabs,
        "no_voice": _synth_no_voice,
    }

    handler = dispatch.get(provider)
    if not handler:
        return TTSResult(
            output_path=output_path, voice=cfg.voice, provider=provider,
            ok=False, error=f"Unknown TTS provider: {provider}. Available: {list(dispatch.keys())}",
        )

    return handler(text, output_path, cfg)


def tts_synthesize_script(
    script: object,
    output_path: str | Path,
    config: TTSConfig | None = None,
    include_hook: bool = True,
    include_body: bool = True,
    include_cta: bool = True,
) -> TTSResult:
    """Synthesize a RadioScript to audio using multi-provider TTS."""
    parts: list[str] = []
    if include_hook and getattr(script, "hook", ""):
        parts.append(script.hook)
    if include_body and getattr(script, "body", ""):
        parts.append(script.body)
    if include_cta and getattr(script, "cta", ""):
        parts.append(script.cta)

    full_text = "\n\n".join(parts)
    return tts_synthesize(full_text, output_path, config=config)


async def tts_synthesize_batch_async(
    items: list[tuple[str, str | Path]],
    config: TTSConfig | None = None,
    max_concurrent: int = 5,
) -> list[TTSResult]:
    """Synthesize multiple texts concurrently.

    Args:
        items: List of (text, output_path) tuples.
        config: Shared TTS config.
        max_concurrent: Max concurrent tasks.

    Returns:
        List of TTSResult in same order.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _synth_one(text: str, path: str | Path) -> TTSResult:
        async with semaphore:
            return await asyncio.to_thread(tts_synthesize, text, path, config)

    tasks = [_synth_one(text, path) for text, path in items]
    return list(await asyncio.gather(*tasks))


# ---------------------------------------------------------------------------
# Provider: Edge TTS (free, default)
# ---------------------------------------------------------------------------


def _synth_edge_tts(text: str, output_path: Path, cfg: TTSConfig) -> TTSResult:
    """Synthesize using Microsoft Edge TTS (free)."""
    try:
        import edge_tts
    except ImportError:
        return TTSResult(
            output_path=output_path, voice=cfg.voice, provider="edge_tts",
            ok=False, error="edge-tts not installed. Run: pip install edge-tts",
        )

    word_timestamps: list[dict] = []

    async def _run():
        communicate = edge_tts.Communicate(
            text, cfg.voice, rate=cfg.rate, pitch=cfg.pitch
        )

        with open(str(output_path), "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    word_timestamps.append({
                        "word": chunk.get("text", ""),
                        "start": chunk.get("offset", 0) / 1e7,  # 100ns units → seconds
                        "end": (chunk.get("offset", 0) + chunk.get("duration", 0)) / 1e7,
                    })

    try:
        asyncio.run(_run())
    except Exception as exc:
        return TTSResult(
            output_path=output_path, voice=cfg.voice, provider="edge_tts",
            ok=False, error=str(exc),
        )

    duration = _get_audio_duration(output_path)
    return TTSResult(
        output_path=output_path,
        voice=cfg.voice,
        provider="edge_tts",
        duration_seconds=duration,
        text_length=len(text),
        word_timestamps=word_timestamps,
        ok=True,
    )


# ---------------------------------------------------------------------------
# Provider: Azure Speech Services
# ---------------------------------------------------------------------------


def _synth_azure(text: str, output_path: Path, cfg: TTSConfig) -> TTSResult:
    """Synthesize using Azure Cognitive Services Speech."""
    if not cfg.azure_key:
        return TTSResult(
            output_path=output_path, voice=cfg.voice, provider="azure",
            ok=False, error="Azure Speech key not set. Set AZURE_SPEECH_KEY or config.azure_key",
        )

    # Map voice names: strip "-Azure" suffix if present
    voice = cfg.voice.replace("-Azure", "")

    try:
        import requests
    except ImportError:
        return TTSResult(
            output_path=output_path, voice=voice, provider="azure",
            ok=False, error="requests not installed",
        )

    # Get access token
    token_url = f"https://{cfg.azure_region}.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    try:
        token_resp = requests.post(
            token_url,
            headers={"Ocp-Apim-Subscription-Key": cfg.azure_key},
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.text
    except Exception as e:
        return TTSResult(
            output_path=output_path, voice=voice, provider="azure",
            ok=False, error=f"Azure token error: {e}",
        )

    # Build SSML
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="vi-VN">'
        f'<voice name="{voice}">'
        f'<prosody rate="{cfg.rate}" pitch="{cfg.pitch}" volume="{cfg.volume}">'
        f'{_escape_xml(text)}'
        f'</prosody></voice></speak>'
    )

    # Synthesize
    tts_url = f"https://{cfg.azure_region}.tts.speech.microsoft.com/cognitiveservices/v1"
    try:
        resp = requests.post(
            tts_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
            },
            data=ssml.encode("utf-8"),
            timeout=60,
        )
        resp.raise_for_status()

        output_path.write_bytes(resp.content)
    except Exception as e:
        return TTSResult(
            output_path=output_path, voice=voice, provider="azure",
            ok=False, error=f"Azure synthesis error: {e}",
        )

    duration = _get_audio_duration(output_path)
    return TTSResult(
        output_path=output_path, voice=voice, provider="azure",
        duration_seconds=duration, text_length=len(text), ok=True,
    )


# ---------------------------------------------------------------------------
# Provider: SiliconFlow CosyVoice2
# ---------------------------------------------------------------------------


def _synth_siliconflow(text: str, output_path: Path, cfg: TTSConfig) -> TTSResult:
    """Synthesize using SiliconFlow CosyVoice2."""
    if not cfg.siliconflow_key:
        return TTSResult(
            output_path=output_path, provider="siliconflow",
            ok=False, error="SiliconFlow API key not set. Set SILICONFLOW_API_KEY",
        )

    try:
        import requests
    except ImportError:
        return TTSResult(
            output_path=output_path, provider="siliconflow",
            ok=False, error="requests not installed",
        )

    url = "https://api.siliconflow.cn/v1/audio/speech"
    payload = {
        "model": cfg.siliconflow_model,
        "input": text,
        "voice": f"{cfg.siliconflow_model}:{cfg.siliconflow_voice}",
        "response_format": "mp3",
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {cfg.siliconflow_key}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        resp.raise_for_status()

        if resp.headers.get("Content-Type", "").startswith("audio"):
            output_path.write_bytes(resp.content)
        else:
            error_data = resp.json() if resp.content else {}
            return TTSResult(
                output_path=output_path, provider="siliconflow",
                ok=False, error=f"SiliconFlow error: {error_data}",
            )
    except Exception as e:
        return TTSResult(
            output_path=output_path, provider="siliconflow",
            ok=False, error=f"SiliconFlow synthesis error: {e}",
        )

    duration = _get_audio_duration(output_path)
    return TTSResult(
        output_path=output_path,
        voice=f"{cfg.siliconflow_model}:{cfg.siliconflow_voice}",
        provider="siliconflow",
        duration_seconds=duration,
        text_length=len(text),
        ok=True,
    )


# ---------------------------------------------------------------------------
# Provider: ElevenLabs
# ---------------------------------------------------------------------------


def _synth_elevenlabs(text: str, output_path: Path, cfg: TTSConfig) -> TTSResult:
    """Synthesize using ElevenLabs."""
    if not cfg.elevenlabs_key:
        return TTSResult(
            output_path=output_path, provider="elevenlabs",
            ok=False, error="ElevenLabs API key not set. Set ELEVENLABS_API_KEY",
        )

    try:
        import requests
    except ImportError:
        return TTSResult(
            output_path=output_path, provider="elevenlabs",
            ok=False, error="requests not installed",
        )

    voice_id = cfg.voice  # ElevenLabs uses voice_id
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    payload = {
        "text": text,
        "model_id": cfg.elevenlabs_model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "xi-api-key": cfg.elevenlabs_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            timeout=120,
        )
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
    except Exception as e:
        return TTSResult(
            output_path=output_path, provider="elevenlabs",
            ok=False, error=f"ElevenLabs synthesis error: {e}",
        )

    duration = _get_audio_duration(output_path)
    return TTSResult(
        output_path=output_path, voice=voice_id, provider="elevenlabs",
        duration_seconds=duration, text_length=len(text), ok=True,
    )


# ---------------------------------------------------------------------------
# Provider: No Voice (silent audio)
# ---------------------------------------------------------------------------


def _synth_no_voice(text: str, output_path: Path, cfg: TTSConfig) -> TTSResult:
    """Generate silent audio file for subtitle-only videos.

    Duration estimated from text length or uses silence_duration if set.
    """
    if cfg.silence_duration > 0:
        duration = cfg.silence_duration
    else:
        # Estimate duration from text: ~2.5 words/sec for Vietnamese
        words = len(text.split())
        duration = max(3.0, words / cfg.reading_speed_wps)

    ok = _generate_silent_audio(duration, output_path)

    return TTSResult(
        output_path=output_path,
        voice="no_voice",
        provider="no_voice",
        duration_seconds=duration if ok else 0,
        text_length=len(text),
        ok=ok,
        error="" if ok else "Failed to generate silent audio",
    )


def _generate_silent_audio(duration: float, output_path: Path) -> bool:
    """Generate a silent WAV/MP3 file of given duration."""
    sample_rate = 16000
    num_samples = int(sample_rate * duration)

    if str(output_path).endswith(".wav"):
        try:
            with wave.open(str(output_path), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(b"\x00\x00" * num_samples)
            return True
        except Exception:
            return False
    else:
        # Generate WAV first, then convert to MP3 via FFmpeg
        wav_path = output_path.with_suffix(".wav")
        try:
            with wave.open(str(wav_path), "w") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(b"\x00\x00" * num_samples)

            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "128k", str(output_path)],
                capture_output=True, timeout=30,
            )
            wav_path.unlink(missing_ok=True)
            return result.returncode == 0
        except Exception:
            wav_path.unlink(missing_ok=True)
            return False


# ---------------------------------------------------------------------------
# Voice listing
# ---------------------------------------------------------------------------


def list_all_voices(include_multilingual: bool = False) -> dict[str, dict]:
    """List all available Vietnamese (and optionally multilingual) voices."""
    voices = dict(VIETNAMESE_VOICES)
    if include_multilingual:
        voices.update(MULTILINGUAL_VOICES)
    return voices


def list_voices_by_provider(provider: str) -> list[str]:
    """List voice names for a specific provider."""
    all_voices = {**VIETNAMESE_VOICES, **MULTILINGUAL_VOICES}
    return [name for name, info in all_voices.items() if info["provider"] == provider]


def get_siliconflow_voices() -> list[str]:
    """Get SiliconFlow CosyVoice2 voice names."""
    voices = [
        "alex", "anna", "bella", "benjamin", "charles",
        "claire", "david", "diana",
    ]
    return [f"siliconflow:FunAudioLLM/CosyVoice2-0.5B:{v}" for v in voices]


# ---------------------------------------------------------------------------
# Duration estimation
# ---------------------------------------------------------------------------


def estimate_duration(text: str, rate_percent: int = 0, wps: float = 2.5) -> float:
    """Estimate audio duration for text.

    Vietnamese narration: ~2.5 words/sec at normal rate.
    """
    words = len(text.split())
    multiplier = 1 + rate_percent / 100
    return words / (wps * max(multiplier, 0.5))


def convert_rate_to_percent(rate: float) -> str:
    """Convert numeric rate (0.5-2.0) to Edge TTS percent string.

    1.0 = normal → "+0%"
    1.5 = faster → "+50%"
    0.8 = slower → "-20%"
    """
    percent = round((rate - 1.0) * 100)
    return f"+{percent}%" if percent >= 0 else f"{percent}%"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_text_for_tts(text: str) -> str:
    """Remove markdown, emoji, URLs, hashtags."""
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(https?://\S+\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(
        r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF"
        r"\u2600-\u26FF\u2700-\u27BF]",
        "", text,
    )
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _escape_xml(text: str) -> str:
    """Escape XML special characters for SSML."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def _get_audio_duration(path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0
