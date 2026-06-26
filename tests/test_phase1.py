"""Tests for Phase 1 Video Engine Upgrade modules.

Tests the new modules inspired by MoneyPrinterTurbo:
- video_effects
- subtitle
- bgm
- stock_video
- upgraded video_render
"""

import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ===========================================================================
# video_effects tests
# ===========================================================================


class TestVideoEffects:
    """Test video transition effects."""

    def test_apply_transition_none(self):
        from bookai.video_effects import apply_transition

        mock_clip = MagicMock()
        result = apply_transition(mock_clip, "none")
        assert result is mock_clip

    def test_apply_transition_none_value(self):
        from bookai.video_effects import apply_transition

        mock_clip = MagicMock()
        result = apply_transition(mock_clip, None)
        assert result is mock_clip

    def test_apply_transition_unknown(self):
        from bookai.video_effects import apply_transition

        mock_clip = MagicMock()
        result = apply_transition(mock_clip, "nonexistent_effect")
        assert result is mock_clip

    def test_transition_map_keys(self):
        from bookai.video_effects import _TRANSITION_MAP

        expected = {"fade_in", "fade_out", "slide_in", "slide_out", "zoom_in", "zoom_out"}
        assert expected == set(_TRANSITION_MAP.keys())

    def test_shuffle_pool_not_empty(self):
        from bookai.video_effects import _SHUFFLE_POOL

        assert len(_SHUFFLE_POOL) > 0


# ===========================================================================
# subtitle tests
# ===========================================================================


class TestSubtitle:
    """Test subtitle generation and parsing."""

    def test_format_srt_time(self):
        from bookai.subtitle import _format_srt_time

        assert _format_srt_time(0.0) == "00:00:00,000"
        assert _format_srt_time(61.5) == "00:01:01,500"
        assert _format_srt_time(3661.123) == "01:01:01,123"

    def test_chunk_words_basic(self):
        from bookai.subtitle import _chunk_words_to_subtitle_lines

        words = [
            {"word": "Xin", "start": 0.0, "end": 0.3},
            {"word": "chào", "start": 0.3, "end": 0.6},
            {"word": "các", "start": 0.6, "end": 0.8},
            {"word": "bạn", "start": 0.8, "end": 1.0},
        ]
        lines = _chunk_words_to_subtitle_lines(words, max_chars=25)
        assert len(lines) >= 1
        assert lines[0]["start"] == 0.0

    def test_chunk_words_line_break(self):
        from bookai.subtitle import _chunk_words_to_subtitle_lines

        words = [
            {"word": "A" * 12, "start": 0.0, "end": 0.5},
            {"word": "B" * 12, "start": 0.5, "end": 1.0},
            {"word": "C" * 12, "start": 1.0, "end": 1.5},
        ]
        lines = _chunk_words_to_subtitle_lines(words, max_chars=25)
        assert len(lines) >= 2  # Should break into multiple lines

    def test_chunk_words_empty(self):
        from bookai.subtitle import _chunk_words_to_subtitle_lines

        assert _chunk_words_to_subtitle_lines([]) == []

    def test_parse_srt_time(self):
        from bookai.subtitle import _parse_srt_time

        assert _parse_srt_time("00:01:30,500") == pytest.approx(90.5, abs=0.01)
        assert _parse_srt_time("01:00:00.000") == pytest.approx(3600.0, abs=0.01)

    def test_write_and_parse_srt(self, tmp_path):
        from bookai.subtitle import _write_srt, parse_srt

        subs = [
            {"text": "Xin chào", "start": 0.0, "end": 1.5},
            {"text": "Thế giới", "start": 1.5, "end": 3.0},
        ]
        srt_path = tmp_path / "test.srt"
        _write_srt(subs, srt_path)

        assert srt_path.exists()
        parsed = parse_srt(srt_path)
        assert len(parsed) == 2
        assert parsed[0]["text"] == "Xin chào"
        assert parsed[1]["text"] == "Thế giới"

    def test_fallback_text_subtitles(self):
        from bookai.subtitle import _fallback_text_subtitles

        subs = _fallback_text_subtitles("Đây là một đoạn văn bản dài để test", max_chars=15)
        assert len(subs) >= 1
        assert subs[0]["start"] == 0.0

    def test_levenshtein_distance(self):
        from bookai.subtitle import _levenshtein_distance

        assert _levenshtein_distance("kitten", "sitting") == 3
        assert _levenshtein_distance("", "abc") == 3
        assert _levenshtein_distance("abc", "abc") == 0

    def test_similarity(self):
        from bookai.subtitle import _similarity

        assert _similarity("hello", "hello") == 1.0
        assert _similarity("hello", "hallo") > 0.7
        assert _similarity("", "") == 0.0

    def test_subtitle_config_defaults(self):
        from bookai.subtitle import SubtitleConfig

        cfg = SubtitleConfig()
        assert cfg.enabled is True
        assert cfg.position == "bottom"
        assert cfg.font_size == 48

    def test_clean_for_tts(self):
        from bookai.subtitle import _clean_for_tts

        text = "**bold** text https://example.com #hashtag"
        cleaned = _clean_for_tts(text)
        assert "**" not in cleaned
        assert "https://" not in cleaned
        assert "#hashtag" not in cleaned
        assert "bold" in cleaned

    def test_parse_srt_empty_file(self, tmp_path):
        from bookai.subtitle import parse_srt

        empty = tmp_path / "empty.srt"
        empty.write_text("")
        assert parse_srt(empty) == []

    def test_parse_srt_nonexistent(self):
        from bookai.subtitle import parse_srt

        assert parse_srt("/nonexistent/file.srt") == []


