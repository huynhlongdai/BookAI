"""TTS Multi-Provider module for BookAI — Phase 2.

Adds support for multiple TTS providers beyond Edge-TTS:
    - edge_tts      (default, free, Vietnamese support)
    - azure         (Microsoft Azure Speech Services)
    - siliconflow   (SiliconFlow CosyVoice2)
    - elevenlabs    (ElevenLabs)
    - vieneu        (VieNeu — best Vietnamese voices, voice cloning)
    - no_voice      (silent audio — for subtitle-only videos)

Each provider implements the same interface: text + config → audio file + SubMaker.
Key rotation: every provider supports multiple API keys via ``keys`` list;
a round-robin ``KeyRing`` cycles through them automatically.

Usage::

    from bookai.tts_providers import tts_synthesize, TTSConfig, list_all_voices

    cfg = TTSConfig(provider="edge_tts", voice="vi-VN-HoaiMyNeural")
    result = tts_synthesize("Xin chào!", "output.mp3", config=cfg)

    voices = list_all_voices()
"""

from __future__ import annotations

import asyncio
import itertools
import os
import re
import subprocess
import threading
import time
import wave
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# ---------------------------------------------------------------------------
# Key rotation
# ---------------------------------------------------------------------------

_key_ring_lock = threading.Lock()


class KeyRing:
    """Thread-safe round-robin key rotator.

    Each provider can have multiple API keys; ``next()`` cycles through them.
    If a key fails, call ``report_failure(key)`` to skip it temporarily.
    """

    def __init__(self, keys: list[str]):
        self._keys = [k for k in keys if k]
        self._cycle = itertools.cycle(self._keys) if self._keys else None
        self._failures: dict[str, float] = {}
        self._cooldown = 300  # seconds to skip a failed key

    @property
    def available(self) -> bool:
        return bool(self._keys)

    def next(self) -> str:
        """Return the next available key (round-robin, skipping failed)."""
        if not self._cycle:
            return ""
        now = time.time()
        with _key_ring_lock:
            for _ in range(len(self._keys)):
                key = next(self._cycle)
                fail_time = self._failures.get(key, 0)
                if now - fail_time > self._cooldown:
                    return key
            # All keys are in cooldown — return the oldest failure
            return min(self._failures, key=self._failures.get, default=self._keys[0])

    def report_failure(self, key: str):
        """Mark a key as temporarily failed."""
        with _key_ring_lock:
            self._failures[key] = time.time()

    def __len__(self):
        return len(self._keys)


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------


