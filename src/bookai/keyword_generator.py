"""LLM-based keyword generation for stock video search.

Extracts visual search terms from book review scripts in any language,
automatically translating to English for stock API compatibility.

Inspired by MoneyPrinterTurbo's generate_terms() but enhanced for
BookAI's multilingual book-review pipeline.

Usage:
    from bookai.keyword_generator import generate_keywords, KeywordConfig

    config = KeywordConfig(
        llm_api_key="sk-...",
        llm_base_url="https://api.openai.com/v1",
        llm_model="gpt-4o-mini",
    )
    terms = generate_keywords(
        script_text="Cuốn sách này kể về hành trình...",
        book_title="Atomic Habits",
        book_genre="self-help",
        config=config,
    )
    # → ["building habits", "morning routine", "productivity workspace", ...]
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class KeywordConfig:
    """Configuration for keyword generation."""

    # LLM settings
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.7

    # Keyword generation
    num_terms: int = 8
    match_script_order: bool = True
    max_retries: int = 3

    # Translation
    auto_translate: bool = True
    source_language: str = "auto"  # "auto", "vi", "zh", "ja", "ko", etc.

    # Fallback
    fallback_to_regex: bool = True


# ---------------------------------------------------------------------------
# Language detection (lightweight)
# ---------------------------------------------------------------------------

# Vietnamese-specific characters
_VI_CHARS = set("àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
                "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ")

# CJK character ranges
_CJK_RANGES = [
    (0x4E00, 0x9FFF),    # CJK Unified
    (0x3400, 0x4DBF),    # CJK Extension A
    (0x3040, 0x309F),    # Hiragana
    (0x30A0, 0x30FF),    # Katakana
    (0xAC00, 0xD7AF),    # Korean Hangul
]


def detect_language(text: str) -> str:
    """Detect the primary language of text.

    Returns: "en", "vi", "zh", "ja", "ko", or "other".
    """
    if not text:
        return "en"

    # Sample first 500 chars
    sample = text[:500]
    char_counts = {"vi": 0, "cjk": 0, "ko": 0, "ja": 0, "ascii": 0, "other": 0}

    for ch in sample:
        if ch in _VI_CHARS:
            char_counts["vi"] += 1
        elif any(lo <= ord(ch) <= hi for lo, hi in _CJK_RANGES):
            code = ord(ch)
            if 0xAC00 <= code <= 0xD7AF:
                char_counts["ko"] += 1
            elif 0x3040 <= code <= 0x309F or 0x30A0 <= code <= 0x30FF:
                char_counts["ja"] += 1
            else:
                char_counts["cjk"] += 1
        elif ch.isascii() and ch.isalpha():
            char_counts["ascii"] += 1

    total_alpha = sum(char_counts.values()) or 1

    if char_counts["vi"] / total_alpha > 0.05:
        return "vi"
    if char_counts["ko"] / total_alpha > 0.1:
        return "ko"
    if char_counts["ja"] / total_alpha > 0.1:
        return "ja"
    if char_counts["cjk"] / total_alpha > 0.1:
        return "zh"
    return "en"


# ---------------------------------------------------------------------------
# LLM-based keyword generation
# ---------------------------------------------------------------------------

def _build_keyword_prompt(
    script_text: str,
    book_title: str,
    book_genre: str,
    num_terms: int,
    match_script_order: bool,
    detected_language: str,
) -> str:
    """Build the LLM prompt for keyword extraction."""

    if match_script_order:
        ordering_rule = (
            "6. Keep search terms in the same chronological order as the script "
            "narration — earlier terms should describe earlier visual moments.\n"
            "7. Distribute terms evenly across the script timeline."
        )
        goal = (
            f"Generate exactly {num_terms} chronological English stock-video search "
            "terms that follow the order of topics in the book review script."
        )
    else:
        ordering_rule = ""
        goal = (
            f"Generate exactly {num_terms} English stock-video search terms "
            "based on the book review script."
        )

    lang_note = ""
    if detected_language != "en":
        lang_map = {"vi": "Vietnamese", "zh": "Chinese", "ja": "Japanese", "ko": "Korean"}
        lang_name = lang_map.get(detected_language, detected_language)
        lang_note = (
            f"\nIMPORTANT: The script is in {lang_name}. You MUST translate all "
            "concepts to English search terms. Do NOT return any non-English words."
        )

    return f"""# Role: Book Video Search Terms Generator

## Goal:
{goal}

## Constraints:
1. Return a JSON array of English strings ONLY. No other text.
2. Each search term: 1-3 words describing a VISUAL scene or concept.
3. ALL terms MUST be in English — translate from any other language.
4. Terms should describe visual scenes suitable for stock video footage.
5. Include at least 1-2 book/reading-related terms (bookshelf, reading, library, etc.)
{ordering_rule}
{lang_note}