# ===========================================================================
# bgm tests
# ===========================================================================


class TestBgm:
    """Test background music manager."""

    def test_get_songs_dir_creates(self, tmp_path):
        from bookai.bgm import get_songs_dir

        d = tmp_path / "songs"
        result = get_songs_dir(str(d))
        assert result.exists()

    def test_list_bgm_empty(self, tmp_path):
        from bookai.bgm import list_bgm

        d = tmp_path / "empty_songs"
        d.mkdir()
        result = list_bgm(str(d))
        assert result == []

    def test_list_bgm_with_files(self, tmp_path):
        from bookai.bgm import list_bgm

        d = tmp_path / "songs"
        d.mkdir()
        (d / "track1.mp3").write_bytes(b"fake mp3 data")
        (d / "track2.mp3").write_bytes(b"fake mp3 data 2")
        (d / "readme.txt").write_text("not a song")

        result = list_bgm(str(d))
        assert len(result) == 2
        assert result[0]["name"] == "track1.mp3"

    def test_get_bgm_none_mode(self):
        from bookai.bgm import get_bgm_file

        assert get_bgm_file(mode="none") is None

    def test_get_bgm_random(self, tmp_path):
        from bookai.bgm import get_bgm_file

        d = tmp_path / "songs"
        d.mkdir()
        (d / "track1.mp3").write_bytes(b"fake")
        result = get_bgm_file(mode="random", songs_dir=str(d))
        assert result is not None
        assert "track1.mp3" in result

    def test_get_bgm_specific(self, tmp_path):
        from bookai.bgm import get_bgm_file

        d = tmp_path / "songs"
        d.mkdir()
        (d / "my_song.mp3").write_bytes(b"fake")
        result = get_bgm_file(mode="specific", filename="my_song.mp3", songs_dir=str(d))
        assert result is not None
        assert "my_song.mp3" in result

    def test_get_bgm_specific_not_found_falls_random(self, tmp_path):
        from bookai.bgm import get_bgm_file

        d = tmp_path / "songs"
        d.mkdir()
        (d / "other.mp3").write_bytes(b"fake")
        result = get_bgm_file(mode="specific", filename="nonexistent.mp3", songs_dir=str(d))
        # Falls back to random
        assert result is not None

    def test_add_bgm_file(self, tmp_path):
        from bookai.bgm import add_bgm_file

        source = tmp_path / "source.mp3"
        source.write_bytes(b"fake mp3")
        dest_dir = tmp_path / "songs"
        dest_dir.mkdir()

        result = add_bgm_file(source, songs_dir=str(dest_dir))
        assert Path(result).exists()

    def test_bgm_config(self):
        from bookai.bgm import BgmConfig

        cfg = BgmConfig(mode="random", volume=0.2)
        assert cfg.enabled is True

        cfg2 = BgmConfig(mode="none")
        assert cfg2.enabled is False


# ===========================================================================
# stock_video tests
# ===========================================================================


