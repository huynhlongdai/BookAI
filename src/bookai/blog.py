"""Blog/SEO content generator for BookAI.

Generates SEO-optimized Vietnamese blog articles from analyzed book chunks.
Output: 1500-2000 word articles with H1/H2 structure, affiliate links, and schema markup.

Usage::

    from bookai.blog import generate_blog_post, BlogPost

    post = generate_blog_post(
        result, affiliate_link="https://shope.ee/xxx",
        api_key="...", base_url="...", model="..."
    )
    print(post.html)        # full HTML with schema markup
    print(post.markdown)    # raw markdown
    post.save("review_dac_nhan_tam.html")
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .models import AnalyzedChunk, BookMetadata, BookResult, ChunkLabel
from .settings import get_api_key as _cfg_api_key, get_base_url as _cfg_base_url, get_model as _cfg_model, get_system_prompt as _cfg_prompt

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class BlogPost:
    """A generated SEO blog post."""

    title: str                       # H1 — e.g. "Review Đắc Nhân Tâm: 10 bài học thay đổi cuộc đời"
    slug: str                        # URL slug
    meta_description: str            # 150-160 chars for Google
    markdown: str                    # Full article in Markdown
    affiliate_link: str = ""
    book_title: str = ""
    author: str = ""
    word_count: int = 0
    sections: list[str] = field(default_factory=list)

    @property
    def html(self) -> str:
        """Convert markdown to basic HTML with schema markup."""
        return _markdown_to_html(self.markdown, self)

    def save(self, output_path: str | Path, fmt: str = "html") -> Path:
        """Save post to file. fmt: 'html' or 'md'."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "md":
            output_path.write_text(self.markdown, encoding="utf-8")
        else:
            output_path.write_text(self.html, encoding="utf-8")
        return output_path


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_blog_post(
    result: BookResult,
    affiliate_link: str = "",
    shopee_link: str = "",
    tiki_link: str = "",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str = "gpt-4o-mini",
    use_ai: bool = True,
    top_n_chunks: int = 15,
) -> BlogPost:
    """Generate a full SEO blog post from a BookResult.

    Args:
        result: BookResult from the analysis pipeline.
        affiliate_link: Primary affiliate URL (TikTok Shop or Shopee).
        shopee_link: Shopee URL (if different from primary).
        tiki_link: Tiki URL.
        api_key: LLM API key (uses mock/template if absent).
        base_url: OpenAI-compatible base URL.
        model: Model name.
        use_ai: If True, use LLM to generate prose. If False, template only.
        top_n_chunks: Number of top chunks to include.

    Returns:
        BlogPost instance.
    """
    meta = result.metadata
    top = result.get_top_content(top_n_chunks)

    # Group chunks by label
    quotes = [a for a in top if ChunkLabel.QUOTE in a.labels][:5]
    insights = [a for a in top if ChunkLabel.INSIGHT in a.labels][:5]
    tips = [a for a in top if ChunkLabel.TIP in a.labels][:5]
    stories = [a for a in top if ChunkLabel.STORY in a.labels][:3]
    hooks = [a for a in top if ChunkLabel.HOOK in a.labels][:2]

    if use_ai and (api_key or base_url):
        try:
            return _generate_with_ai(
                meta, top, quotes, insights, tips, stories, hooks,
                affiliate_link=affiliate_link,
                shopee_link=shopee_link,
                tiki_link=tiki_link,
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
        except Exception:
            pass  # fall through to template

    return _generate_template(
        meta, top, quotes, insights, tips, stories, hooks,
        affiliate_link=affiliate_link,
        shopee_link=shopee_link,
        tiki_link=tiki_link,
    )


# ---------------------------------------------------------------------------
# Template-based generation (offline)
# ---------------------------------------------------------------------------


def _generate_template(
    meta: BookMetadata,
    top: list[AnalyzedChunk],
    quotes: list[AnalyzedChunk],
    insights: list[AnalyzedChunk],
    tips: list[AnalyzedChunk],
    stories: list[AnalyzedChunk],
    hooks: list[AnalyzedChunk],
    affiliate_link: str = "",
    shopee_link: str = "",
    tiki_link: str = "",
) -> BlogPost:
    """Build a structured blog post from templates (no LLM needed)."""

    title = f"Review {meta.title}: Bài học quan trọng nhất & Có nên đọc không?"
    slug = _slugify(meta.title)
    meta_desc = (
        f"Review chi tiết {meta.title} của {meta.author}. "
        f"Những bài học hay nhất, câu trích dẫn đáng nhớ và lý do tại sao bạn nên đọc cuốn sách này."
    )[:160]

    sections: list[str] = []
    parts: list[str] = []

    # Hero section
    intro = (
        f"# {title}\n\n"
        f"> {meta_desc}\n\n"
    )
    if affiliate_link:
        intro += (
            f"👉 **[Mua {meta.title} ngay tại đây]({affiliate_link})** "
            f"(giao hàng nhanh, giá tốt)\n\n"
        )
    parts.append(intro)
    sections.append("Giới thiệu")

    # Hook opener
    if hooks:
        hook_text = hooks[0].chunk.text[:300]
        parts.append(
            f"## Tại sao bạn nên đọc {meta.title}?\n\n"
            f"{hook_text}\n\n"
            f"Đây chỉ là một trong nhiều điều bất ngờ mà **{meta.title}** "
            f"của {meta.author} mang lại. "
            f"Hãy cùng khám phá những bài học đáng giá nhất từ cuốn sách này.\n\n"
        )
        sections.append("Tại sao nên đọc")

    # Key insights
    if insights:
        parts.append(f"## Những bài học cốt lõi từ {meta.title}\n\n")
        for i, chunk_data in enumerate(insights[:5], 1):
            text = chunk_data.chunk.text[:400]
            summary = chunk_data.summary or text[:100]
            parts.append(
                f"### {i}. {summary[:80]}\n\n"
                f"{text}\n\n"
            )
        sections.append("Bài học cốt lõi")

    # Tips section
    if tips:
        parts.append(f"## Mẹo thực hành từ {meta.title}\n\n")
        for tip in tips[:4]:
            text = tip.chunk.text[:300]
            parts.append(f"**💡 {tip.summary or 'Mẹo hay'}:** {text}\n\n")
        sections.append("Mẹo thực hành")

    # Quotes section
    if quotes:
        parts.append(f"## Những câu trích dẫn hay nhất trong {meta.title}\n\n")
        for q in quotes[:5]:
            q_text = q.chunk.text[:200].strip()
            parts.append(f"> *\"{q_text}\"*\n>\n> — {meta.author}, *{meta.title}*\n\n")
        sections.append("Câu trích dẫn hay")

    # Story section
    if stories:
        parts.append(f"## Câu chuyện đáng nhớ trong {meta.title}\n\n")
        parts.append(stories[0].chunk.text[:500] + "\n\n")
        sections.append("Câu chuyện")

    # Who should read
    parts.append(
        f"## Ai nên đọc {meta.title}?\n\n"
        f"Cuốn sách **{meta.title}** đặc biệt phù hợp với:\n\n"
        "- 📌 Những ai đang tìm kiếm sự thay đổi trong cuộc sống\n"
        "- 📌 Người muốn phát triển kỹ năng và tư duy\n"
        "- 📌 Bạn trẻ muốn định hướng con đường phía trước\n"
        "- 📌 Những ai yêu thích sách phát triển bản thân\n\n"
    )
    sections.append("Ai nên đọc")

    # CTA / Buy section
    cta_section = f"## Mua {meta.title} ở đâu giá tốt nhất?\n\n"
    if affiliate_link or shopee_link or tiki_link:
        cta_section += f"Bạn có thể mua **{meta.title}** tại:\n\n"
        if affiliate_link:
            cta_section += (
                f"- 🛒 **[TikTok Shop — Giá tốt + giao nhanh]({affiliate_link})**\n"
            )
        if shopee_link:
            cta_section += f"- 🛍️ **[Shopee]({shopee_link})** — Nhiều voucher hấp dẫn\n"
        if tiki_link:
            cta_section += f"- 📦 **[Tiki]({tiki_link})** — Giao hàng trong ngày\n"
        cta_section += (
            "\n> 💬 *Lưu ý: Đây là link affiliate. Khi bạn mua qua link này, "
            "chúng tôi nhận được hoa hồng nhỏ nhưng giá bán không thay đổi.*\n\n"
        )
    else:
        cta_section += (
            f"Tìm **{meta.title}** tại các nhà sách online như Shopee, Tiki, "
            f"TikTok Shop hoặc nhà sách gần nhà bạn.\n\n"
        )
    parts.append(cta_section)
    sections.append("Mua sách")

    # Conclusion
    parts.append(
        f"## Kết luận\n\n"
        f"**{meta.title}** của {meta.author} là một cuốn sách xứng đáng có trong tủ sách "
        f"của bất kỳ ai muốn phát triển bản thân. "
        f"Với những bài học thực tế và câu chuyện minh họa sinh động, "
        f"đây là một trong những cuốn sách hay nhất bạn nên đọc.\n\n"
        f"*Bạn đã đọc {meta.title} chưa? Hãy để lại bình luận bên dưới!* 👇\n\n"
    )
    sections.append("Kết luận")

    markdown = "".join(parts)
    word_count = len(markdown.split())

    return BlogPost(
        title=title,
        slug=slug,
        meta_description=meta_desc,
        markdown=markdown,
        affiliate_link=affiliate_link,
        book_title=meta.title,
        author=meta.author,
        word_count=word_count,
        sections=sections,
    )


# ---------------------------------------------------------------------------
# AI-based generation
# ---------------------------------------------------------------------------

_BLOG_PROMPT = """\
Bạn là blogger sách chuyên nghiệp tại Việt Nam, chuyên viết bài review giúp độc giả ra quyết định mua sách.

Thông tin sách:
- Tên: {title}
- Tác giả: {author}

Các đoạn hay nhất từ sách:
{chunks_text}

YÊU CẦU BÀI VIẾT — dựa trên nghiên cứu về bài blog convert cao:

1. CẤU TRÚC (theo mô hình Khẳng định → Bằng chứng → Ví dụ → Bài học):
   - H1: tiêu đề gây tò mò, chứa keyword, ≤12 từ
   - Mở bài: 1 câu hỏi tu từ + 1 khẳng định táo bạo (KHÔNG bắt đầu bằng "Cuốn sách này...")
   - H2 "Vì sao [title] khác biệt?" — dùng số liệu/nghiên cứu từ sách
   - H2 "X bài học cốt lõi" — mỗi H3 theo cấu trúc: Tiêu đề → Giải thích → Ví dụ thực tế → Quote ngắn từ sách
   - H2 "Ai nên đọc [title]?" — cụ thể (đừng nói "ai cũng nên đọc")
   - H2 "Kết luận" + CTA mua sách
2. ĐỘ DÀI: 1500-2000 từ
3. GIỌNG VĂN: thân mật + thực hành (76% câu chủ động, dùng "bạn/tôi")
4. SEO: keyword "{title}" xuất hiện tự nhiên 5-8 lần; đặt keyword ngay đầu bài
5. THUẬT NGỮ: Giữ nguyên thuật ngữ chuyên ngành từ sách, KHÔNG diễn giải lại
6. FORMAT: Markdown thuần túy
7. CTA: nếu affiliate_link="{affiliate_link}" khác rỗng, chèn link mua sách vào cuối
8. KHÔNG copy nguyên xi — diễn giải lại bằng lời của bạn

Trả về MARKDOWN hoàn chỉnh (không thêm chú thích).
"""


def _generate_with_ai(
    meta: BookMetadata,
    top: list[AnalyzedChunk],
    quotes: list[AnalyzedChunk],
    insights: list[AnalyzedChunk],
    tips: list[AnalyzedChunk],
    stories: list[AnalyzedChunk],
    hooks: list[AnalyzedChunk],
    affiliate_link: str,
    shopee_link: str,
    tiki_link: str,
    api_key: str | None,
    base_url: str | None,
    model: str,
) -> BlogPost:
    """Use LLM to write a natural blog post."""
    import httpx

    # Build chunks text for prompt
    selected = (quotes[:3] + insights[:3] + tips[:2] + stories[:2] + hooks[:1])
    chunks_text = "\n\n---\n\n".join(
        f"[{', '.join(l.value for l in a.labels)}] Score: {a.viral_score:.1f}\n{a.chunk.text[:400]}"
        for a in selected[:10]
    )

    prompt = _BLOG_PROMPT.format(
        title=meta.title,
        author=meta.author,
        chunks_text=chunks_text,
        affiliate_link=affiliate_link or "",
    )

    _blog_system = _cfg_prompt("blog") or (
        "Bạn là blogger và nhà văn chuyên viết bài review sách SEO cho độc giả Việt Nam, "
        "phong cách Spiderum/Ybox — thân mật, có chiều sâu, thực tế.\n\n"
        "NGUYÊN TẮC VIẾT:\n"
        "1. Mỗi đoạn văn HOÀN CHỈNH: câu chủ đề + triển khai + kết — không câu đứt giữa chừng\n"
        "2. Lập luận: Khẳng định → Bằng chứng → Ví dụ → Bài học áp dụng\n"
        "3. Dùng 'bạn' xuyên suốt — kết nối với người đọc\n"
        "4. Câu văn chủ động là chính, tránh bị động thụ động\n"
        "5. KHÔNG bắt đầu bằng 'Cuốn sách này...' — giết curiosity ngay từ đầu\n"
        "6. Mỗi heading phải gợi tò mò, không chỉ mô tả thuần túy\n"
        "7. Trả về Markdown hoàn chỉnh, không thêm ghi chú hay giải thích ngoài bài viết"
    )

    # Auto-load từ settings nếu caller không truyền
    api_key = api_key or _cfg_api_key()
    base_url = base_url or _cfg_base_url()
    model = model or _cfg_model()

    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _blog_system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 3000,
    }
    url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"

    for attempt in range(3):
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()
            markdown = data["choices"][0]["message"]["content"].strip()
            break
        except Exception:
            if attempt == 2:
                raise

    # Extract title from first H1
    title_match = re.search(r"^#\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1) if title_match else f"Review {meta.title}"
    slug = _slugify(meta.title)
    word_count = len(markdown.split())

    # Build meta description from first paragraph
    paragraphs = [p.strip() for p in markdown.split("\n\n") if p.strip() and not p.startswith("#")]
    meta_desc = (paragraphs[0][:160] if paragraphs else title[:160])

    return BlogPost(
        title=title,
        slug=slug,
        meta_description=meta_desc,
        markdown=markdown,
        affiliate_link=affiliate_link,
        book_title=meta.title,
        author=meta.author,
        word_count=word_count,
    )


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="{meta_description}">
<title>{title}</title>
<script type="application/ld+json">
{schema_json}
</script>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        max-width: 800px; margin: 0 auto; padding: 24px; line-height: 1.7;
        color: #1a1a2e; }}
h1 {{ font-size: 2em; line-height: 1.3; margin-bottom: 8px; }}
h2 {{ font-size: 1.4em; margin-top: 2em; color: #312e81; }}
h3 {{ font-size: 1.15em; color: #4c1d95; }}
blockquote {{ border-left: 4px solid #7c3aed; margin: 1.5em 0;
               padding: 12px 20px; background: #f5f3ff;
               border-radius: 0 8px 8px 0; font-style: italic; }}
a {{ color: #7c3aed; font-weight: 600; }}
a:hover {{ color: #5b21b6; }}
.cta-box {{ background: #f5f3ff; border: 2px solid #7c3aed;
            border-radius: 8px; padding: 20px; text-align: center; margin: 2em 0; }}
</style>
</head>
<body>
{body}
</body>
</html>"""

_SCHEMA_TEMPLATE = {
    "@context": "https://schema.org",
    "@type": "Review",
    "itemReviewed": {
        "@type": "Book",
        "name": "",
        "author": {"@type": "Person", "name": ""},
    },
    "reviewRating": {
        "@type": "Rating",
        "ratingValue": "4.5",
        "bestRating": "5",
    },
    "author": {"@type": "Organization", "name": "BookAI Review"},
}


def _markdown_to_html(markdown: str, post: BlogPost) -> str:
    """Convert markdown to HTML (basic, no external deps)."""
    lines = markdown.split("\n")
    html_lines: list[str] = []
    in_blockquote = False

    for line in lines:
        # Headings
        if line.startswith("### "):
            html_lines.append(f"<h3>{_inline_md(line[4:])}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{_inline_md(line[3:])}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{_inline_md(line[2:])}</h1>")
        # Blockquotes
        elif line.startswith("> "):
            if not in_blockquote:
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{_inline_md(line[2:])}</p>")
        else:
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            # Lists
            if line.startswith("- ") or line.startswith("* "):
                html_lines.append(f"<li>{_inline_md(line[2:])}</li>")
            elif line.strip():
                html_lines.append(f"<p>{_inline_md(line)}</p>")

    if in_blockquote:
        html_lines.append("</blockquote>")

    body = "\n".join(html_lines)

    schema = dict(_SCHEMA_TEMPLATE)
    schema["itemReviewed"]["name"] = post.book_title
    schema["itemReviewed"]["author"]["name"] = post.author

    return _HTML_TEMPLATE.format(
        title=post.title,
        meta_description=post.meta_description,
        schema_json=json.dumps(schema, ensure_ascii=False, indent=2),
        body=body,
    )


def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, links) to HTML."""
    # Links [text](url)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    # Bold **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic *text*
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # Code `text`
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    # Simple ASCII-like slug (Vietnamese-safe)
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text[:60]
