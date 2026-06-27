"""BookAI Library — persistent book catalog + analysis history.

Manages a local JSON-based library tracking all processed books,
their analysis results, and generated content.

Storage layout (default: ~/.bookai/ or /opt/bookai/data/):
    library.json          — index of all books
    books/<isbn|slug>/
        results.json      — full BookResult
        content.json      — ContentPack (if generated)
        meta.json         — quick metadata for listing

Usage::

    from bookai.library import BookLibrary

    lib = BookLibrary()
    lib.save_book(book_result)
    entries = lib.list_books()
    result = lib.load_book("nhìn-thấu-lòng-người")
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_DATA_DIR = Path.home() / ".bookai"
VPS_DATA_DIR = Path("/opt/bookai/data")


def get_data_dir() -> Path:
    """Return the data directory, preferring VPS path if it exists."""
    if VPS_DATA_DIR.parent.exists():
        return VPS_DATA_DIR
    return DEFAULT_DATA_DIR


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class LibraryEntry:
    """Lightweight metadata for a book in the library index."""

    slug: str                   # URL-friendly id, also folder name
    title: str
    author: str = ""
    source_format: str = ""
    chapters: int = 0
    chunks_total: int = 0
    chunks_analyzed: int = 0
    avg_viral_score: float = 0.0
    top_score: float = 0.0
    label_counts: dict = field(default_factory=dict)
    has_content: bool = False   # ContentPack saved?
    analyzed_at: str = ""       # ISO timestamp
    file_size_kb: int = 0
    notes: str = ""

    @property
    def analyzed_at_display(self) -> str:
        if not self.analyzed_at:
            return "—"
        try:
            dt = datetime.fromisoformat(self.analyzed_at)
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return self.analyzed_at

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> LibraryEntry:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------


class BookLibrary:
    """Persistent book catalog stored as JSON files on disk."""

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        self.books_dir = self.data_dir / "books"
        self._index_path = self.data_dir / "library.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, LibraryEntry] = {}
        self._load_index()

    # ── Index I/O ────────────────────────────────────────────

    def _load_index(self) -> None:
        if self._index_path.exists():
            try:
                data = json.loads(self._index_path.read_text(encoding="utf-8"))
                self._entries = {
                    k: LibraryEntry.from_dict(v)
                    for k, v in data.items()
                }
            except Exception:
                self._entries = {}

    def _save_index(self) -> None:
        data = {k: v.to_dict() for k, v in self._entries.items()}
        self._index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── CRUD ─────────────────────────────────────────────────

    def save_book(self, result: object, notes: str = "") -> LibraryEntry:
        """Save a BookResult to the library.

        Args:
            result: BookResult from the analysis pipeline.
            notes: Optional notes about this book.

        Returns:
            LibraryEntry saved in the index.
        """
        meta = result.metadata  # type: ignore[attr-defined]
        analyzed = result.analyzed  # type: ignore[attr-defined]
        chunks = result.chunks  # type: ignore[attr-defined]

        slug = _slugify(meta.title)
        book_dir = self.books_dir / slug
        book_dir.mkdir(parents=True, exist_ok=True)

        # Save full results.json
        results_path = book_dir / "results.json"
        results_path.write_text(
            json.dumps(result.model_dump(), ensure_ascii=False, indent=2),  # type: ignore[attr-defined]
            encoding="utf-8",
        )

        # Build entry
        avg = sum(a.viral_score for a in analyzed) / len(analyzed) if analyzed else 0
        top = max((a.viral_score for a in analyzed), default=0)
        label_counts: dict[str, int] = {}
        for a in analyzed:
            for lbl in a.labels:
                label_counts[lbl.value] = label_counts.get(lbl.value, 0) + 1

        entry = LibraryEntry(
            slug=slug,
            title=meta.title,
            author=meta.author,
            source_format=meta.source_format.value if hasattr(meta.source_format, "value") else str(meta.source_format),
            chapters=meta.chapters,
            chunks_total=len(chunks),
            chunks_analyzed=len(analyzed),
            avg_viral_score=round(avg, 2),
            top_score=round(top, 2),
            label_counts=label_counts,
            has_content=False,
            analyzed_at=datetime.utcnow().isoformat(),
            file_size_kb=results_path.stat().st_size // 1024,
            notes=notes,
        )
        self._entries[slug] = entry
        self._save_index()
        return entry

    def save_content(self, slug: str, pack: object) -> None:
        """Save a ContentPack alongside a book."""
        book_dir = self.books_dir / slug
        book_dir.mkdir(parents=True, exist_ok=True)
        content_path = book_dir / "content.json"
        content_path.write_text(
            json.dumps(pack.model_dump(), ensure_ascii=False, indent=2),  # type: ignore[attr-defined]
            encoding="utf-8",
        )
        if slug in self._entries:
            self._entries[slug].has_content = True
            self._save_index()

    def load_result(self, slug: str) -> object | None:
        """Load a BookResult from disk. Returns None if not found."""
        from .models import BookResult

        results_path = self.books_dir / slug / "results.json"
        if not results_path.exists():
            return None
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
            return BookResult(**data)
        except Exception:
            return None

    def load_content(self, slug: str) -> dict | None:
        """Load ContentPack dict from disk."""
        content_path = self.books_dir / slug / "content.json"
        if not content_path.exists():
            return None
        try:
            return json.loads(content_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def delete_book(self, slug: str) -> bool:
        """Delete a book and all its data."""
        book_dir = self.books_dir / slug
        if book_dir.exists():
            shutil.rmtree(book_dir)
        removed = self._entries.pop(slug, None)
        self._save_index()
        return removed is not None

    def update_notes(self, slug: str, notes: str) -> None:
        """Update notes for a book."""
        if slug in self._entries:
            self._entries[slug].notes = notes
            self._save_index()

    # ── Queries ──────────────────────────────────────────────

    def list_books(self, sort_by: str = "analyzed_at", reverse: bool = True) -> list[LibraryEntry]:
        """Return all library entries sorted by field."""
        entries = list(self._entries.values())
        try:
            entries.sort(key=lambda e: getattr(e, sort_by, ""), reverse=reverse)
        except Exception:
            pass
        return entries

    def get_entry(self, slug: str) -> LibraryEntry | None:
        return self._entries.get(slug)

    def search(self, query: str) -> list[LibraryEntry]:
        """Simple case-insensitive title/author search."""
        q = query.lower().strip()
        return [
            e for e in self._entries.values()
            if q in e.title.lower() or q in e.author.lower() or q in e.notes.lower()
        ]

    @property
    def count(self) -> int:
        return len(self._entries)

    def stats(self) -> dict:
        """Overall library statistics."""
        entries = list(self._entries.values())
        if not entries:
            return {"total": 0}
        return {
            "total": len(entries),
            "total_chunks": sum(e.chunks_analyzed for e in entries),
            "avg_score": round(sum(e.avg_viral_score for e in entries) / len(entries), 2),
            "with_content": sum(1 for e in entries if e.has_content),
            "formats": list({e.source_format for e in entries if e.source_format}),
        }


# ---------------------------------------------------------------------------
# Prompt manager
# ---------------------------------------------------------------------------


BUILTIN_PROMPTS: dict[str, dict] = {
    "analysis": {
        "name": "Phân tích nội dung (Analysis)",
        "description": "Prompt AI phân tích đoạn text, gắn nhãn và chấm viral score",
        "editable": True,
        "template": """Bạn là chuyên gia phân tích nội dung sách cho affiliate marketing.
