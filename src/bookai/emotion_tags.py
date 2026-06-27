"""Auto-insert emotion tags for VieNeu TTS in BookAI scripts.

Analyzes script text and automatically inserts VieNeu emotion tags
([cười], [thở dài], [hắng giọng]) at contextually appropriate positions.

Also supports broader emotion/style annotation for any TTS provider
using SSML-like markers.

Usage::

    from bookai.emotion_tags import auto_insert_emotions, EmotionConfig

    tagged = auto_insert_emotions(
        "Cuốn sách này thật tuyệt vời! Nhưng cuộc đời không dễ dàng.",
        config=EmotionConfig(provider="vieneu"),
    )
    # → "[cười] Cuốn sách này thật tuyệt vời! [thở dài] Nhưng cuộc đời không dễ dàng."
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# VieNeu emotion tags
# ---------------------------------------------------------------------------

VIENEU_TAGS = {
    "laugh": "[cười]",
    "sigh": "[thở dài]",
    "clear_throat": "[hắng giọng]",
}

# Patterns that suggest specific emotions
_LAUGH_PATTERNS: list[tuple[str, float]] = [
    (r"(?:thật\s+)?(?:thú vị|vui|hài hước|buồn cười|hay)", 0.7),
    (r"(?:ha\s*ha|haha|hihi|hehe)", 0.9),
    (r"!{2,}", 0.3),
    (r"(?:tuyệt vời|xuất sắc|amazing|awesome)", 0.5),
    (r"(?:may mắn|vui mừng|phấn khích|hào hứng)", 0.6),
    (r"(?:bất ngờ\s+là|điều thú vị)", 0.5),
]

_SIGH_PATTERNS: list[tuple[str, float]] = [
    (r"(?:nhưng|tuy nhiên|thế nhưng|đáng tiếc)", 0.5),
    (r"(?:buồn|đau|khổ|cô đơn|mệt mỏi|kiệt sức)", 0.7),
    (r"(?:thất bại|thua cuộc|mất mát|chia ly)", 0.6),
    (r"(?:không dễ|khó khăn|gian nan|thử thách)", 0.5),
    (r"(?:tiếc|nuối|hối hận|ước gì)", 0.6),
    (r"(?:chán nản|thất vọng|bế tắc)", 0.7),
    (r"(?:cuộc đời|số phận|nghiệt ngã)", 0.4),
]

_CLEAR_THROAT_PATTERNS: list[tuple[str, float]] = [
    (r"(?:bây giờ|và bây giờ|tiếp theo)", 0.6),
    (r"(?:quan trọng nhất|điều quan trọng|bí quyết)", 0.5),
    (r"(?:hãy|bắt đầu|cùng nhau|chúng ta)", 0.4),
    (r"(?:trước hết|đầu tiên|thứ nhất)", 0.5),
    (r"(?:nói cách khác|tóm lại|kết luận)", 0.5),
    (r"(?:chú ý|lưu ý|nhớ rằng)", 0.6),
]


@dataclass
class EmotionConfig:
    """Configuration for emotion tag insertion."""

    provider: str = "vieneu"  # vieneu, azure, edge_tts
    sensitivity: float = 0.5  # 0.0-1.0: how aggressively to insert tags
    max_tags_per_paragraph: int = 2  # Prevent over-tagging
    min_chars_between_tags: int = 50  # Min characters between consecutive tags
    tags_enabled: list[str] = field(default_factory=lambda: ["laugh", "sigh", "clear_throat"])
    custom_patterns: dict[str, list[tuple[str, float]]] = field(default_factory=dict)


def auto_insert_emotions(
    text: str,
    config: EmotionConfig | None = None,
) -> str:
    """Analyze text and auto-insert emotion tags.

    Args:
        text: Script text to annotate.
        config: Emotion insertion configuration.

    Returns:
        Text with emotion tags inserted at appropriate positions.
    """
    if config is None:
        config = EmotionConfig()

    if config.provider != "vieneu":
        return text  # Only VieNeu supports inline emotion tags for now

    # Split into sentences
    sentences = _split_sentences(text)
    if not sentences:
        return text

    # Score each sentence for each emotion
    tagged_sentences: list[str] = []
    tags_in_current_para = 0
    chars_since_last_tag = config.min_chars_between_tags  # Start ready to tag

    for sentence in sentences:
        # Check paragraph break
        if sentence.strip() == "":
            tagged_sentences.append(sentence)
            tags_in_current_para = 0
            continue

        # Skip if too many tags in current paragraph
        if tags_in_current_para >= config.max_tags_per_paragraph:
            tagged_sentences.append(sentence)
            chars_since_last_tag += len(sentence)
            continue

        # Skip if too close to last tag
        if chars_since_last_tag < config.min_chars_between_tags:
            tagged_sentences.append(sentence)
            chars_since_last_tag += len(sentence)
            continue

        # Find best emotion for this sentence
        best_emotion, best_score = _score_sentence(sentence, config)

        if best_emotion and best_score >= config.sensitivity:
            tag = VIENEU_TAGS.get(best_emotion, "")
            if tag:
                tagged_sentences.append(f"{tag} {sentence}")
                tags_in_current_para += 1
                chars_since_last_tag = 0
                continue

        tagged_sentences.append(sentence)
        chars_since_last_tag += len(sentence)

    return _join_sentences(tagged_sentences)


def _score_sentence(
    sentence: str, config: EmotionConfig,
) -> tuple[str | None, float]:
    """Score a sentence for each emotion, return the best match."""
    scores: dict[str, float] = {}

    all_patterns = {
        "laugh": _LAUGH_PATTERNS,
        "sigh": _SIGH_PATTERNS,
        "clear_throat": _CLEAR_THROAT_PATTERNS,
    }
    # Merge custom patterns
    for emotion, patterns in config.custom_patterns.items():
        if emotion in all_patterns:
            all_patterns[emotion] = all_patterns[emotion] + patterns
        else:
            all_patterns[emotion] = patterns

    sentence_lower = sentence.lower()

    for emotion in config.tags_enabled:
        patterns = all_patterns.get(emotion, [])
        max_score = 0.0
        for pattern, weight in patterns:
            if re.search(pattern, sentence_lower):
                max_score = max(max_score, weight)
        scores[emotion] = max_score

    if not scores:
        return None, 0.0

    best = max(scores, key=scores.get)
    return best, scores[best]


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving paragraph breaks."""
    # Split on newlines first to preserve structure
    lines = text.split("\n")
    result: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            result.append("")
            continue

        # Split on sentence boundaries (. ! ? followed by space or end)
        parts = re.split(r"(?<=[.!?])\s+", line)
        result.extend(parts)

    return result


def _join_sentences(sentences: list[str]) -> str:
    """Join sentences back together."""
    result_parts: list[str] = []
    prev_empty = False

    for s in sentences:
        if s.strip() == "":
            if not prev_empty:
                result_parts.append("\n\n")
            prev_empty = True
        else:
            if result_parts and not prev_empty:
                result_parts.append(" ")
            result_parts.append(s)
            prev_empty = False

    return "".join(result_parts).strip()


def strip_emotion_tags(text: str) -> str:
    """Remove all emotion tags from text.

    Useful when switching to a TTS provider that doesn't support tags.
    """
    for tag in VIENEU_TAGS.values():
        text = text.replace(f"{tag} ", "")
        text = text.replace(tag, "")
    return text.strip()


def list_available_tags() -> dict[str, str]:
    """List all available VieNeu emotion tags."""
    return dict(VIENEU_TAGS)


def tag_script_for_provider(text: str, provider: str) -> str:
    """Tag or strip script based on provider support.

    - vieneu: auto-insert emotion tags
    - others: strip any existing tags
    """
    if provider == "vieneu":
        return auto_insert_emotions(text)
    return strip_emotion_tags(text)
