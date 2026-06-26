"""Data models for BookAI pipeline."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SourceFormat(str, Enum):
    """Supported input formats."""

    EPUB = "epub"
    PDF = "pdf"
    TEXT = "text"
    MARKDOWN = "markdown"
    IMAGE = "image"
    AUDIO = "audio"


# ---------------------------------------------------------------------------
# Video models (Phase 1 upgrade, inspired by MoneyPrinterTurbo)
# ---------------------------------------------------------------------------


class VideoAspect(str, Enum):
    """Supported video aspect ratios."""

    PORTRAIT = "9:16"    # TikTok, Instagram Reels, YouTube Shorts
    LANDSCAPE = "16:9"   # YouTube, Facebook
    SQUARE = "1:1"       # Instagram Feed

    def to_resolution(self) -> tuple[int, int]:
        mapping = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
        return mapping[self.value]


class TransitionMode(str, Enum):
    """Video transition effects between clips."""

    NONE = "none"
    FADE_IN = "fade_in"
    FADE_OUT = "fade_out"
    SLIDE_IN = "slide_in"
    SLIDE_OUT = "slide_out"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    SHUFFLE = "shuffle"


class VideoConcatMode(str, Enum):
    """How stock video clips are ordered."""

    RANDOM = "random"
    SEQUENTIAL = "sequential"
    MATCH_SCRIPT = "match_script"


class BgmMode(str, Enum):
    """Background music mode."""

    NONE = "none"
    RANDOM = "random"
    SPECIFIC = "specific"


class SubtitlePosition(str, Enum):
    """Subtitle vertical position."""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"
    CUSTOM = "custom"


class ChunkLabel(str, Enum):
    """Content labels for analyzed chunks."""

    QUOTE = "quote"
    SUMMARY = "summary"
    STORY = "story"
    EXAMPLE = "example"
    INSIGHT = "insight"
    HOOK = "hook"
    TIP = "tip"
    CONTROVERSIAL = "controversial"


class BookMetadata(BaseModel):
    """Metadata extracted from a book file."""

    title: str
    author: str = "Unknown"
    publisher: str = ""
    language: str = "vi"
    chapters: int = 0
    source_format: SourceFormat = SourceFormat.TEXT
    file_path: str = ""


class Chunk(BaseModel):
    """A semantic unit of text from a book."""

    chunk_id: str = Field(default_factory=lambda: "")
    book_title: str = ""
    chapter: int = 0
    chapter_title: str = ""
    position: int = 0
    text: str
    token_count: int = 0

    def model_post_init(self, _context: object) -> None:
        if not self.chunk_id:
            import hashlib

            self.chunk_id = hashlib.md5(self.text.encode()).hexdigest()[:12]
        if self.token_count == 0:
            self.token_count = len(self.text.split())


class AnalyzedChunk(BaseModel):
    """A chunk with AI-generated analysis."""

    chunk: Chunk
    labels: list[ChunkLabel] = Field(default_factory=list)
    viral_score: float = 0.0
    summary: str = ""
    reason: str = ""


class BookResult(BaseModel):
    """Complete result from processing a book."""

    metadata: BookMetadata
    markdown: str = ""
    chunks: list[Chunk] = Field(default_factory=list)
    analyzed: list[AnalyzedChunk] = Field(default_factory=list)
    top_quotes: list[AnalyzedChunk] = Field(default_factory=list)
    top_hooks: list[AnalyzedChunk] = Field(default_factory=list)
    chapter_summaries: list[str] = Field(default_factory=list)

    def get_top_content(self, n: int = 10) -> list[AnalyzedChunk]:
        """Return top N chunks by viral score."""
        return sorted(self.analyzed, key=lambda x: x.viral_score, reverse=True)[:n]

    def get_by_label(self, label: ChunkLabel) -> list[AnalyzedChunk]:
        """Filter analyzed chunks by label."""
        return [a for a in self.analyzed if label in a.labels]