class TTSProvider(str, Enum):
    """Supported TTS providers."""

    EDGE_TTS = "edge_tts"
    AZURE = "azure"
    SILICONFLOW = "siliconflow"
    ELEVENLABS = "elevenlabs"
    VIENEU = "vieneu"
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
    # VieNeu voices (Vietnamese-native, best quality)
    "vieneu:Ngọc Lan": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Dịu dàng, ấm áp — miền Nam",
    },
    "vieneu:Minh Quân": {
        "provider": "vieneu", "gender": "Male", "region": "south",
        "desc": "Trầm ấm, kể chuyện — miền Nam",
    },
    "vieneu:Hoàng Long": {
        "provider": "vieneu", "gender": "Male", "region": "north",
        "desc": "Trầm ấm, khỏe khoắn — miền Bắc",
    },
    "vieneu:Gia Bảo": {
        "provider": "vieneu", "gender": "Male", "region": "north",
        "desc": "Trầm ấm, mượt mà — miền Bắc",
    },
    "vieneu:Thái Sơn": {
        "provider": "vieneu", "gender": "Male", "region": "south",
        "desc": "Chắc khỏe, rõ ràng — miền Nam",
    },
    "vieneu:Thu Hà": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Ấm áp, nhẹ nhàng — miền Nam",
    },
    "vieneu:Phương Anh": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Nhẹ nhàng, dịu dàng — miền Nam",
    },
    "vieneu:Hải Yến": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Trẻo, tươi sáng — miền Nam",
    },
    "vieneu:Đức Trí": {
        "provider": "vieneu", "gender": "Male", "region": "south",
        "desc": "Trầm ấm, rõ ràng — miền Nam",
    },
    "vieneu:Mỹ Duyên": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Mượt mà, tự nhiên — miền Nam",
    },
    "vieneu:Tuấn Kiệt": {
        "provider": "vieneu", "gender": "Male", "region": "north",
        "desc": "Trầm ấm, rắn rỏi — miền Bắc",
    },
    "vieneu:Kim Chi": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Truyền cảm, tươi sáng — miền Nam",
    },
    "vieneu:Quang Huy": {
        "provider": "vieneu", "gender": "Male", "region": "south",
        "desc": "Trẻ, sôi nổi, năng lượng — miền Nam",
    },
    "vieneu:Bảo Trâm": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Dịu dàng, ấm áp — miền Nam",
    },
    "vieneu:Bảo Nam": {
        "provider": "vieneu", "gender": "Male", "region": "north",
        "desc": "Trầm ấm áp — miền Bắc",
    },
    "vieneu:Diễm My": {
        "provider": "vieneu", "gender": "Female", "region": "north",
        "desc": "Trẻ trung, tươi tắn — miền Bắc",
    },
    "vieneu:Lan Phương": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Mềm mại, dễ mến — miền Nam",
    },
    "vieneu:Trúc Ly": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Trẻ trung, tươi sáng — miền Nam",
    },
    "vieneu:Đăng Khoa": {
        "provider": "vieneu", "gender": "Male", "region": "south",
        "desc": "Rõ ràng, ấm áp, tự nhiên — miền Nam",
    },
    "vieneu:Xuân Vĩnh": {
        "provider": "vieneu", "gender": "Male", "region": "south",
        "desc": "Vui tươi, thân thiện — miền Nam",
    },
    "vieneu:Tuyết Mai": {
        "provider": "vieneu", "gender": "Female", "region": "south",
        "desc": "Thanh thoát, tươi sáng — miền Nam",
    },
    "vieneu:Nhật Minh": {
        "provider": "vieneu", "gender": "Male", "region": "south",
        "desc": "Bình tĩnh, dẫn chuyện — miền Nam",
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

# VieNeu emotion styles
VIENEU_EMOTIONS: list[str] = ["natural", "storytelling"]

# VieNeu emotion tags (inline in text)
VIENEU_EMOTION_TAGS: list[str] = ["[cười]", "[thở dài]", "[hắng giọng]"]


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
    azure_keys: list[str] = field(default_factory=list)
    azure_region: str = "southeastasia"

    # SiliconFlow specific
    siliconflow_key: str = ""
    siliconflow_keys: list[str] = field(default_factory=list)
    siliconflow_model: str = "FunAudioLLM/CosyVoice2-0.5B"
    siliconflow_voice: str = "alex"  # alex, anna, bella, benjamin, etc.

    # ElevenLabs specific
    elevenlabs_key: str = ""
    elevenlabs_keys: list[str] = field(default_factory=list)
    elevenlabs_model: str = "eleven_multilingual_v2"
    elevenlabs_stability: float = 0.5       # 0.0-1.0: lower=more expressive
    elevenlabs_similarity: float = 0.75     # 0.0-1.0: higher=closer to original
    elevenlabs_style: float = 0.0           # 0.0-1.0: style exaggeration
    elevenlabs_speaker_boost: bool = True   # clarity boost
    elevenlabs_language: str = ""           # ISO code: "vi", "en", "ja", etc.

    # VieNeu specific
    vieneu_key: str = ""
    vieneu_keys: list[str] = field(default_factory=list)
    vieneu_base_url: str = "https://api.vieneu.io/api"
    vieneu_emotion: str = "natural"  # natural, storytelling
    vieneu_poll_interval: float = 2.0  # seconds between status polls
    vieneu_poll_timeout: float = 120.0  # max wait for job completion

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
        if not self.vieneu_key:
            self.vieneu_key = os.getenv("VIENEU_API_KEY", "")

    def get_key_ring(self, provider: str) -> KeyRing:
        """Build a KeyRing for a provider, merging single key + keys list."""
        mapping = {
            "azure": (self.azure_key, self.azure_keys),
            "siliconflow": (self.siliconflow_key, self.siliconflow_keys),
            "elevenlabs": (self.elevenlabs_key, self.elevenlabs_keys),
            "vieneu": (self.vieneu_key, self.vieneu_keys),
        }
        single, multi = mapping.get(provider, ("", []))
        all_keys = list(multi) if multi else []
        if single and single not in all_keys:
            all_keys.insert(0, single)
        return KeyRing(all_keys)


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
        "vieneu": _synth_vieneu,
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
    ring = cfg.get_key_ring("azure")
    if not ring.available:
        return TTSResult(
            output_path=output_path, voice=cfg.voice, provider="azure",
            ok=False, error="Azure Speech key not set. Set AZURE_SPEECH_KEY or config.azure_key",
        )

    api_key = ring.next()

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
            headers={"Ocp-Apim-Subscription-Key": api_key},
            timeout=10,
        )
        token_resp.raise_for_status()
        access_token = token_resp.text
    except Exception as e:
        ring.report_failure(api_key)
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
        ring.report_failure(api_key)
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
    ring = cfg.get_key_ring("siliconflow")
    if not ring.available:
        return TTSResult(
            output_path=output_path, provider="siliconflow",
            ok=False, error="SiliconFlow API key not set. Set SILICONFLOW_API_KEY",
        )

    api_key = ring.next()

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
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        resp.raise_for_status()

        if resp.headers.get("Content-Type", "").startswith("audio"):
            output_path.write_bytes(resp.content)
        else:
            ring.report_failure(api_key)
            error_data = resp.json() if resp.content else {}
            return TTSResult(
                output_path=output_path, provider="siliconflow",
                ok=False, error=f"SiliconFlow error: {error_data}",
            )
    except Exception as e:
        ring.report_failure(api_key)
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
# Provider: ElevenLabs (full features)
# ---------------------------------------------------------------------------

