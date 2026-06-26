"""LLM Multi-Provider engine for BookAI.

Supports 10+ LLM providers via OpenAI-compatible API or native SDKs:
- OpenAI (GPT-4o, GPT-4o-mini, etc.)
- Anthropic (Claude)
- Google Gemini
- DeepSeek
- Ollama (local models)
- Moonshot (Kimi)
- Qwen (通义千问)
- Groq (fast inference)
- LiteLLM (100+ providers)
- OpenAI-compatible (any custom endpoint)

All providers are called via a unified interface with automatic retry,
error sanitization, and <think> block stripping.

Usage::

    from bookai.llm_providers import generate, LLMConfig

    cfg = LLMConfig(provider="openai", api_key="sk-...", model="gpt-4o-mini")
    text = generate("Write a short video script about AI books", config=cfg)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds

# Regex patterns for cleaning
_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think\b[^>]*>.*$", re.IGNORECASE | re.DOTALL)
_URL_USERINFO_RE = re.compile(
    r"((?:https?|wss?)://)([^/\s?#@]*:[^/\s?#@]*@)", re.IGNORECASE
)
_SENSITIVE_QUERY_RE = re.compile(
    r"([?&](?:api[_-]?key|access[_-]?token|token|key|secret|password)=)([^&#\s]+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Enums & Config
# ---------------------------------------------------------------------------

class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    MOONSHOT = "moonshot"
    QWEN = "qwen"
    GROQ = "groq"
    LITELLM = "litellm"
    OPENAI_COMPATIBLE = "openai_compatible"

    @classmethod
    def values(cls) -> list[str]:
        return [p.value for p in cls]


# Provider default configurations
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-20250514",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "env_key": "GEMINI_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3",
        "env_key": "",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "env_key": "MOONSHOT_API_KEY",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-max",
        "env_key": "QWEN_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
    "litellm": {
        "base_url": "",
        "model": "openai/gpt-4o-mini",
        "env_key": "",
    },
    "openai_compatible": {
        "base_url": "",
        "model": "",
        "env_key": "LLM_API_KEY",
    },
}


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    max_retries: int = MAX_RETRIES
    retry_delay: float = RETRY_DELAY
    timeout: int = 60
    system_prompt: str = ""

    # Anthropic-specific
    anthropic_version: str = "2023-06-01"

    def __post_init__(self):
        """Fill defaults from provider config and env vars."""
        defaults = PROVIDER_DEFAULTS.get(self.provider, {})

        if not self.base_url:
            self.base_url = defaults.get("base_url", "")
        if not self.model:
            self.model = defaults.get("model", "")
        if not self.api_key:
            env_key = defaults.get("env_key", "")
            if env_key:
                self.api_key = os.getenv(env_key, "")

    @classmethod
    def from_dict(cls, d: dict) -> LLMConfig:
        """Create config from a dictionary."""
        return cls(
            provider=d.get("llm_provider", d.get("provider", "openai")),
            api_key=d.get("api_key", d.get("openai_api_key", "")),
            base_url=d.get("base_url", d.get("openai_base_url", "")),
            model=d.get("model", d.get("openai_model_name", "")),
            temperature=d.get("temperature", 0.7),
            max_tokens=d.get("max_tokens", 4096),
            system_prompt=d.get("system_prompt", ""),
        )


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class LLMResult:
    """Result of an LLM generation call."""
    ok: bool = False
    text: str = ""
    provider: str = ""
    model: str = ""
    error: str = ""
    retries: int = 0
    latency_ms: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "text": self.text[:200] + "..." if len(self.text) > 200 else self.text,
            "provider": self.provider,
            "model": self.model,
            "error": self.error,
            "retries": self.retries,
            "latency_ms": round(self.latency_ms, 1),
        }


# ---------------------------------------------------------------------------
# Text cleaning utilities
# ---------------------------------------------------------------------------

def strip_think_blocks(text: str) -> str:
    """Strip <think>...</think> blocks from reasoning model output."""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _UNCLOSED_THINK_RE.sub("", text)
    return text.strip()


def sanitize_error(error: object) -> str:
    """Sanitize error messages to avoid leaking credentials."""
    message = str(error)
    message = _URL_USERINFO_RE.sub(r"\1***:***@", message)
    message = _SENSITIVE_QUERY_RE.sub(r"\1***", message)
    return message


def clean_response(text: str) -> str:
    """Clean LLM response text: strip think blocks, normalize whitespace."""
    if not text:
        return ""
    text = strip_think_blocks(text)
    # Remove markdown code fences if the whole response is wrapped
    if text.startswith("```") and text.endswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    return text.strip()


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _call_openai_compatible(
    prompt: str,
    config: LLMConfig,
    system_prompt: str = "",
) -> LLMResult:
    """Call any OpenAI-compatible API (OpenAI, DeepSeek, Groq, Moonshot, etc.)."""
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=config.api_key or "ollama",  # Ollama needs any non-empty string
            base_url=config.base_url,
            timeout=config.timeout,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        choices = getattr(response, "choices", None)
        if not choices:
            return LLMResult(ok=False, error=f"[{config.provider}] empty choices")

        content = choices[0].message.content
        if content is None:
            return LLMResult(ok=False, error=f"[{config.provider}] empty content")

        text = clean_response(content)
        if not text:
            return LLMResult(ok=False, error=f"[{config.provider}] empty after cleaning")

        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return LLMResult(
            ok=True,
            text=text,
            provider=config.provider,
            model=config.model,
            usage=usage,
        )

    except ImportError:
        return LLMResult(
            ok=False,
            error="openai package not installed. Run: pip install openai",
        )
    except Exception as e:
        return LLMResult(
            ok=False,
            provider=config.provider,
            model=config.model,
            error=sanitize_error(e),
        )


def _call_anthropic(
    prompt: str,
    config: LLMConfig,
    system_prompt: str = "",
) -> LLMResult:
    """Call Anthropic Claude API (native, not OpenAI-compatible)."""
    try:
        import requests as req

        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": config.anthropic_version,
            "content-type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        response = req.post(
            f"{config.base_url}/messages",
            headers=headers,
            json=payload,
            timeout=config.timeout,
        )
        response.raise_for_status()
        data = response.json()

        content_blocks = data.get("content", [])
        text_parts = [b["text"] for b in content_blocks if b.get("type") == "text"]
        text = clean_response("\n".join(text_parts))

        if not text:
            return LLMResult(ok=False, error="[anthropic] empty response")

        usage = {}
        if "usage" in data:
            usage = {
                "prompt_tokens": data["usage"].get("input_tokens", 0),
                "completion_tokens": data["usage"].get("output_tokens", 0),
            }

        return LLMResult(
            ok=True,
            text=text,
            provider="anthropic",
            model=config.model,
            usage=usage,
        )

    except Exception as e:
        return LLMResult(
            ok=False,
            provider="anthropic",
            model=config.model,
            error=sanitize_error(e),
        )


def _call_gemini(
    prompt: str,
    config: LLMConfig,
    system_prompt: str = "",
) -> LLMResult:
    """Call Google Gemini API via OpenAI-compatible endpoint."""
    # Gemini supports OpenAI-compatible API
    if not config.base_url:
        config.base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
    return _call_openai_compatible(prompt, config, system_prompt)


def _call_litellm(
    prompt: str,
    config: LLMConfig,
    system_prompt: str = "",
) -> LLMResult:
    """Call any provider via LiteLLM."""
    try:
        import litellm

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = litellm.completion(
            model=config.model,
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        content = response.choices[0].message.content
        text = clean_response(content or "")

        if not text:
            return LLMResult(ok=False, error="[litellm] empty response")

        return LLMResult(
            ok=True,
            text=text,
            provider="litellm",
            model=config.model,
        )

    except ImportError:
        return LLMResult(
            ok=False,
            error="litellm package not installed. Run: pip install litellm",
        )
    except Exception as e:
        return LLMResult(
            ok=False,
            provider="litellm",
            model=config.model,
            error=sanitize_error(e),
        )


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------

# Providers that use OpenAI-compatible API
_OPENAI_COMPATIBLE_PROVIDERS = {
    "openai", "deepseek", "moonshot", "qwen", "groq",
    "ollama", "openai_compatible",
}


def _dispatch(
    prompt: str,
    config: LLMConfig,
    system_prompt: str = "",
) -> LLMResult:
    """Dispatch to the appropriate provider."""
    provider = config.provider.lower()

    if not config.api_key and provider not in ("ollama", "litellm"):
        return LLMResult(
            ok=False,
            provider=provider,
            error=f"[{provider}] API key not set",
        )

    if provider in _OPENAI_COMPATIBLE_PROVIDERS:
        return _call_openai_compatible(prompt, config, system_prompt)
    elif provider == "anthropic":
        return _call_anthropic(prompt, config, system_prompt)
    elif provider == "gemini":
        return _call_gemini(prompt, config, system_prompt)
    elif provider == "litellm":
        return _call_litellm(prompt, config, system_prompt)
    else:
        return LLMResult(
            ok=False,
            error=f"Unknown LLM provider: {provider}. "
                  f"Supported: {', '.join(LLMProvider.values())}",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(
    prompt: str,
    config: Optional[LLMConfig] = None,
    system_prompt: str = "",
) -> LLMResult:
    """Generate text using the configured LLM provider.

    Includes automatic retry with exponential backoff.

    Args:
        prompt: User prompt
        config: LLM configuration (uses env defaults if None)
        system_prompt: System prompt for instruction

    Returns:
        LLMResult with generated text
    """
    cfg = config or LLMConfig()
    sys_prompt = system_prompt or cfg.system_prompt

    if not prompt:
        return LLMResult(ok=False, error="Empty prompt")

    last_error = ""
    for attempt in range(cfg.max_retries):
        start = time.time()
        result = _dispatch(prompt, cfg, sys_prompt)
        result.latency_ms = (time.time() - start) * 1000
        result.retries = attempt

        if result.ok:
            return result

        last_error = result.error
        logger.warning(
            f"LLM attempt {attempt + 1}/{cfg.max_retries} failed: {last_error}"
        )

        if attempt < cfg.max_retries - 1:
            delay = cfg.retry_delay * (2 ** attempt)
            time.sleep(delay)

    return LLMResult(
        ok=False,
        provider=cfg.provider,
        model=cfg.model,
        error=f"All {cfg.max_retries} attempts failed. Last error: {last_error}",
        retries=cfg.max_retries,
    )


def generate_json(
    prompt: str,
    config: Optional[LLMConfig] = None,
    system_prompt: str = "",
) -> tuple[bool, Any, str]:
    """Generate and parse JSON from LLM.

    Returns:
        Tuple of (ok, parsed_data, error_message)
    """
    json_system = (system_prompt or "") + "\nRespond with valid JSON only. No markdown."
    result = generate(prompt, config, json_system)

    if not result.ok:
        return False, None, result.error

    try:
        # Try to extract JSON from response
        text = result.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        data = json.loads(text)
        return True, data, ""
    except json.JSONDecodeError as e:
        return False, None, f"JSON parse error: {e}"


def list_providers() -> dict[str, dict[str, str]]:
    """List all supported providers with their defaults."""
    return {k: {**v} for k, v in PROVIDER_DEFAULTS.items()}