Phân tích đoạn text và đánh giá tiềm năng viral TikTok.

Đoạn text:
---
{text}
---

Trả về JSON:
{{
  "labels": ["quote"|"summary"|"story"|"example"|"insight"|"hook"|"tip"|"controversial"],
  "viral_score": <0.0-10.0>,
  "summary": "<tóm tắt 1-2 câu>",
  "reason": "<lý do viral score>"
}}

Tiêu chí (+2 điểm mỗi): Curiosity, Emotion, Actionable, Controversy, Relatability
Chỉ trả JSON, không giải thích.""",
    },
    "radio_rewrite": {
        "name": "Radio Script Rewrite",
        "description": "LLM viết lại script radio từ nội dung sách",
        "editable": True,
        "template": """Bạn là một người dẫn chương trình radio sách chuyên nghiệp tại Việt Nam.
Dựa trên nội dung sách dưới đây, hãy VIẾT LẠI (không sao chép) thành script radio tự nhiên.

Nội dung từ sách:
---
{content}
---

Yêu cầu:
- Thời lượng: ~{duration_minutes} phút khi đọc
- Cấu trúc: Hook (tò mò, gây sốc) → Body (kể chuyện, phân tích) → CTA (mua sách)
- Giọng: Gần gũi, tự nhiên như đang kể chuyện cho bạn nghe
- KHÔNG đọc nguyên văn từ sách — PHẢI viết lại bằng lời của bạn