# ElevenLabs supported languages (29+)
ELEVENLABS_LANGUAGES: dict[str, str] = {
    "vi": "Vietnamese", "en": "English", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "fr": "French", "de": "German", "es": "Spanish",
    "pt": "Portuguese", "it": "Italian", "ru": "Russian", "ar": "Arabic",
    "hi": "Hindi", "th": "Thai", "id": "Indonesian", "ms": "Malay",
    "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "da": "Danish",
    "no": "Norwegian", "fi": "Finnish", "tr": "Turkish", "cs": "Czech",
    "ro": "Romanian", "hu": "Hungarian", "el": "Greek", "he": "Hebrew",
    "uk": "Ukrainian",
}

# ElevenLabs models
ELEVENLABS_MODELS: dict[str, str] = {
    "eleven_multilingual_v2": "Multilingual v2 — chất lượng cao, 29 ngôn ngữ",
    "eleven_turbo_v2_5": "Turbo v2.5 — nhanh hơn, 32 ngôn ngữ",
    "eleven_monolingual_v1": "Monolingual v1 — tiếng Anh",
    "eleven_multilingual_v1": "Multilingual v1 — 8 ngôn ngữ",
}

_ELEVENLABS_BASE = "https://api.elevenlabs.io/v1"


def _synth_elevenlabs(text: str, output_path: Path, cfg: TTSConfig) -> TTSResult:
    """Synthesize using ElevenLabs with full voice settings."""
    ring = cfg.get_key_ring("elevenlabs")
    if not ring.available:
        return TTSResult(
            output_path=output_path, provider="elevenlabs",
            ok=False, error="ElevenLabs API key not set. Set ELEVENLABS_API_KEY",
        )

    api_key = ring.next()

    try:
        import requests
    except ImportError:
        return TTSResult(
            output_path=output_path, provider="elevenlabs",
            ok=False, error="requests not installed",
        )

    voice_id = cfg.voice
    if voice_id.startswith("elevenlabs:"):
        voice_id = voice_id[len("elevenlabs:"):]

    url = f"{_ELEVENLABS_BASE}/text-to-speech/{voice_id}"

    payload: dict = {
        "text": text,
        "model_id": cfg.elevenlabs_model,
        "voice_settings": {
            "stability": cfg.elevenlabs_stability,
            "similarity_boost": cfg.elevenlabs_similarity,
            "style": cfg.elevenlabs_style,
            "use_speaker_boost": cfg.elevenlabs_speaker_boost,
        },
    }
    # Add language code if specified (for multilingual models)
    if cfg.elevenlabs_language:
        payload["language_code"] = cfg.elevenlabs_language

    try:
        resp = requests.post(
            url,
            json=payload,
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            timeout=120,
        )
        resp.raise_for_status()
        output_path.write_bytes(resp.content)
    except Exception as e:
        ring.report_failure(api_key)
        error_detail = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                error_detail = e.response.json().get("detail", {}).get("message", str(e))
            except Exception:
                pass
        return TTSResult(
            output_path=output_path, provider="elevenlabs",
            ok=False, error=f"ElevenLabs synthesis error: {error_detail}",
        )

    duration = _get_audio_duration(output_path)
    return TTSResult(
        output_path=output_path, voice=voice_id, provider="elevenlabs",
        duration_seconds=duration, text_length=len(text), ok=True,
    )


