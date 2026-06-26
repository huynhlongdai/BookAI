"""Internationalization (i18n) for BookAI WebUI.

Supports Vietnamese (vi), English (en), Chinese (zh).

Usage::

    from bookai.i18n import t, set_language
    set_language("vi")
    print(t("Generate Video"))  # "Tạo Video"
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_current_language = "vi"
_translations: dict[str, dict[str, str]] = {}
_i18n_dir = Path(__file__).parent


def _load_language(lang: str) -> dict[str, str]:
    """Load a language file."""
    path = _i18n_dir / f"{lang}.json"
    if not path.exists():
        logger.warning(f"Language file not found: {path}")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("Translation", data)
    except Exception as e:
        logger.error(f"Failed to load {lang}.json: {e}")
        return {}


def set_language(lang: str) -> None:
    """Set the current language."""
    global _current_language
    _current_language = lang
    if lang not in _translations:
        _translations[lang] = _load_language(lang)


def get_language() -> str:
    """Get the current language code."""
    return _current_language


def t(key: str, lang: Optional[str] = None) -> str:
    """Translate a key to the current language.

    Falls back to the key itself if no translation found.
    """
    use_lang = lang or _current_language
    if use_lang not in _translations:
        _translations[use_lang] = _load_language(use_lang)

    return _translations.get(use_lang, {}).get(key, key)


def available_languages() -> list[dict[str, str]]:
    """List available languages."""
    langs = []
    for path in sorted(_i18n_dir.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            langs.append({
                "code": path.stem,
                "name": data.get("Language", path.stem),
            })
        except Exception:
            pass
    return langs


# Auto-load Vietnamese on import
set_language("vi")