Trả về JSON:
{{"hook": "...", "body": "...", "cta": "...", "title": "..."}}""",
    },
    "blog_post": {
        "name": "Blog Review SEO",
        "description": "Viết bài review blog chuẩn SEO",
        "editable": True,
        "template": """Bạn là blogger sách chuyên nghiệp. Viết bài review SEO cho:
Tên sách: {title}
Tác giả: {author}
Nội dung tiêu biểu:
{chunks_text}

Yêu cầu: 1500-2000 từ, H1/H2/H3, keyword "{title}" 5-8 lần, CTA mua sách.
Link affiliate: {affiliate_link}
Trả về Markdown thuần túy.""",
    },
    "caption_tiktok": {
        "name": "TikTok Caption SEO",
        "description": "Tối ưu caption TikTok 3 lớp keyword",
        "editable": True,
        "template": """Viết caption TikTok SEO cho video về sách "{title}".
Nội dung video: {hook}

Yêu cầu:
- Mở đầu bằng keyword chính (nói trong 3s đầu)
- 150-200 ký tự
- 3-5 hashtag liên quan
- Kết bằng CTA: "Link sách ở giỏ hàng 👇"
Trả về text caption hoàn chỉnh.""",
    },
}


class PromptManager:
    """Manage analysis and generation prompts with user customization."""

    def __init__(self, data_dir: str | Path | None = None):
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        self._prompts_path = self.data_dir / "prompts.json"
        self._custom: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if self._prompts_path.exists():
            try:
                self._custom = json.loads(
                    self._prompts_path.read_text(encoding="utf-8")
                )
            except Exception:
                self._custom = {}

    def _save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._prompts_path.write_text(
            json.dumps(self._custom, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, key: str) -> str:
        """Return current prompt template (custom override or builtin)."""
        if key in self._custom:
            return self._custom[key].get("template", "")
        return BUILTIN_PROMPTS.get(key, {}).get("template", "")

    def set(self, key: str, template: str) -> None:
        """Override a prompt template."""
        self._custom[key] = {"template": template, "updated_at": datetime.utcnow().isoformat()}
        self._save()

    def reset(self, key: str) -> None:
        """Reset a prompt to its builtin default."""
        self._custom.pop(key, None)
        self._save()

    def list_prompts(self) -> list[dict]:
        """Return all prompts with is_custom flag."""
        result = []
        for key, builtin in BUILTIN_PROMPTS.items():
            is_custom = key in self._custom
            result.append({
                "key": key,
                "name": builtin["name"],
                "description": builtin["description"],
                "template": self.get(key),
                "is_custom": is_custom,
                "editable": builtin.get("editable", True),
            })
        return result

    def reset_all(self) -> None:
        """Reset all custom prompts to builtins."""
        self._custom = {}
        self._save()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^\w-]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")[:60]