class TestStockVideo:
    """Test stock video search and download."""

    def test_material_info(self):
        from bookai.stock_video import MaterialInfo

        m = MaterialInfo(provider="pexels", url="https://example.com/vid.mp4", duration=10.0)
        assert m.provider == "pexels"
        assert m.local_path == ""

    def test_stock_config_defaults(self):
        from bookai.stock_video import StockVideoConfig

        cfg = StockVideoConfig()
        assert cfg.provider == "pexels"
        assert cfg.min_duration == 3

    def test_url_to_filename(self):
        from bookai.stock_video import _url_to_filename

        fname = _url_to_filename("https://example.com/video.mp4")
        assert fname.startswith("stock_")
        assert fname.endswith(".mp4")

    def test_url_to_filename_webm(self):
        from bookai.stock_video import _url_to_filename

        fname = _url_to_filename("https://example.com/video.webm?param=1")
        assert fname.endswith(".webm")

    def test_search_pexels_no_key(self):
        from bookai.stock_video import StockVideoConfig, search_pexels

        cfg = StockVideoConfig(pexels_api_key="")
        result = search_pexels("test", config=cfg)
        assert result == []

    def test_search_pixabay_no_key(self):
        from bookai.stock_video import StockVideoConfig, search_pixabay

        cfg = StockVideoConfig(pixabay_api_key="")
        result = search_pixabay("test", config=cfg)
        assert result == []

    def test_match_materials_to_script_empty(self):
        from bookai.stock_video import match_materials_to_script

        assert match_materials_to_script([], []) == []

    def test_match_materials_to_script(self):
        from bookai.stock_video import MaterialInfo, match_materials_to_script

        materials = [
            MaterialInfo(search_term="reading book"),
            MaterialInfo(search_term="sunrise motivation"),
            MaterialInfo(search_term="coffee morning"),
        ]
        sections = ["Start your morning with coffee", "Read a good book"]

        ordered = match_materials_to_script(materials, sections)
        assert len(ordered) == 3
        # "coffee" should match first section
        assert ordered[0].search_term == "coffee morning"


# ===========================================================================
# video_render tests
# ===========================================================================


class TestVideoRender:
    """Test video rendering config and utilities."""

    def test_video_config_defaults(self):
        from bookai.video_render import VideoConfig

        cfg = VideoConfig()
        assert cfg.width == 1080
        assert cfg.height == 1920
        assert cfg.aspect == "9:16"

    def test_video_config_landscape(self):
        from bookai.video_render import VideoConfig

        cfg = VideoConfig(aspect="16:9")
        assert cfg.width == 1920
        assert cfg.height == 1080

    def test_video_config_square(self):
        from bookai.video_render import VideoConfig

        cfg = VideoConfig(aspect="1:1")
        assert cfg.width == 1080
        assert cfg.height == 1080

    def test_video_config_resolution(self):
        from bookai.video_render import VideoConfig

        cfg = VideoConfig(aspect="9:16")
        assert cfg.resolution == "1080x1920"

    def test_parse_color_named(self):
        from bookai.video_render import _parse_color

        assert _parse_color("black") == (0, 0, 0)
        assert _parse_color("white") == (255, 255, 255)

    def test_parse_color_hex(self):
        from bookai.video_render import _parse_color

        assert _parse_color("#FF0000") == (255, 0, 0)
        assert _parse_color("#00ff00") == (0, 255, 0)

    def test_parse_color_unknown(self):
        from bookai.video_render import _parse_color

        assert _parse_color("unknown") == (0, 0, 0)

    def test_escape_ffmpeg_text(self):
        from bookai.video_render import _escape_ffmpeg_text

        assert "\\:" in _escape_ffmpeg_text("key:value")
        assert "\\'" in _escape_ffmpeg_text("it's")

    def test_wrap_text(self):
        from bookai.video_render import _wrap_text

        result = _wrap_text("Đây là một đoạn text dài cần wrap", 15)
        assert "\\n" in result

    def test_check_moviepy(self):
        from bookai.video_render import check_moviepy

        # Just verify it returns a bool
        assert isinstance(check_moviepy(), bool)

    def test_video_result(self):
        from bookai.video_render import VideoResult

        r = VideoResult(output_path=Path("/tmp/test.mp4"), ok=True)
        assert r.ok
        assert r.engine == "moviepy"

    def test_clip_segment(self):
        from bookai.video_render import ClipSegment

        seg = ClipSegment(file_path="test.mp4", start_time=0, end_time=5)
        assert seg.duration == 5.0


# ===========================================================================
# models tests (new enums)
# ===========================================================================


class TestVideoModels:
    """Test new video-related models."""

    def test_video_aspect(self):
        from bookai.models import VideoAspect

        assert VideoAspect.PORTRAIT.to_resolution() == (1080, 1920)
        assert VideoAspect.LANDSCAPE.to_resolution() == (1920, 1080)
        assert VideoAspect.SQUARE.to_resolution() == (1080, 1080)

    def test_transition_mode(self):
        from bookai.models import TransitionMode

        assert TransitionMode.FADE_IN.value == "fade_in"
        assert TransitionMode.NONE.value == "none"

    def test_bgm_mode(self):
        from bookai.models import BgmMode

        assert BgmMode.RANDOM.value == "random"
        assert BgmMode.NONE.value == "none"

    def test_subtitle_position(self):
        from bookai.models import SubtitlePosition

        assert SubtitlePosition.BOTTOM.value == "bottom"
        assert SubtitlePosition.CUSTOM.value == "custom"

    def test_video_concat_mode(self):
        from bookai.models import VideoConcatMode

        assert VideoConcatMode.MATCH_SCRIPT.value == "match_script"
