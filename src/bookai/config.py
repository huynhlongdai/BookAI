"""TOML-based configuration system for BookAI.

Replaces JSON settings with a structured TOML config file with sections:
[app], [llm], [tts], [video], [social], [affiliate], [proxy]

Usage::

    from bookai.config import get_config, save_config
    cfg = get_config()
    cfg["llm"]["provider"]  # "openai"
"""

from __future__ import annotations

import os
import shutil
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Try to import toml, fall back to tomllib (Python 3.11+) for reading
try:
    import toml
    _HAS_TOML = True
except ImportError:
    _HAS_TOML = False
    try:
        import tomllib  # Python 3.11+
        _HAS_TOMLLIB = True
    except ImportError:
        _HAS_TOMLLIB = False


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "project_name": "BookAI",
        "version": "0.2.0",
        "listen_host": "0.0.0.0",
        "listen_port": 8080,
        "log_level": "INFO",
        "output_dir": "output",
        "material_directory": "",
        "enable_redis": False,
        "redis_host": "localhost",
        "redis_port": 6379,
        "redis_db": 0,
        "redis_password": "",
        "max_concurrent_tasks": 5,
        "max_queued_tasks": 100,
        "tls_verify": True,
    },
    "llm": {
        "provider": "openai",
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "openai_model_name": "gpt-4o-mini",
        "anthropic_api_key": "",
        "anthropic_model_name": "claude-sonnet-4-20250514",
        "gemini_api_key": "",
        "gemini_model_name": "gemini-2.5-flash",
        "deepseek_api_key": "",
        "deepseek_model_name": "deepseek-chat",
        "ollama_base_url": "http://localhost:11434/v1",
        "ollama_model_name": "llama3",
        "temperature": 0.7,
        "max_tokens": 4096,
    },
    "tts": {
        "provider": "edge_tts",
        "voice": "vi-VN-HoaiMyNeural",
        "rate": "+0%",
        "azure_speech_key": "",
        "azure_speech_region": "",
        "siliconflow_api_key": "",
        "elevenlabs_api_key": "",
        "elevenlabs_model_id": "eleven_multilingual_v2",
        "edge_tts_timeout": 30,
    },
    "video": {
        "aspect": "9:16",
        "transition": "fade_in",
        "bgm_mode": "random",
        "bgm_volume": 0.2,
        "voice_volume": 1.0,
        "subtitle_enabled": True,
        "subtitle_font": "BeVietnamPro-Bold.ttf",
        "subtitle_font_size": 60,
        "subtitle_color": "#FFFFFF",
        "subtitle_stroke_color": "#000000",
        "subtitle_stroke_width": 2,
        "subtitle_position": "bottom",
        "video_source": "pexels",
        "pexels_api_keys": [],
        "pixabay_api_keys": [],
    },
    "social": {
        "upload_post_enabled": False,
        "upload_post_api_key": "",
        "upload_post_username": "",
        "upload_post_platforms": ["tiktok", "instagram"],
        "upload_post_auto_upload": False,
        "upload_post_youtube_privacy_status": "public",
        "youtube_ai_content_flag": True,
        "webhook_url": "",
    },
    "affiliate": {
        "tiki_affiliate_id": "",
        "shopee_affiliate_id": "",
        "lazada_affiliate_id": "",
        "amazon_associate_tag": "",
    },
    "proxy": {},
    "ui": {
        "language": "vi",
        "hide_log": False,
        "hide_config": False,
    },
}


# ---------------------------------------------------------------------------
# Config loading / saving
# ---------------------------------------------------------------------------

_config: Optional[dict[str, Any]] = None
_config_path: Optional[str] = None


def _find_config_path() -> str:
    """Find the config file path."""
    # Check env var first
    env_path = os.getenv("BOOKAI_CONFIG")
    if env_path:
        return env_path

    # Check current directory
    cwd_config = Path.cwd() / "config.toml"
    if cwd_config.exists():
        return str(cwd_config)

    # Check project root (parent of src/)
    src_dir = Path(__file__).parent
    project_root = src_dir.parent.parent
    root_config = project_root / "config.toml"
    if root_config.exists():
        return str(root_config)

    # Default: create in project root
    return str(root_config)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
    """Load configuration from TOML file.

    Falls back to defaults if file doesn't exist.
    Creates config.toml from example if available.
    """
    global _config, _config_path

    path = config_path or _find_config_path()
    _config_path = path

    config_file = Path(path)

    # If no config exists, check for example
    if not config_file.exists():
        example = config_file.parent / "config.example.toml"
        if example.exists():
            shutil.copyfile(example, config_file)
            logger.info(f"Copied config.example.toml → config.toml")
        else:
            logger.info("No config.toml found, using defaults")
            _config = {k: {**v} if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
            return _config

    logger.info(f"Loading config from {path}")

    try:
        if _HAS_TOML:
            file_config = toml.load(str(config_file))
        elif _HAS_TOMLLIB:
            with open(config_file, "rb") as f:
                file_config = tomllib.load(f)
        else:
            logger.warning("No TOML library available. Using defaults.")
            _config = {k: {**v} if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
            return _config
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        _config = {k: {**v} if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
        return _config

    # Merge with defaults
    _config = _deep_merge(DEFAULT_CONFIG, file_config)
    return _config


def save_config(config: Optional[dict] = None, config_path: Optional[str] = None) -> bool:
    """Save configuration to TOML file."""
    if not _HAS_TOML:
        logger.error("toml package required for saving. Run: pip install toml")
        return False

    cfg = config or _config or DEFAULT_CONFIG
    path = config_path or _config_path or _find_config_path()

    try:
        with open(path, "w", encoding="utf-8") as f:
            toml.dump(cfg, f)
        logger.info(f"Config saved to {path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def get_config() -> dict[str, Any]:
    """Get the current configuration (loads if not yet loaded)."""
    global _config
    if _config is None:
        load_config()
    return _config or DEFAULT_CONFIG


def get_section(section: str) -> dict[str, Any]:
    """Get a configuration section."""
    cfg = get_config()
    return cfg.get(section, {})


def set_value(section: str, key: str, value: Any) -> None:
    """Set a configuration value."""
    cfg = get_config()
    if section not in cfg:
        cfg[section] = {}
    cfg[section][key] = value


def generate_example_config() -> str:
    """Generate example config.toml content."""
    if not _HAS_TOML:
        return "# toml package required to generate example config"
    return toml.dumps(DEFAULT_CONFIG)
