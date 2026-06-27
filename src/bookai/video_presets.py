"""Video presets for BookAI — ready-made video configurations.

Provides 6 preset configurations for common book content video formats:
    - booktok_review    (30-60s TikTok/Reels 9:16)
    - youtube_review    (3-5min YouTube 16:9)
    - book_trailer      (30-60s cinematic trailer)
    - quote_compilation (15-30s quote highlight reel)
    - recommendation_list (60-90s top books list)
    - book_promo        (15-30s ad/promo)

Each preset defines: resolution, duration, sections, subtitle template,
hook/title/outro style, music mood, and content structure.

Usage::

    from bookai.video_presets import get_preset, list_presets, apply_preset

    preset = get_preset("booktok_review")
    config = apply_preset(preset, script_text="...", book_title="...")
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VideoPreset:
    """Complete video configuration preset."""

    name: str
    display_name: str
    description: str

    # Resolution & format
    width: int = 1080
    height: int = 1920
    fps: int = 30
    aspect_ratio: str = "9:16"  # 9:16, 16:9, 1:1, 4:5

    # Duration constraints
    min_duration: float = 15.0
    max_duration: float = 60.0
    target_duration: float = 30.0

    # Content structure
    sections: list[str] = field(default_factory=lambda: [
        "hook", "title_card", "content", "outro",
    ])
    section_durations: dict[str, float] = field(default_factory=dict)

    # Video sections style
    hook_style: str = "bold_question"
    title_card_style: str = "minimalist"
    outro_style: str = "subscribe_cta"

    # Subtitle & text
    subtitle_template: str = "capcut_white_box"
    text_animation: str = "fade_in"
    font_size_ratio: float = 1.0  # Multiplier for base font size

    # Audio
    tts_rate: str = "+0%"
    bgm_mood: str = "inspiring"  # inspiring, calm, dramatic, upbeat, emotional
    bgm_volume: float = 0.15  # 0.0-1.0

    # Material preferences
    material_mode: str = "stock"  # stock, local, mixed
    stock_provider: str = "pixabay"
    clips_per_section: int = 2

    # Color scheme
    primary_color: str = "#FFFFFF"
    secondary_color: str = "#FFD700"
    background_color: str = "#000000"
    accent_color: str = "#00D4FF"

    # Platform-specific
    platform: str = "tiktok"  # tiktok, youtube, instagram, facebook
    watermark: bool = False
    end_screen: bool = False

    # Script generation hints
    script_style: str = "review"  # review, storytelling, listicle, educational
    max_words: int = 200
    language: str = "vi"
    tone: str = "engaging"  # engaging, professional, casual, dramatic


# ---------------------------------------------------------------------------
# 6 Video Presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, VideoPreset] = {
    "booktok_review": VideoPreset(
        name="booktok_review",
        display_name="📱 BookTok Review",
        description="Video review sách 30-60s cho TikTok/Reels — hook mạnh, subtitle nổi bật",
        width=1080, height=1920, fps=30,
        aspect_ratio="9:16",
        min_duration=25.0, max_duration=60.0, target_duration=35.0,
        sections=["hook", "title_card", "content", "rating", "outro"],
        section_durations={
            "hook": 2.5, "title_card": 3.0, "content": 20.0,
            "rating": 4.0, "outro": 3.0,
        },
        hook_style="bold_question",
        title_card_style="book_cover",
        outro_style="subscribe_cta",
        subtitle_template="word_by_word_highlight",
        text_animation="pop_bounce",
        tts_rate="+5%",
        bgm_mood="upbeat",
        bgm_volume=0.12,
        material_mode="stock",
        clips_per_section=2,
        primary_color="#FFFFFF",
        secondary_color="#FFD700",
        accent_color="#FF6B6B",
        platform="tiktok",
        script_style="review",
        max_words=180,
        tone="engaging",
    ),

    "youtube_review": VideoPreset(
        name="youtube_review",
        display_name="▶️ YouTube Review",
        description="Video review sách 3-5 phút cho YouTube — chuyên sâu, 16:9",
        width=1920, height=1080, fps=30,
        aspect_ratio="16:9",
        min_duration=120.0, max_duration=300.0, target_duration=180.0,
        sections=["intro", "hook", "title_card", "content", "key_points",
                  "rating", "recommendation", "outro"],
        section_durations={
            "intro": 5.0, "hook": 5.0, "title_card": 5.0,
            "content": 90.0, "key_points": 40.0,
            "rating": 15.0, "recommendation": 10.0, "outro": 8.0,
        },
        hook_style="shocking_fact",
        title_card_style="split_screen",
        outro_style="next_book",
        subtitle_template="the_classic",
        text_animation="slide_up",
        tts_rate="+0%",
        bgm_mood="inspiring",
        bgm_volume=0.10,
        material_mode="mixed",
        clips_per_section=3,
        primary_color="#FFFFFF",
        secondary_color="#1DB954",
        accent_color="#4ECDC4",
        platform="youtube",
        end_screen=True,
        script_style="storytelling",
        max_words=800,
        tone="professional",
    ),

    "book_trailer": VideoPreset(
        name="book_trailer",
        display_name="🎬 Book Trailer",
        description="Trailer sách 30-60s — cinematic, dramatic, gây tò mò",
        width=1920, height=1080, fps=30,
        aspect_ratio="16:9",
        min_duration=25.0, max_duration=60.0, target_duration=40.0,
        sections=["hook", "mystery_build", "climax_tease", "title_reveal", "cta"],
        section_durations={
            "hook": 3.0, "mystery_build": 15.0, "climax_tease": 10.0,
            "title_reveal": 5.0, "cta": 4.0,
        },
        hook_style="mystery",
        title_card_style="gradient_card",
        outro_style="subscribe_cta",
        subtitle_template="neon_glow",
        text_animation="blur_reveal",
        tts_rate="-5%",
        bgm_mood="dramatic",
        bgm_volume=0.20,
        material_mode="stock",
        clips_per_section=2,
        primary_color="#FFFFFF",
        secondary_color="#FF4444",
        accent_color="#8B5CF6",
        platform="youtube",
        script_style="storytelling",
        max_words=150,
        tone="dramatic",
    ),

    "quote_compilation": VideoPreset(
        name="quote_compilation",
        display_name="💎 Quote Compilation",
        description="Tổng hợp trích dẫn hay 15-30s — aesthetic, chia sẻ được",
        width=1080, height=1920, fps=30,
        aspect_ratio="9:16",
        min_duration=12.0, max_duration=30.0, target_duration=20.0,
        sections=["title_card", "quote_1", "quote_2", "quote_3", "outro"],
        section_durations={
            "title_card": 3.0, "quote_1": 5.0, "quote_2": 5.0,
            "quote_3": 5.0, "outro": 3.0,
        },
        hook_style="quote_reveal",
        title_card_style="minimalist",
        outro_style="subscribe_cta",
        subtitle_template="bold_impact",
        text_animation="typewriter",
        font_size_ratio=1.3,
        tts_rate="-10%",
        bgm_mood="calm",
        bgm_volume=0.18,
        material_mode="stock",
        clips_per_section=1,
        primary_color="#FFFFFF",
        secondary_color="#E8D5B7",
        accent_color="#D4AF37",
        platform="instagram",
        script_style="review",
        max_words=80,
        tone="engaging",
    ),

    "recommendation_list": VideoPreset(
        name="recommendation_list",
        display_name="📚 Recommendation List",
        description="Top sách nên đọc 60-90s — listicle format, nhiều sách",
        width=1080, height=1920, fps=30,
        aspect_ratio="9:16",
        min_duration=45.0, max_duration=120.0, target_duration=75.0,
        sections=["hook", "title_card", "item_1", "item_2", "item_3",
                  "item_4", "item_5", "outro"],
        section_durations={
            "hook": 3.0, "title_card": 3.0,
            "item_1": 12.0, "item_2": 12.0, "item_3": 12.0,
            "item_4": 12.0, "item_5": 12.0,
            "outro": 4.0,
        },
        hook_style="shocking_fact",
        title_card_style="gradient_card",
        outro_style="subscribe_cta",
        subtitle_template="capcut_white_box",
        text_animation="slide_left",
        tts_rate="+5%",
        bgm_mood="upbeat",
        bgm_volume=0.12,
        material_mode="stock",
        clips_per_section=2,
        primary_color="#FFFFFF",
        secondary_color="#FF6B6B",
        accent_color="#4ECDC4",
        platform="tiktok",
        script_style="listicle",
        max_words=400,
        tone="engaging",
    ),

    "book_promo": VideoPreset(
        name="book_promo",
        display_name="📢 Book Promo",
        description="Quảng cáo sách 15-30s — CTA mạnh, affiliate link",
        width=1080, height=1920, fps=30,
        aspect_ratio="9:16",
        min_duration=12.0, max_duration=30.0, target_duration=20.0,
        sections=["hook", "value_prop", "social_proof", "cta"],
        section_durations={
            "hook": 3.0, "value_prop": 8.0,
            "social_proof": 4.0, "cta": 5.0,
        },
        hook_style="book_rating",
        title_card_style="book_cover",
        outro_style="subscribe_cta",
        subtitle_template="modern_pill",
        text_animation="zoom_in",
        font_size_ratio=1.2,
        tts_rate="+10%",
        bgm_mood="upbeat",
        bgm_volume=0.15,
        material_mode="stock",
        clips_per_section=1,
        primary_color="#FFFFFF",
        secondary_color="#FF4444",
        accent_color="#FFD700",
        platform="tiktok",
        watermark=True,
        script_style="review",
        max_words=80,
        tone="engaging",
    ),
}


# ---------------------------------------------------------------------------
# API Functions
# ---------------------------------------------------------------------------


def list_presets() -> list[dict]:
    """List all available video presets with metadata."""
    result = []
    for name, preset in PRESETS.items():
        result.append({
            "name": preset.name,
            "display_name": preset.display_name,
            "description": preset.description,
            "platform": preset.platform,
            "aspect_ratio": preset.aspect_ratio,
            "target_duration": preset.target_duration,
            "sections": preset.sections,
            "subtitle_template": preset.subtitle_template,
        })
    return result


def get_preset(name: str) -> VideoPreset | None:
    """Get a video preset by name."""
    return PRESETS.get(name)


def apply_preset(
    preset: VideoPreset,
    book_title: str = "",
    script_text: str = "",
    custom_overrides: dict | None = None,
) -> dict:
    """Apply a preset to generate a complete render configuration.

    Args:
        preset: The VideoPreset to apply.
        book_title: Book title for sections.
        script_text: Script text for content.
        custom_overrides: Optional overrides for any preset field.

    Returns:
        Complete render config dict ready for video_pipeline.
    """
    config = {
        # Video
        "width": preset.width,
        "height": preset.height,
        "fps": preset.fps,
        "aspect_ratio": preset.aspect_ratio,

        # Content
        "book_title": book_title,
        "script_text": script_text,
        "sections": list(preset.sections),
        "section_durations": dict(preset.section_durations),

        # Styles
        "hook_style": preset.hook_style,
        "title_card_style": preset.title_card_style,
        "outro_style": preset.outro_style,
        "subtitle_template": preset.subtitle_template,
        "text_animation": preset.text_animation,
        "font_size_ratio": preset.font_size_ratio,

        # Audio
        "tts_rate": preset.tts_rate,
        "bgm_mood": preset.bgm_mood,
        "bgm_volume": preset.bgm_volume,

        # Materials
        "material_mode": preset.material_mode,
        "stock_provider": preset.stock_provider,
        "clips_per_section": preset.clips_per_section,

        # Colors
        "primary_color": preset.primary_color,
        "secondary_color": preset.secondary_color,
        "background_color": preset.background_color,
        "accent_color": preset.accent_color,

        # Platform
        "platform": preset.platform,
        "watermark": preset.watermark,
        "end_screen": preset.end_screen,

        # Script hints
        "script_style": preset.script_style,
        "max_words": preset.max_words,
        "language": preset.language,
        "tone": preset.tone,

        # Duration
        "min_duration": preset.min_duration,
        "max_duration": preset.max_duration,
        "target_duration": preset.target_duration,
    }

    # Apply custom overrides
    if custom_overrides:
        config.update(custom_overrides)

    return config


def get_preset_for_platform(platform: str) -> list[VideoPreset]:
    """Get all presets for a specific platform."""
    return [p for p in PRESETS.values() if p.platform == platform]


def get_preset_by_duration(max_seconds: float) -> list[VideoPreset]:
    """Get presets that fit within a duration constraint."""
    return [p for p in PRESETS.values() if p.target_duration <= max_seconds]


def get_script_prompt(preset: VideoPreset, book_title: str, book_summary: str = "") -> str:
    """Generate a script-writing prompt optimized for this preset.

    Args:
        preset: The video preset.
        book_title: Book title.
        book_summary: Optional book summary/content.

    Returns:
        LLM prompt string for generating an appropriate script.
    """
    style_guides = {
        "review": (
            f"Viết script review sách \"{book_title}\" dạng ngắn gọn, "
            f"tối đa {preset.max_words} từ. "
            "Mở đầu bằng câu hỏi hoặc nhận định gây tò mò. "
            "Nêu 2-3 điểm nổi bật. Kết bằng CTA kêu gọi đọc."
        ),
        "storytelling": (
            f"Viết script kể chuyện về sách \"{book_title}\", "
            f"tối đa {preset.max_words} từ. "
            "Bắt đầu bằng một tình huống cụ thể, kể câu chuyện cuốn hút, "
            "lồng ghép bài học từ sách. Kết bằng insight sâu sắc."
        ),
        "listicle": (
            f"Viết script dạng listicle về sách \"{book_title}\", "
            f"tối đa {preset.max_words} từ. "
            "Format: X bí mật/bài học/lý do. "
            "Mỗi item ngắn gọn, dễ nhớ. Hook mạnh ở đầu."
        ),
        "educational": (
            f"Viết script giáo dục về nội dung sách \"{book_title}\", "
            f"tối đa {preset.max_words} từ. "
            "Giải thích khái niệm rõ ràng, dùng ví dụ thực tế. "
            "Tone chuyên nghiệp nhưng dễ hiểu."
        ),
    }

    base_prompt = style_guides.get(preset.script_style, style_guides["review"])

    # Add tone modifier
    tone_modifiers = {
        "engaging": "Giọng văn hấp dẫn, tạo tương tác, hỏi người xem.",
        "professional": "Giọng văn chuyên nghiệp, đáng tin cậy.",
        "casual": "Giọng văn thân thiện, gần gũi như nói chuyện.",
        "dramatic": "Giọng văn kịch tính, tạo cảm xúc mạnh.",
    }
    tone_hint = tone_modifiers.get(preset.tone, "")

    # Add structure hint from sections
    section_hint = f"Cấu trúc video: {' → '.join(preset.sections)}"

    # Add platform hint
    platform_hints = {
        "tiktok": "Phù hợp TikTok/Reels — hook 2s đầu phải cực mạnh, tempo nhanh.",
        "youtube": "Phù hợp YouTube — có thể dài hơn, phân tích sâu.",
        "instagram": "Phù hợp Instagram — visual đẹp, caption ngắn gọn.",
    }
    platform_hint = platform_hints.get(preset.platform, "")

    prompt_parts = [base_prompt, tone_hint, section_hint, platform_hint]
    if book_summary:
        prompt_parts.append(f"\nTóm tắt sách:\n{book_summary[:500]}")

    return "\n".join(p for p in prompt_parts if p)
