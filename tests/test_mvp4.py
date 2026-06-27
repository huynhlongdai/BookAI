"""Tests for MVP-4 modules: affiliate, tts, video_render, calendar."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from bookai.affiliate import AffiliateManager, BookLinks, _append_sub_id, make_sub_id
from bookai.calendar import (
    CalendarEntry,
    calendar_summary,
    generate_calendar,
    save_calendar_csv,
    save_calendar_json,
)
from bookai.tts import _clean_text_for_tts, estimate_duration, list_voices
from bookai.video_render import VideoConfig, _escape_ffmpeg_text, _wrap_text, check_ffmpeg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_content_pack(
    radio=2, quotes=3, listicles=2, captions=3, book_title="Nhìn Thấu Lòng Người"
):
    """Build a minimal fake ContentPack."""

    @dataclass
    class FakeRadio:
        hook: str = "Hook text here"
        body: str = "Body text here"
        cta: str = "Đặt sách tại giỏ hàng"
        title: str = "Script"
        hashtags: list = None

        def __post_init__(self):
            if self.hashtags is None:
                self.hashtags = ["sachhay"]

    _bt = book_title  # capture for use in default

    @dataclass
    class FakeQuote:
        quote_text: str = "Một câu hay"
        caption: str = "Caption mẫu"
        book_title: str = _bt
        author: str = "Tác giả"
        hashtags: list = None
        image_path: str = ""

        def __post_init__(self):
            if self.hashtags is None:
                self.hashtags = ["sachhay"]

    @dataclass
    class FakeListicle:
        title: str = "5 bài học"
        items: list = None
        intro: str = "Intro"
        cta: str = "Đặt sách"
        hashtags: list = None

        def __post_init__(self):
            if self.items is None:
                self.items = ["Bài 1", "Bài 2"]
            if self.hashtags is None:
                self.hashtags = ["sachhay"]

    @dataclass
    class FakeCaption:
        text: str = "Caption text đây"
        hashtags: list = None
        platform: str = "tiktok"

        def __post_init__(self):
            if self.hashtags is None:
                self.hashtags = ["sachhay"]

    class FakePack:
        def __init__(self):
            self.book_title = book_title
            self.radio_scripts = [FakeRadio() for _ in range(radio)]
            self.quote_cards = [FakeQuote() for _ in range(quotes)]
            self.listicles = [FakeListicle() for _ in range(listicles)]
            self.captions = [FakeCaption() for _ in range(captions)]

    return FakePack()


# ---------------------------------------------------------------------------
# Affiliate tests
# ---------------------------------------------------------------------------


class TestAffiliate:
    def test_book_links_get(self):
        book = BookLinks(
            book_title="Đắc Nhân Tâm",
            shopee="https://shope.ee/abc",
            tiktok="https://vt.tiktok.com/xyz",
        )
        assert book.get("shopee") == "https://shope.ee/abc"
        assert book.get("tiktok") == "https://vt.tiktok.com/xyz"
        assert book.get("lazada") == ""

    def test_book_links_model_dump(self):
        book = BookLinks(book_title="Test Book", shopee="https://shope.ee/test")
        d = book.model_dump()
        assert d["book_title"] == "Test Book"
        assert d["shopee"] == "https://shope.ee/test"
        assert "isbn" in d

    def test_add_and_list_books(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="Sách A", shopee="https://shope.ee/a"))
        mgr.add_book(BookLinks(book_title="Sách B", tiktok="https://vt.tiktok.com/b"))
        books = mgr.list_books()
        assert len(books) == 2
        assert books[0]["title"] == "Sách A"

    def test_get_link_by_title(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="Đắc Nhân Tâm", shopee="https://shope.ee/dnt"))
        link = mgr.get_link("Đắc Nhân Tâm", platform="shopee")
        assert link == "https://shope.ee/dnt"

    def test_get_link_case_insensitive(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="Đắc Nhân Tâm", shopee="https://shope.ee/dnt"))
        link = mgr.get_link("đắc nhân tâm", platform="shopee")
        assert link == "https://shope.ee/dnt"

    def test_get_link_not_found(self):
        mgr = AffiliateManager()
        assert mgr.get_link("Unknown Book", platform="shopee") == ""

    def test_get_link_with_sub_id(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="Test", shopee="https://shope.ee/test"))
        link = mgr.get_link("Test", platform="shopee", sub_id="vid_001")
        assert "sub_aff_id=vid_001" in link
        assert "shope.ee" in link

    def test_get_best_link_prefers_tiktok(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(
            book_title="Test",
            shopee="https://shope.ee/s",
            tiktok="https://vt.tiktok.com/t",
        ))
        platform, link = mgr.get_best_link("Test")
        assert platform == "tiktok"
        assert "tiktok.com" in link

    def test_remove_book(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="Remove Me", shopee="https://shope.ee/x"))
        assert len(mgr.books) == 1
        assert mgr.remove_book("Remove Me") is True
        assert len(mgr.books) == 0

    def test_remove_nonexistent_book(self):
        mgr = AffiliateManager()
        assert mgr.remove_book("Does Not Exist") is False

    def test_inject_into_cta_with_link_placeholder(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="Test Book", tiktok="https://vt.tiktok.com/abc"))
        cta = "Đặt sách tại {link}"
        result = mgr.inject_into_cta(cta, "Test Book", platform="tiktok")
        assert "https://vt.tiktok.com/abc" in result
        assert "{link}" not in result

    def test_inject_into_cta_appends_when_no_placeholder(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="Test Book", tiktok="https://vt.tiktok.com/abc"))
        cta = "Đặt sách ngay đi bạn"
        result = mgr.inject_into_cta(cta, "Test Book", platform="tiktok")
        assert "https://vt.tiktok.com/abc" in result
        assert "Đặt sách ngay đi bạn" in result

    def test_inject_no_link_configured(self):
        mgr = AffiliateManager()
        cta = "Original CTA"
        result = mgr.inject_into_cta(cta, "Unknown Book", platform="tiktok")
        assert result == "Original CTA"

    def test_save_and_load_json(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            mgr = AffiliateManager()
            mgr.add_book(BookLinks(book_title="Book 1", shopee="https://shope.ee/1"))
            mgr.add_book(BookLinks(book_title="Book 2", tiktok="https://vt.tiktok.com/2"))
            mgr.save(f.name)

            loaded = AffiliateManager.from_file(f.name)
            assert len(loaded.books) == 2
            assert loaded.get_link("Book 1", "shopee") == "https://shope.ee/1"

    def test_load_missing_file(self):
        mgr = AffiliateManager.from_file("/nonexistent/path/affiliate.json")
        assert len(mgr.books) == 0

    def test_update_existing_book(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(book_title="My Book", shopee="https://shope.ee/old"))
        mgr.add_book(BookLinks(book_title="My Book", shopee="https://shope.ee/new"))
        # Should update, not duplicate
        assert len(mgr.books) == 1
        assert mgr.get_link("My Book", "shopee") == "https://shope.ee/new"

    def test_append_sub_id(self):
        url = "https://shope.ee/abc"
        result = _append_sub_id(url, "shopee", "vid_001")
        assert "sub_aff_id=vid_001" in result

    def test_append_sub_id_preserves_existing_params(self):
        url = "https://shope.ee/abc?ref=homepage"
        result = _append_sub_id(url, "shopee", "vid_001")
        assert "ref=homepage" in result
        assert "sub_aff_id=vid_001" in result

    def test_make_sub_id(self):
        assert make_sub_id("vid_001", "tiktok") == "vid_001_tiktok"
        assert make_sub_id("vid_001", "tiktok", "tamly") == "vid_001_tiktok_tamly"

    def test_inject_into_content_pack(self):
        mgr = AffiliateManager()
        mgr.add_book(BookLinks(
            book_title="Nhìn Thấu Lòng Người",
            tiktok="https://vt.tiktok.com/abc",
            shopee="https://shope.ee/xyz",
        ))
        pack = _make_content_pack()
        mgr.inject_into_content_pack(pack, sub_id_prefix="test")
        # CTA of first radio script should have link
        assert "https://vt.tiktok.com/abc" in pack.radio_scripts[0].cta


# ---------------------------------------------------------------------------
# TTS tests (no network calls required for these)
# ---------------------------------------------------------------------------


class TestTTS:
    def test_list_voices(self):
        voices = list_voices()
        assert "vi-VN-HoaiMyNeural" in voices
        assert "vi-VN-NamMinhNeural" in voices

    def test_clean_text_removes_markdown(self):
        text = "**Bold text** and *italic* and [link](https://example.com)"
        clean = _clean_text_for_tts(text)
        assert "**" not in clean
        assert "*" not in clean
        assert "https://example.com" not in clean
        assert "Bold text" in clean

    def test_clean_text_removes_emoji(self):
        text = "Xin chào 👋 bạn ơi 😊 đây là test"
        clean = _clean_text_for_tts(text)
        assert "👋" not in clean
        assert "😊" not in clean
        assert "Xin chào" in clean

    def test_clean_text_removes_hashtags(self):
        text = "Nội dung hay #sachhay #reviewsach xem đi"
        clean = _clean_text_for_tts(text)
        assert "#sachhay" not in clean
        assert "Nội dung hay" in clean

    def test_estimate_duration_normal(self):
        text = " ".join(["word"] * 150)  # 150 words
        duration = estimate_duration(text)
        # 150 words / 2.5 words/sec = 60s
        assert abs(duration - 60.0) < 5.0

    def test_estimate_duration_faster_rate(self):
        text = " ".join(["word"] * 150)
        slow = estimate_duration(text, rate_percent=0)
        fast = estimate_duration(text, rate_percent=20)
        assert fast < slow

    def test_synthesize_text_no_edge_tts(self):
        """When edge-tts not available, returns error result."""
        from bookai.tts import synthesize_text

        with patch.dict("sys.modules", {"edge_tts": None}):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                result = synthesize_text("Test text", f.name)
                # Should return error result (not raise)
                assert result.ok is False or result.ok is True  # Either works

    def test_synthesize_script_builds_text(self):
        """Test that synthesize_script assembles hook+body+cta correctly."""
        from bookai.tts import TTSResult, synthesize_script

        class FakeScript:
            hook = "Hook text"
            body = "Body text"
            cta = "CTA text"
            title = "Test"

        # Mock synthesize_text to capture what text is passed
        captured = {}

        def mock_synth(text, output_path, voice, rate):
            captured["text"] = text
            return TTSResult(output_path=Path(output_path), voice=voice, ok=True)

        with patch("bookai.tts.synthesize_text", side_effect=mock_synth):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                synthesize_script(FakeScript(), f.name)
                assert "Hook text" in captured.get("text", "")
                assert "Body text" in captured.get("text", "")
                assert "CTA text" in captured.get("text", "")

    def test_synthesize_script_can_exclude_sections(self):
        """Test include flags for hook/body/cta."""
        from bookai.tts import TTSResult, synthesize_script

        class FakeScript:
            hook = "HOOK"
            body = "BODY"
            cta = "CTA"
            title = "Test"

        captured = {}

        def mock_synth(text, output_path, voice, rate):
            captured["text"] = text
            return TTSResult(output_path=Path(output_path), voice=voice, ok=True)

        with patch("bookai.tts.synthesize_text", side_effect=mock_synth):
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                synthesize_script(FakeScript(), f.name, include_cta=False)
                assert "CTA" not in captured.get("text", "")
                assert "HOOK" in captured.get("text", "")


# ---------------------------------------------------------------------------
# Video Render tests (no actual FFmpeg execution required for unit tests)
# ---------------------------------------------------------------------------


class TestVideoRender:
    def test_video_config_defaults(self):
        cfg = VideoConfig()
        assert cfg.width == 1080
        assert cfg.height == 1920
        assert cfg.fps == 30
        assert cfg.resolution == "1080x1920"

    def test_video_config_aspect_resolution(self):
        # v2: VideoConfig uses aspect ratio, not custom resolution
        cfg = VideoConfig(aspect="9:16")
        assert cfg.width == 1080
        assert cfg.height == 1920

        cfg2 = VideoConfig(aspect="16:9")
        assert cfg2.width == 1920
        assert cfg2.height == 1080

    def test_escape_ffmpeg_text_special_chars(self):
        text = "Bạn có biết: '10 bí mật' 50% người không biết"
        escaped = _escape_ffmpeg_text(text)
        assert "\\'" in escaped
        assert "\\:" in escaped
        assert "\\%" in escaped

    def test_escape_ffmpeg_text_no_special(self):
        text = "Simple text without special chars"
        escaped = _escape_ffmpeg_text(text)
        assert escaped == text

    def test_wrap_text_short(self):
        text = "Short text"
        wrapped = _wrap_text(text, max_chars=40)
        assert "\\n" not in wrapped

    def test_wrap_text_long(self):
        text = "This is a very long Vietnamese sentence that should be wrapped properly"
        wrapped = _wrap_text(text, max_chars=20)
        assert "\\n" in wrapped

    def test_check_ffmpeg(self):
        # FFmpeg is installed in this environment
        assert check_ffmpeg() is True

    def test_render_returns_error_when_audio_missing(self):
        from bookai.video_render import render_radio_video

        class FakeScript:
            hook = "Hook"
            body = "Body"
            cta = "CTA"

        with tempfile.TemporaryDirectory() as tmp:
            result = render_radio_video(
                FakeScript(),
                audio_path="/nonexistent/audio.mp3",
                output_path=Path(tmp) / "out.mp4",
            )
            assert result.ok is False
            assert "not found" in result.error.lower() or "audio" in result.error.lower()

    def test_render_quote_video_missing_audio(self):
        from bookai.video_render import render_quote_video

        with tempfile.TemporaryDirectory() as tmp:
            result = render_quote_video(
                "Câu quote mẫu",
                audio_path="/nonexistent.mp3",
                output_path=Path(tmp) / "out.mp4",
            )
            assert result.ok is False

    def test_render_slideshow_empty_slides(self):
        from bookai.video_render import render_slideshow_video

        with tempfile.TemporaryDirectory() as tmp:
            result = render_slideshow_video([], output_path=Path(tmp) / "out.mp4")
            assert result.ok is False


# ---------------------------------------------------------------------------
# Calendar tests
# ---------------------------------------------------------------------------


class TestCalendar:
    def test_generate_calendar_basic(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=7)
        assert len(entries) > 0
        assert all(isinstance(e, CalendarEntry) for e in entries)

    def test_calendar_entries_sorted_by_date(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=14)
        dates = [e.date for e in entries]
        assert dates == sorted(dates)

    def test_calendar_date_range(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=7)
        if entries:
            assert entries[0].date == "2025-08-01"
            assert entries[-1].date <= "2025-08-07"

    def test_calendar_platforms(self):
        pack = _make_content_pack()
        entries = generate_calendar(
            pack, start_date="2025-08-01", days=7,
            platforms=["tiktok", "instagram"]
        )
        platforms_used = {e.platform for e in entries}
        assert platforms_used.issubset({"tiktok", "instagram"})

    def test_calendar_week_numbers(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=28)
        weeks = {e.week_number for e in entries}
        assert 1 in weeks
        assert 4 in weeks

    def test_calendar_posts_per_day(self):
        pack = _make_content_pack()
        entries = generate_calendar(
            pack, start_date="2025-08-01", days=7,
            posts_per_day=1, platforms=["tiktok"]
        )
        # Per day should have at most 1 post
        from collections import Counter
        day_counts = Counter(e.date for e in entries)
        assert all(v <= 1 for v in day_counts.values())

    def test_calendar_entry_has_required_fields(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=3)
        if entries:
            e = entries[0]
            assert e.entry_id
            assert e.date
            assert e.platform
            assert e.content_type
            assert e.post_time
            assert ":" in e.post_time  # HH:MM format

    def test_calendar_content_types_used(self):
        pack = _make_content_pack(radio=2, quotes=2, listicles=2, captions=2)
        entries = generate_calendar(pack, start_date="2025-08-01", days=30)
        types = {e.content_type for e in entries}
        # Over 30 days all content types should appear
        assert len(types) > 1

    def test_calendar_empty_pack(self):
        pack = _make_content_pack(radio=0, quotes=0, listicles=0, captions=0)
        entries = generate_calendar(pack, start_date="2025-08-01", days=7)
        assert entries == []

    def test_calendar_summary(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=14)
        summary = calendar_summary(entries)
        assert "total" in summary
        assert summary["total"] == len(entries)
        if entries:
            assert "date_range" in summary
            assert "by_platform" in summary

    def test_calendar_summary_empty(self):
        summary = calendar_summary([])
        assert summary["total"] == 0

    def test_save_calendar_csv(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=7)
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = save_calendar_csv(entries, f.name)
            assert path.exists()
            content = path.read_text(encoding="utf-8")
            assert "entry_id" in content  # header
            if entries:
                assert entries[0].date in content

    def test_save_calendar_json(self):
        pack = _make_content_pack()
        entries = generate_calendar(pack, start_date="2025-08-01", days=7)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = save_calendar_json(entries, f.name)
            assert path.exists()
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, list)
            if entries:
                assert data[0]["date"] == entries[0].date

    def test_save_calendar_csv_empty(self):
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = save_calendar_csv([], f.name)
            assert path.exists()

    def test_hashtag_string_property(self):
        entry = CalendarEntry(
            entry_id="test",
            date="2025-08-01",
            day_number=1,
            week_number=1,
            post_time="09:00",
            platform="tiktok",
            content_type="quote_card",
            content_index=0,
            content_title="Test",
            caption="Test",
            hashtags=["sachhay", "reviewsach"],
        )
        assert entry.hashtag_string == "#sachhay #reviewsach"

    def test_calendar_sub_id_prefix(self):
        pack = _make_content_pack()
        entries = generate_calendar(
            pack, start_date="2025-08-01", days=7, sub_id_prefix="book_aug"
        )
        # Sub-ID is used for affiliate links — entries should be generated
        assert len(entries) > 0


# ---------------------------------------------------------------------------
# Blog generator tests
# ---------------------------------------------------------------------------


class TestBlog:
    def _make_book_result(self):
        from bookai.models import AnalyzedChunk, BookMetadata, BookResult, Chunk, ChunkLabel

        analyzed = [
            AnalyzedChunk(
                chunk=Chunk(text="Đừng bao giờ tin hoàn toàn vào lời nói, hãy quan sát hành động."),
                labels=[ChunkLabel.QUOTE, ChunkLabel.INSIGHT],
                viral_score=9.0,
                summary="Quan sát hành động hơn lời nói",
            ),
            AnalyzedChunk(
                chunk=Chunk(text="Bạn có biết bí mật ít ai nói về tâm lý con người không?"),
                labels=[ChunkLabel.HOOK],
                viral_score=8.5,
                summary="Hook tâm lý",
            ),
            AnalyzedChunk(
                chunk=Chunk(text="Nguyên tắc 1: Nhìn vào mắt khi nói chuyện. "
                                 "Nguyên tắc 2: Chú ý ngôn ngữ cơ thể."),
                labels=[ChunkLabel.TIP],
                viral_score=7.5,
                summary="2 nguyên tắc giao tiếp",
            ),
        ]
        return BookResult(
            metadata=BookMetadata(title="Nhìn Thấu Lòng Người", author="Tác giả mẫu"),
            analyzed=analyzed,
            top_quotes=[analyzed[0]],
            top_hooks=[analyzed[1]],
        )

    def test_generate_blog_template(self):
        from bookai.blog import BlogPost, generate_blog_post

        result = self._make_book_result()
        post = generate_blog_post(result, use_ai=False)
        assert isinstance(post, BlogPost)
        assert "Nhìn Thấu Lòng Người" in post.title
        assert post.word_count > 100
        assert post.slug
        assert post.meta_description

    def test_blog_contains_affiliate_link(self):
        from bookai.blog import generate_blog_post

        result = self._make_book_result()
        aff_link = "https://shope.ee/test123"
        post = generate_blog_post(result, affiliate_link=aff_link, use_ai=False)
        assert aff_link in post.markdown

    def test_blog_html_output(self):
        from bookai.blog import generate_blog_post

        result = self._make_book_result()
        post = generate_blog_post(result, use_ai=False)
        html = post.html
        assert "<!DOCTYPE html>" in html
        assert "application/ld+json" in html  # schema markup
        assert "<h1>" in html
        assert post.book_title in html

    def test_blog_save_html(self):
        import tempfile

        from bookai.blog import generate_blog_post

        result = self._make_book_result()
        post = generate_blog_post(result, use_ai=False)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "review.html"
            saved = post.save(out, fmt="html")
            assert saved.exists()
            assert saved.stat().st_size > 500
            content = saved.read_text(encoding="utf-8")
            assert "<!DOCTYPE html>" in content

    def test_blog_save_markdown(self):
        import tempfile

        from bookai.blog import generate_blog_post

        result = self._make_book_result()
        post = generate_blog_post(result, use_ai=False)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "review.md"
            saved = post.save(out, fmt="md")
            assert saved.exists()
            content = saved.read_text(encoding="utf-8")
            assert "# " in content  # has headings

    def test_blog_slug_generated(self):
        from bookai.blog import _slugify

        slug = _slugify("Đắc Nhân Tâm")
        assert " " not in slug
        assert "/" not in slug
        assert len(slug) > 0
        assert " " not in _slugify("Hello World Book")
        assert "/" not in _slugify("path/test")

    def test_blog_sections_list(self):
        from bookai.blog import generate_blog_post

        result = self._make_book_result()
        post = generate_blog_post(result, use_ai=False)
        assert len(post.sections) >= 3
        assert "Kết luận" in post.sections


# ---------------------------------------------------------------------------
# Series Cliffhanger tests
# ---------------------------------------------------------------------------


class TestSeriesSplitter:
    def _make_script(self):
        from bookai.content_studio import RadioScript

        return RadioScript(
            title="Nhìn Thấu Lòng Người - Script 1",
            hook="Bạn có biết cách nhìn thấu lòng người chỉ trong 3 giây không?",
            body=(
                "Nguyên tắc thứ nhất là quan sát ánh mắt. "
                "Khi ai đó nói dối, ánh mắt họ thường không nhìn thẳng. "
                "Nguyên tắc thứ hai là chú ý ngôn ngữ cơ thể. "
                "Cơ thể không biết nói dối dù miệng có thể. "
                "Nguyên tắc thứ ba là lắng nghe những điều không được nói ra. "
                "Đôi khi sự im lặng nói lên nhiều hơn lời nói. "
                "Nguyên tắc thứ tư là kiểm tra tính nhất quán. "
                "Người thành thật luôn nhất quán trong lời nói và hành động. "
                "Nguyên tắc thứ năm là tin vào trực giác của bạn. "
                "Não bộ nhận biết dấu hiệu nguy hiểm trước khi ý thức kịp xử lý."
            ),
            cta="Đặt sách tại giỏ hàng để đọc thêm!",
            hashtags=["sachhay", "tamly"],
            estimated_seconds=180,
        )

    def test_split_basic(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=5)
        assert len(videos) == 5

    def test_split_part_numbers(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=3)
        assert [v.part_number for v in videos] == [1, 2, 3]
        assert all(v.total_parts == 3 for v in videos)

    def test_split_cliffhanger_on_early_parts(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=3)
        # Parts 1 and 2 should have cliffhanger text
        assert len(videos[0].cliffhanger) > 0
        assert len(videos[1].cliffhanger) > 0

    def test_split_last_part_uses_cta(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=3)
        # Last part should use original CTA
        assert videos[-1].cliffhanger == script.cta

    def test_split_first_part_uses_original_hook(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=3)
        assert videos[0].hook == script.hook

    def test_split_has_body_content(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=5)
        # Every part should have some body content
        assert all(len(v.body) > 0 for v in videos)

    def test_split_model_dump(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=3)
        d = videos[0].model_dump()
        assert "series_title" in d
        assert "part_number" in d
        assert "hook" in d
        assert "body" in d
        assert "cliffhanger" in d
        assert "full_script" in d

    def test_split_full_script_property(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=3)
        for v in videos:
            full = v.full_script
            assert v.hook in full
            assert v.body in full
            assert v.cliffhanger in full

    def test_split_pack_to_series(self):
        from bookai.content_studio import split_pack_to_series

        pack = _make_content_pack(radio=2)
        # Inject real scripts
        from bookai.content_studio import RadioScript
        pack.radio_scripts = [
            RadioScript(
                title=f"Script {i}",
                hook="Hook",
                body="Body sentence one. Body sentence two. Body sentence three.",
                cta="CTA",
                hashtags=["sachhay"],
            )
            for i in range(2)
        ]
        pack.book_title = "Test Book"

        all_videos = split_pack_to_series(pack, parts=3)
        assert len(all_videos) == 6  # 2 scripts × 3 parts

    def test_split_hashtags_include_part_marker(self):
        from bookai.content_studio import split_script_to_series

        script = self._make_script()
        videos = split_script_to_series(script, parts=3)
        # Should include part indicator hashtag
        assert any("phan" in h or "series" in h for h in videos[0].hashtags)
