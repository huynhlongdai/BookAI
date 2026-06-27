"""AI-powered social metadata generator.

Generates platform-optimized titles, captions, hashtags, and descriptions
for TikTok, Instagram, YouTube Shorts, and Facebook.

Usage::

    from bookai.social_metadata import generate_metadata, MetadataRequest
    req = MetadataRequest(book_title="Atomic Habits", script_text="...")
    meta = generate_metadata(req)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class MetadataRequest:
    """Input for metadata generation."""
    book_title: str = ""
    author: str = ""
    script_text: str = ""
    content_type: str = "book_review"  # book_review, quote, listicle, storyboard
    language: str = "vi"  # vi, en
    platforms: list[str] = field(default_factory=lambda: ["tiktok", "instagram", "youtube"])


@dataclass
class PlatformMetadata:
    """Metadata optimized for a specific platform."""
    platform: str = ""
    title: str = ""
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    description: str = ""

    @property
    def full_caption(self) -> str:
        tags = " ".join(f"#{t}" for t in self.hashtags)
        return f"{self.caption}\n\n{tags}" if tags else self.caption

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "title": self.title,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "description": self.description,
            "full_caption": self.full_caption,
        }


@dataclass
class SocialMetadata:
    """Complete social metadata for all platforms."""
    platforms: dict[str, PlatformMetadata] = field(default_factory=dict)
    ok: bool = True
    error: str = ""

    def get(self, platform: str) -> PlatformMetadata | None:
        return self.platforms.get(platform)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error": self.error,
            "platforms": {k: v.to_dict() for k, v in self.platforms.items()},
        }


# Platform constraints
PLATFORM_LIMITS = {
    "tiktok": {"title_max": 150, "caption_max": 2200, "hashtag_max": 10},
    "instagram": {"title_max": 0, "caption_max": 2200, "hashtag_max": 30},
    "youtube": {"title_max": 100, "caption_max": 5000, "hashtag_max": 15},
    "facebook": {"title_max": 0, "caption_max": 63206, "hashtag_max": 10},
}

# Default hashtags by language
DEFAULT_HASHTAGS = {
    "vi": {
        "book_review": ["sách", "reviewsách", "sáchhay", "đọcsách", "booktok", "bookai"],
        "quote": ["quoteoftheday", "cảmhứng", "sáchhay", "tríchdẫn", "booktok"],
        "listicle": ["top5", "sáchhay", "phảiđọc", "bookrecommendation", "bookai"],
        "storyboard": ["booktrailer", "sáchhay", "booktok", "bookstagram", "bookai"],
    },
    "en": {
        "book_review": ["bookreview", "bookstagram", "booktok", "reading", "mustread", "bookai"],
        "quote": ["bookquotes", "quoteoftheday", "inspiration", "booktok", "reading"],
        "listicle": ["booklist", "topbooks", "mustread", "bookrecommendation", "bookai"],
        "storyboard": ["booktrailer", "booktok", "bookstagram", "reading", "bookai"],
    },
}


def _extract_keywords(text: str, max_words: int = 5) -> list[str]:
    """Extract simple keywords from text."""
    words = re.findall(r'\b[a-zA-ZÀ-ỹ]{4,}\b', text.lower())
    seen = set()
    keywords = []
    for w in words:
        if w not in seen and len(keywords) < max_words:
            seen.add(w)
            keywords.append(w)
    return keywords


def generate_metadata_simple(req: MetadataRequest) -> SocialMetadata:
    """Generate metadata using templates (no LLM required).

    This is the fallback when no LLM is configured.
    """
    lang = req.language if req.language in DEFAULT_HASHTAGS else "vi"
    content_type = req.content_type if req.content_type in DEFAULT_HASHTAGS[lang] else "book_review"
    base_hashtags = DEFAULT_HASHTAGS[lang][content_type]

    # Add book-specific hashtags
    book_tag = re.sub(r'[^a-zA-ZÀ-ỹ0-9]', '', req.book_title.lower())
    extra_tags = [book_tag] if book_tag else []

    result = SocialMetadata()

    for platform in req.platforms:
        limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["tiktok"])
        hashtags = (extra_tags + base_hashtags)[:limits["hashtag_max"]]

        if lang == "vi":
            title = f"📚 {req.book_title}" if req.book_title else "📚 Sách Hay"
            caption = f"📖 {req.book_title}"
            if req.author:
                caption += f" — {req.author}"
            caption += "\n\n"
            if req.script_text:
                caption += req.script_text[:300] + "..." if len(req.script_text) > 300 else req.script_text
            desc = f"Review sách {req.book_title} bởi {req.author}. " if req.author else f"Review sách {req.book_title}. "
            desc += "Được tạo bởi BookAI."
        else:
            title = f"📚 {req.book_title}" if req.book_title else "📚 Book Review"
            caption = f"📖 {req.book_title}"
            if req.author:
                caption += f" by {req.author}"
            caption += "\n\n"
            if req.script_text:
                caption += req.script_text[:300] + "..." if len(req.script_text) > 300 else req.script_text
            desc = f"Book review: {req.book_title} by {req.author}. " if req.author else f"Book review: {req.book_title}. "
            desc += "Generated by BookAI."

        # Enforce platform limits
        if limits["title_max"] > 0:
            title = title[:limits["title_max"]]
        caption = caption[:limits["caption_max"]]

        result.platforms[platform] = PlatformMetadata(
            platform=platform,
            title=title,
            caption=caption,
            hashtags=hashtags,
            description=desc,
        )

    return result


def generate_metadata(
    req: MetadataRequest,
    llm_config: object | None = None,
) -> SocialMetadata:
    """Generate social metadata, using LLM if available, else templates.

    Args:
        req: Metadata request with book info and target platforms
        llm_config: Optional LLMConfig for AI-powered generation

    Returns:
        SocialMetadata with per-platform optimized content
    """
    if llm_config is not None:
        try:
            from bookai.llm_providers import generate_json

            prompt = (
                f"Generate social media metadata for a book video.\n"
                f"Book: {req.book_title}\n"
                f"Author: {req.author}\n"
                f"Content type: {req.content_type}\n"
                f"Language: {req.language}\n"
                f"Script excerpt: {req.script_text[:500]}\n\n"
                f"For each platform ({', '.join(req.platforms)}), generate:\n"
                f"- title (short, catchy)\n"
                f"- caption (engaging, platform-appropriate length)\n"
                f"- hashtags (list of strings, no # prefix)\n"
                f"- description (for YouTube/SEO)\n\n"
                f"Return JSON: {{\"platforms\": {{\"tiktok\": {{...}}, ...}}}}"
            )

            ok, data, error = generate_json(prompt, llm_config)
            if ok and data and "platforms" in data:
                result = SocialMetadata()
                for platform, meta in data["platforms"].items():
                    if platform in req.platforms:
                        result.platforms[platform] = PlatformMetadata(
                            platform=platform,
                            title=meta.get("title", ""),
                            caption=meta.get("caption", ""),
                            hashtags=meta.get("hashtags", []),
                            description=meta.get("description", ""),
                        )
                return result
            else:
                logger.warning(f"LLM metadata generation failed: {error}, using templates")
        except Exception as e:
            logger.warning(f"LLM metadata error: {e}, using templates")

    return generate_metadata_simple(req)