## Visual Mapping Guide:
- Abstract concepts → concrete visuals (e.g., "kiên trì" → "climbing mountain")
- Emotions → visual metaphors (e.g., "buồn" → "rain window")
- Actions → stock footage scenes (e.g., "học tập" → "student studying")
- Book genres:
  - Self-help → "sunrise motivation", "person achieving goal"
  - Fiction → "dramatic landscape", "mysterious forest"
  - Business → "office teamwork", "city skyline"
  - Science → "laboratory research", "technology innovation"

## Context:
### Book Title: {book_title or "(not specified)"}
### Book Genre: {book_genre or "(not specified)"}

### Script:
{script_text[:3000]}

## Output Format:
Return ONLY a JSON array like:
["{num_terms} English search terms here"]

Example for a Vietnamese book review about habits:
["building good habits", "morning routine workout", "productivity workspace",
"person writing journal", "sunrise motivation", "bookshelf reading",
"lifestyle change progress", "achievement celebration"]
""".strip()


def _call_llm(prompt: str, config: KeywordConfig) -> str:
    """Call LLM API and return the response text.

    Uses urllib (stdlib) for maximum compatibility — no openai package required.
    """
    import ssl
    import urllib.request

    url = config.llm_base_url.rstrip("/") + "/chat/completions"
    payload = json.dumps({
        "model": config.llm_model,
        "messages": [
            {"role": "system", "content": "You are a stock video search term generator. "
             "You always respond with a JSON array of English search terms."},
            {"role": "user", "content": prompt},
        ],
        "temperature": config.llm_temperature,
        "max_tokens": 500,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.llm_api_key}",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    ctx = ssl.create_default_context()

    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    return data["choices"][0]["message"]["content"].strip()


def _parse_terms_response(response: str) -> list[str]:
    """Parse JSON array from LLM response, handling various formats."""
    # Try direct JSON parse
    cleaned = response.strip()

    # Strip markdown code fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines if they are fences
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        terms = json.loads(cleaned)
        if isinstance(terms, list) and all(isinstance(t, str) for t in terms):
            return terms
    except json.JSONDecodeError:
        pass

    # Try to find JSON array in response
    match = re.search(r'\[.*?\]', cleaned, re.DOTALL)
    if match:
        try:
            terms = json.loads(match.group())
            if isinstance(terms, list) and all(isinstance(t, str) for t in terms):
                return terms
        except json.JSONDecodeError:
            pass

    return []


def generate_keywords_llm(
    script_text: str,
    book_title: str = "",
    book_genre: str = "",
    config: KeywordConfig | None = None,
) -> list[str]:
    """Generate English stock-video search terms from a book script using LLM.

    Args:
        script_text: The book review/summary script (any language).
        book_title: Title of the book.
        book_genre: Genre (self-help, fiction, business, etc.)
        config: KeywordConfig with LLM settings.

    Returns:
        List of English search terms for stock video APIs.
    """
    if config is None:
        config = KeywordConfig()

    if not config.llm_api_key:
        logger.warning("No LLM API key configured, falling back to regex")
        if config.fallback_to_regex:
            return generate_keywords_regex(script_text, book_title, config.num_terms)
        return []

    # Detect language
    detected_lang = detect_language(script_text) if config.source_language == "auto" else config.source_language
    logger.info(f"Detected script language: {detected_lang}")

    # Build prompt
    prompt = _build_keyword_prompt(
        script_text=script_text,
        book_title=book_title,
        book_genre=book_genre,
        num_terms=config.num_terms,
        match_script_order=config.match_script_order,
        detected_language=detected_lang,
    )

    # Try LLM with retries
    for attempt in range(config.max_retries):
        try:
            response = _call_llm(prompt, config)
            terms = _parse_terms_response(response)

            if terms:
                logger.info(f"LLM generated {len(terms)} search terms: {terms}")
                return terms

            logger.warning(f"Attempt {attempt + 1}: LLM returned invalid format: {response[:200]}")

        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}: LLM call failed: {e}")

    # Fallback to regex
    if config.fallback_to_regex:
        logger.warning("All LLM attempts failed, falling back to regex extraction")
        return generate_keywords_regex(script_text, book_title, config.num_terms)

    return []


# ---------------------------------------------------------------------------
# Keyword translation
# ---------------------------------------------------------------------------

def translate_keywords_to_english(
    keywords: list[str],
    config: KeywordConfig | None = None,
) -> list[str]:
    """Translate a list of keywords from any language to English.

    If keywords are already English, returns them unchanged.
    Uses LLM for translation with fallback to basic detection.
    """
    if config is None:
        config = KeywordConfig()

    if not keywords:
        return []

    # Check if already English
    combined = " ".join(keywords)
    lang = detect_language(combined)
    if lang == "en":
        return keywords

    if not config.llm_api_key:
        logger.warning("No LLM API key for translation, returning original keywords")
        return keywords

    prompt = f"""Translate these stock video search terms to English.
