"""Tests for Phase 3 — Distribution + DevOps.

Tests: social_post, llm_providers, social_metadata, config, file_security, i18n
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ===========================================================================
# social_post tests
# ===========================================================================

class TestSocialPost:

    def test_social_platform_enum(self):
        from bookai.social_post import SocialPlatform
        assert SocialPlatform.TIKTOK.value == "tiktok"
        assert len(SocialPlatform.all()) == 4

    def test_privacy_level_enum(self):
        from bookai.social_post import PrivacyLevel
        assert PrivacyLevel.PUBLIC.value == "PUBLIC_TO_EVERYONE"

    def test_config_defaults(self):
        from bookai.social_post import SocialPostConfig
        cfg = SocialPostConfig()
        assert cfg.timeout == 300
        assert "tiktok" in cfg.platforms

    def test_config_from_env(self):
        from bookai.social_post import SocialPostConfig
        with patch.dict(os.environ, {"UPLOAD_POST_API_KEY": "test-key"}):
            cfg = SocialPostConfig.from_env()
            assert cfg.api_key == "test-key"

    def test_config_from_dict(self):
        from bookai.social_post import SocialPostConfig
        cfg = SocialPostConfig.from_dict({
            "upload_post_api_key": "k1",
            "upload_post_username": "u1",
            "upload_post_enabled": True,
        })
        assert cfg.api_key == "k1"
        assert cfg.username == "u1"

    def test_post_result(self):
        from bookai.social_post import PostResult
        r = PostResult(ok=True, request_id="req-123", platforms=["tiktok"])
        d = r.to_dict()
        assert d["ok"] is True
        assert d["request_id"] == "req-123"

    def test_youtube_extra(self):
        from bookai.social_post import YouTubeExtra
        yt = YouTubeExtra(title="Test", tags=["book", "ai"])
        assert yt.contains_synthetic_media is True

    def test_upload_no_key(self):
        from bookai.social_post import SocialPostConfig, upload_video
        cfg = SocialPostConfig(api_key="", username="")
        r = upload_video("/tmp/test.mp4", "Title", config=cfg)
        assert not r.ok
        assert "not configured" in r.error

    def test_upload_disabled(self):
        from bookai.social_post import SocialPostConfig, upload_video
        cfg = SocialPostConfig(api_key="k", username="u", enabled=False)
        r = upload_video("/tmp/test.mp4", "Title", config=cfg)
        assert not r.ok
        assert "disabled" in r.error

    def test_upload_file_not_found(self):
        from bookai.social_post import SocialPostConfig, upload_video
        cfg = SocialPostConfig(api_key="k", username="u")
        r = upload_video("/tmp/nonexistent_video_12345.mp4", "Title", config=cfg)
        assert not r.ok
        assert "not found" in r.error

    def test_webhook_no_url(self):
        from bookai.social_post import SocialPostConfig, post_webhook
        cfg = SocialPostConfig(webhook_url="")
        r = post_webhook("/tmp/test.mp4", {}, config=cfg)
        assert not r.ok
        assert "webhook" in r.error.lower()


# ===========================================================================
# llm_providers tests
# ===========================================================================

class TestLLMProviders:

    def test_provider_enum(self):
        from bookai.llm_providers import LLMProvider
        assert "openai" in LLMProvider.values()
        assert len(LLMProvider.values()) == 10

    def test_config_defaults(self):
        from bookai.llm_providers import LLMConfig
        cfg = LLMConfig(provider="openai")
        assert cfg.base_url == "https://api.openai.com/v1"
        assert cfg.model == "gpt-4o-mini"

    def test_config_deepseek(self):
        from bookai.llm_providers import LLMConfig
        cfg = LLMConfig(provider="deepseek")
        assert "deepseek" in cfg.base_url
        assert cfg.model == "deepseek-chat"

    def test_config_from_dict(self):
        from bookai.llm_providers import LLMConfig
        cfg = LLMConfig.from_dict({"llm_provider": "gemini", "api_key": "k1"})
        assert cfg.provider == "gemini"
        assert cfg.api_key == "k1"

    def test_strip_think_blocks(self):
        from bookai.llm_providers import strip_think_blocks
        text = "<think>internal reasoning</think>Final answer"
        assert strip_think_blocks(text) == "Final answer"

    def test_strip_unclosed_think(self):
        from bookai.llm_providers import strip_think_blocks
        text = "<think>still thinking... no close"
        assert strip_think_blocks(text) == ""

    def test_sanitize_error(self):
        from bookai.llm_providers import sanitize_error
        err = "Error at https://user:pass@api.example.com/v1"
        sanitized = sanitize_error(err)
        assert "pass" not in sanitized
        assert "***" in sanitized

    def test_sanitize_query_params(self):
        from bookai.llm_providers import sanitize_error
        err = "Error at https://api.com?api_key=secret123&other=ok"
        sanitized = sanitize_error(err)
        assert "secret123" not in sanitized

    def test_clean_response(self):
        from bookai.llm_providers import clean_response
        assert clean_response("<think>x</think>Hello") == "Hello"
        assert clean_response("```json\n{}\n```") == "{}"
        assert clean_response("") == ""

    def test_generate_empty_prompt(self):
        from bookai.llm_providers import generate
        r = generate("")
        assert not r.ok
        assert "Empty" in r.error

    def test_generate_no_api_key(self):
        from bookai.llm_providers import LLMConfig, generate
        cfg = LLMConfig(provider="openai", api_key="")
        r = generate("hello", config=cfg)
        assert not r.ok
        assert "key not set" in r.error

    def test_generate_unknown_provider(self):
        from bookai.llm_providers import LLMConfig, generate
        cfg = LLMConfig(provider="nonexistent", api_key="k")
        r = generate("hello", config=cfg)
        assert not r.ok
        assert "Unknown" in r.error

    def test_ollama_no_key_needed(self):
        from bookai.llm_providers import LLMConfig
        cfg = LLMConfig(provider="ollama")
        assert cfg.base_url == "http://localhost:11434/v1"

    def test_list_providers(self):
        from bookai.llm_providers import list_providers
        providers = list_providers()
        assert "openai" in providers
        assert "anthropic" in providers
        assert len(providers) >= 10

    def test_result_to_dict(self):
        from bookai.llm_providers import LLMResult
        r = LLMResult(ok=True, text="x" * 300, provider="openai")
        d = r.to_dict()
        assert len(d["text"]) <= 203  # truncated


# ===========================================================================
# social_metadata tests
# ===========================================================================

class TestSocialMetadata:

    def test_platform_metadata(self):
        from bookai.social_metadata import PlatformMetadata
        pm = PlatformMetadata(platform="tiktok", caption="Hi", hashtags=["book", "ai"])
        assert "#book" in pm.full_caption
        d = pm.to_dict()
        assert d["platform"] == "tiktok"

    def test_generate_simple_vi(self):
        from bookai.social_metadata import MetadataRequest, generate_metadata_simple
        req = MetadataRequest(
            book_title="Atomic Habits",
            author="James Clear",
            language="vi",
        )
        meta = generate_metadata_simple(req)
        assert meta.ok
        assert "tiktok" in meta.platforms
        assert "Atomic Habits" in meta.platforms["tiktok"].caption

    def test_generate_simple_en(self):
        from bookai.social_metadata import MetadataRequest, generate_metadata_simple
        req = MetadataRequest(book_title="Test", language="en")
        meta = generate_metadata_simple(req)
        assert meta.ok

    def test_generate_metadata_no_llm(self):
        from bookai.social_metadata import MetadataRequest, generate_metadata
        req = MetadataRequest(book_title="Test Book")
        meta = generate_metadata(req, llm_config=None)
        assert meta.ok
        assert len(meta.platforms) > 0

    def test_metadata_to_dict(self):
        from bookai.social_metadata import MetadataRequest, generate_metadata
        req = MetadataRequest(book_title="Test")
        meta = generate_metadata(req)
        d = meta.to_dict()
        assert "platforms" in d
        assert d["ok"] is True

    def test_platform_limits(self):
        from bookai.social_metadata import PLATFORM_LIMITS
        assert PLATFORM_LIMITS["youtube"]["title_max"] == 100
        assert PLATFORM_LIMITS["tiktok"]["hashtag_max"] == 10


# ===========================================================================
# config tests
# ===========================================================================

class TestConfig:

    def test_default_config_structure(self):
        from bookai.config import DEFAULT_CONFIG
        assert "app" in DEFAULT_CONFIG
        assert "llm" in DEFAULT_CONFIG
        assert "tts" in DEFAULT_CONFIG
        assert "video" in DEFAULT_CONFIG
        assert "social" in DEFAULT_CONFIG

    def test_deep_merge(self):
        from bookai.config import _deep_merge
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"x": 10, "z": 30}}
        result = _deep_merge(base, override)
        assert result["a"]["x"] == 10
        assert result["a"]["y"] == 2
        assert result["a"]["z"] == 30
        assert result["b"] == 3

    def test_load_nonexistent_config(self):
        from bookai.config import load_config
        cfg = load_config("/tmp/nonexistent_bookai_config_12345.toml")
        assert "app" in cfg
        assert cfg["app"]["project_name"] == "BookAI"

    def test_get_section(self):
        from bookai.config import load_config, get_section
        load_config("/tmp/nonexistent_bookai_config_12345.toml")
        llm = get_section("llm")
        assert "provider" in llm

    def test_set_value(self):
        from bookai.config import load_config, set_value, get_config
        load_config("/tmp/nonexistent_bookai_config_12345.toml")
        set_value("app", "custom_field", "test_value")
        cfg = get_config()
        assert cfg["app"]["custom_field"] == "test_value"

    def test_generate_example(self):
        from bookai.config import generate_example_config
        example = generate_example_config()
        assert "BookAI" in example or "toml" in example.lower() or len(example) > 0


# ===========================================================================
# file_security tests
# ===========================================================================

class TestFileSecurity:

    def test_resolve_safe_path_normal(self):
        from bookai.file_security import resolve_safe_path
        with tempfile.NamedTemporaryFile(dir="/tmp", suffix=".txt") as f:
            result = resolve_safe_path("/tmp", os.path.basename(f.name))
            assert result == f.name

    def test_resolve_safe_path_traversal(self):
        from bookai.file_security import resolve_safe_path
        with pytest.raises(ValueError, match="outside"):
            resolve_safe_path("/tmp/test_base", "../../../etc/passwd")

    def test_resolve_safe_path_empty(self):
        from bookai.file_security import resolve_safe_path
        with pytest.raises(ValueError, match="Empty"):
            resolve_safe_path("/tmp", "")

    def test_sanitize_filename_normal(self):
        from bookai.file_security import sanitize_filename
        assert sanitize_filename("report.pdf") == "report.pdf"

    def test_sanitize_filename_traversal(self):
        from bookai.file_security import sanitize_filename
        assert sanitize_filename("../../evil.sh") == "evil.sh"

    def test_sanitize_filename_special_chars(self):
        from bookai.file_security import sanitize_filename
        result = sanitize_filename('file<>:"|?.txt')
        assert "<" not in result
        assert ">" not in result

    def test_sanitize_filename_empty(self):
        from bookai.file_security import sanitize_filename
        assert sanitize_filename("") == "unnamed"

    def test_sanitize_filename_dots(self):
        from bookai.file_security import sanitize_filename
        assert sanitize_filename("...hidden") == "hidden"

    def test_sanitize_filename_long(self):
        from bookai.file_security import sanitize_filename
        result = sanitize_filename("a" * 300 + ".txt")
        assert len(result) <= 255

    def test_is_safe_path(self):
        from bookai.file_security import is_safe_path
        assert is_safe_path("/tmp", "file.txt") is True
        assert is_safe_path("/tmp", "../../etc/passwd") is False

    def test_validate_file_type(self):
        from bookai.file_security import validate_file_type
        assert validate_file_type("video.mp4") is True
        assert validate_file_type("script.exe") is False
        assert validate_file_type("book.pdf") is True

    def test_validate_file_type_custom(self):
        from bookai.file_security import validate_file_type
        assert validate_file_type("data.csv", {".csv", ".tsv"}) is True
        assert validate_file_type("data.txt", {".csv", ".tsv"}) is False


# ===========================================================================
# i18n tests
# ===========================================================================

class TestI18n:

    def test_set_and_get_language(self):
        from bookai.i18n import set_language, get_language
        set_language("en")
        assert get_language() == "en"
        set_language("vi")
        assert get_language() == "vi"

    def test_translate_vi(self):
        from bookai.i18n import set_language, t
        set_language("vi")
        assert t("Generate Video") == "Tạo Video"
        assert t("Settings") == "Cài Đặt"

    def test_translate_en(self):
        from bookai.i18n import set_language, t
        set_language("en")
        assert t("Generate Video") == "Generate Video"

    def test_translate_fallback(self):
        from bookai.i18n import t
        assert t("nonexistent_key_12345") == "nonexistent_key_12345"

    def test_translate_specific_lang(self):
        from bookai.i18n import t
        assert t("Generate Video", lang="vi") == "Tạo Video"

    def test_available_languages(self):
        from bookai.i18n import available_languages
        langs = available_languages()
        codes = [l["code"] for l in langs]
        assert "vi" in codes
        assert "en" in codes
        # Check language names
        vi_lang = next(l for l in langs if l["code"] == "vi")
        assert vi_lang["name"] == "Tiếng Việt"