def elevenlabs_list_voices(api_key: str = "") -> list[dict]:
    """Fetch all available voices from ElevenLabs API.

    Returns list of dicts with: voice_id, name, category, labels, preview_url, etc.
    Categories: premade, cloned, generated, professional.
    """
    try:
        import requests
    except ImportError:
        return []

    if not api_key:
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return []

    try:
        resp = requests.get(
            f"{_ELEVENLABS_BASE}/voices",
            headers={"xi-api-key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        voices = []
        for v in data.get("voices", []):
            labels = v.get("labels", {})
            voices.append({
                "voice_id": v["voice_id"],
                "name": v["name"],
                "category": v.get("category", "premade"),
                "gender": labels.get("gender", ""),
                "accent": labels.get("accent", ""),
                "age": labels.get("age", ""),
                "description": labels.get("description", ""),
                "use_case": labels.get("use_case", ""),
                "language": labels.get("language", ""),
                "preview_url": v.get("preview_url", ""),
                "is_cloned": v.get("category") == "cloned",
            })
        return voices
    except Exception:
        return []


def elevenlabs_clone_voice(
    name: str,
    audio_files: list[str | Path],
    api_key: str = "",
    description: str = "",
    labels: dict | None = None,
) -> dict:
    """Clone a voice using ElevenLabs Instant Voice Cloning.

    Args:
        name: Name for the cloned voice.
        audio_files: List of audio file paths (mp3/wav, 1-25 files, each <10MB).
        api_key: ElevenLabs API key.
        description: Optional description.
        labels: Optional labels dict, e.g. {"language": "vi", "gender": "female"}.

    Returns:
        Dict with voice_id and name on success, or error info.
    """
    try:
        import requests
    except ImportError:
        return {"ok": False, "error": "requests not installed"}

    if not api_key:
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "No API key"}

    url = f"{_ELEVENLABS_BASE}/voices/add"

    files_data = []
    for af in audio_files:
        af = Path(af)
        if not af.exists():
            return {"ok": False, "error": f"File not found: {af}"}
        files_data.append(("files", (af.name, open(str(af), "rb"), "audio/mpeg")))

    form_data: dict = {"name": name}
    if description:
        form_data["description"] = description
    if labels:
        import json as _json
        form_data["labels"] = _json.dumps(labels)

    try:
        resp = requests.post(
            url,
            data=form_data,
            files=files_data,
            headers={"xi-api-key": api_key},
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        return {
            "ok": True,
            "voice_id": result.get("voice_id", ""),
            "name": name,
        }
    except Exception as e:
        error_msg = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                error_msg = e.response.text[:500]
            except Exception:
                pass
        return {"ok": False, "error": f"Clone error: {error_msg}"}
    finally:
        for _, file_tuple in files_data:
            try:
                file_tuple[1].close()
            except Exception:
                pass


def elevenlabs_delete_voice(voice_id: str, api_key: str = "") -> dict:
    """Delete a cloned voice from ElevenLabs."""
    try:
        import requests
    except ImportError:
        return {"ok": False, "error": "requests not installed"}

    if not api_key:
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "No API key"}

    try:
        resp = requests.delete(
            f"{_ELEVENLABS_BASE}/voices/{voice_id}",
            headers={"xi-api-key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        return {"ok": True, "voice_id": voice_id}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def elevenlabs_get_usage(api_key: str = "") -> dict:
    """Get ElevenLabs subscription usage info (quota, characters used)."""
    try:
        import requests
    except ImportError:
        return {"ok": False, "error": "requests not installed"}

    if not api_key:
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"ok": False, "error": "No API key"}

    try:
        resp = requests.get(
            f"{_ELEVENLABS_BASE}/user/subscription",
            headers={"xi-api-key": api_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "ok": True,
            "tier": data.get("tier", ""),
            "character_count": data.get("character_count", 0),
            "character_limit": data.get("character_limit", 0),
            "voice_limit": data.get("voice_limit", 0),
            "can_clone": data.get("can_extend_voice_limit", False),
            "next_reset": data.get("next_character_count_reset_unix"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Provider: VieNeu (Vietnamese TTS with voice cloning)
# ---------------------------------------------------------------------------


def _synth_vieneu(text: str, output_path: Path, cfg: TTSConfig) -> TTSResult:
    """Synthesize using VieNeu TTS — native Vietnamese voices.

    API flow (async job):
        1. POST /v1/tts  →  {jobId, status: "queued"}
        2. Poll GET /v1/tts/{jobId}  until status == "completed"
        3. Download audioUrl → save to output_path
    """
    ring = cfg.get_key_ring("vieneu")
    if not ring.available:
        return TTSResult(
            output_path=output_path, provider="vieneu",
            ok=False, error="VieNeu API key not set. Set VIENEU_API_KEY or config.vieneu_key",
        )

    api_key = ring.next()

    try:
        import requests
    except ImportError:
        return TTSResult(
            output_path=output_path, provider="vieneu",
            ok=False, error="requests not installed",
        )

    base_url = cfg.vieneu_base_url.rstrip("/")

    # Resolve voiceId: strip "vieneu:" prefix if present
    voice_id = cfg.voice
    if voice_id.startswith("vieneu:"):
        voice_id = voice_id[len("vieneu:"):]

    # 1. Submit TTS job
    payload: dict = {"text": text, "voiceId": voice_id}
    if cfg.vieneu_emotion and cfg.vieneu_emotion != "natural":
        payload["emotion"] = cfg.vieneu_emotion

    try:
        submit_resp = requests.post(
            f"{base_url}/v1/tts",
            json=payload,
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        submit_resp.raise_for_status()
        submit_data = submit_resp.json()
        job_id = submit_data.get("jobId")
        if not job_id:
            ring.report_failure(api_key)
            return TTSResult(
                output_path=output_path, provider="vieneu",
                ok=False, error=f"VieNeu: no jobId in response: {submit_data}",
            )
    except Exception as e:
        ring.report_failure(api_key)
        return TTSResult(
            output_path=output_path, provider="vieneu",
            ok=False, error=f"VieNeu submit error: {e}",
        )

    # 2. Poll for completion
    poll_start = time.time()
    audio_url = None
    duration_secs = 0.0

    while time.time() - poll_start < cfg.vieneu_poll_timeout:
        time.sleep(cfg.vieneu_poll_interval)
        try:
            status_resp = requests.get(
                f"{base_url}/v1/tts/{job_id}",
                headers={"X-API-Key": api_key},
                timeout=15,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()
            status = status_data.get("status", "").lower()

            if status == "completed":
                audio_url = status_data.get("audioUrl")
                duration_secs = float(status_data.get("duration", 0))
                break
            elif status in ("failed", "error"):
                ring.report_failure(api_key)
                return TTSResult(
                    output_path=output_path, provider="vieneu",
                    ok=False, error=f"VieNeu job failed: {status_data.get('error', status_data)}",
                )
            # else: queued / processing → keep polling
        except Exception as e:
            ring.report_failure(api_key)
            return TTSResult(
                output_path=output_path, provider="vieneu",
                ok=False, error=f"VieNeu poll error: {e}",
            )
    else:
        return TTSResult(
            output_path=output_path, provider="vieneu",
            ok=False, error=f"VieNeu timeout after {cfg.vieneu_poll_timeout}s",
        )

    if not audio_url:
        return TTSResult(
            output_path=output_path, provider="vieneu",
            ok=False, error="VieNeu: completed but no audioUrl",
        )

    # 3. Download audio
    try:
        audio_resp = requests.get(audio_url, timeout=60)
        audio_resp.raise_for_status()

        # VieNeu returns WAV — convert to mp3 if needed
        if str(output_path).endswith(".mp3") and audio_url.endswith(".wav"):
            wav_tmp = output_path.with_suffix(".vieneu.wav")
            wav_tmp.write_bytes(audio_resp.content)
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", str(wav_tmp), "-b:a", "192k", str(output_path)],
                capture_output=True, timeout=30,
            )
            wav_tmp.unlink(missing_ok=True)
            if result.returncode != 0:
                return TTSResult(
                    output_path=output_path, provider="vieneu",
                    ok=False, error=f"ffmpeg convert error: {result.stderr.decode()[:200]}",
                )
        else:
            output_path.write_bytes(audio_resp.content)
    except Exception as e:
        return TTSResult(
            output_path=output_path, provider="vieneu",
            ok=False, error=f"VieNeu download error: {e}",
        )

    # If we didn't get duration from API, probe the file
    if duration_secs <= 0:
        duration_secs = _get_audio_duration(output_path)

    return TTSResult(
        output_path=output_path,
        voice=f"vieneu:{voice_id}",
        provider="vieneu",
        duration_seconds=duration_secs,
        text_length=len(text),
        ok=True,
    )


def vieneu_list_voices(api_key: str = "", base_url: str = "https://api.vieneu.io/api") -> list[dict]:
    """Fetch all available VieNeu voices from the API.

    The /v1/voices endpoint is public (no auth needed).
    """
    try:
        import requests
        resp = requests.get(f"{base_url}/v1/voices", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("voices", [])
    except Exception:
        return []


def vieneu_list_emotions(api_key: str = "", base_url: str = "https://api.vieneu.io/api") -> dict:
    """Fetch VieNeu emotion styles and tags."""
    try:
        import requests
        resp = requests.get(f"{base_url}/v1/emotion-tags", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"styles": [], "tags": []}


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


def list_providers() -> dict[str, dict]:
    """List all TTS providers with info."""
    return {
        "edge_tts": {
            "name": "Edge TTS",
            "desc": "Microsoft Edge TTS — miễn phí, hỗ trợ tiếng Việt",
            "needs_key": False,
            "voices": list_voices_by_provider("edge_tts"),
        },
        "azure": {
            "name": "Azure Speech",
            "desc": "Microsoft Azure — chất lượng cao, SSML",
            "needs_key": True,
            "voices": list_voices_by_provider("azure"),
        },
        "siliconflow": {
            "name": "SiliconFlow",
            "desc": "CosyVoice2 — giọng tổng hợp AI",
            "needs_key": True,
            "voices": get_siliconflow_voices(),
        },
        "elevenlabs": {
            "name": "ElevenLabs",
            "desc": "Chất lượng cao, đa ngôn ngữ",
            "needs_key": True,
            "voices": list_voices_by_provider("elevenlabs"),
        },
        "vieneu": {
            "name": "VieNeu TTS",
            "desc": "Giọng đọc tiếng Việt tự nhiên nhất, voice cloning",
            "needs_key": True,
            "voices": list_voices_by_provider("vieneu"),
        },
        "no_voice": {
            "name": "Không giọng đọc",
            "desc": "Audio im lặng — chỉ subtitle",
            "needs_key": False,
            "voices": ["no_voice"],
        },
    }


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