Return ONLY a JSON array of translated English strings.
Each term should be 1-3 words, suitable for searching stock footage.

Input terms: {json.dumps(keywords, ensure_ascii=False)}

Output: JSON array of English translations."""

    try:
        response = _call_llm(prompt, config)
        translated = _parse_terms_response(response)
        if translated and len(translated) == len(keywords):
            logger.info(f"Translated {len(translated)} keywords to English")
            return translated
        elif translated:
            logger.warning(f"Translation count mismatch: {len(keywords)} → {len(translated)}")
            return translated
    except Exception as e:
        logger.warning(f"Translation failed: {e}")

    return keywords


# ---------------------------------------------------------------------------
# Regex-based fallback
# ---------------------------------------------------------------------------

# Common visual terms mapped from Vietnamese book-related concepts
_VI_VISUAL_MAP = {
    r"sách|đọc sách|quyển sách": ["reading book", "bookshelf library"],
    r"hành trình|cuộc sống": ["life journey", "person walking path"],
    r"thành công|mục tiêu": ["achieving goal", "success celebration"],
    r"tình yêu|yêu thương": ["love couple", "romantic sunset"],
    r"gia đình|con cái": ["happy family", "family together"],
    r"thiên nhiên|rừng|biển": ["nature landscape", "forest mountain"],
    r"công nghệ|AI|khoa học": ["technology innovation", "science research"],
    r"kinh doanh|doanh nghiệp": ["business meeting", "office teamwork"],
    r"sáng tạo|nghệ thuật": ["creative workspace", "art painting"],
    r"sức khỏe|thể thao": ["fitness exercise", "healthy lifestyle"],
    r"lịch sử|chiến tranh": ["historical monument", "old photographs"],
    r"trinh thám|bí ẩn": ["mysterious dark corridor", "detective clues"],
    r"phiêu lưu|khám phá": ["adventure exploration", "travel journey"],
    r"tâm lý|cảm xúc": ["emotional expression", "person contemplating"],
    r"học tập|giáo dục": ["student studying", "classroom education"],
}

# Genre-to-visual mapping
_GENRE_TERMS = {
    "self-help": ["sunrise motivation", "person journaling", "growth mindset"],
    "fiction": ["dramatic landscape", "storytelling campfire", "open book reading"],
    "business": ["city skyline", "office collaboration", "success graph"],
    "science": ["laboratory research", "technology screen", "space universe"],
    "history": ["ancient civilization", "historical documents", "old castle"],
    "romance": ["romantic sunset beach", "couple walking", "flowers garden"],
    "thriller": ["dark mysterious street", "suspense shadows", "detective search"],
    "biography": ["portrait photography", "life milestones", "person achievement"],
    "philosophy": ["contemplation nature", "ancient wisdom books", "thinking person"],
    "children": ["colorful playground", "children reading", "cartoon adventure"],
}


def generate_keywords_regex(
    script_text: str,
    book_title: str = "",
    num_terms: int = 8,
) -> list[str]:
    """Fallback keyword extraction using regex patterns.

    Works without LLM by matching Vietnamese patterns to English visual terms.
    """
    terms = set()

    # 1. Match Vietnamese patterns
    for pattern, visual_terms in _VI_VISUAL_MAP.items():
        if re.search(pattern, script_text, re.IGNORECASE):
            terms.update(visual_terms)

    # 2. Extract English words/phrases already in script
    english_phrases = re.findall(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', script_text)
    for phrase in english_phrases[:5]:
        if len(phrase.split()) <= 3:
            terms.add(phrase.lower())

    # 3. Extract technical terms
    tech_terms = re.findall(
        r'\b(?:AI|Machine Learning|Deep Learning|NLP|Data Science|'
        r'Blockchain|Cloud|IoT|VR|AR|Startup|Marketing|SEO)\b',
        script_text, re.IGNORECASE,
    )
    terms.update(t.lower() for t in tech_terms)

    # 4. Add book title as search term
    if book_title:
        # Clean title for search
        clean_title = re.sub(r'[^\w\s]', '', book_title).strip()
        if clean_title and len(clean_title.split()) <= 4:
            terms.add(clean_title.lower())

    # 5. Always include some book-related terms
    base_terms = ["person reading book", "bookshelf close-up", "knowledge education"]
    terms.update(base_terms[:max(1, num_terms - len(terms))])

    # Convert to list and limit
    result = list(terms)
    random.shuffle(result)
    return result[:num_terms]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_keywords(
    script_text: str,
    book_title: str = "",
    book_genre: str = "",
    config: KeywordConfig | None = None,
) -> list[str]:
    """Generate English search terms for stock video from a book script.

    Primary method: LLM-based extraction with automatic language detection
    and translation. Falls back to regex patterns if LLM is unavailable.

    Args:
        script_text: Book review/summary script in any language.
        book_title: Title of the book.
        book_genre: Genre for better visual matching.
        config: KeywordConfig with LLM and generation settings.

    Returns:
        List of English search terms suitable for Pexels/Pixabay/Coverr.
    """
    if config is None:
        config = KeywordConfig()

    if not script_text.strip():
        return ["reading book", "education knowledge", "bookshelf library"]

    # Try LLM first
    if config.llm_api_key:
        terms = generate_keywords_llm(script_text, book_title, book_genre, config)
        if terms:
            return terms

    # Fallback to regex
    return generate_keywords_regex(script_text, book_title, config.num_terms)


# ---------------------------------------------------------------------------
# Script-section keyword mapping (for match_script_order mode)
# ---------------------------------------------------------------------------

def generate_section_keywords(
    script_sections: list[dict],
    book_title: str = "",
    book_genre: str = "",
    terms_per_section: int = 2,
    config: KeywordConfig | None = None,
) -> list[dict]:
    """Generate keywords for each section of a script.

    Args:
        script_sections: List of {"text": "...", "start": 0.0, "end": 5.0}
        terms_per_section: Keywords per section.

    Returns:
        List of {"section_index": 0, "text": "...", "keywords": [...], "start": 0.0, "end": 5.0}
    """
    if config is None:
        config = KeywordConfig()

    if not config.llm_api_key:
        # Regex fallback per section
        results = []
        for i, section in enumerate(script_sections):
            terms = generate_keywords_regex(
                section.get("text", ""),
                book_title,
                terms_per_section,
            )
            results.append({
                "section_index": i,
                "text": section.get("text", ""),
                "keywords": terms,
                "start": section.get("start", 0.0),
                "end": section.get("end", 0.0),
            })
        return results

    # Build combined prompt for all sections
    sections_text = "\n".join(
        f"[Section {i+1}] ({s.get('start', 0):.1f}s - {s.get('end', 0):.1f}s): "
        f"{s.get('text', '')[:200]}"
        for i, s in enumerate(script_sections)
    )

    prompt = f"""# Role: Section-Level Video Search Terms Generator

## Goal:
For each numbered section of this book review script, generate exactly
{terms_per_section} English stock-video search terms.

## Constraints:
1. Return a JSON array of arrays: [[section1_terms], [section2_terms], ...]
2. Each term: 1-3 English words describing a VISUAL scene
3. Terms MUST be in English (translate from any language)
4. Match visual concepts to each section's specific content

## Book: {book_title or "(untitled)"} — Genre: {book_genre or "(unknown)"}

## Sections:
{sections_text}

## Output:
Return ONLY a JSON array of arrays. Example for 3 sections:
[["term1a", "term1b"], ["term2a", "term2b"], ["term3a", "term3b"]]
"""

    for attempt in range(config.max_retries):
        try:
            response = _call_llm(prompt, config)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            all_terms = json.loads(cleaned)
            if isinstance(all_terms, list) and len(all_terms) == len(script_sections):
                results = []
                for i, section in enumerate(script_sections):
                    section_terms = all_terms[i] if i < len(all_terms) else []
                    if not isinstance(section_terms, list):
                        section_terms = []
                    results.append({
                        "section_index": i,
                        "text": section.get("text", ""),
                        "keywords": [str(t) for t in section_terms],
                        "start": section.get("start", 0.0),
                        "end": section.get("end", 0.0),
                    })
                logger.info(f"Generated section keywords for {len(results)} sections")
                return results

        except Exception as e:
            logger.warning(f"Section keyword attempt {attempt + 1} failed: {e}")

    # Fallback: generate for each section individually
    results = []
    for i, section in enumerate(script_sections):
        terms = generate_keywords_regex(
            section.get("text", ""),
            book_title,
            terms_per_section,
        )
        results.append({
            "section_index": i,
            "text": section.get("text", ""),
            "keywords": terms,
            "start": section.get("start", 0.0),
            "end": section.get("end", 0.0),
        })
    return results
